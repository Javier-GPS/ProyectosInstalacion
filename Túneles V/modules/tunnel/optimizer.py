"""
SALVI Tunnel Optimizer — CIE 88:2004 inside-out con optimizacion U0/Ul
=======================================================================

Estrategia:

  INTERIOR (ancla):
    Paso 1: recorrer una malla de interdistancias instalables.
    Paso 2: probar opticas F151 -> F2MD -> F2M2 y variar tilt.
    Paso 3: seleccionar por numero de luminarias o por W/m.

  TRANSICION (interior -> portal):
    La geometria se selecciona antes del modelo-driver. Los flujos definitivos
    se resuelven conjuntamente en influence_optimizer.py mediante L=A@phi.

  UMBRAL:
    Idem transicion con L_req = Lth uniforme.
    Si L@I_max < Lth incluso a d_min -> avisar.

  RETROFIT (posiciones fijas):
    d es input; solo se optimiza (optica, tilt, I).

Corriente continua: I en [I_min_abs, I_max]
  I_min_abs = I_min_pct * 350 mA  (default 30% = 105 mA)
  Por debajo de 350 mA: interpolacion lineal desde catalogo con bonus eficacia.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from photometric_engine.salvi_photometry.ldt_parser import load_ldt, Photometry
from photometric_engine.salvi_photometry.calculator import TunnelCalculator, LuminaireInstance
from photometric_engine.salvi_photometry.geometry import (
    LuminaireOrientation, Observer, mirror_c_for_interior_facing,
)
from modules.tunnel.required_luminance import cie88_transition_luminance

# ── LDTs ──────────────────────────────────────────────────────────────────────
_LDT_DIR = _PROJECT_ROOT / "photometric_engine" / "data" / "photometries"
_OPTIC_LDT = {
    "F2MD": "APHEX_M_H10_40K_F2MD_VDR_SPUW_200W.ldt",
    "F2M2": "APHEX_M_H10_40K_F2M2_VDR_SPUW_200W.ldt",
    "F151": "APHEX_M_H10_40K_F151_VDR_SPUW_200W.ldt",
}
# Orden de prueba por eficiencia (F151 la mas eficiente -> F2MD -> F2M2).
# Los optimizadores paran en la primera optica de esta lista que alcance
# U0/Ul con algun tilt del tilt_grid, sin seguir probando las siguientes.
OPTICS = ["F151", "F2MD", "F2M2"]
_PHOT_CACHE: dict[str, Photometry] = {}


def _load_phot(optic: str) -> Photometry:
    if optic not in _PHOT_CACHE:
        _PHOT_CACHE[optic] = load_ldt(_LDT_DIR / _OPTIC_LDT.get(optic, _OPTIC_LDT["F2MD"]))
    return _PHOT_CACHE[optic]


_REACH_CACHE: dict[tuple, float] = {}


def _reach_for(optic: str, h: float) -> float:
    """Distancia [m] mas alla de la cual esta optica, a esta altura de
    montaje, deja de contribuir de forma apreciable (Photometry.reach_distance)
    -- sustituye la constante fija que antes se usaba tanto para el numero de
    replicas del diseño aislado (n_side) como para el corte de luminarias
    lejanas del calculo real (TunnelCalculator.max_lum_dist), garantizando
    que ambos usen el mismo criterio y no diverjan entre si."""
    key = (optic, round(float(h), 2))
    if key not in _REACH_CACHE:
        _REACH_CACHE[key] = _load_phot(optic).reach_distance(float(h))
    return _REACH_CACHE[key]


# ── Motor de eficiencia LUXEON 5050 HE Plus — reemplaza el catalogo cerrado
#    S/M/L por un modelo parametrico de 9 variantes Aphex. Ver
#    docs/especificaciones/Instrucciones_motor_eficiencia_Aphex_LuxStudio.docx
#    y modules/tunnel/led_engine.py ──
from modules.tunnel import led_engine as _led

CHAIN_ORDER = list(_led._VARIANT_ORDER)   # 9 variantes, orden de capacidad creciente
_DEFAULT_CRI  = 70     # unico soportado hasta que la interfaz exponga selector de CRI
_DEFAULT_TA_C = 20.0   # temperatura ambiente de diseno — media anual del emplazamiento
                       # (evalua la reduccion media de eficiencia del LED, no un limite de
                       # seguridad; ver Geometria > Entorno en la interfaz). Configurable
                       # por proyecto via set_design_ambient_temperature().
# La consigna de regulacion se expresa como porcentaje del punto de control
# historico de 350 mA (la interfaz muestra, por ejemplo, 30 % = 105 mA).
# LED_I_NOMINAL_MA=640 mA solo normaliza la curva fisica del LED.
_CONTROL_CURRENT_REFERENCE_MA = 350.0


def set_design_ambient_temperature(ta_c: float) -> None:
    """Fija la Ta de diseno para las siguientes llamadas a
    flux_power_at_current/select_model_for_flux en este proceso. Se llama
    una vez por calculo desde design_aphex_tunnel_optimized (modulo
    single-request, sin concurrencia — mismo patron que _QC_CACHE)."""
    global _DEFAULT_TA_C
    _DEFAULT_TA_C = float(ta_c)


def _cct_str_to_k(cct) -> float:
    """'4000K' -> 4000.0"""
    try:
        return float(str(cct).upper().replace("K", "").strip())
    except ValueError:
        return 4000.0


def flux_power_at_current(model: str, cct, mA: float, I_min_pct: float = 0.30):
    """(flux_lm, power_W) para una variante Aphex y corriente dadas —
    delega en el motor fisico led_engine (LUXEON 5050 HE Plus)."""
    variant = _led.VARIANTS_BY_ID[model]
    mA_eff = max(I_min_pct * _CONTROL_CURRENT_REFERENCE_MA, mA)
    op = _led._operating_point_at_current(mA_eff, variant, _cct_str_to_k(cct), _DEFAULT_CRI, _DEFAULT_TA_C)
    return op.calculated_luminaire_flux_lm, op.input_power_w


def select_model_for_flux(phi_lm: float, cct, I_max_mA: float,
                          I_min_pct: float = 0.30) -> dict:
    """Selecciona, entre las 9 variantes Aphex (orden de capacidad
    creciente), la mas pequena que alcance phi_lm lm — delega en
    led_engine.select_optimal_variant (seccion 17 del documento)."""
    cct_k = _cct_str_to_k(cct)
    i_min_ma = max(1.0, float(I_min_pct) * _CONTROL_CURRENT_REFERENCE_MA)
    op = _led.select_optimal_variant(
        target_flux_lm=phi_lm, cct_k=cct_k, cri=_DEFAULT_CRI, Ta_C=_DEFAULT_TA_C,
        i_max_ma_project=I_max_mA, i_min_ma_project=i_min_ma,
    )
    if op is None:
        variant = _led.VARIANTS_BY_ID[_led._VARIANT_ORDER[-1]]
        op = _led._operating_point_at_current(I_max_mA, variant, cct_k, _DEFAULT_CRI, _DEFAULT_TA_C)
    return {
        "model": op.variant_id,
        "mA":    round(op.current_per_led_a * 1000, 1),
        "W":     round(op.input_power_w, 1),
        "lm":    round(op.calculated_luminaire_flux_lm, 0),
    }


# ── Motor CIE 140 directo ─────────────────────────────────────────────────────

_UNIT_FLUX = 10000.0   # lm de referencia para calculos de U0/Ul/L

_QC_CACHE: dict = {}   # clave: (optic, d, h, w, tilt, arrangement, rtable, mf_str)


def _n_rows(arrangement: str) -> int:
    return {"central_single":1,"central_offset":1,"central_double":2,
            "lateral_left":1,"lateral_right":1,"unilateral":1,
            "bilateral_sym":2,"bilateral_stag":2,"bilateral":2,"staggered":2
            }.get(arrangement, 1)


_WALL_Y_DEFAULT = 0.30  # m — valor por defecto

def _y_positions(arrangement: str, w: float, wall_offset: float = _WALL_Y_DEFAULT) -> list[float]:
    """Posiciones transversales [m] de las luminarias. Road: y in [0, w].
    ``wall_offset`` es la coordenada medida desde la pared izquierda. En las
    disposiciones centrales desplazadas, la interfaz mantiene
    ``wall_offset + axis_offset = w/2``.
    """
    wo = min(max(0.05, float(wall_offset)), max(0.05, w / 2.0 - 0.05))
    if arrangement in ("bilateral_sym","bilateral_stag","bilateral","staggered"):
        return [wo, w - wo]
    elif arrangement == "central_double":
        return [wo, w - wo]
    elif arrangement == "central_offset":
        return [wo]
    elif arrangement == "lateral_left":
        return [wo]
    elif arrangement in ("lateral_right","unilateral"):
        return [w - wo]
    return [w/2]                                # central


_PAIRED_ARRANGEMENTS = {"bilateral_sym", "bilateral_stag", "bilateral", "staggered", "central_double"}


def _build_lums(optic, d, h, w, tilt, arrangement, n_side=None, flux=_UNIT_FLUX,
               wall_offset=_WALL_Y_DEFAULT):
    """Genera array +/-n_side periodos (2*n_side+1 grupos).
    Convencion identica a photometric_verify para coherencia de estimaciones.

    n_side=None (por defecto): se calcula a partir del alcance fotometrico
    real de la optica a esta altura (Photometry.reach_distance / _reach_for),
    en vez de una constante fija -- para una interdistancia muy apretada
    (tipico en Umbral, L_req alto) hacen falta muchas mas replicas que para
    una amplia (Interior) para representar de verdad lo que aporta el resto
    de luminarias reales dentro del alcance de la fotometria.

    El tilt (rotacion transversal, CIE 140 Anexo A) se espeja entre ambas filas
    en disposiciones enfrentadas: cada fila se inclina hacia el eje del tunel
    (nunca ambas hacia el mismo lado), igual que la vista previa del frontend."""
    phot      = _load_phot(optic)
    if n_side is None:
        reach  = _reach_for(optic, h)
        n_side = max(2, math.ceil(reach / max(d, 0.1)))
    ys        = _y_positions(arrangement, w, wall_offset)
    is_paired = arrangement in _PAIRED_ARRANGEMENTS
    is_staggered = arrangement in {"bilateral_stag", "staggered"}
    lums      = []
    for i in range(-n_side, n_side + 1):
        x = i * d
        physical_ys = [ys[abs(i) % len(ys)]] if is_staggered else ys
        for y in physical_ys:
            y_tilt = tilt if (not is_paired or y < w / 2) else -tilt
            orient = LuminaireOrientation(
                tilt_deg=y_tilt,
                mirror_c=mirror_c_for_interior_facing(y, w, arrangement),
            )
            lums.append(LuminaireInstance(x=x, y=y, H=h,
                                          photometry=phot, flux_lm=flux, orientation=orient))
    return lums


def _calc_grid(d, w, nl=10, nt=5):
    """Grid CIE 140 en la celda central [-d/2, d/2] x [0, w].
    10×5 = 50 puntos — mismo que photometric_verify para consistencia."""
    xs = [(-d/2)+(j+0.5)*d/nl for j in range(nl)]
    ys = [(k+0.5)*w/nt         for k in range(nt)]
    return [(x,y) for x in xs for y in ys], nl, nt


def _L_array(optic, d, h, w, tilt, arrangement, rtable, mf, flux=_UNIT_FLUX,
             wall_offset=_WALL_Y_DEFAULT, direction=1.0):
    """Array numpy de luminancias en la celda central [cd/m2]."""
    lums = _build_lums(optic, d, h, w, tilt, arrangement, flux=flux, wall_offset=wall_offset)
    pts, nl, nt = _calc_grid(d, w)
    calc = TunnelCalculator(rtable_name=rtable, maintenance_factor=mf,
                            max_luminaire_dist=_reach_for(optic, h))
    # CIE 140 sec.6.2.2 — direction=+1: trafico A->B (observador 60 m por
    # delante en +x). direction=-1: trafico entrando por portal B (zonas
    # "_b"), que viaja en -x, asi que su observador va 60 m por delante en -x
    # — ver Observer.direction. Sin esto el beta (y por tanto U0/Ul/L) de las
    # zonas B se evaluaria con la vista de un conductor circulando al reves.
    obs  = Observer(lane_y_m=w/2, d_observer_m=60.0, direction=direction)
    return calc.luminance_at_points_batch(pts, lums, obs), nl, nt


def _quality_and_mean(optic, d, h, w, tilt, rtable, mf, arrangement, wall_offset, direction=1.0):
    """(U0, Ul, L_mean_a_UNIT_FLUX) cacheados juntos bajo una unica clave —
    antes eval_quality() y L_at_unit_flux() construian cada uno su propio
    _L_array() para la misma (optic,d,h,w,tilt,...), duplicando el trabajo
    caro (fotometria LDT + CIE 140 en la rejilla) en cada punto muestreado."""
    key = (optic, round(d,3), round(h,3), round(w,3), round(tilt,1), arrangement, rtable,
           f"{mf:.2f}", round(wall_offset,3), direction)
    if key in _QC_CACHE:
        return _QC_CACHE[key]

    L, nl, nt = _L_array(optic, d, h, w, tilt, arrangement, rtable, mf, wall_offset=wall_offset,
                         direction=direction)
    if L.max() < 1e-9:
        result = (0.0, 0.0, 0.0)
        _QC_CACHE[key] = result
        return result

    U0 = float(L.min() / L.mean())

    # Ul: minimo de (L_min/L_max) por cada fila longitudinal (mismo y)
    ul_rows = []
    for k in range(nt):
        row = L[k::nt]
        if len(row) > 1 and row.max() > 0:
            ul_rows.append(float(row.min()/row.max()))
    Ul = min(ul_rows) if ul_rows else 0.0

    result = (U0, Ul, float(L.mean()))
    _QC_CACHE[key] = result
    return result


def eval_quality(optic, d, h, w, tilt, rtable="R2", mf=0.70, arrangement="central_single",
                wall_offset=_WALL_Y_DEFAULT, direction=1.0):
    """(U0, Ul). Independientes del flujo — se usa UNIT_FLUX."""
    U0, Ul, _ = _quality_and_mean(optic, d, h, w, tilt, rtable, mf, arrangement, wall_offset, direction)
    return U0, Ul


def L_at_unit_flux(optic, d, h, w, tilt, arrangement, rtable, mf,
                   wall_offset=_WALL_Y_DEFAULT, direction=1.0) -> float:
    """L_avg [cd/m2] con UNIT_FLUX lm por luminaria."""
    _, _, L_mean = _quality_and_mean(optic, d, h, w, tilt, rtable, mf, arrangement, wall_offset, direction)
    return L_mean


def phi_for_luminance(optic, d, h, w, tilt, L_req, arrangement, rtable, mf,
                     wall_offset=_WALL_Y_DEFAULT, direction=1.0) -> float:
    """Flujo por luminaria [lm] para producir L_req [cd/m2]."""
    L_unit = L_at_unit_flux(optic, d, h, w, tilt, arrangement, rtable, mf, wall_offset=wall_offset,
                            direction=direction)
    return (L_req / L_unit * _UNIT_FLUX) if L_unit > 0 else 1e9


def L_from_flux(optic, d, h, w, tilt, flux_lm, arrangement, rtable, mf,
                wall_offset=_WALL_Y_DEFAULT, direction=1.0) -> float:
    """L_avg estimada [cd/m2] para flux_lm por luminaria."""
    L_unit = L_at_unit_flux(optic, d, h, w, tilt, arrangement, rtable, mf, wall_offset=wall_offset,
                            direction=direction)
    return L_unit * flux_lm / _UNIT_FLUX


def clear_cache():
    _QC_CACHE.clear()


# ── Fase 1: Optimizador interior ──────────────────────────────────────────────

def _find_dmax_adaptive(ok_fn, d_min, d_max_hard, coarse_n=10, fine_n=25):
    """Mayor d en [d_min, d_max_hard] tal que ok_fn(d) es True — busqueda
    adaptativa grueso->fino.

    ok_fn NO es necesariamente monotona en d (U0/Ul pueden empeorar a d muy
    pequeno -modo casi-puntual bajo la luminaria en una celda muy corta- y
    mejorar de nuevo a d intermedio antes de degradarse otra vez a d grande),
    por lo que no se puede resolver con una biseccion global directa ni
    asumir "si d_min no cumple, ningun d cumple".

    Estrategia:
      1. Muestrea `coarse_n` puntos de MAYOR a MENOR d y para en el primero
         que cumple — es candidato al mayor d factible sin necesidad de
         evaluar el resto (ahorra evaluaciones caras de CIE 140 respecto a
         muestrear los 25 puntos siempre, que era el comportamiento previo).
      2. Si NINGUNO de los `coarse_n` cumple, escala a `fine_n` puntos (la
         resolucion completa original) antes de concluir que no hay ningun
         d factible — evita falsos negativos por una region factible
         estrecha que el paso grueso pudiera saltarse.
      3. Afina el candidato encontrado hacia el siguiente punto muestreado
         (mayor, no factible) por biseccion local — igual que antes.

    Retorna (d_encontrado, True) o (None, False) si no hay ningun d factible.
    """
    if d_max_hard <= d_min:
        return (d_min, True) if ok_fn(d_min) else (None, False)

    def _sample_desc(n):
        step = (d_max_hard - d_min) / (n - 1)
        ds = [d_min + i * step for i in range(n)]
        ds[-1] = d_max_hard  # evitar error de redondeo
        for i in range(n - 1, -1, -1):
            if ok_fn(ds[i]):
                return ds, i
        return ds, None

    ds, idx_best = _sample_desc(coarse_n)
    if idx_best is None:
        ds, idx_best = _sample_desc(fine_n)
        if idx_best is None:
            return None, False

    d_best = ds[idx_best]
    upper  = ds[idx_best + 1] if idx_best < len(ds) - 1 else None

    # Segunda pasada: si el candidato no esta en el extremo superior, TODOS los
    # puntos gruesos por encima (ds[idx_best+1:]) dieron "no cumple" — pero con
    # solo `coarse_n` puntos, una banda factible mas ancha podria caer entera
    # en el hueco entre dos de ellos y pasar desapercibida. Se vuelve a
    # muestrear, con el doble de densidad, SOLO esa region superior; si
    # aparece un d mayor que el candidato grueso, se adopta como nuevo mejor
    # (y su cota superior para la biseccion es el siguiente punto conocido
    # como "no cumple" de ese re-muestreo).
    if upper is not None:
        recheck_n = coarse_n
        step = (d_max_hard - d_best) / recheck_n
        recheck_ds = [d_best + (j + 1) * step for j in range(recheck_n)]
        for j in range(len(recheck_ds) - 1, -1, -1):
            if ok_fn(recheck_ds[j]):
                d_best = recheck_ds[j]
                upper  = recheck_ds[j + 1] if j + 1 < len(recheck_ds) else upper
                break

    if upper is None:
        return round(d_best, 2), True

    # Afinar hacia el siguiente punto muestreado (que no cumple) por biseccion
    # local — dentro de este sub-intervalo SI se puede asumir una unica
    # transicion, ya que el muestreo ya localizo la region factible mas alta.
    lo, hi = d_best, upper
    for _ in range(20):
        mid = (lo + hi) / 2.0
        if ok_fn(mid):
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.05:
            break
    return round(lo, 2), True


def find_dmax_for_quality(optic, tilt, h, w, U0_obj, Ul_obj, rtable, mf, arrangement,
                          d_min=2.5, d_max_hard=25.0,
                          wall_offset=_WALL_Y_DEFAULT) -> float:
    """Mayor d tal que U0>=U0_obj Y Ul>=Ul_obj. Retorna 0 si ninguna d en
    [d_min, d_max_hard] cumple. Ver _find_dmax_adaptive para la estrategia
    de muestreo (U0/Ul no son monotonos en d en general)."""
    def ok(d):
        U0, Ul = eval_quality(optic, d, h, w, tilt, rtable, mf, arrangement,
                              wall_offset=wall_offset)
        return U0 >= U0_obj and Ul >= Ul_obj

    d_found, feasible = _find_dmax_adaptive(ok, d_min, d_max_hard)
    return d_found if feasible else 0.0


def _spacing_grid(d_min: float, d_max: float, quantum: float) -> list[float]:
    """Malla descendente de interdistancias instalables."""
    q = max(0.1, float(quantum))
    lo = max(q, float(d_min))
    hi = max(lo, float(d_max))
    n_hi = int(math.floor((hi + 1e-9) / q))
    n_lo = int(math.ceil((lo - 1e-9) / q))
    return [round(n * q, 3) for n in range(n_hi, n_lo - 1, -1)]


def optimize_interior(
    h, w, L_int, U0_obj, Ul_obj, I_max_mA, cct,
    rtable="R2", mf=0.70, arrangement="central_single",
    I_min_pct=0.30, tilt_grid=None, d_min=2.5, d_max_hard=25.0,
    wall_offset=_WALL_Y_DEFAULT,
    optimization_goal="min_luminaires", spacing_quantum_m=0.5,
    speed_kmh=None, flicker_min_hz=None, flicker_max_hz=None,
    _no_flicker=False,
) -> dict:
    """
    Optimizador zona interior.

    Las opticas se prueban en orden F151 -> F2MD -> F2M2.

    ``min_luminaires`` recorre d de mayor a menor y acepta la primera
    combinacion factible. ``min_power`` minimiza W/m dentro de la primera
    optica que tenga alguna solucion factible.
    """
    if tilt_grid is None:
        tilt_grid = [0.0, 5.0, 10.0, 15.0, 20.0]

    warnings_out = []
    goal = str(optimization_goal or "min_luminaires").lower()
    if goal not in ("min_luminaires", "min_power"):
        goal = "min_luminaires"

    distances = _spacing_grid(d_min, d_max_hard, spacing_quantum_m)
    lm_max, _ = flux_power_at_current(CHAIN_ORDER[-1], cct, I_max_mA, I_min_pct)
    # La decision de la optica no puede ser una caja negra: F151 es la
    # primera preferida, pero F2MD/F2M2 deben quedar evaluadas y trazables
    # para confirmar que no permiten una interdistancia mayor con la misma
    # calidad. La traza se devuelve al motor, no se usa para alterar la regla
    # de prioridad F151 -> F2MD -> F2M2.
    candidate_trace = []
    candidates_by_spacing = {}

    _apply_flicker = not _no_flicker and bool(speed_kmh)
    def _candidate(optic, tilt, d):
        if _apply_flicker and _flicker_forbidden(
            d, speed_kmh, flicker_min_hz, flicker_max_hz,
        ):
            return None
        U0, Ul = eval_quality(
            optic, d, h, w, tilt, rtable, mf, arrangement,
            wall_offset=wall_offset,
        )
        quality_ok = U0 >= U0_obj and Ul >= Ul_obj
        if not quality_ok:
            candidate_trace.append({
                "d": round(float(d), 3), "optic": optic,
                "tilt_deg": round(float(tilt), 2),
                "U0": round(float(U0), 4), "Ul": round(float(Ul), 4),
                "quality_ok": False, "flux_ok": False,
                "feasible": False, "reason": "uniformity",
            })
            return None
        phi = phi_for_luminance(
            optic, d, h, w, tilt, L_int, arrangement, rtable, mf,
            wall_offset=wall_offset,
        )
        if phi > lm_max * (1.0 + 1e-9):
            candidate_trace.append({
                "d": round(float(d), 3), "optic": optic,
                "tilt_deg": round(float(tilt), 2),
                "U0": round(float(U0), 4), "Ul": round(float(Ul), 4),
                "phi_lm": round(float(phi), 1),
                "quality_ok": True, "flux_ok": False,
                "feasible": False, "reason": "max_flux",
            })
            return None
        sel = select_model_for_flux(phi, cct, I_max_mA, I_min_pct)
        L_actual = L_from_flux(
            optic, d, h, w, tilt, sel["lm"], arrangement, rtable, mf,
            wall_offset=wall_offset,
        )
        candidate = {
            "d": d, "optic": optic, "tilt": tilt,
            "phi": phi, "sel": sel, "U0": U0, "Ul": Ul,
            "L_actual": L_actual,
            "power_per_m": float(sel["W"]) / max(d, 1e-9),
        }
        candidate_trace.append({
            "d": round(float(d), 3), "optic": optic,
            "tilt_deg": round(float(tilt), 2),
            "U0": round(float(U0), 4), "Ul": round(float(Ul), 4),
            "phi_lm": round(float(phi), 1),
            "model": str(sel["model"]), "current_mA": float(sel["mA"]),
            "flux_lm": round(float(sel["lm"]), 1),
            "L_at_selected_flux": round(float(L_actual), 4),
            "quality_ok": True, "flux_ok": True,
            "feasible": True, "reason": "ok",
        })
        return candidate

    # Evalua la malla completa una sola vez. La seleccion posterior conserva
    # exactamente el orden funcional anterior, pero ahora F2MD y F2M2 quedan
    # comprobadas incluso cuando F151 ya es valida en ese mismo vano.
    for d in distances:
        per_optic = {}
        for optic_id in OPTICS:
            optic_candidates = []
            for tilt_value in tilt_grid:
                candidate_item = _candidate(optic_id, tilt_value, d)
                if candidate_item is not None:
                    optic_candidates.append(candidate_item)
            per_optic[optic_id] = optic_candidates
        candidates_by_spacing[float(d)] = per_optic

    best = None
    if goal == "min_luminaires":
        for d in distances:
            for optic_id in OPTICS:
                candidates = candidates_by_spacing[float(d)][optic_id]
                if candidates:
                    best = min(candidates, key=lambda c: (c["phi"], c["tilt"]))
                    break
            if best is not None:
                break
    else:
        # Menor potencia debe comparar la malla completa de ópticas. Detenerse
        # en la primera óptica factible conservaba la preferencia F151, pero no
        # garantizaba el mínimo eléctrico solicitado por el usuario.
        candidates = [
            candidate
            for d in distances
            for optic in OPTICS
            for candidate in candidates_by_spacing[float(d)][optic]
        ]
        if candidates:
            optic_rank = {optic: index for index, optic in enumerate(OPTICS)}
            best = min(
                candidates,
                key=lambda c: (
                    c["power_per_m"], -c["d"], c["phi"],
                    optic_rank.get(c["optic"], len(OPTICS)), c["tilt"],
                ),
            )

    if best is None:
        warnings_out.append(
            f"Ninguna combinacion optica x tilt cumple U0>={U0_obj}/Ul>={Ul_obj} "
            f"y L={L_int:.1f} cd/m2 en la malla de "
            f"{spacing_quantum_m:.1f} m. Usando F2M2 tilt=0 d={d_min} m."
        )
        d_opt = distances[-1] if distances else float(d_min)
        optic, tilt = "F2M2", 0.0
        phi = phi_for_luminance(
            optic, d_opt, h, w, tilt, L_int, arrangement, rtable, mf,
            wall_offset=wall_offset,
        )
        sel = select_model_for_flux(phi, cct, I_max_mA, I_min_pct)
        U0f, Ulf = eval_quality(
            optic, d_opt, h, w, tilt, rtable, mf, arrangement,
            wall_offset=wall_offset,
        )
    else:
        d_opt, optic, tilt = best["d"], best["optic"], best["tilt"]
        phi, sel = best["phi"], best["sel"]
        U0f, Ulf = best["U0"], best["Ul"]

    L_est    = L_from_flux(optic, d_opt, h, w, tilt, sel["lm"], arrangement, rtable, mf,
                           wall_offset=wall_offset)

    candidate_summary = []
    for summary_optic in OPTICS:
        optic_rows = [row for row in candidate_trace if row["optic"] == summary_optic]
        feasible_rows = [row for row in optic_rows if row["feasible"]]
        max_spacing = max((row["d"] for row in feasible_rows), default=None)
        max_spacing_rows = (
            [row for row in feasible_rows if row["d"] == max_spacing]
            if max_spacing is not None else []
        )
        # A igual interdistancia, el candidato representativo ha de seguir
        # el mismo criterio de seleccion: menor flujo y despues menor tilt.
        best_spacing = min(
            max_spacing_rows,
            key=lambda row: (row.get("phi_lm", float("inf")), row["tilt_deg"]),
            default=None,
        )
        candidate_summary.append({
            "optic": summary_optic,
            "evaluated": len(optic_rows),
            "feasible": len(feasible_rows),
            "max_feasible_spacing_m": (
                best_spacing["d"] if best_spacing is not None else None
            ),
            "best_at_max_spacing": best_spacing,
        })

    return {
        # Distinguir una solución real de la salida diagnóstica de último
        # recurso. El diseñador de túnel usa esta marca para poder cambiar la
        # disposición física antes de acabar con una retícula de 1 m.
        "feasible": best is not None,
        "d_opt":    round(d_opt, 2),
        "optic":    optic,
        "tilt_deg": tilt,
        "model":    sel["model"],
        "mA":       sel["mA"],
        "W":        sel["W"],
        "lm":       round(sel["lm"], 0),
        "phi_lm":   round(float(phi), 3),
        "U0":       round(U0f, 3),
        "Ul":       round(Ulf, 3),
        "L_est":    round(L_est, 1),
        "optimization_goal": goal,
        "power_per_m": round(float(sel["W"]) / max(d_opt, 1e-9), 3),
        "spacing_quantum_m": float(spacing_quantum_m),
        "candidate_summary": candidate_summary,
        "candidate_trace": candidate_trace,
        "warnings": warnings_out,
    }


# ── Fase 2/3: Optimizador por luminaria ───────────────────────────────────────

def select_geometry_for_spacing(
    L_req, d, h, w, U0_obj, Ul_obj, I_max_mA, cct,
    rtable="R2", mf=0.70, arrangement="central_single",
    I_min_pct=0.30, tilt_grid=None, wall_offset=_WALL_Y_DEFAULT,
    direction=1.0,
    speed_kmh=None, flicker_min_hz=None, flicker_max_hz=None,
) -> dict | None:
    """Selecciona optica y tilt antes de asignar modelo/driver.

    Las opticas se recorren estrictamente en el orden OPTICS. Dentro de la
    primera optica factible se conserva el tilt que necesita menos flujo para
    la luminancia objetivo.
    """
    if tilt_grid is None:
        tilt_grid = [0.0, 5.0, 10.0, 15.0, 20.0]
    if speed_kmh and _flicker_forbidden(
        d, speed_kmh, flicker_min_hz, flicker_max_hz,
    ):
        return None

    lm_max, _ = flux_power_at_current(
        CHAIN_ORDER[-1], cct, I_max_mA, I_min_pct,
    )
    for optic in OPTICS:
        candidates = []
        for tilt in tilt_grid:
            U0, Ul = eval_quality(
                optic, d, h, w, tilt, rtable, mf, arrangement,
                wall_offset=wall_offset, direction=direction,
            )
            if U0 < U0_obj or Ul < Ul_obj:
                continue
            phi = phi_for_luminance(
                optic, d, h, w, tilt, L_req, arrangement, rtable, mf,
                wall_offset=wall_offset, direction=direction,
            )
            if phi <= lm_max * (1.0 + 1e-9):
                candidates.append({
                    "optic": optic,
                    "tilt_deg": float(tilt),
                    "d": float(d),
                    "phi_lm": float(phi),
                    "U0": float(U0),
                    "Ul": float(Ul),
                })
        if candidates:
            return min(
                candidates,
                key=lambda item: (item["phi_lm"], item["tilt_deg"]),
            )
    return None


def optimize_single_luminaire(
    L_req, d, h, w, U0_obj, I_max_mA, cct,
    rtable="R2", mf=0.70, arrangement="central_single",
    I_min_pct=0.30, tilt_grid=None,
    wall_offset=_WALL_Y_DEFAULT, Ul_obj=None, direction=1.0,
) -> dict:
    """
    Para una luminaria en transicion/umbral:
    (optica, tilt, modelo, mA, W) con minima corriente que cumple
    L_req y U0 >= U0_obj (y Ul >= Ul_obj si se indica).

    Primero se filtra por calidad (U0/Ul, independientes del flujo) y solo
    entre las combinaciones que la cumplen se ajusta la potencia (corriente
    minima). Se prueban las opticas en orden de eficiencia (OPTICS: F151 ->
    F2MD -> F2M2) y se PARA en la primera que, con algun tilt, cumpla calidad
    -- sin seguir probando opticas menos eficientes una vez hay solucion.
    """
    if tilt_grid is None:
        tilt_grid = [0.0, 5.0, 10.0, 15.0, 20.0]

    best = None

    for optic in OPTICS:
        optic_best = None
        for tilt in tilt_grid:
            U0, Ul = eval_quality(optic, d, h, w, tilt, rtable, mf, arrangement,
                                 wall_offset=wall_offset, direction=direction)
            if U0 < U0_obj or (Ul_obj is not None and Ul < Ul_obj):
                continue
            # Objetivo L_req (media, target normativo CIE 88/140).
            phi = phi_for_luminance(optic, d, h, w, tilt, L_req,
                                    arrangement, rtable, mf, wall_offset=wall_offset,
                                    direction=direction)
            sel = select_model_for_flux(phi, cct, I_max_mA, I_min_pct)
            if optic_best is None or sel["mA"] < optic_best["mA"]:
                L_est = L_from_flux(optic, d, h, w, tilt, sel["lm"], arrangement, rtable, mf,
                                    wall_offset=wall_offset, direction=direction)
                optic_best = {
                    "optic": optic, "tilt_deg": tilt,
                    "model": sel["model"], "mA": sel["mA"],
                    "W": sel["W"], "lm": round(sel["lm"],0),
                    "U0": round(U0,3), "Ul": round(Ul,3), "L_est": round(L_est,1),
                    "warning": None,
                }

        if optic_best is not None:
            best = optic_best
            break

    if best is None:
        # NOTA: este fallback NUNCA deberia dispararse para llamadas que provienen
        # de find_dmax_for_zone (que pre-valida que d es factible antes de llamar
        # aqui). Se mantiene por compatibilidad con el modo retrofit (d_fixed,
        # donde d es una restriccion externa real y no se puede re-optimizar) y
        # queda marcado explicitamente como no-factible via 'feasible': False para
        # que el llamador SIEMPRE emita un warning visible en vez de aceptar el
        # resultado en silencio.
        optic, tilt = "F2M2", 0.0
        U0, _ = eval_quality(optic, d, h, w, tilt, rtable, mf, arrangement, direction=direction)
        phi   = phi_for_luminance(optic, d, h, w, tilt, L_req,
                                  arrangement, rtable, mf, direction=direction)
        sel   = select_model_for_flux(phi, cct, I_max_mA, I_min_pct)
        L_est = L_from_flux(optic, d, h, w, tilt, sel["lm"], arrangement, rtable, mf, direction=direction)
        best  = {
            "optic": optic, "tilt_deg": tilt,
            "model": sel["model"], "mA": sel["mA"],
            "W": sel["W"], "lm": round(sel["lm"],0),
            "U0": round(U0,3), "L_est": round(L_est,1),
            "feasible": False,
            "warning": (f"⚠️ U0_obj={U0_obj} NO ALCANZABLE a d={d:.1f}m con ninguna "
                        f"optica+tilt (U0 resultante={U0:.3f}). Requiere reducir d."),
        }
    else:
        best["feasible"] = True
        best.setdefault("warning", None)
    return best


# ── Fase 2b: busqueda de d factible (quality + flux) por zona ────────────────

def _flicker_forbidden(d, speed_kmh, f_min, f_max):
    """True si la interdistancia d produce parpadeo en la banda critica
    (CIE 88: f = v/d, critica aprox. 2.5-15 Hz)."""
    if not speed_kmh or float(speed_kmh) <= 0 or not d or d <= 0:
        return False
    f = (float(speed_kmh) / 3.6) / float(d)
    lo = max(0.0, float(f_min or 0.0))
    hi = max(lo, float(f_max or 0.0))
    return lo <= f <= hi


def find_dmax_for_zone(
    L_req, h, w, U0_obj, Ul_obj, I_max_mA, cct,
    rtable="R2", mf=0.70, arrangement="central_single",
    I_min_pct=0.30, tilt_grid=None, d_min=2.5, d_max_hard=25.0,
    wall_offset=_WALL_Y_DEFAULT, tandem=False, direction=1.0,
    speed_kmh=None, flicker_min_hz=None, flicker_max_hz=None,
    _no_flicker=False,
) -> dict:
    """
    Busca, sobre la malla (optica x tilt), el mayor d tal que se puedan
    satisfacer SIMULTANEAMENTE:
      - Calidad:  U0 >= U0_obj  Y  Ul >= Ul_obj  (independiente del flujo)
      - Flujo:    la luminancia L_req (o L_req/2 si tandem=True) es alcanzable
                  con el modelo/corriente disponibles hasta I_max_mA.

    Para cada combo (optica, tilt) se muestrea conjuntamente calidad Y flujo
    sobre [d_min, d_max_hard] y se toma el mayor d que cumple AMBAS
    condiciones SIMULTANEAMENTE (ver nota abajo — NO se puede calcular
    d_quality_max y d_flux_max por separado y tomar min(), porque U0/Ul en
    funcion de d no son monotonos en general).

    Se elige el combo que maximiza d_feasible (mismo criterio que optimize_interior).

    Retorna dict con 'feasible': False si NINGUN combo alcanza d_min con
    calidad Y flujo satisfechos simultaneamente (caso de infactibilidad fisica
    real) — el llamador DEBE emitir un warning explicito en ese caso, nunca
    aceptar en silencio un resultado que viole U0_obj/Ul_obj.

    NOTA (bug corregido): antes se calculaba d_quality_max = find_dmax_for_quality(...)
    y d_flux_max (biseccion asumiendo flujo monotono creciente en d, lo cual SI
    es correcto) por separado, y se tomaba d_feasible = min(d_quality_max, d_flux_max).
    Esto es invalido porque U0/Ul NO son monotonos en d: hay combinaciones optica+tilt
    donde la calidad es mala a d pequeno, buena a d intermedio y mala otra vez a d
    grande (para z. ej. tilt alto, la celda muy corta bajo la luminaria produce un
    pico local que baja U0). d_quality_max localiza el mayor d con calidad OK, pero
    eso NO implica que TODO d <= d_quality_max tambien cumpla calidad. Si
    d_flux_max resultaba menor que d_quality_max, el min() podia caer en una zona
    de d donde la calidad real ya NO se cumplia — produciendo un resultado
    'feasible: True' con U0/Ul realmente incumplidos (el bug reportado: L_est
    llegaba al objetivo pero U0 quedaba muy por debajo de U0_obj). La solucion:
    muestrear d directamente pidiendo calidad Y flujo simultaneos en cada punto.
    """
    if tilt_grid is None:
        tilt_grid = [0.0, 5.0, 10.0, 15.0, 20.0]

    L_target = (L_req / 2.0) if tandem else L_req
    lm_max, _ = flux_power_at_current(CHAIN_ORDER[-1], cct, I_max_mA, I_min_pct)

    best = None  # {"d", "optic", "tilt"}

    # Igual que optimize_interior: probar las opticas por orden de eficiencia,
    # pero elegir globalmente la que permita mayor interdistancia. El orden
    # F151 -> F2MD -> F2M2 solo desempata soluciones con la misma d.
    _apply_flicker = not _no_flicker and bool(speed_kmh)
    for optic in OPTICS:
        optic_best = None
        for tilt in tilt_grid:
            def _combined_ok(d, _optic=optic, _tilt=tilt):
                if _apply_flicker and _flicker_forbidden(
                    d, speed_kmh, flicker_min_hz, flicker_max_hz,
                ):
                    return False
                U0, Ul = eval_quality(_optic, d, h, w, _tilt, rtable, mf, arrangement,
                                      wall_offset=wall_offset, direction=direction)
                if U0 < U0_obj or Ul < Ul_obj:
                    return False
                phi = phi_for_luminance(_optic, d, h, w, _tilt, L_target,
                                        arrangement, rtable, mf, wall_offset=wall_offset,
                                        direction=direction)
                return phi <= lm_max

            d_feasible, feasible = _find_dmax_adaptive(_combined_ok, d_min, d_max_hard)
            if not feasible or d_feasible < d_min:
                continue

            if optic_best is None or d_feasible > optic_best["d"]:
                optic_best = {"d": d_feasible, "optic": optic, "tilt": tilt}

        if optic_best is not None and (best is None or optic_best["d"] > best["d"]):
            best = optic_best

    if best is None:
        if _apply_flicker:
            fallback = find_dmax_for_zone(
                L_req, h, w, U0_obj, Ul_obj, I_max_mA, cct,
                rtable=rtable, mf=mf, arrangement=arrangement,
                I_min_pct=I_min_pct, tilt_grid=tilt_grid, d_min=d_min,
                d_max_hard=d_max_hard, wall_offset=wall_offset,
                tandem=tandem, direction=direction,
                speed_kmh=speed_kmh, flicker_min_hz=flicker_min_hz,
                flicker_max_hz=flicker_max_hz, _no_flicker=True,
            )
            if fallback.get('feasible'):
                fallback['flicker_unavoidable'] = True
            return fallback
        return {
            "feasible": False, "d": round(d_min, 2), "optic": None, "tilt_deg": None,
            "model": None, "mA": 0.0, "W": 0.0, "lm": 0.0,
            "U0": 0.0, "Ul": 0.0, "L_est": 0.0,
            "warning": (
                f"⚠️ INFACTIBLE: ninguna combinacion optica+tilt alcanza "
                f"U0>={U0_obj}/Ul>={Ul_obj} Y el flujo requerido para "
                f"L_req={L_req:.0f} cd/m2 a d>={d_min} m"
                + (" incluso en tandem" if tandem else "") + ". "
                "Posibles soluciones: aumentar el flujo/corriente (I_max o modelo de "
                "mayor potencia), reducir la interdistancia minima, o replantear la "
                "boca del tunel (orientacion, pantallas o apantallamiento de luz "
                "diurna para bajar el L20/Lth exigido)."
            ),
        }

    d_use, optic, tilt = round(best["d"], 2), best["optic"], best["tilt"]
    U0f, Ulf = eval_quality(optic, d_use, h, w, tilt, rtable, mf, arrangement,
                            wall_offset=wall_offset, direction=direction)
    phi   = phi_for_luminance(optic, d_use, h, w, tilt, L_target,
                              arrangement, rtable, mf, wall_offset=wall_offset,
                              direction=direction)
    sel   = select_model_for_flux(phi, cct, I_max_mA, I_min_pct)
    L_unit = L_from_flux(optic, d_use, h, w, tilt, sel["lm"], arrangement, rtable, mf,
                         wall_offset=wall_offset, direction=direction)
    L_total = 2.0 * L_unit if tandem else L_unit

    return {
        "feasible": True,
        "d":        d_use,
        "optic":    optic,
        "tilt_deg": tilt,
        "model":    sel["model"],
        "mA":       sel["mA"],
        "W":        sel["W"],
        "lm":       round(sel["lm"], 0),
        "U0":       round(U0f, 3),
        "Ul":       round(Ulf, 3),
        "L_est":    round(L_total, 1),
        "warning":  None,
    }


# ── Curva CIE 88 de transicion ────────────────────────────────────────────────

def cie88_L_transition(s, s_start, Lth, Lin, speed_kmh):
    """Alias compatible de la fuente unica de Lreq."""
    return cie88_transition_luminance(
        s, s_start, Lth, Lin, speed_kmh,
    )
