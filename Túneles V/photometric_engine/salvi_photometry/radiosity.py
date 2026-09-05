"""
Radiosity Engine — Diffuse inter-reflections for tunnel surfaces
================================================================
Computes the indirect (reflected) luminous flux contribution from
walls, ceiling and road surface in a tunnel cross-section.

Method:  Progressive radiosity (iterative Gauss-Seidel).
Model:   All surfaces assumed perfectly diffuse (Lambertian) reflectors.
         The road luminance toward the observer is still computed with CIE 144
         r-tables (specular component) plus the diffuse indirect component
         from radiosity.

Geometry (2-D cross-section, extruded longitudinally):
  The tunnel is discretised into patches along the cross-section perimeter.
  For a rectangular section of width W and height H_t:
    - Road    : y ∈ [0, W],  z = 0         (nR patches)
    - Left wall: y = 0,      z ∈ [0, H_t]  (nW patches)
    - Right wall: y = W,     z ∈ [0, H_t]  (nW patches)
    - Ceiling : y ∈ [0, W],  z = H_t       (nC patches)

Form factors are computed analytically for 2-D strip-to-strip geometry
(Hottel crossed-string method for parallel/perpendicular strips).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


# ── Patch ─────────────────────────────────────────────────────────────────────

@dataclass
class Patch:
    """A surface patch in the 2-D cross-section."""
    surface:     str     # 'road', 'wall_left', 'wall_right', 'ceiling'
    y_center:    float   # transverse position [m]
    z_center:    float   # height [m]
    width:       float   # patch width along surface [m]
    normal:      tuple[float, float]  # outward normal (ny, nz), unit vector
    reflectance: float   # diffuse reflectance ρ ∈ [0, 1)
    E_direct:    float = 0.0   # direct illuminance [lx] (input from calculator)
    E_total:     float = 0.0   # total illuminance after radiosity [lx]
    B:           float = 0.0   # radiosity [lm/m²] = ρ × E_total


@dataclass
class TunnelSection:
    """
    Rectangular tunnel cross-section for radiosity.

    Parameters
    ----------
    width_m       : carriageway width [m]
    height_m      : tunnel height (road to ceiling) [m]
    rho_road      : diffuse reflectance of road surface  (≈ 0.15–0.25)
    rho_wall      : diffuse reflectance of walls         (≈ 0.40–0.70)
    rho_ceiling   : diffuse reflectance of ceiling       (≈ 0.60–0.85)
    n_road        : number of patches on road
    n_wall        : number of patches on each wall (left + right)
    n_ceiling     : number of patches on ceiling
    """
    width_m:    float
    height_m:   float
    rho_road:   float = 0.20
    rho_wall:   float = 0.60
    rho_ceiling: float = 0.70
    n_road:     int   = 8
    n_wall:     int   = 6
    n_ceiling:  int   = 8


def build_patches(section: TunnelSection) -> list[Patch]:
    """Create the patch list for a rectangular cross-section."""
    patches: list[Patch] = []
    W = section.width_m
    H = section.height_m

    # Road: y in [0, W], z = 0, normal pointing up (0, +1)
    dy_r = W / section.n_road
    for i in range(section.n_road):
        patches.append(Patch(
            surface="road",
            y_center=dy_r * (i + 0.5),
            z_center=0.0,
            width=dy_r,
            normal=(0.0, 1.0),
            reflectance=section.rho_road,
        ))

    # Left wall: y = 0, z in [0, H], normal pointing right (+1, 0)
    dz_w = H / section.n_wall
    for i in range(section.n_wall):
        patches.append(Patch(
            surface="wall_left",
            y_center=0.0,
            z_center=dz_w * (i + 0.5),
            width=dz_w,
            normal=(1.0, 0.0),
            reflectance=section.rho_wall,
        ))

    # Right wall: y = W, z in [0, H], normal pointing left (-1, 0)
    for i in range(section.n_wall):
        patches.append(Patch(
            surface="wall_right",
            y_center=W,
            z_center=dz_w * (i + 0.5),
            width=dz_w,
            normal=(-1.0, 0.0),
            reflectance=section.rho_wall,
        ))

    # Ceiling: y in [0, W], z = H, normal pointing down (0, -1)
    dy_c = W / section.n_ceiling
    for i in range(section.n_ceiling):
        patches.append(Patch(
            surface="ceiling",
            y_center=dy_c * (i + 0.5),
            z_center=H,
            width=dy_c,
            normal=(0.0, -1.0),
            reflectance=section.rho_ceiling,
        ))

    return patches


# ── Form factor (2-D, crossed-string method) ──────────────────────────────────

def form_factor_2d(
    pi: Patch,
    pj: Patch,
) -> float:
    """
    2-D view factor F_ij between two infinitely long parallel strips
    (Hottel's crossed-string method for 2-D geometry).

    Each patch is represented by its end-points in the (y, z) plane.
    F_ij = (Σ crossed strings - Σ uncrossed strings) / (2 × L_i)
    """
    # End-points of patch i
    yi0, yi1 = _patch_endpoints(pi)
    zi0, zi1 = _patch_endpoints_z(pi)

    yj0, yj1 = _patch_endpoints(pj)
    zj0, zj1 = _patch_endpoints_z(pj)

    # Four strings (2 crossed, 2 uncrossed)
    def dist(ay, az, by, bz):
        return math.sqrt((ay - by)**2 + (az - bz)**2)

    # Crossed strings: i0→j1, i1→j0
    crossed = dist(yi0, zi0, yj1, zj1) + dist(yi1, zi1, yj0, zj0)
    # Uncrossed: i0→j0, i1→j1
    uncrossed = dist(yi0, zi0, yj0, zj0) + dist(yi1, zi1, yj1, zj1)

    Li = pi.width
    if Li < 1e-9:
        return 0.0

    Fij = max(0.0, (crossed - uncrossed) / (2.0 * Li))
    return Fij


def _patch_endpoints(p: Patch) -> tuple[float, float]:
    """Return y-coordinates of patch start and end."""
    ny, nz = p.normal
    # Half-width vector perpendicular to normal in 2-D
    half = p.width / 2.0
    if abs(ny) < 0.5:  # vertical surface (wall) — extends in y
        return p.y_center - half, p.y_center + half
    else:              # horizontal surface (road/ceiling) — extends in y
        return p.y_center - half, p.y_center + half


def _patch_endpoints_z(p: Patch) -> tuple[float, float]:
    """Return z-coordinates of patch start and end."""
    ny, nz = p.normal
    half = p.width / 2.0
    if abs(nz) < 0.5:  # vertical surface — extends in z
        return p.z_center - half, p.z_center + half
    else:              # horizontal surface — z constant
        return p.z_center, p.z_center


# ── Radiosity solver ──────────────────────────────────────────────────────────

def solve_radiosity(
    patches:     list[Patch],
    max_iter:    int   = 200,
    tol_rel:     float = 1e-5,
    verbose:     bool  = False,
) -> list[Patch]:
    """
    Iterative radiosity solver (Gauss-Seidel).

    Requires that each patch's E_direct has been set beforehand.

    Returns the same patch list with E_total and B updated.
    """
    n = len(patches)

    # Build form-factor matrix F[i][j]
    F = np.zeros((n, n), dtype=float)
    for i, pi in enumerate(patches):
        for j, pj in enumerate(patches):
            if i != j:
                F[i, j] = form_factor_2d(pi, pj)
        # Normalise row so Σ_j F_ij ≤ 1  (energy conservation)
        row_sum = np.sum(F[i])
        if row_sum > 1.0:
            F[i] /= row_sum

    rho = np.array([p.reflectance for p in patches], dtype=float)
    E_d = np.array([p.E_direct   for p in patches], dtype=float)

    # Radiosity B_i = ρ_i × (E_d_i + Σ_j F_ji × B_j / A_j × A_i)
    # For equal-width per surface group, simplify: B_i = ρ_i × (E_d_i + Σ_j F_ji × B_j)
    B = rho * E_d   # initial guess

    for iteration in range(max_iter):
        B_new = rho * (E_d + F.T @ B)
        delta = np.linalg.norm(B_new - B) / (np.linalg.norm(B) + 1e-12)
        B = B_new
        if delta < tol_rel:
            if verbose:
                print(f"Radiosity converged in {iteration+1} iterations (δ={delta:.2e})")
            break
    else:
        if verbose:
            print(f"Radiosity reached max_iter={max_iter}, δ={delta:.2e}")

    # Write back results
    for i, p in enumerate(patches):
        p.B       = float(B[i])
        p.E_total = float(B[i] / p.reflectance) if p.reflectance > 0 else p.E_direct

    return patches


# ── Per-point indirect illuminance on road ────────────────────────────────────

def indirect_illuminance_on_road(
    patches: list[Patch],
    yP:      float,
) -> float:
    """
    Compute the indirect (reflected) horizontal illuminance at a road point
    (yP, z=0) due to the radiosity of all non-road patches.

    Uses the 2-D view factor from each patch to the point.
    For a point (infinitesimally small), F_patch→point is approximated
    via the cosine-law of 2-D radiosity:

        dE = B_j × cos(α_j) / (π × r_j) × dω_j  (2-D analogue)

    where r_j is the distance from patch j to point, α_j is the angle
    between patch normal and direction to point.
    """
    E_indirect = 0.0
    for p in patches:
        if p.surface == "road" or p.B <= 0:
            continue
        # Direction from patch to point (in 2-D plane)
        dy = yP - p.y_center
        dz = 0.0 - p.z_center
        dist = math.sqrt(dy**2 + dz**2)
        if dist < 0.01:
            continue

        # Cosine of angle between patch normal and direction to point
        cos_patch = (p.normal[0] * dy + p.normal[1] * dz) / dist
        if cos_patch <= 0:
            continue   # patch faces away from point

        # Cosine at receiving point (road is horizontal, normal = +z = (0,1))
        # receiving normal (0,1) · direction from point to patch (−dy,−dz)/dist
        cos_recv = (-dz) / dist   # = (0·(−dy) + 1·(−dz))/dist

        if cos_recv <= 0:
            continue

        # 2-D differential form factor ≈ cos_patch × cos_recv / (π × r)
        dF = cos_patch * cos_recv / (math.pi * dist)
        E_indirect += p.B * dF * p.width

    return max(0.0, E_indirect)
