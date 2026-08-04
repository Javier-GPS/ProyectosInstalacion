"""Utilities for repeating one longitudinal luminaire pattern."""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Sequence

from .domain import LuminairePlacement


def repeat_luminaire_pattern(
    pattern: Sequence[LuminairePlacement],
    period_m: float,
    *,
    x_min_m: float,
    x_max_m: float,
) -> tuple[LuminairePlacement, ...]:
    """Repeat a base cell over a finite calculation interval.

    `pattern` should describe one half-open longitudinal cell. Supports,
    luminaire centres and labels are translated together.
    """

    if not pattern:
        raise ValueError("el patrón debe contener al menos una luminaria")
    if period_m <= 0:
        raise ValueError("period_m debe ser mayor que cero")
    if x_max_m < x_min_m:
        raise ValueError("x_max_m no puede ser menor que x_min_m")

    repeated: dict[tuple[float, float, float, float], LuminairePlacement] = {}
    for luminaire in pattern:
        first_index = math.ceil((x_min_m - luminaire.x_m) / period_m)
        last_index = math.floor((x_max_m - luminaire.x_m) / period_m)
        for repeat_index in range(first_index, last_index + 1):
            offset = repeat_index * period_m
            support_x = (
                None
                if luminaire.support_x_m is None
                else luminaire.support_x_m + offset
            )
            translated = replace(
                luminaire,
                x_m=luminaire.x_m + offset,
                support_x_m=support_x,
                label=(
                    f"{luminaire.label}@{repeat_index:+d}"
                    if luminaire.label
                    else f"repeat_{repeat_index:+d}"
                ),
            )
            key = (
                round(translated.x_m, 9),
                round(translated.y_m, 9),
                round(translated.mounting_height_m, 9),
                round(translated.flux_lm, 9),
            )
            repeated[key] = translated
    return tuple(
        sorted(
            repeated.values(),
            key=lambda item: (item.x_m, item.y_m, item.mounting_height_m),
        )
    )
