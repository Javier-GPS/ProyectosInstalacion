import math

import pytest

from road_ldt_designer.road_ldt.domain import (
    LuminairePlacement,
    PhotometricCandidate,
    RoadGeometry,
)
from road_ldt_designer.road_ldt.glare import (
    angle_from_line_of_sight_deg,
    build_threshold_increment_observers,
    calculate_threshold_increment,
    evaluate_street_threshold_increment,
    line_of_sight_unit_vector,
    veiling_luminance_contribution,
)
from road_ldt_designer.road_ldt.road_luminance import RoadObserver
from road_ldt_designer.road_ldt.street_geometry import (
    build_street_calculation_grid,
)


def _constant_candidate(intensity_cd_per_klm_value: float = 100.0):
    return PhotometricCandidate(
        c_angles_deg=(0.0, 90.0, 180.0, 270.0),
        gamma_angles_deg=(0.0, 45.0, 90.0, 135.0, 180.0),
        intensity_cd_per_klm=tuple(
            tuple(intensity_cd_per_klm_value for _ in range(5))
            for _ in range(4)
        ),
        flux_lm=1000.0,
    )


def test_line_of_sight_is_one_degree_below_horizontal():
    vector = line_of_sight_unit_vector()

    assert vector[0] == pytest.approx(math.cos(math.radians(1.0)))
    assert vector[1] == 0.0
    assert vector[2] == pytest.approx(-math.sin(math.radians(1.0)))


def test_standard_veiling_luminance_formula_for_theta_above_1_5_degrees():
    result = veiling_luminance_contribution(
        eye_illuminance_lx=1.0,
        theta_deg=10.0,
        observer_age_years=23.0,
    )
    expected = 9.86 * (1.0 + (23.0 / 66.4) ** 4) / 100.0

    assert result == pytest.approx(expected)


def test_near_axis_formula_is_used_below_1_5_degrees():
    result = veiling_luminance_contribution(
        eye_illuminance_lx=1.0,
        theta_deg=1.0,
        observer_age_years=23.0,
    )
    expected = 10.0 + 5.0 * (1.0 + (23.0 / 62.5) ** 4)

    assert result == pytest.approx(expected)


def test_threshold_increment_uses_only_luminaires_in_forward_screened_field():
    candidate = _constant_candidate()
    observer = RoadObserver(0.0, 0.0, lane_index=0)
    included = LuminairePlacement(100.0, 0.0, 10.0, 1000.0)
    behind = LuminairePlacement(-100.0, 0.0, 10.0, 1000.0)
    above_screen = LuminairePlacement(10.0, 0.0, 10.0, 1000.0)

    result = calculate_threshold_increment(
        candidate,
        (included, behind, above_screen),
        observer,
        initial_road_luminance_cd_m2=1.0,
    )

    assert len(result.contributions) == 1
    assert result.contributions[0].luminaire_index == 0
    assert result.ti_pct == pytest.approx(
        65.0 * result.veiling_luminance_cd_m2
    )
    assert angle_from_line_of_sight_deg(observer, included) > 1.5


def test_threshold_increment_rejects_luminance_outside_formula_range():
    with pytest.raises(ValueError, match="0.05"):
        calculate_threshold_increment(
            _constant_candidate(),
            (),
            RoadObserver(0.0, 0.0, lane_index=0),
            initial_road_luminance_cd_m2=0.01,
        )


def test_ti_observers_cover_each_lane_and_longitudinal_grid_position():
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.5, 3.5),
        calculation_length_m=20.0,
        longitudinal_points=4,
    )
    grid = build_street_calculation_grid(geometry)
    luminaires = (
        LuminairePlacement(0.0, -1.0, 8.0, 1000.0),
        LuminairePlacement(0.0, 8.0, 8.0, 1000.0),
    )

    observers = build_threshold_increment_observers(
        geometry,
        grid,
        luminaires,
    )

    assert len(observers) == 8
    assert {observer.lane_index for observer in observers} == {0, 1}
    assert min(observer.x_m for observer in observers) == pytest.approx(
        -2.75 * (8.0 - 1.5)
    )


def test_street_ti_returns_maximum_from_all_positions_and_lanes():
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.5, 3.5),
        calculation_length_m=20.0,
        longitudinal_points=4,
    )
    grid = build_street_calculation_grid(geometry)
    candidate = _constant_candidate(1000.0)
    luminaires = tuple(
        LuminairePlacement(float(x_m), -1.0, 8.0, 1000.0)
        for x_m in range(0, 121, 20)
    )

    result = evaluate_street_threshold_increment(
        candidate,
        luminaires,
        geometry,
        grid,
    )

    assert len(result.position_results) == 8
    assert result.ti_pct == pytest.approx(
        max(item.ti_pct for item in result.position_results)
    )
    assert result.critical_result.ti_pct == pytest.approx(result.ti_pct)
