"""
SALVI Tunnel Engine — Definición de zonas normativas
Implementa TUN-ZON-001 a TUN-ZON-006
Norma: CIE 88:2004, Capítulo 6
"""

from .models import (
    ZoneType, TunnelZone, TunnelZones, TrafficDirection,
    TunnelClassification, DaylightingNeed
)
from .required_luminance import cie88_transition_luminance


def calculate_threshold_length(stopping_distance_m: float) -> float:
    """
    TUN-ZON-002 / TUN-THR-001: Longitud de la zona umbral.
    CIE 88:2004 — La zona umbral tiene una longitud igual a la distancia de parada.
    Lth = SD (distancia de parada).
    """
    return stopping_distance_m


def calculate_transition_length(
    Lth: float,
    Lin: float,
    speed_kmh: float
) -> float:
    """
    TUN-ZON-003 / TUN-TRN-001: Longitud de la zona de transición.
    CIE 88:2004 Fig. 6.6 — La curva de adaptación visual es:
      L(t) = L_th × (1.9 + t)^(−1.4)   con t en segundos desde el inicio de transición.

    La zona de transición termina cuando L(t) = Lin:
      Lin = L_th × (1.9 + t_end)^(−1.4)
      → t_end = (L_th / Lin)^(1/1.4) − 1.9

    Longitud = v_ms × t_end
    """
    if Lin <= 0 or Lth <= Lin:
        return 0.0

    ratio = Lth / Lin
    if ratio <= 1.0:
        return 0.0

    # Tiempo hasta alcanzar Lin según CIE 88:2004 Fig. 6.6
    t_end = ratio ** (1.0 / 1.4) - 1.9
    if t_end <= 0:
        return 30.0  # mínimo práctico

    v_ms = speed_kmh / 3.6
    length = v_ms * t_end

    # Mínimo 30 m, máximo razonable 700 m
    return max(30.0, min(length, 700.0))


def calculate_exit_length(stopping_distance_m: float) -> float:
    """
    TUN-ZON-005: Zona de salida.
    CIE 88 recomienda una longitud mínima igual a la distancia de parada
    (o fracción de ella, según el modo — normal o reforzado).
    Simplificación: igual a SD.
    """
    return stopping_distance_m


def calculate_parting_length(stopping_distance_m: float) -> float:
    """
    TUN-ZON-006 / TUN-PAR-001: Zona posterior a la salida (parting zone).
    CIE 88 establece una longitud mínima aproximadamente igual a SD.
    """
    return stopping_distance_m


def build_zones(
    tube_length: float,
    stopping_distance_m: float,
    speed_kmh: float,
    Lth: float,
    Lin: float,
    classification: TunnelClassification,
    traffic_direction: TrafficDirection = TrafficDirection.ONE_WAY,
    L_night: float = 1.0,
    Lth_b: float = None,            # Portal B (bidireccional): orientación opuesta
    stopping_distance_b_m: float = None,  # SD portal B (pendiente invertida)
    threshold_length_override_m: float = None,
    threshold_length_b_override_m: float = None,
    transition_end_override_m: float = None,
    transition_end_b_override_m: float = None,
    exit_length_override_m: float = None,
    exit_luminance_ratio: float = 1.0,
) -> TunnelZones:
    """
    Construye todas las zonas normativas CIE 88 para un tubo/sentido.

    Coordenadas: s=0 es el portal de entrada, positivo hacia el interior.

    Zonas (s en metros desde el portal de entrada):
      Zona de acceso:   s ∈ [-SD, 0]         (exterior)
      Zona umbral:      s ∈ [0, SD]
      Zona transición:  s ∈ [SD, SD + L_tr]
      Zona interior:    s ∈ [SD + L_tr, L - SD_exit]
      Zona salida:      s ∈ [L - SD_exit, L]
      Parting zone:     s ∈ [L, L + SD]       (exterior, tras salida)
    """
    zones = TunnelZones(
        tube_id="",
        traffic_direction=traffic_direction,
        stopping_distance=stopping_distance_m
    )

    # ══════════════════════════════════════════════════════════════════════════
    # LAYOUT BIDIRECCIONAL (tubo único, dos sentidos)
    # CIE 88:2004 §6.3: ambas bocas son entradas → CTH + CTR en cada extremo.
    # Esquema: CTH_A | CTR_A | CIN | CTR_B | CTH_B   (sin zonas de salida)
    # ══════════════════════════════════════════════════════════════════════════
    if traffic_direction == TrafficDirection.TWO_WAY:
        # Portal B puede tener orientación opuesta → Lth distinto
        _Lth_b  = Lth_b if Lth_b is not None else Lth
        _SD_b   = stopping_distance_b_m if stopping_distance_b_m is not None else stopping_distance_m
        _Ltr_start_a = cie88_transition_luminance(
            0.0, 0.0, Lth, Lin, speed_kmh,
        )
        _Ltr_start_b = cie88_transition_luminance(
            0.0, 0.0, _Lth_b, Lin, speed_kmh,
        )
        strict_lth_len = calculate_threshold_length(stopping_distance_m)
        strict_lth_len_b = calculate_threshold_length(_SD_b)
        strict_ltr_len = calculate_transition_length(Lth, Lin, speed_kmh)
        strict_ltr_len_b = calculate_transition_length(_Lth_b, Lin, speed_kmh)
        lth_len = (float(threshold_length_override_m)
                   if threshold_length_override_m is not None else strict_lth_len)
        lth_len_b = (float(threshold_length_b_override_m)
                     if threshold_length_b_override_m is not None else strict_lth_len_b)
        ltr_len = (float(transition_end_override_m) - lth_len
                   if transition_end_override_m is not None else strict_ltr_len)
        ltr_len_b = (float(transition_end_b_override_m) - lth_len_b
                     if transition_end_b_override_m is not None else strict_ltr_len_b)
        if ltr_len <= 0 or ltr_len_b <= 0:
            raise ValueError("El fin de transición de proyecto debe quedar después de la zona umbral")

        # Verificar espacio suficiente (layout asimétrico)
        total_end = lth_len + lth_len_b + ltr_len + ltr_len_b
        cin_len   = tube_length - total_end

        if cin_len < 0:
            # Túnel corto bidireccional: truncar proporcionalmente
            half = tube_length / 2.0
            lth_avg = (lth_len + lth_len_b) / 2.0
            if lth_avg >= half:
                lth_len   = half * 0.45
                lth_len_b = half * 0.45
                ltr_len   = half * 0.10
                ltr_len_b = half * 0.10
            else:
                avail_a = half - lth_len
                avail_b = half - lth_len_b
                total_tr = ltr_len + ltr_len_b
                if total_tr > 0:
                    ltr_len   = max(0.0, avail_a * ltr_len   / total_tr)
                    ltr_len_b = max(0.0, avail_b * ltr_len_b / total_tr)
            cin_len = max(1.0, tube_length - lth_len - lth_len_b - ltr_len - ltr_len_b)
            zones.warnings.append(
                f"⚠️ Túnel bidireccional corto: layout truncado a "
                f"Lth_A={lth_len:.0f} m, Lth_B={lth_len_b:.0f} m, "
                f"Ltr_A={ltr_len:.0f} m, Ltr_B={ltr_len_b:.0f} m."
            )

        # Fronteras (asimétrico — SD puede diferir por pendiente)
        s_cth_a_end = lth_len
        s_ctr_a_end = lth_len + ltr_len
        s_cin_end   = tube_length - lth_len_b - ltr_len_b
        s_ctr_b_end = tube_length - lth_len_b

        zones.threshold = TunnelZone(
            zone_type=ZoneType.THRESHOLD,
            s_start=0.0, s_end=s_cth_a_end,
            L_start=Lth, L_end=_Ltr_start_a, L_min_required=Lth,
            strict_length_m=strict_lth_len,
            project_override=threshold_length_override_m is not None,
            description=f"Zona umbral Portal A, Lth={Lth:.1f} cd/m², L={lth_len:.0f} m"
        )
        zones.transition = TunnelZone(
            zone_type=ZoneType.TRANSITION,
            s_start=s_cth_a_end, s_end=s_ctr_a_end,
            L_start=_Ltr_start_a, L_end=Lin, L_min_required=Lin,
            strict_length_m=strict_ltr_len,
            transition_scale=(ltr_len / strict_ltr_len if strict_ltr_len > 0 else 1.0),
            project_override=transition_end_override_m is not None,
            description=f"Zona transición Portal A, L: {Lth:.1f}→{Lin:.1f} cd/m², L={ltr_len:.0f} m"
        )
        if cin_len > 0:
            zones.interior = TunnelZone(
                zone_type=ZoneType.INTERIOR,
                s_start=s_ctr_a_end, s_end=s_cin_end,
                L_start=Lin, L_end=Lin, L_min_required=Lin,
                description=f"Zona interior, Lin={Lin:.2f} cd/m², L={cin_len:.0f} m"
            )
        zones.transition_b = TunnelZone(
            zone_type=ZoneType.TRANSITION,
            s_start=s_cin_end, s_end=s_ctr_b_end,
            L_start=Lin, L_end=_Ltr_start_b, L_min_required=Lin,
            strict_length_m=strict_ltr_len_b,
            transition_scale=(ltr_len_b / strict_ltr_len_b if strict_ltr_len_b > 0 else 1.0),
            project_override=transition_end_b_override_m is not None,
            description=f"Zona transición Portal B, L: {Lin:.1f}→{_Lth_b:.1f} cd/m², L={ltr_len_b:.0f} m"
        )
        zones.threshold_b = TunnelZone(
            zone_type=ZoneType.THRESHOLD,
            s_start=s_ctr_b_end, s_end=tube_length,
            L_start=_Ltr_start_b, L_end=_Lth_b, L_min_required=_Lth_b,
            strict_length_m=strict_lth_len_b,
            project_override=threshold_length_b_override_m is not None,
            description=f"Zona umbral Portal B, Lth_B={_Lth_b:.1f} cd/m², L={lth_len_b:.0f} m, SD_B={_SD_b:.0f} m"
        )
        return zones

    # ── ZONA DE ACCESO (exterior) — solo para sentido único ──
    if classification.daylighting_need != DaylightingNeed.NONE:
        zones.access = TunnelZone(
            zone_type=ZoneType.ACCESS,
            s_start=-stopping_distance_m,
            s_end=0.0,
            L_start=0.0,  # Luminancia exterior (no aplica para calzada)
            L_end=0.0,
            description="Zona exterior de acceso al portal (distancia de parada)"
        )

    # ── ZONA UMBRAL ──
    strict_lth_length = calculate_threshold_length(stopping_distance_m)
    strict_exit_length = calculate_exit_length(stopping_distance_m)
    lth_length = (float(threshold_length_override_m)
                  if threshold_length_override_m is not None else strict_lth_length)
    exit_length = (float(exit_length_override_m)
                   if exit_length_override_m is not None else strict_exit_length)
    s_exit_start_raw = tube_length - exit_length

    # Túnel extremadamente corto: ni siquiera cabe la zona umbral completa
    if lth_length >= tube_length:
        zones.warnings.append(
            f"⛔ Túnel extremadamente corto: longitud ({tube_length:.0f} m) ≤ distancia "
            f"de parada ({stopping_distance_m:.0f} m). El cálculo CIE 88:2004 no es "
            f"aplicable. Consultar el técnico responsable."
        )
        lth_length = tube_length * 0.5  # fallback para no romper la geometría

    _Ltr_start = cie88_transition_luminance(
        0.0, 0.0, Lth, Lin, speed_kmh,
    )
    zones.threshold = TunnelZone(
        zone_type=ZoneType.THRESHOLD,
        s_start=0.0,
        s_end=lth_length,
        L_start=Lth,
        L_end=_Ltr_start,
        L_min_required=Lth,
        strict_length_m=strict_lth_length,
        project_override=threshold_length_override_m is not None,
        description=f"Zona umbral, Lth={Lth:.1f} cd/m², longitud={lth_length:.0f} m"
    )

    # ── ZONA DE TRANSICIÓN ──
    strict_ltr_length = calculate_transition_length(Lth, Lin, speed_kmh)
    ltr_length = (float(transition_end_override_m) - lth_length
                  if transition_end_override_m is not None else strict_ltr_length)
    # Clase 1 OC 36/2015 no impone Lth. El motor conserva Lin como nivel de
    # continuidad, de modo que no existe salto de adaptación ni, por tanto,
    # una zona de transición que construir. No debe tratarse como un error de
    # geometría de proyecto.
    no_transition_required = (
        transition_end_override_m is None and Lth <= Lin + 1e-9
    )
    if ltr_length <= 0 and not no_transition_required:
        raise ValueError("El fin de transición de proyecto debe quedar después de la zona umbral")
    s_tr_start = lth_length
    s_tr_end   = lth_length + max(0.0, ltr_length)

    if not no_transition_required:
        zones.transition = TunnelZone(
            zone_type=ZoneType.TRANSITION,
            s_start=s_tr_start,
            s_end=s_tr_end,
            L_start=_Ltr_start,
            L_end=Lin,
            L_min_required=Lin,
            strict_length_m=strict_ltr_length,
            transition_scale=(ltr_length / strict_ltr_length if strict_ltr_length > 0 else 1.0),
            project_override=transition_end_override_m is not None,
            description=f"Zona transición, L: {Lth:.1f}→{Lin:.1f} cd/m², longitud={ltr_length:.0f} m"
        )

    # ── ZONA INTERIOR ──
    # s_exit_start nunca puede ser anterior al fin de la zona umbral
    s_exit_start = max(s_exit_start_raw, lth_length)
    s_int_start  = s_tr_end
    s_int_end    = max(s_exit_start, s_int_start)  # No puede ser negativa

    if s_int_end > s_int_start:
        zones.interior = TunnelZone(
            zone_type=ZoneType.INTERIOR,
            s_start=s_int_start,
            s_end=s_int_end,
            L_start=Lin,
            L_end=Lin,
            L_min_required=Lin,
            description=f"Zona interior, Lin={Lin:.2f} cd/m²"
        )

    # ── DETECCIÓN DE TÚNEL CORTO ─────────────────────────────────
    # CIE 88:2004 §6.4: si la zona de transición solapa la zona de salida,
    # el túnel es demasiado corto para el esquema completo de 4 zonas.
    if s_tr_end > s_exit_start:
        overlap_m = s_tr_end - s_exit_start
        zones.warnings.append(
            f"⚠️ Túnel corto (CIE 88:2004 §6.4): la zona de transición solapa "
            f"la zona de salida en {overlap_m:.0f} m. No existe zona interior. "
            f"Verificar que la longitud del túnel ({tube_length:.0f} m) es suficiente "
            f"para el perfil fotométrico requerido."
        )
        # Truncar transición para que no supere el inicio de la zona de salida
        zones.transition = TunnelZone(
            zone_type=ZoneType.TRANSITION,
            s_start=s_tr_start,
            s_end=s_exit_start,   # truncada
            L_start=_Ltr_start,
            L_end=Lin,
            L_min_required=Lin,
            strict_length_m=strict_ltr_length,
            transition_scale=((s_exit_start - s_tr_start) / strict_ltr_length if strict_ltr_length > 0 else 1.0),
            project_override=transition_end_override_m is not None,
            description=(
                f"Zona transición TRUNCADA (túnel corto), L: {Lth:.1f}→{Lin:.1f} cd/m², "
                f"longitud={s_exit_start - s_tr_start:.0f} m "
                f"(teórica {ltr_length:.0f} m — insuficiente)"
            )
        )

    # ── ZONA DE SALIDA ──
    # Por defecto la salida mantiene el nivel interior (100 % de Lin).
    # El porcentaje puede fijarse por proyecto, manteniendo una transicion
    # continua desde el interior.
    try:
        exit_ratio = max(0.0, float(exit_luminance_ratio))
    except (TypeError, ValueError):
        exit_ratio = 1.0
    exit_target = max(0.0, float(Lin)) * exit_ratio
    zones.exit = TunnelZone(
        zone_type=ZoneType.EXIT,
        s_start=s_exit_start,
        s_end=tube_length,
        L_start=Lin,
        L_end=exit_target,
        L_min_required=exit_target,
        strict_length_m=strict_exit_length,
        project_override=(
            exit_length_override_m is not None
            or abs(exit_ratio - 1.0) > 1e-9
        ),
        description=(
            f"Zona salida, longitud={tube_length - s_exit_start:.0f} m, "
            f"L: {Lin:.2f}->{exit_target:.2f} cd/m2"
        )
    )

    # ── ZONA POSTERIOR A LA SALIDA (parting zone) ──
    parting_length = calculate_parting_length(stopping_distance_m)
    zones.parting = TunnelZone(
        zone_type=ZoneType.PARTING,
        s_start=tube_length,
        s_end=tube_length + parting_length,
        L_start=0.0,
        L_end=0.0,
        L_min_required=L_night,
        description=f"Parting zone exterior, longitud={parting_length:.0f} m"
    )

    return zones


def zones_to_dict(zones: TunnelZones) -> dict:
    """Serializa las zonas a dict para la API.
    Para bidireccional incluye transition_b y threshold_b con
    zone_type = 'transition_b' / 'threshold_b' para que el motor
    de luminarias las etiquete correctamente (CTR·B / CTH·B).
    """
    result = {}
    # Zonas estándar (sentido único y bidireccional Portal A + interior)
    for attr in ['access', 'threshold', 'transition', 'interior', 'exit', 'parting']:
        zone: TunnelZone = getattr(zones, attr, None)
        if zone:
            result[attr] = {
                'zone_type': attr,
                'type': zone.zone_type.value,
                's_start': round(zone.s_start, 2),
                's_end': round(zone.s_end, 2),
                'length': round(zone.length, 2),
                'L_start': round(zone.L_start, 2),
                'L_end': round(zone.L_end, 2),
                'L_min_required': round(zone.L_min_required, 2),
                'description': zone.description,
                'strict_length_m': (round(zone.strict_length_m, 2)
                                    if zone.strict_length_m is not None else None),
                'transition_scale': round(zone.transition_scale, 5),
                'project_override': zone.project_override,
            }
    # Zonas exclusivas de bidireccional (Portal B)
    for attr in ['transition_b', 'threshold_b']:
        zone: TunnelZone = getattr(zones, attr, None)
        if zone:
            result[attr] = {
                'zone_type': attr,          # 'transition_b' / 'threshold_b'
                'type': zone.zone_type.value,
                's_start': round(zone.s_start, 2),
                's_end': round(zone.s_end, 2),
                'length': round(zone.length, 2),
                'L_start': round(zone.L_start, 2),
                'L_end': round(zone.L_end, 2),
                'L_min_required': round(zone.L_min_required, 2),
                'description': zone.description,
                'strict_length_m': (round(zone.strict_length_m, 2)
                                    if zone.strict_length_m is not None else None),
                'transition_scale': round(zone.transition_scale, 5),
                'project_override': zone.project_override,
            }
    return result
