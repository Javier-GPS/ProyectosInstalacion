"""Bridge between the LUXEON 5050 V2 model and the existing
calculation pipeline.

Exposes :func:`led_point` which returns a ``LedPoint`` for an LED at a
given operating current.  The LED must have the V2 catalog fields
(``family`` + ``flux_ref_lm``); otherwise the function raises
``LedModelError`` so the caller surfaces a clear error to the
operator.
"""
from __future__ import annotations

from ..models.luminaire_catalog import LED
from .led_calculator import (
    LedCatalogEntry,
    LedModelError,
    LedPoint,
    compute_led_point,
)


def _to_entry(led: LED | None) -> LedCatalogEntry:
    if led is None:
        raise LedModelError(
            "Falta el modelo LED 5050 para este CCT/CRI, no se puede calcular."
        )
    if not led.family or led.flux_ref_lm is None:
        raise LedModelError(
            "Falta el modelo LED 5050 para este CCT/CRI, no se puede calcular."
        )
    return LedCatalogEntry(
        family=led.family,
        flux_ref_lm=led.flux_ref_lm,
        cct=led.cct,
        cri=led.cri,
    )


def led_point(
    led: LED | None,
    current_a: float,
    *,
    t_amb_c: float = 25.0,
    ts_coef_c_per_w: float | None = None,
    n_leds_total: int = 1,
    tj_initial_c: float | None = None,
) -> LedPoint:
    entry = _to_entry(led)
    return compute_led_point(
        entry,
        current_a,
        t_amb_c=t_amb_c,
        ts_coef_c_per_w=ts_coef_c_per_w,
        n_leds_total=n_leds_total,
        tj_initial_c=tj_initial_c,
    )


__all__ = ["led_point", "LedPoint", "LedModelError"]
