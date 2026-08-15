"""EN 13201-2:2015 M-class requirements used by the optimizer."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class MClassRequirements:
    luminance_avg_cd_m2: float
    uo_min: float
    ul_min: float
    ti_max_pct: float
    rei_min: float = 0.5


M_CLASS_REQUIREMENTS = {
    "M1": MClassRequirements(2.00, 0.40, 0.70, 10.0),
    "M2": MClassRequirements(1.50, 0.40, 0.70, 10.0),
    "M3": MClassRequirements(1.00, 0.40, 0.60, 15.0),
    "M4": MClassRequirements(0.75, 0.40, 0.60, 15.0),
    "M5": MClassRequirements(0.50, 0.35, 0.40, 15.0),
    "M6": MClassRequirements(0.30, 0.35, 0.40, 20.0),
}


def requirements_for(lighting_class: str) -> MClassRequirements:
    try:
        return M_CLASS_REQUIREMENTS[str(lighting_class).upper()]
    except KeyError as exc:
        raise ValueError("lighting_class must be M1..M6") from exc


def normative_round(value: float, places: int) -> float:
    """Round presented EN 13201 values using decimal half-up rounding."""
    return float(
        Decimal(str(float(value))).quantize(
            Decimal("1").scaleb(-places), rounding=ROUND_HALF_UP,
        )
    )


def passes_minimum(value: float, required: float, places: int) -> bool:
    return normative_round(value, places) >= normative_round(required, places)


def passes_maximum(value: float, required: float, places: int) -> bool:
    return normative_round(value, places) <= normative_round(required, places)
