"""
SALVI Tunnel Engine — Modelos de datos
Entidades principales según la especificación STES v0.1
Norma de referencia: CIE 88:2004
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum


# --------------------------------------------------
# ENUMERACIONES
# --------------------------------------------------

class TunnelCategory(str, Enum):
    VERY_SHORT   = "very_short"
    SHORT        = "short"
    INTERMEDIATE = "intermediate"
    LONG         = "long"

class OpticalCategory(str, Enum):
    SHORT = "optically_short"
    LONG  = "optically_long"

class DaylightingNeed(str, Enum):
    NONE    = "none"
    REDUCED = "reduced"
    NORMAL  = "normal"

class TrafficDirection(str, Enum):
    ONE_WAY = "one_way"
    TWO_WAY = "two_way"

class ZoneType(str, Enum):
    ACCESS     = "ACCESS"
    THRESHOLD  = "THRESHOLD"
    TRANSITION = "TRANSITION"
    INTERIOR   = "INTERIOR"
    EXIT       = "EXIT"
    PARTING    = "PARTING"
    NIGHT      = "NIGHT"
    EMERGENCY  = "EMERGENCY"

class ControlMode(str, Enum):
    CONTINUOUS = "continuous"
    STEPPED    = "stepped"

class PortalOrientation(str, Enum):
    NORTH     = "N"
    NORTHEAST = "NE"
    EAST      = "E"
    SOUTHEAST = "SE"
    SOUTH     = "S"
    SOUTHWEST = "SW"
    WEST      = "W"
    NORTHWEST = "NW"

class SkyCondition(str, Enum):
    CLEAR        = "clear"
    INTERMEDIATE = "intermediate"
    OVERCAST     = "overcast"

class DataSource(str, Enum):
    GIS     = "GIS"
    OSM     = "OpenStreetMap"
    MDT     = "MDT"
    USER    = "Usuario"
    NORM    = "Norma/Proyecto"
    DEFAULT = "Valor por defecto"
    CALC    = "Calculado"

class DataConfidence(str, Enum):
    HIGH   = "Alta"
    MEDIUM = "Media"
    LOW    = "Baja"


# --------------------------------------------------
# DATOS TRAZABLES
# --------------------------------------------------

@dataclass
class TracedValue:
    """Un dato con su origen y nivel de confianza (P5 - Trazabilidad)."""
    value: float
    source: DataSource = DataSource.USER
    confidence: DataConfidence = DataConfidence.MEDIUM
    note: str = ""


# --------------------------------------------------
# GEOMETRIA DEL TUNEL
# --------------------------------------------------

@dataclass
class CrossSection:
    """Seccion transversal en un punto del eje."""
    width_total: float
    height: float
    num_lanes: int = 2
    lane_width: float = 3.5
    shoulder_width: float = 0.5
    wall_reflectance: float = 0.4
    ceiling_reflectance: float = 0.3
    road_q0: float = 0.07


@dataclass
class Portal:
    """Boca de entrada o salida de un tubo."""
    portal_id: str
    direction: TrafficDirection
    orientation: PortalOrientation = PortalOrientation.SOUTH
    latitude: float = 40.0
    longitude: float = -3.0
    altitude: float = 0.0
    environment_type: str = "road"
    sky_condition: SkyCondition = SkyCondition.CLEAR
    has_daylight_screen: bool = False


@dataclass
class TunnelTube:
    """Galeria de circulacion independiente."""
    tube_id: str
    length: float
    entry_portal: Portal = None
    exit_portal: Portal = None
    cross_section: CrossSection = None
    gradient: float = 0.0
    curvature_radius: Optional[float] = None
    traffic_direction: TrafficDirection = TrafficDirection.ONE_WAY


# --------------------------------------------------
# CLASIFICACION
# --------------------------------------------------

@dataclass
class TunnelClassification:
    """Resultado de la clasificacion CIE 88 (Cap. 6)."""
    geometric_category: TunnelCategory
    optical_category: OpticalCategory
    daylighting_need: DaylightingNeed
    exit_visible_from_sd: bool
    daylight_penetration: str
    justification: str = ""


# --------------------------------------------------
# VELOCIDAD Y DISTANCIA DE PARADA
# --------------------------------------------------

@dataclass
class DesignSpeedResult:
    """TUN-GEO-001 a 004."""
    design_speed_kmh: TracedValue
    stopping_distance_m: float
    reaction_distance_m: float
    braking_distance_m: float
    reference_point_s: float
    reaction_time_s: float = 1.5
    deceleration_mss: float = 3.5
    friction_coefficient: Optional[float] = None
    calculation_method: str = "cie88_table"


# --------------------------------------------------
# ZONAS NORMATIVAS
# --------------------------------------------------

@dataclass
class TunnelZone:
    """Una zona normativa CIE 88 con su posicion y nivel de luminancia."""
    zone_type: ZoneType
    s_start: float
    s_end: float
    L_start: float = 0.0
    L_end: float = 0.0
    L_min_required: float = 0.0
    description: str = ""
    # Referencia CIE conservada cuando el proyecto fija una geometría distinta.
    strict_length_m: Optional[float] = None
    transition_scale: float = 1.0
    project_override: bool = False

    @property
    def length(self) -> float:
        return self.s_end - self.s_start


@dataclass
class TunnelZones:
    """Conjunto completo de zonas de un tubo/sentido."""
    tube_id: str
    traffic_direction: TrafficDirection
    stopping_distance: float
    access: Optional[TunnelZone] = None
    threshold: Optional[TunnelZone] = None     # CTH Portal A (o único)
    transition: Optional[TunnelZone] = None    # CTR Portal A (o único)
    interior: Optional[TunnelZone] = None      # CIN (centro)
    exit: Optional[TunnelZone] = None          # CEX — solo en sentido único
    parting: Optional[TunnelZone] = None       # ACC — solo en sentido único
    # ── Bidireccional: zonas simétricas del Portal B ──────────────────────────
    transition_b: Optional[TunnelZone] = None  # CTR Portal B (espejo)
    threshold_b: Optional[TunnelZone] = None   # CTH Portal B (espejo)
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------
# L20 / LSEQ / LTH
# --------------------------------------------------

@dataclass
class L20Result:
    """Resultado del calculo de luminancia de acceso L20 (Cap. 14)."""
    L20: float
    method: str
    L_road: float = 0.0
    L_portals: float = 0.0
    L_walls: float = 0.0
    L_vegetation: float = 0.0
    w_road: float = 0.0
    w_portals: float = 0.0
    w_walls: float = 0.0
    w_vegetation: float = 0.0
    confidence: DataConfidence = DataConfidence.MEDIUM
    note: str = ""


@dataclass
class LseqResult:
    """Resultado del calculo de luminancia equivalente Lseq (Cap. 15)."""
    Lseq: float
    method: str
    C_obs: float = 0.04
    L_obstacle: float = 0.0
    L_background: float = 0.0
    note: str = ""


@dataclass
class LthResult:
    """Resultado del calculo de luminancia umbral Lth (Cap. 16)."""
    Lth: float
    L20: float
    Lseq: Optional[float]
    k_factor: float
    qc: float
    method: str
    iterations: int = 1
    converged: bool = True
    standard: str = "CIE 88:2004"
    tunnel_class: Optional[int] = None
    calculated_tunnel_class: Optional[int] = None
    tunnel_class_source: str = ""
    stopping_distance_m: Optional[float] = None
    k_source: str = ""
    qc_used: bool = False
    C_obs: Optional[float] = None
    note: str = ""


# --------------------------------------------------
# PERFIL LONGITUDINAL
# --------------------------------------------------

@dataclass
class ProfilePoint:
    """Un punto del perfil longitudinal."""
    s: float
    L_required: float
    zone: ZoneType


@dataclass
class LuminanceProfile:
    """Perfil longitudinal de luminancia (Cap. 23-30)."""
    tube_id: str
    traffic_direction: TrafficDirection
    design_speed_kmh: float
    stopping_distance_m: float
    Lth: float
    Lin: float
    L_night: float
    zones: TunnelZones = None
    points: List[ProfilePoint] = field(default_factory=list)
    Uo_min: float = 0.40
    Ul_min: float = 0.60
    TI_max: float = 15.0
    wall_ratio_min: float = 0.60

    def add_point(self, s: float, L: float, zone: ZoneType):
        self.points.append(ProfilePoint(s=s, L_required=L, zone=zone))

    def to_dict(self) -> List[dict]:
        return [{"s": p.s, "L": p.L_required, "zone": p.zone.value} for p in self.points]


# --------------------------------------------------
# RESULTADOS COMPLETOS
# --------------------------------------------------

@dataclass
class TunnelDesignResult:
    """Resultado completo del diseno de un tunel."""
    project_name: str
    tube_id: str
    classification: TunnelClassification
    speed: DesignSpeedResult
    L20: L20Result
    Lth: LthResult
    profile: LuminanceProfile
    zones: TunnelZones
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    traceability: Dict[str, TracedValue] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return len(self.errors) == 0
