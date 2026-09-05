"""
Tests for CIE 88:2004 zone model.
"""
import pytest
from ..tunnel_domain.cie88 import (
    CIE88Params, build_zones,
    threshold_luminance, interior_luminance,
    transition_luminance, stopping_distance,
    threshold_multiplier,
)


def test_stopping_distance_80():
    """Speed 80 km/h → 140 m stopping distance."""
    assert abs(stopping_distance(80) - 140) < 1


def test_stopping_distance_interpolation():
    """Intermediate speed interpolated correctly."""
    d = stopping_distance(75)
    assert 110 < d < 140  # between 70 and 80 km/h values


def test_threshold_luminance():
    """Lth = k × L20."""
    k80 = threshold_multiplier(80)
    Lth = threshold_luminance(L20=2000, speed_kmh=80)
    assert abs(Lth - k80 * 2000) < 0.1


def test_interior_luminance_min():
    """Very low L20 → Lin clamped at 2 cd/m²."""
    Lin = interior_luminance(100)
    assert Lin == 2.0


def test_interior_luminance_max():
    """Very high L20 → Lin clamped at 10 cd/m²."""
    Lin = interior_luminance(5000)
    assert Lin == 10.0


def test_transition_luminance_decreasing():
    """Transition luminance decreases monotonically with time."""
    Lth, Lin = 200, 5.0
    L_prev = float("inf")
    for t in [0, 1, 2, 5, 10, 20, 30, 60]:
        L = transition_luminance(t, Lth, Lin)
        assert L <= L_prev + 1e-9
        assert L >= Lin
        L_prev = L


def test_transition_luminance_floor():
    """Transition luminance never goes below Lin."""
    Lth, Lin = 200, 5.0
    L = transition_luminance(1000, Lth, Lin)
    assert abs(L - Lin) < 0.01


def test_build_zones_ordering():
    """Zones are ordered by s_start and span the full tunnel."""
    params = CIE88Params(L20=2000, speed_kmh=80, tunnel_length=500, bidirectional=False)
    zones = build_zones(params)
    # Filter out access zone (outside tunnel)
    inner = [z for z in zones if z.s_start >= 0]
    # All inner zones start after the previous ends
    for i in range(len(inner) - 1):
        assert inner[i].s_end <= inner[i + 1].s_start + 0.01

    # Last zone should end at tunnel length
    assert abs(inner[-1].s_end - 500) < 1.0


def test_build_zones_lreq():
    """Threshold zone L_req == Lth, interior L_req == Lin."""
    params = CIE88Params(L20=2000, speed_kmh=80, tunnel_length=600, bidirectional=False)
    zones = build_zones(params)
    threshold = next(z for z in zones if z.zone_type == "threshold")
    interior  = next(z for z in zones if z.zone_type == "interior")
    assert abs(threshold.L_req - params.Lth) < 0.1
    assert abs(interior.L_req  - params.Lin) < 0.01


def test_bidirectional_has_threshold_b():
    """Bidirectional tunnel should have a second threshold zone."""
    params = CIE88Params(L20=2000, speed_kmh=80, tunnel_length=600, bidirectional=True)
    zones = build_zones(params)
    types = [z.zone_type for z in zones]
    assert "threshold_b" in types or "transition_b" in types
