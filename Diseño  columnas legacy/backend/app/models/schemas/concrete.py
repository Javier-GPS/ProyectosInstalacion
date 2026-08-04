"""
Salvi Studio · Columns — Schemas Pydantic Fase 7: Hormigón Pretensado.
"""
from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field, model_validator, field_validator
from uuid import UUID

from app.models.db.concrete import (
    ConcreteCementClass, ConcreteExposureClass, PrestressingSteelClass,
    PrestressingElementType, PrestressLossType, ProductionStageCode,
    LimitState, ConcreteVerificationStatus, ConcreteNormativeRoute,
    ConcreteDesignStatus, InsertType, SpinCurveStatus,
    ConcreteMaterialStatus, ConcreteReportType,
)


# ============================================================================
# Materiales
# ============================================================================

class ConcreteMixCreate(BaseModel):
    mix_code: str
    version: int = 1
    fck_mpa: float = Field(gt=0)
    fcm_mpa: float = Field(gt=0)
    fctm_mpa: float = Field(gt=0)
    Ecm_mpa: float = Field(gt=0)
    s_cement: float = Field(gt=0, le=1)
    cement_class: ConcreteCementClass
    epsilon_ca_inf: Optional[float] = None
    epsilon_cd_0: Optional[float] = None
    phi_ref: Optional[float] = None
    rho_kg_m3: float = 2450.0
    alpha_T: float = 10.0e-6
    poisson: float = 0.2
    exposure_classes: Optional[List[str]] = None
    design_life_years: Optional[float] = None
    max_wk_mm: Optional[float] = None
    process_domain: Optional[dict] = None
    min_transfer_strength_mpa: Optional[float] = None
    curing_regime: Optional[str] = None
    status: ConcreteMaterialStatus = ConcreteMaterialStatus.DRAFT
    provenance: Optional[str] = None

    @model_validator(mode="after")
    def check_fcm_gt_fck(self) -> "ConcreteMixCreate":
        if self.fcm_mpa <= self.fck_mpa:
            raise ValueError("fcm debe ser mayor que fck")
        return self


class ConcreteAgePropertiesRequest(BaseModel):
    """Solicitud de propiedades del hormigón a edad t."""
    mix_version_id: Optional[UUID] = None
    fck_mpa: Optional[float] = None       # o desde biblioteca
    fcm_mpa: Optional[float] = None
    fctm_mpa: Optional[float] = None
    Ecm_mpa: Optional[float] = None
    s_cement: float = 0.25
    t_days: float = Field(gt=0)           # edad en días


class ConcreteAgePropertiesResponse(BaseModel):
    t_days: float
    fcm_t_mpa: float
    Ecm_t_mpa: float
    fctm_t_mpa: float
    fctk_005_t_mpa: float
    epsilon_ca_t: Optional[float] = None  # retracción autógena hasta edad t
    governing_rule: str = "EN 1992-1-1 §3.1.2"


class PrestressingSteelCreate(BaseModel):
    steel_code: str
    version: int = 1
    element_type: PrestressingElementType
    relaxation_class: PrestressingSteelClass
    fpk_mpa: float = Field(gt=0)
    fp01k_mpa: float = Field(gt=0)
    Ep_mpa: float = 195000.0
    elongation_pct: Optional[float] = None
    rho1000_pct: float = Field(gt=0)
    phi_mm: float = Field(gt=0)
    area_mm2: float = Field(gt=0)
    mass_per_m_kg: float = Field(gt=0)
    alpha1: float = 1.25
    alpha2: float = 0.25
    eta1: float = 1.0
    eta2: float = 1.0
    sigma_max_jack_ratio: float = 0.80
    sigma_max_jack_ratio2: float = 0.90
    sigma_after_transfer_ratio: float = 0.75

    @model_validator(mode="after")
    def check_fp01k_lt_fpk(self) -> "PrestressingSteelCreate":
        if self.fp01k_mpa >= self.fpk_mpa:
            raise ValueError("fp01k debe ser menor que fpk")
        return self


# ============================================================================
# Pretensado y pérdidas
# ============================================================================

class PrestressInitialCheck(BaseModel):
    """Verificación de tensión inicial de tesado."""
    sigma_pi_mpa: float
    fpk_mpa: float
    fp01k_mpa: float
    sigma_max_jack_ratio: float = 0.80
    sigma_max_jack_ratio2: float = 0.90


class PrestressInitialCheckResult(BaseModel):
    sigma_pi_mpa: float
    limit_mpa: float
    utilization: float
    status: ConcreteVerificationStatus
    governing_rule: str
    error_code: Optional[str] = None


class AnchorSlipLossRequest(BaseModel):
    """Pérdida por asiento de anclaje."""
    Ap_mm2: float = Field(gt=0)
    Ep_mpa: float = 195000.0
    delta_slip_mm: float = Field(ge=0)
    L_active_mm: float = Field(gt=0)


class AnchorSlipLossResult(BaseModel):
    delta_P_kn: float
    delta_sigma_mpa: float
    loss_pct: float
    governing_rule: str = "EC2 §5.10.4"


class ElasticShorteningLossRequest(BaseModel):
    """Pérdida por acortamiento elástico."""
    Ap_mm2: float = Field(gt=0)
    Ep_mpa: float = 195000.0
    sigma_cp_mpa: float              # tensión en el CG de los cordones por pretensado transferido
    Ecm_t_mpa: float = Field(gt=0)  # módulo a la edad de transferencia
    n_strands: int = Field(ge=1)    # número de cordones simultáneos


class ElasticShorteningLossResult(BaseModel):
    delta_P_per_strand_kn: float
    delta_sigma_mpa: float
    n_ratio: float                   # (n-1)/(2n)
    loss_pct: float
    governing_rule: str = "EC2 §5.10.4"


class RelaxationLossRequest(BaseModel):
    """Relajación del acero de pretensado."""
    sigma_pi_mpa: float
    fpk_mpa: float
    relaxation_class: PrestressingSteelClass
    rho1000_pct: float               # relajación a 1000h [%]
    t_hours: float = Field(gt=0)     # tiempo hasta transferencia


class RelaxationLossResult(BaseModel):
    mu: float                        # σ_pi / fpk
    delta_sigma_pr_mpa: float        # pérdida absoluta
    delta_sigma_pr_ratio: float      # δσ/σ_pi
    governing_rule: str = "EC2 §3.3.2"


class LongTermLossRequest(BaseModel):
    """Pérdidas diferidas por retracción-fluencia-relajación (EC2 §5.10.6 simplificado)."""
    Ap_mm2: float = Field(gt=0)
    Ep_mpa: float = 195000.0
    Ecm_mpa: float = Field(gt=0)
    Ac_m2: float = Field(gt=0)
    Ic_m4: float = Field(gt=0)
    e_mm: float                      # excentricidad del pretensado [mm]

    epsilon_cs: float                # retracción total (autógena + secado)
    delta_sigma_pr_mpa: float        # relajación del acero bajo tensión variable
    phi: float                       # coeficiente de fluencia φ(t,t0)
    sigma_cp_mpa: float              # tensión media en el pretensado (hormigón)


class LongTermLossResult(BaseModel):
    delta_P_kn: float
    delta_sigma_mpa: float
    loss_pct: float
    numerator: float                 # trazabilidad
    denominator: float
    governing_rule: str = "EC2 §5.10.6"


class TransferLengthRequest(BaseModel):
    """Longitud de transferencia y anclaje."""
    phi_mm: float = Field(gt=0)
    sigma_pm0_mpa: float             # tensión tras pérdidas instantáneas
    sigma_pd_mpa: float              # tensión de diseño ELU
    sigma_pm_inf_mpa: float          # tensión efectiva final
    fctd_t_mpa: float                # resistencia diseño tracción en transferencia
    eta1: float = 1.0
    eta2: float = 1.0
    alpha1: float = 1.25             # tipo de corte (1.0 gradual, 1.25 brusco)
    alpha2_transfer: float = 0.25   # tipo elemento (0.25 cordones, 0.5 alambres)
    alpha2_anchor: float = 0.25


class TransferLengthResult(BaseModel):
    fbpt_mpa: float                  # resistencia de adherencia en transferencia
    l_pt_mm: float                   # longitud de transferencia
    l_bpd_mm: float                  # longitud de anclaje ELU
    governing_rule: str = "EC2 §8.10.2"


# ============================================================================
# Secciones y fibras
# ============================================================================

class AnnularSectionRequest(BaseModel):
    D_ext_mm: float = Field(gt=0)
    D_int_mm: float = Field(gt=0)
    rho_kg_m3: float = 2450.0

    @model_validator(mode="after")
    def check_diameters(self) -> "AnnularSectionRequest":
        if self.D_int_mm >= self.D_ext_mm:
            raise ValueError("D_int debe ser menor que D_ext")
        return self


class AnnularSectionProperties(BaseModel):
    D_ext_mm: float
    D_int_mm: float
    t_wall_mm: float
    A_m2: float
    Iy_m4: float
    Iz_m4: float
    J_m4: float
    Wel_y_m3: float
    Wpl_y_m3: float
    iy_m: float                      # radio de giro
    mass_per_m_kg: float
    governing_rule: str = "Geometría anular — analítica"


class TransformedSectionRequest(BaseModel):
    """Sección transformada incluyendo cordones y armadura pasiva."""
    D_ext_mm: float
    D_int_mm: float
    Ecm_mpa: float = Field(gt=0)
    strands: List[dict]              # [{r_mm, theta_deg, Ap_mm2, Ep_mpa}]
    passive_bars: Optional[List[dict]] = None  # [{r_mm, theta_deg, As_mm2, Es_mpa}]


class TransformedSectionResult(BaseModel):
    A_tr_m2: float
    Iy_tr_m4: float
    yG_tr_m: float                   # desviación del centroide transformado
    e_prestress_mm: float            # excentricidad resultante del pretensado
    n_ratio: float                   # Ep/Ecm


class FiberEquilibriumRequest(BaseModel):
    """Verificación de equilibrio por fibras N-My-Mz."""
    D_ext_mm: float
    D_int_mm: float
    n_fibers_ring: int = 32         # discretización angular
    n_fibers_radial: int = 4        # capas radiales
    strands: List[dict]             # [{r_mm, theta_deg, Ap_mm2, Ep_mpa, eps_p0}]
    passive_bars: Optional[List[dict]] = None
    fck_mpa: float = Field(gt=0)
    limit_state: str = "ULS"        # ULS o SLS
    # Esfuerzos solicitantes
    N_ed_kn: float = 0.0
    My_ed_knm: float
    Mz_ed_knm: float = 0.0


class FiberEquilibriumResult(BaseModel):
    converged: bool
    n_iterations: int
    neutral_axis_depth_mm: Optional[float] = None
    max_concrete_strain: Optional[float] = None
    max_steel_strain: Optional[float] = None
    utilization: float
    status: ConcreteVerificationStatus
    governing_rule: str = "EC2 §6.1 + modelo fibras"
    error_code: Optional[str] = None


class InteractionDiagramRequest(BaseModel):
    """Puntos del diagrama de interacción N-M."""
    D_ext_mm: float
    D_int_mm: float
    fck_mpa: float
    strands: List[dict]
    passive_bars: Optional[List[dict]] = None
    n_points: int = 36              # puntos del diagrama


class InteractionDiagramResult(BaseModel):
    points_N_kn: List[float]
    points_My_knm: List[float]
    point_solicitation_N_kn: Optional[float] = None
    point_solicitation_My_knm: Optional[float] = None
    solicitation_inside: Optional[bool] = None
    utilization: Optional[float] = None
    governing_rule: str = "EC2 §6.1 — diagrama N-M"


# ============================================================================
# ELS
# ============================================================================

class ConcreteStressCheckRequest(BaseModel):
    """Verificación de tensión en hormigón."""
    sigma_c_mpa: float               # tensión calculada (positivo compresión)
    fck_mpa: float
    stage: ProductionStageCode
    limit_ratio_compression: float = 0.60  # × fck en transferencia
    limit_ratio_service: float = 0.45       # × fck en servicio (cuasiperm.)


class ConcreteStressCheckResult(BaseModel):
    sigma_c_mpa: float
    limit_mpa: float
    utilization: float
    status: ConcreteVerificationStatus
    governing_rule: str


class CrackWidthRequest(BaseModel):
    """Ancho de fisura EC2 §7.3.4."""
    sigma_s_mpa: float               # tensión de acero en estado fisurado
    Es_mpa: float = 200000.0
    fctm_mpa: float
    cover_c_mm: float
    phi_bar_mm: float
    rho_eff: float                   # armadura eficaz en zona traccionada
    xi1: float = 0.5                 # coeficiente de adherencia cordón (EC2)
    k3: float = 3.4
    k4: float = 0.425


class CrackWidthResult(BaseModel):
    sr_max_mm: float                 # espaciado máximo de fisuras
    eps_sm_minus_eps_cm: float       # diferencia de deformaciones
    wk_mm: float                     # ancho de fisura calculado
    limit_wk_mm: float
    utilization: float
    status: ConcreteVerificationStatus
    governing_rule: str = "EC2 §7.3.4"


class DeflectionRequest(BaseModel):
    """Flecha por pretensado y peso propio."""
    P_eff_kn: float                  # pretensado efectivo
    e_mm: float                      # excentricidad
    EI_kNm2: float                   # rigidez EI en el estado considerado
    L_m: float = Field(gt=0)
    w_kn_per_m: float                # carga distribuida (positivo hacia abajo)
    support_type: str = "CANTILEVER" # CANTILEVER o SIMPLY_SUPPORTED


class DeflectionResult(BaseModel):
    camber_mm: float                 # contraflecha por pretensado (↑)
    deflection_w_mm: float           # flecha por carga (↓)
    net_deflection_mm: float         # resultante
    governing_rule: str


# ============================================================================
# ELU y cortante
# ============================================================================

class ShearCheckRequest(BaseModel):
    """Cortante sin armadura transversal — EC2 §6.2.2."""
    V_ed_kn: float
    fck_mpa: float
    bw_m: float                      # ancho eficaz de alma (perimetro de la pared)
    d_m: float                       # canto útil
    rho_l: float                     # cuantía de armadura longitudinal traccionada
    N_ed_kn: float = 0.0             # axil (positivo compresión)
    Ac_m2: float = Field(gt=0)
    gamma_c: float = 1.5


class ShearCheckResult(BaseModel):
    V_Rd_c_kn: float
    V_ed_kn: float
    utilization: float
    k_factor: float
    sigma_cp_mpa: float
    status: ConcreteVerificationStatus
    governing_rule: str = "EC2 §6.2.2"


class TorsionBredt(BaseModel):
    """Torsión de sección hueca — Bredt."""
    T_ed_knm: float
    D_ext_mm: float
    D_int_mm: float
    fck_mpa: float
    gamma_c: float = 1.5


class TorsionBredtResult(BaseModel):
    A_k_m2: float                    # área encerrada por el eje del muro
    t_ef_m: float                    # espesor eficaz
    tau_t_mpa: float                 # tensión tangencial por torsión
    utilization: float
    status: ConcreteVerificationStatus
    governing_rule: str = "EC2 §6.3 — Bredt"


# ============================================================================
# Fatiga
# ============================================================================

class StrandFatigueRequest(BaseModel):
    """Fatiga del cordón adherente."""
    delta_sigma_p_mpa: float         # rango de tensión en el cordón
    sigma_max_p_mpa: float           # tensión máxima
    fpk_mpa: float
    n_cycles: float                  # número de ciclos
    fatigue_category_mpa: float = 150.0  # ΔσRsk (cordón EC2 §6.8.4)
    gamma_s_fat: float = 1.15


class StrandFatigueResult(BaseModel):
    demand_mpa: float                # Δσ_p
    capacity_mpa: float              # ΔσRsk / γS,fat
    utilization: float
    status: ConcreteVerificationStatus
    governing_rule: str = "EC2 §6.8.4"


class MinerDamageRequest(BaseModel):
    """Daño acumulado Palmgren-Miner."""
    blocks: List[dict]               # [{delta_sigma, n_cycles, N_ref, source}]
    D_limit: float = 1.0


class MinerDamageResult(BaseModel):
    total_damage: float
    individual_damages: List[float]
    status: str
    governing_source: Optional[str] = None
    governing_rule: str = "EC2 §6.8.4 — Miner"


# ============================================================================
# Fabricación
# ============================================================================

class StrandClearanceRequest(BaseModel):
    """Verificación de interferencia cordón-inserto."""
    strand_positions: List[dict]     # [{r_mm, theta_deg, phi_mm}]
    insert_positions: List[dict]     # [{station_m, r_mm, theta_deg, insert_phi_mm}]
    min_clearance_mm: float = 25.0


class StrandClearanceResult(BaseModel):
    all_ok: bool
    conflicts: List[dict]
    error_code: Optional[str] = None  # CON-FAB-001 si hay interferencia


class LiftingPointsRequest(BaseModel):
    """Cálculo de posición óptima de puntos de izado."""
    L_m: float = Field(gt=0)
    n_points: int = 2               # 2 o 3 puntos
    w_kn_per_m: float               # peso propio
    P_eff_kn: float                 # pretensado efectivo
    EI_kNm2: float
    Mcr_knm: float                  # momento de fisuración


class LiftingPointsResult(BaseModel):
    point_positions_m: List[float]   # posiciones desde base
    M_max_knm: float                 # momento máximo en izado
    utilization_vs_Mcr: float
    compliant: bool
    governing_rule: str


class SpinCurveValidation(BaseModel):
    """Validación de curva de centrifugado."""
    spin_stages: List[dict]         # [{rpm, duration_s, accel_rpm_per_s}]
    max_approved_rpm: float
    min_approved_rpm: float = 0.0


class SpinCurveResult(BaseModel):
    within_window: bool
    violations: List[dict]
    spin_status: SpinCurveStatus
    error_code: Optional[str] = None  # CON-FAB-003


class TransportCheckRequest(BaseModel):
    """Verificación de aceleraciones de transporte."""
    mass_kg: float
    a_lateral_g: float = 0.3        # aceleración lateral [g]
    a_vertical_g: float = 0.5       # aceleración vertical [g]
    support_positions_m: List[float]
    L_m: float
    w_kn_per_m: float
    EI_kNm2: float


class TransportCheckResult(BaseModel):
    F_lateral_kn: float
    F_vertical_kn: float
    M_max_transport_knm: float
    compliant: bool
    governing_rule: str


# ============================================================================
# Optimización
# ============================================================================

class PrestressOptimizationRequest(BaseModel):
    revision_id: Optional[UUID] = None
    objectives: List[str] = ["MIN_COST", "MIN_WEIGHT", "MIN_CO2"]
    allowed_steel_ids: Optional[List[UUID]] = None
    geometry_locked: bool = True     # si False, optimiza también geometría
    robustness_level: str = "NOMINAL"  # NOMINAL / DETERMINISTIC / PROBABILISTIC
    utilization_limit: float = 1.0
    max_candidates: int = 1000
    seed: Optional[int] = None


class PrestressCandidate(BaseModel):
    n_strands: int
    strand_diameter_mm: float
    crown_radius_mm: float
    initial_force_per_strand_kn: float
    objectives: dict                  # {cost, mass, co2, robustness}
    constraints_satisfied: bool
    governing_constraint: Optional[str] = None
    feasible: bool = False
    transportable: bool = True
    pareto_dominated: Optional[bool] = None
    rejection_reason: Optional[str] = None


class PrestressOptimizationResult(BaseModel):
    run_id: Optional[UUID] = None
    candidates_evaluated: int
    candidates_feasible: int
    pareto_size: int
    convergence: bool
    min_cost_candidate: Optional[PrestressCandidate] = None
    min_weight_candidate: Optional[PrestressCandidate] = None
    min_co2_candidate: Optional[PrestressCandidate] = None
    balanced_candidate: Optional[PrestressCandidate] = None
    governing_rule: str = "Optimización Pareto multiobjetivo"


class ConcreteReportCreate(BaseModel):
    design_id: UUID
    report_type: ConcreteReportType


# ============================================================================
# Verificación completa por etapas
# ============================================================================

class StageVerificationRequest(BaseModel):
    design_id: UUID
    stage_code: ProductionStageCode
    age_days: float = Field(gt=0)
    applied_loads_json: Optional[dict] = None
    support_positions_json: Optional[dict] = None


class StageVerificationResult(BaseModel):
    stage_code: ProductionStageCode
    age_days: float
    fcm_t_mpa: float
    Ecm_t_mpa: float
    prestress_effective_kn: Optional[float] = None
    loss_accumulated_pct: Optional[float] = None
    verifications: List[dict]
    max_utilization: float
    status: ConcreteVerificationStatus
    governing_limit_state: Optional[LimitState] = None
    governing_station_m: Optional[float] = None


class ConcreteNormativeRouteRequest(BaseModel):
    height_m: float
    has_catenary_cables: bool = False
    mix_in_library: bool
    steel_in_library: bool
    domain_ok: bool
    checks_defined: bool
    evidence_ok: bool
    country_code: str = "ES"


class ConcreteNormativeRouteResult(BaseModel):
    route: ConcreteNormativeRoute
    steps_passed: List[bool]
    blocking_step: Optional[int] = None
    decision_trace: List[str]
    input_hash: str
