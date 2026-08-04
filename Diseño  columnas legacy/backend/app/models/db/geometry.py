"""
Salvi Studio · Columns — Modelos DB Fase 2: Geometría Paramétrica
SS-COL-F02-GEO v0.2

Entidades: GeometryModel, Mast, MastSegment, SectionLaw, SectionProfile,
MastJoint, Arm, Attachment, CableLoadPoint, DoorAssembly, BaseInterface,
ManufacturingConstraintSet, GeometryValidation, GeometryArtifact.

Principios: determinismo, inmutabilidad histórica, unidades SI internas.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.models.db.base_types import UUIDPk, ShortStr, CodeStr


# ── Enums ──────────────────────────────────────────────────────────────────────

class GeometryQualityState(str, enum.Enum):
    DRAFT = "draft"
    GEOMETRY_VALID = "geometrically_valid"
    MANUFACTURABLE = "manufacturable"
    CALCULATION_READY = "calculation_ready"
    CAD_READY = "cad_ready"
    OBSOLETE = "obsolete"


class GeometryLOD(str, enum.Enum):
    G0 = "G0"   # esquema comercial
    G1 = "G1"   # paramétrico nominal (fuente de verdad)
    G2 = "G2"   # cálculo
    G3 = "G3"   # fabricación
    G4 = "G4"   # CAD liberado


class SectionLawType(str, enum.Enum):
    CONSTANT = "constant"
    LINEAR = "linear"
    STEPPED = "stepped"
    TABLE = "table"
    IMPORTED = "imported"


class SectionProfileType(str, enum.Enum):
    CIRCULAR = "circular"
    POLYGONAL_REGULAR = "polygonal_regular"
    FOLDED = "folded"
    EXTRUDED = "extruded"
    CONCRETE_HOLLOW = "concrete_hollow"


class JointType(str, enum.Enum):
    TELESCOPIC = "telescopic"
    FLANGED = "flanged"
    WELDED = "welded"
    SLEEVE = "sleeve"


class ArmType(str, enum.Enum):
    STRAIGHT = "straight"
    CURVED = "curved"
    DAVIT = "davit"         # báculo
    CRUCIFORM = "cruciform"
    RADIAL_CROWN = "radial_crown"
    POST_TOP = "post_top"
    ADAPTER = "adapter"


class AttachmentType(str, enum.Enum):
    LUMINAIRE = "luminaire"
    SOLAR_PANEL = "solar_panel"
    BATTERY_CABINET = "battery_cabinet"
    SIGN_BANNER = "sign_banner"
    CAMERA_SENSOR = "camera_sensor"
    ANTENNA = "antenna"
    TRAFFIC_LIGHT = "traffic_light"
    GENERIC = "generic"


class CableLoadState(str, enum.Enum):
    CONFIRMED = "confirmed"
    ESTIMATED = "estimated"
    PENDING = "pending"


class BaseInterfaceType(str, enum.Enum):
    PLATE = "plate"
    EMBEDDED = "embedded"


class GeometryArtifactFormat(str, enum.Enum):
    STEP = "step"
    DXF = "dxf"
    GLTF = "gltf"
    SVG = "svg"
    JSON = "json"
    GLB = "glb"
    PDF = "pdf"


class GeometryArtifactStatus(str, enum.Enum):
    GENERATING = "generating"
    READY = "ready"
    OBSOLETE = "obsolete"
    FAILED = "failed"


class ValidationResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    BLOCKED = "blocked"


class ValidationSeverity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    EXCEPTION_REQUIRED = "exception_required"


class ManufacturingProcess(str, enum.Enum):
    TUBE = "tube"
    FOLDED_WELD = "folded_longitudinal_weld"
    EXTRUSION = "extrusion"
    CENTRIFUGED_CONCRETE = "centrifuged_concrete"
    MACHINED = "machined"
    WELDED_ASSEMBLY = "welded_assembly"
    BOLTED = "bolted"
    OTHER = "other"


# ── Tablas ─────────────────────────────────────────────────────────────────────

class GeometryModel(Base, TimestampMixin):
    """
    Modelo geométrico completo de una alternativa de columna (ProductGeometry).
    Vinculado a una revisión de proyecto. Una revisión puede tener un modelo
    geométrico activo; las revisiones congeladas tienen su modelo inmutable
    a través del snapshot.

    Principio: determinismo — mismas entradas + versión de motor = misma geometría.
    """
    __tablename__ = "geometry_models"

    id: Mapped[UUIDPk]
    project_revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schema_version: Mapped[ShortStr] = mapped_column(
        String(20), nullable=False, default="2.0"
    )
    lod: Mapped[GeometryLOD] = mapped_column(
        Enum(GeometryLOD, name="geometry_lod"), nullable=False, default=GeometryLOD.G1
    )
    quality_state: Mapped[GeometryQualityState] = mapped_column(
        Enum(GeometryQualityState, name="geometry_quality_state", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=GeometryQualityState.DRAFT,
    )
    coordinate_convention: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Z_up_X_azimuth0"
    )
    canonical_units: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SI"
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )  # manual, template, library, imported, derived
    geometry_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[Optional[ShortStr]] = mapped_column(String(30), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    masts: Mapped[list["Mast"]] = relationship(back_populates="geometry_model", cascade="all, delete-orphan")
    validations: Mapped[list["GeometryValidation"]] = relationship(back_populates="geometry_model", cascade="all, delete-orphan")
    artifacts: Mapped[list["GeometryArtifact"]] = relationship(back_populates="geometry_model", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_geometry_models_revision", "project_revision_id"),
        Index("ix_geometry_models_hash", "geometry_hash"),
        Index("ix_geometry_models_quality", "quality_state"),
    )


class SectionProfile(Base, TimestampMixin):
    """
    Perfil 2D versionado. Componente de biblioteca reutilizable.
    P-07: la versión publicada es inmutable.
    """
    __tablename__ = "section_profiles"

    id: Mapped[UUIDPk]
    library_version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("library_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    code: Mapped[CodeStr] = mapped_column(String(50), nullable=False)
    profile_type: Mapped[SectionProfileType] = mapped_column(
        Enum(SectionProfileType, name="section_profile_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    # Geometry stored as JSON (2D contour, voids, characteristic dimensions)
    geometry_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Canonical dimension: diameter for circular, inscribed circle for polygonal, etc.
    canonical_dimension_m: Mapped[float] = mapped_column(Float, nullable=False)
    orientation_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    schema_version: Mapped[ShortStr] = mapped_column(String(20), nullable=False, default="2.0")
    # Pre-computed section properties (cached, regenerated from params)
    properties_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # area_m2, centroid, Ixx, Iyy, Ixy, J_torsional, perimeter_m, etc.

    __table_args__ = (
        Index("ix_section_profiles_code", "code"),
        Index("ix_section_profiles_type", "profile_type"),
    )


class SectionLaw(Base, TimestampMixin):
    """
    Ley de variación de sección S(z) en un intervalo.
    Tipos: constant, linear, stepped, table, imported.
    """
    __tablename__ = "section_laws"

    id: Mapped[UUIDPk]
    law_type: Mapped[SectionLawType] = mapped_column(
        Enum(SectionLawType, name="section_law_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    interpolation: Mapped[str] = mapped_column(String(30), nullable=False, default="linear")
    continuity: Mapped[str] = mapped_column(String(10), nullable=False, default="C0")
    # Parameters depend on type: {bottom_d_m, top_d_m, thickness_m} for linear circular, etc.
    parameter_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    profile_ref: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("section_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    domain: Mapped[str] = mapped_column(String(50), nullable=False, default="mast_segment")

    profile: Mapped[Optional["SectionProfile"]] = relationship()

    __table_args__ = (
        Index("ix_section_laws_type", "law_type"),
    )


class ManufacturingConstraintSet(Base, TimestampMixin):
    """
    Conjunto versionado de restricciones de fabricación y transporte.
    La geometría puede ser matemáticamente válida pero no fabricable
    bajo un conjunto concreto.
    """
    __tablename__ = "manufacturing_constraint_sets"

    id: Mapped[UUIDPk]
    code: Mapped[CodeStr] = mapped_column(String(50), nullable=False, unique=True)
    version: Mapped[ShortStr] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Rules JSON: max_piece_length_m, max_thickness_mm, min_diameter_steel_mm,
    # min_diameter_concrete_mm, standard_tapers, max_logistic_length_m, etc.
    rules_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_mfg_constraints_code", "code"),
        Index("ix_mfg_constraints_active", "is_active"),
    )


class Mast(Base, TimestampMixin):
    """
    Fuste principal de una columna. Continuo o segmentado.
    Contiene uno o varios MastSegment.
    """
    __tablename__ = "masts"

    id: Mapped[UUIDPk]
    geometry_model_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("geometry_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    nominal_height_m: Mapped[float] = mapped_column(Float, nullable=False)
    base_type: Mapped[BaseInterfaceType] = mapped_column(
        Enum(BaseInterfaceType, name="base_interface_type", values_callable=lambda x: [e.value for e in x]), nullable=False, default=BaseInterfaceType.PLATE
    )
    material_ref: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("materials.id", ondelete="SET NULL"),
        nullable=True,
    )
    manufacturing_process: Mapped[Optional[ManufacturingProcess]] = mapped_column(
        Enum(ManufacturingProcess, name="manufacturing_process", values_callable=lambda x: [e.value for e in x]), nullable=True
    )
    constraint_set_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("manufacturing_constraint_sets.id", ondelete="SET NULL"),
        nullable=True,
    )
    total_height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # derived
    total_mass_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # derived
    cg_z_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)           # derived CG height
    is_segmented: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    geometry_model: Mapped["GeometryModel"] = relationship(back_populates="masts")
    segments: Mapped[list["MastSegment"]] = relationship(
        back_populates="mast", cascade="all, delete-orphan", order_by="MastSegment.segment_order"
    )
    joints: Mapped[list["MastJoint"]] = relationship(back_populates="mast", cascade="all, delete-orphan")
    arms: Mapped[list["Arm"]] = relationship(back_populates="mast", cascade="all, delete-orphan")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="mast", cascade="all, delete-orphan")
    cable_load_points: Mapped[list["CableLoadPoint"]] = relationship(back_populates="mast", cascade="all, delete-orphan")
    door_assemblies: Mapped[list["DoorAssembly"]] = relationship(back_populates="mast", cascade="all, delete-orphan")
    base_interface: Mapped[Optional["BaseInterface"]] = relationship(back_populates="mast", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("nominal_height_m > 0 AND nominal_height_m <= 30", name="ck_mast_height"),
        Index("ix_masts_geometry_model", "geometry_model_id"),
    )


class MastSegment(Base, TimestampMixin):
    """
    Tramo fabricable del fuste. Tiene sección y ley de variación propias.
    Suma de longitudes + solapes debe reproducir la altura total (GEO-006).
    Piezas > 12 m requieren segmentación o excepción (GEO-005).
    """
    __tablename__ = "mast_segments"

    id: Mapped[UUIDPk]
    mast_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("masts.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False)
    piece_id: Mapped[ShortStr] = mapped_column(String(20), nullable=False, default="P01")
    z_start_m: Mapped[float] = mapped_column(Float, nullable=False)
    z_end_m: Mapped[float] = mapped_column(Float, nullable=False)
    section_law_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("section_laws.id", ondelete="RESTRICT"),
        nullable=False,
    )
    physical_length_m: Mapped[float] = mapped_column(Float, nullable=False)
    visible_length_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transport_orientation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    manufacturing_process: Mapped[Optional[ManufacturingProcess]] = mapped_column(
        Enum(ManufacturingProcess, name="manufacturing_process", values_callable=lambda x: [e.value for e in x]), nullable=True
    )
    material_ref: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("materials.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Derived properties (cached)
    mass_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cg_z_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Features: door references, cable slots, etc.
    features_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Manufacturing properties: costura orientation, HAZ mask, tolerances
    manufacturing_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    mast: Mapped["Mast"] = relationship(back_populates="segments")
    section_law: Mapped["SectionLaw"] = relationship()

    __table_args__ = (
        CheckConstraint("z_end_m > z_start_m", name="ck_segment_z_order"),
        CheckConstraint("physical_length_m > 0", name="ck_segment_length_positive"),
        Index("ix_mast_segments_mast", "mast_id"),
        Index("ix_mast_segments_order", "mast_id", "segment_order"),
    )


class MastJoint(Base, TimestampMixin):
    """
    Unión entre tramos del fuste (Fase 2 — geometría).
    Tipos: telescópica, embridada, soldada en taller, manguito.
    Distinta de joints.Joint (Fase 9), que modela el detalle de fabricación
    y verificación de la unión; esta entidad solo registra su posición
    geométrica dentro del modelo paramétrico.
    """
    __tablename__ = "joints"

    id: Mapped[UUIDPk]
    mast_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("masts.id", ondelete="CASCADE"),
        nullable=False,
    )
    lower_segment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mast_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    upper_segment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mast_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    joint_type: Mapped[JointType] = mapped_column(
        Enum(JointType, name="joint_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    overlap_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    z_joint_m: Mapped[float] = mapped_column(Float, nullable=False)
    # Geometry details: plates, bolt pattern, clearances, etc.
    geometry_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    mast: Mapped["Mast"] = relationship(back_populates="joints")
    lower_segment: Mapped["MastSegment"] = relationship(foreign_keys=[lower_segment_id])
    upper_segment: Mapped["MastSegment"] = relationship(foreign_keys=[upper_segment_id])

    __table_args__ = (
        Index("ix_joints_mast", "mast_id"),
    )


class Arm(Base, TimestampMixin):
    """
    Brazo, báculo, soporte, cruceta o adaptador unido al fuste.
    Puede tener múltiples accesorios (luminarias, paneles, etc.).
    """
    __tablename__ = "arms"

    id: Mapped[UUIDPk]
    mast_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("masts.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_segment_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mast_segments.id", ondelete="CASCADE"),
        nullable=True,
    )
    arm_type: Mapped[ArmType] = mapped_column(
        Enum(ArmType, name="arm_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    code: Mapped[Optional[ShortStr]] = mapped_column(String(30), nullable=True)
    library_item_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), nullable=True
    )
    library_version: Mapped[Optional[ShortStr]] = mapped_column(String(20), nullable=True)
    # Anchor: connection point and orientation on the mast
    anchor_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # {z_m, azimuth_rad, offset_m, connection_diameter_m}
    # Axis curve: parametric description of arm centerline
    axis_curve_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    section_law_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("section_laws.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Homogeneous 4x4 transform relative to parent
    transform_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    roll_angle_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    luminaire_interface_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # {diameter_m, length_m, inclination_rad, orientation_rad}
    fabrication_mode: Mapped[Optional[ManufacturingProcess]] = mapped_column(
        Enum(ManufacturingProcess, name="manufacturing_process", values_callable=lambda x: [e.value for e in x]), nullable=True
    )
    symmetry_group: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    material_ref: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("materials.id", ondelete="SET NULL"),
        nullable=True,
    )
    mass_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cg_local_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    projected_areas_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    mast: Mapped["Mast"] = relationship(back_populates="arms")
    section_law: Mapped[Optional["SectionLaw"]] = relationship()

    __table_args__ = (
        Index("ix_arms_mast", "mast_id"),
    )


class Attachment(Base, TimestampMixin):
    """
    Luminaria, panel solar, batería, cartel, cámara, antena, semáforo u otro
    accesorio unido al fuste o a un brazo.
    LOD mínimo: G1 para que el accesorio sea calculation_ready.
    """
    __tablename__ = "attachments"

    id: Mapped[UUIDPk]
    mast_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("masts.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_arm_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("arms.id", ondelete="SET NULL"),
        nullable=True,
    )
    attachment_type: Mapped[AttachmentType] = mapped_column(
        Enum(AttachmentType, name="attachment_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    code: Mapped[Optional[ShortStr]] = mapped_column(String(30), nullable=True)
    library_item_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    library_version: Mapped[Optional[ShortStr]] = mapped_column(String(20), nullable=True)
    library_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    lod: Mapped[GeometryLOD] = mapped_column(
        Enum(GeometryLOD, name="geometry_lod"), nullable=False, default=GeometryLOD.G1
    )
    transform_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Obligatory: mass, CG, projected areas
    mass_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cg_local_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Projected areas by direction: {deg_0: m2, deg_30: m2, ...} or envelope
    projected_areas_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Aerodynamic: Cd table or single value
    aero_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Extra properties: orientation, inclination, etc.
    properties_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    mast: Mapped["Mast"] = relationship(back_populates="attachments")
    arm: Mapped[Optional["Arm"]] = relationship()

    __table_args__ = (
        Index("ix_attachments_mast", "mast_id"),
        Index("ix_attachments_type", "attachment_type"),
    )


class CableLoadPoint(Base, TimestampMixin):
    """
    Punto de anclaje de un cable de catenaria.
    Máximo 6 cables por alternativa (GEO-008).
    La Fase 2 modela la interfaz de carga, no la catenaria completa.
    """
    __tablename__ = "cable_load_points"

    id: Mapped[UUIDPk]
    mast_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("masts.id", ondelete="CASCADE"),
        nullable=False,
    )
    cable_identifier: Mapped[ShortStr] = mapped_column(String(20), nullable=False)
    anchor_z_m: Mapped[float] = mapped_column(Float, nullable=False)
    # Position on the perimeter or eccentricity relative to axis
    position_local_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    azimuth_rad: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tension_n: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cable_state: Mapped[CableLoadState] = mapped_column(
        Enum(CableLoadState, name="cable_load_state", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CableLoadState.PENDING,
    )
    # Interface type for future hardware sizing
    interface_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    interface_envelope_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    mast: Mapped["Mast"] = relationship(back_populates="cable_load_points")

    __table_args__ = (
        Index("ix_cable_load_points_mast", "mast_id"),
    )


class DoorAssembly(Base, TimestampMixin):
    """
    Hueco de puerta, marco/refuerzo y soporte interior en columnas metálicas.
    No permitido en hormigón (GEO-009).
    El hueco no puede atravesar una unión entre tramos.
    """
    __tablename__ = "door_assemblies"

    id: Mapped[UUIDPk]
    mast_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("masts.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mast_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Opening: height_m, width_m, corner_radii_m, z_bottom_m, orientation_rad, tolerance_m
    opening_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Frame/reinforcement: profile, thickness, dimensions, weld nominal
    reinforcement_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reinforcement_ref: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    # Physical door envelope (for interference checks)
    door_envelope_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Interior support: plate/rail dimensions, perforations, position
    interior_support_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Cable routing reserved volume
    cable_path_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Ground connection point
    earth_connection_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    mast: Mapped["Mast"] = relationship(back_populates="door_assemblies")
    segment: Mapped["MastSegment"] = relationship()

    __table_args__ = (
        Index("ix_door_assemblies_mast", "mast_id"),
    )


class BaseInterface(Base, TimestampMixin):
    """
    Placa base (con patrón de pernos) o empotramiento.
    Esta fase valida geometría, no resistencia.
    """
    __tablename__ = "base_interfaces"

    id: Mapped[UUIDPk]
    mast_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("masts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    interface_type: Mapped[BaseInterfaceType] = mapped_column(
        Enum(BaseInterfaceType, name="base_interface_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    # Plate: contour, thickness_m, holes, orientation, shaft_passage_d_m, stiffeners
    # Embedded: length_m, section_ref, protection, cable_entry, fill_volume
    geometry_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Bolt pattern: standard (200x200, 250x250, 300x300) or custom coordinates
    bolt_pattern_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Bolt type: L, J, embedded, post-installed; diameter, length, thread
    bolt_details_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    embedment_length_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    mast: Mapped["Mast"] = relationship(back_populates="base_interface")

    __table_args__ = (
        Index("ix_base_interfaces_mast", "mast_id"),
    )


class GeometryValidation(Base, TimestampMixin):
    """
    Resultado de ejecutar una regla GEO contra un modelo geométrico.
    Inmutable: cada ejecución crea nuevas filas.
    """
    __tablename__ = "geometry_validations"

    id: Mapped[UUIDPk]
    geometry_model_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("geometry_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    geometry_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rule_code: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[ValidationSeverity] = mapped_column(
        Enum(ValidationSeverity, name="validation_severity", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    result: Mapped[ValidationResult] = mapped_column(
        Enum(ValidationResult, name="validation_result", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Exception: approved_by, reason, expires_at
    exception_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    geometry_model: Mapped["GeometryModel"] = relationship(back_populates="validations")

    __table_args__ = (
        Index("ix_geometry_validations_model", "geometry_model_id"),
        Index("ix_geometry_validations_rule", "rule_code"),
        Index("ix_geometry_validations_hash", "geometry_hash"),
        Index("ix_geometry_validations_result", "result"),
    )


class GeometryArtifact(Base, TimestampMixin):
    """
    Artefacto geométrico generado: malla, STEP, DXF, glTF, SVG, PDF.
    Vinculado a un geometry_hash: si el hash cambia → artifact queda OBSOLETE.
    No sobrescribir; siempre nuevo artefacto versionado.
    """
    __tablename__ = "geometry_artifacts"

    id: Mapped[UUIDPk]
    geometry_model_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("geometry_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    geometry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_format: Mapped[GeometryArtifactFormat] = mapped_column(
        Enum(GeometryArtifactFormat, name="geometry_artifact_format", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    lod: Mapped[GeometryLOD] = mapped_column(
        Enum(GeometryLOD, name="geometry_lod"), nullable=False
    )
    status: Mapped[GeometryArtifactStatus] = mapped_column(
        Enum(GeometryArtifactStatus, name="geometry_artifact_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=GeometryArtifactStatus.GENERATING,
    )
    storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    generator_version: Mapped[Optional[ShortStr]] = mapped_column(String(30), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    geometry_model: Mapped["GeometryModel"] = relationship(back_populates="artifacts")

    __table_args__ = (
        Index("ix_geometry_artifacts_model", "geometry_model_id"),
        Index("ix_geometry_artifacts_hash", "geometry_hash"),
        Index("ix_geometry_artifacts_status", "status"),
    )
