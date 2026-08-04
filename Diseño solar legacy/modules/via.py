#!/usr/bin/env python3
"""Road-based photometric power estimation for Salvi solar luminaires.

CU tables are derived from the real EULUMDAT (.ldt) photometric files in the
CALCULO FOTOMETRICO SALVI project and embedded here as averaged per-optic values.
"""
import os
import glob
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 15

# W/H breakpoints used by the EULUMDAT CU table (standard for all European LDT files)
_CU_W_H = [0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50]

# ─── Salvi lens catalogue ────────────────────────────────────────────────────
# CU tables are averaged from all available LDT files per optic family.
# Each CU[i] = fraction of total luminous flux reaching a road strip of width
# W/H = _CU_W_H[i], measured from directly below the pole (cumulative from 0).
# This matches the EULUMDAT standard CU table definition.
# Extensible: add new lenses here without touching calculation logic.
LENTES_SALVI = {
    'f151': {
        'nombre':      'f151 — Asimétrico estrecho',
        'w_H_max':     0.9,
        'l_H_range':   (3.0, 4.0),
        'descripcion': 'Calles estrechas, distribución asimétrica concentrada',
        # Averaged from 13 LDT files (SIL L48, KRONOS 28/42, CLAP M C42)
        'cu_table': [0.2800, 0.3638, 0.4446, 0.5238, 0.5746,
                     0.6638, 0.7138, 0.7546, 0.8146, 0.8500],
    },
    'f2md': {
        'nombre':      'f2md — Asimétrico medio',
        'w_H_max':     1.5,
        'l_H_range':   (3.0, 4.5),
        'descripcion': 'Vías secundarias y urbanas, distribución estándar',
        # Averaged from 7 LDT files (SIL L48, CLAP M C42)
        'cu_table': [0.2136, 0.3036, 0.3993, 0.4843, 0.5450,
                     0.6393, 0.6921, 0.7464, 0.8043, 0.8429],
    },
    'f2m2': {
        'nombre':      'f2m2 — Gran angular / área',
        'w_H_max':     999,
        'l_H_range':   (3.0, 4.0),
        'descripcion': 'Vías anchas, plazas, zonas peatonales',
        # Averaged from 2 LDT files (CLAP M C42)
        'cu_table': [0.2300, 0.3200, 0.4100, 0.5000, 0.5600,
                     0.6500, 0.7000, 0.7500, 0.8100, 0.8500],
    },
}

# ─── OSM highway tag → default EN 13201 class ───────────────────────────────
_OSM_TO_CLASS = {
    'motorway':       'ME1',
    'motorway_link':  'ME2',
    'trunk':          'ME1',
    'trunk_link':     'ME2',
    'primary':        'ME2',
    'primary_link':   'ME3a',
    'secondary':      'ME3a',
    'secondary_link': 'ME4a',
    'tertiary':       'ME4a',
    'tertiary_link':  'ME5',
    'residential':    'ME5',
    'living_street':  'S2',
    'service':        'S3',
    'pedestrian':     'S1',
    'footway':        'S2',
    'cycleway':       'S3',
    'path':           'S3',
    'unclassified':   'ME5',
    'road':           'ME4a',
}

# ─── EN 13201 class → required average illuminance [lux] ────────────────────
_CLASS_LUX = {
    'ME1': 30.0, 'ME2': 15.0, 'ME3a': 10.0, 'ME3b': 10.0,
    'ME4a': 7.5, 'ME4b': 7.5, 'ME5': 5.0,  'ME6': 3.0,
    'CE0': 50.0, 'CE1': 30.0, 'CE2': 20.0,  'CE3': 15.0,
    'CE4': 10.0, 'CE5': 7.5,
    'S1': 15.0,  'S2': 10.0,  'S3': 7.5,   'S4': 5.0,
    'S5': 3.0,   'S6': 2.0,
}

CLASS_LABELS = {
    'ME1':  'ME1 (30 lux) — Autopista / vía rápida',
    'ME2':  'ME2 (15 lux) — Vía principal',
    'ME3a': 'ME3a (10 lux) — Vía secundaria',
    'ME4a': 'ME4a (7.5 lux) — Vía local',
    'ME5':  'ME5 (5 lux) — Residencial',
    'ME6':  'ME6 (3 lux) — Zona tranquila',
    'CE1':  'CE1 (30 lux) — Conflicto alto',
    'CE2':  'CE2 (20 lux) — Conflicto medio',
    'CE3':  'CE3 (15 lux) — Conflicto bajo',
    'CE4':  'CE4 (10 lux)',
    'CE5':  'CE5 (7.5 lux)',
    'S1':   'S1 (15 lux) — Peatonal / ciclista alta circulación',
    'S2':   'S2 (10 lux) — Peatonal / ciclista media',
    'S3':   'S3 (7.5 lux) — Peatonal / ciclista baja',
    'S4':   'S4 (5 lux)',
    'S5':   'S5 (3 lux)',
    'S6':   'S6 (2 lux)',
}

DISP_LABELS = {
    'unilateral':            'Unilateral',
    'bilateral_tresbolillo': 'Bilateral tresbolillo',
    'bilateral_enfrente':    'Bilateral enfrente',
    'central_mediana':       'Central mediana',
}


# ─── CU interpolation ────────────────────────────────────────────────────────

def interpolate_cu(cu_table: list, w_H: float) -> float:
    """
    Linearly interpolate the EULUMDAT CU table for a given w/H ratio.
    Returns fraction of total luminous flux reaching a road strip of width w = w_H × H.
    """
    if w_H <= _CU_W_H[0]:
        return cu_table[0] * (w_H / _CU_W_H[0]) if w_H > 0 else 0.0
    if w_H >= _CU_W_H[-1]:
        return cu_table[-1]
    for i in range(len(_CU_W_H) - 1):
        if w_H <= _CU_W_H[i + 1]:
            t = (w_H - _CU_W_H[i]) / (_CU_W_H[i + 1] - _CU_W_H[i])
            return cu_table[i] + t * (cu_table[i + 1] - cu_table[i])
    return cu_table[-1]


def cu_from_ldt_files(optica_id: str, ldt_dir: str = None) -> list | None:
    """
    Optionally reload CU table by averaging all LDT files matching the optic ID.
    Returns None if no files found (caller falls back to embedded table).
    ldt_dir: directory containing .ldt files. If None, tries the sibling
             'CALCULO FOTOMETRICO SALVI/assets/Salvi' directory.
    """
    if ldt_dir is None:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ldt_dir = os.path.join(os.path.dirname(here),
                               'CALCULO FOTOMETRICO SALVI', 'assets', 'Salvi')
    pattern = os.path.join(ldt_dir, f'*{optica_id.upper()}*.ldt')
    files = glob.glob(pattern)
    if not files:
        return None

    tables = []
    for path in files:
        try:
            with open(path) as f:
                lines = [ln.rstrip() for ln in f.readlines()]
            n_sets = int(lines[25])
            cu_start = 25 + n_sets * 5 + 2
            tables.append([float(lines[cu_start + i]) for i in range(10)])
        except Exception:
            pass

    if not tables:
        return None
    return [round(sum(t[i] for t in tables) / len(tables), 5) for i in range(10)]


# ─── Core calculation functions ───────────────────────────────────────────────

def clase_desde_osm(highway_tag: str) -> str:
    return _OSM_TO_CLASS.get(highway_tag, 'ME4a')


def iluminancia_desde_clase(clase: str) -> float:
    return _CLASS_LUX.get(clase, 7.5)


def calcular_disposicion(ancho_total: float, altura: float) -> dict:
    """
    Suggest road luminaire arrangement from total illuminated width and pole height.
    Also returns the effective road half-width per luminaire for CU lookup.
    """
    w_H = round(ancho_total / altura, 3) if altura > 0 else 0.0
    if w_H < 0.8:
        disp = 'unilateral'
    elif w_H < 1.3:
        disp = 'bilateral_tresbolillo'
    elif w_H < 1.8:
        disp = 'bilateral_enfrente'
    else:
        disp = 'central_mediana'

    # For unilateral: one luminaire covers the full road width from the pole
    # For bilateral / central: each luminaire covers half the road width
    is_bilateral = disp in ('bilateral_tresbolillo', 'bilateral_enfrente', 'central_mediana')
    w_per_lum = ancho_total / 2 if is_bilateral else ancho_total
    w_H_per_lum = round(w_per_lum / altura, 3) if altura > 0 else w_H / 2

    return {
        'disposicion':    disp,
        'label':          DISP_LABELS[disp],
        'descripcion':    f"{DISP_LABELS[disp]} (w/H={w_H:.2f})",
        'w_H':            w_H,
        'w_H_per_lum':    w_H_per_lum,   # use this for CU lookup
        'w_per_lum':      round(w_per_lum, 2),
        'is_bilateral':   is_bilateral,
    }


def sugerir_optica(w_H: float, clase: str = None) -> list:
    """
    Return ordered list of Salvi lens suggestions for given w/H ratio.
    Pedestrian / CE classes always get f2m2 first.
    """
    peatonal = bool(clase and (clase.startswith('S') or clase.startswith('CE')))

    if peatonal:
        order = ['f2m2', 'f2md', 'f151']
    elif w_H < 0.9:
        order = ['f151', 'f2md', 'f2m2']
    elif w_H < 1.5:
        order = ['f2md', 'f151', 'f2m2']
    else:
        order = ['f2m2', 'f2md', 'f151']

    result = []
    for lid in order:
        ldata = LENTES_SALVI[lid]
        cu_at_wH = round(interpolate_cu(ldata['cu_table'], w_H), 4)
        result.append({
            'id':          lid,
            'nombre':      ldata['nombre'],
            'CU':          cu_at_wH,
            'descripcion': ldata['descripcion'],
            'recomendada': len(result) == 0,
        })
    return result


def calcular_potencia(E_lux: float, ancho_total: float, spacing: float,
                      disposicion: dict | str, optica_id: str,
                      MF: float = 0.75, eta_led: float = 130.0,
                      CU_override: float = None) -> dict:
    """
    Estimate luminaire power using real CU from LDT tables.

    Formula (per luminaire):
        P = E × S_lum / (CU × MF × η_LED)

    Where:
        S_lum = w_per_lum × spacing   (road area served by one luminaire)
        CU    = interpolate_cu(cu_table, w_H_per_lum) or CU_override
        w_per_lum = ancho_total for unilateral, ancho_total/2 for bilateral/central

    Args:
        E_lux       required average illuminance [lux]
        ancho_total total illuminated width [m] (carriageway + margins)
        spacing     pole spacing [m]
        disposicion dict from calcular_disposicion() or string key
        optica_id   lens id ('f151', 'f2md', 'f2m2')
        MF          maintenance factor (default 0.75)
        eta_led     LED luminaire efficacy [lm/W] (default 130)
        CU_override manual CU value (overrides LDT table)

    Returns dict with P_w, S_lum, CU, eta_efectivo, and all inputs.
    """
    if optica_id not in LENTES_SALVI:
        return {'error': f'Unknown optica_id: {optica_id}'}

    ldata = LENTES_SALVI[optica_id]

    # Resolve disposition dict
    if isinstance(disposicion, str):
        from modules.via import calcular_disposicion
        altura_est = ancho_total   # fallback: w_H≈1
        disp = calcular_disposicion(ancho_total, altura_est)
    else:
        disp = disposicion

    w_per_lum     = disp.get('w_per_lum', ancho_total)
    w_H_per_lum   = disp.get('w_H_per_lum', w_per_lum / 8.0)

    # CU from LDT table or override
    if CU_override is not None:
        CU = float(CU_override)
        cu_source = 'manual'
    else:
        CU = round(interpolate_cu(ldata['cu_table'], w_H_per_lum), 4)
        cu_source = 'ldt'

    if CU <= 0 or MF <= 0 or eta_led <= 0:
        return {'error': 'Invalid parameters (CU, MF or eta_led ≤ 0)'}

    S_lum = w_per_lum * spacing
    eta_efectivo = CU * MF * eta_led

    P_w = (E_lux * S_lum) / eta_efectivo

    return {
        'P_w':          round(P_w, 1),
        'S_lum':        round(S_lum, 2),
        'w_per_lum':    round(w_per_lum, 2),
        'CU':           round(CU, 4),
        'cu_source':    cu_source,
        'MF':           MF,
        'eta_led':      eta_led,
        'eta_efectivo': round(eta_efectivo, 2),
        'E_lux':        E_lux,
        'ancho_total':  ancho_total,
        'spacing':      spacing,
        'optica_id':    optica_id,
    }


# --- OSM road query ---

def _parse_width(tags):
    raw = tags.get('width') or tags.get('est_width')
    if raw:
        try:
            return float(str(raw).replace(',', '.').replace(' ', '').replace('m', ''))
        except (ValueError, TypeError):
            pass
    return None


def _parse_lanes(tags):
    raw = tags.get('lanes')
    if raw:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return None


def _default_width(highway, lanes):
    n = lanes if lanes else {
        'motorway': 3, 'trunk': 3, 'primary': 2,
        'secondary': 2, 'tertiary': 1, 'residential': 1,
    }.get(highway, 1)
    return n * 3.5


def fetch_road_osm(lat, lon, radius=50):
    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  way(around:{radius},{lat:.6f},{lon:.6f})[highway~"^(motorway|trunk|primary|secondary|tertiary|residential|living_street|service|pedestrian|footway|cycleway|unclassified|road)$"];
);
out body 1;
"""
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={'data': query},
            timeout=OVERPASS_TIMEOUT + 5,
            headers={'User-Agent': 'SALVISolar/1.0'}
        )
        resp.raise_for_status()
        data = resp.json()
        elements = data.get('elements', [])
        if not elements:
            return {'highway': None, 'name': '', 'width_m': 7.0, 'lanes': None,
                    'lighting_class': 'ME4a', 'E_lux': 7.5, 'osm_id': None,
                    'error': 'No road found within 50m'}

        el = elements[0]
        tags = el.get('tags', {})
        highway = tags.get('highway', 'road')
        lanes = _parse_lanes(tags)
        width = _parse_width(tags) or _default_width(highway, lanes)
        lighting_class = clase_desde_osm(highway)
        E_lux = iluminancia_desde_clase(lighting_class)

        return {
            'highway':        highway,
            'name':           tags.get('name') or tags.get('ref') or '',
            'width_m':        round(width, 1),
            'lanes':          lanes,
            'lighting_class': lighting_class,
            'E_lux':          E_lux,
            'osm_id':         el.get('id'),
            'osm_tags':       tags,
        }

    except Exception as e:
        return {'error': str(e), 'highway': None, 'width_m': 7.0,
                'lighting_class': 'ME4a', 'E_lux': 7.5}


# --- Convenience helpers ---

def clase_labels():
    return dict(CLASS_LABELS)


def lentes_catalog():
    out = {}
    for lid, ldata in LENTES_SALVI.items():
        out[lid] = {
            'id':          lid,
            'nombre':      ldata['nombre'],
            'descripcion': ldata['descripcion'],
            'cu_table':    ldata['cu_table'],
            'cu_w_h':      _CU_W_H,
        }
    return out
