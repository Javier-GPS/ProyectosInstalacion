"""
Geometric transforms for CIE 140:2019 road/tunnel lighting calculations
=======================================================================
Reference: CIE 140:2019, Section 6 (Calculation of luminous intensity).

Coordinate system (CIE 140, Fig. 7):
  x  – longitudinal direction (direction of travel, +x forward)
  y  – transverse, positive to the LEFT when looking in +x
  z  – vertical, positive upward

Luminaire photometric centre: Q = (xL, yL, H)  (H = mounting height above road)
Calculation point on road:    P = (xP, yP, 0)
Observer position:             O = (xP + d_obs, yO, h_obs)
  where d_obs ≈ 60 m (CIE 140 §7.1.4) and h_obs = 1.5 m
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np


# ── Observer ──────────────────────────────────────────────────────────────────

@dataclass
class Observer:
    """
    CIE 140 / CIE 88 observer definition.

    Default values follow CIE 140:2019 §7.1.4:
      - height above road : 1.5 m
      - transverse position: centre of evaluation lane (set per scenario)
      - longitudinal offset: 60 m ahead of calculation point (d_observer)
      - observation angle  : 1° downward from horizontal
    """
    height_m: float        = 1.5    # h_obs [m]
    d_observer_m: float    = 60.0   # longitudinal distance ahead of point
    alpha_deg: float       = 1.0    # angle of observation (downward, fixed by CIE)
    lane_y_m: float        = 0.0    # transverse offset of observer's eye
    direction: float       = 1.0    # sentido de circulacion: +1 = observador
                                     # 60 m por delante en +x (trafico A->B,
                                     # zonas ancladas a portal A); -1 = 60 m
                                     # por delante en -x (trafico entrando
                                     # por portal B, zonas "_b")


# ── Luminaire orientation ─────────────────────────────────────────────────────

@dataclass
class LuminaireOrientation:
    """
    Mounting orientation of a luminaire (CIE 140 §6.2–6.5).

    nu_deg   : orientation ν – angle between road direction (+x) and C0 direction [°]
               For a typical road luminaire mounted with C0 toward the road centre: ν = 0.
    tilt_deg : tilt in application θ_f [°]  (0 = horizontal mounting)
    psi_deg  : rotation ψ about the first axis [°] (usually 0)
    """
    nu_deg:   float = 0.0
    tilt_deg: float = 0.0
    psi_deg:  float = 0.0
    # La misma LDT se instala como imagen especular en la fila derecha de una
    # disposición lateral/bilateral.  Sin este dato, dos filas situadas de
    # forma simétrica siguen usando los planos C originales y, con ópticas
    # asimétricas, iluminan de modo diferente los dos carriles.
    # ``True`` equivale a C -> 360° - C después de aplicar tilt/rotación.
    mirror_c: bool = False


def mirror_c_for_interior_facing(
    y_pos: float,
    width_m: float,
    arrangement: str | None,
) -> bool:
    """Indica si una LDT debe reflejarse para que mire hacia el interior.

    La fotometría de catálogo se toma como la de una luminaria montada en
    el lado izquierdo: el interior queda en su semiplano C90. En una fila del
    lado derecho, el interior queda en C270, por lo que se instala la imagen
    especular de la LDT. Esto aplica a bilateral, alternada y unilateral
    derecha. Las filas centrales no se reflejan.
    """
    kind = str(arrangement or "").strip().lower()
    inward_arrangements = {
        "bilateral_sym", "bilateral", "bilateral_stag", "staggered",
        "central_double", "lateral_right", "unilateral",
    }
    return kind in inward_arrangements and float(y_pos) > float(width_m) / 2.0


# ── Core geometry functions ───────────────────────────────────────────────────

class AnglesResult(NamedTuple):
    C_deg:     float    # photometric azimuth [°]
    gamma_deg: float    # vertical photometric angle [°]
    tan_gamma: float    # tan(γ)  (used as r-table row key)
    distance_m: float   # slant distance from luminaire to point [m]


def luminaire_to_point_angles(
    xP: float, yP: float,          # calculation point (road plane, z=0)
    xL: float, yL: float, H: float,  # luminaire position
    orientation: LuminaireOrientation | None = None,
) -> AnglesResult:
    """
    Compute photometric azimuth C and vertical angle γ from luminaire to point.

    Follows CIE 140:2019 §6.3–6.4 (luminaire not turned about photometric axes
    for the base case; full matrix rotation available via tilt/psi).

    Returns AnglesResult(C_deg, gamma_deg, tan_gamma, distance_m).
    """
    if orientation is None:
        orientation = LuminaireOrientation()

    # Displacement in road plane (luminaire → point)
    dx = xP - xL   # longitudinal  (+x = forward)
    dy = yP - yL   # transverse    (+y = left)
    d_plan = math.hypot(dx, dy)   # horizontal distance [m]

    # Guard: point directly below the luminaire
    if d_plan < 1e-9:
        return AnglesResult(C_deg=0.0, gamma_deg=0.0, tan_gamma=0.0,
                            distance_m=H if H > 0 else 0.0)

    # Vertical (photometric) angle γ — measured from nadir (downward vertical)
    # tan(γ) = horizontal_distance / mounting_height
    if H <= 0:
        gamma_deg = 90.0
        tan_gamma = 1e9
    else:
        tan_gamma = d_plan / H
        gamma_deg = math.degrees(math.atan(tan_gamma))

    # Slant distance
    dist = math.sqrt(d_plan**2 + H**2)

    # Photometric azimuth C (CIE 140 §6.3, no tilt, no rotation)
    # C = 0° when light goes in the +x direction (road forward),
    # increases counterclockwise when viewed from above.
    # With ν = 0 (default orientation):  C = atan2(-dy, -dx) mapped to [0, 360)
    nu_rad = math.radians(orientation.nu_deg)
    # Direction from luminaire to point, in luminaire reference frame
    # (rotate by -ν to go from road frame to photometric frame)
    angle_road = math.atan2(dy, dx)          # angle of (dx,dy) in road frame
    angle_photo = angle_road - nu_rad        # in photometric frame

    # C follows CIE convention: C=0 → straight ahead, grows counterclockwise
    # (looking down from above).  Straight-ahead in road frame is +x (angle_road=0).
    # CIE 140 Fig 8: C is measured from the reference half-plane (C=0).
    C_deg = math.degrees(angle_photo) % 360.0

    # Apply tilt correction if any (simplified for small tilt angles typical in road)
    if abs(orientation.tilt_deg) > 0.01:
        C_deg, gamma_deg, tan_gamma = _apply_tilt(
            C_deg, gamma_deg, orientation.tilt_deg, orientation.psi_deg
        )

    # El espejo se aplica al final, en el sistema fotométrico ya inclinado.
    # Así, +tilt a la izquierda y -tilt a la derecha son también imágenes
    # exactas respecto al plano medio del túnel.
    if orientation.mirror_c:
        C_deg = (-C_deg) % 360.0

    return AnglesResult(C_deg=C_deg, gamma_deg=gamma_deg,
                        tan_gamma=tan_gamma, distance_m=dist)


def _apply_tilt(
    C_deg: float, gamma_deg: float,
    tilt_deg: float, psi_deg: float,
) -> tuple[float, float, float]:
    """
    Apply luminaire tilt and rotation to (C, γ) — CIE 140:2019 Annex A.
    Returns updated (C_deg, gamma_deg, tan_gamma).
    """
    # Convert to direction cosines
    C_rad = math.radians(C_deg)
    g_rad = math.radians(gamma_deg)
    t_rad = math.radians(tilt_deg)
    p_rad = math.radians(psi_deg)

    # Direction vector in photometric frame
    sx = math.sin(g_rad) * math.cos(C_rad)
    sy = math.sin(g_rad) * math.sin(C_rad)
    sz = math.cos(g_rad)

    # Rotation about X axis (tilt) — C0/C180 is the longitudinal (along-road)
    # plane (nu=0), so tilting about that axis leaves it undisturbed and
    # rotates the transverse (C90/C270, "frontal view") plane, matching the
    # installation tilt shown in the cross-section preview.
    cos_t, sin_t = math.cos(t_rad), math.sin(t_rad)
    sy2 =  cos_t * sy - sin_t * sz
    sz2 =  sin_t * sy + cos_t * sz
    sx2 =  sx

    # Rotation about Z axis (psi)
    cos_p, sin_p = math.cos(p_rad), math.sin(p_rad)
    sx3 = cos_p * sx2 - sin_p * sy2
    sy3 = sin_p * sx2 + cos_p * sy2
    sz3 = sz2

    # Back to (C, γ)
    g_new = math.acos(max(-1.0, min(1.0, sz3)))
    C_new = math.atan2(sy3, sx3) % (2 * math.pi)

    gamma_new = math.degrees(g_new)
    C_new_deg = math.degrees(C_new)
    tan_gamma_new = math.tan(g_new) if g_new < math.pi / 2 else 1e9

    return C_new_deg, gamma_new, tan_gamma_new


# ── Vectorized (numpy) batch versions — same formulas as the scalar
#    functions above, broadcasting over an array of points (n_p,) against
#    an array of luminaires (n_l,) at once. Used by TunnelCalculator's
#    batch path for performance; must match the scalar results exactly. ──────

def luminaire_to_point_angles_batch(
    xP, yP, xL, yL, H, nu_deg, tilt_deg, psi_deg, mirror_c=False,
):
    """
    Vectorized luminaire_to_point_angles(). xP, yP: (n_p,) arrays.
    xL, yL, H, nu_deg, tilt_deg, psi_deg: (n_l,) arrays (per luminaire).
    Returns (C_deg, gamma_deg, tan_gamma), each shape (n_p, n_l).
    """
    xP = np.asarray(xP, dtype=float)[:, None]
    yP = np.asarray(yP, dtype=float)[:, None]
    xL = np.asarray(xL, dtype=float)[None, :]
    yL = np.asarray(yL, dtype=float)[None, :]
    H  = np.asarray(H,  dtype=float)[None, :]
    nu_deg   = np.asarray(nu_deg,   dtype=float)[None, :]
    tilt_deg = np.asarray(tilt_deg, dtype=float)[None, :]
    psi_deg  = np.asarray(psi_deg,  dtype=float)[None, :]
    mirror_c = np.asarray(mirror_c, dtype=bool)
    if mirror_c.ndim == 0:
        mirror_c = np.full(xL.shape[1], bool(mirror_c), dtype=bool)
    mirror_c = mirror_c.reshape(1, -1)

    dx = xP - xL
    dy = yP - yL
    d_plan = np.hypot(dx, dy)
    under  = d_plan < 1e-9   # point directly below the luminaire

    safe_H = np.where(H <= 0, 1.0, H)
    tan_gamma = np.where(H <= 0, 1e9, d_plan / safe_H)
    gamma_deg = np.where(H <= 0, 90.0, np.degrees(np.arctan(tan_gamma)))

    nu_rad = np.radians(nu_deg)
    angle_road  = np.arctan2(dy, dx)
    angle_photo = angle_road - nu_rad
    C_deg = np.degrees(angle_photo) % 360.0

    apply_tilt = np.abs(tilt_deg) > 0.01
    if np.any(apply_tilt):
        C_tilt, g_tilt, tg_tilt = _apply_tilt_batch(C_deg, gamma_deg, tilt_deg, psi_deg)
        C_deg     = np.where(apply_tilt, C_tilt, C_deg)
        gamma_deg = np.where(apply_tilt, g_tilt, gamma_deg)
        tan_gamma = np.where(apply_tilt, tg_tilt, tan_gamma)

    C_deg = np.where(mirror_c, (-C_deg) % 360.0, C_deg)

    # Point directly below the luminaire → C=0, gamma=0, tan_gamma=0
    # (matches the scalar function's early return, overriding any tilt).
    C_deg     = np.where(under, 0.0, C_deg)
    gamma_deg = np.where(under, 0.0, gamma_deg)
    tan_gamma = np.where(under, 0.0, tan_gamma)

    return C_deg, gamma_deg, tan_gamma


def _apply_tilt_batch(C_deg, gamma_deg, tilt_deg, psi_deg):
    """Vectorized _apply_tilt() — CIE 140:2019 Annex A."""
    C_rad = np.radians(C_deg)
    g_rad = np.radians(gamma_deg)
    t_rad = np.radians(tilt_deg)
    p_rad = np.radians(psi_deg)

    sx = np.sin(g_rad) * np.cos(C_rad)
    sy = np.sin(g_rad) * np.sin(C_rad)
    sz = np.cos(g_rad)

    cos_t, sin_t = np.cos(t_rad), np.sin(t_rad)
    sy2 =  cos_t * sy - sin_t * sz
    sz2 =  sin_t * sy + cos_t * sz
    sx2 =  sx

    cos_p, sin_p = np.cos(p_rad), np.sin(p_rad)
    sx3 = cos_p * sx2 - sin_p * sy2
    sy3 = sin_p * sx2 + cos_p * sy2
    sz3 = sz2

    g_new = np.arccos(np.clip(sz3, -1.0, 1.0))
    C_new = np.arctan2(sy3, sx3) % (2 * np.pi)

    gamma_new     = np.degrees(g_new)
    C_new_deg     = np.degrees(C_new)
    tan_gamma_new = np.where(g_new < np.pi / 2, np.tan(g_new), 1e9)

    return C_new_deg, gamma_new, tan_gamma_new


def deviation_angle_beta_batch(xP, yP, xL, yL, observer=None):
    """
    Vectorized deviation_angle_beta(). xP, yP: (n_p,) arrays.
    xL, yL: (n_l,) arrays. Returns beta_deg, shape (n_p, n_l).
    """
    obs   = observer or Observer()
    d_obs = obs.d_observer_m

    xP = np.asarray(xP, dtype=float)[:, None]
    yP = np.asarray(yP, dtype=float)[:, None]
    xL = np.asarray(xL, dtype=float)[None, :]
    yL = np.asarray(yL, dtype=float)[None, :]

    dx_lp = xP - xL
    dy_lp = yP - yL
    # Observador 60 m POR DETRAS de P (mirando hacia delante, a traves de P) —
    # ver deviation_angle_beta() para la justificacion (CIE 140/RP-8-18).
    dx_op = d_obs * obs.direction
    dy_op = yP - obs.lane_y_m

    angle_lp = np.arctan2(dy_lp, dx_lp)
    angle_op = np.arctan2(dy_op, dx_op)

    beta = np.abs(np.degrees(angle_lp - angle_op)) % 360.0
    beta = np.where(beta > 180.0, 360.0 - beta, beta)
    return beta


# ── β angle ──────────────────────────────────────────────────────────────────

def deviation_angle_beta(
    xP: float, yP: float,           # calculation point
    xL: float, yL: float,           # luminaire position (plan)
    observer: Observer | None = None,
    observer_x_ahead: float = 60.0, # override observer longitudinal offset
) -> float:
    """
    Compute angle of deviation β [°] at point P.

    β is the complementary angle between:
      - the vertical plane containing luminaire Q and point P
      - the vertical plane containing observer O and point P

    (CIE 140:2019 §2.2, Fig. 5)

    For a standard CIE observer looking forward along +x at point P:
      observer O is at (xP - d_obs, yO, h_obs) — 60 m BEHIND P, looking
      forward through P toward the road ahead (CIE 140/RP-8-18 convention;
      the driver evaluates points ahead, never behind, so the eye trails P).
      The vertical plane OP lies along the road direction for β=0.

    β ∈ [0°, 180°] — by symmetry.
    """
    obs = observer or Observer()
    d_obs = obs.d_observer_m

    # Direction: luminaire → point (plan)
    dx_lp = xP - xL
    dy_lp = yP - yL

    # Direction: observer → point (plan)
    # Observer is *behind* P along the direction of travel (+x if
    # obs.direction=+1, -x if obs.direction=-1), at transverse position
    # obs.lane_y_m — looking forward through P.
    dx_op = d_obs * obs.direction
    dy_op = yP - obs.lane_y_m

    angle_lp = math.atan2(dy_lp, dx_lp)
    angle_op = math.atan2(dy_op, dx_op)

    beta = abs(math.degrees(angle_lp - angle_op)) % 360.0
    if beta > 180.0:
        beta = 360.0 - beta

    return beta


# ── TI geometry ──────────────────────────────────────────────────────────────

def angle_luminaire_to_observer(
    xL: float, yL: float, H: float,   # luminaire
    xO: float, yO: float, hO: float,  # observer eye
) -> float:
    """
    Angle θ [°] between line of sight (observer forward along +x) and the
    centre of a luminaire.  Used in TI calculation (CIE 140:2019 §8.4).

    θ is measured from the observer's line of sight (horizontal, forward = +x).
    """
    # Vector from observer to luminaire
    dx = xL - xO
    dz = H  - hO
    dy = yL - yO
    d_plan = math.hypot(dx, dy)

    # Elevation angle from horizontal
    theta_elev = math.degrees(math.atan2(dz, d_plan))

    # CIE TI uses elevation above horizontal line of sight
    return abs(theta_elev)
