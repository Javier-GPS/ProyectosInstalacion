"""EN 13201-3 grid geometry and TI formula tests."""
import math

import pytest

from app.salvi_lighting.calc import (
    OBSERVER_H,
    _veiling_luminance,
    _illuminance_transverse_positions,
    _longitudinal_positions,
    _luminance_grid,
    _luminance_transverse_positions,
    _n_lanes_and_width,
    _n_longitudinal,
    _ti_from_luminances,
)


# ── Longitudinal point count ────────────────────────────────────────────────

@pytest.mark.parametrize("S, expected_N", [
    (10.0, 10),   # S ≤ 30 → N = 10 (D = 1 m)
    (20.0, 10),   # S ≤ 30 → N = 10 (D = 2 m)
    (30.0, 10),   # boundary: S = 30 → N = 10 (D = 3 m)
    (30.001, 11), # S > 30 → smallest N with D ≤ 3
    (36.0, 12),   # S = 36 → N = 12 (D = 3 m)
    (40.0, 14),   # N = ceil(40/3) = 14 (D ≈ 2.86 m)
    (50.0, 17),   # N = ceil(50/3) = 17 (D ≈ 2.94 m)
    (60.0, 20),   # N = 60/3 = 20 (D = 3 m)
])
def test_n_longitudinal_matches_cie_140(S, expected_N):
    assert _n_longitudinal(S) == expected_N
    # D ≤ 3 must always hold once S > 30
    if S > 30.0:
        assert S / _n_longitudinal(S) <= 3.0 + 1e-9


def test_longitudinal_positions_are_centred():
    # x_i = (2i − 1) · S / (2N), first point at D/2 and last at S − D/2
    S, N = 30.0, 10
    xs = _longitudinal_positions(S, N)
    assert xs[0] == pytest.approx(S / (2 * N))
    assert xs[-1] == pytest.approx(S - S / (2 * N))
    assert len(xs) == N


# ── Transverse positions ────────────────────────────────────────────────────

def test_luminance_grid_uses_three_transverse_points_for_carriageway():
    # EN 13201-3: n = 3 per lane for luminance
    n_lanes, lane_w = _n_lanes_and_width(7.0)
    ys = _luminance_transverse_positions(n_lanes, lane_w)
    assert n_lanes == 2
    assert lane_w == 3.5
    assert len(ys) == 6
    assert ys[0] == pytest.approx(3.5 / 6)
    assert ys[2] == pytest.approx(5 * 3.5 / 6)
    assert ys[3] == pytest.approx(3.5 + 3.5 / 6)
    assert ys[5] == pytest.approx(3.5 + 5 * 3.5 / 6)


def test_luminance_grid_respects_configured_lanes():
    xs, ys, n_lanes, lane_w = _luminance_grid({"S": 30.0, "W": 5.0, "lanes": 2})
    assert len(xs) == 10
    assert len(ys) == 6
    assert n_lanes == 2
    assert lane_w == pytest.approx(2.5)


def test_illuminance_grid_respects_1_5_m_transverse_spacing():
    # CIE 140-2000 / EN 13201-3: D_lat ≤ 1.5 m
    # 3.5 m lane → ceil(3.5/1.5) = 3 → D_lat = 1.17 m
    n_lanes, lane_w = _n_lanes_and_width(7.0)
    ys = _illuminance_transverse_positions(n_lanes, lane_w)
    assert len(ys) == 6  # 3 per lane × 2 lanes
    # 5 m lane → ceil(5/1.5) = 4 → D_lat = 1.25 m
    ys_wide = _illuminance_transverse_positions(1, 5.0)
    assert len(ys_wide) == 4
    spacing = ys_wide[1] - ys_wide[0]
    assert spacing <= 1.5 + 1e-9


# ── Threshold Increment two-branch formula ──────────────────────────────────

def test_ti_low_luminance_branch():
    # Lavg ≤ 5 → TI = 65 · Lv / Lav^0.8
    Lavg = 1.0
    Lv = 0.05
    assert _ti_from_luminances(Lv, Lavg) == pytest.approx(65 * Lv / Lavg ** 0.8)


def test_ti_high_luminance_branch():
    # Lavg > 5 → TI = 95 · Lv / Lav^1.05
    Lavg = 10.0
    Lv = 1.0
    assert _ti_from_luminances(Lv, Lavg) == pytest.approx(95 * Lv / Lavg ** 1.05)


def test_ti_boundary_at_five_uses_low_branch():
    # Boundary value Lavg = 5 stays in the low-luminance regime
    Lavg = 5.0
    Lv = 0.1
    assert _ti_from_luminances(Lv, Lavg) == pytest.approx(65 * Lv / Lavg ** 0.8)


def test_ti_handles_zero_luminance():
    assert _ti_from_luminances(0.0, 0.0) == 999.0


def test_veiling_luminance_uses_dialux_scale():
    class Photometry:
        flux = 1000.0

        def intensity(self, C, gamma):
            return 1000.0

    class Luminaire:
        x0 = 0.0
        y0 = 0.0
        h = OBSERVER_H + 2.0
        ph = Photometry()
        flux_scale = 1.0
        mf = 1.0
        mirror_y = False
        _ct = 1.0
        _st = 0.0

    eye = (-10.0, 0.0, OBSERVER_H)
    dz = 2.0
    d = math.sqrt(10.0 ** 2 + dz ** 2)
    alpha = math.radians(-1.0)
    cos_theta = (10.0 * math.cos(alpha) + dz * math.sin(alpha)) / d
    theta = math.degrees(math.acos(cos_theta))
    expected_e_eye = 1000.0 * cos_theta / (d * d)
    age = 23.0

    assert _veiling_luminance([Luminaire()], eye) == pytest.approx(
        9.86 * (1.0 + (age / 66.4) ** 4) * expected_e_eye / (theta * theta)
    )
