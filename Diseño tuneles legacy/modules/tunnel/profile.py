"""
SALVI Tunnel Engine — Perfil longitudinal de luminancia
Implementa TUN-PRO-001, TUN-THR-*, TUN-TRN-*, TUN-INT-*, TUN-EXT-*, TUN-PAR-*
Norma: CIE 88:2004, Capítulos 23–30
"""

import math
from typing import List
from .models import (
    ZoneType, ProfilePoint, LuminanceProfile, TunnelZones,
    TrafficDirection
)
from .required_luminance import (
    cie88_threshold_luminance,
    cie88_transition_luminance,
    transition_envelope,
)


def _transition_curve_cie(
    s: float,
    s_start: float,
    s_end: float,
    Lth: float,
    L_end: float,
    speed_kmh: float
) -> float:
    """
    TUN-TRN-001: Curva de adaptación visual CIE 88:2004 Fig. 6.6.

    Fórmula exacta de la norma:
      L(t) = L_th × (1.9 + t)^(−1.4)
    donde t son segundos desde el inicio de la zona de transición.

    A t=0 (inicio de transición): L = L_th × (1.9)^(−1.4) ≈ 0.41 × L_th.
    La segunda mitad de la zona umbral desciende previamente hasta ese mismo
    valor, por lo que el perfil normativo completo es continuo.

    La zona de transición termina cuando L(t) = Lin.
    """
    if s_end <= s_start or speed_kmh <= 0:
        return L_end

    return cie88_transition_luminance(
        s, s_start, Lth, L_end, speed_kmh,
    )


def _stepped_profile(
    s_start: float,
    s_end: float,
    L_start: float,
    L_end: float,
    n_steps: int = 4,
    max_ratio: float = 3.0
) -> List[tuple]:
    """
    TUN-TRN-003 / TUN-TRN-004: Perfil escalonado en zona de transición.
    Genera escalones de luminancia con ratio máximo entre escalones ≤ 3.
    Devuelve lista de (s_start, s_end, L) para cada escalón.
    """
    if n_steps < 1:
        return [(s_start, s_end, L_start)]

    # Distribución geométrica de escalones
    total_length = s_end - s_start
    step_length = total_length / n_steps

    # Calcular niveles de luminancia por escalones geométricos
    ratio_total = L_start / L_end if L_end > 0 else 1.0
    # Ratio por escalón = ratio_total^(1/n_steps)
    ratio_per_step = ratio_total ** (1 / n_steps)

    # Verificar que el ratio por escalón no supere max_ratio
    if ratio_per_step > max_ratio:
        # Aumentar número de escalones necesario
        import math
        n_steps_min = math.ceil(math.log(ratio_total) / math.log(max_ratio))
        n_steps = n_steps_min
        step_length = total_length / n_steps
        ratio_per_step = ratio_total ** (1 / n_steps)

    steps = []
    L_current = L_start
    for i in range(n_steps):
        s_i = s_start + i * step_length
        s_i_end = s_start + (i + 1) * step_length
        L_next = L_current / ratio_per_step
        L_next = max(L_next, L_end)
        steps.append((s_i, s_i_end, L_current))
        L_current = L_next

    return steps


def build_profile(
    tube_length: float,
    stopping_distance: float,
    speed_kmh: float,
    Lth: float,
    Lin: float,
    L_night: float,
    zones: TunnelZones,
    step_size: float = 1.0,
    use_stepped: bool = False,
    n_steps_transition: int = 4,
    Lth_b: float = None,   # Portal B (puede diferir de Lth si orientación opuesta)
) -> LuminanceProfile:
    """
    TUN-PRO-001: Genera el perfil longitudinal completo de luminancia.

    El perfil cubre desde s=0 (portal) hasta s=tube_length (salida).
    Resolución: step_size metros.

    Zonas segun CIE 88:
    0 -> SD:                 Umbral (Lth plano en la primera mitad y rampa
                              lineal hasta aprox. 0.4 Lth en la segunda)
    SD -> SD + Ltr:          Transicion CIE (continua desde la rampa hasta Lin)
    SD + Ltr -> L - SD_exit: Interior (L = Lin, constante)
    L - SD_exit -> L:        Salida (L sube desde Lin)
    """
    profile = LuminanceProfile(
        tube_id=zones.tube_id if zones.tube_id else "T1",
        traffic_direction=zones.traffic_direction,
        design_speed_kmh=speed_kmh,
        stopping_distance_m=stopping_distance,
        Lth=Lth,
        Lin=Lin,
        L_night=L_night,
        zones=zones
    )

    # Obtener límites de zonas
    th   = zones.threshold
    tr   = zones.transition
    interior = zones.interior
    ex   = zones.exit
    tr_b  = getattr(zones, 'transition_b', None)
    th_b  = getattr(zones, 'threshold_b',  None)
    _Lth_b = Lth_b if Lth_b is not None else Lth   # Portal B luminance
    _Ltr_start_a = cie88_transition_luminance(
        0.0, 0.0, Lth, Lin, speed_kmh,
    )
    _Ltr_start_b = cie88_transition_luminance(
        0.0, 0.0, _Lth_b, Lin, speed_kmh,
    )

    # Generar puntos a lo largo del túnel
    s = 0.0
    while s <= tube_length + step_size / 2:
        s_current = min(s, tube_length)

        # ── ZONA UMBRAL Portal A ──
        if th and th.s_start <= s_current <= th.s_end:
            L = cie88_threshold_luminance(
                s_current, th.s_start, th.s_end, Lth, Lin,
            )
            zone = ZoneType.THRESHOLD

        # ── ZONA DE TRANSICIÓN Portal A ──
        elif tr and tr.s_start < s_current <= tr.s_end:
            if use_stepped:
                steps = _stepped_profile(
                    tr.s_start, tr.s_end,
                    _Ltr_start_a, Lin, n_steps_transition
                )
                L = Lin
                for (ss, se, Ls) in steps:
                    if ss <= s_current <= se:
                        L = Ls
                        break
            else:
                L = _transition_curve_cie(
                    s_current, tr.s_start, tr.s_end, Lth, Lin,
                    speed_kmh * tr.transition_scale,
                )
            zone = ZoneType.TRANSITION

        # ── ZONA INTERIOR ──
        elif interior and interior.s_start < s_current <= interior.s_end:
            L = Lin
            zone = ZoneType.INTERIOR

        # ── ZONA DE TRANSICIÓN Portal B (bidireccional — curva espejo) ──
        elif tr_b and tr_b.s_start < s_current <= tr_b.s_end:
            if use_stepped:
                # Espejo: evaluar por distancia recorrida desde el Portal B.
                steps = _stepped_profile(
                    0.0, tr_b.s_end - tr_b.s_start,
                    _Ltr_start_b, Lin, n_steps_transition
                )
                distance_from_portal = tr_b.s_end - s_current
                L = Lin
                for (ss, se, Ls) in steps:
                    if ss <= distance_from_portal <= se:
                        L = Ls
                        break
            else:
                # Curva CIE espejo: invertir el eje s
                s_mirror = tr_b.s_end - (s_current - tr_b.s_start)
                L = _transition_curve_cie(
                    s_mirror, tr_b.s_start, tr_b.s_end, _Lth_b, Lin,
                    speed_kmh * tr_b.transition_scale,
                )
            zone = ZoneType.TRANSITION

        # ── ZONA UMBRAL Portal B (bidireccional) ──
        elif th_b and th_b.s_start < s_current <= th_b.s_end:
            L = cie88_threshold_luminance(
                s_current, th_b.s_start, th_b.s_end,
                _Lth_b, Lin, reverse=True,
            )
            zone = ZoneType.THRESHOLD

        # ── ZONA DE SALIDA (sentido único) ──
        elif ex and ex.s_start < s_current <= ex.s_end:
            exit_target = max(
                0.0,
                float(getattr(ex, "L_min_required", Lin) or Lin),
            )
            exit_span = max(0.0, float(ex.s_end) - float(ex.s_start))
            exit_fraction = (
                min(1.0, max(0.0, (s_current - float(ex.s_start)) / exit_span))
                if exit_span > 1e-9 else 1.0
            )
            L = float(Lin) + exit_fraction * (exit_target - float(Lin))
            zone = ZoneType.EXIT

        else:
            L = Lin if Lin > 0 else 0
            zone = ZoneType.INTERIOR

        # En tuneles cortos la cola CIE no desaparece al truncar
        # geometricamente la zona de transicion.
        L_tail, _ = transition_envelope(
            s_current,
            [
                candidate
                for candidate in ((tr, 1.0), (tr_b, -1.0))
                if candidate[0]
            ],
            Lth=Lth,
            Lth_b=_Lth_b,
            Lin=Lin,
            speed_kmh=speed_kmh,
        )
        # En salida un objetivo de proyecto inferior a Lin debe poder aplicarse.
        if zone != ZoneType.EXIT:
            L = max(L, L_tail)

        profile.add_point(round(s_current, 2), round(max(L, 0), 3), zone)

        if s_current >= tube_length:
            break
        s += step_size

    return profile


def build_night_profile(
    tube_length: float,
    L_night: float,
    step_size: float = 5.0
) -> List[ProfilePoint]:
    """Perfil nocturno simplificado: nivel uniforme en todo el túnel."""
    points = []
    s = 0.0
    while s <= tube_length:
        points.append(ProfilePoint(s=round(s, 1), L_required=L_night, zone=ZoneType.NIGHT))
        s += step_size
    return points


def validate_profile(profile: LuminanceProfile) -> dict:
    """
    TUN-VAL-003 a TUN-VAL-005: Validación del perfil longitudinal.
    Comprueba:
    - Lth se mantiene en la primera mitad del umbral y la rampa normativa
      llega sin salto al inicio de la transicion
    - Lin se mantiene en zona interior
    - No hay escalones con ratio > 3
    - La transición es continua/monótona
    """
    errors = []
    warnings = []

    points = profile.points
    if not points:
        return {"valid": False, "errors": ["Perfil vacío"], "warnings": []}

    # Validar zona umbral. CIE 88 permite la rampa del ultimo 50 % hasta
    # el inicio de la curva de transicion; por tanto no se exige Lth plano
    # en toda la zona.
    threshold_points = [p for p in points if p.zone == ZoneType.THRESHOLD]
    threshold_specs = []
    if profile.zones:
        if profile.zones.threshold:
            threshold_specs.append((profile.zones.threshold, profile.Lth, False, "A"))
        if profile.zones.threshold_b:
            threshold_level_b = float(
                profile.zones.threshold_b.L_end or profile.Lth
            )
            threshold_specs.append((
                profile.zones.threshold_b,
                threshold_level_b,
                True,
                "B",
            ))

    if threshold_specs:
        for threshold_zone, threshold_level, reverse, portal in threshold_specs:
            zone_points = [
                p for p in points
                if threshold_zone.s_start - 1e-6 <= p.s <= threshold_zone.s_end + 1e-6
            ]
            if not zone_points:
                continue
            L_min_thr = min(p.L_required for p in zone_points)
            transition_boundary = (
                threshold_zone.s_start if reverse else threshold_zone.s_end
            )
            L_start_transition = cie88_threshold_luminance(
                transition_boundary,
                threshold_zone.s_start,
                threshold_zone.s_end,
                threshold_level,
                profile.Lin,
                reverse=reverse,
            )
            if L_min_thr < L_start_transition * 0.95:
                errors.append(
                    f"Zona umbral {portal}: Lmin={L_min_thr:.2f} < "
                    f"inicio transicion={L_start_transition:.2f} cd/m2 (margen 5%)"
                )
    elif threshold_points:
        # Compatibilidad con perfiles antiguos sin metadatos de zonas.
        L_min_thr = min(p.L_required for p in threshold_points)
        if L_min_thr < profile.Lth * 0.95:
            errors.append(
                f"Zona umbral: Lmin={L_min_thr:.2f} < Lth={profile.Lth:.2f} cd/m2 (margen 5%)"
            )

    # Validar zona interior
    interior_points = [p for p in points if p.zone == ZoneType.INTERIOR]
    if interior_points:
        L_min_int = min(p.L_required for p in interior_points)
        if L_min_int < profile.Lin * 0.95:
            errors.append(
                f"Zona interior: Lmin={L_min_int:.2f} < Lin={profile.Lin:.2f} cd/m² (margen 5%)"
            )

    # Validar monotonía en transición
    transition_points = sorted(
        [p for p in points if p.zone == ZoneType.TRANSITION],
        key=lambda p: p.s
    )
    if len(transition_points) >= 2:
        for i in range(1, len(transition_points)):
            ratio = (transition_points[i - 1].L_required /
                     transition_points[i].L_required
                     if transition_points[i].L_required > 0 else 999)
            if ratio > 3.01:
                warnings.append(
                    f"Transición en s={transition_points[i].s:.0f} m: "
                    f"ratio={ratio:.2f} > 3.0 (CIE 88 TUN-TRN-004)"
                )

    # Niveles mínimos
    if profile.Lth < 50 and profile.design_speed_kmh >= 80:
        warnings.append(f"Lth={profile.Lth:.1f} < 50 cd/m² (recomendado para v≥80 km/h)")

    if profile.Lin < 1.0:
        warnings.append(f"Lin={profile.Lin:.2f} < 1.0 cd/m² (verificar tráfico y velocidad)")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "n_points": len(points),
        "Lth_actual": threshold_points[0].L_required if threshold_points else 0,
        "Lin_actual": interior_points[0].L_required if interior_points else 0
    }


def profile_to_chart_data(profile: LuminanceProfile) -> dict:
    """
    Convierte el perfil a formato adecuado para gráfica Recharts en React.
    Devuelve series separadas por zona para colorear diferente.
    """
    data = []
    for p in profile.points:
        data.append({
            "s": p.s,
            "L": round(p.L_required, 3),
            "zone": p.zone.value
        })

    # Líneas de referencia
    references = {
        "Lth": profile.Lth,
        "Lin": profile.Lin,
        "L_night": profile.L_night
    }

    # Límites de zonas para área de fondo
    zone_boundaries = []
    zones = profile.zones
    if zones:
        for attr in ['threshold', 'transition', 'interior', 'exit']:
            z = getattr(zones, attr, None)
            if z:
                zone_boundaries.append({
                    "zone": z.zone_type.value,
                    "s_start": z.s_start,
                    "s_end": z.s_end,
                    "label": z.zone_type.value.replace("_", " ").title()
                })

    return {
        "data": data,
        "references": references,
        "zone_boundaries": zone_boundaries,
        "tunnel_length": profile.points[-1].s if profile.points else 0
    }
