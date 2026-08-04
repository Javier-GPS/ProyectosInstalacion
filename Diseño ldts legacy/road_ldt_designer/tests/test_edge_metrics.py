import pytest

from road_ldt_designer.road_ldt.domain import RoadGeometry, StreetBand
from road_ldt_designer.road_ldt.edge_metrics import (
    build_edge_strip_grid,
    summarize_edge_illuminance,
)


def test_edge_strips_use_common_width_limited_by_adjacent_space():
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.5, 3.5),
        calculation_length_m=20.0,
        longitudinal_points=4,
        side_bands=(
            StreetBand("acera izquierda", "left", 2.0),
            StreetBand("acera derecha", "right", 5.0),
        ),
    )

    grid = build_edge_strip_grid(geometry, transverse_points=2)

    assert grid.width_m == pytest.approx(2.0)
    assert len(grid.left_outside) == 8
    assert all(-2.0 < point.y_m < 0.0 for point in grid.left_outside)
    assert all(0.0 < point.y_m < 2.0 for point in grid.left_inside)
    assert all(5.0 < point.y_m < 7.0 for point in grid.right_inside)
    assert all(7.0 < point.y_m < 9.0 for point in grid.right_outside)


def test_rei_is_worst_side_and_sr_combines_both_sides():
    result = summarize_edge_illuminance(
        strip_width_m=3.5,
        left_outside_lx=(2.0, 2.0),
        left_inside_lx=(4.0, 4.0),
        right_inside_lx=(2.0, 2.0),
        right_outside_lx=(1.5, 1.5),
    )

    assert result.rei_left == pytest.approx(0.5)
    assert result.rei_right == pytest.approx(0.75)
    assert result.rei == pytest.approx(0.5)
    assert result.sr == pytest.approx(3.5 / 6.0)


def test_empty_edge_strip_is_rejected():
    with pytest.raises(ValueError, match="cada banda"):
        summarize_edge_illuminance(3.5, (), (1.0,), (1.0,), (1.0,))
