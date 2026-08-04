"""
Salvi Studio · Columns — Auditoría inmutable y trabajos asíncronos
Fase 1, secciones 18 y 22.

P-03: Todo dato crítico tiene origen, unidad, fecha, autor, estado y versión.
La auditoría es inmutable — no se permite UPDATE ni DELETE sobre audit_logs.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.database import Base, TimestampMixin
from app.models.db.base_types import UUIDPk, LongText


class AuditLog(Base):
    """
    Registro inmutable de cambios críticos.
    INSERT ONLY — nunca se actualiza ni elimina (10 años de retención).
    Sección 18, Fase 1.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_project_id", "project_id"),
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[UUIDPk]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    # Quién
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    actor_email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)  # Snapshot del email
    actor_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)    # Rol en el momento

    # Qué entidad
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)   # "project", "revision", etc.
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )  # Para filtrado rápido por proyecto

    # Qué acción
    action: Mapped[str] = mapped_column(String(64), nullable=False)   # "create", "freeze", "validate_m3"...
    action_result: Mapped[str] = mapped_column(
        String(16), nullable=False, default="success"
    )  # "success", "denied", "error"

    # Detalles
    before_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    diff: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reason: Mapped[LongText]
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Contexto técnico
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Relaciones (solo lectura — no cascade)
    actor: Mapped[Optional["User"]] = relationship(back_populates="audit_entries", foreign_keys=[actor_id])
    project: Mapped[Optional["Project"]] = relationship(back_populates="audit_logs")


class AsyncJob(Base):
    """
    Trabajo asíncrono para cálculos, optimización, CAD e informes.
    Sección 22, Fase 1. AC-27: fallo accionable con correlation_id.
    """
    __tablename__ = "async_jobs"

    id: Mapped[UUIDPk]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", onupdate="now()", nullable=False
    )

    job_type: Mapped[str] = mapped_column(String(64), nullable=False)  # "calculation", "cad", "report"...
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued"
    )  # queued/running/succeeded/failed/cancelled

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    triggered_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Trazabilidad (AC-27)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    arq_job_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Payload y resultado
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[LongText]
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)

    # Tiempos
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)


class Artifact(Base):
    """
    Adjunto, informe, CAD, ensayo o evidencia vinculada a un proyecto.
    Almacenado en object storage; aquí solo metadatos y referencia.
    Sección 7, Fase 1.
    """
    __tablename__ = "artifacts"

    id: Mapped[UUIDPk]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("revisions.id"), nullable=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    artifact_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "report", "cad_step", "cad_dxf", "bom", "test_report", "certificate", "photo", "other"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[LongText]
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)  # Clave en object storage
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)  # Integridad

    # Relaciones
    project: Mapped["Project"] = relationship(back_populates="artifacts")


class Decision(Base, TimestampMixin):
    """
    Decisión técnica o comercial registrada con autor y motivo.
    Contribuye a la trazabilidad (P-03). Sección 7, Fase 1.
    """
    __tablename__ = "decisions"

    id: Mapped[UUIDPk]
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[LongText]
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False, default="technical")
    made_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    rationale: Mapped[LongText]
    alternatives_considered: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relaciones
    project: Mapped["Project"] = relationship(back_populates="decisions")


class Comment(Base, TimestampMixin):
    """
    Observación contextual vinculada a proyecto/revisión/campo.
    Resoluble. AC-22: ancla histórica se conserva. Sección 7, Fase 1.
    """
    __tablename__ = "comments"

    id: Mapped[UUIDPk]
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("revisions.id"), nullable=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    parent_comment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("comments.id"), nullable=True
    )

    # Ancla al campo/sección específica (AC-22)
    field_anchor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(nullable=False, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relaciones
    project: Mapped["Project"] = relationship(back_populates="comments")
