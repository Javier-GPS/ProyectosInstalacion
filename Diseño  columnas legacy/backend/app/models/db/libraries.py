"""
Salvi Studio · Columns — Modelos de bibliotecas maestras
Fase 1, sección 11.

Regla fundamental (P-07): una biblioteca publicada es INMUTABLE.
Para modificar se crea una nueva versión que "sustituye a" la anterior.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.database import Base, TimestampMixin
from app.models.db.base_types import UUIDPk, CodeStr, ShortStr, LongText


class LibraryType(str):
    """Tipos de biblioteca (sección 11, Fase 1)."""
    NORMS = "norms"
    MATERIALS = "materials"
    STANDARD_GEOMETRIES = "standard_geometries"
    PROCESSES = "processes"
    SUPPLIERS = "suppliers"
    COSTS = "costs"
    CO2_FACTORS = "co2_factors"
    UNITS_FORMATS = "units_formats"
    TEMPLATES = "templates"
    CORPORATE_EQUIPMENT = "corporate_equipment"


class Library(Base, TimestampMixin):
    """
    Contenedor de una biblioteca maestra.
    Cada tipo de biblioteca agrupa sus versiones.
    """
    __tablename__ = "libraries"

    id: Mapped[UUIDPk]
    code: Mapped[CodeStr] = mapped_column(unique=True, index=True)
    name: Mapped[ShortStr]
    description: Mapped[LongText]
    library_type: Mapped[str] = mapped_column(
        SAEnum(
            "norms", "materials", "standard_geometries", "processes",
            "suppliers", "costs", "co2_factors", "units_formats",
            "templates", "corporate_equipment",
            name="library_type_enum"
        ),
        nullable=False
    )
    owner_role: Mapped[str] = mapped_column(String(64), nullable=False)  # Rol propietario

    # Relaciones
    versions: Mapped[List["LibraryVersion"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )


class LibraryVersion(Base, TimestampMixin):
    """
    Versión inmutable de una biblioteca maestra.
    Ciclo: borrador → revisión → publicado → retirado.
    P-07: una versión publicada NUNCA se modifica.
    Sección 11.1, Fase 1.
    """
    __tablename__ = "library_versions"

    id: Mapped[UUIDPk]
    library_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[str] = mapped_column(String(32), nullable=False)  # ej: "2.1.0"
    status: Mapped[str] = mapped_column(
        SAEnum("draft", "under_review", "published", "deprecated", "withdrawn",
               name="library_version_status_enum"),
        nullable=False, default="draft"
    )
    description: Mapped[LongText]
    change_notes: Mapped[LongText]

    # Vigencia
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Trazabilidad de publicación (P-04)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Versión sucesora (cuando se crea una nueva versión que la sustituye)
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("library_versions.id"), nullable=True
    )

    # Contenido — JSONB estructurado por tipo de biblioteca
    # La estructura interna varía: materiales, normas, costes, etc.
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Hash de integridad del contenido
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relaciones
    library: Mapped["Library"] = relationship(back_populates="versions")


class Material(Base, TimestampMixin):
    """
    Material estructural. Entidad de dominio dentro de la biblioteca de materiales.
    Propiedades mecánicas por espesor, temperatura y condición de suministro (P-06: SI).
    Sección 11.1, Fase 1 + sección 4.2 doc rector.
    """
    __tablename__ = "materials"

    id: Mapped[UUIDPk]
    library_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("library_versions.id"), nullable=False
    )
    code: Mapped[CodeStr] = mapped_column(index=True)
    name: Mapped[ShortStr]
    material_family: Mapped[str] = mapped_column(
        SAEnum("steel", "aluminum_extruded", "aluminum_sheet", "concrete", "fasteners",
               name="material_family_enum"),
        nullable=False
    )

    # Propiedades base en SI (P-06)
    # Tensión en Pa, densidad en kg/m³, módulo en Pa
    yield_strength_pa: Mapped[Optional[float]] = mapped_column(nullable=True)       # f_y
    ultimate_strength_pa: Mapped[Optional[float]] = mapped_column(nullable=True)    # f_u
    youngs_modulus_pa: Mapped[Optional[float]] = mapped_column(nullable=True)       # E
    poisson_ratio: Mapped[Optional[float]] = mapped_column(nullable=True)           # ν
    density_kg_m3: Mapped[Optional[float]] = mapped_column(nullable=True)           # ρ
    thermal_expansion_1_k: Mapped[Optional[float]] = mapped_column(nullable=True)   # α

    # Propiedades extendidas por espesor/aleación/temple (JSONB)
    extended_properties: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Aplicabilidad
    min_thickness_m: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_thickness_m: Mapped[Optional[float]] = mapped_column(nullable=True)
    applicable_standards: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Soldabilidad y HAZ (aluminio)
    weldable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    haz_properties: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Corrosión y acabados
    corrosion_class: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    compatible_finishes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # CO2 de referencia (kgCO2e/kg)
    co2_factor_kg_per_kg: Mapped[Optional[float]] = mapped_column(nullable=True)
    co2_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
