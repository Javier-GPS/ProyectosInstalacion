"""
Salvi Studio · Columns — Modelos DB Fase 14
CAD paramétrico, BOM y documentación industrial
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


# ── Enums (sufijo 14 para unicidad en PostgreSQL) ─────────────────────────────

class SnapshotState14(str, enum.Enum):
    DRAFT    = "DRAFT"
    REVIEW   = "REVIEW"
    APPROVED = "APPROVED"
    RELEASED = "RELEASED"
    OBSOLETE = "OBSOLETE"


class CadLevel14(str, enum.Enum):
    G0_SCHEMATIC    = "G0_SCHEMATIC"
    G1_CALC         = "G1_CALC"
    G2_ENGINEERING  = "G2_ENGINEERING"
    G3_MANUFACTURING = "G3_MANUFACTURING"
    G4_AS_BUILT     = "G4_AS_BUILT"


class ArtifactType14(str, enum.Enum):
    CAD_STEP        = "CAD_STEP"
    CAD_DXF         = "CAD_DXF"
    CAD_GLB         = "CAD_GLB"
    DRAWING_PDF     = "DRAWING_PDF"
    BOM_EBOM        = "BOM_EBOM"
    BOM_MBOM        = "BOM_MBOM"
    BOM_PBOM        = "BOM_PBOM"
    BOM_SBOM        = "BOM_SBOM"
    BOM_ASBUILT     = "BOM_ASBUILT"
    BOM_SERVICE     = "BOM_SERVICE"
    ROUTING         = "ROUTING"
    DOC_PACKAGE     = "DOC_PACKAGE"
    MANIFEST        = "MANIFEST"


class ArtifactState14(str, enum.Enum):
    PENDING    = "PENDING"
    GENERATING = "GENERATING"
    VALID      = "VALID"
    ERROR      = "ERROR"
    SUPERSEDED = "SUPERSEDED"


class BomView14(str, enum.Enum):
    EBOM    = "EBOM"
    MBOM    = "MBOM"
    PBOM    = "PBOM"
    SBOM    = "SBOM"
    ASBUILT = "ASBUILT"
    SERVICE = "SERVICE"


class BomLineType14(str, enum.Enum):
    MANUFACTURED  = "MANUFACTURED"
    PURCHASED     = "PURCHASED"
    RAW_MATERIAL  = "RAW_MATERIAL"
    CONSUMABLE    = "CONSUMABLE"
    SUBCONTRACTED = "SUBCONTRACTED"
    PHANTOM       = "PHANTOM"
    ALTERNATIVE   = "ALTERNATIVE"
    WASTE         = "WASTE"


class ChangeClass14(str, enum.Enum):
    EDITORIAL  = "EDITORIAL"
    INDUSTRIAL = "INDUSTRIAL"
    GEOMETRIC  = "GEOMETRIC"
    STRUCTURAL = "STRUCTURAL"
    REGULATORY = "REGULATORY"


class ChangeStatus14(str, enum.Enum):
    DRAFT          = "DRAFT"
    UNDER_REVIEW   = "UNDER_REVIEW"
    APPROVED       = "APPROVED"
    REJECTED       = "REJECTED"
    IMPLEMENTED    = "IMPLEMENTED"


class ValidationSeverity14(str, enum.Enum):
    BLOCKING = "BLOCKING"
    ERROR    = "ERROR"
    WARNING  = "WARNING"
    INFO     = "INFO"


class OperationType14(str, enum.Enum):
    RECEPTION            = "RECEPTION"
    CUTTING              = "CUTTING"
    BEVELING             = "BEVELING"
    BENDING              = "BENDING"
    WELDING_LONGITUDINAL = "WELDING_LONGITUDINAL"
    WELDING_CIRCUMFERENTIAL = "WELDING_CIRCUMFERENTIAL"
    ASSEMBLY             = "ASSEMBLY"
    STRAIGHTENING        = "STRAIGHTENING"
    GALVANIZING          = "GALVANIZING"
    PAINTING             = "PAINTING"
    MACHINING            = "MACHINING"
    INSPECTION           = "INSPECTION"
    RELEASE              = "RELEASE"


class ReleaseGate14(str, enum.Enum):
    PENDING = "PENDING"
    PASSED  = "PASSED"
    FAILED  = "FAILED"
    WAIVED  = "WAIVED"


class DocumentAudience14(str, enum.Enum):
    CLIENT      = "CLIENT"
    ENGINEERING = "ENGINEERING"
    PRODUCTION  = "PRODUCTION"
    QUALITY     = "QUALITY"
    SUPPLIER    = "SUPPLIER"
    SITE        = "SITE"
    REGULATORY  = "REGULATORY"


# ── Tablas ────────────────────────────────────────────────────────────────────

class ProductSnapshot(Base):
    """Contrato industrial inmutable que agrupa la definición completa del producto."""
    __tablename__ = "product_snapshot"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_code        = Column(String(80), nullable=False)
    revision            = Column(String(20), nullable=False)
    state               = Column(String(20), nullable=False, default=SnapshotState14.DRAFT)
    snapshot_hash       = Column(String(64), nullable=True)
    source_revision_id  = Column(UUID(as_uuid=True), nullable=True)   # Fase 13 OptimizationRun
    geometry_hash       = Column(String(64), nullable=True)
    material            = Column(String(40), nullable=True)
    cad_level           = Column(String(25), nullable=False, default=CadLevel14.G2_ENGINEERING)
    geometry_params     = Column(JSONB, nullable=False, default=dict)
    structural_hashes   = Column(JSONB, nullable=False, default=dict)
    library_versions    = Column(JSONB, nullable=False, default=dict)
    mass_kg_cad         = Column(Float, nullable=True)
    mass_kg_bom         = Column(Float, nullable=True)
    mass_kg_shipped     = Column(Float, nullable=True)
    cost_eur_industrial = Column(Float, nullable=True)
    co2_kgco2e          = Column(Float, nullable=True)
    is_fit_for_release  = Column(Boolean, nullable=False, default=False)
    release_blockers    = Column(JSONB, nullable=False, default=list)
    notes               = Column(Text, nullable=True)
    created_by          = Column(String(120), nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at         = Column(DateTime(timezone=True), nullable=True)
    released_at         = Column(DateTime(timezone=True), nullable=True)

    assemblies           = relationship("ProductAssembly", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    parts                = relationship("PartDefinition", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    cad_artifacts        = relationship("CadArtifact", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    drawing_artifacts    = relationship("DrawingArtifact", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    bom_headers          = relationship("BomHeader", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    routings             = relationship("Routing", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    doc_packages         = relationship("DocumentPackage", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    release_records      = relationship("ReleaseRecord", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    change_requests      = relationship("ChangeRequest", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    validation_results   = relationship("ValidationResult", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    manifests            = relationship("ArtifactManifest", back_populates="snapshot",
                                        cascade="all, delete-orphan")
    inspection_plans     = relationship("InspectionPlan", back_populates="snapshot",
                                        cascade="all, delete-orphan")


class ProductAssembly(Base):
    """Jerarquía de montaje del producto."""
    __tablename__ = "product_assembly"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id      = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                              ondelete="CASCADE"), nullable=False)
    parent_id        = Column(UUID(as_uuid=True), ForeignKey("product_assembly.id",
                                                              ondelete="SET NULL"), nullable=True)
    code             = Column(String(80), nullable=False)
    name             = Column(String(200), nullable=False)
    level            = Column(Integer, nullable=False, default=0)  # 0=product, 1=assembly, 2=subassembly
    quantity         = Column(Integer, nullable=False, default=1)
    assembly_hash    = Column(String(64), nullable=True)
    mass_kg          = Column(Float, nullable=True)
    center_of_gravity = Column(JSONB, nullable=True)   # {x, y, z} mm
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot  = relationship("ProductSnapshot", back_populates="assemblies")
    parent    = relationship("ProductAssembly", remote_side="ProductAssembly.id")
    parts     = relationship("PartDefinition", back_populates="assembly",
                             cascade="all, delete-orphan")


class PartDefinition(Base):
    """Pieza con parámetros geométricos, material y propiedades físicas."""
    __tablename__ = "part_definition"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id      = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                              ondelete="CASCADE"), nullable=False)
    assembly_id      = Column(UUID(as_uuid=True), ForeignKey("product_assembly.id",
                                                              ondelete="SET NULL"), nullable=True)
    part_code        = Column(String(80), nullable=False)
    name             = Column(String(200), nullable=False)
    material         = Column(String(80), nullable=True)
    thickness_mm     = Column(Float, nullable=True)
    mass_kg          = Column(Float, nullable=True)
    surface_area_m2  = Column(Float, nullable=True)
    volume_cm3       = Column(Float, nullable=True)
    geometry_params  = Column(JSONB, nullable=False, default=dict)
    part_hash        = Column(String(64), nullable=True)
    cad_level        = Column(String(25), nullable=False, default=CadLevel14.G2_ENGINEERING)
    is_purchased     = Column(Boolean, nullable=False, default=False)
    quantity_per_assy = Column(Integer, nullable=False, default=1)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot  = relationship("ProductSnapshot", back_populates="parts")
    assembly  = relationship("ProductAssembly", back_populates="parts")
    features  = relationship("FeatureDefinition", back_populates="part",
                             cascade="all, delete-orphan")
    bom_lines = relationship("BomLine", back_populates="part")


class FeatureDefinition(Base):
    """Feature semántico de una pieza (hueco, taladro, pliegue, soldadura, etc.)."""
    __tablename__ = "feature_definition"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_id             = Column(UUID(as_uuid=True), ForeignKey("part_definition.id",
                                                                  ondelete="CASCADE"), nullable=False)
    feature_id          = Column(String(80), nullable=False)   # identificador estable
    feature_type        = Column(String(40), nullable=False)   # HOLE, BEND, WELD, SLOT, BEVEL, etc.
    parameters          = Column(JSONB, nullable=False, default=dict)
    coordinate_system   = Column(JSONB, nullable=True)
    dependencies        = Column(JSONB, nullable=False, default=list)
    normative_source    = Column(String(120), nullable=True)
    feature_hash        = Column(String(32), nullable=True)
    suppression_rule    = Column(Text, nullable=True)
    is_critical         = Column(Boolean, nullable=False, default=False)
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("part_id", "feature_id",
                                       name="uq_feature_def_part_feature_id"),)

    part = relationship("PartDefinition", back_populates="features")


class InterfaceDefinition(Base):
    """Acoplamiento controlado entre piezas o ensamblajes."""
    __tablename__ = "interface_definition"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id     = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                             ondelete="CASCADE"), nullable=False)
    interface_id    = Column(String(80), nullable=False)
    from_part_id    = Column(UUID(as_uuid=True), ForeignKey("part_definition.id",
                                                             ondelete="SET NULL"), nullable=True)
    to_part_id      = Column(UUID(as_uuid=True), ForeignKey("part_definition.id",
                                                             ondelete="SET NULL"), nullable=True)
    interface_type  = Column(String(40), nullable=False)   # SLIP_FIT, BOLT, WELD, PRESS, etc.
    datums          = Column(JSONB, nullable=False, default=list)
    tolerances      = Column(JSONB, nullable=False, default=dict)
    fasteners       = Column(JSONB, nullable=True)   # pernos, soldaduras, etc.
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("snapshot_id", "interface_id",
                                       name="uq_interface_def_snapshot_id"),)


class CadArtifact(Base):
    """Archivo CAD generado (STEP, DXF, GLB) con metadatos y estado."""
    __tablename__ = "cad_artifact"

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id           = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                                    ondelete="CASCADE"), nullable=False)
    artifact_type         = Column(String(30), nullable=False)
    state                 = Column(String(20), nullable=False, default=ArtifactState14.PENDING)
    format                = Column(String(10), nullable=False)   # STEP, DXF, GLB
    cad_level             = Column(String(25), nullable=False)
    file_path             = Column(String(500), nullable=True)
    checksum              = Column(String(64), nullable=True)
    file_size_bytes       = Column(Integer, nullable=True)
    generator_version     = Column(String(40), nullable=True)
    source_snapshot_hash  = Column(String(64), nullable=True)
    units                 = Column(String(10), nullable=False, default="mm")
    coordinate_system     = Column(String(40), nullable=True)
    validation_status     = Column(String(20), nullable=True)
    dependencies          = Column(JSONB, nullable=False, default=list)
    error_message         = Column(Text, nullable=True)
    idempotency_key       = Column(String(64), nullable=True)
    created_by            = Column(String(120), nullable=True)
    created_at            = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot = relationship("ProductSnapshot", back_populates="cad_artifacts")


class DrawingArtifact(Base):
    """Plano 2D generado con revisión y estado."""
    __tablename__ = "drawing_artifact"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id          = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                                   ondelete="CASCADE"), nullable=False)
    drawing_code         = Column(String(80), nullable=False)
    drawing_type         = Column(String(60), nullable=False)   # GENERAL, SEGMENT, SHEET_DEVELOPMENT, etc.
    revision             = Column(String(20), nullable=False, default="A")
    state                = Column(String(20), nullable=False, default=ArtifactState14.PENDING)
    format               = Column(String(10), nullable=False, default="PDF")
    language             = Column(String(5), nullable=False, default="es")
    file_path            = Column(String(500), nullable=True)
    checksum             = Column(String(64), nullable=True)
    source_snapshot_hash = Column(String(64), nullable=True)
    validation_status    = Column(String(20), nullable=True)
    validation_errors    = Column(JSONB, nullable=False, default=list)
    is_fit_for_manufacture = Column(Boolean, nullable=False, default=False)
    error_message        = Column(Text, nullable=True)
    idempotency_key      = Column(String(64), nullable=True)
    created_by           = Column(String(120), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot = relationship("ProductSnapshot", back_populates="drawing_artifacts")


class BomHeader(Base):
    """Cabecera de una vista BOM (EBOM, MBOM, PBOM, SBOM, etc.)."""
    __tablename__ = "bom_header"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id   = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                           ondelete="CASCADE"), nullable=False)
    bom_view      = Column(String(20), nullable=False)
    revision      = Column(String(20), nullable=False, default="A")
    state         = Column(String(20), nullable=False, default=SnapshotState14.DRAFT)
    bom_hash      = Column(String(64), nullable=True)
    total_mass_kg = Column(Float, nullable=True)
    total_cost_eur = Column(Float, nullable=True)
    currency      = Column(String(3), nullable=False, default="EUR")
    effective_date = Column(DateTime(timezone=True), nullable=True)
    notes         = Column(Text, nullable=True)
    created_by    = Column(String(120), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("snapshot_id", "bom_view",
                                       name="uq_bom_header_snapshot_view"),)

    snapshot = relationship("ProductSnapshot", back_populates="bom_headers")
    lines    = relationship("BomLine", back_populates="header",
                            cascade="all, delete-orphan",
                            order_by="BomLine.position")


class BomLine(Base):
    """Componente dentro de una vista BOM con cantidad y regla de cálculo."""
    __tablename__ = "bom_line"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    header_id         = Column(UUID(as_uuid=True), ForeignKey("bom_header.id",
                                                               ondelete="CASCADE"), nullable=False)
    part_id           = Column(UUID(as_uuid=True), ForeignKey("part_definition.id",
                                                               ondelete="SET NULL"), nullable=True)
    position          = Column(Integer, nullable=False, default=0)
    item_code         = Column(String(80), nullable=False)
    description       = Column(String(300), nullable=False)
    line_type         = Column(String(20), nullable=False, default=BomLineType14.MANUFACTURED)
    quantity          = Column(Float, nullable=False, default=1.0)
    quantity_unit     = Column(String(20), nullable=False, default="EA")
    quantity_rule     = Column(String(40), nullable=True)   # DIRECT, GEOMETRIC, FORMULA, YIELD
    scrap_factor      = Column(Float, nullable=False, default=0.0)
    min_lot           = Column(Float, nullable=True)
    mass_kg_unit      = Column(Float, nullable=True)
    cost_eur_unit     = Column(Float, nullable=True)
    material          = Column(String(80), nullable=True)
    supplier_code     = Column(String(80), nullable=True)
    is_critical       = Column(Boolean, nullable=False, default=False)
    notes             = Column(Text, nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    header = relationship("BomHeader", back_populates="lines")
    part   = relationship("PartDefinition", back_populates="bom_lines")


class MaterialRequirement(Base):
    """Materia prima con formato, merma y trazabilidad."""
    __tablename__ = "material_requirement"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id     = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                             ondelete="CASCADE"), nullable=False)
    part_id         = Column(UUID(as_uuid=True), ForeignKey("part_definition.id",
                                                             ondelete="SET NULL"), nullable=True)
    material_code   = Column(String(80), nullable=False)
    description     = Column(String(200), nullable=False)
    format          = Column(String(60), nullable=True)    # chapa, perfil, tubo, barra
    dimensions      = Column(JSONB, nullable=True)
    quantity_net    = Column(Float, nullable=False)
    quantity_purchase = Column(Float, nullable=False)
    unit            = Column(String(20), nullable=False, default="kg")
    scrap_factor    = Column(Float, nullable=False, default=0.05)
    density_kg_dm3  = Column(Float, nullable=True)
    supplier_code   = Column(String(80), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Routing(Base):
    """Ruta de fabricación homologada para un snapshot."""
    __tablename__ = "routing"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id   = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                           ondelete="CASCADE"), nullable=False)
    part_id       = Column(UUID(as_uuid=True), ForeignKey("part_definition.id",
                                                           ondelete="SET NULL"), nullable=True)
    routing_code  = Column(String(80), nullable=False)
    name          = Column(String(200), nullable=False)
    revision      = Column(String(20), nullable=False, default="A")
    is_primary    = Column(Boolean, nullable=False, default=True)
    plant         = Column(String(60), nullable=True)
    total_time_h  = Column(Float, nullable=True)
    notes         = Column(Text, nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot    = relationship("ProductSnapshot", back_populates="routings")
    operations  = relationship("Operation", back_populates="routing",
                               cascade="all, delete-orphan",
                               order_by="Operation.sequence_no")


class Operation(Base):
    """Operación secuencial en una ruta de fabricación."""
    __tablename__ = "operation"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    routing_id        = Column(UUID(as_uuid=True), ForeignKey("routing.id",
                                                               ondelete="CASCADE"), nullable=False)
    sequence_no       = Column(Integer, nullable=False)
    operation_type    = Column(String(40), nullable=False)
    work_center       = Column(String(80), nullable=True)
    description       = Column(String(300), nullable=False)
    setup_time_h      = Column(Float, nullable=False, default=0.0)
    run_time_h        = Column(Float, nullable=False, default=0.0)
    tooling           = Column(JSONB, nullable=False, default=list)
    control_points    = Column(JSONB, nullable=False, default=list)
    is_stop_point     = Column(Boolean, nullable=False, default=False)
    is_subcontracted  = Column(Boolean, nullable=False, default=False)
    supplier_code     = Column(String(80), nullable=True)
    parameters        = Column(JSONB, nullable=False, default=dict)
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("routing_id", "sequence_no",
                                       name="uq_operation_routing_seq"),)

    routing       = relationship("Routing", back_populates="operations")
    instructions  = relationship("WorkInstruction", back_populates="operation",
                                 cascade="all, delete-orphan")


class WorkInstruction(Base):
    """Instrucción de trabajo estructurada ligada a una operación."""
    __tablename__ = "work_instruction"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_id  = Column(UUID(as_uuid=True), ForeignKey("operation.id",
                                                           ondelete="CASCADE"), nullable=False)
    step_no       = Column(Integer, nullable=False, default=1)
    title         = Column(String(200), nullable=False)
    body          = Column(Text, nullable=False)
    parameters    = Column(JSONB, nullable=False, default=dict)   # critical values from model
    tools         = Column(JSONB, nullable=False, default=list)
    risks         = Column(JSONB, nullable=False, default=list)
    language      = Column(String(5), nullable=False, default="es")
    created_at    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("operation_id", "step_no", "language",
                                       name="uq_work_instruction_op_step_lang"),)

    operation = relationship("Operation", back_populates="instructions")


class InspectionPlan(Base):
    """Plan de control de calidad por snapshot."""
    __tablename__ = "inspection_plan"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id    = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                            ondelete="CASCADE"), nullable=False)
    plan_code      = Column(String(80), nullable=False)
    revision       = Column(String(20), nullable=False, default="A")
    state          = Column(String(20), nullable=False, default=SnapshotState14.DRAFT)
    created_by     = Column(String(120), nullable=True)
    approved_by    = Column(String(120), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at    = Column(DateTime(timezone=True), nullable=True)

    snapshot        = relationship("ProductSnapshot", back_populates="inspection_plans")
    characteristics = relationship("InspectionCharacteristic", back_populates="plan",
                                   cascade="all, delete-orphan")


class InspectionCharacteristic(Base):
    """Control de calidad individual con tolerancia y evidencia."""
    __tablename__ = "inspection_characteristic"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id              = Column(UUID(as_uuid=True), ForeignKey("inspection_plan.id",
                                                                   ondelete="CASCADE"), nullable=False)
    code                 = Column(String(60), nullable=False)
    description          = Column(String(300), nullable=False)
    characteristic_type  = Column(String(60), nullable=False)   # DIMENSIONAL, MATERIAL, WELD, COATING
    method               = Column(String(120), nullable=True)
    instrument           = Column(String(120), nullable=True)
    nominal              = Column(Float, nullable=True)
    tolerance_plus       = Column(Float, nullable=True)
    tolerance_minus      = Column(Float, nullable=True)
    unit                 = Column(String(20), nullable=True)
    frequency            = Column(String(60), nullable=True)   # 100%, SAMPLE, FIRST_OFF
    is_critical          = Column(Boolean, nullable=False, default=False)
    ctq_level            = Column(String(10), nullable=True)   # CTQ-1, CTQ-2, CTQ-3
    reaction_plan        = Column(Text, nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    plan = relationship("InspectionPlan", back_populates="characteristics")


class DocumentPackage(Base):
    """Paquete documental diferenciado por destinatario."""
    __tablename__ = "document_package"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id      = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                              ondelete="CASCADE"), nullable=False)
    audience         = Column(String(20), nullable=False)
    language         = Column(String(5), nullable=False, default="es")
    state            = Column(String(20), nullable=False, default=ArtifactState14.PENDING)
    package_hash     = Column(String(64), nullable=True)
    file_path        = Column(String(500), nullable=True)
    checksum         = Column(String(64), nullable=True)
    expiry_at        = Column(DateTime(timezone=True), nullable=True)
    access_token     = Column(String(64), nullable=True)
    idempotency_key  = Column(String(64), nullable=True)
    created_by       = Column(String(120), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot   = relationship("ProductSnapshot", back_populates="doc_packages")
    documents  = relationship("DocumentArtifact", back_populates="package",
                              cascade="all, delete-orphan")


class DocumentArtifact(Base):
    """Documento individual dentro de un paquete."""
    __tablename__ = "document_artifact"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id      = Column(UUID(as_uuid=True), ForeignKey("document_package.id",
                                                             ondelete="CASCADE"), nullable=False)
    doc_code        = Column(String(80), nullable=False)
    title           = Column(String(300), nullable=False)
    doc_type        = Column(String(60), nullable=False)   # REPORT, DRAWING, CHECKLIST, CERTIFICATE
    format          = Column(String(10), nullable=False, default="PDF")
    language        = Column(String(5), nullable=False, default="es")
    revision        = Column(String(20), nullable=False, default="A")
    state           = Column(String(20), nullable=False, default=ArtifactState14.PENDING)
    file_path       = Column(String(500), nullable=True)
    checksum        = Column(String(64), nullable=True)
    snapshot_hash   = Column(String(64), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    package = relationship("DocumentPackage", back_populates="documents")


class ReleaseRecord(Base):
    """Liberación de revisión industrial con gates y aprobaciones."""
    __tablename__ = "release_record"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id      = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                              ondelete="CASCADE"), nullable=False)
    release_code     = Column(String(80), nullable=False)
    state            = Column(String(20), nullable=False, default=ReleaseGate14.PENDING)
    gates            = Column(JSONB, nullable=False, default=dict)   # gate_code → PENDING/PASSED/FAILED/WAIVED
    blockers         = Column(JSONB, nullable=False, default=list)
    approved_by      = Column(String(120), nullable=True)
    approved_at      = Column(DateTime(timezone=True), nullable=True)
    published_to_erp = Column(Boolean, nullable=False, default=False)
    erp_publish_at   = Column(DateTime(timezone=True), nullable=True)
    notes            = Column(Text, nullable=True)
    created_by       = Column(String(120), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot = relationship("ProductSnapshot", back_populates="release_records")


class ChangeRequest(Base):
    """Solicitud de cambio (ECR) con análisis de impacto."""
    __tablename__ = "change_request"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id     = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                             ondelete="CASCADE"), nullable=False)
    change_class    = Column(String(20), nullable=False)
    status          = Column(String(20), nullable=False, default=ChangeStatus14.DRAFT)
    title           = Column(String(300), nullable=False)
    description     = Column(Text, nullable=False)
    impact_analysis = Column(JSONB, nullable=False, default=dict)
    affected_items  = Column(JSONB, nullable=False, default=list)
    requires_recalc = Column(Boolean, nullable=False, default=False)
    effectivity     = Column(JSONB, nullable=True)   # date, lot, serial, plant
    requested_by    = Column(String(120), nullable=True)
    approved_by     = Column(String(120), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at     = Column(DateTime(timezone=True), nullable=True)

    snapshot = relationship("ProductSnapshot", back_populates="change_requests")
    orders   = relationship("ChangeOrder", back_populates="request",
                            cascade="all, delete-orphan")


class ChangeOrder(Base):
    """Orden de cambio aprobado (ECO)."""
    __tablename__ = "change_order"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id      = Column(UUID(as_uuid=True), ForeignKey("change_request.id",
                                                             ondelete="CASCADE"), nullable=False)
    order_code      = Column(String(80), nullable=False, unique=True)
    status          = Column(String(20), nullable=False, default=ChangeStatus14.APPROVED)
    implemented_changes = Column(JSONB, nullable=False, default=list)
    new_snapshot_id = Column(UUID(as_uuid=True), nullable=True)   # snapshot resultado
    approved_by     = Column(String(120), nullable=True)
    implemented_at  = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    request = relationship("ChangeRequest", back_populates="orders")


class SupplierManufacturingCapability(Base):
    """Capacidades y límites del proveedor de fabricación."""
    __tablename__ = "supplier_manufacturing_capability"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_code     = Column(String(80), nullable=False, unique=True)
    name              = Column(String(200), nullable=False)
    capabilities      = Column(JSONB, nullable=False, default=dict)   # operaciones, materiales
    max_piece_length_m = Column(Float, nullable=True)
    max_mass_kg       = Column(Float, nullable=True)
    max_width_mm      = Column(Float, nullable=True)
    certifications    = Column(JSONB, nullable=False, default=list)
    territories       = Column(JSONB, nullable=False, default=list)   # ISO country codes
    lead_time_days    = Column(Integer, nullable=True)
    is_active         = Column(Boolean, nullable=False, default=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(),
                               onupdate=func.now(), nullable=False)


class AsBuiltMeasurement(Base):
    """Medición real asociada a lote o número de serie."""
    __tablename__ = "as_built_measurement"

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id           = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                                    ondelete="CASCADE"), nullable=True)
    characteristic_id     = Column(UUID(as_uuid=True), ForeignKey("inspection_characteristic.id",
                                                                    ondelete="SET NULL"), nullable=True)
    lot_number            = Column(String(80), nullable=True)
    serial_number         = Column(String(80), nullable=True)
    measured_value        = Column(Float, nullable=True)
    unit                  = Column(String(20), nullable=True)
    nominal               = Column(Float, nullable=True)
    tolerance_plus        = Column(Float, nullable=True)
    tolerance_minus       = Column(Float, nullable=True)
    is_conformant         = Column(Boolean, nullable=False, default=True)
    deviation             = Column(Float, nullable=True)
    instrument            = Column(String(120), nullable=True)
    measured_by           = Column(String(120), nullable=True)
    measured_at           = Column(DateTime(timezone=True), nullable=False)
    created_at            = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NonConformance(Base):
    """Desviación detectada con disposición."""
    __tablename__ = "non_conformance"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id          = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                                   ondelete="CASCADE"), nullable=True)
    measurement_id       = Column(UUID(as_uuid=True), ForeignKey("as_built_measurement.id",
                                                                   ondelete="SET NULL"), nullable=True)
    nc_code              = Column(String(80), nullable=False)
    description          = Column(Text, nullable=False)
    severity             = Column(String(20), nullable=False, default=ValidationSeverity14.ERROR)
    disposition          = Column(String(40), nullable=True)   # USE_AS_IS, REWORK, SCRAP, DEVIATION
    requires_requalification = Column(Boolean, nullable=False, default=False)
    resolved_by          = Column(String(120), nullable=True)
    detected_at          = Column(DateTime(timezone=True), nullable=False)
    resolved_at          = Column(DateTime(timezone=True), nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ValidationResult(Base):
    """Resultado de validación automática de coherencia."""
    __tablename__ = "validation_result"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id     = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                             ondelete="CASCADE"), nullable=False)
    check_code      = Column(String(80), nullable=False)
    severity        = Column(String(20), nullable=False)
    message         = Column(Text, nullable=False)
    context         = Column(JSONB, nullable=False, default=dict)
    is_waived       = Column(Boolean, nullable=False, default=False)
    waived_by       = Column(String(120), nullable=True)
    waived_reason   = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot = relationship("ProductSnapshot", back_populates="validation_results")


class ArtifactManifest(Base):
    """Lista completa de archivos y hashes de una revisión."""
    __tablename__ = "artifact_manifest"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id     = Column(UUID(as_uuid=True), ForeignKey("product_snapshot.id",
                                                             ondelete="CASCADE"), nullable=False)
    manifest_hash   = Column(String(64), nullable=False)
    entries         = Column(JSONB, nullable=False, default=list)   # [{artifact_id, type, checksum, path}]
    artifact_count  = Column(Integer, nullable=False, default=0)
    is_complete     = Column(Boolean, nullable=False, default=False)
    created_by      = Column(String(120), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    snapshot = relationship("ProductSnapshot", back_populates="manifests")
