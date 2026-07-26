"""Resolve the maximum power a 4-tuple ``(gama, difusor, lente, led_type)`` can support.

The cap is sourced from the LED catalog's ``pmax_ajustada`` column (the
highest supported adjusted maximum when a 4-tuple maps to several). The service is
used in three places:

1. The configurator UI displays the cap on the power slider (via
   ``/api/ldt/dimensions`` returning a ``pmax_by_combo`` map).
2. The ``/api/calculate`` endpoint rejects requests whose ``power`` is
   above the cap (HTTP 400). External LDTs (those whose ``ldt_id``
   starts with ``temp-``) are no longer supported and raise 400.
3. The optimizer caps the search at the same value (instead of the
   legacy 500 W ceiling).

If the 4-tuple is not in the catalog we deliberately return ``None``
(no enforcement) so newly created luminaires — whose LDTs come from
the admin flow — are not blocked from saving.
"""
from __future__ import annotations

import difflib
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from ..core.text_utils import norm as _norm
from ..models import LED, Gama, Difusor, Lente, LedType, LuminaireLED, ValidCombination
from ..schemas.models import CalculationConfig


log = logging.getLogger(__name__)

_DIM_CLASSES = {"gama": Gama, "difusor": Difusor, "lente": Lente, "led_type": LedType}

# ``Referencias_productos_pcb_go.xlsx`` stores the diffuser in
# ``Variantes SALVI`` as a short code (``D_Ref``) plus a descriptive
# name (``D_Descr corta``).  The configurator and ``valid_combinations``
# use the descriptive BBDD name, but older ``luminaire_leds`` seeds used
# the short code.  Keep both resolvable so existing DBs enforce the cap
# without a mandatory re-import.
_DIFUSOR_CODE_TO_DESCRIPTIONS: dict[str, tuple[str, ...]] = {
    "0": ("SIN DIF",),
    "A": ("VDR SC",),
    "B": ("VDR SP",),
    "E": ("CONFORT",),
    "F": ("VDR LC",),
    "H": ("PMMA LC BCN",),
    "J": ("PMMA SC",),
    "K": ("PMMA LC",),
    "M": ("PMMA LC",),
    "O": ("PMMA LA",),
    "P": ("PMMA SP",),
    "Q": ("PMMA S", "VDR SP"),
    "S": ("PMMA A",),
    "T": ("PMMA L",),
    "U": ("PMMA LP",),
    "V": ("PMMA VSC",),
    "W": ("VDR SPUW",),
    "Z": ("PMMA VLC",),
}

_DIFUSOR_DESCRIPTION_TO_CODES: dict[str, tuple[str, ...]] = {}
for code, descriptions in _DIFUSOR_CODE_TO_DESCRIPTIONS.items():
    for description in descriptions:
        _DIFUSOR_DESCRIPTION_TO_CODES.setdefault(description, ())
        _DIFUSOR_DESCRIPTION_TO_CODES[description] += (code,)


def _resolve_dim_id(db: Session, model, name: str | None):
    if not name:
        return None
    instance = db.query(model).filter(model.name == _norm(name)).first()
    return instance.id if instance else None


def _fuzzy_resolve_dim_id(db: Session, model, name: str | None, cutoff: float = 0.75):
    """Try exact match (normalized), then fuzzy fallback.

    Returns ``(id, matched_name, score)`` or ``(None, None, 0)``.
    """
    normed = _norm(name) if name else ""
    if not normed:
        return None, None, 0.0

    exact = db.query(model).filter(model.name == normed).first()
    if exact:
        return exact.id, exact.name, 1.0

    all_names = [row.name for row in db.query(model.name).all()]
    matches = difflib.get_close_matches(normed, all_names, n=3, cutoff=cutoff)
    if not matches:
        return None, None, 0.0

    score_first = difflib.SequenceMatcher(None, normed, matches[0]).ratio()
    if len(matches) == 1:
        return db.query(model).filter(model.name == matches[0]).first().id, matches[0], round(score_first, 4)

    score_second = difflib.SequenceMatcher(None, normed, matches[1]).ratio()
    if score_first - score_second > 0.1:
        return db.query(model).filter(model.name == matches[0]).first().id, matches[0], round(score_first, 4)

    return None, None, 0.0


def _difusor_lookup_names(name: str | None) -> list[str]:
    """Return the selected diffuser plus legacy short-code aliases."""
    selected = _norm(name)
    if not selected:
        return []
    names = [selected]
    names.extend(_DIFUSOR_DESCRIPTION_TO_CODES.get(selected, ()))
    names.extend(_DIFUSOR_CODE_TO_DESCRIPTIONS.get(selected, ()))
    return list(dict.fromkeys(names))


def _resolve_dim_ids(db: Session, model, names: list[str]) -> list[int]:
    if not names:
        return []
    rows = db.query(model).filter(model.name.in_(names)).all()
    return [row.id for row in rows]


def _highest_cap_led_for_type(db: Session, led_type: str | None) -> LED | None:
    """Fallback cap when the seed lacks a full 4-tuple binding.

    ``valid_combinations`` can contain rows that are absent from
    ``luminaire_leds`` because the LED reference sheet only lists a
    subset of the commercial catalog.  In that case we still know the
    selected LED family (``LedType.name``), so use the highest
    numeric cap from ``LED.led_tipo`` instead of allowing the legacy
    500 W ceiling.
    """
    led_type_name = _norm(led_type)
    if not led_type_name:
        return None
    return (
        db.query(LED)
        .filter(
            LED.led_tipo == led_type_name,
            LED.pmax_ajustada.isnot(None),
        )
        .order_by(LED.pmax_ajustada.desc(), LED.led_ref.asc())
        .first()
    )


def _resolve_all_dim_ids(
    db: Session,
    gama: str | None,
    difusor: str | None,
    lente: str | None,
    led_type: str | None,
) -> tuple[int | None, list[int], int | None, int | None]:
    """Resolve all 4 dimension names to IDs in as few queries as possible."""
    names_to_find: dict[str, str] = {}
    if gama:
        names_to_find["gama"] = _norm(gama)
    if lente:
        names_to_find["lente"] = _norm(lente)
    if led_type:
        names_to_find["led_type"] = _norm(led_type)
    dif_names = _difusor_lookup_names(difusor)
    if dif_names:
        names_to_find["difusor"] = dif_names[0]
    results: dict[str, int | None] = {"gama": None, "difusor": None, "lente": None, "led_type": None}
    for key, model_cls in (("gama", Gama), ("lente", Lente), ("led_type", LedType)):
        if key in names_to_find:
            sid, _, _ = _fuzzy_resolve_dim_id(db, model_cls, names_to_find[key])
            results[key] = sid
    difusor_ids: list[int] = []
    if dif_names:
        rows = db.query(Difusor).filter(Difusor.name.in_(dif_names)).all()
        difusor_ids = [row.id for row in rows]
    return results["gama"], difusor_ids, results["lente"], results["led_type"]


def get_pmax_for_selection(
    db: Session,
    gama: str | None,
    difusor: str | None,
    lente: str | None,
    led_type: str | None,
) -> dict | None:
    """Return the cap info for a 4-tuple, or ``None`` if unknown.

    The dict has the shape ``{"pmax_ajustada": float, "led_ref": str,
    "led_desc_corta": str|None, "i_max_led": float|None,
    "pmax_lum": float|None, "source": "exact"|"led_type_fallback"}``.
    ``pmax_ajustada`` may itself be ``None`` when the LED has no
    numeric cap recorded.
    """
    if not (gama and difusor and lente):
        return None
    gama_id, difusor_ids, lente_id, led_type_id = _resolve_all_dim_ids(db, gama, difusor, lente, led_type)
    if gama_id is None or not difusor_ids or lente_id is None:
        return None

    bindings = (
        db.query(LuminaireLED)
        .filter(
            LuminaireLED.gama_id == gama_id,
            LuminaireLED.difusor_id.in_(difusor_ids),
            LuminaireLED.lente_id == lente_id,
            LuminaireLED.led_type_id == led_type_id,
        )
        .all()
    )
    led: LED | None = None
    if bindings:
        led_ids = [binding.led_id for binding in bindings]
        leds = db.query(LED).filter(LED.id.in_(led_ids)).all()
        if leds:
            # Alias resolution can legitimately find more than one
            # legacy binding (for example VDR SP can map through B and
            # Q).  Enforce the highest numeric cap, matching
            # the seed's policy.
            led = max(
                leds,
                key=lambda item: item.pmax_ajustada
                if item.pmax_ajustada is not None
                else float("-inf"),
            )
    source = "exact" if led is not None and led.pmax_ajustada is not None else "led_type_fallback"
    if led is None or led.pmax_ajustada is None:
        led = _highest_cap_led_for_type(db, led_type)
        source = "led_type_fallback"
    if led is None:
        return None
    return {
        "pmax_ajustada": led.pmax_ajustada,
        "led_ref": led.led_ref,
        "led_desc_corta": led.led_desc_corta,
        "i_max_led": led.i_max_led,
        "pmax_lum": led.pmax_lum,
        "source": source,
    }


def build_pmax_maps(
    db: Session,
    tuples: Optional[list[tuple[str | None, str | None, str | None, str | None]]] = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Return power caps and where each cap came from.

    When ``tuples`` is omitted, the map covers every 4-tuple in
    ``luminaire_leds``.  When it is provided, the map only includes
    the tuples requested (the FE can pass the currently-selected
    4-tuple for a fast lookup).

    Keys are upper-cased, pipe-joined strings.  Missing
    ``pmax_ajustada`` values are excluded from the map.
    """
    # Keep separate queries: these tables are small and the joinedload approach
    # was excluding LEDs not referenced by any luminaire_leds binding.
    bindings = db.query(LuminaireLED).all()
    gama_names = {row.id: _norm(row.name) for row in db.query(Gama).all()}
    difusor_names_by_id = {row.id: _norm(row.name) for row in db.query(Difusor).all()}
    lente_names = {row.id: _norm(row.name) for row in db.query(Lente).all()}
    led_type_names = {row.id: _norm(row.name) for row in db.query(LedType).all()}
    leds_by_id = {row.id: row for row in db.query(LED).all()}

    out: dict[str, float] = {}
    sources: dict[str, str] = {}
    for b in bindings:
        gama = gama_names.get(b.gama_id)
        dif = difusor_names_by_id.get(b.difusor_id)
        lente = lente_names.get(b.lente_id)
        led = led_type_names.get(b.led_type_id) if b.led_type_id else ""
        led_def = leds_by_id.get(b.led_id)
        if not (gama and dif and lente and led_def and led_def.pmax_ajustada is not None):
            continue
        lookup_difusor_names = [
            dif,
            *_DIFUSOR_CODE_TO_DESCRIPTIONS.get(dif, ()),
        ]
        for difusor_name in dict.fromkeys(lookup_difusor_names):
            key = "|".join([
                gama,
                _norm(difusor_name),
                lente,
                led,
            ])
            pmax = float(led_def.pmax_ajustada)
            if key not in out or pmax > out[key]:
                out[key] = pmax
                sources[key] = "exact"

    # Fill every visible catalog combination that does not have an
    # exact 4-tuple binding.
    led_type_caps: dict[str, float] = {}
    for led in leds_by_id.values():
        if led.led_tipo is None or led.pmax_ajustada is None:
            continue
        led_type_name = _norm(led.led_tipo)
        if not led_type_name:
            continue
        pmax = float(led.pmax_ajustada)
        led_type_caps[led_type_name] = (
            max(led_type_caps[led_type_name], pmax)
            if led_type_name in led_type_caps
            else pmax
        )

    valid_combinations = (
        db.query(ValidCombination)
        .options(
            joinedload(ValidCombination.gama),
            joinedload(ValidCombination.difusor),
            joinedload(ValidCombination.lente),
            joinedload(ValidCombination.led_type),
        )
        .all()
    )
    for vc in valid_combinations:
        if not (vc.gama and vc.difusor and vc.lente and vc.led_type):
            continue
        led_type_name = _norm(vc.led_type.name)
        pmax = led_type_caps.get(led_type_name)
        if pmax is None:
            continue
        key = "|".join([
            _norm(vc.gama.name),
            _norm(vc.difusor.name),
            _norm(vc.lente.name),
            led_type_name,
        ])
        if key not in out:
            out[key] = pmax
            sources[key] = "led_type_fallback"
    return out, sources


def build_pmax_by_combo(
    db: Session,
    tuples: Optional[list[tuple[str | None, str | None, str | None, str | None]]] = None,
) -> dict[str, float]:
    """Return ``{"GAMA|DIF|LENTE|LED": pmax_ajustada}`` for the UI."""
    out, _sources = build_pmax_maps(db, tuples)
    return out


# ---------------------------------------------------------------------------
# Hard-enforcement helpers (used by /api/calculate and the optimizers)
# ---------------------------------------------------------------------------


def _is_external_ldt(ldt_id: str | None) -> bool:
    """True when ``ldt_id`` refers to a temporary, user-uploaded LDT."""
    return bool(ldt_id) and ldt_id.startswith("temp-")


def clamp_power_to_pmax(
    db: Session,
    config: CalculationConfig,
) -> CalculationConfig:
    """Reject ``power`` values that exceed the 4-tuple cap.

    Behaviour:

    - External LDTs (``ldt_id`` starts with ``temp-``) and 4-tuples
      with no catalog binding are passed through unchanged.  This
      keeps the legacy flow (admin uploads an arbitrary LDT, user
      experiments with it) working.
    - ``power`` above ``pmax_ajustada`` raises an HTTP 400 with a
      descriptive message; the client UI surfaces this verbatim.
    - ``power`` below the cap is returned unchanged.

    The function never silently lowers ``power`` (that would mislead
    the user); the UI is expected to clamp the slider proactively.
    """
    # External LDTs (temp-) are no longer supported; raise so the
    # operator gets a clear error.
    if _is_external_ldt(config.ldt_id):
        raise HTTPException(
            status_code=400,
            detail="Los LDTs externos ya no están soportados. Usa la 4-tupla del catálogo 5050.",
        )

    info = get_pmax_for_selection(
        db,
        config.gama,
        config.difusor,
        config.lente,
        config.led_type,
    )
    if info is None or info.get("pmax_ajustada") is None:
        return config

    pmax = float(info["pmax_ajustada"])
    if config.power > pmax + 1e-6:
        # Format with comma decimal separator for the Spanish locale.
        pmax_str = f"{pmax:g}".replace(".", ",")
        power_str = f"{config.power:g}".replace(".", ",")
        fallback_note = (
            " No tenemos el limite exacto para esta combinacion; "
            "se ha usado el limite maximo conocido para este tipo de LED."
            if info.get("source") == "led_type_fallback"
            else ""
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"La potencia solicitada ({power_str} W) supera el máximo del "
                f"LED {info['led_ref']} ({pmax_str} W) para la selección "
                f"({config.gama}/{config.difusor}/{config.lente}/{config.led_type or '—'})."
                f"{fallback_note}"
            ),
        )
    return config


def max_power_for_optimizer(
    db: Session,
    config: CalculationConfig,
    user_supplied: float | None = None,
) -> float | None:
    """Return the ceiling the optimizer should use for ``power``.

    - ``user_supplied`` is honoured if it is below the cap.
    - When the cap is known, it is the absolute ceiling.
    - When the 4-tuple is unknown or the LDT is external, returns
      ``None`` so the caller can fall back to its default ceiling.
    """
    if _is_external_ldt(config.ldt_id):
        raise HTTPException(
            status_code=400,
            detail="Los LDTs externos ya no están soportados. Usa la 4-tupla del catálogo 5050.",
        )
    info = get_pmax_for_selection(
        db,
        config.gama,
        config.difusor,
        config.lente,
        config.led_type,
    )
    pmax = info["pmax_ajustada"] if info else None
    if pmax is None:
        return user_supplied
    if user_supplied is not None:
        return min(float(user_supplied), float(pmax))
    return float(pmax)
