"""
SALVI Tunnel Engine — Velocidad de diseño y distancia de parada
Implementa TUN-GEO-001, TUN-GEO-002, TUN-GEO-003, TUN-GEO-004
Norma: CIE 88:2004, Sección 5
"""

import math
from .models import DataSource, DataConfidence, TracedValue, DesignSpeedResult


# ─────────────────────────────────────────────
# TABLA CIE 88:2004 — Tabla 5.1
# Distancias de parada típicas por velocidad y pendiente
# SD = d_r + d_b  (reacción + frenado)
# CIE 88 adopta: t_r = 1.5 s, a = 3.5 m/s²
# ─────────────────────────────────────────────

# Tabla de SD recomendadas por la norma (km/h → SD en m, pendiente 0%)
# Interpoladas de CIE 88:2004 Table 5.1
_CIE88_SD_TABLE = {
    # v_kmh: SD_m (pendiente 0%)
    40:  45,
    50:  65,
    60:  85,
    70: 110,
    80: 140,
    90: 175,
   100: 215,
   110: 265,
   120: 310,
}

# Factor de corrección por pendiente (CIE 88 Tabla 5.1 simplificada)
# Positivo = rampa subida (más distancia), negativo = bajada (menos freno)
def _gradient_factor(gradient_pct: float) -> float:
    """Multiplicador de SD según pendiente. CIE 88 Tabla 5.1."""
    g = abs(gradient_pct)
    if gradient_pct >= 0:  # bajada (desfavorable)
        if g <= 1:   return 1.00
        elif g <= 2: return 1.05
        elif g <= 3: return 1.10
        elif g <= 4: return 1.18
        elif g <= 5: return 1.28
        elif g <= 6: return 1.40
        else:        return 1.55
    else:              # subida (favorable)
        if g <= 1:   return 1.00
        elif g <= 2: return 0.96
        elif g <= 3: return 0.92
        elif g <= 4: return 0.88
        elif g <= 5: return 0.85
        elif g <= 6: return 0.82
        else:        return 0.78


def calculate_stopping_distance(
    speed_kmh: float,
    gradient_pct: float = 0.0,
    reaction_time_s: float = 1.5,
    deceleration_mss: float = 3.5
) -> tuple:
    """
    Calcula la distancia de parada según CIE 88:2004.

    SD = d_r + d_b
    d_r = v * t_r                     (distancia de reacción)
    d_b = v² / (2 * a)               (distancia de frenado)

    Donde v en m/s.

    Returns:
        (SD_m, d_r_m, d_b_m)
    """
    v_ms = speed_kmh / 3.6  # Convertir a m/s

    # Distancia de reacción
    d_r = v_ms * reaction_time_s

    # Distancia de frenado (sin pendiente)
    d_b = (v_ms ** 2) / (2 * deceleration_mss)

    # Corrección por pendiente (pendiente positiva = subida para el coche)
    # En bajada, el freno es menos efectivo → mayor distancia
    grad_factor = _gradient_factor(gradient_pct)
    d_b_corrected = d_b * grad_factor

    SD = d_r + d_b_corrected

    return SD, d_r, d_b_corrected


def default_friction_coefficient(speed_kmh: float) -> float:
    """Coeficiente longitudinal de proyecto usado por la UI cuando está en Auto."""
    if speed_kmh <= 50:
        return 0.50
    if speed_kmh <= 70:
        return 0.45
    if speed_kmh <= 90:
        return 0.40
    if speed_kmh <= 110:
        return 0.35
    return 0.30


def calculate_stopping_distance_with_friction(
    speed_kmh: float,
    gradient_pct: float = 0.0,
    reaction_time_s: float = 2.5,
    friction_coefficient: float = None,
) -> tuple:
    """
    Distancia de parada editable usada en proyecto.

    La convención de la aplicación es pendiente positiva = bajada:
        DP = v·t_r + v² / (2·g·(mu - i))
    """
    mu = (
        default_friction_coefficient(speed_kmh)
        if friction_coefficient is None
        else float(friction_coefficient)
    )
    if not 0.05 < mu <= 1.0:
        raise ValueError("El coeficiente de rozamiento debe estar entre 0,05 y 1,00")
    if not 0.5 <= reaction_time_s <= 6.0:
        raise ValueError("El tiempo de reacción debe estar entre 0,5 y 6,0 s")

    v_ms = speed_kmh / 3.6
    effective_mu = mu - gradient_pct / 100.0
    if effective_mu <= 0.05:
        raise ValueError(
            "La combinación de pendiente y rozamiento no deja capacidad de frenado suficiente"
        )

    d_r = v_ms * reaction_time_s
    d_b = (v_ms ** 2) / (2 * 9.81 * effective_mu)
    return d_r + d_b, d_r, d_b, mu, 9.81 * effective_mu


def get_stopping_distance_from_table(speed_kmh: float, gradient_pct: float = 0.0) -> float:
    """
    Obtiene SD directamente interpolando de la tabla CIE 88.
    Para velocidades entre los valores tabulados, interpola linealmente.
    """
    speeds = sorted(_CIE88_SD_TABLE.keys())

    if speed_kmh <= speeds[0]:
        sd_base = _CIE88_SD_TABLE[speeds[0]]
    elif speed_kmh >= speeds[-1]:
        sd_base = _CIE88_SD_TABLE[speeds[-1]]
    else:
        # Interpolación lineal
        for i in range(len(speeds) - 1):
            v1, v2 = speeds[i], speeds[i + 1]
            if v1 <= speed_kmh <= v2:
                sd1 = _CIE88_SD_TABLE[v1]
                sd2 = _CIE88_SD_TABLE[v2]
                t = (speed_kmh - v1) / (v2 - v1)
                sd_base = sd1 + t * (sd2 - sd1)
                break
        else:
            sd_base = _CIE88_SD_TABLE[speeds[-1]]

    # Aplicar corrección por pendiente
    grad_factor = _gradient_factor(gradient_pct)
    v_ms = speed_kmh / 3.6
    # Recalcular el frenado con gradiente, manteniendo la reacción tabular
    d_r_approx = v_ms * 1.5  # Reacción a t_r=1.5s
    d_b_approx = sd_base - d_r_approx
    d_b_corrected = d_b_approx * grad_factor
    return d_r_approx + d_b_corrected


def calculate_design_speed(
    speed_kmh: float,
    gradient_pct: float = 0.0,
    source: DataSource = DataSource.USER,
    confidence: DataConfidence = DataConfidence.MEDIUM,
    use_table: bool = True,
    reaction_time_s: float = 1.5,
    friction_coefficient: float = None,
) -> DesignSpeedResult:
    """
    TUN-GEO-001 a TUN-GEO-004: Calcula velocidad de diseño, SD y
    posición del punto de referencia.

    Args:
        speed_kmh:    Velocidad de diseño (km/h)
        gradient_pct: Pendiente del túnel (%, positivo = bajada)
        source:       Fuente del dato de velocidad
        confidence:   Confianza del dato
        use_table:    True = usar tabla CIE 88; False = usar fórmula

    Returns:
        DesignSpeedResult con todos los parámetros calculados
    """
    traced_speed = TracedValue(
        value=speed_kmh,
        source=source,
        confidence=confidence,
        note=f"Velocidad de diseño para cálculo CIE 88"
    )

    calculation_method = "cie88_table"
    used_mu = None
    used_deceleration = 3.5

    if friction_coefficient is not None:
        SD, d_r, d_b, used_mu, used_deceleration = (
            calculate_stopping_distance_with_friction(
                speed_kmh=speed_kmh,
                gradient_pct=gradient_pct,
                reaction_time_s=reaction_time_s,
                friction_coefficient=friction_coefficient,
            )
        )
        calculation_method = "friction_formula"
    elif use_table:
        SD = get_stopping_distance_from_table(speed_kmh, gradient_pct)
        v_ms = speed_kmh / 3.6
        d_r = v_ms * 1.5
        d_b = SD - d_r
        reaction_time_s = 1.5
    else:
        SD, d_r, d_b = calculate_stopping_distance(
            speed_kmh, gradient_pct, reaction_time_s=reaction_time_s
        )
        calculation_method = "deceleration_formula"

    # TUN-GEO-003: El punto de referencia se sitúa a distancia SD
    # antes del portal de entrada (s = -SD en coordenadas locales)
    reference_point_s = -SD  # Negativo = exterior al túnel

    return DesignSpeedResult(
        design_speed_kmh=traced_speed,
        stopping_distance_m=round(SD, 1),
        reaction_distance_m=round(d_r, 1),
        braking_distance_m=round(d_b, 1),
        reference_point_s=round(reference_point_s, 1),
        reaction_time_s=reaction_time_s,
        deceleration_mss=round(used_deceleration, 3),
        friction_coefficient=used_mu,
        calculation_method=calculation_method,
    )


# ─────────────────────────────────────────────
# TABLA DE REFERENCIA RÁPIDA
# ─────────────────────────────────────────────

def get_sd_reference_table() -> list:
    """
    Devuelve tabla resumen de SD para distintas velocidades.
    Útil para mostrar en informes.
    """
    rows = []
    for v in [40, 50, 60, 70, 80, 90, 100, 110, 120]:
        SD, d_r, d_b = calculate_stopping_distance(v)
        rows.append({
            "v_kmh": v,
            "SD_m": round(SD, 0),
            "d_r_m": round(d_r, 1),
            "d_b_m": round(d_b, 1)
        })
    return rows
