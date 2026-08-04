"""
Salvi Studio · Columns — Fase 17: Validación Industrial, Ensayos y Certificación
Modelos SQLAlchemy para el framework V&V: trazabilidad, ensayos, correlación,
dominios de cualificación, no conformidades y gates de liberación.
Sufijo de enum PostgreSQL: 17
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums (sufijo 17 para unicidad en PostgreSQL) ─────────────────────────────

class EvidenceLevel17(str, enum.Enum):
    E0 = "E0"   # Hipótesis sin contraste
    E1 = "E1"   # Prueba unitaria / cálculo manual interno
    E2 = "E2"   # Comparación con solución analítica/software independiente
    E3 = "E3"   # Correlación con ensayo físico o producto conocido
    E4 = "E4"   # Campaña representativa + FPC + auditoría interna
    E5 = "E5"   # Evaluación/certificación externa


class ValidationLevel17(str, enum.Enum):
    V0 = "V0"   # Código en desarrollo, sin decisiones de producto
    V1 = "V1"   # Pruebas unitarias y analíticas aprobadas
    V2 = "V2"   # Comparación independiente y regresión
    V3 = "V3"   # Correlación con ensayos representativos
    V4 = "V4"   # Validación industrial, FPC y familias cualificadas
    V5 = "V5"   # Auditoría/certificación externa


class CriticalityLevel17(str, enum.Enum):
    C1 = "C1"   # Baja: formato/visualización
    C2 = "C2"   # Media: BOM/costes/geometría no resistente
    C3 = "C3"   # Alta: acciones/propiedades/verificaciones
    C4 = "C4"   # Muy alta: solver global/estabilidad/fatiga/base
    C5 = "C5"   # Extrema: ruta normativa/liberación/certificación


class TestRunState17(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED  = "PASSED"
    FAILED  = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class NcmSeverity17(str, enum.Enum):
    S1 = "S1"   # Menor: defecto documental sin impacto
    S2 = "S2"   # Moderada: error de proceso antes de entrega
    S3 = "S3"   # Alta: resultado técnico incorrecto → BLOQUEO
    S4 = "S4"   # Crítica: riesgo de seguridad/producto instalado → CRISIS


class GateId17(str, enum.Enum):
    G17_1 = "G17_1"   # Requisitos
    G17_2 = "G17_2"   # Verificación
    G17_3 = "G17_3"   # Comparación
    G17_4 = "G17_4"   # Ensayos
    G17_5 = "G17_5"   # Industrial
    G17_6 = "G17_6"   # Documental
    G17_7 = "G17_7"   # Liberación


class GateState17(str, enum.Enum):
    OPEN      = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    PASSED    = "PASSED"
    BLOCKED   = "BLOCKED"


# ── Tablas ─────────────────────────────────────────────────────────────────────

class ValidationPlan17(Base):
    """Plan Maestro de Validación (VMP): alcance, versión, riesgos y criterios."""
    __tablename__ = "validation_plans17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.1")
    validation_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default=ValidationLevel17.V0.value,
    )
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    risks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    acceptance_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    responsible: Mapped[str] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    requirement_traces: Mapped[list["RequirementTrace17"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
    )
    release_gates: Mapped[list["ReleaseGate17"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
    )


class RequirementTrace17(Base):
    """Trazabilidad requisito → implementación → prueba → evidencia."""
    __tablename__ = "requirement_traces17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("validation_plans17.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    req_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False)   # norma/cláusula
    description: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_ref: Mapped[str] = mapped_column(String(256), nullable=True)
    test_case_ref: Mapped[str] = mapped_column(String(64), nullable=True)
    evidence_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default=EvidenceLevel17.E0.value,
    )
    criticality: Mapped[str] = mapped_column(
        String(4), nullable=False, default=CriticalityLevel17.C1.value,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    plan: Mapped["ValidationPlan17"] = relationship(back_populates="requirement_traces")


class TestCase17(Base):
    """Caso de prueba: entradas, referencia, tolerancia, criticidad y automatización."""
    __tablename__ = "test_cases17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tc_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    criticality: Mapped[str] = mapped_column(
        String(4), nullable=False, default=CriticalityLevel17.C1.value,
    )
    evidence_level_required: Mapped[str] = mapped_column(
        String(4), nullable=False, default=EvidenceLevel17.E1.value,
    )
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reference_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tolerance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_golden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    automated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    req_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    test_runs: Mapped[list["TestRun17"]] = relationship(
        back_populates="test_case", cascade="all, delete-orphan",
    )


class TestRun17(Base):
    """Ejecución de un caso de prueba: entorno, commit, resultado, logs y hash."""
    __tablename__ = "test_runs17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_cases17.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    run_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TestRunState17.PENDING.value,
    )
    environment: Mapped[str] = mapped_column(String(128), nullable=True)
    commit_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    dataset_ref: Mapped[str] = mapped_column(String(256), nullable=True)
    computed_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    logs: Mapped[str] = mapped_column(Text, nullable=True)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, nullable=True)
    evidence_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default=EvidenceLevel17.E1.value,
    )
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    test_case: Mapped["TestCase17"] = relationship(back_populates="test_runs")


class PhysicalTest17(Base):
    """Ensayo físico: prototipo, procedimiento, instrumentación y datos brutos."""
    __tablename__ = "physical_tests17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    test_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    prototype_ref: Mapped[str] = mapped_column(String(256), nullable=True)
    procedure_ref: Mapped[str] = mapped_column(String(256), nullable=True)
    lab: Mapped[str] = mapped_column(String(128), nullable=True)
    instrumentation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_datasets: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    processed_results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    uncertainty_budget: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default=EvidenceLevel17.E3.value,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLANNED")
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    calibration_records: Mapped[list["CalibrationRecord17"]] = relationship(
        back_populates="physical_test", cascade="all, delete-orphan",
    )
    correlation_results: Mapped[list["CorrelationResult17"]] = relationship(
        back_populates="physical_test", cascade="all, delete-orphan",
    )


class CalibrationRecord17(Base):
    """Registro de calibración: equipo, certificado, rango, incertidumbre y vigencia."""
    __tablename__ = "calibration_records17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    physical_test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("physical_tests17.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    equipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment_name: Mapped[str] = mapped_column(String(256), nullable=False)
    certificate_ref: Mapped[str] = mapped_column(String(256), nullable=True)
    calibrated_by: Mapped[str] = mapped_column(String(128), nullable=True)
    measurement_range: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    uncertainty_k2: Mapped[float] = mapped_column(Float, nullable=True)  # U k=2
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    physical_test: Mapped["PhysicalTest17"] = relationship(back_populates="calibration_records")


class CorrelationResult17(Base):
    """Resultado de correlación modelo–ensayo: métricas, factor de modelo y decisión."""
    __tablename__ = "correlation_results17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    physical_test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("physical_tests17.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[str] = mapped_column(String(64), nullable=False)  # defl, stress, freq…
    n_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    e_rel_max: Mapped[float] = mapped_column(Float, nullable=True)   # max |e_rel|
    e_rel_mean: Mapped[float] = mapped_column(Float, nullable=True)
    rmse: Mapped[float] = mapped_column(Float, nullable=True)
    bias: Mapped[float] = mapped_column(Float, nullable=True)
    model_factor: Mapped[float] = mapped_column(Float, nullable=True)  # θ = mean(y_ref/y_calc)
    uncertainty_u: Mapped[float] = mapped_column(Float, nullable=True)  # U k=2
    tolerance_target: Mapped[float] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default=EvidenceLevel17.E3.value,
    )
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    physical_test: Mapped["PhysicalTest17"] = relationship(back_populates="correlation_results")


class QualificationDomain17(Base):
    """Dominio de cualificación: límites geométricos, materiales, cargas y procesos."""
    __tablename__ = "qualification_domains17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    family: Mapped[str] = mapped_column(String(128), nullable=True)
    geometric_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    material_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    load_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    process_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    extension_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    validation_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default=ValidationLevel17.V0.value,
    )
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class Nonconformity17(Base):
    """No conformidad: severidad, causa raíz, contención, CAPA y cierre."""
    __tablename__ = "nonconformities17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    ncm_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(4), nullable=False, default=NcmSeverity17.S1.value,
    )
    affected_module: Mapped[str] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=True)
    containment: Mapped[str] = mapped_column(Text, nullable=True)
    capa: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    blocks_gate: Mapped[str] = mapped_column(String(8), nullable=True)  # gate ID si bloquea
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class ReleaseGate17(Base):
    """Gate de liberación: estado, evidencias requeridas, aprobadores y fecha."""
    __tablename__ = "release_gates17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("validation_plans17.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    gate_id: Mapped[str] = mapped_column(
        String(8), nullable=False,
    )  # G17_1 … G17_7
    gate_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=GateState17.OPEN.value,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    required_evidences: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    provided_evidences: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    approvers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    decision_by: Mapped[str] = mapped_column(String(128), nullable=True)
    decision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    blocking_ncms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    comments: Mapped[str] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    plan: Mapped["ValidationPlan17"] = relationship(back_populates="release_gates")
    certificate_evidences: Mapped[list["CertificateEvidence17"]] = relationship(
        back_populates="gate", cascade="all, delete-orphan",
    )


class CertificateEvidence17(Base):
    """Evidencia de certificación: documento externo, emisor, alcance y verificación."""
    __tablename__ = "certificate_evidences17"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    gate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_gates17.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    doc_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    issuer: Mapped[str] = mapped_column(String(256), nullable=True)
    scope: Mapped[str] = mapped_column(Text, nullable=True)
    evidence_level: Mapped[str] = mapped_column(
        String(4), nullable=False, default=EvidenceLevel17.E3.value,
    )
    verified_by: Mapped[str] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    gate: Mapped["ReleaseGate17"] = relationship(back_populates="certificate_evidences")
