"""
Pydantic v2 schemas · Fase 5 — Acero: Diseño, Verificación y Fabricación
Salvi Studio · Columns
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Material library
# ---------------------------------------------------------------------------

class SteelProductPropertyCreate(BaseModel):
    product_norm: str = Field(..., max_length=64)
    steel_grade: str
    subgrade: str
    product_form: str
    supply_condition: str = "AR"
    thickness_min_mm: float = Field(..., gt=0)
    thickness_max_mm: float = Field(..., gt=0)
    temperature_min_c: Optional[float] = None

    fy_mpa: float = Field(..., gt=0, le=700)
    fu_mpa: float = Field(..., gt=0, le=900)
    E_gpa: float = Field(default=210.0, gt=0)
    G_gpa: float = Field(default=80.769, gt=0)
    nu: float = Field(default=0.3, ge=0, le=0.5)
    rho_kg_m3: float = Field(default=7850.0, gt=0)
    alpha_t_per_k: float = Field(default=12e-6, gt=0)

    charpy_energy_j: Optional[float] = None
    charpy_temp_c: Optional[float] = None
    cev_max: Optional[float] = None
    weldability_note: Optional[str] = None
    coating_compatibility: Optional[dict[str, Any]] = None
    thickness_tolerance_pct: Optional[float] = None
    certificate_type: Optional[str] = None
    carbon_factor_kg_co2_per_kg: Optional[float] = None
    carbon_factor_source: Optional[str] = None
    carbon_factor_year: Optional[int] = None
    carbon_factor_region: Optional[str] = None
    library_version: str = "1.0"
    notes: Optional[str] = None

    @model_validator(mode="after")
    def thickness_range_valid(self) -> "SteelProductPropertyCreate":
        if self.thickness_max_mm <= self.thickness_min_mm:
            raise ValueError("thickness_max_mm must be greater than thickness_min_mm")
        if self.fu_mpa < self.fy_mpa:
            raise ValueError("fu_mpa must be >= fy_mpa")
        return self


class SteelProductPropertyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    product_norm: str
    steel_grade: str
    subgrade: str
    product_form: str
    supply_condition: str
    thickness_min_mm: float
    thickness_max_mm: float
    temperature_min_c: Optional[float]
    fy_mpa: float
    fu_mpa: float
    E_gpa: float
    G_gpa: float
    nu: float
    rho_kg_m3: float
    alpha_t_per_k: float
    cev_max: Optional[float]
    carbon_factor_kg_co2_per_kg: Optional[float]
    library_version: str
    deprecated: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Thickness policy helper
# ---------------------------------------------------------------------------

class ThicknessPolicyResponse(BaseModel):
    """Política de espesores: muestra simultáneamente t_nom, t_min, t_eff, t_mass."""
    t_nom_mm: float = Field(..., description="Espesor nominal de compra")
    delta_t_tol_mm: float = Field(..., description="Tolerancia negativa de la norma del producto")
    delta_t_corr_mm: float = Field(default=0.0, description="Pérdida de corrosión de proyecto")
    t_min_mm: float = Field(..., description="t_nom - delta_t_tol; mínimo garantizado")
    t_eff_mm: float = Field(..., description="Espesor estructural efectivo para resistencia")
    t_mass_mm: float = Field(..., description="Espesor para cálculo de masa y coste")
    double_deduction_check: bool = Field(
        ..., description="True = sin doble reducción; False = ERROR STEEL-MAT-001"
    )


# ---------------------------------------------------------------------------
# Normative route classifier
# ---------------------------------------------------------------------------

class NormativeRouteRequest(BaseModel):
    project_id: uuid.UUID
    height_nominal_m: float = Field(..., gt=0, le=35)
    has_catenary_cables: bool = False
    has_excluded_actions: bool = False
    section_in_en40_domain: bool = True
    door_in_approved_method: bool = True
    combinations_available: bool = True
    all_rules_have_editions: bool = True
    structural_run_id: Optional[uuid.UUID] = None


class NormativeRouteStepResult(BaseModel):
    step: int
    condition: str
    status: str   # PASS / BLOCKED / WARNING
    detail: Optional[str] = None


class NormativeRouteResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    route: str
    route_version: str
    steps: list[NormativeRouteStepResult]
    decision_trace: dict[str, Any]
    active_rules: list[str]
    discarded_rules: list[str]
    exclusions: list[str]
    warnings: list[str]
    max_declaration_allowed: Optional[str]
    input_hash: str


# ---------------------------------------------------------------------------
# Section verification run
# ---------------------------------------------------------------------------

class SteelSectionCheckRunCreate(BaseModel):
    project_id: uuid.UUID
    structural_run_id: uuid.UUID
    normative_route_id: uuid.UUID
    maturity_level: str = "M2"
    utilization_limit: float = Field(default=1.0, gt=0, le=1.5)
    include_fatigue: bool = False
    include_local_buckling: bool = True
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class SteelSectionCheckRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    structural_run_id: uuid.UUID
    normative_route_id: uuid.UUID
    status: str
    maturity_level: str
    geometry_hash: str
    material_hash: str
    rules_hash: str
    stress_hash: str
    run_hash: Optional[str]
    utilization_limit: float
    max_utilization: Optional[float]
    governing_combination: Optional[str]
    governing_check_type: Optional[str]
    all_checks_passed: Optional[bool]
    error_code: Optional[str]
    error_detail: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class SteelSectionCheckResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    run_id: uuid.UUID
    combination_id: str
    wind_direction_deg: Optional[float]
    check_type: str
    norm: str
    norm_clause: Optional[str]
    property_set: str
    route: str
    N_kn: Optional[float]
    Vy_kn: Optional[float]
    Vz_kn: Optional[float]
    T_knm: Optional[float]
    My_knm: Optional[float]
    Mz_knm: Optional[float]
    N_rd_kn: Optional[float]
    My_rd_knm: Optional[float]
    Mz_rd_knm: Optional[float]
    utilization: float
    margin: Optional[float]
    status: str
    domain_ok: bool
    domain_notes: Optional[str]
    intermediate_values: Optional[dict[str, Any]]


# ---------------------------------------------------------------------------
# Effective section
# ---------------------------------------------------------------------------

class EffectiveSectionRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    element_id: Optional[uuid.UUID]
    station_z_m: Optional[float]
    panels: list[dict[str, Any]]
    section_class: Optional[int]
    A_eff_m2: Optional[float]
    Iy_eff_m4: Optional[float]
    Iz_eff_m4: Optional[float]
    centroid_y_shift_m: Optional[float]
    centroid_z_shift_m: Optional[float]
    iterations: Optional[int]
    converged: bool
    error_code: Optional[str]


# ---------------------------------------------------------------------------
# Door section
# ---------------------------------------------------------------------------

class DoorSectionModelCreate(BaseModel):
    project_id: uuid.UUID
    door_height_mm: float = Field(..., gt=0)
    door_width_mm: float = Field(..., gt=0)
    corner_radius_mm: Optional[float] = Field(default=None, ge=0)
    bottom_elevation_m: float
    top_elevation_m: float
    orientation_deg: float = Field(default=0.0, ge=0, lt=360)
    reinforcement_type: Optional[str] = None
    reinforcement_geometry: Optional[dict[str, Any]] = None
    check_run_id: Optional[uuid.UUID] = None

    @field_validator("top_elevation_m")
    @classmethod
    def top_above_bottom(cls, v: float, info: Any) -> float:
        bottom = info.data.get("bottom_elevation_m")
        if bottom is not None and v <= bottom:
            raise ValueError("top_elevation_m must be greater than bottom_elevation_m")
        return v


class DoorSectionModelResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    door_height_mm: float
    door_width_mm: float
    corner_radius_mm: Optional[float]
    bottom_elevation_m: float
    top_elevation_m: float
    orientation_deg: float
    reinforcement_type: Optional[str]
    A_net_m2: Optional[float]
    Iy_net_m4: Optional[float]
    Iz_net_m4: Optional[float]
    Iyz_net_m4: Optional[float]
    J_net_m4: Optional[float]
    centroid_y_m: Optional[float]
    centroid_z_m: Optional[float]
    principal_angle_deg: Optional[float]
    method_level: str
    method_in_domain: bool
    requires_local_method: bool
    error_code: Optional[str]
    geometry_hash: Optional[str]


# ---------------------------------------------------------------------------
# Weld group
# ---------------------------------------------------------------------------

class WeldGroupCreate(BaseModel):
    project_id: uuid.UUID
    weld_type: str
    weld_process: Optional[str] = None
    quality_class: Optional[str] = None
    weld_group_geometry: dict[str, Any]
    effective_throat_mm: Optional[float] = Field(default=None, gt=0)
    effective_length_mm: Optional[float] = Field(default=None, gt=0)
    ineffective_length_mm: Optional[float] = Field(default=None, ge=0)
    base_material_id: Optional[uuid.UUID] = None
    filler_material: Optional[str] = None
    fu_w_mpa: Optional[float] = Field(default=None, gt=0)
    wps_reference: Optional[str] = None
    position: Optional[str] = None
    accessible_for_inspection: bool = True
    check_run_id: Optional[uuid.UUID] = None

    # Cargas concurrentes (6 resultantes)
    Fx_kn: Optional[float] = None
    Fy_kn: Optional[float] = None
    Fz_kn: Optional[float] = None
    Mx_knm: Optional[float] = None
    My_knm: Optional[float] = None
    Mz_knm: Optional[float] = None


class WeldGroupResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    weld_type: str
    quality_class: Optional[str]
    effective_throat_mm: Optional[float]
    effective_length_mm: Optional[float]
    static_utilization: Optional[float]
    static_status: Optional[str]
    fatigue_utilization: Optional[float]
    fatigue_status: Optional[str]
    fatigue_category: Optional[str]
    fatigue_damage: Optional[float]
    accessible_for_inspection: bool
    fabricable: bool
    error_code: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Fatigue detail
# ---------------------------------------------------------------------------

class FatigueDetailCreate(BaseModel):
    detail_id: str = Field(..., max_length=32)
    description: str = Field(..., max_length=256)
    eligible_geometry: dict[str, Any]
    stress_orientation: str
    fatigue_category_mpa: float = Field(..., gt=0)
    sn_curve_id: str
    thickness_limit_mm: Optional[float] = None
    norm: str
    norm_edition: Optional[str] = None
    norm_clause: Optional[str] = None
    quality_required: Optional[str] = None
    domain_min_thickness_mm: Optional[float] = None
    domain_max_thickness_mm: Optional[float] = None
    domain_notes: Optional[str] = None
    library_version: str = "1.0"
    project_id: Optional[uuid.UUID] = None


class FatigueDetailResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    detail_id: str
    description: str
    stress_orientation: str
    fatigue_category_mpa: float
    sn_curve_id: str
    thickness_limit_mm: Optional[float]
    norm: str
    norm_edition: Optional[str]
    quality_required: Optional[str]
    domain_notes: Optional[str]
    library_version: str
    deprecated: bool


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------

class DurabilitySystemCreate(BaseModel):
    project_id: uuid.UUID
    component: str = "FULL_COLUMN"
    corrosivity_category: str
    design_life_years: int = Field(..., gt=0, le=100)
    exposure_type: Optional[str] = None
    protection_system: str
    layers: list[dict[str, Any]] = Field(..., min_length=1)
    surface_preparation: Optional[str] = None
    maintenance_interval_years: Optional[int] = Field(default=None, ge=1)
    maintenance_notes: Optional[str] = None


class DurabilitySystemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    component: str
    corrosivity_category: str
    design_life_years: int
    protection_system: str
    layers: list[dict[str, Any]]
    galvanizing_vent_holes_ok: Optional[bool]
    galvanizing_drain_holes_ok: Optional[bool]
    closed_cavities_detected: bool
    compatible: Optional[bool]
    error_code: Optional[str]
    cost_per_m2: Optional[float]
    co2_kg_per_m2: Optional[float]
    confirmed_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Manufacturing
# ---------------------------------------------------------------------------

class ManufacturingRouteCreate(BaseModel):
    project_id: uuid.UUID
    utilization_limit: float = Field(default=1.0, gt=0, le=1.5)
    margin_pct: Optional[float] = Field(default=None, ge=0, le=200)
    margin_type: Optional[str] = None
    currency: str = "EUR"


class ManufacturingRouteResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    bom: Optional[dict[str, Any]]
    total_mass_kg: Optional[float]
    total_surface_m2: Optional[float]
    material_cost: Optional[float]
    total_industrial_cost: Optional[float]
    sale_price: Optional[float]
    currency: str
    co2_total_kg: Optional[float]
    blocking_rules: Optional[list[dict[str, Any]]]
    all_fabricable: Optional[bool]
    error_code: Optional[str]
    is_preliminary: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Steel joint
# ---------------------------------------------------------------------------

class SteelJointCreate(BaseModel):
    project_id: uuid.UUID
    joint_type: str
    position_z_m: float = Field(..., ge=0)
    nominal_overlap_mm: Optional[float] = Field(default=None, gt=0)
    min_overlap_mm: Optional[float] = Field(default=None, gt=0)
    check_run_id: Optional[uuid.UUID] = None


class SteelJointResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    joint_type: str
    position_z_m: float
    nominal_overlap_mm: Optional[float]
    rotational_stiffness_nm_per_rad: Optional[float]
    stiffness_validated: bool
    static_status: Optional[str]
    fatigue_status: Optional[str]
    within_validated_domain: bool
    error_code: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

class SteelOptimizationRunCreate(BaseModel):
    project_id: uuid.UUID
    utilization_limit: float = Field(default=1.0, gt=0, le=1.5)
    max_piece_length_m: float = Field(default=12.0, gt=0, le=30)
    min_diameter_mm: float = Field(default=60.0, gt=0)
    available_grades: Optional[list[str]] = None
    available_thicknesses_mm: Optional[list[float]] = None
    allowed_tapers: Optional[list[float]] = None


class ParetoSolution(BaseModel):
    candidate_id: uuid.UUID
    steel_grade: str
    total_mass_kg: float
    total_industrial_cost: float
    co2_total_kg: float
    max_utilization: float
    governing_check: Optional[str]
    n_pieces: Optional[int]
    objectives: list[str]   # MIN_COST / MIN_WEIGHT / MIN_CO2 / BALANCED / none


class SteelOptimizationRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    n_candidates_generated: Optional[int]
    n_candidates_calculated: Optional[int]
    n_pareto_solutions: Optional[int]
    pareto_front: Optional[list[dict[str, Any]]]
    min_cost_candidate_id: Optional[uuid.UUID]
    min_weight_candidate_id: Optional[uuid.UUID]
    min_co2_candidate_id: Optional[uuid.UUID]
    balanced_candidate_id: Optional[uuid.UUID]
    created_at: datetime
    completed_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Product family and validation evidence
# ---------------------------------------------------------------------------

class ProductFamilyCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = None
    domain: dict[str, Any]
    domain_version: str = "1.0"
    project_id: Optional[uuid.UUID] = None


class ProductFamilyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: Optional[str]
    domain: dict[str, Any]
    domain_version: str
    approved_at: Optional[datetime]


class ValidationEvidenceCreate(BaseModel):
    evidence_type: str
    reference: str = Field(..., max_length=256)
    version: Optional[str] = None
    tolerance: Optional[float] = Field(default=None, ge=0, le=100)
    result_summary: Optional[str] = None
    conservative_side: Optional[bool] = None
    laboratory: Optional[str] = None
    test_date: Optional[datetime] = None
    sample_description: Optional[str] = None
    loads_applied: Optional[dict[str, Any]] = None
    failure_mode: Optional[str] = None
    solver_version: Optional[str] = None
    norm_used: Optional[str] = None
    inputs_hash: Optional[str] = None
    family_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None


class ValidationEvidenceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    evidence_type: str
    reference: str
    tolerance: Optional[float]
    result_summary: Optional[str]
    conservative_side: Optional[bool]
    laboratory: Optional[str]
    test_date: Optional[datetime]
    inputs_hash: Optional[str]
    approved_at: Optional[datetime]
    valid_until: Optional[datetime]
    created_at: datetime


# ---------------------------------------------------------------------------
# Report snapshot
# ---------------------------------------------------------------------------

class SteelReportCreate(BaseModel):
    project_id: uuid.UUID
    check_run_id: Optional[uuid.UUID] = None
    report_type: str = Field(..., pattern=r"^(CLIENT|ENGINEERING|INTERNAL|PRODUCTION|INSPECTION|CONFORMITY|COST|CO2)$")
    maturity_level: str
    language: str = Field(default="es", max_length=8)
    format: str = Field(default="PDF", pattern=r"^(PDF|JSON)$")


class SteelReportResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    report_type: str
    maturity_level: str
    language: str
    content_hash: str
    all_evidences_present: Optional[bool]
    all_approvals_present: Optional[bool]
    storage_path: Optional[str]
    format: str
    generated_at: datetime
    approved_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Error codes response
# ---------------------------------------------------------------------------

class SteelErrorResponse(BaseModel):
    error_code: str
    message: str
    blocking: bool = True
    suggested_action: Optional[str] = None
