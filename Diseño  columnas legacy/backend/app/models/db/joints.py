"""
Salvi Studio · Columns — Fase 9: Uniones y Columnas Segmentadas
Modelos ORM SQLAlchemy 2.0
"""
from __future__ import annotations
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


# ── Enumeraciones ─────────────────────────────────────────────────────────────

class JointType(enum.Enum):
    J9_TEL = "J9_TEL"          # Telescópica por solape
    J9_BRI = "J9_BRI"          # Embridada atornillada
    J9_SOL = "J9_SOL"          # Soldada (taller)
    J9_MAN = "J9_MAN"          # Manguito interior/exterior
    J9_HIB = "J9_HIB"          # Híbrida (material mixto)
    J9_HOR = "J9_HOR"          # Hormigón segmentado (solo familia validada)
    J9_ACC = "J9_ACC"          # Accesorio estructural desmontable


class SegmentPlanStatus(enum.Enum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    OPTIMIZING = "OPTIMIZING"
    VERIFIED = "VERIFIED"
    RELEASED = "RELEASED"
    BLOCKED = "BLOCKED"


class JointStiffnessModel(enum.Enum):
    RIGID_IDEAL = "RIGID_IDEAL"
    DECOUPLED_SPRINGS = "DECOUPLED_SPRINGS"
    MATRIX_6X6 = "MATRIX_6X6"
    NONLINEAR_CONTACT = "NONLINEAR_CONTACT"
    FEM_CONDENSED = "FEM_CONDENSED"
    TEST_DERIVED = "TEST_DERIVED"


class TelescopicState(enum.Enum):
    PRE_ASSEMBLY = "PRE_ASSEMBLY"
    INSERTION = "INSERTION"
    SEATED = "SEATED"
    SERVICE = "SERVICE"
    CYCLIC = "CYCLIC"
    DECOMMISSION = "DECOMMISSION"


class FlangeContactState(enum.Enum):
    FULLY_CLOSED = "FULLY_CLOSED"
    PARTIALLY_OPEN = "PARTIALLY_OPEN"
    FULLY_OPEN = "FULLY_OPEN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class WeldProcess(enum.Enum):
    SMAW = "SMAW"
    GMAW = "GMAW"
    GTAW = "GTAW"
    SAW = "SAW"
    FSW = "FSW"


class SleeveType(enum.Enum):
    INTERIOR = "INTERIOR"
    EXTERIOR = "EXTERIOR"
    REPAIR = "REPAIR"
    TRANSITION = "TRANSITION"


class HybridMaterial(enum.Enum):
    STEEL_ALUMINIUM = "STEEL_ALUMINIUM"
    STEEL_CONCRETE = "STEEL_CONCRETE"
    ALUMINIUM_CONCRETE = "ALUMINIUM_CONCRETE"


class AssemblyStage(enum.Enum):
    FACTORY_LOAD = "FACTORY_LOAD"
    TRANSPORT = "TRANSPORT"
    UNLOAD = "UNLOAD"
    PRE_ASSEMBLY = "PRE_ASSEMBLY"
    ASSEMBLY = "ASSEMBLY"
    LIFT = "LIFT"
    INSTALLATION = "INSTALLATION"
    ACCEPTANCE = "ACCEPTANCE"


class JointMaturityLevel(enum.Enum):
    V0_DEVELOPMENT = "V0"
    V1_ANALYTICAL = "V1"
    V2_FEM = "V2"
    V3_TEST = "V3"
    V4_FAMILY = "V4"
    V5_AUDITED = "V5"


class JointReleaseLevel(enum.Enum):
    M0 = "M0"
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"


class JointCheckStatus(enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    FEM_REQUIRED = "FEM_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ── Tablas ORM ────────────────────────────────────────────────────────────────

class SegmentPlan(Base):
    """Plan de segmentación de columna en tramos."""
    __tablename__ = "segment_plan"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    material_route = Column(String(16), nullable=False)  # STEEL / ALUMINIUM / CONCRETE
    total_height_m = Column(Float, nullable=False)
    piece_count = Column(Integer, nullable=False, default=1)
    max_piece_length_m = Column(Float, nullable=False, default=12.0)
    objective = Column(String(32), nullable=False, default="min_cost")
    constraints_json = Column(JSONB, nullable=False, default=dict)
    status = Column(Enum(SegmentPlanStatus), nullable=False, default=SegmentPlanStatus.DRAFT)
    plan_hash = Column(String(64), nullable=True)
    rejected_reasons_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    segments = relationship("Segment", back_populates="plan", cascade="all, delete-orphan")
    joints = relationship("Joint", back_populates="plan", cascade="all, delete-orphan")
    optimization_runs = relationship("JointOptimizationRun", back_populates="plan",
                                     cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_segment_plan_design", "design_id"),
        Index("ix_segment_plan_status", "status"),
    )


class Segment(Base):
    """Tramo individual de la columna segmentada."""
    __tablename__ = "segment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("segment_plan.id", ondelete="CASCADE"),
                     nullable=False)
    index = Column(Integer, nullable=False)
    z_start_m = Column(Float, nullable=False)
    z_end_m = Column(Float, nullable=False)
    length_m = Column(Float, nullable=False)
    envelope_length_m = Column(Float, nullable=False)  # incluye bridas, tolerancias
    mass_kg = Column(Float, nullable=True)
    cg_z_m = Column(Float, nullable=True)
    section_start_json = Column(JSONB, nullable=True)
    section_end_json = Column(JSONB, nullable=True)
    seam_azimuth_deg = Column(Float, nullable=True, default=0.0)
    handling_points_json = Column(JSONB, nullable=True)
    galvanizing_ok = Column(Boolean, nullable=False, default=True)
    transport_ok = Column(Boolean, nullable=False, default=True)
    weight_ok = Column(Boolean, nullable=False, default=True)
    error_codes_json = Column(JSONB, nullable=True)

    plan = relationship("SegmentPlan", back_populates="segments")

    __table_args__ = (
        Index("ix_segment_plan_index", "plan_id", "index", unique=True),
    )


class Joint(Base):
    """Unión entre dos tramos consecutivos."""
    __tablename__ = "joint"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("segment_plan.id", ondelete="CASCADE"),
                     nullable=False)
    joint_type = Column(Enum(JointType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    z_station_m = Column(Float, nullable=False)
    orientation_deg = Column(Float, nullable=False, default=0.0)
    stiffness_model = Column(Enum(JointStiffnessModel), nullable=False,
                              default=JointStiffnessModel.DECOUPLED_SPRINGS)
    stiffness_matrix_json = Column(JSONB, nullable=True)
    design_actions_json = Column(JSONB, nullable=True)
    governing_combination = Column(String(64), nullable=True)
    verification_state = Column(Enum(JointCheckStatus), nullable=False,
                                 default=JointCheckStatus.NOT_APPLICABLE)
    maturity_level = Column(Enum(JointMaturityLevel, values_callable=lambda x: [e.value for e in x]), nullable=False,
                             default=JointMaturityLevel.V0_DEVELOPMENT)
    in_forbidden_zone = Column(Boolean, nullable=False, default=False)
    error_codes_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    plan = relationship("SegmentPlan", back_populates="joints")
    telescopic = relationship("TelescopicJoint", back_populates="joint", uselist=False,
                               cascade="all, delete-orphan")
    flanged = relationship("FlangedJoint", back_populates="joint", uselist=False,
                            cascade="all, delete-orphan")
    welded = relationship("WeldedJoint", back_populates="joint", uselist=False,
                           cascade="all, delete-orphan")
    sleeve = relationship("SleeveJoint", back_populates="joint", uselist=False,
                           cascade="all, delete-orphan")
    hybrid = relationship("HybridInterface", back_populates="joint", uselist=False,
                           cascade="all, delete-orphan")
    assembly_ops = relationship("AssemblyOperation", back_populates="joint",
                                 cascade="all, delete-orphan")
    inspection_points = relationship("InspectionPoint", back_populates="joint",
                                      cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_joint_plan", "plan_id"),
        Index("ix_joint_type", "joint_type"),
    )


class TelescopicJoint(Base):
    """Datos específicos de unión telescópica por solape."""
    __tablename__ = "telescopic_joint"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    joint_id = Column(UUID(as_uuid=True), ForeignKey("joint.id", ondelete="CASCADE"),
                       nullable=False, unique=True)
    overlap_nominal_mm = Column(Float, nullable=False)
    overlap_min_mm = Column(Float, nullable=False)
    overlap_max_mm = Column(Float, nullable=False)
    taper_male = Column(Float, nullable=False, default=0.0)
    taper_female = Column(Float, nullable=False, default=0.0)
    clearance_mm = Column(Float, nullable=True)
    interference_mm = Column(Float, nullable=True)
    ovalization_mm = Column(Float, nullable=True)
    friction_coeff_min = Column(Float, nullable=False, default=0.15)
    friction_coeff_max = Column(Float, nullable=False, default=0.35)
    friction_source = Column(String(128), nullable=True)
    insertion_force_target_kn = Column(Float, nullable=True)
    contact_bands_json = Column(JSONB, nullable=True)
    anti_rotation = Column(Boolean, nullable=False, default=False)
    drain_ok = Column(Boolean, nullable=False, default=True)
    seal_type = Column(String(32), nullable=True)
    state = Column(Enum(TelescopicState), nullable=False, default=TelescopicState.SERVICE)
    overlap_achieved_ok = Column(Boolean, nullable=True)
    sliding_uls_mm = Column(Float, nullable=True)
    sliding_sls_mm = Column(Float, nullable=True)
    fretting_fatigue_ok = Column(Boolean, nullable=True)
    robust_scenario_json = Column(JSONB, nullable=True)
    result_json = Column(JSONB, nullable=True)

    joint = relationship("Joint", back_populates="telescopic")


class FlangedJoint(Base):
    """Datos específicos de unión embridada atornillada."""
    __tablename__ = "flanged_joint"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    joint_id = Column(UUID(as_uuid=True), ForeignKey("joint.id", ondelete="CASCADE"),
                       nullable=False, unique=True)
    flange_outer_d_mm = Column(Float, nullable=False)
    flange_inner_d_mm = Column(Float, nullable=False)
    flange_thickness_mm = Column(Float, nullable=False)
    bolt_count = Column(Integer, nullable=False)
    bolt_pcd_mm = Column(Float, nullable=False)  # bolt circle diameter
    bolt_class = Column(String(8), nullable=False, default="8.8")
    bolt_diameter_mm = Column(Float, nullable=False)
    bolt_grip_length_mm = Column(Float, nullable=True)
    pretensioned = Column(Boolean, nullable=False, default=False)
    target_pretension_kn = Column(Float, nullable=True)
    tightening_method = Column(String(32), nullable=True)
    tightening_torque_nm = Column(Float, nullable=True)
    stiffener_count = Column(Integer, nullable=False, default=0)
    contact_state = Column(Enum(FlangeContactState), nullable=False,
                            default=FlangeContactState.NOT_APPLICABLE)
    prying_amplification = Column(Float, nullable=True)
    bolt_max_tension_kn = Column(Float, nullable=True)
    bolt_utilization_max = Column(Float, nullable=True)
    flange_utilization_max = Column(Float, nullable=True)
    sliding_ok = Column(Boolean, nullable=True)
    moment_rotation_json = Column(JSONB, nullable=True)
    fatigue_ok = Column(Boolean, nullable=True)
    result_json = Column(JSONB, nullable=True)

    joint = relationship("Joint", back_populates="flanged")


class WeldedJoint(Base):
    """Datos específicos de unión soldada."""
    __tablename__ = "welded_joint"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    joint_id = Column(UUID(as_uuid=True), ForeignKey("joint.id", ondelete="CASCADE"),
                       nullable=False, unique=True)
    weld_process = Column(Enum(WeldProcess), nullable=False, default=WeldProcess.GMAW)
    joint_configuration = Column(String(32), nullable=False, default="butt_full_penetration")
    edge_prep = Column(String(64), nullable=True)
    throat_mm = Column(Float, nullable=True)
    weld_category = Column(String(4), nullable=True)   # FAT class
    field_weld = Column(Boolean, nullable=False, default=False)  # soldadura obra: bloqueada por defecto
    field_weld_approved = Column(Boolean, nullable=False, default=False)
    wps_reference = Column(String(64), nullable=True)
    ndt_method = Column(String(32), nullable=True)     # VT/PT/MT/UT/RT
    misalignment_mm = Column(Float, nullable=True)
    distortion_tolerance_mm = Column(Float, nullable=True)
    static_utilization = Column(Float, nullable=True)
    fatigue_utilization = Column(Float, nullable=True)
    result_json = Column(JSONB, nullable=True)

    joint = relationship("Joint", back_populates="welded")


class SleeveJoint(Base):
    """Datos específicos de manguito interior/exterior."""
    __tablename__ = "sleeve_joint"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    joint_id = Column(UUID(as_uuid=True), ForeignKey("joint.id", ondelete="CASCADE"),
                       nullable=False, unique=True)
    sleeve_type = Column(Enum(SleeveType), nullable=False)
    length_mm = Column(Float, nullable=False)
    outer_d_mm = Column(Float, nullable=False)
    inner_d_mm = Column(Float, nullable=False)
    attachment_method = Column(String(32), nullable=False)  # weld / bolt / both
    stop_provided = Column(Boolean, nullable=False, default=True)
    anti_rotation = Column(Boolean, nullable=False, default=False)
    drain_ok = Column(Boolean, nullable=False, default=True)
    transfer_length_ok = Column(Boolean, nullable=True)
    torsion_ok = Column(Boolean, nullable=True)
    fatigue_edge_ok = Column(Boolean, nullable=True)
    result_json = Column(JSONB, nullable=True)

    joint = relationship("Joint", back_populates="sleeve")


class HybridInterface(Base):
    """Datos específicos de interfaz híbrida entre materiales."""
    __tablename__ = "hybrid_interface"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    joint_id = Column(UUID(as_uuid=True), ForeignKey("joint.id", ondelete="CASCADE"),
                       nullable=False, unique=True)
    hybrid_type = Column(Enum(HybridMaterial), nullable=False)
    isolator_type = Column(String(64), nullable=True)
    isolator_thickness_mm = Column(Float, nullable=True)
    galvanic_area_ratio = Column(Float, nullable=True)  # cathodic/anodic
    thermal_delta_k = Column(Float, nullable=True)
    thermal_stress_mpa = Column(Float, nullable=True)
    isolator_continuous = Column(Boolean, nullable=True)
    drain_ok = Column(Boolean, nullable=False, default=True)
    galvanic_ok = Column(Boolean, nullable=True)
    thermal_ok = Column(Boolean, nullable=True)
    concrete_bearing_stress_mpa = Column(Float, nullable=True)
    concrete_bearing_ok = Column(Boolean, nullable=True)
    grout_hardened = Column(Boolean, nullable=True)
    result_json = Column(JSONB, nullable=True)

    joint = relationship("Joint", back_populates="hybrid")


class AssemblyOperation(Base):
    """Operación de montaje para una junta."""
    __tablename__ = "assembly_operation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    joint_id = Column(UUID(as_uuid=True), ForeignKey("joint.id", ondelete="CASCADE"),
                       nullable=False)
    stage = Column(Enum(AssemblyStage), nullable=False)
    sequence_index = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    tools_json = Column(JSONB, nullable=True)
    force_target_kn = Column(Float, nullable=True)
    torque_target_nm = Column(Float, nullable=True)
    tolerance_json = Column(JSONB, nullable=True)
    hold_point = Column(Boolean, nullable=False, default=False)
    evidence_required = Column(Boolean, nullable=False, default=False)
    accessible = Column(Boolean, nullable=True)
    operadores_count = Column(Integer, nullable=True, default=1)
    error_codes_json = Column(JSONB, nullable=True)

    joint = relationship("Joint", back_populates="assembly_ops")

    __table_args__ = (
        Index("ix_assembly_joint_seq", "joint_id", "sequence_index"),
    )


class InspectionPoint(Base):
    """Punto de inspección de una junta."""
    __tablename__ = "inspection_point"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    joint_id = Column(UUID(as_uuid=True), ForeignKey("joint.id", ondelete="CASCADE"),
                       nullable=False)
    characteristic = Column(String(128), nullable=False)
    method = Column(String(32), nullable=False)
    sample_description = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=False)
    criticality = Column(String(8), nullable=False, default="B")  # A/B/C
    evidence_path = Column(Text, nullable=True)
    passed = Column(Boolean, nullable=True)

    joint = relationship("Joint", back_populates="inspection_points")


class JointOptimizationRun(Base):
    """Ejecución de optimización multiobjetivo de un plan de segmentación."""
    __tablename__ = "joint_optimization_run"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("segment_plan.id", ondelete="CASCADE"),
                     nullable=False)
    candidates_count = Column(Integer, nullable=True)
    pareto_count = Column(Integer, nullable=True)
    weights_json = Column(JSONB, nullable=True)
    min_cost_candidate_json = Column(JSONB, nullable=True)
    min_weight_candidate_json = Column(JSONB, nullable=True)
    min_co2_candidate_json = Column(JSONB, nullable=True)
    balanced_candidate_json = Column(JSONB, nullable=True)
    discarded_reasons_json = Column(JSONB, nullable=True)
    run_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    plan = relationship("SegmentPlan", back_populates="optimization_runs")

    __table_args__ = (
        Index("ix_joint_opt_plan", "plan_id"),
    )
