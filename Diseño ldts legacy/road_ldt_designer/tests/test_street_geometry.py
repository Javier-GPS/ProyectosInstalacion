import pytest

from road_ldt_designer.road_ldt.domain import (
    AdjacentBuilding,
    RoadGeometry,
    StreetBand,
)
from road_ldt_designer.road_ldt.street_geometry import (
    build_street_calculation_grid,
)


def _complete_street() -> RoadGeometry:
    return RoadGeometry(
        carriageway_width_m=10.5,
        lane_widths_m=(3.0, 3.5, 4.0),
        calculation_length_m=30.0,
        longitudinal_points=10,
        transverse_points_per_lane=3,
        side_bands=(
            StreetBand("acera_izquierda", "left", 2.5, elevation_m=0.15),
            StreetBand("acera_derecha", "right", 3.0, elevation_m=0.15),
        ),
        buildings=(
            AdjacentBuilding(
                "edificio_izquierdo",
                "left",
                setback_m=5.0,
                facade_height_m=12.0,
                length_m=30.0,
                window_bottom_m=1.0,
                window_top_m=10.0,
            ),
            AdjacentBuilding(
                "edificio_derecho",
                "right",
                setback_m=6.0,
                facade_height_m=9.0,
                length_m=30.0,
            ),
        ),
    )


def test_lane_grids_follow_individual_lane_widths():
    grid = build_street_calculation_grid(_complete_street())

    assert len(grid.lane_grids) == 3
    assert [len(lane.points) for lane in grid.lane_grids] == [30, 30, 30]
    assert min(point.y_m for point in grid.lane_grids[0].points) == pytest.approx(0.5)
    assert max(point.y_m for point in grid.lane_grids[0].points) == pytest.approx(2.5)
    assert min(point.y_m for point in grid.lane_grids[1].points) > 3.0
    assert max(point.y_m for point in grid.lane_grids[2].points) < 10.5
    assert all(point.normal_z == 1.0 for point in grid.road_points)


def test_sidewalks_are_generated_outside_the_carriageway():
    grid = build_street_calculation_grid(_complete_street())
    left, right = grid.band_grids

    assert len(left.points) == 30
    assert all(-2.5 < point.y_m < 0.0 for point in left.points)
    assert all(point.z_m == pytest.approx(0.15) for point in left.points)
    assert all(10.5 < point.y_m < 13.5 for point in right.points)


def test_facades_face_the_street_and_windows_use_the_window_band():
    grid = build_street_calculation_grid(
        _complete_street(),
        facade_vertical_points=6,
    )
    left, right = grid.facade_grids

    assert len(left.points) == 60
    assert all(point.y_m == pytest.approx(-5.0) for point in left.points)
    assert all(point.normal_y == 1.0 for point in left.points)
    assert all(point.y_m == pytest.approx(16.5) for point in right.points)
    assert all(point.normal_y == -1.0 for point in right.points)

    assert len(grid.window_grids) == 1
    windows = grid.window_grids[0]
    assert all(1.0 < point.z_m < 10.0 for point in windows.points)
    assert all(point.surface_kind == "window" for point in windows.points)


def test_all_points_contains_horizontal_and_vertical_surfaces():
    grid = build_street_calculation_grid(_complete_street())

    expected = (
        sum(len(item.points) for item in grid.lane_grids)
        + sum(len(item.points) for item in grid.band_grids)
        + sum(len(item.points) for item in grid.facade_grids)
        + sum(len(item.points) for item in grid.window_grids)
    )
    assert len(grid.all_points) == expected


def test_carriageway_width_must_match_lane_sum():
    with pytest.raises(ValueError, match="suma de los carriles"):
        RoadGeometry(
            carriageway_width_m=8.0,
            lane_widths_m=(3.5, 3.5),
        )
