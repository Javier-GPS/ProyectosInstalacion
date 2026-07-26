"""LUXEON 5050 flux / Vf / efficacy calculator.

Implements the V2 model from
``docs/modelo_completo_flujo_led_luxeon5050_todas_referencias_v2_con_rs.md``
plus the iterative Tj solver (3-5 iterations, per the doc) used to
self-consistently couple Tj → Vf → power → Tj.

Public entry point: :func:`compute_led_point` returns a ``LedPoint`` with
the converged Tj, Vf, power, flux and efficacy for a single LED.  The
caller multiplies ``flux_lm`` by ``total_n_leds`` to obtain the
luminaire flux.
"""
from __future__ import annotations

from dataclasses import dataclass

from .led_data import (
    LedFamily,
    family_kt,
    family_vf,
    interpolate_curve,
    lookup_curve,
    lookup_family,
)


# Numerical tolerances for the Tj iteration (the doc calls for 3-5 iters;
# we stop early if successive Tj differ by less than 0.01 °C).
TJ_TOLERANCE_C = 1e-2
TJ_MAX_ITERATIONS = 8


class LedModelError(ValueError):
    """Raised when an LED is missing the 5050 catalog data or the
    operating point violates family limits."""


@dataclass(frozen=True)
class LedCatalogEntry:
    """Minimum subset of a ``LED`` row required by the calculator.

    Keeping this as a plain dataclass lets us pass fixtures into
    :func:`compute_led_point` without dragging the SQLAlchemy session
    around.
    """

    family: str
    flux_ref_lm: float
    cct: int | None = None
    cri: int | None = None


@dataclass(frozen=True)
class LedPoint:
    """Converged operating point for a single LED."""

    tj_c: float
    current_a: float
    vf_v: float
    power_w: float
    flux_lm: float
    efficacy_lm_w: float
    ki: float
    kt: float


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


def compute_led_point(
    led: LedCatalogEntry,
    current_a: float,
    *,
    t_amb_c: float = 25.0,
    ts_coef_c_per_w: float | None = None,
    n_leds_total: int = 1,
    tj_initial_c: float | None = None,
) -> LedPoint:
    """Return the converged operating point for one LED.

    Parameters
    ----------
    led:
        Catalog entry.  Must have ``family`` set to one of the 5050
        family keys and a non-null ``flux_ref_lm``.
    current_a:
        Operating current per LED in amps.
    t_amb_c:
        Ambient temperature in °C.  Used only if ``ts_coef_c_per_w``
        is provided.
    ts_coef_c_per_w:
        Solder-pad thermal coefficient (°C/W) for the luminaire.  When
        provided, ``Tsp = T_amb + coef × (P_led × n_leds_total)`` and
        the iteration uses it.  When ``None``, the iteration starts
        from ``tj_initial_c`` (or 85 °C by default) and does not
        recompute Tsp.
    n_leds_total:
        Total number of LEDs in the luminaire.  Only used to scale the
        Tsp computation (``P_luminaire = P_led × n_leds_total``).
    tj_initial_c:
        Optional initial guess for Tj (°C).  Defaults to 85 °C
        (datasheet worst case) if neither this nor ``ts_coef`` is
        given.
    """
    if not led.family:
        raise LedModelError(
            "Falta el modelo LED 5050 para este CCT/CRI, no se puede calcular."
        )
    if led.flux_ref_lm is None:
        raise LedModelError(
            f"LED sin flux_ref_lm; no se puede calcular con el modelo 5050."
        )
    try:
        family = lookup_family(led.family)
    except KeyError as exc:
        raise LedModelError(
            f"Familia LED desconocida: {led.family!r}."
        ) from exc

    if current_a > family.max_current_a:
        raise LedModelError(
            f"Corriente {current_a:.3f} A excede max_current_a={family.max_current_a:.3f} A "
            f"de la familia {family.key}."
        )
    if current_a <= 0:
        raise LedModelError("Corriente del LED debe ser > 0.")

    curve = lookup_curve(family.curve_id)
    ki = interpolate_curve(curve, current_a)
    if ki < 0:
        raise LedModelError(
            f"KI extrapolado es negativo ({ki:.3f}); corriente fuera de rango viable."
        )

    # Initial Tj guess.
    if tj_initial_c is not None:
        tj = float(tj_initial_c)
    elif ts_coef_c_per_w is not None:
        tj = _initial_tj_from_thermal(family, current_a, t_amb_c, ts_coef_c_per_w, n_leds_total)
    else:
        tj = 85.0

    # Iterate Tj → Vf → P_led → Tj.
    for _ in range(TJ_MAX_ITERATIONS):
        vf = family_vf(family, current_a, tj)
        p_led = vf * current_a
        if ts_coef_c_per_w is not None:
            new_tj = _tj_from_thermal(
                family, current_a, t_amb_c, ts_coef_c_per_w, p_led, n_leds_total
            )
        else:
            new_tj = tj
        if abs(new_tj - tj) < TJ_TOLERANCE_C:
            tj = new_tj
            break
        tj = new_tj

    if tj > family.max_junction_temp_c:
        raise LedModelError(
            f"Tj={tj:.1f} °C excede max_junction_temp_c={family.max_junction_temp_c} °C "
            f"de la familia {family.key}."
        )

    vf = family_vf(family, current_a, tj)
    p_led = vf * current_a
    kt = family_kt(tj)
    flux = led.flux_ref_lm * ki * kt
    if p_led > 0:
        efficacy = flux / p_led
    else:
        efficacy = 0.0

    return LedPoint(
        tj_c=tj,
        current_a=current_a,
        vf_v=vf,
        power_w=p_led,
        flux_lm=flux,
        efficacy_lm_w=efficacy,
        ki=ki,
        kt=kt,
    )


# ---------------------------------------------------------------------
# Thermal helpers
# ---------------------------------------------------------------------


def _initial_tj_from_thermal(
    family: LedFamily,
    current_a: float,
    t_amb_c: float,
    ts_coef_c_per_w: float,
    n_leds_total: int,
) -> float:
    """Rough Tj guess assuming Vf at I_ref."""
    p_led_initial = family.vf_ref_v * current_a
    p_lum = p_led_initial * n_leds_total
    tsp = t_amb_c + ts_coef_c_per_w * p_lum
    return tsp + family.rth_junction_to_solder_c_per_w * p_led_initial


def _tj_from_thermal(
    family: LedFamily,
    current_a: float,
    t_amb_c: float,
    ts_coef_c_per_w: float,
    p_led: float,
    n_leds_total: int,
) -> float:
    p_lum = p_led * n_leds_total
    tsp = t_amb_c + ts_coef_c_per_w * p_lum
    return tsp + family.rth_junction_to_solder_c_per_w * p_led


__all__ = [
    "LedCatalogEntry",
    "LedPoint",
    "LedModelError",
    "compute_led_point",
]
