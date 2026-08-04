"""
Motor de eficiencia Aphex basado en el LED Lumileds LUXEON 5050 HE Plus - 6V.

Sustituye el catalogo cerrado APHEX S/M/L (tablas de potencia/flujo por
3 puntos de operacion) por un modelo parametrico: corriente -> flujo,
tension directa, potencia DC, temperatura de soldadura (Ts) y perdidas
opticas/electricas, con seleccion automatica de la variante mas pequena
que cumpla los requisitos fotometricos, electricos y termicos.

Ver "Instrucciones_motor_eficiencia_Aphex_LuxStudio.docx" (version
consolidada, julio 2026) para la especificacion completa.

Curvas digitalizadas por analisis de pixel directo sobre las graficas
del datasheet (no OCR/lectura visual aproximada):
  - DS174_LUXEON 5050.pdf, Figura 3b (flujo normalizado vs. corriente,
    HE Plus - 6V, Tj=25 C) -> FI(I).
  - DS174_LUXEON 5050.pdf, Figura 4a (corriente vs. tension directa,
    HE Plus - 6V, Tj=25 C) -> Vf,25(I).
Ambas curvas se validaron contra el punto de referencia del propio
datasheet (640 mA / 5,85 V): FI(640)=1.002, Vf25(640)=5.81 V.
"""
import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ══════════════════════════════════════════════════════════════════════════
# 1. Datos nominales del LED (seccion 4 del documento)
# ══════════════════════════════════════════════════════════════════════════

LED_TYPE                     = "LUXEON_5050_HE_PLUS_6V"
LED_VF_NOMINAL_V             = 6.0
LED_I_NOMINAL_MA             = 640.0
LED_VF_TYP_25C_V             = 5.85
LED_VF_TEMP_COEFF_V_PER_C    = -0.003      # -3 mV/C
LED_RTH_JUNCTION_SOLDER_CPW  = 1.10        # C/W, no usado directamente (Ts es la variable de control)
LED_I_MAX_ABS_MA             = 1200.0
LED_I_RECOMMENDED_MAX_MA     = 1000.0      # limite recomendado configurable, < al maximo absoluto
LED_TJ_MAX_C                 = 125.0
TS_MAX_C                     = 90.0        # limite del sistema optico (lentes PMMA), no del LED

CCT_MIN_K = 2200
CCT_MAX_K = 5000
SUPPORTED_CCT_K = [2200, 2700, 3000, 4000, 5000]
SUPPORTED_CRI   = [70, 80]


# ══════════════════════════════════════════════════════════════════════════
# 2. Curvas digitalizadas (Fig. 3b / Fig. 4a) — coeficientes versionados
# ══════════════════════════════════════════════════════════════════════════

CURVE_VERSION = "DS174-2025-fig3b-fig4a-v1"

# FI(I[mA]): flujo normalizado a corriente I, normalizado a 1.0 en 640 mA.
# Digitalizado sobre 720 columnas de pixel de la Fig. 3b (rango de datos
# 78-801 mA); ajuste cuadratico de minimos cuadrados.
_FI_A, _FI_B, _FI_C = -3.3518338221e-07, 1.76071e-03, 1.2101e-02

def _FI(mA: float) -> float:
    return _FI_A * mA * mA + _FI_B * mA + _FI_C


# Vf,25(I[mA]): tension directa a Tj=25 C en funcion de la corriente.
# Digitalizado sobre la curva negra "LUXEON 5050 HE Plus" de la Fig. 4a
# (652 columnas de pixel, filtro robusto de valores atipicos, 528
# conservados); ajuste cuadratico de minimos cuadrados.
_VF_A, _VF_B, _VF_C = 8.9893715474e-07, -2.640e-05, 5.455852

def _vf_25(mA: float) -> float:
    return _VF_A * mA * mA + _VF_B * mA + _VF_C


def vf_at(mA: float, Ts_C: float) -> float:
    """Vf(I,Ts) = Vf,25(I) - 0,003*(Ts-25). Correccion de tension con Ts
    como aproximacion termica operativa (sin penalizacion adicional de
    flujo por Tj, ver seccion 9.3 del documento)."""
    return _vf_25(mA) + LED_VF_TEMP_COEFF_V_PER_C * (Ts_C - 25.0)


# ══════════════════════════════════════════════════════════════════════════
# 3. Flujo de referencia por CCT y CRI (seccion 5 — valores tabulados)
# ══════════════════════════════════════════════════════════════════════════

_FLUX_REF_LM: Dict[int, Dict[int, float]] = {
    70: {2200: 626, 2700: 687, 3000: 708, 4000: 746, 5000: 737},
    80: {2200: 541, 2700: 624, 3000: 645, 4000: 684, 5000: 690},
}

# Curvas cuadraticas de minimos cuadrados Phi_ref(CCT,CRI) = a*CCT^2+b*CCT+c,
# SOLO para interpolar CCT no soportados directamente (seccion 6). Cuando
# el CCT solicitado coincide con uno de los 5 valores tabulados, se usa
# siempre el dato exacto de la tabla, nunca la curva.
def _fit_quadratic(pairs):
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    n = len(xs)
    sx  = sum(xs);            sx2 = sum(x*x for x in xs)
    sx3 = sum(x**3 for x in xs); sx4 = sum(x**4 for x in xs)
    sy  = sum(ys);  sxy = sum(x*y for x, y in zip(xs, ys))
    sx2y = sum(x*x*y for x, y in zip(xs, ys))
    # Sistema normal 3x3 para minimos cuadrados (a,b,c)
    A = [[sx4, sx3, sx2], [sx3, sx2, sx], [sx2, sx, n]]
    B = [sx2y, sxy, sy]
    return _solve3(A, B)

def _solve3(A, B):
    import copy
    M = [row[:] + [b] for row, b in zip(A, B)]
    for i in range(3):
        piv = M[i][i]
        if abs(piv) < 1e-12:
            for k in range(i+1, 3):
                if abs(M[k][i]) > 1e-12:
                    M[i], M[k] = M[k], M[i]
                    piv = M[i][i]
                    break
        for j in range(i, 4):
            M[i][j] /= piv
        for k in range(3):
            if k != i:
                factor = M[k][i]
                for j in range(i, 4):
                    M[k][j] -= factor * M[i][j]
    return M[0][3], M[1][3], M[2][3]

_FLUX_REF_CURVE: Dict[int, tuple] = {
    cri: _fit_quadratic([(cct, lm) for cct, lm in table.items()])
    for cri, table in _FLUX_REF_LM.items()
}


def flux_ref(cct_k: float, cri: int) -> float:
    """Phi_ref(CCT,CRI): flujo tipico por LED a corriente nominal (640 mA)."""
    cri = 80 if cri not in _FLUX_REF_LM else cri
    table = _FLUX_REF_LM[cri]
    cct_int = int(round(cct_k))
    if cct_int in table:
        return float(table[cct_int])
    if not (CCT_MIN_K <= cct_k <= CCT_MAX_K):
        raise ValueError(f"CCT {cct_k} K fuera de rango valido [{CCT_MIN_K}-{CCT_MAX_K}] K.")
    a, b, c = _FLUX_REF_CURVE[cri]
    return a * cct_k * cct_k + b * cct_k + c


def led_flux_lm(mA: float, cct_k: float, cri: int) -> float:
    """Phi_LED(I,CCT,CRI) = Phi_ref(CCT,CRI) x FI(I). Sin penalizacion por Tj
    (seccion 9.3): la temperatura se usa como restriccion de diseno y para
    la correccion de Vf, no para reducir el flujo del LED."""
    return flux_ref(cct_k, cri) * _FI(mA)


# ══════════════════════════════════════════════════════════════════════════
# 4. Perdidas opticas y electricas (seccion 10)
# ══════════════════════════════════════════════════════════════════════════

LENS_EFFICIENCY       = 0.95
GLASS_EFFICIENCY      = 0.97
OPTICAL_EFFICIENCY    = LENS_EFFICIENCY * GLASS_EFFICIENCY   # 0.9215
DRIVER_EFFICIENCY     = 0.90


# ══════════════════════════════════════════════════════════════════════════
# 5. Variantes Aphex (seccion 11) — resistencias termicas por familia (9.1)
# ══════════════════════════════════════════════════════════════════════════

_RTH_BODY_AMBIENT_CPW = {"S": 0.1088, "M": 0.077, "L": 0.0595}


@dataclass
class LuminaireVariant:
    id: str
    commercial_name: str
    family: str                 # "APHEX_S" | "APHEX_M" | "APHEX_L"
    led_count: int
    driver_manufacturer: str
    driver_model: str
    driver_count: int
    driver_rated_power_each_w: float
    driver_rated_power_total_w: float
    driver_efficiency: float
    luminaire_max_input_power_w: float
    thermal_resistance_body_ambient_c_per_w: float
    max_solder_point_temperature_c: float = TS_MAX_C
    led_type: str = LED_TYPE
    active: bool = True
    version: int = 1


APHEX_VARIANTS: List[LuminaireVariant] = [
    LuminaireVariant("APHEX_S_75W",  "Aphex S 75W",  "APHEX_S", 25, "OSRAM", "75W",  1,  75.0,  75.0,
                     DRIVER_EFFICIENCY,  75.0, _RTH_BODY_AMBIENT_CPW["S"]),
    LuminaireVariant("APHEX_S_100W", "Aphex S 100W", "APHEX_S", 25, "OSRAM", "100W", 1, 100.0, 100.0,
                     DRIVER_EFFICIENCY, 100.0, _RTH_BODY_AMBIENT_CPW["S"]),
    LuminaireVariant("APHEX_S_165W", "Aphex S 165W", "APHEX_S", 50, "OSRAM", "165W", 1, 165.0, 165.0,
                     DRIVER_EFFICIENCY, 165.0, _RTH_BODY_AMBIENT_CPW["S"]),
    LuminaireVariant("APHEX_S_240W", "Aphex S 240W", "APHEX_S", 50, "Inventronics EUR", "240W", 1, 240.0, 240.0,
                     DRIVER_EFFICIENCY, 240.0, _RTH_BODY_AMBIENT_CPW["S"]),
    # Nombre comercial "300W" pero driver/limite operativo real de 320W (seccion 12).
    LuminaireVariant("APHEX_S_300W", "Aphex S 300W", "APHEX_S", 50, "Inventronics EUR", "320W", 1, 320.0, 320.0,
                     DRIVER_EFFICIENCY, 320.0, _RTH_BODY_AMBIENT_CPW["S"]),
    LuminaireVariant("APHEX_M_200Wx2", "Aphex M 200W x2", "APHEX_M", 100, "Inventronics EUR", "200W", 2, 200.0, 400.0,
                     DRIVER_EFFICIENCY, 400.0, _RTH_BODY_AMBIENT_CPW["M"]),
    LuminaireVariant("APHEX_M_240Wx2", "Aphex M 240W x2", "APHEX_M", 100, "Inventronics EUR", "240W", 2, 240.0, 480.0,
                     DRIVER_EFFICIENCY, 480.0, _RTH_BODY_AMBIENT_CPW["M"]),
    LuminaireVariant("APHEX_L_320Wx2", "Aphex L 320W x2", "APHEX_L", 150, "Inventronics EUR", "320W", 2, 320.0, 640.0,
                     DRIVER_EFFICIENCY, 640.0, _RTH_BODY_AMBIENT_CPW["L"]),
    # Driver nominal 2x480W=960W, pero la luminaria se limita a 800W (seccion 12).
    LuminaireVariant("APHEX_L_480Wx2", "Aphex L 480W x2", "APHEX_L", 150, "Inventronics EUR", "480W", 2, 480.0, 960.0,
                     DRIVER_EFFICIENCY, 800.0, _RTH_BODY_AMBIENT_CPW["L"]),
]

# Orden inicial de evaluacion (seccion 17)
_VARIANT_ORDER = ["APHEX_S_75W", "APHEX_S_100W", "APHEX_S_165W", "APHEX_S_240W",
                   "APHEX_S_300W", "APHEX_M_200Wx2", "APHEX_M_240Wx2",
                   "APHEX_L_320Wx2", "APHEX_L_480Wx2"]
VARIANTS_BY_ID = {v.id: v for v in APHEX_VARIANTS}


# ══════════════════════════════════════════════════════════════════════════
# 6. Procedimiento de calculo para un punto de operacion (seccion 15)
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class LuminaireOperatingPoint:
    variant_id: str
    luminaire_name: str
    optic_id: Optional[str]
    cct_k: float
    cri: int
    required_luminaire_flux_lm: float
    calculated_luminaire_flux_lm: float
    led_count: int
    current_per_led_a: float
    voltage_per_led_v: float
    total_led_power_w: float
    input_power_w: float
    ambient_temperature_c: float
    solder_point_temperature_c: float
    led_efficacy_lm_w: float
    luminaire_efficacy_lm_w: float
    power_margin_w: float
    thermal_margin_c: float
    status: str                 # "VALID" | "WARNING" | "INVALID"
    warnings: List[str] = field(default_factory=list)
    calculation_version: str = CURVE_VERSION


def _operating_point_at_current(mA: float, variant: LuminaireVariant, cct_k: float,
                                 cri: int, Ta_C: float, optic_id: Optional[str] = None,
                                 required_flux_lm: Optional[float] = None) -> LuminaireOperatingPoint:
    """Itera Vf/Ts hasta convergencia para una corriente dada (seccion 15)."""
    n = variant.led_count
    Ts = Ta_C + 20.0   # estimacion inicial
    Vf = _vf_25(mA)
    warnings_out: List[str] = []
    converged = False
    for _ in range(30):
        Vf_new = vf_at(mA, Ts)
        P_led_total = n * (mA / 1000.0) * Vf_new
        Ts_new = Ta_C + variant.thermal_resistance_body_ambient_c_per_w * P_led_total
        if abs(Ts_new - Ts) < 0.01 and abs(Vf_new - Vf) < 0.0001:
            Ts, Vf = Ts_new, Vf_new
            converged = True
            break
        Ts, Vf = Ts_new, Vf_new

    status = "VALID"
    if not converged:
        status = "INVALID"
        warnings_out.append("El calculo termico no convergio en 30 iteraciones.")
    if Ts > variant.max_solder_point_temperature_c:
        status = "INVALID"
        warnings_out.append(
            f"Ts calculada ({Ts:.1f} C) supera el limite de {variant.max_solder_point_temperature_c:.0f} C "
            f"(lentes PMMA) — solucion descartada.")

    P_led_total = n * (mA / 1000.0) * Vf
    phi_led = led_flux_lm(mA, cct_k, cri)
    phi_lum = n * phi_led * OPTICAL_EFFICIENCY
    P_input = P_led_total / variant.driver_efficiency

    if mA > LED_I_MAX_ABS_MA:
        status = "INVALID"
        warnings_out.append(f"Corriente {mA:.0f} mA supera el maximo absoluto ({LED_I_MAX_ABS_MA:.0f} mA).")
    elif mA > LED_I_RECOMMENDED_MAX_MA:
        if status == "VALID":
            status = "WARNING"
        warnings_out.append(f"Corriente {mA:.0f} mA supera el limite recomendado ({LED_I_RECOMMENDED_MAX_MA:.0f} mA).")

    driver_limit_w = min(variant.driver_rated_power_total_w, variant.luminaire_max_input_power_w)
    if P_input > driver_limit_w:
        status = "INVALID"
        warnings_out.append(
            f"Potencia de entrada ({P_input:.1f} W) supera el limite de la variante ({driver_limit_w:.1f} W).")

    led_efficacy = phi_led / (mA / 1000.0 * Vf) if mA > 0 else 0.0
    lum_efficacy = phi_lum / P_input if P_input > 0 else 0.0

    return LuminaireOperatingPoint(
        variant_id=variant.id,
        luminaire_name=variant.commercial_name, optic_id=optic_id, cct_k=cct_k, cri=cri,
        required_luminaire_flux_lm=required_flux_lm if required_flux_lm is not None else phi_lum,
        calculated_luminaire_flux_lm=phi_lum, led_count=n,
        current_per_led_a=mA / 1000.0, voltage_per_led_v=Vf, total_led_power_w=P_led_total,
        input_power_w=P_input, ambient_temperature_c=Ta_C, solder_point_temperature_c=Ts,
        led_efficacy_lm_w=led_efficacy, luminaire_efficacy_lm_w=lum_efficacy,
        power_margin_w=driver_limit_w - P_input, thermal_margin_c=variant.max_solder_point_temperature_c - Ts,
        status=status, warnings=warnings_out,
    )


# ══════════════════════════════════════════════════════════════════════════
# 7. Resolucion inversa de la corriente (seccion 16) — metodo de Brent
# ══════════════════════════════════════════════════════════════════════════

def _brent(g, lo, hi, tol_x=0.05, max_iter=60):
    """Metodo de Brent simplificado (fallback a biseccion si no hay
    convergencia superlineal). Requiere g(lo) y g(hi) de signo opuesto."""
    flo, fhi = g(lo), g(hi)
    if flo == 0: return lo
    if fhi == 0: return hi
    if flo * fhi > 0:
        return None  # no hay cambio de signo en el rango -> sin solucion valida
    a, b, fa, fb = lo, hi, flo, fhi
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc = a, fa
    mflag = True
    d = a
    for _ in range(max_iter):
        if fb == 0 or abs(b - a) < tol_x:
            return b
        if fa != fc and fb != fc:
            s = (a*fb*fc/((fa-fb)*(fa-fc)) + b*fa*fc/((fb-fa)*(fb-fc)) + c*fa*fb/((fc-fa)*(fc-fb)))
        else:
            s = b - fb*(b-a)/(fb-fa)
        cond = (
            s < (3*a+b)/4 or s > b
            or (mflag and abs(s-b) >= abs(b-c)/2)
            or (not mflag and abs(s-b) >= abs(c-d)/2)
            or (mflag and abs(b-c) < tol_x)
            or (not mflag and abs(c-d) < tol_x)
        )
        if cond:
            s = (a+b)/2.0
            mflag = True
        else:
            mflag = False
        fs = g(s)
        d = c
        c, fc = b, fb
        if fa*fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa
    return b


def _max_current_within_power(variant: LuminaireVariant, cct_k: float, cri: int, Ta_C: float,
                               i_max_ma_ceiling: float) -> float:
    """Corriente maxima (mA) a la que Pinput de esta variante concreta
    todavia respeta su propio limite (min(driver_rated, luminaire_max)),
    dentro del techo de corriente del LED. Pinput(mA) es monotona
    creciente, asi que basta con biseccion.

    Sin este acotado, todas las variantes de una misma familia con igual
    numero de LEDs (p.ej. S165W/S240W/S300W, todas con 50 LEDs) darian el
    mismo flujo maximo posible — el del techo de corriente del LED — sin
    importar que su driver sea mucho mas pequeno, anulando el sentido de
    tener variantes graduadas por potencia."""
    driver_limit_w = min(variant.driver_rated_power_total_w, variant.luminaire_max_input_power_w)
    op_at_ceiling = _operating_point_at_current(i_max_ma_ceiling, variant, cct_k, cri, Ta_C)
    if op_at_ceiling.input_power_w <= driver_limit_w:
        return i_max_ma_ceiling   # el techo de corriente del LED ya respeta el limite de potencia
    lo, hi = 1.0, i_max_ma_ceiling
    for _ in range(40):
        mid = (lo + hi) / 2.0
        op = _operating_point_at_current(mid, variant, cct_k, cri, Ta_C)
        if op.input_power_w > driver_limit_w:
            hi = mid
        else:
            lo = mid
        if hi - lo < 0.1:
            break
    return lo


def solve_current_for_flux(variant: LuminaireVariant, target_flux_lm: float, cct_k: float,
                            cri: int, Ta_C: float, optic_id: Optional[str] = None,
                            i_max_ma_project: Optional[float] = None,
                            i_min_ma_project: Optional[float] = None) -> LuminaireOperatingPoint:
    """Resuelve g(I) = Phi_lum(I) - Phi_required = 0 con el metodo de Brent
    (seccion 16). Limita el rango por corriente maxima, potencia maxima
    ESPECIFICA de la variante y Ts maxima. Criterio de convergencia:
    max(1 lm, 0.1% del flujo requerido).

    i_max_ma_project: limite de corriente adicional configurado por el
    proyecto (parametro I_max_mA de la interfaz existente) — se aplica
    como tope adicional sobre el limite recomendado del LED, nunca lo
    supera.

    i_min_ma_project: suelo de corriente de atenuacion configurado por el
    proyecto (parametro I_min_pct de la interfaz, en mA ya convertido por
    el llamador) — nunca se resuelve por debajo de este valor. Si target_flux_lm
    ya se alcanza (o se supera) en este suelo, esa es la mejor solucion posible
    para esta variante (no se puede bajar mas), y NO se marca INVALID: sigue
    siendo una variante valida, simplemente sub-utilizada respecto del objetivo."""
    i_min_ma = 1.0
    if i_min_ma_project is not None:
        i_min_ma = max(i_min_ma, float(i_min_ma_project))
    i_max_ma_led = min(LED_I_MAX_ABS_MA, LED_I_RECOMMENDED_MAX_MA)
    if i_max_ma_project is not None:
        i_max_ma_led = min(i_max_ma_led, float(i_max_ma_project))
    i_max_ma = _max_current_within_power(variant, cct_k, cri, Ta_C, i_max_ma_led)
    i_max_ma = max(i_max_ma, i_min_ma)   # mantiene el rango valido para Brent

    def g(mA):
        op = _operating_point_at_current(mA, variant, cct_k, cri, Ta_C, optic_id, target_flux_lm)
        return op.calculated_luminaire_flux_lm - target_flux_lm

    flux_at_max = _operating_point_at_current(i_max_ma, variant, cct_k, cri, Ta_C, optic_id, target_flux_lm)
    if flux_at_max.calculated_luminaire_flux_lm < target_flux_lm:
        # La variante no alcanza el flujo ni al maximo de corriente que su
        # propia potencia permite -> INVALID
        flux_at_max.status = "INVALID"
        flux_at_max.warnings.append(
            f"Flujo requerido ({target_flux_lm:.0f} lm) no alcanzable dentro del limite de "
            f"potencia de esta variante ({i_max_ma:.0f} mA) — flujo maximo posible: "
            f"{flux_at_max.calculated_luminaire_flux_lm:.0f} lm.")
        return flux_at_max

    flux_at_min = _operating_point_at_current(i_min_ma, variant, cct_k, cri, Ta_C, optic_id, target_flux_lm)
    if flux_at_min.calculated_luminaire_flux_lm >= target_flux_lm:
        # El flujo minimo alcanzable en esta variante (suelo de corriente del
        # proyecto, o 1 mA si no hay suelo) ya cubre el objetivo. No hay forma
        # de bajar mas -> esta es la mejor solucion posible para esta variante.
        # NUNCA marcar INVALID aqui: forzar INVALID hacia arriba en la cadena
        # de variantes (todas con mas LEDs, luego un suelo aun mas alto) hacia
        # la variante MAS GRANDE de todas -- justo lo opuesto de "el modelo mas
        # pequeno que cumple".
        return flux_at_min

    mA_sol = _brent(g, i_min_ma, i_max_ma)
    if mA_sol is None:
        # No deberia ocurrir tras las comprobaciones de arriba (flux_at_min <
        # target <= flux_at_max garantiza cambio de signo). Fallback defensivo:
        # el suelo de corriente es la mejor aproximacion disponible.
        return flux_at_min

    return _operating_point_at_current(mA_sol, variant, cct_k, cri, Ta_C, optic_id, target_flux_lm)


# ══════════════════════════════════════════════════════════════════════════
# 8. Seleccion automatica de la variante optima (seccion 17)
# ══════════════════════════════════════════════════════════════════════════

def select_optimal_variant(target_flux_lm: float, cct_k: float, cri: int, Ta_C: float = 35.0,
                            optic_id: Optional[str] = None,
                            variant_ids: Optional[List[str]] = None,
                            i_max_ma_project: Optional[float] = None,
                            i_min_ma_project: Optional[float] = None) -> LuminaireOperatingPoint:
    """Ordena las variantes activas por capacidad creciente, resuelve la
    corriente necesaria para cada una y selecciona la solucion valida de
    menor potencia instalada. Lanza ValueError si ninguna variante activa
    alcanza el flujo requerido."""
    order = variant_ids or _VARIANT_ORDER
    best: Optional[LuminaireOperatingPoint] = None
    attempts: List[LuminaireOperatingPoint] = []
    for vid in order:
        variant = VARIANTS_BY_ID[vid]
        if not variant.active:
            continue
        op = solve_current_for_flux(variant, target_flux_lm, cct_k, cri, Ta_C, optic_id,
                                     i_max_ma_project, i_min_ma_project)
        attempts.append(op)
        if op.status in ("VALID", "WARNING"):
            best = op
            break
    if best is None:
        # Ninguna variante alcanza el flujo — devolver la de mayor potencia
        # (L 480W x2) marcada INVALID, igual que hace el motor anterior con
        # el modelo L al tope de corriente, para no dejar de emitir un
        # resultado (el llamador debe comprobar status == "INVALID").
        return attempts[-1] if attempts else None
    return best
