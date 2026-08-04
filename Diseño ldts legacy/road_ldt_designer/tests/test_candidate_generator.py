import pytest

from road_ldt_designer.road_ldt.candidate_generator import (
    DEFAULT_RESOLUTION_STAGES,
    AngularResolutionStage,
    PhotometricFamilyParameters,
    generate_resolution_pyramid,
    generate_symmetric_candidate,
    integrated_flux_lm_per_klm,
)
from road_ldt_designer.road_ldt.photometric_symmetry import (
    is_longitudinally_symmetric,
)


def test_generated_candidate_is_symmetric_and_normalized_to_one_klm():
    candidate = generate_symmetric_candidate(PhotometricFamilyParameters())

    assert is_longitudinally_symmetric(candidate)
    assert integrated_flux_lm_per_klm(candidate) == pytest.approx(
        1000.0,
        rel=1e-9,
    )
    assert candidate.metadata["generator"] == "symmetric-road-basis-v2"


def test_all_c_planes_share_one_physical_nadir_intensity():
    candidate = generate_symmetric_candidate(PhotometricFamilyParameters())

    nadir_values = tuple(row[0] for row in candidate.intensity_cd_per_klm)

    assert max(nadir_values) == pytest.approx(min(nadir_values), abs=1e-12)


def test_gamma_crest_sharpens_the_peak_and_outer_slope():
    common = dict(
        peak_c_deg=30.0,
        peak_gamma_deg=60.0,
        c_spread_deg=12.0,
        gamma_spread_deg=15.0,
        gamma_outer_spread_deg=8.0,
        crest_spread_deg=4.0,
        nadir_weight=0.0,
        cross_weight=0.0,
        c_step_deg=5.0,
        gamma_step_deg=1.0,
    )
    smooth = generate_symmetric_candidate(
        PhotometricFamilyParameters(**common, crest_weight=0.0)
    )
    sharpened = generate_symmetric_candidate(
        PhotometricFamilyParameters(**common, crest_weight=0.5)
    )
    c_index = sharpened.c_angles_deg.index(30.0)
    gamma_peak = sharpened.gamma_angles_deg.index(60.0)
    gamma_inner = sharpened.gamma_angles_deg.index(50.0)
    gamma_outer = sharpened.gamma_angles_deg.index(70.0)

    smooth_ratio = (
        smooth.intensity_cd_per_klm[c_index][gamma_peak]
        / smooth.intensity_cd_per_klm[c_index][gamma_inner]
    )
    sharpened_ratio = (
        sharpened.intensity_cd_per_klm[c_index][gamma_peak]
        / sharpened.intensity_cd_per_klm[c_index][gamma_inner]
    )

    assert sharpened_ratio > smooth_ratio
    assert (
        sharpened.intensity_cd_per_klm[c_index][gamma_inner]
        > sharpened.intensity_cd_per_klm[c_index][gamma_outer]
    )


def test_peak_planes_are_brighter_than_opposite_lateral_side():
    candidate = generate_symmetric_candidate(
        PhotometricFamilyParameters(
            peak_c_deg=60.0,
            peak_gamma_deg=65.0,
            c_step_deg=5.0,
            gamma_step_deg=5.0,
        )
    )
    gamma_index = candidate.gamma_angles_deg.index(65.0)
    c_60 = candidate.c_angles_deg.index(60.0)
    c_120 = candidate.c_angles_deg.index(120.0)
    c_270 = candidate.c_angles_deg.index(270.0)

    assert candidate.intensity_cd_per_klm[c_60][gamma_index] == pytest.approx(
        candidate.intensity_cd_per_klm[c_120][gamma_index]
    )
    assert (
        candidate.intensity_cd_per_klm[c_60][gamma_index]
        > candidate.intensity_cd_per_klm[c_270][gamma_index]
    )


def test_cutoff_removes_upward_flux():
    candidate = generate_symmetric_candidate(
        PhotometricFamilyParameters(c_step_deg=10.0, gamma_step_deg=5.0)
    )
    gamma_90 = candidate.gamma_angles_deg.index(90.0)

    assert all(
        all(value == pytest.approx(0.0) for value in row[gamma_90:])
        for row in candidate.intensity_cd_per_klm
    )


def test_invalid_angular_grid_is_rejected():
    with pytest.raises(ValueError, match="dividir exactamente 360"):
        PhotometricFamilyParameters(c_step_deg=7.0)


def test_default_resolution_pyramid_runs_from_coarse_to_export_grid():
    candidates = generate_resolution_pyramid(PhotometricFamilyParameters())

    assert [item.metadata["resolution_stage"] for item in candidates] == [
        "coarse",
        "medium",
        "fine",
        "export",
    ]
    assert [len(item.c_angles_deg) for item in candidates] == [36, 72, 144, 360]
    assert [len(item.gamma_angles_deg) for item in candidates] == [37, 73, 181, 181]
    assert all(is_longitudinally_symmetric(item) for item in candidates)
    assert all(
        integrated_flux_lm_per_klm(item) == pytest.approx(1000.0, rel=1e-9)
        for item in candidates
    )


def test_candidate_can_be_regenerated_at_selected_resolution():
    stage = AngularResolutionStage("verification", 2.0, 1.0)
    candidate = generate_symmetric_candidate(
        PhotometricFamilyParameters(),
        resolution=stage,
    )

    assert len(candidate.c_angles_deg) == 180
    assert len(candidate.gamma_angles_deg) == 181
    assert candidate.metadata["resolution_stage"] == "verification"


def test_default_resolution_steps_are_ordered_from_coarse_to_fine():
    assert [stage.c_step_deg for stage in DEFAULT_RESOLUTION_STAGES] == [
        10.0,
        5.0,
        2.5,
        1.0,
    ]
    assert [stage.gamma_step_deg for stage in DEFAULT_RESOLUTION_STAGES] == [
        5.0,
        2.5,
        1.0,
        1.0,
    ]
