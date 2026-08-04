"""
DB ORM models · Fase 5 — Acero: Diseño, Verificación y Fabricación
Salvi Studio · Columns
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SteelGrade(str, enum.Enum):
    S235 = "S235"
    S275 = "S275"
    S355 = "S355"
    S420 = "S420"  # extensible
    S460 = "S460"


class SteelSubgrade(str, enum.Enum):
    JR = "JR"
    J0 = "J0"
    J2 = "J2"
    K2 = "K2"
    M = "M"
    N = "N"


class SteelProductForm(str, enum.Enum):
    SHEET = "SHEET"           # chapa
    COIL = "COIL"             # banda/rollo
    HOT_TUBE = "HOT_TUBE"     # tubo acabado en caliente
    COLD_TUBE = "COLD_TUBE"   # tubo conformado en frío
    PROFILE = "PROFILE"       # perfil
    BAR = "BAR"               # barra
    BOLT = "BOLT"             # perno
    MACHINED = "MACHINED"     # pieza mecanizada


class NormativeRoute(str, enum.Enum):
    EN40 = "EN40"                  # ≤20m, sin cables, dentro de EN 40-3-3
    EN40_EXTENDED = "EN40_EXTENDED"  # >20m, cables, o detalles fuera de EN 40
    SPECIAL = "SPECIAL"            # estructura especial


class RouteDecisionStatus(str, enum.Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"


class SectionPropertySet(str, enum.Enum):
    GROSS = "GROSS"           # bruta
    NET = "NET"               # neta (con huecos)
    COMPOSITE = "COMPOSITE"  # compuesta (fuste + refuerzo)
    EFFECTIVE = "EFFECTIVE"  # efectiva (clase 4 / pandeo local)
    FABRICATION = "FABRICATION"  # de fabricación


class SteelCheckStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"    # falta datos o dominio excedido
    WARNING = "WARNING"


class WeldType(str, enum.Enum):
    W_LONG = "W_LONG"    # costura longitudinal fuste
    W_CIRC = "W_CIRC"    # unión circunferencial virolas
    W_BASE = "W_BASE"    # fuste a placa base
    W_ARM = "W_ARM"      # brazo/cruceta a fuste
    W_REINF = "W_REINF"  # marco/refuerzo puerta
    W_STIFF = "W_STIFF"  # cartelas y rigidizadores
    W_SLEEVE = "W_SLEEVE"  # manguito o solape


class WeldProcess(str, enum.Enum):
    SMAW = "SMAW"   # electrodo revestido
    GMAW = "GMAW"   # MIG/MAG
    GTAW = "GTAW"   # TIG
    SAW = "SAW"     # arco sumergido
    FCAW = "FCAW"   # hilo tubular


class WeldQualityClass(str, enum.Enum):
    B = "B"     # mejor
    C = "C"
    D = "D"
    E = "E"     # mínima


class FatigueMethod(str, enum.Enum):
    SIMPLIFIED_EN40 = "SIMPLIFIED_EN40"
    DAMAGE_ACCUMULATION = "DAMAGE_ACCUMULATION"
    STRUCTURAL_STRESS = "STRUCTURAL_STRESS"


class CorrosivityCategory(str, enum.Enum):
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"
    CX = "CX"
    IM1 = "IM1"
    IM2 = "IM2"
    IM3 = "IM3"


class ProtectionSystem(str, enum.Enum):
    HOT_DIP_GALVANIZING = "HOT_DIP_GALVANIZING"
    PAINT = "PAINT"
    DUPLEX = "DUPLEX"
    THERMAL_SPRAY = "THERMAL_SPRAY"
    REINFORCED = "REINFORCED"


class JointType(str, enum.Enum):
    TELESCOPIC = "TELESCOPIC"
    FLANGED = "FLANGED"
    SHOP_WELDED = "SHOP_WELDED"
    BOLTED = "BOLTED"
    SLEEVE = "SLEEVE"


class SteelRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class OptimizationObjective(str, enum.Enum):
    MIN_COST = "MIN_COST"
    MIN_WEIGHT = "MIN_WEIGHT"
    MIN_CO2 = "MIN_CO2"
    BALANCED = "BALANCED"


class MaturityLevel(str, enum.Enum):
    M1 = "M1"   # exploración
    M2 = "M2"   # predimensionamiento
    M3 = "M3"   # cálculo verificado
    M4 = "M4"   # liberado para producción


class ValidationEvidenceType(str, enum.Enum):
    CALCULATION = "CALCULATION"
    TEST_EN40_3_2 = "TEST_EN40_3_2"
    LOCAL_FEM = "LOCAL_FEM"
    HISTORICAL = "HISTORICAL"
    PRODUCTION_INSPECTION = "PRODUCTION_INSPECTION"


# ---------------------------------------------------------------------------
# Steel material library
# ---------------------------------------------------------------------------

class SteelProductProperty(Base):
    """
    Biblioteca de propiedades de acero por norma, grado, subgrado, forma y rango
    de espesor. Clave canónica: norm+grade+subgrade+product_form+condition+
    thickness_range+temperature. Inmutable una vez publicada; nueva versión si cambia.
    """
    __tablename__ = "steel_product_properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)

    # Clave canónica
    product_norm = Column(String(64), nullable=False)          # p.ej. "EN 10025-2"
    steel_grade = Column(Enum(SteelGrade, name="steel_grade"), nullable=False)
    subgrade = Column(Enum(SteelSubgrade, name="steel_subgrade"), nullable=False)
    product_form = Column(Enum(SteelProductForm, name="steel_product_form"), nullable=False)
    supply_condition = Column(String(32), nullable=False, default="AR")  # AR, N, M, Q…
    thickness_min_mm = Column(Numeric(6, 2), nullable=False)
    thickness_max_mm = Column(Numeric(6, 2), nullable=False)
    temperature_min_c = Column(Numeric(6, 1), nullable=True)  # temperatura de servicio mínima

    # Propiedades resistentes
    fy_mpa = Column(Numeric(8, 2), nullable=False)   # límite elástico
    fu_mpa = Column(Numeric(8, 2), nullable=False)   # resistencia última

    # Propiedades elásticas
    E_gpa = Column(Numeric(8, 3), nullable=False, default=210.0)
    G_gpa = Column(Numeric(8, 3), nullable=False, default=80.769)
    nu = Column(Numeric(6, 4), nullable=False, default=0.3)
    rho_kg_m3 = Column(Numeric(8, 2), nullable=False, default=7850.0)
    alpha_t_per_k = Column(Numeric(12, 10), nullable=False, default=12e-6)

    # Tenacidad y soldabilidad
    charpy_energy_j = Column(Numeric(8, 2), nullable=True)
    charpy_temp_c = Column(Numeric(6, 1), nullable=True)
    cev_max = Column(Numeric(6, 4), nullable=True)          # carbono equivalente máx.
    weldability_note = Column(Text, nullable=True)

    # Recubrimientos y tolerancias
    coating_compatibility = Column(JSONB, nullable=True)     # {galvanizing: true, ...}
    thickness_tolerance_pct = Column(Numeric(6, 3), nullable=True)  # Δt_tol como % del nominal
    certificate_type = Column(String(32), nullable=True)     # 3.1, 3.2, 2.2

    # CO₂
    carbon_factor_kg_co2_per_kg = Column(Numeric(8, 4), nullable=True)
    carbon_factor_source = Column(String(128), nullable=True)
    carbon_factor_year = Column(Integer, nullable=True)
    carbon_factor_region = Column(String(64), nullable=True)

    # Trazabilidad
    library_version = Column(String(32), nullable=False, default="1.0")
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    deprecated = Column(Boolean, nullable=False, default=False)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "product_norm", "steel_grade", "subgrade", "product_form",
            "supply_condition", "thickness_min_mm", "thickness_max_mm",
            "temperature_min_c", "library_version",
            name="uq_steel_product_property_canonical",
        ),
    )


# ---------------------------------------------------------------------------
# Normative route classifier result
# ---------------------------------------------------------------------------

class SteelNormativeRoute(Base):
    """
    Resultado del clasificador normativo de 7 pasos para una ejecución de
    verificación de acero. Inmutable; nueva fila si cambia cualquier condición.
    """
    __tablename__ = "steel_normative_routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    structural_run_id = Column(UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id"), nullable=True)

    route = Column(Enum(NormativeRoute, name="normative_route"), nullable=False)
    route_version = Column(String(32), nullable=False, default="1.0")

    # Traza de decisión paso a paso
    step_1_status = Column(Enum(RouteDecisionStatus, name="route_decision_status"), nullable=False)
    step_2_status = Column(Enum(RouteDecisionStatus, name="route_decision_status"), nullable=False)
    step_3_status = Column(Enum(RouteDecisionStatus, name="route_decision_status"), nullable=False)
    step_4_status = Column(Enum(RouteDecisionStatus, name="route_decision_status"), nullable=False)
    step_5_status = Column(Enum(RouteDecisionStatus, name="route_decision_status"), nullable=False)
    step_6_status = Column(Enum(RouteDecisionStatus, name="route_decision_status"), nullable=False)
    step_7_status = Column(Enum(RouteDecisionStatus, name="route_decision_status"), nullable=False)

    decision_trace = Column(JSONB, nullable=False)          # detalles de cada paso
    active_rules = Column(JSONB, nullable=False, default=list)
    discarded_rules = Column(JSONB, nullable=False, default=list)
    exclusions = Column(JSONB, nullable=False, default=list)
    warnings = Column(JSONB, nullable=False, default=list)
    max_declaration_allowed = Column(String(128), nullable=True)

    # Hash de los inputs que generaron esta ruta
    input_hash = Column(String(64), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


# ---------------------------------------------------------------------------
# Section verification run
# ---------------------------------------------------------------------------

class SteelSectionCheckRun(Base):
    """
    Ejecución completa de verificación de secciones de acero sobre un run de Fase 4.
    Crea una nueva fila en cada recálculo; no sobrescribe.
    """
    __tablename__ = "steel_section_check_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    structural_run_id = Column(UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id"), nullable=False)
    normative_route_id = Column(UUID(as_uuid=True), ForeignKey("steel_normative_routes.id"), nullable=False)

    status = Column(Enum(SteelRunStatus, name="steel_run_status"), nullable=False, default=SteelRunStatus.PENDING)
    maturity_level = Column(Enum(MaturityLevel, name="maturity_level"), nullable=False, default=MaturityLevel.M2)

    # Hashes de trazabilidad
    geometry_hash = Column(String(64), nullable=False)
    material_hash = Column(String(64), nullable=False)
    rules_hash = Column(String(64), nullable=False)
    stress_hash = Column(String(64), nullable=False)
    run_hash = Column(String(64), nullable=True)   # combinación de todos

    # Configuración del motor
    utilization_limit = Column(Numeric(6, 4), nullable=False, default=1.0)
    include_fatigue = Column(Boolean, nullable=False, default=False)
    include_local_buckling = Column(Boolean, nullable=False, default=True)

    # Resumen global
    max_utilization = Column(Numeric(8, 6), nullable=True)
    governing_station_id = Column(UUID(as_uuid=True), nullable=True)
    governing_combination = Column(String(128), nullable=True)
    governing_check_type = Column(String(64), nullable=True)
    all_checks_passed = Column(Boolean, nullable=True)
    error_code = Column(String(32), nullable=True)
    error_detail = Column(Text, nullable=True)

    idempotency_key = Column(String(128), nullable=True, unique=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    checks = relationship("SteelSectionCheck", back_populates="run", lazy="dynamic")


class SteelSectionCheck(Base):
    """
    Resultado de una verificación individual (estación × combinación × tipo de check).
    Inmutable.
    """
    __tablename__ = "steel_section_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("steel_section_check_runs.id", ondelete="CASCADE"), nullable=False)

    station_id = Column(UUID(as_uuid=True), ForeignKey("structural_nodes.id"), nullable=True)
    element_id = Column(UUID(as_uuid=True), ForeignKey("structural_elements.id"), nullable=True)
    combination_id = Column(String(128), nullable=False)
    wind_direction_deg = Column(Numeric(6, 2), nullable=True)

    check_type = Column(String(64), nullable=False)     # TENSION, BENDING, SHEAR, TORSION, INTERACTION, LOCAL_BUCKLING, GLOBAL_BUCKLING, FATIGUE
    norm = Column(String(32), nullable=False)            # EN40-3-3 / EN1993-1-1
    norm_edition = Column(String(16), nullable=True)
    norm_clause = Column(String(32), nullable=True)

    property_set = Column(Enum(SectionPropertySet, name="section_property_set"), nullable=False)
    route = Column(Enum(NormativeRoute, name="normative_route"), nullable=False)

    # Esfuerzos concurrentes de entrada (N)
    N_kn = Column(Numeric(14, 4), nullable=True)
    Vy_kn = Column(Numeric(14, 4), nullable=True)
    Vz_kn = Column(Numeric(14, 4), nullable=True)
    T_knm = Column(Numeric(14, 6), nullable=True)
    My_knm = Column(Numeric(14, 6), nullable=True)
    Mz_knm = Column(Numeric(14, 6), nullable=True)

    # Resistencias de cálculo
    N_rd_kn = Column(Numeric(14, 4), nullable=True)
    Vy_rd_kn = Column(Numeric(14, 4), nullable=True)
    Vz_rd_kn = Column(Numeric(14, 4), nullable=True)
    T_rd_knm = Column(Numeric(14, 6), nullable=True)
    My_rd_knm = Column(Numeric(14, 6), nullable=True)
    Mz_rd_knm = Column(Numeric(14, 6), nullable=True)

    utilization = Column(Numeric(8, 6), nullable=False)
    margin = Column(Numeric(8, 6), nullable=True)       # 1 - utilization
    status = Column(Enum(SteelCheckStatus, name="steel_check_status"), nullable=False)

    # Intermedios completos
    intermediate_values = Column(JSONB, nullable=True)  # todas las variables intermedias
    domain_ok = Column(Boolean, nullable=False, default=True)
    domain_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("SteelSectionCheckRun", back_populates="checks")


# ---------------------------------------------------------------------------
# Effective section (pandeo local / clase 4)
# ---------------------------------------------------------------------------

class EffectiveSectionRun(Base):
    """
    Iteración de propiedades efectivas por pandeo local o clasificación de sección.
    """
    __tablename__ = "effective_section_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    check_run_id = Column(UUID(as_uuid=True), ForeignKey("steel_section_check_runs.id", ondelete="CASCADE"), nullable=False)
    element_id = Column(UUID(as_uuid=True), ForeignKey("structural_elements.id"), nullable=True)
    station_z_m = Column(Numeric(10, 4), nullable=True)

    # Paneles analizados
    panels = Column(JSONB, nullable=False)    # lista de paneles: {id, width_mm, t_mm, angle_deg, psi, class}
    section_class = Column(Integer, nullable=True)  # 1, 2, 3 o 4

    # Propiedades efectivas calculadas
    A_eff_m2 = Column(Numeric(14, 10), nullable=True)
    Iy_eff_m4 = Column(Numeric(20, 16), nullable=True)
    Iz_eff_m4 = Column(Numeric(20, 16), nullable=True)
    centroid_y_shift_m = Column(Numeric(12, 9), nullable=True)
    centroid_z_shift_m = Column(Numeric(12, 9), nullable=True)

    iterations = Column(Integer, nullable=True)
    converged = Column(Boolean, nullable=False, default=False)
    convergence_tolerance = Column(Numeric(10, 8), nullable=True)
    error_code = Column(String(32), nullable=True)   # STEEL-SEC-001 si no converge

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Door section model
# ---------------------------------------------------------------------------

class DoorSectionModel(Base):
    """
    Modelo de sección de puerta: hueco, refuerzos y propiedades netas/compuestas.
    """
    __tablename__ = "door_section_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    check_run_id = Column(UUID(as_uuid=True), ForeignKey("steel_section_check_runs.id"), nullable=True)

    # Geometría del hueco
    door_height_mm = Column(Numeric(8, 2), nullable=False)
    door_width_mm = Column(Numeric(8, 2), nullable=False)
    corner_radius_mm = Column(Numeric(6, 2), nullable=True)
    bottom_elevation_m = Column(Numeric(8, 4), nullable=False)  # respecto a rasante
    top_elevation_m = Column(Numeric(8, 4), nullable=False)
    orientation_deg = Column(Numeric(6, 2), nullable=False, default=0.0)

    # Refuerzos
    reinforcement_type = Column(String(64), nullable=True)   # FRAME, RING, SHEET, MIXED
    reinforcement_geometry = Column(JSONB, nullable=True)

    # Propiedades netas de la sección con puerta
    A_net_m2 = Column(Numeric(14, 10), nullable=True)
    Iy_net_m4 = Column(Numeric(20, 16), nullable=True)
    Iz_net_m4 = Column(Numeric(20, 16), nullable=True)
    Iyz_net_m4 = Column(Numeric(20, 16), nullable=True)     # tensor cruzado si refuerzo asimétrico
    J_net_m4 = Column(Numeric(20, 16), nullable=True)
    centroid_y_m = Column(Numeric(12, 9), nullable=True)
    centroid_z_m = Column(Numeric(12, 9), nullable=True)
    principal_angle_deg = Column(Numeric(8, 4), nullable=True)

    # Método de cálculo usado
    method_level = Column(String(32), nullable=False, default="GLOBAL_EN40")  # GLOBAL_EN40, IMPROVED, LOCAL_ANALYTICAL, FEM, TEST
    method_in_domain = Column(Boolean, nullable=False, default=True)
    requires_local_method = Column(Boolean, nullable=False, default=False)
    error_code = Column(String(32), nullable=True)   # STEEL-DOOR-001

    # Hash para invalidación
    geometry_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Weld groups and checks
# ---------------------------------------------------------------------------

class SteelWeldGroup(Base):
    """
    Grupo de soldadura con geometría efectiva, cargas concurrentes y resultados
    estático + fatiga.
    """
    __tablename__ = "weld_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    check_run_id = Column(UUID(as_uuid=True), ForeignKey("steel_section_check_runs.id"), nullable=True)

    weld_type = Column(Enum(WeldType, name="weld_type"), nullable=False)
    weld_process = Column(Enum(WeldProcess, name="weld_process"), nullable=True)
    quality_class = Column(Enum(WeldQualityClass, name="weld_quality_class"), nullable=True)

    # Geometría efectiva del grupo
    weld_group_geometry = Column(JSONB, nullable=False)  # segmentos, arcos, garganta, longitud efectiva, retornos
    effective_throat_mm = Column(Numeric(6, 2), nullable=True)
    effective_length_mm = Column(Numeric(8, 2), nullable=True)
    ineffective_length_mm = Column(Numeric(8, 2), nullable=True)  # inicios, cráteres, interrupciones

    # Materiales
    base_material_id = Column(UUID(as_uuid=True), ForeignKey("steel_product_properties.id"), nullable=True)
    filler_material = Column(String(64), nullable=True)
    fu_w_mpa = Column(Numeric(8, 2), nullable=True)     # resistencia de cálculo del material de aportación

    # WPS
    wps_reference = Column(String(64), nullable=True)
    position = Column(String(16), nullable=True)         # PA, PB, PC, PD, PE, PF, PG
    accessible_for_inspection = Column(Boolean, nullable=False, default=True)
    fabricable = Column(Boolean, nullable=False, default=True)

    # Cargas resultantes en el centroide del grupo
    Fx_kn = Column(Numeric(14, 4), nullable=True)
    Fy_kn = Column(Numeric(14, 4), nullable=True)
    Fz_kn = Column(Numeric(14, 4), nullable=True)
    Mx_knm = Column(Numeric(14, 6), nullable=True)
    My_knm = Column(Numeric(14, 6), nullable=True)
    Mz_knm = Column(Numeric(14, 6), nullable=True)

    # Resultado estático
    sigma_eq_mpa = Column(Numeric(10, 4), nullable=True)    # tensión equivalente
    sigma_rd_mpa = Column(Numeric(10, 4), nullable=True)    # resistencia de cálculo
    static_utilization = Column(Numeric(8, 6), nullable=True)
    static_status = Column(Enum(SteelCheckStatus, name="steel_check_status"), nullable=True)

    # Resultado fatiga
    delta_sigma_mpa = Column(Numeric(10, 4), nullable=True)  # rango de tensión
    fatigue_category = Column(String(16), nullable=True)      # Δσc en MPa
    fatigue_cycles = Column(Numeric(14, 2), nullable=True)
    fatigue_damage = Column(Numeric(10, 8), nullable=True)    # Σ(n/N)
    fatigue_utilization = Column(Numeric(8, 6), nullable=True)
    fatigue_status = Column(Enum(SteelCheckStatus, name="steel_check_status"), nullable=True)

    # Inspección
    inspection_method = Column(String(32), nullable=True)  # VT/MT/PT/UT/RT
    inspection_extent_pct = Column(Numeric(6, 2), nullable=True)
    inspection_criterion = Column(String(64), nullable=True)

    error_code = Column(String(32), nullable=True)   # STEEL-WELD-001
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Fatigue details catalogue
# ---------------------------------------------------------------------------

class FatigueDetail(Base):
    """
    Catálogo de detalles de fatiga versionados. Cada detalle tiene geometría
    elegible, categoría, curva, dominio y evidencia. No se selecciona manualmente.
    """
    __tablename__ = "fatigue_details"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)

    detail_id = Column(String(32), nullable=False)          # código interno
    description = Column(String(256), nullable=False)
    eligible_geometry = Column(JSONB, nullable=False)       # condiciones de elegibilidad
    stress_orientation = Column(String(32), nullable=False) # NORMAL, SHEAR, COMBINED
    fatigue_category_mpa = Column(Numeric(8, 2), nullable=False)  # Δσc (categoría)
    sn_curve_id = Column(String(32), nullable=False)        # referencia a curva S-N
    thickness_limit_mm = Column(Numeric(6, 2), nullable=True)

    norm = Column(String(32), nullable=False)
    norm_edition = Column(String(16), nullable=True)
    norm_clause = Column(String(32), nullable=True)
    quality_required = Column(Enum(WeldQualityClass, name="weld_quality_class"), nullable=True)

    domain_min_thickness_mm = Column(Numeric(6, 2), nullable=True)
    domain_max_thickness_mm = Column(Numeric(6, 2), nullable=True)
    domain_notes = Column(Text, nullable=True)

    validation_cases = Column(JSONB, nullable=True)
    reference_images = Column(JSONB, nullable=True)

    library_version = Column(String(32), nullable=False, default="1.0")
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    deprecated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Durability / corrosion system
# ---------------------------------------------------------------------------

class DurabilitySystem(Base):
    """
    Sistema de protección anticorrosiva seleccionado para un proyecto o componente.
    """
    __tablename__ = "durability_systems"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    component = Column(String(64), nullable=True, default="FULL_COLUMN")  # FULL_COLUMN, SOIL_ZONE, INTERIOR...
    corrosivity_category = Column(Enum(CorrosivityCategory, name="corrosivity_category"), nullable=False)
    design_life_years = Column(Integer, nullable=False)
    exposure_type = Column(String(64), nullable=True)   # URBAN, INDUSTRIAL, MARINE, BURIED, SPLASH
    protection_system = Column(Enum(ProtectionSystem, name="protection_system"), nullable=False)

    # Capas del sistema
    layers = Column(JSONB, nullable=False)   # [{type, thickness_um, product, norm}]
    surface_preparation = Column(String(32), nullable=True)   # Sa 2.5, St 3...
    maintenance_interval_years = Column(Integer, nullable=True)
    maintenance_notes = Column(Text, nullable=True)

    # Reglas automáticas de galvanizado
    galvanizing_vent_holes_ok = Column(Boolean, nullable=True)
    galvanizing_drain_holes_ok = Column(Boolean, nullable=True)
    closed_cavities_detected = Column(Boolean, nullable=False, default=False)

    compatible = Column(Boolean, nullable=True)          # ¿cumple vida útil?
    error_code = Column(String(32), nullable=True)       # STEEL-COR-001

    # Coste estimado
    cost_per_m2 = Column(Numeric(10, 4), nullable=True)
    co2_kg_per_m2 = Column(Numeric(10, 4), nullable=True)

    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Manufacturing route and calibration
# ---------------------------------------------------------------------------

class ManufacturingCalibration(Base):
    """
    Calibración de plegado versionada por material, espesor, máquina, útil y proveedor.
    Si no existe calibración → salida preliminar no liberable.
    """
    __tablename__ = "manufacturing_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)

    material = Column(String(32), nullable=False)
    thickness_min_mm = Column(Numeric(6, 2), nullable=False)
    thickness_max_mm = Column(Numeric(6, 2), nullable=False)
    machine = Column(String(64), nullable=True)
    tool = Column(String(64), nullable=True)
    provider = Column(String(128), nullable=True)

    # Datos de calibración
    bend_allowance_mm = Column(Numeric(8, 4), nullable=True)      # compensación de plegado
    springback_deg = Column(Numeric(6, 3), nullable=True)          # recuperación elástica
    min_inner_radius_mm = Column(Numeric(6, 2), nullable=True)
    k_factor = Column(Numeric(6, 4), nullable=True)

    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    version = Column(String(32), nullable=False, default="1.0")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ManufacturingRoute(Base):
    """
    Ruta de fabricación: secuencia de proceso, BOM, tolerancias y restricciones
    para un proyecto de acero.
    """
    __tablename__ = "manufacturing_routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(SteelRunStatus, name="steel_run_status"), nullable=False, default=SteelRunStatus.PENDING)

    # BOM agrupado
    bom = Column(JSONB, nullable=True)       # {fuste, puerta, interior, uniones, base, brazos, soldadura, acabado, embalaje}
    total_mass_kg = Column(Numeric(10, 3), nullable=True)
    total_surface_m2 = Column(Numeric(10, 4), nullable=True)

    # Coste
    material_cost = Column(Numeric(12, 2), nullable=True)
    process_cost = Column(JSONB, nullable=True)  # {material_bruto, merma, corte, plegado, soldadura, ...}
    total_industrial_cost = Column(Numeric(12, 2), nullable=True)
    margin_pct = Column(Numeric(6, 3), nullable=True)
    margin_type = Column(String(16), nullable=True)   # ON_SALE, ON_COST
    sale_price = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(8), nullable=False, default="EUR")

    # CO₂
    co2_steel_kg = Column(Numeric(12, 4), nullable=True)
    co2_process_kg = Column(Numeric(12, 4), nullable=True)
    co2_coating_kg = Column(Numeric(12, 4), nullable=True)
    co2_transport_kg = Column(Numeric(12, 4), nullable=True)
    co2_total_kg = Column(Numeric(12, 4), nullable=True)

    # Restricciones bloqueantes
    blocking_rules = Column(JSONB, nullable=True)   # lista de reglas incumplidas
    all_fabricable = Column(Boolean, nullable=True)
    error_code = Column(String(32), nullable=True)  # STEEL-MFG-001

    # Desarrollo de chapa
    blank_geometry = Column(JSONB, nullable=True)   # contorno 2D, longitudes, referencias
    bend_lines = Column(JSONB, nullable=True)
    nesting = Column(JSONB, nullable=True)          # formato chapa, orientación, merma, retales

    # Tolerancias
    tolerances = Column(JSONB, nullable=True)       # {longitud, rectitud, sección, puerta, ...}

    calibration_id = Column(UUID(as_uuid=True), ForeignKey("manufacturing_calibrations.id"), nullable=True)
    is_preliminary = Column(Boolean, nullable=False, default=False)  # True si no hay calibración

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


# ---------------------------------------------------------------------------
# Steel joint (unión entre tramos)
# ---------------------------------------------------------------------------

class SteelJoint(Base):
    """
    Unión entre tramos de acero: telescópica, embridada, soldada de taller o
    atornillada. Retroalimenta rigidez a Fase 4.
    """
    __tablename__ = "steel_joints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    check_run_id = Column(UUID(as_uuid=True), ForeignKey("steel_section_check_runs.id"), nullable=True)

    joint_type = Column(Enum(JointType, name="steel_joint_type", values_callable=lambda x: [e.value for e in x]), nullable=False)
    position_z_m = Column(Numeric(8, 4), nullable=False)   # cota respecto a rasante

    # Geometría
    nominal_overlap_mm = Column(Numeric(8, 2), nullable=True)   # solo telescópica
    min_overlap_mm = Column(Numeric(8, 2), nullable=True)
    taper_compatibility = Column(Boolean, nullable=True)

    # Rigidez equivalente (retroalimentación a F4)
    rotational_stiffness_nm_per_rad = Column(Numeric(14, 2), nullable=True)
    axial_stiffness_n_per_m = Column(Numeric(14, 2), nullable=True)
    stiffness_validated = Column(Boolean, nullable=False, default=False)  # por ensayo o modelo aprobado

    # Esfuerzos transmitidos
    N_kn = Column(Numeric(14, 4), nullable=True)
    Vy_kn = Column(Numeric(14, 4), nullable=True)
    Vz_kn = Column(Numeric(14, 4), nullable=True)
    T_knm = Column(Numeric(14, 6), nullable=True)
    My_knm = Column(Numeric(14, 6), nullable=True)
    Mz_knm = Column(Numeric(14, 6), nullable=True)

    # Verificaciones
    static_status = Column(Enum(SteelCheckStatus, name="steel_check_status"), nullable=True)
    fatigue_status = Column(Enum(SteelCheckStatus, name="steel_check_status"), nullable=True)
    slip_status = Column(Enum(SteelCheckStatus, name="steel_check_status"), nullable=True)
    within_validated_domain = Column(Boolean, nullable=False, default=True)
    error_code = Column(String(32), nullable=True)   # STEEL-DOMAIN-001 si telescópica fuera dominio

    design_sequence = Column(JSONB, nullable=True)   # 8 etapas de la secuencia canónica
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

class SteelOptimizationRun(Base):
    """
    Ejecución de optimización multiobjetivo de acero (coste, peso, CO₂).
    Genera un frente de Pareto de alternativas fabricables.
    """
    __tablename__ = "steel_optimization_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(SteelRunStatus, name="steel_run_status"), nullable=False, default=SteelRunStatus.PENDING)

    # Restricciones de la optimización
    utilization_limit = Column(Numeric(6, 4), nullable=False, default=1.0)
    max_piece_length_m = Column(Numeric(6, 2), nullable=False, default=12.0)
    min_diameter_mm = Column(Numeric(6, 2), nullable=False, default=60.0)
    available_grades = Column(JSONB, nullable=True)       # [S235, S275, S355]
    available_thicknesses_mm = Column(JSONB, nullable=True)  # lista de espesores disponibles
    allowed_tapers = Column(JSONB, nullable=True)          # [11, 13] (‰)

    # Resultados: frente de Pareto
    pareto_front = Column(JSONB, nullable=True)           # lista de candidatos en el frente
    n_candidates_generated = Column(Integer, nullable=True)
    n_candidates_filtered = Column(Integer, nullable=True)
    n_candidates_calculated = Column(Integer, nullable=True)
    n_pareto_solutions = Column(Integer, nullable=True)

    # Soluciones seleccionadas
    min_cost_candidate_id = Column(UUID(as_uuid=True), nullable=True)
    min_weight_candidate_id = Column(UUID(as_uuid=True), nullable=True)
    min_co2_candidate_id = Column(UUID(as_uuid=True), nullable=True)
    balanced_candidate_id = Column(UUID(as_uuid=True), nullable=True)

    input_hash = Column(String(64), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    candidates = relationship("SteelOptimizationCandidate", back_populates="optimization_run", lazy="dynamic")


class SteelOptimizationCandidate(Base):
    """
    Un candidato de diseño generado durante la optimización de acero.
    """
    __tablename__ = "steel_optimization_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    optimization_run_id = Column(UUID(as_uuid=True), ForeignKey("steel_optimization_runs.id", ondelete="CASCADE"), nullable=False)

    # Variables de diseño
    steel_grade = Column(Enum(SteelGrade, name="steel_grade"), nullable=False)
    subgrade = Column(Enum(SteelSubgrade, name="steel_subgrade"), nullable=True)
    thickness_profile = Column(JSONB, nullable=False)  # [{"z_from": 0, "z_to": 5, "t_mm": 4}]
    diameter_base_mm = Column(Numeric(8, 2), nullable=True)
    diameter_top_mm = Column(Numeric(8, 2), nullable=True)
    taper_per_mille = Column(Numeric(6, 3), nullable=True)
    n_faces = Column(Integer, nullable=True)
    segments = Column(JSONB, nullable=True)            # lista de tramos y uniones

    # Objetivos calculados
    total_mass_kg = Column(Numeric(10, 3), nullable=True)
    total_industrial_cost = Column(Numeric(12, 2), nullable=True)
    co2_total_kg = Column(Numeric(12, 4), nullable=True)

    # Verificaciones
    max_utilization = Column(Numeric(8, 6), nullable=True)
    governing_check = Column(String(64), nullable=True)
    all_checks_passed = Column(Boolean, nullable=True)
    fabricable = Column(Boolean, nullable=True)
    transportable = Column(Boolean, nullable=True)

    # Estado en la optimización
    pareto_dominated = Column(Boolean, nullable=False, default=False)
    objective = Column(Enum(OptimizationObjective, name="optimization_objective"), nullable=True)
    selected = Column(Boolean, nullable=False, default=False)

    check_run_id = Column(UUID(as_uuid=True), ForeignKey("steel_section_check_runs.id"), nullable=True)
    manufacturing_route_id = Column(UUID(as_uuid=True), ForeignKey("manufacturing_routes.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    optimization_run = relationship("SteelOptimizationRun", back_populates="candidates")


# ---------------------------------------------------------------------------
# Product family and validation evidence
# ---------------------------------------------------------------------------

class SteelProductFamily(Base):
    """
    Familia de producto: dominio de extensión de ensayos y cálculos.
    """
    __tablename__ = "product_families"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    # Dominio de la familia
    domain = Column(JSONB, nullable=False)   # variables y rangos: altura, conicidad, espesor, diámetro, puerta, material, proceso, soldadura, placa, brazo
    domain_version = Column(String(32), nullable=False, default="1.0")

    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    evidence = relationship("ValidationEvidence", back_populates="family", lazy="dynamic")


class ValidationEvidence(Base):
    """
    Evidencia de validación (ensayo, cálculo, FEM local, histórico, inspección)
    asociada a una familia de producto.
    """
    __tablename__ = "validation_evidences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    family_id = Column(UUID(as_uuid=True), ForeignKey("product_families.id"), nullable=True)

    evidence_type = Column(Enum(ValidationEvidenceType, name="validation_evidence_type"), nullable=False)
    reference = Column(String(256), nullable=False)
    version = Column(String(32), nullable=True)
    tolerance = Column(Numeric(8, 4), nullable=True)   # % de tolerancia de comparación
    result_summary = Column(Text, nullable=True)
    conservative_side = Column(Boolean, nullable=True)  # ¿en el lado seguro?

    # Metadatos del ensayo
    laboratory = Column(String(128), nullable=True)
    test_date = Column(DateTime(timezone=True), nullable=True)
    sample_description = Column(Text, nullable=True)
    loads_applied = Column(JSONB, nullable=True)
    failure_mode = Column(String(128), nullable=True)

    # Metadatos del cálculo/FEM
    solver_version = Column(String(32), nullable=True)
    norm_used = Column(String(64), nullable=True)
    inputs_hash = Column(String(64), nullable=True)

    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    family = relationship("SteelProductFamily", back_populates="evidence")


# ---------------------------------------------------------------------------
# Steel report snapshot
# ---------------------------------------------------------------------------

class SteelReportSnapshot(Base):
    """
    Instantánea inmutable de informe de acero. Tipos: CLIENT, ENGINEERING,
    INTERNAL, PRODUCTION, INSPECTION, CONFORMITY, COST, CO2.
    """
    __tablename__ = "steel_report_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    check_run_id = Column(UUID(as_uuid=True), ForeignKey("steel_section_check_runs.id"), nullable=True)

    report_type = Column(String(32), nullable=False)     # CLIENT, ENGINEERING, INTERNAL, PRODUCTION, INSPECTION, CONFORMITY, COST, CO2
    maturity_level = Column(Enum(MaturityLevel, name="maturity_level"), nullable=False)
    language = Column(String(8), nullable=False, default="es")

    content_hash = Column(String(64), nullable=False)    # hash del contenido del informe
    input_hashes = Column(JSONB, nullable=False)         # {geometry, material, rules, stress, run}
    all_evidences_present = Column(Boolean, nullable=True)
    all_approvals_present = Column(Boolean, nullable=True)

    storage_path = Column(String(512), nullable=True)    # ruta de almacenamiento del PDF/JSON
    format = Column(String(16), nullable=False, default="PDF")

    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Aprobaciones
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
