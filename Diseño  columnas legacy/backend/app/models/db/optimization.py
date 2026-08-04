"""
Salvi Studio · Columns — Modelos DB Fase 13
Optimización Multiobjetivo y Diseño Especial
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


# ── Enums (sufijo 13 para unicidad en PostgreSQL) ─────────────────────────────

class VariableType13(str, enum.Enum):
    CONTINUOUS   = "CONTINUOUS"
    DISCRETE     = "DISCRETE"
    CATEGORICAL  = "CATEGORICAL"
    BOOLEAN      = "BOOLEAN"
    DERIVED      = "DERIVED"
    DEPENDENT    = "DEPENDENT"


class VariableMode13(str, enum.Enum):
    FIXED       = "FIXED"
    SELECTABLE  = "SELECTABLE"
    OPTIMIZABLE = "OPTIMIZABLE"
    DERIVED     = "DERIVED"


class ConstraintClass13(str, enum.Enum):
    NORMATIVA         = "NORMATIVA"
    DOMINIO           = "DOMINIO"
    GEOMETRICA        = "GEOMETRICA"
    FABRICACION       = "FABRICACION"
    TRANSPORTE_MONTAJE = "TRANSPORTE_MONTAJE"
    COMERCIAL         = "COMERCIAL"
    SOSTENIBILIDAD    = "SOSTENIBILIDAD"
    ROBUSTEZ          = "ROBUSTEZ"


class ConstraintSeverity13(str, enum.Enum):
    HARD    = "HARD"
    SOFT    = "SOFT"
    WARNING = "WARNING"


class CandidateStatus13(str, enum.Enum):
    PENDING    = "PENDING"
    EVALUATING = "EVALUATING"
    VALID      = "VALID"
    REJECTED   = "REJECTED"
    DOMINATED  = "DOMINATED"
    SELECTED   = "SELECTED"


class OptimizationRunStatus13(str, enum.Enum):
    DRAFT     = "DRAFT"
    RUNNING   = "RUNNING"
    PAUSED    = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED    = "FAILED"


class ObjectiveDirection13(str, enum.Enum):
    MINIMIZE = "MINIMIZE"
    MAXIMIZE = "MAXIMIZE"


class RobustnessMethod13(str, enum.Enum):
    DISCRETE_SCENARIOS  = "DISCRETE_SCENARIOS"
    INTERVALS           = "INTERVALS"
    LATIN_HYPERCUBE     = "LATIN_HYPERCUBE"
    MONTE_CARLO         = "MONTE_CARLO"
    ROBUST_OPTIMIZATION = "ROBUST_OPTIMIZATION"
    WORST_CASE          = "WORST_CASE"


class InterviewState13(str, enum.Enum):
    NEW           = "NEW"
    DISCOVERY     = "DISCOVERY"
    ELICITATION   = "ELICITATION"
    CLARIFICATION = "CLARIFICATION"
    REVIEW        = "REVIEW"
    CONFIRMED     = "CONFIRMED"
    BLOCKED       = "BLOCKED"
    READY         = "READY"


class QuestionPriority13(str, enum.Enum):
    P0        = "P0"
    P1        = "P1"
    P2        = "P2"
    P3        = "P3"
    DERIVABLE = "DERIVABLE"


class FieldDataStatus13(str, enum.Enum):
    EXACT                = "EXACT"
    ESTIMATED            = "ESTIMATED"
    RANGE                = "RANGE"
    UNKNOWN              = "UNKNOWN"
    CONFLICT             = "CONFLICT"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"


class InterviewRole13(str, enum.Enum):
    USER      = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM    = "SYSTEM"


# ── Tablas ────────────────────────────────────────────────────────────────────

class OptimizationProfile(Base):
    """Perfil de optimización: pesos, límites y algoritmos por rol."""
    __tablename__ = "optimization_profile"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name              = Column(String(120), nullable=False, unique=True)
    user_role         = Column(String(60), nullable=False)
    defaults          = Column(JSONB, nullable=False, default=dict)
    limits            = Column(JSONB, nullable=False, default=dict)
    published_version = Column(Integer, nullable=False, default=0)
    is_published      = Column(Boolean, nullable=False, default=False)
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(),
                               onupdate=func.now(), nullable=False)

    runs = relationship("OptimizationRun", back_populates="profile")


class OptimizationRun(Base):
    """Ejecución de optimización: semilla, estado, hashes y presupuesto."""
    __tablename__ = "optimization_run"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_revision_id = Column(UUID(as_uuid=True), nullable=True)   # FK externo, validado por app
    profile_id          = Column(UUID(as_uuid=True), ForeignKey("optimization_profile.id"), nullable=True)
    objectives          = Column(JSONB, nullable=False, default=list)
    algorithm_config    = Column(JSONB, nullable=False, default=dict)
    algorithm_version   = Column(String(40), nullable=False, default="1.0.0")
    seed                = Column(Integer, nullable=True)
    status              = Column(String(20), nullable=False, default=OptimizationRunStatus13.DRAFT)
    run_hash            = Column(String(64), nullable=True)
    result_hash         = Column(String(64), nullable=True)
    candidate_count     = Column(Integer, nullable=False, default=0)
    pareto_count        = Column(Integer, nullable=False, default=0)
    budget_evaluations  = Column(Integer, nullable=False, default=1000)
    elapsed_seconds     = Column(Float, nullable=True)
    error_message       = Column(Text, nullable=True)
    created_by          = Column(String(120), nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at          = Column(DateTime(timezone=True), nullable=True)
    completed_at        = Column(DateTime(timezone=True), nullable=True)

    profile              = relationship("OptimizationProfile", back_populates="runs")
    variables            = relationship("DesignVariable", back_populates="run",
                                        cascade="all, delete-orphan")
    constraints          = relationship("ConstraintDefinition", back_populates="run",
                                        cascade="all, delete-orphan")
    objectives_def       = relationship("ObjectiveDefinition", back_populates="run",
                                        cascade="all, delete-orphan")
    candidates           = relationship("CandidateDesign", back_populates="run",
                                        cascade="all, delete-orphan")
    pareto_alternatives  = relationship("ParetoAlternative", back_populates="run",
                                        cascade="all, delete-orphan")
    robustness_scenarios = relationship("RobustnessScenario", back_populates="run",
                                        cascade="all, delete-orphan")
    cost_snapshots       = relationship("CostSnapshot", back_populates="run",
                                        cascade="all, delete-orphan")
    carbon_snapshots     = relationship("CarbonSnapshot", back_populates="run",
                                        cascade="all, delete-orphan")


class DesignVariable(Base):
    """Variable de diseño con tipo, modo y dominio."""
    __tablename__ = "design_variable"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id          = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                              ondelete="CASCADE"), nullable=False)
    name            = Column(String(120), nullable=False)
    variable_type   = Column(String(20), nullable=False)
    mode            = Column(String(20), nullable=False)
    domain          = Column(JSONB, nullable=False, default=dict)
    unit            = Column(String(30), nullable=True)
    dependency_expr = Column(Text, nullable=True)
    source          = Column(String(60), nullable=True)
    version         = Column(String(20), nullable=False, default="1")
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "name", name="uq_design_variable_run_name"),)

    run = relationship("OptimizationRun", back_populates="variables")


class ConstraintDefinition(Base):
    """Definición de restricción versionada."""
    __tablename__ = "constraint_definition"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id               = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                                   ondelete="CASCADE"), nullable=False)
    code                 = Column(String(60), nullable=False)
    constraint_class     = Column(String(30), nullable=False)
    severity             = Column(String(20), nullable=False, default=ConstraintSeverity13.HARD)
    evaluator            = Column(String(120), nullable=True)
    limit_value          = Column(JSONB, nullable=True)
    normative_reference  = Column(String(120), nullable=True)
    version              = Column(String(20), nullable=False, default="1")
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "code", name="uq_constraint_def_run_code"),)

    run = relationship("OptimizationRun", back_populates="constraints")


class ObjectiveDefinition(Base):
    """Definición de función objetivo: dirección, peso, normalización."""
    __tablename__ = "objective_definition"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id        = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                           ondelete="CASCADE"), nullable=False)
    code          = Column(String(60), nullable=False)
    normalization = Column(JSONB, nullable=False, default=dict)
    weight        = Column(Float, nullable=False, default=1.0)
    direction     = Column(String(20), nullable=False, default=ObjectiveDirection13.MINIMIZE)
    scope         = Column(String(60), nullable=True)
    permissions   = Column(JSONB, nullable=False, default=dict)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("run_id", "code", name="uq_objective_def_run_code"),)

    run = relationship("OptimizationRun", back_populates="objectives_def")


class CandidateDesign(Base):
    """Candidato de diseño generado por el optimizador."""
    __tablename__ = "candidate_design"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id           = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                              ondelete="CASCADE"), nullable=False)
    parent_id        = Column(UUID(as_uuid=True), ForeignKey("candidate_design.id",
                                                              ondelete="SET NULL"), nullable=True)
    variables        = Column(JSONB, nullable=False, default=dict)
    geometry_hash    = Column(String(64), nullable=True)
    candidate_hash   = Column(String(64), nullable=True)   # hash canónico anti-duplicado
    status           = Column(String(20), nullable=False, default=CandidateStatus13.PENDING)
    rejection_reason = Column(Text, nullable=True)
    rejection_code   = Column(String(60), nullable=True)
    generation       = Column(Integer, nullable=False, default=0)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run        = relationship("OptimizationRun", back_populates="candidates")
    parent     = relationship("CandidateDesign", remote_side="CandidateDesign.id")
    evaluation = relationship("OptimizationCandidateEvaluation", back_populates="candidate",
                              uselist=False, cascade="all, delete-orphan")
    pareto_alt = relationship("ParetoAlternative", back_populates="candidate",
                              uselist=False, cascade="all, delete-orphan")
    robustness = relationship("RobustnessScenario", back_populates="candidate")
    costs      = relationship("CostSnapshot", back_populates="candidate")
    carbons    = relationship("CarbonSnapshot", back_populates="candidate")


class OptimizationCandidateEvaluation(Base):
    """Resultado de evaluación de un candidato (1:1 con CandidateDesign)."""
    __tablename__ = "candidate_evaluation_13"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id       = Column(UUID(as_uuid=True), ForeignKey("candidate_design.id",
                                                                 ondelete="CASCADE"),
                                nullable=False, unique=True)
    solver_run_ids     = Column(JSONB, nullable=False, default=list)
    utilizations       = Column(JSONB, nullable=False, default=dict)
    objective_values   = Column(JSONB, nullable=False, default=dict)
    constraint_results = Column(JSONB, nullable=False, default=dict)
    warnings           = Column(JSONB, nullable=False, default=list)
    evidence           = Column(JSONB, nullable=False, default=dict)
    cost_eur           = Column(Float, nullable=True)
    mass_kg            = Column(Float, nullable=True)
    co2_kg             = Column(Float, nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    candidate = relationship("CandidateDesign", back_populates="evaluation")


class ParetoAlternative(Base):
    """Alternativa en el frente de Pareto."""
    __tablename__ = "pareto_alternative"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id           = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                              ondelete="CASCADE"), nullable=False)
    candidate_id     = Column(UUID(as_uuid=True), ForeignKey("candidate_design.id",
                                                              ondelete="CASCADE"),
                              nullable=False, unique=True)
    dominance_rank   = Column(Integer, nullable=False, default=1)
    crowding_distance = Column(Float, nullable=True)
    label            = Column(String(60), nullable=True)
    selected_reason  = Column(Text, nullable=True)
    is_selected      = Column(Boolean, nullable=False, default=False)
    selected_at      = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run       = relationship("OptimizationRun", back_populates="pareto_alternatives")
    candidate = relationship("CandidateDesign", back_populates="pareto_alt")


class RobustnessScenario(Base):
    """Análisis de robustez para un candidato."""
    __tablename__ = "robustness_scenario"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id              = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                                 ondelete="CASCADE"), nullable=False)
    candidate_id        = Column(UUID(as_uuid=True), ForeignKey("candidate_design.id",
                                                                  ondelete="SET NULL"), nullable=True)
    uncertain_variables = Column(JSONB, nullable=False, default=dict)
    method              = Column(String(30), nullable=False,
                                 default=RobustnessMethod13.DISCRETE_SCENARIOS)
    samples             = Column(Integer, nullable=False, default=0)
    results             = Column(JSONB, nullable=False, default=dict)
    sensitivity         = Column(JSONB, nullable=False, default=dict)
    status              = Column(String(20), nullable=False, default="PENDING")
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at        = Column(DateTime(timezone=True), nullable=True)

    run       = relationship("OptimizationRun", back_populates="robustness_scenarios")
    candidate = relationship("CandidateDesign", back_populates="robustness")


class CostSnapshot(Base):
    """Snapshot de coste industrial con trazabilidad de fuentes."""
    __tablename__ = "cost_snapshot"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id           = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                              ondelete="CASCADE"), nullable=False)
    candidate_id     = Column(UUID(as_uuid=True), ForeignKey("candidate_design.id",
                                                              ondelete="SET NULL"), nullable=True)
    currency         = Column(String(3), nullable=False, default="EUR")
    snapshot_date    = Column(DateTime(timezone=True), nullable=False)
    source_versions  = Column(JSONB, nullable=False, default=dict)
    components       = Column(JSONB, nullable=False, default=dict)
    total_eur        = Column(Float, nullable=True)
    confidence       = Column(Float, nullable=True)   # 0..1
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run       = relationship("OptimizationRun", back_populates="cost_snapshots")
    candidate = relationship("CandidateDesign", back_populates="costs")


class CarbonSnapshot(Base):
    """Snapshot de huella de carbono con jerarquía EPD."""
    __tablename__ = "carbon_snapshot"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id          = Column(UUID(as_uuid=True), ForeignKey("optimization_run.id",
                                                             ondelete="CASCADE"), nullable=False)
    candidate_id    = Column(UUID(as_uuid=True), ForeignKey("candidate_design.id",
                                                             ondelete="SET NULL"), nullable=True)
    scope           = Column(String(30), nullable=False, default="A1-A3")
    factors         = Column(JSONB, nullable=False, default=dict)
    geography       = Column(String(10), nullable=True)
    snapshot_date   = Column(DateTime(timezone=True), nullable=False)
    sources         = Column(JSONB, nullable=False, default=dict)
    total_kgco2e    = Column(Float, nullable=True)
    confidence      = Column(Float, nullable=True)   # 0..1
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run       = relationship("OptimizationRun", back_populates="carbon_snapshots")
    candidate = relationship("CandidateDesign", back_populates="carbons")


# ── Asistente conversacional ──────────────────────────────────────────────────

class DesignInterview(Base):
    """Entrevista conversacional para captura de requisitos de optimización."""
    __tablename__ = "design_interview"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id      = Column(UUID(as_uuid=True), nullable=True)
    state           = Column(String(20), nullable=False, default=InterviewState13.NEW)
    title           = Column(String(200), nullable=True)
    language        = Column(String(5), nullable=False, default="es")
    created_by      = Column(String(120), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(),
                             onupdate=func.now(), nullable=False)
    confirmed_at    = Column(DateTime(timezone=True), nullable=True)

    messages         = relationship("InterviewMessage", back_populates="interview",
                                    cascade="all, delete-orphan", order_by="InterviewMessage.timestamp")
    extracted_fields = relationship("ExtractedField", back_populates="interview",
                                    cascade="all, delete-orphan")


class InterviewMessage(Base):
    """Mensaje en el historial de la entrevista."""
    __tablename__ = "interview_message"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id = Column(UUID(as_uuid=True), ForeignKey("design_interview.id",
                                                          ondelete="CASCADE"), nullable=False)
    role         = Column(String(15), nullable=False)
    content      = Column(Text, nullable=False)
    timestamp    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    extra_metadata = Column(JSONB, nullable=False, default=dict)

    interview = relationship("DesignInterview", back_populates="messages")


class ExtractedField(Base):
    """Campo extraído y trazado a fuente conversacional o documental."""
    __tablename__ = "extracted_field"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id         = Column(UUID(as_uuid=True), ForeignKey("design_interview.id",
                                                                   ondelete="CASCADE"), nullable=False)
    field_path           = Column(String(200), nullable=False)
    value                = Column(JSONB, nullable=True)
    unit                 = Column(String(30), nullable=True)
    status               = Column(String(30), nullable=False, default=FieldDataStatus13.PENDING_CONFIRMATION)
    confidence           = Column(Float, nullable=True)
    criticality          = Column(String(20), nullable=True)
    source               = Column(JSONB, nullable=False, default=dict)
    interpretation       = Column(Text, nullable=True)
    uncertainty          = Column(JSONB, nullable=True)
    confirmation_required = Column(Boolean, nullable=False, default=True)
    confirmed_at         = Column(DateTime(timezone=True), nullable=True)
    parser_version       = Column(String(30), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(),
                                  onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("interview_id", "field_path",
                                       name="uq_extracted_field_interview_path"),)

    interview = relationship("DesignInterview", back_populates="extracted_fields")


class QuestionTemplate(Base):
    """Plantilla de pregunta versionada para el planificador conversacional."""
    __tablename__ = "question_template"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id          = Column(String(60), nullable=False, unique=True)
    target_fields        = Column(JSONB, nullable=False, default=list)
    preconditions        = Column(JSONB, nullable=False, default=list)
    skip_condition       = Column(Text, nullable=True)
    criticality          = Column(String(10), nullable=False, default=QuestionPriority13.P2)
    allowed_answer_types = Column(JSONB, nullable=False, default=list)
    examples             = Column(JSONB, nullable=False, default=list)
    validation_rules     = Column(JSONB, nullable=False, default=dict)
    clarification_policy = Column(JSONB, nullable=False, default=dict)
    completion_rule      = Column(Text, nullable=True)
    version              = Column(String(20), nullable=False, default="1")
    is_active            = Column(Boolean, nullable=False, default=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(),
                                  onupdate=func.now(), nullable=False)
