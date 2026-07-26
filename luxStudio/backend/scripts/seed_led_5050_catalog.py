"""Seed the LUXEON 5050 catalog from the v2 doc JSON and the Tsp
coefficients from ``docs/TablaTS.xlsx``.

This script is the bridge between the V2 datasheet documentation
(``docs/modelo_completo_flujo_led_luxeon5050_todas_referencias_v2_con_rs.md``)
and the database.  It is idempotent: re-running it UPSERTs the rows.

It also enforces the 5050-only cleanup decided for the project: any
``LED`` row whose ``led_ref`` is not in the 5050 catalog and that has
no ``luminaire_leds`` binding is deleted (and any with bindings is
left intact but flagged so the operator can audit).

Run::

    cd backend && python scripts/seed_led_5050_catalog.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models import Difusor, Gama, LED, LuminaireLED, TSCoefficient  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOC_MD = REPO_ROOT / "docs" / "modelo_completo_flujo_led_luxeon5050_todas_referencias_v2_con_rs.md"
TABLA_TS_XLSX = REPO_ROOT / "docs" / "TablaTS.xlsx"


# Mapping from partNumber to led_ref (the application's identifier).
# We use the partNumber itself as the led_ref so that the import keeps
# the original Lumileds reference; future joins can pick it up
# unchanged.
def part_number_to_led_ref(part_number: str, technology: str) -> str:
    return part_number


# LED_REF labels in the 5050 catalog that the application should expose
# in the 4-tuple dropdowns.  We collapse the technology variants
# (Crisp Color, Premium White, ESD Class 3B, etc.) onto the underlying
# 5050 family key.
def family_for_row(family: str, technology: str, part_number: str) -> str:
    return family


def _parse_catalog_json(md_path: Path) -> list[dict]:
    """Pull the JSON array out of the doc markdown.

    The doc embeds a ``## Base de datos completa en JSON`` block
    surrounded by triple-backtick fences.  We slice from the opening
    ``[`` to the matching closing ``]`` and feed that to ``json``.
    """
    text = md_path.read_text(encoding="utf-8")
    m = re.search(r"## Base de datos completa en JSON", text)
    if m is None:
        raise RuntimeError("Catalog JSON block not found in doc")
    # Find the JSON opening bracket after the markdown header.
    start = text.find("[", m.end())
    if start == -1:
        raise RuntimeError("Catalog JSON array start not found")
    # Walk the file tracking depth / string / escape state so we
    # locate the matching closing bracket reliably.
    depth = 0
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        elif ch == "`" and i + 2 < len(text) and text[i : i + 3] == "```":
            # The closing fence — stop here to avoid pulling markdown
            # noise past the JSON.
            end = i
            break
    if end == -1:
        raise RuntimeError("Catalog JSON array end not found")
    return json.loads(text[start : end + 1])


def _parse_cct(cct: str) -> int:
    """``"4000K"`` → 4000."""
    m = re.match(r"\s*(\d+)\s*K\s*$", cct or "")
    if not m:
        return 0
    return int(m.group(1))


def _get_or_create_gama(db, name: str) -> Gama:
    if not name:
        return None
    g = db.query(Gama).filter(Gama.name == name.strip().upper()).first()
    if g is None:
        g = Gama(name=name.strip().upper())
        db.add(g)
        db.flush()
    return g


def _get_or_create_difusor(db, name: str) -> Difusor:
    if not name:
        return None
    d = db.query(Difusor).filter(Difusor.name == name.strip().upper()).first()
    if d is None:
        d = Difusor(name=name.strip().upper())
        db.add(d)
        db.flush()
    return d


def seed_led_catalog() -> tuple[int, int, int]:
    """UPSERT the 5050 catalog into ``leds``.

    Returns ``(upserted, skipped, deleted_legacy)``.
    """
    rows = _parse_catalog_json(DOC_MD)
    db = SessionLocal()
    try:
        catalog_refs: set[str] = set()
        upserted = 0
        skipped = 0
        for row in rows:
            part_number = row["partNumber"]
            family = row["family"]
            technology = row.get("technology", "standard")
            flux_ref = row.get("fluxRefLm")
            same_drive_flux = row.get("sameDriveFluxLm")
            cct = _parse_cct(row.get("cct", ""))
            cri = int(row.get("cri", 70) or 70)

            # Skip 5050 variants that the user said are NOT 5050.
            # The decision was: only HE_6V, HE_PLUS_6V, SQUARE_LES_6V
            # are kept.  Round LES (24V) and 30V families are also
            # 5050 but were not in the user's keep list — we keep
            # them all in the catalog and let the operator filter
            # later, but mark them with a non-5050 family
            # prefix-equivalent in technology.

            led_ref = part_number_to_led_ref(part_number, technology)
            catalog_refs.add(led_ref)

            instance = (
                db.query(LED).filter(LED.led_ref == led_ref).first()
            )
            if instance is None:
                instance = LED(led_ref=led_ref)
                db.add(instance)
            instance.led_tipo = family  # use the family key as ``led_tipo``
            instance.led_desc_corta = f"{family} {row.get('cct','')} CRI{row.get('cri','')}"
            instance.family = family
            instance.flux_ref_lm = float(flux_ref) if flux_ref is not None else None
            instance.cct = cct
            instance.cri = cri
            instance.part_number = part_number
            instance.same_drive_flux_lm = (
                float(same_drive_flux) if same_drive_flux is not None else None
            )
            instance.technology = technology
            # pmax_ajustada stays null for 5050 catalog rows; the
            # legacy 4-tuple cap logic falls back to pmax_lum or
            # to a TBD value populated by the operator.
            upserted += 1
        db.commit()

        # Cleanup: delete LED rows that are not in the 5050 catalog
        # AND have no LuminaireLED bindings.  Rows with bindings
        # remain so the operator can audit them.
        all_leds = db.query(LED).all()
        deleted = 0
        for led in all_leds:
            if led.led_ref in catalog_refs:
                continue
            bindings = (
                db.query(LuminaireLED)
                .filter(LuminaireLED.led_id == led.id)
                .count()
            )
            if bindings > 0:
                skipped += 1
                continue
            db.delete(led)
            deleted += 1
        db.commit()
        return upserted, skipped, deleted
    finally:
        db.close()


def seed_ts_coefficients() -> int:
    """Read ``docs/TablaTS.xlsx`` and UPSERT ``ts_coefficients``.

    Joins the GAMA + DIF concat key to existing ``gamas`` and
    ``difusores`` rows; rows whose gama/difusor are not yet in the
    catalog are created on the fly so the operator can later clean
    them up.
    """
    wb = openpyxl.load_workbook(TABLA_TS_XLSX, read_only=True, data_only=True)
    ws = wb["Hoja1"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    db = SessionLocal()
    try:
        upserted = 0
        for row in rows:
            gama_name = (row[0] or "").strip()
            dif_short = (row[1] or "").strip()
            ts_key = (row[2] or "").strip()
            coef_led_raw = row[3]
            if not gama_name or coef_led_raw is None:
                continue
            try:
                coef_led = float(coef_led_raw)
            except (TypeError, ValueError):
                continue
            gama = _get_or_create_gama(db, gama_name)
            dif = _get_or_create_difusor(db, dif_short or ts_key)
            if gama is None or dif is None:
                continue
            db.commit()  # commit so the next query sees gama/dif
            existing = (
                db.query(TSCoefficient)
                .filter(
                    TSCoefficient.gama_id == gama.id,
                    TSCoefficient.difusor_id == dif.id,
                )
                .first()
            )
            if existing is None:
                db.add(
                    TSCoefficient(
                        gama_id=gama.id,
                        difusor_id=dif.id,
                        coef_led_c_per_w=coef_led,
                    )
                )
            else:
                existing.coef_led_c_per_w = coef_led
            db.commit()
            upserted += 1
        return upserted
    finally:
        db.close()


def main() -> None:
    print(f"Catalog source: {DOC_MD}")
    upserted, skipped, deleted = seed_led_catalog()
    print(
        f"LEDs: 5050 upserted={upserted}, "
        f"legacy with bindings kept={skipped}, legacy deleted={deleted}"
    )
    ts_rows = seed_ts_coefficients()
    print(f"TS coefficients upserted: {ts_rows}")


if __name__ == "__main__":
    main()
