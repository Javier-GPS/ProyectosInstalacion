"""
Salvi Studio · Columns — Schemas Pydantic Fase 13
Optimización Multiobjetivo y Diseño Especial
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class VariableTypeEnum:
    CONTINUOUS   = "CONTINUOUS"
    DISCRETE     = "DISCRETE"
    CATEGORICAL  = "CATEGORICAL"
    BOOLEAN      = "BOOLEAN"
    DERIVED      = "DERIVED"
    DEPENDENT    = "DEPENDENT"


class VariableModeEnum:
    FIXED       = "FIXED"
    SELECTABLE  = "SELECTABLE"
    OPTIMIZABLE = "OPTIMIZABLE"
    DERIVED     = "DERIVED"


class ConstraintClassEnum:
    NORMATIVA          = "NORMATIVA"
    DOMINIO            = "DOMINIO"
    GEOMETRICA         = "GEOMETRICA"
    FABRICACION        = "FABRICACION"
    TRANSPORTE_MONTAJE = "TRANSPORTE_MONTAJE"
    COMERCIAL          = "COMERCIAL"
    SOSTENIBILIDAD     = "SOSTENIBILIDAD"
    ROBUSTEZ           = "ROBUSTEZ"


VALID_CONSTRAINT_CLASSES = {
    "NORMATIVA", "DOMINIO", "GEOMETRICA", "FABRICACION",
    "TRANSPORTE_MONTAJE", "COMERCIAL", "SOSTENIBILIDAD", "ROBUSTEZ",
}
VALID_SEVERITIES       = {"HARD", "SOFT", "WARNING"}
VALID_OPT_STATUSES     = {"DRAFT", "RUNNING", "PAUSED", "COMPLETED", "CANCELLED", "FAILED"}
VALID_CANDIDATE_STATUSES = {"PENDING", "EVALUATING", "VALID", "REJECTED", "DOMINATED", "SELECTED"}
VALID_DIRECTIONS       = {"MINIMIZE", "MAXIMIZE"}
VALID_ROBUSTNESS_METHODS = {
    "DISCRETE_SCENARIOS", "INTERVALS", "LATIN_HYPERCUBE",
    "MONTE_CARLO", "ROBUST_OPTIMIZATION", "WORST_CASE",
}
VALID_INTERVIEW_STATES = {
    "NEW", "DISCOVERY", "ELICITATION", "CLARIFICATION",
    "REVIEW", "CONFIRMED", "BLOCKED", "READY",
}
VALID_QUESTION_PRIORITIES = {"P0", "P1", "P2", "P3", "DERIVABLE"}
VALID_FIELD_STATUSES = {
    "EXACT", "ESTIMATED", "RANGE", "UNKNOWN", "CONFLICT", "PENDING_CONFIRMATION",
}
VALID_LANGUAGES = {"es", "en", "fr", "ca", "it", "pt"}
VALID_VARIABLE_TYPES = {"CONTINUOUS", "DISCRETE", "CATEGORICAL", "BOOLEAN", "DERIVED", "DEPENDENT"}
VALID_VARIABLE_MODES = {"FIXED", "SELECTABLE", "OPTIMIZABLE", "DERIVED"}


# ── OptimizationProfile ───────────────────────────────────────────────────────

class OptimizationProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    user_role: str = Field(..., min_length=1, max_length=60)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    limits: Dict[str, Any] = Field(default_factory=dict)


class OptimizationProfileOut(OptimizationProfileCreate):
    id: UUID
    published_version: int
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── OptimizationRun ───────────────────────────────────────────────────────────

class ObjectiveSpec(BaseModel):
    code: str = Field(..., min_length=1, max_length=60)
    direction: str = Field(default="MINIMIZE")
    weight: float = Field(default=1.0, ge=0.0)

    @field_validator("direction")
    @classmethod
    def check_direction(cls, v: str) -> str:
        if v not in VALID_DIRECTIONS:
            raise ValueError(f"direction must be one of {VALID_DIRECTIONS}")
        return v


class OptimizationRunCreate(BaseModel):
    project_revision_id: Optional[UUID] = None
    profile_id: Optional[UUID] = None
    objectives: List[ObjectiveSpec] = Field(default_factory=list)
    algorithm_config: Dict[str, Any] = Field(default_factory=dict)
    algorithm_version: str = Field(default="1.0.0", max_length=40)
    seed: Optional[int] = Field(default=None, ge=0)
    budget_evaluations: int = Field(default=1000, ge=1, le=100_000)
    created_by: Optional[str] = Field(default=None, max_length=120)

    @field_validator("objectives")
    @classmethod
    def check_objectives(cls, v: List[ObjectiveSpec]) -> List[ObjectiveSpec]:
        codes = [o.code for o in v]
        if len(codes) != len(set(codes)):
            raise ValueError("Duplicate objective codes")
        return v


class OptimizationRunOut(BaseModel):
    id: UUID
    project_revision_id: Optional[UUID]
    profile_id: Optional[UUID]
    objectives: List[Any]
    algorithm_version: str
    seed: Optional[int]
    status: str
    run_hash: Optional[str]
    result_hash: Optional[str]
    candidate_count: int
    pareto_count: int
    budget_evaluations: int
    elapsed_seconds: Optional[float]
    error_message: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── DesignVariable ─────────────────────────────────────────────────────────────

class DesignVariableCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    variable_type: str
    mode: str
    domain: Dict[str, Any] = Field(default_factory=dict)
    unit: Optional[str] = Field(default=None, max_length=30)
    dependency_expr: Optional[str] = None
    source: Optional[str] = Field(default=None, max_length=60)
    version: str = Field(default="1", max_length=20)

    @field_validator("variable_type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in VALID_VARIABLE_TYPES:
            raise ValueError(f"variable_type must be one of {VALID_VARIABLE_TYPES}")
        return v

    @field_validator("mode")
    @classmethod
    def check_mode(cls, v: str) -> str:
        if v not in VALID_VARIABLE_MODES:
            raise ValueError(f"mode must be one of {VALID_VARIABLE_MODES}")
        return v


class DesignVariableOut(DesignVariableCreate):
    id: UUID
    run_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── ConstraintDefinition ──────────────────────────────────────────────────────

class ConstraintDefinitionCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=60)
    constraint_class: str
    severity: str = Field(default="HARD")
    evaluator: Optional[str] = Field(default=None, max_length=120)
    limit_value: Optional[Dict[str, Any]] = None
    normative_reference: Optional[str] = Field(default=None, max_length=120)
    version: str = Field(default="1", max_length=20)

    @field_validator("constraint_class")
    @classmethod
    def check_class(cls, v: str) -> str:
        if v not in VALID_CONSTRAINT_CLASSES:
            raise ValueError(f"constraint_class must be one of {VALID_CONSTRAINT_CLASSES}")
        return v

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {VALID_SEVERITIES}")
        return v


class ConstraintDefinitionOut(ConstraintDefinitionCreate):
    id: UUID
    run_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── CandidateDesign ────────────────────────────────────────────────────────────

class CandidateDesignOut(BaseModel):
    id: UUID
    run_id: UUID
    parent_id: Optional[UUID]
    variables: Dict[str, Any]
    geometry_hash: Optional[str]
    candidate_hash: Optional[str]
    status: str
    rejection_reason: Optional[str]
    rejection_code: Optional[str]
    generation: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── CandidateEvaluation ────────────────────────────────────────────────────────

class CandidateEvaluationOut(BaseModel):
    id: UUID
    candidate_id: UUID
    solver_run_ids: List[Any]
    utilizations: Dict[str, Any]
    objective_values: Dict[str, float]
    constraint_results: Dict[str, Any]
    warnings: List[Any]
    evidence: Dict[str, Any]
    cost_eur: Optional[float]
    mass_kg: Optional[float]
    co2_kg: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── ParetoAlternative ─────────────────────────────────────────────────────────

class ParetoAlternativeOut(BaseModel):
    id: UUID
    run_id: UUID
    candidate_id: UUID
    dominance_rank: int
    crowding_distance: Optional[float]
    label: Optional[str]
    selected_reason: Optional[str]
    is_selected: bool
    selected_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class SelectAlternativeRequest(BaseModel):
    candidate_id: UUID
    reason: Optional[str] = None


# ── RobustnessScenario ────────────────────────────────────────────────────────

class RobustnessRequest(BaseModel):
    candidate_id: UUID
    uncertain_variables: Dict[str, Any] = Field(default_factory=dict)
    method: str = Field(default="DISCRETE_SCENARIOS")
    samples: int = Field(default=10, ge=1, le=10_000)

    @field_validator("method")
    @classmethod
    def check_method(cls, v: str) -> str:
        if v not in VALID_ROBUSTNESS_METHODS:
            raise ValueError(f"method must be one of {VALID_ROBUSTNESS_METHODS}")
        return v


class RobustnessScenarioOut(BaseModel):
    id: UUID
    run_id: UUID
    candidate_id: Optional[UUID]
    uncertain_variables: Dict[str, Any]
    method: str
    samples: int
    results: Dict[str, Any]
    sensitivity: Dict[str, Any]
    status: str
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── CostSnapshot & CarbonSnapshot ─────────────────────────────────────────────

class CostSnapshotOut(BaseModel):
    id: UUID
    run_id: UUID
    candidate_id: Optional[UUID]
    currency: str
    snapshot_date: datetime
    source_versions: Dict[str, Any]
    components: Dict[str, Any]
    total_eur: Optional[float]
    confidence: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


class CarbonSnapshotOut(BaseModel):
    id: UUID
    run_id: UUID
    candidate_id: Optional[UUID]
    scope: str
    factors: Dict[str, Any]
    geography: Optional[str]
    snapshot_date: datetime
    sources: Dict[str, Any]
    total_kgco2e: Optional[float]
    confidence: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── DesignInterview ───────────────────────────────────────────────────────────

class DesignInterviewCreate(BaseModel):
    project_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, max_length=200)
    language: str = Field(default="es", max_length=5)
    created_by: Optional[str] = Field(default=None, max_length=120)

    @field_validator("language")
    @classmethod
    def check_language(cls, v: str) -> str:
        if v not in VALID_LANGUAGES:
            raise ValueError(f"language must be one of {VALID_LANGUAGES}")
        return v


class DesignInterviewOut(BaseModel):
    id: UUID
    project_id: Optional[UUID]
    state: str
    title: Optional[str]
    language: str
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class InterviewMessageCreate(BaseModel):
    role: str = Field(..., pattern="^(USER|ASSISTANT|SYSTEM)$")
    content: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InterviewMessageOut(InterviewMessageCreate):
    id: UUID
    interview_id: UUID
    timestamp: datetime

    model_config = {"from_attributes": True}


class ResolveConflictRequest(BaseModel):
    field_path: str
    winning_source: str   # "USER" | "DOCUMENT" | "CATALOG"
    confirmed_value: Any


# ── ExtractedField ────────────────────────────────────────────────────────────

class ExtractedFieldOut(BaseModel):
    id: UUID
    interview_id: UUID
    field_path: str
    value: Optional[Any]
    unit: Optional[str]
    status: str
    confidence: Optional[float]
    criticality: Optional[str]
    source: Dict[str, Any]
    interpretation: Optional[str]
    uncertainty: Optional[Dict[str, Any]]
    confirmation_required: bool
    confirmed_at: Optional[datetime]
    parser_version: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── QuestionTemplate ──────────────────────────────────────────────────────────

class QuestionTemplateCreate(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=60)
    target_fields: List[str] = Field(default_factory=list)
    preconditions: List[str] = Field(default_factory=list)
    skip_condition: Optional[str] = None
    criticality: str = Field(default="P2")
    allowed_answer_types: List[str] = Field(default_factory=list)
    examples: List[Any] = Field(default_factory=list)
    validation_rules: Dict[str, Any] = Field(default_factory=dict)
    clarification_policy: Dict[str, Any] = Field(default_factory=dict)
    completion_rule: Optional[str] = None
    version: str = Field(default="1", max_length=20)

    @field_validator("criticality")
    @classmethod
    def check_criticality(cls, v: str) -> str:
        if v not in VALID_QUESTION_PRIORITIES:
            raise ValueError(f"criticality must be one of {VALID_QUESTION_PRIORITIES}")
        return v


class QuestionTemplateOut(QuestionTemplateCreate):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Explanation ───────────────────────────────────────────────────────────────

class OptimizationExplanationOut(BaseModel):
    run_id: UUID
    candidate_id: Optional[UUID]
    summary: str
    governing_constraints: List[str]
    objective_contributions: Dict[str, float]
    sensitivity_top: List[Dict[str, Any]]
    pareto_label: Optional[str]
    standard_comparison: Optional[Dict[str, Any]]
