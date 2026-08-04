"""
SALVI Tunnel Engine — Clasificación del túnel
Implementa TUN-CLS-001, TUN-CLS-002, TUN-CLS-003
Norma: CIE 88:2004, Sección 4 (Fig. 4.1)
"""

import math
from .models import (
    TunnelCategory, OpticalCategory, DaylightingNeed,
    TunnelClassification, TunnelTube, TrafficDirection
)


def classify_geometric(length_m: float) -> TunnelCategory:
    """
    TUN-CLS-001: Clasificación geométrica preliminar por longitud.
    CIE 88:2004 — la distinción largo/corto tiene base en si se ve la salida.
    """
    if length_m < 25:
        return TunnelCategory.VERY_SHORT
    elif length_m < 75:
        return TunnelCategory.SHORT
    elif length_m < 125:
        return TunnelCategory.INTERMEDIATE
    else:
        return TunnelCategory.LONG


def classify_optical(
    length_m: float,
    stopping_distance_m: float,
    exit_visible: bool,
    daylight_penetration: str,   # "good" | "poor"
    wall_reflectance: float = 0.4,
    curvature_radius_m: float = None,
    gradient_pct: float = 0.0
) -> OpticalCategory:
    """
    TUN-CLS-002: Clasificación óptica.
    Un túnel es ópticamente largo si el conductor NO puede ver claramente
    la salida desde la posición a distancia SD antes del portal.

    CIE 88 Table 4.1:
    - Si el conductor puede ver a través del túnel (exit visible) Y
      hay buena penetración de luz diurna → ópticamente corto.
    - En caso contrario → ópticamente largo.
    """
    # Comprobar visibilidad geométrica simple por curvatura
    geometrically_visible = True
    if curvature_radius_m is not None and curvature_radius_m > 0:
        # Ángulo subtendido por el túnel desde el punto de referencia
        # Si el túnel curva más de ~10° no se ve la salida
        arc_angle_deg = math.degrees(length_m / curvature_radius_m)
        if arc_angle_deg > 10:
            geometrically_visible = False

    # Pendiente muy pronunciada puede ocultar la salida (simplificado)
    if abs(gradient_pct) > 3.0 and length_m > 100:
        geometrically_visible = False

    if exit_visible and geometrically_visible and daylight_penetration == "good":
        return OpticalCategory.SHORT
    else:
        return OpticalCategory.LONG


def classify_daylighting_need(
    length_m: float,
    optical_category: OpticalCategory,
    traffic_veh_h: int = 500,
    has_pedestrians: bool = False,
    wall_reflectance: float = 0.4,
    speed_kmh: float = 60.0
) -> DaylightingNeed:
    """
    TUN-CLS-003: Necesidad de iluminación diurna.
    CIE 88:2004 Fig. 4.1 y secciones 4.3–4.4.

    Reglas:
    - Túneles muy cortos (< 25 m) y ópticamente cortos con buenas
      condiciones → sin iluminación diurna.
    - Túneles ópticamente largos → siempre iluminación diurna.
    - Nivel normal vs reducido según tráfico, peatones y velocidad.
    """
    if optical_category == OpticalCategory.SHORT:
        if length_m < 25:
            return DaylightingNeed.NONE
        elif length_m < 75 and traffic_veh_h < 200 and not has_pedestrians:
            return DaylightingNeed.REDUCED
        elif length_m < 125 and traffic_veh_h < 150 and not has_pedestrians:
            return DaylightingNeed.REDUCED
        else:
            return DaylightingNeed.NORMAL

    # Ópticamente largo → siempre requiere iluminación diurna
    if traffic_veh_h >= 500 or has_pedestrians or speed_kmh >= 80:
        return DaylightingNeed.NORMAL
    else:
        return DaylightingNeed.REDUCED


def classify_tunnel(
    length_m: float,
    stopping_distance_m: float,
    exit_visible: bool,
    daylight_penetration: str,
    traffic_veh_h: int = 500,
    has_pedestrians: bool = False,
    speed_kmh: float = 80.0,
    wall_reflectance: float = 0.4,
    curvature_radius_m: float = None,
    gradient_pct: float = 0.0
) -> TunnelClassification:
    """
    Función principal de clasificación completa del túnel.
    Devuelve un TunnelClassification con toda la información de clasificación.
    """
    geo_cat = classify_geometric(length_m)

    opt_cat = classify_optical(
        length_m=length_m,
        stopping_distance_m=stopping_distance_m,
        exit_visible=exit_visible,
        daylight_penetration=daylight_penetration,
        wall_reflectance=wall_reflectance,
        curvature_radius_m=curvature_radius_m,
        gradient_pct=gradient_pct
    )

    daylight_need = classify_daylighting_need(
        length_m=length_m,
        optical_category=opt_cat,
        traffic_veh_h=traffic_veh_h,
        has_pedestrians=has_pedestrians,
        wall_reflectance=wall_reflectance,
        speed_kmh=speed_kmh
    )

    # Justificación textual
    justification_parts = [
        f"Longitud: {length_m:.0f} m → {geo_cat.value}.",
        f"Clasificación óptica: {'salida visible' if exit_visible else 'salida no visible'} desde SD={stopping_distance_m:.0f} m, "
        f"penetración de luz: {daylight_penetration} → {opt_cat.value}.",
        f"Necesidad de iluminación diurna: {daylight_need.value}."
    ]

    return TunnelClassification(
        geometric_category=geo_cat,
        optical_category=opt_cat,
        daylighting_need=daylight_need,
        exit_visible_from_sd=exit_visible,
        daylight_penetration=daylight_penetration,
        justification=" ".join(justification_parts)
    )
