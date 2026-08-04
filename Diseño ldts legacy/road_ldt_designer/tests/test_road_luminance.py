import pytest

from road_ldt_designer.road_ldt.domain import (
    LuminairePlacement,
    PhotometricCandidate,
    RoadGeometry,
)
from road_ldt_designer.road_ldt.road_luminance import (
    RoadLuminanceAtPoint,
    RoadObserver,
    build_lane_observers,
    deviation_angle_beta,
    evaluate_street_luminance,
    luminance_from_luminaire,
    road_luminance_at_point,
    summarize_observer_luminance,
)
from road_ldt_designer.road_ldt.street_geometry import (
    CalculationPoint,
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


def _road_point(x_m, y_m, lane_index=0):
    return CalculationPoint(
        x_m=x_m,
        y_m=y_m,
        z_m=0.0,
        normal_x=0.0,
        normal_y=0.0,
        normal_z=1.0,
        surface_name=f"lane_{lane_index + 1}",
        surface_kind="carriageway",
        lane_index=lane_index,
    )


def test_nadir_luminance_matches_rtable_formula():
    candidate = _constant_candidate()
    luminaire = LuminairePlacement(0.0, 0.0, 10.0, 1000.0)
    point = _road_point(0.0, 0.0)
    observer = RoadObserver(-60.0, 0.0, lane_index=0)

    luminance = luminance_from_luminaire(
        candidate,
        luminaire,
        point,
        observer,
        r_table="R2",
    )

    assert luminance == pytest.approx(100.0 * 0.039 / 100.0)


def test_maintenance_factor_and_luminaires_scale_linearly():
    candidate = _constant_candidate()
    luminaires = (
        LuminairePlacement(0.0, 0.0, 10.0, 1000.0),
        LuminairePlacement(0.0, 0.0, 10.0, 1000.0),
    )
    point = _road_point(0.0, 0.0)
    observer = RoadObserver(-60.0, 0.0, lane_index=0)

    result = road_luminance_at_point(
        candidate,
        luminaires,
        point,
        observer,
        maintenance_factor=0.8,
    )

    assert len(result.contributions_cd_m2) == 2
    assert result.luminance_cd_m2 == pytest.approx(2.0 * 0.039 * 0.8)


def test_beta_is_angle_between_luminaire_and_observer_planes():
    observer = RoadObserver(-60.0, 0.0, lane_index=0)
    point = _road_point(0.0, 0.0)
    luminaire_ahead = LuminairePlacement(10.0, 0.0, 10.0, 1000.0)
    luminaire_left = LuminairePlacement(0.0, 10.0, 10.0, 1000.0)

    assert deviation_angle_beta(point, luminaire_ahead, observer) == pytest.approx(0.0)
    assert deviation_angle_beta(point, luminaire_left, observer) == pytest.approx(90.0)


def test_lane_observers_are_placed_before_grid_at_lane_centres():
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.0, 4.0),
        calculation_length_m=20.0,
        longitudinal_points=2,
    )
    grid = build_street_calculation_grid(geometry)

    observers = build_lane_observers(geometry, grid)

    first_row_x = min(point.x_m for point in grid.road_points)
    assert [observer.y_m for observer in observers] == pytest.approx([1.5, 5.0])
    assert all(observer.x_m == pytest.approx(first_row_x - 60.0) for observer in observers)


def test_summary_calculates_uo_and_lane_centreline_ul():
    observer = RoadObserver(-60.0, 1.5, lane_index=0)
    data = (
        (_road_point(0.0, 1.5), 1.0),
        (_road_point(10.0, 1.5), 2.0),
        (_road_point(0.0, 0.5), 0.5),
        (_road_point(10.0, 0.5), 1.5),
    )
    results = tuple(
        RoadLuminanceAtPoint(
            point=point,
            luminance_cd_m2=value,
            contributions_cd_m2=(value,),
        )
        for point, value in data
    )

    summary = summarize_observer_luminance(observer, results)

    assert summary.luminance_avg_cd_m2 == pytest.approx(1.25)
    assert summary.uo == pytest.approx(0.4)
    assert summary.ul == pytest.approx(0.5)


def test_complete_street_evaluation_returns_worst_lane_metrics():
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.5, 3.5),
        calculation_length_m=20.0,
        longitudinal_points=4,
        transverse_points_per_lane=3,
        r_table="R2",
    )
    grid = build_street_calculation_grid(geometry)
    candidate = _constant_candidate()
    luminaires = (
        LuminairePlacement(-5.0, -1.0, 8.0, 1000.0),
        LuminairePlacement(5.0, 8.0, 8.0, 1000.0),
    )

    result = evaluate_street_luminance(
        candidate,
        luminaires,
        geometry,
        grid,
        maintenance_factor=0.8,
    )

    assert len(result.observer_results) == 2
    assert result.luminance_avg_cd_m2 == pytest.approx(
        min(item.luminance_avg_cd_m2 for item in result.observer_results)
    )
    assert result.uo == pytest.approx(min(item.uo for item in result.observer_results))
    assert result.ul == pytest.approx(min(item.ul for item in result.observer_results))
    assert 0.0 < result.uo <= 1.0
    assert 0.0 < result.ul <= 1.0
