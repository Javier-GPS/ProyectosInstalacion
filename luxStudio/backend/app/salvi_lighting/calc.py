"""CIE 140 / EN 13201 street-lighting calculator (strict implementation).

Coordinates:
  x: longitudinal (along road, direction of travel)
  y: transverse, 0 = left edge of carriageway, W = right edge
  z: vertical (up positive)

LDT convention:
  C=0°   along road in direction of travel (+x)
  C=90°  across road towards road interior (+y of luminaire frame)
  gamma=0° straight down

Mounting height:
  The user-supplied ``height`` is the POLE TOP (where the bracket attaches).
  The photometry is measured from the LUMINOUS CENTRE, which sits below the
  pole top by the luminaire housing height (LDT field ``height_mm``). DIALux
  reports both: "Mounting Height" (pole top) and "Height" (luminous centre).
  This module subtracts ``photometry.housing_height_m`` from the supplied
  height so all geometry uses the luminous centre.

Observer (EN 13201-3:2015):
  Lavg / Uo / TI : per-lane observer at lane centre, operative worst case.
  Ul             : per-lane centre-line, worst ratio reported.
  TI             : line of sight is 1° below horizontal; the observer is swept
                   longitudinally from xd = 2.75 · (H - 1.5 m).
"""
import math

import functools
from decimal import Decimal, ROUND_HALF_UP

from .r_table import r_value

_OBSERVER_X = -60.0

# EN 13201-2 requirements per class (legacy SR requirement kept for compliance)
ME_REQ = {
    "M1": dict(L=2.0,  Uo=0.4,  Ul=0.7, TI=10, SR=0.5),
    "M2": dict(L=1.5,  Uo=0.4,  Ul=0.7, TI=10, SR=0.5),
    "M3": dict(L=1.0,  Uo=0.4,  Ul=0.6, TI=15, SR=0.5),
    "M4": dict(L=0.75, Uo=0.4,  Ul=0.6, TI=15, SR=0.5),
    "M5": dict(L=0.5,  Uo=0.35, Ul=0.4, TI=15, SR=0.5),
    "M6": dict(L=0.3,  Uo=0.35, Ul=0.4, TI=20, SR=0.5),
}
P_REQ = {
    "P1": dict(Eavg=15.0, Emin=3.0),
    "P2": dict(Eavg=10.0, Emin=2.0),
    "P3": dict(Eavg=7.5,  Emin=1.5),
    "P4": dict(Eavg=5.0,  Emin=1.0),
    "P5": dict(Eavg=3.0,  Emin=0.6),
    "P6": dict(Eavg=2.0,  Emin=0.4),
    # P7 in EN 13201-2:2015 = "no requirement applies" (orientation only)
    "P7": dict(Eavg=0.0,  Emin=0.0),
}


def _norm_round(value: float, places: int) -> float:
    """Round a final result as presented by EN 13201-3, using decimal half-up."""
    numeric = float(value)
    if not math.isfinite(numeric):
        return numeric
    quantum = Decimal("1").scaleb(-places)
    return float(Decimal(str(numeric)).quantize(quantum, rounding=ROUND_HALF_UP))


def _passes_min(value: float, required: float, places: int) -> bool:
    return _norm_round(value, places) >= _norm_round(required, places)


def _passes_max(value: float, required: float, places: int) -> bool:
    return _norm_round(value, places) <= _norm_round(required, places)


def _illuminance_places(required: float) -> int:
    """EN 13201-3 Table 2 presentation precision for illuminance."""
    if required < 10:
        return 2
    if required <= 20:
        return 1
    return 0


def _me_compliance(values: dict, requirements: dict) -> dict[str, bool]:
    """Compare the presented EN 13201 values with the class requirements."""
    return {
        "ok_L": _passes_min(values.get("Lavg", 0), requirements.get("L", 0), 2),
        "ok_Uo": _passes_min(values.get("Uo", 0), requirements.get("Uo", 0), 2),
        "ok_Ul": _passes_min(values.get("Ul", 0), requirements.get("Ul", 0), 2),
        "ok_TI": _passes_max(values.get("TI", 0), requirements.get("TI", 999), 0),
        "ok_SR": _passes_min(values.get("SR", 0), requirements.get("SR", 0), 2),
    }


def _p_passes(value: float, required: float) -> bool:
    return _passes_min(value, required, _illuminance_places(required))

# Observer height (CIE 140-2000): 1.5 m
OBSERVER_H = 1.5
# Observer longitudinal offset before the rear luminaire (CIE 140-2000): 60 m
OBSERVER_DIST = 60.0


class Photometry:
    """Wrap a parsed LDT dict for sampling I(C, gamma) in cd/klm."""

    def __init__(self, d):
        self.d = d
        self.Mc = d["Mc"]
        self.Dc = d["Dc"]
        self.Ng = d["Ng"]
        self.Dg = d["Dg"]
        self.I = d["I"]
        self.flux = d["lamp_sets"][0]["flux_lm"]
        self.power = d["lamp_sets"][0]["wattage"] or 1.0
        self.eff = self.flux / self.power
        self.LORL = d["LORL"] / 100.0
        self.conv = d["conv"]
        self.housing_height_m = float(d.get("height_mm", 0.0) or 0.0) / 1000.0
        self._inv_Dc = 1.0 / self.Dc
        self._inv_Dg = 1.0 / self.Dg

    @functools.lru_cache(maxsize=2048)
    def intensity(self, C_deg, gamma_deg):
        """Return I in cd/klm, bilinearly interpolated."""
        C = C_deg % 360
        ci = C * self._inv_Dc
        c0 = int(ci) % self.Mc
        c1 = (c0 + 1) % self.Mc
        tc = ci - int(ci)
        g = max(0.0, min(180.0, gamma_deg))
        gi = g * self._inv_Dg
        g0 = int(gi)
        g1 = min(g0 + 1, self.Ng - 1)
        tg = gi - g0
        i00 = self.I[c0][g0]
        i01 = self.I[c0][g1]
        i10 = self.I[c1][g0]
        i11 = self.I[c1][g1]
        v = (1 - tc) * (1 - tg) * i00 + (1 - tc) * tg * i01 + tc * (1 - tg) * i10 + tc * tg * i11
        return max(0.0, v) * self.conv


class Luminaire:
    """A luminaire instance: position, orientation, scaling."""

    def __init__(self, photometry, pos, height, aim_deg=0.0, tilt_deg=0.0,
                 flux_scale=1.0, mf=1.0, mirror_y=False):
        self.ph = photometry
        self.x0, self.y0 = pos
        self.h = height
        self.flux_scale = flux_scale
        self.mf = mf
        self.mirror_y = mirror_y
        self._ca = math.cos(-math.radians(aim_deg))
        self._sa = math.sin(-math.radians(aim_deg))
        # Positive UI/DIALux tilt pitches the optical axis toward the road.
        self._ct = math.cos(math.radians(tilt_deg))
        self._st = math.sin(-math.radians(tilt_deg))

    def _world_to_lum_frame(self, dx, dy):
        """Rotate world offset into luminaire frame, returning (rx2, ry2, rz2)."""
        rx = self._ca * dx - self._sa * dy
        ry = self._sa * dx + self._ca * dy
        if self.mirror_y:
            ry = -ry
        rz = -self.h
        ry2 = ry * self._ct - rz * self._st
        rz2 = ry * self._st + rz * self._ct
        return rx, ry2, rz2

    def _candela(self, rx2, ry2, rz2):
        """Return (cd, d, gamma) from luminaire-frame vector."""
        d = math.sqrt(rx2 * rx2 + ry2 * ry2 + rz2 * rz2)
        if d < 1e-6:
            return 0.0, d, 0.0
        cos_g = max(-1.0, min(1.0, -rz2 / d))
        gamma = math.degrees(math.acos(cos_g))
        C = math.degrees(math.atan2(ry2, rx2)) % 360
        I_cdkl = self.ph.intensity(C, gamma)
        cd = I_cdkl * (self.ph.flux / 1000.0) * self.flux_scale * self.mf
        return cd, d, gamma

    def E_at(self, x, y):
        """Illuminance contribution at (x, y) on road (z=0). Returns lux."""
        rx2, ry2, rz2 = self._world_to_lum_frame(x - self.x0, y - self.y0)
        cd, d, _ = self._candela(rx2, ry2, rz2)
        if d < 1e-6:
            return 0.0
        cos_inc = self.h / d
        return cd * cos_inc / (d * d)

    def L_at(self, x, y, observer_xy, _observer_h=OBSERVER_H, road='R3'):
        """Luminance contribution at (x, y) for observer. Returns cd/m².

        CIE 140 / CIE 144 convention:
            beta = 180 - angle_between(observer->P, luminaire->P) in plan view
        """
        rx2, ry2, rz2 = self._world_to_lum_frame(x - self.x0, y - self.y0)
        cd, d, gamma = self._candela(rx2, ry2, rz2)
        if d < 1e-6:
            return 0.0
        dx, dy = x - self.x0, y - self.y0
        tg = math.sqrt(dx * dx + dy * dy) / self.h
        opx = x - observer_xy[0]
        opy = y - observer_xy[1]
        lpx = x - self.x0
        lpy = y - self.y0
        n_op = math.hypot(opx, opy)
        n_lp = math.hypot(lpx, lpy)
        if n_op < 1e-6 or n_lp < 1e-6:
            return 0.0
        cos_th = max(-1.0, min(1.0, (opx * lpx + opy * lpy) / (n_op * n_lp)))
        theta = math.degrees(math.acos(cos_th))
        beta = 180.0 - theta
        r = r_value(tg, beta, road=road)
        return r * cd / (self.h * self.h)


def _luminous_centre_height(cfg, photometry) -> float:
    """Return luminous-centre height from pole/mounting height."""
    return max(0.1, float(cfg["h"]) - photometry.housing_height_m)


def build_luminaires(cfg, photometry, flux_scale=1.0, periods=None):
    """Build all luminaire instances covering the calculation field.

    Uses the LUMINOUS CENTRE height (pole top − LDT housing height).

    EN 13201-3 7.1.5 / 7.2.8 inclusion distances:
      - luminance uses ±5H longitudinal and lateral limits of 5H/12H/5H
      - illuminance uses ±5H
    The caller can override with periods for TI, which is the strictest case
    because the observer can be placed far before the field.
    """
    # ponytail: default longitudinal window = 5H on each side unless explicit
    # periods are requested (e.g. TI sweep needs many more luminaires ahead).
    if periods is None:
        h = _luminous_centre_height(cfg, photometry)
        S = cfg["S"]
        if S > 0:
            periods = max(5, math.ceil(5.0 * h / S) + 1)
        else:
            periods = 5
    arr = cfg["arrangement"]
    h = _luminous_centre_height(cfg, photometry)
    S = cfg["S"]
    W = cfg["W"]
    arm = cfg["arm"]
    tilt = cfg["tilt"]
    mf = cfg["mf"]

    if arr == "Lineal":
        pole_side = str(cfg.get("pole_side", "left")).lower()
        poles = [dict(side="R" if pole_side == "right" else "L", x_offset=0.0)]
    elif arr == "Bilateral":
        poles = [dict(side="L", x_offset=0.0), dict(side="R", x_offset=0.0)]
    elif arr == "Bilateral Alternada":
        pole_side = str(cfg.get("pole_side", "left")).lower()
        first = "R" if pole_side == "right" else "L"
        second = "L" if first == "R" else "R"
        poles = [dict(side=first, x_offset=0.0), dict(side=second, x_offset=S / 2.0)]
    elif arr == "Central Doble":
        poles = [dict(side="C", x_offset=0.0, mirror=False), dict(side="C", x_offset=0.0, mirror=True)]
    elif arr == "En Isleta":
        poles = [dict(side="C", x_offset=0.0, mirror=False)]
    else:
        poles = [dict(side="L", x_offset=0.0)]

    # Find carriageway edges when road_elements are present
    road_elements = cfg.get("road_elements")
    cw_left = 0.0
    cw_right = W
    if road_elements:
        z = 0.0
        for el in road_elements:
            if el.get("type") == "carriageway":
                cw_left = z
                break
            z += el.get("width", 0)
        z = W
        for el in reversed(road_elements):
            if el.get("type") == "carriageway":
                cw_right = z
                break
            z -= el.get("width", 0)

    luminaires = []
    for k in range(-periods, periods + 1):
        for p in poles:
            x = k * S + p.get("x_offset", 0.0)
            side = p["side"]
            if side == "L":
                lum_y = cw_left + arm
                mirror = False
            elif side == "R":
                lum_y = cw_right - arm
                mirror = True
            else:  # C
                lum_y = W / 2.0
                mirror = bool(p.get("mirror", False))
            luminaires.append(
                Luminaire(photometry, (x, lum_y), h,
                          aim_deg=0.0, tilt_deg=tilt,
                          flux_scale=flux_scale, mf=mf, mirror_y=mirror)
            )
    return luminaires


# ── Grid geometry (CIE 140-2000 / EN 13201-3) ───────────────────────────────

def _n_longitudinal(S: float) -> int:
    """CIE 140 longitudinal point count.

    N = 10 if S ≤ 30 m;
    N = smallest integer such that D = S/N ≤ 3 m  (S > 30 m).
    """
    if S <= 30.0:
        return 10
    return max(10, math.ceil(S / 3.0))


def _n_lanes_and_width(W: float, lanes: int | None = None) -> tuple[int, float]:
    """Number of carriageway lanes and lane width.

    Lane count = configured lanes when available, otherwise round(W / 3.5),
    clipped to ≥ 1.
    """
    n_lanes = max(1, int(lanes)) if lanes else max(1, int(round(W / 3.5)))
    return n_lanes, W / n_lanes


def _longitudinal_positions(S: float, N: int) -> list[float]:
    """Centred longitudinal grid: x_i = (2i − 1) · S / (2N), i = 1..N."""
    return [(2 * i - 1) * S / (2 * N) for i in range(1, N + 1)]


def _luminance_transverse_positions(n_lanes: int, lane_width: float, y_start: float = 0.0) -> list[float]:
    """EN 13201-3 luminance grid: 3 transverse points per lane."""
    return [
        y_start + ln * lane_width + (j + 0.5) * lane_width / 3.0
        for ln in range(n_lanes)
        for j in range(3)
    ]


def _illuminance_transverse_positions(n_lanes: int, lane_width: float, y_start: float = 0.0) -> list[float]:
    """CIE 140 illuminance grid: transverse spacing ≤ 1.5 m, min 3 per lane."""
    n_per_lane = max(3, math.ceil(lane_width / 1.5))
    ys: list[float] = []
    for ln in range(n_lanes):
        y0 = y_start + ln * lane_width
        for j in range(n_per_lane):
            ys.append(y0 + (j + 0.5) * lane_width / n_per_lane)
    return ys


def _luminance_grid(cfg, y_start: float = 0.0, carriage_w: float | None = None) -> tuple[list[float], list[float], int, float]:
    S = cfg["S"]
    W = carriage_w if carriage_w is not None else cfg["W"]
    N = _n_longitudinal(S)
    lanes = cfg.get("lanes") if carriage_w is None else None
    n_lanes, lane_w = _n_lanes_and_width(W, lanes)
    xs = _longitudinal_positions(S, N)
    ys = _luminance_transverse_positions(n_lanes, lane_w, y_start)
    return xs, ys, n_lanes, lane_w


def _illuminance_grid(cfg, y_start: float = 0.0, carriage_w: float | None = None) -> tuple[list[float], list[float], int, float]:
    S = cfg["S"]
    W = carriage_w if carriage_w is not None else cfg["W"]
    N = _n_longitudinal(S)
    lanes = cfg.get("lanes") if carriage_w is None else None
    n_lanes, lane_w = _n_lanes_and_width(W, lanes)
    xs = _longitudinal_positions(S, N)
    ys = _illuminance_transverse_positions(n_lanes, lane_w, y_start)
    return xs, ys, n_lanes, lane_w


def _lane_centre_ys(n_lanes: int, lane_width: float, y_start: float = 0.0) -> list[float]:
    """Centre y of each carriageway lane."""
    return [y_start + (ln + 0.5) * lane_width for ln in range(n_lanes)]


def _carriageway_splits(cfg) -> list[tuple[float, float]]:
    """Return (y_start, y_end) for each independent carriageway.

    For Central Doble with a median, the road is two sub-carriageways.
    Otherwise it is a single carriageway spanning [0, W].
    """
    W = cfg["W"]
    arr = cfg.get("arrangement", "")
    median = float(cfg.get("median_width", 0) or 0)
    if arr == "Central Doble" and median > 0 and median < W:
        mid = W / 2.0
        half_median = median / 2.0
        left_end = mid - half_median
        right_start = mid + half_median
        if left_end > 0 and right_start < W:
            return [(0.0, left_end), (right_start, W)]
    return [(0.0, W)]


def _sidewalk_transverse_positions(SW: float) -> list[float]:
    """3 transverse points per sidewalk strip."""
    n = 3
    return [(j + 0.5) * SW / n for j in range(n)]


def calc_sidewalk(cfg, photometry, flux_scale=1.0, side='left', _luminaires=None):
    """CIE 140 illuminance on a sidewalk strip.

    Left sidewalk: y ∈ [-SW_L, 0)
    Right sidewalk: y ∈ (W, W+SW_R]

    Returns dict with Eavg, Emin, Emax, xs, ys, Egrid or None if sidewalk width ≤ 0.
    """
    key = "sidewalk_left" if side == 'left' else "sidewalk_right"
    SW = cfg.get(key, 0)
    if SW <= 0:
        return None
    W = cfg["W"]
    S = cfg["S"]
    if _luminaires is None:
        _luminaires = build_luminaires(cfg, photometry, flux_scale=flux_scale)
    N = _n_longitudinal(S)
    xs = _longitudinal_positions(S, N)
    ys = _sidewalk_transverse_positions(SW)
    if side == 'left':
        ys_abs = [-SW + y for y in ys]
    else:
        ys_abs = [W + y for y in ys]
    Egrid = [[sum(lum.E_at(x, y) for lum in _luminaires) for y in ys_abs] for x in xs]
    Eflat = [v for row in Egrid for v in row]
    if not Eflat:
        return None
    return dict(
        Eavg=sum(Eflat) / len(Eflat),
        Emin=min(Eflat),
        Emax=max(Eflat),
        xs=xs,
        ys=ys_abs,
        Egrid=Egrid,
    )


# Backwards-compatible helpers used by tests / external callers
def _main_observer_y(W: float) -> float:
    """Return the y-coordinate of the observer in the (right) outer lane.

    Provided for backwards compatibility with earlier tests; the strict
    calculation uses one observer per lane, see ``calc_luminance``.
    """
    return 0.75 * W


def _observer_y_for_luminance(cfg, ys=None, n_lanes=None, lane_width=None) -> float:
    """Return the y-coordinate of the right-lane observer (legacy helper)."""
    return _main_observer_y(float(cfg["W"]))


# ── Calculations ─────────────────────────────────────────────────────────────

def calc_road(cfg, photometry, flux_scale=1.0, _luminaires=None, _xs=None, _ys=None, _n_lanes=None, _lane_width=None):
    if _luminaires is None:
        _luminaires = build_luminaires(cfg, photometry, flux_scale=flux_scale)
    if _xs is None:
        _xs, _ys, _n_lanes, _lane_width = _illuminance_grid(cfg)
    Egrid = [[sum(lum.E_at(x, y) for lum in _luminaires) for y in _ys] for x in _xs]
    Eflat = [v for row in Egrid for v in row]
    return dict(
        xs=_xs, ys=_ys, Egrid=Egrid,
        Eavg=sum(Eflat) / len(Eflat),
        Emin=min(Eflat),
        Emax=max(Eflat),
        n_lanes=_n_lanes,
        lane_width=_lane_width,
    )


def _veiling_luminance(luminaires, eye_xyz, max_dx=500.0):
    """Equivalent initial veiling luminance Lv per EN 13201-3:2015.

    Line of sight is 1° below horizontal. Luminaires are considered up to
    500 m ahead and below the 20° screening plane through the observer eye.
    """
    Lv = 0.0
    alpha = math.radians(-1.0)
    cos_alpha = math.cos(alpha)
    sin_alpha = math.sin(alpha)
    tan_screen = math.tan(math.radians(20.0))
    age = 23.0
    for lum in luminaires:
        dx = lum.x0 - eye_xyz[0]
        dy = lum.y0 - eye_xyz[1]
        dz = lum.h - eye_xyz[2]
        if dx <= 0.0 or dx > max_dx or dz > dx * tan_screen:
            continue
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < 1e-6:
            continue
        # EN 13201-3 formula (40): LOS is tilted 1° below horizontal.
        cos_theta = (dx * cos_alpha + dz * sin_alpha) / d
        cos_theta = max(-1.0, min(1.0, cos_theta))
        theta = math.degrees(math.acos(cos_theta))
        if theta <= 0.1 or theta > 60.0 or cos_theta <= 0.0:
            continue
        # Intensity emitted from luminaire toward the eye direction
        rx = -dx
        ry = -dy
        rz = -dz
        if lum.mirror_y:
            ry = -ry
        ry2 = ry * lum._ct - rz * lum._st
        rz2 = ry * lum._st + rz * lum._ct
        dd = math.sqrt(rx * rx + ry2 * ry2 + rz2 * rz2)
        if dd < 1e-6:
            continue
        cos_g = max(-1.0, min(1.0, -rz2 / dd))
        gamma = math.degrees(math.acos(cos_g))
        C = math.degrees(math.atan2(ry2, rx)) % 360
        cd = lum.ph.intensity(C, gamma) * (lum.ph.flux / 1000.0) * lum.flux_scale * lum.mf
        # Illuminance on plane normal to LOS at observer eye.
        E_eye = cd * cos_theta / (d * d)
        if theta <= 1.5:
            Lv += E_eye * (
                10.0 / (theta ** 3)
                + (5.0 / (theta * theta)) * (1.0 + (age / 62.5) ** 4)
            )
        else:
            Lv += 9.86 * (1.0 + (age / 66.4) ** 4) * E_eye / (theta * theta)
    return Lv


def _ti_observer_xs(S: float, H: float, N: int) -> list[float]:
    """EN 13201-3 TI observer sweep, Formula (39) plus D increments."""
    xd = 2.75 * max(0.0, H - OBSERVER_H)
    D = S / N
    return [-xd + i * D for i in range(N)]


def _ti_for_lane(luminaires, S: float, N: int, y_obs: float, H: float, Lavg_initial: float) -> tuple[float, float]:
    """Return max fTI and its Lv for one lane observer axis."""
    best_ti = 0.0
    best_lv = 0.0
    for x_obs in _ti_observer_xs(S, H, N):
        Lv = _veiling_luminance(luminaires, (x_obs, y_obs, OBSERVER_H))
        TI = _ti_from_luminances(Lv, Lavg_initial)
        if TI > best_ti:
            best_ti = TI
            best_lv = Lv
    return best_ti, best_lv


def _ti_from_luminances(Lv: float, Lavg: float) -> float:
    """CIE 140 / EN 13201 threshold increment.

    TI = 65 · Lv / Lav^0.8   if  0.05 ≤ Lav ≤ 5 cd/m²
    TI = 95 · Lv / Lav^1.05  if  Lav > 5 cd/m²
    """
    if Lavg <= 0:
        return 999.0
    if Lavg <= 5.0:
        return 65.0 * Lv / (Lavg ** 0.8)
    return 95.0 * Lv / (Lavg ** 1.05)


def _luminance_for_observer(luminaires, xs, ys, obs_xy, road):
    """Full luminance grid (cd/m²) for one observer position."""
    return [[sum(lum.L_at(x, y, obs_xy, road=road) for lum in luminaires) for y in ys]
            for x in xs]


def calc_luminance(cfg, photometry, flux_scale=1.0, road='R3',
                    _luminaires=None, _xs=None, _ys=None, _n_lanes=None, _lane_width=None,
                    _y_obs_list=None, _ti_luminaires=None):
    if _luminaires is None:
        _luminaires = build_luminaires(cfg, photometry, flux_scale=flux_scale)
    if _xs is None:
        _xs, _ys, _n_lanes, _lane_width = _luminance_grid(cfg)

    mf = float(cfg.get("mf", 1.0) or 1.0)
    ti_cfg = dict(cfg, mf=1.0)
    ti_periods = max(5, math.ceil(500.0 / max(float(cfg["S"]), 0.1)) + 2)
    ti_luminaires = _ti_luminaires or build_luminaires(ti_cfg, photometry, flux_scale=flux_scale, periods=ti_periods)

    y_obs_list = _y_obs_list if _y_obs_list is not None else _lane_centre_ys(_n_lanes, _lane_width)
    per_observer = []
    for y_obs in y_obs_list:
        obs_xy = (_OBSERVER_X, y_obs)
        Lgrid = _luminance_for_observer(_luminaires, _xs, _ys, obs_xy, road)
        Lflat = [v for row in Lgrid for v in row]
        Lavg_i = sum(Lflat) / len(Lflat)
        Lmin_i = min(Lflat)
        Lmax_i = max(Lflat)
        Uo_i = (Lmin_i / Lavg_i) if Lavg_i > 0 else 0.0
        j_obs = min(range(len(_ys)), key=lambda j: abs(_ys[j] - y_obs))
        Lline = [Lgrid[i][j_obs] for i in range(len(_xs))]
        Lmax_line = max(Lline)
        Lmin_line = min(Lline)
        Ul_i = (Lmin_line / Lmax_line) if Lmax_line > 0 else 0.0
        Lavg_initial_i = Lavg_i / mf if mf > 0 else Lavg_i
        TI_i, Lv_i = _ti_for_lane(ti_luminaires, float(cfg["S"]), len(_xs), y_obs, ti_luminaires[0].h, Lavg_initial_i)
        per_observer.append(dict(
            obs_y=y_obs, obs_xy=obs_xy, Lgrid=Lgrid,
            Lavg=Lavg_i, Lmin=Lmin_i, Lmax=Lmax_i,
            Uo=Uo_i, Ul=Ul_i, TI=TI_i, Lv=Lv_i,
        ))

    if not per_observer:
        raise ValueError("calc_luminance requires at least one lane")

    operative_L = min(per_observer, key=lambda p: p["Lavg"])
    operative_Uo = min(per_observer, key=lambda p: p["Uo"])
    operative_TI = max(per_observer, key=lambda p: p["TI"])
    worst_Ul = min(p["Ul"] for p in per_observer)
    return dict(
        Lavg=_norm_round(operative_L["Lavg"], 2), Lmin=operative_L["Lmin"], Lmax=operative_L["Lmax"],
        Uo=_norm_round(operative_Uo["Uo"], 2), Ul=_norm_round(worst_Ul, 2), TI=operative_TI["TI"], Lv=operative_TI["Lv"],
        Lgrid=operative_L["Lgrid"], xs=_xs, ys=_ys,
        n_lanes=_n_lanes, lane_width=_lane_width,
        obs=operative_L["obs_xy"],
        Ul_per_lane=[p["Ul"] for p in per_observer],
        per_observer=per_observer,
    )


def _edge_strip_illuminances(cfg, photometry, flux_scale=1.0, _luminaires=None,
                             y_start=None, y_end=None):
    """Return inner/outer strip illuminances for REI per EN 13201-3 8.6.

    The strip width is the lane width; when there is no outer strip on one
    side (e.g. the carriageway abuts the road edge), that ratio is not used
    for REI but the value is still returned as 0.0.
    """
    S = cfg["S"]
    W = cfg["W"]
    if _luminaires is None:
        _luminaires = build_luminaires(cfg, photometry, flux_scale=flux_scale)
    a = y_start if y_start is not None else 0.0
    b = y_end if y_end is not None else W
    sub_w = b - a
    # EN 13201-3 8.6: strip width equals the width of a traffic lane.
    # ponytail: we use the computed lane width for this sub-carriageway.
    n_lanes, lane_w = _n_lanes_and_width(sub_w, cfg.get("lanes") if y_start is None else None)
    # DIALux/EN 13201 SR uses adjacent strips no wider than half the
    # carriageway; for a one-lane 3.5 m road this is 1.75 m, not 3.5 m.
    strip_w = min(lane_w, sub_w / 2.0)
    N = _n_longitudinal(S)
    xs = _longitudinal_positions(S, N)

    def strip_avg(y0, y1):
        # Use the same transverse sampling density as the illuminance grid
        # (<= 1.5 m spacing) for consistent averages.
        width = y1 - y0
        if width <= 0:
            return 0.0
        n = max(3, math.ceil(width / 1.5))
        ys_s = [y0 + (j + 0.5) * width / n for j in range(n)]
        total = sum(
            sum(lum.E_at(x, y) for lum in _luminaires)
            for x in xs for y in ys_s
        )
        return total / (len(xs) * n)

    inner_L = strip_avg(a, a + strip_w)
    # Outer strips are evaluated outside the carriageway (sidewalk/verge),
    # exactly as EN 13201-3 places them.
    outer_L = strip_avg(a - strip_w, a)
    inner_R = strip_avg(b - strip_w, b)
    outer_R = strip_avg(b, b + strip_w)
    return inner_L, outer_L, inner_R, outer_R


def calc_SR(cfg, photometry, flux_scale=1.0, _luminaires=None, y_start=None, y_end=None):
    """Aggregate (outer)/(inner) ratio kept only for reporting compatibility."""
    inner_L, outer_L, inner_R, outer_R = _edge_strip_illuminances(
        cfg, photometry, flux_scale=flux_scale, _luminaires=_luminaires,
        y_start=y_start, y_end=y_end)
    denom = inner_L + inner_R
    return (outer_L + outer_R) / denom if denom > 0 else 0.0


def calc_EIR(cfg, photometry, flux_scale=1.0, _luminaires=None, y_start=None, y_end=None):
    """Edge illuminance ratio per EN 13201-3 8.6 (min of the two side ratios)."""
    inner_L, outer_L, inner_R, outer_R = _edge_strip_illuminances(
        cfg, photometry, flux_scale=flux_scale, _luminaires=_luminaires,
        y_start=y_start, y_end=y_end)
    SR_L = outer_L / inner_L if inner_L > 0 else float('inf')
    SR_R = outer_R / inner_R if inner_R > 0 else float('inf')
    return min(SR_L, SR_R)


def _add_sidewalk_results(out: dict, side: str, sw_class: str | None, sw_data: dict | None):
    """Add sidewalk illuminance results and compliance checks to ``out``."""
    key = f"sidewalk_{side}"
    cls_key = f"{key}_class"
    if sw_data is None or not sw_class:
        out[cls_key] = None
        out[f"{key}_Eavg"] = None
        out[f"{key}_Emin"] = None
        out[f"{key}_ok_Eavg"] = True
        out[f"{key}_ok_Emin"] = True
        return
    out[cls_key] = sw_class
    out[f"{key}_Eavg"] = sw_data["Eavg"]
    out[f"{key}_Emin"] = sw_data["Emin"]
    req = P_REQ.get(sw_class, {})
    if sw_class == "P7":
        out[f"{key}_ok_Eavg"] = True
        out[f"{key}_ok_Emin"] = True
    else:
        out[f"{key}_ok_Eavg"] = _p_passes(sw_data["Eavg"], req.get("Eavg", 0))
        out[f"{key}_ok_Emin"] = _p_passes(sw_data["Emin"], req.get("Emin", 0))
    out[f"{key}_req"] = req


def _sub_carriageway_luminance(cfg, photometry, flux_scale, road, luminaires,
                               y_start, y_end, lanes_override=None, ti_luminaires=None):
    """Evaluate luminance + SR for one sub-carriageway [y_start, y_end].

    When *lanes_override* is set it replaces the lane count derived from
    *cfg*, which is needed when evaluating a road-element segment whose
    lane count differs from the legacy cfg default.
    """
    sub_w = y_end - y_start
    cw_xs, cw_ys, cw_n_lanes, cw_lane_w = _luminance_grid(cfg, y_start, sub_w)
    if lanes_override is not None:
        cw_n_lanes = lanes_override
        cw_lane_w = sub_w / max(lanes_override, 1)
        cw_ys = _luminance_transverse_positions(cw_n_lanes, cw_lane_w, y_start)
    cw_y_obs = _lane_centre_ys(cw_n_lanes, cw_lane_w, y_start)
    rL = calc_luminance(cfg, photometry, flux_scale=flux_scale, road=road,
                        _luminaires=luminaires, _xs=cw_xs, _ys=cw_ys,
                        _n_lanes=cw_n_lanes, _lane_width=cw_lane_w,
                        _y_obs_list=cw_y_obs, _ti_luminaires=ti_luminaires)
    rE = calc_road(cfg, photometry, flux_scale=flux_scale,
                   _luminaires=luminaires, _xs=cw_xs, _ys=cw_ys,
                   _n_lanes=cw_n_lanes, _lane_width=cw_lane_w)
    inner_L, outer_L, inner_R, outer_R = _edge_strip_illuminances(
        cfg, photometry, flux_scale=flux_scale, _luminaires=luminaires,
        y_start=y_start, y_end=y_end)
    SR = _norm_round((outer_L + outer_R) / (inner_L + inner_R), 2) if (inner_L + inner_R) > 0 else 0.0
    SR_L = outer_L / inner_L if inner_L > 0 else 0.0
    SR_R = outer_R / inner_R if inner_R > 0 else 0.0
    EIR = min(SR_L, SR_R)
    return dict(rL=rL, rE=rE, SR=SR, EIR=EIR)


def _calc_sidewalk_range(cfg, photometry, flux_scale, luminaires, y_start, y_end):
    """Illuminance on a sidewalk strip spanning [y_start, y_end].

    Returns dict with Eavg, Emin, Emax, xs, ys, Egrid or None if width ≤ 0.
    """
    sw = y_end - y_start
    if sw <= 0:
        return None
    S = cfg["S"]
    N = _n_longitudinal(S)
    xs = _longitudinal_positions(S, N)
    ys = _sidewalk_transverse_positions(sw)
    ys_abs = [y_start + y for y in ys]
    Egrid = [[sum(lum.E_at(x, y) for lum in luminaires) for y in ys_abs] for x in xs]
    Eflat = [v for row in Egrid for v in row]
    if not Eflat:
        return None
    return dict(
        Eavg=sum(Eflat) / len(Eflat),
        Emin=min(Eflat),
        Emax=max(Eflat),
        xs=xs,
        ys=ys_abs,
        Egrid=Egrid,
    )


def _aggregate_carriageway_results(per_cw: list[dict]) -> dict:
    """Aggregate worst-case values across multiple carriageway segments."""
    out = {}
    out["Lavg"] = min(cw["rL"]["Lavg"] for cw in per_cw)
    out["Uo"] = min(cw["rL"]["Uo"] for cw in per_cw)
    out["Ul"] = min(cw["rL"]["Ul"] for cw in per_cw)
    out["TI"] = max(cw["rL"]["TI"] for cw in per_cw)
    out["Lv"] = max(cw["rL"]["Lv"] for cw in per_cw)
    out["SR"] = min(cw["SR"] for cw in per_cw)
    out["EIR"] = min(cw["EIR"] for cw in per_cw)
    out["Eavg"] = min(cw["rE"]["Eavg"] for cw in per_cw)
    out["Emin"] = min(cw["rE"]["Emin"] for cw in per_cw)
    base = min(per_cw, key=lambda cw: cw["rL"]["Lavg"])
    out["Lgrid"] = base["rL"]["Lgrid"]
    out["xs"] = base["rL"]["xs"]
    out["ys"] = base["rL"]["ys"]
    out["n_lanes"] = base["rL"]["n_lanes"]
    out["lane_width"] = base["rL"]["lane_width"]
    out["obs"] = base["rL"]["obs"]
    out["Lmin"] = base["rL"]["Lmin"]
    out["Lmax"] = base["rL"]["Lmax"]
    out["Ul_per_lane"] = base["rL"]["Ul_per_lane"]
    out["per_observer"] = base["rL"]["per_observer"]
    return out


def _evaluate_multi(cfg, photometry, flux_scale, road, luminaires, elements) -> dict:
    """Evaluate a road cross-section built from *road_elements*."""
    out: dict = {}
    per_cw: list[dict] = []
    el_results: list[dict] = []
    sw_idx = 0
    ti_periods = max(5, math.ceil(500.0 / max(float(cfg["S"]), 0.1)) + 2)
    ti_luminaires = build_luminaires(dict(cfg, mf=1.0), photometry, flux_scale=flux_scale, periods=ti_periods)

    for idx, el in enumerate(elements):
        if el["type"] == "carriageway":
            seg_w = el["width"]
            seg_start = el["y_start"]
            seg_lanes = el.get("lanes", 2)
            seg_class = el.get("lighting_class", "M3")

            seg_cfg = dict(cfg, W=seg_w, lanes=seg_lanes)
            seg_cfg["class"] = seg_class
            result = _sub_carriageway_luminance(
                seg_cfg, photometry, flux_scale, road, luminaires,
                seg_start, seg_start + seg_w, lanes_override=seg_lanes, ti_luminaires=ti_luminaires,
            )
            result["lighting_class"] = seg_class
            per_cw.append(result)

            cw_req = ME_REQ.get(seg_class, {})
            cw_values = dict(result["rL"], SR=result["SR"])
            cw_passed = _me_compliance(cw_values, cw_req) if seg_class.startswith("M") else {}
            cw_ok = all(cw_passed.values()) if cw_passed else True
            el_results.append({
                "index": idx, "type": "carriageway", "width": seg_w,
                "lighting_class": seg_class, "compliant": cw_ok,
                "criteria_passed": {
                    "Lavg": cw_passed.get("ok_L", True),
                    "Uo": cw_passed.get("ok_Uo", True),
                    "Ul": cw_passed.get("ok_Ul", True),
                    "TI": cw_passed.get("ok_TI", True),
                    "SR": cw_passed.get("ok_SR", True),
                    "EIR": True,
                },
                "criteria_required": {
                    "Lavg": cw_req.get("L", 0), "Uo": cw_req.get("Uo", 0),
                    "Ul": cw_req.get("Ul", 0), "TI": cw_req.get("TI", 0),
                    "SR": cw_req.get("SR", 0), "EIR": cw_req.get("SR", 0),
                },
                "Lavg": result["rL"]["Lavg"], "Uo": result["rL"]["Uo"],
                "Ul": result["rL"]["Ul"], "TI": result["rL"]["TI"],
                "SR": result["SR"], "EIR": result["EIR"],
                "Eavg": result["rE"]["Eavg"], "Emin": result["rE"]["Emin"],
            })

        elif el["type"] == "sidewalk":
            ped_class = el.get("pedestrian_class")
            sw = _calc_sidewalk_range(cfg, photometry, flux_scale, luminaires,
                                       el["y_start"], el["y_end"])
            _add_sidewalk_results(out, f"e{sw_idx}", ped_class, sw)
            sw_ok = True
            if sw and ped_class and ped_class != "P7":
                sw_req = P_REQ.get(ped_class, {})
                sw_passed = {
                    "Eavg": _p_passes(sw["Eavg"], sw_req.get("Eavg", 0)),
                    "Emin": _p_passes(sw["Emin"], sw_req.get("Emin", 0)),
                }
                sw_ok = all(sw_passed.values())
            else:
                sw_passed = {"Eavg": True, "Emin": True}
            el_results.append({
                "index": idx, "type": "sidewalk", "width": el["width"],
                "pedestrian_class": ped_class, "compliant": sw_ok,
                "criteria_passed": sw_passed,
                "criteria_required": {
                    "Eavg": P_REQ.get(ped_class, {}).get("Eavg", 0) if ped_class else 0,
                    "Emin": P_REQ.get(ped_class, {}).get("Emin", 0) if ped_class else 0,
                },
                "Eavg_ped": sw["Eavg"] if sw else None,
                "Emin_ped": sw["Emin"] if sw else None,
            })
            sw_idx += 1

    # Determine overall mode based on first carriageway class
    all_m = all(cw["lighting_class"].startswith("M") for cw in per_cw) if per_cw else False
    all_p = all(cw["lighting_class"].startswith("P") for cw in per_cw) if per_cw else False

    if per_cw:
        if all_m or (not all_p):
            out.update(_aggregate_carriageway_results(per_cw))
            out["mode"] = "ME"
            most_demanding = min(per_cw, key=lambda cw: ME_REQ.get(cw["lighting_class"], {}).get("L", 0))
            eclass = most_demanding["lighting_class"]
            req = ME_REQ.get(eclass, {})
            out["req"] = req
            out.update(_me_compliance(out, req))
            compliant = all([out["ok_L"], out["ok_Uo"], out["ok_Ul"], out["ok_TI"], out["ok_SR"]])
        else:
            out["Eavg"] = min(cw["rE"]["Eavg"] for cw in per_cw)
            out["Emin"] = min(cw["rE"]["Emin"] for cw in per_cw)
            out["mode"] = "P"
            eclass = per_cw[0]["lighting_class"]
            req = P_REQ.get(eclass, {})
            out["req"] = req
            if eclass == "P7":
                out["ok_Eavg"] = True
                out["ok_Emin"] = True
            else:
                out["ok_Eavg"] = _p_passes(out["Eavg"], req.get("Eavg", 0))
                out["ok_Emin"] = _p_passes(out["Emin"], req.get("Emin", 0))
            compliant = out["ok_Eavg"] and out["ok_Emin"]
    else:
        compliant = True

    for sw_key in [k for k in out if k.startswith("sidewalk_e") and k.endswith("_ok_Eavg")]:
        base_key = sw_key.replace("_ok_Eavg", "")
        ok_eavg = out.get(f"{base_key}_ok_Eavg", True)
        ok_emin = out.get(f"{base_key}_ok_Emin", True)
        compliant = compliant and ok_eavg and ok_emin

    out["compliant"] = compliant
    out["_element_results"] = el_results
    return out


def evaluate(cfg, photometry, flux_scale=1.0, road='R3'):
    elements = cfg.get("road_elements")
    luminaires = build_luminaires(cfg, photometry, flux_scale=flux_scale)

    if elements:
        return _evaluate_multi(cfg, photometry, flux_scale, road, luminaires, elements)

    # ── Legacy single-carriageway path ──────────────────────────────────
    eclass = cfg["class"]
    out: dict = {}
    splits = _carriageway_splits(cfg)

    if eclass.startswith("M"):
        if len(splits) > 1:
            per_cw = [_sub_carriageway_luminance(cfg, photometry, flux_scale, road, luminaires, ys, ye)
                      for ys, ye in splits]
            out.update(_aggregate_carriageway_results(per_cw))
        else:
            lum_xs, lum_ys, n_lanes, lane_w = _luminance_grid(cfg)
            rL = calc_luminance(cfg, photometry, flux_scale=flux_scale, road=road,
                               _luminaires=luminaires, _xs=lum_xs, _ys=lum_ys,
                               _n_lanes=n_lanes, _lane_width=lane_w)
            out.update(rL)
            rE = calc_road(cfg, photometry, flux_scale=flux_scale,
                          _luminaires=luminaires, _xs=lum_xs, _ys=lum_ys,
                          _n_lanes=n_lanes, _lane_width=lane_w)
            out["Eavg"] = rE["Eavg"]
            out["Emin"] = rE["Emin"]
            inner_L, outer_L, inner_R, outer_R = _edge_strip_illuminances(cfg, photometry, flux_scale=flux_scale, _luminaires=luminaires)
            out["SR"] = _norm_round((outer_L + outer_R) / (inner_L + inner_R), 2) if (inner_L + inner_R) > 0 else 0.0
            SR_L = outer_L / inner_L if inner_L > 0 else float('inf')
            SR_R = outer_R / inner_R if inner_R > 0 else float('inf')
            out["EIR"] = min(SR_L, SR_R)
        req = ME_REQ[eclass]
        out["req"] = req
        out.update(_me_compliance(out, req))
        compliant = all([out["ok_L"], out["ok_Uo"], out["ok_Ul"], out["ok_TI"], out["ok_SR"]])
        out["mode"] = "ME"
    elif eclass.startswith("P"):
        if len(splits) > 1:
            per_cw_E = []
            for y_start, y_end in splits:
                sub_w = y_end - y_start
                cw_xs, cw_ys, cw_n_lanes, cw_lane_w = _illuminance_grid(cfg, y_start, sub_w)
                rE = calc_road(cfg, photometry, flux_scale=flux_scale,
                              _luminaires=luminaires, _xs=cw_xs, _ys=cw_ys,
                              _n_lanes=cw_n_lanes, _lane_width=cw_lane_w)
                per_cw_E.append(rE)
            out["Eavg"] = min(cw["Eavg"] for cw in per_cw_E)
            out["Emin"] = min(cw["Emin"] for cw in per_cw_E)
        else:
            lum_xs, lum_ys, n_lanes, lane_w = _illuminance_grid(cfg)
            rE = calc_road(cfg, photometry, flux_scale=flux_scale,
                          _luminaires=luminaires, _xs=lum_xs, _ys=lum_ys,
                          _n_lanes=n_lanes, _lane_width=lane_w)
            out["Eavg"] = rE["Eavg"]
            out["Emin"] = rE["Emin"]
        req = P_REQ.get(eclass, {})
        out["req"] = req
        if eclass == "P7":
            out["ok_Eavg"] = True
            out["ok_Emin"] = True
        else:
            out["ok_Eavg"] = _p_passes(out["Eavg"], req.get("Eavg", 0))
            out["ok_Emin"] = _p_passes(out["Emin"], req.get("Emin", 0))
        compliant = out["ok_Eavg"] and out["ok_Emin"]
        out["mode"] = "P"

    for side, sw_w_key in [("left", "sidewalk_left"), ("right", "sidewalk_right")]:
        sw_width = cfg.get(sw_w_key, 0)
        sw_class = cfg.get(f"{sw_w_key}_class") or cfg.get(f"sidewalk_{side}_class")
        if sw_width > 0 and sw_class:
            sw = calc_sidewalk(cfg, photometry, flux_scale=flux_scale, side=side, _luminaires=luminaires)
            _add_sidewalk_results(out, side, sw_class, sw)
        else:
            _add_sidewalk_results(out, side, sw_class, None)
        if out.get(f"sidewalk_{side}_ok_Eavg") is not None:
            compliant = compliant and out[f"sidewalk_{side}_ok_Eavg"] and out[f"sidewalk_{side}_ok_Emin"]

    out["compliant"] = compliant
    return out
