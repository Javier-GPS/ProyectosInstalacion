"""Fuente unica de luminancia requerida y malla longitudinal de validacion.

La curva continua CIE 88 se usa desde el perfil, el control y los dos
validadores del layout. Centralizarla evita que una misma posicion tenga
objetivos distintos segun el modulo que la consulte.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def _zone_value(zone, name: str, default=None):
    """Lee una zona de dominio o un diccionario procedente de la API."""
    if isinstance(zone, Mapping):
        if name == "zone_type":
            return zone.get("zone_type", zone.get("type", default))
        if name == "L_required":
            return zone.get("L_required", zone.get("L_min_required", default))
        return zone.get(name, default)
    if name == "L_required":
        return getattr(zone, "L_required", getattr(zone, "L_min_required", default))
    return getattr(zone, name, default)


def cie88_transition_luminance(
    s: float,
    s_start: float,
    Lth: float,
    Lin: float,
    speed_kmh: float,
) -> float:
    """L(t) = Lth * (1.9 + t)^(-1.4), con suelo Lin."""
    v_ms = max(float(speed_kmh) / 3.6, 0.1)
    t_s = max(0.0, (float(s) - float(s_start)) / v_ms)
    return max(float(Lth) * (1.9 + t_s) ** (-1.4), float(Lin))


def cie88_threshold_luminance(
    s: float,
    s_start: float,
    s_end: float,
    Lth: float,
    Lin: float,
    *,
    reverse: bool = False,
) -> float:
    """Perfil CIE 88 en Umbral, continuo con la zona de Transicion.

    Se mantiene ``Lth`` durante la primera mitad recorrida desde el portal y
    se reduce linealmente durante la segunda mitad hasta el valor inicial de
    la curva de adaptacion: ``Lth * 1.9**-1.4`` (aprox. ``0.4 * Lth``).
    ``reverse=True`` aplica el mismo perfil desde el portal B hacia ``-s``.
    """
    start = float(s_start)
    end = float(s_end)
    length = end - start
    if length <= 1e-9:
        return max(float(Lth), float(Lin))

    position = min(max(float(s), start), end)
    distance_from_portal = (
        end - position if reverse else position - start
    )
    progress = min(max(distance_from_portal / length, 0.0), 1.0)
    if progress <= 0.5:
        return max(float(Lth), float(Lin))

    transition_start = cie88_transition_luminance(
        0.0, 0.0, Lth, Lin, 1.0,
    )
    fraction = (progress - 0.5) / 0.5
    return max(
        float(Lth) + fraction * (transition_start - float(Lth)),
        float(Lin),
    )


def daylight_contribution_for_zone(
    zone,
    s: float,
    *,
    Lth: float,
    Lth_b: float,
) -> float:
    """Natural daylight contribution entering from the enabled portals."""
    profile = _zone_value(zone, "daylight_profile", None)
    if not isinstance(profile, Mapping) or not profile.get("enabled"):
        return 0.0

    penetration = max(
        0.0, float(profile.get("penetration_length_m", 0.0) or 0.0)
    )
    mouth_fraction = max(
        0.0,
        min(1.0, float(profile.get("mouth_contribution_pct", 0.0) or 0.0) / 100.0),
    )
    if penetration <= 1e-9 or mouth_fraction <= 1e-9:
        return 0.0

    exponent = max(
        0.1, min(5.0, float(profile.get("decay_exponent", 1.0) or 1.0))
    )
    tube_length = max(
        0.0, float(profile.get("tube_length_m", 0.0) or 0.0)
    )

    def decay(distance):
        if distance < 0.0 or distance >= penetration:
            return 0.0
        return max(0.0, 1.0 - distance / penetration) ** exponent

    position = float(s)
    contribution = 0.0
    if profile.get("portal_a", True):
        contribution += max(0.0, float(Lth)) * mouth_fraction * decay(position)
    if profile.get("portal_b", False):
        contribution += (
            max(0.0, float(Lth_b))
            * mouth_fraction
            * decay(tube_length - position)
        )
    return max(0.0, contribution)


def required_luminance_for_zone(
    zone,
    s: float,
    *,
    Lth: float,
    Lth_b: float,
    Lin: float,
    speed_kmh: float,
) -> float:
    """Objetivo continuo de una zona de calculo en la posicion ``s``."""
    zone_type = str(_zone_value(zone, "zone_type", "") or "").lower()
    if "threshold" in zone_type:
        total = cie88_threshold_luminance(
            s,
            float(_zone_value(zone, "s_start")),
            float(_zone_value(zone, "s_end")),
            Lth_b if zone_type.endswith("_b") else Lth,
            Lin,
            reverse=zone_type.endswith("_b"),
        )
    elif "exit" in zone_type:
        # La salida parte de Lin y puede terminar en un objetivo de proyecto
        # distinto. Se interpola para evitar el salto artificial observado
        # cuando el requisito de salida era un valor constante.
        start = float(_zone_value(zone, "s_start", s) or s)
        end = float(_zone_value(zone, "s_end", start) or start)
        target = max(
            0.0,
            float(_zone_value(zone, "L_required", Lin) or 0.0),
        )
        span = end - start
        fraction = (
            min(1.0, max(0.0, (float(s) - start) / span))
            if span > 1e-9 else 1.0
        )
        total = float(Lin) + fraction * (target - float(Lin))
    elif "transition" not in zone_type:
        total = max(
            0.0, float(_zone_value(zone, "L_required", 0.0) or 0.0)
        )
    elif zone_type.endswith("_b"):
        total = cie88_transition_luminance(
            float(_zone_value(zone, "s_end")) - float(s),
            0.0,
            Lth_b,
            Lin,
            speed_kmh * float(_zone_value(zone, "transition_scale", 1.0) or 1.0),
        )
    else:
        total = cie88_transition_luminance(
            float(s),
            float(_zone_value(zone, "s_start")),
            Lth,
            Lin,
            speed_kmh * float(_zone_value(zone, "transition_scale", 1.0) or 1.0),
        )
    daylight = daylight_contribution_for_zone(
        zone, s, Lth=Lth, Lth_b=Lth_b,
    )
    # En umbral/transicion/interior Lin es el suelo normativo. En salida se
    # respeta el objetivo configurado, que puede ser inferior a Lin.
    floor = 0.0 if "exit" in zone_type else float(Lin)
    return max(floor, float(total) - daylight)


def transition_envelope(
    s: float,
    zones,
    *,
    Lth: float,
    Lth_b: float,
    Lin: float,
    speed_kmh: float,
) -> tuple[float, float]:
    """Mayor cola de adaptacion activa y su sentido de observacion.

    La cola no se corta artificialmente en ``s_end``. En un tunel corto
    continua sobre la siguiente zona hasta alcanzar ``Lin``.
    """
    best = float(Lin)
    direction = 1.0
    for item in zones:
        if isinstance(item, tuple):
            zone, explicit_direction = item
        else:
            zone, explicit_direction = item, None
        zone_type = str(getattr(zone, "zone_type", "") or "").lower()
        if "transition" not in zone_type:
            continue
        is_b = explicit_direction == -1.0 or (
            explicit_direction is None and zone_type.endswith("_b")
        )
        if is_b:
            if float(s) > float(getattr(zone, "s_end")) + 1e-9:
                continue
            value = cie88_transition_luminance(
                float(getattr(zone, "s_end")) - float(s),
                0.0,
                Lth_b,
                Lin,
                speed_kmh * float(getattr(zone, "transition_scale", 1.0) or 1.0),
            )
            candidate_direction = -1.0
        else:
            if float(s) < float(getattr(zone, "s_start")) - 1e-9:
                continue
            value = cie88_transition_luminance(
                float(s),
                float(getattr(zone, "s_start")),
                Lth,
                Lin,
                speed_kmh * float(getattr(zone, "transition_scale", 1.0) or 1.0),
            )
            candidate_direction = 1.0
        value = max(
            float(Lin),
            float(value) - daylight_contribution_for_zone(
                zone, s, Lth=Lth, Lth_b=Lth_b,
            ),
        )
        if value > best + 1e-12:
            best = value
            direction = candidate_direction
    return best, direction


def canonical_validation_positions(
    tube_length_m: float,
    *,
    zone_boundaries: Iterable[float] = (),
    luminaire_positions: Sequence[float] = (),
    step_m: float = 1.0,
    include_luminaire_midpoints: bool = True,
) -> list[float]:
    """Malla comun para optimizacion y cierre fotometrico.

    Usa centros de intervalos, puntos medios entre luminarias y dos sondas
    laterales en cada frontera de zona. No incluye el plano exacto del portal,
    que no dispone de la mitad exterior del array de luminarias.
    """
    length = max(0.0, float(tube_length_m))
    step = max(0.1, float(step_m))
    half = step / 2.0

    values: list[float] = []
    s = half
    while s < length - 1e-9:
        values.append(s)
        s += step

    positions = sorted(
        min(max(float(value), 0.0), length)
        for value in luminaire_positions
    )
    if include_luminaire_midpoints:
        values.extend(
            (positions[i] + positions[i + 1]) / 2.0
            for i in range(len(positions) - 1)
        )

    for boundary in zone_boundaries:
        b = float(boundary)
        values.extend((b - half, b + half))

    return sorted({
        round(min(max(value, 0.0), length), 3)
        for value in values
        if 0.0 < value < length
    })


def build_requirement_samples(
    zone_designs,
    *,
    tube_length_m: float,
    Lth: float,
    Lth_b: float,
    Lin: float,
    speed_kmh: float,
    step_m: float = 1.0,
    include_luminaire_midpoints: bool = True,
) -> list[dict]:
    """Devuelve los mismos puntos ``s, zona, Lreq, sentido`` para todo solver."""
    active = [
        zone for zone in zone_designs
        if float(getattr(zone, "s_end", 0.0)) >= 0.0
        and float(getattr(zone, "s_start", 0.0)) <= float(tube_length_m)
    ]
    boundaries = [
        value
        for zone in active
        for value in (
            float(getattr(zone, "s_start", 0.0)),
            float(getattr(zone, "s_end", 0.0)),
        )
    ]
    luminaire_positions = [
        float(sp["s"])
        for zone in active
        for sp in (getattr(zone, "setpoints", None) or [])
        if "s" in sp
    ]
    sample_s = canonical_validation_positions(
        tube_length_m,
        zone_boundaries=boundaries,
        luminaire_positions=luminaire_positions,
        step_m=step_m,
        include_luminaire_midpoints=include_luminaire_midpoints,
    )

    samples: list[dict] = []
    for s_val in sample_s:
        candidates = [
            zone for zone in active
            if float(getattr(zone, "s_start")) - 1e-6
            <= s_val
            <= float(getattr(zone, "s_end")) + 1e-6
        ]
        if not candidates:
            continue
        evaluated = [
            (
                zone,
                required_luminance_for_zone(
                    zone,
                    s_val,
                    Lth=Lth,
                    Lth_b=Lth_b,
                    Lin=Lin,
                    speed_kmh=speed_kmh,
                ),
            )
            for zone in candidates
        ]
        zone, target = max(evaluated, key=lambda item: item[1])
        direction = (
            -1.0
            if str(getattr(zone, "zone_type", "") or "").lower().endswith("_b")
            else 1.0
        )
        tail_target, tail_direction = transition_envelope(
            s_val,
            active,
            Lth=Lth,
            Lth_b=Lth_b,
            Lin=Lin,
            speed_kmh=speed_kmh,
        )
        if tail_target > target:
            target = tail_target
            direction = tail_direction
        if target <= 0.0:
            continue
        samples.append({
            "s": s_val,
            "zone": zone,
            "target": float(target),
            "direction": direction,
        })
    return samples
