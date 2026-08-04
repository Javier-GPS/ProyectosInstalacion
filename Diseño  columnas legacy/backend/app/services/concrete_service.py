"""
Salvi Studio · Columns — Servicios Fase 7: Hormigón Pretensado.

Motor determinista de cálculo. Para las mismas entradas + versión de reglas
produce siempre el mismo resultado. Ningún coeficiente inventado por IA.
"""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.models.db.concrete import (
    PrestressingSteelClass, ConcreteNormativeRoute,
    ConcreteVerificationStatus, ProductionStageCode, LimitState,
)


# ============================================================================
# Dataclasses de resultado
# ============================================================================

@dataclass
class ConcreteAgeResult:
    t_days: float
    fcm_t_mpa: float
    Ecm_t_mpa: float
    fctm_t_mpa: float
    fctk_005_t_mpa: float
    epsilon_ca_t: float
    governing_rule: str = "EN 1992-1-1 §3.1.2"


@dataclass
class ConcreteCheckResult:
    check_type: str
    status: ConcreteVerificationStatus
    solicitation: float
    resistance: float
    utilization: float
    unit: str
    governing_rule: str
    intermediate_values: dict = field(default_factory=dict)
    equation_trace: Optional[dict] = None
    error_code: Optional[str] = None


@dataclass
class AnnularProperties:
    D_ext_mm: float
    D_int_mm: float
    t_wall_mm: float
    A_m2: float
    Iy_m4: float
    Iz_m4: float
    J_m4: float
    Wel_y_m3: float
    Wpl_y_m3: float
    iy_m: float
    mass_per_m_kg: float


@dataclass
class LossResult:
    loss_type: str
    delta_P_kn: float
    delta_sigma_mpa: float
    loss_pct: float
    governing_rule: str
    intermediate_values: dict = field(default_factory=dict)


@dataclass
class MinerResult:
    total_damage: float
    individual_damages: List[float]
    status: str
    duplicate_source_detected: bool
    governing_source: Optional[str] = None
    governing_rule: str = "EC2 §6.8.4 — Miner"


@dataclass
class TransferLengthResult:
    fbpt_mpa: float
    l_pt_mm: float
    l_bpd_mm: float
    governing_rule: str = "EC2 §8.10.2"


@dataclass
class LiftingResult:
    point_positions_m: List[float]
    M_max_knm: float
    utilization_vs_Mcr: float
    compliant: bool
    governing_rule: str = "Izado — posición óptima = 0.207L"


@dataclass
class NormativeRouteResult:
    route: ConcreteNormativeRoute
    steps_passed: List[bool]
    blocking_step: Optional[int]
    decision_trace: List[str]
    input_hash: str


@dataclass
class PrestressCandidate:
    n_strands: int
    strand_diameter_mm: float
    crown_radius_mm: float
    initial_force_per_strand_kn: float
    total_cost_eur: float
    total_mass_kg: float
    total_co2_kg: float
    robustness_score: float
    feasible: bool
    transportable: bool
    pareto_dominated: Optional[bool] = None
    rejection_reason: Optional[str] = None
    governing_constraint: Optional[str] = None


# ============================================================================
# ConcreteMaterialService
# ============================================================================

class ConcreteMaterialService:
    """
    Propiedades del hormigón dependientes de la edad (EC2 §3.1.2).
    Todas las fórmulas son deterministas y referenciadas a norma.
    """

    CEMENT_S = {
        "R": 0.20,
        "N": 0.25,
        "S": 0.25,
        "SL": 0.38,
    }

    # Biblioteca mínima de mezclas homologadas para Salvi
    _LIBRARY = [
        {
            "mix_code": "HAP-45/50", "fck": 45.0, "fcm": 53.0, "fctm": 3.8,
            "Ecm": 36000.0, "s": 0.25, "cement_class": "N",
            "epsilon_ca_inf": 50.0, "rho": 2450.0, "alpha_T": 10e-6,
        },
        {
            "mix_code": "HAP-50/60", "fck": 50.0, "fcm": 58.0, "fctm": 4.1,
            "Ecm": 37000.0, "s": 0.25, "cement_class": "N",
            "epsilon_ca_inf": 55.0, "rho": 2450.0, "alpha_T": 10e-6,
        },
        {
            "mix_code": "HAP-60/75", "fck": 60.0, "fcm": 68.0, "fctm": 4.4,
            "Ecm": 39000.0, "s": 0.20, "cement_class": "R",
            "epsilon_ca_inf": 60.0, "rho": 2450.0, "alpha_T": 10e-6,
        },
    ]

    @classmethod
    def age_properties(
        cls,
        fcm_28_mpa: float,
        fctm_28_mpa: float,
        Ecm_28_mpa: float,
        s_cement: float,
        t_days: float,
        epsilon_ca_inf: float = 50.0,
    ) -> ConcreteAgeResult:
        """Propiedades del hormigón a edad t (EC2 §3.1.2 y §3.1.4)."""
        if t_days <= 0:
            raise ValueError("CON-MAT-001: edad t debe ser > 0")
        if s_cement not in (0.20, 0.25, 0.38):
            raise ValueError(f"CON-MAT-001: s_cement {s_cement} no reconocido")

        # Coeficiente de madurez βcc(t)
        beta_cc = math.exp(s_cement * (1.0 - math.sqrt(28.0 / t_days)))

        fcm_t = fcm_28_mpa * beta_cc
        Ecm_t = Ecm_28_mpa * (fcm_t / fcm_28_mpa) ** 0.3

        # fctm(t)
        if t_days < 28:
            alpha = 2.0 / 3.0
            fctm_t = fctm_28_mpa * (fcm_t / fcm_28_mpa) ** alpha
        else:
            fctm_t = fctm_28_mpa * (fcm_t / fcm_28_mpa) ** 1.0

        fctk_005_t = 0.7 * fctm_t

        # Retracción autógena EC2 §3.1.4: εca(t) = εca(∞) × (1 - exp(-0.2√t))
        epsilon_ca_t = epsilon_ca_inf * (1.0 - math.exp(-0.2 * math.sqrt(t_days)))

        return ConcreteAgeResult(
            t_days=t_days,
            fcm_t_mpa=round(fcm_t, 4),
            Ecm_t_mpa=round(Ecm_t, 2),
            fctm_t_mpa=round(fctm_t, 4),
            fctk_005_t_mpa=round(fctk_005_t, 4),
            epsilon_ca_t=round(epsilon_ca_t, 4),
        )

    @classmethod
    def resolve_mix(cls, mix_code: str) -> dict:
        """Resuelve mezcla de la biblioteca. Lanza CON-MAT-001 si no existe."""
        for rec in cls._LIBRARY:
            if rec["mix_code"] == mix_code:
                return rec
        raise ValueError(f"CON-MAT-001: mezcla '{mix_code}' no publicada en biblioteca")

    @classmethod
    def check_transfer_strength(
        cls, fcm_t_mpa: float, min_required_mpa: float
    ) -> ConcreteCheckResult:
        """Verifica que la resistencia es suficiente para la transferencia."""
        ok = fcm_t_mpa >= min_required_mpa
        util = min_required_mpa / fcm_t_mpa if fcm_t_mpa > 0 else float("inf")
        status = ConcreteVerificationStatus.PASS if ok else ConcreteVerificationStatus.BLOCKED
        return ConcreteCheckResult(
            check_type="TRANSFER_STRENGTH",
            status=status,
            solicitation=min_required_mpa,
            resistance=fcm_t_mpa,
            utilization=round(util, 4),
            unit="MPa",
            governing_rule="EC2 §5.10.2.2",
            error_code=None if ok else "CON-MAT-001",
        )


# ============================================================================
# PrestressLossService
# ============================================================================

class PrestressLossService:
    """
    Pérdidas de pretensado: instantáneas y diferidas (EC2 §5.10.4–5.10.6).
    Cada método retorna delta_P [kN], delta_sigma [MPa] y trazabilidad.
    """

    @staticmethod
    def anchor_slip_loss(
        Ap_mm2: float,
        Ep_mpa: float,
        delta_slip_mm: float,
        L_active_mm: float,
        P0_kn: float,
    ) -> LossResult:
        """
        Pérdida por asiento de anclaje.
        ΔP_slip = Ap × Ep × δ_slip / L_active
        """
        if L_active_mm <= 0:
            raise ValueError("CON-PST-002: L_active debe ser > 0")
        delta_sigma = Ep_mpa * delta_slip_mm / L_active_mm  # MPa
        delta_P = Ap_mm2 * delta_sigma / 1000.0             # kN
        loss_pct = delta_P / P0_kn * 100.0 if P0_kn > 0 else 0.0
        return LossResult(
            loss_type="ANCHOR_SLIP",
            delta_P_kn=round(delta_P, 4),
            delta_sigma_mpa=round(delta_sigma, 4),
            loss_pct=round(loss_pct, 3),
            governing_rule="EC2 §5.10.4",
            intermediate_values={"delta_slip_mm": delta_slip_mm, "L_active_mm": L_active_mm},
        )

    @staticmethod
    def elastic_shortening_loss(
        Ap_mm2: float,
        Ep_mpa: float,
        sigma_cp_mpa: float,
        Ecm_t_mpa: float,
        n_strands: int,
        P0_kn: float,
    ) -> LossResult:
        """
        Pérdida por acortamiento elástico (pretensado simultáneo por batería).
        ΔP_el = Ap × Ep × σ_cp / Ecm × (n-1)/(2n)
        Para n=1 o pretensado individual: factor = 1.0
        """
        n_ratio = (n_strands - 1) / (2 * n_strands) if n_strands > 1 else 1.0
        delta_sigma = Ep_mpa / Ecm_t_mpa * sigma_cp_mpa * n_ratio
        delta_P = Ap_mm2 * delta_sigma / 1000.0
        loss_pct = delta_P / P0_kn * 100.0 if P0_kn > 0 else 0.0
        return LossResult(
            loss_type="ELASTIC_SHORTENING",
            delta_P_kn=round(delta_P, 4),
            delta_sigma_mpa=round(delta_sigma, 4),
            loss_pct=round(loss_pct, 3),
            governing_rule="EC2 §5.10.4",
            intermediate_values={
                "n_ratio": round(n_ratio, 6),
                "Ep_over_Ecm": round(Ep_mpa / Ecm_t_mpa, 4),
                "sigma_cp_mpa": sigma_cp_mpa,
            },
        )

    @staticmethod
    def relaxation_loss(
        sigma_pi_mpa: float,
        fpk_mpa: float,
        relaxation_class: PrestressingSteelClass,
        rho1000_pct: float,
        t_hours: float,
        Ap_mm2: float,
        P0_kn: float,
    ) -> LossResult:
        """
        Relajación del acero a tiempo t (EC2 §3.3.2).
        Clase 1 (alambres): Δσ/σ = 5.39 × ρ1000 × exp(6.7μ) × (t/1000)^(0.75(1-μ)) × 10^-5
        Clase 2 (cordones): Δσ/σ = 0.66 × ρ1000 × exp(9.1μ) × (t/1000)^(0.75(1-μ)) × 10^-5
        """
        mu = sigma_pi_mpa / fpk_mpa
        rho = rho1000_pct
        t_norm = t_hours / 1000.0
        exponent = 0.75 * (1.0 - mu)

        if relaxation_class == PrestressingSteelClass.CLASS_1:
            ratio = 5.39e-5 * rho * math.exp(6.7 * mu) * (t_norm ** exponent)
        else:
            ratio = 0.66e-5 * rho * math.exp(9.1 * mu) * (t_norm ** exponent)

        delta_sigma = ratio * sigma_pi_mpa
        delta_P = Ap_mm2 * delta_sigma / 1000.0
        loss_pct = delta_P / P0_kn * 100.0 if P0_kn > 0 else 0.0

        return LossResult(
            loss_type="SHORT_TERM_RELAXATION",
            delta_P_kn=round(delta_P, 4),
            delta_sigma_mpa=round(delta_sigma, 4),
            loss_pct=round(loss_pct, 3),
            governing_rule="EC2 §3.3.2",
            intermediate_values={
                "mu": round(mu, 4),
                "t_hours": t_hours,
                "ratio": round(ratio, 8),
                "class": relaxation_class.value,
            },
        )

    @staticmethod
    def thermal_loss(
        Ap_mm2: float,
        Ep_mpa: float,
        alpha_T: float,
        delta_T_celsius: float,
        P0_kn: float,
    ) -> LossResult:
        """
        Pérdida por diferencia de temperatura acero-hormigón.
        ΔP_T = Ap × Ep × αT × ΔT
        """
        delta_sigma = Ep_mpa * alpha_T * delta_T_celsius  # MPa
        delta_P = Ap_mm2 * delta_sigma / 1000.0            # kN
        loss_pct = delta_P / P0_kn * 100.0 if P0_kn > 0 else 0.0
        return LossResult(
            loss_type="THERMAL_GRADIENT",
            delta_P_kn=round(delta_P, 4),
            delta_sigma_mpa=round(delta_sigma, 4),
            loss_pct=round(loss_pct, 3),
            governing_rule="EC2 §5.10.4",
            intermediate_values={"alpha_T": alpha_T, "delta_T": delta_T_celsius},
        )

    @staticmethod
    def long_term_loss_simplified(
        Ap_mm2: float,
        Ep_mpa: float,
        Ecm_mpa: float,
        Ac_m2: float,
        Ic_m4: float,
        e_mm: float,
        epsilon_cs: float,
        delta_sigma_pr_mpa: float,
        phi: float,
        sigma_cp_mpa: float,
        P0_kn: float,
    ) -> LossResult:
        """
        Pérdidas diferidas (retracción + fluencia + relajación) — EC2 §5.10.6.
        ΔP_c+s+r = Ap × Ep × [εcs×Ep + 0.8×Δσ_pr + (Ep/Ecm)×φ×σ_cp] /
                   [1 + (Ep/Ecm)×(Ap/Ac)×(1 + Ac×e²/Ic)×(1 + 0.8×φ)]
        """
        n = Ep_mpa / Ecm_mpa
        e_m = e_mm / 1000.0  # mm → m

        numerator = epsilon_cs * Ep_mpa + 0.8 * delta_sigma_pr_mpa + n * phi * sigma_cp_mpa
        denominator = 1.0 + n * (Ap_mm2 / 1e6) / Ac_m2 * (1.0 + Ac_m2 * e_m**2 / Ic_m4) * (1.0 + 0.8 * phi)

        delta_sigma = numerator / denominator   # MPa
        delta_P = (Ap_mm2 * delta_sigma) / 1000.0  # kN
        loss_pct = delta_P / P0_kn * 100.0 if P0_kn > 0 else 0.0

        return LossResult(
            loss_type="COMBINED_CSR",
            delta_P_kn=round(delta_P, 4),
            delta_sigma_mpa=round(delta_sigma, 4),
            loss_pct=round(loss_pct, 3),
            governing_rule="EC2 §5.10.6",
            intermediate_values={
                "numerator": round(numerator, 6),
                "denominator": round(denominator, 6),
                "n_ratio": round(n, 4),
                "phi": phi,
                "epsilon_cs": epsilon_cs,
            },
        )

    @staticmethod
    def transfer_length(
        phi_mm: float,
        sigma_pm0_mpa: float,
        sigma_pd_mpa: float,
        sigma_pm_inf_mpa: float,
        fctd_t_mpa: float,
        eta1: float = 1.0,
        eta2: float = 1.0,
        alpha1: float = 1.25,
        alpha2_transfer: float = 0.25,
        alpha2_anchor: float = 0.25,
    ) -> TransferLengthResult:
        """
        Longitudes de transferencia y anclaje (EC2 §8.10.2).
        fbpt = 2.25 × η1 × η2 × fctd(t)
        l_pt = α1 × α2 × φ × σ_pm0 / fbpt
        l_bpd = l_pt2 + α2 × φ × (σ_pd - σ_pm∞) / fbpd
        """
        fbpt = 2.25 * eta1 * eta2 * fctd_t_mpa  # resistencia de adherencia
        l_pt = alpha1 * alpha2_transfer * phi_mm * sigma_pm0_mpa / fbpt

        # Longitud de anclaje (fbpd ≈ fbpt × 1.4 conservador para ELU)
        fbpd = fbpt * 1.4
        l_pt2 = 0.8 * l_pt  # límite de dispersión inferior
        l_bpd = l_pt2 + alpha2_anchor * phi_mm * max(0.0, sigma_pd_mpa - sigma_pm_inf_mpa) / fbpd

        return TransferLengthResult(
            fbpt_mpa=round(fbpt, 4),
            l_pt_mm=round(l_pt, 2),
            l_bpd_mm=round(l_bpd, 2),
        )


# ============================================================================
# ConcreteSectionEngine
# ============================================================================

class ConcreteSectionEngine:
    """Propiedades geométricas y verificaciones de sección de hormigón."""

    @staticmethod
    def annular_properties(
        D_ext_mm: float,
        D_int_mm: float,
        rho_kg_m3: float = 2450.0,
    ) -> AnnularProperties:
        """Propiedades analíticas de la sección anular circular."""
        if D_int_mm >= D_ext_mm:
            raise ValueError("CON-SEC-001: D_int debe ser menor que D_ext")

        De = D_ext_mm / 1000.0  # m
        Di = D_int_mm / 1000.0
        t = (D_ext_mm - D_int_mm) / 2.0 / 1000.0  # espesor de pared [m]

        A = math.pi / 4.0 * (De**2 - Di**2)
        I = math.pi / 64.0 * (De**4 - Di**4)
        J = math.pi / 32.0 * (De**4 - Di**4)  # Bredt — sección cerrada
        Wel = I / (De / 2.0)
        # Módulo plástico anular (aproximación)
        Wpl = (De**3 - Di**3) / 6.0

        iy = math.sqrt(I / A) if A > 0 else 0.0
        mass_per_m = rho_kg_m3 * A

        return AnnularProperties(
            D_ext_mm=D_ext_mm,
            D_int_mm=D_int_mm,
            t_wall_mm=(D_ext_mm - D_int_mm) / 2.0,
            A_m2=round(A, 8),
            Iy_m4=round(I, 14),
            Iz_m4=round(I, 14),
            J_m4=round(J, 14),
            Wel_y_m3=round(Wel, 10),
            Wpl_y_m3=round(Wpl, 10),
            iy_m=round(iy, 6),
            mass_per_m_kg=round(mass_per_m, 4),
        )

    @staticmethod
    def stress_at_fiber(
        N_kn: float,
        My_knm: float,
        Mz_knm: float,
        A_m2: float,
        Iy_m4: float,
        Iz_m4: float,
        y_m: float,
        z_m: float,
        P_kn: float = 0.0,
        e_y_m: float = 0.0,
        e_z_m: float = 0.0,
    ) -> float:
        """
        Tensión en fibra (y, z) por N + My + Mz + pretensado.
        σ = N/A + My/Iy × z + Mz/Iz × y + P/A + P×ey/Iy×z + P×ez/Iz×y
        Positivo = compresión.
        """
        N_total = N_kn + P_kn  # [kN] (P_kn compresión si positivo)
        My_total = My_knm + P_kn * e_y_m   # [kNm]
        Mz_total = Mz_knm + P_kn * e_z_m

        sigma = (N_total * 1e3) / (A_m2 * 1e6)  # MPa (N total en N, A en mm²)
        sigma += (My_total * 1e3) / (Iy_m4 * 1e12) * z_m * 1e3   # MPa
        sigma += (Mz_total * 1e3) / (Iz_m4 * 1e12) * y_m * 1e3
        return round(sigma, 6)

    @staticmethod
    def check_stress_concrete(
        sigma_c_mpa: float,      # calculada (positivo compresión)
        fck_mpa: float,
        stage: str,
        is_tension: bool = False,
        fctm_t_mpa: Optional[float] = None,
        gamma_c: float = 1.5,
    ) -> ConcreteCheckResult:
        """Verificación de tensión en hormigón (ELS)."""
        if is_tension:
            limit = fctm_t_mpa if fctm_t_mpa else 0.0
            util = abs(sigma_c_mpa) / limit if limit > 0 else float("inf")
            ok = util <= 1.0
            rule = "EC2 §5.10.2.2 — tracción admisible"
        elif stage in ("S1", "S2"):
            limit = 0.60 * fck_mpa
            util = abs(sigma_c_mpa) / limit if limit > 0 else float("inf")
            ok = util <= 1.0
            rule = "EC2 §5.10.2.2 — compresión en transferencia ≤ 0.60fck"
        else:
            limit = 0.45 * fck_mpa
            util = abs(sigma_c_mpa) / limit if limit > 0 else float("inf")
            ok = util <= 1.0
            rule = "EC2 §7.2 — compresión en servicio ≤ 0.45fck (cuasipermanente)"

        status = ConcreteVerificationStatus.PASS if ok else ConcreteVerificationStatus.FAIL
        return ConcreteCheckResult(
            check_type="STRESS_CONCRETE",
            status=status,
            solicitation=round(abs(sigma_c_mpa), 4),
            resistance=round(limit, 4),
            utilization=round(util, 4),
            unit="MPa",
            governing_rule=rule,
            intermediate_values={"stage": stage, "is_tension": is_tension},
        )

    @staticmethod
    def check_shear(
        V_ed_kn: float,
        fck_mpa: float,
        bw_m: float,
        d_m: float,
        rho_l: float,
        N_ed_kn: float = 0.0,
        Ac_m2: float = 0.01,
        gamma_c: float = 1.5,
    ) -> ConcreteCheckResult:
        """
        Cortante sin armadura transversal — EC2 §6.2.2.
        V_Rd,c = [CRd,c × k × (100ρl×fck)^(1/3) + k1×σ_cp] × bw × d
        """
        CRd_c = 0.18 / gamma_c
        k = min(1.0 + math.sqrt(200.0 / (d_m * 1000.0)), 2.0)
        sigma_cp = N_ed_kn * 1000.0 / (Ac_m2 * 1e6)   # MPa (tensión media)
        sigma_cp = min(sigma_cp, 0.2 * fck_mpa / gamma_c)
        k1 = 0.15

        rho_l_capped = min(rho_l, 0.02)
        V_Rd_c = (CRd_c * k * (100.0 * rho_l_capped * fck_mpa) ** (1.0 / 3.0) + k1 * sigma_cp) * bw_m * d_m * 1000.0  # kN
        # Mínimo EC2 §6.2.2(1)
        v_min = 0.035 * k**1.5 * math.sqrt(fck_mpa)
        V_Rd_c_min = (v_min + k1 * sigma_cp) * bw_m * d_m * 1000.0
        V_Rd_c = max(V_Rd_c, V_Rd_c_min)

        util = V_ed_kn / V_Rd_c if V_Rd_c > 0 else float("inf")
        status = ConcreteVerificationStatus.PASS if util <= 1.0 else ConcreteVerificationStatus.FAIL
        return ConcreteCheckResult(
            check_type="SHEAR",
            status=status,
            solicitation=round(V_ed_kn, 4),
            resistance=round(V_Rd_c, 4),
            utilization=round(util, 4),
            unit="kN",
            governing_rule="EC2 §6.2.2",
            intermediate_values={
                "k": round(k, 4),
                "CRd_c": CRd_c,
                "sigma_cp_mpa": round(sigma_cp, 4),
                "V_Rd_c_min": round(V_Rd_c_min, 4),
            },
        )

    @staticmethod
    def check_torsion_bredt(
        T_ed_knm: float,
        D_ext_mm: float,
        D_int_mm: float,
        fck_mpa: float,
        gamma_c: float = 1.5,
    ) -> ConcreteCheckResult:
        """
        Torsión de sección hueca — Bredt (EC2 §6.3).
        τ_t = T / (2 × Ak × t_ef)
        """
        De = D_ext_mm / 1000.0; Di = D_int_mm / 1000.0
        A_gross = math.pi / 4.0 * De**2
        perimeter = math.pi * De

        t_ef = max((De - Di) / 2.0, A_gross / perimeter)  # EC2 §6.3.2(1)
        # Área encerrada por el eje del muro
        r_mid = (De + Di) / 4.0
        A_k = math.pi * r_mid**2

        tau_t = T_ed_knm * 1e3 / (2.0 * A_k * t_ef * 1e6)  # MPa (kNm→Nm / m²→mm²)
        # Límite de resistencia EC2: τ_Rd ≈ fck / (1.5 × sqrt(3))
        tau_Rd = fck_mpa / (gamma_c * math.sqrt(3.0))
        util = tau_t / tau_Rd if tau_Rd > 0 else float("inf")
        status = ConcreteVerificationStatus.PASS if util <= 1.0 else ConcreteVerificationStatus.FAIL
        return ConcreteCheckResult(
            check_type="TORSION",
            status=status,
            solicitation=round(tau_t, 4),
            resistance=round(tau_Rd, 4),
            utilization=round(util, 4),
            unit="MPa",
            governing_rule="EC2 §6.3 — Bredt",
            intermediate_values={
                "A_k_m2": round(A_k, 6),
                "t_ef_m": round(t_ef, 4),
            },
        )

    @staticmethod
    def compute_run_hash(
        geometry_hash: str,
        material_hash: str,
        layout_hash: str,
        rules_hash: str,
        engine_version: str = "1.0",
    ) -> str:
        payload = {"g": geometry_hash, "m": material_hash, "l": layout_hash,
                   "r": rules_hash, "v": engine_version}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# ============================================================================
# ConcreteVerificationService
# ============================================================================

class ConcreteVerificationService:
    """Verificación de estados límite de servicio y último."""

    @staticmethod
    def check_decompression(
        sigma_min_mpa: float,
    ) -> ConcreteCheckResult:
        """
        Descompresión: la tensión mínima en toda la sección debe ser ≥ 0.
        Aplica a exposición marina y clases XS, XD.
        """
        ok = sigma_min_mpa >= 0.0
        status = ConcreteVerificationStatus.PASS if ok else ConcreteVerificationStatus.FAIL
        return ConcreteCheckResult(
            check_type="DECOMPRESSION",
            status=status,
            solicitation=round(sigma_min_mpa, 4),
            resistance=0.0,
            utilization=round(-sigma_min_mpa / abs(sigma_min_mpa + 1e-9), 4) if not ok else 0.0,
            unit="MPa",
            governing_rule="EC2 §7.3.1 — descompresión en sección",
        )

    @staticmethod
    def check_crack_width(
        sigma_s_mpa: float,
        Es_mpa: float,
        fctm_mpa: float,
        cover_c_mm: float,
        phi_bar_mm: float,
        rho_eff: float,
        wk_limit_mm: float = 0.2,
        xi1: float = 0.5,
        k3: float = 3.4,
        k4: float = 0.425,
    ) -> ConcreteCheckResult:
        """
        Ancho de fisura EC2 §7.3.4.
        wk = sr_max × (εsm - εcm)
        """
        # Espaciado de fisuras
        sr_max_mm = k3 * cover_c_mm + k4 * phi_bar_mm / (rho_eff * xi1)

        # Diferencia de deformaciones (EC2 ec. 7.9)
        kt = 0.4  # carga larga duración
        eps_sm_minus_eps_cm = (sigma_s_mpa - kt * fctm_mpa / rho_eff * (1.0 + Es_mpa / 200000.0 * rho_eff)) / Es_mpa
        eps_sm_minus_eps_cm = max(eps_sm_minus_eps_cm, 0.6 * sigma_s_mpa / Es_mpa)

        wk_mm = sr_max_mm * eps_sm_minus_eps_cm
        util = wk_mm / wk_limit_mm if wk_limit_mm > 0 else float("inf")
        status = ConcreteVerificationStatus.PASS if util <= 1.0 else ConcreteVerificationStatus.FAIL
        return ConcreteCheckResult(
            check_type="CRACKING",
            status=status,
            solicitation=round(wk_mm, 6),
            resistance=wk_limit_mm,
            utilization=round(util, 4),
            unit="mm",
            governing_rule="EC2 §7.3.4",
            intermediate_values={
                "sr_max_mm": round(sr_max_mm, 4),
                "eps_sm_eps_cm": round(eps_sm_minus_eps_cm, 8),
            },
        )


# ============================================================================
# ConcreteFatigueService
# ============================================================================

class ConcreteFatigueService:
    """Fatiga de cordones, armadura pasiva y hormigón."""

    @staticmethod
    def strand_fatigue_check(
        delta_sigma_p_mpa: float,
        fatigue_category_mpa: float = 150.0,
        gamma_s_fat: float = 1.15,
        gamma_ff: float = 1.0,
    ) -> ConcreteCheckResult:
        """
        Fatiga simplificada del cordón.
        Demanda = γ_Ff × Δσ_p
        Capacidad = ΔσRsk / γS,fat
        """
        demand = gamma_ff * delta_sigma_p_mpa
        capacity = fatigue_category_mpa / gamma_s_fat
        util = demand / capacity if capacity > 0 else float("inf")
        status = ConcreteVerificationStatus.PASS if util <= 1.0 else ConcreteVerificationStatus.FAIL
        return ConcreteCheckResult(
            check_type="FATIGUE_STRAND",
            status=status,
            solicitation=round(demand, 4),
            resistance=round(capacity, 4),
            utilization=round(util, 4),
            unit="MPa",
            governing_rule="EC2 §6.8.4",
        )

    @staticmethod
    def miner_damage(
        blocks: List[dict],
        D_limit: float = 1.0,
    ) -> MinerResult:
        """
        Daño acumulado Palmgren-Miner: D = Σ(ni/Ni) ≤ D_limit.
        blocks: [{delta_sigma_mpa, n_cycles, N_ref, source}]
        """
        sources = [b.get("source", "") for b in blocks]
        duplicate_detected = len(sources) != len(set(sources))
        governing_source = None

        damages = []
        for b in blocks:
            n = b.get("n_cycles", 0)
            N = b.get("N_ref", 1)
            d = n / N if N > 0 else float("inf")
            damages.append(d)

        total = sum(damages)
        if damages:
            idx_max = damages.index(max(damages))
            governing_source = blocks[idx_max].get("source")

        status = "PASS" if total <= D_limit else "FAIL"
        return MinerResult(
            total_damage=round(total, 6),
            individual_damages=[round(d, 6) for d in damages],
            status=status,
            duplicate_source_detected=duplicate_detected,
            governing_source=governing_source,
        )


# ============================================================================
# ConcreteProductionService
# ============================================================================

class ConcreteProductionService:
    """Validaciones de fabricación, izado y transporte."""

    MAX_PIECE_LENGTH_M = 12.0   # límite general de transporte
    MIN_DIAMETER_MM = 150.0     # diámetro mínimo exterior

    @staticmethod
    def check_lifting_positions(
        L_m: float,
        n_points: int,
        Mcr_knm: float,
        w_kn_per_m: float,
        safety_factor: float = 0.85,
    ) -> LiftingResult:
        """
        Posición óptima de puntos de izado.
        Para 2 puntos: x = 0.207 × L desde extremos.
        Momento máximo: M = w × (0.207L)² / 2
        """
        if n_points == 2:
            x_opt = 0.207 * L_m
            M_max = w_kn_per_m * x_opt**2 / 2.0
            positions = [x_opt, L_m - x_opt]
        elif n_points == 3:
            x1 = 0.1464 * L_m
            x3 = L_m - x1
            M_max = w_kn_per_m * x1**2 / 2.0
            positions = [x1, L_m / 2.0, x3]
        else:
            x_opt = L_m / (n_points + 1)
            M_max = w_kn_per_m * x_opt**2 / 2.0
            positions = [x_opt * (i + 1) for i in range(n_points)]

        util = M_max / (safety_factor * Mcr_knm) if Mcr_knm > 0 else float("inf")
        compliant = util <= 1.0
        return LiftingResult(
            point_positions_m=[round(p, 3) for p in positions],
            M_max_knm=round(M_max, 4),
            utilization_vs_Mcr=round(util, 4),
            compliant=compliant,
        )

    @staticmethod
    def check_strand_clearance(
        strand_r_mm: float,
        strand_phi_mm: float,
        insert_r_mm: float,
        insert_phi_mm: float,
        insert_theta_deg: float,
        strand_theta_deg: float,
        D_ext_mm: float,
        min_clearance_mm: float = 25.0,
    ) -> ConcreteCheckResult:
        """
        Verificación de distancia mínima cordón-inserto.
        Calcula distancia en plano de la sección.
        """
        # Posición cartesiana
        theta_s = math.radians(strand_theta_deg)
        theta_i = math.radians(insert_theta_deg)
        xs = strand_r_mm * math.cos(theta_s)
        ys = strand_r_mm * math.sin(theta_s)
        xi = insert_r_mm * math.cos(theta_i)
        yi = insert_r_mm * math.sin(theta_i)

        dist = math.sqrt((xs - xi)**2 + (ys - yi)**2)
        clear = dist - (strand_phi_mm / 2.0) - (insert_phi_mm / 2.0)

        ok = clear >= min_clearance_mm
        util = min_clearance_mm / clear if clear > 0 else float("inf")
        status = ConcreteVerificationStatus.PASS if ok else ConcreteVerificationStatus.BLOCKED
        return ConcreteCheckResult(
            check_type="STRAND_CLEARANCE",
            status=status,
            solicitation=round(clear, 4),
            resistance=min_clearance_mm,
            utilization=round(util, 4),
            unit="mm",
            governing_rule="EN 40-4 — distancia mínima cordón-inserto",
            error_code=None if ok else "CON-FAB-001",
        )

    @staticmethod
    def check_piece_length(L_m: float, max_L: float = 12.0) -> ConcreteCheckResult:
        ok = L_m <= max_L
        util = L_m / max_L if max_L > 0 else float("inf")
        status = ConcreteVerificationStatus.PASS if ok else ConcreteVerificationStatus.BLOCKED
        return ConcreteCheckResult(
            check_type="PIECE_LENGTH",
            status=status,
            solicitation=round(L_m, 3),
            resistance=max_L,
            utilization=round(util, 4),
            unit="m",
            governing_rule="EN 40 — longitud máxima de transporte estándar",
            error_code=None if ok else "CON-FAB-001",
        )

    @staticmethod
    def check_spin_within_window(
        rpm: float,
        min_rpm: float,
        max_rpm: float,
    ) -> ConcreteCheckResult:
        """Verifica que la velocidad de centrifugado está dentro de ventana aprobada."""
        ok = min_rpm <= rpm <= max_rpm
        if max_rpm == min_rpm:
            util = 1.0 if ok else float("inf")
        else:
            util = max(
                abs(rpm - min_rpm) / (max_rpm - min_rpm),
                0.0
            ) if ok else float("inf")
        status = ConcreteVerificationStatus.PASS if ok else ConcreteVerificationStatus.BLOCKED
        return ConcreteCheckResult(
            check_type="SPIN_WINDOW",
            status=status,
            solicitation=rpm,
            resistance=max_rpm,
            utilization=round(util, 4),
            unit="rpm",
            governing_rule="Proceso centrifugado — ventana aprobada",
            error_code=None if ok else "CON-FAB-003",
        )

    @staticmethod
    def bom_mass(
        concrete_volume_m3: float,
        strand_mass_kg: float,
        passive_steel_mass_kg: float,
        inserts_mass_kg: float,
        rho_concrete_kg_m3: float = 2450.0,
    ) -> dict:
        concrete_mass = rho_concrete_kg_m3 * concrete_volume_m3
        total = concrete_mass + strand_mass_kg + passive_steel_mass_kg + inserts_mass_kg
        return {
            "concrete_mass_kg": round(concrete_mass, 2),
            "strand_mass_kg": round(strand_mass_kg, 2),
            "passive_steel_mass_kg": round(passive_steel_mass_kg, 2),
            "inserts_mass_kg": round(inserts_mass_kg, 2),
            "total_mass_kg": round(total, 2),
        }


# ============================================================================
# ConcreteNormativeClassifier
# ============================================================================

class ConcreteNormativeClassifier:
    """Clasificador normativo de 7 pasos — BLOCKING si falla alguno."""

    CLASSIFIER_VERSION = "1.0"

    @staticmethod
    def classify(
        height_m: float,
        has_catenary_cables: bool,
        mix_in_library: bool,
        steel_in_library: bool,
        domain_ok: bool,
        checks_defined: bool,
        evidence_ok: bool,
    ) -> NormativeRouteResult:
        steps = []
        trace = []

        # Paso 1: normativa aplicable (asumimos siempre válida si llega aquí)
        steps.append(True)
        trace.append("Paso 1: Normativa EN40/EC2 aplicable")

        # Paso 2: altura y tipología
        ok2 = height_m <= 30.0 and not (has_catenary_cables and height_m > 20.0)
        steps.append(ok2)
        trace.append(f"Paso 2: Altura {height_m}m ≤ 30m: {'OK' if ok2 else 'FAIL'}")

        # Paso 3: materiales en biblioteca
        ok3 = mix_in_library and steel_in_library
        steps.append(ok3)
        trace.append(f"Paso 3: Materiales en biblioteca: {'OK' if ok3 else 'BLOQUEADO'}")

        # Paso 4: dominio de ecuaciones
        steps.append(domain_ok)
        trace.append(f"Paso 4: Dominio normativo: {'OK' if domain_ok else 'BLOQUEADO'}")

        # Paso 5: comprobaciones definidas
        steps.append(checks_defined)
        trace.append(f"Paso 5: Comprobaciones definidas: {'OK' if checks_defined else 'BLOQUEADO'}")

        # Paso 6: reglas disponibles (same as checks_defined en esta implementación)
        steps.append(checks_defined)
        trace.append(f"Paso 6: Reglas disponibles: {'OK' if checks_defined else 'BLOQUEADO'}")

        # Paso 7: evidencias
        steps.append(evidence_ok)
        trace.append(f"Paso 7: Evidencias: {'OK' if evidence_ok else 'BLOQUEADO'}")

        # Hash determinista
        payload = {
            "height_m": height_m, "cables": has_catenary_cables,
            "mix": mix_in_library, "steel": steel_in_library,
            "domain": domain_ok, "checks": checks_defined,
            "evidence": evidence_ok, "v": ConcreteNormativeClassifier.CLASSIFIER_VERSION,
        }
        input_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

        # Ruta
        blocking_step = None
        for i, ok in enumerate(steps):
            if not ok:
                blocking_step = i + 1
                break

        if blocking_step is not None:
            route = ConcreteNormativeRoute.BLOCKED
        elif has_catenary_cables:
            route = ConcreteNormativeRoute.SPECIAL
        elif height_m > 20.0:
            route = ConcreteNormativeRoute.EN40_EC2
        else:
            route = ConcreteNormativeRoute.EN40_EC2  # siempre usa EC2 para hormigón

        return NormativeRouteResult(
            route=route,
            steps_passed=steps,
            blocking_step=blocking_step,
            decision_trace=trace,
            input_hash=input_hash,
        )


# ============================================================================
# ConcreteOptimizer
# ============================================================================

class ConcreteOptimizer:
    """Optimización multiobjetivo Pareto del pretensado."""

    @staticmethod
    def is_dominated(a: PrestressCandidate, b: PrestressCandidate) -> bool:
        """Retorna True si b domina a (b mejor o igual en todo, estrictamente mejor en algo)."""
        if not (a.feasible and a.transportable):
            return True   # no-factible siempre dominado
        if not (b.feasible and b.transportable):
            return False  # b no apto → no puede dominar
        dominated = (
            b.total_cost_eur <= a.total_cost_eur and
            b.total_mass_kg <= a.total_mass_kg and
            b.total_co2_kg <= a.total_co2_kg and
            (
                b.total_cost_eur < a.total_cost_eur or
                b.total_mass_kg < a.total_mass_kg or
                b.total_co2_kg < a.total_co2_kg
            )
        )
        return dominated

    @classmethod
    def build_pareto_front(cls, candidates: List[PrestressCandidate]) -> List[PrestressCandidate]:
        """Construye el frente de Pareto. Solo candidatos factibles y transportables."""
        eligible = [c for c in candidates if c.feasible and c.transportable]
        pareto = []
        for c in eligible:
            dominated = any(cls.is_dominated(c, other) for other in eligible if other is not c)
            if not dominated:
                pareto.append(c)
        return pareto

    @classmethod
    def select_solutions(cls, pareto: List[PrestressCandidate]) -> dict:
        """Selecciona 4 soluciones del frente de Pareto."""
        if not pareto:
            return {"min_cost": None, "min_weight": None, "min_co2": None, "balanced": None}
        min_cost = min(pareto, key=lambda c: c.total_cost_eur)
        min_weight = min(pareto, key=lambda c: c.total_mass_kg)
        min_co2 = min(pareto, key=lambda c: c.total_co2_kg)

        # Solución equilibrada: mínima distancia normalizada al ideal
        max_c = max(c.total_cost_eur for c in pareto) or 1.0
        max_w = max(c.total_mass_kg for c in pareto) or 1.0
        max_co2 = max(c.total_co2_kg for c in pareto) or 1.0
        min_c_v = min(c.total_cost_eur for c in pareto)
        min_w_v = min(c.total_mass_kg for c in pareto)
        min_co2_v = min(c.total_co2_kg for c in pareto)

        balanced = min(
            pareto,
            key=lambda c: (
                ((c.total_cost_eur - min_c_v) / (max_c - min_c_v + 1e-12))**2 +
                ((c.total_mass_kg - min_w_v) / (max_w - min_w_v + 1e-12))**2 +
                ((c.total_co2_kg - min_co2_v) / (max_co2 - min_co2_v + 1e-12))**2
            )
        )
        return {
            "min_cost": min_cost,
            "min_weight": min_weight,
            "min_co2": min_co2,
            "balanced": balanced,
        }
