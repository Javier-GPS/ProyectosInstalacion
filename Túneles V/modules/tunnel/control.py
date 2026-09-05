"""
SALVI Tunnel Engine — Módulo de Control
TUN-CTL-001 a TUN-CTL-007: Grupos de control, escenas, niveles de regulación,
curvas adaptativas y export DALI/Smartec.
Norma: CIE 88:2004, Capítulos 87-111
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import math

from .models import ZoneType, TunnelZones
from .required_luminance import cie88_transition_luminance


# ══════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════

class SceneType(Enum):
    SUNNY    = "sunny"     # Día soleado — L20 máximo de diseño
    NORMAL   = "normal"    # Día normal (70% L20 máx)
    OVERCAST = "overcast"  # Nublado (30% L20 máx)
    DUSK     = "dusk"      # Amanecer / atardecer (~200 cd/m²)
    NIGHT    = "night"     # Noche reducida — compatibilidad histórica
    NIGHT_NORMAL = "night_normal"  # Noche normal — BASE al nivel Lin


class ControlProtocol(Enum):
    DALI     = "DALI"
    SMARTEC  = "Smartec"
    ANALOGUE = "0-10V"


# ══════════════════════════════════════════════════════════════════
# DATACLASSES
# ══════════════════════════════════════════════════════════════════

@dataclass
class ControlScene:
    """
    TUN-CTL-002: Escena de control (condición ambiental → nivel de iluminación).
    CIE 88 requiere mínimo 3 escenas diurnas + 1 nocturna.
    """
    scene_id: int
    scene_type: SceneType
    name: str
    L20_cd_m2: float      # Luminancia campo 20° para esta escena (cd/m²)
    L20_b_cd_m2: Optional[float] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "scene_id":    self.scene_id,
            "scene_type":  self.scene_type.value,
            "name":        self.name,
            "L20":         round(self.L20_cd_m2, 0),
            "L20_b":       round(
                self.L20_b_cd_m2
                if self.L20_b_cd_m2 is not None
                else self.L20_cd_m2,
                0,
            ),
            "description": self.description
        }


@dataclass
class ControlGroup:
    """
    TUN-CTL-001: Grupo de control — conjunto de luminarias de la misma zona
    que se regulan conjuntamente.

    Grupos estándar:
      CTH  — Umbral (Threshold)
      CTR1 … CTRn — Transición (1 a 4 sub-grupos)
      CIN  — Interior
      CEX  — Salida (Exit)
    """
    group_id: int
    name: str
    zone_type: ZoneType
    zone_label: str
    L_design: float                            # Luminancia de diseño (cd/m²)
    layer: str = "reinforcement"                # permanent | reinforcement
    portal: Optional[str] = None                # A | B | None
    s_reference_m: Optional[float] = None
    total_L_design: Optional[float] = None
    off_allowed: bool = True
    min_dim_pct: float = 0.1
    dimming_levels: Dict[int, float] = field(default_factory=dict)  # {scene_id: %}
    dali_levels:    Dict[int, int]   = field(default_factory=dict)  # {scene_id: 0-254}
    notes: str = ""
    daylight_profile: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "group_id":       self.group_id,
            "name":           self.name,
            "zone_type":      self.zone_type.value,
            "zone_label":     self.zone_label,
            "L_design":       round(self.L_design, 1),
            "layer":          self.layer,
            "portal":         self.portal,
            "s_reference_m":  (
                round(self.s_reference_m, 2)
                if self.s_reference_m is not None else None
            ),
            "total_L_design": (
                round(self.total_L_design, 1)
                if self.total_L_design is not None else None
            ),
            "off_allowed":    self.off_allowed,
            "min_dim_pct":    round(self.min_dim_pct, 3),
            "dimming_levels": {str(k): round(v, 1) for k, v in self.dimming_levels.items()},
            "dali_levels":    {str(k): v for k, v in self.dali_levels.items()},
            "notes":          self.notes,
            "daylight_profile": self.daylight_profile,
        }


@dataclass
class RegulationPoint:
    """Punto de la curva de regulación adaptativa."""
    L20: float          # cd/m²
    L_required: float   # Luminancia requerida en esta zona (cd/m²)
    dimming_pct: float  # Porcentaje de regulación (0-100%)
    dali_level: int     # Nivel DALI (0-254)

    def to_dict(self) -> dict:
        return {
            "L20":         round(self.L20, 0),
            "L_required":  round(self.L_required, 1),
            "dimming_pct": round(self.dimming_pct, 1),
            "dali_level":  self.dali_level
        }


@dataclass
class RegulationCurve:
    """
    TUN-CTL-004: Curva de regulación continua para control adaptativo.
    Relaciona L20 medido → nivel de regulación del grupo.
    """
    group_id: int
    group_name: str
    zone_type: ZoneType
    points: List[RegulationPoint] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "group_id":   self.group_id,
            "group_name": self.group_name,
            "zone_type":  self.zone_type.value,
            "points":     [p.to_dict() for p in self.points]
        }


@dataclass
class TunnelControlPlan:
    """
    Plan de control completo de un tubo de túnel.
    Contiene escenas, grupos, niveles y curvas de regulación.
    """
    tube_id: str
    protocol: ControlProtocol
    scenes: List[ControlScene]
    groups: List[ControlGroup]
    regulation_curves: List[RegulationCurve]
    warnings: List[str] = field(default_factory=list)
    strategy: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tube_id":           self.tube_id,
            "protocol":          self.protocol.value,
            "n_groups":          len(self.groups),
            "n_scenes":          len(self.scenes),
            "scenes":            [s.to_dict() for s in self.scenes],
            "groups":            [g.to_dict() for g in self.groups],
            "regulation_curves": [c.to_dict() for c in self.regulation_curves],
            "strategy":          self.strategy,
            "warnings":          self.warnings
        }


# ══════════════════════════════════════════════════════════════════
# UTILIDADES DALI (IEC 62386)
# ══════════════════════════════════════════════════════════════════

def dimming_to_dali(dimming_pct: float) -> int:
    """
    Convierte porcentaje de flujo (0-100%) a nivel DALI (0-254).

    Relación normalizada IEC 62386:
      Φ_rel(%) = 10^(((x-1) × 3 / 253) - 1), x ∈ [1, 254]
      x = 1 → 0.1 %, x = 254 → 100 %, x = 0 → apagado.
    """
    if dimming_pct <= 0:
        return 0
    if dimming_pct >= 100:
        return 254
    # IEC 62386 inverse mapping. Values below the standard 0.1 % floor
    # are represented by the lowest arc level; switching off remains 0.
    pct = max(0.1, float(dimming_pct))
    level = 1.0 + (253.0 / 3.0) * math.log10(pct / 0.1)
    return max(1, min(254, round(level)))


def dali_to_dimming(dali_level: int) -> float:
    """Nivel DALI (0-254) → porcentaje de flujo (0-100%)."""
    if dali_level <= 0:
        return 0.0
    if dali_level >= 254:
        return 100.0
    pct = 10.0 ** ((((dali_level - 1) * 3.0) / 253.0) - 1.0)
    return round(pct, 3)


# ══════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def _build_control_plan_legacy(
    tube_id: str,
    L20_design: float,
    Lth_design: float,
    Lin: float,
    L_night: float,
    k_factor: float,
    speed_kmh: float,
    zones: TunnelZones,
    n_transition_groups: int = 2,
    protocol: str = "DALI"
) -> TunnelControlPlan:
    """
    TUN-CTL-001 a 007: Genera el plan de control completo del túnel.

    Args:
        tube_id:             ID del tubo (ej. "T1")
        L20_design:          Luminancia de campo 20° de diseño (cd/m²)
        Lth_design:          Luminancia umbral de diseño (cd/m²)
        Lin:                 Luminancia zona interior (cd/m²)
        L_night:             Luminancia nocturna mínima (cd/m²)
        k_factor:            Factor k (Lth = k × L20)
        speed_kmh:           Velocidad de diseño (km/h)
        zones:               Zonas del túnel
        n_transition_groups: Grupos en zona transición (1–4)
        protocol:            "DALI" | "Smartec" | "0-10V"

    Returns:
        TunnelControlPlan con escenas, grupos y curvas
    """
    warnings = []

    # Protocolo
    valid_protocols = {p.value: p for p in ControlProtocol}
    ctrl_protocol = valid_protocols.get(protocol, ControlProtocol.DALI)

    # Mínimo Lth según CIE 88:2004 tabla 6.2
    Lth_min = 50.0 if speed_kmh >= 80 else 25.0

    # ── 1. ESCENAS (TUN-CTL-002) ──────────────────────────────────
    # CIE 88 requiere ≥ 3 escenas diurnas + noche.
    # Los niveles de L20 de cada escena se calculan como fracción del diseño.
    L20_dusk = min(200.0, L20_design * 0.05)

    scenes: List[ControlScene] = [
        ControlScene(1, SceneType.SUNNY,
                     "Soleado",
                     L20_design,
                     f"Cielo despejado — L20 = {L20_design:.0f} cd/m² (diseño máximo)"),
        ControlScene(2, SceneType.NORMAL,
                     "Normal",
                     round(L20_design * 0.70, 0),
                     f"Día nublado parcial — L20 = {L20_design*0.70:.0f} cd/m²"),
        ControlScene(3, SceneType.OVERCAST,
                     "Cubierto",
                     round(L20_design * 0.30, 0),
                     f"Cielo cubierto — L20 = {L20_design*0.30:.0f} cd/m²"),
        ControlScene(4, SceneType.DUSK,
                     "Atardecer",
                     L20_dusk,
                     f"Amanecer/atardecer — L20 = {L20_dusk:.0f} cd/m²"),
        ControlScene(5, SceneType.NIGHT,
                     "Noche",
                     0.0,
                     f"Iluminación nocturna — L_night = {L_night:.1f} cd/m²"),
    ]

    # ── 2. GRUPOS DE CONTROL (TUN-CTL-001) ───────────────────────
    groups: List[ControlGroup] = []
    gid = 1

    # CTH — Umbral
    groups.append(ControlGroup(
        group_id=gid, name="CTH — Umbral",
        zone_type=ZoneType.THRESHOLD, zone_label="Umbral",
        L_design=Lth_design,
        notes=f"Lth = k × L20 = {k_factor:.4f} × L20  (mín. {Lth_min:.0f} cd/m²)"
    ))
    gid += 1

    # CTR1…CTRn — Transición
    if zones.transition and n_transition_groups > 0:
        n_tr = max(1, min(4, n_transition_groups))
        for i in range(n_tr):
            # Posición relativa en la zona de transición (punto medio del sub-grupo)
            t_mid = (i + 0.5) / n_tr
            # Punto medio del grupo sobre la fuente unica CIE 88.
            s_mid = (
                float(zones.transition.s_start)
                + t_mid
                * (
                    float(zones.transition.s_end)
                    - float(zones.transition.s_start)
                )
            )
            L_tr = cie88_transition_luminance(
                s_mid,
                float(zones.transition.s_start),
                Lth_design,
                Lin,
                speed_kmh,
            )
            groups.append(ControlGroup(
                group_id=gid,
                name=f"CTR{i+1} — Transición {i+1}/{n_tr}",
                zone_type=ZoneType.TRANSITION,
                zone_label=f"Transición {i+1}",
                L_design=round(L_tr, 1),
                notes=f"s={s_mid:.1f} m en curva CIE 88"
            ))
            gid += 1

    # CIN — Interior
    if zones.interior:
        groups.append(ControlGroup(
            group_id=gid, name="CIN — Interior",
            zone_type=ZoneType.INTERIOR, zone_label="Interior",
            L_design=Lin,
            notes="Nivel constante = Lin"
        ))
        gid += 1

    # CEX — Salida
    if zones.exit:
        exit_level = max(
            0.0,
            float(getattr(zones.exit, "L_min_required", Lin) or Lin),
        )
        groups.append(ControlGroup(
            group_id=gid, name="CEX — Salida",
            zone_type=ZoneType.EXIT, zone_label="Salida",
            L_design=exit_level,
            notes="Lin (adaptación visual hacia el exterior es positiva)"
        ))
        gid += 1

    # ── 3. NIVELES POR ESCENA (TUN-CTL-003) ──────────────────────
    for scene in scenes:
        L20_s = scene.L20_cd_m2

        for group in groups:
            if scene.scene_type == SceneType.NIGHT:
                # Noche: todos los grupos al nivel nocturno
                dim = (L_night / group.L_design * 100.0) if group.L_design > 0 else 5.0
                dim = max(5.0, min(100.0, dim))

            elif group.zone_type == ZoneType.THRESHOLD:
                # CTH: proporcional a L20 (Lth_s = k × L20_s)
                Lth_s = max(Lth_min, k_factor * L20_s)
                dim = (Lth_s / Lth_design * 100.0) if Lth_design > 0 else 100.0
                dim = max(5.0, min(100.0, dim))

            elif group.zone_type == ZoneType.TRANSITION:
                # CTRx: proporcional al umbral, escalado por su posición en la curva
                Lth_s = max(Lth_min, k_factor * L20_s)
                ratio = (Lth_s / Lth_design) if Lth_design > 0 else 1.0
                L_s = max(Lin, group.L_design * ratio)
                dim = (L_s / group.L_design * 100.0) if group.L_design > 0 else 100.0
                dim = max(5.0, min(100.0, dim))

            else:
                # CIN / CEX: siempre al 100% en día; nivel nocturno en noche
                dim = 100.0

            group.dimming_levels[scene.scene_id] = round(dim, 1)
            group.dali_levels[scene.scene_id]    = dimming_to_dali(dim)

    # ── 4. VALIDAR RATIOS ENTRE ESCENAS (TUN-CTL-005) ────────────
    # CIE 88: el ratio de luminancia entre escenas consecutivas no debe superar 3:1.
    # Se agrupa por par de escenas para evitar avisos repetidos por cada grupo.
    ratio_violations: dict = {}  # {(scene_i-1, scene_i): max_ratio}
    for group in groups:
        if group.zone_type in (ZoneType.THRESHOLD, ZoneType.TRANSITION):
            levels = [group.dimming_levels.get(s.scene_id, 100) for s in scenes]
            for i in range(1, len(levels)):
                prev, curr = levels[i-1], levels[i]
                if curr > 0 and prev / curr > 3.01:
                    key = (scenes[i-1].name, scenes[i].name)
                    ratio = prev / curr
                    if key not in ratio_violations or ratio > ratio_violations[key]:
                        ratio_violations[key] = ratio
    for (s_prev, s_curr), ratio in ratio_violations.items():
        warnings.append(
            f"Ratio escenas '{s_prev}'/'{s_curr}' = {ratio:.1f} > 3.0 (CIE 88 §9.3) "
            f"— considerar añadir una escena intermedia"
        )

    # ── 5. CURVAS DE REGULACIÓN (TUN-CTL-004) ────────────────────
    regulation_curves = _build_regulation_curves(
        groups=groups,
        L20_max=L20_design,
        k_factor=k_factor,
        Lth_design=Lth_design,
        Lin=Lin,
        L_night=L_night,
        speed_kmh=speed_kmh
    )

    return TunnelControlPlan(
        tube_id=tube_id,
        protocol=ctrl_protocol,
        scenes=scenes,
        groups=groups,
        regulation_curves=regulation_curves,
        warnings=warnings
    )


# ══════════════════════════════════════════════════════════════════
# CURVAS DE REGULACIÓN ADAPTATIVA
# ══════════════════════════════════════════════════════════════════

def _build_regulation_curves(
    groups: List[ControlGroup],
    L20_max: float,
    k_factor: float,
    Lth_design: float,
    Lin: float,
    L_night: float,
    speed_kmh: float
) -> List[RegulationCurve]:
    """
    TUN-CTL-004: Genera curvas de regulación continua para control adaptativo
    basado en sensor fotométrico de L20.

    La curva muestra: L20 medido → dimming % del grupo.
    Se muestrea en 13 puntos equidistantes de 0 a L20_max.
    """
    Lth_min = 50.0 if speed_kmh >= 80 else 25.0
    curves = []

    # 13 puntos: 0%, 10%, 20%, … 100% + algún intermedio
    n_pts = 13
    L20_samples = [L20_max * i / (n_pts - 1) for i in range(n_pts)]

    for group in groups:
        curve = RegulationCurve(
            group_id=group.group_id,
            group_name=group.name,
            zone_type=group.zone_type
        )

        for L20 in L20_samples:
            if group.zone_type == ZoneType.THRESHOLD:
                L_req = max(Lth_min, k_factor * L20)
                dim   = (L_req / Lth_design * 100.0) if Lth_design > 0 else 100.0

            elif group.zone_type == ZoneType.TRANSITION:
                Lth_s = max(Lth_min, k_factor * L20)
                ratio = (Lth_s / Lth_design) if Lth_design > 0 else 1.0
                L_req = max(Lin, group.L_design * ratio)
                dim   = (L_req / group.L_design * 100.0) if group.L_design > 0 else 100.0

            else:
                # Interior / Salida — nivel fijo (independiente de L20)
                L_req = group.L_design
                dim   = 100.0

            dim = max(5.0, min(100.0, dim))

            curve.points.append(RegulationPoint(
                L20=round(L20, 0),
                L_required=round(L_req, 1),
                dimming_pct=round(dim, 1),
                dali_level=dimming_to_dali(dim)
            ))

        curves.append(curve)

    return curves


def _transition_total_for_group(
    group: ControlGroup,
    zones: TunnelZones,
    Lth_scene: float,
    Lin: float,
    speed_kmh: float,
) -> float:
    """Luminancia total requerida en el punto local de un grupo de transición."""
    zone = zones.transition_b if group.portal == "B" else zones.transition
    if zone is None or group.s_reference_m is None:
        return Lin
    if group.portal == "B":
        return cie88_transition_luminance(
            float(zone.s_end) - group.s_reference_m,
            0.0,
            Lth_scene,
            Lin,
            speed_kmh,
        )
    return cie88_transition_luminance(
        group.s_reference_m,
        float(zone.s_start),
        Lth_scene,
        Lin,
        speed_kmh,
    )


def _layer_required_luminance(
    group: ControlGroup,
    L20_scene: float,
    k_scene: float,
    Lin: float,
    speed_kmh: float,
    zones: TunnelZones,
) -> Tuple[float, float]:
    """
    Devuelve (luminancia total requerida, contribución requerida del grupo).

    La capa base aporta Lin en modo diurno. El refuerzo aporta únicamente la
    diferencia positiva entre la curva CIE y la base.
    """
    if group.layer == "permanent":
        return Lin, Lin
    if group.layer == "exterior":
        # La capa exterior aporta una fraccion de la luminancia de boca. No
        # se aplica el suelo Lin: con L20 nula debe apagarse por completo.
        Lmouth_scene = max(0.0, float(k_scene) * max(0.0, float(L20_scene)))
        Lmouth_design = max(0.0, float(group.total_L_design or 0.0))
        contribution = (
            float(group.L_design) * Lmouth_scene / Lmouth_design
            if Lmouth_design > 1e-9 else 0.0
        )
        return float(Lmouth_scene), max(0.0, float(contribution))
    Lth_scene = max(Lin, float(k_scene) * max(0.0, float(L20_scene)))
    if group.zone_type == ZoneType.THRESHOLD:
        total = Lth_scene
    else:
        total = _transition_total_for_group(
            group, zones, Lth_scene, Lin, speed_kmh,
        )
    profile = group.daylight_profile
    if isinstance(profile, dict) and profile.get("enabled"):
        penetration = max(
            0.0, float(profile.get("penetration_length_m", 0.0) or 0.0)
        )
        mouth_fraction = max(
            0.0,
            min(
                1.0,
                float(profile.get("mouth_contribution_pct", 0.0) or 0.0)
                / 100.0,
            ),
        )
        position = float(group.s_reference_m or 0.0)
        tube_length = float(profile.get("tube_length_m", 0.0) or 0.0)
        distance = (
            tube_length - position if group.portal == "B" else position
        )
        decay = (
            max(0.0, 1.0 - distance / penetration)
            if penetration > 1e-9 and 0.0 <= distance < penetration
            else 0.0
        )
        natural = Lth_scene * mouth_fraction * decay
        total = max(float(Lin), float(total) - natural)
    return float(total), max(0.0, float(total) - Lin)


def _build_layered_regulation_curves(
    groups: List[ControlGroup],
    L20_max_a: float,
    L20_max_b: float,
    k_factor_a: float,
    k_factor_b: float,
    Lin: float,
    speed_kmh: float,
    zones: TunnelZones,
) -> List[RegulationCurve]:
    """Curvas diurnas continuas; la conmutación nocturna es una escena aparte."""
    curves: List[RegulationCurve] = []
    n_pts = 13
    for group in groups:
        curve = RegulationCurve(
            group_id=group.group_id,
            group_name=group.name,
            zone_type=group.zone_type,
        )
        l20_max = L20_max_b if group.portal == "B" else L20_max_a
        k_scene = k_factor_b if group.portal == "B" else k_factor_a
        for i in range(n_pts):
            L20 = float(l20_max) * i / (n_pts - 1)
            _, contribution = _layer_required_luminance(
                group, L20, k_scene, Lin, speed_kmh, zones,
            )
            if group.layer == "permanent":
                dim = 100.0
            else:
                dim = (
                    contribution / group.L_design * 100.0
                    if group.L_design > 1e-9 else 0.0
                )
            dim = max(0.0, min(100.0, dim))
            curve.points.append(RegulationPoint(
                L20=round(L20, 0),
                L_required=round(contribution, 3),
                dimming_pct=round(dim, 3),
                dali_level=dimming_to_dali(dim),
            ))
        curves.append(curve)
    return curves


def build_control_plan(
    tube_id: str,
    L20_design: float,
    Lth_design: float,
    Lin: float,
    L_night: float,
    k_factor: float,
    speed_kmh: float,
    zones: TunnelZones,
    n_transition_groups: int = 2,
    protocol: str = "DALI",
    L20_design_b: Optional[float] = None,
    Lth_design_b: Optional[float] = None,
    k_factor_b: Optional[float] = None,
    driver_min_dim_pct: float = 0.1,
    scene_factors: Optional[List[float]] = None,
    L_night_normal: Optional[float] = None,
    exterior_enabled: bool = False,
    exterior_portal_a: bool = True,
    exterior_portal_b: bool = True,
    exterior_mouth_contribution_pct: float = 10.0,
    exterior_penetration_length_m: float = 60.0,
) -> TunnelControlPlan:
    """
    Plan multiescenario con dos capas físicas:

    * BASE permanente y regular de portal A a portal B.
    * REFUERZO diurno independiente en cada umbral/transición.

    Las escenas son anclas operativas; las curvas continuas se calculan a
    partir de L20 y no como porcentajes directos de la escena máxima.
    """
    warnings: List[str] = []

    protocol_key = str(protocol or "DALI").lower()
    if "smartec" in protocol_key:
        ctrl_protocol = ControlProtocol.SMARTEC
    elif "0-10" in protocol_key:
        ctrl_protocol = ControlProtocol.ANALOGUE
    else:
        ctrl_protocol = ControlProtocol.DALI

    L20_b = float(L20_design_b if L20_design_b is not None else L20_design)
    Lth_b = float(Lth_design_b if Lth_design_b is not None else Lth_design)
    k_b = float(k_factor_b if k_factor_b is not None else (
        Lth_b / L20_b if L20_b > 0 else k_factor
    ))
    min_dim = max(0.1, min(100.0, float(driver_min_dim_pct)))

    factors = list(scene_factors or [1.0, 0.70, 0.30, 0.05])
    if len(factors) != 4:
        warnings.append(
            "Los factores de escena deben contener cuatro valores; "
            "se usan 100 %, 70 %, 30 % y 5 %."
        )
        factors = [1.0, 0.70, 0.30, 0.05]
    factors = [max(0.0, min(1.0, float(value))) for value in factors]

    scene_defs = [
        (SceneType.SUNNY, "Soleado", factors[0]),
        (SceneType.NORMAL, "Normal", factors[1]),
        (SceneType.OVERCAST, "Cubierto", factors[2]),
        (SceneType.DUSK, "Crepuscular", factors[3]),
    ]
    scenes: List[ControlScene] = []
    for scene_id, (scene_type, name, factor) in enumerate(scene_defs, start=1):
        l20_a_scene = float(L20_design) * factor
        l20_b_scene = L20_b * factor
        scenes.append(ControlScene(
            scene_id=scene_id,
            scene_type=scene_type,
            name=name,
            L20_cd_m2=l20_a_scene,
            L20_b_cd_m2=l20_b_scene,
            description=(
                f"Ancla: L20 A={l20_a_scene:.0f} cd/m², "
                f"L20 B={l20_b_scene:.0f} cd/m²"
            ),
        ))
    night_normal = max(
        0.0,
        float(L_night_normal if L_night_normal is not None else Lin),
    )
    scenes.append(ControlScene(
        scene_id=5,
        scene_type=SceneType.NIGHT,
        name="Noche reducida",
        L20_cd_m2=0.0,
        L20_b_cd_m2=0.0,
        description=(
            f"BASE a {L_night:.2f} cd/m² y todos los refuerzos apagados"
        ),
    ))
    scenes.append(ControlScene(
        scene_id=6,
        scene_type=SceneType.NIGHT_NORMAL,
        name="Noche normal",
        L20_cd_m2=0.0,
        L20_b_cd_m2=0.0,
        description=(
            f"BASE a {night_normal:.2f} cd/m² y todos los refuerzos apagados"
        ),
    ))

    groups: List[ControlGroup] = [
        ControlGroup(
            group_id=1,
            name="BASE — Permanente A–B",
            zone_type=ZoneType.INTERIOR,
            zone_label="Todo el túnel",
            L_design=max(0.0, Lin),
            layer="permanent",
            portal=None,
            total_L_design=max(0.0, Lin),
            off_allowed=False,
            min_dim_pct=min_dim,
            notes=(
                "Disposición regular continua. Mantiene Lin de día y "
                "L_noche de noche; requiere verificación U0/Ul/TI en ambos."
            ),
        )
    ]
    gid = 2

    def add_threshold(portal: str, zone, Lth_portal: float) -> None:
        nonlocal gid
        if zone is None:
            return
        total_design = max(float(Lth_portal), Lin)
        groups.append(ControlGroup(
            group_id=gid,
            name=f"REF-{portal}-TH — Umbral {portal}",
            zone_type=ZoneType.THRESHOLD,
            zone_label=f"Umbral {portal}",
            L_design=max(0.0, total_design - Lin),
            layer="reinforcement",
            portal=portal,
            s_reference_m=(
                float(zone.s_start) + float(zone.s_end)
            ) / 2.0,
            total_L_design=total_design,
            off_allowed=True,
            min_dim_pct=min_dim,
            notes="Refuerzo sobre la contribución permanente de la BASE.",
        ))
        gid += 1

    def add_transition(portal: str, zone, Lth_portal: float) -> None:
        nonlocal gid
        if zone is None or n_transition_groups <= 0:
            return
        n_groups = max(1, min(4, int(n_transition_groups)))
        for index in range(n_groups):
            fraction = (index + 0.5) / n_groups
            s_reference = float(zone.s_start) + fraction * (
                float(zone.s_end) - float(zone.s_start)
            )
            placeholder = ControlGroup(
                group_id=gid,
                name=(
                    f"REF-{portal}-TR{index + 1} — "
                    f"Transición {portal} {index + 1}/{n_groups}"
                ),
                zone_type=ZoneType.TRANSITION,
                zone_label=f"Transición {portal} {index + 1}",
                L_design=0.0,
                layer="reinforcement",
                portal=portal,
                s_reference_m=s_reference,
                total_L_design=None,
                off_allowed=True,
                min_dim_pct=min_dim,
                notes="",
            )
            total_design = _transition_total_for_group(
                placeholder, zones, Lth_portal, Lin, speed_kmh,
            )
            placeholder.total_L_design = float(total_design)
            placeholder.L_design = max(0.0, float(total_design) - Lin)
            placeholder.notes = (
                f"Punto local s={s_reference:.1f} m. BASE aporta "
                f"{Lin:.2f} cd/m²; el grupo aporta la diferencia."
            )
            groups.append(placeholder)
            gid += 1

    add_threshold("A", zones.threshold, Lth_design)
    add_transition("A", zones.transition, Lth_design)
    if zones.threshold_b is not None:
        add_transition("B", zones.transition_b, Lth_b)
        add_threshold("B", zones.threshold_b, Lth_b)

    if exterior_enabled:
        enabled_portals = [
            portal
            for portal, active in (
                ("A", exterior_portal_a),
                (
                    "B",
                    exterior_portal_b and zones.threshold_b is not None,
                ),
            )
            if active
        ]
        warnings.append(
            "El aporte solar natural de portal(es) "
            f"{'/'.join(enabled_portals) or 'ninguno'} se usa para reducir "
            "el requisito artificial según L20; no constituye un grupo "
            "DALI ni una capa de luminarias."
        )
        tube_length = max(
            float(
                zone.s_end
            )
            for zone in (
                zones.threshold_b,
                zones.exit,
                zones.interior,
                zones.transition_b,
                zones.threshold,
            )
            if zone is not None
        )
        daylight_profile = {
            "enabled": True,
            "penetration_length_m": max(
                0.0, float(exterior_penetration_length_m or 0.0),
            ),
            "mouth_contribution_pct": max(
                0.0,
                min(
                    100.0,
                    float(exterior_mouth_contribution_pct or 0.0),
                ),
            ),
            "tube_length_m": tube_length,
        }
        for group in groups:
            if group.layer != "reinforcement":
                continue
            if (
                group.portal == "A" and not exterior_portal_a
            ) or (
                group.portal == "B" and not exterior_portal_b
            ):
                continue
            group.daylight_profile = dict(daylight_profile)
            design_l20 = L20_b if group.portal == "B" else L20_design
            design_k = k_b if group.portal == "B" else k_factor
            _total, artificial = _layer_required_luminance(
                group,
                design_l20,
                design_k,
                Lin,
                speed_kmh,
                zones,
            )
            group.L_design = artificial
            group.notes += (
                " Aporte solar natural descontado según L20 y distancia "
                "a la boca."
            )

    for scene in scenes:
        for group in groups:
            if scene.scene_type in (
                SceneType.NIGHT, SceneType.NIGHT_NORMAL
            ):
                if group.layer == "permanent":
                    night_target = (
                        night_normal
                        if scene.scene_type == SceneType.NIGHT_NORMAL
                        else L_night
                    )
                    dim = (
                        night_target / group.L_design * 100.0
                        if group.L_design > 0 else 0.0
                    )
                    if dim + 1e-9 < group.min_dim_pct:
                        warnings.append(
                            f"La BASE necesita {dim:.3f} % para "
                            f"{night_target:.2f} cd/m², por debajo del mínimo "
                            f"configurado del driver ({group.min_dim_pct:.3f} %)."
                        )
                else:
                    dim = 0.0
            else:
                scene_l20 = (
                    scene.L20_b_cd_m2
                    if group.portal == "B"
                    and scene.L20_b_cd_m2 is not None
                    else scene.L20_cd_m2
                )
                scene_k = k_b if group.portal == "B" else k_factor
                _, contribution = _layer_required_luminance(
                    group,
                    scene_l20,
                    scene_k,
                    Lin,
                    speed_kmh,
                    zones,
                )
                dim = (
                    contribution / group.L_design * 100.0
                    if group.L_design > 1e-9 else 0.0
                )
            dim = max(0.0, min(100.0, float(dim)))
            group.dimming_levels[scene.scene_id] = round(dim, 3)
            group.dali_levels[scene.scene_id] = dimming_to_dali(dim)

    # Saltos grandes no son un problema del modo continuo, pero sí de las
    # escenas almacenadas usadas como respaldo.
    ratio_violations: Dict[Tuple[str, str], float] = {}
    for group in groups:
        if group.layer != "reinforcement":
            continue
        levels = [
            group.dimming_levels.get(scene.scene_id, 0.0)
            for scene in scenes
        ]
        for index in range(1, len(levels)):
            previous, current = levels[index - 1], levels[index]
            if current > 0 and previous / current > 3.01:
                key = (scenes[index - 1].name, scenes[index].name)
                ratio_violations[key] = max(
                    ratio_violations.get(key, 0.0),
                    previous / current,
                )
    for (previous_name, current_name), ratio in ratio_violations.items():
        warnings.append(
            f"Salto de respaldo '{previous_name}'/'{current_name}' = "
            f"{ratio:.1f}:1; considerar una escena intermedia."
        )

    curves = _build_layered_regulation_curves(
        groups=groups,
        L20_max_a=float(L20_design),
        L20_max_b=L20_b,
        k_factor_a=float(k_factor),
        k_factor_b=k_b,
        Lin=float(Lin),
        speed_kmh=float(speed_kmh),
        zones=zones,
    )
    return TunnelControlPlan(
        tube_id=tube_id,
        protocol=ctrl_protocol,
        scenes=scenes,
        groups=groups,
        regulation_curves=curves,
        warnings=list(dict.fromkeys(warnings)),
        strategy={
            "architecture": "permanent_base_plus_portal_reinforcement",
            "base_scope": "portal_A_to_portal_B",
            "base_day_target_cd_m2": round(Lin, 3),
            "base_night_target_cd_m2": round(L_night, 3),
            "base_night_normal_target_cd_m2": round(night_normal, 3),
            "base_night_reduced_target_cd_m2": round(L_night, 3),
            "reinforcement_night_state": "off",
            "continuous_control": True,
            "independent_portals": zones.threshold_b is not None,
            "quality_verification_required_per_scene": [
                "Lavg", "U0", "Ul", "TI",
            ],
            "implementation_status": (
                "control_targets_defined_physical_layout_pending"
            ),
        },
    )


# ══════════════════════════════════════════════════════════════════
# EXPORT DALI (TUN-CTL-006)
# ══════════════════════════════════════════════════════════════════

def export_dali(plan: TunnelControlPlan) -> dict:
    """
    TUN-CTL-006: Genera la tabla de programación DALI.

    Formato:
      groups: lista de grupos con dirección DALI (GA 0-15)
      scenes: tabla scene_id → {group_id → DALI level (0-254)}

    Los grupos se asignan a grupos DALI (GA) comenzando en GA 0.
    Las escenas se mapean a DALI scenes (0-15) comenzando en escena 0.
    """
    if len(plan.groups) > 16:
        raise ValueError("DALI soporta máximo 16 grupos (GA 0-15)")
    if len(plan.scenes) > 16:
        raise ValueError("DALI soporta máximo 16 escenas por grupo")

    dali_groups = []
    for g in plan.groups:
        ga = g.group_id - 1  # DALI Group Address: 0-based
        dali_groups.append({
            "ga":         ga,
            "group_id":   g.group_id,
            "name":       g.name,
            "zone_type":  g.zone_type.value,
            "L_design":   g.L_design
        })

    # Tabla de escenas: scene_index → {ga → dali_level}
    dali_scenes = []
    for scene in plan.scenes:
        scene_entry = {
            "scene_index": scene.scene_id - 1,  # DALI scene: 0-based
            "scene_id":    scene.scene_id,
            "name":        scene.name,
            "L20":         scene.L20_cd_m2,
            "levels":      {}
        }
        for group in plan.groups:
            ga = group.group_id - 1
            level = group.dali_levels.get(scene.scene_id, 254)
            scene_entry["levels"][str(ga)] = level

        dali_scenes.append(scene_entry)

    return {
        "protocol":    "DALI IEC 62386",
        "tube_id":     plan.tube_id,
        "n_groups":    len(plan.groups),
        "n_scenes":    len(plan.scenes),
        "groups":      dali_groups,
        "scenes":      dali_scenes
    }


# ══════════════════════════════════════════════════════════════════
# EXPORT SMARTEC (TUN-CTL-007)
# ══════════════════════════════════════════════════════════════════

def export_smartec(plan: TunnelControlPlan) -> dict:
    """
    TUN-CTL-007: Genera la tabla de programación para Smartec.

    Formato: lista de circuitos con sus niveles (0-100%) por escena.
    Smartec usa porcentajes directos (no niveles DALI).
    """
    smartec_circuits = []
    for g in plan.groups:
        circuit = {
            "circuit_id": g.group_id,
            "name":       g.name,
            "zone":       g.zone_label,
            "L_design":   g.L_design,
            "scenes":     []
        }
        for scene in plan.scenes:
            circuit["scenes"].append({
                "scene_id":    scene.scene_id,
                "scene_name":  scene.name,
                "dimming_pct": g.dimming_levels.get(scene.scene_id, 100.0)
            })
        smartec_circuits.append(circuit)

    return {
        "protocol":  "Smartec",
        "tube_id":   plan.tube_id,
        "circuits":  smartec_circuits,
        "scenes":    [s.to_dict() for s in plan.scenes]
    }
