"""
Salvi Studio · Columns — Fase 17: Schemas Pydantic v2
Modelos de entrada/salida para la API de validación V&V.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Solicitudes de creación ───────────────────────────────────────────────────

class ValidationPlanCreate(BaseModel):
    project_id: uuid.UUID
    code: str = Field(..., max_length=64)
    title: str = Field(..., max_length=256)
    version: str = Field(default="0.1", max_length=32)
    validation_level: str = Field(default="V0")
    scope: Dict[str, Any] = Field(default_factory=dict)
    risks: Dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: Dict[str, Any] = Field(default_factory=dict)
    responsible: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class TestRunCreate(BaseModel):
    test_case_id: uuid.UUID
    environment: Optional[str] = None
    commit_hash: Optional[str] = None
    dataset_ref: Optional[str] = None
    inputs_override: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class PhysicalTestDatasetCreate(BaseModel):
    physical_test_id: uuid.UUID
    dataset_label: str = Field(..., max_length=128)
    raw_data: List[Dict[str, Any]] = Field(default_factory=list)
    channel_map: Dict[str, str] = Field(default_factory=dict)
    sampling_rate_hz: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class CorrelationCreate(BaseModel):
    physical_test_id: uuid.UUID
    module: str = Field(..., max_length=64)
    quantity: str = Field(..., max_length=64)
    predicted: List[float]
    measured: List[float]
    tolerance_target: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class QualificationEvaluateRequest(BaseModel):
    domain_id: uuid.UUID
    candidate: Dict[str, Any]   # valores a comprobar vs límites del dominio


class GateDecisionCreate(BaseModel):
    gate_id_row: uuid.UUID      # PK de release_gates17
    decision: str               # PASSED | BLOCKED
    decision_by: str
    provided_evidences: List[str] = Field(default_factory=list)
    blocking_ncms: List[str] = Field(default_factory=list)
    comments: Optional[str] = None


# ── Respuestas de lectura ─────────────────────────────────────────────────────

class ValidationPlanRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    title: str
    version: str
    validation_level: str
    status: str
    responsible: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestRunRead(BaseModel):
    id: uuid.UUID
    test_case_id: uuid.UUID
    run_state: str
    environment: Optional[str]
    commit_hash: Optional[str]
    computed_values: Dict[str, Any]
    error_codes: List[str]
    result_hash: Optional[str]
    evidence_level: str
    executed_at: datetime

    model_config = {"from_attributes": True}


class CorrelationResultRead(BaseModel):
    id: uuid.UUID
    physical_test_id: uuid.UUID
    module: str
    quantity: str
    n_points: int
    e_rel_max: Optional[float]
    e_rel_mean: Optional[float]
    rmse: Optional[float]
    bias: Optional[float]
    model_factor: Optional[float]
    uncertainty_u: Optional[float]
    tolerance_target: Optional[float]
    passed: bool
    decision: str
    evidence_level: str
    created_at: datetime

    model_config = {"from_attributes": True}


class QualificationEvaluateResult(BaseModel):
    domain_id: uuid.UUID
    candidate: Dict[str, Any]
    in_domain: bool
    violations: List[Dict[str, Any]]
    warnings: List[str]
    validation_level: str


class GateDecisionRead(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    gate_id: str
    gate_state: str
    decision_by: Optional[str]
    decision_at: Optional[datetime]
    blocking_ncms: List[str]
    comments: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class TraceabilityRead(BaseModel):
    req_id: str
    source: str
    description: str
    implementation_ref: Optional[str]
    test_case_ref: Optional[str]
    evidence_level: str
    criticality: str
    state: str
    evidence_refs: List[str]
    linked_test_runs: List[Dict[str, Any]]
