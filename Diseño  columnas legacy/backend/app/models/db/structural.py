"""
Salvi Studio · Columns — Modelos de base de datos Fase 4: Motor Estructural Común
Entidades para el modelo 3D de barras, análisis, resultados y envolventes.
"""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────────

class ElementType(str, enum.Enum):
    BEAM3D_VAR = "BEAM3D_VAR"       # Fuste/brazo sección variable (Timoshenko)
    BEAM3D_CONST = "BEAM3D_CONST"   # Tramo prismático (6 DOF)
    RIGID_LINK = "RIGID_LINK"       # Offset rígido, nudo maestro
    SPRING6 = "SPRING6"             # Resorte 6×6 (apoyo elástico)
    MASS6 = "MASS6"                 # Masa concentrada con tensor inercia
    RELEASE = "RELEASE"             # Articulación/liberación explícita


class AnalysisOrder(str, enum.Enum):
    FIRST_ORDER = "FIRST_ORDER"
    SECOND_ORDER = "SECOND_ORDER"   # P-Delta (y P-delta si procede)


class MeshProfile(str, enum.Enum):
    FAST = "FAST"               # L/20 — exploración comercial
    STANDARD = "STANDARD"       # L/40 — uso habitual
    PRECISE = "PRECISE"         # L/80 — diseños límite
    VALIDATION = "VALIDATION"   # L/160 o adaptativo — golden cases


class ShearFormulation(str, enum.Enum):
    EULER_BERNOULLI = "EULER_BERNOULLI"
    TIMOSHENKO = "TIMOSHENKO"


class MassModel(str, enum.Enum):
    LUMPED = "LUMPED"
    CONSISTENT = "CONSISTENT"


class StructuralAnalysisType(str, enum.Enum):
    LINEAR = "LINEAR"
    SECOND_ORDER = "SECOND_ORDER"
    BUCKLING = "BUCKLING"
    MODAL = "MODAL"
    SEISMIC_SPECTRAL = "SEISMIC_SPECTRAL"


class StructuralRunStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    SOLVING = "SOLVING"
    POSTPROCESSING = "POSTPROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SupportType(str, enum.Enum):
    IDEAL_FIXED = "IDEAL_FIXED"
    ELASTIC = "ELASTIC"
    DISTRIBUTED_SPRINGS = "DISTRIBUTED_SPRINGS"
    PINNED = "PINNED"
    GUIDED = "GUIDED"
    TEMPORARY = "TEMPORARY"


class StructuralPropertySet(str, enum.Enum):
    GROSS = "GROSS"
    NET = "NET"
    CRACKED = "CRACKED"
    HAZ = "HAZ"
    DOOR = "DOOR"
    EFFECTIVE = "EFFECTIVE"


class StructuralModelStatus(str, enum.Enum):
    BUILDING = "BUILDING"
    BUILT = "BUILT"
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"


class StructuralDiagnosticSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"   # Bloquea liberación de resultados


class EnvelopeScope(str, enum.Enum):
    BY_STATION = "BY_STATION"
    BY_COMPONENT = "BY_COMPONENT"
    BY_CONNECTION = "BY_CONNECTION"
    BY_PROJECT = "BY_PROJECT"
    BY_DIRECTION = "BY_DIRECTION"


class StructuralLoadType(str, enum.Enum):
    NODAL = "NODAL"
    DISTRIBUTED = "DISTRIBUTED"
    THERMAL = "THERMAL"
    INERTIAL = "INERTIAL"
    IMPOSED_DEFORMATION = "IMPOSED_DEFORMATION"
    PRESTRESS = "PRESTRESS"


# ── Modelos de datos ───────────────────────────────────────────────────────────

class StructuralModel(Base):
    """
    Grafo estructural completo construido a partir de los contratos de F2+F3.
    Invalidado si cambian: geometría estructural, propiedades elásticas o vínculos.
    """
    __tablename__ = "structural_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revisions.id", ondelete="RESTRICT"), nullable=False,
    )
    action_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_runs.id", ondelete="SET NULL"), nullable=True,
    )

    # Versión y trazabilidad
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="4.0.0")
    structural_model_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    geometry_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action_run_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False, default="4.0.0")

    status: Mapped[StructuralModelStatus] = mapped_column(
        Enum(StructuralModelStatus, name="structural_model_status"),
        nullable=False, default=StructuralModelStatus.BUILDING,
    )
    property_set: Mapped[StructuralPropertySet] = mapped_column(
        Enum(StructuralPropertySet, name="structural_property_set"),
        nullable=False, default=StructuralPropertySet.GROSS,
    )

    # Configuración de análisis por defecto
    mesh_profile: Mapped[MeshProfile] = mapped_column(
        Enum(MeshProfile, name="mesh_profile"), nullable=False, default=MeshProfile.STANDARD,
    )
    shear_formulation: Mapped[ShearFormulation] = mapped_column(
        Enum(ShearFormulation, name="shear_formulation"),
        nullable=False, default=ShearFormulation.TIMOSHENKO,
    )
    mass_model: Mapped[MassModel] = mapped_column(
        Enum(MassModel, name="mass_model"), nullable=False, default=MassModel.CONSISTENT,
    )
    default_analysis_order: Mapped[AnalysisOrder] = mapped_column(
        Enum(AnalysisOrder, name="analysis_order"),
        nullable=False, default=AnalysisOrder.SECOND_ORDER,
    )
    modal_modes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Estadísticas (populadas tras construcción)
    node_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    element_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dof_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    station_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    built_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    build_time_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    build_log_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relaciones
    nodes: Mapped[list["StructuralNode"]] = relationship(
        back_populates="model", cascade="all, delete-orphan",
    )
    elements: Mapped[list["StructuralElement"]] = relationship(
        back_populates="model", cascade="all, delete-orphan",
    )
    supports: Mapped[list["SupportCondition"]] = relationship(
        back_populates="model", cascade="all, delete-orphan",
    )
    masses: Mapped[list["MassObject"]] = relationship(
        back_populates="model", cascade="all, delete-orphan",
    )
    analysis_runs: Mapped[list["StructuralAnalysisRun"]] = relationship(
        back_populates="model",
    )
    diagnostics: Mapped[list["StructuralDiagnosticEvent"]] = relationship(
        back_populates="model", cascade="all, delete-orphan",
    )


class StructuralNode(Base):
    """
    Nodo del grafo estructural. Conserva referencia al componente físico de origen
    para navegación bidireccional geometría ↔ resultado.
    """
    __tablename__ = "structural_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False,
    )

    x_m: Mapped[float] = mapped_column(Float, nullable=False)
    y_m: Mapped[float] = mapped_column(Float, nullable=False)
    z_m: Mapped[float] = mapped_column(Float, nullable=False)

    # DOF activos: [UX, UY, UZ, RX, RY, RZ] — lista de 6 bools
    dof_active_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=lambda: [True, True, True, True, True, True],
    )

    # Origen físico (F2)
    component_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    component_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Sistema de ejes locales (matriz 3×3 en JSON) — None = ejes globales
    local_axes_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    is_master_node: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_mandatory_station: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    model: Mapped["StructuralModel"] = relationship(back_populates="nodes")
    nodal_results: Mapped[list["NodalResult"]] = relationship(back_populates="node")


class StructuralElement(Base):
    """
    Elemento de barra del grafo estructural.
    Tipos: BEAM3D_VAR, BEAM3D_CONST, RIGID_LINK, SPRING6, MASS6, RELEASE.
    """
    __tablename__ = "structural_elements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False,
    )
    node_i_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False,
    )
    node_j_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=True,
    )

    element_type: Mapped[ElementType] = mapped_column(
        Enum(ElementType, name="element_type"), nullable=False,
    )
    element_order: Mapped[int] = mapped_column(Integer, nullable=False)
    length_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roll_angle_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Propiedades de sección en estaciones internas
    # [{xi, A_m2, Iy_m4, Iz_m4, Iyz_m4, J_m4, Ay_m2, Az_m2, perimeter_m, ...}]
    section_stations_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)

    # Propiedades del material elástico (E, G, rho, alphaT)
    material_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        default=lambda: {"E_Pa": None, "G_Pa": None, "rho_kg_m3": None, "alpha_T_1_K": None},
    )

    # Para SPRING6: matriz 6×6 de rigidez
    stiffness_matrix_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Para RELEASE: DOF liberados por extremo [UX,UY,UZ,RX,RY,RZ]
    releases_i_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    releases_j_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Para RIGID_LINK: vector offset {dx, dy, dz}
    offset_vector_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Origen físico (F2)
    component_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    component_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    model: Mapped["StructuralModel"] = relationship(back_populates="elements")
    section_results: Mapped[list["SectionResult"]] = relationship(back_populates="element")


class SupportCondition(Base):
    """
    Condición de apoyo en un nodo.
    Valida: simetría, unidades, rango y semidefinición positiva de la matriz 6×6.
    """
    __tablename__ = "support_conditions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False,
    )

    support_type: Mapped[SupportType] = mapped_column(
        Enum(SupportType, name="support_type"), nullable=False,
    )

    # DOF restringidos para IDEAL_FIXED/PINNED/GUIDED
    constrained_dofs_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Para ELASTIC: matriz simétrica 6×6 (N/m, N/rad, N·m/m, N·m/rad)
    stiffness_matrix_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Para DISTRIBUTED_SPRINGS: {kx_N_m2, ky_N_m2, kz_N_m2} por metro de longitud empotrada
    distributed_springs_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    model: Mapped["StructuralModel"] = relationship(back_populates="supports")


class MassObject(Base):
    """
    Masa concentrada con CG y tensor de inercia.
    Representa luminarias, brazos, paneles solares u otros equipos.
    """
    __tablename__ = "mass_objects"
    __table_args__ = (
        CheckConstraint("mass_kg >= 0", name="ck_mass_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False,
    )

    mass_kg: Mapped[float] = mapped_column(Float, nullable=False)
    cg_global_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=lambda: {"x_m": 0.0, "y_m": 0.0, "z_m": 0.0},
    )
    # {Ixx, Iyy, Izz, Ixy, Ixz, Iyz} en kg·m²
    inertia_tensor_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    component_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    component_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    include_in_self_weight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    model: Mapped["StructuralModel"] = relationship(back_populates="masses")


class StructuralLoadVector(Base):
    """
    Carga aplicada al modelo, asociada a un caso de Fase 3.
    Conserva: vector original + transformación + vector aplicado (trazabilidad completa).
    """
    __tablename__ = "structural_load_vectors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False,
    )
    analysis_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=True,
    )
    load_case_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    load_type: Mapped[StructuralLoadType] = mapped_column(
        Enum(StructuralLoadType, name="structural_load_type"), nullable=False,
    )
    target_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_element_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Vectores [Fx, Fy, Fz, Mx, My, Mz] en N y N·m
    original_vector_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    transform_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    applied_vector_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Para cargas distribuidas: estación inicio/fin (coordenada global z)
    station_start_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    station_end_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Para cargas térmicas
    delta_t_uniform_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_t_gradient_k_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class StructuralAnalysisRun(Base):
    """
    Ejecución de análisis estructural. Inmutable tras completarse.
    Estado: QUEUED → PREPARING → SOLVING → POSTPROCESSING → COMPLETED / FAILED / CANCELLED
    """
    __tablename__ = "structural_analysis_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_struct_run_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_models.id", ondelete="RESTRICT"), nullable=False,
    )

    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    structural_model_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    analysis_input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    solver_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False, default="4.0.0")

    # Configuración de la ejecución
    analysis_types_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=lambda: ["LINEAR", "SECOND_ORDER"],
    )
    analysis_order: Mapped[AnalysisOrder] = mapped_column(
        Enum(AnalysisOrder, name="analysis_order"), nullable=False, default=AnalysisOrder.SECOND_ORDER,
    )
    mesh_profile: Mapped[MeshProfile] = mapped_column(
        Enum(MeshProfile, name="mesh_profile"), nullable=False, default=MeshProfile.STANDARD,
    )
    shear_formulation: Mapped[ShearFormulation] = mapped_column(
        Enum(ShearFormulation, name="shear_formulation"),
        nullable=False, default=ShearFormulation.TIMOSHENKO,
    )
    mass_model: Mapped[MassModel] = mapped_column(
        Enum(MassModel, name="mass_model"), nullable=False, default=MassModel.CONSISTENT,
    )
    modal_modes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    buckling_modes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Tolerancias Newton-Raphson
    nl_tol_residual: Mapped[float] = mapped_column(Float, nullable=False, default=1e-6)
    nl_tol_displacement: Mapped[float] = mapped_column(Float, nullable=False, default=1e-6)
    nl_max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    status: Mapped[StructuralRunStatus] = mapped_column(
        Enum(StructuralRunStatus, name="structural_run_status"),
        nullable=False, default=StructuralRunStatus.QUEUED,
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Tiempos (segundos)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    preprocess_time_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assembly_time_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    factorization_time_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    solve_time_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    postprocess_time_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Métricas del sistema (observabilidad)
    system_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nonzeros: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    condition_number: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nl_iterations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nl_residual_final: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relaciones
    model: Mapped["StructuralModel"] = relationship(back_populates="analysis_runs")
    nodal_results: Mapped[list["NodalResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
    )
    section_results: Mapped[list["SectionResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
    )
    modal_results: Mapped[list["ModalResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
    )
    buckling_results: Mapped[list["BucklingResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
    )
    envelopes: Mapped[list["ResultEnvelope"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
    )


class NodalResult(Base):
    """
    Desplazamientos, giros y reacciones en un nodo por caso de análisis.
    """
    __tablename__ = "nodal_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False,
    )
    load_case_ref: Mapped[str] = mapped_column(String(100), nullable=False)

    # Desplazamientos (m) y giros (rad)
    ux_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uy_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uz_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rx_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ry_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rz_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Reacciones (N, N·m) — solo para nodos de apoyo
    rx_n: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ry_n: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rz_n: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mrx_nm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mry_nm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mrz_nm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Derivados
    u_horizontal_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    run: Mapped["StructuralAnalysisRun"] = relationship(back_populates="nodal_results")
    node: Mapped["StructuralNode"] = relationship(back_populates="nodal_results")


class SectionResult(Base):
    """
    Esfuerzos internos en una estación de un elemento, por caso de análisis.
    """
    __tablename__ = "section_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_elements.id", ondelete="RESTRICT"), nullable=False,
    )
    load_case_ref: Mapped[str] = mapped_column(String(100), nullable=False)

    xi: Mapped[float] = mapped_column(Float, nullable=False)          # 0..1 normalizado
    z_global_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Esfuerzos internos (ejes locales del elemento)
    n_n: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)    # Axil (N)
    vy_n: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)   # Cortante Y (N)
    vz_n: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)   # Cortante Z (N)
    t_nm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)   # Torsor (N·m)
    my_nm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # Momento Y (N·m)
    mz_nm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # Momento Z (N·m)

    curvature_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    curvature_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    run: Mapped["StructuralAnalysisRun"] = relationship(back_populates="section_results")
    element: Mapped["StructuralElement"] = relationship(back_populates="section_results")


class ModalResult(Base):
    """
    Resultado de análisis modal: frecuencias, formas y masas participantes.
    Un registro por modo.
    """
    __tablename__ = "modal_results"
    __table_args__ = (
        CheckConstraint("frequency_hz > 0", name="ck_modal_freq_pos"),
        CheckConstraint("mode_number >= 1", name="ck_modal_mode_pos"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )

    mode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency_hz: Mapped[float] = mapped_column(Float, nullable=False)
    period_s: Mapped[float] = mapped_column(Float, nullable=False)

    eff_mass_x_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eff_mass_y_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eff_mass_z_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    participation_x_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    participation_y_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    participation_z_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    modal_shape_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    mode_description: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    run: Mapped["StructuralAnalysisRun"] = relationship(back_populates="modal_results")


class BucklingResult(Base):
    """
    Resultado de análisis de estabilidad elástica.
    Factor crítico ≠ capacidad resistente normativa.
    """
    __tablename__ = "buckling_results"
    __table_args__ = (
        CheckConstraint("critical_factor > 0", name="ck_buckling_factor_pos"),
        CheckConstraint("mode_number >= 1", name="ck_buckling_mode_pos"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )
    load_case_ref: Mapped[str] = mapped_column(String(100), nullable=False)

    mode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_factor: Mapped[float] = mapped_column(Float, nullable=False)
    buckling_shape_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    critical_element_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    run: Mapped["StructuralAnalysisRun"] = relationship(back_populates="buckling_results")


class ResultEnvelope(Base):
    """
    Envolvente de resultados con procedencia completa.
    Conserva: id ejecución, caso, combinación, signo, dirección, estación, componente.
    """
    __tablename__ = "result_envelopes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False,
    )

    scope: Mapped[EnvelopeScope] = mapped_column(
        Enum(EnvelopeScope, name="envelope_scope"), nullable=False,
    )
    quantity: Mapped[str] = mapped_column(String(30), nullable=False)   # e.g. "My_nm", "ux_m"
    sign: Mapped[str] = mapped_column(String(4), nullable=False)        # "max" | "min"
    value: Mapped[float] = mapped_column(Float, nullable=False)

    # Procedencia completa
    load_case_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    combination_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    wind_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    station_xi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    element_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    node_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    governing_context_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    run: Mapped["StructuralAnalysisRun"] = relationship(back_populates="envelopes")


class StructuralDiagnosticEvent(Base):
    """
    Evento de diagnóstico del motor: errores de conectividad, mal condicionamiento,
    DOF sin rigidez, modos rígidos inesperados, etc.
    """
    __tablename__ = "structural_diagnostic_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=True,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=True,
    )

    severity: Mapped[StructuralDiagnosticSeverity] = mapped_column(
        Enum(StructuralDiagnosticSeverity, name="structural_diagnostic_severity"), nullable=False,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metric_unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    model: Mapped[Optional["StructuralModel"]] = relationship(back_populates="diagnostics")


class StructuralExport(Base):
    """
    Exportación de modelo neutro para contraste con software externo.
    """
    __tablename__ = "structural_exports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structural_analysis_runs.id", ondelete="RESTRICT"), nullable=False,
    )

    format: Mapped[str] = mapped_column(String(20), nullable=False)  # "json", "csv", "nastran"
    structural_model_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
