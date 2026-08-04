"""
Salvi Studio · Columns — Schemas Pydantic v2 Fase 4: Motor Estructural
"""
import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator

from app.models.db.structural import (
    AnalysisOrder, MeshProfile, ShearFormulation, MassModel,
    ElementType, SupportType, StructuralPropertySet,
    StructuralRunStatus, StructuralDiagnosticSeverity, EnvelopeScope,
    StructuralLoadType,
)


# ── Construcción de modelo ─────────────────────────────────────────────────────

class StructuralModelCreate(BaseModel):
    project_revision_id: uuid.UUID
    action_run_id: Optional[uuid.UUID] = None
    mesh_profile: MeshProfile = MeshProfile.STANDARD
    shear_formulation: ShearFormulation = ShearFormulation.TIMOSHENKO
    mass_model: MassModel = MassModel.CONSISTENT
    default_analysis_order: AnalysisOrder = AnalysisOrder.SECOND_ORDER
    modal_modes: Optional[int] = Field(default=None, ge=1, le=100)
    property_set: StructuralPropertySet = StructuralPropertySet.GROSS


class StructuralModelSummary(BaseModel):
    id: uuid.UUID
    project_revision_id: uuid.UUID
    status: str
    structural_model_hash: Optional[str] = None
    engine_version: str
    node_count: Optional[int] = None
    element_count: Optional[int] = None
    dof_count: Optional[int] = None
    build_time_s: Optional[float] = None
    mesh_profile: str
    property_set: str

    model_config = {"from_attributes": True}


# ── Validación de conectividad ─────────────────────────────────────────────────

class ModelValidationResult(BaseModel):
    model_id: uuid.UUID
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    system_size: Optional[int] = None
    condition_number: Optional[float] = None
    disconnected_components: int = 0
    rigid_body_modes: int = 0


# ── Ejecución de análisis ──────────────────────────────────────────────────────

class AnalysisRunCreate(BaseModel):
    model_id: uuid.UUID
    analysis_types: list[str] = Field(
        default=["LINEAR", "SECOND_ORDER"],
        description="Tipos de análisis a ejecutar",
    )
    analysis_order: AnalysisOrder = AnalysisOrder.SECOND_ORDER
    mesh_profile: MeshProfile = MeshProfile.STANDARD
    shear_formulation: ShearFormulation = ShearFormulation.TIMOSHENKO
    mass_model: MassModel = MassModel.CONSISTENT
    modal_modes: Optional[int] = Field(default=None, ge=1, le=100)
    buckling_modes: Optional[int] = Field(default=None, ge=1, le=20)

    # Tolerancias Newton-Raphson
    nl_tol_residual: float = Field(default=1e-6, gt=0, le=1e-3)
    nl_tol_displacement: float = Field(default=1e-6, gt=0, le=1e-3)
    nl_max_iterations: int = Field(default=50, ge=5, le=500)

    idempotency_key: Optional[str] = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_modal_requires_mass(self) -> "AnalysisRunCreate":
        if "MODAL" in self.analysis_types and self.modal_modes is None:
            self.modal_modes = 10  # default
        return self


class AnalysisRunSummary(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    status: StructuralRunStatus
    engine_version: str
    structural_model_hash: Optional[str] = None
    analysis_input_hash: Optional[str] = None
    analysis_types: list[str] = []
    system_size: Optional[int] = None
    condition_number: Optional[float] = None
    nl_iterations: Optional[int] = None
    nl_residual_final: Optional[float] = None
    preprocess_time_s: Optional[float] = None
    solve_time_s: Optional[float] = None
    postprocess_time_s: Optional[float] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class AnalysisRunManifest(BaseModel):
    run_id: uuid.UUID
    structural_model_hash: str
    analysis_input_hash: str
    solver_hash: str
    engine_version: str
    analysis_types: list[str]
    mesh_profile: str
    analysis_order: str
    modal_modes: Optional[int] = None
    buckling_modes: Optional[int] = None
    nl_tolerances: dict[str, float]
    timing: dict[str, Optional[float]]
    system_stats: dict[str, Any]


# ── Resultados nodales ─────────────────────────────────────────────────────────

class NodalResultResponse(BaseModel):
    node_id: uuid.UUID
    load_case_ref: str
    ux_m: float
    uy_m: float
    uz_m: float
    rx_rad: float
    ry_rad: float
    rz_rad: float
    u_horizontal_m: Optional[float] = None
    # Reacciones (solo en apoyos)
    rx_n: Optional[float] = None
    ry_n: Optional[float] = None
    rz_n: Optional[float] = None
    mrx_nm: Optional[float] = None
    mry_nm: Optional[float] = None
    mrz_nm: Optional[float] = None

    model_config = {"from_attributes": True}


class ResultsFilter(BaseModel):
    load_case_refs: Optional[list[str]] = None
    node_ids: Optional[list[uuid.UUID]] = None
    element_ids: Optional[list[uuid.UUID]] = None
    z_min_m: Optional[float] = None
    z_max_m: Optional[float] = None
    quantity: Optional[str] = None   # e.g. "My_nm", "ux_m"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=1000)


# ── Resultados de sección ──────────────────────────────────────────────────────

class SectionResultResponse(BaseModel):
    element_id: uuid.UUID
    load_case_ref: str
    xi: float
    z_global_m: Optional[float] = None
    n_n: float
    vy_n: float
    vz_n: float
    t_nm: float
    my_nm: float
    mz_nm: float
    curvature_y: Optional[float] = None
    curvature_z: Optional[float] = None

    model_config = {"from_attributes": True}


# ── Resultados modales ─────────────────────────────────────────────────────────

class ModalResultResponse(BaseModel):
    mode_number: int
    frequency_hz: float
    period_s: float
    eff_mass_x_kg: Optional[float] = None
    eff_mass_y_kg: Optional[float] = None
    eff_mass_z_kg: Optional[float] = None
    participation_x_pct: Optional[float] = None
    participation_y_pct: Optional[float] = None
    participation_z_pct: Optional[float] = None
    mode_description: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Resultados de pandeo ───────────────────────────────────────────────────────

class BucklingResultResponse(BaseModel):
    mode_number: int
    critical_factor: float
    load_case_ref: str
    critical_element_id: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}


# ── Envolventes ────────────────────────────────────────────────────────────────

class EnvelopeResponse(BaseModel):
    id: uuid.UUID
    scope: EnvelopeScope
    quantity: str
    sign: str
    value: float
    load_case_ref: Optional[str] = None
    combination_ref: Optional[str] = None
    wind_direction_deg: Optional[float] = None
    station_xi: Optional[float] = None
    element_id: Optional[uuid.UUID] = None
    node_id: Optional[uuid.UUID] = None
    governing_context: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class EnvelopeFilter(BaseModel):
    scope: Optional[EnvelopeScope] = None
    quantity: Optional[str] = None   # e.g. "My_nm"
    sign: Optional[str] = None       # "max" | "min"


# ── Diagnósticos ──────────────────────────────────────────────────────────────

class DiagnosticEventResponse(BaseModel):
    id: uuid.UUID
    severity: StructuralDiagnosticSeverity
    code: str
    message: str
    context: Optional[dict[str, Any]] = None
    metric_value: Optional[float] = None
    metric_unit: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Exportación ────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    format: str = Field(
        default="json",
        description="Formato de exportación: 'json', 'csv', 'nastran'",
    )

    @model_validator(mode="after")
    def validate_format(self) -> "ExportRequest":
        allowed = {"json", "csv", "nastran"}
        if self.format not in allowed:
            raise ValueError(f"Formato no soportado: {self.format}. Permitidos: {allowed}")
        return self


class ExportResponse(BaseModel):
    export_id: uuid.UUID
    run_id: uuid.UUID
    format: str
    structural_model_hash: str
    storage_key: str
    checksum: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Comparación de ejecuciones ────────────────────────────────────────────────

class RunCompareResponse(BaseModel):
    run_a_id: uuid.UUID
    run_b_id: uuid.UUID
    same_model_hash: bool
    same_input_hash: bool
    max_diff_ux_m: Optional[float] = None
    max_diff_uy_m: Optional[float] = None
    max_diff_uz_m: Optional[float] = None
    max_diff_my_nm: Optional[float] = None
    max_diff_mz_nm: Optional[float] = None
    max_diff_freq_hz: Optional[float] = None
    max_diff_critical_factor: Optional[float] = None
    within_tolerance: bool
    tolerance_pct: float = 0.5

    model_config = {"from_attributes": True}
