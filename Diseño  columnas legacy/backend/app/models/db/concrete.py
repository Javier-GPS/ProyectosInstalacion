"""
Salvi Studio · Columns — Modelos DB Fase 7: Hormigón Pretensado
Diseño, verificación y fabricación de columnas centrifugadas huecas.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


# ============================================================================
# Enums
# ============================================================================

class ConcreteCementClass(str, enum.Enum):
    R = "R"    # rápido (s=0.20)
    N = "N"    # normal (s=0.25)
    S = "S"    # lento (s=0.25)
    SL = "SL"  # muy lento (s=0.38)


class ConcreteExposureClass(str, enum.Enum):
    X0 = "X0"
    XC1 = "XC1"
    XC2 = "XC2"
    XC3 = "XC3"
    XC4 = "XC4"
    XD1 = "XD1"
    XD2 = "XD2"
    XD3 = "XD3"
    XS1 = "XS1"
    XS2 = "XS2"
    XS3 = "XS3"
    XF1 = "XF1"
    XF2 = "XF2"
    XF3 = "XF3"
    XF4 = "XF4"
    XA1 = "XA1"
    XA2 = "XA2"
    XA3 = "XA3"


class PrestressingSteelClass(str, enum.Enum):
    CLASS_1 = "CLASS_1"   # alambres — alta relajación
    CLASS_2 = "CLASS_2"   # cordones — baja relajación


class PrestressingElementType(str, enum.Enum):
    WIRE = "WIRE"
    STRAND_3W = "STRAND_3W"
    STRAND_7W = "STRAND_7W"
    BAR = "BAR"


class PrestressLossType(str, enum.Enum):
    ANCHOR_SLIP = "ANCHOR_SLIP"
    ELASTIC_SHORTENING = "ELASTIC_SHORTENING"
    SHORT_TERM_RELAXATION = "SHORT_TERM_RELAXATION"
    THERMAL_GRADIENT = "THERMAL_GRADIENT"
    BED_DEFORMATION = "BED_DEFORMATION"
    SHRINKAGE = "SHRINKAGE"
    CREEP = "CREEP"
    LONG_TERM_RELAXATION = "LONG_TERM_RELAXATION"
    COMBINED_CSR = "COMBINED_CSR"


class ProductionStageCode(str, enum.Enum):
    S0 = "S0"   # tesado antes de hormigonado
    S1 = "S1"   # transferencia/corte
    S2 = "S2"   # desmoldeo e izado
    S3 = "S3"   # almacenamiento
    S4 = "S4"   # transporte
    S5 = "S5"   # montaje
    S6 = "S6"   # servicio inicial
    S7 = "S7"   # servicio final


class LimitState(str, enum.Enum):
    SLS_COMPRESSION = "SLS_COMPRESSION"
    SLS_TENSION = "SLS_TENSION"
    SLS_DECOMPRESSION = "SLS_DECOMPRESSION"
    SLS_CRACKING = "SLS_CRACKING"
    SLS_DEFLECTION = "SLS_DEFLECTION"
    SLS_VIBRATION = "SLS_VIBRATION"
    ULS_BENDING = "ULS_BENDING"
    ULS_SHEAR = "ULS_SHEAR"
    ULS_TORSION = "ULS_TORSION"
    ULS_INTERACTION = "ULS_INTERACTION"
    ULS_STABILITY = "ULS_STABILITY"
    FATIGUE_STRAND = "FATIGUE_STRAND"
    FATIGUE_CONCRETE = "FATIGUE_CONCRETE"
    FATIGUE_PASSIVE = "FATIGUE_PASSIVE"
    TRANSFER_SPLITTING = "TRANSFER_SPLITTING"
    TRANSFER_COMPRESSION = "TRANSFER_COMPRESSION"


class ConcreteVerificationStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ConcreteNormativeRoute(str, enum.Enum):
    EN40 = "EN40"
    EN40_EC2 = "EN40_EC2"
    SPECIAL = "SPECIAL"
    BLOCKED = "BLOCKED"


class ConcreteDesignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED = "VERIFIED"
    RELEASED = "RELEASED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class OptimizationObjective(str, enum.Enum):
    MIN_COST = "MIN_COST"
    MIN_WEIGHT = "MIN_WEIGHT"
    MIN_CO2 = "MIN_CO2"
    MAX_ROBUSTNESS = "MAX_ROBUSTNESS"
    BALANCED = "BALANCED"


class ConcreteMaterialStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"


class ConcreteReportType(str, enum.Enum):
    CLIENT_SUMMARY = "CLIENT_SUMMARY"
    CALCULATION = "CALCULATION"
    PRODUCTION = "PRODUCTION"
    QUALITY = "QUALITY"
    TRANSPORT_ASSEMBLY = "TRANSPORT_ASSEMBLY"
    BOM_COST = "BOM_COST"
    CONFORMITY = "CONFORMITY"


class InsertType(str, enum.Enum):
    LUMINAIRE_POST_TOP = "LUMINAIRE_POST_TOP"
    ARM_PLATE = "ARM_PLATE"
    THREADED_INSERT = "THREADED_INSERT"
    LIFTING_POINT = "LIFTING_POINT"
    GROUNDING = "GROUNDING"
    SEGMENT_JOINT = "SEGMENT_JOINT"
    BASE_CONNECTION = "BASE_CONNECTION"


class SpinCurveStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    EXPERIMENTAL = "EXPERIMENTAL"
    BLOCKED = "BLOCKED"


# ============================================================================
# Tablas maestras de materiales
# ============================================================================

class ConcreteMixVersion(Base):
    """Mezcla de hormigón con propiedades por edad, durabilidad y proceso."""
    __tablename__ = "concrete_mix_version"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mix_code = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)

    # Resistencia característica y media a 28 días (MPa)
    fck_mpa = Column(Float, nullable=False)        # característica
    fcm_mpa = Column(Float, nullable=False)        # media = fck + 8
    fctm_mpa = Column(Float, nullable=False)       # tracción media
    fctk_005_mpa = Column(Float, nullable=True)    # tracción 5%
    Ecm_mpa = Column(Float, nullable=False)        # módulo 28d
    s_cement = Column(Float, nullable=False)       # coef. endurecimiento (0.20/0.25/0.38)
    cement_class = Column(Enum(ConcreteCementClass), nullable=False)

    # Retracción y fluencia (parámetros simplificados)
    epsilon_ca_inf = Column(Float, nullable=True)  # retracción autógena ∞ (×10^-6)
    epsilon_cd_0 = Column(Float, nullable=True)    # retracción de secado nominal (×10^-6)
    phi_ref = Column(Float, nullable=True)         # fluencia de referencia φ(70y, 28d)

    # Propiedades físicas
    rho_kg_m3 = Column(Float, nullable=False, default=2450.0)  # densidad centrifugada
    alpha_T = Column(Float, nullable=False, default=10.0e-6)   # coeficiente térmico [1/°C]
    poisson = Column(Float, nullable=False, default=0.2)

    # Durabilidad
    exposure_classes = Column(JSONB, nullable=True)            # lista de clases XC, XS, etc.
    design_life_years = Column(Float, nullable=True)
    max_wk_mm = Column(Float, nullable=True)                   # ancho máximo fisura

    # Proceso de fabricación
    process_domain = Column(JSONB, nullable=True)              # restricciones centrifugado
    min_transfer_strength_mpa = Column(Float, nullable=True)   # fcm mínimo para transferencia
    curing_regime = Column(String(64), nullable=True)

    status = Column(Enum(ConcreteMaterialStatus), nullable=False, default=ConcreteMaterialStatus.DRAFT)
    provenance = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("mix_code", "version", name="uq_concrete_mix_version"),
    )


class PrestressingSteelVersion(Base):
    """Acero de pretensado: cordones, alambres, barras."""
    __tablename__ = "prestressing_steel_version"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    steel_code = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)

    element_type = Column(Enum(PrestressingElementType), nullable=False)
    relaxation_class = Column(Enum(PrestressingSteelClass), nullable=False)

    # Resistencias (MPa)
    fpk_mpa = Column(Float, nullable=False)        # resistencia característica
    fp01k_mpa = Column(Float, nullable=False)      # tensión convencional 0.1%
    Ep_mpa = Column(Float, nullable=False, default=195000.0)  # módulo elasticidad
    elongation_pct = Column(Float, nullable=True)  # elongación característica

    # Relajación
    rho1000_pct = Column(Float, nullable=False)    # relajación a 1000h (% de σ_pi)

    # Geometría
    phi_mm = Column(Float, nullable=False)         # diámetro nominal
    area_mm2 = Column(Float, nullable=False)       # área real
    mass_per_m_kg = Column(Float, nullable=False)  # masa por metro

    # Adherencia y transferencia
    alpha1 = Column(Float, nullable=False)         # factor tipo de corte (1.0/1.25)
    alpha2 = Column(Float, nullable=False)         # factor tipo de cordón (0.25/0.5)
    eta1 = Column(Float, nullable=False, default=1.0)   # condición adherencia
    eta2 = Column(Float, nullable=False, default=1.0)   # diámetro

    # Límites de tesado
    sigma_max_jack_ratio = Column(Float, nullable=False, default=0.80)   # × fpk
    sigma_max_jack_ratio2 = Column(Float, nullable=False, default=0.90)  # × fp01k
    sigma_after_transfer_ratio = Column(Float, nullable=False, default=0.75)  # × fpk

    # Compatibilidad
    compatible_processes = Column(JSONB, nullable=True)   # lista de procesos aprobados
    supplier = Column(String(128), nullable=True)
    norm_reference = Column(String(128), nullable=True)   # EN 10138, etc.

    status = Column(Enum(ConcreteMaterialStatus), nullable=False, default=ConcreteMaterialStatus.DRAFT)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("steel_code", "version", name="uq_prestress_steel_version"),
    )


class PassiveReinforcementVersion(Base):
    """Armadura pasiva: barras, espirales, mallas."""
    __tablename__ = "passive_reinforcement_version"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bar_code = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)

    fyk_mpa = Column(Float, nullable=False)
    ftk_mpa = Column(Float, nullable=False)
    Es_mpa = Column(Float, nullable=False, default=200000.0)
    phi_mm = Column(Float, nullable=False)
    ductility_class = Column(String(8), nullable=False)   # A, B, C
    weldable = Column(Boolean, nullable=False, default=True)
    min_bend_dia_ratio = Column(Float, nullable=True)     # φ_bend/φ_bar

    status = Column(Enum(ConcreteMaterialStatus), nullable=False, default=ConcreteMaterialStatus.DRAFT)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("bar_code", "version", name="uq_passive_bar_version"),
    )


# ============================================================================
# Diseño principal
# ============================================================================

class ConcretePoleDesign(Base):
    """Diseño completo de columna centrifugada de hormigón pretensado."""
    __tablename__ = "concrete_pole_design"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(UUID(as_uuid=True), nullable=True)  # FK projects_revision

    # Geometría
    height_m = Column(Float, nullable=False)
    D_base_mm = Column(Float, nullable=False)
    D_top_mm = Column(Float, nullable=False)
    t_base_mm = Column(Float, nullable=False)
    t_top_mm = Column(Float, nullable=False)
    is_segmented = Column(Boolean, nullable=False, default=False)
    segment_count = Column(Integer, nullable=True)

    # Materiales
    mix_version_id = Column(UUID(as_uuid=True), ForeignKey("concrete_mix_version.id"), nullable=True)
    prestress_steel_id = Column(UUID(as_uuid=True), ForeignKey("prestressing_steel_version.id"), nullable=True)

    # Normativa y ruta
    normative_route = Column(Enum(ConcreteNormativeRoute), nullable=True)
    normative_route_hash = Column(String(64), nullable=True)

    # Hashes de trazabilidad
    geometry_hash = Column(String(64), nullable=True)
    material_hash = Column(String(64), nullable=True)
    layout_hash = Column(String(64), nullable=True)
    rules_hash = Column(String(64), nullable=True)

    status = Column(Enum(ConcreteDesignStatus), nullable=False, default=ConcreteDesignStatus.DRAFT)
    max_utilization = Column(Float, nullable=True)
    governing_stage = Column(String(16), nullable=True)
    governing_limit_state = Column(Enum(LimitState, values_callable=lambda x: [e.value for e in x]), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    # Relaciones
    layouts = relationship("PrestressLayout", back_populates="design", cascade="all, delete-orphan")
    stages = relationship("ProductionStage", back_populates="design", cascade="all, delete-orphan")
    verifications = relationship("ConcreteVerificationResult", back_populates="design", cascade="all, delete-orphan")
    inserts = relationship("ConcreteInsert", back_populates="design", cascade="all, delete-orphan")


class PrestressLayout(Base):
    """Distribución de elementos activos (cordones/alambres)."""
    __tablename__ = "prestress_layout"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)
    strand_version_id = Column(UUID(as_uuid=True), ForeignKey("prestressing_steel_version.id"), nullable=False)

    # Posición en sección
    element_index = Column(Integer, nullable=False)       # número de elemento (1-based)
    group_id = Column(Integer, nullable=True)             # grupo de tesado
    r_polar_mm = Column(Float, nullable=False)            # radio desde eje
    theta_deg = Column(Float, nullable=False)             # ángulo (0-360°)
    x_mm = Column(Float, nullable=True)                   # cartesiano (calculado)
    y_mm = Column(Float, nullable=True)

    # Pretensado
    initial_force_kn = Column(Float, nullable=False)      # P0 por elemento
    sigma_initial_mpa = Column(Float, nullable=False)     # σ_pi = P0/Ap
    sigma_after_transfer_mpa = Column(Float, nullable=True)  # tras pérdidas instantáneas
    sigma_final_mpa = Column(Float, nullable=True)        # tras pérdidas diferidas

    # Secuencia
    jack_sequence = Column(Integer, nullable=True)        # orden de tesado
    cut_sequence = Column(Integer, nullable=True)         # orden de corte

    # Longitudes (mm)
    l_transfer_mm = Column(Float, nullable=True)          # longitud de transferencia
    l_anchor_ulu_mm = Column(Float, nullable=True)        # longitud de anclaje ELU
    active_length_mm = Column(Float, nullable=False)      # longitud activa en bancada

    layout_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    design = relationship("ConcretePoleDesign", back_populates="layouts")

    __table_args__ = (
        UniqueConstraint("design_id", "element_index", name="uq_prestress_layout_element"),
    )


class ProductionStage(Base):
    """Estado del producto en cada etapa constructiva S0-S7."""
    __tablename__ = "concrete_production_stage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)
    stage_code = Column(Enum(ProductionStageCode), nullable=False)
    sequence_order = Column(Integer, nullable=False)

    # Condiciones del hormigón en esta etapa
    age_days = Column(Float, nullable=False)              # edad del hormigón
    fcm_at_stage_mpa = Column(Float, nullable=True)      # resistencia en esta edad
    Ecm_at_stage_mpa = Column(Float, nullable=True)
    fctm_at_stage_mpa = Column(Float, nullable=True)

    # Pretensado efectivo en esta etapa
    prestress_effective_kn = Column(Float, nullable=True)  # fuerza resultante total
    prestress_eccentricity_mm = Column(Float, nullable=True)  # excentricidad resultante
    loss_accumulated_pct = Column(Float, nullable=True)    # % pérdida acumulada

    # Cargas aplicadas (JSON con tipo, valor, posición)
    applied_loads_json = Column(JSONB, nullable=True)

    # Condiciones de apoyo
    support_positions_json = Column(JSONB, nullable=True)
    environment_json = Column(JSONB, nullable=True)  # temperatura, humedad

    # Resultados clave de esta etapa
    max_stress_concrete_mpa = Column(Float, nullable=True)
    min_stress_concrete_mpa = Column(Float, nullable=True)
    max_stress_strand_mpa = Column(Float, nullable=True)
    max_deflection_mm = Column(Float, nullable=True)
    camber_mm = Column(Float, nullable=True)             # contraflecha
    cracking_occurred = Column(Boolean, nullable=True)

    stage_hash = Column(String(64), nullable=True)       # hash determinista
    stage_status = Column(Enum(ConcreteVerificationStatus), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    design = relationship("ConcretePoleDesign", back_populates="stages")
    losses = relationship("LossComponentResult", back_populates="stage", cascade="all, delete-orphan")
    verifications = relationship("ConcreteVerificationResult", back_populates="stage")

    __table_args__ = (
        UniqueConstraint("design_id", "stage_code", "sequence_order", name="uq_production_stage"),
    )


class LossComponentResult(Base):
    """Pérdida de pretensado por componente y etapa."""
    __tablename__ = "loss_component_result"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("concrete_production_stage.id", ondelete="CASCADE"), nullable=False)
    design_id = Column(UUID(as_uuid=True), nullable=False)

    loss_type = Column(Enum(PrestressLossType), nullable=False)
    delta_P_kn = Column(Float, nullable=False)           # pérdida total en bancada [kN]
    delta_sigma_mpa = Column(Float, nullable=False)      # pérdida por cordón [MPa]
    loss_pct = Column(Float, nullable=False)             # % sobre P0

    # Método de cálculo
    method = Column(String(64), nullable=True)           # "SIMPLIFIED" / "INCREMENTAL"
    rule_reference = Column(String(128), nullable=True)  # EC2 §5.10.x
    sensitivity = Column(Float, nullable=True)           # dP/dparámetro_gobernante
    input_values_json = Column(JSONB, nullable=True)     # entradas usadas
    equation_trace_json = Column(JSONB, nullable=True)   # trazabilidad

    stage = relationship("ProductionStage", back_populates="losses")


class ConcreteSectionStation(Base):
    """Propiedades geométricas de la sección en una estación longitudinal."""
    __tablename__ = "concrete_section_station"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)
    station_m = Column(Float, nullable=False)            # posición desde base [m]

    # Geometría en esta estación
    D_ext_mm = Column(Float, nullable=False)
    D_int_mm = Column(Float, nullable=False)
    t_wall_mm = Column(Float, nullable=False)

    # Propiedades brutas
    A_gross_m2 = Column(Float, nullable=True)
    Iy_gross_m4 = Column(Float, nullable=True)
    Iz_gross_m4 = Column(Float, nullable=True)
    J_gross_m4 = Column(Float, nullable=True)
    Wel_y_m3 = Column(Float, nullable=True)

    # Propiedades transformadas (incluyendo pretensado)
    A_transformed_m2 = Column(Float, nullable=True)
    Iy_transformed_m4 = Column(Float, nullable=True)
    yG_transformed_m = Column(Float, nullable=True)     # centroide transformado desde eje

    # Propiedades fisuradas
    Iy_cracked_m4 = Column(Float, nullable=True)
    neutral_axis_cracked_m = Column(Float, nullable=True)

    # Modelo de fibras
    fiber_mesh_hash = Column(String(64), nullable=True)  # hash de discretización
    n_fibers = Column(Integer, nullable=True)

    # Pretensado en esta sección
    P_prestress_kn = Column(Float, nullable=True)        # fuerza efectiva resultante
    e_prestress_mm = Column(Float, nullable=True)        # excentricidad resultante

    geometry_hash = Column(String(64), nullable=True)


class ConcreteVerificationResult(Base):
    """Resultado de verificación por estado límite, etapa y estación."""
    __tablename__ = "concrete_verification_result"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("concrete_production_stage.id", ondelete="SET NULL"), nullable=True)

    stage_code = Column(Enum(ProductionStageCode), nullable=False)
    station_m = Column(Float, nullable=False)
    limit_state = Column(Enum(LimitState, values_callable=lambda x: [e.value for e in x]), nullable=False)

    # Esfuerzos aplicados
    N_ed_kn = Column(Float, nullable=True)
    My_ed_knm = Column(Float, nullable=True)
    Mz_ed_knm = Column(Float, nullable=True)
    V_ed_kn = Column(Float, nullable=True)
    T_ed_knm = Column(Float, nullable=True)

    # Resultado
    solicitation = Column(Float, nullable=True)          # demanda (MPa, kN, kNm, ...)
    resistance = Column(Float, nullable=True)            # capacidad
    utilization = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)
    status = Column(Enum(ConcreteVerificationStatus), nullable=False)
    governing_case = Column(String(128), nullable=True)
    governing_rule = Column(String(128), nullable=True)
    equation_trace_json = Column(JSONB, nullable=True)
    intermediate_values_json = Column(JSONB, nullable=True)

    combination_id = Column(UUID(as_uuid=True), nullable=True)
    run_hash = Column(String(64), nullable=True)

    design = relationship("ConcretePoleDesign", back_populates="verifications")
    stage = relationship("ProductionStage", back_populates="verifications")


class ConcreteInsert(Base):
    """Insertos, cabezales, puntos de izado, etc."""
    __tablename__ = "concrete_insert"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)

    insert_type = Column(Enum(InsertType), nullable=False)
    station_m = Column(Float, nullable=False)            # posición longitudinal
    theta_deg = Column(Float, nullable=True)             # posición angular
    material = Column(String(64), nullable=True)
    embedded_length_mm = Column(Float, nullable=True)
    axial_capacity_kn = Column(Float, nullable=True)
    shear_capacity_kn = Column(Float, nullable=True)

    # Verificación de interferencia
    min_distance_to_strand_mm = Column(Float, nullable=True)
    clearance_ok = Column(Boolean, nullable=True)        # False → CON-FAB-001
    clearance_error_code = Column(String(32), nullable=True)

    insert_hash = Column(String(64), nullable=True)
    design = relationship("ConcretePoleDesign", back_populates="inserts")


class ProductionRecipe(Base):
    """Instrucciones de fabricación: centrifugado, curado, corte."""
    __tablename__ = "production_recipe"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)
    mould_id = Column(String(64), nullable=True)

    # Centrifugado
    spin_curve_json = Column(JSONB, nullable=True)       # etapas: rpm, duración, aceleración
    spin_status = Column(Enum(SpinCurveStatus), nullable=True)
    max_spin_rpm = Column(Float, nullable=True)

    # Curado
    curing_regime = Column(String(64), nullable=True)
    curing_temperature_c = Column(Float, nullable=True)
    min_transfer_strength_mpa = Column(Float, nullable=False)  # mínimo antes de cortar

    # Corte de cordones
    cut_sequence_json = Column(JSONB, nullable=True)     # orden de corte numerado

    # Izado y transporte
    lifting_points_json = Column(JSONB, nullable=True)   # posiciones de izado [m desde base]
    transport_supports_json = Column(JSONB, nullable=True)  # posición de cunas

    # BOM simplificada
    concrete_volume_m3 = Column(Float, nullable=True)
    strand_mass_kg = Column(Float, nullable=True)
    passive_steel_mass_kg = Column(Float, nullable=True)
    inserts_mass_kg = Column(Float, nullable=True)
    total_mass_kg = Column(Float, nullable=True)

    # Coste y CO₂
    material_cost_eur = Column(Float, nullable=True)
    process_cost_eur = Column(Float, nullable=True)
    total_cost_eur = Column(Float, nullable=True)
    total_co2_kg = Column(Float, nullable=True)

    recipe_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ConcreteOptimizationRun(Base):
    """Ejecución de optimización multiobjetivo del pretensado."""
    __tablename__ = "concrete_optimization_run"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)

    solver_version = Column(String(32), nullable=False)
    ruleset_hash = Column(String(64), nullable=False)
    seed = Column(Integer, nullable=True)
    run_hash = Column(String(64), nullable=False, unique=True)

    objectives = Column(JSONB, nullable=False)            # lista de objetivos activos
    constraints_json = Column(JSONB, nullable=True)       # restricciones duras

    # Estadísticas
    candidates_evaluated = Column(Integer, nullable=True)
    candidates_rejected = Column(Integer, nullable=True)
    pareto_size = Column(Integer, nullable=True)
    convergence_reached = Column(Boolean, nullable=True)

    # Soluciones seleccionadas (FK a candidatos)
    min_cost_candidate_id = Column(UUID(as_uuid=True), nullable=True)
    min_weight_candidate_id = Column(UUID(as_uuid=True), nullable=True)
    min_co2_candidate_id = Column(UUID(as_uuid=True), nullable=True)
    balanced_candidate_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    candidates = relationship("ConcreteOptimizationCandidate", back_populates="run", cascade="all, delete-orphan")


class ConcreteOptimizationCandidate(Base):
    """Candidato evaluado en la optimización."""
    __tablename__ = "concrete_optimization_candidate"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("concrete_optimization_run.id", ondelete="CASCADE"), nullable=False)

    # Variables de diseño
    n_strands = Column(Integer, nullable=False)
    strand_diameter_mm = Column(Float, nullable=False)
    strand_steel_id = Column(UUID(as_uuid=True), nullable=True)
    crown_radius_mm = Column(Float, nullable=False)
    initial_force_per_strand_kn = Column(Float, nullable=False)
    design_variables_json = Column(JSONB, nullable=True)  # posiciones individuales

    # Resultados de etapas (evaluación completa)
    stage_results_json = Column(JSONB, nullable=True)

    # Objetivos
    total_cost_eur = Column(Float, nullable=True)
    total_mass_kg = Column(Float, nullable=True)
    total_co2_kg = Column(Float, nullable=True)
    robustness_score = Column(Float, nullable=True)      # mayor = más robusto

    # Restricciones
    max_utilization = Column(Float, nullable=True)
    governing_constraint = Column(String(128), nullable=True)
    governing_stage = Column(String(16), nullable=True)
    feasible = Column(Boolean, nullable=False, default=False)
    transportable = Column(Boolean, nullable=False, default=True)
    pareto_dominated = Column(Boolean, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    candidate_hash = Column(String(64), nullable=True)
    run = relationship("ConcreteOptimizationRun", back_populates="candidates")


class ConcreteReportSnapshot(Base):
    """Snapshot inmutable de informe de la Fase 7."""
    __tablename__ = "concrete_report_snapshot"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("concrete_pole_design.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(Enum(ConcreteReportType), nullable=False)
    content_hash = Column(String(64), nullable=False)
    input_hashes_json = Column(JSONB, nullable=True)
    all_checks_passed = Column(Boolean, nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
