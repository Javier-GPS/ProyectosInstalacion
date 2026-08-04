"""
Salvi Studio · Columns — Fase 16: Catenarias y Alumbrado Suspendido
Modelos SQLAlchemy (sufijo 16).
"""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


# ── Enumeraciones ─────────────────────────────────────────────────────────────

class CableSystemState16(str, enum.Enum):
    DRAFT     = "DRAFT"
    VALIDATED = "VALIDATED"
    ANALYZED  = "ANALYZED"
    OPTIMIZED = "OPTIMIZED"
    RELEASED  = "RELEASED"


class CableDataType16(str, enum.Enum):
    CONFIRMED        = "CONFIRMED"
    IMPORTED         = "IMPORTED"
    CALCULATED       = "CALCULATED"
    ESTIMATED        = "ESTIMATED"
    CONSERVATIVE     = "CONSERVATIVE"
    PENDING          = "PENDING"
    CONFLICT         = "CONFLICT"
    MEASURED_AS_BUILT = "MEASURED_AS_BUILT"


class CableTypology16(str, enum.Enum):
    C1 = "C1"   # Vano simple entre dos apoyos
    C2 = "C2"   # Dos vanos con apoyo central
    C3 = "C3"   # Cable continuo con varios apoyos
    C4 = "C4"   # Vanos independientes sobre una columna
    C5 = "C5"   # Red radial hasta seis cables
    C6 = "C6"   # Cables a diferentes cotas
    C7 = "C7"   # Dos cables paralelos con luminaria compartida
    C8 = "C8"   # Cable portante y cable estabilizador


class TensioningMethod16(str, enum.Enum):
    FORCE               = "FORCE"
    SAG                 = "SAG"
    CUT_LENGTH          = "CUT_LENGTH"
    MIN_CLEARANCE       = "MIN_CLEARANCE"
    TENSOR_DISPLACEMENT = "TENSOR_DISPLACEMENT"
    AS_BUILT            = "AS_BUILT"


class CableAnalysisState16(str, enum.Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    CONVERGED = "CONVERGED"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"


class CouplingStrategy16(str, enum.Enum):
    MONOLITHIC       = "MONOLITHIC"
    PARTITIONED      = "PARTITIONED"
    STIFFNESS_EQUIV  = "STIFFNESS_EQUIV"
    FIXED_SUPPORT    = "FIXED_SUPPORT"


class AnchorType16(str, enum.Enum):
    COLUMN      = "COLUMN"
    FACADE      = "FACADE"
    INDEPENDENT = "INDEPENDENT"
    EXTERNAL    = "EXTERNAL"


# ── Tablas ────────────────────────────────────────────────────────────────────

class CableSystem16(Base):
    """Conjunto funcional completo de catenarias de una instalación."""
    __tablename__ = "cable_systems16"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id   = Column(UUID(as_uuid=True), nullable=False, index=True)
    name         = Column(String(200), nullable=False)
    description  = Column(Text)
    typology     = Column(String(4), nullable=False)          # C1-C8
    state        = Column(String(20), nullable=False, default="DRAFT")
    max_cables   = Column(Integer, nullable=False, default=6)  # límite dominio
    location_data = Column(JSONB)                               # zona viento/nieve/temperatura
    geometry_hash = Column(String(64))
    input_hash   = Column(String(64))
    meta         = Column(JSONB, default=dict)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(),
                          onupdate=func.now(), nullable=False)
    created_by   = Column(UUID(as_uuid=True))

    cable_lines   = relationship("CableLine16",    back_populates="system", cascade="all, delete-orphan")
    cable_anchors = relationship("CableAnchor16",  back_populates="system", cascade="all, delete-orphan")
    cable_states  = relationship("CableState16",   back_populates="system", cascade="all, delete-orphan")
    analysis_runs = relationship("CableAnalysisRun16", back_populates="system",
                                 cascade="all, delete-orphan")
    tensioning_plans = relationship("TensioningPlan16", back_populates="system",
                                    cascade="all, delete-orphan")
    as_builts    = relationship("CableAsBuilt16",  back_populates="system", cascade="all, delete-orphan")


class CableLine16(Base):
    """Cable físico continuo: material, sección y propiedades."""
    __tablename__ = "cable_lines16"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id   = Column(UUID(as_uuid=True), ForeignKey("cable_systems16.id",
                          ondelete="CASCADE"), nullable=False, index=True)
    code        = Column(String(50), nullable=False)
    material_id = Column(UUID(as_uuid=True))                   # ref biblioteca F01
    diameter_mm = Column(Float, nullable=False)
    area_mm2    = Column(Float)
    e_mpa       = Column(Float, nullable=False)                # módulo de Young
    alpha_k     = Column(Float, nullable=False, default=12e-6) # coef. dilatación 1/K
    mass_kg_m   = Column(Float, nullable=False)                # masa por metro lineal
    mbl_kn      = Column(Float, nullable=False)                # carga de rotura mínima
    data_quality = Column(String(20), nullable=False, default="ESTIMATED")
    meta        = Column(JSONB, default=dict)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    system = relationship("CableSystem16", back_populates="cable_lines")
    spans  = relationship("CableSpan16",   back_populates="line", cascade="all, delete-orphan")


class CableSpan16(Base):
    """Tramo de cable entre dos apoyos o desviadores."""
    __tablename__ = "cable_spans16"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_id      = Column(UUID(as_uuid=True), ForeignKey("cable_lines16.id",
                           ondelete="CASCADE"), nullable=False, index=True)
    span_index   = Column(Integer, nullable=False)             # orden en el cable
    anchor_a_id  = Column(UUID(as_uuid=True), ForeignKey("cable_anchors16.id"), nullable=False)
    anchor_b_id  = Column(UUID(as_uuid=True), ForeignKey("cable_anchors16.id"), nullable=False)
    length_m     = Column(Float, nullable=False)               # longitud horizontal
    height_diff_m = Column(Float, nullable=False, default=0.0) # diferencia de cotas A-B
    distributed_load_n_m = Column(Float, nullable=False)       # carga repartida total
    point_loads  = Column(JSONB, default=list)                 # [{pos_m, force_n, label}]
    sag_m        = Column(Float)                               # resultado: flecha máxima
    tension_h_kn = Column(Float)                               # resultado: tensión horizontal
    clearance_min_m = Column(Float)                            # resultado: gálibo mínimo
    data_quality = Column(String(20), nullable=False, default="ESTIMATED")
    meta         = Column(JSONB, default=dict)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    line     = relationship("CableLine16",  back_populates="spans")
    anchor_a = relationship("CableAnchor16", foreign_keys=[anchor_a_id])
    anchor_b = relationship("CableAnchor16", foreign_keys=[anchor_b_id])
    suspended_items = relationship("SuspendedItem16", back_populates="span",
                                   cascade="all, delete-orphan")


class CableAnchor16(Base):
    """Punto de anclaje 3D: columna, fachada, estructura independiente o exterior."""
    __tablename__ = "cable_anchors16"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id    = Column(UUID(as_uuid=True), ForeignKey("cable_systems16.id",
                           ondelete="CASCADE"), nullable=False, index=True)
    anchor_type  = Column(String(15), nullable=False)          # COLUMN, FACADE, INDEPENDENT, EXTERNAL
    structure_id = Column(UUID(as_uuid=True))                  # columna/fachada de referencia
    x_m          = Column(Float, nullable=False)
    y_m          = Column(Float, nullable=False)
    z_m          = Column(Float, nullable=False)               # cota de fijación
    stiffness_kn_m = Column(Float)                             # rigidez equivalente soporte
    cables_attached = Column(Integer, nullable=False, default=0)  # cables incidentes ≤6
    reaction_fx_kn = Column(Float)                             # resultado: reacción X
    reaction_fy_kn = Column(Float)                             # resultado: reacción Y
    reaction_fz_kn = Column(Float)                             # resultado: reacción Z
    moment_mx_knm  = Column(Float)                             # resultado: momento X
    moment_my_knm  = Column(Float)                             # resultado: momento Y
    moment_mz_knm  = Column(Float)                             # resultado: momento Z
    data_quality   = Column(String(20), nullable=False, default="ESTIMATED")
    meta           = Column(JSONB, default=dict)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    system = relationship("CableSystem16", back_populates="cable_anchors")


class SuspendedItem16(Base):
    """Luminaria o accesorio suspendido del cable."""
    __tablename__ = "suspended_items16"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    span_id     = Column(UUID(as_uuid=True), ForeignKey("cable_spans16.id",
                          ondelete="CASCADE"), nullable=False, index=True)
    label       = Column(String(100), nullable=False)
    item_type   = Column(String(30), nullable=False, default="LUMINAIRE")  # LUMINAIRE, ACCESSORY
    position_m  = Column(Float, nullable=False)                # posición desde anchor_a
    mass_kg     = Column(Float, nullable=False)
    wind_area_m2 = Column(Float, nullable=False, default=0.0)  # área frontal al viento
    cd          = Column(Float, nullable=False, default=1.2)   # coef. arrastre
    luminaire_id = Column(UUID(as_uuid=True))                  # ref catálogo F12
    data_quality = Column(String(20), nullable=False, default="ESTIMATED")
    meta        = Column(JSONB, default=dict)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    span = relationship("CableSpan16", back_populates="suspended_items")


class TensioningPlan16(Base):
    """Plan de tensado: método, objetivo y secuencia de operaciones."""
    __tablename__ = "tensioning_plans16"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id      = Column(UUID(as_uuid=True), ForeignKey("cable_systems16.id",
                            ondelete="CASCADE"), nullable=False, index=True)
    method         = Column(String(25), nullable=False)        # FORCE, SAG, CUT_LENGTH, …
    target_value   = Column(Float, nullable=False)             # fuerza [kN] o flecha [m]
    target_unit    = Column(String(5), nullable=False, default="kN")
    tolerance_pct  = Column(Float, nullable=False, default=2.0)
    t_install_c    = Column(Float, nullable=False, default=15.0)  # temperatura instalación °C
    tensor_stroke_mm = Column(Float)                           # carrera de tensor disponible
    sequence       = Column(JSONB, default=list)               # [{step, action, check}]
    cut_length_m   = Column(Float)                             # longitud de corte calculada
    approved       = Column(Boolean, nullable=False, default=False)
    meta           = Column(JSONB, default=dict)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    system = relationship("CableSystem16", back_populates="tensioning_plans")


class CableState16(Base):
    """Estado de carga del sistema: temperatura + acciones + simultaneidad."""
    __tablename__ = "cable_states16"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id       = Column(UUID(as_uuid=True), ForeignKey("cable_systems16.id",
                             ondelete="CASCADE"), nullable=False, index=True)
    label           = Column(String(100), nullable=False)      # ELU_VIENTO, ELS_NORMAL, etc.
    combination_type = Column(String(10), nullable=False, default="ELS")  # ELU / ELS / ELS_FREC / ACC
    temperature_c   = Column(Float, nullable=False)
    wind_speed_ms   = Column(Float, nullable=False, default=0.0)
    wind_angle_deg  = Column(Float, nullable=False, default=0.0)
    ice_load_n_m    = Column(Float, nullable=False, default=0.0)
    snow_load_kpa   = Column(Float, nullable=False, default=0.0)
    accidental_code = Column(String(5))                        # A1-A8
    accidental_data = Column(JSONB, default=dict)
    is_governing    = Column(Boolean, nullable=False, default=False)
    meta            = Column(JSONB, default=dict)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    system = relationship("CableSystem16", back_populates="cable_states")
    analysis_runs = relationship("CableAnalysisRun16", back_populates="state")


class CableAnalysisRun16(Base):
    """Ejecución del solver: parámetros, convergencia, hashes."""
    __tablename__ = "cable_analysis_runs16"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id       = Column(UUID(as_uuid=True), ForeignKey("cable_systems16.id",
                             ondelete="CASCADE"), nullable=False, index=True)
    state_id        = Column(UUID(as_uuid=True), ForeignKey("cable_states16.id"), index=True)
    solver_version  = Column(String(30), nullable=False, default="newton_raphson_v1")
    coupling_strategy = Column(String(20), nullable=False, default="PARTITIONED")
    max_iterations  = Column(Integer, nullable=False, default=200)
    tol_residual    = Column(Float, nullable=False, default=1e-6)
    tol_displacement = Column(Float, nullable=False, default=1e-7)
    tol_reaction    = Column(Float, nullable=False, default=1e-5)
    iterations_used = Column(Integer)
    residual_final  = Column(Float)
    displacement_final = Column(Float)
    converged       = Column(Boolean)
    run_state       = Column(String(15), nullable=False, default="PENDING")
    error_code      = Column(String(20))
    error_detail    = Column(Text)
    input_hash      = Column(String(64))
    output_hash     = Column(String(64))
    duration_s      = Column(Float)
    meta            = Column(JSONB, default=dict)
    started_at      = Column(DateTime(timezone=True))
    finished_at     = Column(DateTime(timezone=True))
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    system  = relationship("CableSystem16", back_populates="analysis_runs")
    state   = relationship("CableState16",  back_populates="analysis_runs")
    results = relationship("CableResult16", back_populates="run", cascade="all, delete-orphan")


class CableResult16(Base):
    """Resultados del solver: tensiones, flechas, reacciones, verificaciones."""
    __tablename__ = "cable_results16"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id          = Column(UUID(as_uuid=True), ForeignKey("cable_analysis_runs16.id",
                             ondelete="CASCADE"), nullable=False, index=True)
    span_id         = Column(UUID(as_uuid=True), ForeignKey("cable_spans16.id"), index=True)
    anchor_id       = Column(UUID(as_uuid=True), ForeignKey("cable_anchors16.id"), index=True)
    # Resultados de tramo
    tension_h_kn    = Column(Float)
    tension_max_kn  = Column(Float)
    sag_m           = Column(Float)
    clearance_min_m = Column(Float)
    cable_length_m  = Column(Float)
    # Resultados de anclaje (reacciones vectoriales)
    reaction_fx_kn  = Column(Float)
    reaction_fy_kn  = Column(Float)
    reaction_fz_kn  = Column(Float)
    moment_mx_knm   = Column(Float)
    moment_my_knm   = Column(Float)
    moment_mz_knm   = Column(Float)
    # Verificaciones
    utilization_strength = Column(Float)  # T_max / MBL_design
    utilization_clearance = Column(Float)  # (clearance_req - clearance_min) / clearance_req
    checks_passed   = Column(Boolean)
    error_codes     = Column(JSONB, default=list)  # [CAB-xxx-yyy, ...]
    detail          = Column(JSONB, default=dict)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run    = relationship("CableAnalysisRun16", back_populates="results")


class CableAsBuilt16(Base):
    """Mediciones reales post-instalación: flecha, tensión, gálibo."""
    __tablename__ = "cable_as_builts16"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_id       = Column(UUID(as_uuid=True), ForeignKey("cable_systems16.id",
                             ondelete="CASCADE"), nullable=False, index=True)
    span_id         = Column(UUID(as_uuid=True), ForeignKey("cable_spans16.id"), index=True)
    measured_at     = Column(DateTime(timezone=True), nullable=False)
    technician      = Column(String(100), nullable=False)
    t_measure_c     = Column(Float, nullable=False)            # temperatura durante medición
    method          = Column(String(30), nullable=False)       # LASER, TAPE, PHOTOGRAMMETRY, etc.
    sag_measured_m  = Column(Float)
    tension_measured_kn = Column(Float)
    clearance_measured_m = Column(Float)
    uncertainty_m   = Column(Float)                            # incertidumbre combinada
    deviation_from_plan_pct = Column(Float)                    # desviación del plan de tensado
    accepted        = Column(Boolean)
    comments        = Column(Text)
    evidence        = Column(JSONB, default=dict)              # {photo_ids, report_id}
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    system = relationship("CableSystem16", back_populates="as_builts")
