"""
Fase 12 · Catálogo y Selección Estándar
ORM models: 15 entities + enums
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProductStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    HOMOLOGATED = "HOMOLOGATED"
    RESTRICTED = "RESTRICTED"
    SUSPENDED = "SUSPENDED"
    OBSOLETE = "OBSOLETE"
    RETIRED = "RETIRED"


class ApplicabilityStatus(str, enum.Enum):
    COVERED = "COVERED"
    RECALCULATE = "RECALCULATE"
    CONDITIONAL = "CONDITIONAL"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNKNOWN = "UNKNOWN"


class VerificationRoute(str, enum.Enum):
    ROUTE_A = "ROUTE_A"   # prestación cubierta por evidencia
    ROUTE_B = "ROUTE_B"   # recálculo completo Fases 3-11
    ROUTE_C = "ROUTE_C"   # método especial / OT


class EvidenceType12(str, enum.Enum):
    TEST = "TEST"
    CALCULATION = "CALCULATION"
    CERTIFICATE = "CERTIFICATE"
    INSPECTION = "INSPECTION"
    FEM = "FEM"
    DECLARATION = "DECLARATION"
    APPROVAL = "APPROVAL"


class EvidenceQualityStatus(str, enum.Enum):
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class SubstitutionType(str, enum.Enum):
    EXACT = "EXACT"
    TECHNICAL = "TECHNICAL"
    COMMERCIAL = "COMMERCIAL"
    SUPERIOR = "SUPERIOR"
    CONDITIONAL = "CONDITIONAL"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"


class ThirdPartyStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    CONDITIONED = "CONDITIONED"
    SUSPENDED = "SUSPENDED"
    WITHDRAWN = "WITHDRAWN"


class DataSourceType(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    IMPORTED = "IMPORTED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    CONSERVATIVE = "CONSERVATIVE"
    PENDING = "PENDING"
    CONFLICT = "CONFLICT"


class RankingProfile(str, enum.Enum):
    COMMERCIAL = "COMMERCIAL"
    ENGINEERING = "ENGINEERING"
    ESG = "ESG"
    URGENT = "URGENT"
    MAINTENANCE = "MAINTENANCE"


class ImportJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    STAGED = "STAGED"
    REVIEWING = "REVIEWING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class OptionType(str, enum.Enum):
    COSMETIC = "COSMETIC"
    MINOR_GEOMETRIC = "MINOR_GEOMETRIC"
    STRUCTURAL = "STRUCTURAL"
    MATERIAL_PROCESS = "MATERIAL_PROCESS"
    MARKET = "MARKET"
    ACCESSORY = "ACCESSORY"


class CompatibilityRuleOp(str, enum.Enum):
    REQUIRE = "REQUIRE"
    EXCLUDE = "EXCLUDE"
    IMPLIES = "IMPLIES"
    RANGE = "RANGE"
    ONE_OF = "ONE_OF"
    ALL_OF = "ALL_OF"


class SelectionRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_CUSTOM = "NEEDS_CUSTOM"


# ---------------------------------------------------------------------------
# ORM Tables
# ---------------------------------------------------------------------------

class ProductFamily(Base):
    """Familia de producto: taxonomía, jerarquías, reglas y dominios."""
    __tablename__ = "product_family"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(256), nullable=False)
    material = Column(String(32), nullable=False)    # STEEL/ALUMINIUM/CONCRETE/MIXED
    geometry_type = Column(String(64), nullable=True)  # CYLINDRICAL/CONICAL/POLYGONAL/etc.
    base_type = Column(String(32), nullable=True)    # PLATE/EMBEDDED/SPECIAL
    has_hierarchy = Column(Boolean, nullable=False, default=False)
    hierarchy_description = Column(Text, nullable=True)
    extension_rules_version = Column(String(32), nullable=True)
    is_third_party = Column(Boolean, nullable=False, default=False)
    third_party_status = Column(Enum(ThirdPartyStatus, name="thirdpartystatus12"),
                                nullable=True)
    owner = Column(String(128), nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    products = relationship("StandardProduct", back_populates="family",
                            cascade="all, delete-orphan")
    hierarchies = relationship("HierarchyDefinition", back_populates="family",
                               cascade="all, delete-orphan")
    extension_rules = relationship("ExtensionRule", back_populates="family",
                                   cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_productfamily_code", "code"),
    )


class StandardProduct(Base):
    """Referencia técnica principal: geometría, material, estados, mercados."""
    __tablename__ = "standard_product"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey("product_family.id",
                       ondelete="RESTRICT"), nullable=False, index=True)
    code = Column(String(128), nullable=False)
    name = Column(String(256), nullable=False)
    status = Column(Enum(ProductStatus, name="productstatus12"), nullable=False,
                    default=ProductStatus.DRAFT)
    current_revision = Column(String(32), nullable=True)
    # Geometry (key fields — full geometry links to Phase 2)
    nominal_height_m = Column(Float, nullable=True)
    total_height_m = Column(Float, nullable=True)
    base_type = Column(String(32), nullable=True)    # PLATE/EMBEDDED/SPECIAL
    geometry_definition_id = Column(UUID(as_uuid=True), nullable=True)  # FK to Phase 2
    # Material
    material_grade = Column(String(64), nullable=True)
    material_data_source = Column(Enum(DataSourceType, name="datasourcetype12"),
                                  nullable=False, default=DataSourceType.PENDING)
    # Logistics
    piece_length_m = Column(Float, nullable=True)
    piece_mass_kg = Column(Float, nullable=True)
    is_segmented = Column(Boolean, nullable=False, default=False)
    segment_count = Column(Integer, nullable=True)
    # Sustainability
    total_co2_kg = Column(Float, nullable=True)
    # Market
    sales_regions = Column(JSONB, nullable=True)      # list of country codes
    lead_time_days = Column(Integer, nullable=True)
    minimum_order = Column(Integer, nullable=True)
    # Quality index (computed, not a blocker by itself)
    quality_index = Column(Float, nullable=True)
    # Substitution
    superseded_by_id = Column(UUID(as_uuid=True), nullable=True)   # self-referential
    # Audit
    owner = Column(String(128), nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    family = relationship("ProductFamily", back_populates="products")
    revisions = relationship("ProductRevision", back_populates="product",
                             cascade="all, delete-orphan",
                             order_by="ProductRevision.revision_number")
    variants = relationship("ProductVariant", back_populates="product",
                            cascade="all, delete-orphan")
    performance_envelopes = relationship("PerformanceEnvelope", back_populates="product",
                                         cascade="all, delete-orphan")
    evidence_records = relationship("EvidenceRecord", back_populates="product",
                                    cascade="all, delete-orphan")
    market_availabilities = relationship("MarketAvailability", back_populates="product",
                                         cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("family_id", "code", name="uq_standard_product_family_code"),
        Index("ix_standardproduct_code", "code"),
        Index("ix_standardproduct_status", "status"),
    )


class ProductRevision(Base):
    """Snapshot inmutable de datos de producto con vigencia."""
    __tablename__ = "product_revision"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("standard_product.id",
                        ondelete="CASCADE"), nullable=False, index=True)
    revision_number = Column(String(32), nullable=False)
    status_at_revision = Column(Enum(ProductStatus, name="productstatus12_rev"),
                                nullable=False)
    # Snapshot data
    geometry_snapshot = Column(JSONB, nullable=True)
    material_snapshot = Column(JSONB, nullable=True)
    performance_snapshot = Column(JSONB, nullable=True)
    options_snapshot = Column(JSONB, nullable=True)
    # Versioning
    valid_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime, nullable=True)
    superseded_by_revision = Column(String(32), nullable=True)
    change_summary = Column(Text, nullable=True)
    # Audit (immutable after publication)
    published_by = Column(String(128), nullable=True)
    published_at = Column(DateTime, nullable=True)
    reviewed_by = Column(JSONB, nullable=True)   # list of reviewer names
    data_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("StandardProduct", back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("product_id", "revision_number", name="uq_revision_product_rev"),
    )


class ProductVariant(Base):
    """Configuración discreta o paramétrica permitida de un producto."""
    __tablename__ = "product_variant"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("standard_product.id",
                        ondelete="CASCADE"), nullable=False, index=True)
    variant_code = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    option_type = Column(Enum(OptionType, name="optiontype12"), nullable=False)
    # Effects
    requires_recalculation = Column(Boolean, nullable=False, default=False)
    alters_mass = Column(Boolean, nullable=False, default=False)
    alters_wind_area = Column(Boolean, nullable=False, default=False)
    alters_fatigue = Column(Boolean, nullable=False, default=False)
    # Delta parameters (JSONB for flexibility)
    parameter_deltas = Column(JSONB, nullable=True)
    cost_delta_eur = Column(Float, nullable=True)
    co2_delta_kg = Column(Float, nullable=True)
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    evidence_id = Column(UUID(as_uuid=True), nullable=True)
    extra_data = Column(JSONB, nullable=True)

    product = relationship("StandardProduct", back_populates="variants")


class ProductOption(Base):
    """Opción configurable con efectos en geometría/cálculo/coste."""
    __tablename__ = "product_option"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey("product_family.id",
                       ondelete="CASCADE"), nullable=False, index=True)
    option_group = Column(String(64), nullable=False)   # BASE/DOOR/HEAD/ARMS/etc.
    option_key = Column(String(64), nullable=False)
    option_label = Column(String(256), nullable=True)
    option_type = Column(Enum(OptionType, name="optiontype12_opt"), nullable=False)
    # Effects
    affects_calculation = Column(Boolean, nullable=False, default=False)
    affects_bom = Column(Boolean, nullable=False, default=False)
    requires_recalculation = Column(Boolean, nullable=False, default=False)
    default_value = Column(String(128), nullable=True)
    allowed_values = Column(JSONB, nullable=True)   # list of valid values
    extra_data = Column(JSONB, nullable=True)


class CompatibilityRule(Base):
    """Regla de compatibilidad/dependencia entre opciones (DSL versionado)."""
    __tablename__ = "compatibility_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey("product_family.id",
                       ondelete="CASCADE"), nullable=False, index=True)
    rule_code = Column(String(64), nullable=False)
    rule_op = Column(Enum(CompatibilityRuleOp, name="compatibilityruleop12"), nullable=False)
    # DSL expression stored as structured JSONB
    condition = Column(JSONB, nullable=False)    # {"field": "door.height", "op": ">", "value": 600}
    consequence = Column(JSONB, nullable=False)  # {"field": "shell.thickness", "op": ">=", "value": 4}
    rule_dsl = Column(Text, nullable=True)       # human-readable DSL string
    # Metadata
    version = Column(String(16), nullable=False, default="1.0")
    is_active = Column(Boolean, nullable=False, default=True)
    approved_by = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PerformanceEnvelope(Base):
    """Prestaciones y dominio multidimensional evaluable de un producto."""
    __tablename__ = "performance_envelope"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("standard_product.id",
                        ondelete="CASCADE"), nullable=False, index=True)
    revision_id = Column(UUID(as_uuid=True), nullable=True)
    applicability_status = Column(Enum(ApplicabilityStatus, name="applicabilitystatus12"),
                                  nullable=False, default=ApplicabilityStatus.UNKNOWN)
    # Domain bounds (key scalar limits — full envelope in JSONB)
    max_moment_knm = Column(Float, nullable=True)
    max_shear_kn = Column(Float, nullable=True)
    max_axial_kn = Column(Float, nullable=True)
    max_height_m = Column(Float, nullable=True)
    min_height_m = Column(Float, nullable=True)
    max_wind_area_m2 = Column(Float, nullable=True)
    max_luminaire_mass_kg = Column(Float, nullable=True)
    max_utilization = Column(Float, nullable=True)
    # Full multidimensional domain
    domain_envelope = Column(JSONB, nullable=True)   # list of points or evaluable function
    domain_type = Column(String(32), nullable=True)  # RECTANGULAR/POLYTOPE/FUNCTION
    governing_check = Column(String(128), nullable=True)
    # Normative
    norm_edition = Column(String(64), nullable=True)
    country_scope = Column(JSONB, nullable=True)     # list of country codes
    # Cache key
    calc_hash = Column(String(64), nullable=True)
    evidence_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("StandardProduct", back_populates="performance_envelopes")


class EvidenceRecord(Base):
    """Ensayo, cálculo, certificado o aprobación que sustenta una prestación (inmutable cuando aprobado)."""
    __tablename__ = "evidence_record"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("standard_product.id",
                        ondelete="CASCADE"), nullable=False, index=True)
    evidence_type = Column(Enum(EvidenceType12, name="evidencetype12"), nullable=False)
    quality_status = Column(Enum(EvidenceQualityStatus, name="evidencequalitystatus12"),
                            nullable=False, default=EvidenceQualityStatus.PENDING)
    source = Column(String(256), nullable=True)      # lab / OT / supplier
    reference_code = Column(String(128), nullable=True)
    # Scope
    tested_object = Column(Text, nullable=True)      # exact reference/prototype
    conditions = Column(JSONB, nullable=True)        # load, position, material, door, base
    results = Column(JSONB, nullable=True)           # prestaciones, loads, failure modes
    applicability = Column(JSONB, nullable=True)     # families/references covered + extension rules
    # Validity
    evidence_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    has_domain = Column(Boolean, nullable=False, default=False)
    # File integrity
    file_hash = Column(String(64), nullable=True)
    file_ref = Column(String(512), nullable=True)
    # Audit
    approved_by = Column(String(128), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("StandardProduct", back_populates="evidence_records")


class ExtensionRule(Base):
    """Regla de extensión de evidencia a una familia de productos."""
    __tablename__ = "extension_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey("product_family.id",
                       ondelete="CASCADE"), nullable=False, index=True)
    evidence_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    rule_code = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    # Variables allowed to change
    allowed_variables = Column(JSONB, nullable=True)   # list: geometry, material, door, etc.
    allowed_ranges = Column(JSONB, nullable=True)      # variable → {min, max, tolerance}
    conservative_factor = Column(Float, nullable=True)
    # Coverage
    covers_product_ids = Column(JSONB, nullable=True)   # explicit covered product IDs
    # Validity
    is_active = Column(Boolean, nullable=False, default=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)    # expiry
    version = Column(String(16), nullable=False, default="1.0")
    approved_by = Column(String(128), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("ProductFamily", back_populates="extension_rules")


class HierarchyDefinition(Base):
    """Orden y criterio de referencia inmediatamente superior para una familia."""
    __tablename__ = "hierarchy_definition"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey("product_family.id",
                       ondelete="CASCADE"), nullable=False, index=True)
    hierarchy_code = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    # Ordinal mapping: product_id → rank_ordinal (JSONB list)
    ordinal_map = Column(JSONB, nullable=True)   # [{product_id, ordinal, basis}]
    comparison_basis = Column(Text, nullable=True)  # e.g. "full verification set"
    upgrade_rule = Column(Text, nullable=True)      # e.g. "select lowest ordinal that complies"
    cross_family_allowed = Column(Boolean, nullable=False, default=False)
    fallback = Column(String(64), nullable=True)    # e.g. "CUSTOM_DESIGN"
    version = Column(String(16), nullable=False, default="1.0")
    approved_by = Column(String(128), nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("ProductFamily", back_populates="hierarchies")


class SubstitutionRelation(Base):
    """Relación de equivalencia o sustitución entre referencias."""
    __tablename__ = "substitution_relation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_product_id = Column(UUID(as_uuid=True), ForeignKey("standard_product.id",
                             ondelete="RESTRICT"), nullable=False, index=True)
    to_product_id = Column(UUID(as_uuid=True), ForeignKey("standard_product.id",
                           ondelete="RESTRICT"), nullable=False, index=True)
    substitution_type = Column(Enum(SubstitutionType, name="substitutiontype12"), nullable=False)
    # Conditions
    conditions = Column(JSONB, nullable=True)       # conditions under which substitution applies
    adaptations_required = Column(JSONB, nullable=True)   # BOM/CAD changes needed
    requires_recalculation = Column(Boolean, nullable=False, default=True)
    interface_changes = Column(Boolean, nullable=False, default=False)
    # Validity
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    approved_by = Column(String(128), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("from_product_id", "to_product_id",
                         name="uq_substitution_from_to"),
        Index("ix_substitution_from", "from_product_id"),
    )


class MarketAvailability(Base):
    """Disponibilidad regional: mercado, proveedor, plazo y estado."""
    __tablename__ = "market_availability"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("standard_product.id",
                        ondelete="CASCADE"), nullable=False, index=True)
    country_code = Column(String(4), nullable=False)
    norm_edition = Column(String(64), nullable=True)
    manufacturing_site = Column(String(128), nullable=True)
    stock_status = Column(String(32), nullable=True)    # STOCK/ON_ORDER/PROTOTYPE/SUSPENDED
    lead_time_days = Column(Integer, nullable=True)
    lead_time_range_days = Column(Integer, nullable=True)
    minimum_order = Column(Integer, nullable=True)
    supply_risk = Column(String(16), nullable=True)    # LOW/MEDIUM/HIGH
    supply_risk_reason = Column(String(256), nullable=True)
    # Commercial
    price_eur = Column(Float, nullable=True)
    price_date = Column(DateTime, nullable=True)
    currency = Column(String(4), nullable=True, default="EUR")
    is_offerable = Column(Boolean, nullable=False, default=False)
    is_technically_valid = Column(Boolean, nullable=False, default=True)
    # Validity
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    extra_data = Column(JSONB, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("StandardProduct", back_populates="market_availabilities")

    __table_args__ = (
        UniqueConstraint("product_id", "country_code", "manufacturing_site",
                         name="uq_market_product_country_site"),
    )


class SelectionRun(Base):
    """Ejecución de selección: entrada, catálogo, algoritmo y resultados (inmutable)."""
    __tablename__ = "selection_run"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    selection_code = Column(String(64), nullable=True)   # e.g. SEL-2026-000184
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    project_revision = Column(String(64), nullable=True)
    # Snapshots
    catalog_snapshot_id = Column(String(64), nullable=True)   # catalog version hash
    requirements_snapshot = Column(JSONB, nullable=False)     # normalized requirements
    ranking_profile = Column(Enum(RankingProfile, name="rankingprofile12"),
                             nullable=False, default=RankingProfile.COMMERCIAL)
    utilization_limit = Column(Float, nullable=True, default=0.9)
    # Results
    status = Column(Enum(SelectionRunStatus, name="selectionrunstatus12"),
                    nullable=False, default=SelectionRunStatus.RUNNING)
    recommended_product_id = Column(UUID(as_uuid=True), nullable=True)
    recommended_revision = Column(String(32), nullable=True)
    recommended_configuration_hash = Column(String(64), nullable=True)
    confidence = Column(String(16), nullable=True)   # HIGH/MEDIUM/LOW/CONDITIONAL
    governing_check = Column(String(128), nullable=True)
    max_utilization = Column(Float, nullable=True)
    next_action = Column(String(64), nullable=True)
    # Trace
    selection_trace_hash = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    # Audit (immutable)
    run_by = Column(String(128), nullable=True)
    run_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    evaluations = relationship("CandidateEvaluation", back_populates="run",
                               cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_selectionrun_project_id", "project_id"),
    )


class CandidateEvaluation(Base):
    """Evaluación de un candidato: filtros, cálculo, score y estado."""
    __tablename__ = "candidate_evaluation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("selection_run.id",
                    ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_code = Column(String(128), nullable=True)
    # Filter result
    passed_hard_filters = Column(Boolean, nullable=False, default=False)
    discard_reasons = Column(JSONB, nullable=True)    # list of CAT-XXX-NNN codes
    applicability_status = Column(Enum(ApplicabilityStatus, name="applicabilitystatus12_ev"),
                                  nullable=True)
    # Verification
    verification_route = Column(Enum(VerificationRoute, name="verificationroute12"),
                                nullable=True)
    max_utilization = Column(Float, nullable=True)
    governing_check = Column(String(128), nullable=True)
    compliant = Column(Boolean, nullable=True)
    # Hierarchy
    hierarchy_ordinal = Column(Integer, nullable=True)
    is_immediately_superior = Column(Boolean, nullable=False, default=False)
    is_inferior_candidate = Column(Boolean, nullable=False, default=False)
    # Score
    score_total = Column(Float, nullable=True)
    score_breakdown = Column(JSONB, nullable=True)
    label = Column(String(32), nullable=True)   # RECOMMENDED/MIN_COST/MIN_CO2/etc.
    # Detail
    configuration_applied = Column(JSONB, nullable=True)
    configuration_delta = Column(JSONB, nullable=True)
    verification_detail = Column(JSONB, nullable=True)

    run = relationship("SelectionRun", back_populates="evaluations")


class CatalogImportJob(Base):
    """Trabajo de importación: archivo, mapeo, staging, errores y publicación."""
    __tablename__ = "catalog_import_job"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_code = Column(String(64), nullable=True)
    status = Column(Enum(ImportJobStatus, name="importjobstatus12"), nullable=False,
                    default=ImportJobStatus.PENDING)
    # Source
    source_file_name = Column(String(512), nullable=True)
    source_file_hash = Column(String(64), nullable=True)
    source_type = Column(String(32), nullable=True)    # EXCEL/CSV/API/MANUAL
    mapping_template_id = Column(String(64), nullable=True)
    mapping_template_version = Column(String(16), nullable=True)
    # Results
    total_rows = Column(Integer, nullable=True)
    imported_ok = Column(Integer, nullable=True)
    errors = Column(Integer, nullable=True)
    warnings = Column(Integer, nullable=True)
    staged_product_ids = Column(JSONB, nullable=True)   # list of UUIDs in staging
    error_report = Column(JSONB, nullable=True)
    # Publication
    published_at = Column(DateTime, nullable=True)
    published_by = Column(String(128), nullable=True)
    reviewed_by = Column(JSONB, nullable=True)
    rollback_available = Column(Boolean, nullable=False, default=True)
    rollback_snapshot = Column(JSONB, nullable=True)
    idempotency_key = Column(String(128), nullable=True, unique=True)
    # Audit
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
