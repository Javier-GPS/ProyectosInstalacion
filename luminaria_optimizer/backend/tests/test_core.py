from pathlib import Path

import numpy as np
import pytest

from luminaire_optimizer.composition import DEFAULT_GROUP_ANGLES_DEG, GROUP_C_ROTATION_DEG, compose_luminaire
from luminaire_optimizer.hl2x import Hl2xModel, calculate_luminaire_operating_point
from luminaire_optimizer.ldt import LdtPhotometry, LampSet, ldt_diagnostic, ldt_text, parse_ldt_text
from luminaire_optimizer.r_tables import ReducedLuminanceTable, load_rtable
from luminaire_optimizer.road import RoadScenario, _angles_to_point
from luminaire_optimizer.road import (
    _beta,
    _group_intensity_cd,
    _positions,
    _road_points,
    _virtual_sources,
    calculate_road,
    calculate_reference_road,
    luminance_from_flux,
    luminance_uniformity,
    luminance_uniformity_batch,
    precompute_luminance_influence,
)
from luminaire_optimizer.road import _base_group_intensity, photometric_azimuth_profile
from luminaire_optimizer.optimizer import _symmetric_vector, _uniformity_quality, optimize_currents_and_tilt


def group_ldt() -> LdtPhotometry:
    return LdtPhotometry(
        company="TEST",
        name="Group",
        c_angles_deg=[0.0, 90.0, 180.0, 270.0],
        gamma_angles_deg=[0.0, 45.0, 90.0],
        intensities_cd_per_klm=[[100.0, 50.0, 0.0], [100.0, 50.0, 0.0], [100.0, 50.0, 0.0], [100.0, 50.0, 0.0]],
        lamp_sets=[LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )


def test_hl2x_series_group_and_eight_profiles():
    model = Hl2xModel(897.81, ts_coefficient_c_per_w=0.3)
    result = calculate_luminaire_operating_point([700] * 8, model, 4000, 70)
    assert result.converged
    assert result.total_flux_lm > 0
    assert result.total_led_power_w == pytest.approx(sum(point.group_power_w for point in result.groups))
    assert result.total_driver_power_w > result.total_led_power_w
    assert all(point.group_power_w == pytest.approx(3 * point.led_power_w) for point in result.groups)


def test_hl2x_low_current_flux_extrapolates_from_zero():
    model = Hl2xModel(897.81)
    point = model.point(50, 4000, 70, tj_c=85)
    assert point.ki == pytest.approx(0.076)
    assert point.group_flux_lm == pytest.approx(897.81 * 0.076)


def test_current_step_and_published_cct_cri_validation():
    model = Hl2xModel(897.81)
    continuous = calculate_luminaire_operating_point([725] * 8, model, 4000, 70)
    assert continuous.currents_ma == pytest.approx((725.0,) * 8)
    with pytest.raises(ValueError):
        calculate_luminaire_operating_point([700] * 8, model, 6500, 80)


def test_composition_scales_flux_and_rotates_groups():
    model = Hl2xModel(897.81)
    operating = calculate_luminaire_operating_point([700] * 8, model, 4000, 70)
    result = compose_luminaire(group_ldt(), operating, c_step_deg=15.0, gamma_step_deg=45.0)
    assert result.flux_lm == pytest.approx(operating.total_flux_lm)
    assert len(result.c_angles_deg) == 24
    assert result.c_angles_deg[1] == 15.0
    assert max(max(row) for row in result.intensities_cd_per_klm) > 0


def test_road_uses_virtual_groups_without_composed_ldt():
    model = Hl2xModel(897.81)
    operating = calculate_luminaire_operating_point([700] * 8, model, 4000, 70)
    sources = _virtual_sources(operating)
    composed = compose_luminaire(group_ldt(), operating, c_step_deg=15.0, gamma_step_deg=45.0)
    expected = composed.intensity_cd_per_klm(30.0, 45.0) * composed.flux_lm / 1000.0
    actual = _group_intensity_cd(group_ldt(), sources, 30.0, 45.0)
    assert actual == pytest.approx(expected)
    assert len(sources) == 8
    assert all(source.flux_lm > 0 for source in sources)


def test_complete_group_composition_has_no_c180_to_c360_emission():
    model = Hl2xModel(897.81)
    operating = calculate_luminaire_operating_point([700] * 8, model, 4000, 70)
    composed = compose_luminaire(group_ldt(), operating, c_step_deg=15.0, gamma_step_deg=45.0)
    assert composed.intensity_cd_per_klm(270.0, 45.0) == pytest.approx(0.0)


def test_directional_group_ldt_is_rotated_clockwise_into_road_frame():
    directional = LdtPhotometry(
        company="TEST",
        name="Directional group",
        c_angles_deg=[0.0, 90.0, 180.0],
        gamma_angles_deg=[0.0, 45.0, 90.0],
        intensities_cd_per_klm=[[100.0, 100.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        lamp_sets=[LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )
    operating = calculate_luminaire_operating_point([700] * 8, Hl2xModel(897.81), 4000, 70)
    sources = _virtual_sources(operating, angles_deg=(0.0,) * 8)
    assert GROUP_C_ROTATION_DEG == pytest.approx(90.0)
    assert _group_intensity_cd(directional, sources, 90.0, 45.0) > 0
    assert _group_intensity_cd(directional, sources, 0.0, 45.0) == pytest.approx(0.0)


def test_photometric_profile_reports_oriented_curve():
    model = Hl2xModel(897.81)
    operating = calculate_luminaire_operating_point([700] * 8, model, 4000, 70)
    profile = photometric_azimuth_profile(group_ldt(), operating, gamma_deg=45, samples=36)
    assert profile["gamma_deg"] == 45
    assert len(profile["c_angles_deg"]) == 36
    assert len(profile["normalized"]) == 36
    assert max(profile["normalized"]) == pytest.approx(1.0)
    assert len(profile["groups"]) == 8
    assert all(len(group["normalized"]) == 36 for group in profile["groups"])
    for index, total in enumerate(profile["intensity_cd"]):
        assert total == pytest.approx(sum(group["intensity_cd"][index] for group in profile["groups"]))


def test_ldt_round_trip():
    original = group_ldt()
    parsed = parse_ldt_text(ldt_text(original))
    assert parsed.flux_lm == pytest.approx(original.flux_lm)
    assert parsed.power_w == pytest.approx(original.power_w)
    assert parsed.intensity_cd_per_klm(30, 30) == pytest.approx(original.intensity_cd_per_klm(30, 30))


def test_custom_rtable_loader(tmp_path: Path):
    path = tmp_path / "custom.rtb"
    path.write_text("""RTable.v1\nC2 test\n2\n0\n12\n3\n0\n90\n180\n10\n20\n30\n40\n50\n60\n""", encoding="latin-1")
    table = load_rtable(path)
    assert table.name == "C2 test"
    assert table.value(6, 45) == pytest.approx(0.003)


def test_road_scenario_defaults_and_validation():
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0)
    assert scenario.carriageway_width_m == 3.5
    assert scenario.lighting_class == "M3"
    with pytest.raises(ValueError):
        RoadScenario(height_m=1.0, spacing_m=10.0, carriageway_width_m=4.0)
    with pytest.raises(ValueError):
        RoadScenario(height_m=1.0, spacing_m=10.0, tilt_deg=10.1)


def test_tilt_rotates_the_complete_luminaire_frame():
    zero = _angles_to_point(2.0, 0.0, -1.0, 0.0, 0.0)
    tilted = _angles_to_point(2.0, 0.0, -1.0, 0.0, 10.0)
    assert tilted[1] == pytest.approx(zero[1])
    assert tilted[2] != pytest.approx(zero[2])


def test_edge_offset_is_transverse_not_longitudinal():
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0, edge_offset_m=0.75)
    positions = _positions(scenario, k_min=0, k_max=1)
    assert [position[0] for position in positions] == [0.0, 10.0]
    assert [position[1] for position in positions] == [-0.75, -0.75]
    assert [position[2] for position in positions] == [0.0, 0.0]


def test_luminance_grid_uses_cie_140_centered_longitudinal_points():
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0)
    xs, _, _ = _road_points(scenario)
    assert xs == pytest.approx([0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5])


def test_bilateral_rows_face_the_carriageway():
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0, arrangement="bilateral_paired")
    positions = _positions(scenario, k_min=0, k_max=0)
    assert [position[2] for position in positions] == [0.0, 180.0]


def test_right_side_unilateral_luminaire_is_rotated_180_degrees():
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0, pole_side="right")
    positions = _positions(scenario, k_min=0, k_max=0)
    assert positions[0][2] == pytest.approx(180.0)


def test_row_orientation_maps_interior_to_local_c90():
    left = _angles_to_point(0.0, 1.0, -1.0, 0.0, 0.0)
    right = _angles_to_point(0.0, -1.0, -1.0, 180.0, 0.0)
    assert left[1] == pytest.approx(90.0)
    assert right[1] == pytest.approx(90.0)


def test_directional_ldt_does_not_wrap_c180_to_c0():
    photometry = LdtPhotometry(
        company="TEST",
        name="Directional group",
        c_angles_deg=[0.0, 90.0, 180.0],
        gamma_angles_deg=[0.0, 45.0, 90.0],
        intensities_cd_per_klm=[[100.0, 50.0, 0.0]] * 3,
        lamp_sets=[LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )
    assert photometry.intensity_cd_per_klm(180.0, 45.0) == pytest.approx(50.0)
    assert photometry.intensity_cd_per_klm(270.0, 45.0) == pytest.approx(0.0)


def test_ul_uses_the_lane_centerline_not_transverse_extrema():
    grid = np.array([[[1.0, 10.0, 2.0], [2.0, 8.0, 4.0]]])
    assert luminance_uniformity(grid) == pytest.approx((4.5, 1.0 / 4.5, 0.8))


def test_beta_uses_cie_140_complementary_angle():
    # Observer and luminaire are on opposite sides of the calculation point
    # along the longitudinal axis: theta=180, therefore beta=0.
    assert _beta(0, 0, -10, 0, 10, 0) == pytest.approx(0.0)
    # Same-side aligned directions give theta=0, therefore beta=180.
    assert _beta(0, 0, 10, 0, 20, 0) == pytest.approx(180.0)


def test_symmetric_profile_mirrors_the_four_optical_pairs():
    assert _symmetric_vector([50, 100, 150, 200]) == [50, 100, 150, 200, 200, 150, 100, 50]
    assert DEFAULT_GROUP_ANGLES_DEG[0] + DEFAULT_GROUP_ANGLES_DEG[-1] == pytest.approx(180.0)


def test_uniformity_quality_prioritizes_the_weakest_uniformity():
    assert _uniformity_quality(0.70, 0.70) < _uniformity_quality(0.70, 0.69)
    assert _uniformity_quality(0.70, 0.75) < _uniformity_quality(0.68, 0.80)


def test_optimizer_returns_tilt_and_relative_current_solution():
    table = ReducedLuminanceTable(
        "test",
        (0.0, 1.0, 2.0, 5.0, 10.0),
        tuple(float(value) for value in range(0, 181, 10)),
        tuple(tuple(1000.0 for _ in range(19)) for _ in range(5)),
    )
    result = optimize_currents_and_tilt(
        group_ldt(), Hl2xModel(897.81), RoadScenario(height_m=1.0, spacing_m=10.0),
        table, cct_k=4000, cri=70, optimization_mode="independent",
    )
    assert -10.0 <= result.calculation.scenario.tilt_deg <= 10.0
    assert len(result.currents_ma) == 8
    assert "Tilt optimizado" in result.message


def test_symmetric_photometry_averages_the_reflected_base_ldt():
    photometry = LdtPhotometry(
        "TEST", "Asymmetric", [0.0, 90.0, 180.0, 270.0], [0.0, 45.0, 90.0],
        [[10.0, 4.0, 0.0], [20.0, 5.0, 0.0], [30.0, 6.0, 0.0], [40.0, 7.0, 0.0]],
        [LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )
    assert _base_group_intensity(photometry, 30.0, 45.0, symmetric=False) != pytest.approx(
        _base_group_intensity(photometry, 150.0, 45.0, symmetric=False),
    )
    assert _base_group_intensity(photometry, 30.0, 45.0, symmetric=True) == pytest.approx(
        _base_group_intensity(photometry, 150.0, 45.0, symmetric=True),
    )


def test_symmetric_composed_photometry_mirrors_the_complete_luminaire():
    photometry = LdtPhotometry(
        "TEST", "Asymmetric", [0.0, 90.0, 180.0, 270.0], [0.0, 45.0],
        [[10.0, 4.0], [20.0, 5.0], [30.0, 6.0], [40.0, 7.0]],
        [LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )
    operating = calculate_luminaire_operating_point([700] * 8, Hl2xModel(897.81), 4000, 70)
    sources = _virtual_sources(operating)
    for angle in range(0, 180, 15):
        assert _group_intensity_cd(photometry, sources, angle, 45.0, symmetric=True) == pytest.approx(
            _group_intensity_cd(photometry, sources, 180.0 - angle, 45.0, symmetric=True),
        )


def test_c90_and_c270_are_not_a_mirror_pair():
    photometry = LdtPhotometry(
        "TEST", "Planes", [0.0, 90.0, 180.0, 270.0], [0.0, 45.0],
        [[10.0, 4.0], [20.0, 5.0], [30.0, 6.0], [40.0, 7.0]],
        [LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )
    pairs = {(pair["c_deg"], pair["mirror_c_deg"]) for pair in ldt_diagnostic(photometry)["pairs"]}
    assert (90.0, 90.0) in pairs
    assert (270.0, 270.0) in pairs
    assert (90.0, 270.0) not in pairs
    assert (270.0, 90.0) not in pairs


def test_ldt_diagnostic_marks_non_symmetric_c_plane_pairs():
    photometry = LdtPhotometry(
        "TEST", "Asymmetric", [0.0, 90.0, 180.0, 270.0], [0.0, 45.0],
            [[10.0, 4.0], [20.0, 5.0], [30.0, 6.0], [40.0, 7.0]],
        [LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )
    diagnostic = ldt_diagnostic(photometry)
    assert diagnostic["symmetric"] is False
    assert any(not pair["symmetric"] for pair in diagnostic["pairs"])


def test_symmetric_base_photometry_is_mirrored_about_c90():
    model = Hl2xModel(897.81)
    photometry = LdtPhotometry(
        "TEST", "Asymmetric", [0.0, 90.0, 180.0, 270.0], [0.0, 45.0, 90.0],
        [[10.0, 4.0, 0.0], [20.0, 5.0, 0.0], [30.0, 6.0, 0.0], [40.0, 7.0, 0.0]],
        [LampSet("3", "HL2X", 897.81, "4000K", "70", 6.6)],
    )
    for angle in range(0, 360, 15):
        assert _base_group_intensity(photometry, angle, 45.0, symmetric=True) == pytest.approx(
            _base_group_intensity(photometry, 180.0 - angle, 45.0, symmetric=True),
        )


def test_precomputed_luminance_matches_road_calculation():
    model = Hl2xModel(897.81)
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0)
    table = ReducedLuminanceTable(
        "test",
        (0.0, 1.0, 2.0, 5.0, 10.0),
        tuple(float(value) for value in range(0, 181, 10)),
        tuple(tuple(1000.0 for _ in range(19)) for _ in range(5)),
    )
    influence = precompute_luminance_influence(group_ldt(), scenario, table)
    operating = calculate_luminaire_operating_point([700] * 8, model, 4000, 70)
    calculated = calculate_road(
        group_ldt(), model, [700] * 8, scenario, table,
        cct_k=4000, cri=70,
    )
    fast = luminance_from_flux(
        influence,
        np.array([point.group_flux_lm for point in operating.groups]),
    )
    np.testing.assert_allclose(fast[0], calculated.visual_grid["luminance_cd_m2"])


def test_complete_luminaire_ldt_can_be_evaluated_as_reference_road():
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0)
    table = ReducedLuminanceTable(
        "test",
        (0.0, 1.0, 2.0, 5.0, 10.0),
        tuple(float(value) for value in range(0, 181, 10)),
        tuple(tuple(1000.0 for _ in range(19)) for _ in range(5)),
    )
    result = calculate_reference_road(group_ldt(), scenario, table)
    assert result.metrics.lavg_cd_m2 > 0
    assert result.visual_grid is not None
    assert result.metrics.power_limit_ok


def test_visual_grid_exposes_each_observer_lane_and_normative_profile():
    model = Hl2xModel(897.81)
    scenario = RoadScenario(
        height_m=1.0, spacing_m=10.0,
        carriageway_width_m=7.0, lane_widths_m=(3.5, 3.5),
    )
    table = ReducedLuminanceTable(
        "test",
        (0.0, 1.0, 2.0, 5.0, 10.0),
        tuple(float(value) for value in range(0, 181, 10)),
        tuple(tuple(1000.0 for _ in range(19)) for _ in range(5)),
    )
    result = calculate_road(group_ldt(), model, [700] * 8, scenario, table, cct_k=4000, cri=70)
    visual = result.visual_grid
    assert len(visual["lane_grids"]) == 2
    assert [grid["observer_y_m"] for grid in visual["lane_grids"]] == [1.75, 5.25]
    assert len(visual["lane_profiles"]) == 2
    assert visual["normative_profile"]["lane_index"] == visual["worst_lane_index"]


def test_symmetric_isolux_is_mirrored_about_midpoint_between_luminaires():
    model = Hl2xModel(897.81)
    scenario = RoadScenario(height_m=1.0, spacing_m=10.0, photometry_symmetry="symmetric")
    table = ReducedLuminanceTable(
        "test",
        (0.0, 1.0, 2.0, 5.0, 10.0),
        tuple(float(value) for value in range(0, 181, 10)),
        tuple(tuple(1000.0 for _ in range(19)) for _ in range(5)),
    )
    result = calculate_road(group_ldt(), model, [700] * 8, scenario, table, cct_k=4000, cri=70)
    isolux = [row[1] for row in result.visual_grid["illuminance_lx"]]
    np.testing.assert_allclose(isolux, isolux[::-1], rtol=1e-5, atol=1e-5)


def test_batch_uniformity_matches_single_candidate_evaluation():
    rng = np.random.default_rng(7)
    grids = rng.random((5, 1, 10, 3))
    averages, uos, uls = luminance_uniformity_batch(grids)
    for index, grid in enumerate(grids):
        assert averages[index] == pytest.approx(luminance_uniformity(grid)[0])
        assert uos[index] == pytest.approx(luminance_uniformity(grid)[1])
        assert uls[index] == pytest.approx(luminance_uniformity(grid)[2])
