"""
Fase 12 · Catálogo y Selección Estándar — Pydantic v2 schemas
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.db.catalog import (
    ApplicabilityStatus,
    CompatibilityRuleOp,
    DataSourceType,
    EvidenceQualityStatus,
    EvidenceType12,
    ImportJobStatus,
    OptionType,
    ProductStatus,
    RankingProfile,
    SelectionRunStatus,
    SubstitutionType,
    ThirdPartyStatus,
    VerificationRoute,
)


# ---------------------------------------------------------------------------
# Product Family
# ---------------------------------------------------------------------------

class ProductFamilyRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=2, max_length=256)
    material: str = Field(..., pattern=r"^(STEEL|ALUMINIUM|CONCRETE|MIXED)$")
    geometry_type: Optional[str] = None
    base_type: Optional[str] = None
    is_third_party: bool = False
    owner: Optional[str] = None
    extra_data: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def third_party_needs_status(self) -> "ProductFamilyRequest":
        # Third-party families need explicit status tracking
        return self


class ProductFamilyResponse(BaseModel):
    id: UUID
    code: str
    name: str
    material: str
    geometry_type: Optional[str]
    base_type: Optional[str]
    has_hierarchy: bool
    is_third_party: bool
    third_party_status: Optional[ThirdPartyStatus]
    owner: Optional[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Standard Product
# ---------------------------------------------------------------------------

class StandardProductRequest(BaseModel):
    family_id: UUID
    code: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=2, max_length=256)
    status: ProductStatus = ProductStatus.DRAFT
    nominal_height_m: Optional[float] = Field(None, ge=0.5, le=50.0)
    total_height_m: Optional[float] = Field(None, ge=0.5, le=55.0)
    base_type: Optional[str] = Field(None, pattern=r"^(PLATE|EMBEDDED|SPECIAL)$")
    material_grade: Optional[str] = None
    material_data_source: DataSourceType = DataSourceType.PENDING
    piece_length_m: Optional[float] = Field(None, ge=0.0, le=20.0)
    piece_mass_kg: Optional[float] = Field(None, ge=0.0, le=20000.0)
    is_segmented: bool = False
    segment_count: Optional[int] = Field(None, ge=1, le=20)
    total_co2_kg: Optional[float] = Field(None, ge=0.0)
    sales_regions: Optional[list[str]] = None
    lead_time_days: Optional[int] = Field(None, ge=0, le=730)
    owner: Optional[str] = None

    @model_validator(mode="after")
    def height_consistency(self) -> "StandardProductRequest":
        if self.nominal_height_m and self.total_height_m:
            if self.total_height_m < self.nominal_height_m:
                raise ValueError("CAT-DATA-010: total_height_m < nominal_height_m")
        return self

    @model_validator(mode="after")
    def segmented_needs_count(self) -> "StandardProductRequest":
        if self.is_segmented and self.segment_count is None:
            raise ValueError("CAT-DATA-010: is_segmented=True requiere segment_count")
        return self

    @model_validator(mode="after")
    def piece_length_check(self) -> "StandardProductRequest":
        if not self.is_segmented and self.piece_length_m and self.piece_length_m > 12.0:
            raise ValueError("CAT-GEO-002: pieza >12m sin segmentación no permitida")
        return self


class StandardProductResponse(BaseModel):
    id: UUID
    family_id: UUID
    code: str
    name: str
    status: ProductStatus
    current_revision: Optional[str]
    nominal_height_m: Optional[float]
    total_height_m: Optional[float]
    base_type: Optional[str]
    material_grade: Optional[str]
    material_data_source: DataSourceType
    is_segmented: bool
    segment_count: Optional[int]
    quality_index: Optional[float]
    sales_regions: Optional[list[str]]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Product Revision
# ---------------------------------------------------------------------------

class PublishRevisionRequest(BaseModel):
    revision_number: str = Field(..., min_length=1, max_length=32)
    published_by: str = Field(..., min_length=2)
    reviewed_by: list[str] = Field(..., min_length=1)   # dual review
    change_summary: Optional[str] = None

    @model_validator(mode="after")
    def dual_review_required(self) -> "PublishRevisionRequest":
        if len(self.reviewed_by) < 2:
            raise ValueError("CAT-EVID-006: publicación requiere revisión técnica y de producto (2 revisores)")
        return self


# ---------------------------------------------------------------------------
# Product Variant
# ---------------------------------------------------------------------------

class ProductVariantRequest(BaseModel):
    variant_code: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    option_type: OptionType
    requires_recalculation: bool = False
    alters_mass: bool = False
    alters_wind_area: bool = False
    alters_fatigue: bool = False
    parameter_deltas: Optional[dict[str, Any]] = None
    cost_delta_eur: Optional[float] = None
    co2_delta_kg: Optional[float] = None

    @model_validator(mode="after")
    def structural_needs_recalc(self) -> "ProductVariantRequest":
        if self.option_type == OptionType.STRUCTURAL and not self.requires_recalculation:
            raise ValueError("CAT-CONFIG-009: opción STRUCTURAL debe requerir recálculo")
        return self


# ---------------------------------------------------------------------------
# Compatibility Rule
# ---------------------------------------------------------------------------

class CompatibilityRuleRequest(BaseModel):
    family_id: UUID
    rule_code: str = Field(..., min_length=1, max_length=64)
    rule_op: CompatibilityRuleOp
    condition: dict[str, Any]
    consequence: dict[str, Any]
    rule_dsl: Optional[str] = None
    version: str = "1.0"
    description: Optional[str] = None


class CompatibilityRuleResult(BaseModel):
    rule_code: str
    rule_op: CompatibilityRuleOp
    result: str   # PASS/FAIL/UNKNOWN
    responsible_fields: list[str]
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Performance Envelope
# ---------------------------------------------------------------------------

class PerformanceEnvelopeRequest(BaseModel):
    product_id: UUID
    applicability_status: ApplicabilityStatus = ApplicabilityStatus.UNKNOWN
    max_moment_knm: Optional[float] = Field(None, ge=0.0)
    max_shear_kn: Optional[float] = Field(None, ge=0.0)
    max_axial_kn: Optional[float] = Field(None, ge=0.0)
    max_height_m: Optional[float] = Field(None, ge=0.0, le=50.0)
    min_height_m: Optional[float] = Field(None, ge=0.0, le=50.0)
    max_wind_area_m2: Optional[float] = Field(None, ge=0.0)
    max_luminaire_mass_kg: Optional[float] = Field(None, ge=0.0)
    max_utilization: Optional[float] = Field(None, ge=0.0, le=1.0)
    domain_envelope: Optional[list[Any]] = None
    domain_type: Optional[str] = None
    norm_edition: Optional[str] = None
    country_scope: Optional[list[str]] = None


class DomainEvaluateRequest(BaseModel):
    product_id: UUID
    moment_knm: Optional[float] = None
    shear_kn: Optional[float] = None
    axial_kn: Optional[float] = None
    height_m: Optional[float] = None
    wind_area_m2: Optional[float] = None
    luminaire_mass_kg: Optional[float] = None
    country_code: Optional[str] = None
    norm_edition: Optional[str] = None


class DomainEvaluateResponse(BaseModel):
    applicability_status: ApplicabilityStatus
    inside_domain: bool
    boundary_margins: dict[str, float]
    extrapolation_detected: bool
    governing_dimension: Optional[str]


# ---------------------------------------------------------------------------
# Evidence Record
# ---------------------------------------------------------------------------

class EvidenceRecordRequest(BaseModel):
    product_id: UUID
    evidence_type: EvidenceType12
    source: Optional[str] = None
    reference_code: Optional[str] = None
    tested_object: Optional[str] = None
    conditions: Optional[dict[str, Any]] = None
    results: Optional[dict[str, Any]] = None
    applicability: Optional[dict[str, Any]] = None
    evidence_date: Optional[str] = None
    expiry_date: Optional[str] = None
    has_domain: bool = False
    file_ref: Optional[str] = None

    @model_validator(mode="after")
    def no_domain_means_not_applicable(self) -> "EvidenceRecordRequest":
        # Evidence without domain stays PENDING until reviewed
        return self


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class RequirementVector(BaseModel):
    """Normalized project requirements for selection."""
    project_id: Optional[UUID] = None
    project_revision: Optional[str] = None
    # Geometry requirements
    nominal_height_m: float = Field(..., ge=1.0, le=50.0)
    base_type: str = Field(..., pattern=r"^(PLATE|EMBEDDED|SPECIAL)$")
    material: Optional[str] = None     # STEEL/ALUMINIUM/CONCRETE
    market_country: str = Field(..., min_length=2, max_length=4)
    norm_edition: Optional[str] = None
    # Load requirements
    moment_knm: Optional[float] = Field(None, ge=0.0)
    shear_kn: Optional[float] = Field(None, ge=0.0)
    axial_kn: Optional[float] = Field(None, ge=0.0)
    wind_area_m2: Optional[float] = Field(None, ge=0.0)
    luminaire_mass_kg: Optional[float] = Field(None, ge=0.0)
    has_catenary: bool = False
    # Configuration preferences
    door_required: Optional[bool] = None
    head_diameter_mm: Optional[float] = None
    arm_count: Optional[int] = Field(None, ge=0, le=6)
    finish: Optional[str] = None
    # Constraints
    max_utilization_limit: float = Field(default=0.9, ge=0.1, le=1.0)
    maturity_level_required: Optional[str] = None
    ranking_profile: RankingProfile = RankingProfile.COMMERCIAL
    # Availability
    min_stock_status: Optional[str] = None


class SelectionRequest(BaseModel):
    requirements: RequirementVector
    catalog_snapshot_id: Optional[str] = None
    force_candidate_id: Optional[UUID] = None   # engineering mode only
    run_by: Optional[str] = None


class CandidateEvaluationResponse(BaseModel):
    product_id: UUID
    product_code: str
    passed_hard_filters: bool
    discard_reasons: Optional[list[str]]
    applicability_status: Optional[ApplicabilityStatus]
    verification_route: Optional[VerificationRoute]
    max_utilization: Optional[float]
    governing_check: Optional[str]
    compliant: Optional[bool]
    hierarchy_ordinal: Optional[int]
    is_immediately_superior: bool
    is_inferior_candidate: bool
    score_total: Optional[float]
    label: Optional[str]

    model_config = {"from_attributes": True}


class SelectionRunResponse(BaseModel):
    id: UUID
    selection_code: Optional[str]
    status: SelectionRunStatus
    recommended_product_id: Optional[UUID]
    recommended_revision: Optional[str]
    confidence: Optional[str]
    governing_check: Optional[str]
    max_utilization: Optional[float]
    next_action: Optional[str]
    selection_trace_hash: Optional[str]
    evaluations: list[CandidateEvaluationResponse] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Substitution
# ---------------------------------------------------------------------------

class SubstitutionRequest(BaseModel):
    from_product_id: UUID
    to_product_id: UUID
    substitution_type: SubstitutionType
    conditions: Optional[dict[str, Any]] = None
    adaptations_required: Optional[list[str]] = None
    requires_recalculation: bool = True
    interface_changes: bool = False
    approved_by: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def no_self_substitution(self) -> "SubstitutionRequest":
        if self.from_product_id == self.to_product_id:
            raise ValueError("CAT-DATA-010: un producto no puede sustituirse a sí mismo")
        return self


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

class ImportJobRequest(BaseModel):
    source_type: str = Field(..., pattern=r"^(EXCEL|CSV|API|MANUAL)$")
    source_file_name: Optional[str] = None
    mapping_template_id: Optional[str] = None
    mapping_template_version: Optional[str] = None
    idempotency_key: Optional[str] = None


class ImportJobResponse(BaseModel):
    id: UUID
    job_code: Optional[str]
    status: ImportJobStatus
    total_rows: Optional[int]
    imported_ok: Optional[int]
    errors: Optional[int]
    warnings: Optional[int]
    error_report: Optional[dict[str, Any]]
    published_at: Optional[str]

    model_config = {"from_attributes": True}


class PublishImportRequest(BaseModel):
    reviewed_by: list[str] = Field(..., min_length=2)
    published_by: str = Field(..., min_length=2)

    @model_validator(mode="after")
    def dual_review_on_publish(self) -> "PublishImportRequest":
        if len(self.reviewed_by) < 2:
            raise ValueError("CAT-EVID-006: publicación staging requiere 2 revisores")
        return self


# ---------------------------------------------------------------------------
# Market Availability
# ---------------------------------------------------------------------------

class MarketAvailabilityRequest(BaseModel):
    product_id: UUID
    country_code: str = Field(..., min_length=2, max_length=4)
    norm_edition: Optional[str] = None
    manufacturing_site: Optional[str] = None
    stock_status: Optional[str] = None
    lead_time_days: Optional[int] = Field(None, ge=0)
    supply_risk: Optional[str] = Field(None, pattern=r"^(LOW|MEDIUM|HIGH)$")
    price_eur: Optional[float] = Field(None, ge=0.0)
    currency: str = "EUR"
    is_offerable: bool = False
    is_technically_valid: bool = True


# ---------------------------------------------------------------------------
# Health dashboard
# ---------------------------------------------------------------------------

class CatalogHealthResponse(BaseModel):
    family_code: Optional[str]
    missing_geometry_count: int
    unresolved_material_count: int
    expired_evidence_count: int
    no_domain_evidence_count: int
    suspended_supplier_count: int
    mass_discrepancy_count: int
    duplicate_candidate_count: int
    total_products: int
    health_score: float   # 0–1


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------

class ImpactAnalysisRequest(BaseModel):
    product_id: UUID
    change_type: str = Field(...,
        pattern=r"^(GEOMETRY|MATERIAL|DOMAIN|EVIDENCE|STATUS|COMMERCIAL|NORM)$")
    change_description: Optional[str] = None


class ImpactAnalysisResponse(BaseModel):
    product_id: UUID
    open_project_count: int
    open_offer_count: int
    affected_families: list[str]
    invalidated_selections: int
    stale_evidences: int
    invalidated_certificates: int
    affected_bom_count: int
    action_required: str
