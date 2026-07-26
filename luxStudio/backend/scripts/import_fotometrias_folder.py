"""Import backend/fotometrias files and link them to BBDD_Fotometrias.xlsx rows."""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402

from app.database import BACKEND_DIR, FOTOMETRIAS_DIR, SessionLocal  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.models import Difusor, Fotometria, Gama, LedType, Lente, Manufacturer, ValidCombination  # noqa: E402
from app.core.text_utils import norm  # noqa: E402
from app.salvi_lighting import parse_ldt  # noqa: E402


def _file_key(value: str) -> str:
    return norm(value).rstrip(".")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", norm(value)).strip("-")


def _get_or_create(db, model, name: str):
    name = norm(name)
    obj = db.query(model).filter(model.name == name).first()
    if obj is None:
        obj = model(name=name)
        db.add(obj)
        db.flush()
    return obj


def _manufacturer(db) -> Manufacturer:
    obj = db.query(Manufacturer).filter(Manufacturer.name == "Salvi").first()
    if obj is None:
        obj = Manufacturer(name="Salvi")
        db.add(obj)
        db.flush()
    return obj


def _ensure_valid_combination(db, gama_id: int, difusor_id: int, lente_id: int, led_type_id: int | None) -> None:
    exists = (
        db.query(ValidCombination)
        .filter(
            ValidCombination.gama_id == gama_id,
            ValidCombination.difusor_id == difusor_id,
            ValidCombination.lente_id == lente_id,
            ValidCombination.led_type_id == led_type_id,
        )
        .first()
    )
    if exists is None:
        db.add(ValidCombination(
            gama_id=gama_id,
            difusor_id=difusor_id,
            lente_id=lente_id,
            led_type_id=led_type_id,
        ))


def _read_rows(xlsx: Path) -> list[dict]:
    wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)
    ws = wb["Hoja1"]
    seen = set()
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        ensayo, gama, difusor, cri, lente, ok, led_type, _date = (list(row) + [None] * 8)[:8]
        item = {
            "ensayo": norm(ensayo),
            "gama": norm(gama),
            "difusor": norm(difusor),
            "cri": int(cri) if cri is not None else 70,
            "lente": norm(lente),
            "led_type": norm(led_type),
        }
        if not item["ensayo"] or not item["gama"] or not item["difusor"] or not item["lente"]:
            continue
        key = tuple(item.values())
        if key not in seen:
            seen.add(key)
            rows.append(item)
    return rows


def _catalog_code(row: dict, duplicated_ensayos: set[str]) -> str:
    if row["ensayo"] not in duplicated_ensayos:
        return row["ensayo"]
    suffix = "__".join(_slug(row[k]) for k in ("gama", "difusor", "lente", "led_type") if row[k])
    return f"{row['ensayo']}__{suffix}"[:255]


def import_folder(xlsx: Path, photometry_dir: Path, default_mf_origen: float = 1.0) -> dict:
    xlsx = xlsx.resolve()
    photometry_dir = photometry_dir.resolve()
    files = {_file_key(path.stem): path for path in photometry_dir.iterdir() if path.is_file()}
    rows = _read_rows(xlsx)
    duplicated_ensayos = {ensayo for ensayo, count in Counter(r["ensayo"] for r in rows).items() if count > 1}

    db = SessionLocal()
    stats = {"created": 0, "updated": 0, "skipped_missing_file": 0, "skipped_parse": 0, "rows": len(rows)}
    parsed_cache: dict[Path, dict] = {}
    try:
        manufacturer = _manufacturer(db)
        next_id = (db.query(func.max(Fotometria.id)).scalar() or 0) + 1
        for row in rows:
            path = files.get(_file_key(row["ensayo"]))
            if path is None:
                stats["skipped_missing_file"] += 1
                continue
            try:
                parsed = parsed_cache.setdefault(path, parse_ldt(str(path)))
            except Exception:
                stats["skipped_parse"] += 1
                continue

            lamp = parsed["lamp_sets"][0]
            power = float(lamp["wattage"]) or 1.0
            flux = float(lamp["flux_lm"])
            gama = _get_or_create(db, Gama, row["gama"])
            difusor = _get_or_create(db, Difusor, row["difusor"])
            lente = _get_or_create(db, Lente, row["lente"])
            led_type = _get_or_create(db, LedType, row["led_type"]) if row["led_type"] else None
            _ensure_valid_combination(db, gama.id, difusor.id, lente.id, led_type.id if led_type else None)

            code = _catalog_code(row, duplicated_ensayos)
            relative = path.relative_to(BACKEND_DIR).as_posix()
            lum = db.query(Fotometria).filter(Fotometria.fotometria == code).one_or_none()
            if lum is None:
                lum = Fotometria(id=next_id, fotometria=code, created_at=datetime.now(timezone.utc))
                next_id += 1
                db.add(lum)
                stats["created"] += 1
            else:
                stats["updated"] += 1

            lum.manufacturer_id = manufacturer.id
            lum.type = row["gama"]
            lum.optic_family = row["lente"]
            lum.gama_id = gama.id
            lum.difusor_id = difusor.id
            lum.lente_id = lente.id
            lum.led_type_id = led_type.id if led_type else None
            lum.name = f"{row['gama']} {row['lente']} {row['difusor']} {row['led_type']}".strip()
            lum.power = power
            lum.cct = 4000
            lum.cri = row["cri"]
            lum.flux = flux
            lum.efficiency = round(flux / power, 1) if power > 0 else 0
            lum.LORL = float(parsed["LORL"])
            lum.isym = int(parsed["Isym"])
            lum.photometric_path = relative
            lum.mf_origen = default_mf_origen
            lum.updated_at = datetime.now(timezone.utc)

        db.commit()
    finally:
        db.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, default=ROOT.parent / "BBDD_Fotometrias.xlsx")
    parser.add_argument("--photometry-dir", type=Path, default=FOTOMETRIAS_DIR)
    parser.add_argument(
        "--default-mf-origen", type=float, default=1.0,
        help="Maintenance factor already baked into the LDTs (default 1.0: raw photometry).",
    )
    args = parser.parse_args()
    stats = import_folder(args.xlsx, args.photometry_dir, default_mf_origen=args.default_mf_origen)
    print(stats)


if __name__ == "__main__":
    main()
