"""EN 13201-3 observer placement.

Lavg / Uo / TI → per-lane observer at lane centre, worst operative value.
Ul             → per-lane observer at lane centre, worst ratio reported.
"""
from app.salvi_lighting.calc import (
    _lane_centre_ys,
    _main_observer_y,
    _observer_y_for_luminance,
)


def test_main_observer_at_three_quarter_W_for_two_lane_road():
    # Legacy helper kept for old external callers.
    assert _main_observer_y(7.0) == 5.25


def test_main_observer_at_three_quarter_W_for_single_lane_road():
    # Legacy helper kept for old external callers.
    assert _main_observer_y(3.5) == 2.625


def test_lane_centres_for_two_lane_road():
    # 2 lanes of 3.5 m → centres at 1.75 and 5.25
    assert _lane_centre_ys(2, 3.5) == [1.75, 5.25]


def test_lane_centres_for_three_lane_road():
    # 3 lanes of 3.5 m → centres at 1.75, 5.25, 8.75
    assert _lane_centre_ys(3, 3.5) == [1.75, 5.25, 8.75]


def test_observer_y_helper_returns_main_observer_for_any_arrangement():
    # Backward-compatible wrapper still returns 3W/4 regardless of pole side.
    assert _observer_y_for_luminance({"W": 7.0, "arrangement": "Lineal", "pole_side": "left"}) == 5.25
    assert _observer_y_for_luminance({"W": 7.0, "arrangement": "Lineal", "pole_side": "right"}) == 5.25
    assert _observer_y_for_luminance({"W": 10.5, "arrangement": "Bilateral"}) == 7.875
