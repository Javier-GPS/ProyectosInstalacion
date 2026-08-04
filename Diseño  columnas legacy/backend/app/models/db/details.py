"""
Salvi Studio · Columns — Modelos DB Fase 8: Puertas, Soportes y Detalles Locales.
"""
from __future__ import annotations
import enum
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class OpeningType(str, enum.Enum):
    RECTANGULAR = "RECTANGULAR"
    RECTANGULAR_ROUNDED = "RECTANGULAR_ROUNDED"
    OVAL = "OVAL"
    CABLE_SLOT = "CABLE_SLOT"
    VENTILATION = "VENTILATION"
    DRAIN = "DRAIN"
    CUSTOM = "CUSTOM"


class OpeningGeometricLevel(str, enum.Enum):
    G0 = "G0"   # esquemático
    G1 = "G1"   # nominal
    G2 = "G2"   # local analítico
    G3 = "G3"   # fabricación
    G4 = "G4"   # FEM


class DetailRoute(str, enum.Enum):
    R8_A = "R8_A"   # familia estándar ensayada
    R8_B = "R8_B"   # cálculo analítico normativo
    R8_C = "R8_C"   # submodelo shell + chequeos globales
    R8_D = "R8_D"   # FEM + ensayo / aprobación externa
    R8_E = "R8_E"   # BLOQUEADO — entrada incompleta o fuera de límites


class ReinforcementFamily(str, enum.Enum):
    FRAME = "FRAME"                   # marco perimetral de chapa
    TWO_VERTICALS = "TWO_VERTICALS"   # dos montantes verticales
    VERTICALS_CROSSBARS = "VERTICALS_CROSSBARS"  # montantes + travesaños
    WRAPPING_PLATE = "WRAPPING_PLATE" # chapa interior/exterior envolvente
    RING = "RING"                     # anillo/collar circunferencial
    EXTRUSION = "EXTRUSION"          # perfil extrusionado (aluminio)
    HYBRID = "HYBRID"                 # solución híbrida


class DetailCheckStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    FEM_REQUIRED = "FEM_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class WeldProcess(str, enum.Enum):
    SMAW = "SMAW"     # electrodo revestido
    GMAW = "GMAW"     # MIG/MAG
    GTAW = "GTAW"     # TIG
    SAW = "SAW"       # arco sumergido
    FSW = "FSW"       # fricción-agitación (aluminio)


class WeldInspection(str, enum.Enum):
    VT = "VT"         # visual
    PT = "PT"         # líquidos penetrantes
    MT = "MT"         # partículas magnéticas
    UT = "UT"         # ultrasonidos
    RT = "RT"         # radiografía


class EquipmentCategory(str, enum.Enum):
    DRIVER = "DRIVER"
    BATTERY = "BATTERY"
    SMARTEC_NODE = "SMARTEC_NODE"
    TERMINAL_BLOCK = "TERMINAL_BLOCK"
    PROTECTION = "PROTECTION"
    AUXILIARY = "AUXILIARY"


class FEAStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    CONVERGED = "CONVERGED"
    FAILED = "FAILED"
    NOT_REQUIRED = "NOT_REQUIRED"


class DetailReleaseLevel(str, enum.Enum):
    M0 = "M0"   # exploración libre
    M1 = "M1"   # concepto
    M2 = "M2"   # prediseño
    M3 = "M3"   # detalle (requiere revisión OT)
    M4 = "M4"   # producción (detalle congelado, documentos)


class OpeningStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    OPTIMIZED = "OPTIMIZED"
    RELEASED = "RELEASED"
    BLOCKED = "BLOCKED"


# ── Tablas ORM ───────────────────────────────────────────────────────────────

class OpeningDefinition(Base):
    """Definición geométrica de un hueco en el fuste."""
    __tablename__ = "opening_definition"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    design_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    opening_type = Column(Enum(OpeningType), nullable=False)
    geometric_level = Column(Enum(OpeningGeometricLevel), nullable=False, default=OpeningGeometricLevel.G1)
    route = Column(Enum(DetailRoute))
    status = Column(Enum(OpeningStatus), nullable=False, default=OpeningStatus.DRAFT)

    # Geometría del hueco
    station_bottom_m = Column(Float, nullable=False)
    station_top_m = Column(Float, nullable=False)
    width_mm = Column(Float, nullable=False)
    height_mm = Column(Float, nullable=False)
    corner_radius_mm = Column(Float, default=0.0)
    orientation_deg = Column(Float, nullable=False, default=0.0)  # respecto al cero geométrico

    # Tolerancias
    tol_width_mm = Column(Float, default=1.0)
    tol_height_mm = Column(Float, default=1.0)
    tol_position_mm = Column(Float, default=2.0)
    tol_corner_radius_mm = Column(Float, default=0.5)

    # Geometría del fuste en la estación
    D_ext_mm = Column(Float)
    t_wall_mm = Column(Float)

    # Hashes de trazabilidad
    geometric_hash = Column(String(64))
    rules_hash = Column(String(64))

    # Datos adicionales
    extra_json = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    reinforcements = relationship("ReinforcementDefinition", back_populates="opening", cascade="all, delete-orphan")
    section_results = relationship("LocalSectionResult", back_populates="opening", cascade="all, delete-orphan")
    check_results = relationship("LocalCheckResult", back_populates="opening", cascade="all, delete-orphan")
    weld_groups = relationship("WeldGroup", back_populates="opening", cascade="all, delete-orphan")
    support_layouts = relationship("SupportLayout", back_populates="opening", cascade="all, delete-orphan")
    fea_models = relationship("FEALocalModel", back_populates="opening", cascade="all, delete-orphan")
    releases = relationship("DetailRelease", back_populates="opening", cascade="all, delete-orphan")


class ReinforcementDefinition(Base):
    """Definición de un refuerzo para un hueco."""
    __tablename__ = "reinforcement_definition"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    opening_id = Column(UUID(as_uuid=True), ForeignKey("opening_definition.id", ondelete="CASCADE"), nullable=False)
    family = Column(Enum(ReinforcementFamily), nullable=False)
    material_code = Column(String(64), nullable=False)
    thickness_mm = Column(Float, nullable=False)
    width_mm = Column(Float)
    depth_mm = Column(Float)
    extension_top_mm = Column(Float, default=0.0)
    extension_bottom_mm = Column(Float, default=0.0)
    offset_mm = Column(Float, default=0.0)
    geometry_json = Column(JSONB, default={})
    weld_process = Column(Enum(WeldProcess))
    cost_eur = Column(Float)
    mass_kg = Column(Float)
    co2_kg = Column(Float)
    feasible = Column(Boolean, default=True)
    pareto_dominated = Column(Boolean)
    rejection_reason = Column(String(256))
    design_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opening = relationship("OpeningDefinition", back_populates="reinforcements")


class LocalSectionResult(Base):
    """Propiedades de sección neta/compuesta calculadas para un hueco."""
    __tablename__ = "local_section_result"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    opening_id = Column(UUID(as_uuid=True), ForeignKey("opening_definition.id", ondelete="CASCADE"), nullable=False)
    method = Column(String(64), nullable=False)  # "INTEGRATION" | "FIBER" | "COMPOSITE"
    include_reinforcement = Column(Boolean, default=False)

    # Sección bruta
    A_gross_m2 = Column(Float)
    Iy_gross_m4 = Column(Float)
    Iz_gross_m4 = Column(Float)

    # Sección neta
    A_net_m2 = Column(Float)
    centroid_x_m = Column(Float)
    centroid_y_m = Column(Float)
    Iy_net_m4 = Column(Float)
    Iz_net_m4 = Column(Float)
    Iyz_net_m4 = Column(Float)
    J_net_m4 = Column(Float)
    Cw_m6 = Column(Float)

    # Ejes principales
    alpha_principal_deg = Column(Float)
    I1_m4 = Column(Float)
    I2_m4 = Column(Float)

    # Módulos
    Wel_y_m3 = Column(Float)
    Wel_z_m3 = Column(Float)

    # Contraste por fibras
    contrast_delta_pct = Column(Float)
    contrast_passed = Column(Boolean)

    status = Column(Enum(DetailCheckStatus), nullable=False)
    error_code = Column(String(32))
    run_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opening = relationship("OpeningDefinition", back_populates="section_results")


class LocalCheckResult(Base):
    """Resultado de una verificación local (resistencia, estabilidad, fatiga…)."""
    __tablename__ = "local_check_result"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    opening_id = Column(UUID(as_uuid=True), ForeignKey("opening_definition.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String(32))
    check_type = Column(String(64), nullable=False)
    demand = Column(Float, nullable=False)
    resistance = Column(Float, nullable=False)
    utilization = Column(Float, nullable=False)
    unit = Column(String(32))
    status = Column(Enum(DetailCheckStatus), nullable=False)
    governing_rule = Column(String(256))
    intermediate_values_json = Column(JSONB, default={})
    equation_trace_json = Column(JSONB, default={})
    error_code = Column(String(32))
    run_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opening = relationship("OpeningDefinition", back_populates="check_results")


class WeldGroup(Base):
    """Grupo de soldaduras para un detalle local."""
    __tablename__ = "weld_group"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    opening_id = Column(UUID(as_uuid=True), ForeignKey("opening_definition.id", ondelete="CASCADE"), nullable=False)
    reinforcement_id = Column(UUID(as_uuid=True), ForeignKey("reinforcement_definition.id"), nullable=True)

    group_label = Column(String(64))
    segment_count = Column(Integer)
    total_length_mm = Column(Float, nullable=False)
    throat_mm = Column(Float, nullable=False)
    weld_process = Column(Enum(WeldProcess), nullable=False)
    fatigue_category = Column(String(16))  # p.ej. "FAT71", "FAT90"
    inspection_level = Column(Enum(WeldInspection))

    # Propiedades del grupo
    centroid_json = Column(JSONB, default={})
    Ip_polar_mm4 = Column(Float)

    # Resultados
    force_direct_n_mm = Column(Float)
    force_torsion_n_mm = Column(Float)
    f_res_max_n_mm = Column(Float)
    capacity_n_mm = Column(Float)
    utilization = Column(Float)
    status = Column(Enum(DetailCheckStatus))
    governing_rule = Column(String(128))
    run_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opening = relationship("OpeningDefinition", back_populates="weld_groups")


class EquipmentItem(Base):
    """Equipo instalable en el interior de la columna."""
    __tablename__ = "equipment_item"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id = Column(UUID(as_uuid=True), nullable=False)
    equipment_type = Column(Enum(EquipmentCategory), nullable=False)
    reference = Column(String(128))
    description = Column(Text)

    # Envolvente física
    length_mm = Column(Float, nullable=False)
    width_mm = Column(Float, nullable=False)
    height_mm = Column(Float, nullable=False)
    mass_kg = Column(Float, nullable=False)
    cg_json = Column(JSONB, default={})  # {x, y, z} mm desde referencia

    # Interfaces y servicio
    interfaces_json = Column(JSONB, default={})
    service_volume_json = Column(JSONB, default={})
    extraction_volume_json = Column(JSONB, default={})

    # Requisitos ambientales
    ip_rating = Column(String(8))
    ik_rating = Column(String(8))
    max_temperature_c = Column(Float)
    min_temperature_c = Column(Float)

    # Cargas
    max_load_kn = Column(Float)
    vibration_class = Column(String(16))

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SupportLayout(Base):
    """Disposición de soportes y equipos en el interior de la columna."""
    __tablename__ = "support_layout"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    opening_id = Column(UUID(as_uuid=True), ForeignKey("opening_definition.id", ondelete="CASCADE"), nullable=False)
    equipment_ids_json = Column(JSONB, default=[])

    plate_type = Column(String(64))
    rail_type = Column(String(64))
    fastener_pattern_json = Column(JSONB, default={})

    # Cargas totales
    loads_json = Column(JSONB, default={})

    # Verificación de accesibilidad
    accessible = Column(Boolean)
    tool_clearance_ok = Column(Boolean)
    cable_radius_ok = Column(Boolean)
    extraction_sequence_json = Column(JSONB, default=[])

    status = Column(Enum(DetailCheckStatus))
    error_code = Column(String(32))
    run_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opening = relationship("OpeningDefinition", back_populates="support_layouts")


class FEALocalModel(Base):
    """Submodelo FEM local para un detalle."""
    __tablename__ = "fea_local_model"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    opening_id = Column(UUID(as_uuid=True), ForeignKey("opening_definition.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(32), nullable=False, default="1.0")
    mesh_hash = Column(String(64))
    bc_json = Column(JSONB, default={})          # condiciones de contorno
    material_model = Column(String(32))           # "ELASTIC" | "NONLINEAR"
    activation_reason = Column(String(256))

    # Resultados de convergencia
    convergence_ratio = Column(Float)             # variación entre mallas ≤ 3%
    equilibrium_residual_pct = Column(Float)     # ≤ 0.1%

    # Resultados estructurales
    max_stress_mpa = Column(Float)
    max_hotspot_stress_mpa = Column(Float)
    max_deformation_mm = Column(Float)
    buckling_factor = Column(Float)

    # Comparación analítica
    analytic_ref_stress_mpa = Column(Float)
    comparison_delta_pct = Column(Float)

    status = Column(Enum(FEAStatus), nullable=False, default=FEAStatus.PENDING)
    error_code = Column(String(32))
    run_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opening = relationship("OpeningDefinition", back_populates="fea_models")


class DetailFamily(Base):
    """Familia estándar de detalles con expediente digital."""
    __tablename__ = "detail_family"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    family_code = Column(String(64), nullable=False, unique=True)
    description = Column(Text)
    opening_type = Column(Enum(OpeningType))
    reinforcement_family = Column(Enum(ReinforcementFamily))

    # Dominio de validez
    domain_json = Column(JSONB, default={})        # ratios altura/ancho, rango diámetros, cargas, materiales
    test_references_json = Column(JSONB, default=[])
    modifications_allowed_json = Column(JSONB, default=[])

    status = Column(String(32), default="ACTIVE")  # ACTIVE | DEPRECATED | DRAFT
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DetailRelease(Base):
    """Revisión liberada de un detalle local."""
    __tablename__ = "detail_release"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    opening_id = Column(UUID(as_uuid=True), ForeignKey("opening_definition.id", ondelete="CASCADE"), nullable=False)
    release_level = Column(Enum(DetailReleaseLevel), nullable=False)
    content_hash = Column(String(64), nullable=False)
    input_hashes_json = Column(JSONB, default={})
    all_checks_passed = Column(Boolean, nullable=False, default=False)
    approved_by = Column(String(256))
    approved_at = Column(DateTime(timezone=True))
    documents_json = Column(JSONB, default={})   # {plano_dxf, bom, memoria, instrucciones}
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opening = relationship("OpeningDefinition", back_populates="releases")
