"""
Salvi Studio · Columns — Modelos DB Fase 15
Informes, Validación Documental y Liberación.
Sufijo de enum PostgreSQL: 15
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text,
    func, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class MaturityState15(str, Enum):
    DRAFT = "DRAFT"
    PREDIM = "PREDIM"
    CALC_INTERNO = "CALC_INTERNO"
    VALIDADO_OT = "VALIDADO_OT"
    LIBERADO = "LIBERADO"


class ReleaseGate15(str, Enum):
    G0 = "G0"
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"
    G6 = "G6"


class DocPurpose15(str, Enum):
    PKG_COM = "PKG_COM"
    PKG_CLI = "PKG_CLI"
    PKG_CAL = "PKG_CAL"
    PKG_PRD = "PKG_PRD"
    PKG_SUB = "PKG_SUB"
    PKG_SIT = "PKG_SIT"
    PKG_QA = "PKG_QA"
    PKG_REG = "PKG_REG"
    PKG_SRV = "PKG_SRV"


class ValidationSeverity15(str, Enum):
    BLOQUEANTE = "BLOQUEANTE"
    GRAVE = "GRAVE"
    ADVERTENCIA = "ADVERTENCIA"
    INFO = "INFO"


class ReviewDecision15(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ABSTAINED = "ABSTAINED"
    REQUESTED_CHANGES = "REQUESTED_CHANGES"


class AuthoringMode15(str, Enum):
    DETERMINISTA = "DETERMINISTA"
    PLANTILLA = "PLANTILLA"
    IA_REVISADA = "IA_REVISADA"
    COMENTARIO_HUMANO = "COMENTARIO_HUMANO"


class ApprovalState15(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class DistributionState15(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ChangeKind15(str, Enum):
    IDENTIDAD = "IDENTIDAD"
    ENTRADA_TECNICA = "ENTRADA_TECNICA"
    REGLA_NORMATIVA = "REGLA_NORMATIVA"
    RESULTADO = "RESULTADO"
    INDUSTRIAL = "INDUSTRIAL"
    EDITORIAL = "EDITORIAL"
    TRADUCCION = "TRADUCCION"
    PERMISO = "PERMISO"


class AuthLevel15(str, Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"


class DistributionChannel15(str, Enum):
    PORTAL_CLIENTE = "PORTAL_CLIENTE"
    PORTAL_PROVEEDOR = "PORTAL_PROVEEDOR"
    ERP = "ERP"
    CORREO_SEGURO = "CORREO_SEGURO"
    EXPORTACION_OFFLINE = "EXPORTACION_OFFLINE"
    API = "API"


# ── Tablas ───────────────────────────────────────────────────────────────────

class ReleaseSnapshot15(Base):
    """
    Fuente de verdad inmutable del expediente en un estado de madurez dado.
    Una vez en M3/M4 no puede modificarse; solo sustituirse por nueva revisión.
    """
    __tablename__ = "release_snapshots15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    revision: Mapped[str] = mapped_column(String(20), nullable=False)
    maturity: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    gate_passed: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # Hashes de snapshots de fases anteriores
    product_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    library_set_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geometry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cad_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Manifiesto completo (JSONB)
    manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Firma y publicación
    signature_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    auth_level: Mapped[str] = mapped_column(String(5), nullable=False, default="A0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Trazabilidad de sustitución
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=True
    )

    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relaciones
    document_instances: Mapped[list["DocumentInstance15"]] = relationship(
        back_populates="release_snapshot", cascade="all, delete-orphan"
    )
    validation_runs: Mapped[list["ValidationRun15"]] = relationship(
        back_populates="release_snapshot", cascade="all, delete-orphan"
    )
    review_tasks: Mapped[list["ReviewTask15"]] = relationship(
        back_populates="release_snapshot", cascade="all, delete-orphan"
    )
    approval_records: Mapped[list["ApprovalRecord15"]] = relationship(
        back_populates="release_snapshot", cascade="all, delete-orphan"
    )
    distribution_records: Mapped[list["DistributionRecord15"]] = relationship(
        back_populates="release_snapshot", cascade="all, delete-orphan"
    )


class DocumentTemplate15(Base):
    """
    Contrato de plantilla versionado y aprobado.
    Define datos obligatorios, fuentes autorizadas, reglas de formato y visibilidad.
    """
    __tablename__ = "document_templates15"
    __table_args__ = (
        UniqueConstraint("template_code", "version", "locale", name="uq_template_version_locale15"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)  # DocPurpose15
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="es")
    market: Mapped[str] = mapped_column(String(40), nullable=False, default="EU")
    allowed_maturity: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Contrato ejecutable
    sections: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    data_bindings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    inclusion_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    format_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    visibility_policies: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    validation_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    render_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    approval_state: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    template_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    document_instances: Mapped[list["DocumentInstance15"]] = relationship(
        back_populates="template"
    )


class DocumentInstance15(Base):
    """
    Instancia de documento generada a partir de un template y un release snapshot.
    Es una vista del expediente, nunca una fuente primaria.
    """
    __tablename__ = "document_instances15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=False, index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_templates15.id"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="es")
    recipient_role: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Contenido y trazabilidad
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lineage: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # campo → fuente
    render_qa_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accessibility_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pdf_a_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Estado
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_manual_edits: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    release_snapshot: Mapped["ReleaseSnapshot15"] = relationship(
        back_populates="document_instances"
    )
    template: Mapped["DocumentTemplate15"] = relationship(
        back_populates="document_instances"
    )
    ai_generation_records: Mapped[list["AiGenerationRecord15"]] = relationship(
        back_populates="document_instance", cascade="all, delete-orphan"
    )


class ValidationRun15(Base):
    """
    Ejecución de validación automática contra un release snapshot.
    Produce lista de checks con severidad y código de validación.
    """
    __tablename__ = "validation_runs15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=False, index=True
    )
    gate: Mapped[str] = mapped_column(String(5), nullable=False)  # G0-G6
    checks: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{code, severity, message, passed}]
    blocking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grave_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    advertencia_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    run_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run_by: Mapped[str] = mapped_column(String(120), nullable=False)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    release_snapshot: Mapped["ReleaseSnapshot15"] = relationship(
        back_populates="validation_runs"
    )


class ReviewTask15(Base):
    """
    Tarea de revisión OT (Oficina Técnica).
    Implementa la regla de cuatro ojos: revisor ≠ aprobador.
    """
    __tablename__ = "review_tasks15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=False, index=True
    )
    assigned_to: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    release_snapshot: Mapped["ReleaseSnapshot15"] = relationship(
        back_populates="review_tasks"
    )
    comments: Mapped[list["ReviewComment15"]] = relationship(
        back_populates="review_task", cascade="all, delete-orphan"
    )


class ReviewComment15(Base):
    """Comentario de revisión OT con estado de resolución."""
    __tablename__ = "review_comments15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    review_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_tasks15.id"), nullable=False, index=True
    )
    author: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    target_section: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    review_task: Mapped["ReviewTask15"] = relationship(back_populates="comments")


class ApprovalRecord15(Base):
    """
    Registro de aprobación formal.
    Múltiples aprobaciones pueden requerirse según el gate (cuatro ojos).
    """
    __tablename__ = "approval_records15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=False, index=True
    )
    approver: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(60), nullable=False)
    gate: Mapped[str] = mapped_column(String(5), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_level: Mapped[str] = mapped_column(String(5), nullable=False, default="A1")
    mfa_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    release_snapshot: Mapped["ReleaseSnapshot15"] = relationship(
        back_populates="approval_records"
    )


class DistributionRecord15(Base):
    """
    Registro de distribución controlada de paquetes documentales.
    La distribución forma parte del expediente; no es un correo sin registro.
    """
    __tablename__ = "distribution_records15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=False, index=True
    )
    recipient: Mapped[str] = mapped_column(String(120), nullable=False)
    recipient_role: Mapped[str | None] = mapped_column(String(60), nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")

    # Política de acceso
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    can_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_print: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_forward: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_acceptance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    watermark: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hash del paquete enviado
    package_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    release_snapshot: Mapped["ReleaseSnapshot15"] = relationship(
        back_populates="distribution_records"
    )


class ChangeSet15(Base):
    """
    Diff semántico entre dos revisiones de un release.
    Clasifica cada cambio por naturaleza, criticidad y alcance.
    """
    __tablename__ = "change_sets15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=False
    )
    to_release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("release_snapshots15.id"), nullable=False
    )

    changes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # [{kind, path, from_value, to_value, criticality, affected_docs, affected_approvals}]
    blocking_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    technical_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    editorial_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Impacto calculado
    docs_to_regenerate: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    approvals_invalidated: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    recipients_notified: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    computed_by: Mapped[str] = mapped_column(String(120), nullable=False)


class AiGenerationRecord15(Base):
    """
    Registro de texto generado por IA para un documento.
    Requiere aceptación humana explícita antes de liberar.
    """
    __tablename__ = "ai_generation_records15"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_instances15.id"), nullable=False, index=True
    )
    section_id: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="es")
    model_version: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Aceptación humana
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    document_instance: Mapped["DocumentInstance15"] = relationship(
        back_populates="ai_generation_records"
    )
