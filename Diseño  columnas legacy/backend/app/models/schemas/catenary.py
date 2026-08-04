"""
Salvi Studio · Columns — Fase 16: Schemas Pydantic v2 para la capa API.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Schemas de creación / entrada ────────────────────────────────────────────

class CableSystemCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    typology: str = Field(..., pattern="^C[1-8]$")
    max_cables: int = Field(6, ge=1, le=6)
    location_data: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class CableLineCreate(BaseModel):
    system_id: uuid.UUID
    code: str = Field(..., max_length=50)
    material_id: Optional[uuid.UUID] = None
    diameter_mm: float = Field(..., gt=0)
    area_mm2: Optional[float] = None
    e_mpa: float = Field(..., gt=0)
    alpha_k: float = Field(12e-6, gt=0)
    mass_kg_m: float = Field(..., gt=0)
    mbl_kn: float = Field(..., gt=0)
    data_quality: str = "ESTIMATED"
    meta: Dict[str, Any] = Field(default_factory=dict)


class CableSpanCreate(BaseModel):
    line_id: uuid.UUID
    span_index: int = Field(..., ge=0)
    anchor_a_id: uuid.UUID
    anchor_b_id: uuid.UUID
    length_m: float = Field(..., gt=0.5, le=200)
    height_diff_m: float = 0.0
    distributed_load_n_m: float = Field(..., gt=0)
    point_loads: List[Dict[str, Any]] = Field(default_factory=list)
    data_quality: str = "ESTIMATED"


class CableAnchorCreate(BaseModel):
    system_id: uuid.UUID
    anchor_type: str = Field(..., pattern="^(COLUMN|FACADE|INDEPENDENT|EXTERNAL)$")
    structure_id: Optional[uuid.UUID] = None
    x_m: float
    y_m: float
    z_m: float
    stiffness_kn_m: Optional[float] = None
    data_quality: str = "ESTIMATED"


class SuspendedItemCreate(BaseModel):
    span_id: uuid.UUID
    label: str = Field(..., max_length=100)
    item_type: str = "LUMINAIRE"
    position_m: float = Field(..., ge=0)
    mass_kg: float = Field(..., gt=0)
    wind_area_m2: float = Field(0.0, ge=0)
    cd: float = Field(1.2, gt=0)
    luminaire_id: Optional[uuid.UUID] = None
    data_quality: str = "ESTIMATED"


class TensioningPlanCreate(BaseModel):
    system_id: uuid.UUID
    method: str = Field(..., pattern="^(FORCE|SAG|CUT_LENGTH|MIN_CLEARANCE|TENSOR_DISPLACEMENT|AS_BUILT)$")
    target_value: float
    target_unit: str = Field("kN", max_length=5)
    tolerance_pct: float = Field(2.0, gt=0)
    t_install_c: float = 15.0
    tensor_stroke_mm: Optional[float] = None
    sequence: List[Dict[str, Any]] = Field(default_factory=list)


class CableStateCreate(BaseModel):
    system_id: uuid.UUID
    label: str = Field(..., max_length=100)
    combination_type: str = Field("ELS", pattern="^(ELU|ELS|ELS_FREC|ACC)$")
    temperature_c: float
    wind_speed_ms: float = 0.0
    wind_angle_deg: float = 0.0
    ice_load_n_m: float = 0.0
    snow_load_kpa: float = 0.0
    accidental_code: Optional[str] = None
    accidental_data: Dict[str, Any] = Field(default_factory=dict)


class InterpretRequest(BaseModel):
    """Solicitud de interpretación NL del sistema de cables."""
    text: str = Field(..., max_length=4000)
    language: str = "es"


class AnalysisRequest(BaseModel):
    state_ids: List[uuid.UUID] = Field(..., min_length=1)
    coupling_strategy: str = Field("PARTITIONED",
        pattern="^(MONOLITHIC|PARTITIONED|STIFFNESS_EQUIV|FIXED_SUPPORT)$")
    max_iterations: int = Field(200, ge=10, le=5000)
    tol_residual: float = Field(1e-6, gt=0)


class OptimizationRequest(BaseModel):
    objectives: List[str] = Field(default_factory=lambda: ["cost", "weight"])
    constraints: Dict[str, Any] = Field(default_factory=dict)
    n_alternatives: int = Field(5, ge=1, le=20)


class AsBuiltCreate(BaseModel):
    span_id: uuid.UUID
    measured_at: datetime
    technician: str = Field(..., max_length=100)
    t_measure_c: float
    method: str = Field(..., max_length=30)
    sag_measured_m: Optional[float] = None
    tension_measured_kn: Optional[float] = None
    clearance_measured_m: Optional[float] = None
    uncertainty_m: Optional[float] = None
    comments: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)


# ── Schemas de respuesta ─────────────────────────────────────────────────────

class CableSystemRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    typology: str
    state: str
    max_cables: int
    geometry_hash: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CableAnalysisRunRead(BaseModel):
    id: uuid.UUID
    system_id: uuid.UUID
    run_state: str
    converged: Optional[bool] = None
    iterations_used: Optional[int] = None
    residual_final: Optional[float] = None
    error_code: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ValidationResult(BaseModel):
    passed: bool
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    info: List[Dict[str, Any]] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    pareto_front: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_id: Optional[str] = None
