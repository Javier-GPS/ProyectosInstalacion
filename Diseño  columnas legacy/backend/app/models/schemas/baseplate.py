"""
Fase 10 · Placa Base, Pernos y Anclajes
Pydantic v2 request/response schemas
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.db.baseplate import (
    AnchorFamily,
    AnchorRodType,
    AssemblyStatus,
    BasePlateMaturityLevel,

    ConcreteCondition,
    ConcreteFailureMode,
    ContactState,
    GroutType,
    MarketHomologationStatus,
    PlateDesignMethod,
    PlatePatternType,
    PostInstalledType,
    ShearMechanism,
)


# ---------------------------------------------------------------------------
# Base assembly
# ---------------------------------------------------------------------------

class BaseAssemblyCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    project_id: UUID
    code: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    anchor_family: AnchorFamily
    pattern_type: PlatePatternType
    N_kn: float = 0.0
    Vy_kn: float = 0.0
    Vz_kn: float = 0.0
    T_knm: float = 0.0
    My_knm: float = 0.0
    Mz_knm: float = 0.0
    governing_combination: Optional[str] = None


class BaseAssemblyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    code: str
    status: AssemblyStatus
    maturity_level: BasePlateMaturityLevel
    anchor_family: AnchorFamily
    pattern_type: PlatePatternType
    N_kn: float
    Vy_kn: float
    Vz_kn: float
    T_knm: float
    My_knm: float
    Mz_knm: float
    governing_combination: Optional[str]
    geometry_hash: Optional[str]
    calc_hash: Optional[str]
    solver_version: Optional[str]


# ---------------------------------------------------------------------------
# Base plate
# ---------------------------------------------------------------------------

class BasePlateRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    assembly_id: UUID
    shape: str = "RECTANGULAR"
    width_mm: float = Field(..., gt=0, le=2000)
    length_mm: float = Field(..., gt=0, le=2000)
    thickness_mm: float = Field(..., gt=0, le=150)
    material_grade: str = "S355"
    fy_mpa: float = Field(355.0, gt=0)
    fu_mpa: float = Field(470.0, gt=0)
    design_method: PlateDesignMethod = PlateDesignMethod.P1_CANTILEVER
    hole_diameter_mm: Optional[float] = Field(None, gt=0)
    hole_count: Optional[int] = Field(None, ge=2)
    planarity_tolerance_mm: float = 1.0

    @model_validator(mode="after")
    def check_fu_gt_fy(self) -> "BasePlateRequest":
        if self.fu_mpa <= self.fy_mpa:
            raise ValueError("B10-E001: fu_mpa debe ser mayor que fy_mpa")
        return self

    @model_validator(mode="after")
    def check_hole_consistency(self) -> "BasePlateRequest":
        if (self.hole_diameter_mm is None) != (self.hole_count is None):
            raise ValueError("B10-E002: hole_diameter_mm y hole_count deben definirse juntos")
        return self


class BasePlateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assembly_id: UUID
    shape: str
    width_mm: float
    length_mm: float
    thickness_mm: float
    material_grade: str
    fy_mpa: float
    fu_mpa: float
    design_method: PlateDesignMethod
    hole_diameter_mm: Optional[float]
    hole_count: Optional[int]
    mass_kg: Optional[float]
    is_recommended: bool
    util_plate: Optional[float]


# ---------------------------------------------------------------------------
# Anchor pattern & rod
# ---------------------------------------------------------------------------

class AnchorPatternRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    assembly_id: UUID
    pattern_label: str = Field(..., min_length=1, max_length=32)
    bolt_count: int = Field(..., ge=2)
    bolt_pcd_mm: Optional[float] = Field(None, gt=0)
    bolt_x_mm: Optional[List[float]] = None
    bolt_y_mm: Optional[List[float]] = None
    orientation_deg: float = 0.0
    position_tolerance_mm: float = 3.0

    @model_validator(mode="after")
    def check_coords_or_pcd(self) -> "AnchorPatternRequest":
        has_coords = self.bolt_x_mm is not None and self.bolt_y_mm is not None
        has_pcd = self.bolt_pcd_mm is not None
        if not has_coords and not has_pcd:
            raise ValueError("B10-E003: bolt_pcd_mm o bolt_x_mm/bolt_y_mm requerido")
        if has_coords:
            if len(self.bolt_x_mm) != self.bolt_count or len(self.bolt_y_mm) != self.bolt_count:
                raise ValueError("B10-E004: longitud de coordenadas no coincide con bolt_count")
        return self


class AnchorPatternResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assembly_id: UUID
    pattern_label: str
    bolt_count: int
    bolt_pcd_mm: Optional[float]
    bolt_x_mm: Optional[List[float]]
    bolt_y_mm: Optional[List[float]]
    orientation_deg: float
    position_tolerance_mm: float


class AnchorRodRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    pattern_id: UUID
    rod_index: int = Field(..., ge=0)
    rod_type: AnchorRodType
    material_grade: str = "4.8"
    nominal_diameter_mm: float = Field(..., gt=0, le=100)
    thread_pitch_mm: Optional[float] = None
    total_length_mm: float = Field(..., gt=0)
    embedment_depth_mm: float = Field(..., gt=0)
    hook_length_mm: Optional[float] = None
    hook_radius_mm: Optional[float] = None
    end_plate_diameter_mm: Optional[float] = None
    free_length_mm: Optional[float] = None
    fy_mpa: float = Field(..., gt=0)
    fu_mpa: float = Field(..., gt=0)
    coating: Optional[str] = None

    @model_validator(mode="after")
    def check_hook_fields(self) -> "AnchorRodRequest":
        if self.rod_type in (AnchorRodType.L, AnchorRodType.J):
            if self.hook_length_mm is None:
                raise ValueError("B10-E005: hook_length_mm requerido para tipo L/J")
            if self.hook_radius_mm is None:
                raise ValueError("B10-E006: hook_radius_mm requerido para tipo L/J")
        return self

    @model_validator(mode="after")
    def check_embedment_lt_total(self) -> "AnchorRodRequest":
        if self.embedment_depth_mm >= self.total_length_mm:
            raise ValueError("B10-E007: embedment_depth_mm debe ser menor que total_length_mm")
        return self


class AnchorRodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pattern_id: UUID
    rod_index: int
    rod_type: AnchorRodType
    nominal_diameter_mm: float
    embedment_depth_mm: float
    fy_mpa: float
    fu_mpa: float
    util_tension: Optional[float]
    util_shear: Optional[float]
    util_interaction: Optional[float]
    axial_stiffness_kn_mm: Optional[float]


# ---------------------------------------------------------------------------
# Post-installed anchor
# ---------------------------------------------------------------------------

class PostInstalledAnchorRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    assembly_id: UUID
    anchor_index: int = Field(..., ge=0)
    post_type: PostInstalledType
    manufacturer: str
    product_name: str
    eta_document: str = Field(..., min_length=3)
    eta_edition: Optional[str] = None
    nominal_diameter_mm: float = Field(..., gt=0)
    drill_diameter_mm: float = Field(..., gt=0)
    embedment_depth_mm: float = Field(..., gt=0)
    concrete_condition: ConcreteCondition = ConcreteCondition.CRACKED
    fck_mpa: float = Field(..., gt=0)
    temperature_max_c: Optional[float] = None
    installation_torque_nm: Optional[float] = None
    cure_time_hours: Optional[float] = None

    @model_validator(mode="after")
    def check_chemical_cure(self) -> "PostInstalledAnchorRequest":
        if self.post_type in (PostInstalledType.CHEMICAL_THREADED,
                              PostInstalledType.CHEMICAL_SPECIAL):
            if self.cure_time_hours is None:
                raise ValueError("B10-E008: cure_time_hours requerido para anclaje químico")
        return self


class PostInstalledAnchorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assembly_id: UUID
    anchor_index: int
    post_type: PostInstalledType
    manufacturer: str
    product_name: str
    eta_document: str
    nominal_diameter_mm: float
    embedment_depth_mm: float
    fck_mpa: float
    NRd_c_kn: Optional[float]
    NRd_p_kn: Optional[float]
    VRd_c_kn: Optional[float]
    util_tension: Optional[float]
    util_shear: Optional[float]
    util_interaction: Optional[float]


# ---------------------------------------------------------------------------
# Grout layer
# ---------------------------------------------------------------------------

class GroutLayerRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    assembly_id: UUID
    grout_type: GroutType = GroutType.LEVELING_NUTS_THEN_GROUT
    product_name: Optional[str] = None
    thickness_mm: float = Field(50.0, gt=0, le=300)
    fck_mortar_mpa: float = Field(..., gt=0)
    elastic_modulus_mpa: Optional[float] = None

    @model_validator(mode="after")
    def check_special_grout_approval(self) -> "GroutLayerRequest":
        if self.grout_type == GroutType.SPECIAL_NO_GROUT and self.product_name is None:
            raise ValueError("B10-E009: sistema sin mortero requiere product_name con referencia de validación")
        return self


class GroutLayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assembly_id: UUID
    grout_type: GroutType
    thickness_mm: float
    fck_mortar_mpa: float
    sigma_Ed_mpa: Optional[float]
    sigma_Rd_mpa: Optional[float]
    util_bearing: Optional[float]


# ---------------------------------------------------------------------------
# Shear key
# ---------------------------------------------------------------------------

class ShearKeyRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    assembly_id: UUID
    shape: str = "RECTANGULAR"
    width_mm: float = Field(..., gt=0)
    height_mm: float = Field(..., gt=0)
    depth_mm: float = Field(..., gt=0)
    eccentricity_mm: float = 0.0
    material_grade: str = "S355"
    fy_mpa: float = Field(355.0, gt=0)
    weld_throat_mm: Optional[float] = None
    Vx_design_kn: Optional[float] = None
    Vy_design_kn: Optional[float] = None


# ---------------------------------------------------------------------------
# Contact solver request/response
# ---------------------------------------------------------------------------

class ContactSolverRequest(BaseModel):
    assembly_id: UUID
    combination_id: str
    N_kn: float
    Vy_kn: float
    Vz_kn: float
    T_knm: float
    My_knm: float
    Mz_knm: float
    plate_width_mm: float = Field(..., gt=0)
    plate_length_mm: float = Field(..., gt=0)
    plate_thickness_mm: float = Field(..., gt=0)
    bolt_x_mm: List[float]
    bolt_y_mm: List[float]
    bolt_stiffness_kn_mm: float = Field(..., gt=0)
    mortar_modulus_mpa: float = Field(20000.0, gt=0)
    mortar_thickness_mm: float = Field(50.0, gt=0)
    max_iterations: int = Field(200, ge=10, le=5000)
    tolerance_force: float = Field(1e-4, gt=0)
    tolerance_area: float = Field(0.001, gt=0)  # relative


class ContactSolverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assembly_id: UUID
    combination_id: str
    contact_state: ContactState
    contact_area_mm2: Optional[float]
    sigma_max_mpa: Optional[float]
    sigma_avg_mpa: Optional[float]
    neutral_axis_dist_mm: Optional[float]
    max_bolt_tension_kn: Optional[float]
    max_bolt_shear_kn: Optional[float]
    iterations: Optional[int]
    converged: bool
    equilibrium_error: Optional[float]
    rotation_rad: Optional[float]
    horizontal_slip_mm: Optional[float]
    force_per_bolt: Optional[List[Dict[str, float]]]


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

class OptimizationWeights(BaseModel):
    w_cost: float = Field(0.4, ge=0, le=1)
    w_mass: float = Field(0.2, ge=0, le=1)
    w_co2: float = Field(0.2, ge=0, le=1)
    w_risk: float = Field(0.2, ge=0, le=1)

    @model_validator(mode="after")
    def check_weights_sum(self) -> "OptimizationWeights":
        total = self.w_cost + self.w_mass + self.w_co2 + self.w_risk
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"B10-E010: pesos deben sumar 1.0, suma actual={total:.6f}")
        return self


class OptimizationRequest(BaseModel):
    assembly_id: UUID
    weights: OptimizationWeights = OptimizationWeights()
    max_candidates: int = Field(20, ge=1, le=200)
    allow_special: bool = False


class OptimizeSolution(BaseModel):
    label: str                   # e.g. "RECOMMENDED", "MIN_COST", "MIN_MASS", "MIN_CO2", "MIN_RISK"
    plate_id: Optional[UUID]
    pattern_label: str
    bolt_count: int
    bolt_diameter_mm: float
    plate_thickness_mm: float
    total_cost_eur: float
    total_mass_kg: float
    total_co2_kg: float
    risk_score: float
    score: float
    util_governing: float
    is_standard: bool


class OptimizationResponse(BaseModel):
    assembly_id: UUID
    solutions: List[OptimizeSolution]
    pareto_count: int
    special_activated: bool


# ---------------------------------------------------------------------------
# Concrete failure
# ---------------------------------------------------------------------------

class ConcreteFailureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assembly_id: UUID
    combination_id: str
    failure_mode: ConcreteFailureMode
    NEd_kn: Optional[float]
    VEd_kn: Optional[float]
    NRd_kn: Optional[float]
    VRd_kn: Optional[float]
    util: Optional[float]
    governing: bool
    factors: Optional[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Market reference
# ---------------------------------------------------------------------------

class MarketAnchorSearchRequest(BaseModel):
    anchor_family: AnchorFamily
    post_type: Optional[PostInstalledType] = None
    nominal_diameter_mm: Optional[float] = None
    fck_min_mpa: Optional[float] = None
    concrete_condition: Optional[ConcreteCondition] = None
    homologation_status: MarketHomologationStatus = MarketHomologationStatus.HOMOLOGATED
    limit: int = Field(50, ge=1, le=200)


class MarketAnchorApproveRequest(BaseModel):
    approved_by: str = Field(..., min_length=2)

    @model_validator(mode="after")
    def check_approver(self) -> "MarketAnchorApproveRequest":
        if not self.approved_by.strip():
            raise ValueError("B10-E011: approved_by no puede estar vacío")
        return self


# ---------------------------------------------------------------------------
# Foundation interface
# ---------------------------------------------------------------------------

class FoundationInterfaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assembly_id: UUID
    N_max_kn: Optional[float]
    N_min_kn: Optional[float]
    Vx_max_kn: Optional[float]
    Vy_max_kn: Optional[float]
    T_max_knm: Optional[float]
    Mx_max_knm: Optional[float]
    My_max_knm: Optional[float]
    min_concrete_thickness_mm: Optional[float]
    min_edge_distance_x_mm: Optional[float]
    min_edge_distance_y_mm: Optional[float]
    min_fck_mpa: Optional[float]
    rebar_requirement: Optional[str]
    stiffness_matrix_6x6: Optional[List[List[float]]]
    snapshot_hash: Optional[str]
