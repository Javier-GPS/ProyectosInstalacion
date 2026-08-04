"""
Fase 10 · Placa Base, Pernos y Anclajes
ORM models: enums + 14 DB entities
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

class AnchorRodType(str, enum.Enum):
    L = "L"
    J = "J"
    STRAIGHT = "STRAIGHT"


class AnchorFamily(str, enum.Enum):
    EMBEDDED = "EMBEDDED"
    POST_INSTALLED = "POST_INSTALLED"


class PostInstalledType(str, enum.Enum):
    MECHANICAL_EXPANSION = "MECHANICAL_EXPANSION"
    UNDERCUT = "UNDERCUT"
    CHEMICAL_THREADED = "CHEMICAL_THREADED"
    CHEMICAL_SPECIAL = "CHEMICAL_SPECIAL"
    HYBRID_SLEEVE = "HYBRID_SLEEVE"


class ConcreteCondition(str, enum.Enum):
    CRACKED = "CRACKED"
    UNCRACKED = "UNCRACKED"


class PlatePatternType(str, enum.Enum):
    P200X200 = "200x200"
    P250X250 = "250x250"
    P300X300 = "300x300"
    CIRCULAR_4 = "CIRCULAR_4"
    CIRCULAR_6 = "CIRCULAR_6"
    CIRCULAR_8 = "CIRCULAR_8"
    RECTANGULAR = "RECTANGULAR"
    SPECIAL = "SPECIAL"


class PlateDesignMethod(str, enum.Enum):
    P0_RIGID = "P0_RIGID"
    P1_CANTILEVER = "P1_CANTILEVER"
    P2_YIELD_LINE = "P2_YIELD_LINE"
    P3_FEM_SHELL = "P3_FEM_SHELL"
    P4_FEM_SOLID = "P4_FEM_SOLID"


class ContactState(str, enum.Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    BIAXIAL_SECTORS = "BIAXIAL_SECTORS"
    LOCAL_OPENING = "LOCAL_OPENING"


class ShearMechanism(str, enum.Enum):
    FRICTION = "FRICTION"
    BOLT_BEARING = "BOLT_BEARING"
    PLATE_BEARING = "PLATE_BEARING"
    SHEAR_KEY = "SHEAR_KEY"
    COMBINED = "COMBINED"


class ConcreteFailureMode(str, enum.Enum):
    CONCRETE_CONE = "CONCRETE_CONE"
    PULL_OUT = "PULL_OUT"
    SPLITTING = "SPLITTING"
    BLOW_OUT = "BLOW_OUT"
    PRY_OUT = "PRY_OUT"
    EDGE_SHEAR = "EDGE_SHEAR"
    BOND = "BOND"
    LOCAL_CRUSHING = "LOCAL_CRUSHING"


class GroutType(str, enum.Enum):
    CONTINUOUS_MORTAR = "CONTINUOUS_MORTAR"
    LEVELING_NUTS_THEN_GROUT = "LEVELING_NUTS_THEN_GROUT"
    PERMANENT_PACKERS = "PERMANENT_PACKERS"
    DRY_PACK = "DRY_PACK"
    SPECIAL_NO_GROUT = "SPECIAL_NO_GROUT"


class AssemblyStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PRELIMINARY = "PRELIMINARY"
    VERIFIED = "VERIFIED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class MarketHomologationStatus(str, enum.Enum):
    HOMOLOGATED = "HOMOLOGATED"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class BasePlateMaturityLevel(str, enum.Enum):
    V0 = "V0"   # sin verificar
    V1 = "V1"   # predimensionado
    V2 = "V2"   # verificado parcial
    V3 = "V3"   # verificado completo
    V4 = "V4"   # validado con ensayo/referencia


# ---------------------------------------------------------------------------
# ORM Tables
# ---------------------------------------------------------------------------

class BaseAssembly(Base):
    """Conjunto placa base - identidad y estado."""
    __tablename__ = "base_assembly"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    revision_id = Column(UUID(as_uuid=True), nullable=True)
    code = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(AssemblyStatus, name="assemblystatus10"), nullable=False,
                    default=AssemblyStatus.DRAFT)
    maturity_level = Column(Enum(BasePlateMaturityLevel, name="bplatematurity"), nullable=False,
                            default=BasePlateMaturityLevel.V0)
    anchor_family = Column(Enum(AnchorFamily, name="anchorfamily10"), nullable=False)
    pattern_type = Column(Enum(PlatePatternType, name="platepatterntype", values_callable=lambda x: [e.value for e in x]), nullable=False)
    # design actions passed from structural model
    N_kn = Column(Float, nullable=False, default=0.0)
    Vy_kn = Column(Float, nullable=False, default=0.0)
    Vz_kn = Column(Float, nullable=False, default=0.0)
    T_knm = Column(Float, nullable=False, default=0.0)
    My_knm = Column(Float, nullable=False, default=0.0)
    Mz_knm = Column(Float, nullable=False, default=0.0)
    governing_combination = Column(String(64), nullable=True)
    geometry_hash = Column(String(64), nullable=True)
    calc_hash = Column(String(64), nullable=True)
    solver_version = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    plates = relationship("BasePlate", back_populates="assembly", cascade="all, delete-orphan")
    anchor_pattern = relationship("AnchorPattern", back_populates="assembly", uselist=False,
                                  cascade="all, delete-orphan")
    grout_layer = relationship("GroutLayer", back_populates="assembly", uselist=False,
                               cascade="all, delete-orphan")
    shear_key = relationship("ShearKey", back_populates="assembly", uselist=False,
                             cascade="all, delete-orphan")
    contact_solutions = relationship("ContactSolution", back_populates="assembly",
                                     cascade="all, delete-orphan")
    anchor_group_results = relationship("AnchorGroupResult", back_populates="assembly",
                                        cascade="all, delete-orphan")
    concrete_failure_results = relationship("ConcreteFailureResult", back_populates="assembly",
                                            cascade="all, delete-orphan")
    foundation_interface = relationship("FoundationInterface", back_populates="assembly",
                                        uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_baseassembly_project_code"),
    )


class BasePlate(Base):
    """Geometría y material de la placa base."""
    __tablename__ = "base_plate"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    shape = Column(String(32), nullable=False, default="RECTANGULAR")  # RECTANGULAR, CIRCULAR, OCTAGONAL
    width_mm = Column(Float, nullable=False)
    length_mm = Column(Float, nullable=False)
    thickness_mm = Column(Float, nullable=False)
    material_grade = Column(String(16), nullable=False, default="S355")
    fy_mpa = Column(Float, nullable=False, default=355.0)
    fu_mpa = Column(Float, nullable=False, default=470.0)
    design_method = Column(Enum(PlateDesignMethod, name="platedesignmethod"), nullable=False,
                           default=PlateDesignMethod.P1_CANTILEVER)
    overhang_x_mm = Column(Float, nullable=True)   # cantilever from shaft
    overhang_y_mm = Column(Float, nullable=True)
    hole_diameter_mm = Column(Float, nullable=True)
    hole_count = Column(Integer, nullable=True)
    planarity_tolerance_mm = Column(Float, nullable=True, default=1.0)
    mass_kg = Column(Float, nullable=True)
    is_recommended = Column(Boolean, nullable=False, default=False)
    util_plate = Column(Float, nullable=True)   # governing utilization ratio
    extra_data = Column(JSONB, nullable=True)

    assembly = relationship("BaseAssembly", back_populates="plates")
    stiffeners = relationship("Stiffener", back_populates="plate", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_baseplate_assembly_id", "assembly_id"),
    )


class Stiffener(Base):
    """Cartela/rigidizador de la placa base."""
    __tablename__ = "stiffener"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plate_id = Column(UUID(as_uuid=True), ForeignKey("base_plate.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    label = Column(String(32), nullable=True)
    height_mm = Column(Float, nullable=False)
    thickness_mm = Column(Float, nullable=False)
    length_mm = Column(Float, nullable=False)
    position_angle_deg = Column(Float, nullable=True)   # angular position
    material_grade = Column(String(16), nullable=False, default="S355")
    weld_throat_mm = Column(Float, nullable=True)
    util_stiffener = Column(Float, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    plate = relationship("BasePlate", back_populates="stiffeners")


class AnchorPattern(Base):
    """Patrón de anclajes: coordenadas, orientación, tolerancias."""
    __tablename__ = "anchor_pattern"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, unique=True)
    pattern_label = Column(String(32), nullable=False)   # e.g. "200x200_4B"
    bolt_count = Column(Integer, nullable=False)
    bolt_pcd_mm = Column(Float, nullable=True)    # bolt circle diameter
    bolt_x_mm = Column(JSONB, nullable=True)      # list of x coords
    bolt_y_mm = Column(JSONB, nullable=True)      # list of y coords
    orientation_deg = Column(Float, nullable=False, default=0.0)
    position_tolerance_mm = Column(Float, nullable=True, default=3.0)
    cage_drawing_ref = Column(String(128), nullable=True)
    extra_data = Column(JSONB, nullable=True)

    assembly = relationship("BaseAssembly", back_populates="anchor_pattern")
    anchor_rods = relationship("AnchorRod", back_populates="pattern",
                               cascade="all, delete-orphan")


class AnchorRod(Base):
    """Perno embebido tipo L/J/recto."""
    __tablename__ = "anchor_rod"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern_id = Column(UUID(as_uuid=True), ForeignKey("anchor_pattern.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    rod_index = Column(Integer, nullable=False)
    rod_type = Column(Enum(AnchorRodType, name="anchorrodtype10"), nullable=False)
    material_grade = Column(String(16), nullable=False, default="4.8")
    nominal_diameter_mm = Column(Float, nullable=False)
    thread_pitch_mm = Column(Float, nullable=True)
    effective_thread_area_mm2 = Column(Float, nullable=True)
    total_length_mm = Column(Float, nullable=False)
    embedment_depth_mm = Column(Float, nullable=False)   # hef
    hook_length_mm = Column(Float, nullable=True)        # for L and J
    hook_radius_mm = Column(Float, nullable=True)
    end_plate_diameter_mm = Column(Float, nullable=True) # for STRAIGHT with plate
    free_length_mm = Column(Float, nullable=True)
    fy_mpa = Column(Float, nullable=False)
    fu_mpa = Column(Float, nullable=False)
    coating = Column(String(64), nullable=True)          # HOT_DIP_GALV, STAINLESS, DUPLEX
    util_tension = Column(Float, nullable=True)
    util_shear = Column(Float, nullable=True)
    util_interaction = Column(Float, nullable=True)
    axial_stiffness_kn_mm = Column(Float, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    pattern = relationship("AnchorPattern", back_populates="anchor_rods")
    nut_washer_set = relationship("NutWasherSet", back_populates="rod", uselist=False,
                                  cascade="all, delete-orphan")


class PostInstalledAnchor(Base):
    """Anclaje postinstalado con evaluación técnica (ETA)."""
    __tablename__ = "post_installed_anchor"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    anchor_index = Column(Integer, nullable=False)
    post_type = Column(Enum(PostInstalledType, name="postinstalledtype10"), nullable=False)
    manufacturer = Column(String(128), nullable=False)
    product_name = Column(String(128), nullable=False)
    eta_document = Column(String(128), nullable=False)   # e.g. "ETA-12/0063"
    eta_edition = Column(String(32), nullable=True)
    nominal_diameter_mm = Column(Float, nullable=False)
    drill_diameter_mm = Column(Float, nullable=False)
    embedment_depth_mm = Column(Float, nullable=False)
    concrete_condition = Column(Enum(ConcreteCondition, name="concretecondition10"),
                                nullable=False, default=ConcreteCondition.CRACKED)
    fck_mpa = Column(Float, nullable=False)
    temperature_max_c = Column(Float, nullable=True)
    installation_torque_nm = Column(Float, nullable=True)
    cure_time_hours = Column(Float, nullable=True)       # for chemical
    NRd_c_kn = Column(Float, nullable=True)    # concrete cone
    NRd_p_kn = Column(Float, nullable=True)    # pull-out
    VRd_c_kn = Column(Float, nullable=True)    # edge shear
    util_tension = Column(Float, nullable=True)
    util_shear = Column(Float, nullable=True)
    util_interaction = Column(Float, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_postinstalled_assembly_id", "assembly_id"),
    )


class NutWasherSet(Base):
    """Conjunto tuerca/arandela/contratuerca para cada perno."""
    __tablename__ = "nut_washer_set"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rod_id = Column(UUID(as_uuid=True), ForeignKey("anchor_rod.id", ondelete="CASCADE"),
                    nullable=False, unique=True)
    nut_grade = Column(String(16), nullable=False, default="4")
    washer_od_mm = Column(Float, nullable=True)
    washer_thickness_mm = Column(Float, nullable=True)
    lock_nut = Column(Boolean, nullable=False, default=True)
    coating = Column(String(64), nullable=True)
    torque_target_nm = Column(Float, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    rod = relationship("AnchorRod", back_populates="nut_washer_set")


class GroutLayer(Base):
    """Capa de mortero de nivelación."""
    __tablename__ = "grout_layer"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, unique=True)
    grout_type = Column(Enum(GroutType, name="grouttype10"), nullable=False,
                        default=GroutType.LEVELING_NUTS_THEN_GROUT)
    product_name = Column(String(128), nullable=True)
    thickness_mm = Column(Float, nullable=False, default=50.0)
    fck_mortar_mpa = Column(Float, nullable=False)
    elastic_modulus_mpa = Column(Float, nullable=True)
    effective_area_mm2 = Column(Float, nullable=True)
    sigma_Ed_mpa = Column(Float, nullable=True)    # max bearing pressure
    sigma_Rd_mpa = Column(Float, nullable=True)    # design bearing resistance
    util_bearing = Column(Float, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    assembly = relationship("BaseAssembly", back_populates="grout_layer")


class ShearKey(Base):
    """Llave de cortante central o excéntrica."""
    __tablename__ = "shear_key"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, unique=True)
    shape = Column(String(32), nullable=False, default="RECTANGULAR")
    width_mm = Column(Float, nullable=False)
    height_mm = Column(Float, nullable=False)
    depth_mm = Column(Float, nullable=False)    # embedment in concrete
    eccentricity_mm = Column(Float, nullable=False, default=0.0)
    material_grade = Column(String(16), nullable=False, default="S355")
    fy_mpa = Column(Float, nullable=False, default=355.0)
    weld_throat_mm = Column(Float, nullable=True)
    Vx_design_kn = Column(Float, nullable=True)
    Vy_design_kn = Column(Float, nullable=True)
    util_shear = Column(Float, nullable=True)
    util_bending = Column(Float, nullable=True)
    util_concrete = Column(Float, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    assembly = relationship("BaseAssembly", back_populates="shear_key")


class ContactSolution(Base):
    """Resultado del solver de contacto placa-mortero."""
    __tablename__ = "contact_solution"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    combination_id = Column(String(64), nullable=False)
    contact_state = Column(Enum(ContactState, name="contactstate10"), nullable=False)
    contact_area_mm2 = Column(Float, nullable=True)
    sigma_max_mpa = Column(Float, nullable=True)    # max compressive stress
    sigma_avg_mpa = Column(Float, nullable=True)
    neutral_axis_dist_mm = Column(Float, nullable=True)
    max_bolt_tension_kn = Column(Float, nullable=True)
    max_bolt_shear_kn = Column(Float, nullable=True)
    iterations = Column(Integer, nullable=True)
    converged = Column(Boolean, nullable=False, default=False)
    equilibrium_error = Column(Float, nullable=True)
    rotation_rad = Column(Float, nullable=True)
    horizontal_slip_mm = Column(Float, nullable=True)
    shear_mechanism = Column(Enum(ShearMechanism, name="shearmechanism10"), nullable=True)
    force_per_bolt = Column(JSONB, nullable=True)   # list of {"N": float, "Vx": float, "Vy": float}
    solver_version = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assembly = relationship("BaseAssembly", back_populates="contact_solutions")

    __table_args__ = (
        Index("ix_contactsol_assembly_combination", "assembly_id", "combination_id"),
    )


class AnchorGroupResult(Base):
    """Resultado de verificación del grupo de anclajes."""
    __tablename__ = "anchor_group_result"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    combination_id = Column(String(64), nullable=False)
    bolt_index = Column(Integer, nullable=False)
    N_Ed_kn = Column(Float, nullable=False)
    V_Ed_kn = Column(Float, nullable=False)
    util_steel_tension = Column(Float, nullable=True)
    util_steel_shear = Column(Float, nullable=True)
    util_interaction = Column(Float, nullable=True)
    util_bending = Column(Float, nullable=True)
    util_governing = Column(Float, nullable=True)
    governing_mode = Column(String(64), nullable=True)
    extra_data = Column(JSONB, nullable=True)

    assembly = relationship("BaseAssembly", back_populates="anchor_group_results")

    __table_args__ = (
        Index("ix_anchorgroupres_assembly", "assembly_id"),
    )


class ConcreteFailureResult(Base):
    """Resultado de verificación de modos de fallo del hormigón."""
    __tablename__ = "concrete_failure_result"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    combination_id = Column(String(64), nullable=False)
    failure_mode = Column(Enum(ConcreteFailureMode, name="concretefailuremode10"), nullable=False)
    NEd_kn = Column(Float, nullable=True)
    VEd_kn = Column(Float, nullable=True)
    NRd_kn = Column(Float, nullable=True)
    VRd_kn = Column(Float, nullable=True)
    util = Column(Float, nullable=True)
    governing = Column(Boolean, nullable=False, default=False)
    edge_distances_mm = Column(JSONB, nullable=True)    # {c1: float, c2: float, ...}
    cone_geometry = Column(JSONB, nullable=True)        # 3D cone idealisation for overlap check
    factors = Column(JSONB, nullable=True)              # all psi factors applied
    extra_data = Column(JSONB, nullable=True)

    assembly = relationship("BaseAssembly", back_populates="concrete_failure_results")

    __table_args__ = (
        Index("ix_concretefail_assembly", "assembly_id"),
    )


class MarketReference(Base):
    """Referencia comercial de anclaje con homologación."""
    __tablename__ = "market_reference10"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manufacturer = Column(String(128), nullable=False)
    product_name = Column(String(128), nullable=False)
    product_code = Column(String(64), nullable=False, unique=True)
    anchor_family = Column(Enum(AnchorFamily, name="anchorfamily10_mkt"), nullable=False)
    post_type = Column(Enum(PostInstalledType, name="postinstalledtype10_mkt"), nullable=True)
    nominal_diameter_mm = Column(Float, nullable=False)
    embedment_range_mm = Column(JSONB, nullable=True)   # [min, max]
    fck_range_mpa = Column(JSONB, nullable=True)        # [min, max]
    concrete_condition = Column(Enum(ConcreteCondition, name="concretecondition10_mkt"),
                                nullable=True)
    eta_document = Column(String(128), nullable=True)
    eta_edition = Column(String(32), nullable=True)
    homologation_status = Column(Enum(MarketHomologationStatus, name="mkthomostat10"),
                                 nullable=False, default=MarketHomologationStatus.PENDING)
    unit_price_eur = Column(Float, nullable=True)
    mass_kg = Column(Float, nullable=True)
    co2_kg_per_unit = Column(Float, nullable=True)
    country_of_origin = Column(String(8), nullable=True)
    lead_time_days = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String(128), nullable=True)
    extra_data = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("product_code", name="uq_mktref10_product_code"),
        Index("ix_mktref10_anchor_family", "anchor_family"),
    )


class FoundationInterface(Base):
    """Envolvente de cargas y requisitos mínimos para fase de cimentación."""
    __tablename__ = "foundation_interface"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assembly_id = Column(UUID(as_uuid=True), ForeignKey("base_assembly.id", ondelete="CASCADE"),
                         nullable=False, unique=True)
    N_max_kn = Column(Float, nullable=True)
    N_min_kn = Column(Float, nullable=True)
    Vx_max_kn = Column(Float, nullable=True)
    Vy_max_kn = Column(Float, nullable=True)
    T_max_knm = Column(Float, nullable=True)
    Mx_max_knm = Column(Float, nullable=True)
    My_max_knm = Column(Float, nullable=True)
    # minimum requirements for foundation design
    min_concrete_thickness_mm = Column(Float, nullable=True)
    min_edge_distance_x_mm = Column(Float, nullable=True)
    min_edge_distance_y_mm = Column(Float, nullable=True)
    min_fck_mpa = Column(Float, nullable=True)
    rebar_requirement = Column(String(256), nullable=True)
    cone_geometry_envelope = Column(JSONB, nullable=True)  # spatial 3D cone envelope
    # 6x6 equivalent stiffness matrix for global model
    stiffness_matrix_6x6 = Column(JSONB, nullable=True)
    snapshot_hash = Column(String(64), nullable=True)
    frozen_at = Column(DateTime, nullable=True)
    extra_data = Column(JSONB, nullable=True)

    assembly = relationship("BaseAssembly", back_populates="foundation_interface")
