import pytest

from road_ldt_designer.road_ldt.candidate_generator import (
    AngularResolutionStage,
    PhotometricFamilyParameters,
    generate_symmetric_candidate,
    integrated_flux_lm_per_klm,
)
from road_ldt_designer.road_ldt.photometric_symmetry import (
    is_longitudinally_symmetric,
)
from road_ldt_designer.road_ldt.photometric_validation import (
    angular_residual_map,
    compare_photometries,
    compensate_target,
    describe_photometry,
)


STAGE = AngularResolutionStage("validation", 5.0, 1.0)


def _candidate(**updates):
    parameters = dict(
        peak_c_deg=30.0,
        peak_gamma_deg=60.0,
        c_spread_deg=16.0,
        gamma_spread_deg=14.0,
        gamma_outer_spread_deg=8.0,
        crest_weight=0.30,
        crest_spread_deg=5.0,
        cutoff_start_deg=78.0,
        cutoff_end_deg=89.0,
    )
    parameters.update(updates)
    return generate_symmetric_candidate(
        PhotometricFamilyParameters(**parameters),
        resolution=STAGE,
    )


def test_descriptor_reports_peak_widths_and_controlled_upward_flux():
    descriptor = describe_photometry(_candidate())

    assert descriptor.peak_intensity_cd_per_klm > 0
    assert descriptor.peak_gamma_deg == pytest.approx(60.0, abs=2.0)
    assert 0 < descriptor.gamma_width_90_deg < descriptor.gamma_fwhm_deg
    assert descriptor.high_angle_flux_fraction >= 0
    assert descriptor.upward_flux_fraction == pytest.approx(0.0, abs=1e-12)
    assert descriptor.longitudinal_symmetry_error_pct == pytest.approx(
        0.0,
        abs=1e-9,
    )


def test_comparison_is_zero_for_the_same_photometry():
    candidate = _candidate()

    comparison = compare_photometries(candidate, candidate)

    assert comparison.normalized_rmse_pct == pytest.approx(0.0)
    assert comparison.normalized_mean_absolute_error_pct == pytest.approx(0.0)
    assert comparison.shape_correlation == pytest.approx(1.0)
    assert comparison.peak_c_shift_deg == pytest.approx(0.0)
    assert comparison.peak_gamma_shift_deg == pytest.approx(0.0)


def test_comparison_detects_peak_and_width_changes():
    target = _candidate()
    physical = _candidate(
        peak_gamma_deg=66.0,
        gamma_spread_deg=20.0,
        gamma_outer_spread_deg=12.0,
        crest_weight=0.15,
    )

    comparison = compare_photometries(target, physical)

    assert comparison.normalized_rmse_pct > 0
    assert comparison.shape_correlation < 1.0
    assert comparison.peak_gamma_shift_deg > 0
    assert comparison.gamma_fwhm_delta_deg > 0


def test_angular_residual_is_zero_for_same_candidate():
    candidate = _candidate()

    residual = angular_residual_map(candidate, candidate)

    assert residual.minimum_error_pct == pytest.approx(0.0)
    assert residual.maximum_error_pct == pytest.approx(0.0)
    assert len(residual.c_angles_deg) == 72
    assert len(residual.gamma_angles_deg) == 46


def test_compensation_preserves_target_when_residual_is_zero():
    target = _candidate()

    compensation = compensate_target(target, target)

    assert compensation.correction_gain == pytest.approx(0.60)
    assert compensation.clipped_low_fraction == pytest.approx(0.0)
    assert compensation.capped_high_fraction == pytest.approx(0.0)
    assert compensation.integrated_flux_lm_per_klm == pytest.approx(
        integrated_flux_lm_per_klm(target),
        rel=1e-8,
    )
    assert is_longitudinally_symmetric(compensation.candidate)
    for corrected_row, target_row in zip(
        compensation.candidate.intensity_cd_per_klm,
        target.intensity_cd_per_klm,
    ):
        assert corrected_row == pytest.approx(target_row, rel=1e-8)


def test_compensation_moves_next_target_against_physical_peak_error():
    target = _candidate()
    physical = _candidate(
        peak_gamma_deg=66.0,
        gamma_spread_deg=20.0,
        gamma_outer_spread_deg=12.0,
        crest_weight=0.15,
    )

    compensation = compensate_target(
        target,
        physical,
        correction_gain=0.65,
    )
    target_peak = describe_photometry(target)
    c_index = target.c_angles_deg.index(target_peak.peak_c_deg)
    gamma_index = target.gamma_angles_deg.index(66.0)

    assert (
        compensation.candidate.intensity_cd_per_klm[c_index][gamma_index]
        < target.intensity_cd_per_klm[c_index][gamma_index]
    )
    assert compensation.maximum_adjustment_pct_of_target_peak > 0
    assert compensation.integrated_flux_lm_per_klm == pytest.approx(
        integrated_flux_lm_per_klm(target),
        rel=1e-8,
    )
    assert is_longitudinally_symmetric(compensation.candidate)
