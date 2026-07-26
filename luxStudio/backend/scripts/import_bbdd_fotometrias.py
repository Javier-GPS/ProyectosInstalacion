"""Import the photometric catalog from BBDD_Fotometrias.xlsx.

This script is idempotent — re-running it does not create duplicate
rows. It:

1. Reads the ``Hoja1`` sheet of the xlsx (8 columns: ``ENSAYO ORIGEN``,
   ``GAMA``, ``DIFUSOR``, ``CRI``, ``LENTE``, ``OK``, ``LED TYPE``,
   ``DATE`` — only the first 5 are used in PR1).
2. UPSERTs each distinct value into ``gamas`` / ``difusores`` /
   ``lentes`` / ``led_types`` (the names are normalised with
   ``strip().upper()`` to make the catalog case-insensitive).
3. UPSERTs every distinct ``(gama, difusor, lente, led_type)`` tuple
   into ``valid_combinations`` (the 4-tuple has a UNIQUE constraint).
4. **Does not** create rows in ``luminaires`` — those are created when
   the corresponding photometric file (``.ldt``) is uploaded by the
   admin and associated to a ``fotometria`` code.
5. Writes ``fotometria_mapping.csv`` next to the xlsx with one row per
   ``(fotometria, gama, difusor, lente, led_type, expected_ldt)`` so the
   admin can quickly associate incoming LDTs to existing catalog rows.

Usage:
    python scripts/import_bbdd_fotometrias.py
    python scripts/import_bbdd_fotometrias.py --xlsx path/to/BBDD_Fotometrias.xlsx
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Make ``app`` importable when the script is run from any cwd.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402

from app.core.text_utils import norm  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Difusor,
    Gama,
    LedType,
    Lente,
    ValidCombination,
)


def _get_or_create(db, model, **fields) -> int:
    """Return the id of an existing row, creating it if necessary."""
    name = fields["name"]
    if not name:
        raise ValueError(f"Cannot create {model.__name__} with empty name")
    instance = db.query(model).filter(model.name == name).first()
    if instance is None:
        instance = model(**fields)
        db.add(instance)
        db.flush()
    return instance.id


def import_xlsx(xlsx_path: Path) -> dict:
    print(f"Loading {xlsx_path}…")
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb["Hoja1"]

    db = SessionLocal()
    stats = {
        "rows_read": 0,
        "rows_skipped": 0,
        "gamas_added": 0,
        "difusores_added": 0,
        "lentes_added": 0,
        "led_types_added": 0,
        "valid_combinations_added": 0,
        "fotometrias": [],
    }
    # Track VC tuples we have already added *in this run* (the xlsx
    # contains duplicate (gama, difusor, lente, led_type) tuples
    # across different ``ensayo_origen`` rows; a single combination
    # must only be inserted once). The DB UNIQUE constraint would
    # catch duplicates at flush time, but the cleaner approach is
    # to short-circuit before the INSERT.
    seen_vc: set[tuple[int, int, int, int | None]] = set()
    try:
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or all(cell is None for cell in row[:5]):
                stats["rows_skipped"] += 1
                continue
            ensayo, gama, difusor, cri, lente, ok, led_type, _date = (list(row) + [None] * 8)[:8]
            ensayo = norm(ensayo)
            gama_name = norm(gama)
            difusor_name = norm(difusor)
            lente_name = norm(lente)
            led_name = norm(led_type)
            if not ensayo or not gama_name or not difusor_name or not lente_name:
                stats["rows_skipped"] += 1
                continue

            # UPSERT dimensions.
            gama_id = _get_or_create(db, Gama, name=gama_name)
            difusor_id = _get_or_create(db, Difusor, name=difusor_name)
            lente_id = _get_or_create(db, Lente, name=lente_name)
            led_id = _get_or_create(db, LedType, name=led_name) if led_name else None

            # UPSERT valid_combination.
            vc_key = (gama_id, difusor_id, lente_id, led_id)
            if vc_key in seen_vc:
                pass
            else:
                existing_vc = (
                    db.query(ValidCombination)
                    .filter(
                        ValidCombination.gama_id == gama_id,
                        ValidCombination.difusor_id == difusor_id,
                        ValidCombination.lente_id == lente_id,
                        ValidCombination.led_type_id == led_id,
                    )
                    .first()
                )
                if existing_vc is None:
                    db.add(ValidCombination(
                        gama_id=gama_id,
                        difusor_id=difusor_id,
                        lente_id=lente_id,
                        led_type_id=led_id,
                    ))
                    stats["valid_combinations_added"] += 1
                seen_vc.add(vc_key)

            # Detect "added vs. existing" deltas for the dimension tables
            # by counting rows before and after. We do this once at the
            # end (cheaper than querying per-row).
            stats["fotometrias"].append({
                "fotometria": ensayo,
                "gama": gama_name,
                "difusor": difusor_name,
                "lente": lente_name,
                "led_type": led_name or "",
                "cri": int(cri) if cri is not None else 70,
            })
            stats["rows_read"] += 1

        # Count distinct values in the dimension tables after the loop
        # and compare with the "wanted" set. The deltas (positive) tell
        # us how many new rows the script created.
        wanted_gamas = {f["gama"] for f in stats["fotometrias"]}
        wanted_difusores = {f["difusor"] for f in stats["fotometrias"]}
        wanted_lentes = {f["lente"] for f in stats["fotometrias"]}
        wanted_leds = {f["led_type"] for f in stats["fotometrias"] if f["led_type"]}

        stats["gamas_added"] = sum(
            1 for g in wanted_gamas
            if db.query(Gama).filter(Gama.name == g).count() == 1
        )
        stats["difusores_added"] = sum(
            1 for d in wanted_difusores
            if db.query(Difusor).filter(Difusor.name == d).count() == 1
        )
        stats["lentes_added"] = sum(
            1 for l in wanted_lentes
            if db.query(Lente).filter(Lente.name == l).count() == 1
        )
        stats["led_types_added"] = sum(
            1 for lt in wanted_leds
            if db.query(LedType).filter(LedType.name == lt).count() == 1
        )

        db.commit()
    finally:
        db.close()

    return stats


def write_mapping_csv(stats: dict, xlsx_path: Path) -> Path:
    csv_path = xlsx_path.with_name("fotometria_mapping.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["fotometria", "gama", "difusor", "lente", "led_type", "cri", "expected_ldt"],
        )
        writer.writeheader()
        for row in stats["fotometrias"]:
            row["expected_ldt"] = f"{row['fotometria']}.ldt"
            writer.writerow(row)
    return csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xlsx",
        type=Path,
        default=ROOT.parent / "BBDD_Fotometrias.xlsx",
        help="Path to BBDD_Fotometrias.xlsx (default: project root).",
    )
    args = parser.parse_args()

    if not args.xlsx.exists():
        raise SystemExit(f"xlsx not found: {args.xlsx}")

    stats = import_xlsx(args.xlsx)
    csv_path = write_mapping_csv(stats, args.xlsx)

    print("\n=== Resumen de import ===")
    print(f"  Filas leídas:           {stats['rows_read']}")
    print(f"  Filas saltadas:         {stats['rows_skipped']}")
    n_gamas = len({f['gama'] for f in stats['fotometrias']})
    n_difus = len({f['difusor'] for f in stats['fotometrias']})
    n_lent = len({f['lente'] for f in stats['fotometrias']})
    n_led = len({f['led_type'] for f in stats['fotometrias'] if f['led_type']})
    print(f"  Gamas en el xlsx:       {n_gamas}")
    print(f"  Difusores en el xlsx:   {n_difus}")
    print(f"  Lentes en el xlsx:      {n_lent}")
    print(f"  LED types en el xlsx:   {n_led}")
    print(f"  Combinaciones añadidas: {stats['valid_combinations_added']}")
    print(f"  Mapeo CSV escrito en:   {csv_path}")


if __name__ == "__main__":
    main()
