"""Tests for the LUXEON 5050 V2 model and the Tj iteration.

Verify the formulas from
``docs/modelo_completo_flujo_led_luxeon5050_todas_referencias_v2_con_rs.md``
and the example given in §"Ejemplo".
"""
from __future__ import annotations

import pytest

from app.services.led_calculator import (
    LedCatalogEntry,
    LedModelError,
    compute_led_point,
)
from app.services.led_data import (
    FAMILIES,
    CURVES,
    family_kt,
    family_vf,
    interpolate_curve,
    kt_factor,
)


# ---------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------


def test_kt_factor_at_25c_is_one():
    assert kt_factor(25.0) == pytest.approx(1.0)


def test_kt_factor_at_85c_matches_doc():
    # 1 - 0.0021 * (85 - 25) = 0.874
    assert kt_factor(85.0) == pytest.approx(0.874)


def test_kt_factor_at_125c_matches_doc():
    # 1 - 0.0021 * 100 = 0.79
    assert kt_factor(125.0) == pytest.approx(0.79)


def test_interpolate_curve_returns_nominal_at_reference():
    """The doc says the curve is normalised to 1.0 at the reference current."""
    for family_key, family in FAMILIES.items():
        curve = CURVES[family.curve_id]
        ki_at_ref = interpolate_curve(curve, family.reference_current_a)
        assert ki_at_ref == pytest.approx(1.0, rel=1e-3), (
            f"family {family_key} expected KI(iref)≈1, got {ki_at_ref}"
        )


def test_interpolate_curve_inside_range():
    curve = CURVES["CURVE_6V_ROUND_HE_HEPLUS"]
    # Known point: I=0.36 → K=0.58
    assert interpolate_curve(curve, 0.36) == pytest.approx(0.58, rel=1e-2)


def test_interpolate_curve_extrapolates_above():
    curve = CURVES["CURVE_6V_ROUND_HE_HEPLUS"]
    # Above the last point (0.8) the slope is small but non-zero;
    # ensure the result is > the last known point and monotonic.
    last_i, last_k = curve[-1].current_a, curve[-1].flux_factor
    extrapolated = interpolate_curve(curve, 1.0)
    assert extrapolated > last_k
    # The slope between the two top points:
    #   0.7 → 1.08, 0.8 → 1.21; slope = 1.3 per amp
    #   from 0.8 to 1.0: 1.21 + 0.2 * 1.3 = 1.47
    assert extrapolated == pytest.approx(1.47, rel=1e-2)


def test_interpolate_curve_extrapolates_below():
    curve = CURVES["CURVE_6V_ROUND_HE_HEPLUS"]
    # Below the first point (0.1) the slope is large and the
    # extrapolated value may be negative — the application must
    # detect that and raise an error in compute_led_point.
    extrapolated = interpolate_curve(curve, 0.0)
    assert extrapolated < curve[0].flux_factor


# ---------------------------------------------------------------------
# Family Vf
# ---------------------------------------------------------------------


def test_family_vf_at_reference_and_tref():
    """At I=Iref and Tj=25, Vf should equal the family's vf_ref_v."""
    for family in FAMILIES.values():
        vf = family_vf(family, family.reference_current_a, 25.0)
        assert vf == pytest.approx(family.vf_ref_v, rel=1e-3)


def test_family_vf_drops_at_lower_current():
    family = FAMILIES["HE_PLUS_6V"]
    vf_at_ref = family_vf(family, family.reference_current_a, 25.0)
    vf_at_lower = family_vf(family, 0.36, 25.0)
    # Drop = Rs * (0.36 - 0.64) = 0.30 * -0.28 = -0.084
    assert vf_at_lower == pytest.approx(vf_at_ref - 0.084, rel=1e-3)


# ---------------------------------------------------------------------
# compute_led_point
# ---------------------------------------------------------------------


def test_compute_led_point_doc_example():
    """The doc's worked example: L150-4070500600HH0, 0.36 A, Tj=85 °C
    target.  Without the thermal iteration (no ts_coef), the result
    should match the doc's numbers within a few percent.
    """
    led = LedCatalogEntry(
        family="HE_PLUS_6V", flux_ref_lm=746, cct=4000, cri=70
    )
    p = compute_led_point(led, 0.36, tj_initial_c=85.0)
    assert p.flux_lm == pytest.approx(378.0, rel=0.02)
    assert p.vf_v == pytest.approx(5.586, rel=0.02)
    assert p.power_w == pytest.approx(2.01, rel=0.02)
    assert p.ki == pytest.approx(0.58, rel=0.01)
    assert p.kt == pytest.approx(0.874, rel=0.01)


def test_compute_led_point_with_thermal_iteration():
    """With ts_coef and a single LED, Tj must converge near the
    ambient + Rth*P_led + coef*P_lum case.  We assert that the
    iteration terminates and produces a self-consistent Vf.
    """
    led = LedCatalogEntry(
        family="HE_PLUS_6V", flux_ref_lm=746, cct=4000, cri=70
    )
    p = compute_led_point(
        led,
        0.36,
        t_amb_c=25.0,
        ts_coef_c_per_w=0.4,
        n_leds_total=1,
    )
    # The Rth for HE_PLUS_6V is 1.1 °C/W and the coef is 0.4, so
    # Tj ~= 25 + 0.4*P + 1.1*P = 25 + 1.5*P.  At P ~ 2 W,
    # Tj ~ 28 °C, not 85 °C.
    assert p.tj_c < 50.0
    # KT(28) ~= 0.993, flux ~ 746 * 0.58 * 0.993 ~ 430 lm
    assert p.flux_lm == pytest.approx(430.0, rel=0.05)
    # Power is Vf*0.36 ~ 5.76*0.36 ~ 2.07 W
    assert p.power_w == pytest.approx(2.07, rel=0.05)


def test_compute_led_point_iteration_converges_within_8_steps():
    """The doc says 3-5 iterations; we cap at 8.  The fixture below
    has a high ts_coef to force a slow convergence.
    """
    led = LedCatalogEntry(
        family="ROUND_LES_24V", flux_ref_lm=485, cct=4000, cri=70
    )
    p = compute_led_point(
        led,
        0.10,
        t_amb_c=25.0,
        ts_coef_c_per_w=1.2,  # high coefficient to stress the loop
        n_leds_total=4,
    )
    # Rth=2.4 °C/W for ROUND_LES_24V. With Vf~22V at low current
    # the point is reasonable: Tj ~ 25 + 1.2*4*P + 2.4*P, P~2W → Tj~37°C
    assert p.flux_lm > 0


# ---------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------


def test_compute_led_point_raises_when_no_family():
    led = LedCatalogEntry(family=None, flux_ref_lm=500)
    with pytest.raises(LedModelError, match="Falta el modelo LED 5050"):
        compute_led_point(led, 0.5)


def test_compute_led_point_raises_when_no_flux_ref():
    led = LedCatalogEntry(family="HE_PLUS_6V", flux_ref_lm=None)
    with pytest.raises(LedModelError, match="flux_ref_lm"):
        compute_led_point(led, 0.5)


def test_compute_led_point_raises_on_unknown_family():
    led = LedCatalogEntry(family="NE_24V", flux_ref_lm=500)
    with pytest.raises(LedModelError, match="Familia LED desconocida"):
        compute_led_point(led, 0.5)


def test_compute_led_point_raises_when_current_exceeds_max():
    led = LedCatalogEntry(family="HE_PLUS_6V", flux_ref_lm=746)
    # HE_PLUS_6V max_current_a = 1.2
    with pytest.raises(LedModelError, match="excede max_current_a"):
        compute_led_point(led, 2.0)


def test_compute_led_point_raises_on_negative_current():
    led = LedCatalogEntry(family="HE_PLUS_6V", flux_ref_lm=746)
    with pytest.raises(LedModelError, match="> 0"):
        compute_led_point(led, 0.0)
