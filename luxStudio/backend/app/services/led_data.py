"""LUXEON 5050 model constants and lookup helpers.

Encodes the V2 model from
``docs/modelo_completo_flujo_led_luxeon5050_todas_referencias_v2_con_rs.md``:

    Φ(I, Tj) = Φref × KI(I) × KT(Tj)
    Vf(I, Tj) = vfRefV + Rs × (I - Iref) + vfTempCoeffVPerC × (Tj - 25)
    η(I, Tj)  = Φ(I, Tj) / (Vf(I, Tj) × I)
    KT(Tj)    = 1 - 0.0021 × (Tj - 25)

`FAMILIES` holds the per-family electrical / thermal parameters.
`CURVES` holds the 3 normalised current-flux tables (KI) used by several
families.  See the doc for the source of every number.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class LedFamily:
    """Per-family parameters from the V2 doc."""

    key: str
    reference_current_a: float
    same_drive_current_a: float
    vf_ref_v: float
    vf_temp_coeff_v_per_c: float
    max_current_a: float
    max_pulsed_current_a: float
    max_junction_temp_c: float
    rth_junction_to_solder_c_per_w: float
    series_resistance_ohm: float
    curve_id: str


@dataclass(frozen=True)
class CurvePoint:
    """Single (I, K) pair from a normalised flux curve."""

    current_a: float
    flux_factor: float


FAMILIES: dict[str, LedFamily] = {
    "ROUND_LES_24V": LedFamily(
        key="ROUND_LES_24V",
        reference_current_a=0.16,
        same_drive_current_a=0.09,
        vf_ref_v=24.4,
        vf_temp_coeff_v_per_c=-0.012,
        max_current_a=0.24,
        max_pulsed_current_a=0.30,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=2.4,
        series_resistance_ohm=1.2,
        curve_id="CURVE_24V_30V",
    ),
    "ROUND_LES_6V": LedFamily(
        key="ROUND_LES_6V",
        reference_current_a=0.64,
        same_drive_current_a=0.36,
        vf_ref_v=6.1,
        vf_temp_coeff_v_per_c=-0.003,
        max_current_a=0.80,
        max_pulsed_current_a=1.00,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=2.4,
        series_resistance_ohm=0.30,
        curve_id="CURVE_6V_ROUND_HE_HEPLUS",
    ),
    "SQUARE_LES_30V": LedFamily(
        key="SQUARE_LES_30V",
        reference_current_a=0.16,
        same_drive_current_a=0.09,
        vf_ref_v=30.5,
        vf_temp_coeff_v_per_c=-0.015,
        max_current_a=0.24,
        max_pulsed_current_a=0.30,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=1.4,
        series_resistance_ohm=1.5,
        curve_id="CURVE_24V_30V",
    ),
    "SQUARE_LES_6V": LedFamily(
        key="SQUARE_LES_6V",
        reference_current_a=0.80,
        same_drive_current_a=0.36,
        vf_ref_v=6.1,
        vf_temp_coeff_v_per_c=-0.003,
        max_current_a=1.00,
        max_pulsed_current_a=1.25,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=1.4,
        series_resistance_ohm=0.30,
        curve_id="CURVE_6V_SQUARE",
    ),
    "HE_24V": LedFamily(
        key="HE_24V",
        reference_current_a=0.16,
        same_drive_current_a=0.09,
        vf_ref_v=24.2,
        vf_temp_coeff_v_per_c=-0.012,
        max_current_a=0.24,
        max_pulsed_current_a=0.30,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=2.2,
        series_resistance_ohm=1.2,
        curve_id="CURVE_24V_30V",
    ),
    "HE_24V_ESD_3B": LedFamily(
        key="HE_24V_ESD_3B",
        reference_current_a=0.16,
        same_drive_current_a=0.09,
        vf_ref_v=24.2,
        vf_temp_coeff_v_per_c=-0.012,
        max_current_a=0.24,
        max_pulsed_current_a=0.30,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=2.2,
        series_resistance_ohm=1.2,
        curve_id="CURVE_24V_30V",
    ),
    "HE_6V": LedFamily(
        key="HE_6V",
        reference_current_a=0.64,
        same_drive_current_a=0.36,
        vf_ref_v=6.05,
        vf_temp_coeff_v_per_c=-0.003,
        max_current_a=0.80,
        max_pulsed_current_a=1.00,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=2.2,
        series_resistance_ohm=0.30,
        curve_id="CURVE_6V_ROUND_HE_HEPLUS",
    ),
    "HE_6V_ESD_3B": LedFamily(
        key="HE_6V_ESD_3B",
        reference_current_a=0.64,
        same_drive_current_a=0.36,
        vf_ref_v=6.05,
        vf_temp_coeff_v_per_c=-0.003,
        max_current_a=0.80,
        max_pulsed_current_a=1.00,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=2.2,
        series_resistance_ohm=0.30,
        curve_id="CURVE_6V_ROUND_HE_HEPLUS",
    ),
    "HE_PLUS_6V": LedFamily(
        key="HE_PLUS_6V",
        reference_current_a=0.64,
        same_drive_current_a=0.36,
        vf_ref_v=5.85,
        vf_temp_coeff_v_per_c=-0.003,
        max_current_a=1.20,
        max_pulsed_current_a=1.50,
        max_junction_temp_c=125.0,
        rth_junction_to_solder_c_per_w=1.1,
        series_resistance_ohm=0.30,
        curve_id="CURVE_6V_ROUND_HE_HEPLUS",
    ),
}


CURVES: dict[str, tuple[CurvePoint, ...]] = {
    "CURVE_24V_30V": tuple(
        CurvePoint(c, k)
        for c, k in (
            (0.025, 0.15),
            (0.050, 0.32),
            (0.075, 0.50),
            (0.100, 0.66),
            (0.125, 0.82),
            (0.160, 1.00),
            (0.200, 1.21),
            (0.240, 1.41),
        )
    ),
    "CURVE_6V_ROUND_HE_HEPLUS": tuple(
        CurvePoint(c, k)
        for c, k in (
            (0.10, 0.15),
            (0.20, 0.35),
            (0.30, 0.51),
            (0.36, 0.58),
            (0.40, 0.66),
            (0.50, 0.81),
            (0.60, 0.95),
            (0.64, 1.00),
            (0.70, 1.08),
            (0.80, 1.21),
        )
    ),
    "CURVE_6V_SQUARE": tuple(
        CurvePoint(c, k)
        for c, k in (
            (0.10, 0.14),
            (0.20, 0.28),
            (0.30, 0.41),
            (0.40, 0.54),
            (0.50, 0.66),
            (0.60, 0.79),
            (0.70, 0.90),
            (0.80, 1.00),
            (0.90, 1.11),
            (1.00, 1.21),
        )
    ),
}


# Salvi-led_ref labels that should be re-mapped to 5050 family keys when
# re-importing the catalog.  See decision log: ``luxeon hop 5050`` is the
# HE Plus 6V variant, ``ho 5050`` is the HE 6V variant, ``luxeon 5050``
# is the Square LES 6V variant.


def lookup_family(key: str) -> LedFamily:
    """Resolve a family key, raising ``KeyError`` if missing."""
    return FAMILIES[key]


def lookup_curve(curve_id: str) -> tuple[CurvePoint, ...]:
    return CURVES[curve_id]


# -----------------------------------------------------------------------
# Pure helpers
# -----------------------------------------------------------------------


def interpolate_curve(points: Sequence[CurvePoint], current_a: float) -> float:
    """Linear interpolation through a KI curve.

    Out-of-range currents extend the last segment with the same slope
    (the doc's extrapolation policy).  Returns the extrapolated factor
    rather than raising — bounds enforcement happens separately via
    ``family.max_current_a``.
    """
    if not points:
        raise ValueError("curve must have at least one point")
    if current_a <= points[0].current_a:
        if current_a == points[0].current_a:
            return points[0].flux_factor
        # Linear extrapolation below the first point.
        p0, p1 = points[0], points[1] if len(points) > 1 else points[0]
        slope = (p1.flux_factor - p0.flux_factor) / max(
            p1.current_a - p0.current_a, 1e-12
        )
        return p0.flux_factor + slope * (current_a - p0.current_a)
    if current_a >= points[-1].current_a:
        if current_a == points[-1].current_a:
            return points[-1].flux_factor
        if len(points) < 2:
            return points[-1].flux_factor
        pn1, pn = points[-2], points[-1]
        slope = (pn.flux_factor - pn1.flux_factor) / max(
            pn.current_a - pn1.current_a, 1e-12
        )
        return pn.flux_factor + slope * (current_a - pn.current_a)

    # In-range: binary search.
    lo, hi = 0, len(points) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if points[mid].current_a <= current_a:
            lo = mid
        else:
            hi = mid
    a, b = points[lo], points[hi]
    return a.flux_factor + (current_a - a.current_a) * (
        b.flux_factor - a.flux_factor
    ) / (b.current_a - a.current_a)


def family_vf(family: LedFamily, current_a: float, tj_c: float) -> float:
    """``Vf(I, Tj) = vfRefV + Rs × (I - Iref) + vfTempCoeffVPerC × (Tj - 25)``."""
    return (
        family.vf_ref_v
        + family.series_resistance_ohm * (current_a - family.reference_current_a)
        + family.vf_temp_coeff_v_per_c * (tj_c - 25.0)
    )


def kt_factor(tj_c: float) -> float:
    """``KT(Tj) = 1 - 0.0021 × (Tj - 25)``."""
    return 1.0 - 0.0021 * (tj_c - 25.0)


# ``family_kt`` is the public alias used by callers that work in family
# space; both names expose the same thermal factor.
family_kt = kt_factor


__all__ = [
    "FAMILIES",
    "CURVES",
    "LedFamily",
    "lookup_family",
    "lookup_curve",
    "interpolate_curve",
    "family_vf",
    "family_kt",
    "kt_factor",
]
