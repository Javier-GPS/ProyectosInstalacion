from fastapi import HTTPException

from ..core.text_utils import norm as _norm
from ..schemas.models import CalculationConfig
from .ldt_loader import get_all_ldts, get_ldt_by_id


def find_ldt_for_config(config: CalculationConfig):
    scoped_ldts = get_all_ldts()
    if config.manufacturer:
        scoped_ldts = [
            l for l in scoped_ldts
            if _norm(l.get("manufacturer", "")) == _norm(config.manufacturer)
        ]
    if config.model_family:
        scoped_ldts = [
            l for l in scoped_ldts
            if l.get("model_family", "UNKNOWN") == config.model_family
        ]
    elif config.gama:
        scoped_ldts = [
            l for l in scoped_ldts
            if _norm(l.get("gama", "")) == _norm(config.gama)
        ]

    if all([config.gama, config.difusor, config.lente, config.led_type]):
        exact_tuple = [
            l for l in scoped_ldts
            if _norm(l.get("gama", "")) == _norm(config.gama)
            and _norm(l.get("difusor", "")) == _norm(config.difusor)
            and _norm(l.get("lente", "")) == _norm(config.lente)
            and _norm(l.get("led_type", "")) == _norm(config.led_type)
        ]
        if exact_tuple:
            ldt = min(exact_tuple, key=lambda l: (
                abs(float(l.get("power", 0)) - float(config.power)),
                abs(int(l.get("cct", config.cct)) - int(config.cct)),
                abs(int(l.get("cri", config.cri)) - int(config.cri)),
            ))
            return ldt["id"], ldt

    if config.ldt_id:
        ldt = get_ldt_by_id(config.ldt_id)
        if ldt is not None and ldt in scoped_ldts:
            return ldt["id"], ldt

    optic_family = _norm(config.optic_family) if config.optic_family else ""
    ldt_id = f"{optic_family}_{config.power:.0f}W".lower().replace(" ", "_")
    ldt = get_ldt_by_id(ldt_id)
    if ldt is not None and ldt in scoped_ldts:
        return ldt_id, ldt

    normed_optic = optic_family

    candidates = [
        l for l in scoped_ldts
        if (
            _norm(l.get("optic_family", "")) == normed_optic and
            abs(l["power"] - config.power) < 1 and
            int(l.get("cri", 70)) == int(config.cri) and
            int(l.get("cct", config.cct)) == int(config.cct)
        )
    ]
    if candidates:
        ldt = candidates[0]
        return ldt["id"], ldt

    candidates = [
        l for l in scoped_ldts
        if (
            _norm(l.get("optic_family", "")) == normed_optic and
            abs(l["power"] - config.power) < 1 and
            int(l.get("cct", config.cct)) == int(config.cct)
        )
    ]
    if candidates:
        ldt = candidates[0]
        return ldt["id"], ldt

    candidates = [
        l for l in scoped_ldts
        if _norm(l.get("optic_family", "")) == normed_optic and abs(l["power"] - config.power) < 1
    ]
    if candidates:
        ldt = min(candidates, key=lambda l: abs(int(l.get("cct", config.cct)) - int(config.cct)))
        return ldt["id"], ldt

    same_family = [l for l in scoped_ldts if _norm(l.get("optic_family", "")) == normed_optic]
    if same_family:
        ldt = min(same_family, key=lambda l: (
            abs(l["power"] - config.power),
            abs(int(l.get("cct", config.cct)) - int(config.cct)),
        ))
        return ldt["id"], ldt

    if scoped_ldts:
        ldt = min(scoped_ldts, key=lambda l: abs(l["power"] - config.power))
        return ldt["id"], ldt

    raise HTTPException(status_code=404, detail="No LDT files available")


def require_ldt_for_config(config: CalculationConfig):
    ldt_id, ldt = find_ldt_for_config(config)
    if ldt is None:
        available = sorted(set(
            f"{l['optic_family']} {l['power']:.0f}W" for l in get_all_ldts()
        ))
        raise HTTPException(
            status_code=404,
            detail=f"No LDT found for family '{config.optic_family}' at {config.power:.0f}W. "
                   f"Available: {', '.join(available[:20])}",
        )
    return ldt_id, ldt
