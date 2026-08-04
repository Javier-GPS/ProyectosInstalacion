"""
SALVI Tunnel Engine — Módulo de Cálculo de Luminarias APHEX
Algoritmo inside-out (CIE 88:2004): diseña desde la zona interior (menor
luminancia requerida) hacia la boca de entrada (mayor luminancia), manteniendo
el espaciado fijo y aumentando corriente/modelo según sea necesario.

Cadena APHEX:  S/50G → M/100G → L/150G
Corrientes:    350 mA → 500 mA → 750 mA (≤ I_max del proyecto)
Ópticas:       F151 (w/h < 0.8)  · F2M2 (0.8 ≤ w/h < 1.6)  · F2MD (w/h ≥ 1.6)

Tablas UF/Ul: calculadas a partir de los ficheros LDT de fotometría real de
las ópticas METRO M H50 (F2M2, F2MD, F151) — cálculo por integración directa.

Referencias:
    CIE 88:2004 §15–16 (criterios de luminancia en túneles)
    Eulumdat photometry files — SALVI (Julio 2026)
"""

import copy
import math
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from modules.tunnel.required_luminance import (
    cie88_transition_luminance,
    daylight_contribution_for_zone,
    required_luminance_for_zone,
)


# ══════════════════════════════════════════════════════════════════════════════
# SUPERFICIES DE CALZADA
# ══════════════════════════════════════════════════════════════════════════════

ROAD_SURFACES: Dict[str, dict] = {
    "dark_asphalt":   {"label": "Asfalto oscuro (R3)",       "rho": 0.065},
    "medium_asphalt": {"label": "Asfalto medio (R2)",         "rho": 0.085},
    "light_asphalt":  {"label": "Asfalto claro (R1)",         "rho": 0.105},
    "concrete":       {"label": "Hormigón (C1/C2)",           "rho": 0.140},
    "bright_concrete":{"label": "Hormigón claro",             "rho": 0.165},
}

DEFAULT_MF = 0.70

# Longitud del cuerpo APHEX en la direccion del tunel (m) — distancia entre
# los dos del par en tandem. Las tres familias (S/M/L) miden 500 mm en esta
# direccion (confirmado por el usuario), aunque el cuerpo optico completo
# tenga distinta anchura/profundidad transversal segun el modelo.
_BODY_LEN: Dict[str, float] = {"S": 0.50, "M": 0.50, "L": 0.50}

# Motor nuevo (led_engine): 9 variantes identificadas por variant_id
# (p.ej. "APHEX_S_75W"). Mismo valor para las tres familias (ver nota arriba).
from modules.tunnel import led_engine as _led_eng
_BODY_LEN_BY_FAMILY: Dict[str, float] = {"APHEX_S": 0.50, "APHEX_M": 0.50, "APHEX_L": 0.50}

def _body_len_for(model_id: str) -> float:
    variant = _led_eng.VARIANTS_BY_ID.get(model_id)
    if variant is not None:
        return _BODY_LEN_BY_FAMILY.get(variant.family, 0.50)
    return _BODY_LEN.get(model_id, 0.50)   # compat con el motor legacy

def _commercial_name_for(model_id: str) -> str:
    variant = _led_eng.VARIANTS_BY_ID.get(model_id)
    return variant.commercial_name if variant is not None else str(model_id)

# ══════════════════════════════════════════════════════════════════════════════
# ARREGLOS DE LUMINARIAS
# ══════════════════════════════════════════════════════════════════════════════

ARRANGEMENTS = {
    "central_single": {"label": "Fila central única (eje)",           "n_rows": 1, "lut_key": "central"},
    "central_offset": {"label": "Fila central desplazada del eje",    "n_rows": 1, "lut_key": "central"},
    "central_double": {"label": "Doble fila central",                 "n_rows": 2, "lut_key": "central"},
    "lateral_left":   {"label": "Lateral izquierda (sentido marcha)", "n_rows": 1, "lut_key": "lateral_right"},
    "lateral_right":  {"label": "Lateral derecha (sentido marcha)",   "n_rows": 1, "lut_key": "lateral_right"},
    "bilateral_sym":  {"label": "Bilateral simétrico",                "n_rows": 2, "lut_key": "lateral_right"},
    "bilateral_stag": {"label": "Bilateral en tresbolillo",           "n_rows": 2, "lut_key": "lateral_right"},
    # Legacy
    "bilateral":      {"label": "Bilateral",                          "n_rows": 2, "lut_key": "lateral_right"},
    "unilateral":     {"label": "Unilateral",                         "n_rows": 1, "lut_key": "lateral_right"},
    "staggered":      {"label": "Tresbolillo",                        "n_rows": 2, "lut_key": "lateral_right"},
}

_PAIRED_PHYSICAL_ARRANGEMENTS = {
    "central_double", "bilateral_sym", "bilateral",
}


def physical_luminaires_per_setpoint(arrangement: str) -> int:
    """Número de equipos físicos representados por un setpoint longitudinal.

    En tresbolillo cada setpoint es una única luminaria y el lado alterna con
    el índice. En disposiciones enfrentadas cada setpoint representa una
    luminaria en cada una de las dos filas.
    """
    return 2 if arrangement in _PAIRED_PHYSICAL_ARRANGEMENTS else 1


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO APHEX  (verificado contra hoja técnica — Julio 2026)
#
# Cadena S→M→L: sin solape en la unión S/M (M@350mA > S@750mA).
# Nota de producto: L@350mA (56.825/60.559 klm) < M@750mA (73.305/78.123 klm)
#   → el algoritmo inside-out lo gestiona correctamente: al no cubrir el requisito
#     con L@350mA pasa a L@500mA. L@350mA solo se selecciona para requisitos en
#     el rango 56.826–73.304 klm donde M@500mA tampoco llega.
# ══════════════════════════════════════════════════════════════════════════════

APHEX_CATALOG: Dict[str, dict] = {
    "S": {
        "pcb":   "50G",
        "label": "Aphex S",
        "dims_mm": (472, 400, 90),
        "operating_points": {
            "3000K": [
                {"mA": 350, "W":  97, "lm": 18941},
                {"mA": 500, "W": 143, "lm": 26057},
                {"mA": 750, "W": 223, "lm": 36652},
            ],
            "4000K": [
                {"mA": 350, "W":  97, "lm": 20186},
                {"mA": 500, "W": 143, "lm": 27769},
                {"mA": 750, "W": 223, "lm": 39061},
            ],
        },
    },
    "M": {
        "pcb":   "100G",
        "label": "Aphex M",
        "dims_mm": None,
        "operating_points": {
            "3000K": [
                {"mA": 350, "W": 194, "lm": 37883},
                {"mA": 500, "W": 286, "lm": 52114},
                {"mA": 750, "W": 446, "lm": 73305},
            ],
            "4000K": [
                {"mA": 350, "W": 194, "lm": 40372},
                {"mA": 500, "W": 286, "lm": 55539},
                {"mA": 750, "W": 446, "lm": 78123},
            ],
        },
    },
    "L": {
        "pcb":   "150G",
        "label": "Aphex L",
        "dims_mm": None,
        "operating_points": {
            "3000K": [
                {"mA": 350, "W": 292, "lm":  56825},
                {"mA": 500, "W": 429, "lm":  78122},
                {"mA": 750, "W": 670, "lm": 109958},
            ],
            "4000K": [
                {"mA": 350, "W": 292, "lm":  60559},
                {"mA": 500, "W": 429, "lm":  83309},
                {"mA": 750, "W": 670, "lm": 117184},
            ],
        },
    },
}

# Orden de la cadena S → M → L
APHEX_CHAIN_ORDER = ["S", "M", "L"]


# ══════════════════════════════════════════════════════════════════════════════
# TABLAS UF Y d/h_max  (calculadas desde LDT reales — integración directa)
#
# UF: factor de utilización por fila de luminarias (fracción de flujo que
#     llega a la calzada) — casi constante con d/h, se usa valor a d/h=2.0.
# dh_max: máximo d/h que cumple Ul ≥ 0.6 (CIE 88:2004)
#
# Clave de wh: relación ancho_calzada / altura_montaje
# ══════════════════════════════════════════════════════════════════════════════

# Factor de utilización representativo por óptica, arreglo y relación w/h
# Interpolación lineal para valores intermedios de w/h
_UF_TABLE: Dict[str, Dict[str, Dict[str, float]]] = {
    "F2M2": {
        "central": {
            "0.5": 0.2504, "0.8": 0.3819, "1.0": 0.4608,
            "1.2": 0.5334, "1.5": 0.6310, "2.0": 0.7598,
            "2.5": 0.8464, "3.0": 0.8999,
        },
        "lateral_right": {
            "0.5": 0.1993, "0.8": 0.2639, "1.0": 0.2929,
            "1.2": 0.3143, "1.5": 0.3362, "2.0": 0.3559,
            "2.5": 0.3653, "3.0": 0.3701,
        },
    },
    "F2MD": {
        "central": {
            "0.5": 0.2590, "0.8": 0.3819, "1.0": 0.4510,
            "1.2": 0.5162, "1.5": 0.6116, "2.0": 0.7525,
            "2.5": 0.8520, "3.0": 0.9120,
        },
        "lateral_right": {
            "0.5": 0.1615, "0.8": 0.1781, "1.0": 0.1840,
            "1.2": 0.1885, "1.5": 0.1935, "2.0": 0.1987,
            "2.5": 0.2015, "3.0": 0.2031,
        },
    },
    "F151": {
        "central": {
            "0.5": 0.2329, "0.8": 0.3766, "1.0": 0.4656,
            "1.2": 0.5469, "1.5": 0.6539, "2.0": 0.7850,
            "2.5": 0.8632, "3.0": 0.9094,
        },
        "lateral_right": {
            "0.5": 0.1112, "0.8": 0.1333, "1.0": 0.1435,
            "1.2": 0.1511, "1.5": 0.1588, "2.0": 0.1664,
            "2.5": 0.1713, "3.0": 0.1742,
        },
    },
}

# Máximo d/h para Ul ≥ 0.6
_DH_MAX_TABLE: Dict[str, Dict[str, Dict[str, float]]] = {
    "F2M2": {
        "central": {
            "0.5": 2.64, "0.8": 2.64, "1.0": 2.64,
            "1.2": 2.64, "1.5": 2.64, "2.0": 2.64,
            "2.5": 2.64, "3.0": 2.64,
        },
        "lateral_right": {
            "0.5": 2.67, "0.8": 2.67, "1.0": 2.67,
            "1.2": 2.67, "1.5": 2.67, "2.0": 2.67,
            "2.5": 2.67, "3.0": 2.67,
        },
    },
    "F2MD": {
        "central": {
            "0.5": 2.83, "0.8": 2.83, "1.0": 2.83,
            "1.2": 2.83, "1.5": 2.31, "2.0": 2.31,
            "2.5": 2.31, "3.0": 2.32,
        },
        "lateral_right": {
            "0.5": 2.83, "0.8": 2.31, "1.0": 2.31,
            "1.2": 2.31, "1.5": 2.31, "2.0": 2.31,
            "2.5": 2.31, "3.0": 2.31,
        },
    },
    "F151": {
        "central": {
            "0.5": 2.07, "0.8": 2.07, "1.0": 2.08,
            "1.2": 2.07, "1.5": 2.07, "2.0": 2.07,
            "2.5": 2.08, "3.0": 2.08,
        },
        "lateral_right": {
            "0.5": 2.49, "0.8": 2.49, "1.0": 2.49,
            "1.2": 2.49, "1.5": 2.49, "2.0": 2.49,
            "2.5": 2.38, "3.0": 2.38,
        },
    },
}

_WH_BREAKPOINTS = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]


def _interp_wh(table_by_wh: Dict[str, float], wh: float) -> float:
    """Interpolación lineal de UF o dh_max según w/h."""
    wh = max(0.5, min(wh, 3.0))
    bps = _WH_BREAKPOINTS
    if wh <= bps[0]:
        return table_by_wh[f"{bps[0]:.1f}"]
    if wh >= bps[-1]:
        return table_by_wh[f"{bps[-1]:.1f}"]
    for i in range(len(bps) - 1):
        lo, hi = bps[i], bps[i + 1]
        if lo <= wh <= hi:
            t = (wh - lo) / (hi - lo)
            v_lo = table_by_wh[f"{lo:.1f}"]
            v_hi = table_by_wh[f"{hi:.1f}"]
            return v_lo + t * (v_hi - v_lo)
    return table_by_wh[f"{bps[-1]:.1f}"]


def _lut_key(arrangement: str) -> str:
    return ARRANGEMENTS.get(arrangement, {}).get("lut_key", "central")


def lookup_uf(optic: str, wh: float, arrangement: str) -> float:
    """Devuelve el factor de utilización (UF) para óptica, geometría y arreglo."""
    key = _lut_key(arrangement)
    tbl = _UF_TABLE.get(optic, _UF_TABLE["F2M2"]).get(key, {})
    return _interp_wh(tbl, wh)


def lookup_dh_max(optic: str, wh: float, arrangement: str) -> float:
    """Devuelve el máximo d/h que cumple Ul ≥ 0.6."""
    key = _lut_key(arrangement)
    tbl = _DH_MAX_TABLE.get(optic, _DH_MAX_TABLE["F2M2"]).get(key, {})
    return _interp_wh(tbl, wh)


def auto_select_optic(optic_pref: str, wh: float) -> str:
    """Selección automática de óptica según relación w/h."""
    if optic_pref not in ("auto", ""):
        return optic_pref
    if wh < 0.8:
        return "F151"
    if wh < 1.6:
        return "F2M2"
    return "F2MD"


def _interp_op(ops: List[dict], target_lm: float) -> dict:
    """
    Interpolación lineal por tramos entre los puntos de operación (350/500/750 mA)
    para obtener la corriente exacta que produce target_lm.
    Devuelve {mA, W, lm} interpolados.
    """
    if target_lm <= ops[0]["lm"]:
        return dict(ops[0])
    if target_lm >= ops[-1]["lm"]:
        return dict(ops[-1])
    for i in range(len(ops) - 1):
        lo, hi = ops[i], ops[i + 1]
        if lo["lm"] <= target_lm <= hi["lm"]:
            t = (target_lm - lo["lm"]) / (hi["lm"] - lo["lm"])
            return {
                "mA": round(lo["mA"] + t * (hi["mA"] - lo["mA"])),
                "W":  round(lo["W"]  + t * (hi["W"]  - lo["W"]),  1),
                "lm": target_lm,
            }
    return dict(ops[-1])


def select_aphex_continuous(
    phi_required: float,
    cct:          str,
    I_max_mA:     int,
) -> dict:
    """
    Selección continua S→M→L con interpolación lineal por tramos.

    Dentro de cada modelo la corriente varía libremente entre 350 mA e I_max_mA
    (sin saltos discretos). Se usa el primer modelo cuyo rango [lm_min, lm_max]
    cubre phi_required. Si phi_required < lm_min del modelo actual se devuelve
    ese modelo a corriente mínima (350 mA). Si supera todos los modelos se
    devuelve L a I_max_mA (insuficiente → el llamador reduce el espaciado).

    Devuelve: {model, pcb, label, mA, W, lm}
    """
    for model_key in APHEX_CHAIN_ORDER:
        cat  = APHEX_CATALOG[model_key]
        ops  = cat["operating_points"].get(cct, [])
        if not ops:
            continue

        # Recortar a I_max_mA (interpolando el punto límite si queda entre dos)
        valid_ops = [op for op in ops if op["mA"] <= I_max_mA]
        if not valid_ops:
            # I_max_mA < 350 mA — usar mínimo disponible
            valid_ops = [ops[0]]

        # Si I_max_mA queda entre dos puntos de catálogo, añadir punto interpolado
        max_cat_mA = valid_ops[-1]["mA"]
        if max_cat_mA < I_max_mA and len(ops) > len(valid_ops):
            next_op = ops[len(valid_ops)]
            lo, hi  = valid_ops[-1], next_op
            t_cut   = (I_max_mA - lo["mA"]) / (hi["mA"] - lo["mA"])
            valid_ops.append({
                "mA": I_max_mA,
                "W":  round(lo["W"] + t_cut * (hi["W"] - lo["W"]), 1),
                "lm": round(lo["lm"] + t_cut * (hi["lm"] - lo["lm"]), 0),
            })

        lm_max = valid_ops[-1]["lm"]

        if phi_required <= lm_max:
            interp = _interp_op(valid_ops, phi_required)
            return {
                "model": model_key,
                "pcb":   cat["pcb"],
                "label": cat["label"],
                **interp,
            }

    # phi_required supera todos los modelos → L a I_max_mA
    cat     = APHEX_CATALOG["L"]
    ops     = cat["operating_points"].get(cct, [])
    valid_ops = [op for op in ops if op["mA"] <= I_max_mA] or [ops[0]]
    if I_max_mA < valid_ops[-1]["mA"] and len(ops) > len(valid_ops):
        next_op = ops[len(valid_ops)]
        lo, hi  = valid_ops[-1], next_op
        t_cut   = (I_max_mA - lo["mA"]) / (hi["mA"] - lo["mA"])
        valid_ops.append({
            "mA": I_max_mA,
            "W":  round(lo["W"] + t_cut * (hi["W"] - lo["W"]), 1),
            "lm": round(lo["lm"] + t_cut * (hi["lm"] - lo["lm"]), 0),
        })
    max_op = valid_ops[-1]
    return {
        "model": "L",
        "pcb":   cat["pcb"],
        "label": cat["label"],
        "mA":    max_op["mA"],
        "W":     max_op["W"],
        "lm":    max_op["lm"],
    }


def build_aphex_chain(cct: str, I_max_mA: int) -> List[dict]:
    """Compat: devuelve los extremos de cada modelo para fijar el espaciado interior."""
    chain = []
    for model in APHEX_CHAIN_ORDER:
        cat = APHEX_CATALOG[model]
        ops = [op for op in cat["operating_points"].get(cct, []) if op["mA"] <= I_max_mA]
        if ops:
            chain.append({
                "model": model, "pcb": cat["pcb"], "label": cat["label"],
                "mA": ops[0]["mA"], "W": ops[0]["W"], "lm": ops[0]["lm"],
            })
    chain.sort(key=lambda x: x["lm"])
    return chain


# ══════════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ZoneLuminaireDesign:
    """Diseño de luminarias para una zona del túnel — algoritmo inside-out."""
    zone_type:      str
    zone_name:      str
    s_start:        float
    s_end:          float
    zone_length:    float
    L_required:     float
    E_required:     float
    # Selección de luminaria
    model:          str       # S, M, L
    pcb:            str       # 50G, 100G, 150G
    current_mA:     int
    flux_lm:        float     # flujo por luminaria (lm)
    power_w:        float     # potencia por luminaria (W)
    optic:          str       # F2M2, F2MD, F151
    # Diseño espacial
    d_max_ul:       float     # máximo espaciado por Ul (m)
    d_used:         float     # espaciado efectivo (m)
    n_luminaires:   int       # luminarias en la zona
    # Resultados
    L_estimated:    float
    UF:             float
    # Potencias
    power_zone_w:   float
    flux_zone_lm:   float
    power_density_wm2: float
    # Retrocompat
    d_max:          float = 0.0   # alias de d_used (para motor de cálculo)
    # Perfil por luminaria (solo zonas de transición — DALI individual)
    setpoints:      List[dict] = field(default_factory=list)
    tilt_deg:        float = 0.0   # inclinación hacia el portal (°)
    n_tandem:        int   = 1     # luminarias físicas por posición (1=normal, 2=tándem)
    tandem_offset_m: float = 0.0   # separación entre las dos del par (m)
    Ul:              float = 0.0   # uniformidad longitudinal (U0 va en UF, ver arriba)
    # Validacion directa del layout fisico completo (incluye zonas vecinas).
    profile_L_avg:   Optional[float] = None
    profile_L_min:   Optional[float] = None
    profile_min_ratio: Optional[float] = None
    profile_median_ratio: Optional[float] = None
    profile_p95_ratio: Optional[float] = None
    profile_max_ratio: Optional[float] = None
    # Arquitectura multiescenario.
    control_layer: str = "legacy"       # permanent | reinforcement | legacy
    portal: Optional[str] = None         # A | B | None
    L_total_required: Optional[float] = None
    daylight_profile: Optional[dict] = None

    def to_dict(self) -> dict:
        def _s(v, d=2):
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                return None
            return round(v, d)
        return {
            "zone_type":          self.zone_type,
            "zone_name":          self.zone_name,
            "s_start":            self.s_start,
            "s_end":              self.s_end,
            "zone_length":        _s(self.zone_length, 1),
            "L_required":         _s(self.L_required, 1),
            "E_required":         _s(self.E_required, 1),
            "model":              self.model,
            "pcb":                self.pcb,
            "current_mA":         self.current_mA,
            "flux_lm":            _s(self.flux_lm, 0),
            "power_w":            _s(self.power_w, 0),
            "optic":              self.optic,
            "d_max_ul":           _s(self.d_max_ul, 2),
            "d_used":             _s(self.d_used, 2),
            "d_max":              _s(self.d_used, 2),
            "n_luminaires":       self.n_luminaires,
            "L_estimated":        _s(self.L_estimated, 1),
            "UF":                 _s(self.UF, 4),
            "Ul":                 _s(self.Ul, 4),
            "power_zone_w":       _s(self.power_zone_w, 0),
            "flux_zone_lm":       _s(self.flux_zone_lm, 0),
            "power_density_wm2":  _s(self.power_density_wm2, 2),
            "margin_pct":         round((self.L_estimated / self.L_required - 1) * 100, 1)
                                  if self.L_required > 0 else 0,
            "setpoints":          self.setpoints,   # lista vacía salvo en transiciones
            "tilt_deg":           _s(self.tilt_deg, 1),
            "n_tandem":           self.n_tandem,
            "tandem_offset_m":    round(self.tandem_offset_m, 2),
            "profile_L_avg":      _s(self.profile_L_avg, 2),
            "profile_L_min":      _s(self.profile_L_min, 2),
            "profile_min_ratio":  _s(self.profile_min_ratio, 4),
            "profile_median_ratio": _s(self.profile_median_ratio, 4),
            "profile_p95_ratio":  _s(self.profile_p95_ratio, 4),
            "profile_max_ratio":  _s(self.profile_max_ratio, 4),
            "control_layer":      self.control_layer,
            "portal":             self.portal,
            "L_total_required":   _s(self.L_total_required, 3),
            "daylight_profile":   self.daylight_profile,
        }


@dataclass
class LuminaireSpec:
    """Parámetros de la luminaria (compat con API existente)."""
    flux_lm:           float
    power_w:           float
    efficiency:        float
    mounting_height_m: float
    arrangement:       str
    maintenance_factor: float = DEFAULT_MF
    name:              str = ""

    @property
    def n_rows(self) -> int:
        return ARRANGEMENTS.get(self.arrangement, {}).get("n_rows", 1)

    @property
    def efficacy_lm_w(self) -> float:
        return self.flux_lm / self.power_w if self.power_w > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "name":              self.name,
            "flux_lm":           self.flux_lm,
            "power_w":           self.power_w,
            "efficiency":        self.efficiency,
            "mounting_height_m": self.mounting_height_m,
            "arrangement":       self.arrangement,
            "arrangement_label": ARRANGEMENTS.get(self.arrangement, {}).get("label", self.arrangement),
            "n_rows":            self.n_rows,
            "maintenance_factor":self.maintenance_factor,
            "efficacy_lm_w":     round(self.efficacy_lm_w, 1),
        }


@dataclass
class TunnelLuminaireResult:
    """Resultado completo del cálculo de luminarias."""
    tube_id:            str
    luminaire:          Optional[LuminaireSpec]
    road_surface_type:  str
    rho_eff:            float
    road_width_m:       float
    tube_length_m:      float
    optic:              str = ""
    cct:                str = ""
    I_max_mA:           int = 750
    arrangement:        str = ""
    zones:              List[ZoneLuminaireDesign] = field(default_factory=list)
    total_luminaires:   int   = 0
    total_power_w:      float = 0.0
    total_flux_lm:      float = 0.0
    avg_power_density_wm2: float = 0.0
    total_power_kw:     float = 0.0
    warnings:           List[str] = field(default_factory=list)
    architecture:       str = "legacy_zonal"
    scenarios:          Dict[str, dict] = field(default_factory=dict)
    performance:        Dict[str, object] = field(default_factory=dict)
    optimization_comparison: Dict[str, object] = field(default_factory=dict)
    daylight:           Dict[str, object] = field(default_factory=dict)

    def _compute_totals(self):
        physical_factor = physical_luminaires_per_setpoint(self.arrangement)
        self.total_luminaires = (
            sum(z.n_luminaires for z in self.zones) * physical_factor
        )
        self.total_power_w = (
            sum(z.power_zone_w for z in self.zones) * physical_factor
        )
        self.total_flux_lm = (
            sum(z.flux_zone_lm for z in self.zones) * physical_factor
        )
        self.total_power_kw   = round(self.total_power_w / 1000, 2)
        area = self.tube_length_m * self.road_width_m
        self.avg_power_density_wm2 = round(self.total_power_w / area if area > 0 else 0, 2)

    def to_dict(self) -> dict:
        self._compute_totals()
        physical_factor = physical_luminaires_per_setpoint(self.arrangement)
        layer_totals = {}
        for zone in self.zones:
            layer = str(getattr(zone, "control_layer", "legacy") or "legacy")
            bucket = layer_totals.setdefault(layer, {
                "n_positions": 0,
                "n_luminaires": 0,
                "power_kw": 0.0,
                "flux_lm": 0.0,
            })
            n_positions = int(zone.n_luminaires or 0)
            bucket["n_positions"] += n_positions
            bucket["n_luminaires"] += n_positions * physical_factor
            bucket["power_kw"] += (
                float(zone.power_zone_w or 0.0)
                * physical_factor
                / 1000.0
            )
            bucket["flux_lm"] += (
                float(zone.flux_zone_lm or 0.0) * physical_factor
            )
        for bucket in layer_totals.values():
            bucket["power_kw"] = round(bucket["power_kw"], 3)
            bucket["flux_lm"] = round(bucket["flux_lm"], 0)

        zone_payloads = []
        for zone in self.zones:
            payload = zone.to_dict()
            n_positions = int(zone.n_luminaires or 0)
            payload.update({
                "n_positions": n_positions,
                "n_luminaires": n_positions * physical_factor,
                "power_zone_positions_w": payload["power_zone_w"],
                "power_zone_w": round(
                    float(zone.power_zone_w or 0.0) * physical_factor, 0
                ),
                "flux_zone_positions_lm": payload["flux_zone_lm"],
                "flux_zone_lm": round(
                    float(zone.flux_zone_lm or 0.0) * physical_factor, 0
                ),
                "power_density_positions_wm2": payload["power_density_wm2"],
                "power_density_wm2": round(
                    float(zone.power_density_wm2 or 0.0) * physical_factor, 2
                ),
            })
            zone_payloads.append(payload)

        scenarios_payload = copy.deepcopy(self.scenarios)
        if physical_factor != 1:
            count_keys = {
                "active_luminaires",
                "off_luminaires",
                "driver_floor_luminaires",
                "active_base_luminaires",
                "reinforcement_active_luminaires",
            }
            total_keys = {"power_kw", "flux_lm"}
            for scene in scenarios_payload.values():
                if not isinstance(scene, dict):
                    continue
                for key in count_keys:
                    if isinstance(scene.get(key), (int, float)):
                        scene[key] *= physical_factor
                for key in total_keys:
                    if isinstance(scene.get(key), (int, float)):
                        scene[key] = round(
                            scene[key] * physical_factor, 3
                        )

        # La potencia instalada que se presenta al proyectista es la suma de
        # las potencias de cada luminaria con su consigna individual de la
        # escena Soleado.  En un diseño multiescena no siempre coincide con la
        # suma zonal histórica: esta última procede de los setpoints físicos
        # iniciales, mientras que Soleado contiene las consignas DALI finales
        # (incluidos los ajustes manuales y la optimización por escena).
        sunny_scene = scenarios_payload.get("sunny", {})
        sunny_power_kw = sunny_scene.get("power_kw")
        try:
            installed_power_kw = round(float(sunny_power_kw), 3)
            installed_power_source = "sunny_scene_currents"
        except (TypeError, ValueError):
            installed_power_kw = round(float(self.total_power_kw or 0.0), 3)
            installed_power_source = "physical_setpoints_fallback"
        calculation_stages = []
        if self.architecture == (
            "permanent_base_plus_portal_reinforcement"
        ):
            calculation_stages = [
                {
                    "stage": 1,
                    "id": "base",
                    "label": "BASE interior A–B",
                    "status": "frozen",
                    "geometry_locked": True,
                    **layer_totals.get("permanent", {}),
                },
                {
                    "stage": 2,
                    "id": "adaptation",
                    "label": "Adaptación crepuscular",
                    "status": "frozen",
                    "geometry_locked": True,
                    **layer_totals.get("adaptation", {}),
                },
                {
                    "stage": 3,
                    "id": "reinforcement",
                    "label": "Transiciones y umbrales",
                    "status": "optimized",
                    "geometry_locked": False,
                    **layer_totals.get("reinforcement", {}),
                },
            ]
        return {
            "tube_id":       self.tube_id,
            "architecture":  self.architecture,
            "layers":        layer_totals,
            "calculation_stages": calculation_stages,
            "scenarios":     scenarios_payload,
            "performance":   self.performance,
            "optimization_comparison": self.optimization_comparison,
            "daylight":      self.daylight,
            "luminaire":     self.luminaire.to_dict() if self.luminaire else None,
            "optic":         self.optic,
            "cct":           self.cct,
            "I_max_mA":      self.I_max_mA,
            "arrangement":   self.arrangement,
            "road_surface":  {
                "type":  self.road_surface_type,
                "label": ROAD_SURFACES.get(self.road_surface_type, {}).get("label", ""),
                "rho":   self.rho_eff,
            },
            "road_width_m":  self.road_width_m,
            "tube_length_m": self.tube_length_m,
            "zones":         zone_payloads,
            "totals": {
                "n_positions":       sum(
                    int(z.n_luminaires or 0) for z in self.zones
                ),
                "n_luminaires":      self.total_luminaires,
                "power_kw":          self.total_power_kw,
                "installed_power_kw": installed_power_kw,
                "installed_power_source": installed_power_source,
                "flux_lm":           round(self.total_flux_lm, 0),
                "power_density_wm2": self.avg_power_density_wm2,
                "installed_lm_per_m": round(
                    self.total_flux_lm / self.tube_length_m
                    if self.tube_length_m > 0 else 0, 1
                ),
            },
            "warnings": self.warnings,
        }


# ══════════════════════════════════════════════════════════════════════════════
# ALGORITMO INSIDE-OUT
# ══════════════════════════════════════════════════════════════════════════════

def apply_manual_luminaire_overrides(
    result: TunnelLuminaireResult, overrides: dict | None,
) -> list[str]:
    """Apply traceable user edits to generated setpoints before CIE 140.

    The optimizer always creates the baseline first.  Overrides are keyed as
    ``<zone_name>|<setpoint_idx>`` and only alter a position, current or tilt.
    Flux and power are scaled from the selected APHEX operating point so the
    subsequent photometric verification evaluates the edited state, while the
    original design remains reproducible by removing the override.
    """
    if not isinstance(overrides, dict) or not overrides:
        return []
    warnings: list[str] = []
    for zone in result.zones:
        for setpoint in zone.setpoints or []:
            key = f"{zone.zone_name}|{int(setpoint.get('idx', 0) or 0)}"
            override = overrides.get(key)
            values = override.get("values", {}) if isinstance(override, dict) else {}
            if not isinstance(values, dict) or not values:
                continue
            if "s" in values:
                s_new = float(values["s"])
                if not (0.0 <= s_new <= float(result.tube_length_m) + 1e-6):
                    warnings.append(
                        f"{key}: progresiva manual fuera del túnel; se ignora."
                    )
                else:
                    setpoint["s"] = round(s_new, 3)
            if "tilt_deg" in values:
                setpoint["tilt_deg"] = round(float(values["tilt_deg"]), 2)
            if "current_mA" in values:
                old_current = max(
                    1e-6, float(setpoint.get("current_mA", 0.0) or 0.0)
                )
                new_current = max(0.0, float(values["current_mA"]))
                ratio = new_current / old_current
                setpoint["current_mA"] = round(new_current, 2)
                setpoint["flux_lm"] = round(
                    float(setpoint.get("flux_lm", 0.0) or 0.0) * ratio, 2
                )
                setpoint["power_w"] = round(
                    float(setpoint.get("power_w", 0.0) or 0.0) * ratio, 3
                )
                setpoint["L_est"] = round(
                    float(setpoint.get("L_est", 0.0) or 0.0) * ratio, 3
                )
            setpoint["manual_override"] = True
        if zone.setpoints:
            zone.n_luminaires = len(zone.setpoints)
            zone.power_zone_w = round(sum(
                float(item.get("power_w", 0.0) or 0.0)
                for item in zone.setpoints
            ), 3)
            zone.flux_zone_lm = round(sum(
                float(item.get("flux_lm", 0.0) or 0.0)
                for item in zone.setpoints
            ), 3)
    result._compute_totals()
    if overrides:
        warnings.append(
            f"Se aplicaron anulaciones manuales a {len(overrides)} posiciones."
        )
    return warnings


def apply_scene_current_overrides(
    result: TunnelLuminaireResult,
    overrides: dict | None,
    *,
    I_min_pct: float = 0.30,
) -> list[str]:
    """Apply manual DALI-current edits to a single operating scene.

    Unlike :func:`apply_manual_luminaire_overrides`, these edits never modify
    the installed luminaire design.  They only replace the operating point of
    ``<scene>|<zone_name>|<setpoint_idx>`` before its CIE 140 verification.
    A zero current explicitly turns that setpoint off; any positive current is
    constrained to the configured driver range and recalculated with the same
    APHEX electrical model used by the optimiser.
    """
    if not isinstance(overrides, dict) or not overrides:
        return []

    from modules.tunnel.optimizer import flux_power_at_current

    warnings: list[str] = []
    applied = 0
    cct = str(getattr(result, "cct", "4000K") or "4000K")
    i_max_mA = max(1.0, float(getattr(result, "I_max_mA", 750) or 750))
    raw_min = float(I_min_pct or 0.30)
    min_fraction = raw_min / 100.0 if raw_min > 1.0 else raw_min
    i_min_mA = max(1.0, min_fraction * 350.0)
    scene_keys = (
        "sunny", "normal", "overcast", "dusk",
        "night_normal", "night_reduced",
    )

    for zone in result.zones:
        layer = str(getattr(zone, "control_layer", "legacy") or "legacy")
        for setpoint in zone.setpoints or []:
            index = int(setpoint.get("idx", 0) or 0)
            operations = setpoint.setdefault("scenario_operating_points", {})
            for scene_key in scene_keys:
                key = f"{scene_key}|{zone.zone_name}|{index}"
                override = overrides.get(key)
                if override is None:
                    continue
                requested = (
                    override.get("current_mA")
                    if isinstance(override, dict)
                    else override
                )
                try:
                    requested_mA = float(requested)
                except (TypeError, ValueError):
                    warnings.append(
                        f"{key}: corriente de escena no vÃ¡lida; se ignora."
                    )
                    continue

                # Las escenas nocturnas son exclusivamente de la BASE
                # permanente; conservar esa arquitectura evita encender un
                # refuerzo de portal de forma silenciosa durante la noche.
                if scene_key.startswith("night_") and layer != "permanent":
                    warnings.append(
                        f"{key}: la capa de refuerzo permanece apagada de noche."
                    )
                    continue

                if scene_key == "night_normal":
                    fallback = {
                        "state": "on",
                        "current_mA": setpoint.get("current_mA", 0.0),
                        "flux_lm": setpoint.get("flux_lm", 0.0),
                        "power_w": setpoint.get("power_w", 0.0),
                        "driver_floor": False,
                    }
                elif scene_key == "night_reduced":
                    fallback = {
                        "state": "on",
                        "current_mA": setpoint.get("night_current_mA", 0.0),
                        "flux_lm": setpoint.get("night_flux_lm", 0.0),
                        "power_w": setpoint.get("night_power_w", 0.0),
                        "driver_floor": bool(
                            setpoint.get("night_driver_floor", False)
                        ),
                    }
                else:
                    fallback = None
                previous = dict(operations.get(scene_key) or fallback or {})
                if not previous:
                    warnings.append(
                        f"{key}: no existe una consigna DALI para esta escena."
                    )
                    continue

                if requested_mA <= 0.0:
                    previous.update({
                        "state": "off",
                        "current_mA": 0.0,
                        "flux_lm": 0.0,
                        "power_w": 0.0,
                        "driver_floor": False,
                        "manual_current_override": True,
                    })
                    operations[scene_key] = previous
                    applied += 1
                    continue

                current_mA = min(i_max_mA, max(i_min_mA, requested_mA))
                if abs(current_mA - requested_mA) > 1e-8:
                    warnings.append(
                        f"{key}: corriente limitada a {current_mA:.0f} mA "
                        f"(rango DALI {i_min_mA:.0f}-{i_max_mA:.0f} mA)."
                    )
                model = str(setpoint.get("model", zone.model) or zone.model)
                try:
                    flux_lm, power_w = flux_power_at_current(
                        model, cct, current_mA, min_fraction,
                    )
                except (KeyError, ValueError):
                    # Mantiene disponible el recÃ¡lculo para un modelo legado
                    # que no figure en el catÃ¡logo LED, sin simular un cambio
                    # de modelo. Los APHEX usan siempre la rama anterior.
                    old_current = max(
                        1e-6,
                        float(previous.get("current_mA", 0.0) or 0.0),
                    )
                    ratio = current_mA / old_current
                    flux_lm = float(previous.get("flux_lm", 0.0) or 0.0) * ratio
                    power_w = float(previous.get("power_w", 0.0) or 0.0) * ratio
                    warnings.append(
                        f"{key}: catÃ¡logo APHEX no disponible; se ha aplicado "
                        "una escala proporcional de respaldo."
                    )
                previous.update({
                    "state": "on",
                    "current_mA": round(current_mA, 2),
                    "flux_lm": round(float(flux_lm), 3),
                    "power_w": round(float(power_w), 3),
                    "driver_floor": abs(current_mA - i_min_mA) < 1e-6,
                    "manual_current_override": True,
                })
                operations[scene_key] = previous
                applied += 1

    if applied:
        warnings.append(
            f"Se aplicaron {applied} consignas manuales de corriente por escena."
        )
    return warnings


def _luminance(flux_lm: float, n_rows: int, uf: float, mf: float,
               rho_eff: float, d: float, w: float) -> float:
    """
    L [cd/m²] = Φ × n_rows × UF × MF × ρ_eff / (π × d × w)
    Fórmula de luminancia media CIE para calzada Lambertiana.
    """
    denom = math.pi * d * w
    return (flux_lm * n_rows * uf * mf * rho_eff / denom) if denom > 0 else 0.0


def _cie_L_transition(s: float, s_start: float, Lth: float, Lin: float,
                      speed_kmh: float) -> float:
    """
    Luminancia requerida en la zona de transición según CIE 88:2004 Fig. 6.6.
        L(t) = Lth × (1.9 + t)^(−1.4)
    donde t = tiempo desde inicio de transición = (s − s_start) / v_ms.
    Garantiza L ≥ Lin.
    """
    return cie88_transition_luminance(
        s, s_start, Lth, Lin, speed_kmh,
    )



def _zone_tilt_deg(zone_type: str, L_required: float = 0.0, L_interior: float = 0.0) -> float:
    """Inclinación recomendada de luminarias APHEX por tipo de zona (grados).
    Las zonas de umbral y transición se inclinan hacia el portal para
    aumentar la luminancia efectiva en la zona de adaptación visual.
    """
    t = zone_type.lower()
    if 'interior' in t:
        return 0.0
    if 'exit' in t or 'salida' in t or 'access' in t or 'parting' in t:
        return 0.0
    if 'transition' in t:
        return 5.0
    if 'threshold' in t:
        ratio = L_required / max(L_interior, 1.0)
        if ratio >= 15: return 20.0
        if ratio >= 8:  return 15.0
        if ratio >= 3:  return 10.0
        return 5.0
    return 0.0


def _design_zone_aphex(
    zone_type:   str,
    zone_name:   str,
    s_start:     float,
    s_end:       float,
    L_required:  float,
    chain:       List[dict],   # solo se usa para fallback de zona nula
    d_global:    float,
    d_max_ul:    float,
    uf:          float,
    n_rows:      int,
    mf:          float,
    rho_eff:     float,
    w:           float,
    optic:       str,
    warnings:    List[str],
    cct:         str   = "4000K",
    I_max_mA:    int   = 750,
    speed_kmh:   float = 80.0,
    Lth:         float = 0.0,
    Lin:         float = 0.0,
    L_interior:    float = 0.0,
    tandem_override: Optional[bool] = None,  # None=auto, True=forzar, False=desactivar
) -> ZoneLuminaireDesign:
    """
    Diseña una zona con selección CONTINUA de corriente (S→M→L).

    Zonas uniformes (umbral, interior, salida):
        Misma corriente en todas las luminarias. Espaciado = d_global; si la
        luminaria máxima no alcanza se reduce el espaciado.

    Zona de transición:
        Espaciado fijo = d_global (DALI permite dimming individual).
        Cada luminaria recibe la corriente exacta para producir la luminancia
        que indica la curva CIE 88:2004 en su posición.
        El ZoneLuminaireDesign retorna el perfil completo en `setpoints`.
    """
    zone_length = max(0.0, s_end - s_start)

    # Zona sin requisito de luminancia
    if L_required <= 0 or zone_length <= 0:
        op = chain[0] if chain else {"model": "S", "pcb": "50G", "mA": 350, "W": 97, "lm": 0, "label": "Aphex S"}
        return ZoneLuminaireDesign(
            zone_type=zone_type, zone_name=zone_name, s_start=s_start, s_end=s_end,
            zone_length=zone_length, L_required=L_required, E_required=0,
            model=op["model"], pcb=op["pcb"], current_mA=op["mA"],
            flux_lm=op["lm"], power_w=op["W"], optic=optic,
            d_max_ul=d_max_ul, d_used=0, n_luminaires=0,
            L_estimated=0, UF=uf, power_zone_w=0, flux_zone_lm=0, power_density_wm2=0,
            tilt_deg=0.0,
        )

    def phi_needed(d: float, L_req: float) -> float:
        denom = n_rows * uf * mf * rho_eff
        return (L_req * math.pi * d * w) / denom if denom > 0 else 1e9

    # Flujo máximo disponible (L @ I_max_mA)
    _ops_L   = APHEX_CATALOG["L"]["operating_points"].get(cct, [])
    _vops_L  = [op for op in _ops_L if op["mA"] <= I_max_mA] or [_ops_L[0]]
    lm_max_avail = _vops_L[-1]["lm"]

    # ── ZONA DE TRANSICIÓN: corriente individual CIE 88 por luminaria ──────
    is_transition = "transition" in zone_type.lower()
    if is_transition and Lth > 0 and Lin > 0 and speed_kmh > 0:

        # Determinar la corriente máxima necesaria (inicio de transición ~ Lth)
        phi_start  = phi_needed(d_global, Lth)
        auto_tandem = phi_start > lm_max_avail
        use_tandem  = (tandem_override if tandem_override is not None else auto_tandem)
        t_offset    = _BODY_LEN.get("L", 1.00) if use_tandem else 0.0  # par al inicio = modelo L

        if use_tandem and auto_tandem:
            # Tándem: 2× flujo → d_global es alcanzable
            d_try = d_global
            warnings.append(
                f"Zona {zone_name}: TÁNDEM AUTOMÁTICO — Lth={Lth:.0f} cd/m² no alcanzable "
                f"individual; par de luminarias por posición (offset {t_offset:.2f} m)"
            )
        elif auto_tandem:
            # Tándem forzado OFF: reducir d como antes
            denom = math.pi * w * Lth
            num   = lm_max_avail * n_rows * uf * mf * rho_eff
            d_try = max(0.5, min(num / denom if denom > 0 else d_global, d_max_ul))
            warnings.append(
                f"Zona {zone_name}: Lth={Lth:.0f} cd/m² no alcanzable con Aphex L "
                f"{I_max_mA} mA al espaciado global — d reducido a {d_try:.1f} m"
            )
        elif use_tandem:
            # Tándem FORZADO sobre zona que no lo necesitaba
            d_try    = d_global
            t_offset = _BODY_LEN.get("S", 0.50)
            warnings.append(f"Zona {zone_name}: TÁNDEM MANUAL activado")
        else:
            d_try = d_global

        n_groups = max(1, math.ceil(zone_length / d_try))
        d_actual = zone_length / n_groups
        n_lum    = n_groups * (2 if use_tandem else 1)  # físicas por lado

        # CIE 88 sentido de la transición (Portal A: Lth→Lin; Portal B: Lin→Lth)
        is_b = zone_type.lower() in ("transition_b",)

        setpoints = []
        pwr_zone  = 0.0
        flux_zone = 0.0
        L_sum     = 0.0

        for i in range(n_groups):
            # Posición central del hueco del grupo i
            if not is_b:
                s_i = s_start + (i + 0.5) * d_actual
                L_i = _cie_L_transition(s_i, s_start, Lth, Lin, speed_kmh)
            else:
                # Portal B: curva espejada → t medido desde el final
                s_i_mirror = s_end - (i + 0.5) * d_actual
                s_i = s_i_mirror   # posición central real (usada en s_phys más abajo)
                L_i = _cie_L_transition(s_end - s_i_mirror, s_start,
                                        Lth, Lin, speed_kmh)

            L_i   = max(L_i, Lin)
            n_ph  = 2 if use_tandem else 1
            phi_i = phi_needed(d_actual, L_i) / n_ph
            op_i  = select_aphex_continuous(phi_i, cct, I_max_mA)
            body  = _BODY_LEN.get(op_i["model"], 0.70) if use_tandem else 0.0

            pwr_zone  += op_i["W"] * n_ph
            flux_zone += op_i["lm"] * n_ph
            L_sum     += L_i

            if use_tandem:
                for idx_t, tag in enumerate(("A", "B")):
                    s_phys = round(s_i + (idx_t * 2 - 1) * body / 2, 2)
                    setpoints.append({
                        "idx":        i * 2 + idx_t + 1,
                        "s":          s_phys,
                        "L_req":      round(L_i, 1),
                        "model":      op_i["model"],
                        "current_mA": op_i["mA"],
                        "power_w":    op_i["W"],
                        "flux_lm":    round(op_i["lm"], 0),
                        "tandem":     tag,
                        "pair":       i,
                    })
            else:
                setpoints.append({
                    "idx":        i + 1,
                    "s":          round(s_start + (i + 0.5) * d_actual, 1),
                    "L_req":      round(L_i, 1),
                    "model":      op_i["model"],
                    "current_mA": op_i["mA"],
                    "power_w":    op_i["W"],
                    "flux_lm":    round(op_i["lm"], 0),
                })

        # Representativo: luminaria del extremo de mayor luminancia (inicio)
        dom   = setpoints[0] if not is_b else setpoints[-1]
        L_avg = L_sum / n_groups
        area  = zone_length * w
        E_req = L_required / rho_eff if rho_eff > 0 else 0.0

        return ZoneLuminaireDesign(
            zone_type=zone_type, zone_name=zone_name, s_start=s_start, s_end=s_end,
            zone_length=zone_length, L_required=L_required, E_required=round(E_req, 1),
            model=dom["model"], pcb=APHEX_CATALOG[dom["model"]]["pcb"],
            current_mA=dom["current_mA"],
            flux_lm=dom["flux_lm"], power_w=round(dom["power_w"], 1), optic=optic,
            d_max_ul=round(d_max_ul, 2), d_used=round(d_actual, 2),
            n_luminaires=n_lum, L_estimated=round(L_avg, 1),
            UF=round(uf, 4),
            power_zone_w=round(pwr_zone, 0),
            flux_zone_lm=round(flux_zone, 0),
            power_density_wm2=round(pwr_zone / area if area > 0 else 0, 3),
            d_max=round(d_actual, 2),
            setpoints=setpoints,
            tilt_deg=_zone_tilt_deg(zone_type, L_required, L_interior),
            n_tandem=2 if use_tandem else 1,
            tandem_offset_m=round(t_offset, 2),
        )

    # ── ZONAS UNIFORMES (umbral, interior, salida) ──────────────────────────
    D_MIN = 2.5   # m — espaciado mínimo práctico para luminarias de túnel

    # Decisión tándem —————————————————————————————————————————————————————
    phi_at_global = phi_needed(d_global, L_required)
    flux_shortage = phi_at_global > lm_max_avail

    if flux_shortage:
        denom            = math.pi * w * L_required
        num              = lm_max_avail * n_rows * uf * mf * rho_eff
        d_optimal_single = num / denom if denom > 0 else d_global
        auto_tandem      = (d_optimal_single < D_MIN)
    else:
        d_optimal_single = d_global
        auto_tandem      = False

    use_tandem = (tandem_override if tandem_override is not None else auto_tandem)

    if use_tandem:
        if flux_shortage:
            d_optimal_tandem = min(2.0 * d_optimal_single, d_max_ul)
        else:
            d_optimal_tandem = d_global
        d_try = max(D_MIN, d_optimal_tandem)
        phi   = phi_needed(d_try, L_required) / 2   # por luminaria física del par
        if auto_tandem and tandem_override is None:
            warnings.append(
                f"Zona {zone_name}: TÁNDEM AUTOMÁTICO "
                f"(d_opt={d_optimal_single:.1f} m < D_MIN={D_MIN} m) — "
                f"espaciado inter-par {d_try:.1f} m"
            )
        else:
            warnings.append(f"Zona {zone_name}: TÁNDEM MANUAL activado — inter-par {d_try:.1f} m")
    else:
        if flux_shortage:
            d_try = max(D_MIN, min(d_optimal_single, d_max_ul))
            if d_optimal_single < D_MIN:
                L_max_dmin   = _luminance(lm_max_avail, n_rows, uf, mf, rho_eff, D_MIN, w)
                L_max_tandem = 2.0 * L_max_dmin
                warnings.append(
                    f"⚠️ ZONA {zone_name}: L_req={L_required:.0f} cd/m² NO ALCANZABLE "
                    f"individual (máx ~{L_max_dmin:.0f} cd/m²). "
                    f"En tándem alcanzaría ~{L_max_tandem:.0f} cd/m². "
                    f"Activar modo TÁNDEM."
                )
            else:
                warnings.append(
                    f"Zona {zone_name}: luminaria máxima insuficiente al espaciado global — "
                    f"se reduce a {d_try:.1f} m (L_req={L_required:.0f} cd/m²)"
                )
        else:
            d_try = min(d_global, d_max_ul)
        phi = phi_needed(d_try, L_required)

    selected_op   = select_aphex_continuous(phi, cct, I_max_mA)
    tandem_offset = _BODY_LEN.get(selected_op["model"], 0.70) if use_tandem else 0.0

    n_positions = max(1, math.ceil(zone_length / d_try))
    d_actual    = zone_length / n_positions
    n_lum       = n_positions * (2 if use_tandem else 1)   # físicas por lado
    n_ph        = 2 if use_tandem else 1

    L_est     = _luminance(selected_op["lm"] * n_ph, n_rows, uf, mf, rho_eff, d_actual, w)
    E_req     = L_required / rho_eff if rho_eff > 0 else 0.0
    area      = zone_length * w
    pwr_zone  = n_lum * selected_op["W"]
    flux_zone = n_lum * selected_op["lm"]
    pwr_dens  = pwr_zone / area if area > 0 else 0.0

    # Setpoints con posiciones físicas reales (necesario para tándem)
    unif_setpoints = []
    if use_tandem:
        tlt = _zone_tilt_deg(zone_type, L_required, L_interior)
        for i in range(n_positions):
            x_c = s_start + (i + 0.5) * d_actual
            for idx_t, tag in enumerate(("A", "B")):
                x_phys = round(x_c + (idx_t * 2 - 1) * tandem_offset / 2, 2)
                unif_setpoints.append({
                    "idx":        i * 2 + idx_t + 1,
                    "s":          x_phys,
                    "L_req":      round(L_required, 1),
                    "model":      selected_op["model"],
                    "current_mA": selected_op["mA"],
                    "power_w":    selected_op["W"],
                    "flux_lm":    round(selected_op["lm"], 0),
                    "tilt_deg":   tlt,
                    "tandem":     tag,
                    "pair":       i,
                })

    return ZoneLuminaireDesign(
        zone_type=zone_type, zone_name=zone_name, s_start=s_start, s_end=s_end,
        zone_length=zone_length, L_required=L_required, E_required=round(E_req, 1),
        model=selected_op["model"], pcb=selected_op["pcb"], current_mA=selected_op["mA"],
        flux_lm=selected_op["lm"], power_w=selected_op["W"], optic=optic,
        d_max_ul=round(d_max_ul, 2), d_used=round(d_actual, 2),
        n_luminaires=n_lum, L_estimated=round(L_est, 1),
        UF=round(uf, 4), power_zone_w=round(pwr_zone, 0),
        flux_zone_lm=round(flux_zone, 0), power_density_wm2=round(pwr_dens, 3),
        d_max=round(d_actual, 2),
        setpoints=unif_setpoints,
        tilt_deg=_zone_tilt_deg(zone_type, L_required, L_interior),
        n_tandem=2 if use_tandem else 1,
        tandem_offset_m=round(tandem_offset, 2),
    )


def _zone_label(z_type: str, tr_count: int) -> str:
    """Etiqueta normalizada de zona.
    Las zonas bidireccionales del Portal B llevan sufijo ·B.
    """
    t = z_type.lower()
    if t == "threshold_b":              return "CTH·B"
    if t == "transition_b":             return f"CTR{tr_count}·B"
    if "threshold" in t:                return "CTH"
    if "transition" in t:               return f"CTR{tr_count}"
    if "interior" in t:                 return "CIN"
    if "exit" in t or "salida" in t:    return "CEX"
    if "access" in t or "parting" in t: return "ACC"
    return t.upper()[:4]


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — DISEÑO INSIDE-OUT APHEX
# ══════════════════════════════════════════════════════════════════════════════

def design_aphex_tunnel(
    zones_list:    list,
    params:        dict,
    road_width_m:  float,
    tube_length_m: float,
    tube_id:       str = "T1",
) -> TunnelLuminaireResult:
    """
    Algoritmo inside-out CIE 88:2004 con cadena APHEX S→M→L.

    Parámetros relevantes en `params`:
        I_max_mA         : corriente máxima global DALI (int, default 750)
        cct              : temperatura de color "3000K" / "4000K" (default "4000K")
        arrangement      : clave de ARRANGEMENTS (default "central_single")
        mounting_height_m: altura de montaje (m, default 5.0)
        maintenance_factor: MF (default 0.70)
        road_surface     : clave de ROAD_SURFACES (default "medium_asphalt")
        rho_eff          : reflectancia efectiva (si se especifica, sobreescribe road_surface)
        optic            : "F2M2" / "F2MD" / "F151" / "auto" (default "auto")
    """
    warnings: List[str] = []

    # ── Parámetros ──────────────────────────────────────────────────────────
    I_max_mA   = int(params.get("I_max_mA", 750))
    cct        = str(params.get("cct", "4000K"))
    if cct not in ("3000K", "4000K"):
        cct = "4000K"
        warnings.append("CCT no reconocida — se usa 4000K")

    arrangement = str(params.get("arrangement", "central_single"))
    if arrangement not in ARRANGEMENTS:
        arrangement = "central_single"
        warnings.append("Arreglo no reconocido — se usa central_single")

    h    = float(params.get("mounting_height_m", 4.5))
    mf   = float(params.get("maintenance_factor", DEFAULT_MF))
    w    = max(road_width_m, 1.0)
    wh   = w / h if h > 0 else 1.0
    # d_used representa la distancia entre setpoints consecutivos. En
    # tresbolillo hay un solo equipo por setpoint y el lado va alternando.
    n_rows = physical_luminaires_per_setpoint(arrangement)

    surface_key = str(params.get("road_surface", "medium_asphalt"))
    rho_eff = float(params.get("rho_eff",
                   ROAD_SURFACES.get(surface_key, ROAD_SURFACES["medium_asphalt"])["rho"]))

    optic_pref = str(params.get("optic", "auto"))
    optic      = auto_select_optic(optic_pref, wh)

    # Parámetros CIE 88 para la curva de transición
    speed_kmh = float(params.get("speed_kmh", 80.0))
    Lth_cie   = float(params.get("Lth", 0.0))
    Lin_cie   = float(params.get("Lin", 0.0))

    # ── Tablas fotométricas ─────────────────────────────────────────────────
    uf      = lookup_uf(optic, wh, arrangement)
    dh_max  = lookup_dh_max(optic, wh, arrangement)
    d_max_ul = dh_max * h

    # Límite práctico (túneles grandes) — nunca > 20 m
    d_interior = min(d_max_ul, 20.0)

    # ── Cadena APHEX ─────────────────────────────────────────────────────────
    chain = build_aphex_chain(cct, I_max_mA)
    if not chain:
        warnings.append(f"No hay puntos de operación con I_max={I_max_mA} mA y CCT={cct}")
        chain = build_aphex_chain(cct, 750)

    # ── Diseño por zona ──────────────────────────────────────────────────────
    zone_designs: List[ZoneLuminaireDesign] = []
    tr_count = 0

    # Zona interior = menor L_req → fija el espaciado global
    # El espaciado base de uniformidad lo gobiernan Interior/Transicion,
    # nunca la zona de salida (que puede tener un objetivo de proyecto menor)
    # ni las zonas exteriores. Asi un CEX fijado al 50 % de Lin no reduce por
    # accidente el nivel usado para dimensionar todo el tunel.
    valid_zones = [
        z for z in zones_list
        if str(z.get("zone_type") or z.get("type") or "").lower()
        not in {"exit", "access", "parting"}
        and float(z.get("L_min_required", 0)) > 0
        and float(z.get("s_end", 0)) > float(z.get("s_start", 0))
    ]

    if valid_zones:
        L_interior = min(float(z.get("L_min_required", 0)) for z in valid_zones)
        # Verificar que S/350mA cumple en zona interior con d_interior
        op0 = chain[0]
        L0  = _luminance(op0["lm"], n_rows, uf, mf, rho_eff, d_interior, w)
        if L0 < L_interior:
            # Recalcular d_interior para que el mínimo punto de operación cubra la interior
            denom = math.pi * w * L_interior
            num   = op0["lm"] * n_rows * uf * mf * rho_eff
            d_possible = num / denom if denom > 0 else d_interior
            d_interior = max(2.5, min(d_possible, d_max_ul))
            warnings.append(
                f"El espaciado máximo de uniformidad ({d_max_ul:.1f} m) es demasiado grande "
                f"para cumplir L_int={L_interior:.0f} cd/m² con el menor punto de operación. "
                f"Se usa d={d_interior:.1f} m."
            )
    else:
        warnings.append("No hay zonas con L_req > 0 — se usa espaciado por Ul.")

    for z in zones_list:
        z_type  = str(z.get("zone_type") or z.get("type") or "interior").lower()
        z_start = float(z.get("s_start", 0))
        z_end   = float(z.get("s_end",   0))
        L_req   = float(z.get("L_min_required", 0))

        if "transition" in z_type:
            tr_count += 1
        z_name = _zone_label(z_type, tr_count)

        _tilt_ov   = params.get("tilt_overrides", {})
        _tandem_ov = params.get("tandem_overrides", {})
        tandem_ov_zone = _tandem_ov.get(z_name)   # True / False / None

        zd = _design_zone_aphex(
            zone_type=z_type, zone_name=z_name,
            s_start=z_start, s_end=z_end, L_required=L_req,
            chain=chain, d_global=d_interior, d_max_ul=d_max_ul,
            uf=uf, n_rows=n_rows, mf=mf, rho_eff=rho_eff, w=w,
            optic=optic, warnings=warnings,
            cct=cct, I_max_mA=I_max_mA,
            speed_kmh=speed_kmh, Lth=Lth_cie, Lin=Lin_cie,
            L_interior=L_interior if valid_zones else 0.0,
            tandem_override=tandem_ov_zone,
        )
        # Aplicar override de tilt del usuario si existe
        if zd.zone_name in _tilt_ov:
            zd.tilt_deg = float(_tilt_ov[zd.zone_name])
        zone_designs.append(zd)

        # Avisos de diseño
        if zd.d_used < 2.5 and zd.n_luminaires > 0 and zd.n_tandem == 1:
            warnings.append(
                f"Zona {z_name}: espaciado {zd.d_used:.2f} m muy reducido — "
                "verificar si es posible la instalación"
            )

    # ── Resultado ────────────────────────────────────────────────────────────
    # LuminaireSpec representativa (zona con mayor L_req)
    if zone_designs:
        dominant = max(zone_designs, key=lambda zd: zd.L_required)
        lum_spec = LuminaireSpec(
            flux_lm           = dominant.flux_lm,
            power_w           = dominant.power_w,
            efficiency        = uf,
            mounting_height_m = h,
            arrangement       = arrangement,
            maintenance_factor= mf,
            name              = f"Aphex {dominant.model}/{dominant.pcb} {dominant.current_mA}mA {cct}",
        )
    else:
        lum_spec = None

    result = TunnelLuminaireResult(
        tube_id           = tube_id,
        luminaire         = lum_spec,
        road_surface_type = surface_key,
        rho_eff           = rho_eff,
        road_width_m      = w,
        tube_length_m     = tube_length_m,
        optic             = optic,
        cct               = cct,
        I_max_mA          = I_max_mA,
        arrangement       = arrangement,
        zones             = zone_designs,
        warnings          = list(set(warnings)),  # deduplicate
    )
    result._compute_totals()
    return result


# ══════════════════════════════════════════════════════════════════════════════
# BACKWARD COMPAT — calculate_luminaire_layout
# Mantiene la interfaz existente del motor; detecta si se usan parámetros
# legacy (flux_lm / efficiency) o nuevos (I_max_mA / cct).
# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
# MOTOR OPTIMIZADOR — design_aphex_tunnel_optimized
# Sustituye a design_aphex_tunnel cuando se pasan U0_obj/Ul_obj.
# Usa optimizer.py: max d para U0/Ul → corriente para L_req.
# ══════════════════════════════════════════════════════════════════════════════

_SURFACE_RTABLE = {
    "dark_asphalt":    "R3",
    "medium_asphalt":  "R2",
    "light_asphalt":   "R1",
    "concrete":        "C1",
    "bright_concrete": "C2",
}


def _y_positions_for_validation(arrangement: str, w: float, wall_offset: float) -> list:
    """Posiciones y [m] de las luminarias para validación de sección."""
    wo = min(max(0.05, wall_offset), max(0.05, w / 2 - 0.05))
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
    return [w/2]  # central


def is_inside_tunnel(y_m: float, z_m: float, W: float, H_total: float,
                    shape: str = "horseshoe", H_pared: float = 3.0) -> bool:
    """
    Comprueba si el punto (y_m, z_m) está dentro del contorno de la sección transversal.
    Road: y ∈ [0, W], z ∈ [0, H_total] (z=0 en la calzada).
    Para herradura: tramo recto hasta H_pared + bóveda semi-elíptica hasta H_total.
    """
    if y_m < 0 or y_m > W or z_m < 0:
        return False
    if shape == "rectangular":
        return z_m <= H_total
    if shape == "circular":
        # Galería circular: R = ((W/2)² + H_total²) / (2·H_total)
        R = ((W / 2.0) ** 2 + H_total ** 2) / (2.0 * H_total)
        z_ctr = H_total - R   # centro puede estar por debajo de la calzada
        return (y_m - W / 2.0) ** 2 + (z_m - z_ctr) ** 2 <= R ** 2 * 1.02  # 2% margen
    # Herradura: tramo recto
    Hp = min(H_pared, H_total)
    if z_m <= Hp:
        return True
    # Bóveda semi-elíptica: centro en (W/2, Hp), semi-ejes a=W/2, b=H_total-Hp
    a = W / 2.0
    b = H_total - Hp
    if b <= 0:
        return z_m <= H_total
    return ((y_m - W / 2.0) ** 2 / a ** 2 + (z_m - Hp) ** 2 / b ** 2) <= 1.02  # 2% margen


def _relax_setpoints_for_zone_spillover(
    zone_designs, h, w, mf, rtable, cct, I_max_mA, I_min_pct,
    arrangement, wall_offset, tolerance=0.10, max_iters=4,
):
    """
    Correccion posterior al diseño aislado por zona: una luminaria de
    Transicion cercana a un Umbral (mucho mas brillante) recibe luz real de
    ese vecino que el diseño de su propia zona no tuvo en cuenta (cada zona
    se dimensiona asumiendo solo su propio array periodico infinito, sin
    vecinos). El resultado es una L real muy por encima de L_req cerca del
    limite entre zonas (hallazgo verificado: a 2 m del Umbral el spillover
    por si solo ya superaba a L_req en un ~5x).

    Esta pasada NO toca espaciado/optica/tilt (gobernados por U0/Ul, que no
    empeoran por el spillover — si acaso mejoran la uniformidad aparente).
    Solo atenua el flujo de cada posicion cuya L real (con TODAS las zonas
    juntas) supere L_req x (1+tolerance), respetando el suelo de corriente
    I_min_pct — nunca se fuerza por debajo de ese minimo, aunque el spillover
    por si solo ya supere el objetivo (ahi no hay nada que optimizar: ya es
    imposible bajar mas, y no supone ningun problema de seguridad).

    Gauss-Seidel secuencial (no por lotes): las posiciones se recorren una a
    una, ordenadas por posicion a lo largo del tunel, y cada correccion se
    aplica de inmediato antes de evaluar la siguiente -- de forma que la
    contribucion EXACTA de la propia luminaria se aisla usando siempre el
    valor mas reciente de sus vecinas (ya corregidas si les tocaba antes en
    esta misma pasada). Corregir todas las posiciones a la vez asumiendo que
    las demas se quedan fijas (por lotes) se probo inestable: varias
    posiciones vecinas se atenuan a la vez por el mismo exceso mutuo y el
    efecto combinado se pasa de frenada muy por debajo de L_req. La
    actualizacion secuencial e inmediata evita ese problema. Varias pasadas
    (max_iters) por si hace falta que la correccion se propague varias veces.

    Muta zone_designs in-place (setpoints y agregados de zona). Devuelve una
    lista de mensajes de aviso (vacia si no hizo falta corregir nada).
    """
    from photometric_engine.salvi_photometry.ldt_parser import load_ldt
    from photometric_engine.salvi_photometry.geometry import (
        Observer, LuminaireOrientation, mirror_c_for_interior_facing,
    )
    from photometric_engine.salvi_photometry.calculator import TunnelCalculator, LuminaireInstance
    from modules.tunnel.optimizer import select_model_for_flux, _OPTIC_LDT, _LDT_DIR

    warnings_out = []

    zones_with_sp = [zd for zd in zone_designs if zd.n_luminaires > 0 and (zd.setpoints or [])]
    if not zones_with_sp:
        return warnings_out

    if arrangement == 'lateral_left':
        ys_default = [wall_offset]
    elif arrangement in ('lateral_right', 'unilateral'):
        ys_default = [w - wall_offset]
    elif arrangement in ('bilateral_sym', 'bilateral', 'staggered'):
        ys_default = [wall_offset, w - wall_offset]
    elif arrangement == 'central_double':
        ys_default = [wall_offset, w - wall_offset]
    elif arrangement == 'central_offset':
        ys_default = [wall_offset]
    else:
        ys_default = [w / 2]

    def _tilt_for_y(tilt_base, y_pos):
        return tilt_base if y_pos < w / 2 else -tilt_base

    def _y_for_setpoint(sp):
        if arrangement in ('bilateral_stag', 'staggered'):
            idx = sp.get('idx', 1)
            return wall_offset if (idx - 1) % 2 == 0 else (w - wall_offset)
        return ys_default[0]

    _phot_cache = {}
    def _phot(optic_id):
        if optic_id not in _phot_cache:
            fname = _OPTIC_LDT.get(optic_id, _OPTIC_LDT['F2MD'])
            _phot_cache[optic_id] = load_ldt(_LDT_DIR / fname)
        return _phot_cache[optic_id]

    def _lum_for_setpoint(sp):
        x_pos = float(sp['s'])
        y_pos = _y_for_setpoint(sp)
        tilt0 = float(sp.get('tilt_deg', 0) or 0)
        optic_id = sp.get('optic') or 'F2MD'
        flux = float(sp.get('flux_lm', 0) or 0)
        return LuminaireInstance(x=x_pos, y=y_pos, H=h, photometry=_phot(optic_id), flux_lm=flux,
                                 orientation=LuminaireOrientation(
                                     tilt_deg=_tilt_for_y(tilt0, y_pos),
                                     mirror_c=mirror_c_for_interior_facing(y_pos, w, arrangement),
                                 ))

    # Solo se corrigen posiciones de Transicion. Umbral/Interior/Acceso/Salida
    # son zonas UNIFORMES (mismo flujo en todas sus posiciones): su diseño
    # aislado ya es autoconsistente (verificado: L_est del diseño coincide con
    # la L real de la zona construida con sus vecinas reales, una vez
    # corregido n_side/max_lum_dist — ver optimizer._reach_for). Si se
    # "corrigen" tambien esas posiciones, cada una ve como spillover fijo la
    # contribucion de sus vecinas — que en una zona uniforme son casi toda la
    # señal — y todas se atenuan entre si en cascada hacia el suelo. Solo
    # Transicion, con flujo variable posicion a posicion y un vecino de OTRO
    # tipo (Umbral, mucho mas brillante) al lado, tiene un exceso real que
    # corregir aqui.
    targets = []  # (zd, sp_index)
    for zd in zones_with_sp:
        if 'transition' not in str(zd.zone_type or ''):
            continue
        for i, sp in enumerate(zd.setpoints):
            if float(sp.get('flux_lm', 0) or 0) > 0 and float(sp.get('L_req', 0) or 0) > 0:
                targets.append((zd, i))
    if not targets:
        return warnings_out

    def _direction_for_zone(zd_obj) -> float:
        zt = str(getattr(zd_obj, 'zone_type', '') or '')
        return -1.0 if zt.endswith('_b') else 1.0

    # Alcance conservador (maximo entre las opticas realmente usadas) para el
    # corte de luminarias lejanas -- mismo criterio que optimizer._reach_for.
    optics_in_use = {sp.get('optic') or 'F2MD' for zd in zones_with_sp for sp in zd.setpoints}
    reach = max((_phot(o).reach_distance(h) for o in optics_in_use), default=300.0)
    calc = TunnelCalculator(rtable, mf, max_luminaire_dist=reach)
    obs_fwd = Observer(lane_y_m=w / 2, d_observer_m=60.0, direction=1.0)
    obs_bwd = Observer(lane_y_m=w / 2, d_observer_m=60.0, direction=-1.0)

    # L_req representa una media en la malla CIE 140 (5 puntos a lo ancho de
    # la calzada — mismo criterio que _calc_grid/_ys_profile en optimizer.py
    # y photometric_verify.py), NO el valor en un unico punto. Medir L_now/
    # own_only solo en la linea bajo la luminaria (disposicion central) da un
    # valor sistematicamente mas alto que la media real del carril -- ese
    # punto es, por construccion, el mas brillante de la seccion transversal
    # -- lo que hacia parecer "exceso" en casi cualquier posicion (no solo
    # las que de verdad reciben spillover de una zona vecina) y recortaba
    # flujo de mas en toda la Transicion.
    _N_AVG  = 5
    _ys_avg = [(j + 0.5) * w / _N_AVG for j in range(_N_AVG)]

    def _L_avg(x_pos, lums, obs):
        pts = [(x_pos, y) for y in _ys_avg]
        vals = calc.luminance_at_points_batch(pts, lums, obs)
        return float(sum(vals) / len(vals))

    # ── Correccion secuencial (Gauss-Seidel real) ───────────────────────────
    # Se recorren las posiciones de Transicion UNA A UNA (ordenadas por x) y
    # cada correccion se aplica de inmediato sobre el mismo array de
    # luminarias -- las posiciones siguientes de esta misma pasada YA ven el
    # valor corregido, en vez de asumir que todas las vecinas se quedan fijas
    # y aplicar todas las correcciones a la vez (eso, probado, oscila: varias
    # posiciones cercanas se atenuan simultaneamente por exceso mutuo y el
    # efecto combinado se pasa de frenada muy por debajo de L_req). Con
    # actualizacion inmediata cada correccion es exacta con la informacion
    # disponible en ese momento y no hace falta amortiguar.
    flat_refs = []
    lums_all  = []
    for zd in zones_with_sp:
        for i, sp in enumerate(zd.setpoints):
            flat_refs.append((zd, i))
            lums_all.append(_lum_for_setpoint(sp))
    index_of = {(id(zd), i): k for k, (zd, i) in enumerate(flat_refs)}

    targets_sorted = sorted(targets, key=lambda t: float(t[0].setpoints[t[1]]['s']))

    n_corrected  = 0
    power_before = {}  # (id(zd), i) -> W antes de tocar nada, para el resumen final

    for _sweep in range(max_iters):
        any_change = False
        for zd, i in targets_sorted:
            sp    = zd.setpoints[i]
            key   = (id(zd), i)
            if key not in power_before:
                power_before[key] = float(sp.get('power_w', 0) or 0)

            L_req    = float(sp['L_req'])
            x_pos    = float(sp['s'])
            obs_use  = obs_bwd if _direction_for_zone(zd) < 0 else obs_fwd

            L_now = _L_avg(x_pos, lums_all, obs_use)
            if L_now <= L_req * (1.0 + tolerance):
                continue

            idx      = index_of[key]
            own_only = _L_avg(x_pos, [lums_all[idx]], obs_use)
            if own_only <= 1e-9:
                continue  # esta posicion no depende de si misma (ya la cubre solo el vecino)

            spillover       = L_now - own_only
            own_only_target = max(0.0, L_req - spillover)
            flux_old        = float(sp['flux_lm'])
            sel             = select_model_for_flux(flux_old * (own_only_target / own_only),
                                                     cct, I_max_mA, I_min_pct)
            flux_new        = sel['lm']
            if flux_new >= flux_old * 0.999:
                continue  # ya en el suelo de corriente, o no hace falta bajar mas

            sp['flux_lm']    = round(flux_new, 0)
            sp['model']      = sel['model']
            sp['current_mA'] = round(sel['mA'], 1)
            sp['power_w']    = sel['W']
            lums_all[idx]    = _lum_for_setpoint(sp)  # visible de inmediato al resto de la pasada
            n_corrected += 1
            any_change = True

        if not any_change:
            break

    if n_corrected == 0:
        return warnings_out

    # ── Pasada final de seguridad: nunca por debajo de L_req ────────────────
    # Tras converger, alguna posicion puede haber quedado un poco por debajo
    # de L_req (la correccion de una vecina posterior en la misma pasada
    # puede dejar a una anterior justo debajo). El exceso es seguro (nunca se
    # corrige de mas), pero un defecto no lo es -- una unica pasada secuencial
    # que SOLO sube flujo, partiendo ya del estado casi convergido de arriba
    # (por eso no hace falta iterarla ni amortiguarla: los ajustes que quedan
    # son pequeños).
    for zd, i in targets_sorted:
        sp = zd.setpoints[i]
        obs_use = obs_bwd if _direction_for_zone(zd) < 0 else obs_fwd
        x_pos = float(sp['s'])
        L_req = float(sp['L_req'])
        L_now = _L_avg(x_pos, lums_all, obs_use)
        if L_now >= L_req * 0.999:
            continue
        idx = index_of[(id(zd), i)]
        own_only = _L_avg(x_pos, [lums_all[idx]], obs_use)
        if own_only <= 1e-9:
            continue
        spillover = L_now - own_only
        own_only_target = max(0.0, L_req - spillover)
        flux_old = float(sp['flux_lm'])
        if own_only_target <= own_only:
            continue
        sel = select_model_for_flux(flux_old * (own_only_target / own_only), cct, I_max_mA, I_min_pct)
        if sel['lm'] <= flux_old * 1.001:
            continue
        sp['flux_lm']    = round(sel['lm'], 0)
        sp['model']      = sel['model']
        sp['current_mA'] = round(sel['mA'], 1)
        sp['power_w']    = sel['W']
        lums_all[idx]    = _lum_for_setpoint(sp)

    # Recalculo final de L real (con el flujo ya corregido) para reportar en
    # cada setpoint, y agregados de zona afectados por el cambio de potencia.
    for zd, i in targets:
        sp = zd.setpoints[i]
        obs_use = obs_bwd if _direction_for_zone(zd) < 0 else obs_fwd
        L_now = _L_avg(float(sp['s']), lums_all, obs_use)
        sp['L_est'] = round(float(L_now), 1)

    total_saving_w = 0.0
    for (zd, i) in targets:
        key = (id(zd), i)
        if key in power_before:
            total_saving_w += power_before[key] - float(zd.setpoints[i].get('power_w', 0) or 0)

    corrected_zones = {id(zd): zd for zd, _ in targets}.values()
    for zd in corrected_zones:
        sps = zd.setpoints
        zd.power_zone_w        = round(sum(float(sp.get('power_w', 0) or 0) for sp in sps), 0)
        zd.flux_zone_lm         = round(sum(float(sp.get('flux_lm', 0) or 0) for sp in sps), 0)
        area = zd.zone_length * w
        zd.power_density_wm2   = round(zd.power_zone_w / area, 3) if area > 0 else 0.0
        zd.L_estimated          = round(sum(float(sp.get('L_est', 0) or 0) for sp in sps) / len(sps), 1) if sps else zd.L_estimated
        dominant = max(sps, key=lambda sp: float(sp.get('L_req', 0) or 0))
        zd.model      = dominant['model']
        zd.current_mA = round(float(dominant.get('current_mA', 0) or 0))
        zd.flux_lm    = round(float(dominant.get('flux_lm', 0) or 0), 0)
        zd.power_w    = round(float(dominant.get('power_w', 0) or 0), 1)

    warnings_out.append(
        f"Ajuste por interferencia entre zonas: {n_corrected} luminarias atenuadas porque ya reciben "
        f"suficiente luz de una zona vecina mas brillante (ahorro estimado: {total_saving_w/1000:.2f} kW)."
    )
    return warnings_out


def _enforce_required_luminance_profile(
    zone_designs, h, w, mf, rtable, cct, I_max_mA, I_min_pct,
    arrangement, wall_offset, tube_length_m, Lth, Lth_b, Lin,
    speed_kmh, tolerance=0.0, max_iters=40, spacing_quantum=0.5,
    enforce_portal_edges=True, sample_step_m=4.0,
):
    """
    Cierre fotometrico del layout fisico completo.

    El dimensionado local usa celdas periodicas CIE 140 para maximizar la
    interdistancia. Esta pasada evalua despues todas las luminarias reales
    juntas, a intervalos de 1 m y en cinco puntos transversales, y aumenta
    modelo/corriente donde Lcalc < Lreq. Si todas las luminarias vecinas han
    alcanzado su limite, anade una posicion de refuerzo en el punto deficitario.

    La optica y el tilt no se modifican aqui: ya fueron elegidos por U0/Ul.
    """
    import numpy as np
    from photometric_engine.salvi_photometry.ldt_parser import load_ldt
    from photometric_engine.salvi_photometry.geometry import (
        Observer, LuminaireOrientation, mirror_c_for_interior_facing,
    )
    from photometric_engine.salvi_photometry.calculator import TunnelCalculator, LuminaireInstance
    from modules.tunnel.optimizer import (
        select_model_for_flux, cie88_L_transition,
        _OPTIC_LDT, _LDT_DIR,
    )
    from modules.tunnel.required_luminance import build_requirement_samples

    warnings_out = []
    active_zones = [
        zd for zd in zone_designs
        if zd.n_luminaires > 0 and (zd.setpoints or [])
        and float(zd.s_end) >= 0.0 and float(zd.s_start) <= tube_length_m
        # ADAPTACIÓN es una capa exclusiva de crepúsculo. No puede aportar
        # luz al cierre soleado de umbral/transición.
        and str(getattr(zd, "control_layer", "legacy") or "legacy")
        != "adaptation"
    ]
    if not active_zones:
        return warnings_out

    if arrangement == 'lateral_left':
        ys_default = [wall_offset]
    elif arrangement in ('lateral_right', 'unilateral'):
        ys_default = [w - wall_offset]
    elif arrangement in ('bilateral_sym', 'bilateral', 'staggered'):
        ys_default = [wall_offset, w - wall_offset]
    elif arrangement == 'central_double':
        ys_default = [wall_offset, w - wall_offset]
    elif arrangement == 'central_offset':
        ys_default = [wall_offset]
    else:
        ys_default = [w / 2]

    def _tilt_for_y(tilt_base, y_pos):
        return tilt_base if y_pos < w / 2 else -tilt_base

    def _ys_for_setpoint(sp):
        if arrangement in ('bilateral_stag', 'staggered'):
            idx = int(sp.get('idx', 1) or 1)
            return [wall_offset if (idx - 1) % 2 == 0 else (w - wall_offset)]
        return ys_default

    phot_cache = {}

    def _phot(optic_id):
        oid = optic_id or 'F2MD'
        if oid not in phot_cache:
            phot_cache[oid] = load_ldt(_LDT_DIR / _OPTIC_LDT.get(oid, _OPTIC_LDT['F2MD']))
        return phot_cache[oid]

    optics_in_use = {
        sp.get('optic') or 'F2MD'
        for zd in active_zones for sp in (zd.setpoints or [])
    }
    reach = max((_phot(oid).reach_distance(h) for oid in optics_in_use), default=300.0)
    calc = TunnelCalculator(rtable, mf, max_luminaire_dist=reach)
    obs_fwd = Observer(lane_y_m=w / 2, d_observer_m=60.0, direction=1.0)
    obs_bwd = Observer(lane_y_m=w / 2, d_observer_m=60.0, direction=-1.0)
    ys_calc = [(j + 0.5) * w / 5 for j in range(5)]

    def _target_for_zone(zd, s_val):
        return required_luminance_for_zone(
            zd,
            s_val,
            Lth=Lth,
            Lth_b=Lth_b,
            Lin=Lin,
            speed_kmh=speed_kmh,
        )

    def _zone_and_target(s_val):
        candidates = [
            zd for zd in active_zones
            if float(zd.s_start) - 1e-6 <= s_val <= float(zd.s_end) + 1e-6
        ]
        if not candidates:
            return None, 0.0
        evaluated = [(zd, _target_for_zone(zd, s_val)) for zd in candidates]
        return max(evaluated, key=lambda item: item[1])

    def _build_groups():
        groups = []
        lums = []
        for zd in active_zones:
            for i, sp in enumerate(zd.setpoints or []):
                flux = float(sp.get('flux_lm', 0) or 0)
                if flux <= 0:
                    continue
                optic_id = sp.get('optic') or zd.optic or 'F2MD'
                tilt0 = float(sp.get('tilt_deg', zd.tilt_deg) or 0)
                group_lums = []
                for y_pos in _ys_for_setpoint(sp):
                    group_lums.append(LuminaireInstance(
                        x=float(sp['s']), y=y_pos, H=h,
                        photometry=_phot(optic_id), flux_lm=flux,
                        orientation=LuminaireOrientation(
                            tilt_deg=_tilt_for_y(tilt0, y_pos),
                            mirror_c=mirror_c_for_interior_facing(
                                y_pos, w, arrangement,
                            ),
                        ),
                    ))
                groups.append({'zd': zd, 'i': i, 'sp': sp, 'lums': group_lums})
                lums.extend(group_lums)
        return groups, lums

    # Este cierre solo decide dÃ³nde reforzar el hardware. La verificaciÃ³n
    # final sigue resolviendo cada campo CIE 140 completo. Una malla de 1 m
    # aquÃ­ repetÃ­a centenares de evaluaciones LDT antes de esa verificaciÃ³n
    # exacta; los puntos medios entre luminarias y las fronteras se conservan
    # siempre en ``build_requirement_samples``.
    closure_step_m = min(5.0, max(1.0, float(sample_step_m or 4.0)))
    canonical_samples = build_requirement_samples(
        active_zones,
        tube_length_m=tube_length_m,
        Lth=Lth,
        Lth_b=Lth_b,
        Lin=Lin,
        speed_kmh=speed_kmh,
        step_m=closure_step_m,
        include_luminaire_midpoints=False,
    )
    sample_meta = [
        (item["s"], item["zone"], item["target"], item["direction"])
        for item in canonical_samples
        if str(
            getattr(item["zone"], "control_layer", "legacy") or "legacy"
        ) != "permanent"
        # El cierre estricto incluye el primer/ultimo campo fisico del
        # umbral. La exclusión historica de 5H ocultaba justo los deficits que
        # el usuario ve en la planta junto a la boca.
        if enforce_portal_edges or not (
            (
                any(
                    "threshold" in str(zd.zone_type or "").lower()
                    and not str(zd.zone_type or "").lower().endswith("_b")
                    for zd in active_zones
                )
                and item["direction"] == 1.0
                and float(item["s"]) < 5.0 * float(h)
            )
            or (
                any(
                    str(zd.zone_type or "").lower().endswith("_b")
                    for zd in active_zones
                )
                and item["direction"] == -1.0
                and float(item["s"]) > tube_length_m - 5.0 * float(h)
            )
        )
    ]

    def _evaluate(lums, meta):
        values = [0.0] * len(meta)
        for direction, obs in ((1.0, obs_fwd), (-1.0, obs_bwd)):
            indices = [
                i for i, (_, _, _, sample_direction) in enumerate(meta)
                if sample_direction == direction
            ]
            if not indices:
                continue
            pts = [
                (meta[i][0], y_pos)
                for i in indices for y_pos in ys_calc
            ]
            raw = np.asarray(calc.luminance_at_points_batch(pts, lums, obs))
            means = raw.reshape(len(indices), len(ys_calc)).mean(axis=1)
            for local_i, meta_i in enumerate(indices):
                values[meta_i] = float(means[local_i])
        return values

    # La geometria, optica y tilt permanecen fijos durante los ajustes de
    # corriente. Construir de nuevo la luminancia de cada punto en cada
    # iteracion hacia que un tunel largo evaluase cientos de luminarias contra
    # todos los campos una y otra vez. Se calcula una matriz CIE 140 por
    # geometria (L = A @ flujo) y NumPy actualiza despues cada iteracion.
    # Solo se reconstruye si se anade un refuerzo, porque entonces cambia A.
    influence_cache = {}

    def _evaluate_groups_linear(groups, meta):
        geometry_key = tuple(
            (
                id(group['zd']), int(group['i']),
                round(float(group['sp']['s']), 4),
                str(group['sp'].get('optic') or group['zd'].optic or ''),
                round(float(group['sp'].get('tilt_deg', group['zd'].tilt_deg) or 0), 3),
                len(group['lums']),
            )
            for group in groups
        )
        sample_key = tuple(
            (round(float(s_val), 4), float(direction))
            for s_val, _zd, _target, direction in meta
        )
        cache_key = (geometry_key, sample_key)
        matrix = influence_cache.get(cache_key)
        if matrix is None:
            matrix = np.zeros((len(meta), len(groups)), dtype=float)
            unit_lums = []
            group_starts = []
            for group in groups:
                group_starts.append(len(unit_lums))
                for lum in group['lums']:
                    unit_lums.append(LuminaireInstance(
                        x=lum.x, y=lum.y, H=lum.H,
                        photometry=lum.photometry, flux_lm=10000.0,
                        orientation=lum.orientation,
                    ))
            starts = np.asarray(group_starts, dtype=int)
            for direction, obs in ((1.0, obs_fwd), (-1.0, obs_bwd)):
                indices = [
                    index for index, (_s, _z, _t, sample_direction)
                    in enumerate(meta) if sample_direction == direction
                ]
                if not indices:
                    continue
                points = [
                    (meta[index][0], y_pos)
                    for index in indices for y_pos in ys_calc
                ]
                raw = calc.luminance_contributions_at_points_batch(
                    points, unit_lums, obs,
                )
                physical = np.asarray(raw, dtype=float).reshape(
                    len(indices), len(ys_calc), len(unit_lums),
                )
                grouped = np.add.reduceat(
                    physical, starts, axis=2,
                ).mean(axis=1) / 10000.0
                matrix[indices, :] = grouped
            influence_cache[cache_key] = matrix
        fluxes = np.asarray([
            float(group['sp'].get('flux_lm', 0.0) or 0.0)
            for group in groups
        ], dtype=float)
        return (matrix @ fluxes).tolist()

    initial_count = sum(len(zd.setpoints or []) for zd in active_zones)
    # Los extremos fisicos no reciben la mitad del array periodico "virtual"
    # usado para dimensionar el vano. En opticas longitudinales el refuerzo
    # necesario puede superar el 10 % aun con una solucion correcta; el
    # limite sigue siendo una salvaguarda, no un criterio de diseno.
    booster_limit = max(20, int(math.ceil(initial_count * 0.25)))
    boosters_added = 0

    for _ in range(max_iters):
        groups, lums = _build_groups()
        if not lums:
            break
        calc_values = _evaluate_groups_linear(groups, sample_meta)
        deficits = [
            (target / max(L_calc, 1e-9), i)
            for i, ((_, _, target, _), L_calc) in enumerate(zip(sample_meta, calc_values))
            if L_calc < target * (1.0 - tolerance)
        ]
        if not deficits:
            break

        factors = {}
        factor_sources = {}
        for ratio, meta_i in deficits:
            s_val, zd, _, _ = sample_meta[meta_i]
            same_zone = [
                (abs(float(g['sp']['s']) - s_val), gi)
                for gi, g in enumerate(groups)
                if g['zd'] is zd
            ]
            if not same_zone and 'transition' in str(zd.zone_type or ''):
                same_zone = [
                    (abs(float(g['sp']['s']) - s_val), gi)
                    for gi, g in enumerate(groups)
                    if str(g['zd'].zone_type or '') == str(zd.zone_type or '')
                ]
            if not same_zone:
                continue
            _, nearest = min(same_zone)
            key = nearest
            factors[key] = max(factors.get(key, 1.0), ratio * 1.01)
            factor_sources.setdefault(key, []).append((ratio, meta_i))

        changed = False
        unresolved = []
        for gi, factor in factors.items():
            group = groups[gi]
            sp = group['sp']
            flux_old = float(sp.get('flux_lm', 0) or 0)
            selected = select_model_for_flux(
                flux_old * factor, cct, I_max_mA, I_min_pct,
            )
            if selected['lm'] <= flux_old * 1.001:
                unresolved.extend(factor_sources.get(gi, []))
                continue
            sp['model'] = selected['model']
            sp['current_mA'] = round(selected['mA'], 1)
            sp['power_w'] = selected['W']
            sp['flux_lm'] = round(selected['lm'], 0)
            changed = True

        # Un deficit cuyo punto mas cercano ya esta al limite no debe quedar
        # bloqueado por el hecho de que, en otra zona, aun se pueda aumentar
        # corriente. Resolver ambos problemas en la misma iteracion evita que
        # los portales esperen a que converja todo el resto del tunel.
        if not unresolved:
            if not changed:
                break
            continue

        # Las posiciones candidatas de estos puntos ya estan al limite.
        # Incorporar varios refuerzos en una misma pasada cuando el deficit es
        # grande evita recalcular todo el tunel una vez por cada unidad. Al
        # final se podan individualmente los que resulten redundantes.
        if boosters_added >= booster_limit:
            if changed:
                continue
            break
        max_sel = select_model_for_flux(1e12, cct, I_max_mA, I_min_pct)
        unresolved.sort(reverse=True)
        worst_ratio = unresolved[0][0]
        n_boost_round = min(
            6,
            booster_limit - boosters_added,
            max(1, int(math.ceil((worst_ratio - 1.0) * 8.0))),
        )
        for add_idx in range(n_boost_round):
            _, worst_i = unresolved[min(add_idx, len(unresolved) - 1)]
            s_worst, zd_worst, target_worst, _ = sample_meta[worst_i]
            existing = sorted(
                zd_worst.setpoints or [],
                key=lambda sp: abs(float(sp['s']) - s_worst),
            )
            if not existing:
                continue
            template = existing[0]
            quantum = max(0.5, float(spacing_quantum))
            s_boost = round(s_worst / quantum) * quantum
            s_boost = min(
                max(s_boost, float(zd_worst.s_start)),
                float(zd_worst.s_end),
            )
            occupied = {round(float(sp['s']), 3) for sp in zd_worst.setpoints}
            if round(s_boost, 3) in occupied:
                for step in range(1, 65):
                    delta = quantum * ((step + 1) // 2) * (1 if step % 2 else -1)
                    candidate = min(
                        max(
                            s_boost + delta,
                            float(zd_worst.s_start),
                        ),
                        float(zd_worst.s_end),
                    )
                    if round(candidate, 3) not in occupied:
                        s_boost = candidate
                        break
            booster = {
                'idx': len(zd_worst.setpoints) + 1,
                's': round(s_boost, 2),
                'L_req': round(target_worst, 1),
                'model': max_sel['model'],
                'optic': template.get('optic') or zd_worst.optic,
                'tilt_deg': float(template.get('tilt_deg', zd_worst.tilt_deg) or 0),
                'current_mA': round(max_sel['mA'], 1),
                'power_w': max_sel['W'],
                'flux_lm': round(max_sel['lm'], 0),
                'target_flux_lm': round(max_sel['lm'], 3),
                'U0': template.get('U0', zd_worst.UF),
                'L_est': 0.0,
                'booster': True,
                'spacing_m': round(
                    min(
                        abs(float(sp['s']) - s_boost)
                        for sp in existing
                    ),
                    3,
                ),
                'spacing_stage': int(
                    template.get('spacing_stage', 0) or 0
                ) + 1,
            }
            if 'transition' in str(zd_worst.zone_type or ''):
                inner_edge = (
                    float(zd_worst.s_start)
                    if str(zd_worst.zone_type or '').endswith('_b')
                    else float(zd_worst.s_end)
                )
                booster['distance_from_interior_m'] = round(
                    abs(s_boost - inner_edge), 3,
                )
            zd_worst.setpoints.append(booster)
            boosters_added += 1

    groups, lums = _build_groups()
    final_values = _evaluate_groups_linear(groups, sample_meta) if lums else []

    # Eliminar cualquier refuerzo que el ajuste por lotes haya dejado
    # redundante. La luminancia directa es lineal con el flujo, por lo que su
    # contribucion puede restarse sin recalcular el resto del layout.
    for group in reversed([g for g in groups if g['sp'].get('booster')]):
        contribution = _evaluate(group['lums'], sample_meta)
        candidate_values = [
            total - own for total, own in zip(final_values, contribution)
        ]
        if all(
            L_calc >= target * (1.0 - tolerance)
            for (_, _, target, _), L_calc in zip(sample_meta, candidate_values)
        ):
            group['zd'].setpoints.remove(group['sp'])
            final_values = candidate_values
            boosters_added -= 1

    groups, lums = _build_groups()

    # En los refuerzos que siguen siendo necesarios, bajar modelo/corriente
    # hasta el minimo que conserva simultaneamente todas las restricciones.
    # Se calcula por superposicion lineal y luego se redondea al punto fisico
    # disponible mediante select_model_for_flux.
    for group in reversed([g for g in groups if g['sp'].get('booster')]):
        sp = group['sp']
        flux_old = float(sp.get('flux_lm', 0) or 0)
        if flux_old <= 0:
            continue
        contribution = _evaluate(group['lums'], sample_meta)
        base_values = [
            total - own for total, own in zip(final_values, contribution)
        ]
        required_scale = 0.0
        for (_, _, target, _), base, own in zip(sample_meta, base_values, contribution):
            if own <= 1e-12:
                continue
            required_scale = max(
                required_scale,
                (target * (1.0 - tolerance) - base) / own,
            )
        required_scale = min(1.0, max(0.0, required_scale))
        selected = select_model_for_flux(
            flux_old * required_scale * 1.001,
            cct, I_max_mA, I_min_pct,
        )
        flux_new = float(selected['lm'])
        if flux_new >= flux_old * 0.999:
            continue
        sp['model'] = selected['model']
        sp['current_mA'] = round(selected['mA'], 1)
        sp['power_w'] = selected['W']
        sp['flux_lm'] = round(flux_new, 0)
        scale_new = flux_new / flux_old
        final_values = [
            base + own * scale_new
            for base, own in zip(base_values, contribution)
        ]

    groups, lums = _build_groups()
    final_deficits = [
        (target / max(L_calc, 1e-9), s_val, L_calc, target)
        for (s_val, _, target, _), L_calc in zip(sample_meta, final_values)
        if L_calc < target * (1.0 - tolerance)
    ]

    # Actualizar L_est de cada setpoint y agregados de zona con el layout
    # definitivo. Esto hace que la tabla compare magnitudes homogeneas.
    sp_meta = []
    for zd in active_zones:
        for sp in zd.setpoints or []:
            sp_meta.append((
                float(sp['s']),
                zd,
                _target_for_zone(zd, float(sp['s'])),
                -1.0 if str(zd.zone_type or '').endswith('_b') else 1.0,
            ))
    sp_values = _evaluate(lums, sp_meta) if sp_meta and lums else []
    for (_, _, _, _), L_calc, group in zip(sp_meta, sp_values, groups):
        # La BASE ya se ha cerrado contra su propio campo CIE 140 antes de
        # esta pasada. No debe recibir como "L estimada" la luminancia TOTAL
        # de una posicion que cae dentro de una transicion/umbral: eso mezcla
        # artificialmente la aportacion de los refuerzos con la BASE.
        if str(
            getattr(group['zd'], "control_layer", "legacy") or "legacy"
        ) == "permanent":
            continue
        group['sp']['L_est'] = round(L_calc, 1)

    profile_by_zone = {}
    for (s_val, zd, target, _), L_calc in zip(sample_meta, final_values):
        bucket = profile_by_zone.setdefault(id(zd), {
            'values': [], 'ratios': [],
        })
        bucket['values'].append(float(L_calc))
        bucket['ratios'].append(float(L_calc) / max(float(target), 1e-9))

    for zd in active_zones:
        if str(
            getattr(zd, "control_layer", "legacy") or "legacy"
        ) == "permanent":
            continue
        sps = zd.setpoints or []
        if not sps:
            continue
        sps.sort(key=lambda sp: float(sp['s']))
        for idx, sp in enumerate(sps, start=1):
            sp['idx'] = idx
        zd.n_luminaires = len(sps)
        zd.power_zone_w = round(sum(float(sp.get('power_w', 0) or 0) for sp in sps), 0)
        zd.flux_zone_lm = round(sum(float(sp.get('flux_lm', 0) or 0) for sp in sps), 0)
        area = zd.zone_length * w
        zd.power_density_wm2 = round(zd.power_zone_w / area, 3) if area > 0 else 0.0
        zd.L_estimated = round(
            sum(float(sp.get('L_est', 0) or 0) for sp in sps) / len(sps), 1
        )
        dominant = max(sps, key=lambda sp: float(sp.get('L_req', 0) or 0))
        zd.model = dominant['model']
        zd.current_mA = round(float(dominant.get('current_mA', 0) or 0))
        zd.flux_lm = round(float(dominant.get('flux_lm', 0) or 0), 0)
        zd.power_w = round(float(dominant.get('power_w', 0) or 0), 1)
        profile_stats = profile_by_zone.get(id(zd))
        if profile_stats and profile_stats['values']:
            zd.profile_L_avg = round(
                sum(profile_stats['values']) / len(profile_stats['values']), 2
            )
            zd.profile_L_min = round(min(profile_stats['values']), 2)
            zd.profile_min_ratio = round(min(profile_stats['ratios']), 4)

    if boosters_added:
        warnings_out.append(
            f"Cierre Lcalc>=Lreq: añadidas {boosters_added} posiciones de refuerzo "
            "solo donde modelo/corriente ya habian alcanzado su limite."
        )
    if final_deficits:
        worst = max(final_deficits)
        warnings_out.append(
            f"🔴 Cierre fotometrico incompleto: {len(final_deficits)} puntos siguen por "
            f"debajo de Lreq; peor punto s={worst[1]:.1f} m, "
            f"Lcalc={worst[2]:.1f}, Lreq={worst[3]:.1f} cd/m2."
        )
    else:
        warnings_out.append(
            f"Perfil fisico validado: Lcalc >= Lreq en {len(sample_meta)} puntos "
            "longitudinales (media de 5 puntos transversales)."
        )
    return warnings_out



def _build_layered_physical_layout(
    zone_designs: List[ZoneLuminaireDesign],
    *,
    tube_length_m: float,
    road_width_m: float,
    Lin: float,
    L_night: float,
    Lth: float,
    Lth_b: float,
    speed_kmh: float,
    d_interior: float,
    spacing_quantum: float,
    int_model: str,
    int_optic: str,
    int_tilt: float,
    int_mA: float,
    int_lm: float,
    int_W: float,
    int_U0: float,
    int_Ul: float,
    int_L_est: float,
    cct: str,
    I_max_mA: float,
    I_min_pct: float,
    base_design_margin: float,
    adaptation_spacing_override_m: float | None = None,
) -> Tuple[List[ZoneLuminaireDesign], List[str], Dict[str, dict]]:
    """Convierte el diseño zonal máximo en BASE A–B + refuerzo residual.

    La geometría interior se replica físicamente a lo largo de todo el tubo.
    Las geometrías de umbral/transición se conservan como candidatos de
    refuerzo; el solver global posterior reparte su flujo teniendo ya presente
    la contribución fija de la BASE.
    """
    from modules.tunnel.optimizer import (
        flux_power_at_current,
        select_model_for_flux,
    )

    messages: List[str] = []
    scenarios: Dict[str, dict] = {}
    length = max(0.0, float(tube_length_m))
    if length <= 0.0 or Lin <= 0.0:
        return zone_designs, messages, scenarios

    quantum = max(0.5, float(spacing_quantum))
    d_base = max(
        quantum,
        math.floor(float(d_interior) / quantum + 1e-9) * quantum,
    )
    last_grid_index = max(1, int(math.ceil(length / d_base)))
    # Una posición de apoyo antes de cada boca conserva el patrón fotométrico
    # del primer/último campo nocturno. Son luminarias BASE, no refuerzos de
    # alta potencia, y quedan identificadas para el replanteo exterior.
    positions = [
        index * d_base
        for index in range(-1, last_grid_index + 1)
    ]

    base_margin = max(0.0, float(base_design_margin))
    base_selection = select_model_for_flux(
        float(int_lm) * (1.0 + base_margin),
        cct,
        I_max_mA,
        I_min_pct,
    )
    base_model = str(base_selection["model"])
    base_mA = float(base_selection["mA"])
    base_lm = float(base_selection["lm"])
    base_W = float(base_selection["W"])
    base_L_est = float(int_L_est) * (
        base_lm / max(float(int_lm), 1e-9)
    )

    night_ratio = max(0.0, float(L_night)) / max(float(Lin), 1e-9)
    night_target_flux = base_lm * night_ratio
    i_min_mA = max(1.0, float(I_min_pct) * 350.0)
    flux_at_min, power_at_min = flux_power_at_current(
        base_model, cct, i_min_mA, I_min_pct,
    )
    if night_target_flux <= flux_at_min:
        night_current_mA = i_min_mA
        night_flux_actual = float(flux_at_min)
        night_power_actual = float(power_at_min)
        night_at_driver_floor = True
    else:
        low, high = i_min_mA, max(i_min_mA, float(int_mA))
        for _ in range(40):
            mid = (low + high) / 2.0
            flux_mid, _ = flux_power_at_current(
                base_model, cct, mid, I_min_pct,
            )
            if flux_mid >= night_target_flux:
                high = mid
            else:
                low = mid
            if high - low <= 0.05:
                break
        night_current_mA = high
        night_flux_actual, night_power_actual = flux_power_at_current(
            base_model, cct, night_current_mA, I_min_pct,
        )
        night_at_driver_floor = False
    night_L_estimated = base_L_est * (
        float(night_flux_actual) / max(base_lm, 1e-9)
    )
    base_setpoints = []
    for index, position in enumerate(positions, start=1):
        base_setpoints.append({
            "idx": index,
            "s": round(position, 3),
            "L_req": round(float(Lin), 3),
            "L_total_req": round(float(Lin), 3),
            "model": base_model,
            "optic": int_optic,
            "tilt_deg": float(int_tilt),
            "current_mA": round(base_mA, 1),
            "power_w": round(base_W, 1),
            "flux_lm": round(base_lm, 0),
            "base_current_mA": round(base_mA, 1),
            "base_power_w": round(base_W, 1),
            "base_flux_lm": round(base_lm, 3),
            "target_flux_lm": round(base_lm, 3),
            "day_flux_lm": round(base_lm, 3),
            "night_target_flux_lm": round(night_target_flux, 3),
            "night_flux_lm": round(float(night_flux_actual), 3),
            "night_current_mA": round(float(night_current_mA), 1),
            "night_power_w": round(float(night_power_actual), 2),
            "night_L_est": round(night_L_estimated, 3),
            "night_driver_floor": night_at_driver_floor,
            "spacing_m": round(d_base, 3),
            "spacing_stage": 0,
            "U0": round(float(int_U0), 4),
            "Ul": round(float(int_Ul), 4),
            "L_est": round(base_L_est, 3),
            "control_layer": "permanent",
            "portal": None,
            "portal_support": position < 0.0 or position > length,
        })

    base_power = len(base_setpoints) * base_W
    base_flux = len(base_setpoints) * base_lm
    base = ZoneLuminaireDesign(
        zone_type="interior_base",
        zone_name="BASE A–B",
        s_start=0.0,
        s_end=length,
        zone_length=length,
        L_required=float(Lin),
        L_total_required=float(Lin),
        E_required=round(float(Lin) / 0.085, 1),
        model=base_model,
        pcb=_commercial_name_for(base_model),
        current_mA=round(base_mA),
        flux_lm=round(base_lm, 0),
        power_w=round(base_W, 1),
        optic=int_optic,
        d_max_ul=round(float(d_interior), 2),
        d_used=round(d_base, 2),
        n_luminaires=len(base_setpoints),
        L_estimated=round(base_L_est, 3),
        UF=round(float(int_U0), 4),
        Ul=round(float(int_Ul), 4),
        power_zone_w=round(base_power, 1),
        flux_zone_lm=round(base_flux, 0),
        power_density_wm2=round(
            base_power / max(length * road_width_m, 1e-9), 3,
        ),
        d_max=round(d_base, 2),
        setpoints=base_setpoints,
        tilt_deg=float(int_tilt),
        control_layer="permanent",
        portal=None,
    )

    reinforcement: List[ZoneLuminaireDesign] = []
    removed_names = []
    for zone in zone_designs:
        zone_type = str(zone.zone_type or "").lower()
        if "threshold" not in zone_type and "transition" not in zone_type:
            removed_names.append(zone.zone_name)
            continue
        zone.control_layer = "reinforcement"
        zone.portal = "B" if zone_type.endswith("_b") else "A"
        total_required = max(0.0, float(zone.L_required))
        zone.L_total_required = total_required
        zone.L_required = max(0.0, total_required - float(Lin))
        zone.E_required = round(zone.L_required / 0.085, 1)
        for setpoint in zone.setpoints or []:
            total_at_point = max(
                0.0, float(setpoint.get("L_req", total_required) or 0.0)
            )
            residual_at_point = max(0.0, total_at_point - float(Lin))
            residual_ratio = (
                residual_at_point / total_at_point
                if total_at_point > 1e-9 else 0.0
            )
            setpoint["L_total_req"] = round(total_at_point, 3)
            setpoint["L_req"] = round(residual_at_point, 3)
            setpoint["control_layer"] = "reinforcement"
            setpoint["portal"] = zone.portal
            previous_target = float(
                setpoint.get(
                    "target_flux_lm",
                    setpoint.get("flux_lm", 0.0),
                ) or 0.0
            )
            residual_target = max(0.0, previous_target * residual_ratio)
            selected = select_model_for_flux(
                residual_target, cct, I_max_mA, I_min_pct,
            )
            setpoint["target_flux_lm"] = round(residual_target, 3)
            setpoint["model"] = selected["model"]
            setpoint["current_mA"] = selected["mA"]
            setpoint["power_w"] = selected["W"]
            setpoint["flux_lm"] = selected["lm"]
            setpoint["L_est"] = round(
                float(setpoint.get("L_est", total_at_point) or 0.0)
                * residual_ratio,
                3,
            )
        if zone.setpoints:
            zone.n_luminaires = len(zone.setpoints)
            zone.power_zone_w = round(sum(
                float(sp.get("power_w", 0.0) or 0.0)
                for sp in zone.setpoints
            ), 1)
            zone.flux_zone_lm = round(sum(
                float(sp.get("flux_lm", 0.0) or 0.0)
                for sp in zone.setpoints
            ), 0)
            zone.power_density_wm2 = round(
                zone.power_zone_w
                / max(float(zone.zone_length) * road_width_m, 1e-9),
                3,
            )
            dominant = max(
                zone.setpoints,
                key=lambda sp: float(sp.get("L_req", 0.0) or 0.0),
            )
            zone.model = str(dominant.get("model", zone.model))
            zone.pcb = _commercial_name_for(zone.model)
            zone.current_mA = round(float(
                dominant.get("current_mA", zone.current_mA) or 0.0
            ))
            zone.power_w = round(float(
                dominant.get("power_w", zone.power_w) or 0.0
            ), 1)
            zone.flux_lm = round(float(
                dominant.get("flux_lm", zone.flux_lm) or 0.0
            ), 0)
            zone.L_estimated = round(sum(
                float(sp.get("L_est", 0.0) or 0.0)
                for sp in zone.setpoints
            ) / len(zone.setpoints), 3)
        reinforcement.append(zone)

    messages.append(
        f"Arquitectura multiescenario: BASE A–B con {len(base_setpoints)} "
        f"posiciones, d={d_base:.1f} m, {int_optic}, tilt={int_tilt:.1f}°."
    )
    messages.append(
        f"BASE incluye dos apoyos de portal de baja potencia y margen "
        f"fotométrico {base_margin * 100.0:.1f}% para cerrar los campos "
        "CIE 140 de borde."
    )
    messages.append(
        "Umbral y transición se optimizan como refuerzo residual sobre Lin; "
        "salida/acceso/interior zonal quedan sustituidos por la BASE."
    )
    scenarios["day_max"] = {
        "base_target_cd_m2": round(float(Lin), 3),
        "base_current_mA": round(base_mA, 1),
        "base_flux_per_luminaire_lm": round(base_lm, 0),
        "reinforcement_state": "regulated",
    }
    scenarios["night"] = {
        "target_cd_m2": round(float(L_night), 3),
        "estimated_base_cd_m2": round(night_L_estimated, 3),
        "base_current_mA": round(float(night_current_mA), 1),
        "base_flux_per_luminaire_lm": round(float(night_flux_actual), 0),
        "base_power_per_luminaire_w": round(float(night_power_actual), 2),
        "active_base_luminaires": len(base_setpoints),
        "reinforcement_state": "off",
        "reinforcement_active_luminaires": 0,
        "U0": round(float(int_U0), 4),
        "Ul": round(float(int_Ul), 4),
        "driver_floor_reached": night_at_driver_floor,
        "luminance_compliant": (
            night_L_estimated + 1e-9 >= float(L_night)
        ),
        "TI_status": "pending_exact_verification",
    }
    if night_at_driver_floor and night_L_estimated > float(L_night) * 1.02:
        messages.append(
            f"BASE nocturna limitada por corriente mínima: "
            f"L≈{night_L_estimated:.2f} cd/m² para objetivo "
            f"{L_night:.2f} cd/m²."
        )
    if removed_names:
        messages.append(
            "Capas zonales sustituidas: " + ", ".join(removed_names) + "."
        )
    # Capa intermedia dedicada al crepusculo. Replica la geometria periodica
    # validada de la BASE, desplazada medio vano, y solo ocupa la longitud en
    # la que la curva al 5 % sigue por encima de Lin.
    from modules.tunnel.required_luminance import (
        required_luminance_for_zone,
    )

    adaptation: List[ZoneLuminaireDesign] = []
    requested_adaptation_spacing = adaptation_spacing_override_m
    try:
        requested_adaptation_spacing = float(
            requested_adaptation_spacing,
        )
    except (TypeError, ValueError):
        requested_adaptation_spacing = 0.0
    if requested_adaptation_spacing > 0.0:
        # Targeted physical retry: it only densifies the low-flow dusk layer.
        # BASE and daytime reinforcement retain their accepted geometry.
        d_adaptation = max(
            quantum,
            math.floor(
                requested_adaptation_spacing / quantum + 1e-9
            ) * quantum,
        )
    else:
        d_adaptation = max(
            quantum,
            math.floor(
                max(quantum, d_base - 2.0) / quantum + 1e-9
            ) * quantum,
        )
    adaptation_flux_margin = 0.12
    for portal in ("A", "B"):
        portal_zones = [
            zone for zone in reinforcement
            if str(getattr(zone, "portal", "") or "") == portal
        ]
        if not portal_zones:
            continue
        span_start = min(float(zone.s_start) for zone in portal_zones)
        span_end = max(float(zone.s_end) for zone in portal_zones)
        if span_end - span_start <= 1e-9:
            continue
        grid_origin = (
            span_start + d_adaptation / 2.0
            if portal == "A"
            else span_end - d_adaptation / 2.0
        )
        positions_adaptation = []
        position = grid_origin
        while (
            position <= span_end + 1e-9
            if portal == "A"
            else position >= span_start - 1e-9
        ):
            total_dusk = max(
                (
                    required_luminance_for_zone(
                        zone,
                        position,
                        Lth=max(float(Lin), float(Lth) * 0.05),
                        Lth_b=max(float(Lin), float(Lth_b) * 0.05),
                        Lin=Lin,
                        speed_kmh=speed_kmh,
                    )
                    for zone in portal_zones
                    if float(zone.s_start) - 1e-6
                    <= position
                    <= float(zone.s_end) + 1e-6
                ),
                default=float(Lin),
            )
            residual = max(0.0, float(total_dusk) - float(Lin))
            if residual > 1e-6:
                target_flux = (
                    base_lm
                    * residual
                    / max(float(Lin), 1e-9)
                    * d_adaptation
                    / max(d_base, 1e-9)
                    * (1.0 + adaptation_flux_margin)
                )
                selected = select_model_for_flux(
                    target_flux, cct, I_max_mA, I_min_pct,
                )
                positions_adaptation.append({
                    "s": round(position, 3),
                    "L_req": round(residual, 3),
                    "L_total_req": round(float(total_dusk), 3),
                    "model": selected["model"],
                    "optic": int_optic,
                    "tilt_deg": (
                        float(int_tilt)
                        if portal == "A" else -float(int_tilt)
                    ),
                    "current_mA": selected["mA"],
                    "power_w": selected["W"],
                    "flux_lm": selected["lm"],
                    "target_flux_lm": round(target_flux, 3),
                    "spacing_m": round(d_adaptation, 3),
                    "spacing_stage": 0,
                    "U0": round(float(int_U0), 4),
                    "Ul": round(float(int_Ul), 4),
                    "L_est": round(residual, 3),
                    "control_layer": "adaptation",
                    "portal": portal,
                })
            position += (
                d_adaptation if portal == "A" else -d_adaptation
            )
        if not positions_adaptation:
            continue
        positions_adaptation.sort(key=lambda item: float(item["s"]))
        for index, setpoint in enumerate(
            positions_adaptation, start=1,
        ):
            setpoint["idx"] = index
        dominant = max(
            positions_adaptation,
            key=lambda item: float(item["L_req"]),
        )
        power_zone = sum(
            float(item["power_w"]) for item in positions_adaptation
        )
        flux_zone = sum(
            float(item["flux_lm"]) for item in positions_adaptation
        )
        adaptation.append(ZoneLuminaireDesign(
            zone_type=f"adaptation_{portal.lower()}",
            zone_name=f"ADAPTACIÓN {portal}",
            s_start=span_start,
            s_end=span_end,
            zone_length=span_end - span_start,
            L_required=max(
                float(item["L_req"]) for item in positions_adaptation
            ),
            L_total_required=max(
                float(item["L_total_req"])
                for item in positions_adaptation
            ),
            E_required=round(
                max(float(item["L_req"]) for item in positions_adaptation)
                / 0.085,
                1,
            ),
            model=str(dominant["model"]),
            pcb=_commercial_name_for(str(dominant["model"])),
            current_mA=round(float(dominant["current_mA"])),
            flux_lm=round(float(dominant["flux_lm"]), 0),
            power_w=round(float(dominant["power_w"]), 1),
            optic=int_optic,
            d_max_ul=round(d_adaptation, 2),
            d_used=round(d_adaptation, 2),
            n_luminaires=len(positions_adaptation),
            L_estimated=round(sum(
                float(item["L_est"]) for item in positions_adaptation
            ) / len(positions_adaptation), 3),
            UF=round(float(int_U0), 4),
            Ul=round(float(int_Ul), 4),
            power_zone_w=round(power_zone, 1),
            flux_zone_lm=round(flux_zone, 0),
            power_density_wm2=round(
                power_zone
                / max((span_end - span_start) * road_width_m, 1e-9),
                3,
            ),
            d_max=round(d_adaptation, 2),
            setpoints=positions_adaptation,
            tilt_deg=(
                float(int_tilt)
                if portal == "A" else -float(int_tilt)
            ),
            control_layer="adaptation",
            portal=portal,
        ))

    if adaptation:
        messages.append(
            "Capa ADAPTACIÓN crepuscular añadida: "
            + ", ".join(
                f"{zone.portal}={zone.n_luminaires} luminarias"
                for zone in adaptation
            )
            + f", malla d={d_adaptation:.1f} m desplazada medio vano "
            f"y margen {adaptation_flux_margin * 100.0:.0f}%."
        )
    return [base, *adaptation, *reinforcement], messages, scenarios


def _apply_solar_daylight_contribution(
    zone_designs: List[ZoneLuminaireDesign],
    *,
    params: dict,
    tube_length_m: float,
    road_width_m: float,
    Lin: float,
    Lth: float,
    Lth_b: float,
    cct: str,
    I_max_mA: float,
    I_min_pct: float,
    two_way: bool,
) -> Tuple[List[str], Dict[str, object]]:
    """Reduce artificial reinforcement by a longitudinal daylight profile."""
    enabled = bool(
        params.get("daylight_contribution_enabled", False)
        or params.get("exterior_layer_enabled", False)
    )
    if not enabled:
        return [], {"enabled": False}

    legacy_enabled = bool(params.get("exterior_layer_enabled", False))
    penetration_key = (
        "exterior_length_m"
        if legacy_enabled else "daylight_penetration_length_m"
    )
    contribution_key = (
        "exterior_mouth_contribution_pct"
        if legacy_enabled else "daylight_mouth_contribution_pct"
    )
    portal_a_key = "exterior_portal_a" if legacy_enabled else "daylight_portal_a"
    portal_b_key = "exterior_portal_b" if legacy_enabled else "daylight_portal_b"
    penetration = max(
        0.0, float(params.get(penetration_key, 60.0) or 0.0),
    )
    mouth_pct = max(
        0.0,
        min(100.0, float(params.get(contribution_key, 10.0) or 0.0)),
    )
    portal_a = bool(params.get(portal_a_key, True))
    portal_b = bool(params.get(portal_b_key, True)) and bool(two_way)
    decay_exponent = max(0.1, min(5.0, float(params.get(
        "daylight_decay_exponent", 1.0,
    ) or 1.0)))
    profile = {
        "enabled": True,
        "model": "linear_decay",
        "penetration_length_m": round(penetration, 3),
        "mouth_contribution_pct": round(mouth_pct, 3),
        "decay_exponent": round(decay_exponent, 3),
        "tube_length_m": round(float(tube_length_m), 3),
        "portal_a": portal_a,
        "portal_b": portal_b,
    }
    if penetration <= 1e-9 or mouth_pct <= 1e-9:
        return [
            "Aporte solar no aplicado: define penetracion y aporte en boca "
            "mayores que cero."
        ], profile

    from modules.tunnel.optimizer import select_model_for_flux

    affected_positions = 0
    removed_positions = 0
    peak_contribution = 0.0
    for zone in zone_designs:
        if str(getattr(zone, "control_layer", "") or "") != "reinforcement":
            continue
        zone.daylight_profile = dict(profile)
        retained = []
        residuals = []
        for setpoint in zone.setpoints or []:
            position = float(setpoint.get("s", 0.0) or 0.0)
            total_required = max(
                float(Lin),
                float(setpoint.get(
                    "L_total_req",
                    float(setpoint.get("L_req", 0.0) or 0.0) + float(Lin),
                ) or float(Lin)),
            )
            daylight = daylight_contribution_for_zone(
                zone,
                position,
                Lth=Lth,
                Lth_b=Lth_b,
            )
            daylight = min(daylight, max(0.0, total_required - float(Lin)))
            artificial_total = max(float(Lin), total_required - daylight)
            previous_residual = max(
                0.0,
                float(setpoint.get(
                    "L_req", total_required - float(Lin),
                ) or 0.0),
            )
            residual = max(0.0, artificial_total - float(Lin))
            setpoint["natural_daylight_cd_m2"] = round(daylight, 3)
            setpoint["L_artificial_total_req"] = round(
                artificial_total, 3,
            )
            setpoint["L_req"] = round(residual, 3)
            peak_contribution = max(peak_contribution, daylight)
            if daylight > 1e-9:
                affected_positions += 1
            if residual <= 1e-9:
                removed_positions += 1
                continue

            previous_target = max(
                0.0,
                float(setpoint.get(
                    "target_flux_lm",
                    setpoint.get("flux_lm", 0.0),
                ) or 0.0),
            )
            ratio = (
                residual / previous_residual
                if previous_residual > 1e-9 else 1.0
            )
            target_flux = previous_target * min(1.0, max(0.0, ratio))
            selected = select_model_for_flux(
                target_flux, cct, I_max_mA, I_min_pct,
            )
            setpoint["target_flux_lm"] = round(target_flux, 3)
            setpoint["model"] = selected["model"]
            setpoint["current_mA"] = selected["mA"]
            setpoint["power_w"] = selected["W"]
            setpoint["flux_lm"] = selected["lm"]
            setpoint["L_est"] = round(
                float(setpoint.get("L_est", previous_residual) or 0.0)
                * min(1.0, max(0.0, ratio)),
                3,
            )
            residuals.append(residual)
            retained.append(setpoint)

        zone.setpoints = retained
        zone.n_luminaires = len(retained)
        zone.L_required = max(residuals, default=0.0)
        zone.E_required = round(zone.L_required / 0.085, 1)
        zone.power_zone_w = round(sum(
            float(item.get("power_w", 0.0) or 0.0) for item in retained
        ), 1)
        zone.flux_zone_lm = round(sum(
            float(item.get("flux_lm", 0.0) or 0.0) for item in retained
        ), 0)
        zone.power_density_wm2 = round(
            zone.power_zone_w
            / max(float(zone.zone_length) * float(road_width_m), 1e-9),
            3,
        )
        if retained:
            dominant = max(
                retained,
                key=lambda item: float(item.get("L_req", 0.0) or 0.0),
            )
            zone.model = str(dominant.get("model", zone.model))
            zone.pcb = _commercial_name_for(zone.model)
            zone.current_mA = round(float(
                dominant.get("current_mA", zone.current_mA) or 0.0
            ))
            zone.power_w = round(float(
                dominant.get("power_w", zone.power_w) or 0.0
            ), 1)
            zone.flux_lm = round(float(
                dominant.get("flux_lm", zone.flux_lm) or 0.0
            ), 0)
            zone.L_estimated = round(sum(
                float(item.get("L_est", 0.0) or 0.0)
                for item in retained
            ) / len(retained), 3)
        else:
            zone.power_w = 0.0
            zone.flux_lm = 0.0
            zone.L_estimated = 0.0

    daylight_summary = {
        **profile,
        "portal_a_mouth_cd_m2": round(
            float(Lth) * mouth_pct / 100.0 if portal_a else 0.0, 3,
        ),
        "portal_b_mouth_cd_m2": round(
            float(Lth_b) * mouth_pct / 100.0 if portal_b else 0.0, 3,
        ),
        "peak_contribution_cd_m2": round(peak_contribution, 3),
        "affected_reinforcement_positions": affected_positions,
        "removed_reinforcement_positions": removed_positions,
        "counts_as_installed_luminaires": False,
        "installed_power_kw": 0.0,
    }
    configured_factors = params.get(
        "control_scene_factors", [1.0, 0.70, 0.30, 0.05],
    )
    if (
        not isinstance(configured_factors, (list, tuple))
        or len(configured_factors) != 4
    ):
        configured_factors = [1.0, 0.70, 0.30, 0.05]
    scene_names = ("sunny", "normal", "overcast", "dusk")
    daylight_summary["scenes"] = {
        scene_name: {
            "L20_factor": round(
                max(0.0, min(1.0, float(factor))), 3,
            ),
            "portal_a_mouth_cd_m2": round(
                daylight_summary["portal_a_mouth_cd_m2"]
                * max(0.0, min(1.0, float(factor))),
                3,
            ),
            "portal_b_mouth_cd_m2": round(
                daylight_summary["portal_b_mouth_cd_m2"]
                * max(0.0, min(1.0, float(factor))),
                3,
            ),
        }
        for scene_name, factor in zip(scene_names, configured_factors)
    }
    daylight_summary["scenes"]["night"] = {
        "L20_factor": 0.0,
        "portal_a_mouth_cd_m2": 0.0,
        "portal_b_mouth_cd_m2": 0.0,
    }
    portals = [
        portal for portal, active in (("A", portal_a), ("B", portal_b))
        if active
    ]
    message = (
        "Aporte solar natural aplicado en portal(es) "
        f"{'/'.join(portals) or 'ninguno'}: {mouth_pct:.1f}% de Lth en "
        f"boca, decaimiento lineal durante {penetration:.0f} m; "
        f"{removed_positions} posiciones de refuerzo artificial eliminadas. "
        "No añade luminarias ni potencia instalada."
    )
    return [message], daylight_summary


def _build_exterior_portal_layers(
    *,
    params: dict,
    tube_length_m: float,
    h: float,
    w: float,
    mf: float,
    rtable: str,
    cct: str,
    I_max_mA: float,
    I_min_pct: float,
    arrangement: str,
    wall_offset: float,
    U0_obj: float,
    Ul_obj: float,
    tilt_grid: List[float],
    spacing_quantum: float,
    two_way: bool,
    Lth: float,
    Lth_b: float,
) -> Tuple[List[ZoneLuminaireDesign], List[str]]:
    """Compatibilidad: la antigua capa APHEX exterior ya no se construye."""
    return [], [
        "La antigua capa de luminarias exteriores esta desactivada; "
        "usa el aporte solar natural en boca."
    ]

    # Código histórico inaccesible, conservado temporalmente para facilitar
    # la migración de proyectos guardados durante esta revisión.
    if not bool(params.get("exterior_layer_enabled", False)):
        return [], []

    from modules.tunnel.optimizer import optimize_single_luminaire, L_from_flux

    exterior_length = max(
        0.0, float(params.get("exterior_length_m", 60.0) or 0.0),
    )
    mouth_contribution_pct = max(
        0.0,
        min(
            100.0,
            float(params.get("exterior_mouth_contribution_pct", 10.0) or 0.0),
        ),
    )
    requested_spacing = max(
        float(spacing_quantum),
        float(params.get("exterior_spacing_m", 15.0) or 15.0),
    )
    spacing = max(
        float(spacing_quantum),
        math.floor(requested_spacing / float(spacing_quantum) + 1e-9)
        * float(spacing_quantum),
    )
    if exterior_length <= 1e-9 or mouth_contribution_pct <= 1e-9:
        return [], [
            "Capa exterior no creada: define una longitud y un aporte en boca mayores que cero."
        ]

    portal_flags = [("A", bool(params.get("exterior_portal_a", True)))]
    if two_way:
        portal_flags.append(("B", bool(params.get("exterior_portal_b", True))))

    layers: List[ZoneLuminaireDesign] = []
    messages: List[str] = []
    for portal, enabled in portal_flags:
        if not enabled:
            continue
        mouth_luminance = max(0.0, float(Lth_b if portal == "B" else Lth))
        exterior_target = mouth_luminance * mouth_contribution_pct / 100.0
        if exterior_target <= 1e-9:
            messages.append(
                f"Capa exterior {portal} no creada: Lth de boca nula."
            )
            continue
        direction = -1.0 if portal == "B" else 1.0
        selected = optimize_single_luminaire(
            L_req=exterior_target,
            d=spacing,
            h=h,
            w=w,
            U0_obj=U0_obj,
            Ul_obj=Ul_obj,
            I_max_mA=I_max_mA,
            cct=cct,
            rtable=rtable,
            mf=mf,
            arrangement=arrangement,
            I_min_pct=I_min_pct,
            tilt_grid=tilt_grid,
            wall_offset=wall_offset,
            direction=direction,
        )
        if selected.get("warning"):
            messages.append(f"Exterior {portal}: {selected['warning']}")

        count = max(1, int(math.ceil(exterior_length / spacing)))
        if portal == "A":
            positions = [-(index + 0.5) * spacing for index in range(count)]
            positions.sort()
            zone_type, zone_name = "exterior_a", "EXTERIOR A"
            zone_start = zone_end = 0.0
        else:
            positions = [
                float(tube_length_m) + (index + 0.5) * spacing
                for index in range(count)
            ]
            zone_type, zone_name = "exterior_b", "EXTERIOR B"
            zone_start = zone_end = float(tube_length_m)

        L_est = L_from_flux(
            selected["optic"], spacing, h, w, selected["tilt_deg"],
            selected["lm"], arrangement, rtable, mf,
            wall_offset=wall_offset, direction=direction,
        )
        setpoints = [
            {
                "idx": index + 1,
                "s": round(position, 3),
                "L_req": round(exterior_target, 3),
                "L_total_req": round(exterior_target, 3),
                "model": selected["model"],
                "optic": selected["optic"],
                "tilt_deg": selected["tilt_deg"],
                "current_mA": round(selected["mA"], 1),
                "power_w": selected["W"],
                "flux_lm": round(selected["lm"], 0),
                "target_flux_lm": round(selected["lm"], 3),
                "day_flux_lm": round(selected["lm"], 3),
                "spacing_m": round(spacing, 3),
                "spacing_stage": 0,
                "U0": round(selected["U0"], 4),
                "Ul": round(selected.get("Ul", 0.0), 4),
                "L_est": round(L_est, 3),
                "control_layer": "exterior",
                "portal": portal,
                "exterior": True,
                "mouth_luminance_cd_m2": round(mouth_luminance, 3),
                "mouth_contribution_pct": round(mouth_contribution_pct, 3),
            }
            for index, position in enumerate(positions)
        ]
        power_zone = sum(float(item["power_w"]) for item in setpoints)
        flux_zone = sum(float(item["flux_lm"]) for item in setpoints)
        layers.append(ZoneLuminaireDesign(
            zone_type=zone_type,
            zone_name=zone_name,
            # Los limites se fijan en el plano del portal para que el perfil
            # CIE 140 siga abarcando unicamente el interior del tunel. Las
            # coordenadas reales de las luminarias estan en cada setpoint.
            s_start=zone_start,
            s_end=zone_end,
            zone_length=exterior_length,
            L_required=exterior_target,
            L_total_required=exterior_target,
            E_required=round(exterior_target / 0.085, 1),
            model=selected["model"],
            pcb=_commercial_name_for(selected["model"]),
            current_mA=round(selected["mA"]),
            flux_lm=round(selected["lm"], 0),
            power_w=round(selected["W"], 1),
            optic=selected["optic"],
            d_max_ul=round(spacing, 2),
            d_used=round(spacing, 2),
            n_luminaires=len(setpoints),
            L_estimated=round(L_est, 3),
            UF=round(selected["U0"], 4),
            Ul=round(selected.get("Ul", 0.0), 4),
            power_zone_w=round(power_zone, 1),
            flux_zone_lm=round(flux_zone, 0),
            power_density_wm2=round(
                power_zone / max(exterior_length * w, 1e-9), 3,
            ),
            d_max=round(spacing, 2),
            setpoints=setpoints,
            tilt_deg=selected["tilt_deg"],
            control_layer="exterior",
            portal=portal,
        ))
        messages.append(
            f"Capa exterior {portal}: {len(setpoints)} luminarias, "
            f"{exterior_length:.0f} m, d={spacing:.1f} m, "
            f"aporte={mouth_contribution_pct:.1f} % de Lth "
            f"({exterior_target:.1f} cd/m2)."
        )
    return layers, messages


def _close_permanent_base_against_cie140(
    zone_designs: List[ZoneLuminaireDesign],
    *,
    road_width_m: float,
    road_surface: str,
    luminaire_params: dict,
    Lin: float,
    L_night: float,
    cct: str,
    I_max_mA: float,
    I_min_pct: float,
    margin: float,
    scenarios: Dict[str, dict],
    max_iterations: int = 2,
) -> Tuple[List[str], Dict[str, object]]:
    """Cierra la BASE con campos reales CIE 140 antes de congelarla.

    La celda periodica sirve para elegir geometria (optica, tilt e
    interdistancia). Sin embargo, la BASE A--B se materializa despues como un
    layout fisico con dos apoyos de portal y se verifica con el peor carril y
    sentido. Esta funcion aprovecha la linealidad L~Phi para volver a resolver
    el flujo de la BASE hasta que el peor campo interior quede en Lin con un
    margen positivo pequeño y explicito.
    """
    from types import SimpleNamespace
    from modules.tunnel.optimizer import (
        flux_power_at_current,
        select_model_for_flux,
    )
    from modules.tunnel.photometric_verify import (
        compute_real_luminance_profile,
    )

    messages: List[str] = []
    diagnostics: Dict[str, object] = {
        "available": False,
        "iterations": 0,
        "target_cd_m2": round(float(Lin) * (1.0 + max(0.0, margin)), 4),
    }
    base = next(
        (
            zone for zone in zone_designs
            if str(getattr(zone, "control_layer", "") or "")
            == "permanent"
        ),
        None,
    )
    if base is None or not base.setpoints or Lin <= 0.0:
        diagnostics["error"] = "No existe una BASE continua para cerrar."
        return messages, diagnostics

    calc_params = dict(luminaire_params)
    calc_params["road_width_m"] = float(road_width_m)
    # El perfil debe comprobar los dos sentidos dentro del Interior cuando
    # existe trafico bidireccional, aunque solo se evalúe la zona BASE.
    calc_params.setdefault("traffic_direction", "one_way")
    base_result = SimpleNamespace(
        road_surface_type=road_surface,
        optic=base.optic,
        zones=[base],
    )
    target = float(Lin) * (1.0 + max(0.0, float(margin)))
    h = max(0.1, float(calc_params.get("mounting_height_m", 5.0) or 5.0))
    edge_buffer = 5.0 * h

    def _core_fields(profile: dict) -> list[dict]:
        fields = profile.get("fields", []) or []
        core = [
            field for field in fields
            if float(field.get("field_start", 0.0)) >= edge_buffer - 1e-6
            and float(field.get("field_end", 0.0))
            <= float(base.s_end) - edge_buffer + 1e-6
        ]
        return core or fields

    def _night_point(model: str, day_flux: float, day_current: float):
        minimum_current = max(1.0, float(I_min_pct) * 350.0)
        requested_flux = day_flux * max(0.0, float(L_night)) / max(float(Lin), 1e-9)
        minimum_flux, minimum_power = flux_power_at_current(
            model, cct, minimum_current, I_min_pct,
        )
        if requested_flux <= minimum_flux + 1e-9:
            return (
                minimum_current, float(minimum_flux), float(minimum_power),
                True, requested_flux,
            )
        low = minimum_current
        high = max(minimum_current, float(day_current))
        for _ in range(40):
            middle = (low + high) / 2.0
            middle_flux, _ = flux_power_at_current(
                model, cct, middle, I_min_pct,
            )
            if middle_flux >= requested_flux:
                high = middle
            else:
                low = middle
            if high - low <= 0.05:
                break
        night_flux, night_power = flux_power_at_current(
            model, cct, high, I_min_pct,
        )
        return high, float(night_flux), float(night_power), False, requested_flux

    def _apply_selection(selection: dict, measured_luminance: float) -> None:
        model = str(selection["model"])
        current = float(selection["mA"])
        flux = float(selection["lm"])
        power = float(selection["W"])
        (
            night_current, night_flux, night_power, night_floor,
            night_target,
        ) = _night_point(model, flux, current)
        for setpoint in base.setpoints:
            setpoint.update({
                "model": model,
                "current_mA": round(current, 1),
                "power_w": round(power, 3),
                "flux_lm": round(flux, 3),
                "base_current_mA": round(current, 1),
                "base_power_w": round(power, 3),
                "base_flux_lm": round(flux, 3),
                "target_flux_lm": round(flux, 3),
                "day_flux_lm": round(flux, 3),
                "night_target_flux_lm": round(night_target, 3),
                "night_flux_lm": round(night_flux, 3),
                "night_current_mA": round(night_current, 1),
                "night_power_w": round(night_power, 3),
                "night_driver_floor": bool(night_floor),
                "L_est": round(measured_luminance, 3),
            })
        base.model = model
        base.pcb = _commercial_name_for(model)
        base.current_mA = round(current)
        base.flux_lm = round(flux, 0)
        base.power_w = round(power, 1)
        base.power_zone_w = round(len(base.setpoints) * power, 1)
        base.flux_zone_lm = round(len(base.setpoints) * flux, 0)
        base.power_density_wm2 = round(
            base.power_zone_w / max(base.zone_length * road_width_m, 1e-9), 3,
        )

    final_profile = None
    profile_matches_selection = False
    for iteration in range(1, max(1, int(max_iterations)) + 1):
        profile = compute_real_luminance_profile(
            base_result,
            calc_params,
            road_width_m,
            include_quality_metrics=False,
        )
        if not profile.get("available"):
            diagnostics["error"] = profile.get("error", "Perfil CIE 140 no disponible.")
            return messages, diagnostics
        fields = _core_fields(profile)
        if not fields:
            diagnostics["error"] = "No hay campos interiores CIE 140 para cerrar la BASE."
            return messages, diagnostics
        values = [float(field["L"]) for field in fields]
        minimum = min(values)
        maximum = max(values)
        mean = sum(values) / len(values)
        diagnostics.update({
            "available": True,
            "iterations": iteration,
            "n_core_fields": len(fields),
            "minimum_Lavg_cd_m2": round(minimum, 4),
            "maximum_Lavg_cd_m2": round(maximum, 4),
            "mean_Lavg_cd_m2": round(mean, 4),
        })
        final_profile = profile
        profile_matches_selection = True
        current_flux = float(base.setpoints[0].get("flux_lm", 0.0) or 0.0)
        requested_flux = current_flux * target / max(minimum, 1e-9)
        selection = select_model_for_flux(
            requested_flux, cct, I_max_mA,
            I_min_pct,
        )
        next_flux = float(selection["lm"])
        if abs(next_flux - current_flux) <= max(1.0, current_flux * 2e-4):
            break
        _apply_selection(selection, minimum * next_flux / max(current_flux, 1e-9))
        # La selección acaba de cambiar; el perfil de esta vuelta todavía
        # corresponde al flujo anterior y sólo habrá que recalcularlo si no
        # existe una siguiente iteración.
        profile_matches_selection = False

    if final_profile is None:
        return messages, diagnostics
    final_fields = _core_fields(final_profile)
    final_values = [float(field["L"]) for field in final_fields]
    final_minimum = min(final_values)
    final_maximum = max(final_values)
    # Normalmente la última vuelta ya mide la selección definitiva. Sólo se
    # necesita otra malla si se alcanzó el límite de iteraciones justo después
    # de modificar flujo/modelo; antes se recalculaba siempre por duplicado.
    if not profile_matches_selection:
        profile_after = compute_real_luminance_profile(
            base_result,
            calc_params,
            road_width_m,
            include_quality_metrics=False,
        )
        if profile_after.get("available"):
            final_fields = _core_fields(profile_after)
            final_values = [float(field["L"]) for field in final_fields]
            final_minimum = min(final_values)
            final_maximum = max(final_values)
            final_profile = profile_after
    final_mean = sum(final_values) / len(final_values)
    base.L_estimated = round(final_mean, 3)
    base.profile_L_avg = round(final_mean, 3)
    base.profile_L_min = round(final_minimum, 3)
    base.profile_min_ratio = round(final_minimum / max(float(Lin), 1e-9), 4)
    base.profile_median_ratio = base.profile_min_ratio
    base.profile_p95_ratio = round(final_maximum / max(float(Lin), 1e-9), 4)
    base.profile_max_ratio = base.profile_p95_ratio
    numerical_tolerance = max(0.002, target * 1e-3)
    diagnostics.update({
        "minimum_Lavg_cd_m2": round(final_minimum, 4),
        "maximum_Lavg_cd_m2": round(final_maximum, 4),
        "mean_Lavg_cd_m2": round(final_mean, 4),
        "final_flux_lm": round(float(base.flux_lm), 3),
        "final_current_mA": round(float(base.current_mA), 1),
        "within_target_band": (
            final_minimum + numerical_tolerance >= float(Lin)
            and final_maximum <= target + numerical_tolerance
        ),
    })
    scenarios.setdefault("day_max", {}).update({
        "base_target_cd_m2": round(float(Lin), 3),
        "base_current_mA": round(float(base.current_mA), 1),
        "base_flux_per_luminaire_lm": round(float(base.flux_lm), 0),
        "base_cie140_closure": diagnostics,
    })
    if diagnostics["within_target_band"]:
        messages.append(
            "BASE CIE 140 ajustada: "
            f"Lavg={final_minimum:.2f}..{final_maximum:.2f} cd/m2 "
            f"para Lin={Lin:.2f} cd/m2."
        )
    else:
        messages.append(
            "BASE CIE 140 no puede quedar dentro del margen configurado con "
            "una regulacion uniforme: se conserva sin deficit y debe evaluarse "
            "otra interdistancia, optica o un escalon de encendido."
        )
    return messages, diagnostics


def _resolve_constructive_position_conflicts(
    zone_designs: List[ZoneLuminaireDesign],
    *,
    spacing_quantum: float,
    minimum_separation_m: float,
) -> List[str]:
    """Protege la malla BASE y desfasa las mallas de refuerzo.

    Se intenta mover cada zona completa para conservar sus interdistancias.
    Solo se elimina una posición extrema cuando el desfase la sitúa fuera de
    los límites de la zona. La BASE nunca se desplaza ni se redimensiona.
    """
    messages: List[str] = []
    quantum = max(0.5, float(spacing_quantum))
    clearance = max(0.0, float(minimum_separation_m))
    if clearance <= 1e-9:
        return messages

    permanent_positions = sorted(
        float(sp["s"])
        for zone in zone_designs
        if str(getattr(zone, "control_layer", "legacy") or "legacy")
        == "permanent"
        for sp in zone.setpoints or []
    )
    occupied = list(permanent_positions)

    def conflicts(position: float, positions: List[float]) -> bool:
        return any(
            abs(float(position) - existing) < clearance - 1e-9
            for existing in positions
        )

    reinforcement_zones = [
        zone for zone in zone_designs
        if str(getattr(zone, "control_layer", "legacy") or "legacy")
        in ("adaptation", "reinforcement")
        and zone.setpoints
    ]
    reinforcement_zones.sort(
        key=lambda zone: (
            0
            if str(
                getattr(zone, "control_layer", "legacy") or "legacy"
            )
            == "adaptation"
            else 1,
            float(zone.s_start),
        )
    )
    for zone in reinforcement_zones:
        original = sorted(
            zone.setpoints or [],
            key=lambda sp: float(sp.get("s", 0.0) or 0.0),
        )
        max_steps = max(
            2,
            int(math.ceil(
                max(clearance, quantum) / quantum
            )) + 2,
        )
        offsets = [0.0]
        for step in range(1, max_steps + 1):
            offsets.extend((step * quantum, -step * quantum))

        candidates = []
        for offset in offsets:
            shifted = [
                (sp, float(sp["s"]) + offset)
                for sp in original
                if float(zone.s_start) - 1e-9
                <= float(sp["s"]) + offset
                <= float(zone.s_end) + 1e-9
            ]
            collision_count = sum(
                1 for _sp, position in shifted
                if conflicts(position, occupied)
            )
            dropped = len(original) - len(shifted)
            candidates.append((
                collision_count,
                dropped,
                abs(offset),
                0 if offset >= 0.0 else 1,
                offset,
                shifted,
            ))
        (
            collision_count,
            dropped,
            _abs_offset,
            _offset_order,
            selected_offset,
            shifted,
        ) = min(candidates, key=lambda item: item[:4])

        selected_setpoints = []
        local_positions: List[float] = []
        locally_relocated = 0
        for sp, proposed in shifted:
            position = proposed
            if conflicts(position, occupied + local_positions):
                alternatives = []
                for step in range(1, max_steps + 5):
                    for sign in (1.0, -1.0):
                        candidate = proposed + sign * step * quantum
                        if not (
                            float(zone.s_start) - 1e-9
                            <= candidate
                            <= float(zone.s_end) + 1e-9
                        ):
                            continue
                        if not conflicts(
                            candidate, occupied + local_positions,
                        ):
                            alternatives.append(candidate)
                    if alternatives:
                        break
                if alternatives:
                    position = min(
                        alternatives,
                        key=lambda candidate: abs(candidate - proposed),
                    )
                    locally_relocated += 1
                else:
                    dropped += 1
                    continue
            sp["s"] = round(position, 3)
            sp["constructive_offset_m"] = round(
                position - float(proposed) + selected_offset,
                3,
            )
            if "distance_from_interior_m" in sp:
                zone_type = str(zone.zone_type or "").lower()
                inner_edge = (
                    float(zone.s_start)
                    if zone_type.endswith("_b")
                    else float(zone.s_end)
                )
                sp["distance_from_interior_m"] = round(
                    abs(position - inner_edge), 3,
                )
            selected_setpoints.append(sp)
            local_positions.append(position)

        selected_setpoints.sort(key=lambda sp: float(sp["s"]))
        for index, sp in enumerate(selected_setpoints, start=1):
            sp["idx"] = index
        zone.setpoints = selected_setpoints
        zone.n_luminaires = len(selected_setpoints)
        zone.power_zone_w = round(sum(
            float(sp.get("power_w", 0.0) or 0.0)
            for sp in selected_setpoints
        ), 1)
        zone.flux_zone_lm = round(sum(
            float(sp.get("flux_lm", 0.0) or 0.0)
            for sp in selected_setpoints
        ), 0)
        occupied.extend(local_positions)
        occupied.sort()

        if (
            abs(selected_offset) > 1e-9
            or locally_relocated
            or dropped
            or collision_count
        ):
            detail = (
                f"{zone.zone_name}: malla de refuerzo desfasada "
                f"{selected_offset:+.2f} m"
            )
            if locally_relocated:
                detail += (
                    f", {locally_relocated} posiciones recolocadas"
                )
            if dropped:
                detail += f", {dropped} posición(es) extrema(s) omitidas"
            messages.append(
                detail
                + f"; separación constructiva mínima {clearance:.2f} m."
            )

    return messages


def _attach_layered_scene_operating_points(
    zone_designs: List[ZoneLuminaireDesign],
    *,
    Lth: float,
    Lth_b: float,
    Lin: float,
    L_night: float,
    speed_kmh: float,
    cct: str,
    I_min_pct: float,
    scenarios: Optional[Dict[str, dict]] = None,
    enable_static_floor_shedding: bool = False,
) -> Dict[str, dict]:
    """Asigna a cada luminaria el punto físico de trabajo de cada escena.

    La selección del modelo/driver se mantiene fija: aquí solo se resuelve su
    corriente. En soleado la BASE usa la rampa instalada; en las demás escenas
    diurnas parte de la corriente que mantiene Lin y el control global puede
    elevarla hasta esa rampa. Por la noche trabaja a ``L_night``.
    """
    from modules.tunnel.optimizer import flux_power_at_current
    from modules.tunnel.required_luminance import (
        required_luminance_for_zone,
    )

    scene_defs = (
        ("sunny", "Soleado", 1.00),
        ("normal", "Normal", 0.70),
        ("overcast", "Cubierto", 0.30),
        ("dusk", "Crepuscular", 0.05),
        ("night", "Noche", 0.00),
    )
    output = dict(scenarios or {})
    totals = {
        key: {
            "name": label,
            "L20_factor": factor,
            "active_luminaires": 0,
            "off_luminaires": 0,
            "driver_floor_luminaires": 0,
            "power_w": 0.0,
            "flux_lm": 0.0,
        }
        for key, label, factor in scene_defs
    }
    i_min_mA = max(1.0, float(I_min_pct) * 350.0)

    def solve_fixed_model(
        model: str,
        target_flux: float,
        installed_current: float,
        installed_flux: float,
        installed_power: float,
    ) -> dict:
        target = max(0.0, float(target_flux))
        if target <= 1e-9:
            return {
                "state": "off",
                "current_mA": 0.0,
                "flux_lm": 0.0,
                "power_w": 0.0,
                "driver_floor": False,
                "target_flux_lm": 0.0,
            }
        if target >= installed_flux - 1e-6:
            return {
                "state": "on",
                "current_mA": round(installed_current, 1),
                "flux_lm": round(installed_flux, 3),
                "power_w": round(installed_power, 3),
                "driver_floor": False,
                "target_flux_lm": round(target, 3),
            }
        flux_min, power_min = flux_power_at_current(
            model, cct, i_min_mA, I_min_pct,
        )
        if target <= float(flux_min) + 1e-9:
            return {
                "state": "on",
                "current_mA": round(i_min_mA, 1),
                "flux_lm": round(float(flux_min), 3),
                "power_w": round(float(power_min), 3),
                "driver_floor": True,
                "target_flux_lm": round(target, 3),
            }
        low = i_min_mA
        high = max(i_min_mA, float(installed_current))
        for _ in range(36):
            mid = (low + high) / 2.0
            flux_mid, _ = flux_power_at_current(
                model, cct, mid, I_min_pct,
            )
            if float(flux_mid) >= target:
                high = mid
            else:
                low = mid
            if high - low <= 0.05:
                break
        flux_actual, power_actual = flux_power_at_current(
            model, cct, high, I_min_pct,
        )
        return {
            "state": "on",
            "current_mA": round(high, 1),
            "flux_lm": round(float(flux_actual), 3),
            "power_w": round(float(power_actual), 3),
            "driver_floor": False,
            "target_flux_lm": round(target, 3),
        }

    has_adaptation = any(
        str(getattr(zone, "control_layer", "legacy") or "legacy")
        == "adaptation"
        for zone in zone_designs
    )
    for zone in zone_designs:
        layer = str(
            getattr(zone, "control_layer", "legacy") or "legacy"
        )
        permanent = layer == "permanent"
        adaptation = layer == "adaptation"
        exterior = layer == "exterior"
        for setpoint in zone.setpoints or []:
            installed_model = str(
                setpoint.get("model", zone.model) or zone.model
            )
            installed_current = float(
                setpoint.get("current_mA", zone.current_mA) or 0.0
            )
            installed_flux = float(
                setpoint.get("flux_lm", zone.flux_lm) or 0.0
            )
            installed_power = float(
                setpoint.get("power_w", zone.power_w) or 0.0
            )
            base_current = float(
                setpoint.get("base_current_mA", installed_current)
                or installed_current
            )
            base_flux = float(
                setpoint.get("base_flux_lm", installed_flux)
                or installed_flux
            )
            base_power = float(
                setpoint.get("base_power_w", installed_power)
                or installed_power
            )
            position = float(setpoint.get("s", 0.0) or 0.0)
            max_total = (
                float(Lin)
                if permanent else required_luminance_for_zone(
                    zone,
                    position,
                    Lth=Lth,
                    Lth_b=Lth_b,
                    Lin=Lin,
                    speed_kmh=speed_kmh,
                )
            )
            max_residual = max(0.0, max_total - float(Lin))
            max_target_flux = float(
                setpoint.get("target_flux_lm", installed_flux)
                or installed_flux
            )
            operations = {}

            for key, _label, factor in scene_defs:
                if key == "night":
                    if permanent:
                        operation = {
                            "state": "on",
                            "current_mA": float(
                                setpoint.get("night_current_mA", 0.0) or 0.0
                            ),
                            "flux_lm": float(
                                setpoint.get("night_flux_lm", 0.0) or 0.0
                            ),
                            "power_w": float(
                                setpoint.get("night_power_w", 0.0) or 0.0
                            ),
                            "driver_floor": bool(
                                setpoint.get("night_driver_floor", False)
                            ),
                            "target_flux_lm": float(
                                setpoint.get(
                                    "night_target_flux_lm",
                                    setpoint.get("night_flux_lm", 0.0),
                                ) or 0.0
                            ),
                            "target_total_cd_m2": round(float(L_night), 3),
                            "target_layer_cd_m2": round(float(L_night), 3),
                        }
                    else:
                        operation = {
                            "state": "off",
                            "current_mA": 0.0,
                            "flux_lm": 0.0,
                            "power_w": 0.0,
                            "driver_floor": False,
                            "target_flux_lm": 0.0,
                            "target_total_cd_m2": round(float(L_night), 3),
                            "target_layer_cd_m2": 0.0,
                        }
                elif permanent:
                    use_installed_boost = key == "sunny"
                    operation = {
                        "state": "on",
                        "current_mA": round(
                            installed_current
                            if use_installed_boost else base_current,
                            1,
                        ),
                        "flux_lm": round(
                            installed_flux
                            if use_installed_boost else base_flux,
                            3,
                        ),
                        "power_w": round(
                            installed_power
                            if use_installed_boost else base_power,
                            3,
                        ),
                        "driver_floor": False,
                        "target_flux_lm": round(
                            installed_flux
                            if use_installed_boost else base_flux,
                            3,
                        ),
                        "target_total_cd_m2": round(float(Lin), 3),
                        "target_layer_cd_m2": round(float(Lin), 3),
                    }
                elif exterior:
                    target_flux = max_target_flux * factor
                    operation = solve_fixed_model(
                        installed_model,
                        target_flux,
                        installed_current,
                        installed_flux,
                        installed_power,
                    )
                    operation.update({
                        "target_total_cd_m2": round(
                            float(zone.L_total_required or zone.L_required or 0.0)
                            * factor,
                            3,
                        ),
                        "target_layer_cd_m2": round(
                            float(zone.L_required or 0.0) * factor,
                            3,
                        ),
                    })
                elif adaptation and key == "dusk":
                    dusk_total = float(
                        setpoint.get(
                            "L_total_req",
                            float(Lin)
                            + float(setpoint.get("L_req", 0.0) or 0.0),
                        )
                        or float(Lin)
                    )
                    operation = {
                        "state": "on",
                        "current_mA": round(installed_current, 1),
                        "flux_lm": round(installed_flux, 3),
                        "power_w": round(installed_power, 3),
                        "driver_floor": False,
                        "target_flux_lm": round(max_target_flux, 3),
                        "target_total_cd_m2": round(dusk_total, 3),
                        "target_layer_cd_m2": round(
                            max(0.0, dusk_total - float(Lin)), 3,
                        ),
                    }
                elif adaptation:
                    operation = {
                        "state": "off",
                        "current_mA": 0.0,
                        "flux_lm": 0.0,
                        "power_w": 0.0,
                        "driver_floor": False,
                        "target_flux_lm": 0.0,
                        "target_total_cd_m2": round(float(Lin), 3),
                        "target_layer_cd_m2": 0.0,
                    }
                elif key == "dusk" and has_adaptation:
                    operation = {
                        "state": "off",
                        "current_mA": 0.0,
                        "flux_lm": 0.0,
                        "power_w": 0.0,
                        "driver_floor": False,
                        "target_flux_lm": 0.0,
                        "target_total_cd_m2": round(
                            float(
                                setpoint.get("L_total_req", Lin) or Lin
                            ),
                            3,
                        ),
                        "target_layer_cd_m2": 0.0,
                    }
                else:
                    total_scene = required_luminance_for_zone(
                        zone,
                        position,
                        Lth=max(float(Lin), float(Lth) * factor),
                        Lth_b=max(float(Lin), float(Lth_b) * factor),
                        Lin=Lin,
                        speed_kmh=speed_kmh,
                    )
                    residual_scene = max(
                        0.0, float(total_scene) - float(Lin),
                    )
                    target_flux = (
                        max_target_flux * residual_scene / max_residual
                        if max_residual > 1e-9 else 0.0
                    )
                    operation = solve_fixed_model(
                        installed_model,
                        target_flux,
                        installed_current,
                        installed_flux,
                        installed_power,
                    )
                    operation.update({
                        "target_total_cd_m2": round(total_scene, 3),
                        "target_layer_cd_m2": round(residual_scene, 3),
                    })
                operations[key] = operation
            setpoint["scenario_operating_points"] = operations

        # Cuando el flujo residual por luminaria cae por debajo de Imin, dejar
        # todas las unidades al mínimo produciría una sobreiluminación grande.
        # Se conserva una distribución espacial ponderada y se apaga el resto.
        # La validación fotométrica posterior decide si esa malla es admisible.
        if (
            not permanent
            and not adaptation
            and enable_static_floor_shedding
        ):
            ordered = sorted(
                zone.setpoints or [],
                key=lambda item: float(item.get("s", 0.0) or 0.0),
            )
            for key in ("normal", "overcast", "dusk"):
                floor_candidates = [
                    sp for sp in ordered
                    if sp["scenario_operating_points"][key]["state"] == "on"
                    and sp["scenario_operating_points"][key]["driver_floor"]
                ]
                if len(floor_candidates) <= 1:
                    continue
                requested = sum(
                    float(
                        sp["scenario_operating_points"][key][
                            "target_flux_lm"
                        ]
                    )
                    for sp in floor_candidates
                )
                floor_fluxes = [
                    float(sp["scenario_operating_points"][key]["flux_lm"])
                    for sp in floor_candidates
                ]
                mean_floor_flux = (
                    sum(floor_fluxes) / len(floor_fluxes)
                    if floor_fluxes else 0.0
                )
                n_on = min(
                    len(floor_candidates),
                    max(
                        1,
                        int(math.ceil(
                            requested / max(mean_floor_flux, 1e-9)
                        )),
                    ),
                )
                if n_on >= len(floor_candidates):
                    continue
                weights = [
                    max(
                        1e-9,
                        float(sp["scenario_operating_points"][key][
                            "target_flux_lm"
                        ]),
                    )
                    for sp in floor_candidates
                ]
                total_weight = sum(weights)
                cumulative = []
                running = 0.0
                for weight in weights:
                    running += weight
                    cumulative.append(running)
                selected_indices = set()
                for index in range(n_on):
                    target_weight = (
                        (index + 0.5) * total_weight / n_on
                    )
                    selected = min(
                        range(len(cumulative)),
                        key=lambda candidate: abs(
                            cumulative[candidate] - target_weight
                        ),
                    )
                    if selected in selected_indices:
                        alternatives = [
                            candidate
                            for candidate in range(len(cumulative))
                            if candidate not in selected_indices
                        ]
                        selected = min(
                            alternatives,
                            key=lambda candidate: abs(
                                cumulative[candidate] - target_weight
                            ),
                        )
                    selected_indices.add(selected)
                for index, sp in enumerate(floor_candidates):
                    operation = sp["scenario_operating_points"][key]
                    if index in selected_indices:
                        operation["floor_shedding"] = False
                        continue
                    operation.update({
                        "state": "off",
                        "current_mA": 0.0,
                        "flux_lm": 0.0,
                        "power_w": 0.0,
                        "driver_floor": False,
                        "floor_shedding": True,
                    })

    for zone in zone_designs:
        for setpoint in zone.setpoints or []:
            for key, _label, _factor in scene_defs:
                operation = setpoint["scenario_operating_points"][key]
                bucket = totals[key]
                if operation["state"] == "off":
                    bucket["off_luminaires"] += 1
                else:
                    bucket["active_luminaires"] += 1
                if operation["driver_floor"]:
                    bucket["driver_floor_luminaires"] += 1
                bucket["power_w"] += float(operation["power_w"])
                bucket["flux_lm"] += float(operation["flux_lm"])

    for key, _label, _factor in scene_defs:
        bucket = totals[key]
        bucket["power_kw"] = round(bucket.pop("power_w") / 1000.0, 3)
        bucket["flux_lm"] = round(bucket["flux_lm"], 0)
        output.setdefault(key, {}).update(bucket)
    output.setdefault("day_max", {}).update(output["sunny"])
    return output


def _repair_dusk_scene_quality(
    result: TunnelLuminaireResult,
    params: dict,
    *,
    cct: str,
    I_min_pct: float,
    max_iterations: int = 1,
    max_candidates_per_iteration: int = 5,
) -> tuple[list[str], dict]:
    """Repara Uo/Ul crepuscular con una búsqueda CIE 140 acotada.

    La comprobación posterior de las seis escenas siempre es completa. Aquí
    sólo se evalúan los cambios locales más prometedores: explorar todas las
    parejas de luminarias cercanas multiplicaba los perfiles CIE 140 y podía
    convertir un cálculo de diseño en varios minutos sin aportar una mejora
    proporcional.
    """
    from modules.tunnel.optimizer import flux_power_at_current
    from modules.tunnel.photometric_verify import (
        verify_layered_operating_scenario,
    )

    messages: list[str] = []
    diagnostics = {
        "attempted": True,
        "iterations": 0,
        "evaluations": 0,
        "max_candidates_per_iteration": max(
            1, int(max_candidates_per_iteration),
        ),
        "changes": [],
    }
    if int(max_iterations) <= 0:
        diagnostics.update({
            "attempted": False,
            "reason": "disabled_by_project",
            "final": {},
        })
        return messages, diagnostics
    U0_required = float(params.get("U0_obj", 0.40) or 0.40)
    Ul_required = float(params.get("Ul_obj", 0.60) or 0.60)
    i_min_mA = max(1.0, float(I_min_pct) * 350.0)

    def _verify() -> dict:
        diagnostics["evaluations"] += 1
        return verify_layered_operating_scenario(
            result, params, "dusk", include_ti=False,
        )

    def _score(verification: dict) -> tuple[float, float, float]:
        if not verification.get("available"):
            return (-1.0, -1.0, -1e9)
        normalized = (
            float(verification.get("minimum_L_ratio", 0.0) or 0.0),
            float(verification.get("minimum_U0", 0.0) or 0.0)
            / max(U0_required, 1e-9),
            float(verification.get("minimum_Ul", 0.0) or 0.0)
            / max(Ul_required, 1e-9),
        )
        return (
            min(normalized),
            sum(min(value, 1.0) for value in normalized),
            -abs(normalized[0] - 1.0),
        )

    def _off_operation(previous: dict) -> dict:
        operation = dict(previous)
        operation.update({
            "state": "off",
            "current_mA": 0.0,
            "flux_lm": 0.0,
            "power_w": 0.0,
            "driver_floor": False,
            "quality_repair": "off",
        })
        return operation

    def _floor_operation(zone, setpoint, previous: dict) -> dict:
        model = str(
            setpoint.get("model", zone.model) or zone.model
        )
        floor_flux, floor_power = flux_power_at_current(
            model, cct, i_min_mA, I_min_pct,
        )
        operation = dict(previous)
        operation.update({
            "state": "on",
            "current_mA": round(i_min_mA, 1),
            "flux_lm": round(float(floor_flux), 3),
            "power_w": round(float(floor_power), 3),
            "driver_floor": True,
            "quality_repair": "minimum",
        })
        return operation

    current = _verify()
    diagnostics["initial"] = {
        key: current.get(key)
        for key in (
            "minimum_L_ratio", "minimum_U0", "minimum_Ul", "compliant",
        )
    }
    if not current.get("available") or current.get("compliant"):
        diagnostics["final"] = diagnostics["initial"]
        return messages, diagnostics

    reinforcement = [
        (zone, setpoint)
        for zone in result.zones
        if str(getattr(zone, "control_layer", "legacy") or "legacy")
        != "permanent"
        for setpoint in (zone.setpoints or [])
        if "dusk" in setpoint.get("scenario_operating_points", {})
    ]
    zero_residual_active = [
        (zone, setpoint)
        for zone, setpoint in reinforcement
        if (
            setpoint["scenario_operating_points"]["dusk"].get("state")
            != "off"
            and float(
                setpoint["scenario_operating_points"]["dusk"].get(
                    "target_layer_cd_m2", 0.0,
                )
                or 0.0
            )
            <= 1e-9
        )
    ]
    if zero_residual_active:
        originals = [
            (
                zone,
                setpoint,
                dict(setpoint["scenario_operating_points"]["dusk"]),
            )
            for zone, setpoint in zero_residual_active
        ]
        for _zone, setpoint, previous in originals:
            setpoint["scenario_operating_points"]["dusk"] = (
                _off_operation(previous)
            )
        candidate = _verify()
        if _score(candidate) > _score(current):
            diagnostics["changes"].append({
                "action": "off_zero_residual",
                "count": len(zero_residual_active),
                "group": 0,
            })
            current = candidate
        else:
            for _zone, setpoint, previous in originals:
                setpoint["scenario_operating_points"]["dusk"] = previous

    for iteration in range(max(1, int(max_iterations))):
        diagnostics["iterations"] = iteration + 1
        ratios = {
            "L": float(current.get("minimum_L_ratio", 0.0) or 0.0),
            "U0": (
                float(current.get("minimum_U0", 0.0) or 0.0)
                / max(U0_required, 1e-9)
            ),
            "Ul": (
                float(current.get("minimum_Ul", 0.0) or 0.0)
                / max(Ul_required, 1e-9)
            ),
        }
        governing = min(ratios, key=ratios.get)
        target_s = float(
            current.get(
                {
                    "L": "worst_field_s_m",
                    "U0": "minimum_U0_s_m",
                    "Ul": "minimum_Ul_s_m",
                }[governing],
                0.0,
            )
            or 0.0
        )
        active = []
        inactive = []
        for zone, setpoint in reinforcement:
            operation = setpoint["scenario_operating_points"]["dusk"]
            item = (
                abs(float(setpoint.get("s", 0.0) or 0.0) - target_s),
                zone,
                setpoint,
            )
            if operation.get("state") == "off":
                inactive.append(item)
            else:
                active.append(item)
        # Dos candidatos por tipo bastan para la pasada de reparación. Las
        # alternativas restantes se validan en la comprobación final y, si
        # procede, activan la reoptimización física multiescena.
        nearest_active = sorted(active, key=lambda item: item[0])[:2]
        nearest_inactive = sorted(inactive, key=lambda item: item[0])[:2]
        candidates = []
        for _, zone, setpoint in nearest_active:
            previous = setpoint["scenario_operating_points"]["dusk"]
            candidates.append((
                "off",
                [(zone, setpoint, _off_operation(previous))],
            ))
        for _, zone, setpoint in nearest_inactive:
            previous = setpoint["scenario_operating_points"]["dusk"]
            candidates.append((
                "minimum",
                [(zone, setpoint, _floor_operation(
                    zone, setpoint, previous,
                ))],
            ))
        for _, active_zone, active_setpoint in nearest_active:
            for _, inactive_zone, inactive_setpoint in nearest_inactive:
                active_previous = active_setpoint[
                    "scenario_operating_points"
                ]["dusk"]
                inactive_previous = inactive_setpoint[
                    "scenario_operating_points"
                ]["dusk"]
                candidates.append((
                    "swap",
                    [
                        (
                            active_zone,
                            active_setpoint,
                            _off_operation(active_previous),
                        ),
                        (
                            inactive_zone,
                            inactive_setpoint,
                            _floor_operation(
                                inactive_zone,
                                inactive_setpoint,
                                inactive_previous,
                            ),
                        ),
                    ],
                ))
        candidates = candidates[:max(1, int(max_candidates_per_iteration))]
        best = None
        best_score = _score(current)
        for action, mutations in candidates:
            originals = [
                (
                    zone,
                    setpoint,
                    dict(setpoint["scenario_operating_points"]["dusk"]),
                )
                for zone, setpoint, _operation in mutations
            ]
            for _zone, setpoint, operation in mutations:
                setpoint["scenario_operating_points"]["dusk"] = operation
            verification = _verify()
            candidate_score = _score(verification)
            for _zone, setpoint, previous in originals:
                setpoint["scenario_operating_points"]["dusk"] = previous
            if candidate_score > best_score:
                best_score = candidate_score
                best = (
                    action,
                    mutations,
                    verification,
                )
        if best is None:
            break
        action, mutations, verification = best
        for zone, setpoint, operation in mutations:
            setpoint["scenario_operating_points"]["dusk"] = operation
            diagnostics["changes"].append({
                "action": (
                    operation.get("quality_repair", action)
                    if action == "swap" else action
                ),
                "s_m": round(
                    float(setpoint.get("s", 0.0) or 0.0), 3,
                ),
                "zone": str(getattr(zone, "zone_name", "") or ""),
                "group": iteration + 1,
            })
        current = verification
        if current.get("compliant"):
            break

    active_count = 0
    off_count = 0
    floor_count = 0
    power_w = 0.0
    flux_lm = 0.0
    for zone in result.zones:
        for setpoint in zone.setpoints or []:
            operation = setpoint.get(
                "scenario_operating_points", {},
            ).get("dusk")
            if operation is None:
                continue
            if operation.get("state") == "off":
                off_count += 1
            else:
                active_count += 1
            floor_count += int(bool(operation.get("driver_floor", False)))
            power_w += float(operation.get("power_w", 0.0) or 0.0)
            flux_lm += float(operation.get("flux_lm", 0.0) or 0.0)
    result.scenarios.setdefault("dusk", {}).update({
        "active_luminaires": active_count,
        "off_luminaires": off_count,
        "driver_floor_luminaires": floor_count,
        "power_kw": round(power_w / 1000.0, 3),
        "flux_lm": round(flux_lm, 0),
    })
    diagnostics["final"] = {
        key: current.get(key)
        for key in (
            "minimum_L_ratio", "minimum_U0", "minimum_Ul", "compliant",
        )
    }
    if current.get("compliant"):
        messages.append(
            "Crepusculo reparado con validacion CIE 140: "
            f"{len(diagnostics['changes'])} conmutacion(es), "
            f"L/Lreq={current.get('minimum_L_ratio')}, "
            f"Uo={current.get('minimum_U0')}, "
            f"Ul={current.get('minimum_Ul')}."
        )
    else:
        # The influence matrix can close luminance while the exact CIE 140
        # verification still finds a deficit of luminance or uniformity. This
        # is a physical-layout shortfall, not merely an advisory message.
        diagnostics["reason"] = "verification_deficit"
        diagnostics["infeasibility_type"] = "cie140_quality"
        messages.append(
            "Crepusculo pendiente tras reparacion local: "
            f"L/Lreq={current.get('minimum_L_ratio')}, "
            f"Uo={current.get('minimum_U0')}, "
            f"Ul={current.get('minimum_Ul')}."
        )
    return messages, diagnostics


def _refresh_scene_operation_summary(
    result: TunnelLuminaireResult,
    scene_key: str,
) -> None:
    """Actualiza el resumen de una escena desde sus consignas individuales."""
    active = off = floors = 0
    power_w = flux_lm = 0.0
    for zone in result.zones:
        for setpoint in zone.setpoints or []:
            operation = setpoint.get(
                "scenario_operating_points", {},
            ).get(scene_key)
            if operation is None:
                continue
            if operation.get("state") == "off":
                off += 1
            else:
                active += 1
            floors += int(bool(operation.get("driver_floor", False)))
            power_w += float(operation.get("power_w", 0.0) or 0.0)
            flux_lm += float(operation.get("flux_lm", 0.0) or 0.0)
    result.scenarios.setdefault(scene_key, {}).update({
        "active_luminaires": active,
        "off_luminaires": off,
        "driver_floor_luminaires": floors,
        "power_kw": round(power_w / 1000.0, 3),
        "flux_lm": round(flux_lm, 0),
    })


def _optimize_scene_currents_exact(
    result: TunnelLuminaireResult,
    params: dict,
    *,
    scene_key: str,
    cct: str,
    I_min_pct: float,
    I_max_mA: float,
    max_iterations: int = 2,
    max_candidates_per_iteration: int = 2,
) -> tuple[list[str], dict]:
    """Ajusta una escena por luminaria contra los campos CIE 140 reales.

    La matriz de influencia solo genera un buen punto de partida. Esta fase no
    aplica un factor comun a toda la instalacion: prueba cambios discretos de
    corriente u OFF/Imin alrededor del campo que gobierna y acepta unicamente
    aquellos que mejoran la verificacion CIE 140 completa.  Soleado se trata
    primero y fija el limite superior de las otras escenas para cada equipo.
    """
    from modules.tunnel.optimizer import flux_power_at_current
    from modules.tunnel.photometric_verify import (
        verify_layered_operating_scenario,
    )

    labels = {
        "sunny": "Soleado", "normal": "Normal",
        "overcast": "Cubierto", "dusk": "Crepuscular",
    }
    diagnostics = {
        "attempted": True,
        "scene": scene_key,
        "iterations": 0,
        "evaluations": 0,
        "changes": [],
    }
    messages: list[str] = []
    if scene_key not in labels or max_iterations <= 0:
        diagnostics.update({
            "attempted": False,
            "reason": "disabled_or_unknown_scene",
            "final": {},
        })
        return messages, diagnostics

    i_min_mA = max(1.0, float(I_min_pct) * 350.0)
    i_max_mA = max(i_min_mA, float(I_max_mA))
    u0_required = max(1e-9, float(params.get("U0_obj", 0.40) or 0.40))
    ul_required = max(1e-9, float(params.get("Ul_obj", 0.60) or 0.60))
    upper_ratio = max(
        1.0,
        float(params.get("scene_exact_upper_ratio", 1.07) or 1.07),
    )

    def _verify() -> dict:
        diagnostics["evaluations"] += 1
        return verify_layered_operating_scenario(
            result, params, scene_key, include_ti=False,
        )

    def _quality(verification: dict) -> tuple[float, float, float, float]:
        wall_required = max(
            1e-9,
            float(verification.get("wall_ratio_required", 0.0) or 0.0),
        )
        wall_ratio = verification.get("minimum_wall_ratio")
        wall_normalized = (
            float(wall_ratio) / wall_required
            if wall_ratio is not None else 1.0
        )
        return (
            float(verification.get("minimum_L_ratio", 0.0) or 0.0),
            float(verification.get("minimum_U0", 0.0) or 0.0)
            / u0_required,
            float(verification.get("minimum_Ul", 0.0) or 0.0)
            / ul_required,
            wall_normalized,
        )

    def _score(verification: dict) -> tuple:
        if not verification.get("available"):
            return (-1, -1.0, -1.0, -1e9, -1e9)
        quality = _quality(verification)
        floor = min(quality)
        coverage = sum(min(value, 1.0) for value in quality)
        excess = max(
            0.0,
            float(verification.get("maximum_L_ratio", 1.0) or 1.0)
            - upper_ratio,
        )
        power = float(verification.get("operating_power_kw", 0.0) or 0.0)
        if floor < 1.0 - 1e-8:
            # Primero se recupera el cumplimiento; una reduccion de exceso
            # nunca puede ganar a L/U0/Ul/pared insuficientes.
            return (0, floor, coverage, -excess, -power)
        # Ya conforme: aproximar Lest a Lreq y, a igualdad, ahorrar potencia.
        return (1, -excess, floor, coverage, -power)

    def _operation_at_current(zone, setpoint, previous, current_mA, action):
        layer = str(
            getattr(zone, "control_layer", "legacy") or "legacy"
        )
        model = str(setpoint.get("model", zone.model) or zone.model)
        permanent = layer == "permanent"
        adaptation = layer == "adaptation"
        current_cap = i_max_mA
        sunny_operation = setpoint.get(
            "scenario_operating_points", {},
        ).get("sunny", {})
        # La misma luminaria no puede trabajar en una escena intermedia por
        # encima de su consigna Soleado. La capa ADAPTACION es independiente
        # y se deja disponible exclusivamente para el escalon crepuscular.
        if scene_key != "sunny" and not adaptation:
            sunny_current = float(
                sunny_operation.get("current_mA", 0.0) or 0.0
            )
            if sunny_operation.get("state") != "off" and sunny_current > 0:
                current_cap = min(current_cap, sunny_current)
        # "permanent" describe la capa fisica y su funcionamiento nocturno,
        # no una corriente fija durante el dia.  En Soleado/Normal/Cubierto/
        # Crepuscular se conserva encendida (no se apaga), pero puede bajar a
        # Imin como cualquier equipo DALI/Wirepas.  Bloquearla a la corriente
        # base nocturna era la causa de los picos Lest que no se podian
        # recortar aunque el campo CIE 140 ya estuviera por encima de Lreq.
        # La escena nocturna se construye y verifica aparte con
        # ``night_current_mA`` y no pasa por este optimizador.
        minimum_current = i_min_mA
        current_cap = max(minimum_current, current_cap)
        # La capa BASE permanece instalada y alimenta la escena nocturna,
        # pero en una escena diurna cada equipo puede quedar OFF si el campo
        # completo CIE 140 lo admite.  Es imprescindible para no mantener un
        # solape de Imin que eleve Lest en Normal/Cubierto; la comprobacion
        # exacta inmediatamente posterior impide crear huecos o perder U0/Ul.
        if current_mA <= 1e-9:
            operation = dict(previous)
            operation.update({
                "state": "off", "current_mA": 0.0, "flux_lm": 0.0,
                "power_w": 0.0, "driver_floor": False,
                "exact_local_action": action,
            })
            return operation, current_cap, minimum_current
        actual_current = min(
            current_cap, max(minimum_current, float(current_mA)),
        )
        flux, power = flux_power_at_current(
            model, cct, actual_current, I_min_pct,
        )
        operation = dict(previous)
        operation.update({
            "state": "on",
            "current_mA": round(float(actual_current), 1),
            "flux_lm": round(float(flux), 3),
            "power_w": round(float(power), 3),
            "driver_floor": actual_current <= minimum_current + 0.05,
            "exact_local_action": action,
        })
        return operation, current_cap, minimum_current

    # Garantiza el orden de consignas entre escenas antes de evaluar: la
    # regulacion intermedia no puede quedar por encima de Soleado para la
    # misma luminaria. ADAPTACION queda exenta porque es una capa dedicada al
    # escalon de crepusculo.
    if scene_key != "sunny":
        for zone in result.zones:
            layer = str(
                getattr(zone, "control_layer", "legacy") or "legacy"
            )
            if layer == "adaptation":
                continue
            for setpoint in zone.setpoints or []:
                operations = setpoint.get("scenario_operating_points", {})
                operation = operations.get(scene_key)
                sunny_operation = operations.get("sunny")
                if (
                    operation is None
                    or sunny_operation is None
                    or operation.get("state") == "off"
                    or sunny_operation.get("state") == "off"
                ):
                    continue
                sunny_current = float(
                    sunny_operation.get("current_mA", 0.0) or 0.0,
                )
                current_value = float(
                    operation.get("current_mA", 0.0) or 0.0,
                )
                if sunny_current > 0.0 and current_value > sunny_current + 0.05:
                    capped, _cap, _minimum = _operation_at_current(
                        zone, setpoint, operation, sunny_current,
                        "cap_to_sunny",
                    )
                    operations[scene_key] = capped

    current = _verify()
    diagnostics["initial"] = {
        key: current.get(key)
        for key in (
            "minimum_L_ratio", "maximum_L_ratio", "minimum_U0",
            "minimum_Ul", "minimum_wall_ratio", "compliant",
        )
    }
    if not current.get("available"):
        diagnostics.update({"reason": "profile_unavailable", "final": {}})
        return messages, diagnostics

    # Cuando una escena ya cumple todos los minimos, pero esta entera muy por
    # encima del perfil, una busqueda exclusivamente local necesitara decenas
    # de pasos para llegar a la vecindad util.  Esta pasada es solo una
    # precondicion (no la solucion final): baja cada equipo respecto de su
    # propio Imin/base y, despues, el bucle CIE 140 siguiente corrige cada
    # luminaria de forma individual.  Cada factor se acepta unicamente si la
    # verificacion completa conserva L, U0, Ul y pared.
    global_precondition = {
        "attempted": False,
        "applied": False,
        "factor": 1.0,
        "evaluations": 0,
    }
    current_quality = _quality(current)
    if (
        min(current_quality) >= 1.0 - 1e-8
        and float(current.get("maximum_L_ratio", 1.0) or 1.0)
        > upper_ratio * 1.12
        and bool(params.get("scene_exact_precondition", True))
        # Los candidatos de rediseño físico se validan con una pasada muy
        # corta; el refinamiento completo se reserva para la alternativa que
        # finalmente se selecciona. De otro modo cada alternativa multiplica
        # la verificación CIE 140 de las cuatro escenas.
        and not bool(params.get("_scene_reoptimization_attempt", False))
    ):
        original_operations: list[tuple[dict, dict]] = []
        scalable: list[tuple[object, dict, dict, float, float]] = []
        for zone in result.zones:
            for setpoint in zone.setpoints or []:
                operations = setpoint.get("scenario_operating_points", {})
                previous = operations.get(scene_key)
                if previous is None or previous.get("state") == "off":
                    continue
                previous_current = float(
                    previous.get("current_mA", 0.0) or 0.0,
                )
                _probe, _cap, minimum = _operation_at_current(
                    zone, setpoint, previous, previous_current, "probe",
                )
                if previous_current > minimum + 0.05:
                    scalable.append((
                        zone, setpoint, previous, previous_current, minimum,
                    ))
                    original_operations.append((setpoint, previous))

        if scalable:
            global_precondition["attempted"] = True

            def _scaled_candidate(factor: float) -> tuple[dict, list[tuple[dict, dict]]]:
                replacements: list[tuple[dict, dict]] = []
                for zone, setpoint, previous, previous_current, minimum in scalable:
                    target_current = minimum + float(factor) * (
                        previous_current - minimum
                    )
                    operation, _cap, _minimum = _operation_at_current(
                        zone, setpoint, previous, target_current,
                        "scene_precondition",
                    )
                    replacements.append((setpoint, operation))
                for setpoint, operation in replacements:
                    setpoint["scenario_operating_points"][scene_key] = operation
                verification = _verify()
                global_precondition["evaluations"] += 1
                for setpoint, previous in original_operations:
                    setpoint["scenario_operating_points"][scene_key] = previous
                return verification, replacements

            # f=0 representa Imin/base. Si no cierra, se buscan dos puntos
            # acotados entre esa situacion y la consigna inicial f=1.
            best_factor = 1.0
            best_verification = current
            floor_verification, floor_replacements = _scaled_candidate(0.0)
            if floor_verification.get("available") and floor_verification.get(
                "compliant"
            ):
                best_factor = 0.0
                best_verification = floor_verification
                best_replacements = floor_replacements
            else:
                low, high = 0.0, 1.0
                best_replacements = []
                for _ in range(2):
                    midpoint = (low + high) / 2.0
                    verification, replacements = _scaled_candidate(midpoint)
                    if verification.get("available") and verification.get(
                        "compliant"
                    ):
                        high = midpoint
                        best_factor = midpoint
                        best_verification = verification
                        best_replacements = replacements
                    else:
                        low = midpoint
            if best_factor < 1.0 - 1e-8:
                for setpoint, operation in best_replacements:
                    setpoint["scenario_operating_points"][scene_key] = operation
                current = best_verification
                global_precondition.update({
                    "applied": True,
                    "factor": round(float(best_factor), 4),
                    "scalable_luminaires": len(scalable),
                    "minimum_L_ratio": current.get("minimum_L_ratio"),
                    "maximum_L_ratio": current.get("maximum_L_ratio"),
                })
    diagnostics["preconditioning"] = global_precondition

    for iteration in range(max(1, int(max_iterations))):
        quality = _quality(current)
        normalized = {
            "L": quality[0], "U0": quality[1],
            "Ul": quality[2], "wall": quality[3],
        }
        governing = min(normalized, key=normalized.get)
        is_compliant = min(normalized.values()) >= 1.0 - 1e-8
        highest_ratio = float(
            current.get("maximum_L_ratio", 1.0) or 1.0,
        )
        if is_compliant and highest_ratio <= upper_ratio + 1e-8:
            break
        target_s = float(current.get(
            "maximum_field_s_m" if is_compliant else {
                "L": "worst_field_s_m",
                "U0": "minimum_U0_s_m",
                "Ul": "minimum_Ul_s_m",
                "wall": "worst_field_s_m",
            }[governing],
            0.0,
        ) or 0.0)
        active: list[tuple[float, object, dict]] = []
        inactive: list[tuple[float, object, dict]] = []
        for zone in result.zones:
            for setpoint in zone.setpoints or []:
                operation = setpoint.get(
                    "scenario_operating_points", {},
                ).get(scene_key)
                if operation is None:
                    continue
                item = (
                    abs(float(setpoint.get("s", 0.0) or 0.0) - target_s),
                    zone,
                    setpoint,
                )
                if operation.get("state") == "off":
                    inactive.append(item)
                else:
                    active.append(item)
        active = sorted(active, key=lambda item: item[0])[:3]
        inactive = sorted(inactive, key=lambda item: item[0])[:2]
        mutations: list[tuple[str, object, dict, dict]] = []
        if is_compliant:
            for _distance, zone, setpoint in active:
                previous = setpoint["scenario_operating_points"][scene_key]
                previous_current = float(
                    previous.get("current_mA", 0.0) or 0.0,
                )
                _probe, _cap, minimum = _operation_at_current(
                    zone, setpoint, previous, previous_current, "probe",
                )
                operation, _cap, minimum = _operation_at_current(
                    zone, setpoint, previous,
                    max(0.0, previous_current
                        - max(15.0, 0.30 * max(
                            0.0,
                            previous_current - minimum,
                        ))),
                    "reduce_current",
                )
                mutations.append(("reduce_current", zone, setpoint, operation))
                off_operation, _cap, _minimum = _operation_at_current(
                    zone, setpoint, previous, 0.0, "switch_off",
                )
                mutations.append(("switch_off", zone, setpoint, off_operation))
        else:
            # Un fallo de uniformidad no se resuelve necesariamente
            # aumentando el punto oscuro: cuando hay exceso local, bajar la
            # luminaria que gobierna el maximo puede mejorar U0/Ul sin perder
            # el minimo de L.  Se prueban ambas direcciones contra el campo
            # CIE 140 real y solo se conserva la que mejora la puntuacion.
            # Esto evita que Normal/Cubierto queden sobredimensionadas por
            # intentar resolver U0/Ul unicamente con mas corriente.
            reduction_mutations: list[tuple[str, object, dict, dict]] = []
            if governing in ("U0", "Ul", "wall") and highest_ratio > (
                upper_ratio + 1e-8
            ):
                high_target_s = float(
                    current.get("maximum_field_s_m", target_s) or target_s,
                )
                high_active = sorted(
                    [
                        (
                            abs(float(setpoint.get("s", 0.0) or 0.0)
                                - high_target_s),
                            zone,
                            setpoint,
                        )
                        for zone in result.zones
                        for setpoint in zone.setpoints or []
                        if (
                            setpoint.get("scenario_operating_points", {})
                            .get(scene_key, {}).get("state") != "off"
                        )
                    ],
                    key=lambda item: item[0],
                )[:2]
                for _distance, zone, setpoint in high_active:
                    previous = setpoint["scenario_operating_points"][scene_key]
                    previous_current = float(
                        previous.get("current_mA", 0.0) or 0.0,
                    )
                    _probe, _cap, minimum = _operation_at_current(
                        zone, setpoint, previous, previous_current, "probe",
                    )
                    operation, _cap, minimum = _operation_at_current(
                        zone, setpoint, previous,
                        max(
                            0.0,
                            previous_current - max(
                                15.0,
                                0.30 * max(0.0, previous_current - minimum),
                            ),
                        ),
                        "reduce_excess_for_uniformity",
                    )
                    if float(operation.get("current_mA", 0.0) or 0.0) < (
                        previous_current - 0.05
                    ):
                        reduction_mutations.append((
                            "reduce_excess_for_uniformity", zone, setpoint,
                            operation,
                        ))

            increase_mutations: list[tuple[str, object, dict, dict]] = []
            for _distance, zone, setpoint in active:
                previous = setpoint["scenario_operating_points"][scene_key]
                prior_current = float(
                    previous.get("current_mA", 0.0) or 0.0,
                )
                _probe, cap, _minimum = _operation_at_current(
                    zone, setpoint, previous, prior_current, "probe",
                )
                operation, _cap, _minimum = _operation_at_current(
                    zone, setpoint, previous,
                    min(cap, prior_current + max(
                        20.0, 0.25 * max(0.0, cap - prior_current),
                    )),
                    "increase_current",
                )
                if float(operation.get("current_mA", 0.0) or 0.0) > prior_current + 0.05:
                    increase_mutations.append((
                        "increase_current", zone, setpoint, operation,
                    ))
            for _distance, zone, setpoint in inactive:
                previous = setpoint["scenario_operating_points"][scene_key]
                operation, _cap, _minimum = _operation_at_current(
                    zone, setpoint, previous, i_min_mA, "switch_on_minimum",
                )
                if operation.get("state") != "off":
                    increase_mutations.append((
                        "switch_on_minimum", zone, setpoint, operation,
                    ))
            # Con una exploracion corta (dos candidatos por defecto),
            # alternamos descenso en el maximo y refuerzo del minimo. Asi la
            # decision no queda sesgada hacia la primera luminaria de una
            # lista ordenada por distancia.
            for index in range(max(
                len(reduction_mutations), len(increase_mutations),
            )):
                if index < len(reduction_mutations):
                    mutations.append(reduction_mutations[index])
                if index < len(increase_mutations):
                    mutations.append(increase_mutations[index])

        # Un candidato es una modificacion de una luminaria: se elige por la
        # verificacion exacta completa, no por una estimacion longitudinal.
        best = None
        baseline_score = _score(current)
        for action, zone, setpoint, operation in mutations[:max(
            1, int(max_candidates_per_iteration),
        )]:
            previous = dict(
                setpoint["scenario_operating_points"][scene_key],
            )
            setpoint["scenario_operating_points"][scene_key] = operation
            verification = _verify()
            setpoint["scenario_operating_points"][scene_key] = previous
            candidate_score = _score(verification)
            if candidate_score > baseline_score and (
                best is None or candidate_score > best[0]
            ):
                best = (candidate_score, action, zone, setpoint, operation,
                        verification)
        diagnostics["iterations"] = iteration + 1
        if best is None:
            break
        _score_value, action, zone, setpoint, operation, verification = best
        setpoint["scenario_operating_points"][scene_key] = operation
        diagnostics["changes"].append({
            "action": action,
            "s_m": round(float(setpoint.get("s", 0.0) or 0.0), 3),
            "zone": str(getattr(zone, "zone_name", "") or ""),
            "current_mA": round(
                float(operation.get("current_mA", 0.0) or 0.0), 1,
            ),
        })
        current = verification

    _refresh_scene_operation_summary(result, scene_key)
    diagnostics["final"] = {
        key: current.get(key)
        for key in (
            "minimum_L_ratio", "maximum_L_ratio", "minimum_U0",
            "minimum_Ul", "minimum_wall_ratio", "worst_field_s_m",
            "maximum_field_s_m", "minimum_U0_s_m", "minimum_Ul_s_m",
            "compliant",
        )
    }
    diagnostics["upper_ratio_target"] = round(upper_ratio, 4)
    if diagnostics["changes"]:
        messages.append(
            f"{labels[scene_key]}: ajuste CIE 140 luminaria a luminaria "
            f"({len(diagnostics['changes'])} cambio(s))."
        )
    if not current.get("compliant"):
        diagnostics["reason"] = "verification_deficit"
        diagnostics["infeasibility_type"] = "cie140_quality"
    elif float(current.get("maximum_L_ratio", 1.0) or 1.0) > upper_ratio:
        diagnostics["reason"] = "excess_unresolved"
    return messages, diagnostics


def _trim_scene_to_exact_profile(
    result: TunnelLuminaireResult,
    params: dict,
    *,
    scene_key: str,
    cct: str,
    I_min_pct: float,
    max_evaluations: int = 6,
) -> tuple[list[str], dict]:
    """Reduce refuerzos solo cuando el perfil CIE 140 exacto lo permite.

    La matriz de influencia ofrece una solución inicial muy rápida, pero sus
    muestras no sustituyen el promedio de campo CIE 140. Esta pasada hace una
    búsqueda acotada sobre el flujo de las capas de refuerzo; cada propuesta
    se acepta únicamente si el perfil real sigue cumpliendo L, Uo, Ul y pared.
    """
    from modules.tunnel.optimizer import flux_power_at_current
    from modules.tunnel.photometric_verify import (
        verify_layered_operating_scenario,
    )

    labels = {
        "sunny": "Soleado", "normal": "Normal",
        "overcast": "Cubierto", "dusk": "Crepuscular",
    }
    diagnostics = {
        "attempted": True,
        "evaluations": 0,
        "scene": scene_key,
        "changes": 0,
    }

    def _verify() -> dict:
        diagnostics["evaluations"] += 1
        return verify_layered_operating_scenario(
            result, params, scene_key, include_ti=False,
        )

    current = _verify()
    diagnostics["initial"] = {
        key: current.get(key)
        for key in ("minimum_L_ratio", "minimum_U0", "minimum_Ul", "compliant")
    }
    # Un déficit o una falta de uniformidad no se puede resolver reduciendo
    # flujo: se conserva para la reoptimización física posterior.
    if not current.get("available") or not current.get("compliant"):
        diagnostics["reason"] = "not_compliant_before_trim"
        diagnostics["final"] = dict(diagnostics["initial"])
        return [], diagnostics

    candidates = [
        (zone, setpoint, dict(setpoint["scenario_operating_points"][scene_key]))
        for zone in result.zones
        if str(getattr(zone, "control_layer", "legacy") or "legacy")
        != "permanent"
        for setpoint in zone.setpoints or []
        if scene_key in setpoint.get("scenario_operating_points", {})
        and setpoint["scenario_operating_points"][scene_key].get("state") != "off"
        and float(
            setpoint["scenario_operating_points"][scene_key].get("flux_lm", 0.0)
            or 0.0
        ) > 1e-9
    ]
    if not candidates:
        diagnostics["reason"] = "no_reinforcement_active"
        diagnostics["final"] = dict(diagnostics["initial"])
        return [], diagnostics

    i_min_mA = max(1.0, float(I_min_pct) * 350.0)

    def _operation_at_scale(zone, setpoint, previous, scale: float) -> dict:
        operation = dict(previous)
        model = str(setpoint.get("model", zone.model) or zone.model)
        target_flux = max(0.0, float(previous.get("flux_lm", 0.0)) * scale)
        min_flux, _min_power = flux_power_at_current(
            model, cct, i_min_mA, I_min_pct,
        )
        if target_flux < float(min_flux) - 1e-9:
            operation.update({
                "state": "off", "current_mA": 0.0, "flux_lm": 0.0,
                "power_w": 0.0, "driver_floor": False,
            })
        else:
            low = i_min_mA
            high = max(low, float(previous.get("current_mA", low) or low))
            for _ in range(28):
                middle = (low + high) / 2.0
                flux_mid, _power_mid = flux_power_at_current(
                    model, cct, middle, I_min_pct,
                )
                if float(flux_mid) >= target_flux:
                    high = middle
                else:
                    low = middle
            flux, power = flux_power_at_current(
                model, cct, high, I_min_pct,
            )
            operation.update({
                "state": "on", "current_mA": round(high, 1),
                "flux_lm": round(float(flux), 3),
                "power_w": round(float(power), 3),
                "driver_floor": high <= i_min_mA + 0.05,
            })
        operation["exact_profile_trim"] = round(scale, 5)
        return operation

    def _apply(scale: float) -> None:
        for zone, setpoint, previous in candidates:
            setpoint["scenario_operating_points"][scene_key] = (
                _operation_at_scale(zone, setpoint, previous, scale)
            )

    lower = 0.0
    upper = 1.0
    best_scale = 1.0
    best_verification = current
    for _ in range(max(1, int(max_evaluations))):
        candidate_scale = (lower + upper) / 2.0
        _apply(candidate_scale)
        verification = _verify()
        if verification.get("available") and verification.get("compliant"):
            best_scale = candidate_scale
            best_verification = verification
            upper = candidate_scale
        else:
            lower = candidate_scale
    _apply(best_scale)
    diagnostics["scale"] = round(best_scale, 5)
    diagnostics["changes"] = len(candidates) if best_scale < 0.999 else 0
    diagnostics["final"] = {
        key: best_verification.get(key)
        for key in ("minimum_L_ratio", "minimum_U0", "minimum_Ul", "compliant")
    }

    # Mantener los indicadores de la escena coherentes con las consignas que
    # acaba de validar el perfil exacto.
    active = off = floors = 0
    power_w = flux_lm = 0.0
    for zone in result.zones:
        for setpoint in zone.setpoints or []:
            operation = setpoint.get("scenario_operating_points", {}).get(scene_key)
            if operation is None:
                continue
            if operation.get("state") == "off":
                off += 1
            else:
                active += 1
            floors += int(bool(operation.get("driver_floor", False)))
            power_w += float(operation.get("power_w", 0.0) or 0.0)
            flux_lm += float(operation.get("flux_lm", 0.0) or 0.0)
    result.scenarios.setdefault(scene_key, {}).update({
        "active_luminaires": active, "off_luminaires": off,
        "driver_floor_luminaires": floors,
        "power_kw": round(power_w / 1000.0, 3),
        "flux_lm": round(flux_lm, 0),
    })
    messages = []
    if best_scale < 0.999:
        messages.append(
            f"{labels.get(scene_key, scene_key)}: consignas ajustadas con "
            f"perfil CIE 140 real ({best_scale * 100:.1f}% del refuerzo)."
        )
    return messages, diagnostics


def design_aphex_tunnel_optimized(
    zones_list:    list,
    params:        dict,
    road_width_m:  float,
    tube_length_m: float,
    tube_id:       str = "T1",
) -> TunnelLuminaireResult:
    """
    Motor inside-out con optimizacion U0/Ul via CIE 140 real.

    Fase 1 — Interior:
        Celda periodica sobre malla instalable. Prioridad
        F151 -> F2MD -> F2M2 y objetivo configurable de numero o potencia.

    Fase 2 — Transicion continua:
        Desde Interior hacia cada portal, con reducciones discretas de
        interdistancia. Optica y tilt se resuelven antes del hardware.

    Fase 3 — Acoplamiento global:
        Matriz de influencia L=A@phi, monotonia por escalon y asignacion
        posterior del modelo-driver menor compatible con Imin/Imax.

    Modo retrofit (d_fixed != None): d fijo en todas las zonas.
    """
    from modules.tunnel.optimizer import (
        optimize_interior, optimize_single_luminaire, find_dmax_for_zone,
        cie88_L_transition, flux_power_at_current,
        L_from_flux, phi_for_luminance, eval_quality,
        select_geometry_for_spacing, select_model_for_flux,
        set_design_ambient_temperature,
    )

    calculation_started = time.perf_counter()
    performance: Dict[str, object] = {
        "stages_s": {},
        "counters": {},
    }
    warnings_out: List[str] = []
    # La fase BASE devuelve primero la instalación física y su escena soleada.
    # La optimización DALI multiescenario queda como segunda fase: en túneles
    # largos domina el tiempo de respuesta pero no modifica la geometría.
    # Quien no especifique fase conserva el cálculo completo anterior.
    calculation_phase = str(params.get("calculation_phase", "full") or "full").lower()
    full_control_validation = calculation_phase == "full"
    if calculation_phase not in ("base", "full"):
        calculation_phase = "full"
        full_control_validation = True
    performance["calculation_phase"] = calculation_phase

    # ── Parametros ─────────────────────────────────────────────────────────
    set_design_ambient_temperature(float(params.get('ta_design_c', 20.0)))
    I_max_mA    = float(params.get('I_max_mA', 750))
    _I_min_raw  = params.get('I_min_pct', 0.30)
    I_min_pct   = float(_I_min_raw) / 100.0 if float(_I_min_raw) > 1.0 else float(_I_min_raw)

    cct         = str(params.get('cct', '4000K'))
    if cct not in ('3000K', '4000K'):
        cct = '4000K'

    arrangement = str(params.get('arrangement', 'central_single'))
    if arrangement not in ARRANGEMENTS:
        arrangement = 'central_single'

    h          = float(params.get('mounting_height_m', 4.5))
    wall_offset = float(params.get('wall_offset_m', 0.30))
    mf  = float(params.get('maintenance_factor', DEFAULT_MF))
    w   = max(road_width_m, 1.0)
    wall_offset = min(
        max(0.05, wall_offset),
        max(0.05, w / 2.0 - 0.05),
    )

    # ── Validación de posición de luminaria dentro de la sección ────────────
    _H_total  = float(params.get('height_m', 5.5))
    _shape    = str(params.get('tunnel_shape', 'horseshoe'))
    _H_pared  = float(params.get('H_pared_m', 3.0))
    arrangement_val = str(params.get('arrangement', 'central_single'))
    _ys_check = _y_positions_for_validation(arrangement_val, w, wall_offset)
    for _y in _ys_check:
        if not is_inside_tunnel(_y, h, w, _H_total, _shape, _H_pared):
            warnings_out.append(
                f"⚠️ POSICIÓN DE LUMINARIA FUERA DEL CONTORNO: "
                f"y={_y:.2f} m, altura={h:.2f} m — "
                f"ajusta la distancia a pared o altura de montaje."
            )

    surface_key = str(params.get('road_surface', 'medium_asphalt'))
    rtable      = _SURFACE_RTABLE.get(surface_key, 'R2')

    U0_obj   = float(params.get('U0_obj',  0.40))
    Ul_obj   = float(params.get('Ul_obj',  0.60))
    tilt_max = float(params.get('tilt_max', 20.0))
    tilt_grid = [float(t) for t in range(0, int(tilt_max)+1, 5)]
    if tilt_max not in tilt_grid:
        tilt_grid.append(tilt_max)

    _df     = params.get('d_fixed', None)
    d_fixed = float(_df) if _df not in (None, '', 0, '0') else None

    _dm     = params.get('d_min', 2.5)
    D_MIN   = float(_dm) if _dm not in (None, '', 0) else 2.5
    D_MIN   = max(0.3, min(D_MIN, 10.0))  # clamp 0.3–10 m

    optimization_goal = str(
        params.get('optimization_goal', 'min_luminaires')
    ).lower()
    if optimization_goal not in ('min_luminaires', 'min_power'):
        optimization_goal = 'min_luminaires'
    spacing_quantum = max(
        0.5, float(params.get('spacing_quantum_m', 0.5) or 0.5)
    )
    constructive_min_separation = max(
        0.05,
        float(
            params.get('constructive_min_separation_m', 0.50)
            or 0.50
        ),
    )
    D_MIN = (
        math.ceil(D_MIN / spacing_quantum - 1e-9)
        * spacing_quantum
    )
    transition_spacing_step = max(
        spacing_quantum,
        float(params.get('transition_spacing_step_m', 2.0) or 2.0),
    )
    transition_spacing_step = (
        math.ceil(transition_spacing_step / spacing_quantum - 1e-9)
        * spacing_quantum
    )
    raw_threshold_spacing_caps = params.get(
        "_scene_reoptimization_threshold_spacing_caps", {},
    )
    threshold_spacing_caps = (
        raw_threshold_spacing_caps
        if isinstance(raw_threshold_spacing_caps, dict) else {}
    )

    speed_kmh = float(params.get('speed_kmh', 80.0))
    Lth_cie   = float(params.get('Lth', 0.0))
    Lth_b_cie = float(params.get('Lth_b', Lth_cie))   # luminancia umbral portal B
    Lin_cie   = float(params.get('Lin', 0.0))
    L_night_cie = float(params.get('L_night', 1.0))

    # ── Zonas validas ───────────────────────────────────────────────────────
    # En un túnel corto zones.py conserva la etiqueta de transición truncada
    # para señalar el solape con la salida, pero la curva CIE no se interrumpe.
    # En la arquitectura por capas el refuerzo debe prolongarse físicamente
    # sobre ese solape hasta alcanzar Lin o la boca correspondiente.
    source_zones = [dict(zone) for zone in zones_list]
    if str(params.get(
        'control_architecture',
        'permanent_base_plus_portal_reinforcement',
    )) == 'permanent_base_plus_portal_reinforcement':
        from modules.tunnel.zones import calculate_transition_length
        for zone in source_zones:
            zone_type = str(zone.get('zone_type', '') or '').lower()
            if 'transition' not in zone_type:
                continue
            portal_lth = Lth_b_cie if zone_type.endswith('_b') else Lth_cie
            theoretical_length = calculate_transition_length(
                portal_lth, Lin_cie, speed_kmh,
            )
            if zone_type.endswith('_b'):
                zone['s_start'] = max(
                    0.0,
                    float(zone.get('s_end', tube_length_m))
                    - theoretical_length,
                )
            else:
                zone['s_end'] = min(
                    float(tube_length_m),
                    float(zone.get('s_start', 0.0))
                    + theoretical_length,
                )
            zone['zone_length'] = max(
                0.0,
                float(zone['s_end']) - float(zone['s_start']),
            )

    valid_zones = [
        z for z in source_zones
        if str(z.get('zone_type') or z.get('type') or '').lower()
        not in {'exit', 'access', 'parting'}
        and float(z.get('L_min_required', 0)) > 0
        and float(z.get('s_end', 0)) > float(z.get('s_start', 0))
    ]
    performance["stages_s"]["prepare"] = round(
        time.perf_counter() - calculation_started, 4,
    )
    performance["counters"]["normative_zones"] = len(valid_zones)

    if not valid_zones:
        warnings_out.append('No hay zonas con L_req > 0.')
        result = TunnelLuminaireResult(
            tube_id=tube_id, luminaire=None,
            road_surface_type=surface_key, rho_eff=0.085,
            road_width_m=w, tube_length_m=tube_length_m,
            optic='F2M2', cct=cct, I_max_mA=int(I_max_mA),
            arrangement=arrangement, zones=[], warnings=warnings_out,
            performance=performance,
        )
        result._compute_totals()
        performance["total_s"] = round(
            time.perf_counter() - calculation_started, 4,
        )
        return result

    # El ancla inside-out es la zona INTERIOR y, si el tunel es corto y no
    # llega a existir geometricamente, el Lin normativo. Tomar el minimo de
    # todas las zonas incluia salida/parting (habitualmente 0.5*Lin) y
    # dimensionaba el centro por debajo de su requisito real.
    interior_zone = next(
        (z for z in valid_zones
         if 'interior' in str(z.get('zone_type') or z.get('type') or '').lower()),
        None,
    )
    L_interior = (
        float(interior_zone.get('L_min_required', Lin_cie))
        if interior_zone is not None
        else (Lin_cie if Lin_cie > 0 else min(
            float(z.get('L_min_required', 0)) for z in valid_zones
        ))
    )

    # ── Fase 1: Optimizar interior ─────────────────────────────────────────
    phase_started = time.perf_counter()
    if d_fixed is not None:
        # Modo retrofit: d fijo, optimizar (optica, tilt, I) para L_int
        from modules.tunnel.optimizer import optimize_single_luminaire as _opt_single
        int_res = _opt_single(
            L_req=L_interior, d=d_fixed, h=h, w=w,
            U0_obj=U0_obj, Ul_obj=Ul_obj, I_max_mA=I_max_mA, cct=cct,
            rtable=rtable, mf=mf, arrangement=arrangement,
            I_min_pct=I_min_pct, tilt_grid=tilt_grid,
            wall_offset=wall_offset,
        )
        d_interior  = d_fixed
        int_optic   = int_res['optic']
        int_tilt    = int_res['tilt_deg']
        int_model   = int_res['model']
        int_mA      = int_res['mA']
        int_lm      = int_res['lm']
        int_W       = int_res['W']
        int_U0      = int_res['U0']
        int_Ul      = 0.0  # en retrofit no se garantiza Ul a priori
        int_L_est   = int_res['L_est']
        if int_res.get('warning'):
            warnings_out.append(f"🔴 INTERIOR (retrofit d={d_fixed:.1f}m): {int_res['warning']}")
    else:
        base_d_min = D_MIN
        if optimization_goal == 'min_power':
            base_d_min = max(
                base_d_min,
                float(params.get('_power_base_d_min_m', 0.0) or 0.0),
            )
            base_d_min = min(
                25.0,
                math.ceil(base_d_min / spacing_quantum - 1e-9)
                * spacing_quantum,
            )
        int_res = optimize_interior(
            h=h, w=w, L_int=L_interior,
            U0_obj=U0_obj, Ul_obj=Ul_obj,
            I_max_mA=I_max_mA, cct=cct,
            rtable=rtable, mf=mf, arrangement=arrangement,
            I_min_pct=I_min_pct, tilt_grid=tilt_grid,
            d_min=base_d_min, wall_offset=wall_offset,
            optimization_goal=optimization_goal,
            spacing_quantum_m=spacing_quantum,
        )

        # Una fila central única puede no cubrir transversalmente una
        # calzada ancha. Antes se conservaba como salida de emergencia la
        # celda no factible a D_MIN (p.ej. 1 m): el túnel acababa con cientos
        # o miles de luminarias y el cálculo de las escenas se volvía muy
        # lento, sin resolver realmente U0. Cuando el proyecto no está
        # bloqueado, probamos primero la doble fila equivalente. Es una
        # modificación física explícita, trazable y solo se acepta si la
        # celda CIE 140 cumple U0, Ul y flujo.
        raw_auto_topology = params.get('auto_physical_reoptimization', True)
        if isinstance(raw_auto_topology, str):
            raw_auto_topology = raw_auto_topology.strip().lower() not in (
                '0', 'false', 'no', 'off',
            )
        auto_topology = (
            bool(raw_auto_topology)
            and not bool(params.get('_physical_layout_locked', False))
            and arrangement in ('central_single', 'central_offset')
            and not bool(int_res.get('feasible', False))
        )
        topology_trials = []
        if auto_topology:
            for proposed_arrangement in ('central_double', 'bilateral_sym'):
                trial = optimize_interior(
                    h=h, w=w, L_int=L_interior,
                    U0_obj=U0_obj, Ul_obj=Ul_obj,
                    I_max_mA=I_max_mA, cct=cct,
                    rtable=rtable, mf=mf,
                    arrangement=proposed_arrangement,
                    I_min_pct=I_min_pct, tilt_grid=tilt_grid,
                    d_min=base_d_min, wall_offset=wall_offset,
                    optimization_goal=optimization_goal,
                    spacing_quantum_m=spacing_quantum,
                )
                topology_trials.append({
                    'arrangement': proposed_arrangement,
                    'feasible': bool(trial.get('feasible', False)),
                    'spacing_m': float(trial.get('d_opt', 0.0) or 0.0),
                    'U0': float(trial.get('U0', 0.0) or 0.0),
                    'Ul': float(trial.get('Ul', 0.0) or 0.0),
                })
                if trial.get('feasible', False):
                    original_arrangement = arrangement
                    arrangement = proposed_arrangement
                    int_res = trial
                    warnings_out.append(
                        '⚙️ DISPOSICIÓN REOPTIMIZADA: '
                        f'{original_arrangement} → {arrangement}. '
                        'La fila única no alcanzaba U0/Ul; se adopta la '
                        'primera geometría CIE 140 factible.'
                    )
                    break
        performance['topology_reoptimization'] = {
            'enabled': bool(auto_topology),
            'selected_arrangement': arrangement,
            'trials': topology_trials,
        }
        d_interior = int_res['d_opt']
        int_optic  = int_res['optic']
        int_tilt   = int_res['tilt_deg']
        int_model  = int_res['model']
        int_mA     = int_res['mA']
        int_lm     = int_res['lm']
        int_W      = int_res['W']
        int_U0     = int_res['U0']
        int_Ul     = int_res['Ul']
        int_L_est  = int_res['L_est']
        warnings_out.extend(int_res.get('warnings', []))

    performance["base_spacing_m"] = round(float(d_interior), 3)
    performance["stages_s"]["base_cell"] = round(
        time.perf_counter() - phase_started, 4,
    )
    performance["base_cell_candidates"] = int_res.get(
        "candidate_summary", [],
    )
    performance["base_cell_candidate_trace"] = int_res.get(
        "candidate_trace", [],
    )
    performance["counters"]["base_cell_candidates"] = len(
        performance["base_cell_candidate_trace"]
    )

    # ── Fase 2-3: Diseno por zona ──────────────────────────────────────────
    phase_started = time.perf_counter()
    zone_designs: List[ZoneLuminaireDesign] = []
    tr_count = 0

    for z in valid_zones:
        z_type  = str(z.get('zone_type') or z.get('type') or 'interior').lower()
        z_start = float(z.get('s_start', 0))
        z_end   = float(z.get('s_end',   0))
        z_len   = max(0.0, z_end - z_start)
        L_req   = float(z.get('L_min_required', 0))

        if 'transition' in z_type:
            tr_count += 1
        z_name = _zone_label(z_type, tr_count)

        # Aplicar override de tilt si existe
        _tilt_ov = params.get('tilt_overrides', {})

        # Zona sin luminarias
        if z_len <= 0 or L_req <= 0:
            zone_designs.append(ZoneLuminaireDesign(
                zone_type=z_type, zone_name=z_name,
                s_start=z_start, s_end=z_end,
                zone_length=z_len, L_required=L_req, E_required=0,
                model=int_model, pcb=_commercial_name_for(int_model),
                current_mA=int(int_mA), flux_lm=int_lm, power_w=int_W,
                optic=int_optic, d_max_ul=round(d_interior,2),
                d_used=0, n_luminaires=0, L_estimated=0,
                UF=0, power_zone_w=0, flux_zone_lm=0,
                power_density_wm2=0, tilt_deg=int_tilt,
            ))
            continue

        # ── Zona interior ─────────────────────────────────────────────────
        if 'interior' in z_type:
            n_lum    = max(1, math.ceil(z_len / d_interior))
            d_actual = d_interior
            edge_margin = max(0.0, (z_len - (n_lum - 1) * d_actual) / 2.0)
            tilt_use = float(_tilt_ov.get(z_name, int_tilt))
            optic_use = int_optic
            mA_use    = int_mA
            lm_use    = int_lm
            W_use     = int_W
            # Re-estimar L con d_actual real
            L_est = L_from_flux(optic_use, d_actual, h, w, tilt_use,
                                 lm_use, arrangement, rtable, mf, wall_offset=wall_offset)

            pwr_zone  = n_lum * W_use
            flux_zone = n_lum * lm_use
            area      = z_len * w

            int_setpoints = []
            for i in range(n_lum):
                int_setpoints.append({
                    'idx':        i + 1,
                    's':          round(z_start + edge_margin + i * d_actual, 2),
                    'L_req':      round(L_req, 1),
                    'model':      int_model,
                    'optic':      optic_use,
                    'tilt_deg':   tilt_use,
                    'current_mA': round(mA_use, 1),
                    'power_w':    W_use,
                    'flux_lm':    round(lm_use, 0),
                    'target_flux_lm': round(float(int_res.get('phi_lm', lm_use)), 3),
                    'spacing_m':  round(d_actual, 3),
                    'spacing_stage': 0,
                    'U0':         round(int_U0, 4),
                    'L_est':      round(L_est, 1),
                })

            zone_designs.append(ZoneLuminaireDesign(
                zone_type=z_type, zone_name=z_name,
                s_start=z_start, s_end=z_end,
                zone_length=z_len, L_required=L_req,
                E_required=round(L_req / 0.085, 1),
                model=int_model, pcb=_commercial_name_for(int_model),
                current_mA=round(mA_use), flux_lm=round(lm_use,0),
                power_w=round(W_use,1), optic=optic_use,
                d_max_ul=round(d_interior,2), d_used=round(d_actual,2),
                n_luminaires=n_lum, L_estimated=round(L_est,1),
                UF=round(int_U0,4), Ul=round(int_Ul,4),
                power_zone_w=round(pwr_zone,0), flux_zone_lm=round(flux_zone,0),
                power_density_wm2=round(pwr_zone/area if area>0 else 0,3),
                d_max=round(d_actual,2), setpoints=int_setpoints, tilt_deg=tilt_use,
            ))
            continue

        # ── Transicion continua: desde Interior hacia el portal ────────────
        # La cadena mantiene una distancia concreta hasta que ninguna
        # combinacion optica+tilt puede cubrir el siguiente nivel con la
        # variante mayor. Solo entonces baja un escalon instalable.
        if 'transition' in z_type:
            is_b = z_type == 'transition_b'
            direction = -1.0 if is_b else 1.0
            outward_sign = 1.0 if is_b else -1.0
            inner_edge = z_start if is_b else z_end
            _tilt_probe = float(_tilt_ov.get(z_name, -1))
            tilt_candidates = (
                [_tilt_probe] if _tilt_probe >= 0 else tilt_grid
            )

            d_stage = (
                math.floor(d_interior / spacing_quantum + 1e-9)
                * spacing_quantum
            )
            d_stage = max(D_MIN, d_stage)
            stage_idx = 0
            setpoints = []
            previous_s = None
            previous_phi_in_stage = 0.0
            max_attempts = max(
                20, int(math.ceil(z_len / max(D_MIN, 0.3))) + 20,
            )

            for _ in range(max_attempts):
                if previous_s is None:
                    s_candidate = inner_edge + outward_sign * d_stage / 2.0
                else:
                    s_candidate = previous_s + outward_sign * d_stage
                if s_candidate < z_start - 1e-9 or s_candidate > z_end + 1e-9:
                    break

                if not is_b:
                    L_i = cie88_L_transition(
                        s_candidate, z_start, Lth_cie, Lin_cie, speed_kmh,
                    )
                else:
                    L_i = cie88_L_transition(
                        z_end - s_candidate, 0.0,
                        Lth_b_cie, Lin_cie, speed_kmh,
                    )
                L_i = max(float(L_i), Lin_cie)

                geometry = select_geometry_for_spacing(
                    L_req=L_i, d=d_stage, h=h, w=w,
                    U0_obj=U0_obj, Ul_obj=Ul_obj,
                    I_max_mA=I_max_mA, cct=cct,
                    rtable=rtable, mf=mf, arrangement=arrangement,
                    I_min_pct=I_min_pct, tilt_grid=tilt_candidates,
                    wall_offset=wall_offset, direction=direction,
                )

                while geometry is None and d_stage > D_MIN + 1e-9:
                    d_next = max(
                        D_MIN,
                        math.floor(
                            (d_stage - transition_spacing_step)
                            / spacing_quantum + 1e-9
                        ) * spacing_quantum,
                    )
                    if d_next >= d_stage - 1e-9:
                        d_next = max(D_MIN, d_stage - spacing_quantum)
                    d_stage = round(d_next, 3)
                    stage_idx += 1
                    previous_phi_in_stage = 0.0
                    if previous_s is None:
                        s_candidate = inner_edge + outward_sign * d_stage / 2.0
                    else:
                        s_candidate = previous_s + outward_sign * d_stage
                    if s_candidate < z_start - 1e-9 or s_candidate > z_end + 1e-9:
                        break
                    if not is_b:
                        L_i = cie88_L_transition(
                            s_candidate, z_start, Lth_cie, Lin_cie, speed_kmh,
                        )
                    else:
                        L_i = cie88_L_transition(
                            z_end - s_candidate, 0.0,
                            Lth_b_cie, Lin_cie, speed_kmh,
                        )
                    L_i = max(float(L_i), Lin_cie)
                    geometry = select_geometry_for_spacing(
                        L_req=L_i, d=d_stage, h=h, w=w,
                        U0_obj=U0_obj, Ul_obj=Ul_obj,
                        I_max_mA=I_max_mA, cct=cct,
                        rtable=rtable, mf=mf, arrangement=arrangement,
                        I_min_pct=I_min_pct, tilt_grid=tilt_candidates,
                        wall_offset=wall_offset, direction=direction,
                    )

                if s_candidate < z_start - 1e-9 or s_candidate > z_end + 1e-9:
                    break
                if geometry is None:
                    warnings_out.append(
                        f"🔴 {z_name}: L={L_i:.1f} cd/m2 no es alcanzable "
                        f"a d={d_stage:.1f} m con ninguna optica+tilt."
                    )
                    fallback = optimize_single_luminaire(
                        L_req=L_i, d=d_stage, h=h, w=w,
                        U0_obj=U0_obj, Ul_obj=Ul_obj,
                        I_max_mA=I_max_mA, cct=cct,
                        rtable=rtable, mf=mf, arrangement=arrangement,
                        I_min_pct=I_min_pct, tilt_grid=tilt_candidates,
                        wall_offset=wall_offset, direction=direction,
                    )
                    geometry = {
                        'optic': fallback['optic'],
                        'tilt_deg': fallback['tilt_deg'],
                        'phi_lm': fallback['lm'],
                        'U0': fallback['U0'],
                        'Ul': fallback.get('Ul', 0.0),
                    }

                # Dentro de una misma distancia la curva CIE creciente no
                # permite que el flujo continuo retroceda hacia el portal.
                phi_target = max(
                    float(geometry['phi_lm']),
                    previous_phi_in_stage,
                )
                previous_phi_in_stage = phi_target
                sel_i = select_model_for_flux(
                    phi_target, cct, I_max_mA, I_min_pct,
                )
                L_est_i = L_from_flux(
                    geometry['optic'], d_stage, h, w,
                    geometry['tilt_deg'], sel_i['lm'],
                    arrangement, rtable, mf,
                    wall_offset=wall_offset, direction=direction,
                )

                setpoints.append({
                    'idx': len(setpoints) + 1,
                    's': round(s_candidate, 2),
                    'L_req': round(L_i, 3),
                    'model': sel_i['model'],
                    'optic': geometry['optic'],
                    'tilt_deg': geometry['tilt_deg'],
                    'current_mA': round(sel_i['mA'], 1),
                    'power_w': sel_i['W'],
                    'flux_lm': round(sel_i['lm'], 0),
                    'target_flux_lm': round(phi_target, 3),
                    'U0': round(geometry['U0'], 4),
                    'Ul': round(geometry['Ul'], 4),
                    'L_est': round(L_est_i, 3),
                    'spacing_m': round(d_stage, 3),
                    'spacing_stage': stage_idx,
                    'distance_from_interior_m': round(
                        abs(s_candidate - inner_edge), 3,
                    ),
                })
                previous_s = s_candidate

            setpoints.sort(key=lambda sp: float(sp['s']))
            for idx, sp in enumerate(setpoints, start=1):
                sp['idx'] = idx

            if not setpoints:
                warnings_out.append(
                    f"🔴 {z_name}: no se pudo colocar ninguna luminaria."
                )
                continue

            dominant = max(setpoints, key=lambda sp: float(sp['L_req']))
            pwr_zone = sum(float(sp['power_w']) for sp in setpoints)
            flux_zone = sum(float(sp['flux_lm']) for sp in setpoints)
            L_avg = sum(float(sp['L_req']) for sp in setpoints) / len(setpoints)
            L_est_avg = (
                sum(float(sp['L_est']) for sp in setpoints) / len(setpoints)
            )
            area = z_len * w
            min_u0 = min(float(sp['U0']) for sp in setpoints)
            min_ul = min(float(sp['Ul']) for sp in setpoints)
            min_spacing = min(float(sp['spacing_m']) for sp in setpoints)

            zone_designs.append(ZoneLuminaireDesign(
                zone_type=z_type, zone_name=z_name,
                s_start=z_start, s_end=z_end,
                zone_length=z_len, L_required=round(L_avg, 3),
                E_required=round(L_avg / 0.085, 1),
                model=dominant['model'],
                pcb=_commercial_name_for(dominant['model']),
                current_mA=round(dominant['current_mA']),
                flux_lm=round(dominant['flux_lm'], 0),
                power_w=round(dominant['power_w'], 1),
                optic=dominant['optic'],
                d_max_ul=round(d_interior, 2),
                d_used=round(min_spacing, 2),
                n_luminaires=len(setpoints),
                L_estimated=round(L_est_avg, 3),
                UF=round(min_u0, 4), Ul=round(min_ul, 4),
                power_zone_w=round(pwr_zone, 1),
                flux_zone_lm=round(flux_zone, 0),
                power_density_wm2=round(
                    pwr_zone / area if area > 0 else 0, 3,
                ),
                d_max=round(d_interior, 2),
                setpoints=setpoints,
                tilt_deg=dominant['tilt_deg'],
            ))
            continue


        # ── Zona umbral / salida / acceso (uniforme) ─────────────────────
        # threshold_b = trafico entrando por el portal B (viaja en -x) -> el
        # observador CIE 140 60 m "por delante" tambien va en -x. access/exit/
        # threshold(A) son trafico A->B, direccion +1 normal.
        zone_direction = -1.0 if z_type == 'threshold_b' else 1.0
        tilt_use = float(_tilt_ov.get(z_name, -1))
        _tilt_grid_zone = [tilt_use] if tilt_use >= 0 else tilt_grid
        zone_spacing_cap = d_interior
        if z_type in ('threshold', 'threshold_b'):
            raw_cap = threshold_spacing_caps.get(
                z_name, threshold_spacing_caps.get('*'),
            )
            try:
                requested_cap = float(raw_cap)
            except (TypeError, ValueError):
                requested_cap = 0.0
            if requested_cap > 0.0:
                zone_spacing_cap = max(
                    D_MIN, min(d_interior, requested_cap),
                )
                if zone_spacing_cap < d_interior - 1e-9:
                    warnings_out.append(
                        f"{z_name}: interdistancia limitada a "
                        f"{zone_spacing_cap:.1f} m por cierre CIE 140 "
                        "multiescena."
                    )
        tandem_overrides = params.get('tandem_overrides', {}) or {}
        tandem_ov_zone   = tandem_overrides.get(z_name)   # True/False/None

        use_tandem    = False
        tandem_offset = 0.0

        def _zone_unit_count(zr, is_tandem):
            """Numero de luminarias fisicas de la zona."""
            if not zr or not zr.get('feasible'):
                return None
            n_ph  = 2 if is_tandem else 1
            n_pos = max(1, math.ceil(z_len / zr['d']))
            return n_pos * n_ph

        # ── Busqueda real de d que satisface U0/Ul Y flujo para L_req ──────
        zres = None
        if tandem_ov_zone is not True:
            zres = find_dmax_for_zone(
                L_req=L_req, h=h, w=w, U0_obj=U0_obj, Ul_obj=Ul_obj,
                I_max_mA=I_max_mA, cct=cct, rtable=rtable, mf=mf,
                arrangement=arrangement, I_min_pct=I_min_pct,
                tilt_grid=_tilt_grid_zone, d_min=D_MIN, d_max_hard=zone_spacing_cap,
                wall_offset=wall_offset, tandem=False, direction=zone_direction,
            )
            # Ademas de "individual infactible", tambien merece la pena comprobar
            # tandem cuando individual SI es factible pero a una d muy comprimida
            # respecto de la d optima de calidad — ahi el individual puede ganar
            # "tecnicamente" siendo en realidad peor en potencia Y en numero de
            # luminarias que un tandem a la d de calidad (ver hallazgo real:
            # individual d=4.62m/31 luminarias/20.7kW vs tandem d=15m/20
            # luminarias/12.3kW para el mismo L_req).
            zres_comprimido = zres['feasible'] and zres['d'] < 0.7 * d_interior
            if (not zres['feasible'] or zres_comprimido) and tandem_ov_zone is None:
                zres_t = find_dmax_for_zone(
                    L_req=L_req, h=h, w=w, U0_obj=U0_obj, Ul_obj=Ul_obj,
                    I_max_mA=I_max_mA, cct=cct, rtable=rtable, mf=mf,
                    arrangement=arrangement, I_min_pct=I_min_pct,
                    tilt_grid=_tilt_grid_zone, d_min=D_MIN, d_max_hard=zone_spacing_cap,
                    wall_offset=wall_offset, tandem=True, direction=zone_direction,
                )
                if not zres['feasible']:
                    if zres_t['feasible']:
                        use_tandem = True
                        zres = zres_t
                        warnings_out.append(
                            f'{z_name}: TÁNDEM AUTOMÁTICO — L_req={L_req:.0f} cd/m2 no alcanzable '
                            f'individual con U0>={U0_obj}/Ul>={Ul_obj} — espaciado {zres["d"]:.1f} m'
                        )
                    else:
                        # Infactible incluso en tándem — pero el par entrega ~2x el flujo
                        # de una sola luminaria a igual d, así que sigue siendo la mejor
                        # opción disponible (nunca peor que caer a 1x individual).
                        zres = zres_t
                        use_tandem = True
                else:
                    # Si ambas soluciones cumplen, manda el numero de unidades
                    # fisicas. A igualdad se conserva la individual.
                    count_i = _zone_unit_count(zres, False)
                    count_t = _zone_unit_count(zres_t, True)
                    d_ind = zres['d']
                    if count_t is not None and count_t < count_i:
                        warnings_out.append(
                            f'{z_name}: TÁNDEM AUTOMÁTICO — individual factible pero comprimido a '
                            f'd={d_ind:.1f} m ({count_i} luminarias); tándem a d={zres_t["d"]:.1f} m '
                            f'necesita {count_t} luminarias — se usa tándem.'
                        )
                        use_tandem = True
                        zres = zres_t

        if tandem_ov_zone is True:
            use_tandem = True
            zres = find_dmax_for_zone(
                L_req=L_req, h=h, w=w, U0_obj=U0_obj, Ul_obj=Ul_obj,
                I_max_mA=I_max_mA, cct=cct, rtable=rtable, mf=mf,
                arrangement=arrangement, I_min_pct=I_min_pct,
                tilt_grid=_tilt_grid_zone, d_min=D_MIN, d_max_hard=zone_spacing_cap,
                wall_offset=wall_offset, tandem=True, direction=zone_direction,
            )
            warnings_out.append(f'{z_name}: TÁNDEM MANUAL activado — espaciado {zres["d"]:.1f} m')

        if zres is None or not zres['feasible']:
            tandem_note = " (con tándem — igualmente insuficiente, es la mejor opción disponible)" if use_tandem else ""
            warnings_out.append(
                f"🔴🔴 {z_name}: {(zres or {}).get('warning', 'INFACTIBLE')} "
                f"— usando d={D_MIN:.1f} m (espaciado minimo){tandem_note}. El resultado puede "
                f"NO cumplir U0_obj={U0_obj}/Ul_obj={Ul_obj}."
            )
            d_use = D_MIN
            L_target_fb = (L_req / 2.0) if use_tandem else L_req
            sel = optimize_single_luminaire(
                L_req=L_target_fb, d=d_use, h=h, w=w,
                U0_obj=U0_obj, Ul_obj=Ul_obj, I_max_mA=I_max_mA, cct=cct,
                rtable=rtable, mf=mf, arrangement=arrangement,
                I_min_pct=I_min_pct, tilt_grid=_tilt_grid_zone,
                wall_offset=wall_offset, direction=zone_direction,
            )
            if sel.get('warning'):
                warnings_out.append(f"🔴🔴 {z_name}: {sel['warning']}")
            tandem_offset = _body_len_for(sel['model']) if use_tandem else 0.0
            _, sel['Ul'] = eval_quality(sel['optic'], d_use, h, w, sel['tilt_deg'],
                                        rtable, mf, arrangement, wall_offset=wall_offset,
                                        direction=zone_direction)
        else:
            d_use = zres['d']
            sel = {
                'model': zres['model'], 'mA': zres['mA'], 'W': zres['W'],
                'lm': zres['lm'], 'optic': zres['optic'], 'tilt_deg': zres['tilt_deg'],
                'U0': zres['U0'], 'Ul': zres['Ul'],
                'L_est': (zres['L_est'] / 2.0) if use_tandem else zres['L_est'],
            }
            tandem_offset = _body_len_for(sel['model']) if use_tandem else 0.0

        d_actual = max(
            D_MIN,
            math.floor(d_use / spacing_quantum + 1e-9) * spacing_quantum,
        )
        n_ph        = 2 if use_tandem else 1
        portal_anchor_offset = tandem_offset / 2.0 if use_tandem else 0.0
        if z_type == 'threshold':
            centers = []
            x_c = z_start + portal_anchor_offset
            while x_c <= z_end + 1e-9:
                centers.append(x_c)
                x_c += d_actual
        elif z_type == 'threshold_b':
            centers = []
            x_c = z_end - portal_anchor_offset
            while x_c >= z_start - 1e-9:
                centers.append(x_c)
                x_c -= d_actual
            centers.sort()
        else:
            n_positions_guess = max(1, math.ceil(z_len / d_actual))
            edge_margin = max(
                0.0,
                (z_len - (n_positions_guess - 1) * d_actual) / 2.0,
            )
            centers = [
                z_start + edge_margin + i * d_actual
                for i in range(n_positions_guess)
            ]
        n_positions = len(centers)
        n_lum       = n_positions * n_ph
        area        = z_len * w
        pwr_zone    = n_lum * sel['W']
        flux_zone   = n_lum * sel['lm']
        L_est       = 2.0 * sel['L_est'] if use_tandem else sel['L_est']

        # Setpoints con posiciones físicas reales — siempre se generan (A/B
        # si es tándem, una única posición por lugar si no) para que la
        # gráfica L(s) tenga datos punto a punto en cualquier zona uniforme.
        unif_setpoints = []

        def _point_requirement(x_pos):
            return required_luminance_for_zone(
                z,
                x_pos,
                Lth=Lth_cie,
                Lth_b=Lth_b_cie,
                Lin=Lin_cie,
                speed_kmh=speed_kmh,
            )

        def _uniform_setpoint(idx, x_pos, **extra):
            point_L_req = _point_requirement(x_pos)
            point_target_flux = phi_for_luminance(
                sel['optic'], d_actual, h, w, sel['tilt_deg'],
                point_L_req / n_ph, arrangement, rtable, mf,
                wall_offset=wall_offset, direction=zone_direction,
            )
            point_selection = select_model_for_flux(
                point_target_flux, cct, I_max_mA, I_min_pct,
            )
            point_L_est = L_from_flux(
                sel['optic'], d_actual, h, w, sel['tilt_deg'],
                point_selection['lm'], arrangement, rtable, mf,
                wall_offset=wall_offset, direction=zone_direction,
            ) * n_ph
            return {
                "idx": idx,
                "s": round(x_pos, 2),
                "L_req": round(point_L_req, 3),
                "model": point_selection['model'],
                "optic": sel['optic'],
                "tilt_deg": sel['tilt_deg'],
                "current_mA": round(point_selection['mA'], 1),
                "power_w": point_selection['W'],
                "flux_lm": round(point_selection['lm'], 0),
                "target_flux_lm": round(point_target_flux, 3),
                "spacing_m": round(d_actual, 3),
                "spacing_stage": 0,
                "U0": round(sel['U0'], 4),
                "L_est": round(point_L_est, 3),
                **extra,
            }
        for i, x_c in enumerate(centers):
            if use_tandem:
                for idx_t, tag in enumerate(("A", "B")):
                    x_phys = round(x_c + (idx_t * 2 - 1) * tandem_offset / 2, 2)
                    unif_setpoints.append(_uniform_setpoint(
                        i * 2 + idx_t + 1, x_phys, tandem=tag, pair=i,
                    ))
            else:
                unif_setpoints.append(_uniform_setpoint(i + 1, x_c))

        dominant = max(unif_setpoints, key=lambda sp: float(sp['L_req']))
        pwr_zone = sum(float(sp['power_w']) for sp in unif_setpoints)
        flux_zone = sum(float(sp['flux_lm']) for sp in unif_setpoints)
        L_est = sum(float(sp['L_est']) for sp in unif_setpoints) / len(unif_setpoints)

        zone_designs.append(ZoneLuminaireDesign(
            zone_type=z_type, zone_name=z_name,
            s_start=z_start, s_end=z_end,
            zone_length=z_len, L_required=L_req,
            E_required=round(L_req/0.085, 1),
            model=dominant['model'], pcb=_commercial_name_for(dominant['model']),
            current_mA=round(dominant['current_mA']), flux_lm=round(dominant['flux_lm'], 0),
            power_w=round(dominant['power_w'], 1), optic=sel['optic'],
            d_max_ul=round(d_interior,2), d_used=round(d_actual,2),
            n_luminaires=n_lum, L_estimated=round(L_est,1),
            UF=round(sel['U0'],4), Ul=round(sel.get('Ul',0.0),4),
            power_zone_w=round(pwr_zone,0), flux_zone_lm=round(flux_zone,0),
            power_density_wm2=round(pwr_zone/area if area>0 else 0,3),
            d_max=round(d_actual,2), tilt_deg=sel['tilt_deg'],
            setpoints=unif_setpoints,
            n_tandem=2 if use_tandem else 1,
            tandem_offset_m=round(tandem_offset, 2),
        ))

    performance["stages_s"]["zonal_geometry"] = round(
        time.perf_counter() - phase_started, 4,
    )
    performance["counters"]["zonal_luminaires"] = sum(
        len(zone.setpoints or []) for zone in zone_designs
    )

    # ── Arquitectura física multiescenario ─────────────────────────────────
    phase_started = time.perf_counter()
    # La configuración interior se convierte en una capa BASE continua entre
    # bocas. Umbral y transición conservan sus posiciones como refuerzo y el
    # solver global siguiente calcula únicamente el flujo residual necesario.
    layered_architecture = str(
        params.get(
            'control_architecture',
            'permanent_base_plus_portal_reinforcement',
        )
    ) == 'permanent_base_plus_portal_reinforcement'
    daylight_summary = {"enabled": False}
    if layered_architecture:
        zone_designs, layer_messages, layer_scenarios = (
            _build_layered_physical_layout(
            zone_designs,
            tube_length_m=tube_length_m,
            road_width_m=w,
            Lin=Lin_cie,
            L_night=L_night_cie,
            Lth=Lth_cie,
            Lth_b=Lth_b_cie,
            speed_kmh=speed_kmh,
            d_interior=d_interior,
            spacing_quantum=spacing_quantum,
            int_model=int_model,
            int_optic=int_optic,
            int_tilt=int_tilt,
            int_mA=int_mA,
            int_lm=int_lm,
            int_W=int_W,
            int_U0=int_U0,
            int_Ul=int_Ul,
            int_L_est=int_L_est,
            cct=cct,
            I_max_mA=I_max_mA,
            I_min_pct=I_min_pct,
            # El margen de BASE debe ser el mismo margen visible que se usa
            # para el cierre de luminancia; no se admite un 5 % oculto.
            base_design_margin=(
                float(params.get('luminance_margin_pct', 4.0) or 4.0)
                / 100.0
            ),
            adaptation_spacing_override_m=params.get(
                '_scene_reoptimization_adaptation_spacing_m',
            ),
            )
        )
        warnings_out.extend(layer_messages)
        daylight_messages, daylight_summary = (
            _apply_solar_daylight_contribution(
                zone_designs,
                params=params,
                tube_length_m=tube_length_m,
                road_width_m=w,
                Lin=Lin_cie,
                Lth=Lth_cie,
                Lth_b=Lth_b_cie,
                cct=cct,
                I_max_mA=I_max_mA,
                I_min_pct=I_min_pct,
                two_way=(
                    str(params.get(
                        "traffic_direction", "one_way",
                    )).lower() == "two_way"
                ),
            )
        )
        warnings_out.extend(daylight_messages)
        base_messages, base_diagnostics = (
            _close_permanent_base_against_cie140(
                zone_designs,
                road_width_m=w,
                road_surface=surface_key,
                luminaire_params=params,
                Lin=Lin_cie,
                L_night=L_night_cie,
                cct=cct,
                I_max_mA=I_max_mA,
                I_min_pct=I_min_pct,
                margin=(
                    float(params.get('luminance_margin_pct', 4.0) or 4.0)
                    / 100.0
                ),
                scenarios=layer_scenarios,
            )
        )
        warnings_out.extend(base_messages)
        performance["base_cie140_closure"] = base_diagnostics
        warnings_out.extend(_resolve_constructive_position_conflicts(
            zone_designs,
            spacing_quantum=spacing_quantum,
            minimum_separation_m=constructive_min_separation,
        ))
    else:
        layer_scenarios = {}
    performance["stages_s"]["layered_layout"] = round(
        time.perf_counter() - phase_started, 4,
    )
    performance["counters"]["layered_luminaires"] = sum(
        len(zone.setpoints or []) for zone in zone_designs
    )

    # Cerrar primero cualquier deficit de capacidad geometrica en los campos
    # representativos. Esta pasada vectorizada puede añadir posiciones sobre
    # la malla instalable; el solver matricial posterior afina sus flujos y
    # selecciona el modelo-driver mínimo.
    phase_started = time.perf_counter()
    if layered_architecture:
        try:
            closure_messages = _enforce_required_luminance_profile(
                zone_designs,
                h=h, w=w, mf=mf, rtable=rtable, cct=cct,
                I_max_mA=I_max_mA, I_min_pct=I_min_pct,
                arrangement=arrangement, wall_offset=wall_offset,
                tube_length_m=tube_length_m,
                Lth=Lth_cie, Lth_b=Lth_b_cie, Lin=Lin_cie,
                speed_kmh=speed_kmh,
                tolerance=0.0,
                max_iters=16,
                spacing_quantum=spacing_quantum,
                sample_step_m=float(
                    params.get('geometric_closure_sample_step_m', 4.0)
                    or 4.0
                ),
                enforce_portal_edges=bool(
                    params.get('enforce_portal_edge_luminance', True)
                ),
            )
            warnings_out.extend(closure_messages)
            warnings_out.extend(_resolve_constructive_position_conflicts(
                zone_designs,
                spacing_quantum=spacing_quantum,
                minimum_separation_m=constructive_min_separation,
            ))
        except Exception as _closure_err:
            warnings_out.append(
                "Cierre de capacidad geometrica omitido por error: "
                f"{_closure_err}"
            )
    performance["stages_s"]["geometric_closure"] = round(
        time.perf_counter() - phase_started, 4,
    )

    # ── Resolucion global mediante matriz de influencia ────────────────────
    # Geometria/optica/tilt ya estan fijados. Se resuelven ahora todos los
    # flujos continuos de forma acoplada y solo despues se asigna el
    # modelo-driver menor compatible con Imin/Imax.
    phase_started = time.perf_counter()
    sensitivity_fast = bool(params.get('sensitivity_fast', False))
    if sensitivity_fast:
        # U0 y Ul dependen de la geometría y no cambian al regular el flujo.
        # La matriz de sensibilidad prueba varias geometrías: evitar en cada
        # celda el MIP global de flujos mantiene el análisis interactivo. El
        # diseño normal nunca activa este atajo.
        warnings_out.append(
            "Sensibilidad U0/Ul: estimacion geométrica rápida; "
            "el cierre global de flujos se omite solo en la matriz."
        )
    else:
        try:
            from modules.tunnel.influence_optimizer import optimize_layout_fluxes
            matrix_messages = optimize_layout_fluxes(
                zone_designs,
                h=h, w=w, mf=mf, rtable=rtable, cct=cct,
                I_max_mA=I_max_mA, I_min_pct=I_min_pct,
                arrangement=arrangement, wall_offset=wall_offset,
                tube_length_m=tube_length_m,
                Lth=Lth_cie, Lth_b=Lth_b_cie, Lin=Lin_cie,
                speed_kmh=speed_kmh,
                optimization_goal=optimization_goal,
                design_margin=(
                    float(params.get('luminance_margin_pct', 4.0) or 4.0)
                    / 100.0
                ),
                enforce_portal_edges=bool(
                    params.get('enforce_portal_edge_luminance', True)
                ),
                num_lanes=int(params.get('num_lanes', 1) or 1),
                lane_width_m=float(params.get('lane_width_m', w) or w),
                shoulder_left_m=float(params.get('shoulder_left_m', 0.0) or 0.0),
                shoulder_right_m=float(params.get('shoulder_right_m', 0.0) or 0.0),
                sidewalk_left_m=float(params.get('sidewalk_left_m', 0.0) or 0.0),
                sidewalk_right_m=float(params.get('sidewalk_right_m', 0.0) or 0.0),
                sample_step_m=float(
                    params.get('optimizer_sample_step_m', 4.0) or 4.0
                ),
                mip_time_limit_s=float(
                    params.get('optimizer_mip_time_limit_s', 2.0) or 2.0
                ),
            )
            warnings_out.extend(matrix_messages)
        except Exception as _matrix_err:
            warnings_out.append(
                f"🔴 Optimizacion global por matriz omitida por error: {_matrix_err}"
            )
    performance["stages_s"]["influence_solver"] = round(
        time.perf_counter() - phase_started, 4,
    )

    # Restaurar la regla de montaje despues del ajuste continuo: dentro de
    # cada escalon con igual geometria, el flujo no disminuye al acercarse al
    # portal.
    phase_started = time.perf_counter()
    for zd in zone_designs:
        zone_type = str(zd.zone_type or '').lower()
        if 'transition' not in zone_type and 'threshold' not in zone_type:
            continue
        buckets = {}
        for sp in zd.setpoints or []:
            if 'distance_from_interior_m' not in sp:
                sp['distance_from_interior_m'] = round(
                    (
                        abs(float(sp['s']) - float(zd.s_start))
                        if zone_type.endswith('_b')
                        else abs(float(zd.s_end) - float(sp['s']))
                    ),
                    3,
                )
            key = (
                int(sp.get('spacing_stage', 0) or 0),
                round(float(sp.get('spacing_m', zd.d_used) or 0), 3),
                str(sp.get('optic') or zd.optic or ''),
                round(float(sp.get('tilt_deg', zd.tilt_deg) or 0), 2),
            )
            buckets.setdefault(key, []).append(sp)
        for items in buckets.values():
            previous_flux = 0.0
            for sp in sorted(
                items,
                key=lambda item: float(item['distance_from_interior_m']),
            ):
                current_flux = float(sp.get('flux_lm', 0) or 0)
                if current_flux + 1e-6 < previous_flux:
                    selected = select_model_for_flux(
                        previous_flux, cct, I_max_mA, I_min_pct,
                    )
                    sp['model'] = selected['model']
                    sp['current_mA'] = selected['mA']
                    sp['power_w'] = selected['W']
                    sp['flux_lm'] = selected['lm']
                    current_flux = float(selected['lm'])
                previous_flux = current_flux
        if zd.setpoints:
            zd.power_zone_w = round(sum(
                float(sp.get('power_w', 0) or 0) for sp in zd.setpoints
            ), 1)
            zd.flux_zone_lm = round(sum(
                float(sp.get('flux_lm', 0) or 0) for sp in zd.setpoints
            ), 0)
            zd.power_density_wm2 = round(
                zd.power_zone_w / max(zd.zone_length * w, 1e-9), 3,
            )

    if layered_architecture:
        layer_scenarios = _attach_layered_scene_operating_points(
            zone_designs,
            Lth=Lth_cie,
            Lth_b=Lth_b_cie,
            Lin=Lin_cie,
            L_night=L_night_cie,
            speed_kmh=speed_kmh,
            cct=cct,
            I_min_pct=I_min_pct,
            scenarios=layer_scenarios,
            enable_static_floor_shedding=bool(
                params.get("enable_static_floor_shedding", False)
            ),
        )
        if full_control_validation:
            try:
                from modules.tunnel.influence_optimizer import (
                    optimize_layered_scene_fluxes,
                )
                control_messages, control_diagnostics = (
                    optimize_layered_scene_fluxes(
                        zone_designs,
                        h=h,
                        w=w,
                        mf=mf,
                        rtable=rtable,
                        cct=cct,
                        I_min_pct=I_min_pct,
                        I_max_mA=I_max_mA,
                        arrangement=arrangement,
                        wall_offset=wall_offset,
                        tube_length_m=tube_length_m,
                        Lth=Lth_cie,
                        Lth_b=Lth_b_cie,
                        Lin=Lin_cie,
                        speed_kmh=speed_kmh,
                        scenarios=layer_scenarios,
                        # Soleado conserva el papel de dimensionamiento físico,
                        # pero también se regula contra los mismos campos CIE
                        # 140 que el resto de escenas. Así BASE puede crecer
                        # primero hasta Imax cuando falte Lreq en umbral.
                        scene_keys=("sunny", "normal", "overcast", "dusk"),
                        enforce_portal_edges=bool(
                            params.get("enforce_portal_edge_luminance", True)
                        ),
                        design_margin=(
                            float(
                                params.get(
                                    "luminance_margin_pct", 4.0,
                                )
                                or 4.0
                            )
                            / 100.0
                        ),
                        sample_step_m=float(
                            params.get('optimizer_sample_step_m', 4.0)
                            or 4.0
                        ),
                        mip_time_limit_s=float(
                            params.get(
                                'scene_optimizer_mip_time_limit_s', 2.0,
                            ) or 2.0),
                    )
                )
                warnings_out.extend(control_messages)
                layer_scenarios["global_control_optimization"] = (
                    control_diagnostics
                )
            except Exception as _control_err:
                warnings_out.append(
                    "Control multiescenario global omitido por error: "
                    f"{_control_err}"
                )
        else:
            layer_scenarios["control_validation"] = {
                "status": "pending",
                "message": (
                    "Escenas DALI pendientes: ejecutar la fase de control "
                    "para optimizar y verificar normal, nublado, "
                    "crepuscular y noche."
                ),
            }
    performance["stages_s"]["control_setpoints"] = round(
        time.perf_counter() - phase_started, 4,
    )
    performance["counters"]["final_luminaires"] = sum(
        len(zone.setpoints or []) for zone in zone_designs
    )

    # ── Resultado ──────────────────────────────────────────────────────────
    dominant = max(zone_designs, key=lambda zd: zd.L_required) if zone_designs else None
    lum_spec = LuminaireSpec(
        flux_lm           = dominant.flux_lm if dominant else 0,
        power_w           = dominant.power_w if dominant else 0,
        efficiency        = dominant.UF if dominant else 0,
        mounting_height_m = h,
        arrangement       = arrangement,
        maintenance_factor= mf,
        name              = (f"Aphex {dominant.model}/{dominant.pcb} "
                             f"{dominant.current_mA}mA {cct}") if dominant else '',
    ) if dominant else None

    result = TunnelLuminaireResult(
        tube_id           = tube_id,
        luminaire         = lum_spec,
        road_surface_type = surface_key,
        rho_eff           = 0.085,
        road_width_m      = w,
        tube_length_m     = tube_length_m,
        optic             = int_optic,
        cct               = cct,
        I_max_mA          = int(I_max_mA),
        arrangement       = arrangement,
        zones             = zone_designs,
        warnings          = list(set(warnings_out)),
        architecture      = (
            'permanent_base_plus_portal_reinforcement'
            if layered_architecture else 'legacy_zonal'
        ),
        scenarios         = layer_scenarios,
        performance       = performance,
        daylight          = daylight_summary,
    )
    result._compute_totals()
    # Nunca se recupera de forma silenciosa la regulación local de nublado:
    # la misma consignación global que se muestra en la curva es la que se
    # valida abajo con CIE 140. Si falla, pasa al rediseño físico.
    if False:  # Legacy block retained temporarily for backwards readability.
        phase_started = time.perf_counter()
        try:
            from modules.tunnel.photometric_verify import (
                verify_layered_operating_scenario,
            )

            global_overcast = verify_layered_operating_scenario(
                result, params, "overcast", include_ti=False,
            )
            selected_control = "global"
            local_overcast = None
            if not global_overcast.get("compliant"):
                global_operations = [
                    (
                        setpoint,
                        dict(
                            setpoint[
                                "scenario_operating_points"
                            ]["overcast"]
                        ),
                    )
                    for setpoint, _operation
                    in local_overcast_operations
                ]
                for setpoint, operation in local_overcast_operations:
                    setpoint["scenario_operating_points"]["overcast"] = (
                        dict(operation)
                    )
                local_overcast = verify_layered_operating_scenario(
                    result, params, "overcast", include_ti=False,
                )

                def _control_score(verification):
                    if not verification.get("available"):
                        return (-1.0, -1.0)
                    normalized = (
                        float(
                            verification.get(
                                "minimum_L_ratio", 0.0,
                            )
                            or 0.0
                        ),
                        float(
                            verification.get("minimum_U0", 0.0) or 0.0
                        )
                        / max(
                            float(params.get("U0_obj", 0.40) or 0.40),
                            1e-9,
                        ),
                        float(
                            verification.get("minimum_Ul", 0.0) or 0.0
                        )
                        / max(
                            float(params.get("Ul_obj", 0.60) or 0.60),
                            1e-9,
                        ),
                    )
                    return (
                        min(normalized),
                        sum(min(value, 1.0) for value in normalized),
                    )

                if _control_score(global_overcast) > _control_score(
                    local_overcast
                ):
                    for setpoint, operation in global_operations:
                        setpoint[
                            "scenario_operating_points"
                        ]["overcast"] = dict(operation)
                else:
                    selected_control = "local"

            active = 0
            off = 0
            floors = 0
            power_w = 0.0
            flux_lm = 0.0
            for zone in result.zones:
                for setpoint in zone.setpoints or []:
                    operation = setpoint.get(
                        "scenario_operating_points", {},
                    ).get("overcast")
                    if operation is None:
                        continue
                    if operation.get("state") == "off":
                        off += 1
                    else:
                        active += 1
                    floors += int(bool(
                        operation.get("driver_floor", False)
                    ))
                    power_w += float(
                        operation.get("power_w", 0.0) or 0.0
                    )
                    flux_lm += float(
                        operation.get("flux_lm", 0.0) or 0.0
                    )
            result.scenarios.setdefault("overcast", {}).update({
                "active_luminaires": active,
                "off_luminaires": off,
                "driver_floor_luminaires": floors,
                "power_kw": round(power_w / 1000.0, 3),
                "flux_lm": round(flux_lm, 0),
                "selected_control": selected_control,
            })
            result.scenarios.setdefault(
                "global_control_optimization", {},
            ).setdefault("scenes", {}).setdefault(
                "overcast", {},
            )["selected_control"] = selected_control
            if selected_control == "local":
                result.warnings.append(
                    "Escena nublado: se conserva la regulacion local "
                    "porque la alternativa global no mantiene Uo/Ul."
                )
        except Exception as _overcast_selection_err:
            result.warnings.append(
                "Seleccion fotometrica de control nublado omitida: "
                f"{_overcast_selection_err}"
            )
        performance["stages_s"]["overcast_control_selection"] = round(
            time.perf_counter() - phase_started, 4,
        )
    dusk_optimization = (
        result.scenarios.get("global_control_optimization", {})
        .get("scenes", {})
        .get("dusk", {})
    )
    if False and (
        full_control_validation
        and layered_architecture
        and (
            dusk_optimization.get("applied")
            or dusk_optimization.get("reason")
            == "adaptation_layer_active"
        )
    ):
        phase_started = time.perf_counter()
        try:
            repair_messages, repair_diagnostics = (
                _repair_dusk_scene_quality(
                    result,
                    params,
                    cct=cct,
                    I_min_pct=I_min_pct,
                    max_iterations=max(
                        0,
                        int(params.get(
                            'dusk_quality_repair_max_iterations', 1,
                        ) or 0),
                    ),
                    max_candidates_per_iteration=max(
                        1,
                        int(params.get(
                            'dusk_quality_repair_max_candidates', 5,
                        ) or 1),
                    ),
                )
            )
            result.warnings.extend(repair_messages)
            dusk_optimization["quality_repair"] = repair_diagnostics
            if repair_diagnostics.get("reason") == "verification_deficit":
                # Propagate the exact CIE 140 result to the physical fallback.
                # Previously the global matrix could report success and the
                # final dusk failure never reached the layout optimiser.
                dusk_optimization["reason"] = "verification_deficit"
                dusk_optimization["infeasibility_type"] = (
                    repair_diagnostics.get("infeasibility_type")
                )
                dusk_optimization["verification"] = dict(
                    repair_diagnostics.get("final", {})
                )
        except Exception as _dusk_repair_err:
            result.warnings.append(
                "Reparacion fotometrica de crepusculo omitida por error: "
                f"{_dusk_repair_err}"
            )
        performance["stages_s"]["dusk_quality_repair"] = round(
            time.perf_counter() - phase_started, 4,
        )
    # Una vez cerrados los déficits, recortamos únicamente los refuerzos que
    # el perfil CIE 140 real confirme como prescindibles. Así la aproximación
    # de la matriz no puede dejar un exceso visible en la curva publicada.
    if False and full_control_validation and layered_architecture:
        phase_started = time.perf_counter()
        scene_diagnostics = result.scenarios.get(
            "global_control_optimization", {},
        ).get("scenes", {})
        for scene_key in ("sunny", "normal", "overcast", "dusk"):
            diagnostic = scene_diagnostics.get(scene_key)
            if not isinstance(diagnostic, dict) or not diagnostic.get("applied"):
                continue
            try:
                trim_messages, trim_diagnostics = (
                    _trim_scene_to_exact_profile(
                        result, params, scene_key=scene_key, cct=cct,
                        I_min_pct=I_min_pct,
                        max_evaluations=max(
                            1,
                            int(params.get(
                                "scene_exact_trim_max_evaluations", 5,
                            ) or 1),
                        ),
                    )
                )
                result.warnings.extend(trim_messages)
                diagnostic["exact_profile_trim"] = trim_diagnostics
            except Exception as _scene_trim_err:
                result.warnings.append(
                    f"Ajuste CIE 140 de escena {scene_key} omitido: "
                    f"{_scene_trim_err}"
                )
        performance["stages_s"]["scene_exact_trim"] = round(
            time.perf_counter() - phase_started, 4,
        )
    # Los extremos gobiernan la instalacion: Soleado conserva el diseno
    # fisico; Crepuscular comprueba primero los limites OFF/Imin. Solo despues
    # se afinan Normal y Cubierto. Cada paso trabaja con los campos CIE 140
    # completos y cambios individuales de corriente, no con una reduccion
    # comun de flujo.
    if full_control_validation and layered_architecture:
        phase_started = time.perf_counter()
        scene_diagnostics = result.scenarios.setdefault(
            "global_control_optimization", {},
        ).setdefault("scenes", {})
        scene_retry = bool(params.get("_scene_reoptimization_attempt", False))
        for scene_key in ("sunny", "dusk", "normal", "overcast"):
            diagnostic = scene_diagnostics.setdefault(scene_key, {
                "applied": scene_key == "sunny",
                "solver": "exact_cie140_local",
            })
            try:
                exact_messages, exact_diagnostics = (
                    _optimize_scene_currents_exact(
                        result,
                        params,
                        scene_key=scene_key,
                        cct=cct,
                        I_min_pct=I_min_pct,
                        I_max_mA=I_max_mA,
                        max_iterations=max(
                            1,
                            int(params.get(
                                "scene_exact_local_max_iterations",
                                1 if scene_retry else 3,
                            ) or 1),
                        ),
                        max_candidates_per_iteration=max(
                            1,
                            int(params.get(
                                "scene_exact_local_max_candidates",
                                1 if scene_retry else 2,
                            ) or 1),
                        ),
                    )
                )
                result.warnings.extend(exact_messages)
                diagnostic["exact_current_optimization"] = exact_diagnostics
                if exact_diagnostics.get("reason") == "verification_deficit":
                    diagnostic["reason"] = "verification_deficit"
                    diagnostic["infeasibility_type"] = "cie140_quality"
                    diagnostic["verification"] = dict(
                        exact_diagnostics.get("final", {}),
                    )
            except Exception as _scene_current_error:
                result.warnings.append(
                    f"Ajuste individual CIE 140 de {scene_key} omitido: "
                    f"{_scene_current_error}"
                )
        performance["stages_s"]["scene_exact_current_optimization"] = round(
            time.perf_counter() - phase_started, 4,
        )

    # La matriz de influencia es un acelerador para obtener consignas, no la
    # autoridad final. Cerramos todas las escenas contra los campos CIE 140
    # reales (incluidos los bordes si el proyecto los exige) antes de decidir
    # que la instalación puede mantenerse sin modificar geometría.
    if full_control_validation and layered_architecture:
        phase_started = time.perf_counter()
        try:
            from modules.tunnel.photometric_verify import (
                verify_layered_operating_scenario,
            )

            scene_diagnostics = result.scenarios.setdefault(
                "global_control_optimization", {},
            ).setdefault("scenes", {})
            for scene_key in ("sunny", "normal", "overcast", "dusk"):
                diagnostic = scene_diagnostics.get(scene_key)
                if not isinstance(diagnostic, dict):
                    continue
                verification = verify_layered_operating_scenario(
                    result, params, scene_key, include_ti=False,
                )
                diagnostic["exact_verification"] = verification
                diagnostic["verification"] = {
                    key: verification.get(key)
                    for key in (
                        "minimum_L_ratio", "maximum_L_ratio",
                        "minimum_U0", "minimum_Ul",
                        "minimum_wall_ratio", "wall_ratio_required",
                        "worst_field_s_m", "maximum_field_s_m",
                        "compliant",
                    )
                }
                if not verification.get("available") or not verification.get(
                    "compliant"
                ):
                    diagnostic["reason"] = "verification_deficit"
                    diagnostic["infeasibility_type"] = "cie140_quality"
                else:
                    # Una estimación matricial conservadora puede declarar
                    # capacidad insuficiente aunque el campo CIE 140 real
                    # cierre. La autoridad es la verificación exacta: no se
                    # debe lanzar un rediseño físico en ese caso.
                    diagnostic["exact_compliant"] = True
                    diagnostic.pop("reason", None)
                    diagnostic.pop("infeasibility_type", None)
        except Exception as _scene_exact_verification_err:
            result.warnings.append(
                "Verificación CIE 140 final de escenas omitida por error: "
                f"{_scene_exact_verification_err}"
            )
        performance["stages_s"]["scene_exact_verification"] = round(
            time.perf_counter() - phase_started, 4,
        )
    performance["total_s"] = round(
        time.perf_counter() - calculation_started, 4,
    )
    return result


def _bounded_power_base_spacing(
    reference_spacing_m: float,
    max_luminaire_increase_pct: float,
    max_base_spacing_reduction_pct: float,
    spacing_quantum_m: float = 0.5,
) -> float:
    """Lower spacing bound for a user-constrained power optimization."""
    reference_spacing_m = max(0.0, float(reference_spacing_m or 0.0))
    quantum = max(0.1, float(spacing_quantum_m or 0.5))
    if reference_spacing_m <= 0:
        return quantum

    max_increase = max(
        0.0, min(500.0, float(max_luminaire_increase_pct or 0.0))
    )
    max_reduction = max(
        0.0, min(95.0, float(max_base_spacing_reduction_pct or 0.0))
    )
    reduction_floor = reference_spacing_m * (1.0 - max_reduction / 100.0)
    count_floor = reference_spacing_m / (1.0 + max_increase / 100.0)
    raw_floor = min(
        reference_spacing_m,
        max(quantum, reduction_floor, count_floor),
    )
    return round(
        math.ceil(raw_floor / quantum - 1e-9) * quantum,
        3,
    )


def _result_base_spacing(result: TunnelLuminaireResult) -> float:
    """Return the optimizer BASE spacing, with a zonal fallback."""
    performance_spacing = (
        getattr(result, "performance", {}) or {}
    ).get("base_spacing_m")
    if (
        isinstance(performance_spacing, (int, float))
        and performance_spacing > 0
    ):
        return float(performance_spacing)
    spacings = [
        float(zone.d_used)
        for zone in getattr(result, "zones", [])
        if getattr(zone, "control_layer", "") == "permanent"
        and float(getattr(zone, "d_used", 0.0) or 0.0) > 0
    ]
    return max(spacings, default=0.0)


def _scene_control_shortfalls(result: TunnelLuminaireResult) -> list[dict]:
    """Return only the scene failures that cannot be repaired by dimming.

    ``optimize_layered_scene_fluxes`` is the authoritative operation solver:
    it keeps the installed positions, luminaires and optics fixed and varies
    only current/flux.  A failure reported by that solver is therefore the
    precise point at which it is legitimate to redesign the physical layout.
    Keeping this decision here (rather than parsing text warnings in Flask or
    the UI) also makes the behaviour reusable for the API and future control
    topologies.
    """
    scenarios = getattr(result, "scenarios", {}) or {}
    diagnostics = scenarios.get("global_control_optimization", {})
    scene_diagnostics = diagnostics.get("scenes", {}) if isinstance(
        diagnostics, dict,
    ) else {}
    shortfalls: list[dict] = []
    for scene_key, diagnostic in scene_diagnostics.items():
        if not isinstance(diagnostic, dict):
            continue
        reason = str(diagnostic.get("reason", "") or "")
        if reason not in {
            "infeasible",
            "driver_mapping_deficit",
            "verification_deficit",
        }:
            continue
        shortfalls.append({
            "scene": str(scene_key),
            "reason": reason,
            "infeasibility_type": diagnostic.get("infeasibility_type"),
            "capacity_min_target_ratio": diagnostic.get(
                "capacity_min_target_ratio",
            ),
            "min_ratio": diagnostic.get("min_ratio"),
            "verification": diagnostic.get("verification"),
        })
    return shortfalls


def _threshold_targets_for_shortfalls(
    result: TunnelLuminaireResult,
    shortfalls: list[dict],
) -> list[str]:
    """Identifica los umbrales que contienen los campos exactos deficientes."""
    threshold_zones = [
        zone for zone in getattr(result, "zones", []) or []
        if "threshold" in str(
            getattr(zone, "zone_type", "") or ""
        ).lower()
    ]
    targets: list[str] = []
    for shortfall in shortfalls:
        verification = shortfall.get("verification") or {}
        try:
            position = float(verification.get("worst_field_s_m"))
        except (TypeError, ValueError):
            continue
        for zone in threshold_zones:
            if (
                float(getattr(zone, "s_start", 0.0)) - 1e-6
                <= position
                <= float(getattr(zone, "s_end", 0.0)) + 1e-6
            ):
                name = str(getattr(zone, "zone_name", "") or "")
                if name and name not in targets:
                    targets.append(name)
                break
    return targets


def _scene_reoptimization_spacings(
    base_spacing_m: float,
    params: dict,
) -> list[float]:
    """Build progressively denser physical-layout candidates.

    A fixed candidate spacing intentionally makes the second pass redesign
    both longitudinal positions and the APHEX operating point/model.  It is a
    controlled fallback, not a silent local current increase.  The user's
    installation minimum remains a hard bound.
    """
    base = max(0.0, float(base_spacing_m or 0.0))
    if base <= 0.0:
        return []
    quantum = max(0.1, float(params.get("spacing_quantum_m", 0.5) or 0.5))
    configured_min = max(0.3, float(params.get("d_min", 0.3) or 0.3))
    configured_min = math.ceil(configured_min / quantum - 1e-9) * quantum
    max_reduction = max(0.0, min(
        80.0,
        float(params.get(
            "scene_reoptimization_max_spacing_reduction_pct", 46.0,
        ) or 0.0),
    ))
    max_attempts = max(1, min(
        4,
        int(params.get("scene_reoptimization_max_attempts", 3) or 3),
    ))
    floor = max(configured_min, base * (1.0 - max_reduction / 100.0))
    floor = math.ceil(floor / quantum - 1e-9) * quantum
    if floor >= base - 1e-9:
        return []

    candidates: list[float] = []
    for index in range(1, max_attempts + 1):
        fraction = index / max_attempts
        raw = base - (base - floor) * fraction
        # Round down: every retry must actually be denser than the prior one.
        candidate = math.floor(raw / quantum + 1e-9) * quantum
        candidate = max(floor, candidate)
        if candidate < base - 1e-9 and candidate not in candidates:
            candidates.append(round(candidate, 3))
    if floor < base - 1e-9 and round(floor, 3) not in candidates:
        candidates.append(round(floor, 3))
    return candidates


def _layout_snapshot(result: TunnelLuminaireResult) -> dict:
    """Small, serialisable comparison for an automatic physical redesign."""
    result._compute_totals()
    models: dict[str, int] = {}
    for zone in getattr(result, "zones", []) or []:
        for setpoint in getattr(zone, "setpoints", []) or []:
            model = str(setpoint.get("model", getattr(zone, "model", "")) or "")
            if model:
                models[model] = models.get(model, 0) + 1
    return {
        "base_spacing_m": round(_result_base_spacing(result), 3),
        "n_luminaires": int(getattr(result, "total_luminaires", 0) or 0),
        "power_kw": round(float(getattr(result, "total_power_w", 0.0) or 0.0) / 1000.0, 3),
        "models": models,
    }


def _attach_scene_reoptimization_metadata(
    result: TunnelLuminaireResult,
    metadata: dict,
) -> TunnelLuminaireResult:
    performance = dict(getattr(result, "performance", {}) or {})
    performance["scene_physical_reoptimization"] = metadata
    result.performance = performance
    return result


def _refine_selected_scene_controls(
    result: TunnelLuminaireResult,
    params: dict,
) -> TunnelLuminaireResult:
    """Aplica el ajuste CIE 140 completo solo al rediseño elegido.

    Los intentos de geometría se mantienen deliberadamente ligeros para no
    repetir el coste de cuatro escenas por cada alternativa. Una vez elegido
    el primer trazado que resuelve el déficit físico, se recupera aquí el
    refinamiento luminaria a luminaria (incluida la precondición de exceso).
    """
    if (
        str(getattr(result, "architecture", "") or "")
        != "permanent_base_plus_portal_reinforcement"
    ):
        return result
    if str(params.get("calculation_phase", "full") or "full").lower() != "full":
        return result

    refinement_params = dict(params)
    refinement_params.pop("_scene_reoptimization_attempt", None)
    raw_i_min = float(refinement_params.get("I_min_pct", 0.30) or 0.30)
    i_min_pct = raw_i_min / 100.0 if raw_i_min > 1.0 else raw_i_min
    cct = str(refinement_params.get("cct", "4000K") or "4000K")
    i_max_mA = float(refinement_params.get("I_max_mA", 750) or 750)
    started = time.perf_counter()
    diagnostics = result.scenarios.setdefault(
        "global_control_optimization", {},
    ).setdefault("scenes", {})

    for scene_key in ("sunny", "dusk", "normal", "overcast"):
        diagnostic = diagnostics.setdefault(scene_key, {
            "applied": scene_key == "sunny",
            "solver": "exact_cie140_local",
        })
        try:
            messages, exact = _optimize_scene_currents_exact(
                result,
                refinement_params,
                scene_key=scene_key,
                cct=cct,
                I_min_pct=i_min_pct,
                I_max_mA=i_max_mA,
                max_iterations=max(
                    1,
                    int(refinement_params.get(
                        "scene_exact_local_max_iterations", 3,
                    ) or 1),
                ),
                max_candidates_per_iteration=max(
                    1,
                    int(refinement_params.get(
                        "scene_exact_local_max_candidates", 2,
                    ) or 1),
                ),
            )
            result.warnings.extend(messages)
            diagnostic["exact_current_optimization"] = exact
            final = dict(exact.get("final", {}) or {})
            diagnostic["verification"] = {
                key: final.get(key)
                for key in (
                    "minimum_L_ratio", "maximum_L_ratio", "minimum_U0",
                    "minimum_Ul", "minimum_wall_ratio", "worst_field_s_m",
                    "maximum_field_s_m", "compliant",
                )
            }
            if exact.get("reason") == "verification_deficit":
                diagnostic["reason"] = "verification_deficit"
                diagnostic["infeasibility_type"] = "cie140_quality"
            else:
                diagnostic.pop("infeasibility_type", None)
                if exact.get("reason") == "excess_unresolved":
                    diagnostic["reason"] = "excess_unresolved"
                else:
                    diagnostic.pop("reason", None)
        except Exception as exc:
            result.warnings.append(
                f"Refinamiento CIE 140 de {scene_key} omitido: {exc}"
            )

    performance = dict(getattr(result, "performance", {}) or {})
    stages = dict(performance.get("stages_s", {}) or {})
    stages["scene_exact_refinement_after_physical"] = round(
        time.perf_counter() - started, 4,
    )
    performance["stages_s"] = stages
    result.performance = performance
    return result


def _reoptimize_physical_layout_for_scenes(
    baseline: TunnelLuminaireResult,
    *,
    zones_list: list,
    params: dict,
    road_width_m: float,
    tube_length_m: float,
    tube_id: str,
) -> TunnelLuminaireResult:
    """Retry the physical layout only after an immutable-hardware failure.

    The first calculation is always retained if all scenes can be solved by
    current.  When this is not possible, progressively denser layouts are
    rebuilt with the normal APHEX selector, which may move luminaires and
    select different models.  Manual edits and fixed-spacing retrofit designs
    are never replaced automatically.
    """
    shortfalls = _scene_control_shortfalls(baseline)
    baseline_snapshot = _layout_snapshot(baseline)
    metadata = {
        "enabled": bool(params.get("auto_physical_reoptimization", True)),
        "status": "not_needed",
        "trigger_shortfalls": shortfalls,
        "reference": baseline_snapshot,
        "attempts": [],
    }
    if not metadata["enabled"]:
        metadata["status"] = "disabled"
        return _attach_scene_reoptimization_metadata(baseline, metadata)
    if str(params.get("calculation_phase", "full") or "full").lower() != "full":
        metadata["status"] = "deferred"
        metadata["message"] = "La reoptimizacion fisica se ejecuta con el calculo completo de escenas."
        return _attach_scene_reoptimization_metadata(baseline, metadata)
    if bool(params.get("_physical_layout_locked", False)):
        metadata["status"] = "locked_manual"
        metadata["message"] = "Se conserva la geometria porque existen ediciones manuales o un retrofit con paso fijo."
        return _attach_scene_reoptimization_metadata(baseline, metadata)
    if params.get("d_fixed") not in (None, "", 0, "0"):
        metadata["status"] = "locked_fixed_spacing"
        metadata["message"] = "Se conserva la geometria porque el proyecto usa una interdistancia fija."
        return _attach_scene_reoptimization_metadata(baseline, metadata)
    if not shortfalls:
        return _attach_scene_reoptimization_metadata(baseline, metadata)

    max_attempts = max(
        1, min(
            4,
            int(params.get("scene_reoptimization_max_attempts", 3) or 3),
        ),
    )
    attempts_remaining = max_attempts

    # Si el campo exacto que falla esta en Umbral, no se comprime todo el
    # tunel: se prueba primero una nueva interdistancia solo en ese portal.
    # El propio selector APHEX vuelve a elegir optica/modelo para el limite de
    # paso solicitado, por lo que esta alternativa puede resolver capacidad y
    # uniformidad sin modificar el Interior ni el otro portal.
    threshold_targets = _threshold_targets_for_shortfalls(
        baseline, shortfalls,
    )
    if threshold_targets and attempts_remaining > 0:
        target_zones = [
            zone for zone in getattr(baseline, "zones", []) or []
            if str(getattr(zone, "zone_name", "") or "")
            in threshold_targets
        ]
        threshold_reference = min(
            (
                float(getattr(zone, "d_used", 0.0) or 0.0)
                for zone in target_zones
                if float(getattr(zone, "d_used", 0.0) or 0.0) > 0.0
            ),
            default=0.0,
        )
        threshold_budget = max(
            1 if attempts_remaining == 1 else 0,
            attempts_remaining - 1,
        )
        threshold_candidates = _scene_reoptimization_spacings(
            threshold_reference, params,
        )[:threshold_budget]
        if threshold_candidates:
            metadata["targeted_thresholds"] = threshold_targets
            metadata["targeted_reference_spacing_m"] = round(
                threshold_reference, 3,
            )
        for candidate_spacing in threshold_candidates:
            retry_params = dict(params)
            retry_params["_scene_reoptimization_threshold_spacing_caps"] = {
                name: candidate_spacing for name in threshold_targets
            }
            retry_params["_scene_reoptimization_attempt"] = True
            candidate = design_aphex_tunnel_optimized(
                zones_list=zones_list,
                params=retry_params,
                road_width_m=road_width_m,
                tube_length_m=tube_length_m,
                tube_id=tube_id,
            )
            candidate_shortfalls = _scene_control_shortfalls(candidate)
            attempt = {
                "scope": "threshold",
                "zones": threshold_targets,
                "spacing_m": candidate_spacing,
                "shortfalls": candidate_shortfalls,
                "layout": _layout_snapshot(candidate),
            }
            metadata["attempts"].append(attempt)
            attempts_remaining -= 1
            if not candidate_shortfalls:
                metadata.update({
                    "status": "applied",
                    "selected_scope": "threshold",
                    "selected_spacing_m": candidate_spacing,
                    "selected": attempt["layout"],
                    "message": (
                        "Se ha redisenado solo el Umbral que contenia el "
                        "campo CIE 140 deficitario."
                    ),
                })
                candidate.warnings.append(
                    "Reoptimizacion fisica aplicada en Umbral: "
                    "posiciones, interdistancia y modelo recalculados para "
                    "la escena gobernante."
                )
                candidate = _refine_selected_scene_controls(candidate, params)
                return _attach_scene_reoptimization_metadata(
                    candidate, metadata,
                )
            if attempts_remaining <= 0:
                break

    # A dusk-only CIE 140 deficit is normally attributable to the dedicated
    # low-flow layer. Densify that layer first: it changes neither the BASE
    # nor sunny/normal/overcast operation, so it is the smallest physical
    # correction that can resolve the threshold.
    adaptation_spacings = [
        float(getattr(zone, "d_used", 0.0) or 0.0)
        for zone in getattr(baseline, "zones", []) or []
        if str(getattr(zone, "control_layer", "") or "") == "adaptation"
        and float(getattr(zone, "d_used", 0.0) or 0.0) > 0.0
    ]
    dusk_only = bool(shortfalls) and all(
        item.get("scene") == "dusk" for item in shortfalls
    )
    if dusk_only and adaptation_spacings:
        adaptation_reference = min(adaptation_spacings)
        # Keep one bounded alternative for a whole-layout retry.  The
        # adaptation layer is the least invasive correction and is always
        # tested first, but a longitudinal-uniformity failure can also depend
        # on the permanent layout.  Without this reserve a default of three
        # attempts could be consumed entirely by the adaptation layer and
        # never try the positions/models of the base installation.
        adaptation_budget = max(
            1 if attempts_remaining == 1 else 0,
            attempts_remaining - 1,
        )
        adaptation_candidates = _scene_reoptimization_spacings(
            adaptation_reference, params,
        )[:adaptation_budget]
        metadata["targeted_layer"] = "adaptation"
        metadata["targeted_reference_spacing_m"] = round(
            adaptation_reference, 3,
        )
        for candidate_spacing in adaptation_candidates:
            retry_params = dict(params)
            retry_params[
                "_scene_reoptimization_adaptation_spacing_m"
            ] = candidate_spacing
            retry_params["_scene_reoptimization_attempt"] = True
            candidate = design_aphex_tunnel_optimized(
                zones_list=zones_list,
                params=retry_params,
                road_width_m=road_width_m,
                tube_length_m=tube_length_m,
                tube_id=tube_id,
            )
            candidate_shortfalls = _scene_control_shortfalls(candidate)
            attempt = {
                "scope": "adaptation",
                "spacing_m": candidate_spacing,
                "shortfalls": candidate_shortfalls,
                "layout": _layout_snapshot(candidate),
            }
            metadata["attempts"].append(attempt)
            attempts_remaining -= 1
            if not candidate_shortfalls:
                metadata.update({
                    "status": "applied",
                    "selected_scope": "adaptation",
                    "selected_spacing_m": candidate_spacing,
                    "selected": attempt["layout"],
                    "message": (
                        "Se ha redisenado la capa de adaptacion crepuscular "
                        "para cerrar la verificacion CIE 140 sin alterar "
                        "las escenas diurnas."
                    ),
                })
                candidate.warnings.append(
                    "Reoptimizacion fisica crepuscular aplicada: se ajustaron "
                    "posiciones, interdistancia y modelos de la capa ADAPTACION."
                )
                candidate = _refine_selected_scene_controls(candidate, params)
                return _attach_scene_reoptimization_metadata(candidate, metadata)
            if attempts_remaining <= 0:
                break

    candidates = _scene_reoptimization_spacings(
        baseline_snapshot["base_spacing_m"], params,
    )[:attempts_remaining]
    # Si el perfil exacto revela una Ul muy por debajo del objetivo, los
    # escalones intermedios solo consumen tiempo y no pueden corregir la
    # periodicidad de la instalación. En ese caso se evalúa directamente la
    # alternativa más densa permitida; el resultado se acepta solo si cierra
    # todas las escenas CIE 140.
    ul_required = max(1e-9, float(params.get("Ul_obj", 0.60) or 0.60))
    ul_ratio = min(
        (
            float((item.get("verification") or {}).get("minimum_Ul", 1.0)
                  or 0.0) / ul_required
            for item in shortfalls
            if isinstance(item.get("verification"), dict)
        ),
        default=1.0,
    )
    # Una vez que el campo exacto CIE 140 ha declarado un déficit, las
    # separaciones intermedias solo repiten el coste de las cuatro escenas y
    # rara vez resuelven una U0/Ul o un Lmin insuficiente. Probamos primero el
    # límite constructivo permitido; después el ajuste de corrientes devuelve
    # el perfil al objetivo. Es la misma decisión que se aplicaba a Ul grave,
    # ampliada a cualquier déficit CIE 140 exacto para evitar cálculos de dos
    # o tres minutos sin ganar capacidad.
    exact_quality_shortfall = any(
        str(item.get("reason", "") or "") == "verification_deficit"
        for item in shortfalls
    )
    if candidates and (ul_ratio < 0.80 or exact_quality_shortfall):
        candidates = [candidates[-1]]
        metadata["selection_strategy"] = (
            "direct_dense_for_exact_cie140_shortfall"
            if exact_quality_shortfall else "direct_dense_for_severe_ul"
        )
    if not candidates:
        metadata["status"] = (
            "unresolved" if metadata["attempts"] else "bounded"
        )
        metadata["message"] = (
            "La capa crepuscular no ha cerrado la verificacion dentro de "
            "las alternativas configuradas."
            if metadata["attempts"] else
            "La interdistancia ya alcanza el minimo configurado; no se puede densificar automaticamente."
        )
        return _attach_scene_reoptimization_metadata(baseline, metadata)

    for candidate_spacing in candidates:
        retry_params = dict(params)
        retry_params["d_fixed"] = candidate_spacing
        retry_params["_scene_reoptimization_attempt"] = True
        candidate = design_aphex_tunnel_optimized(
            zones_list=zones_list,
            params=retry_params,
            road_width_m=road_width_m,
            tube_length_m=tube_length_m,
            tube_id=tube_id,
        )
        candidate_shortfalls = _scene_control_shortfalls(candidate)
        attempt = {
            "scope": "global",
            "spacing_m": candidate_spacing,
            "shortfalls": candidate_shortfalls,
            "layout": _layout_snapshot(candidate),
        }
        metadata["attempts"].append(attempt)
        if not candidate_shortfalls:
            metadata.update({
                "status": "applied",
                "selected_scope": "global",
                "selected_spacing_m": candidate_spacing,
                "selected": attempt["layout"],
                "message": (
                    "Se ha redisenado la instalacion para resolver las escenas "
                    "que no admitian una solucion solo por corriente."
                ),
            })
            candidate.warnings.append(
                "Reoptimizacion fisica multiescena aplicada: se ajustaron "
                "posiciones/interdistancia y modelos APHEX para cerrar las "
                "escenas que no resolvia la regulacion por corriente."
            )
            candidate = _refine_selected_scene_controls(candidate, params)
            return _attach_scene_reoptimization_metadata(candidate, metadata)

    metadata["status"] = "unresolved"
    metadata["message"] = (
        "Ni la regulacion ni las alternativas automaticas de interdistancia "
        "han cerrado todas las escenas; revisar limites de montaje o el proyecto."
    )
    return _attach_scene_reoptimization_metadata(baseline, metadata)


def _select_bounded_power_result(
    reference: TunnelLuminaireResult,
    candidate: TunnelLuminaireResult,
    *,
    max_luminaire_increase_pct: float,
    max_base_spacing_reduction_pct: float,
    min_base_spacing_m: float,
) -> TunnelLuminaireResult:
    """Select the lower-power result only when it respects the user limits."""
    reference._compute_totals()
    candidate._compute_totals()

    max_increase = max(
        0.0, min(500.0, float(max_luminaire_increase_pct or 0.0))
    )
    max_reduction = max(
        0.0, min(95.0, float(max_base_spacing_reduction_pct or 0.0))
    )
    max_luminaires = int(math.floor(
        reference.total_luminaires * (1.0 + max_increase / 100.0)
        + 1e-9
    ))
    candidate_saves_power = (
        candidate.total_power_w < reference.total_power_w - 0.5
    )
    count_ok = candidate.total_luminaires <= max_luminaires
    accepted = bool(candidate_saves_power and count_ok)

    if accepted:
        selected = candidate
        reason = "accepted"
    elif not count_ok:
        selected = reference
        reason = "luminaire_limit"
        selected.warnings.append(
            "La alternativa de minima potencia se descarta: "
            f"{candidate.total_luminaires} luminarias superan el limite "
            f"de {max_luminaires}."
        )
    else:
        selected = reference
        reason = "no_power_saving"
        selected.warnings.append(
            "La alternativa de minima potencia no reduce la potencia "
            "respecto a la solucion de minimas luminarias."
        )

    reference_power_kw = reference.total_power_w / 1000.0
    candidate_power_kw = candidate.total_power_w / 1000.0
    selected_power_kw = selected.total_power_w / 1000.0
    candidate_increase = (
        candidate.total_luminaires - reference.total_luminaires
    )
    candidate_increase_pct = (
        100.0 * candidate_increase / reference.total_luminaires
        if reference.total_luminaires > 0 else 0.0
    )
    selected_saving_kw = reference_power_kw - selected_power_kw
    selected_saving_pct = (
        100.0 * selected_saving_kw / reference_power_kw
        if reference_power_kw > 0 else 0.0
    )
    comparison = {
        "reference": {
            "n_luminaires": reference.total_luminaires,
            "power_kw": round(reference_power_kw, 3),
            "base_spacing_m": round(_result_base_spacing(reference), 3),
        },
        "candidate": {
            "n_luminaires": candidate.total_luminaires,
            "power_kw": round(candidate_power_kw, 3),
            "base_spacing_m": round(_result_base_spacing(candidate), 3),
            "luminaire_increase": candidate_increase,
            "luminaire_increase_pct": round(candidate_increase_pct, 1),
            "power_saving_kw": round(
                reference_power_kw - candidate_power_kw, 3,
            ),
            "power_saving_pct": round(
                (
                    100.0 * (reference_power_kw - candidate_power_kw)
                    / reference_power_kw
                ) if reference_power_kw > 0 else 0.0,
                1,
            ),
        },
        "limits": {
            "max_luminaire_increase_pct": round(max_increase, 1),
            "max_luminaires": max_luminaires,
            "max_base_spacing_reduction_pct": round(max_reduction, 1),
            "min_base_spacing_m": round(float(min_base_spacing_m), 3),
        },
        "decision": {
            "accepted": accepted,
            "selected": (
                "bounded_min_power" if accepted
                else "min_luminaires_reference"
            ),
            "reason": reason,
        },
        "selected_power_saving_kw": round(selected_saving_kw, 3),
        "selected_power_saving_pct": round(selected_saving_pct, 1),
    }
    selected.optimization_comparison = comparison
    return selected


def calculate_quality_sensitivity(
    zones_list: list,
    luminaire_params: dict,
    road_width_m: float,
    tube_length_m: float,
    tube_id: str,
    u0_values: List[float],
    ul_values: List[float],
    reference_layout: dict | None = None,
    max_workers: int = 3,
) -> dict:
    """Calculate the U0/Ul matrix using the same full design as the UI.

    The sensitivity table is actionable: its power and luminaire count must
    come from the selected targets, not from a scaled interior-only estimate.
    Therefore each cell runs ``calculate_luminaire_layout`` with its own U0/Ul
    pair.  If the current layout is supplied, its active cell is copied
    verbatim so the table cannot disagree with the installed design shown
    elsewhere in the application.  A geometric estimate is kept only as a
    guarded fallback when an individual full calculation fails.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from modules.tunnel.optimizer import optimize_interior

    started = time.perf_counter()
    combinations = [
        (row_index, column_index, float(u0), float(ul))
        for row_index, ul in enumerate(ul_values)
        for column_index, u0 in enumerate(u0_values)
    ]
    cells = [None] * len(combinations)

    layout = reference_layout if isinstance(reference_layout, dict) else {}
    layout_zones = layout.get("zones", []) if isinstance(layout, dict) else []
    layout_totals = layout.get("totals", {}) if isinstance(layout, dict) else {}
    reference_zone = next((
        zone for zone in layout_zones
        if str(zone.get("control_layer", "") or "") == "permanent"
    ), None)
    if reference_zone is None:
        reference_zone = next((
            zone for zone in layout_zones
            if "interior" in str(zone.get("zone_type", "") or "").lower()
            or str(zone.get("zone_name", "") or "").upper().startswith("CIN")
        ), None)
    reference_spacing = max(0.5, float(
        (reference_zone or {}).get("d_used", 0.0) or 0.0
    ))
    reference_power_per_lum = max(0.1, float(
        (reference_zone or {}).get("power_w", 0.0) or 0.0
    ))
    reference_n = int(layout_totals.get("n_luminaires", 0) or 0)
    reference_power_kw = float(layout_totals.get("power_kw", 0.0) or 0.0)
    if reference_spacing <= 0.5:
        reference_spacing = max(
            0.5, min(20.0, float(tube_length_m) / max(reference_n, 1)),
        )

    h = float(luminaire_params.get("mounting_height_m", 4.5) or 4.5)
    mf = float(luminaire_params.get("maintenance_factor", DEFAULT_MF) or DEFAULT_MF)
    I_max_mA = float(luminaire_params.get("I_max_mA", 750) or 750)
    raw_min = float(luminaire_params.get("I_min_pct", 0.30) or 0.30)
    I_min_pct = raw_min / 100.0 if raw_min > 1.0 else raw_min
    cct = str(luminaire_params.get("cct", "4000K") or "4000K")
    arrangement = str(luminaire_params.get("arrangement", "central_single") or "central_single")
    wall_offset = float(luminaire_params.get("wall_offset_m", 0.30) or 0.30)
    L_int = max(0.1, float(luminaire_params.get("Lin", 2.0) or 2.0))
    spacing_quantum = max(0.1, float(
        luminaire_params.get("spacing_quantum_m", 0.5) or 0.5
    ))
    d_min = max(0.5, float(luminaire_params.get("d_min", 1.0) or 1.0))
    tilt_max = max(0.0, min(35.0, float(
        luminaire_params.get("tilt_max", 20.0) or 20.0
    )))
    tilt_grid = sorted({0.0, tilt_max / 2.0, tilt_max})

    active_u0 = None
    active_ul = None
    try:
        active_u0 = float(luminaire_params.get("U0_obj"))
        active_ul = float(luminaire_params.get("Ul_obj"))
    except (TypeError, ValueError):
        pass

    def _result_totals(result):
        """Read totals from a result object or its JSON-like representation."""
        payload = {}
        try:
            if isinstance(result, dict):
                payload = result
            elif hasattr(result, "to_dict"):
                payload = result.to_dict() or {}
        except Exception:
            # Some lightweight test/double results have SimpleNamespace zones
            # and intentionally do not implement the full JSON serializer.
            payload = {}
        totals = payload.get("totals", {}) if isinstance(payload, dict) else {}
        zones = payload.get("zones", []) if isinstance(payload, dict) else []
        if not zones:
            zones = getattr(result, "zones", []) or []
        arrangement_result = str(
            payload.get("arrangement", "") if isinstance(payload, dict) else ""
        ) or str(getattr(result, "arrangement", "") or arrangement)
        physical_factor = physical_luminaires_per_setpoint(arrangement_result)
        n_luminaires = totals.get("n_luminaires") if isinstance(totals, dict) else None
        power_kw = totals.get("power_kw") if isinstance(totals, dict) else None
        if n_luminaires in (None, 0):
            n_luminaires = sum(
                int(getattr(zone, "n_luminaires", 0) or 0)
                if not isinstance(zone, dict)
                else int(zone.get("n_luminaires", 0) or 0)
                for zone in zones
            ) * physical_factor
        if power_kw in (None, 0):
            power_kw = sum(
                float(getattr(zone, "power_zone_w", 0.0) or 0.0)
                if not isinstance(zone, dict)
                else float(zone.get("power_zone_w", 0.0) or 0.0)
                for zone in zones
            ) * physical_factor / 1000.0
        zone_for_spacing = next((
            zone for zone in zones
            if (str(zone.get("control_layer", "") or "")
                if isinstance(zone, dict) else
                str(getattr(zone, "control_layer", "") or "")) == "permanent"
        ), None)
        if zone_for_spacing is None:
            zone_for_spacing = next(iter(zones), None)
        if isinstance(zone_for_spacing, dict):
            spacing = zone_for_spacing.get("d_used", 0.0)
            model = zone_for_spacing.get("model")
            optic = zone_for_spacing.get("optic")
        else:
            spacing = getattr(zone_for_spacing, "d_used", 0.0)
            model = getattr(zone_for_spacing, "model", None)
            optic = getattr(zone_for_spacing, "optic", None)
        if isinstance(payload, dict):
            model = (payload.get("luminaire") or {}).get("name") or model
            optic = payload.get("optic") or optic
        return {
            "power_kw": float(power_kw or 0.0),
            "n_luminaires": int(n_luminaires or 0),
            "n_positions": int(
                (totals.get("n_positions", 0) if isinstance(totals, dict) else 0)
                or 0
            ),
            "base_spacing_m": float(spacing or 0.0),
            "model": model,
            "optic": optic,
        }

    reference_totals = _result_totals(layout) if layout else {}
    reference_is_valid = (
        reference_totals.get("n_luminaires", 0) > 0
        and reference_totals.get("power_kw", 0.0) > 0.0
    )

    def _calculate_cell(item):
        row_index, column_index, u0, ul = item
        cell_started = time.perf_counter()

        # Preserve the exact installed design for the selected target pair.
        # This is important when the design has manual edits or a bounded
        # optimisation decision that a fresh estimate would not reproduce.
        if (
            reference_is_valid
            and active_u0 is not None
            and active_ul is not None
            and abs(u0 - active_u0) < 1e-6
            and abs(ul - active_ul) < 1e-6
        ):
            return {
                "row_index": row_index,
                "column_index": column_index,
                "U0": round(u0, 3),
                "Ul": round(ul, 3),
                **reference_totals,
                "power_kw": round(reference_totals["power_kw"], 3),
                "n_luminaires": int(reference_totals["n_luminaires"]),
                "optimization_decision": "current_layout_reference",
                "approximate": False,
                "elapsed_s": round(time.perf_counter() - cell_started, 3),
                "error": None,
            }

        # Normal path: run the same complete APHEX design used by the main
        # luminaires calculation, with the U0/Ul values of this cell.
        full_error = None
        try:
            cell_params = dict(luminaire_params)
            cell_params.update({
                "U0_obj": u0,
                "Ul_obj": ul,
                "calculation_phase": "base",
            })
            full_result = calculate_luminaire_layout(
                zones_list=zones_list,
                luminaire_params=cell_params,
                road_width_m=road_width_m,
                tube_length_m=tube_length_m,
                tube_id=tube_id,
            )
            manual_overrides = luminaire_params.get(
                "manual_luminaire_overrides", {}
            ) or {}
            if manual_overrides:
                apply_manual_luminaire_overrides(
                    full_result, manual_overrides,
                )
            totals = _result_totals(full_result)
            if totals.get("n_luminaires", 0) > 0 and totals.get("power_kw", 0.0) > 0:
                return {
                    "row_index": row_index,
                    "column_index": column_index,
                    "U0": round(u0, 3),
                    "Ul": round(ul, 3),
                    **totals,
                    "power_kw": round(totals["power_kw"], 3),
                    "n_luminaires": int(totals["n_luminaires"]),
                    "optimization_decision": "full_layout",
                    "approximate": False,
                    "elapsed_s": round(time.perf_counter() - cell_started, 3),
                    "error": None,
                }
            full_error = "El diseño completo no devolvió luminarias válidas."
        except Exception as exc:
            full_error = str(exc)

        # Safe fallback for a transient/isolated failure.  It is explicitly
        # marked so the UI never presents this value as an exact calculation.
        interior = optimize_interior(
            h=h,
            w=float(road_width_m),
            L_int=L_int,
            U0_obj=u0,
            Ul_obj=ul,
            I_max_mA=I_max_mA,
            cct=cct,
            rtable=str(luminaire_params.get("rtable", "R2") or "R2"),
            mf=mf,
            arrangement=arrangement,
            I_min_pct=I_min_pct,
            tilt_grid=tilt_grid,
            d_min=d_min,
            d_max_hard=25.0,
            wall_offset=wall_offset,
            optimization_goal=str(
                luminaire_params.get("optimization_goal", "min_luminaires")
                or "min_luminaires"
            ),
            spacing_quantum_m=spacing_quantum,
        )
        spacing = max(0.1, float(interior["d_opt"]))
        density_ratio = reference_spacing / spacing
        power_ratio = float(interior["W"]) / reference_power_per_lum
        if reference_n <= 0:
            reference_count = max(1, int(round(tube_length_m / reference_spacing)))
        else:
            reference_count = reference_n
        if reference_power_kw <= 0:
            reference_power = reference_count * reference_power_per_lum / 1000.0
        else:
            reference_power = reference_power_kw
        return {
            "row_index": row_index,
            "column_index": column_index,
            "U0": round(u0, 3),
            "Ul": round(ul, 3),
            "power_kw": round(reference_power * density_ratio * power_ratio, 3),
            "n_luminaires": max(1, int(round(reference_count * density_ratio))),
            "n_positions": None,
            "base_spacing_m": round(spacing, 3),
            "model": interior.get("model"),
            "optic": interior.get("optic"),
            "optimization_decision": "interior_geometric_estimate",
            "approximate": True,
            "elapsed_s": round(time.perf_counter() - cell_started, 3),
            "error": None,
            "fallback_reason": full_error,
        }

    workers = max(1, min(int(max_workers or 1), len(combinations)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_calculate_cell, item): index
            for index, item in enumerate(combinations)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            row_index, column_index, u0, ul = combinations[index]
            try:
                cells[index] = future.result()
            except Exception as exc:
                cells[index] = {
                    "row_index": row_index,
                    "column_index": column_index,
                    "U0": round(u0, 3),
                    "Ul": round(ul, 3),
                    "power_kw": None,
                    "n_luminaires": None,
                    "n_positions": None,
                    "base_spacing_m": None,
                    "optimization_decision": None,
                    "approximate": True,
                    "elapsed_s": None,
                    "error": str(exc),
                }

    rows = [
        {
            "Ul": round(float(ul), 3),
            "cells": [
                cells[row_index * len(u0_values) + column_index]
                for column_index in range(len(u0_values))
            ],
        }
        for row_index, ul in enumerate(ul_values)
    ]
    return {
        "u0_values": [round(float(value), 3) for value in u0_values],
        "ul_values": [round(float(value), 3) for value in ul_values],
        "rows": rows,
        "n_combinations": len(combinations),
        "n_successful": sum(cell["error"] is None for cell in cells),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "mode": (
            "full_layout"
            if all(not cell.get("approximate") for cell in cells if cell)
            else "full_layout_with_estimates"
        ),
    }


def calculate_luminaire_layout(
    zones_list:       list,
    luminaire_params: dict,
    road_width_m:     float,
    tube_length_m:    float,
    tube_id:          str = "T1",
) -> TunnelLuminaireResult:
    """
    Punto de entrada compatible con el motor existente.
    Si luminaire_params contiene 'I_max_mA' delega a design_aphex_tunnel (APHEX).
    Caso contrario usa flujo/eficiencia directamente (modo legacy).
    """
    params = dict(luminaire_params)
    params.setdefault('road_width_m',  road_width_m)
    params.setdefault('tube_length_m', tube_length_m)

    # ── Modo APHEX optimizado (U0/Ul objetivos via CIE 140 real) ─────────────
    if params.get('I_max_mA') or params.get('cct'):
        try:
            optimization_goal = str(
                params.get('optimization_goal', 'min_luminaires')
                or 'min_luminaires'
            ).lower()
            fixed_spacing = params.get('d_fixed') not in (
                None, '', 0, '0',
            )
            if optimization_goal == 'min_power' and not fixed_spacing:
                max_increase = max(
                    0.0,
                    min(
                        500.0,
                        float(params.get(
                            'max_luminaire_increase_pct', 15.0,
                        ) or 0.0),
                    ),
                )
                max_reduction = max(
                    0.0,
                    min(
                        95.0,
                        float(params.get(
                            'max_base_spacing_reduction_pct', 20.0,
                        ) or 0.0),
                    ),
                )
                reference_params = dict(params)
                reference_params['optimization_goal'] = 'min_luminaires'
                reference = design_aphex_tunnel_optimized(
                    zones_list=zones_list,
                    params=reference_params,
                    road_width_m=road_width_m,
                    tube_length_m=tube_length_m,
                    tube_id=tube_id,
                )
                reference_spacing = _result_base_spacing(reference)
                min_base_spacing = _bounded_power_base_spacing(
                    reference_spacing,
                    max_increase,
                    max_reduction,
                    float(params.get('spacing_quantum_m', 0.5) or 0.5),
                )
                candidate_params = dict(params)
                candidate_params['_power_base_d_min_m'] = min_base_spacing
                candidate = design_aphex_tunnel_optimized(
                    zones_list=zones_list,
                    params=candidate_params,
                    road_width_m=road_width_m,
                    tube_length_m=tube_length_m,
                    tube_id=tube_id,
                )
                baseline = _select_bounded_power_result(
                    reference,
                    candidate,
                    max_luminaire_increase_pct=max_increase,
                    max_base_spacing_reduction_pct=max_reduction,
                    min_base_spacing_m=min_base_spacing,
                )
            else:
                baseline = design_aphex_tunnel_optimized(
                    zones_list    = zones_list,
                    params        = params,
                    road_width_m  = road_width_m,
                    tube_length_m = tube_length_m,
                    tube_id       = tube_id,
                )
            return _reoptimize_physical_layout_for_scenes(
                baseline,
                zones_list=zones_list,
                params=params,
                road_width_m=road_width_m,
                tube_length_m=tube_length_m,
                tube_id=tube_id,
            )
        except Exception as _opt_err:
            import traceback, warnings as _w
            _w.warn(f"Optimizador fallido, usando motor clasico: {_opt_err}")
            return design_aphex_tunnel(
                zones_list    = zones_list,
                params        = params,
                road_width_m  = road_width_m,
                tube_length_m = tube_length_m,
                tube_id       = tube_id,
            )

    # ── Modo legacy (flux_lm / efficiency) ───────────────────────────────────
    warnings: list = []
    flux_lm    = float(params.get('flux_lm',  15000))
    uf         = float(params.get('efficiency', 0.60))
    mf         = float(params.get('maintenance_factor', 0.70))
    h          = float(params.get('mounting_height_m', 5.0))
    w          = road_width_m
    n_rows     = int(params.get('n_rows', 1))
    arrangement = str(params.get('arrangement', 'central_single'))
    rho_eff    = float(params.get('rho_eff', 0.07))
    power_w    = float(params.get('power_w', 200))
    optic      = str(params.get('optic', 'F2MD'))
    cct        = str(params.get('cct', '4000K'))
    I_max_mA   = int(params.get('I_max_mA', 500))

    zone_designs: list = []
    tr_count = 0

    _v_leg = [
        z for z in zones_list
        if str(z.get('zone_type') or z.get('type') or '').lower()
        not in {'exit', 'access', 'parting'}
        and float(z.get("L_min_required",0)) > 0
        and float(z.get("s_end",0)) > float(z.get("s_start",0))
    ]
    L_interior_legacy = min((float(z.get("L_min_required",0)) for z in _v_leg), default=0.0)

    for z in zones_list:
        z_type   = str(z.get('zone_type') or z.get('type') or 'interior').lower()
        z_start  = float(z.get('s_start', 0))
        z_end    = float(z.get('s_end',   0))
        z_length = max(0.0, z_end - z_start)
        L_req    = float(z.get('L_min_required', 0))

        if 'transition' in z_type:
            tr_count += 1
        z_name = _zone_label(z_type, tr_count)

        if z_length <= 0 or L_req <= 0:
            zone_designs.append(ZoneLuminaireDesign(
                zone_type=z_type, zone_name=z_name,
                s_start=z_start, s_end=z_end,
                zone_length=z_length, L_required=L_req, E_required=0,
                model='M', pcb='F2MD', current_mA=I_max_mA,
                flux_lm=flux_lm, power_w=power_w, optic=optic,
                d_max_ul=10.0, d_used=0, n_luminaires=0,
                L_estimated=0, UF=uf, power_zone_w=0,
                flux_zone_lm=0, power_density_wm2=0, d_max=0,
                tilt_deg=0.0,
            ))
            continue

        denom = math.pi * w * L_req
        num   = flux_lm * n_rows * uf * mf * rho_eff
        d_try = max(2.5, min(num / denom if denom > 0 else 10.0, 20.0))
        n_lum    = max(1, math.ceil(z_length / d_try))
        d_actual = z_length / n_lum
        L_est    = _luminance(flux_lm, n_rows, uf, mf, rho_eff, d_actual, w)
        area     = z_length * w
        pwr_zone = n_lum * power_w

        zone_designs.append(ZoneLuminaireDesign(
            zone_type=z_type, zone_name=z_name,
            s_start=z_start, s_end=z_end,
            zone_length=z_length, L_required=L_req, E_required=0,
            model='M', pcb=optic, current_mA=I_max_mA,
            flux_lm=flux_lm, power_w=power_w, optic=optic,
            d_max_ul=round(d_actual, 2), d_used=round(d_actual, 2),
            n_luminaires=n_lum, L_estimated=round(L_est, 1),
            UF=round(uf, 4), power_zone_w=round(pwr_zone, 0),
            flux_zone_lm=round(n_lum * flux_lm, 0),
            power_density_wm2=round(pwr_zone / area if area > 0 else 0, 3),
            d_max=round(d_actual, 2),
            tilt_deg=_zone_tilt_deg(z_type, L_req, L_interior_legacy),
        ))

    lum_spec = None
    if zone_designs:
        dom = max(zone_designs, key=lambda z: z.L_required)
        lum_spec = LuminaireSpec(
            flux_lm=dom.flux_lm, power_w=dom.power_w,
            efficiency=uf, mounting_height_m=h,
            arrangement=arrangement, maintenance_factor=mf,
            name=f"Legacy {optic} {cct}",
        )

    result = TunnelLuminaireResult(
        tube_id=tube_id, luminaire=lum_spec,
        road_surface_type='medium_asphalt', rho_eff=rho_eff,
        road_width_m=w, tube_length_m=tube_length_m,
        optic=optic, cct=cct, I_max_mA=I_max_mA,
        arrangement=arrangement, zones=zone_designs,
        warnings=warnings,
    )
    result._compute_totals()
    return result
