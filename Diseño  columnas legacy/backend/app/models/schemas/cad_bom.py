"""
Salvi Studio · Columns — Schemas Pydantic Fase 14
CAD paramétrico, BOM y documentación industrial
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

# ── Constantes ────────────────────────────────────────────────────────────────

VALID_SNAPSHOT_STATES = {"DRAFT", "REVIEW", "APPROVED", "RELEASED", "OBSOLETE"}
VALID_CAD_LEVELS      = {"G0_SCHEMATIC","G1_CALC","G2_ENGINEERING","G3_MANUFACTURING","G4_AS_BUILT"}
VALID_ARTIFACT_TYPES  = {
    "CAD_STEP","CAD_DXF","CAD_GLB","DRAWING_PDF",
    "BOM_EBOM","BOM_MBOM","BOM_PBOM","BOM_SBOM","BOM_ASBUILT","BOM_SERVICE",
    "ROUTING","DOC_PACKAGE","MANIFEST",
}
VALID_ARTIFACT_STATES = {"PENDING","GENERATING","VALID","ERROR","SUPERSEDED"}
VALID_BOM_VIEWS       = {"EBOM","MBOM","PBOM","SBOM","ASBUILT","SERVICE"}
VALID_BOM_LINE_TYPES  = {
    "MANUFACTURED","PURCHASED","RAW_MATERIAL","CONSUMABLE",
    "SUBCONTRACTED","PHANTOM","ALTERNATIVE","WASTE",
}
VALID_CHANGE_CLASSES  = {"EDITORIAL","INDUSTRIAL","GEOMETRIC","STRUCTURAL","REGULATORY"}
VALID_CHANGE_STATUSES = {"DRAFT","UNDER_REVIEW","APPROVED","REJECTED","IMPLEMENTED"}
VALID_SEVERITIES      = {"BLOCKING","ERROR","WARNING","INFO"}
VALID_OP_TYPES        = {
    "RECEPTION","CUTTING","BEVELING","BENDING","WELDING_LONGITUDINAL",
    "WELDING_CIRCUMFERENTIAL","ASSEMBLY","STRAIGHTENING","GALVANIZING",
    "PAINTING","MACHINING","INSPECTION","RELEASE",
}
VALID_RELEASE_GATES   = {"PENDING","PASSED","FAILED","WAIVED"}
VALID_DOC_AUDIENCES   = {"CLIENT","ENGINEERING","PRODUCTION","QUALITY","SUPPLIER","SITE","REGULATORY"}
VALID_LANGUAGES       = {"es","en","fr","ca","it","pt"}
VALID_FEATURE_TYPES   = {"HOLE","BEND","WELD","SLOT","BEVEL","STATION","EXTRUSION","CUT","EMBOSS","THREAD"}


# ── ProductSnapshot ───────────────────────────────────────────────────────────

class ProductSnapshotCreate(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=80)
    revision: str = Field(..., min_length=1, max_length=20)
    material: Optional[str] = Field(default=None, max_length=40)
    cad_level: str = Field(default="G2_ENGINEERING")
    geometry_params: Dict[str, Any] = Field(default_factory=dict)
    structural_hashes: Dict[str, str] = Field(default_factory=dict)
    library_versions: Dict[str, str] = Field(default_factory=dict)
    source_revision_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_by: Optional[str] = Field(default=None, max_length=120)

    @field_validator("cad_level")
    @classmethod
    def check_cad_level(cls, v):
        if v not in VALID_CAD_LEVELS:
            raise ValueError(f"cad_level must be one of {VALID_CAD_LEVELS}")
        return v


class ProductSnapshotOut(BaseModel):
    id: UUID
    product_code: str
    revision: str
    state: str
    snapshot_hash: Optional[str]
    material: Optional[str]
    cad_level: str
    mass_kg_cad: Optional[float]
    mass_kg_bom: Optional[float]
    mass_kg_shipped: Optional[float]
    cost_eur_industrial: Optional[float]
    co2_kgco2e: Optional[float]
    is_fit_for_release: bool
    release_blockers: List[Any]
    notes: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    approved_at: Optional[datetime]
    released_at: Optional[datetime]
    model_config = {"from_attributes": True}


# ── PartDefinition ────────────────────────────────────────────────────────────

class PartDefinitionCreate(BaseModel):
    part_code: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=200)
    material: Optional[str] = Field(default=None, max_length=80)
    thickness_mm: Optional[float] = Field(default=None, gt=0)
    geometry_params: Dict[str, Any] = Field(default_factory=dict)
    cad_level: str = Field(default="G2_ENGINEERING")
    is_purchased: bool = False
    quantity_per_assy: int = Field(default=1, ge=1)

    @field_validator("cad_level")
    @classmethod
    def check_cad_level(cls, v):
        if v not in VALID_CAD_LEVELS:
            raise ValueError(f"cad_level must be one of {VALID_CAD_LEVELS}")
        return v


class PartDefinitionOut(PartDefinitionCreate):
    id: UUID
    snapshot_id: UUID
    assembly_id: Optional[UUID]
    mass_kg: Optional[float]
    surface_area_m2: Optional[float]
    volume_cm3: Optional[float]
    part_hash: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── FeatureDefinition ─────────────────────────────────────────────────────────

class FeatureDefinitionCreate(BaseModel):
    feature_id: str = Field(..., min_length=1, max_length=80)
    feature_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    coordinate_system: Optional[Dict[str, Any]] = None
    dependencies: List[str] = Field(default_factory=list)
    normative_source: Optional[str] = Field(default=None, max_length=120)
    suppression_rule: Optional[str] = None
    is_critical: bool = False

    @field_validator("feature_type")
    @classmethod
    def check_feature_type(cls, v):
        if v not in VALID_FEATURE_TYPES:
            raise ValueError(f"feature_type must be one of {VALID_FEATURE_TYPES}")
        return v


class FeatureDefinitionOut(FeatureDefinitionCreate):
    id: UUID
    part_id: UUID
    feature_hash: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── CadArtifact ───────────────────────────────────────────────────────────────

class CadJobRequest(BaseModel):
    snapshot_id: UUID
    artifact_type: str = Field(default="CAD_STEP")
    cad_level: str = Field(default="G3_MANUFACTURING")
    idempotency_key: Optional[str] = Field(default=None, max_length=64)
    created_by: Optional[str] = Field(default=None, max_length=120)

    @field_validator("artifact_type")
    @classmethod
    def check_type(cls, v):
        if v not in VALID_ARTIFACT_TYPES:
            raise ValueError(f"artifact_type must be one of {VALID_ARTIFACT_TYPES}")
        return v

    @field_validator("cad_level")
    @classmethod
    def check_level(cls, v):
        if v not in VALID_CAD_LEVELS:
            raise ValueError(f"cad_level must be one of {VALID_CAD_LEVELS}")
        return v


class CadArtifactOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    artifact_type: str
    state: str
    format: str
    cad_level: str
    checksum: Optional[str]
    file_size_bytes: Optional[int]
    generator_version: Optional[str]
    source_snapshot_hash: Optional[str]
    units: str
    validation_status: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── DrawingArtifact ───────────────────────────────────────────────────────────

class DrawingJobRequest(BaseModel):
    snapshot_id: UUID
    drawing_type: str = Field(..., min_length=1, max_length=60)
    language: str = Field(default="es")
    idempotency_key: Optional[str] = Field(default=None, max_length=64)

    @field_validator("language")
    @classmethod
    def check_lang(cls, v):
        if v not in VALID_LANGUAGES:
            raise ValueError(f"language must be one of {VALID_LANGUAGES}")
        return v


class DrawingArtifactOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    drawing_code: str
    drawing_type: str
    revision: str
    state: str
    format: str
    language: str
    source_snapshot_hash: Optional[str]
    validation_status: Optional[str]
    validation_errors: List[Any]
    is_fit_for_manufacture: bool
    error_message: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── BOM ───────────────────────────────────────────────────────────────────────

class BomBuildRequest(BaseModel):
    snapshot_id: UUID
    bom_view: str = Field(default="EBOM")
    include_costs: bool = True

    @field_validator("bom_view")
    @classmethod
    def check_view(cls, v):
        if v not in VALID_BOM_VIEWS:
            raise ValueError(f"bom_view must be one of {VALID_BOM_VIEWS}")
        return v


class BomLineCreate(BaseModel):
    item_code: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1, max_length=300)
    line_type: str = Field(default="MANUFACTURED")
    quantity: float = Field(default=1.0, gt=0)
    quantity_unit: str = Field(default="EA", max_length=20)
    quantity_rule: Optional[str] = Field(default=None, max_length=40)
    scrap_factor: float = Field(default=0.0, ge=0.0, lt=1.0)
    min_lot: Optional[float] = Field(default=None, gt=0)
    mass_kg_unit: Optional[float] = None
    cost_eur_unit: Optional[float] = None
    material: Optional[str] = Field(default=None, max_length=80)
    is_critical: bool = False

    @field_validator("line_type")
    @classmethod
    def check_line_type(cls, v):
        if v not in VALID_BOM_LINE_TYPES:
            raise ValueError(f"line_type must be one of {VALID_BOM_LINE_TYPES}")
        return v


class BomLineOut(BomLineCreate):
    id: UUID
    header_id: UUID
    part_id: Optional[UUID]
    position: int
    created_at: datetime
    model_config = {"from_attributes": True}


class BomHeaderOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    bom_view: str
    revision: str
    state: str
    bom_hash: Optional[str]
    total_mass_kg: Optional[float]
    total_cost_eur: Optional[float]
    currency: str
    created_at: datetime
    lines: List[BomLineOut] = []
    model_config = {"from_attributes": True}


# ── Routing ───────────────────────────────────────────────────────────────────

class RoutingBuildRequest(BaseModel):
    snapshot_id: UUID
    part_id: Optional[UUID] = None
    plant: Optional[str] = Field(default=None, max_length=60)


class OperationCreate(BaseModel):
    sequence_no: int = Field(..., ge=1)
    operation_type: str
    work_center: Optional[str] = Field(default=None, max_length=80)
    description: str = Field(..., min_length=1, max_length=300)
    setup_time_h: float = Field(default=0.0, ge=0)
    run_time_h: float = Field(default=0.0, ge=0)
    is_stop_point: bool = False
    is_subcontracted: bool = False
    supplier_code: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("operation_type")
    @classmethod
    def check_op_type(cls, v):
        if v not in VALID_OP_TYPES:
            raise ValueError(f"operation_type must be one of {VALID_OP_TYPES}")
        return v


class OperationOut(OperationCreate):
    id: UUID
    routing_id: UUID
    created_at: datetime
    model_config = {"from_attributes": True}


class RoutingOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    routing_code: str
    name: str
    revision: str
    is_primary: bool
    plant: Optional[str]
    total_time_h: Optional[float]
    created_at: datetime
    operations: List[OperationOut] = []
    model_config = {"from_attributes": True}


# ── DocumentPackage ───────────────────────────────────────────────────────────

class DocumentPackageRequest(BaseModel):
    snapshot_id: UUID
    audience: str
    language: str = Field(default="es")
    idempotency_key: Optional[str] = None

    @field_validator("audience")
    @classmethod
    def check_audience(cls, v):
        if v not in VALID_DOC_AUDIENCES:
            raise ValueError(f"audience must be one of {VALID_DOC_AUDIENCES}")
        return v

    @field_validator("language")
    @classmethod
    def check_lang(cls, v):
        if v not in VALID_LANGUAGES:
            raise ValueError(f"language must be one of {VALID_LANGUAGES}")
        return v


class DocumentPackageOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    audience: str
    language: str
    state: str
    package_hash: Optional[str]
    expiry_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── ReleaseRecord ─────────────────────────────────────────────────────────────

class ReleaseValidateRequest(BaseModel):
    snapshot_id: UUID
    waive_warnings: bool = False


class ReleaseValidateOut(BaseModel):
    snapshot_id: UUID
    is_fit_for_release: bool
    blockers: List[str]
    errors: List[str]
    warnings: List[str]
    info: List[str]


class ReleaseRequest(BaseModel):
    snapshot_id: UUID
    release_code: str = Field(..., min_length=1, max_length=80)
    approved_by: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class ReleaseRecordOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    release_code: str
    state: str
    gates: Dict[str, str]
    blockers: List[Any]
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    published_to_erp: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── ChangeRequest ─────────────────────────────────────────────────────────────

class ChangeImpactRequest(BaseModel):
    snapshot_id: UUID
    change_class: str
    description: str = Field(..., min_length=1)
    affected_fields: List[str] = Field(default_factory=list)

    @field_validator("change_class")
    @classmethod
    def check_class(cls, v):
        if v not in VALID_CHANGE_CLASSES:
            raise ValueError(f"change_class must be one of {VALID_CHANGE_CLASSES}")
        return v


class ChangeImpactOut(BaseModel):
    change_class: str
    requires_recalc: bool
    affected_artifacts: List[str]
    affected_documents: List[str]
    estimated_effort: str   # LOW, MEDIUM, HIGH
    recommendation: str


class ChangeRequestCreate(BaseModel):
    snapshot_id: UUID
    change_class: str
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1)
    requested_by: Optional[str] = Field(default=None, max_length=120)

    @field_validator("change_class")
    @classmethod
    def check_class(cls, v):
        if v not in VALID_CHANGE_CLASSES:
            raise ValueError(f"change_class must be one of {VALID_CHANGE_CLASSES}")
        return v


class ChangeRequestOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    change_class: str
    status: str
    title: str
    requires_recalc: bool
    requested_by: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── ValidationResult ──────────────────────────────────────────────────────────

class ValidationResultOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    check_code: str
    severity: str
    message: str
    context: Dict[str, Any]
    is_waived: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── InspectionPlan ────────────────────────────────────────────────────────────

class InspectionCharacteristicCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=60)
    description: str = Field(..., min_length=1, max_length=300)
    characteristic_type: str
    method: Optional[str] = None
    nominal: Optional[float] = None
    tolerance_plus: Optional[float] = None
    tolerance_minus: Optional[float] = None
    unit: Optional[str] = None
    frequency: Optional[str] = None
    is_critical: bool = False
    ctq_level: Optional[str] = None


class InspectionPlanCreate(BaseModel):
    plan_code: str = Field(..., min_length=1, max_length=80)
    created_by: Optional[str] = None


class InspectionPlanOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    plan_code: str
    revision: str
    state: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ── AsBuiltMeasurement ────────────────────────────────────────────────────────

class AsBuiltMeasurementCreate(BaseModel):
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    measured_value: float
    unit: str = Field(..., min_length=1, max_length=20)
    nominal: float
    tolerance_plus: float = Field(..., ge=0)
    tolerance_minus: float = Field(..., ge=0)
    instrument: Optional[str] = None
    measured_by: Optional[str] = None
    measured_at: datetime


class AsBuiltMeasurementOut(AsBuiltMeasurementCreate):
    id: UUID
    is_conformant: bool
    deviation: Optional[float]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── NonConformance ────────────────────────────────────────────────────────────

class NonConformanceCreate(BaseModel):
    nc_code: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1)
    severity: str = Field(default="ERROR")
    detected_at: datetime

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v):
        if v not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {VALID_SEVERITIES}")
        return v


class NonConformanceOut(NonConformanceCreate):
    id: UUID
    disposition: Optional[str]
    requires_requalification: bool
    resolved_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── ArtifactManifest ──────────────────────────────────────────────────────────

class ArtifactManifestOut(BaseModel):
    id: UUID
    snapshot_id: UUID
    manifest_hash: str
    artifact_count: int
    is_complete: bool
    entries: List[Dict[str, Any]]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── ERP Integration ───────────────────────────────────────────────────────────

class ErpPublishRequest(BaseModel):
    release_record_id: UUID
    target_system: str = Field(default="ERP", max_length=40)
    include_bom: bool = True
    include_routing: bool = True
    dry_run: bool = False


class ErpPublishOut(BaseModel):
    release_record_id: UUID
    target_system: str
    published: bool
    transaction_id: Optional[str]
    items_published: int
    dry_run: bool
    errors: List[str]
