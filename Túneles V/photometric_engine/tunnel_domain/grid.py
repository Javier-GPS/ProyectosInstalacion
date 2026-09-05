"""
CIE 140:2019 Calculation Grid for Tunnel Zones
===============================================
Generates the calculation point grid per zone following CIE 140:2019 §7.1.2–7.1.3.

Grid rules (CIE 140:2019 §7.1.3):
  Longitudinal spacing D = S / N  where N ≥ 10  (S = luminaire spacing)
  Transverse spacing   d = WL / n  where n = floor(WL / 3) or ≥ 3 points/lane

  Points offset by D/2 from start and d/2 from edge (centred in sub-cells).
  The first and last longitudinal points are at D/2 from the module boundaries.

For tunnel calculations the grid covers the full zone length in x and the
carriageway width in y.  Interior zones use a fixed N per spacing period;
threshold/transition zones use a finer grid to resolve luminance gradients.
"""
from __future__ import annotations

import math
from typing import NamedTuple


class GridSpec(NamedTuple):
    """Description of one zone's calculation grid."""
    zone_name:   str
    s_start:     float
    s_end:       float
    spacing_x:   float   # longitudinal spacing D [m]
    spacing_y:   float   # transverse spacing d [m]
    n_long:      int     # number of longitudinal points
    n_trans:     int     # number of transverse points


def make_grid(
    zone_name:      str,
    zone_type:      str,
    s_start:        float,
    s_end:          float,
    luminaire_spacing: float,    # S [m] — longitudinal spacing between luminaires
    road_width:     float,       # WL [m] — carriageway width
    n_lanes:        int   = 2,   # number of lanes
    n_long_min:     int   = 10,  # minimum longitudinal points per spacing period
    n_trans_per_lane: int = 3,   # minimum transverse points per lane
) -> list[tuple[float, float]]:
    """
    Generate (x, y) calculation grid for a tunnel zone.

    Returns list of (x, y) tuples where x is the longitudinal coordinate and
    y is the transverse coordinate (measured from left road edge).

    CIE 140 convention:
      x offset from lane centre line — here x is absolute tunnel coordinate.
      y from left carriageway edge.
    """
    zone_length = max(0.0, s_end - s_start)
    if zone_length < 0.01:
        return []

    # Transverse: n_trans points per lane, covering [0, road_width]
    n_trans = max(n_lanes * n_trans_per_lane, 3)
    dy = road_width / n_trans
    ys = [dy * (i + 0.5) for i in range(n_trans)]

    # Longitudinal: use luminaire spacing if available, else fall back
    if luminaire_spacing > 0.5:
        # Number of spacing periods in zone
        n_periods = max(1, round(zone_length / luminaire_spacing))
        period    = zone_length / n_periods
        n_per_period = max(n_long_min, 10)
        D = period / n_per_period
    else:
        # Default: one point every 2 m
        D = 2.0
        n_per_period = 1

    # Total longitudinal points
    N_total = max(1, math.ceil(zone_length / D))
    D_actual = zone_length / N_total
    xs = [s_start + D_actual * (i + 0.5) for i in range(N_total)]

    # Build grid
    return [(x, y) for x in xs for y in ys]


def make_longitudinal_lines(
    zone_name:    str,
    s_start:      float,
    s_end:        float,
    road_width:   float,
    n_lanes:      int   = 2,
    n_trans:      int   = 3,    # transverse lines per lane for Ul
    n_long:       int   = 50,   # longitudinal resolution
) -> dict[float, list[float]]:
    """
    Return dict {y_position: [x0, x1, ...]} for longitudinal uniformity Ul.
    """
    dy = road_width / (n_lanes * n_trans)
    ys = [dy * (i + 0.5) for i in range(n_lanes * n_trans)]
    dx = (s_end - s_start) / n_long
    xs = [s_start + dx * (i + 0.5) for i in range(n_long)]
    return {y: xs for y in ys}
