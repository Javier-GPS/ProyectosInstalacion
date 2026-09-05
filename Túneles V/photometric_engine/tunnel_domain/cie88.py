"""
CIE 88:2004 Tunnel Lighting — Zone Model and Normative Requirements
====================================================================
Defines zone types, luminance requirements, uniformity limits and
the L20/Lth/Lin relationship per CIE 88:2004.

Key formulas:
  Lth  = k × L20          (k from Table 4 of CIE 88, function of v and position)
  L_tr = Lth × (1.9+t)^(-1.4)   (transition curve)
  Lin  ≥ 2–10 cd/m²              (interior, function of L20 and category)

The threshold luminance multiplier k depends on:
  • vehicle speed (design speed)
  • access zone length (stopping distance based)
  • whether measured L20 includes sky, surroundings, road, etc.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ── Zone type ────────────────────────────────────────────────────────────────

ZONE_TYPES = ("access", "threshold", "transition", "interior", "exit",
              "emergency", "transition_b")


@dataclass
class TunnelZone:
    """
    One zone of a tunnel (CIE 88:2004 §4).

    Attributes
    ----------
    zone_type    : one of ZONE_TYPES
    s_start      : longitudinal start [m] (from portal A)
    s_end        : longitudinal end [m]
    L_req        : required average luminance [cd/m²]
    U0_min       : minimum overall luminance uniformity (default CIE 88)
    Ul_min       : minimum longitudinal luminance uniformity
    TI_max       : maximum threshold increment [%]
    """
    zone_type:  str
    s_start:    float
    s_end:      float
    L_req:      float
    U0_min:     float = 0.40
    Ul_min:     float = 0.60
    TI_max:     float = 15.0

    @property
    def length(self) -> float:
        return max(0.0, self.s_end - self.s_start)


# ── CIE 88 parameter tables ───────────────────────────────────────────────────

# Stopping distance [m] for design speed [km/h]  (CIE 88:2004 Table 1)
_STOPPING_DIST = {
    40:  45,
    50:  65,
    60:  85,
    70: 110,
    80: 140,
    90: 175,
    100: 215,
    120: 300,
}

# Threshold multiplier k (CIE 88:2004 Table 4, simplified interpolation)
# k = Lth / L20   for observer at stopping distance D from portal
# Values for D ≤ 160 m (common range), speed 60–100 km/h:
#   speed  60: k=0.035   70: k=0.040   80: k=0.050   100: k=0.058
_K_THRESHOLD = {
    40: 0.025, 50: 0.030, 60: 0.035,
    70: 0.040, 80: 0.050, 90: 0.054,
    100: 0.058, 120: 0.065,
}

# Interior luminance Lin [cd/m²] for day condition as function of L20
# (CIE 88:2004 §4.4, simplified: Lin ≈ max(2, min(10, 0.01 × L20)))
_LIN_MIN = 2.0
_LIN_MAX = 10.0


def stopping_distance(speed_kmh: float) -> float:
    """Interpolated stopping distance [m] for design speed [km/h]."""
    speeds = sorted(_STOPPING_DIST.keys())
    if speed_kmh <= speeds[0]:
        return float(_STOPPING_DIST[speeds[0]])
    if speed_kmh >= speeds[-1]:
        return float(_STOPPING_DIST[speeds[-1]])
    for i in range(len(speeds) - 1):
        v0, v1 = speeds[i], speeds[i + 1]
        if v0 <= speed_kmh <= v1:
            t = (speed_kmh - v0) / (v1 - v0)
            return (1 - t) * _STOPPING_DIST[v0] + t * _STOPPING_DIST[v1]
    return 140.0


def threshold_multiplier(speed_kmh: float) -> float:
    """k = Lth / L20 for given design speed."""
    speeds = sorted(_K_THRESHOLD.keys())
    if speed_kmh <= speeds[0]:
        return _K_THRESHOLD[speeds[0]]
    if speed_kmh >= speeds[-1]:
        return _K_THRESHOLD[speeds[-1]]
    for i in range(len(speeds) - 1):
        v0, v1 = speeds[i], speeds[i + 1]
        if v0 <= speed_kmh <= v1:
            t = (speed_kmh - v0) / (v1 - v0)
            return (1 - t) * _K_THRESHOLD[v0] + t * _K_THRESHOLD[v1]
    return 0.050


def threshold_luminance(L20: float, speed_kmh: float) -> float:
    """Lth [cd/m²] = k(v) × L20."""
    return threshold_multiplier(speed_kmh) * L20


def interior_luminance(L20: float) -> float:
    """
    Lin [cd/m²] — required interior luminance (day condition).
    CIE 88:2004 §4.4 simplified: Lin ≈ 0.01 × L20 clamped to [2, 10] cd/m².
    """
    return max(_LIN_MIN, min(_LIN_MAX, 0.01 * L20))


def transition_luminance(t_sec: float, Lth: float, Lin: float) -> float:
    """
    Required luminance at time t [s] after threshold zone.
    L_tr(t) = Lth × (1.9 + t)^(-1.4)  ≥ Lin
    """
    return max(float(Lth * (1.9 + max(0.0, t_sec)) ** (-1.4)), Lin)


def transition_luminance_at_s(
    s:         float,
    s_start:   float,
    speed_kmh: float,
    Lth:       float,
    Lin:       float,
) -> float:
    """Transition luminance at position s [m] from tunnel start."""
    v_ms = max(speed_kmh / 3.6, 0.1)
    t    = max(0.0, (s - s_start) / v_ms)
    return transition_luminance(t, Lth, Lin)


def threshold_zone_length(speed_kmh: float) -> float:
    """
    CIE 88:2004 §4.3: threshold zone length = stopping distance [m].
    """
    return stopping_distance(speed_kmh)


def transition_zone_length(speed_kmh: float) -> float:
    """
    CIE 88:2004 §4.3: transition zone length for driver to adapt
    from Lth to Lin.  Approximately = stopping distance as well.
    Rule: time for luminance to drop to 3× Lin ≈ stopping distance / v.
    Simplified conservative value used here.
    """
    return stopping_distance(speed_kmh)


# ── Zone builder ──────────────────────────────────────────────────────────────

@dataclass
class CIE88Params:
    """All CIE 88 parameters for a single-portal tunnel calculation."""
    L20:          float           # field luminance [cd/m²]
    speed_kmh:    float           # design speed [km/h]
    tunnel_length: float          # total one-way length [m]
    bidirectional: bool = False   # bidirectional tunnel → add exit threshold

    # Computed
    Lth:  float = field(init=False)
    Lin:  float = field(init=False)
    D_stop: float = field(init=False)
    Ltr_start: float = field(init=False)

    def __post_init__(self):
        self.Lth    = threshold_luminance(self.L20, self.speed_kmh)
        self.Lin    = interior_luminance(self.L20)
        self.D_stop = stopping_distance(self.speed_kmh)
        # Luminance at start of transition (t=0): Lth × 1.9^(-1.4)
        self.Ltr_start = transition_luminance(0, self.Lth, self.Lin)


def build_zones(params: CIE88Params) -> list[TunnelZone]:
    """
    Build the canonical CIE 88:2004 zone list for a portal-A configuration.

    Returns zones ordered by s_start.
    """
    D = params.D_stop
    L = params.tunnel_length
    Lth   = params.Lth
    Lin   = params.Lin

    zones: list[TunnelZone] = []
    s = 0.0

    # 1. Access zone (outside tunnel — informative only)
    zones.append(TunnelZone(
        zone_type="access",
        s_start=max(0.0, -D),
        s_end=0.0,
        L_req=Lth,   # same luminance as threshold
        U0_min=0.40, Ul_min=0.60, TI_max=15.0,
    ))

    # 2. Threshold zone (entry, from portal to D)
    s_th_end = min(D, L)
    zones.append(TunnelZone(
        zone_type="threshold",
        s_start=0.0,
        s_end=s_th_end,
        L_req=Lth,
        U0_min=0.40, Ul_min=0.60, TI_max=15.0,
    ))
    s = s_th_end

    # 3. Transition zone A (portal A side)
    s_tr_end = min(s + D, L)
    if s_tr_end > s:
        # L_req for transition = mean of curve (approx Lth/2 … Lin)
        # For compliance check we use Lin (most conservative) — actual curve
        # is evaluated point-by-point in the optic_selector.
        L_tr_mean = (params.Ltr_start + Lin) / 2.0
        zones.append(TunnelZone(
            zone_type="transition",
            s_start=s,
            s_end=s_tr_end,
            L_req=L_tr_mean,
            U0_min=0.40, Ul_min=0.60, TI_max=15.0,
        ))
        s = s_tr_end

    # 4. Interior zone
    s_int_end = L if not params.bidirectional else L - D
    if s_int_end > s:
        zones.append(TunnelZone(
            zone_type="interior",
            s_start=s,
            s_end=max(s, s_int_end),
            L_req=Lin,
            U0_min=0.40, Ul_min=0.60, TI_max=10.0,
        ))
        s = max(s, s_int_end)

    # 5. Transition zone B (portal B side, bidirectional)
    if params.bidirectional and s < L:
        s_trb_end = min(s + D, L)
        if s_trb_end > s:
            L_tr_mean = (params.Ltr_start + Lin) / 2.0
            zones.append(TunnelZone(
                zone_type="transition_b",
                s_start=s,
                s_end=s_trb_end,
                L_req=L_tr_mean,
                U0_min=0.40, Ul_min=0.60, TI_max=15.0,
            ))
            s = s_trb_end

    # 6. Threshold zone B (bidirectional)
    if params.bidirectional and s < L:
        zones.append(TunnelZone(
            zone_type="threshold_b",
            s_start=s,
            s_end=L,
            L_req=Lth,
            U0_min=0.40, Ul_min=0.60, TI_max=15.0,
        ))

    return zones
