"""
Modelos DB · Fase 6 — Aluminio: Diseño, Verificación y Fabricación
Salvi Studio · Columns
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


# ── Enumeraciones ────────────────────────────────────────────────────────────

class AluminiumProductForm(str, enum.Enum):
    SHEET = "SHEET"
    STRIP = "STRIP"
    HOLLOW_EXTRUSION = "HOLLOW_EXTRUSION"
    SOLID_EXTRUSION = "SOLID_EXTRUSION"
    TUBE = "TUBE"
    FORGING = "FORGING"
    PLATE = "PLATE"
    OTHER_APPROVED = "OTHER_APPROVED"


class AluminiumRoute(str, enum.Enum):
    EN40 = "EN40"
    EN40_EXTENDED = "EN40_EXTENDED"
    SPECIAL = "SPECIAL"
    BLOCKED = "BLOCKED"


class HAZType(str, enum.Enum):
    LONGITUDINAL_SEAM = "LONGITUDINAL_SEAM"
    CIRCUMFERENTIAL = "CIRCUMFERENTIAL"
    FILLET_REINFORCEMENT = "FILLET_REINFORCEMENT"
    BASE_PLATE = "BASE_PLATE"
    FSW_NUGGET = "FSW_NUGGET"
    FSW_TMAZ = "FSW_TMAZ"
    FSW_HAZ = "FSW_HAZ"
    REPAIR = "REPAIR"


class WeldProcess(str, enum.Enum):
    MIG = "MIG"
    TIG = "TIG"
    FSW = "FSW"
    OTHER_APPROVED = "OTHER_APPROVED"


class JointGeometry(str, enum.Enum):
    BUTT = "BUTT"
    LAP = "LAP"
    FILLET = "FILLET"
    T_JOINT = "T_JOINT"
    CORNER = "CORNER"


class SectionRegionType(str, enum.Enum):
    BASE_METAL = "BASE_METAL"
    HAZ = "HAZ"
    TMAZ = "TMAZ"
    FSW_NUGGET = "FSW_NUGGET"
    WELD_METAL = "WELD_METAL"
    REINFORCEMENT = "REINFORCEMENT"
    HOLE = "HOLE"
    VOID = "VOID"


class PanelStatus(str, enum.Enum):
    EFFECTIVE = "EFFECTIVE"
    REDUCED = "REDUCED"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    BLOCKED = "BLOCKED"


class DoorReinforcementType(str, enum.Enum):
    PERIMETER_FRAME = "PERIMETER_FRAME"
    VERTICAL_PROFILES = "VERTICAL_PROFILES"
    INNER_PLATE = "INNER_PLATE"
    RING_SLEEVE = "RING_SLEEVE"
    REINFORCED_EXTRUSION = "REINFORCED_EXTRUSION"


class AluminiumSurfaceTreatment(str, enum.Enum):
    NATURAL = "NATURAL"
    ANODIZED = "ANODIZED"
    POWDER_COAT = "POWDER_COAT"
    LIQUID_PAINT = "LIQUID_PAINT"
    COMBINED_SYSTEM = "COMBINED_SYSTEM"
    GALVANIC_ISOLATION = "GALVANIC_ISOLATION"


class AluminiumJointType(str, enum.Enum):
    TELESCOPIC = "TELESCOPIC"
    FLANGED = "FLANGED"
    WELDED = "WELDED"
    SLEEVE = "SLEEVE"
    HYBRID_AL_STEEL = "HYBRID_AL_STEEL"


class AluminiumCheckType(str, enum.Enum):
    AXIAL = "AXIAL"
    BENDING_UNIAXIAL = "BENDING_UNIAXIAL"
    BENDING_BIAXIAL = "BENDING_BIAXIAL"
    SHEAR = "SHEAR"
    TORSION = "TORSION"
    INTERACTION = "INTERACTION"
    GLOBAL_BUCKLING = "GLOBAL_BUCKLING"
    DEFORMATION = "DEFORMATION"
    FATIGUE = "FATIGUE"
    WALL_SLENDERNESS = "WALL_SLENDERNESS"


class AluminiumCheckStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    WARNING = "WARNING"
    PENDING = "PENDING"


class MaterialStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    WITHDRAWN = "WITHDRAWN"
    SUPERSEDED = "SUPERSEDED"


class OptimizationObjective(str, enum.Enum):
    MIN_COST = "MIN_COST"
    MIN_WEIGHT = "MIN_WEIGHT"
    MIN_CO2 = "MIN_CO2"
    BALANCED = "BALANCED"


class AluminiumReportType(str, enum.Enum):
    CLIENT_SUMMARY = "CLIENT_SUMMARY"
    CLIENT_EXTENDED = "CLIENT_EXTENDED"
    INTERNAL_CALC = "INTERNAL_CALC"
    PRODUCTION = "PRODUCTION"
    QUALITY = "QUALITY"
    CONFORMITY = "CONFORMITY"
    COST_SUSTAINABILITY = "COST_SUSTAINABILITY"


# ── Tablas ORM ───────────────────────────────────────────────────────────────

class AluminiumAlloyVersion(Base):
    """Biblioteca versionada de aleaciones, temples y formas de producto."""
    __tablename__ = "aluminium_alloy_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alloy_designation = Column(String(32), nullable=False)          # "EN AW-5083"
    temper = Column(String(16), nullable=False)                     # "H111", "T6", etc.
    product_form = Column(
        Enum(AluminiumProductForm, name="aluminium_product_form"),
        nullable=False,
    )
    norm_reference = Column(String(64), nullable=False)             # "EN 485-2", etc.
    thickness_min_mm = Column(Float, nullable=False)
    thickness_max_mm = Column(Float, nullable=False)
    direction = Column(String(16), nullable=True)                   # "L", "LT", "ST"
    temperature_c = Column(Float, nullable=False, default=20.0)
    # Resistencias
    f0_mpa = Column(Float, nullable=False)                          # límite 0.2%
    fu_mpa = Column(Float, nullable=False)                          # resistencia última
    E_mpa = Column(Float, nullable=False, default=70000.0)
    G_mpa = Column(Float, nullable=False, default=26900.0)
    nu = Column(Float, nullable=False, default=0.33)
    rho_kg_m3 = Column(Float, nullable=False, default=2700.0)
    alpha_T_per_k = Column(Float, nullable=False, default=2.36e-5)
    # Factores HAZ (nulos si no soldable)
    haz_rho_yield = Column(Float, nullable=True)                    # ρ_HAZ fluencia
    haz_rho_ultimate = Column(Float, nullable=True)                 # ρ_HAZ rotura
    haz_rho_buckling = Column(Float, nullable=True)                 # ρ_HAZ pandeo
    haz_rho_fatigue = Column(Float, nullable=True)                  # ρ_HAZ fatiga
    haz_width_mm = Column(Float, nullable=True)                     # anchura HAZ
    # Conformado
    bend_limit_r_over_t_L = Column(Float, nullable=True)            # radio mín dir. L
    bend_limit_r_over_t_LT = Column(Float, nullable=True)           # radio mín dir. LT
    # Control
    status = Column(
        Enum(MaterialStatus, name="material_status"),
        nullable=False,
        default=MaterialStatus.DRAFT,
    )
    approved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    epd_factor_kg_co2_per_kg = Column(Float, nullable=True)
    price_per_kg_eur = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "alloy_designation", "temper", "product_form", "norm_reference",
            "thickness_min_mm", "thickness_max_mm", "direction", "temperature_c",
            name="uq_al_alloy_canonical_key",
        ),
    )


class HAZRuleVersion(Base):
    """Regla versionada de zona afectada térmicamente por proceso y aleación."""
    __tablename__ = "haz_rule_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alloy_designation = Column(String(32), nullable=False)
    temper = Column(String(16), nullable=False)
    product_form = Column(
        Enum(AluminiumProductForm, name="aluminium_product_form"),
        nullable=False,
    )
    process = Column(Enum(WeldProcess, name="aluminium_weld_process"), nullable=False)
    haz_type = Column(Enum(HAZType, name="haz_type"), nullable=False)
    thickness_min_mm = Column(Float, nullable=False)
    thickness_max_mm = Column(Float, nullable=False)
    # Geometría HAZ
    haz_width_mm = Column(Float, nullable=False)
    # Factores de reducción
    rho_yield = Column(Float, nullable=False)
    rho_ultimate = Column(Float, nullable=False)
    rho_buckling = Column(Float, nullable=True)
    rho_fatigue = Column(Float, nullable=True)
    # Trazabilidad
    norm_reference = Column(String(64), nullable=False)
    clause = Column(String(32), nullable=True)
    status = Column(
        Enum(MaterialStatus, name="material_status"),
        nullable=False,
        default=MaterialStatus.DRAFT,
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumNormativeRoute(Base):
    """Resultado del clasificador normativo de 7 pasos para aluminio."""
    __tablename__ = "aluminium_normative_routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    route = Column(Enum(AluminiumRoute, name="aluminium_route"), nullable=False)
    route_version = Column(String(16), nullable=False, default="1.0")
    # Resultados por paso
    step_1_norm_active = Column(Boolean, nullable=False)
    step_2_height_typology = Column(Boolean, nullable=False)
    step_3_alloy_in_library = Column(Boolean, nullable=False)
    step_4_domain_ok = Column(Boolean, nullable=False)
    step_5_checks_defined = Column(Boolean, nullable=False)
    step_6_rules_available = Column(Boolean, nullable=False)
    step_7_evidence_ok = Column(Boolean, nullable=False)
    # Trazabilidad
    decision_trace = Column(JSONB, nullable=False, default=list)
    active_rules = Column(JSONB, nullable=False, default=list)
    discarded_rules = Column(JSONB, nullable=False, default=list)
    exclusions = Column(JSONB, nullable=False, default=list)
    warnings = Column(JSONB, nullable=False, default=list)
    max_declaration_allowed = Column(String(64), nullable=True)
    input_hash = Column(String(64), nullable=False)
    height_nominal_m = Column(Float, nullable=False)
    has_catenary_cables = Column(Boolean, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumHAZMap(Base):
    """Mapa de regiones HAZ de una sección en una ejecución de verificación."""
    __tablename__ = "aluminium_haz_maps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    alloy_version_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_alloy_versions.id"), nullable=True)
    section_station_m = Column(Float, nullable=False)
    # Regiones como JSONB: [{haz_type, width_mm, rho_yield, rho_ultimate, side, process}]
    regions = Column(JSONB, nullable=False, default=list)
    has_overlapping_zones = Column(Boolean, nullable=False, default=False)
    overlap_treatment = Column(String(64), nullable=True)  # "WORST_CASE" o referencia a regla
    geometry_hash = Column(String(64), nullable=False)
    material_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumSectionRegion(Base):
    """Región geométrica de sección con material y propiedades asignadas."""
    __tablename__ = "aluminium_section_regions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    haz_map_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_haz_maps.id"), nullable=False)
    region_type = Column(
        Enum(SectionRegionType, name="section_region_type"),
        nullable=False,
    )
    area_m2 = Column(Float, nullable=False)
    centroid_y_m = Column(Float, nullable=False)
    centroid_z_m = Column(Float, nullable=False)
    Iy_m4 = Column(Float, nullable=True)
    Iz_m4 = Column(Float, nullable=True)
    # Propiedades de diseño aplicables
    f0_d_mpa = Column(Float, nullable=False)
    fu_d_mpa = Column(Float, nullable=False)
    E_mpa = Column(Float, nullable=False)
    rho_yield_applied = Column(Float, nullable=True)
    rho_ultimate_applied = Column(Float, nullable=True)
    gamma_M = Column(Float, nullable=False, default=1.1)
    notes = Column(Text, nullable=True)


class AluminiumWeldJoint(Base):
    """Junta de soldadura por arco o FSW con procedimiento, HAZ y fatiga."""
    __tablename__ = "aluminium_weld_joints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    joint_id_code = Column(String(32), nullable=False)
    process = Column(Enum(WeldProcess, name="aluminium_weld_process"), nullable=False)
    geometry = Column(Enum(JointGeometry, name="joint_geometry"), nullable=False)
    # Materiales
    alloy_1_designation = Column(String(32), nullable=False)
    temper_1 = Column(String(16), nullable=False)
    alloy_2_designation = Column(String(32), nullable=True)
    temper_2 = Column(String(16), nullable=True)
    thickness_mm = Column(Float, nullable=False)
    orientation_deg = Column(Float, nullable=True)
    # Procedimiento
    wps_pqr_reference = Column(String(64), nullable=True)
    fsw_procedure_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_fsw_procedures.id"), nullable=True)
    # HAZ
    haz_rule_id = Column(UUID(as_uuid=True), ForeignKey("haz_rule_versions.id"), nullable=True)
    # Resistencia
    throat_mm = Column(Float, nullable=True)
    effective_length_mm = Column(Float, nullable=True)
    # Fatiga
    fatigue_detail_category = Column(Float, nullable=True)   # MPa, curva EN 1999
    fatigue_detail_id = Column(String(32), nullable=True)
    end_condition = Column(String(32), nullable=True)
    # Inspección
    inspection_methods = Column(JSONB, nullable=False, default=list)  # ["VT","PT","RT"]
    inspection_percentage = Column(Float, nullable=False, default=100.0)
    # Resultados
    static_utilization = Column(Float, nullable=True)
    fatigue_damage = Column(Float, nullable=True)
    is_compliant = Column(Boolean, nullable=True)
    governing_case = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "joint_id_code", name="uq_al_weld_joint"),
    )


class AluminiumFSWProcedure(Base):
    """Procedimiento cualificado de Friction Stir Welding."""
    __tablename__ = "aluminium_fsw_procedures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    procedure_code = Column(String(32), nullable=False, unique=True)
    # Equipo y utillaje
    machine_model = Column(String(64), nullable=True)
    max_force_kn = Column(Float, nullable=True)
    backing_type = Column(String(32), nullable=True)
    # Herramienta
    tool_material = Column(String(32), nullable=True)
    shoulder_diameter_mm = Column(Float, nullable=True)
    pin_geometry = Column(String(32), nullable=True)
    # Ventana cualificada
    alloy_designation = Column(String(32), nullable=False)
    temper = Column(String(16), nullable=False)
    thickness_min_mm = Column(Float, nullable=False)
    thickness_max_mm = Column(Float, nullable=False)
    rotation_speed_min_rpm = Column(Float, nullable=True)
    rotation_speed_max_rpm = Column(Float, nullable=True)
    travel_speed_min_mm_per_min = Column(Float, nullable=True)
    travel_speed_max_mm_per_min = Column(Float, nullable=True)
    axial_force_min_kn = Column(Float, nullable=True)
    axial_force_max_kn = Column(Float, nullable=True)
    # Calidad
    nugget_properties = Column(JSONB, nullable=True)
    tmaz_properties = Column(JSONB, nullable=True)
    haz_width_mm = Column(Float, nullable=True)
    haz_rho_yield = Column(Float, nullable=True)
    haz_rho_ultimate = Column(Float, nullable=True)
    # Defectos y criterios
    defect_criteria = Column(JSONB, nullable=True)
    inspection_methods = Column(JSONB, nullable=False, default=list)
    status = Column(
        Enum(MaterialStatus, name="material_status"),
        nullable=False,
        default=MaterialStatus.DRAFT,
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumLocalBucklingPanel(Base):
    """Panel de pandeo local con iteración de sección efectiva."""
    __tablename__ = "aluminium_local_buckling_panels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    verification_run_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_verification_runs.id"), nullable=False)
    panel_index = Column(Integer, nullable=False)
    panel_description = Column(String(64), nullable=True)
    # Geometría
    width_gross_mm = Column(Float, nullable=False)
    thickness_eff_mm = Column(Float, nullable=False)
    curvature_radius_mm = Column(Float, nullable=True)
    support_condition = Column(String(32), nullable=False, default="SS")  # SS, fixed, free
    # Carga
    stress_distribution = Column(String(16), nullable=False, default="UNIFORM")
    sigma_max_mpa = Column(Float, nullable=False)
    sigma_min_mpa = Column(Float, nullable=True)
    psi = Column(Float, nullable=True)             # ratio sigma_min/sigma_max
    # Sección efectiva
    slenderness = Column(Float, nullable=True)
    reduction_factor = Column(Float, nullable=True)
    width_effective_mm = Column(Float, nullable=True)
    # Iteración
    n_iterations = Column(Integer, nullable=True)
    converged = Column(Boolean, nullable=True)
    iteration_history = Column(JSONB, nullable=True)
    status = Column(
        Enum(PanelStatus, name="panel_status"),
        nullable=False,
        default=PanelStatus.EFFECTIVE,
    )
    governing_rule = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)


class AluminiumVerificationRun(Base):
    """Ejecución de verificación de aluminio — inmutable, con hashes de trazabilidad."""
    __tablename__ = "aluminium_verification_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    normative_route_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_normative_routes.id"), nullable=True)
    structural_run_id = Column(UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id"), nullable=True)
    # Hashes de trazabilidad
    geometry_hash = Column(String(64), nullable=False)
    material_hash = Column(String(64), nullable=False)
    haz_hash = Column(String(64), nullable=False)
    rules_hash = Column(String(64), nullable=False)
    stress_hash = Column(String(64), nullable=False)
    run_hash = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=True, unique=True)
    engine_version = Column(String(16), nullable=False, default="1.0")
    # Parámetros
    gamma_M0 = Column(Float, nullable=False, default=1.0)
    gamma_M1 = Column(Float, nullable=False, default=1.0)
    gamma_M2 = Column(Float, nullable=False, default=1.25)
    utilization_limit = Column(Float, nullable=False, default=1.0)
    # Resultados globales
    overall_status = Column(
        Enum(AluminiumCheckStatus, name="aluminium_check_status"),
        nullable=False,
        default=AluminiumCheckStatus.PENDING,
    )
    max_utilization = Column(Float, nullable=True)
    governing_station_m = Column(Float, nullable=True)
    governing_combination = Column(String(64), nullable=True)
    governing_check_type = Column(
        Enum(AluminiumCheckType, name="aluminium_check_type"),
        nullable=True,
    )
    warnings = Column(JSONB, nullable=False, default=list)
    errors = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class AluminiumSectionCheck(Base):
    """Verificación individual por estación × combinación × tipo."""
    __tablename__ = "aluminium_section_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_verification_runs.id"), nullable=False)
    station_m = Column(Float, nullable=False)
    combination_id = Column(String(64), nullable=False)
    check_type = Column(
        Enum(AluminiumCheckType, name="aluminium_check_type"),
        nullable=False,
    )
    status = Column(
        Enum(AluminiumCheckStatus, name="aluminium_check_status"),
        nullable=False,
    )
    # Esfuerzos aplicados
    N_kn = Column(Float, nullable=True)
    Vy_kn = Column(Float, nullable=True)
    Vz_kn = Column(Float, nullable=True)
    My_knm = Column(Float, nullable=True)
    Mz_knm = Column(Float, nullable=True)
    T_knm = Column(Float, nullable=True)
    # Resistencias
    N_Rd_kn = Column(Float, nullable=True)
    Vpl_Rd_kn = Column(Float, nullable=True)
    Mc_Rd_knm = Column(Float, nullable=True)
    T_Rd_knm = Column(Float, nullable=True)
    # Utilización y trazabilidad
    utilization = Column(Float, nullable=True)
    governing_rule = Column(String(64), nullable=True)
    equation_trace = Column(JSONB, nullable=True)
    intermediate_values = Column(JSONB, nullable=True)
    note = Column(Text, nullable=True)


class AluminiumDoorReinforcement(Base):
    """Candidato de refuerzo de puerta de registro para aluminio."""
    __tablename__ = "aluminium_door_reinforcements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    reinforcement_type = Column(
        Enum(DoorReinforcementType, name="door_reinforcement_type"),
        nullable=False,
    )
    door_height_m = Column(Float, nullable=False)
    door_width_m = Column(Float, nullable=False)
    door_station_bottom_m = Column(Float, nullable=False)
    door_station_top_m = Column(Float, nullable=False)
    door_azimuth_deg = Column(Float, nullable=False, default=0.0)
    # Geometría del refuerzo
    reinforcement_geometry = Column(JSONB, nullable=False)
    alloy_designation = Column(String(32), nullable=False)
    temper = Column(String(16), nullable=False)
    # Sección con puerta
    net_A_m2 = Column(Float, nullable=True)
    net_Iy_m4 = Column(Float, nullable=True)
    net_J_m4 = Column(Float, nullable=True)
    # Verificación
    max_utilization = Column(Float, nullable=True)
    fatigue_damage = Column(Float, nullable=True)
    is_fabricable = Column(Boolean, nullable=True)
    is_compliant = Column(Boolean, nullable=True)
    # Economía
    extra_mass_kg = Column(Float, nullable=True)
    extra_cost_eur = Column(Float, nullable=True)
    extra_co2_kg = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumSurfaceSystem(Base):
    """Sistema de protección superficial para aluminio."""
    __tablename__ = "aluminium_surface_systems"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    treatment = Column(
        Enum(AluminiumSurfaceTreatment, name="aluminium_surface_treatment"),
        nullable=False,
    )
    corrosivity_category = Column(String(4), nullable=False)  # C1..C5, CX, Im1..Im3
    design_life_years = Column(Float, nullable=False)
    # Parámetros del sistema
    anodizing_thickness_um = Column(Float, nullable=True)
    sealing_type = Column(String(32), nullable=True)
    paint_system_layers = Column(JSONB, nullable=True)
    total_dft_um = Column(Float, nullable=True)
    # Verificación de vida útil
    life_adequate = Column(Boolean, nullable=True)
    life_range_min_years = Column(Float, nullable=True)
    life_range_max_years = Column(Float, nullable=True)
    # Aislamiento galvánico
    galvanic_pairs = Column(JSONB, nullable=True)
    galvanic_isolation_required = Column(Boolean, nullable=False, default=False)
    isolation_method = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumManufacturingRoute(Base):
    """Ruta de fabricación para columnas plegadas/extrusionadas de aluminio."""
    __tablename__ = "aluminium_manufacturing_routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    alloy_designation = Column(String(32), nullable=False)
    temper = Column(String(16), nullable=False)
    product_form = Column(
        Enum(AluminiumProductForm, name="aluminium_product_form"),
        nullable=False,
    )
    # Geometría de blank (plegada)
    blank_geometry = Column(JSONB, nullable=True)     # desarrollo, líneas de plegado, DXF layers
    folding_sequence = Column(JSONB, nullable=True)   # pasos, radios, útiles, tonelaje
    seam_azimuth_deg = Column(Float, nullable=True)
    seam_not_in_door = Column(Boolean, nullable=True)
    # Extrusión
    extrusion_die_id = Column(String(32), nullable=True)
    extrusion_die_cost_eur = Column(Float, nullable=True)
    is_existing_die = Column(Boolean, nullable=True)
    # BOM
    bom = Column(JSONB, nullable=False, default=list)
    total_mass_kg = Column(Float, nullable=True)
    nesting_efficiency = Column(Float, nullable=True)
    scrap_rate = Column(Float, nullable=True)
    # Proceso y costes
    process_operations = Column(JSONB, nullable=False, default=list)
    material_cost_eur = Column(Float, nullable=True)
    process_cost_eur = Column(Float, nullable=True)
    weld_cost_eur = Column(Float, nullable=True)
    surface_cost_eur = Column(Float, nullable=True)
    inspection_cost_eur = Column(Float, nullable=True)
    transport_cost_eur = Column(Float, nullable=True)
    total_cost_eur = Column(Float, nullable=True)
    total_co2_kg = Column(Float, nullable=True)
    # Restricciones
    max_piece_length_m = Column(Float, nullable=False, default=12.0)
    min_diameter_mm = Column(Float, nullable=False, default=60.0)
    is_fabricable = Column(Boolean, nullable=True)
    fabricability_issues = Column(JSONB, nullable=False, default=list)
    is_preliminary = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumJoint(Base):
    """Unión entre tramos de aluminio."""
    __tablename__ = "aluminium_joints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    joint_type = Column(
        Enum(AluminiumJointType, name="aluminium_joint_type"),
        nullable=False,
    )
    station_m = Column(Float, nullable=False)
    # Geometría
    overlap_length_mm = Column(Float, nullable=True)        # telescópica
    flange_plate_thickness_mm = Column(Float, nullable=True)  # embridada
    bolt_pattern = Column(JSONB, nullable=True)              # embridada
    # Compatibilidad galvánica
    is_aluminium_steel_interface = Column(Boolean, nullable=False, default=False)
    galvanic_isolation_detail = Column(JSONB, nullable=True)
    # Resultados
    moment_transfer_verified = Column(Boolean, nullable=True)
    shear_transfer_verified = Column(Boolean, nullable=True)
    torsion_transfer_verified = Column(Boolean, nullable=True)
    rotational_stiffness_knm_per_rad = Column(Float, nullable=True)
    fretting_risk = Column(Boolean, nullable=True)
    max_utilization = Column(Float, nullable=True)
    fatigue_damage = Column(Float, nullable=True)
    is_compliant = Column(Boolean, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumOptimizationRun(Base):
    """Ejecución de optimización Pareto multiobjetivo para aluminio."""
    __tablename__ = "aluminium_optimization_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    normative_route_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_normative_routes.id"), nullable=True)
    # Restricciones
    utilization_limit = Column(Float, nullable=False, default=1.0)
    max_piece_length_m = Column(Float, nullable=False, default=12.0)
    min_diameter_mm = Column(Float, nullable=False, default=60.0)
    # Resultados — IDs de candidatos destacados
    candidate_min_cost_id = Column(UUID(as_uuid=True), nullable=True)
    candidate_min_weight_id = Column(UUID(as_uuid=True), nullable=True)
    candidate_min_co2_id = Column(UUID(as_uuid=True), nullable=True)
    candidate_balanced_id = Column(UUID(as_uuid=True), nullable=True)
    n_candidates_total = Column(Integer, nullable=True)
    n_pareto_front = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AluminiumOptimizationCandidate(Base):
    """Candidato de diseño en el espacio de optimización."""
    __tablename__ = "aluminium_optimization_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_optimization_runs.id"), nullable=False)
    # Variables de diseño
    alloy_designation = Column(String(32), nullable=False)
    temper = Column(String(16), nullable=False)
    product_form = Column(
        Enum(AluminiumProductForm, name="aluminium_product_form"),
        nullable=False,
    )
    weld_process = Column(Enum(WeldProcess, name="aluminium_weld_process"), nullable=False)
    thickness_mm = Column(Float, nullable=False)
    diameter_base_mm = Column(Float, nullable=False)
    taper_ratio = Column(Float, nullable=False, default=11.0)  # mm/m
    n_segments = Column(Integer, nullable=False, default=1)
    # Objetivos
    total_cost_eur = Column(Float, nullable=False)
    total_mass_kg = Column(Float, nullable=False)
    total_co2_kg = Column(Float, nullable=False)
    # Restricciones de admisibilidad
    max_utilization = Column(Float, nullable=False)
    is_fabricable = Column(Boolean, nullable=False)
    is_transportable = Column(Boolean, nullable=False)
    is_pareto_dominated = Column(Boolean, nullable=False, default=False)
    objectives = Column(JSONB, nullable=False, default=list)
    notes = Column(Text, nullable=True)


class AluminiumReportSnapshot(Base):
    """Informe inmutable con hash de contenido para aluminio."""
    __tablename__ = "aluminium_report_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    verification_run_id = Column(UUID(as_uuid=True), ForeignKey("aluminium_verification_runs.id"), nullable=True)
    report_type = Column(
        Enum(AluminiumReportType, name="aluminium_report_type"),
        nullable=False,
    )
    content_hash = Column(String(64), nullable=False)
    input_hashes = Column(JSONB, nullable=False, default=dict)
    language = Column(String(8), nullable=False, default="es")
    generated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    includes_cost_data = Column(Boolean, nullable=False, default=False)
    all_evidences_present = Column(Boolean, nullable=False, default=False)
    all_approvals_present = Column(Boolean, nullable=False, default=False)
    content_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
