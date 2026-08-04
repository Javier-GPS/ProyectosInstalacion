"""
Fase 10 · Placa Base, Pernos y Anclajes
Services: ContactSolver, BasePlateDesignService, AnchorCheckService,
          ConcreteFailureService, ShearTransferService,
          BasePlateOptimizer, BasePlateNormativeClassifier
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DesignActions:
    N_kn: float = 0.0    # axial (tension +)
    Vy_kn: float = 0.0
    Vz_kn: float = 0.0
    T_knm: float = 0.0
    My_knm: float = 0.0
    Mz_knm: float = 0.0


@dataclass
class BoltForce:
    index: int
    N_kn: float    # tension positive
    Vx_kn: float
    Vy_kn: float


@dataclass
class ContactResult:
    contact_state: str
    contact_area_mm2: float
    sigma_max_mpa: float
    sigma_avg_mpa: float
    neutral_axis_dist_mm: Optional[float]
    bolt_forces: List[BoltForce]
    iterations: int
    converged: bool
    equilibrium_error: float
    rotation_rad: float
    horizontal_slip_mm: float


@dataclass
class PlateCheckResult:
    util_bending: float
    util_stress: float
    governing_region: str
    design_method: str
    moment_arm_mm: float


@dataclass
class AnchorSteelResult:
    rod_index: int
    util_tension: float
    util_shear: float
    util_interaction: float
    util_bending: float
    governing_mode: str
    axial_stiffness_kn_mm: float


@dataclass
class ConcreteFailureCheck:
    mode: str
    NEd_kn: float
    VEd_kn: float
    NRd_kn: float
    VRd_kn: float
    util: float
    governing: bool
    factors: Dict[str, float]


@dataclass
class NormativeClassResult:
    is_compliant: bool
    blockers: List[str]
    warnings: List[str]
    solution_family: str
    maturity_level: str


@dataclass
class OptimCandidate:
    label: str
    pattern_label: str
    bolt_count: int
    bolt_diameter_mm: float
    plate_thickness_mm: float
    total_cost_eur: float
    total_mass_kg: float
    total_co2_kg: float
    risk_score: float
    util_governing: float
    is_standard: bool


# ---------------------------------------------------------------------------
# 1. Contact Solver
# ---------------------------------------------------------------------------

class ContactSolver:
    """
    Iterative unilateral contact solver for base plate - mortar - concrete.

    The plate can transmit compression but not tension to the mortar.
    Bolts carry tension (and optionally shear).

    Algorithm:
    1. Initialize contact over full effective footprint
    2. Solve displacements and forces
    3. Remove tension contact points; activate bolts in tension where opening occurs
    4. Update non-linear stiffnesses and gaps
    5. Repeat until convergence:
       - Δbolt_force < tolerance_force (relative)
       - Δcontact_area < tolerance_area (relative)
    """

    GAMMA_CONCRETE = 1.5
    GAMMA_MORTAR = 1.5

    @classmethod
    def solve(
        cls,
        N_kn: float,
        Vy_kn: float,
        Vz_kn: float,
        T_knm: float,
        My_knm: float,
        Mz_knm: float,
        plate_width_mm: float,
        plate_length_mm: float,
        plate_thickness_mm: float,
        bolt_x_mm: List[float],
        bolt_y_mm: List[float],
        bolt_stiffness_kn_mm: float,
        mortar_modulus_mpa: float = 20000.0,
        mortar_thickness_mm: float = 50.0,
        max_iterations: int = 200,
        tolerance_force: float = 1e-4,
        tolerance_area: float = 0.001,
    ) -> ContactResult:
        """
        Simplified elastic model with iterative neutral axis search.

        For a rectangular plate under biaxial bending + axial:
        - Contact zone limited to compression side
        - Bolts provide tensile restraint on tension side
        - Mortar provides distributed compression spring
        """
        n_bolts = len(bolt_x_mm)
        assert n_bolts == len(bolt_y_mm), "Bolt coordinate arrays must match"

        # Mortar spring stiffness per unit area [kN/mm/mm²]
        k_mortar = mortar_modulus_mpa / mortar_thickness_mm / 1000.0  # kN/mm/mm²

        plate_area = plate_width_mm * plate_length_mm
        Ix = plate_width_mm * plate_length_mm ** 3 / 12.0
        Iy = plate_length_mm * plate_width_mm ** 3 / 12.0

        # Iterative search for neutral axis position
        # Use a simplified 1D section model along the moment axis
        # Dominant moment direction
        M_res_knm = math.sqrt(My_knm ** 2 + Mz_knm ** 2)

        # Determine contact depth via bisection (neutral axis search)
        # Reference: plate centroid at (0,0)
        half_L = plate_length_mm / 2.0

        bolt_forces: List[BoltForce] = [BoltForce(i, 0.0, 0.0, 0.0) for i in range(n_bolts)]
        converged = False
        iterations = 0
        equilibrium_error = 0.0
        neutral_axis = 0.0
        contact_area = plate_area
        sigma_max = 0.0
        sigma_avg = 0.0
        rotation_rad = 0.0
        horizontal_slip_mm = 0.0
        contact_state = "FULL"

        # Simplified elastic distribution assuming rigid plate
        # This is the P0 conservative model
        e_y = My_knm * 1000.0 / N_kn if abs(N_kn) > 1e-6 else 0.0  # mm
        e_z = Mz_knm * 1000.0 / N_kn if abs(N_kn) > 1e-6 else 0.0

        # Determine if contact is full or partial
        if N_kn >= 0:
            # Pure tension - all bolts loaded
            bolt_tension_each = N_kn / n_bolts if n_bolts > 0 else 0.0
            for i in range(n_bolts):
                bolt_forces[i] = BoltForce(i, bolt_tension_each, 0.0, 0.0)
            contact_state = "LOCAL_OPENING"
            contact_area = 0.0
            sigma_max = 0.0
            sigma_avg = 0.0
            neutral_axis = half_L  # full opening
        else:
            # Compression dominant
            # Check eccentricity to determine contact state
            e_total = math.sqrt(e_y ** 2 + e_z ** 2)
            kern_radius = min(plate_length_mm, plate_width_mm) / 6.0

            if e_total <= kern_radius:
                # Full contact - all compressed
                contact_state = "FULL"
                contact_area = plate_area
                sigma_avg = abs(N_kn) / plate_area * 1000.0  # MPa (N → kN, area in mm²)
                # Bending contribution
                sigma_bend_y = abs(My_knm) * 1e6 / (Ix / (plate_length_mm / 2)) if Ix > 0 else 0.0
                sigma_bend_z = abs(Mz_knm) * 1e6 / (Iy / (plate_width_mm / 2)) if Iy > 0 else 0.0
                sigma_max = sigma_avg + sigma_bend_y / 1000.0 + sigma_bend_z / 1000.0
                neutral_axis = None
                for i in range(n_bolts):
                    bolt_forces[i] = BoltForce(i, 0.0, 0.0, 0.0)
            else:
                # Partial contact - iterative neutral axis
                contact_state = "PARTIAL"
                # Bisection: find contact depth c such that equilibrium is satisfied
                c_lo, c_hi = 0.0, plate_length_mm
                prev_bolt_tension_max = 0.0

                for it in range(max_iterations):
                    iterations = it + 1
                    c = (c_lo + c_hi) / 2.0
                    # Contact block centroid from compressed edge
                    x_c = plate_length_mm / 2.0 - c / 2.0  # distance from plate center
                    A_c = c * plate_width_mm
                    # Resultant contact force (compression)
                    # Moment arm to contact resultant
                    arm = x_c  # simplified
                    # Compression from contact
                    C_kn = abs(N_kn) + sum(f.N_kn for f in bolt_forces)
                    # Check equilibrium of moments
                    M_contact = C_kn * arm / 1000.0  # kNm
                    M_applied = M_res_knm
                    if M_contact < M_applied:
                        # Need deeper contact → more tension bolts
                        c_hi = c
                    else:
                        c_lo = c

                    # Update bolt forces (tension bolts on opening side)
                    bolt_tension_total = max(0.0, M_applied * 1000.0 / arm - abs(N_kn)) \
                        if arm > 1e-6 else 0.0
                    bolt_tension_each = bolt_tension_total / n_bolts if n_bolts > 0 else 0.0
                    for i in range(n_bolts):
                        y_b = bolt_x_mm[i]  # bolt position relative to plate center
                        # Bolts on tension side get tension
                        if y_b > (plate_length_mm / 2.0 - c):
                            bolt_forces[i] = BoltForce(i, bolt_tension_each, 0.0, 0.0)
                        else:
                            bolt_forces[i] = BoltForce(i, 0.0, 0.0, 0.0)

                    delta_f = abs(bolt_tension_each - prev_bolt_tension_max)
                    rel_err = delta_f / (abs(bolt_tension_each) + 1e-10)
                    if rel_err < tolerance_force and abs(c_hi - c_lo) / plate_length_mm < tolerance_area:
                        converged = True
                        break
                    prev_bolt_tension_max = bolt_tension_each

                neutral_axis = plate_length_mm / 2.0 - (c_lo + c_hi) / 2.0
                contact_area = ((c_lo + c_hi) / 2.0) * plate_width_mm
                sigma_max = abs(N_kn) / contact_area * 1000.0 * 2.0 if contact_area > 0 else 0.0
                sigma_avg = abs(N_kn) / contact_area * 1000.0 if contact_area > 0 else 0.0

                # Check biaxial sectors
                if abs(My_knm) > 1e-6 and abs(Mz_knm) > 1e-6:
                    contact_state = "BIAXIAL_SECTORS"

            # Shear distribution (simplified): equal to all bolts in contact
            V_total = math.sqrt(Vy_kn ** 2 + Vz_kn ** 2)
            v_per_bolt = V_total / n_bolts if n_bolts > 0 else 0.0
            for i in range(n_bolts):
                bolt_forces[i] = BoltForce(
                    bolt_forces[i].index,
                    bolt_forces[i].N_kn,
                    v_per_bolt * Vy_kn / (V_total + 1e-12),
                    v_per_bolt * Vz_kn / (V_total + 1e-12),
                )

            horizontal_slip_mm = V_total / (bolt_stiffness_kn_mm * n_bolts) if n_bolts > 0 else 0.0

        # Equilibrium check
        sum_N = sum(f.N_kn for f in bolt_forces)
        residual = abs(sum_N + N_kn)  # should be zero (tensile bolt + compressive contact = 0)
        equilibrium_error = residual / (abs(N_kn) + 1e-6)

        max_bolt_tension = max((f.N_kn for f in bolt_forces), default=0.0)
        max_bolt_shear = max((math.sqrt(f.Vx_kn**2 + f.Vy_kn**2) for f in bolt_forces), default=0.0)

        rotation_rad = M_res_knm / (bolt_stiffness_kn_mm * 1e-3 *
                                     sum((bolt_y_mm[i]**2 + bolt_x_mm[i]**2)
                                         for i in range(n_bolts)) + 1e-9)

        return ContactResult(
            contact_state=contact_state,
            contact_area_mm2=contact_area,
            sigma_max_mpa=sigma_max,
            sigma_avg_mpa=sigma_avg,
            neutral_axis_dist_mm=neutral_axis,
            bolt_forces=bolt_forces,
            iterations=iterations,
            converged=converged or (contact_state in ("FULL", "LOCAL_OPENING")),
            equilibrium_error=equilibrium_error,
            rotation_rad=rotation_rad,
            horizontal_slip_mm=horizontal_slip_mm,
        )


# ---------------------------------------------------------------------------
# 2. Base Plate Design Service
# ---------------------------------------------------------------------------

class BasePlateDesignService:
    """
    Hierarchical plate design: P0 (rigid) → P1 (cantilever/components)
    → P2 (yield line) → P3 (FEM shell) → P4 (FEM solid)

    P1 cantilever model (EN 1993-1-8 §6):
    m = overhang length from bolt / shaft edge [mm]
    t_req = sqrt(6 * M_Ed_per_unit / fy_mpa)
    """

    GAMMA_M0 = 1.0

    @classmethod
    def check_cantilever(
        cls,
        overhang_mm: float,
        sigma_contact_mpa: float,
        plate_thickness_mm: float,
        fy_mpa: float,
    ) -> PlateCheckResult:
        """
        P1 cantilever model.
        M_Ed per unit width = sigma_contact * overhang^2 / 2
        Required thickness: t >= sqrt(6 * M_Ed / fy / gamma_M0)
        """
        M_Ed_nmm = sigma_contact_mpa * overhang_mm ** 2 / 2.0  # N·mm per mm width
        t_req_mm = math.sqrt(6.0 * M_Ed_nmm / (fy_mpa / cls.GAMMA_M0))
        util = t_req_mm / plate_thickness_mm

        sigma_Ed = 6.0 * M_Ed_nmm / plate_thickness_mm ** 2
        sigma_Rd = fy_mpa / cls.GAMMA_M0
        util_stress = sigma_Ed / sigma_Rd

        return PlateCheckResult(
            util_bending=util,
            util_stress=util_stress,
            governing_region="CANTILEVER",
            design_method="P1_CANTILEVER",
            moment_arm_mm=overhang_mm,
        )

    @classmethod
    def check_yield_line(
        cls,
        plate_width_mm: float,
        bolt_pcd_mm: float,
        sigma_contact_mpa: float,
        plate_thickness_mm: float,
        fy_mpa: float,
        bolt_count: int,
    ) -> PlateCheckResult:
        """
        P2 yield line (simplified Yun & Salmon approach for bolt pattern).
        Moment per unit width at yield line between bolts.
        """
        # bolt spacing along bolt circle
        s_bolt = math.pi * bolt_pcd_mm / bolt_count
        # effective tributary width per bolt
        b_eff = s_bolt
        # Moment demand (triangular distribution assumption)
        overhang = (plate_width_mm - bolt_pcd_mm) / 2.0
        M_Ed = sigma_contact_mpa * overhang ** 2 / 2.0  # N·mm per mm
        t_req = math.sqrt(4.0 * M_Ed / (fy_mpa / cls.GAMMA_M0))  # plastic section modulus
        util = t_req / plate_thickness_mm

        return PlateCheckResult(
            util_bending=util,
            util_stress=util * (fy_mpa / cls.GAMMA_M0) / (fy_mpa / cls.GAMMA_M0),
            governing_region="YIELD_LINE",
            design_method="P2_YIELD_LINE",
            moment_arm_mm=overhang,
        )

    @classmethod
    def minimum_thickness(
        cls,
        N_kn: float,
        My_knm: float,
        Mz_knm: float,
        plate_width_mm: float,
        plate_length_mm: float,
        bolt_pcd_mm: float,
        fy_mpa: float,
        contact_result: ContactResult,
    ) -> float:
        """
        Compute minimum required plate thickness from P1 model.
        Uses governing cantilever overhang and max sigma.
        """
        overhang = (min(plate_width_mm, plate_length_mm) - bolt_pcd_mm) / 2.0
        sigma = contact_result.sigma_max_mpa
        if sigma < 1e-6:
            sigma = abs(N_kn) / (plate_width_mm * plate_length_mm) * 1000.0
        M_Ed = sigma * overhang ** 2 / 2.0
        t_min = math.sqrt(6.0 * M_Ed / (fy_mpa / cls.GAMMA_M0))
        return t_min


# ---------------------------------------------------------------------------
# 3. Anchor Check Service (steel)
# ---------------------------------------------------------------------------

class AnchorCheckService:
    """
    Steel verification for embedded bolts (L, J, straight).
    EN 1993-1-8 adapted for anchor rods.
    """

    GAMMA_M2 = 1.25

    @classmethod
    def check_rod_steel(
        cls,
        N_Ed_kn: float,
        V_Ed_kn: float,
        nominal_diameter_mm: float,
        effective_thread_area_mm2: float,
        fy_mpa: float,
        fu_mpa: float,
        rod_type: str,
        hook_length_mm: Optional[float] = None,
        plate_thickness_mm: float = 0.0,
        hole_clearance_mm: float = 3.0,
    ) -> AnchorSteelResult:
        """
        Verify rod in tension, shear and interaction.
        """
        # Tension resistance (thread area governs)
        NRd_tension = 0.9 * fu_mpa * effective_thread_area_mm2 / cls.GAMMA_M2 / 1000.0  # kN
        util_tension = N_Ed_kn / NRd_tension if NRd_tension > 0 else 999.0

        # Shear resistance (gross shank area)
        A_s = math.pi * nominal_diameter_mm ** 2 / 4.0
        VRd_shear = fu_mpa * A_s / (math.sqrt(3.0) * cls.GAMMA_M2) / 1000.0  # kN
        util_shear = V_Ed_kn / VRd_shear if VRd_shear > 0 else 999.0

        # Interaction (EN 1993-1-8 Table 3.2)
        util_interaction = math.sqrt(util_tension ** 2 + util_shear ** 2)

        # Bending from shear + plate flexibility (simplified)
        # M_Ed = V_Ed * (t_plate / 2 + clearance)
        e_bend = plate_thickness_mm / 2.0 + hole_clearance_mm
        M_Ed_knm = V_Ed_kn * e_bend / 1000.0
        Wel = math.pi * nominal_diameter_mm ** 3 / 32.0  # mm³
        sigma_bend = M_Ed_knm * 1e6 / Wel if Wel > 0 else 0.0  # MPa
        sigma_Rd = fy_mpa / 1.0  # gamma_M0 = 1
        util_bending = sigma_bend / sigma_Rd

        # Axial stiffness (composed: shank + thread + embedment)
        E_steel = 210000.0  # MPa
        L_shank = max(plate_thickness_mm, 1.0)
        L_thread = nominal_diameter_mm * 1.5
        L_embed = 100.0  # representative
        k_shank = E_steel * A_s / L_shank / 1000.0 if L_shank > 0 else 1e6
        k_thread = E_steel * effective_thread_area_mm2 / L_thread / 1000.0 if L_thread > 0 else 1e6
        k_embed = E_steel * A_s / L_embed / 1000.0
        k_total = 1.0 / (1.0 / k_shank + 1.0 / k_thread + 1.0 / k_embed)

        governing_mode = "TENSION" if util_tension >= util_shear else "SHEAR"
        if util_interaction > max(util_tension, util_shear):
            governing_mode = "INTERACTION"
        if util_bending > util_interaction:
            governing_mode = "BENDING"

        return AnchorSteelResult(
            rod_index=-1,  # to be set by caller
            util_tension=util_tension,
            util_shear=util_shear,
            util_interaction=util_interaction,
            util_bending=util_bending,
            governing_mode=governing_mode,
            axial_stiffness_kn_mm=k_total,
        )

    @classmethod
    def effective_thread_area(cls, nominal_d_mm: float) -> float:
        """Approximate effective thread area for metric bolts (EN ISO 898-1)."""
        # Stress area approximation: As ≈ π/4 * ((d - 0.9382*p)/1)²
        # Using simplified: As ≈ 0.7854 * (d - 0.9382 * p)²
        # Pitch approximation from diameter
        pitch = {8: 1.25, 10: 1.5, 12: 1.75, 16: 2.0, 20: 2.5, 24: 3.0,
                 27: 3.0, 30: 3.5, 33: 3.5, 36: 4.0, 42: 4.5, 48: 5.0}.get(
            int(nominal_d_mm), nominal_d_mm / 10.0)
        d2 = nominal_d_mm - 0.6495 * pitch
        d3 = nominal_d_mm - 1.2269 * pitch
        As = math.pi / 4.0 * ((d2 + d3) / 2.0) ** 2
        return As


# ---------------------------------------------------------------------------
# 4. Concrete Failure Service
# ---------------------------------------------------------------------------

class ConcreteFailureService:
    """
    EN 1992-4 concrete failure modes for anchor groups.
    """

    GAMMA_C = 1.5

    @classmethod
    def concrete_cone(
        cls,
        N_Ed_kn: float,
        hef_mm: float,
        fck_mpa: float,
        cracked: bool = True,
        c_min_mm: Optional[float] = None,
        s_min_mm: Optional[float] = None,
        n_anchors: int = 1,
    ) -> ConcreteFailureCheck:
        """
        EN 1992-4 §7.2.1 — Concrete cone failure.
        NRd,c = NRk,c / gamma_c
        NRk,c = k1 * sqrt(fck) * hef^1.5 * (A_c,N / A_c0,N) * psi_s * psi_re * psi_ec
        """
        k1 = 7.7 if cracked else 11.0  # EN 1992-4 Table 6
        # Reference area single anchor
        A_c0 = (3.0 * hef_mm) ** 2  # mm²
        # Actual projected area (simplified: assume no edge effects if c_min not given)
        psi_s = 1.0   # edge distance factor (conservative = 1.0)
        if c_min_mm is not None and c_min_mm < 1.5 * hef_mm:
            psi_s = 0.7 + 0.3 * c_min_mm / (1.5 * hef_mm)

        psi_re = 0.5 + hef_mm / 200.0  # supplementary reinforcement factor
        psi_re = min(psi_re, 1.0)

        psi_ec = 1.0   # eccentricity factor (conservative)

        # Group effect: A_c,N / A_c0,N ≈ n_anchors (simplified, no overlap)
        area_ratio = min(n_anchors, 4)  # capped for simplicity

        NRk_c = k1 * math.sqrt(fck_mpa) * hef_mm ** 1.5 * area_ratio * psi_s * psi_re * psi_ec
        NRk_c /= 1000.0  # N → kN
        NRd_c = NRk_c / cls.GAMMA_C
        util = N_Ed_kn / NRd_c if NRd_c > 0 else 999.0

        return ConcreteFailureCheck(
            mode="CONCRETE_CONE",
            NEd_kn=N_Ed_kn,
            VEd_kn=0.0,
            NRd_kn=NRd_c,
            VRd_kn=0.0,
            util=util,
            governing=False,
            factors={"k1": k1, "psi_s": psi_s, "psi_re": psi_re, "psi_ec": psi_ec,
                     "area_ratio": area_ratio, "NRk_c_kn": NRk_c},
        )

    @classmethod
    def pull_out(
        cls,
        N_Ed_kn: float,
        hef_mm: float,
        fck_mpa: float,
        rod_type: str = "STRAIGHT",
        end_plate_d_mm: Optional[float] = None,
        hook_length_mm: Optional[float] = None,
        nominal_d_mm: float = 20.0,
        cracked: bool = True,
    ) -> ConcreteFailureCheck:
        """
        EN 1992-4 §7.2.2 — Pull-out resistance.
        For headed bolts: NRk,p = p * A_h * fck  (p = 6 for cracked, 9 for uncracked)
        For hook bolts: NRk,p = 0.9 * fck * l_b * pi * d
        """
        if rod_type == "STRAIGHT" and end_plate_d_mm is not None:
            A_h = math.pi / 4.0 * (end_plate_d_mm ** 2 - nominal_d_mm ** 2)
            p = 6.0 if cracked else 9.0
            NRk_p = p * A_h * fck_mpa / 1000.0  # kN
        elif rod_type in ("L", "J") and hook_length_mm is not None:
            l_b = hook_length_mm  # bend length
            NRk_p = 0.9 * fck_mpa * l_b * math.pi * nominal_d_mm / 1000.0
        else:
            # Conservative fallback: use cone
            A_s = math.pi * nominal_d_mm ** 2 / 4.0
            NRk_p = 7.0 * fck_mpa * A_s / 1000.0

        NRd_p = NRk_p / cls.GAMMA_C
        util = N_Ed_kn / NRd_p if NRd_p > 0 else 999.0

        return ConcreteFailureCheck(
            mode="PULL_OUT",
            NEd_kn=N_Ed_kn,
            VEd_kn=0.0,
            NRd_kn=NRd_p,
            VRd_kn=0.0,
            util=util,
            governing=False,
            factors={"rod_type": rod_type},
        )

    @classmethod
    def edge_shear(
        cls,
        V_Ed_kn: float,
        c1_mm: float,
        hef_mm: float,
        fck_mpa: float,
        cracked: bool = True,
        load_toward_edge: bool = True,
    ) -> ConcreteFailureCheck:
        """
        EN 1992-4 §7.2.4 — Shear failure near edge.
        VRk,c = k2 * l^0.2 * d_nom^0.1 * sqrt(fck) * c1^1.5 * psi_h * psi_s * psi_alpha * psi_ec
        Simplified: VRk,c = k_v * sqrt(fck) * c1^1.5
        """
        if not load_toward_edge:
            VRd_c = 999.0  # not governing
            return ConcreteFailureCheck(
                mode="EDGE_SHEAR", NEd_kn=0.0, VEd_kn=V_Ed_kn,
                NRd_kn=0.0, VRd_kn=VRd_c, util=0.0, governing=False,
                factors={"note": "load not toward edge"}
            )
        k_v = 1.4 if cracked else 1.7
        VRk_c = k_v * math.sqrt(fck_mpa) * c1_mm ** 1.5 / 1000.0  # kN
        VRd_c = VRk_c / cls.GAMMA_C
        util = V_Ed_kn / VRd_c if VRd_c > 0 else 999.0

        return ConcreteFailureCheck(
            mode="EDGE_SHEAR",
            NEd_kn=0.0,
            VEd_kn=V_Ed_kn,
            NRd_kn=0.0,
            VRd_kn=VRd_c,
            util=util,
            governing=False,
            factors={"k_v": k_v, "c1_mm": c1_mm},
        )

    @classmethod
    def pry_out(
        cls,
        V_Ed_kn: float,
        hef_mm: float,
        fck_mpa: float,
        cracked: bool = True,
        n_anchors: int = 1,
    ) -> ConcreteFailureCheck:
        """
        EN 1992-4 §7.2.4 pry-out: VRk,cp = k3 * NRk,c
        k3 = 1 if hef < 60 mm, 2 if hef >= 60 mm
        """
        k3 = 1.0 if hef_mm < 60.0 else 2.0
        k1 = 7.7 if cracked else 11.0
        NRk_c = k1 * math.sqrt(fck_mpa) * hef_mm ** 1.5 * n_anchors / 1000.0
        VRk_cp = k3 * NRk_c
        VRd_cp = VRk_cp / cls.GAMMA_C
        util = V_Ed_kn / VRd_cp if VRd_cp > 0 else 999.0

        return ConcreteFailureCheck(
            mode="PRY_OUT",
            NEd_kn=0.0,
            VEd_kn=V_Ed_kn,
            NRd_kn=0.0,
            VRd_kn=VRd_cp,
            util=util,
            governing=False,
            factors={"k3": k3, "NRk_c_kn": NRk_c},
        )

    @classmethod
    def interaction_check(
        cls,
        N_Ed_kn: float,
        V_Ed_kn: float,
        NRd_kn: float,
        VRd_kn: float,
    ) -> float:
        """
        EN 1992-4 §7.4 interaction: (N/NRd)^alpha + (V/VRd)^alpha <= 1
        alpha = 1.5
        """
        if NRd_kn <= 0 or VRd_kn <= 0:
            return 999.0
        alpha = 1.5
        util = (N_Ed_kn / NRd_kn) ** alpha + (V_Ed_kn / VRd_kn) ** alpha
        return util ** (1.0 / alpha)


# ---------------------------------------------------------------------------
# 5. Shear Transfer Service
# ---------------------------------------------------------------------------

class ShearTransferService:
    """
    Validates shear and torsion transfer mechanisms.
    Rules:
    - Friction: only with guaranteed compression (non-pretensioned → no permanent friction)
    - Bolt bearing: after gap is closed
    - Shear key: verified independently
    """

    @classmethod
    def check_friction(
        cls,
        V_Ed_kn: float,
        N_compression_kn: float,
        mu: float = 0.3,
        pretensioned: bool = False,
        gamma_friction: float = 1.25,
    ) -> Tuple[float, List[str]]:
        """
        Friction resistance: VRd,f = mu * N_comp / gamma_friction
        Only valid if there is guaranteed compression.
        For non-pretensioned: friction from gravitational compression only in permanent combinations.
        """
        errors = []
        if N_compression_kn <= 0:
            errors.append("B10-E012: sin compresión garantizada - fricción no aplicable")
            return 999.0, errors
        if not pretensioned and N_compression_kn < abs(V_Ed_kn) * 0.5:
            errors.append("B10-E013: compresión insuficiente para garantizar fricción sin pretensado")

        VRd_f = mu * N_compression_kn / gamma_friction
        util = V_Ed_kn / VRd_f if VRd_f > 0 else 999.0
        return util, errors

    @classmethod
    def check_shear_key(
        cls,
        Vx_kn: float,
        Vy_kn: float,
        key_width_mm: float,
        key_height_mm: float,
        key_depth_mm: float,
        fy_mpa: float,
        fck_mpa: float,
        weld_throat_mm: float,
        plate_fy_mpa: float = 355.0,
        gamma_M0: float = 1.0,
        gamma_c: float = 1.5,
    ) -> Dict[str, float]:
        """
        Shear key: verify bending, shear, bearing in concrete.
        Modeled as cantilever embedded in concrete.
        """
        V_total = math.sqrt(Vx_kn ** 2 + Vy_kn ** 2)
        # Bending: cantilever with depth embedment
        arm_mm = key_depth_mm / 2.0
        M_Ed_knm = V_total * arm_mm / 1000.0
        Wel_mm3 = key_width_mm * key_height_mm ** 2 / 6.0
        sigma_Ed = M_Ed_knm * 1e6 / Wel_mm3 if Wel_mm3 > 0 else 0.0
        util_bending = sigma_Ed / (fy_mpa / gamma_M0)

        # Shear in key section
        A_key = key_width_mm * key_height_mm
        tau_Ed = V_total * 1000.0 / A_key if A_key > 0 else 0.0
        tau_Rd = fy_mpa / (math.sqrt(3.0) * gamma_M0)
        util_shear = tau_Ed / tau_Rd

        # Bearing on concrete (local crushing)
        sigma_concrete = V_total * 1000.0 / (key_width_mm * key_depth_mm) if key_depth_mm > 0 else 0.0
        sigma_Rd_concrete = 3.0 * fck_mpa / gamma_c  # EN 1992-1-1 §6.7
        util_concrete = sigma_concrete / sigma_Rd_concrete

        # Weld to base plate (fillet weld)
        A_weld = 2.0 * weld_throat_mm * key_height_mm  # two welds
        tau_weld = V_total * 1000.0 / A_weld if A_weld > 0 else 0.0
        fu_plate = plate_fy_mpa * 1.35  # approximate
        util_weld = tau_weld / (fu_plate / (math.sqrt(3.0) * 1.25))

        return {
            "util_bending": util_bending,
            "util_shear": util_shear,
            "util_concrete": util_concrete,
            "util_weld": util_weld,
            "governing": max(util_bending, util_shear, util_concrete, util_weld),
        }


# ---------------------------------------------------------------------------
# 6. Base Plate Optimizer (Pareto)
# ---------------------------------------------------------------------------

class BasePlateOptimizer:
    """
    Pareto optimization: cost / mass / CO₂ / risk → 5 solutions
    Labels: RECOMMENDED, MIN_COST, MIN_MASS, MIN_CO2, MIN_RISK
    """

    @staticmethod
    def is_dominated(a: OptimCandidate, b: OptimCandidate) -> bool:
        """True if b dominates a (b is better on all 4 objectives and strictly better on ≥1)."""
        obj_a = (a.total_cost_eur, a.total_mass_kg, a.total_co2_kg, a.risk_score)
        obj_b = (b.total_cost_eur, b.total_mass_kg, b.total_co2_kg, b.risk_score)
        all_leq = all(bv <= av for av, bv in zip(obj_a, obj_b))
        any_lt = any(bv < av for av, bv in zip(obj_a, obj_b))
        return all_leq and any_lt

    @classmethod
    def pareto_front(cls, candidates: List[OptimCandidate]) -> List[OptimCandidate]:
        """Return the non-dominated subset."""
        front = []
        for c in candidates:
            if not any(cls.is_dominated(c, other) for other in candidates if other is not c):
                front.append(c)
        return front

    @classmethod
    def select(
        cls,
        candidates: List[OptimCandidate],
        w_cost: float = 0.4,
        w_mass: float = 0.2,
        w_co2: float = 0.2,
        w_risk: float = 0.2,
    ) -> List[OptimCandidate]:
        """
        Return up to 5 labelled solutions from the Pareto front.
        """
        feasible = [c for c in candidates if c.util_governing <= 1.0]
        if not feasible:
            return []

        pareto = cls.pareto_front(feasible)
        if not pareto:
            pareto = feasible

        # Normalize objectives
        costs = [c.total_cost_eur for c in pareto]
        masses = [c.total_mass_kg for c in pareto]
        co2s = [c.total_co2_kg for c in pareto]
        risks = [c.risk_score for c in pareto]

        def _norm(val: float, vals: List[float]) -> float:
            mn, mx = min(vals), max(vals)
            return (val - mn) / (mx - mn + 1e-12)

        for c in pareto:
            c_n = _norm(c.total_cost_eur, costs)
            m_n = _norm(c.total_mass_kg, masses)
            co2_n = _norm(c.total_co2_kg, co2s)
            r_n = _norm(c.risk_score, risks)
            c.label = ""  # reset
            c.__dict__["_score"] = w_cost * c_n + w_mass * m_n + w_co2 * co2_n + w_risk * r_n

        pareto.sort(key=lambda c: c.__dict__["_score"])

        results = []
        recommended = pareto[0]
        recommended.label = "RECOMMENDED"
        results.append(recommended)

        def _best(key: str, label: str, attr: str) -> None:
            best = min(pareto, key=lambda c: getattr(c, attr))
            if best is not recommended:
                best.label = label
                results.append(best)

        _best("cost", "MIN_COST", "total_cost_eur")
        _best("mass", "MIN_MASS", "total_mass_kg")
        _best("co2", "MIN_CO2", "total_co2_kg")
        _best("risk", "MIN_RISK", "risk_score")

        return results


# ---------------------------------------------------------------------------
# 7. Normative Classifier
# ---------------------------------------------------------------------------

class BasePlateNormativeClassifier:
    """
    7-step applicability tree for base plate solutions.
    Returns solution family + maturity level.
    """

    @classmethod
    def classify(
        cls,
        anchor_family: str,           # EMBEDDED / POST_INSTALLED
        eta_available: bool,          # ETA document available (for post-installed)
        eta_covers_condition: bool,   # ETA covers actual concrete condition
        inside_domain: bool,          # geometry within standard pattern domain
        family_tested: bool,          # family has experimental validation
        friction_with_compression: bool,  # shear by friction only with verified compression
        concrete_family_approved: bool,   # concrete family approved by OT
        non_pretensioned: bool = True,    # default: non-pretensioned
    ) -> NormativeClassResult:
        """
        Blocking rules (any blocker → not compliant):
        B10-E014: post-installed without ETA → BLOCKED
        B10-E015: ETA doesn't cover actual concrete condition → BLOCKED
        B10-E016: friction claimed without guaranteed compression → BLOCKED
        B10-E017: concrete family not approved → BLOCKED
        """
        blockers = []
        warnings = []

        # Step 1: Post-installed without ETA
        if anchor_family == "POST_INSTALLED" and not eta_available:
            blockers.append("B10-E014: anclaje postinstalado sin ETA disponible → BLOQUEADO")

        # Step 2: ETA doesn't cover condition
        if anchor_family == "POST_INSTALLED" and eta_available and not eta_covers_condition:
            blockers.append("B10-E015: ETA no cubre condición de hormigón real → BLOQUEADO")

        # Step 3: Friction without compression
        if not friction_with_compression:
            blockers.append("B10-E016: fricción declarada sin compresión garantizada → BLOQUEADO")

        # Step 4: Concrete family not approved
        if not concrete_family_approved:
            blockers.append("B10-E017: familia de hormigón no aprobada por OT → BLOQUEADO")

        # Warnings
        if non_pretensioned:
            warnings.append("W10-001: no pretensado - no atribuir fricción permanente a apriete no garantizado")
        if not inside_domain:
            warnings.append("W10-002: fuera de dominio patrón estándar - requiere diseño especial")

        # Maturity level
        if blockers:
            maturity = "V0"
        elif family_tested and inside_domain:
            maturity = "V4"
        elif inside_domain:
            maturity = "V3"
        elif not inside_domain:
            maturity = "V2"
        else:
            maturity = "V1"

        # Solution family
        if anchor_family == "EMBEDDED":
            family = "FAM-BPL-EMB"
        elif eta_available and eta_covers_condition:
            family = "FAM-BPL-POST"
        else:
            family = "FAM-BPL-SPECIAL"

        return NormativeClassResult(
            is_compliant=len(blockers) == 0,
            blockers=blockers,
            warnings=warnings,
            solution_family=family,
            maturity_level=maturity,
        )


# ---------------------------------------------------------------------------
# Geometry hash
# ---------------------------------------------------------------------------

def compute_geometry_hash(
    plate_width_mm: float,
    plate_length_mm: float,
    plate_thickness_mm: float,
    bolt_x_mm: List[float],
    bolt_y_mm: List[float],
    embedment_depth_mm: float,
) -> str:
    """SHA-256 hash of geometric inputs for immutability tracking."""
    data = json.dumps({
        "plate": [plate_width_mm, plate_length_mm, plate_thickness_mm],
        "bolts_x": sorted(bolt_x_mm),
        "bolts_y": sorted(bolt_y_mm),
        "hef": embedment_depth_mm,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()[:32]
