"""
Salvi Studio · Columns — Schemas Pydantic Fase 8: Detalles Locales.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from app.models.db.details import (
    OpeningType, DetailRoute, ReinforcementFamily, WeldProcess,
    DetailCheckStatus, EquipmentCategory, FEAStatus, DetailReleaseLevel,
)


# ── Opening ───────────────────────────────────────────────────────────────────

class OpeningCreate(BaseModel):
    design_id: str
    opening_type: OpeningType
    station_bottom_m: float = Field(..., ge=0.0)
    station_top_m: float = Field(..., gt=0.0)
    width_mm: float = Field(..., gt=0.0)
    height_mm: float = Field(..., gt=0.0)
    corner_radius_mm: float = Field(0.0, ge=0.0)
    orientation_deg: float = Field(0.0, ge=0.0, lt=360.0)
    D_ext_mm: Optional[float] = Field(None, gt=0.0)
    t_wall_mm: Optional[float] = Field(None, gt=0.0)
    tol_width_mm: float = Field(1.0, ge=0.0)
    tol_height_mm: float = Field(1.0, ge=0.0)
    tol_position_mm: float = Field(2.0, ge=0.0)
    tol_corner_radius_mm: float = Field(0.5, ge=0.0)

    @model_validator(mode="after")
    def check_stations(self):
        if self.station_top_m <= self.station_bottom_m:
            raise ValueError("LOC-GEO-001: station_top_m debe ser mayor que station_bottom_m")
        return self


class OpeningValidationResult(BaseModel):
    route: DetailRoute
    status: DetailCheckStatus
    blocking_step: Optional[int] = None
    decision_trace: List[str]
    geometric_hash: str
    errors: List[str] = []
    warnings: List[str] = []


# ── Sección local ─────────────────────────────────────────────────────────────

class NetSectionRequest(BaseModel):
    D_ext_mm: float = Field(..., gt=0.0)
    D_int_mm: float = Field(..., gt=0.0)
    width_mm: float = Field(..., gt=0.0)
    height_mm: float = Field(..., gt=0.0)
    orientation_deg: float = Field(0.0, ge=0.0, lt=360.0)
    include_reinforcement: bool = False
    reinforcement_family: Optional[ReinforcementFamily] = None
    reinforcement_thickness_mm: Optional[float] = None
    reinforcement_width_mm: Optional[float] = None
    contrast_tolerance_pct: float = Field(0.5, gt=0.0)


class NetSectionResult(BaseModel):
    A_gross_m2: float
    A_net_m2: float
    A_reduction_pct: float
    centroid_x_m: float
    centroid_y_m: float
    Iy_net_m4: float
    Iz_net_m4: float
    Iyz_net_m4: float
    J_net_m4: float
    alpha_principal_deg: float
    I1_m4: float
    I2_m4: float
    Wel_y_m3: float
    Wel_z_m3: float
    contrast_delta_pct: float
    contrast_passed: bool
    governing_rule: str
    method: str


# ── Verificaciones locales ────────────────────────────────────────────────────

class LocalCheckRequest(BaseModel):
    D_ext_mm: float = Field(..., gt=0.0)
    t_wall_mm: float = Field(..., gt=0.0)
    width_mm: float = Field(..., gt=0.0)
    height_mm: float = Field(..., gt=0.0)
    fy_mpa: float = Field(..., gt=0.0)
    E_mpa: float = Field(210000.0, gt=0.0)
    gamma_M0: float = Field(1.0, gt=0.0)
    N_ed_kn: float = Field(0.0)
    My_ed_knm: float = Field(0.0)
    Mz_ed_knm: float = Field(0.0)
    V_ed_kn: float = Field(0.0)
    T_ed_knm: float = Field(0.0)
    orientation_deg: float = Field(0.0)


class LocalCheckResult(BaseModel):
    check_type: str
    status: DetailCheckStatus
    demand: float
    resistance: float
    utilization: float
    unit: str
    governing_rule: str
    error_code: Optional[str] = None
    intermediate_values: Dict[str, Any] = {}


class LigamentCheckRequest(BaseModel):
    b_free_mm: float = Field(..., gt=0.0)
    t_mm: float = Field(..., gt=0.0)
    fy_mpa: float = Field(..., gt=0.0)
    E_mpa: float = Field(210000.0, gt=0.0)
    sigma_nom_mpa: float = Field(0.0)
    sigma_shear_mpa: float = Field(0.0)
    gamma_M1: float = Field(1.0, gt=0.0)


class PanelBucklingRequest(BaseModel):
    a_mm: float = Field(..., gt=0.0)   # menor dimensión libre
    b_mm: float = Field(..., gt=0.0)   # mayor dimensión libre
    t_mm: float = Field(..., gt=0.0)
    E_mpa: float = Field(210000.0, gt=0.0)
    nu: float = Field(0.3)
    sigma_cr_type: str = Field("COMPRESSION")  # "COMPRESSION" | "SHEAR"


# ── Soldaduras ────────────────────────────────────────────────────────────────

class WeldSegment(BaseModel):
    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float
    throat_mm: float = Field(..., gt=0.0)


class WeldGroupRequest(BaseModel):
    segments: List[WeldSegment] = Field(..., min_length=1)
    weld_process: WeldProcess
    fu_mpa: float = Field(..., gt=0.0)
    fatigue_category_mpa: Optional[float] = None
    gamma_M2: float = Field(1.25, gt=0.0)
    beta_w: float = Field(0.8, gt=0.0)
    # Cargas aplicadas al grupo
    Fx_kn: float = Field(0.0)
    Fy_kn: float = Field(0.0)
    M_knm: float = Field(0.0)   # momento torsor en plano del grupo


class WeldGroupResult(BaseModel):
    total_length_mm: float
    centroid_x_mm: float
    centroid_y_mm: float
    Ip_polar_mm4: float
    f_res_max_n_mm: float     # fuerza resultante máxima [N/mm]
    capacity_n_mm: float      # capacidad del cordón [N/mm]
    utilization: float
    status: DetailCheckStatus
    governing_rule: str
    intermediate_values: Dict[str, Any] = {}


# ── Refuerzo ──────────────────────────────────────────────────────────────────

class ReinforcementCandidate(BaseModel):
    family: ReinforcementFamily
    material_code: str
    thickness_mm: float
    width_mm: Optional[float] = None
    depth_mm: Optional[float] = None
    extension_top_mm: float = 0.0
    extension_bottom_mm: float = 0.0
    cost_eur: float
    mass_kg: float
    co2_kg: float
    feasible: bool = True
    transportable: bool = True
    pareto_dominated: Optional[bool] = None
    rejection_reason: Optional[str] = None
    max_utilization: Optional[float] = None


class ReinforcementOptimizationRequest(BaseModel):
    candidates: List[dict] = Field(..., min_length=1)


class ReinforcementOptimizationResult(BaseModel):
    pareto_size: int
    min_cost: Optional[dict] = None
    min_weight: Optional[dict] = None
    min_co2: Optional[dict] = None
    balanced: Optional[dict] = None


# ── Equipos y accesibilidad ───────────────────────────────────────────────────

class EquipmentCreate(BaseModel):
    equipment_type: EquipmentCategory
    reference: Optional[str] = None
    length_mm: float = Field(..., gt=0.0)
    width_mm: float = Field(..., gt=0.0)
    height_mm: float = Field(..., gt=0.0)
    mass_kg: float = Field(..., gt=0.0)
    cg_json: Dict[str, float] = {}
    service_volume_json: Dict[str, float] = {}
    extraction_volume_json: Dict[str, float] = {}
    ip_rating: Optional[str] = None
    ik_rating: Optional[str] = None


class AccessibilityCheckRequest(BaseModel):
    opening_width_mm: float = Field(..., gt=0.0)
    opening_height_mm: float = Field(..., gt=0.0)
    equipment_list: List[EquipmentCreate]
    tool_clearance_required_mm: float = Field(50.0, ge=0.0)
    cable_radius_min_mm: float = Field(25.0, ge=0.0)
    available_column_D_int_mm: float = Field(..., gt=0.0)


class AccessibilityCheckResult(BaseModel):
    accessible: bool
    tool_clearance_ok: bool
    cable_radius_ok: bool
    all_equipment_fit: bool
    extraction_sequence: List[str] = []
    blocking_equipment: Optional[str] = None
    error_code: Optional[str] = None
    governing_rule: str


# ── FEA local ─────────────────────────────────────────────────────────────────

class FEAActivationCheck(BaseModel):
    multiple_openings_close: bool = False
    outside_formula_domain: bool = False
    high_torsion: bool = False
    complex_open_section: bool = False
    discontinuous_reinforcement: bool = False
    near_joint: bool = False
    analytic_utilization: float = Field(0.0, ge=0.0)
    analytic_threshold: float = Field(0.90, gt=0.0)
    new_detail_no_test: bool = False


class FEAActivationResult(BaseModel):
    fea_required: bool
    activation_reasons: List[str]
    route: DetailRoute


class FEAContractResult(BaseModel):
    model_valid: bool
    convergence_ratio: float
    equilibrium_residual_pct: float
    max_stress_mpa: float
    max_hotspot_mpa: float
    buckling_factor: float
    comparison_delta_pct: float
    status: FEAStatus
    errors: List[str] = []
    governing_rule: str


# ── Normativa y liberación ────────────────────────────────────────────────────

class DetailNormativeRequest(BaseModel):
    height_m: float = Field(..., gt=0.0)
    has_tested_family: bool = False
    within_analytic_domain: bool = True
    complex_geometry: bool = False
    new_detail: bool = False
    entry_complete: bool = True
    has_evidence: bool = True


class DetailNormativeResult(BaseModel):
    route: DetailRoute
    steps_passed: List[bool]
    blocking_step: Optional[int]
    decision_trace: List[str]
    input_hash: str


class DetailReleaseCreate(BaseModel):
    opening_id: str
    release_level: DetailReleaseLevel
    all_checks_passed: bool
    approved_by: Optional[str] = None
    documents_json: Dict[str, Any] = {}

    @model_validator(mode="after")
    def check_m4_evidence(self):
        if self.release_level == DetailReleaseLevel.M4 and not self.all_checks_passed:
            raise ValueError("LOC-REL-001: nivel M4 requiere all_checks_passed=True")
        return self
