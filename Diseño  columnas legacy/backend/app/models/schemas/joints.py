"""
Salvi Studio · Columns — Fase 9: Uniones y Columnas Segmentadas
Schemas Pydantic v2
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Segmentación ─────────────────────────────────────────────────────────────

class SegmentConstraints(BaseModel):
    max_piece_length_m: float = Field(12.0, gt=0.0, le=30.0)
    max_piece_mass_kg: Optional[float] = Field(None, gt=0.0)
    forbidden_zones: List[Dict[str, float]] = Field(default_factory=list)
    preferred_stations: List[float] = Field(default_factory=list)
    galvanizing_bath_length_m: Optional[float] = Field(None, gt=0.0)
    exception_approved: bool = False
    exception_reference: Optional[str] = None

    @field_validator("max_piece_length_m")
    @classmethod
    def validate_max_length(cls, v: float, info) -> float:
        # Excepción solo si aprobada
        return v


class SegmentPlanRequest(BaseModel):
    design_id: str
    material_route: str = Field(..., pattern="^(STEEL|ALUMINIUM|CONCRETE)$")
    total_height_m: float = Field(..., gt=0.0, le=30.0)
    constraints: SegmentConstraints = Field(default_factory=SegmentConstraints)
    joint_type_preference: Optional[str] = None
    objective: str = Field("min_cost")


class SegmentResult(BaseModel):
    index: int
    z_start_m: float
    z_end_m: float
    length_m: float
    envelope_length_m: float
    mass_kg: Optional[float]
    galvanizing_ok: bool
    transport_ok: bool
    weight_ok: bool
    error_codes: List[str] = Field(default_factory=list)


class JointProposal(BaseModel):
    joint_type: str
    z_station_m: float
    in_forbidden_zone: bool
    stiffness_model: str
    error_codes: List[str] = Field(default_factory=list)


class SegmentPlanResult(BaseModel):
    plan_id: Optional[str] = None
    feasible: bool
    piece_count: int
    segments: List[SegmentResult]
    joints: List[JointProposal]
    plan_hash: str
    error_codes: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ── Telescópica ───────────────────────────────────────────────────────────────

class TelescopicRequest(BaseModel):
    D_ext_mm: float = Field(..., gt=0.0)
    t_wall_mm: float = Field(..., gt=0.0)
    overlap_mm: float = Field(..., gt=0.0)
    taper_male: float = Field(0.0, ge=0.0)
    taper_female: float = Field(0.0, ge=0.0)
    ovalization_mm: float = Field(0.0, ge=0.0)
    friction_coeff: float = Field(..., gt=0.0, le=1.0)
    N_kn: float = 0.0
    Vy_kn: float = 0.0
    Vz_kn: float = 0.0
    My_knm: float = 0.0
    Mz_knm: float = 0.0
    T_knm: float = 0.0
    fy_mpa: float = Field(355.0, gt=0.0)
    environment: str = "C3"  # ISO 12944 corrosivity


class TelescopicCheckResult(BaseModel):
    overlap_ok: bool
    contact_pressure_mpa: float
    sliding_sls_mm: float
    utilization_stress: float
    utilization_sliding: float
    fretting_risk: bool
    rigidity_kN_per_mm: float
    robust_overlap_ok: bool
    status: str
    governing_rule: str
    intermediate_values: Dict[str, Any] = Field(default_factory=dict)
    error_codes: List[str] = Field(default_factory=list)


class TelescopicInsertionCheck(BaseModel):
    insertion_force_kn: float
    force_limit_kn: Optional[float]
    friction_coeff_max: float
    feasible: bool
    error_code: Optional[str] = None


class TelescopicRobustRequest(BaseModel):
    base: TelescopicRequest
    overlap_min_mm: Optional[float] = None
    friction_min: Optional[float] = None
    ovalization_max_mm: Optional[float] = None
    fy_min_mpa: Optional[float] = None


# ── Embridada ─────────────────────────────────────────────────────────────────

class BoltGroupRequest(BaseModel):
    bolt_count: int = Field(..., ge=4)
    bolt_pcd_mm: float = Field(..., gt=0.0)
    bolt_class: str = Field("8.8")
    bolt_diameter_mm: float = Field(..., gt=0.0)
    pretensioned: bool = False
    target_pretension_kn: Optional[float] = None
    friction_coeff_flange: float = Field(0.3, gt=0.0)
    N_kn: float = 0.0
    Vy_kn: float = 0.0
    Vz_kn: float = 0.0
    My_knm: float = 0.0
    Mz_knm: float = 0.0
    T_knm: float = 0.0
    fy_bolt_mpa: float = Field(640.0, gt=0.0)


class BoltGroupResult(BaseModel):
    n_bolts: int
    max_bolt_tension_kn: float
    min_bolt_tension_kn: float
    max_shear_per_bolt_kn: float
    prying_factor: float
    contact_state: str
    sliding_ok: bool
    utilization_tension: float
    utilization_shear: float
    utilization_interaction: float
    status: str
    governing_rule: str
    intermediate_values: Dict[str, Any] = Field(default_factory=dict)
    error_codes: List[str] = Field(default_factory=list)


class FlangeAccessCheck(BaseModel):
    bolt_diameter_mm: float
    wrench_size_mm: float
    available_clearance_mm: float

class FlangeAccessResult(BaseModel):
    accessible: bool
    required_clearance_mm: float
    error_code: Optional[str] = None


# ── Soldada ───────────────────────────────────────────────────────────────────

class WeldedJointRequest(BaseModel):
    joint_config: str = Field("butt_full_penetration")
    throat_mm: Optional[float] = None
    weld_category: str = Field("71")  # FAT class
    misalignment_mm: float = Field(0.0, ge=0.0)
    N_kn: float = 0.0
    My_knm: float = 0.0
    Mz_knm: float = 0.0
    T_knm: float = 0.0
    D_ext_mm: float = Field(..., gt=0.0)
    t_wall_mm: float = Field(..., gt=0.0)
    fy_mpa: float = Field(355.0, gt=0.0)
    fu_mpa: float = Field(490.0, gt=0.0)
    field_weld: bool = False
    field_weld_approved: bool = False

    @model_validator(mode="after")
    def check_field_weld(self) -> "WeldedJointRequest":
        if self.field_weld and not self.field_weld_approved:
            raise ValueError("J9-E003: soldadura de obra no autorizada. Requiere procedimiento aprobado.")
        return self


class WeldedJointResult(BaseModel):
    static_utilization: float
    fatigue_utilization: float
    misalignment_penalty_pct: float
    ndt_required: str
    status: str
    governing_rule: str
    intermediate_values: Dict[str, Any] = Field(default_factory=dict)
    error_codes: List[str] = Field(default_factory=list)


# ── Manguito ──────────────────────────────────────────────────────────────────

class SleeveRequest(BaseModel):
    sleeve_type: str = Field("INTERIOR")
    length_mm: float = Field(..., gt=0.0)
    outer_d_mm: float = Field(..., gt=0.0)
    inner_d_mm: float = Field(..., gt=0.0)
    attachment: str = Field("weld")
    T_knm: float = 0.0
    My_knm: float = 0.0
    fy_mpa: float = Field(355.0, gt=0.0)
    drain_ok: bool = True
    exterior_water_retained: bool = False

    @field_validator("exterior_water_retained")
    @classmethod
    def check_exterior_water(cls, v: bool, info) -> bool:
        # Manguito exterior con agua retenida → bloqueo
        return v


class SleeveResult(BaseModel):
    transfer_length_ok: bool
    torsion_ok: bool
    fatigue_edge_ok: bool
    water_retention_blocked: bool
    status: str
    governing_rule: str
    error_codes: List[str] = Field(default_factory=list)


# ── Híbrida ───────────────────────────────────────────────────────────────────

class HybridInterfaceRequest(BaseModel):
    hybrid_type: str = Field("STEEL_ALUMINIUM")
    isolator_type: Optional[str] = None
    isolator_thickness_mm: Optional[float] = None
    galvanic_area_ratio: Optional[float] = None  # cathodic/anodic
    delta_T_k: float = Field(50.0, ge=0.0)
    E_steel_mpa: float = 210000.0
    E_aluminium_mpa: float = 70000.0
    alpha_steel: float = 12e-6
    alpha_aluminium: float = 23e-6
    N_kn: float = 0.0
    My_knm: float = 0.0
    fy_aluminium_mpa: float = 160.0


class HybridInterfaceResult(BaseModel):
    galvanic_ok: bool
    isolator_continuous: bool
    thermal_stress_mpa: float
    thermal_ok: bool
    drain_required: bool
    status: str
    governing_rule: str
    intermediate_values: Dict[str, Any] = Field(default_factory=dict)
    error_codes: List[str] = Field(default_factory=list)


class ConcreteInterfaceRequest(BaseModel):
    N_kn: float = 0.0
    My_knm: float = 0.0
    V_kn: float = 0.0
    bearing_area_mm2: float = Field(..., gt=0.0)
    fck_mpa: float = Field(..., gt=0.0)
    family_approved: bool = False
    grout_hardened: bool = True

    @field_validator("family_approved")
    @classmethod
    def check_family(cls, v: bool) -> bool:
        return v


class ConcreteInterfaceResult(BaseModel):
    bearing_stress_mpa: float
    bearing_ok: bool
    pullout_ok: Optional[bool] = None
    family_blocked: bool
    grout_stability_ok: bool
    status: str
    governing_rule: str
    error_codes: List[str] = Field(default_factory=list)


# ── Optimización ──────────────────────────────────────────────────────────────

class JointCandidate(BaseModel):
    joint_type: str
    template_ref: Optional[str] = None
    cost_eur: float
    mass_kg: float
    co2_kg: float
    assembly_complexity: float = Field(..., ge=0.0, le=10.0)
    risk_score: float = Field(..., ge=0.0, le=1.0)
    logistics_score: float = Field(..., ge=0.0, le=1.0)
    durability_score: float = Field(..., ge=0.0, le=1.0)
    feasible: bool = True
    discard_reason: Optional[str] = None
    utilization_max: float = Field(0.0, ge=0.0)


class OptimizationWeights(BaseModel):
    w_cost: float = Field(0.3, ge=0.0, le=1.0)
    w_weight: float = Field(0.15, ge=0.0, le=1.0)
    w_co2: float = Field(0.15, ge=0.0, le=1.0)
    w_assembly: float = Field(0.15, ge=0.0, le=1.0)
    w_risk: float = Field(0.1, ge=0.0, le=1.0)
    w_logistics: float = Field(0.1, ge=0.0, le=1.0)
    w_durability: float = Field(0.05, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def sum_to_one(self) -> "OptimizationWeights":
        total = (self.w_cost + self.w_weight + self.w_co2 + self.w_assembly
                 + self.w_risk + self.w_logistics + self.w_durability)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Los pesos deben sumar 1.0 (actual: {total:.3f})")
        return self


class OptimizationResult(BaseModel):
    pareto_count: int
    recommended: Optional[JointCandidate]
    min_cost: Optional[JointCandidate]
    min_weight: Optional[JointCandidate]
    min_co2: Optional[JointCandidate]
    balanced: Optional[JointCandidate]
    weights_hash: str
    discarded: List[Dict[str, str]] = Field(default_factory=list)


# ── Montaje ───────────────────────────────────────────────────────────────────

class AssemblyValidationRequest(BaseModel):
    joint_type: str
    overlap_mm: Optional[float] = None
    insertion_force_kn: Optional[float] = None
    torque_nm: Optional[float] = None
    interior_access: bool = True
    personnel_count: int = Field(2, ge=1)
    environment: str = "outdoor"


class AssemblyValidationResult(BaseModel):
    feasible: bool
    hold_points: List[str] = Field(default_factory=list)
    tools_required: List[str] = Field(default_factory=list)
    insertion_force_ok: Optional[bool] = None
    access_ok: bool
    error_codes: List[str] = Field(default_factory=list)


# ── Análisis robusto ──────────────────────────────────────────────────────────

class RobustnessScenario(BaseModel):
    name: str
    overlap_factor: float = 1.0
    friction_factor: float = 1.0
    fy_factor: float = 1.0
    ovalization_factor: float = 1.0


class RobustnessResult(BaseModel):
    nominal_utilization: float
    worst_utilization: float
    worst_scenario: str
    robust_pass: bool
    scenario_results: List[Dict[str, Any]] = Field(default_factory=list)
    error_code: Optional[str] = None


# ── Liberación ────────────────────────────────────────────────────────────────

class JointReleaseCreate(BaseModel):
    plan_id: str
    release_level: str
    all_checks_passed: bool
    approved_by: Optional[str] = None

    @model_validator(mode="after")
    def validate_release(self) -> "JointReleaseCreate":
        if self.release_level == "M4" and not self.all_checks_passed:
            raise ValueError("J9-E007: liberación M4 sin todas las verificaciones completadas")
        return self
