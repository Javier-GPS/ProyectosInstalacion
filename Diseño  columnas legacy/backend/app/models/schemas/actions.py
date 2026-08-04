"""
Salvi Studio · Columns — Schemas Pydantic v2: Acciones, Ubicación y Combinaciones (Fase 3)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

from app.models.db.actions import (
    EnvironmentType, GeoParameterType, DataConfidenceLevel, ConfirmationState,
    ActionType, CableActionState, ActionRunStatus, DiagnosticSeverity,
    LimitState, SpatialLoadType, AeroQuality,
)


# ── Location ───────────────────────────────────────────────────────────────────

class LocationCreate(BaseModel):
    project_revision_id: uuid.UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    country_code: str = Field(max_length=3)
    country_name: Optional[str] = None
    region: Optional[str] = None
    municipality: Optional[str] = None
    altitude_m: Optional[float] = None
    altitude_source: Optional[str] = None
    environment: Optional[EnvironmentType] = None
    project_life_years: Optional[int] = Field(default=None, gt=0)
    reference_date: Optional[datetime] = None


class LocationRead(BaseModel):
    id: uuid.UUID
    project_revision_id: uuid.UUID
    latitude: float
    longitude: float
    country_code: str
    country_name: Optional[str] = None
    region: Optional[str] = None
    municipality: Optional[str] = None
    altitude_m: Optional[float] = None
    altitude_source: Optional[str] = None
    environment: Optional[EnvironmentType] = None
    project_life_years: Optional[int] = None
    confirmation_state: ConfirmationState
    jurisdiction_json: Optional[dict[str, Any]] = None
    normative_set_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class LocationResolveRequest(BaseModel):
    """Solicitud de resolución de ubicación con propuesta automática de parámetros."""
    project_revision_id: uuid.UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_m: Optional[float] = None
    environment: Optional[EnvironmentType] = None
    project_life_years: Optional[int] = None
    reference_date: Optional[datetime] = None


class LocationResolveResponse(BaseModel):
    location: LocationRead
    proposed_parameters: list["GeoParameterRead"]
    normative_set: Optional[dict[str, Any]] = None
    warnings: list[str] = []
    coverage_status: dict[str, str] = {}  # {parameter_type: "A"|"B"|...|"E"}


# ── GeoParameter ──────────────────────────────────────────────────────────────

class GeoParameterRead(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    parameter_type: GeoParameterType
    name: str
    proposed_value: Optional[float] = None
    adopted_value: Optional[float] = None
    unit: Optional[str] = None
    source_id: Optional[str] = None
    source_version: Optional[str] = None
    confidence: DataConfidenceLevel
    confirmation_state: ConfirmationState
    justification: Optional[str] = None

    model_config = {"from_attributes": True}


class GeoParameterOverride(BaseModel):
    parameter_id: uuid.UUID
    adopted_value: float
    justification: str
    evidence: Optional[str] = None


# ── Aerodynamic Property ───────────────────────────────────────────────────────

class AerodynamicPropertyCreate(BaseModel):
    component_id: uuid.UUID
    component_type: str
    orientation_deg: Optional[float] = None
    area_m2: Optional[float] = None
    cd: Optional[float] = None
    polar_table_json: Optional[dict[str, Any]] = None
    method: str = "geometric_projection"
    quality: AeroQuality = AeroQuality.C
    source: Optional[str] = None
    cp_local_json: Optional[dict[str, Any]] = None


class AerodynamicPropertyRead(BaseModel):
    id: uuid.UUID
    component_id: uuid.UUID
    component_type: str
    orientation_deg: Optional[float] = None
    area_m2: Optional[float] = None
    cd: Optional[float] = None
    method: str
    quality: AeroQuality
    source: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Cable Action ───────────────────────────────────────────────────────────────

class CableActionCreate(BaseModel):
    cable_id: Optional[uuid.UUID] = None
    cable_identifier: str = Field(max_length=20)
    anchor_z_m: float
    tension_n: float = Field(ge=0)
    azimuth_rad: float = Field(ge=0, lt=6.2832)  # [0, 2π), CAT-001: numérico obligatorio
    elevation_rad: float = 0.0
    cable_state: CableActionState = CableActionState.ACTIVE_PERMANENT
    source: Optional[str] = None
    uncertainty_pct: Optional[float] = None


class CableActionRead(BaseModel):
    id: uuid.UUID
    action_run_id: uuid.UUID
    cable_identifier: str
    anchor_z_m: float
    tension_n: float
    azimuth_rad: float
    elevation_rad: float
    force_vector_json: Optional[dict[str, Any]] = None
    cable_state: CableActionState

    model_config = {"from_attributes": True}


# ── Load Case ──────────────────────────────────────────────────────────────────

class LoadCaseRead(BaseModel):
    id: uuid.UUID
    action_run_id: uuid.UUID
    code: str
    label: Optional[str] = None
    direction_deg: Optional[float] = None
    action_types_json: dict[str, Any]
    case_hash: Optional[str] = None
    is_base_direction: bool
    is_refined: bool

    model_config = {"from_attributes": True}


# ── Combination Template ───────────────────────────────────────────────────────

class CombinationTemplateRead(BaseModel):
    id: uuid.UUID
    code: str
    edition: str
    country_code: Optional[str] = None
    limit_state: LimitState
    label: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ── Combination Instance ───────────────────────────────────────────────────────

class CombinationInstanceRead(BaseModel):
    id: uuid.UUID
    action_run_id: uuid.UUID
    load_case_id: uuid.UUID
    template_id: Optional[uuid.UUID] = None
    limit_state: LimitState
    label: Optional[str] = None
    leading_action: Optional[ActionType] = None
    normalized_terms_json: dict[str, Any]
    instance_hash: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Spatial Load ───────────────────────────────────────────────────────────────

class SpatialLoadRead(BaseModel):
    id: uuid.UUID
    action_run_id: uuid.UUID
    load_case_id: Optional[uuid.UUID] = None
    target_id: uuid.UUID
    target_type: str
    station_start_m: Optional[float] = None
    station_end_m: Optional[float] = None
    load_type: SpatialLoadType
    coordinate_system: str
    vector_json: Optional[dict[str, Any]] = None
    law_json: Optional[dict[str, Any]] = None
    action_type: Optional[ActionType] = None
    direction_deg: Optional[float] = None

    model_config = {"from_attributes": True}


# ── Mass Item ──────────────────────────────────────────────────────────────────

class MassItemRead(BaseModel):
    id: uuid.UUID
    component_id: uuid.UUID
    component_type: str
    mass_kg: float
    cg_global_json: Optional[dict[str, Any]] = None
    source: str
    includes_hardware: bool
    additional_margin_pct: Optional[float] = None

    model_config = {"from_attributes": True}


# ── Action Diagnostic ──────────────────────────────────────────────────────────

class ActionDiagnosticRead(BaseModel):
    id: uuid.UUID
    code: str
    severity: DiagnosticSeverity
    message: str
    field_path: Optional[str] = None
    normative_ref: Optional[str] = None
    accepted_by_id: Optional[uuid.UUID] = None
    accepted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DiagnosticAcceptRequest(BaseModel):
    diagnostic_id: uuid.UUID
    acceptance_note: str


# ── User Override ──────────────────────────────────────────────────────────────

class UserOverrideCreate(BaseModel):
    parameter_ref: str
    adopted_value: Optional[float] = None
    adopted_value_json: Optional[dict[str, Any]] = None
    reason: str
    evidence: Optional[str] = None
    requires_ot_approval: bool = False


class UserOverrideRead(BaseModel):
    id: uuid.UUID
    parameter_ref: str
    original_value: Optional[float] = None
    adopted_value: Optional[float] = None
    reason: str
    author_id: uuid.UUID
    requires_ot_approval: bool
    approved_by_id: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}


# ── Action Run ─────────────────────────────────────────────────────────────────

class ActionRunCreate(BaseModel):
    project_revision_id: uuid.UUID
    location_id: uuid.UUID
    combination_template_id: Optional[uuid.UUID] = None
    sweep_config_json: Optional[dict[str, Any]] = None
    # Optional: extra cables defined at run time
    additional_cables: list[CableActionCreate] = []
    idempotency_key: Optional[str] = None


class ActionRunRead(BaseModel):
    id: uuid.UUID
    project_revision_id: uuid.UUID
    location_id: Optional[uuid.UUID] = None
    status: ActionRunStatus
    geometry_hash: Optional[str] = None
    input_hash: Optional[str] = None
    outputs_hash: Optional[str] = None
    engine_version: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    arq_job_id: Optional[str] = None
    idempotency_key: Optional[str] = None

    model_config = {"from_attributes": True}


class ActionRunManifest(BaseModel):
    """Manifest completo de una ejecución de acciones (DAT-303)."""
    action_run: ActionRunRead
    location: Optional[LocationRead] = None
    geo_parameters: list[GeoParameterRead] = []
    cable_actions: list[CableActionRead] = []
    load_cases: list[LoadCaseRead] = []
    combination_instances: list[CombinationInstanceRead] = []
    mass_items: list[MassItemRead] = []
    diagnostics: list[ActionDiagnosticRead] = []
    user_overrides: list[UserOverrideRead] = []
    summary: dict[str, Any] = {}


# ── Validate & Sensitivity ─────────────────────────────────────────────────────

class ActionValidateResponse(BaseModel):
    project_revision_id: uuid.UUID
    is_complete: bool
    blocking_issues: list[str] = []
    warnings: list[str] = []
    missing_fields: list[str] = []
    data_quality_summary: dict[str, str] = {}  # {parameter: confidence}


class SensitivityRequest(BaseModel):
    """Análisis de sensibilidad: ±% en variables críticas (AC-26)."""
    wind_variation_pct: Optional[float] = Field(default=None, ge=-50, le=50)
    cable_tension_variation_pct: Optional[float] = Field(default=None, ge=-50, le=50)
    mass_variation_pct: Optional[float] = Field(default=None, ge=-50, le=50)
    cd_variation_pct: Optional[float] = Field(default=None, ge=-50, le=50)


class SensitivityResponse(BaseModel):
    base_run_id: uuid.UUID
    variations: list[dict[str, Any]] = []
    dominant_parameter: Optional[str] = None
    summary: dict[str, Any] = {}
