"""
CIE 140:2019 Photometric Calculator
====================================
Computes road/tunnel luminance and illuminance at calculation points.

Core formula (CIE 140:2019 §7.1.1):

    L(P) = Σ_i  [ I_i(C_i, γ_i) / H_i² ] × r(β_i, tan γ_i) × f_m

Where:
    I_i(C, γ)   luminous intensity of luminaire i toward P [cd]
    H_i         mounting height of luminaire i [m]
    r(β, tan γ) reduced luminance coefficient from CIE 144 r-table [sr⁻¹]
    f_m         maintenance factor (MF)

Horizontal illuminance (CIE 140:2019 §7.2.1):
    E_h(P) = Σ_i  I_i(C_i, γ_i) × cos³(γ_i) / H_i²  × f_m

Usage
-----
    from salvi_photometry.calculator import TunnelCalculator, LuminaireInstance

    lum = LuminaireInstance(
        x=5.0, y=0.0, H=7.5,
        photometry=phot,       # Photometry object from ldt_parser
        flux_lm=42000,         # actual operating flux from catalog
        orientation=LuminaireOrientation(),
    )
    calc = TunnelCalculator(rtable_name="R2", maintenance_factor=0.80)
    result = calc.calculate(
        calc_points=[(x, y) for x in xs for y in ys],
        luminaires=[lum],
        observer=Observer(lane_y_m=2.0),
    )
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .ldt_parser import Photometry
from .geometry   import (
    LuminaireOrientation, Observer,
    luminaire_to_point_angles, deviation_angle_beta,
    angle_luminaire_to_observer,
    luminaire_to_point_angles_batch, deviation_angle_beta_batch,
)
from .rtables import r_value, r_value_batch


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class LuminaireInstance:
    """
    A single luminaire installed in the tunnel.

    Attributes
    ----------
    x, y        : position on road plane [m]
                  x = longitudinal (0 = reference cross-section)
                  y = transverse (0 = road axis, positive = left)
    H           : mounting height above road [m]
    photometry  : angular distribution (from LDT parser)
    flux_lm     : actual operating luminous flux [lm]
                  (used to scale the photometric distribution)
    orientation : luminaire mounting orientation
    label       : optional identifier
    """
    x:           float
    y:           float
    H:           float
    photometry:  Photometry
    flux_lm:     float
    orientation: LuminaireOrientation = field(default_factory=LuminaireOrientation)
    label:       str = ""

    def intensity_toward(self, xP: float, yP: float) -> tuple[float, float, float, float]:
        """
        Compute I [cd], γ [°], C [°], tan(γ) for this luminaire toward point P.
        Scales the LDT distribution to self.flux_lm.
        """
        ar = luminaire_to_point_angles(xP, yP, self.x, self.y, self.H,
                                       self.orientation)
        I_cd = self.photometry.intensity(ar.C_deg, ar.gamma_deg,
                                         scale_flux_lm=self.flux_lm)
        return I_cd, ar.gamma_deg, ar.C_deg, ar.tan_gamma


# ── Results ───────────────────────────────────────────────────────────────────

@dataclass
class PointResult:
    """Photometric quantities at a single calculation point."""
    x:         float
    y:         float
    L:         float   # road surface luminance [cd/m²]
    E_h:       float   # horizontal illuminance [lx]
    # Per-luminaire contributions (optional, for debugging)
    L_contrib: list[float] = field(default_factory=list)


@dataclass
class ZoneResult:
    """Aggregated photometric results for a tunnel zone."""
    zone_name:   str
    zone_type:   str
    s_start:     float
    s_end:       float
    L_avg:       float   # average luminance [cd/m²]
    L_min:       float
    L_max:       float
    U0:          float   # overall luminance uniformity = L_min / L_avg
    Ul:          float   # longitudinal uniformity = L_min_longitudinal / L_max_longitudinal
    E_h_avg:     float   # average horizontal illuminance [lx]
    TI:          float   # threshold increment [%]
    EIR:         float   # edge illuminance ratio
    L_req:       float   # required luminance (from CIE 88)
    compliant:   bool
    warnings:    list[str] = field(default_factory=list)
    point_grid:  list[PointResult] = field(default_factory=list)


# ── Calculator ────────────────────────────────────────────────────────────────

class TunnelCalculator:
    """
    CIE 140:2019 photometric calculator for road tunnel sections.

    Parameters
    ----------
    rtable_name        : CIE 144 r-table identifier  (e.g. 'R2')
    maintenance_factor : f_m  (0 < MF ≤ 1)
    max_luminaire_dist : maximum longitudinal distance to consider for each
                         calculation point [m].  Luminaires further away
                         contribute < 0.1% and are skipped for performance.
    """

    def __init__(
        self,
        rtable_name:        str   = "R2",
        maintenance_factor: float = 0.80,
        max_luminaire_dist: float = 300.0,
    ):
        self.rtable_name        = rtable_name
        self.mf                 = maintenance_factor
        self.max_lum_dist       = max_luminaire_dist

    # ── Point calculation ────────────────────────────────────────────────────

    def luminance_at_point(
        self,
        xP: float,
        yP: float,
        luminaires: Sequence[LuminaireInstance],
        observer:   Observer,
    ) -> PointResult:
        """
        Compute road surface luminance L and horizontal illuminance E_h at (xP, yP).
        """
        L_total  = 0.0
        Eh_total = 0.0
        L_per    = []

        for lum in luminaires:
            # Skip distant luminaires (performance optimisation)
            if abs(lum.x - xP) > self.max_lum_dist:
                L_per.append(0.0)
                continue

            I_cd, gamma_deg, C_deg, tan_gamma = lum.intensity_toward(xP, yP)

            if I_cd <= 0:
                L_per.append(0.0)
                continue

            H2 = lum.H ** 2

            # β: angle of deviation (CIE 140 §2.2)
            beta_deg = deviation_angle_beta(xP, yP, lum.x, lum.y,
                                            observer)

            # r-table lookup
            r = r_value(self.rtable_name, beta_deg, tan_gamma)

            # Luminance contribution [cd/m²]
            dL = (I_cd / H2) * r * self.mf
            L_total += dL
            L_per.append(dL)

            # Horizontal illuminance contribution [lx]
            # E_h = I × cos³(γ) / H²  × MF  (inverse-square law projected to horizontal)
            cos_g  = math.cos(math.radians(gamma_deg))
            dEh    = (I_cd / H2) * (cos_g ** 3) * self.mf
            Eh_total += dEh

        return PointResult(x=xP, y=yP, L=L_total, E_h=Eh_total, L_contrib=L_per)

    # ── Vectorized (numpy) batch point calculation ──────────────────────────

    def luminance_at_points_batch(
        self,
        points:     Sequence[tuple[float, float]],
        luminaires: Sequence[LuminaireInstance],
        observer:   Observer,
    ) -> np.ndarray:
        """
        Vectorized equivalent of calling luminance_at_point(xP, yP, ...).L
        for every (xP, yP) in `points`, matching it exactly (same formula,
        same max_lum_dist skip) but computed with numpy instead of a
        per-point/per-luminaire Python loop — used where the same
        luminaire layout is evaluated at many points (design search grids,
        L(s) profile curves).

        Luminaires may use different Photometry objects (mixed opticas);
        they are grouped internally by object identity so each group's
        LDT table lookup is still fully vectorized.
        """
        contributions = self.luminance_contributions_at_points_batch(
            points, luminaires, observer,
        )
        return contributions.sum(axis=1)

    def luminance_contributions_at_points_batch(
        self,
        points:     Sequence[tuple[float, float]],
        luminaires: Sequence[LuminaireInstance],
        observer:   Observer,
    ) -> np.ndarray:
        """Matriz de contribuciones ``(puntos, luminarias)``.

        Conserva el orden original de las luminarias aunque haya fotometrias
        mezcladas. Su suma por filas es exactamente el resultado de
        :meth:`luminance_at_points_batch`. Esta forma permite construir
        matrices de influencia completas sin una llamada por luminaria.
        """
        n_points = len(points)
        n_luminaires = len(luminaires)
        if n_points == 0:
            return np.zeros((0, n_luminaires))
        if not luminaires:
            return np.zeros((n_points, 0))

        xP = np.array([p[0] for p in points], dtype=float)
        yP = np.array([p[1] for p in points], dtype=float)

        groups: dict[int, list[tuple[int, LuminaireInstance]]] = {}
        for index, lum in enumerate(luminaires):
            groups.setdefault(id(lum.photometry), []).append((index, lum))

        contributions = np.zeros((n_points, n_luminaires))
        for indexed_lums in groups.values():
            # La mayoría de los perfiles se resuelve por bloques longitudinales
            # cortos. Recortar primero las luminarias que quedan fuera del
            # alcance de TODO el bloque evita construir y evaluar matrices
            # angulares para cientos de columnas que acabarían en cero.
            # El filtro puntual exacto se conserva más abajo.
            x_min = float(np.min(xP)) - self.max_lum_dist
            x_max = float(np.max(xP)) + self.max_lum_dist
            indexed_lums = [
                item for item in indexed_lums
                if x_min <= float(item[1].x) <= x_max
            ]
            if not indexed_lums:
                continue
            indices = np.array([item[0] for item in indexed_lums], dtype=int)
            lums_g = [item[1] for item in indexed_lums]
            phot = lums_g[0].photometry
            xL   = np.array([l.x for l in lums_g], dtype=float)
            yL   = np.array([l.y for l in lums_g], dtype=float)
            H    = np.array([l.H for l in lums_g], dtype=float)
            flux = np.array([l.flux_lm for l in lums_g], dtype=float)
            nu   = np.array([l.orientation.nu_deg   for l in lums_g], dtype=float)
            tilt = np.array([l.orientation.tilt_deg for l in lums_g], dtype=float)
            psi  = np.array([l.orientation.psi_deg  for l in lums_g], dtype=float)
            mirror_c = np.array([l.orientation.mirror_c for l in lums_g], dtype=bool)

            C_deg, gamma_deg, tan_gamma = luminaire_to_point_angles_batch(
                xP, yP, xL, yL, H, nu, tilt, psi, mirror_c)     # (n_p, n_l)

            I_cd = phot.intensity_batch(C_deg, gamma_deg,
                                        scale_flux_lm=flux[None, :])

            in_range = np.abs(xP[:, None] - xL[None, :]) <= self.max_lum_dist
            valid    = in_range & (I_cd > 0)

            beta_deg = deviation_angle_beta_batch(xP, yP, xL, yL, observer)
            r        = r_value_batch(self.rtable_name, beta_deg, tan_gamma)

            H2 = (H ** 2)[None, :]
            dL = np.where(valid, (I_cd / H2) * r * self.mf, 0.0)
            contributions[:, indices] = dL

        return contributions

    # ── Zone calculation ─────────────────────────────────────────────────────

    def calculate_zone(
        self,
        zone_name:  str,
        zone_type:  str,
        s_start:    float,
        s_end:      float,
        L_req:      float,
        calc_points: list[tuple[float, float]],  # (x, y) on road plane
        luminaires:  Sequence[LuminaireInstance],
        observer:    Observer,
    ) -> ZoneResult:
        """
        Calculate photometric quantities for one tunnel zone.

        calc_points should be the CIE 140-compliant grid for this zone
        (generated by tunnel_domain.grid.make_grid).
        """
        if not calc_points:
            return ZoneResult(
                zone_name=zone_name, zone_type=zone_type,
                s_start=s_start, s_end=s_end,
                L_avg=0, L_min=0, L_max=0, U0=0, Ul=0,
                E_h_avg=0, TI=0, EIR=0, L_req=L_req,
                compliant=False,
                warnings=["No calculation points provided."],
            )

        point_results = [
            self.luminance_at_point(xP, yP, luminaires, observer)
            for xP, yP in calc_points
        ]

        L_vals = np.array([pr.L for pr in point_results])
        Eh_vals = np.array([pr.E_h for pr in point_results])

        L_avg = float(np.mean(L_vals))
        L_min = float(np.min(L_vals))
        L_max = float(np.max(L_vals))

        U0 = L_min / L_avg if L_avg > 0 else 0.0
        Ul = self._longitudinal_uniformity(point_results, s_start, s_end)
        E_h_avg = float(np.mean(Eh_vals))

        TI  = self._threshold_increment(point_results, luminaires, observer)
        EIR = self._edge_illuminance_ratio(Eh_vals, calc_points)

        compliant = (L_avg >= L_req and U0 >= 0.4 and Ul >= 0.6)

        return ZoneResult(
            zone_name=zone_name, zone_type=zone_type,
            s_start=s_start, s_end=s_end,
            L_avg=L_avg, L_min=L_min, L_max=L_max,
            U0=U0, Ul=Ul, E_h_avg=E_h_avg,
            TI=TI, EIR=EIR, L_req=L_req,
            compliant=compliant,
            point_grid=point_results,
        )

    # ── TI — Threshold Increment (CIE 140:2019 §8.4 corrected formula) ───────

    def _threshold_increment(
        self,
        point_results: list[PointResult],
        luminaires:    Sequence[LuminaireInstance],
        observer:      Observer,
    ) -> float:
        """
        TI = 65 × L_v / L_avg^0.8   [%]   (CIE 140:2019 corrected formula)

        L_v = veiling luminance = Σ_k  E_k / θ_k²
        E_k = illuminance at observer's eye from luminaire k [lx]
        θ_k = angle between line of sight and luminaire k [°]
        """
        if not point_results:
            return 0.0

        L_avg = float(np.mean([pr.L for pr in point_results]))
        if L_avg <= 0:
            return 0.0

        # Observer eye position: at centre of road, d_obs BEHIND mean calculation x
        # (CIE 140/RP-8-18: observer trails the point, looking forward through it).
        x_mean = float(np.mean([pr.x for pr in point_results]))
        x_obs  = x_mean - observer.d_observer_m * observer.direction
        y_obs  = observer.lane_y_m
        h_obs  = observer.height_m

        L_v = 0.0
        for lum in luminaires:
            # Angle from observer's horizontal line of sight to luminaire
            theta = angle_luminaire_to_observer(
                lum.x, lum.y, lum.H, x_obs, y_obs, h_obs
            )
            if theta < 0.5:
                theta = 0.5   # CIE 140 lower bound

            # Illuminance at observer's eye (on plane normal to line of sight)
            dx = lum.x - x_obs
            dy = lum.y - y_obs
            dz = lum.H - h_obs
            dist2 = dx**2 + dy**2 + dz**2
            if dist2 < 1.0:
                continue

            I_cd, gamma_deg, C_deg, _ = lum.intensity_toward(x_obs, y_obs)
            E_k = (I_cd * self.mf) / dist2 if dist2 > 0 else 0.0

            L_v += E_k / (theta ** 2)

        TI = 65.0 * L_v / (L_avg ** 0.8) if L_avg > 0 else 0.0
        return float(TI)

    # ── Longitudinal uniformity ───────────────────────────────────────────────

    def _longitudinal_uniformity(
        self,
        point_results: list[PointResult],
        s_start: float,
        s_end:   float,
    ) -> float:
        """
        Ul = L_min / L_max  along each longitudinal line (CIE 140:2019 §8.3).
        """
        if not point_results:
            return 0.0

        # Group by transverse position y (unique y values → one lane-line each)
        y_vals = sorted(set(pr.y for pr in point_results))
        ul_per_line = []

        for y in y_vals:
            row = sorted([pr for pr in point_results if pr.y == y], key=lambda p: p.x)
            if len(row) < 2:
                continue
            L_row = [pr.L for pr in row]
            L_max_row = max(L_row)
            L_min_row = min(L_row)
            if L_max_row > 0:
                ul_per_line.append(L_min_row / L_max_row)

        return float(min(ul_per_line)) if ul_per_line else 0.0

    # ── EIR — Edge Illuminance Ratio (CIE 140:2019 §8.5) ────────────────────

    def _edge_illuminance_ratio(
        self,
        Eh_vals: np.ndarray,
        calc_points: list[tuple[float, float]],
    ) -> float:
        """
        EIR = E_outer_strip / E_inner_strip  per carriageway edge.
        Simplified: ratio of illuminance at outermost points vs. innermost.
        """
        if len(calc_points) < 4:
            return 0.0
        ys = [pt[1] for pt in calc_points]
        y_min, y_max = min(ys), max(ys)
        y_range = y_max - y_min
        if y_range < 0.1:
            return 1.0

        outer_mask = np.array([abs(pt[1] - y_max) < y_range * 0.15 or
                                abs(pt[1] - y_min) < y_range * 0.15
                                for pt in calc_points])
        inner_mask = ~outer_mask

        E_outer = float(np.mean(Eh_vals[outer_mask])) if outer_mask.any() else 0.0
        E_inner = float(np.mean(Eh_vals[inner_mask])) if inner_mask.any() else 1.0
        return E_outer / E_inner if E_inner > 0 else 0.0
