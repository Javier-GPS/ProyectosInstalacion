"""Re-map legacy 4-tuple → LED bindings onto the LUXEON 5050 catalog.

For every existing ``LuminaireLED`` whose LED row has no ``family``
(pre-V2 legacy), the script looks at the original LED's
``led_tipo`` field (e.g. "LUXEON 5050", "LUXEON HO 5050",
"LUXEON HOP 5050", or a non-5050 string) and either:

* re-points the binding at a 5050 partNumber with default
  CCT/CRI (4000 K / CRI 70) when ``led_tipo`` is one of the
  three 5050 variants;
* deletes the binding when the ``led_tipo`` is not 5050 (e.g.
  WICOP, CREE, LUXEON MX, or a code that does not map).

The script is idempotent: re-running it leaves a clean state.

Run::

    cd backend && python scripts/remap_to_5050.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import update  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import LED, LuminaireLED  # noqa: E402


# Heuristic: map the legacy led_tipo to a 5050 family.
# * HO → HE_6V, HOP → HE_PLUS_6V, plain "LUXEON 5050" → SQUARE_LES_6V.
#   ponytail: confirm this with the operator; the user said these
#   three Salvi labels map onto the 3 documented LUXEON 5050
#   families.
TIPO_TO_FAMILY: dict[str, str] = {
    "LUXEON 5050": "SQUARE_LES_6V",
    "LUXEON HO 5050": "HE_6V",
    "LUXEON HOP 5050": "HE_PLUS_6V",
}
DEFAULT_CCT = 4000
DEFAULT_CRI = 70


def _pick_5050_led(db, family: str) -> LED | None:
    """Return the 5050 LED with the default CCT/CRI for the family,
    preferring ``HE_PLUS_6V`` (highest flux).  Falls back to any
    available LED of the family if the default is missing.
    """
    candidate = (
        db.query(LED)
        .filter(
            LED.family == family,
            LED.cct == DEFAULT_CCT,
            LED.cri == DEFAULT_CRI,
        )
        .first()
    )
    if candidate is not None:
        return candidate
    return (
        db.query(LED)
        .filter(LED.family == family)
        .order_by(LED.flux_ref_lm.desc())
        .first()
    )


def main() -> None:
    db = SessionLocal()
    try:
        remapped = 0
        deleted = 0
        legacy_led_ids = [
            led_id
            for (led_id,) in db.query(LED.id)
            .filter(LED.family.is_(None))
            .all()
        ]
        if not legacy_led_ids:
            print("No legacy bindings found.  Nothing to do.")
            return
        # Cache legacy LED → led_tipo so we can re-use the heuristic
        # for all bindings pointing to the same LED.
        legacy_leds = {
            l.id: l for l in db.query(LED).filter(LED.id.in_(legacy_led_ids))
        }
        # Group bindings by their legacy LED id; resolve the
        # replacement once per legacy LED.
        bindings_by_led: dict[int, list[LuminaireLED]] = {}
        for binding in (
            db.query(LuminaireLED)
            .filter(LuminaireLED.led_id.in_(legacy_led_ids))
            .all()
        ):
            bindings_by_led.setdefault(binding.led_id, []).append(binding)

        for legacy_led_id, bindings in bindings_by_led.items():
            legacy = legacy_leds[legacy_led_id]
            target_family = TIPO_TO_FAMILY.get(legacy.led_tipo or "")
            if target_family is None:
                # Non-5050 LED: drop every binding pointing here.
                db.query(LuminaireLED).filter(
                    LuminaireLED.id.in_([b.id for b in bindings])
                ).delete(synchronize_session=False)
                deleted += len(bindings)
                continue
            target = _pick_5050_led(db, target_family)
            if target is None:
                # No 5050 LED for the requested family: drop the
                # bindings.  Should not happen because the seed
                # populates all 3 families.
                db.query(LuminaireLED).filter(
                    LuminaireLED.id.in_([b.id for b in bindings])
                ).delete(synchronize_session=False)
                deleted += len(bindings)
                continue
            db.execute(
                update(LuminaireLED)
                .where(LuminaireLED.id.in_([b.id for b in bindings]))
                .values(led_id=target.id)
            )
            remapped += len(bindings)
        db.commit()

        # Drop orphan legacy LED rows (no remaining bindings).
        orphan = 0
        for legacy_led_id in legacy_led_ids:
            still_bound = (
                db.query(LuminaireLED)
                .filter(LuminaireLED.led_id == legacy_led_id)
                .count()
            )
            if still_bound == 0:
                db.query(LED).filter(LED.id == legacy_led_id).delete()
                orphan += 1
        db.commit()

        print(
            f"Bindings remapped to 5050: {remapped}\n"
            f"Bindings deleted (no 5050 equivalent): {deleted}\n"
            f"Orphan LEDs deleted: {orphan}"
        )
        print(
            f"Remaining: luminaire_leds={db.query(LuminaireLED).count()}, "
            f"leds={db.query(LED).count()}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
