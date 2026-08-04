"""
Fase 11 · Cimentaciones y Geotecnia — Services
EC7 bearing capacity, overturning/sliding/uplift, Winkler stiffness,
embedded pole, Pareto optimizer, normative classifier.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class BearingCapacityResult:
    qu_kpa: float             # ultimate bearing capacity
    qRd_kpa: float            # design resistance (divided by gamma_R)
    sigma_Ed_kpa: float       # applied effective contact pressure
    utilization: float
    area_effective_m2: float
    B_prime_m: float
    L_prime_m: float
    Nc: float
    Nq: float
    Ngamma: float
    factors: dict[str, float]
    norm_clause: str = "EC7 §6.5.2 / Meyerhof"
    error_codes: list[str] = field(default_factory=list)


@dataclass
class OverturningSlidingResult:
    overturning_ratio: float      # M_stab / M_overturning
    resultant_eccentricity_m: float
    within_third: bool            # resultant in middle third
    sliding_VRd_kn: float
    sliding_VEd_kn: float
    sliding_util: float
    overturning_compliant: bool
    sliding_compliant: bool
    error_codes: list[str] = field(default_factory=list)


@dataclass
class UpliftResult:
    W_prop_kn: float
    W_soil_kn: float
    U_kn: float               # hydrostatic uplift
    W_eff_kn: float           # = W_prop + W_soil - U
    T_uplift_kn: float        # tensile demand
    gamma_uplift: float
    utilization: float
    compliant: bool
    error_codes: list[str] = field(default_factory=list)


@dataclass
class WinklerStiffness:
    kz_kn_m: float            # vertical
    kx_kn_m: float
    ky_kn_m: float
    kthx_knm_rad: float       # rotational
    kthy_knm_rad: float
    kthz_knm_rad: float       # torsional (approx)
    matrix_6x6: list[list[float]]
    converged: bool
    iterations: int


@dataclass
class EmbeddedPoleResult:
    L_embed_m: float
    passive_pressure_kpa: float
    reaction_top_kn: float
    reaction_bottom_kn: float
    moment_at_surface_knm: float
    util_lateral: float
    util_toe: float
    compliant: bool


@dataclass
class FoundationCandidateSummary:
    family: str
    width_m: Optional[float]
    length_m: Optional[float]
    depth_m: Optional[float]
    diameter_m: Optional[float]
    util_bearing: float
    util_overturning: float
    util_sliding: float
    util_uplift: float
    util_governing: float
    total_cost_eur: float
    concrete_volume_m3: float
    excavation_volume_m3: float
    total_co2_kg: float
    total_mass_kg: float
    feasible: bool
    label: str = ""
    score: float = 0.0


# ---------------------------------------------------------------------------
# EC7 Bearing Capacity Service
# ---------------------------------------------------------------------------

class BearingCapacityService:
    """
    EC7 §6.5.2 bearing capacity with Meyerhof/Hansen factors.
    Works for both drained (φ, c) and undrained (cu) conditions.
    """

    GAMMA_R: float = 1.4   # EC7 DA2* resistance factor (geotechnical)

    @classmethod
    def bearing_factors(cls, phi_deg: float) -> tuple[float, float, float]:
        """Compute Nc, Nq, Ngamma from friction angle."""
        phi = math.radians(phi_deg)
        Nq = math.exp(math.pi * math.tan(phi)) * (math.tan(math.radians(45) + phi / 2)) ** 2
        if phi_deg > 0:
            Nc = (Nq - 1.0) / math.tan(phi)
        else:
            Nc = math.pi + 2.0   # Prandtl limit (5.14)
        Ngamma = 2.0 * (Nq + 1.0) * math.tan(phi)
        return Nc, Nq, Ngamma

    @classmethod
    def shape_factors(cls, B: float, L: float, phi_deg: float,
                      Nq: float, Nc: float) -> tuple[float, float, float]:
        """Meyerhof shape factors for rectangular foundation."""
        if L <= 0 or B <= 0:
            raise ValueError("F11-E005: B y L deben ser positivos")
        ratio = B / L
        sc = 1.0 + ratio * (Nq / Nc) if Nc > 0 else 1.0
        sq = 1.0 + ratio * math.tan(math.radians(phi_deg))
        sgamma = 1.0 - 0.3 * ratio
        return sc, sq, sgamma

    @classmethod
    def depth_factors(cls, D: float, B: float, phi_deg: float) -> tuple[float, float, float]:
        """Meyerhof depth factors."""
        phi = math.radians(phi_deg)
        ratio = D / B if B > 0 else 0.0
        dc = 1.0 + 0.4 * ratio
        if phi_deg > 0:
            dq = 1.0 + 2.0 * math.tan(phi) * (1.0 - math.sin(phi)) ** 2 * ratio
        else:
            dq = 1.0
        dgamma = 1.0
        return dc, dq, dgamma

    @classmethod
    def inclination_factors(cls, V_kn: float, N_kn: float,
                            phi_deg: float) -> tuple[float, float, float]:
        """Meyerhof inclination factors (simplified — single direction)."""
        if N_kn <= 0:
            return 1.0, 1.0, 1.0
        alpha = math.degrees(math.atan(abs(V_kn) / abs(N_kn)))
        ic = (1.0 - alpha / 90.0) ** 2
        iq = (1.0 - alpha / phi_deg) ** 2 if phi_deg > 0 else ic
        igamma = (1.0 - alpha / phi_deg) ** 3 if phi_deg > 0 else 0.0
        ic = max(0.0, ic)
        iq = max(0.0, iq)
        igamma = max(0.0, igamma)
        return ic, iq, igamma

    @classmethod
    def effective_dimensions(cls, B: float, L: float,
                              ey: float, ez: float) -> tuple[float, float]:
        """EC7 effective dimensions after eccentricity reduction."""
        B_prime = B - 2.0 * abs(ey)
        L_prime = L - 2.0 * abs(ez)
        B_prime = max(B_prime, 0.01)
        L_prime = max(L_prime, 0.01)
        return B_prime, L_prime

    @classmethod
    def check_drained(cls,
                      N_Ed_kn: float, My_knm: float, Mz_knm: float,
                      V_Ed_kn: float,
                      B_m: float, L_m: float, D_m: float,
                      phi_deg: float, c_kpa: float,
                      gamma_kn_m3: float, q_surcharge_kpa: float = 0.0) -> BearingCapacityResult:
        """Drained bearing capacity check."""
        # Eccentricity
        ey = abs(My_knm) / abs(N_Ed_kn) if abs(N_Ed_kn) > 0.001 else 0.0
        ez = abs(Mz_knm) / abs(N_Ed_kn) if abs(N_Ed_kn) > 0.001 else 0.0
        B_prime, L_prime = cls.effective_dimensions(B_m, L_m, ey, ez)
        A_prime = B_prime * L_prime

        Nc, Nq, Ngamma = cls.bearing_factors(phi_deg)
        sc, sq, sgamma = cls.shape_factors(B_prime, L_prime, phi_deg, Nq, Nc)
        dc, dq, dgamma = cls.depth_factors(D_m, B_prime, phi_deg)
        ic, iq, igamma = cls.inclination_factors(V_Ed_kn, N_Ed_kn, phi_deg)

        q = gamma_kn_m3 * D_m + q_surcharge_kpa  # overburden pressure
        qu = (c_kpa * Nc * sc * dc * ic
              + q * Nq * sq * dq * iq
              + 0.5 * gamma_kn_m3 * B_prime * Ngamma * sgamma * dgamma * igamma)

        sigma_Ed = abs(N_Ed_kn) / A_prime
        qRd = qu / cls.GAMMA_R
        util = sigma_Ed / qRd if qRd > 0 else 999.0

        factors = {"sc": sc, "sq": sq, "sgamma": sgamma,
                   "dc": dc, "dq": dq, "dgamma": dgamma,
                   "ic": ic, "iq": iq, "igamma": igamma,
                   "ey_m": ey, "ez_m": ez}
        errors = []
        if util > 1.0:
            errors.append("F11-E003")

        return BearingCapacityResult(
            qu_kpa=qu, qRd_kpa=qRd, sigma_Ed_kpa=sigma_Ed,
            utilization=util, area_effective_m2=A_prime,
            B_prime_m=B_prime, L_prime_m=L_prime,
            Nc=Nc, Nq=Nq, Ngamma=Ngamma,
            factors=factors, error_codes=errors,
        )

    @classmethod
    def check_undrained(cls,
                        N_Ed_kn: float, My_knm: float, Mz_knm: float,
                        B_m: float, L_m: float, D_m: float,
                        cu_kpa: float) -> BearingCapacityResult:
        """Undrained (short-term) bearing capacity — Prandtl."""
        ey = abs(My_knm) / abs(N_Ed_kn) if abs(N_Ed_kn) > 0.001 else 0.0
        ez = abs(Mz_knm) / abs(N_Ed_kn) if abs(N_Ed_kn) > 0.001 else 0.0
        B_prime, L_prime = cls.effective_dimensions(B_m, L_m, ey, ez)
        A_prime = B_prime * L_prime

        Nc_u = math.pi + 2.0   # 5.14
        sc_u = 1.0 + 0.2 * (B_prime / L_prime)
        dc_u = 1.0 + 0.4 * (D_m / B_prime) if B_prime > 0 else 1.0
        qu = cu_kpa * Nc_u * sc_u * dc_u

        sigma_Ed = abs(N_Ed_kn) / A_prime
        qRd = qu / cls.GAMMA_R
        util = sigma_Ed / qRd if qRd > 0 else 999.0

        errors = []
        if util > 1.0:
            errors.append("F11-E003")

        return BearingCapacityResult(
            qu_kpa=qu, qRd_kpa=qRd, sigma_Ed_kpa=sigma_Ed,
            utilization=util, area_effective_m2=A_prime,
            B_prime_m=B_prime, L_prime_m=L_prime,
            Nc=Nc_u, Nq=1.0, Ngamma=0.0,
            factors={"sc_u": sc_u, "dc_u": dc_u, "ey_m": ey, "ez_m": ez},
            error_codes=errors,
        )


# ---------------------------------------------------------------------------
# Overturning & Sliding Service
# ---------------------------------------------------------------------------

class OverturningSlidingService:
    """
    EC7 §6.5.3 (sliding) and §6.5.4 (overturning/eccentricity).
    """
    GAMMA_OVT: float = 1.5    # overturning safety factor (EQU)
    GAMMA_SLIDE: float = 1.1   # sliding safety factor

    @classmethod
    def check(cls,
              N_Ed_kn: float, Vy_kn: float, Vz_kn: float,
              My_knm: float, Mz_knm: float,
              B_m: float, L_m: float, D_m: float,
              gamma_concrete_kn_m3: float,
              gamma_soil_kn_m3: float,
              phi_deg: float, c_kpa: float) -> OverturningSlidingResult:
        # Foundation weight (including soil on top of footing)
        V_foot = B_m * L_m * D_m
        W_prop = V_foot * gamma_concrete_kn_m3

        # Stabilising moment (about base edge, both directions)
        M_stab_y = W_prop * B_m / 2.0
        M_stab_z = W_prop * L_m / 2.0
        M_ovt_y = abs(My_knm)
        M_ovt_z = abs(Mz_knm)

        ratio_y = M_stab_y / M_ovt_y if M_ovt_y > 0.001 else 999.0
        ratio_z = M_stab_z / M_ovt_z if M_ovt_z > 0.001 else 999.0
        overturning_ratio = min(ratio_y, ratio_z)

        # Eccentricity
        N_total = abs(N_Ed_kn) + W_prop
        ey = abs(My_knm) / N_total if N_total > 0.001 else 0.0
        ez = abs(Mz_knm) / N_total if N_total > 0.001 else 0.0
        within_third = (ey <= B_m / 6.0) and (ez <= L_m / 6.0)

        # Sliding
        V_Ed = math.sqrt(Vy_kn ** 2 + Vz_kn ** 2)
        phi = math.radians(phi_deg)
        A = B_m * L_m
        VRd = (N_total * math.tan(phi) + c_kpa * A) / cls.GAMMA_SLIDE
        sliding_util = V_Ed / VRd if VRd > 0 else 999.0

        errors = []
        if overturning_ratio < cls.GAMMA_OVT:
            errors.append("F11-E004")
        if sliding_util > 1.0:
            errors.append("F11-E004")

        return OverturningSlidingResult(
            overturning_ratio=overturning_ratio,
            resultant_eccentricity_m=math.sqrt(ey ** 2 + ez ** 2),
            within_third=within_third,
            sliding_VRd_kn=VRd,
            sliding_VEd_kn=V_Ed,
            sliding_util=sliding_util,
            overturning_compliant=overturning_ratio >= cls.GAMMA_OVT,
            sliding_compliant=sliding_util <= 1.0,
            error_codes=errors,
        )


# ---------------------------------------------------------------------------
# Uplift Service
# ---------------------------------------------------------------------------

class UpliftService:
    """
    Levantamiento / flotación según EC7 §2.4.7.4.
    """
    GAMMA_UPLIFT: float = 1.1   # EQU: destabilising / stabilising ratio
    GAMMA_W: float = 10.0       # water unit weight kN/m³

    @classmethod
    def check(cls,
              N_uplift_kn: float,     # tensile demand from structure (positive = tension)
              B_m: float, L_m: float, D_m: float,
              gamma_concrete_kn_m3: float,
              water_table_depth_m: float,  # depth of water table from surface
              surcharge_soil_thickness_m: float = 0.0,
              gamma_soil_kn_m3: float = 18.0) -> UpliftResult:
        A = B_m * L_m
        W_prop = B_m * L_m * D_m * gamma_concrete_kn_m3
        W_soil = A * surcharge_soil_thickness_m * gamma_soil_kn_m3

        # Hydrostatic uplift: h_w = depth from bottom of foundation to water table
        h_w = max(0.0, D_m - water_table_depth_m)   # water head at foundation base
        U = cls.GAMMA_W * h_w * A

        W_eff = W_prop + W_soil - U
        util = (N_uplift_kn * cls.GAMMA_UPLIFT) / W_eff if W_eff > 0.001 else 999.0

        errors = []
        if util > 1.0 or W_eff < 0:
            errors.append("F11-E004")

        return UpliftResult(
            W_prop_kn=W_prop,
            W_soil_kn=W_soil,
            U_kn=U,
            W_eff_kn=W_eff,
            T_uplift_kn=N_uplift_kn,
            gamma_uplift=cls.GAMMA_UPLIFT,
            utilization=util,
            compliant=util <= 1.0,
            error_codes=errors,
        )


# ---------------------------------------------------------------------------
# Foundation Stiffness Service (Winkler)
# ---------------------------------------------------------------------------

class FoundationStiffnessService:
    """
    Winkler spring stiffness for rectangular/circular foundations.
    Exports 6×6 diagonal spring matrix for Fase 4.
    """

    @classmethod
    def winkler_rectangular(cls,
                             B_m: float, L_m: float, D_m: float,
                             Es_mpa: float, nu: float = 0.3) -> WinklerStiffness:
        """
        Simplified Winkler springs for rectangular shallow foundation.
        kz = Es * A / h_eq; ktheta = Es * I / h_eq
        h_eq = B/2 (representative soil depth = half-width)
        """
        Es = Es_mpa * 1000.0   # convert to kN/m²
        A = B_m * L_m
        Ix = L_m * B_m ** 3 / 12.0
        Iy = B_m * L_m ** 3 / 12.0
        h_eq = max(B_m / 2.0, 0.5)    # representative depth

        kz = Es * A / h_eq
        kx = 0.5 * kz           # horizontal ≈ half vertical (simplified)
        ky = kx
        kthx = Es * Ix / h_eq
        kthy = Es * Iy / h_eq
        kthz = Es * (Ix + Iy) / h_eq * 0.5   # approx torsional

        # 6×6 diagonal matrix (order: Kx, Ky, Kz, Kthx, Kthy, Kthz)
        k_diag = [kx, ky, kz, kthx, kthy, kthz]
        matrix = [[k_diag[i] if i == j else 0.0 for j in range(6)] for i in range(6)]

        return WinklerStiffness(
            kz_kn_m=kz, kx_kn_m=kx, ky_kn_m=ky,
            kthx_knm_rad=kthx, kthy_knm_rad=kthy, kthz_knm_rad=kthz,
            matrix_6x6=matrix, converged=True, iterations=1,
        )

    @classmethod
    def iterate_global_model(cls,
                              current_kthx: float, current_kthy: float,
                              new_kthx: float, new_kthy: float,
                              tolerance: float = 0.05,
                              iteration: int = 1,
                              max_iterations: int = 10) -> tuple[bool, float]:
        """
        Check convergence between Fase 4 structural model and foundation stiffness.
        Returns (converged, max_relative_error).
        """
        err_x = abs(new_kthx - current_kthx) / max(abs(current_kthx), 1.0)
        err_y = abs(new_kthy - current_kthy) / max(abs(current_kthy), 1.0)
        max_err = max(err_x, err_y)
        converged = max_err <= tolerance
        return converged, max_err


# ---------------------------------------------------------------------------
# Embedded Pole Service
# ---------------------------------------------------------------------------

class EmbeddedPoleService:
    """
    Direct embedment: pole in concrete/grout block.
    Broms simplified method for short rigid pile in cohesive/cohesionless soil.
    """

    @classmethod
    def check(cls,
              V_Ed_kn: float, M_Ed_knm: float,
              pole_diameter_mm: float,
              embedment_length_m: float,
              fill_type: str,
              gamma_concrete_kn_m3: float = 24.0,
              cu_kpa: Optional[float] = None,
              phi_deg: Optional[float] = None,
              gamma_soil_kn_m3: float = 18.0) -> EmbeddedPoleResult:
        """
        Simplified passive pressure model for embedded pole.
        For concrete fill: treat as equivalent rectangular block.
        """
        d = pole_diameter_mm / 1000.0   # convert to m
        L = embedment_length_m

        # Passive resistance of fill:
        # Concrete/grout fill → bearing strength σ_Rd ~ 3 fck (simplified)
        # For grout: approximate fck = 30 MPa
        if fill_type in ("CONCRETE", "GROUT"):
            fck_kpa = 25_000.0 if fill_type == "CONCRETE" else 30_000.0
            sigma_Rd = 3.0 * fck_kpa / 1.5  # EC2 local bearing ≈ 60 MPa → simplified
        else:
            # Granular: use Rankine passive + Kp
            Kp = 3.0   # conservative for dense granular
            sigma_Rd = Kp * gamma_soil_kn_m3 * L   # pressure at toe

        # Reaction model: top reaction R_top, toe reaction R_toe
        # Equilibrium of rigid pole:
        # Moment about base: V_Ed * L - R_top * L + M_Ed = 0 (simplified two-spring)
        R_top = (V_Ed_kn * L + M_Ed_knm) / L if L > 0 else 0.0
        R_toe = V_Ed_kn - R_top   # horizontal equilibrium

        # Passive resistance capacity (per unit width, full depth)
        F_passive = sigma_Rd * d * L / 2.0   # triangular distribution
        util_lateral = abs(R_top) / F_passive if F_passive > 0 else 999.0

        # Toe bearing
        sigma_toe = abs(R_toe) / (d * 0.5) if d > 0 else 999.0
        util_toe = sigma_toe / sigma_Rd if sigma_Rd > 0 else 999.0

        # Moment at surface
        M_at_surface = V_Ed_kn * 0.0 + M_Ed_knm  # stub: moment at surface = M_Ed

        compliant = (util_lateral <= 1.0) and (util_toe <= 1.0)

        return EmbeddedPoleResult(
            L_embed_m=L,
            passive_pressure_kpa=sigma_Rd,
            reaction_top_kn=R_top,
            reaction_bottom_kn=R_toe,
            moment_at_surface_knm=M_at_surface,
            util_lateral=util_lateral,
            util_toe=util_toe,
            compliant=compliant,
        )


# ---------------------------------------------------------------------------
# Foundation Optimizer (Pareto)
# ---------------------------------------------------------------------------

class FoundationOptimizer:
    """
    Multi-objective Pareto optimizer for foundation candidates.
    Objectives: cost, CO2, excavation_volume, risk (= util_governing).
    """

    @staticmethod
    def is_dominated(a: FoundationCandidateSummary,
                     b: FoundationCandidateSummary) -> bool:
        """Return True if candidate b dominates candidate a (b ≤ a on all, < on one)."""
        objs_a = (a.total_cost_eur, a.total_co2_kg, a.excavation_volume_m3, a.util_governing)
        objs_b = (b.total_cost_eur, b.total_co2_kg, b.excavation_volume_m3, b.util_governing)
        return all(bv <= av for av, bv in zip(objs_a, objs_b)) and any(
            bv < av for av, bv in zip(objs_a, objs_b)
        )

    @classmethod
    def pareto_front(cls, candidates: list[FoundationCandidateSummary]
                     ) -> list[FoundationCandidateSummary]:
        front = []
        for c in candidates:
            if not c.feasible:
                continue
            if not any(cls.is_dominated(c, other) for other in candidates if other is not c):
                front.append(c)
        return front

    @classmethod
    def select(cls, candidates: list[FoundationCandidateSummary],
               w_cost: float = 0.4, w_co2: float = 0.3,
               w_excavation: float = 0.2, w_risk: float = 0.1,
               ) -> list[FoundationCandidateSummary]:
        """
        Returns up to 4 labeled solutions:
        RECOMMENDED (min weighted score), MIN_COST, MIN_CO2, MIN_EXCAVATION
        """
        front = cls.pareto_front(candidates)
        if not front:
            return []

        # Normalize objectives
        costs = [c.total_cost_eur for c in front]
        co2s = [c.total_co2_kg for c in front]
        excs = [c.excavation_volume_m3 for c in front]
        utils = [c.util_governing for c in front]

        def norm(val: float, vals: list[float]) -> float:
            lo, hi = min(vals), max(vals)
            return (val - lo) / (hi - lo) if hi > lo else 0.0

        for c in front:
            c.score = (w_cost * norm(c.total_cost_eur, costs)
                       + w_co2 * norm(c.total_co2_kg, co2s)
                       + w_excavation * norm(c.excavation_volume_m3, excs)
                       + w_risk * norm(c.util_governing, utils))

        front_sorted = sorted(front, key=lambda c: c.score)
        front_sorted[0].label = "RECOMMENDED"

        min_cost = min(front, key=lambda c: c.total_cost_eur)
        min_co2 = min(front, key=lambda c: c.total_co2_kg)
        min_exc = min(front, key=lambda c: c.excavation_volume_m3)

        if min_cost is not front_sorted[0]:
            min_cost.label = "MIN_COST"
        if min_co2 is not front_sorted[0] and min_co2 is not min_cost:
            min_co2.label = "MIN_CO2"
        if min_exc is not front_sorted[0] and min_exc is not min_cost and min_exc is not min_co2:
            min_exc.label = "MIN_EXCAVATION"

        labeled = [c for c in front_sorted if c.label]
        return labeled[:4]


# ---------------------------------------------------------------------------
# Normative Classifier
# ---------------------------------------------------------------------------

@dataclass
class NormativeClassification:
    geo_level: str
    maturity_level: str
    applicable_families: list[str]
    blockers: list[str]
    warnings: list[str]
    release_blocked: bool


class FoundationNormativeClassifier:
    """
    Assigns maturity level M0-M4 and applicable families based on G-level and checks.
    """

    @classmethod
    def classify(cls,
                 geo_level: str,
                 has_location: bool,
                 has_soil_params: bool,
                 has_geotechnical_report: bool,
                 has_as_built: bool,
                 pile_route: bool = False,
                 slope_proximity: bool = False,
                 checks_pass: bool = True,
                 ) -> NormativeClassification:
        blockers: list[str] = []
        warnings: list[str] = []
        families = ["F11-A", "F11-B", "F11-C", "F11-D", "F11-E", "F11-F", "F11-G"]

        if not has_location:
            blockers.append("F11-E001: Ubicación no definida")

        if pile_route:
            if geo_level not in ("G3", "G4"):
                blockers.append("F11-E006: F11-H requiere informe geotécnico (G3+)")
            else:
                families = ["F11-H"]

        if slope_proximity:
            blockers.append("F11-E006: Interacción con talud no verificada")

        if not checks_pass:
            blockers.append("F11-E003/E004: Verificaciones geotécnicas no conformes")

        # Maturity level
        if not has_location:
            maturity = "M0"
        elif geo_level == "G0":
            maturity = "M0"
            warnings.append("F11-W001: Suelo G0 — solo estimación comercial")
        elif geo_level == "G1":
            maturity = "M1"
            warnings.append("F11-W001: Suelo simplificado G1")
        elif geo_level == "G2":
            maturity = "M2"
            warnings.append("F11-W003: Parámetros parciales — validar con OT")
        elif geo_level == "G3" and checks_pass:
            maturity = "M3"
        elif geo_level == "G4" and checks_pass and has_as_built:
            maturity = "M4"
        else:
            maturity = "M2"
            warnings.append("F11-W003: G4 sin as-built → M2")

        release_blocked = maturity in ("M0", "M1") or bool(blockers)

        if geo_level in ("G0", "G1") and not has_geotechnical_report:
            warnings.append("F11-W001: Sin informe geotécnico — valores conservadores")

        return NormativeClassification(
            geo_level=geo_level,
            maturity_level=maturity,
            applicable_families=families,
            blockers=blockers,
            warnings=warnings,
            release_blocked=release_blocked,
        )


# ---------------------------------------------------------------------------
# Geotechnical Classifier
# ---------------------------------------------------------------------------

@dataclass
class GeoClassificationResult:
    geo_level: str
    confirmed_fields: list[str]
    proposed_fields: list[str]
    conservative_fields: list[str]
    blockers: list[str]
    warnings: list[str]


class GeotechnicalClassifier:
    """
    7-question intake → assigns G-level, generates blockers and warnings.
    """

    @classmethod
    def classify(cls,
                 has_location: bool,
                 surface_type: Optional[str],          # ROCK/GRAVEL/SAND/CLAY/FILL/UNKNOWN
                 has_soil_params: bool,
                 water_scenario: str,
                 has_geotechnical_report: bool,
                 has_field_tests: bool,
                 has_as_built: bool,
                 slope_near_m: Optional[float] = None,
                 buried_services: Optional[bool] = None,
                 ) -> GeoClassificationResult:
        blockers: list[str] = []
        warnings: list[str] = []
        confirmed: list[str] = []
        proposed: list[str] = []
        conservative: list[str] = []

        if not has_location:
            blockers.append("F11-E001: Ubicación no definida — sin datos geotécnicos posibles")
            return GeoClassificationResult("G0", confirmed, proposed, conservative, blockers, warnings)

        confirmed.append("location")

        if water_scenario == "UNKNOWN":
            warnings.append("F11-W002: Nivel freático desconocido — se asumirá nivel conservador")
            conservative.append("water_table")
        else:
            confirmed.append("water_scenario")

        if buried_services is None:
            warnings.append("F11-W001: Servicios enterrados no verificados")
        if slope_near_m is not None and slope_near_m < 5.0:
            blockers.append("F11-E006: Talud a menos de 5m — análisis estabilidad requerido")

        if not surface_type or surface_type == "UNKNOWN":
            conservative.append("soil_class")
            proposed.append("phi_deg (conservative)")
            proposed.append("gamma_kn_m3 (conservative)")
            geo_level = "G0"
        elif not has_soil_params:
            conservative.append("phi_deg")
            conservative.append("c_kpa")
            proposed.append("E_mpa")
            geo_level = "G1"
            warnings.append("F11-W001: Parámetros de suelo estimados por tipo")
        elif has_soil_params and not has_geotechnical_report:
            confirmed.extend(["phi_deg", "c_kpa", "gamma_kn_m3"])
            geo_level = "G2"
        elif has_geotechnical_report and not has_as_built:
            confirmed.extend(["phi_deg", "c_kpa", "gamma_kn_m3", "geotechnical_report"])
            if has_field_tests:
                confirmed.append("field_tests")
            geo_level = "G3"
        else:
            confirmed.extend(["phi_deg", "c_kpa", "gamma_kn_m3", "geotechnical_report",
                               "as_built", "execution_control"])
            geo_level = "G4"

        return GeoClassificationResult(
            geo_level=geo_level,
            confirmed_fields=confirmed,
            proposed_fields=proposed,
            conservative_fields=conservative,
            blockers=blockers,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Geometry hash
# ---------------------------------------------------------------------------

def compute_foundation_hash(family: str,
                             width_m: Optional[float],
                             length_m: Optional[float],
                             depth_m: Optional[float],
                             diameter_m: Optional[float],
                             N_kn: Optional[float],
                             My_knm: Optional[float],
                             Mz_knm: Optional[float]) -> str:
    payload = {
        "family": family,
        "width_m": round(width_m or 0.0, 4),
        "length_m": round(length_m or 0.0, 4),
        "depth_m": round(depth_m or 0.0, 4),
        "diameter_m": round(diameter_m or 0.0, 4),
        "N_kn": round(N_kn or 0.0, 3),
        "My_knm": round(My_knm or 0.0, 3),
        "Mz_knm": round(Mz_knm or 0.0, 3),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
