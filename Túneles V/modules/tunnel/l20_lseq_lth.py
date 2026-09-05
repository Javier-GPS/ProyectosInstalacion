"""
SALVI Tunnel Engine — Cálculo de L20, Lseq y Lth
Implementa TUN-L20-*, TUN-LSEQ-*, TUN-LTH-*
Norma: CIE 88:2004, Capítulos 12–16
"""

import math
from .models import (
    L20Result, LseqResult, LthResult,
    PortalOrientation, SkyCondition, DataConfidence
)


# ─────────────────────────────────────────────
# TABLA CIE 88 — Valores de luminancia por categoría de entorno
# TUN-L20-006: Tabla de referencia para estimación de L20
# Fuente: CIE 88:2004 Tabla 6.1 (luminancias típicas por tipo de entorno)
# ─────────────────────────────────────────────

# Luminancia típica del campo de 20° por tipo de entorno (cd/m²)
# Valor para condición de diseño (percentil 85 aprox)
_L20_BY_ENVIRONMENT = {
    "open_country_flat":  4000,
    "open_country_hilly": 5000,
    "forest":             2500,
    "urban":              3000,
    "mountain":           6000,
    "coastal":            5500,
    "desert":             7000,
    "default":            4000
}

# Factores de orientación del portal respecto al sol
# TUN-ENV-002: Orientación del portal
# Un portal orientado al sol tiene mayor L20
_ORIENTATION_FACTOR = {
    PortalOrientation.NORTH:     0.70,
    PortalOrientation.NORTHEAST: 0.85,
    PortalOrientation.EAST:      0.95,
    PortalOrientation.SOUTHEAST: 1.05,
    PortalOrientation.SOUTH:     1.10,
    PortalOrientation.SOUTHWEST: 1.05,
    PortalOrientation.WEST:      0.95,
    PortalOrientation.NORTHWEST: 0.85,
}

# Factor por condición de cielo (CIE 88 recomienda usar condición de diseño = claro)
_SKY_FACTOR = {
    SkyCondition.CLEAR:        1.00,   # Condición de diseño máxima
    SkyCondition.INTERMEDIATE: 0.60,
    SkyCondition.OVERCAST:     0.25,
}

# ─────────────────────────────────────────────
# TABLA CIE 88 — Relación Lth/L20 (método legacy)
# TUN-L20-007 / TUN-LTH-001
# CIE 88:2004 Tabla 6.2: k = Lth/L20 según velocidad y tráfico
# ─────────────────────────────────────────────

# k_factor = Lth / L20
# Tabla: velocidad_kmh → k
# Para tráfico normal (qc = 0.10 m² · sr / lm)
_K_FACTOR_TABLE = {
    # v_kmh: k (qc=0.10, tráfico normal)
     40: 0.040,
     50: 0.050,
     60: 0.055,
     70: 0.060,
     80: 0.065,
     90: 0.075,
    100: 0.080,
    110: 0.090,
    120: 0.100,
}

# Factor de tráfico para qc
# CIE 88 Tabla 6.3: qc varía entre 0.07 (alto) y 0.14 (bajo tráfico)
_QC_BY_TRAFFIC = {
    "very_high": 0.07,   # > 1500 veh/h
    "high":      0.08,   #  750–1500
    "medium":    0.10,   #  300–750
    "low":       0.12,   #  100–300
    "very_low":  0.14,   # < 100
}

# Orden Circular 36/2015, tomo II, tabla 2.4.
# Columnas: DP <= 60 m, DP = 100 m y DP >= 160 m.
_OC36_K_BY_CLASS = {
    4: (0.05, 0.06, 0.10),
    3: (0.04, 0.05, 0.07),
    2: (0.03, 0.04, 0.05),
}


def traffic_category(veh_h: int) -> str:
    if veh_h > 1500: return "very_high"
    elif veh_h > 750: return "high"
    elif veh_h > 300: return "medium"
    elif veh_h > 100: return "low"
    else: return "very_low"


def get_k_factor(speed_kmh: float, qc: float = 0.10) -> float:
    """
    Obtiene el factor k = Lth/L20.
    Interpolado de la tabla CIE 88 y ajustado por qc.
    """
    speeds = sorted(_K_FACTOR_TABLE.keys())

    if speed_kmh <= speeds[0]:
        k_base = _K_FACTOR_TABLE[speeds[0]]
    elif speed_kmh >= speeds[-1]:
        k_base = _K_FACTOR_TABLE[speeds[-1]]
    else:
        for i in range(len(speeds) - 1):
            v1, v2 = speeds[i], speeds[i + 1]
            if v1 <= speed_kmh <= v2:
                k1 = _K_FACTOR_TABLE[v1]
                k2 = _K_FACTOR_TABLE[v2]
                t = (speed_kmh - v1) / (v2 - v1)
                k_base = k1 + t * (k2 - k1)
                break
        else:
            k_base = _K_FACTOR_TABLE[speeds[-1]]

    # Ajuste por qc: k se escala con qc/qc_ref (qc_ref = 0.10)
    k = k_base * (qc / 0.10)
    return k


def traffic_intensity_oc36(
    traffic_veh_h: float,
    num_lanes: int = 1,
    traffic_direction: str = "one_way",
) -> tuple:
    """
    Devuelve (nivel, veh/h/carril) según OC 36/2015, tabla 2.2.
    """
    lanes = max(1, int(num_lanes or 1))
    per_lane = max(0.0, float(traffic_veh_h)) / lanes
    is_two_way = str(traffic_direction) in ("two_way", "bidirectional")

    high_limit = 700.0 if is_two_way else 1500.0
    medium_limit = 200.0 if is_two_way else 500.0
    if per_lane > high_limit:
        level = "high"
    elif per_lane >= medium_limit:
        level = "medium"
    else:
        level = "low"
    return level, per_lane


def derive_tunnel_class_oc36(
    traffic_veh_h: float,
    num_lanes: int = 1,
    traffic_direction: str = "one_way",
    mixed_traffic: bool = False,
) -> tuple:
    """
    Devuelve (clase, nivel, veh/h/carril) según tablas 2.2 y 2.3.

    Tipo A: solo tráfico motorizado.
    Tipo M: tráfico mixto, incluyendo bicicletas.
    """
    level, per_lane = traffic_intensity_oc36(
        traffic_veh_h, num_lanes, traffic_direction
    )
    classes = {
        "high": 4 if mixed_traffic else 3,
        "medium": 3 if mixed_traffic else 2,
        "low": 2 if mixed_traffic else 1,
    }
    return classes[level], level, per_lane


def get_k_factor_oc36(stopping_distance_m: float, tunnel_class: int) -> float:
    """
    Interpola k = Lth/L20 según OC 36/2015, tabla 2.4.

    La clase 1 no tiene requisito de Lth y por tanto devuelve 0.
    """
    tunnel_class = int(tunnel_class)
    if tunnel_class == 1:
        return 0.0
    if tunnel_class not in _OC36_K_BY_CLASS:
        raise ValueError("La clase de túnel debe estar entre 1 y 4")

    dp = float(stopping_distance_m)
    k60, k100, k160 = _OC36_K_BY_CLASS[tunnel_class]
    if dp <= 60.0:
        return k60
    if dp <= 100.0:
        return k60 + (dp - 60.0) / 40.0 * (k100 - k60)
    if dp < 160.0:
        return k100 + (dp - 100.0) / 60.0 * (k160 - k100)
    return k160


def calculate_L20_model(
    environment_type: str = "default",
    orientation: PortalOrientation = PortalOrientation.SOUTH,
    sky_condition: SkyCondition = SkyCondition.CLEAR,
    latitude: float = 40.0,
    month_design: int = 6,    # Mes de diseño (junio = máximo solar)
    custom_segments: dict = None
) -> L20Result:
    """
    TUN-L20-001 a TUN-L20-006: Calcula L20 mediante modelo de entorno.
    Divide el campo de 20° en segmentos según tipo de superficie.

    El campo de 20° se descompone en (CIE 88 Fig. 6.2):
    - Zona de calzada/suelo:  ω_road ≈ 30%
    - Cielo/portal:           ω_portal ≈ 50%
    - Paredes laterales:      ω_walls ≈ 20%

    Args:
        custom_segments: dict con claves 'road', 'portal', 'walls', 'vegetation'
                         y valores como {'luminance': x, 'weight': y}
    """
    # Valores por defecto de segmentos del campo de 20°
    if custom_segments:
        segments = custom_segments
    else:
        # Luminancia de cielo según condición
        L_sky_clear   = 8000  # cd/m² (cielo azul + entorno)
        L_sky_overcast = 2000
        L_sky = (L_sky_clear if sky_condition == SkyCondition.CLEAR else
                 L_sky_overcast if sky_condition == SkyCondition.OVERCAST else
                 (L_sky_clear + L_sky_overcast) / 2)

        L_road_env = 500   # cd/m² (calzada exterior, asfaltada)
        L_veg = 1500       # Vegetación / montaña

        segments = {
            'portal': {'luminance': L_sky,     'weight': 0.50},
            'road':   {'luminance': L_road_env,'weight': 0.25},
            'walls':  {'luminance': L_veg,     'weight': 0.15},
            'other':  {'luminance': L_veg,     'weight': 0.10},
        }

    # L20 = Σ(L_i * ω_i)
    L20 = sum(seg['luminance'] * seg['weight'] for seg in segments.values())

    # Aplicar factor de orientación
    orient_factor = _ORIENTATION_FACTOR.get(orientation, 1.0)
    L20 *= orient_factor

    # Aplicar factor de entorno base
    env_base = _L20_BY_ENVIRONMENT.get(environment_type, _L20_BY_ENVIRONMENT['default'])
    # Ajuste fino: si L20 calculado difiere mucho del valor base de entorno,
    # ponderamos 70% cálculo / 30% tabla
    L20_final = 0.70 * L20 + 0.30 * env_base * orient_factor

    return L20Result(
        L20=round(L20_final, 0),
        method="model",
        L_road=round(segments.get('road', {}).get('luminance', 0) *
                     segments.get('road', {}).get('weight', 0), 0),
        L_portals=round(segments.get('portal', {}).get('luminance', 0) *
                        segments.get('portal', {}).get('weight', 0), 0),
        L_walls=round(segments.get('walls', {}).get('luminance', 0) *
                      segments.get('walls', {}).get('weight', 0), 0),
        w_road=segments.get('road', {}).get('weight', 0),
        w_portals=segments.get('portal', {}).get('weight', 0),
        w_walls=segments.get('walls', {}).get('weight', 0),
        confidence=DataConfidence.MEDIUM,
        note=f"Modelo entorno: {environment_type}, orientación: {orientation.value}, cielo: {sky_condition.value}"
    )


def calculate_L20_table(environment_type: str, orientation: PortalOrientation) -> L20Result:
    """
    TUN-L20-006: Estimación de L20 por tabla de referencia CIE 88.
    Método más conservador para casos sin datos meteorológicos.
    """
    L20_base = _L20_BY_ENVIRONMENT.get(environment_type, _L20_BY_ENVIRONMENT['default'])
    orient_factor = _ORIENTATION_FACTOR.get(orientation, 1.0)
    L20 = L20_base * orient_factor

    return L20Result(
        L20=round(L20, 0),
        method="table",
        confidence=DataConfidence.MEDIUM,
        note=f"Tabla CIE 88: {environment_type}, factor orientación: {orient_factor:.2f}"
    )


def calculate_Lseq(
    L20: float,
    qc: float = 0.10,
    method: str = "estimated",
    override: float = None,
) -> LseqResult:
    """
    TUN-LSEQ-001 a TUN-LSEQ-006: Calcula la luminancia equivalente Lseq.

    Método "perceived_contrast":
      Lseq = L_obstáculo + Ev / (π * qc)
      donde Ev es la iluminancia vertical sobre el obstáculo.

    Para estimación sin motor fotométrico:
      Lseq ≈ L20 * k_seq
    donde k_seq es un factor que relaciona Lseq con L20 para la
    condición temporal de diseño (TUN-LSEQ-001: t=1/3 * t_total).

    CIE 88 indica que en la práctica Lseq es similar a L20 para
    condiciones de diseño estándar, pero puede diferir en túneles
    con entorno complejo.
    """
    if override is not None:
        value = float(override)
        if value < 0:
            raise ValueError("Lseq no puede ser negativa")
        return LseqResult(
            Lseq=value,
            method="override",
            C_obs=0.04,
            note="Lseq introducida manualmente por el usuario",
        )

    if method == "estimated":
        # Factor de conversión Lseq/L20 ≈ 1.0 para condición estándar
        # En condiciones con sol directo en portal puede ser mayor
        k_seq = 1.0
        Lseq = L20 * k_seq

        return LseqResult(
            Lseq=round(Lseq, 0),
            method="estimated",
            C_obs=0.04,  # CIE 88: contraste de observación mínimo
            note=f"Estimación: Lseq ≈ L20 = {L20:.0f} cd/m²"
        )
    else:
        # Para el método completo necesitamos el motor fotométrico
        raise ValueError("El método 'perceived_contrast' requiere datos del motor fotométrico")


def calculate_Lth(
    L20_result: L20Result,
    speed_kmh: float,
    traffic_veh_h: int = 500,
    method: str = "k_factor",
    Lseq_result: LseqResult = None,
    qc_override: float = None,
    stopping_distance_m: float = None,
    tunnel_class=None,
    num_lanes: int = 1,
    traffic_direction: str = "one_way",
    mixed_traffic: bool = False,
    standard: str = "oc36_2015",
    k_override: float = None,
    contrast_observation: float = 0.04,
) -> LthResult:
    """
    TUN-LTH-001 a TUN-LTH-005: Calcula la luminancia umbral Lth.

    Métodos:
    - "k_factor": Lth = k * L20 (método tabla CIE 88)
    - "lseq":     Lth = f(Lseq, qc) (método riguroso)

    La luminancia umbral es el nivel mínimo de luminancia en la zona umbral
    que garantiza que el conductor puede detectar un obstáculo de referencia
    (cubo 0.2m, reflectancia 0.2) desde la distancia de parada.
    """
    L20 = L20_result.L20

    calculated_class, intensity_level, traffic_per_lane = derive_tunnel_class_oc36(
        traffic_veh_h=traffic_veh_h,
        num_lanes=num_lanes,
        traffic_direction=traffic_direction,
        mixed_traffic=mixed_traffic,
    )
    if tunnel_class in (None, "", "auto"):
        resolved_class = calculated_class
        class_source = (
            "auto_oc36:"
            f"{intensity_level}:{traffic_per_lane:.1f}_veh_h_lane:"
            f"{'M' if mixed_traffic else 'A'}"
        )
    else:
        resolved_class = int(tunnel_class)
        if resolved_class not in (1, 2, 3, 4):
            raise ValueError("La clase de túnel debe estar entre 1 y 4")
        class_source = "user_override"

    dp = float(stopping_distance_m) if stopping_distance_m is not None else None
    qc = float(qc_override) if qc_override is not None else 0.10

    if method == "k_factor":
        if k_override is not None:
            k = float(k_override)
            if not 0 <= k <= 0.25:
                raise ValueError("k = Lth/L20 debe estar entre 0 y 0,25")
            k_source = "user_override"
        elif standard == "oc36_2015":
            if dp is None:
                raise ValueError(
                    "La OC 36/2015 requiere la distancia de parada para obtener k"
                )
            k = get_k_factor_oc36(dp, resolved_class)
            k_source = "OC36_2015_table_2_4"
        else:
            # Compatibilidad con cálculos anteriores basados solo en velocidad.
            k = get_k_factor(speed_kmh, qc)
            k_source = "legacy_speed_table"

        Lth = k * L20

        # Redondear al cd/m² entero más cercano por encima
        # Evitar que el error binario (p. ej. 2600 * 0,035 =
        # 91,00000000000001) fuerce un cd/m² adicional.
        Lth = math.ceil(Lth - 1e-9)
        note = ""
        if resolved_class == 1 and k_override is None:
            note = (
                "La clase 1 no tiene requisito de Lth en la OC 36/2015; "
                "solo se exige guiado del alumbrado."
            )

        return LthResult(
            Lth=float(Lth),
            L20=L20,
            Lseq=None,
            k_factor=k,
            qc=qc,
            method="k_factor",
            iterations=1,
            converged=True,
            standard=(
                "OC 36/2015 tabla 2.4"
                if standard == "oc36_2015"
                else "CIE 88 legacy"
            ),
            tunnel_class=resolved_class,
            calculated_tunnel_class=calculated_class,
            tunnel_class_source=class_source,
            stopping_distance_m=dp,
            k_source=k_source,
            qc_used=False,
            C_obs=None,
            note=note,
        )

    elif method == "lseq":
        if Lseq_result is None:
            raise ValueError("Se requiere Lseq para el método 'lseq'")

        Lseq = Lseq_result.Lseq
        if qc <= 0:
            raise ValueError("q_c debe ser mayor que cero")
        C_obs = float(contrast_observation)
        if not 0 < C_obs < 1:
            raise ValueError("El contraste de observación debe estar entre 0 y 1")

        # TUN-LTH-002: Lth por contraste percibido
        # Lth = Lseq / (qc * (1 + C_obs)) * C_obs
        # Equivalente: Lth tal que el obstáculo tenga contraste C_obs con el fondo
        # Fórmula CIE 88 Ec. 6.3: Lth = Lseq / (1 + C_obs * π / qc)
        # Simplificación práctica:
        Lth = Lseq * C_obs / qc

        Lth = math.ceil(Lth - 1e-9)

        # Iteración: recalcular qc con la luminancia obtenida
        # TUN-LTH-004 y TUN-LTH-005
        iterations = 1
        converged = True
        prev_Lth = Lth + 999

        while abs(Lth - prev_Lth) > 1.0 and iterations < 10:
            prev_Lth = Lth
            # En iteración completa qc se recalcularía con el motor fotométrico
            # Aquí usamos valor constante como aproximación
            Lth = Lseq * C_obs / qc
            Lth = math.ceil(Lth - 1e-9)
            iterations += 1

        if iterations >= 10:
            converged = False

        return LthResult(
            Lth=float(Lth),
            L20=L20,
            Lseq=Lseq,
            k_factor=Lth / L20 if L20 > 0 else 0,
            qc=qc,
            method="lseq",
            iterations=iterations,
            converged=converged,
            standard="CIE 88:2004 (Lseq)",
            tunnel_class=resolved_class,
            calculated_tunnel_class=calculated_class,
            tunnel_class_source=class_source,
            stopping_distance_m=dp,
            k_source="derived_from_Lseq",
            qc_used=True,
            C_obs=C_obs,
            note=(
                "Método Lseq: q_c y el contraste de observación intervienen; "
                "q_c debe proceder de la instalación fotométrica o de un dato validado."
            ),
        )

    else:
        raise ValueError(f"Método desconocido: {method}. Usar 'k_factor' o 'lseq'.")


def calculate_interior_luminance(
    speed_kmh: float,
    traffic_veh_h: int,
    tunnel_length_m: float
) -> float:
    """
    TUN-INT-001 a TUN-INT-006: Luminancia de la zona interior.
    CIE 88:2004 Tabla 7.1: Lin según velocidad y tráfico.
    Interpolación bilineal de la tabla CIE 88.
    """
    # Tabla CIE 88 Tabla 7.1 (cd/m²)
    # Lin para túneles largos (> 125 m, sin ver salida)
    # Eje X: tráfico (veh/h/carril), Eje Y: velocidad (km/h)
    #
    #          <200  200-500  500-1000  >1000
    #  60 km/h:  2.0    2.5     3.0      3.0
    #  80 km/h:  2.0    2.5     3.0      3.0
    # 100 km/h:  2.0    2.5     3.0      4.0
    # 120 km/h:  2.0    3.0     4.0      4.0

    if traffic_veh_h < 200:
        t_cat = 0
    elif traffic_veh_h < 500:
        t_cat = 1
    elif traffic_veh_h < 1000:
        t_cat = 2
    else:
        t_cat = 3

    table = [
        # [<200, 200-500, 500-1000, >1000]
        [2.0, 2.5, 3.0, 3.0],   # 60 km/h
        [2.0, 2.5, 3.0, 3.0],   # 80 km/h
        [2.0, 2.5, 3.0, 4.0],   # 100 km/h
        [2.0, 3.0, 4.0, 4.0],   # 120 km/h
    ]
    speed_rows = [60, 80, 100, 120]

    # Interpolar por velocidad
    if speed_kmh <= speed_rows[0]:
        row = table[0]
    elif speed_kmh >= speed_rows[-1]:
        row = table[-1]
    else:
        for i in range(len(speed_rows) - 1):
            v1, v2 = speed_rows[i], speed_rows[i + 1]
            if v1 <= speed_kmh <= v2:
                t = (speed_kmh - v1) / (v2 - v1)
                row = [table[i][j] + t * (table[i + 1][j] - table[i][j])
                       for j in range(4)]
                break
        else:
            row = table[-1]

    Lin = row[t_cat]

    # Túneles muy largos (> 1 km): posible segunda subzona
    if tunnel_length_m > 1000:
        Lin = max(Lin, 2.0)

    return round(Lin, 2)


def calculate_night_luminance(
    Lin: float,
    illuminated_road: bool = False,
    external_road_luminance: float = None,
    reduced_night: bool = False,
) -> float:
    """
    TUN-NGT-001 a TUN-NGT-004: Luminancia nocturna.
    CIE 88:2004 Sección 8.2.
    """
    if reduced_night:
        # Solo debe habilitarse cuando el proyecto admite el régimen reducido
        # y cuenta con las medidas complementarias exigibles.
        return 0.5
    if illuminated_road and external_road_luminance is not None:
        # En carretera iluminada se iguala el nivel del acceso, sin superar
        # el nivel interior diurno de diseño.
        return round(max(0.5, min(float(Lin), float(external_road_luminance))), 2)
    # Referencia habitual para carretera exterior no iluminada. En carretera
    # iluminada sin dato medido se conserva el mismo valor prudente y se
    # solicita después la luminancia real del acceso.
    return 1.0
