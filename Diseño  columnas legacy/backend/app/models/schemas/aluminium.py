"""
Schemas Pydantic v2 · Fase 6 — Aluminio
Salvi Studio · Columns
"""
from __future__ import annotations

import re
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from app.models.db.aluminium import (
    AluminiumProductForm, AluminiumRoute, HAZType, WeldProcess,
    JointGeometry, SectionRegionType, PanelStatus, DoorReinforcementType,
    AluminiumSurfaceTreatment, AluminiumJointType, AluminiumCheckType,
    AluminiumCheckStatus, MaterialStatus, AluminiumReportType,
    OptimizationObjective,
)


_ORM = {"from_attributes": True}


# ── Material ──────────────────────────────────────────────────────────────────

class AluminiumAlloyVersionCreate(BaseModel):
    alloy_designation: str = Field(..., pattern=r"^EN AW-\d{4}[A-Z]?$")
    temper: str = Field(..., min_length=1, max_length=16)
    product_form: AluminiumProductForm
    norm_reference: str
    thickness_min_mm: float = Field(..., gt=0)
    thickness_max_mm: float = Field(..., gt=0)
    direction: Optional[str] = None
    temperature_c: float = Field(default=20.0)
    f0_mpa: float = Field(..., gt=0)
    fu_mpa: float = Field(..., gt=0)
    E_mpa: float = Field(default=70000.0, gt=0)
    G_mpa: float = Field(default=26900.0, gt=0)
    nu: float = Field(default=0.33, gt=0, lt=0.5)
    rho_kg_m3: float = Field(default=2700.0, gt=0)
    alpha_T_per_k: float = Field(default=2.36e-5, gt=0)
    haz_rho_yield: Optional[float] = Field(default=None, ge=0, le=1)
    haz_rho_ultimate: Optional[float] = Field(default=None, ge=0, le=1)
    haz_rho_buckling: Optional[float] = Field(default=None, ge=0, le=1)
    haz_rho_fatigue: Optional[float] = Field(default=None, ge=0, le=1)
    haz_width_mm: Optional[float] = Field(default=None, gt=0)
    bend_limit_r_over_t_L: Optional[float] = None
    bend_limit_r_over_t_LT: Optional[float] = None
    epd_factor_kg_co2_per_kg: Optional[float] = None
    price_per_kg_eur: Optional[float] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_material(self) -> "AluminiumAlloyVersionCreate":
        if self.fu_mpa <= self.f0_mpa:
            raise ValueError("fu_mpa must be > f0_mpa")
        if self.thickness_max_mm <= self.thickness_min_mm:
            raise ValueError("thickness_max_mm must be > thickness_min_mm")
        return self


class AluminiumAlloyVersionResponse(BaseModel):
    model_config = _ORM
    id: Any
    alloy_designation: str
    temper: str
    product_form: AluminiumProductForm
    norm_reference: str
    thickness_min_mm: float
    thickness_max_mm: float
    f0_mpa: float
    fu_mpa: float
    E_mpa: float
    rho_kg_m3: float
    haz_rho_yield: Optional[float]
    haz_rho_ultimate: Optional[float]
    haz_width_mm: Optional[float]
    status: MaterialStatus


class MaterialResolveRequest(BaseModel):
    alloy_designation: str
    temper: str
    product_form: AluminiumProductForm
    thickness_mm: float = Field(..., gt=0)
    direction: Optional[str] = None
    temperature_c: float = Field(default=20.0)
    gamma_M: float = Field(default=1.1, gt=0)

    @field_validator("alloy_designation")
    @classmethod
    def check_alloy(cls, v: str) -> str:
        if not re.match(r"^EN AW-\d{4}[A-Z]?$", v):
            raise ValueError("alloy_designation must match EN AW-NNNN[X] pattern")
        return v


class MaterialResolveResponse(BaseModel):
    alloy_designation: str
    temper: str
    product_form: str
    thickness_mm: float
    f0_d_mpa: float
    fu_d_mpa: float
    E_mpa: float
    G_mpa: float
    rho_kg_m3: float
    gamma_M: float
    provenance: str
    status: MaterialStatus


# ── HAZ ───────────────────────────────────────────────────────────────────────

class HAZRegionInput(BaseModel):
    haz_type: HAZType
    process: WeldProcess
    alloy_designation: str
    temper: str
    thickness_mm: float = Field(..., gt=0)
    orientation_deg: Optional[float] = None


class HAZRegionResult(BaseModel):
    haz_type: HAZType
    haz_width_mm: float
    rho_yield: float
    rho_ultimate: float
    rho_buckling: Optional[float]
    rho_fatigue: Optional[float]
    side: str
    overlaps_door: bool = False
    error_code: Optional[str] = None


class HAZBuildRequest(BaseModel):
    project_id: Any
    section_station_m: float
    haz_inputs: list[HAZRegionInput]
    check_overlaps: bool = True


class HAZBuildResponse(BaseModel):
    section_station_m: float
    regions: list[HAZRegionResult]
    has_overlapping_zones: bool
    overlap_treatment: Optional[str]
    geometry_hash: str
    material_hash: str
    error_codes: list[str]


# ── Sección ───────────────────────────────────────────────────────────────────

class SectionPropertiesRequest(BaseModel):
    section_type: str = Field(..., pattern="^(CIRCULAR|POLYGONAL|EXTRUDED|WITH_DOOR)$")
    D_ext_mm: Optional[float] = Field(default=None, gt=0)
    t_nom_mm: Optional[float] = Field(default=None, gt=0)
    n_faces: Optional[int] = Field(default=None, ge=3)
    inscribed_d_mm: Optional[float] = Field(default=None, gt=0)
    rho_kg_m3: float = Field(default=2700.0)
    include_haz: bool = False
    haz_regions: Optional[list[HAZRegionResult]] = None


class SectionPropertiesResponse(BaseModel):
    section_type: str
    A_gross_m2: float
    A_net_m2: Optional[float]
    centroid_y_m: float
    centroid_z_m: float
    Iy_m4: float
    Iz_m4: float
    Iyz_m4: float
    J_m4: float
    Ay_m2: float
    Az_m2: float
    Wel_y_m3: float
    Wel_z_m3: float
    mass_per_m_kg: float
    haz_area_fraction: Optional[float]
    check_passed: bool
    qa_notes: list[str]


class EffectiveSectionRequest(BaseModel):
    D_ext_mm: float = Field(..., gt=0)
    t_eff_mm: float = Field(..., gt=0)
    E_mpa: float = Field(default=70000.0)
    f0_d_mpa: float = Field(..., gt=0)
    sigma_max_mpa: float
    max_iterations: int = Field(default=20, ge=1, le=100)
    convergence_tol: float = Field(default=1e-4)


class EffectiveSectionResponse(BaseModel):
    width_effective_mm: Optional[float]
    reduction_factor: Optional[float]
    slenderness: float
    n_iterations: int
    converged: bool
    panel_status: PanelStatus
    governing_rule: Optional[str]


# ── Verificación ──────────────────────────────────────────────────────────────

class AluminiumCheckResult(BaseModel):
    check_type: AluminiumCheckType
    status: AluminiumCheckStatus
    solicitation: float
    resistance: float
    utilization: float
    unit: str
    governing_rule: Optional[str]
    equation_trace: Optional[dict[str, Any]]
    intermediate_values: Optional[dict[str, Any]]
    error_code: Optional[str]


class AluminiumVerifyRequest(BaseModel):
    section_type: str
    f0_d_mpa: float = Field(..., gt=0)
    fu_d_mpa: float = Field(..., gt=0)
    E_mpa: float = Field(default=70000.0)
    gamma_M0: float = Field(default=1.0, gt=0)
    A_m2: float = Field(..., gt=0)
    Iy_m4: float = Field(..., gt=0)
    Iz_m4: float = Field(default=0.0)
    J_m4: float = Field(..., gt=0)
    Ay_m2: Optional[float] = None
    Az_m2: Optional[float] = None
    Wel_y_m3: float = Field(..., gt=0)
    Wel_z_m3: Optional[float] = None
    N_kn: float = Field(default=0.0)
    Vy_kn: float = Field(default=0.0)
    Vz_kn: float = Field(default=0.0)
    My_knm: float = Field(default=0.0)
    Mz_knm: float = Field(default=0.0)
    T_knm: float = Field(default=0.0)
    haz_rho_yield: Optional[float] = Field(default=None, ge=0, le=1)
    utilization_limit: float = Field(default=1.0, gt=0)


class AluminiumVerifyResponse(BaseModel):
    checks: list[AluminiumCheckResult]
    overall_status: AluminiumCheckStatus
    max_utilization: float
    governing_check: Optional[AluminiumCheckType]
    error_codes: list[str]
    warnings: list[str]


# ── Normative route ───────────────────────────────────────────────────────────

class AluminiumRouteRequest(BaseModel):
    height_nominal_m: float = Field(..., gt=0, le=30.0)
    has_catenary_cables: bool
    alloy_in_library: bool
    domain_ok: bool
    checks_defined: bool
    rules_available: bool
    evidence_ok: bool


class AluminiumRouteStepResult(BaseModel):
    step: int
    condition: str
    status: str
    detail: Optional[str]


class AluminiumRouteResponse(BaseModel):
    route: AluminiumRoute
    route_version: str
    steps: list[AluminiumRouteStepResult]
    decision_trace: list[str]
    active_rules: list[str]
    discarded_rules: list[str]
    exclusions: list[str]
    warnings: list[str]
    max_declaration_allowed: Optional[str]
    input_hash: str


# ── Fatiga ────────────────────────────────────────────────────────────────────

class AluminiumFatigueCheckRequest(BaseModel):
    delta_sigma_mpa: float = Field(..., gt=0)
    fatigue_category_mpa: float = Field(..., gt=0)
    n_cycles: float = Field(..., gt=0)
    N_ref_cycles: float = Field(..., gt=0)
    gamma_Ff: float = Field(default=1.0, gt=0)
    gamma_Mf: float = Field(default=1.15, gt=0)
    source: str = Field(default="wind")


class AluminiumMinerBlock(BaseModel):
    delta_sigma_mpa: float = Field(..., gt=0)
    n_cycles: float = Field(..., gt=0)
    N_ref: float = Field(..., gt=0)
    source: str


class AluminiumMinerRequest(BaseModel):
    cycle_blocks: list[AluminiumMinerBlock]
    D_limit: float = Field(default=1.0, gt=0)


class AluminiumMinerResponse(BaseModel):
    total_damage: float
    D_limit: float
    status: str
    source_breakdown: dict[str, float]
    duplicate_source_detected: bool


# ── Durabilidad ───────────────────────────────────────────────────────────────

class AluminiumDurabilityRequest(BaseModel):
    treatment: AluminiumSurfaceTreatment
    corrosivity_category: str = Field(..., pattern=r"^(C[1-5X]|Im[1-3])$")
    design_life_years: float = Field(..., gt=0)
    has_open_cavities: bool = False
    galvanic_contacts: Optional[list[str]] = None


class AluminiumDurabilityResponse(BaseModel):
    life_adequate: bool
    life_range_min_years: Optional[float]
    life_range_max_years: Optional[float]
    galvanic_isolation_required: bool
    galvanic_risks: list[str]
    open_cavity_risk: bool
    recommendations: list[str]
    error_codes: list[str]


# ── Fabricación ───────────────────────────────────────────────────────────────

class AluminiumBendAllowanceRequest(BaseModel):
    thickness_mm: float = Field(..., gt=0)
    bend_angle_deg: float = Field(..., gt=0, le=180)
    inner_radius_mm: float = Field(..., ge=0)
    k_factor: float = Field(default=0.33, gt=0, lt=1.0)


class AluminiumBendAllowanceResponse(BaseModel):
    bend_allowance_mm: float
    outside_setback_mm: float
    neutral_radius_mm: float
    k_factor: float
    compliant_with_min_radius: bool
    min_radius_for_material: Optional[float]


class AluminiumFabricabilityRequest(BaseModel):
    piece_length_m: float = Field(..., gt=0)
    diameter_mm: float = Field(..., gt=0)
    seam_azimuth_deg: float = Field(default=0.0)
    door_azimuth_deg: float = Field(default=0.0)
    weld_process: WeldProcess = WeldProcess.MIG
    door_tolerance_deg: float = Field(default=5.0, ge=0)


class FabricabilityIssue(BaseModel):
    code: str
    severity: str
    description: str


class AluminiumFabricabilityResponse(BaseModel):
    is_fabricable: bool
    issues: list[FabricabilityIssue]
    piece_length_ok: bool
    diameter_ok: bool
    seam_not_in_door: bool


# ── Optimización ──────────────────────────────────────────────────────────────

class AluminiumOptimizationRequest(BaseModel):
    project_id: Any
    normative_route_id: Optional[Any] = None
    utilization_limit: float = Field(default=1.0, gt=0, le=1.0)
    max_piece_length_m: float = Field(default=12.0, gt=0)
    min_diameter_mm: float = Field(default=60.0, gt=0)


class AluminiumParetoSolution(BaseModel):
    candidate_id: Optional[Any]
    objective: OptimizationObjective
    total_cost_eur: float
    total_mass_kg: float
    total_co2_kg: float
    max_utilization: float
    alloy_designation: str
    temper: str
    weld_process: WeldProcess
    is_fabricable: bool
    is_transportable: bool


class AluminiumOptimizationResponse(BaseModel):
    pareto_front_size: int
    solutions: list[AluminiumParetoSolution]
    n_candidates_evaluated: int
    n_discarded: int
    error_codes: list[str]


# ── Informe ───────────────────────────────────────────────────────────────────

class AluminiumReportCreate(BaseModel):
    project_id: Any
    verification_run_id: Optional[Any] = None
    report_type: AluminiumReportType
    language: str = Field(default="es", pattern="^[a-z]{2}$")
