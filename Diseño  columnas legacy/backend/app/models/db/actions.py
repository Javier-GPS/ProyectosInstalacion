"""
Salvi Studio · Columns — Modelos DB Fase 3: Acciones, Ubicación y Combinaciones
v0.2

Entidades: Location, GeoParameter, NormativeActionRule, AerodynamicProperty,
ActionComponent, CableAction, LoadCase, CombinationTemplate, CombinationInstance,
SpatialLoad, MassItem, ActionRun, ActionDiagnostic, UserOverride.

Principios: determinismo (ACT-P-001), inmutabilidad de ejecuciones publicadas (DAT-301),
unidades SI internas (ACT-FLOW-003).
"""
import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey,
    Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin
from app.models.db.base_types import UUIDPk, ShortStr, CodeStr


# ── Enums ──────────────────────────────────────────────────────────────────────

class EnvironmentType(str, enum.Enum):
    SEA = "sea"
    RURAL = "rural"
    SUBURBAN = "suburban"
    URBAN = "urban"
    URBAN_DENSE = "urban_dense"


class GeoParameterType(str, enum.Enum):
    WIND_BASIC_VELOCITY = "wind_basic_velocity"
    WIND_ROUGHNESS_CATEGORY = "wind_roughness_category"
    WIND_OROGRAPHIC_FACTOR = "wind_orographic_factor"
    WIND_DIRECTIONAL_FACTOR = "wind_directional_factor"
    SNOW_LOAD = "snow_load"
    ICE_LOAD = "ice_load"
    SEISMIC_ACCELERATION = "seismic_acceleration"
    SEISMIC_ZONE = "seismic_zone"
    AIR_DENSITY = "air_density"
    ALTITUDE = "altitude"
    TEMPERATURE_MIN = "temperature_min"
    TEMPERATURE_MAX = "temperature_max"
    OTHER = "other"


class DataConfidenceLevel(str, enum.Enum):
    A = "A"  # Autoritativo (mapa/tabla normativa oficial)
    B = "B"  # Fuente pública compatible
    C = "C"  # Estimado asistido
    D = "D"  # Usuario (dato contractual)
    E = "E"  # Pendiente — bloquea cálculo oficial


class ConfirmationState(str, enum.Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    SUBSTITUTED = "substituted"
    ESTIMATED = "estimated"
    CONSERVATIVE = "conservative"
    PENDING = "pending"


class ActionType(str, enum.Enum):
    G = "G"   # Permanentes
    W = "W"   # Viento
    S = "S"   # Nieve
    I = "I"   # Hielo
    E = "E"   # Sismo
    T = "T"   # Temperatura
    C = "C"   # Cables
    M = "M"   # Mantenimiento/montaje
    A = "A"   # Accidental
    P = "P"   # Pretensado


class CableActionState(str, enum.Enum):
    ACTIVE_PERMANENT = "active_permanent"
    ACTIVE_CONDITIONAL = "active_conditional"
    ABSENT = "absent"
    ACCIDENTAL_BREAK = "accidental_break"
    TEMPORARY_TENSIONED = "temporary_tensioned"


class ActionRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DiagnosticSeverity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    BLOCKED = "blocked"


class LimitState(str, enum.Enum):
    ULS_PERSISTENT = "ULS_persistent"
    ULS_ACCIDENTAL = "ULS_accidental"
    ULS_SEISMIC = "ULS_seismic"
    SLS_CHARACTERISTIC = "SLS_characteristic"
    SLS_FREQUENT = "SLS_frequent"
    SLS_QUASI_PERMANENT = "SLS_quasi_permanent"
    FATIGUE = "fatigue"


class SpatialLoadType(str, enum.Enum):
    NODAL = "nodal"
    DISTRIBUTED = "distributed"
    SURFACE_PRESSURE = "surface_pressure"
    MASS = "mass"
    IMPOSED_DISPLACEMENT = "imposed_displacement"
    TEMPERATURE = "temperature"


class AeroQuality(str, enum.Enum):
    A = "A"  # Ensayo/norma directa
    B = "B"  # Interpolación
    C = "C"  # Aproximación conservadora


# ── Tablas ─────────────────────────────────────────────────────────────────────

class Location(Base, TimestampMixin):
    """
    Ubicación versionada del emplazamiento del proyecto.
    Entidad, no simple par de coordenadas — incluye jurisdicciones,
    parámetros ambientales y trazabilidad de fuentes.
    """
    __tablename__ = "locations"

    id: Mapped[UUIDPk]
    project_revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Coordinates in WGS84
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    country_code: Mapped[ShortStr] = mapped_column(String(3), nullable=False)
    country_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    municipality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    altitude_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    altitude_resolution_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    environment: Mapped[Optional[EnvironmentType]] = mapped_column(
        Enum(EnvironmentType, name="environment_type", values_callable=lambda x: [e.value for e in x]), nullable=True
    )
    project_life_years: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reference_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Resolved jurisdictions and applicable normative set
    jurisdiction_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    normative_set_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Geocoding metadata
    geocoding_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    geocoding_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Overall confirmation state
    confirmation_state: Mapped[ConfirmationState] = mapped_column(
        Enum(ConfirmationState, name="confirmation_state", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConfirmationState.PROPOSED,
    )
    confirmed_by_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    geo_parameters: Mapped[list["GeoParameter"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_location_lat"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_location_lon"),
        Index("ix_locations_revision", "project_revision_id"),
        Index("ix_locations_country", "country_code"),
    )


class GeoParameter(Base, TimestampMixin):
    """
    Parámetro geográfico/ambiental individual con trazabilidad completa.
    GEO-001: incluye value, unit, source_id, source_version, retrieval_date,
    resolution, interpolation_method, confidence y confirmation_state.
    GEO-003: override conserva propuesto, adoptado y justificación.
    """
    __tablename__ = "geo_parameters"

    id: Mapped[UUIDPk]
    location_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    parameter_type: Mapped[GeoParameterType] = mapped_column(
        Enum(GeoParameterType, name="geo_parameter_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Resolved (proposed) value
    proposed_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    proposed_value_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # User-adopted value (may differ from proposed)
    adopted_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adopted_value_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    unit: Mapped[Optional[ShortStr]] = mapped_column(String(20), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    retrieval_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    interpolation_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[DataConfidenceLevel] = mapped_column(
        Enum(DataConfidenceLevel, name="data_confidence_level"),
        nullable=False,
        default=DataConfidenceLevel.E,
    )
    confirmation_state: Mapped[ConfirmationState] = mapped_column(
        Enum(ConfirmationState, name="confirmation_state", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConfirmationState.PROPOSED,
    )
    justification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Spatial reference for reproducibility (GEO-010, GEO-011)
    spatial_ref_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    location: Mapped["Location"] = relationship(back_populates="geo_parameters")

    __table_args__ = (
        Index("ix_geo_parameters_location", "location_id"),
        Index("ix_geo_parameters_type", "parameter_type"),
        Index("ix_geo_parameters_confidence", "confidence"),
    )


class NormativeActionRule(Base, TimestampMixin):
    """
    Regla normativa versionada para el motor de acciones.
    NOR-301: cada fórmula y coeficiente es una regla versionada, no constante en código.
    NOR-302: proyectos históricos conservan la edición congelada.
    """
    __tablename__ = "normative_action_rules"

    id: Mapped[UUIDPk]
    library_version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("library_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    code: Mapped[CodeStr] = mapped_column(String(50), nullable=False)
    edition: Mapped[ShortStr] = mapped_column(String(30), nullable=False)
    clause: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country_code: Mapped[Optional[ShortStr]] = mapped_column(String(3), nullable=True)
    action_type: Mapped[Optional[ActionType]] = mapped_column(
        Enum(ActionType, name="action_type"), nullable=True
    )
    # Formula, coefficients, limits, validity, dependencies
    formula_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validity_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_normative_rules_code", "code"),
        Index("ix_normative_rules_edition", "edition"),
        Index("ix_normative_rules_country", "country_code"),
    )


class AerodynamicProperty(Base, TimestampMixin):
    """
    Propiedad aerodinámica de un componente: área proyectada + Cd.
    AER-001: área proyectada calculada normal a la dirección de viento.
    AER-003: proyección geométrica NO sustituye coeficiente Cd.
    """
    __tablename__ = "aerodynamic_properties"

    id: Mapped[UUIDPk]
    component_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Orientation: single value (deg) or "all" for symmetric
    orientation_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Projected area normal to wind direction [m²]
    area_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Drag coefficient (adimensional)
    cd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Polar table: {deg: {area_m2, cd, cp_x, cp_y}} every N degrees
    polar_table_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    method: Mapped[str] = mapped_column(String(50), nullable=False, default="geometric_projection")
    # Validity domain: Re range, shape family, geometry constraints
    validity_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    quality: Mapped[AeroQuality] = mapped_column(
        Enum(AeroQuality, name="aero_quality"), nullable=False, default=AeroQuality.C
    )
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Center of pressure (local coordinates)
    cp_local_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_aero_props_component", "component_id"),
        Index("ix_aero_props_type", "component_type"),
    )


class ActionRun(Base, TimestampMixin):
    """
    Ejecución inmutable del motor de acciones.
    DAT-301: las ejecuciones publicadas no se editan; un cambio crea nueva ejecución.
    ACT-FLOW-001: cada paso conserva input_hash, output_hash, engine_version, etc.
    """
    __tablename__ = "action_runs"

    id: Mapped[UUIDPk]
    project_revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    geometry_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outputs_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[Optional[ShortStr]] = mapped_column(String(30), nullable=True)
    library_versions_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # {lib_id: version, normative_edition: ..., ...}
    status: Mapped[ActionRunStatus] = mapped_column(
        Enum(ActionRunStatus, name="action_run_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ActionRunStatus.PENDING,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Manifest: summary of all inputs, versions, hashes
    manifest_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # ARQ job reference
    arq_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Wind sweep configuration
    sweep_config_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Combination template reference
    combination_template_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)

    location: Mapped[Optional["Location"]] = relationship()
    action_components: Mapped[list["ActionComponent"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )
    cable_actions: Mapped[list["CableAction"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )
    load_cases: Mapped[list["LoadCase"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )
    combination_instances: Mapped[list["CombinationInstance"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )
    spatial_loads: Mapped[list["SpatialLoad"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )
    mass_items: Mapped[list["MassItem"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )
    diagnostics: Mapped[list["ActionDiagnostic"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )
    user_overrides: Mapped[list["UserOverride"]] = relationship(
        back_populates="action_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_action_runs_revision", "project_revision_id"),
        Index("ix_action_runs_status", "status"),
        Index("ix_action_runs_input_hash", "input_hash"),
    )


class ActionComponent(Base, TimestampMixin):
    """
    Acción elemental característica por componente y dirección.
    Sin factores de combinación — esos se aplican en CombinationInstance.
    WND-002: contribuciones separadas por componente para auditoría.
    """
    __tablename__ = "action_components"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, name="action_type"), nullable=False
    )
    component_ref: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    component_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Characteristic value without partial factors (SI units: N, N/m, Pa, etc.)
    characteristic_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[ShortStr]] = mapped_column(String(20), nullable=True)
    # Distribution: distributed/concentrated/pressure/moment
    distribution_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Normative rule reference
    rule_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Intermediate calculation values for audit
    calculation_trace_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="action_components")

    __table_args__ = (
        Index("ix_action_components_run", "action_run_id"),
        Index("ix_action_components_type", "action_type"),
    )


class CableAction(Base, TimestampMixin):
    """
    Acción de cable de catenaria vinculada a una ejecución de acciones.
    CAT-001: azimut numérico obligatorio.
    CAT-002: tensión como valor característico positivo (sin factor parcial).
    CAT-003: rotura accidental = estado de escenario, no tensión negativa.
    """
    __tablename__ = "cable_actions"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    cable_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cable_load_points.id", ondelete="SET NULL"),
        nullable=True,
    )
    cable_identifier: Mapped[ShortStr] = mapped_column(String(20), nullable=False)
    anchor_z_m: Mapped[float] = mapped_column(Float, nullable=False)
    # Tension characteristic value [N], positive
    tension_n: Mapped[float] = mapped_column(Float, nullable=False)
    azimuth_rad: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Force vector applied to column (3D, SI units)
    force_vector_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # {Fx_N, Fy_N, Fz_N, Mx_Nm, My_Nm, Mz_Nm} at anchor point
    eccentricity_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    cable_state: Mapped[CableActionState] = mapped_column(
        Enum(CableActionState, name="cable_action_state", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CableActionState.ACTIVE_PERMANENT,
    )
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    uncertainty_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="cable_actions")

    __table_args__ = (
        CheckConstraint("tension_n >= 0", name="ck_cable_tension_positive"),
        Index("ix_cable_actions_run", "action_run_id"),
    )


class LoadCase(Base, TimestampMixin):
    """
    Caso de carga: conjunto coherente de acciones simultáneas.
    Cada dirección de viento genera un caso elemental.
    Los casos de cable y especiales se añaden separadamente.
    """
    __tablename__ = "load_cases"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[ShortStr] = mapped_column(String(30), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    action_types_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # List of active ActionComponent IDs
    active_actions_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Component states (cables active/absent, etc.)
    component_states_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Canonical hash for deduplication (COM-005)
    case_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_base_direction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_refined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="load_cases")
    combination_instances: Mapped[list["CombinationInstance"]] = relationship(
        back_populates="load_case", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_load_cases_run", "action_run_id"),
        Index("ix_load_cases_direction", "direction_deg"),
        Index("ix_load_cases_hash", "case_hash"),
    )


class CombinationTemplate(Base, TimestampMixin):
    """
    Plantilla normativa versionada de combinación (ELU/ELS/fatiga).
    COM-001: almacena acciones, factores parciales, factores de simultaneidad,
    acción principal, signo y regla de exclusión.
    NOR-302: proyectos históricos conservan la edición congelada.
    """
    __tablename__ = "combination_templates"

    id: Mapped[UUIDPk]
    library_version_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("library_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    code: Mapped[CodeStr] = mapped_column(String(50), nullable=False)
    edition: Mapped[ShortStr] = mapped_column(String(30), nullable=False)
    country_code: Mapped[Optional[ShortStr]] = mapped_column(String(3), nullable=True)
    limit_state: Mapped[LimitState] = mapped_column(
        Enum(LimitState, name="limit_state", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Declarative formula graph: actions, partial factors, combination factors
    formula_graph_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Partial and combination factors
    factors_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Mutual exclusion groups (e.g., wind directions)
    exclusions_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_combination_templates_code", "code"),
        Index("ix_combination_templates_limit_state", "limit_state"),
    )


class CombinationInstance(Base, TimestampMixin):
    """
    Instancia de combinación para un caso de carga específico.
    COM-004: nombre humano e identificador canónico reproducible.
    COM-005: deduplicación por normalización algebraica y hash.
    """
    __tablename__ = "combination_instances"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    load_case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("load_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("combination_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    limit_state: Mapped[LimitState] = mapped_column(
        Enum(LimitState, name="limit_state", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    leading_action: Mapped[Optional[ActionType]] = mapped_column(
        Enum(ActionType, name="action_type"), nullable=True
    )
    # Normalized algebraic expression of the combination
    normalized_terms_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Canonical hash for deduplication
    instance_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="combination_instances")
    load_case: Mapped["LoadCase"] = relationship(back_populates="combination_instances")
    template: Mapped[Optional["CombinationTemplate"]] = relationship()

    __table_args__ = (
        Index("ix_combination_instances_run", "action_run_id"),
        Index("ix_combination_instances_hash", "instance_hash"),
        Index("ix_combination_instances_limit_state", "limit_state"),
    )


class SpatialLoad(Base, TimestampMixin):
    """
    Carga espacial expresada en sistema global y local de componente.
    LOD-001: resultantes reconciliadas con resultantes físicas antes de exportar.
    LOD-002: transformación global-local validada por invariantes de fuerza y momento.
    """
    __tablename__ = "spatial_loads"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    load_case_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("load_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # station_z_m for distributed, or node reference
    station_start_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    station_end_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    load_type: Mapped[SpatialLoadType] = mapped_column(
        Enum(SpatialLoadType, name="spatial_load_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    coordinate_system: Mapped[str] = mapped_column(String(20), nullable=False, default="global")
    # For nodal: {Fx_N, Fy_N, Fz_N, Mx_Nm, My_Nm, Mz_Nm}
    # For distributed: {law_type, parameters_json, start_vector, end_vector}
    vector_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    law_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    action_type: Mapped[Optional[ActionType]] = mapped_column(
        Enum(ActionType, name="action_type"), nullable=True
    )
    direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Provenance: which action component and rule generated this load
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="spatial_loads")
    load_case: Mapped[Optional["LoadCase"]] = relationship()

    __table_args__ = (
        Index("ix_spatial_loads_run", "action_run_id"),
        Index("ix_spatial_loads_case", "load_case_id"),
        Index("ix_spatial_loads_target", "target_id"),
    )


class MassItem(Base, TimestampMixin):
    """
    Masa de un componente con CG e inercia para cálculo sísmico y gravitatorio.
    SEI-011: masas reconciliadas con BOM y modelo geométrico.
    PER-001: masa indica si incluye tornillería, cableado y soporte.
    """
    __tablename__ = "mass_items"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mass_kg: Mapped[float] = mapped_column(Float, nullable=False)
    # CG in global coordinates {x_m, y_m, z_m}
    cg_global_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Mass moment of inertia tensor (optional, for seismic)
    inertia_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="geometry")
    # Flags for what is included in mass
    includes_hardware: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    includes_cables: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    includes_finish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    additional_margin_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="mass_items")

    __table_args__ = (
        CheckConstraint("mass_kg >= 0", name="ck_mass_item_positive"),
        Index("ix_mass_items_run", "action_run_id"),
        Index("ix_mass_items_component", "component_id"),
    )


class ActionDiagnostic(Base, TimestampMixin):
    """
    Error, advertencia o información generada durante la ejecución de acciones.
    ACT-FLOW-002: ejecución fallida no publica resultados parciales como válidos.
    """
    __tablename__ = "action_diagnostics"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[DiagnosticSeverity] = mapped_column(
        Enum(DiagnosticSeverity, name="diagnostic_severity", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    condition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    field_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    normative_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Acceptance by authorized user
    accepted_by_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acceptance_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="diagnostics")

    __table_args__ = (
        Index("ix_action_diagnostics_run", "action_run_id"),
        Index("ix_action_diagnostics_code", "code"),
        Index("ix_action_diagnostics_severity", "severity"),
    )


class UserOverride(Base, TimestampMixin):
    """
    Override de parámetro por el usuario.
    DAT-302: almacenado como objeto separado con motivo, autor, fecha y evidencia.
    """
    __tablename__ = "user_overrides"

    id: Mapped[UUIDPk]
    action_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("action_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    parameter_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    original_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    original_value_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    adopted_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adopted_value_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    requires_ot_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    action_run: Mapped["ActionRun"] = relationship(back_populates="user_overrides")

    __table_args__ = (
        Index("ix_user_overrides_run", "action_run_id"),
    )
