"""
Salvi Studio · Columns — Modelos de proyecto, escenario, alternativa y revisión
Fase 1, secciones 7, 8 y 9.

Principios clave:
  P-01: Inmutabilidad — revisiones congeladas nunca se modifican
  P-07: No sobrescritura silenciosa — bibls. maestras no alteran proyectos históricos
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Text, Boolean, DateTime, ForeignKey,
    Enum as SAEnum, Integer, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.database import Base, TimestampMixin
from app.core.security import MaturityLevel, ProjectStatus
from app.models.db.base_types import UUIDPk, CodeStr, ShortStr, LongText


class Project(Base, TimestampMixin):
    """
    Contenedor empresarial principal. No es una única columna sino una
    referencia comercial/técnica que puede contener múltiples emplazamientos,
    escenarios y alternativas.
    Sección 7, Fase 1.
    """
    __tablename__ = "projects"

    id: Mapped[UUIDPk]
    project_code: Mapped[CodeStr] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[LongText]

    # Contexto comercial
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )  # Referencia a entidad cliente de Salvi Studio
    opportunity_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # Contexto geográfico y normativo
    country: Mapped[str] = mapped_column(String(2), nullable=False)   # ISO 3166-1 alpha-2
    region: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Madrid")

    # Configuración
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")  # ISO 4217
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="es")
    confidentiality: Mapped[str] = mapped_column(
        SAEnum("internal", "restricted", "client", name="confidentiality_enum"),
        nullable=False, default="internal"
    )

    # Estado y madurez
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status_enum",
               values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False, default=ProjectStatus.DRAFT
    )
    maturity: Mapped[MaturityLevel] = mapped_column(
        SAEnum(MaturityLevel, name="maturity_enum"),
        nullable=False, default=MaturityLevel.M0
    )

    # Responsable
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Soft delete
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Plantilla origen (para clonación — AC-16, AC-17)
    cloned_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )

    # Relaciones
    sites: Mapped[List["Site"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    scenarios: Mapped[List["DesignScenario"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    revisions: Mapped[List["Revision"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    artifacts: Mapped[List["Artifact"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    decisions: Mapped[List["Decision"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    comments: Mapped[List["Comment"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="project")


class Site(Base, TimestampMixin):
    """
    Emplazamiento o zona con ubicación y condiciones comunes.
    Un proyecto puede tener múltiples emplazamientos.
    Sección 7, Fase 1.
    """
    __tablename__ = "sites"

    id: Mapped[UUIDPk]
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[ShortStr]
    description: Mapped[LongText]

    # Coordenadas (para geodatos — Fase 3)
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    altitude_m: Mapped[Optional[float]] = mapped_column(nullable=True)  # m s.n.m., SI

    # Geo-params confirmados (snapshot parcial — se completa en Fase 3)
    geo_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relaciones
    project: Mapped["Project"] = relationship(back_populates="sites")
    scenarios: Mapped[List["DesignScenario"]] = relationship(back_populates="site")


class DesignScenario(Base, TimestampMixin):
    """
    Conjunto coherente de hipótesis y objetivos para un proyecto.
    Modificar una hipótesis que afecte conformidad requiere nueva revisión.
    Sección 8.1, Fase 1.
    """
    __tablename__ = "design_scenarios"

    id: Mapped[UUIDPk]
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True
    )
    name: Mapped[ShortStr]
    description: Mapped[LongText]
    status: Mapped[str] = mapped_column(
        SAEnum("active", "discarded", "comparative", "contractual", name="scenario_status_enum"),
        nullable=False, default="active"
    )
    is_base: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cloned_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("design_scenarios.id"), nullable=True
    )

    # Hipótesis en JSONB — se estructura en Fases 3-4
    hypotheses: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relaciones
    project: Mapped["Project"] = relationship(back_populates="scenarios")
    site: Mapped[Optional["Site"]] = relationship(back_populates="scenarios")
    alternatives: Mapped[List["Alternative"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class Alternative(Base, TimestampMixin):
    """
    Solución candidata dentro de un escenario.
    Las alternativas descartadas se conservan con motivo (no se borran).
    Sección 8.2, Fase 1.
    """
    __tablename__ = "alternatives"

    id: Mapped[UUIDPk]
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("design_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[ShortStr]
    description: Mapped[LongText]
    origin: Mapped[str] = mapped_column(
        SAEnum("manual", "catalog", "optimization", name="alternative_origin_enum"),
        nullable=False, default="manual"
    )
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discard_reason: Mapped[LongText]
    selection_criteria: Mapped[LongText]

    # Relaciones
    scenario: Mapped["DesignScenario"] = relationship(back_populates="alternatives")


class Revision(Base, TimestampMixin):
    """
    Estado congelado e inmutable del contenido editable de un proyecto.
    P-01: Una revisión congelada NUNCA se modifica.
    P-02: Debe ser reproducible a partir del snapshot.
    Sección 8.3 y 9, Fase 1.
    """
    __tablename__ = "revisions"

    __table_args__ = (
        CheckConstraint(
            "frozen_at IS NOT NULL OR is_frozen = false",
            name="ck_revisions_frozen_consistency"
        ),
    )

    id: Mapped[UUIDPk]
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    revision_code: Mapped[str] = mapped_column(String(16), nullable=False)
    # Tipos: D (borrador interno), R (técnica), C (cliente), P (producción), AB (as-built)
    revision_type: Mapped[str] = mapped_column(
        SAEnum("draft", "technical", "client", "production", "as_built", name="revision_type_enum"),
        nullable=False, default="draft"
    )
    maturity: Mapped[MaturityLevel] = mapped_column(
        SAEnum(MaturityLevel, name="revision_maturity_enum"),
        nullable=False, default=MaturityLevel.M0
    )
    description: Mapped[LongText]
    change_summary: Mapped[LongText]

    # Congelación — P-01
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    frozen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    frozen_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Validación OT — M3
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    validation_comment: Mapped[LongText]

    # Hash de integridad (P-02) — calculado al congelar
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relaciones
    project: Mapped["Project"] = relationship(back_populates="revisions")
    snapshot: Mapped[Optional["RevisionSnapshot"]] = relationship(
        back_populates="revision", uselist=False
    )
    calculation_runs: Mapped[List["CalculationRun"]] = relationship(back_populates="revision")


class RevisionSnapshot(Base):
    """
    Instantánea completa de una revisión congelada.
    Autosuficiente para reproducir el cálculo. Inmutable.
    Sección 9, Fase 1.
    """
    __tablename__ = "revision_snapshots"

    id: Mapped[UUIDPk]
    revision_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("revisions.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    # Componentes del snapshot (sección 9, Fase 1)
    project_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normative_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    library_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    geo_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    configuration_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    software_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifact_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Hash canónico — serialización estable, excluye campos no deterministas
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Relaciones
    revision: Mapped["Revision"] = relationship(back_populates="snapshot")


class CalculationRun(Base):
    """
    Ejecución de cálculo inmutable. Un recálculo crea nueva entrada, nunca sobrescribe.
    Preparado para Fase 4+. En Fase 1 solo se crea el contenedor.
    """
    __tablename__ = "calculation_runs"

    id: Mapped[UUIDPk]
    revision_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("revisions.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )
    triggered_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        SAEnum("queued", "running", "succeeded", "failed", "cancelled", name="job_status_enum"),
        nullable=False, default="queued"
    )
    engine_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[LongText]
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relaciones
    revision: Mapped["Revision"] = relationship(back_populates="calculation_runs")
