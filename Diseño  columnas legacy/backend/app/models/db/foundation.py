"""
Fase 11 · Cimentaciones y Geotecnia
ORM models: enums + 10 DB entities
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

class GeotechnicalLevel(str, enum.Enum):
    G0 = "G0"   # Sin información — estimación comercial
    G1 = "G1"   # Tipo simplificado — predimensionamiento conservador
    G2 = "G2"   # Parámetros parciales — cálculo condicionado
    G3 = "G3"   # Informe geotécnico — cálculo final
    G4 = "G4"   # Control ejecución + as-built — liberado


class FoundationFamily(str, enum.Enum):
    F11_A = "F11-A"   # Zapata cuadrada con pedestal
    F11_B = "F11-B"   # Zapata rectangular orientada
    F11_C = "F11-C"   # Dado enterrado
    F11_D = "F11-D"   # Bloque circular
    F11_E = "F11-E"   # Anillo o corona
    F11_F = "F11-F"   # Bloque de empotramiento directo
    F11_G = "F11-G"   # Prefabricada estándar
    F11_H = "F11-H"   # Pilotes/micropilotes (ruta especial)


class SoilClass(str, enum.Enum):
    ROCK = "ROCK"
    DENSE_GRAVEL = "DENSE_GRAVEL"
    DENSE_SAND = "DENSE_SAND"
    MEDIUM_SAND = "MEDIUM_SAND"
    LOOSE_SAND = "LOOSE_SAND"
    STIFF_CLAY = "STIFF_CLAY"
    FIRM_CLAY = "FIRM_CLAY"
    SOFT_CLAY = "SOFT_CLAY"
    CONTROLLED_FILL = "CONTROLLED_FILL"
    UNKNOWN_FILL = "UNKNOWN_FILL"
    EXPANSIVE = "EXPANSIVE"
    COLLAPSIBLE = "COLLAPSIBLE"


class DrainageCondition(str, enum.Enum):
    DRAINED = "DRAINED"
    UNDRAINED = "UNDRAINED"
    BOTH = "BOTH"


class WaterScenario(str, enum.Enum):
    NONE = "NONE"            # No water
    PERMANENT = "PERMANENT"  # Permanent water table
    SEASONAL = "SEASONAL"    # Seasonal variation
    ACCIDENTAL = "ACCIDENTAL"
    UNKNOWN = "UNKNOWN"      # Conservative scenario applied


class FoundationCandidateStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PREDIMENSIONED = "PREDIMENSIONED"
    CALCULATED = "CALCULATED"
    VERIFIED = "VERIFIED"
    OPTIMIZED = "OPTIMIZED"
    REJECTED = "REJECTED"
    RELEASED = "RELEASED"


class FoundationCheckMode(str, enum.Enum):
    BEARING_CAPACITY = "BEARING_CAPACITY"
    OVERTURNING = "OVERTURNING"
    SLIDING = "SLIDING"
    UPLIFT = "UPLIFT"
    FLOTATION = "FLOTATION"
    PUNCHING = "PUNCHING"
    SHEAR_1D = "SHEAR_1D"
    BENDING_PLATE = "BENDING_PLATE"
    LOCAL_COMPRESSION = "LOCAL_COMPRESSION"
    DEFORMATION_SLS = "DEFORMATION_SLS"


class StiffnessModel(str, enum.Enum):
    RIGID = "RIGID"               # Fixed support
    ELASTIC_LINEAR = "ELASTIC_LINEAR"   # Winkler springs (diagonal 6×6)
    ELASTIC_FULL = "ELASTIC_FULL"       # Full 6×6 matrix
    NONLINEAR = "NONLINEAR"       # Nonlinear curves
    EXTERNAL_FEM = "EXTERNAL_FEM"       # Exported to external model


class EmbedmentFill(str, enum.Enum):
    CONCRETE = "CONCRETE"
    GROUT = "GROUT"
    GRANULAR_CONTROLLED = "GRANULAR_CONTROLLED"
    GRANULAR_UNKNOWN = "GRANULAR_UNKNOWN"


class FoundationMaturityLevel(str, enum.Enum):
    M0 = "M0"
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"


class EvidenceType(str, enum.Enum):
    MANUAL_CALC = "MANUAL_CALC"
    SOFTWARE = "SOFTWARE"
    TEST = "TEST"
    APPROVAL = "APPROVAL"
    AS_BUILT = "AS_BUILT"


# ---------------------------------------------------------------------------
# ORM Tables
# ---------------------------------------------------------------------------

class GeotechnicalSiteModel(Base):
    """Modelo geotécnico del emplazamiento: ubicación, nivel G, agua, estratigrafía."""
    __tablename__ = "geotechnical_site_model"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    revision_id = Column(UUID(as_uuid=True), nullable=True)
    geo_level = Column(Enum(GeotechnicalLevel, name="geotechnicallevel11"), nullable=False,
                       default=GeotechnicalLevel.G0)
    # Location
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    country_code = Column(String(4), nullable=True)
    municipality = Column(String(128), nullable=True)
    altitude_m = Column(Float, nullable=True)
    # Site conditions
    frost_depth_m = Column(Float, nullable=True)
    seismic_zone = Column(String(32), nullable=True)
    environmental_class = Column(String(32), nullable=True)
    # Water
    water_scenario = Column(Enum(WaterScenario, name="waterscenario11"), nullable=False,
                            default=WaterScenario.UNKNOWN)
    water_table_depth_m = Column(Float, nullable=True)    # from surface
    water_table_seasonal_high_m = Column(Float, nullable=True)
    # Flags (from 7-question intake)
    surface_type = Column(String(64), nullable=True)      # ROCK/GRAVEL/SAND/CLAY/FILL/UNKNOWN
    slope_near_m = Column(Float, nullable=True)           # distance to slope/excavation
    buried_services = Column(Boolean, nullable=True)      # True/False/None(unknown)
    proximity_slope = Column(Boolean, nullable=True)      # True/False/None
    # Data quality
    data_source = Column(JSONB, nullable=True)           # list of source descriptions
    confirmed_fields = Column(JSONB, nullable=True)      # list of confirmed field names
    proposed_fields = Column(JSONB, nullable=True)       # auto-completed fields
    blockers = Column(JSONB, nullable=True)
    warnings = Column(JSONB, nullable=True)
    calc_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    soil_layers = relationship("SoilLayer", back_populates="site",
                               cascade="all, delete-orphan", order_by="SoilLayer.layer_index")
    foundation_candidates = relationship("FoundationCandidate", back_populates="site",
                                         cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_geosite_project_id", "project_id"),
    )


class SoilLayer(Base):
    """Estrato de suelo con parámetros geotécnicos."""
    __tablename__ = "soil_layer"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("geotechnical_site_model.id",
                     ondelete="CASCADE"), nullable=False, index=True)
    layer_index = Column(Integer, nullable=False)
    depth_top_m = Column(Float, nullable=False, default=0.0)
    depth_bottom_m = Column(Float, nullable=False)
    soil_class = Column(Enum(SoilClass, name="soilclass11"), nullable=False)
    description = Column(Text, nullable=True)
    # Unit weights
    gamma_kn_m3 = Column(Float, nullable=True)           # natural unit weight
    gamma_sat_kn_m3 = Column(Float, nullable=True)       # saturated
    gamma_sub_kn_m3 = Column(Float, nullable=True)       # submerged
    # Strength — drained
    phi_deg = Column(Float, nullable=True)               # friction angle
    c_kpa = Column(Float, nullable=True)                 # cohesion
    # Strength — undrained
    cu_kpa = Column(Float, nullable=True)
    # Stiffness
    E_mpa = Column(Float, nullable=True)                 # elastic modulus
    nu = Column(Float, nullable=True)                    # Poisson ratio
    ks_kn_m3 = Column(Float, nullable=True)              # subgrade reaction coefficient (Winkler)
    # Data quality
    drainage_condition = Column(Enum(DrainageCondition, name="drainagecondition11"),
                                nullable=False, default=DrainageCondition.DRAINED)
    source = Column(String(256), nullable=True)          # e.g., "EC7 Table A.5", "Lab test"
    is_conservative_estimate = Column(Boolean, nullable=False, default=True)
    extra_data = Column(JSONB, nullable=True)

    site = relationship("GeotechnicalSiteModel", back_populates="soil_layers")


class FoundationCandidate(Base):
    """Candidato de cimentación: familia, dimensiones, orientación, materiales."""
    __tablename__ = "foundation_candidate"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("geotechnical_site_model.id",
                     ondelete="CASCADE"), nullable=False, index=True)
    family = Column(Enum(FoundationFamily, name="foundationfamily11", values_callable=lambda x: [e.value for e in x]), nullable=False)
    status = Column(Enum(FoundationCandidateStatus, name="foundationcandidatestatus11"),
                    nullable=False, default=FoundationCandidateStatus.DRAFT)
    maturity_level = Column(Enum(FoundationMaturityLevel, name="foundationmaturity11"),
                            nullable=False, default=FoundationMaturityLevel.M0)
    # Geometry
    width_m = Column(Float, nullable=True)               # B
    length_m = Column(Float, nullable=True)              # L (for rectangular)
    depth_m = Column(Float, nullable=True)               # D (embedment depth)
    diameter_m = Column(Float, nullable=True)            # for circular/annular
    pedestal_width_m = Column(Float, nullable=True)
    pedestal_height_m = Column(Float, nullable=True)
    # Material
    fck_mpa = Column(Float, nullable=True, default=25.0)
    # Design actions
    N_kn = Column(Float, nullable=True)
    My_knm = Column(Float, nullable=True)
    Mz_knm = Column(Float, nullable=True)
    Vy_kn = Column(Float, nullable=True)
    Vz_kn = Column(Float, nullable=True)
    T_knm = Column(Float, nullable=True)
    governing_combination = Column(String(64), nullable=True)
    # Results
    util_bearing = Column(Float, nullable=True)
    util_overturning = Column(Float, nullable=True)
    util_sliding = Column(Float, nullable=True)
    util_uplift = Column(Float, nullable=True)
    util_governing = Column(Float, nullable=True)
    governing_mode = Column(String(64), nullable=True)
    # Cost/CO2
    total_cost_eur = Column(Float, nullable=True)
    concrete_volume_m3 = Column(Float, nullable=True)
    excavation_volume_m3 = Column(Float, nullable=True)
    total_co2_kg = Column(Float, nullable=True)
    total_mass_kg = Column(Float, nullable=True)
    is_recommended = Column(Boolean, nullable=False, default=False)
    label = Column(String(32), nullable=True)            # RECOMMENDED, MIN_COST, MIN_CO2, etc.
    calc_hash = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    site = relationship("GeotechnicalSiteModel", back_populates="foundation_candidates")
    checks = relationship("FoundationCheck", back_populates="candidate",
                          cascade="all, delete-orphan")
    stiffness = relationship("FoundationStiffness", back_populates="candidate",
                             uselist=False, cascade="all, delete-orphan")
    cost_model = relationship("FoundationCostModel", back_populates="candidate",
                              uselist=False, cascade="all, delete-orphan")
    carbon_model = relationship("FoundationCarbonModel", back_populates="candidate",
                                uselist=False, cascade="all, delete-orphan")
    embedded_pole = relationship("EmbeddedPoleModel", back_populates="candidate",
                                 uselist=False, cascade="all, delete-orphan")
    evidence = relationship("FoundationEvidence", back_populates="candidate",
                            cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_foundationcandidate_site_id", "site_id"),
    )


class FoundationCheck(Base):
    """Verificación geotécnica/estructural de un candidato."""
    __tablename__ = "foundation_check"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("foundation_candidate.id",
                          ondelete="CASCADE"), nullable=False, index=True)
    combination_id = Column(String(64), nullable=False)
    check_mode = Column(Enum(FoundationCheckMode, name="foundationcheckmode11"), nullable=False)
    demand = Column(Float, nullable=True)
    resistance = Column(Float, nullable=True)
    utilization = Column(Float, nullable=True)
    governing = Column(Boolean, nullable=False, default=False)
    norm_clause = Column(String(128), nullable=True)     # e.g. "EC7 §6.5.2"
    factors = Column(JSONB, nullable=True)               # all factors applied
    error_codes = Column(JSONB, nullable=True)           # list of F11-Exxx
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    candidate = relationship("FoundationCandidate", back_populates="checks")

    __table_args__ = (
        Index("ix_foundationcheck_candidate_id", "candidate_id"),
    )


class FoundationStiffness(Base):
    """Rigidez de apoyo equivalente 6×6 para exportar a Fase 4."""
    __tablename__ = "foundation_stiffness"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("foundation_candidate.id",
                          ondelete="CASCADE"), nullable=False, unique=True)
    stiffness_model = Column(Enum(StiffnessModel, name="stiffnessmodel11"), nullable=False,
                             default=StiffnessModel.ELASTIC_LINEAR)
    kz_kn_m = Column(Float, nullable=True)               # vertical stiffness
    kx_kn_m = Column(Float, nullable=True)
    ky_kn_m = Column(Float, nullable=True)
    kthx_knm_rad = Column(Float, nullable=True)          # rotational stiffness x
    kthy_knm_rad = Column(Float, nullable=True)
    kthz_knm_rad = Column(Float, nullable=True)          # torsional stiffness
    matrix_6x6 = Column(JSONB, nullable=True)            # full 6×6 stiffness matrix
    domain_conditions = Column(JSONB, nullable=True)     # validity domain
    converged = Column(Boolean, nullable=True)
    iterations = Column(Integer, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    candidate = relationship("FoundationCandidate", back_populates="stiffness")


class EmbeddedPoleModel(Base):
    """Modelo de columna empotrada directamente en bloque."""
    __tablename__ = "embedded_pole_model"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("foundation_candidate.id",
                          ondelete="CASCADE"), nullable=False, unique=True)
    pole_diameter_mm = Column(Float, nullable=False)
    block_diameter_m = Column(Float, nullable=True)
    embedment_length_m = Column(Float, nullable=False)
    fill_type = Column(Enum(EmbedmentFill, name="embedmentfill11"), nullable=False,
                       default=EmbedmentFill.CONCRETE)
    # Lateral pressure model
    passive_pressure_kpa = Column(Float, nullable=True)   # max passive at toe
    reaction_top_kn = Column(Float, nullable=True)        # reaction at top of block
    reaction_bottom_kn = Column(Float, nullable=True)     # reaction at toe
    moment_at_surface_knm = Column(Float, nullable=True)
    shear_at_surface_kn = Column(Float, nullable=True)
    util_lateral = Column(Float, nullable=True)
    util_toe = Column(Float, nullable=True)
    # Drainage and durability
    has_bottom_drain = Column(Boolean, nullable=False, default=False)
    corrosion_protection = Column(String(128), nullable=True)
    extra_data = Column(JSONB, nullable=True)

    candidate = relationship("FoundationCandidate", back_populates="embedded_pole")


class ConstructionScenario(Base):
    """Escenario constructivo temporal (cargas de montaje, obra parcial)."""
    __tablename__ = "construction_scenario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("foundation_candidate.id",
                          ondelete="CASCADE"), nullable=False, index=True)
    stage_name = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    N_kn = Column(Float, nullable=True)
    Vy_kn = Column(Float, nullable=True)
    Vz_kn = Column(Float, nullable=True)
    My_knm = Column(Float, nullable=True)
    Mz_knm = Column(Float, nullable=True)
    water_table_m = Column(Float, nullable=True)    # during construction
    concrete_strength_fraction = Column(Float, nullable=True, default=1.0)
    util_governing = Column(Float, nullable=True)
    compliant = Column(Boolean, nullable=True)
    extra_data = Column(JSONB, nullable=True)


class FoundationCostModel(Base):
    """Modelo de coste de la cimentación por partidas."""
    __tablename__ = "foundation_cost_model"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("foundation_candidate.id",
                          ondelete="CASCADE"), nullable=False, unique=True)
    # Unit prices
    concrete_eur_m3 = Column(Float, nullable=True)
    excavation_eur_m3 = Column(Float, nullable=True)
    backfill_eur_m3 = Column(Float, nullable=True)
    grout_eur_m3 = Column(Float, nullable=True)
    labour_eur = Column(Float, nullable=True)
    transport_eur = Column(Float, nullable=True)
    prefab_eur = Column(Float, nullable=True)
    # Quantities
    concrete_volume_m3 = Column(Float, nullable=True)
    excavation_volume_m3 = Column(Float, nullable=True)
    backfill_volume_m3 = Column(Float, nullable=True)
    # Totals
    total_cost_eur = Column(Float, nullable=True)
    cost_breakdown = Column(JSONB, nullable=True)
    currency = Column(String(4), nullable=True, default="EUR")
    price_date = Column(DateTime, nullable=True)
    country_code = Column(String(4), nullable=True)

    candidate = relationship("FoundationCandidate", back_populates="cost_model")


class FoundationCarbonModel(Base):
    """Huella de carbono de la cimentación (EPD/factores)."""
    __tablename__ = "foundation_carbon_model"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("foundation_candidate.id",
                          ondelete="CASCADE"), nullable=False, unique=True)
    concrete_co2_kg_m3 = Column(Float, nullable=True)
    steel_co2_kg_kg = Column(Float, nullable=True)
    excavation_co2_kg_m3 = Column(Float, nullable=True)
    transport_co2_kg = Column(Float, nullable=True)
    total_co2_kg = Column(Float, nullable=True)
    co2_breakdown = Column(JSONB, nullable=True)
    epd_references = Column(JSONB, nullable=True)

    candidate = relationship("FoundationCandidate", back_populates="carbon_model")


class FoundationEvidence(Base):
    """Evidencia de validación: cálculo manual, ensayo, software, aprobación."""
    __tablename__ = "foundation_evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("foundation_candidate.id",
                          ondelete="CASCADE"), nullable=False, index=True)
    evidence_type = Column(Enum(EvidenceType, name="evidencetype11"), nullable=False)
    description = Column(Text, nullable=False)
    reference = Column(String(256), nullable=True)
    file_ref = Column(String(512), nullable=True)
    approved_by = Column(String(128), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    geo_level_at_approval = Column(Enum(GeotechnicalLevel, name="geotechnicallevel11_ev"),
                                   nullable=True)
    extra_data = Column(JSONB, nullable=True)

    candidate = relationship("FoundationCandidate", back_populates="evidence")
