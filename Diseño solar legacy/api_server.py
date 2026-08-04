#!/usr/bin/env python3
"""SALVI Studio Solar — API Backend. Flask. Port 5001."""
import os, json, uuid, traceback
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
PORT = int(os.environ.get('PORT', 5001))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)

# Init DB and import modules
from modules import db as db_module
from modules import geo, consumo, pvgis as pvgis_mod
from modules import bateria, geometrias, productos as prod_mod, optimizador, smartec
from modules import report_docx
from modules import via as via_mod
from modules import shadowmap as shadowmap_mod
from modules import ai_assistant

db_module.init_db()

COUNTRIES = [
    {"code":"ES","name":"España","co2":0.19,"cost":0.20},
    {"code":"FR","name":"Francia","co2":0.05,"cost":0.18},
    {"code":"DE","name":"Alemania","co2":0.38,"cost":0.30},
    {"code":"IT","name":"Italia","co2":0.26,"cost":0.24},
    {"code":"PT","name":"Portugal","co2":0.20,"cost":0.16},
    {"code":"MA","name":"Marruecos","co2":0.65,"cost":0.10},
    {"code":"DZ","name":"Argelia","co2":0.60,"cost":0.04},
    {"code":"TN","name":"Túnez","co2":0.55,"cost":0.08},
    {"code":"SN","name":"Senegal","co2":0.70,"cost":0.12},
    {"code":"EG","name":"Egipto","co2":0.58,"cost":0.05},
    {"code":"NG","name":"Nigeria","co2":0.45,"cost":0.07},
    {"code":"KE","name":"Kenia","co2":0.15,"cost":0.18},
    {"code":"ZA","name":"Sudáfrica","co2":0.87,"cost":0.08},
    {"code":"SA","name":"Arabia Saudí","co2":0.65,"cost":0.05},
    {"code":"IN","name":"India","co2":0.71,"cost":0.07},
    {"code":"BR","name":"Brasil","co2":0.09,"cost":0.11},
    {"code":"MX","name":"México","co2":0.45,"cost":0.10},
]

@app.route('/')
def index():
    html_path = os.path.join(BASE_DIR, 'SALVI Solar.html')
    if os.path.exists(html_path):
        return send_file(html_path)
    return "<h1>SALVI Solar API running on port 5001</h1><p>SALVI Solar.html not found yet.</p>", 200

_ghi_pt_cache   = {}   # (rounded_lat, rounded_lon) -> {monthly:[12], annual:int}
_meteo_pt_cache = {}   # (rounded_lat, rounded_lon) -> {precip:[12], temp:[12], wind:[12]}

def _fetch_monthly_ghi(lat, lon):
    """Fetch monthly GHI (kWh/m2/day) for a point. Returns {monthly, annual} with cache."""
    import requests as req
    key = (round(lat * 2) / 2, round(lon * 2) / 2)
    if key in _ghi_pt_cache:
        return _ghi_pt_cache[key]
    try:
        params = {'lat': round(lat, 4), 'lon': round(lon, 4),
                  'horirrad': 1, 'outputformat': 'json', 'browser': 0}
        r = req.get('https://re.jrc.ec.europa.eu/api/v5_2/MRcalc',
                    params=params, timeout=20)
        r.raise_for_status()
        d = r.json()
        monthly_raw = d.get('outputs', {}).get('monthly', [])
        if isinstance(monthly_raw, dict):
            months = monthly_raw.get('fixed', monthly_raw.get('variable', []))
        else:
            months = monthly_raw if isinstance(monthly_raw, list) else []
        if len(months) >= 12:
            days   = [31,28,31,30,31,30,31,31,30,31,30,31]
            H_KEYS = ['H(h)_d', 'Hh', 'H_d', 'Gh', 'G(h)']
            mo_sum = [0.0]*12; mo_cnt = [0]*12
            for m in months:
                mo = int(m.get('month', 0)) - 1
                if not (0 <= mo < 12): continue
                val = None
                for k in H_KEYS:
                    if k in m: val = float(m[k]); break
                if val is None and 'H(h)_m' in m:
                    val = float(m['H(h)_m']) / days[mo]
                if val is not None:
                    mo_sum[mo] += val; mo_cnt[mo] += 1
            monthly = [round(mo_sum[i]/mo_cnt[i], 2) if mo_cnt[i] else 0.0
                       for i in range(12)]
            annual = round(sum(v * days[i] for i, v in enumerate(monthly)))
            result = {'monthly': monthly, 'annual': annual}
            if annual > 0:
                _ghi_pt_cache[key] = result
            return result
    except Exception:
        pass
    return None

def _fetch_monthly_meteo(lat, lon):
    """Fetch monthly precip/temp/wind for a point via Open-Meteo. Returns {precip,temp,wind} with cache."""
    import requests as req
    key = (round(lat * 2) / 2, round(lon * 2) / 2)
    if key in _meteo_pt_cache:
        return _meteo_pt_cache[key]
    try:
        params = {
            'latitude': round(lat, 4), 'longitude': round(lon, 4),
            'start_date': '2020-01-01', 'end_date': '2023-12-31',
            'daily': 'precipitation_sum,temperature_2m_mean,wind_speed_10m_max',
            'timezone': 'UTC'
        }
        r = req.get('https://archive-api.open-meteo.com/v1/archive',
                    params=params, timeout=20)
        r.raise_for_status()
        d = r.json()
        daily  = d.get('daily', {})
        times  = daily.get('time', [])
        p_vals = daily.get('precipitation_sum', [])
        t_vals = daily.get('temperature_2m_mean', [])
        w_vals = daily.get('wind_speed_10m_max', [])
        if times:
            p_sum = [0.0]*12; t_sum = [0.0]*12; w_sum = [0.0]*12
            p_cnt = [0]*12;   t_cnt = [0]*12;   w_cnt = [0]*12
            for i, ts in enumerate(times):
                mo = int(ts[5:7]) - 1
                if i < len(p_vals) and p_vals[i] is not None:
                    p_sum[mo] += p_vals[i]; p_cnt[mo] += 1
                if i < len(t_vals) and t_vals[i] is not None:
                    t_sum[mo] += t_vals[i]; t_cnt[mo] += 1
                if i < len(w_vals) and w_vals[i] is not None:
                    w_sum[mo] += w_vals[i]; w_cnt[mo] += 1
            result = {
                'precip': [round(p_sum[i]/p_cnt[i], 1) if p_cnt[i] else 0 for i in range(12)],
                'temp':   [round(t_sum[i]/t_cnt[i], 1) if t_cnt[i] else 0 for i in range(12)],
                'wind':   [round(w_sum[i]/w_cnt[i], 1) if w_cnt[i] else 0 for i in range(12)],
            }
            _meteo_pt_cache[key] = result
            return result
    except Exception:
        pass
    return None

@app.route('/api/climate/grid')
def get_climate_grid():
    from concurrent.futures import ThreadPoolExecutor
    lat  = request.args.get('lat',  type=float)
    lon  = request.args.get('lon',  type=float)
    n    = request.args.get('n',    type=int,   default=5)
    dlat = request.args.get('dlat', type=float, default=5.0)
    dlon = request.args.get('dlon', type=float, default=6.0)
    if lat is None or lon is None:
        return jsonify({'error': 'lat and lon required'}), 400
    half = (n - 1) / 2.0
    points = [
        (max(-60, min(75,  lat + (i - half) * dlat)),
         max(-180, min(180, lon + (j - half) * dlon)))
        for i in range(n) for j in range(n)
    ]
    with ThreadPoolExecutor(max_workers=25) as ex:
        ghi_futs   = [ex.submit(_fetch_monthly_ghi,   *p) for p in points]
        meteo_futs = [ex.submit(_fetch_monthly_meteo, *p) for p in points]
        ghi_res   = [f.result() for f in ghi_futs]
        meteo_res = [f.result() for f in meteo_futs]
    grid = [
        {'lat': round(p[0], 4), 'lon': round(p[1], 4),
         'monthly': g['monthly'] if g else None,
         'annual':  g['annual']  if g else None,
         'precip':  m['precip']  if m else None,
         'temp':    m['temp']    if m else None,
         'wind':    m['wind']    if m else None}
        for p, g, m in zip(points, ghi_res, meteo_res)
    ]
    ok_ghi   = sum(1 for r in ghi_res   if r)
    ok_meteo = sum(1 for r in meteo_res if r)
    print(f'[grid] GHI {ok_ghi}/{len(points)} OK  meteo {ok_meteo}/{len(points)} OK')
    return jsonify({'grid': grid, 'n': n, 'dlat': dlat, 'dlon': dlon,
                    'center': {'lat': lat, 'lon': lon}})

@app.route('/fonts/<path:filename>')
def serve_font(filename):
    fonts_dir = os.path.join(BASE_DIR, 'fonts')
    return send_file(os.path.join(fonts_dir, filename))

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/health')
def health():
    products = prod_mod.get_all_products()
    return jsonify({'status': 'ok', 'version': '1.0.0', 'module': 'SALVI Solar',
                    'products_count': len(products)})

@app.route('/api/products')
def get_products():
    return jsonify({'products': prod_mod.get_all_products()})


@app.route('/api/prefetch', methods=['POST'])
def prefetch_pvgis():
    """
    Pre-warm PVGIS SQLite cache for a location + candidate list.
    Fires background threads and returns immediately (non-blocking).
    Call this when user selects a location (step 1) so that by step 6
    all PVGIS data is already cached → simulation completes in ~1-2s.
    """
    import threading
    data = request.get_json() or {}
    try:
        lat = float(data.get('lat', 0))
        lon = float(data.get('lon', 0))
        candidate_ids = data.get('candidates', [])
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid coords'}), 400

    def _do_prefetch():
        try:
            pvgis_db = pvgis_mod.auto_select_pvgis_db(lat, lon)
            # Collect unique geometries for requested candidates
            unique_geos = set()
            for pid in candidate_ids:
                p = prod_mod.get_product(pid)
                if p:
                    geo = p['geometry_type']
                    # Cylinder variants share one canonical fetch
                    canonical = 'cylinder_250' if geo in ('cylinder_250', 'cylinder_300', 'cylinder_350') else geo
                    unique_geos.add(canonical)

            def _fetch_one(geo):
                try:
                    pvgis_mod.fetch_pvgis_geometry(
                        lat, lon, geo, 1000,
                        losses_pct=14, pvgis_db=pvgis_db, road_orientation_deg=0
                    )
                    print(f'[prefetch] ✓ {geo} cached for ({lat:.3f},{lon:.3f})')
                except Exception as exc:
                    print(f'[prefetch] ✗ {geo}: {exc}')

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(4, len(unique_geos) or 1)) as ex:
                list(ex.map(_fetch_one, unique_geos))
        except Exception as e:
            print(f'[prefetch] background error: {e}')

    # Fire and forget — do not block the response
    t = threading.Thread(target=_do_prefetch, daemon=True)
    t.start()

    return jsonify({'status': 'prefetch_started', 'lat': lat, 'lon': lon,
                    'candidates': len(candidate_ids)})

@app.route('/api/costs')
def get_costs():
    lib = db_module.get_cost_library()
    if lib:
        return jsonify({'version': lib['version'], 'costs': lib['data'], 'margin': lib['data'].get('gross_margin', 0.62)})
    return jsonify({'error': 'No cost library found'}), 404

@app.route('/api/countries')
def get_countries():
    return jsonify({'countries': COUNTRIES})

@app.route('/api/projects', methods=['GET', 'POST'])
def projects():
    if request.method == 'GET':
        return jsonify({'projects': db_module.list_projects()})
    data = request.get_json() or {}
    p = db_module.create_project(data)
    return jsonify(p), 201

@app.route('/api/ai/ask', methods=['POST'])
def ai_ask():
    data = request.get_json() or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'Falta la pregunta'}), 400
    result = ai_assistant.ask_question(question, data.get('context', {}), data.get('history', []))
    if 'error' in result:
        return jsonify(result), 502
    return jsonify(result)

@app.route('/api/projects/<pid>', methods=['GET', 'PUT', 'DELETE'])
def project(pid):
    if request.method == 'GET':
        p = db_module.get_project(pid)
        if not p: return jsonify({'error': 'Not found'}), 404
        return jsonify(p)
    elif request.method == 'PUT':
        data = request.get_json() or {}
        p = db_module.update_project(pid, data)
        return jsonify(p)
    else:
        db_module.delete_project(pid)
        return jsonify({'status': 'deleted'})

# Geometries that support modular scaling (multiple units per luminaire).
# These products can be combined ×N: PV power and battery scale proportionally.
# PVGIS data is fetched once for N=1 and multiplied for N>1 (linear scaling is exact).
MODULAR_GEOMETRIES = {'cylinder_250', 'cylinder_300', 'cylinder_350', 'double_vertical_eo'}
MAX_MODULAR_UNITS  = 6

# Geometries where panel Wp + battery Wh are sized by the optimizer (no fixed product specs).
# Algorithm: fetch PVGIS once for 1 kWp; sweep panel sizes; binary-search minimum battery
# for each panel size; select the combination with lowest TCO that meets the reliability target.
SIZING_GEOMETRIES  = {'custom_orientable', 'sil_independent'}

# Geometry loss estimates vs optimal south-facing 30° tilt (F1 V2 §9, loss tree §4.1.1 benchmark)
_GEOMETRY_LOSS_PCT = {
    'sil_horizontal':     6.0,   # almost horizontal, slightly sub-optimal vs 30° south
    'sil_independent':    3.0,   # freely orientable, minor penalty
    'double_vertical_eo': 14.0,  # vertical panels E/O, significant loss vs tilted
    'cylinder_250':       18.0,  # cylindrical, all-direction capture but less per Wp
    'cylinder_300':       18.0,
    'cylinder_350':       18.0,
}
_TEMPERATURE_LOSS_PCT  = 4.0   # standard ~4% temperature effect (part of PVGIS losses=14)
_CONTROLLER_LOSS_PCT   = 3.0   # DC wiring + MPPT conversion (part of PVGIS losses=14)
_BATTERY_ROUNDTRIP_PCT = round((1 - 0.97 * 0.97) * 100, 1)  # charge_eff=0.97, discharge_eff=0.97 → 5.9%
_DEGRADATION_LOSS_PCT  = 2.0   # average annual capacity loss yr1→yr10 (30% total / ~15 avg)


def _monthly_kwh_from_hourly(hourly_wh):
    """Aggregate 8760 hourly Wh values to 12 monthly kWh values."""
    days = [31,28,31,30,31,30,31,31,30,31,30,31]
    monthly, h = [], 0
    for d in days:
        m_hours = d * 24
        monthly.append(round(sum(hourly_wh[h:h+m_hours]) / 1000, 3))
        h += m_hours
    return monthly


def _build_loss_tree(geometry_type: str, soiling_loss_fraction: float) -> dict:
    """Build per-candidate loss tree for UI display (F1 V2 §4.1.1)."""
    geo_loss     = _GEOMETRY_LOSS_PCT.get(geometry_type, 6.0)
    soiling_loss = round(soiling_loss_fraction * 100, 1)
    avail = round(
        100.0 - geo_loss - soiling_loss - _TEMPERATURE_LOSS_PCT
        - _CONTROLLER_LOSS_PCT - _BATTERY_ROUNDTRIP_PCT - _DEGRADATION_LOSS_PCT, 1
    )
    return {
        'pv_theoretical_pct':       100.0,
        'geometry_loss_pct':        geo_loss,
        'soiling_loss_pct':         soiling_loss,
        'temperature_loss_pct':     _TEMPERATURE_LOSS_PCT,
        'controller_loss_pct':      _CONTROLLER_LOSS_PCT,
        'battery_roundtrip_loss_pct': _BATTERY_ROUNDTRIP_PCT,
        'degradation_loss_pct':     _DEGRADATION_LOSS_PCT,
        'energy_available_pct':     max(0.0, avail),
    }


@app.route('/api/simulate', methods=['POST'])
def simulate():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    lat = float(data.get('lat', 41.39))
    lon = float(data.get('lon', 2.17))
    system_power_w = float(data.get('system_power_w', 90))
    periods_def = data.get('night_profile', [
        {'duration_pct': 0.333, 'presence_ratio': 0.5, 'dimming_presence': 1.0, 'dimming_no_presence': 0.3},
        {'duration_pct': 0.333, 'presence_ratio': 0.2, 'dimming_presence': 0.8, 'dimming_no_presence': 0.2},
        {'duration_pct': 0.333, 'presence_ratio': 0.3, 'dimming_presence': 0.8, 'dimming_no_presence': 0.2},
    ])
    margin_on = int(data.get('margin_on_min', -15))
    margin_off = int(data.get('margin_off_min', 15))
    candidate_ids = data.get('candidates', ['SIL_M_60', 'SIL_M_90', 'SIL_L_200', 'SIL_L_260'])
    soiling_env = data.get('soiling_env', 'urbana_normal')
    electricity_cost = float(data.get('electricity_cost', 0.12))
    co2_factor = float(data.get('country_co2_factor', 0.25))
    objective = data.get('optimization_objective', 'min_tco_10y')
    max_failure = float(data.get('max_failure_rate_pct', 2.0))
    aux_wh = float(data.get('aux_consumption_wh', 0))
    year = int(data.get('year', 2024))
    pvgis_db_override = data.get('pvgis_db', None)

    # Local-shading correction (Shadowmap, Phase 1 — single point per project).
    # use_local_shading=False (default) reproduces the exact PVGIS-only pipeline —
    # no behavior change unless the user opts in.
    use_local_shading = bool(data.get('use_local_shading', False))
    shading_mode = data.get('shading_mode', 'PVGIS_SHADOWMAP_POINT')
    shading_environment_context = data.get('shading_environment_context', 'urban_street')
    panel_center_height_m = float(data.get('panel_center_height_m') or 0)
    # No real Shadowmap credentials yet — mock scenario selectable for dev/testing.
    shadowmap_mock_scenario = data.get('shadowmap_mock_scenario', 'urban_canyon')

    try:
        # Step 1: Build annual consumption profile
        consumo_result = consumo.calcular_consumo_anual(
            system_power_w, lat, lon, year, periods_def, aux_wh, margin_on, margin_off
        )
        schedule = consumo_result['schedule']
        consumo_hourly = consumo_result['hourly_wh']
        monthly_consumption_wh = consumo_result['monthly_wh']
        avg_night_wh = consumo_result['avg_night_wh']
        
        # Get cost library
        cost_lib_entry = db_module.get_cost_library()
        costs = cost_lib_entry['data'] if cost_lib_entry else {}

        # ── Step 2a: Parallel PVGIS prefetch — one call per unique geometry at 1 kWp ──
        # PVGIS output is linear with peak power, so fetching at 1 kWp and scaling is exact.
        # This collapses cylinder_250/300/350 (3 products × 12 sectors = 36 calls) into
        # a single 12-sector fetch, and runs all geometries concurrently.
        _pvgis_db_now = pvgis_db_override or pvgis_mod.auto_select_pvgis_db(lat, lon)
        _unique_geos  = set()
        for _pid in candidate_ids:
            _p = prod_mod.get_product(_pid)
            if _p:
                # Map cylinder variants to a single canonical geometry for the prefetch
                geo = _p['geometry_type']
                canonical = 'cylinder_250' if geo in ('cylinder_250','cylinder_300','cylinder_350') else geo
                _unique_geos.add(canonical)

        _pvgis_1kwp = {}   # geometry → pvgis result at 1 kWp (after soiling NOT applied here)

        def _prefetch_geo(geo):
            try:
                return geo, pvgis_mod.fetch_pvgis_geometry(
                    lat, lon, geo, 1000,
                    losses_pct=14, pvgis_db=_pvgis_db_now, road_orientation_deg=0,
                    with_components=use_local_shading
                )
            except Exception as exc:
                print(f'[prefetch] PVGIS error for {geo}: {exc}')
                return geo, None

        from concurrent.futures import ThreadPoolExecutor as _TPE
        with _TPE(max_workers=min(4, len(_unique_geos) or 1)) as ex:
            for geo, res in ex.map(_prefetch_geo, _unique_geos):
                if res:
                    _pvgis_1kwp[geo] = res
                    # Cylinder variants share the canonical result
                    if geo == 'cylinder_250':
                        _pvgis_1kwp['cylinder_300'] = res
                        _pvgis_1kwp['cylinder_350'] = res

        # Pre-build night_map once — shared across ALL battery simulations this request
        # (avoids rebuilding 8760-entry dict ~280 times for custom_orientable sizing loop)
        _night_map = bateria.build_night_map(schedule)

        # ── Local-shading (Shadowmap) setup — built once per request, reused per geometry ──
        # Fase 1: un único punto (lat/lon del proyecto). Sin credenciales reales todavía →
        # proveedor mock (modules/shadowmap.py). Nunca bloquea el cálculo: si algo falla,
        # use_local_shading queda desactivado y el pipeline PVGIS-only sigue igual que hoy.
        _shadow_pattern = None
        if use_local_shading:
            try:
                _shadow_provider = shadowmap_mod.MockShadowmapProvider(shadowmap_mock_scenario)
                _shadow_pattern = shadowmap_mod.build_monthly_shadow_pattern(
                    _shadow_provider, lat, lon, panel_center_height_m
                )
            except Exception as exc:
                print(f'[shadowmap] provider error, falling back to PVGIS-only: {exc}')
                use_local_shading = False

        _shaded_1kwp_cache = {}  # geometry_type → (corrected_hourly_wh_1kwp, shading_stats)

        def _get_shaded_1kwp(geometry_type, soiling_loss):
            """Returns (corrected_hourly_wh, stats) at 1 kWp reference, or (None, stats)
            if PVGIS didn't return components for this geometry (fetch error) or
            shading wasn't requested. All geometries support component-level
            correction (single-plane and multi-plane/sector geometries alike)."""
            if not use_local_shading:
                return None, None
            if geometry_type in _shaded_1kwp_cache:
                return _shaded_1kwp_cache[geometry_type]
            pre = _pvgis_1kwp.get(geometry_type)
            if not pre or 'hourly_direct_wh' not in pre:
                stats = {'status': 'not_supported_geometry', 'shadow_correction_applied': False,
                         'warnings': [f'Corrección de sombra no soportada para {geometry_type} en esta fase.']}
                _shaded_1kwp_cache[geometry_type] = (None, stats)
                return None, stats
            soiling_factor = 1.0 - soiling_loss
            direct    = [v * soiling_factor for v in pre['hourly_direct_wh']]
            diffuse   = [v * soiling_factor for v in pre['hourly_diffuse_wh']]
            reflected = [v * soiling_factor for v in pre['hourly_reflected_wh']]
            corrected, stats = shadowmap_mod.apply_shadow_correction(
                direct, diffuse, reflected, _shadow_pattern, shading_environment_context
            )
            stats = dict(stats, mode=shading_mode, provider='SHADOWMAP',
                         height_mode=('panel_center_height' if panel_center_height_m else 'ground_level_proxy'))
            _shaded_1kwp_cache[geometry_type] = (corrected, stats)
            return corrected, stats

        # Fetch monthly diffuse irradiance fractions (PVGIS MRcalc) — once per location.
        # If the call fails, fall back to a typical 0.45 fraction (mid-latitude default).
        _monthly_diffuse_raw = pvgis_mod.fetch_monthly_diffuse(lat, lon, _pvgis_db_now)
        _diffuse_frac = (
            [m.get('diffuse_fraction', 0.45) for m in _monthly_diffuse_raw]
            if _monthly_diffuse_raw else [0.45] * 12
        )

        # ── Step 2b: Simulate each candidate ─────────────────────────────────
        candidates_results = []

        for pid in candidate_ids:
            product = prod_mod.get_product(pid)
            if not product:
                continue
            try:
                geometry_type = product['geometry_type']
                pvgis_db = _pvgis_db_now

                # ════════════════════════════════════════════════════════════
                # SIZING PATH — custom_orientable: optimize panel + battery
                # ════════════════════════════════════════════════════════════
                if geometry_type in SIZING_GEOMETRIES:
                    soiling_loss   = geometrias.get_soiling_loss(soiling_env, geometry_type)
                    soiling_factor = 1.0 - soiling_loss

                    # Fetch PVGIS for 1 kWp base (optimal south-facing tilt for lat)
                    pvgis_1kwp = pvgis_mod.fetch_pvgis_geometry(
                        lat, lon, geometry_type, 1000,
                        losses_pct=14, pvgis_db=pvgis_db, road_orientation_deg=0,
                        with_components=use_local_shading
                    )
                    _pvgis_1kwp.setdefault(geometry_type, pvgis_1kwp)
                    solar_1kwp_net_base = geometrias.apply_soiling(pvgis_1kwp['hourly_wh'], soiling_loss)

                    # If local shading is active and supported for this geometry, size the
                    # panel/battery against the SHADE-CORRECTED production (doc §26: shading
                    # must feed into dimensioning, not just be reported after the fact).
                    shaded_1kwp, shading_stats = _get_shaded_1kwp(geometry_type, soiling_loss)
                    solar_1kwp_net = shaded_1kwp if shaded_1kwp is not None else solar_1kwp_net_base

                    # Search bounds scaled to project consumption
                    panel_max  = max(2000, int(avg_night_wh * 6))
                    panel_step = max(25, panel_max // 40)   # ~40 candidate panel sizes
                    bat_max    = max(8000, int(avg_night_wh * 12))
                    bat_step   = max(100, bat_max // 80)    # binary search granularity

                    best_cand_data = None   # (panel_wp, bat_wh, cap_quick, tco_quick)
                    best_tco_cost  = float('inf')

                    # ── Numpy batch sweep: all battery sizes for each panel size in one pass ──
                    # Replaces ~280 sequential Python simulations with 40 numpy-vectorized sweeps.
                    # Each sweep evaluates ~80 battery sizes simultaneously via numpy broadcasting.
                    # Skips smartec_protection (conservative: finds minimum battery >= actual need).
                    _bat_candidates = list(range(bat_step, bat_max + bat_step, bat_step))

                    for panel_wp in range(panel_step, panel_max + panel_step, panel_step):
                        scale        = panel_wp / 1000.0
                        solar_hourly = [v * scale for v in solar_1kwp_net]

                        # One vectorized call replaces ~7 binary-search iterations
                        failure_rates = bateria.simular_bateria_batch_numpy(
                            solar_hourly, consumo_hourly, _bat_candidates,
                            prebuilt_night_map=_night_map
                        )

                        # Find minimum viable battery (failure_rates non-increasing with bat size)
                        valid_bat = None
                        for i, rate in enumerate(failure_rates):
                            if rate <= max_failure:
                                valid_bat = float(_bat_candidates[i])
                                break

                        if valid_bat is None:
                            continue  # this panel size can't meet target even at bat_max

                        sp        = {'pv_peak_power_wp': panel_wp, 'battery_nominal_wh': valid_bat, 'weight_kg': 0}
                        cap_quick = optimizador.calcular_capex(sp, costs)
                        tco_quick = optimizador.calcular_tco_10y(
                            cap_quick['cost'], 0, electricity_cost, costs,
                            valid_bat, 0.70, costs.get('gross_margin', 0.62)
                        )
                        if tco_quick['cost'] < best_tco_cost:
                            best_tco_cost = tco_quick['cost']
                            best_cand_data = (panel_wp, valid_bat, cap_quick, tco_quick)

                    if best_cand_data is None:
                        # No configuration meets target — report best attempt at panel_max
                        panel_wp     = panel_max
                        bat_wh       = bat_max
                        warning_no_sol = f"Sin solución con panel hasta {panel_max} Wp + batería {bat_max} Wh"
                    else:
                        panel_wp, bat_wh, cap_quick, tco_quick = best_cand_data
                        warning_no_sol = None

                    # Run full simulation (with smartec + year10) only for the winner
                    solar_hourly = [v * (panel_wp / 1000.0) for v in solar_1kwp_net]
                    br = bateria.simular_bateria_anual(
                        solar_hourly, consumo_hourly, bat_wh,
                        smartec_protection=data.get('smartec_enabled', True),
                        annual_schedule=schedule,
                        prebuilt_night_map=_night_map
                    )
                    if best_cand_data is None:
                        sp  = {'pv_peak_power_wp': panel_wp, 'battery_nominal_wh': bat_wh, 'weight_kg': 0}
                        cap = optimizador.calcular_capex(sp, costs)
                        tco = optimizador.calcular_tco_10y(
                            cap['cost'], 0, electricity_cost, costs,
                            bat_wh, 0.70, costs.get('gross_margin', 0.62)
                        )
                    else:
                        cap, tco = cap_quick, tco_quick
                    bat_new  = br['new']
                    bat_y10  = br['year10']

                    # Comparativa obligatoria PVGIS puro vs. PVGIS+Shadowmap (doc §28): re-simula
                    # el MISMO panel/batería ya elegido con la producción SIN corregir. Solo un
                    # sim extra (no un resweep de 40 tamaños) — coste acotado.
                    shading_comparison = None
                    if shaded_1kwp is not None:
                        solar_hourly_base = [v * (panel_wp / 1000.0) for v in solar_1kwp_net_base]
                        br_base = bateria.simular_bateria_anual(
                            solar_hourly_base, consumo_hourly, bat_wh,
                            smartec_protection=data.get('smartec_enabled', True),
                            annual_schedule=schedule, prebuilt_night_map=_night_map
                        )
                        annual_prod_base_kwh = round(sum(solar_hourly_base) / 1000, 2)
                        annual_prod_corr_kwh = round(sum(solar_hourly) / 1000, 2)
                        shading_comparison = {
                            'base_case': {
                                'label': 'PVGIS puro',
                                'annual_production_kwh': annual_prod_base_kwh,
                                'annual_failure_rate_pct': br_base['new']['annual_failure_rate_pct'],
                            },
                            'corrected_case': {
                                'label': 'PVGIS + Shadowmap',
                                'annual_production_kwh': annual_prod_corr_kwh,
                                'annual_failure_rate_pct': bat_new['annual_failure_rate_pct'],
                            },
                            'monthly_production_base_wh': [round(v * 1000, 0) for v in _monthly_kwh_from_hourly(solar_hourly_base)],
                        }

                    scale              = panel_wp / 1000.0
                    if shaded_1kwp is not None:
                        # solar_hourly already includes soiling + shading — don't re-apply soiling.
                        monthly_prod_net    = _monthly_kwh_from_hourly(solar_hourly)
                        annual_prod_net_kwh = round(sum(solar_hourly) / 1000, 2)
                    else:
                        monthly_prod_net    = [round(v * scale * soiling_factor, 2) for v in pvgis_1kwp['monthly_kwh']]
                        annual_prod_net_kwh = round(pvgis_1kwp['annual_kwh'] * scale * soiling_factor, 2)
                    co2                = optimizador.calcular_co2_evitado(annual_prod_net_kwh, co2_factor, 0, 10)
                    autonomy           = bateria.calcular_autonomia_equivalente(bat_wh, 0.85, 0.15, avg_night_wh)
                    # Rough weight: ~6 kg/100 Wp panel + ~0.5 kg/100 Wh battery
                    weight_est         = round(panel_wp * 0.06 + bat_wh * 0.005)

                    # Retrieve optimal tilt from pvgis geometry result for display
                    opt_tilt = pvgis_1kwp.get('geometry', {}).get('tilt', '–')

                    # Build monthly_data: array of objects with kWh/day + min SOC per month
                    _days_m = [31,28,31,30,31,30,31,31,30,31,30,31]
                    _soc_min_new  = bat_new.get('monthly_soc_min_pct',  bat_new['monthly_soc_avg_pct'])
                    _soc_min_y10  = bat_y10.get('monthly_soc_min_pct',  bat_y10['monthly_soc_avg_pct'])
                    _soc_dusk_new = bat_new.get('monthly_soc_dusk_avg_pct', bat_new['monthly_soc_avg_pct'])
                    _prot_new     = bat_new.get('monthly_protection_nights', [0] * 12)
                    monthly_data_c = []
                    for _mi in range(12):
                        _d = _days_m[_mi]
                        monthly_data_c.append({
                            'production_kwh':  round(monthly_prod_net[_mi] / _d, 3),    # kWh/día
                            'consumption_kwh': round(monthly_consumption_wh[_mi] / 1000 / _d, 3),  # kWh/noche
                            'prod_total_kwh':  round(monthly_prod_net[_mi], 2),
                            'cons_total_kwh':  round(monthly_consumption_wh[_mi] / 1000, 2),
                            'soc_min_pct':     _soc_min_new[_mi],
                            'soc_min_y10':     _soc_min_y10[_mi],
                            'soc_dusk_pct':    _soc_dusk_new[_mi],     # avg SOC at dusk (start of night)
                            'protection_nights': _prot_new[_mi],        # nights Smartec protected battery
                            'diffuse_fraction': _diffuse_frac[_mi],     # fraction of irradiance that is diffuse
                            'failures':        bat_new['monthly_failures'][_mi],
                        })

                    warnings_c = []
                    if warning_no_sol:
                        warnings_c.append(warning_no_sol)
                    if bat_new['annual_failure_rate_pct'] > max_failure:
                        warnings_c.append(f"Fiabilidad limitada: {100 - bat_new['annual_failure_rate_pct']:.1f}%")

                    candidates_results.append({
                        'product_id':   pid,
                        'product_name': f"{product['name']} – {panel_wp} Wp / {bat_wh} Wh",
                        'is_custom_sized': True,
                        'optimal_tilt_deg': opt_tilt,
                        'pv_peak_power_wp':   panel_wp,
                        'battery_nominal_wh': bat_wh,
                        'weight_kg':          weight_est,
                        'geometry_type':      geometry_type,
                        'loss_tree': _build_loss_tree(geometry_type, soiling_loss),
                        'annual_failure_rate_pct':     bat_new['annual_failure_rate_pct'],
                        'annual_failure_rate_pct_y10': bat_y10['annual_failure_rate_pct'],
                        'meets_reliability': bat_new['annual_failure_rate_pct'] <= max_failure,
                        'monthly_data': monthly_data_c,
                        'monthly_production_wh':  [round(v * 1000, 0) for v in monthly_prod_net],
                        'monthly_consumption_wh': [round(v, 0) for v in monthly_consumption_wh],
                        'monthly_soc_avg_pct':      bat_new['monthly_soc_avg_pct'],
                        'monthly_soc_avg_pct_y10':  bat_y10['monthly_soc_avg_pct'],
                        'monthly_failures':         bat_new['monthly_failures'],
                        'annual_production_wh':     round(annual_prod_net_kwh * 1000, 0),
                        'annual_consumption_wh':    round(consumo_result['annual_wh'], 0),
                        'autonomy_2days_viable': autonomy.get('days_2_viable', False),
                        'autonomy_3days_viable': autonomy.get('days_3_viable', False),
                        'capex_cost': cap['cost'],
                        'capex_sale': cap['sale_price'],
                        'capex_breakdown': cap.get('breakdown', {}),
                        'tco_10y_cost': tco['cost'],
                        'tco_10y_sale': tco['sale_price'],
                        'tco_breakdown': tco.get('breakdown', {}),
                        'grid_energy_kwh_y': 0,
                        'co2_saved_10y_kg':  co2,
                        'protected_mode_hours': bat_new['protected_mode_hours'],
                        'recommended': False,
                        'rank': 0,
                        'warnings': warnings_c,
                        'shading': shading_stats,
                        'shading_comparison': shading_comparison,
                    })
                    continue   # skip the standard modular/fixed path below
                # ════════════════════════════════════════════════════════════

                # ── Use prefetched 1 kWp result, scale to product Wp ──────────
                soiling_loss   = geometrias.get_soiling_loss(soiling_env, geometry_type)
                soiling_factor = 1.0 - soiling_loss
                _pre = _pvgis_1kwp.get(geometry_type)
                if _pre:
                    _wp_scale = product['pv_peak_power_wp'] / 1000.0
                    pvgis_result_1 = {
                        'hourly_wh':  [v * _wp_scale for v in _pre['hourly_wh']],
                        'monthly_kwh':[v * _wp_scale for v in _pre['monthly_kwh']],
                        'annual_kwh':  _pre['annual_kwh'] * _wp_scale,
                        'geometry':    _pre.get('geometry', {}),
                    }
                else:
                    # Cache miss — fall back to direct fetch
                    pvgis_result_1 = pvgis_mod.fetch_pvgis_geometry(
                        lat, lon, geometry_type, product['pv_peak_power_wp'],
                        losses_pct=14, pvgis_db=pvgis_db, road_orientation_deg=0
                    )
                solar_base_net = geometrias.apply_soiling(pvgis_result_1['hourly_wh'], soiling_loss)

                # Shade-corrected production for this geometry (None if unsupported/inactive) —
                # scaled to this product's actual Wp, same reasoning as solar_base_net above.
                shaded_1kwp, shading_stats = _get_shaded_1kwp(geometry_type, soiling_loss)
                solar_shaded_net = None
                if shaded_1kwp is not None:
                    _wp_scale_shaded = product['pv_peak_power_wp'] / 1000.0
                    solar_shaded_net = [v * _wp_scale_shaded for v in shaded_1kwp]

                # ── Determine unit count to simulate ──────────────────────────
                is_modular = geometry_type in MODULAR_GEOMETRIES
                unit_range = range(1, MAX_MODULAR_UNITS + 1) if is_modular else range(1, 2)

                chosen_candidate = None
                for n_units in unit_range:
                    # Scale solar and battery linearly with number of units.
                    # Uses shade-corrected production when available (doc §26: shading must
                    # feed into how many modular units get recommended, not just be reported).
                    _base_for_sim = solar_shaded_net if solar_shaded_net is not None else solar_base_net
                    solar_hourly = [v * n_units for v in _base_for_sim]
                    bat_wh = product['battery_nominal_wh'] * n_units

                    bat_result = bateria.simular_bateria_anual(
                        solar_hourly, consumo_hourly, bat_wh,
                        smartec_protection=data.get('smartec_enabled', True),
                        annual_schedule=schedule,
                        prebuilt_night_map=_night_map
                    )
                    bat_new = bat_result['new']
                    bat_y10 = bat_result['year10']

                    failure_rate = bat_new['annual_failure_rate_pct']
                    meets_target = failure_rate <= max_failure

                    # For modular: stop at first N that meets target; always record N=max as fallback
                    if not is_modular or meets_target or n_units == MAX_MODULAR_UNITS:
                        # Build scaled product specs
                        pv_wp    = product['pv_peak_power_wp'] * n_units
                        weight   = product.get('weight_kg', 0) * n_units

                        if solar_shaded_net is not None:
                            # solar_hourly already includes soiling + shading — don't re-apply soiling.
                            monthly_prod_net    = _monthly_kwh_from_hourly(solar_hourly)
                            annual_prod_net_kwh = round(sum(solar_hourly) / 1000, 2)
                        else:
                            monthly_prod_net    = [round(v * n_units * soiling_factor, 2)
                                                   for v in pvgis_result_1['monthly_kwh']]
                            annual_prod_net_kwh = round(pvgis_result_1['annual_kwh'] * n_units * soiling_factor, 2)

                        # Comparativa obligatoria PVGIS puro vs. PVGIS+Shadowmap (doc §28) —
                        # mismo producto/n_units, solo un sim extra sin corregir.
                        shading_comparison = None
                        if solar_shaded_net is not None:
                            solar_hourly_base = [v * n_units for v in solar_base_net]
                            br_base = bateria.simular_bateria_anual(
                                solar_hourly_base, consumo_hourly, bat_wh,
                                smartec_protection=data.get('smartec_enabled', True),
                                annual_schedule=schedule, prebuilt_night_map=_night_map
                            )
                            shading_comparison = {
                                'base_case': {
                                    'label': 'PVGIS puro',
                                    'annual_production_kwh': round(sum(solar_hourly_base) / 1000, 2),
                                    'annual_failure_rate_pct': br_base['new']['annual_failure_rate_pct'],
                                },
                                'corrected_case': {
                                    'label': 'PVGIS + Shadowmap',
                                    'annual_production_kwh': annual_prod_net_kwh,
                                    'annual_failure_rate_pct': bat_new['annual_failure_rate_pct'],
                                },
                                'monthly_production_base_wh': [round(v * 1000, 0) for v in _monthly_kwh_from_hourly(solar_hourly_base)],
                            }

                        # Scaled product dict for CAPEX (panel + battery cost scale with N)
                        scaled_product = dict(product)
                        scaled_product['pv_peak_power_wp']   = pv_wp
                        scaled_product['battery_nominal_wh'] = bat_wh
                        scaled_product['weight_kg']          = weight

                        capex = optimizador.calcular_capex(scaled_product, costs)
                        tco   = optimizador.calcular_tco_10y(
                            capex['cost'], 0, electricity_cost, costs,
                            bat_wh, 0.70, costs.get('gross_margin', 0.62)
                        )
                        co2      = optimizador.calcular_co2_evitado(annual_prod_net_kwh, co2_factor, 0, 10)
                        autonomy = bateria.calcular_autonomia_equivalente(bat_wh, 0.85, 0.15, avg_night_wh)

                        # Label suffix for modular products with N>1
                        name_suffix = f' x{n_units}' if (is_modular and n_units > 1) else ''
                        cid = pid + (f'_x{n_units}' if (is_modular and n_units > 1) else '')

                        # Build monthly_data: daily avg kWh + min SOC per month
                        _days_m = [31,28,31,30,31,30,31,31,30,31,30,31]
                        _soc_min_new  = bat_new.get('monthly_soc_min_pct',  bat_new['monthly_soc_avg_pct'])
                        _soc_min_y10  = bat_y10.get('monthly_soc_min_pct',  bat_y10['monthly_soc_avg_pct'])
                        _soc_dusk_new = bat_new.get('monthly_soc_dusk_avg_pct', bat_new['monthly_soc_avg_pct'])
                        _prot_new     = bat_new.get('monthly_protection_nights', [0] * 12)
                        monthly_data_c = []
                        for _mi in range(12):
                            _d = _days_m[_mi]
                            monthly_data_c.append({
                                'production_kwh':  round(monthly_prod_net[_mi] / _d, 3),
                                'consumption_kwh': round(monthly_consumption_wh[_mi] / 1000 / _d, 3),
                                'prod_total_kwh':  round(monthly_prod_net[_mi], 2),
                                'cons_total_kwh':  round(monthly_consumption_wh[_mi] / 1000, 2),
                                'soc_min_pct':     _soc_min_new[_mi],
                                'soc_min_y10':     _soc_min_y10[_mi],
                                'soc_dusk_pct':    _soc_dusk_new[_mi],
                                'protection_nights': _prot_new[_mi],
                                'diffuse_fraction': _diffuse_frac[_mi],
                                'failures':        bat_new['monthly_failures'][_mi],
                            })

                        warnings_c = []
                        if failure_rate > max_failure:
                            warnings_c.append(f"Incluso con {n_units} unidades: {failure_rate:.1f}% noches fallo")
                        if weight > 50:
                            warnings_c.append(f"Peso elevado: {weight:.0f} kg")

                        chosen_candidate = {
                            'product_id':   cid,
                            'product_name': product['name'] + name_suffix,
                            'n_units':      n_units,
                            'is_modular':   is_modular,
                            'pv_peak_power_wp':   pv_wp,
                            'battery_nominal_wh': bat_wh,
                            'weight_kg':          weight,
                            'geometry_type':      geometry_type,
                            'loss_tree': _build_loss_tree(geometry_type, soiling_loss),
                            'annual_failure_rate_pct':     bat_new['annual_failure_rate_pct'],
                            'annual_failure_rate_pct_y10': bat_y10['annual_failure_rate_pct'],
                            'meets_reliability': meets_target,
                            'monthly_data': monthly_data_c,
                            'monthly_production_wh':  [round(v * 1000, 0) for v in monthly_prod_net],
                            'monthly_consumption_wh': [round(v, 0) for v in monthly_consumption_wh],
                            'monthly_soc_avg_pct':      bat_new['monthly_soc_avg_pct'],
                            'monthly_soc_avg_pct_y10':  bat_y10['monthly_soc_avg_pct'],
                            'monthly_failures':         bat_new['monthly_failures'],
                            'annual_production_wh':     round(annual_prod_net_kwh * 1000, 0),
                            'annual_consumption_wh':    round(consumo_result['annual_wh'], 0),
                            'autonomy_2days_viable': autonomy.get('days_2_viable', False),
                            'autonomy_3days_viable': autonomy.get('days_3_viable', False),
                            'capex_cost': capex['cost'],
                            'capex_sale': capex['sale_price'],
                            'capex_breakdown': capex.get('breakdown', {}),
                            'tco_10y_cost': tco['cost'],
                            'tco_10y_sale': tco['sale_price'],
                            'tco_breakdown': tco.get('breakdown', {}),
                            'grid_energy_kwh_y': 0,
                            'co2_saved_10y_kg':  co2,
                            'protected_mode_hours': bat_new['protected_mode_hours'],
                            'recommended': False,
                            'rank': 0,
                            'warnings': warnings_c,
                            'shading': shading_stats,
                            'shading_comparison': shading_comparison,
                        }
                        break  # found optimal N (or exhausted max)

                if chosen_candidate:
                    candidates_results.append(chosen_candidate)

            except ConnectionError as e:
                print(f'[simulate] PVGIS ERROR for {pid}: {e}')
                candidates_results.append({
                    'product_id': pid,
                    'product_name': product['name'],
                    'error': str(e),
                    'warnings': [f'Error PVGIS: {e}']
                })
            except Exception as e:
                print(f'[simulate] EXCEPTION for {pid}: {type(e).__name__}: {e}')
                traceback.print_exc()
                candidates_results.append({
                    'product_id': pid,
                    'product_name': product.get('name', pid),
                    'error': str(e),
                    'warnings': [f'Error de simulacion: {e}']
                })

        # Rank candidates
        valid_candidates = [c for c in candidates_results if 'error' not in c]
        ranked = optimizador.rankear_candidatos(valid_candidates, objective, max_failure)
        error_candidates = [c for c in candidates_results if 'error' in c]

        # Get recommended product
        recommended_id = ranked[0]['product_id'] if ranked else None

        # Generate Smartec profile for recommended
        smartec_profile = None
        if recommended_id:
            rec = ranked[0]
            smartec_profile = smartec.generar_perfil_smartec(
                periods_def, rec['battery_nominal_wh']
            )

        # Save simulation run
        run_id = str(uuid.uuid4())
        with db_module.db() as conn:
            conn.execute(
                "INSERT INTO simulation_runs (id, params_json, status) VALUES (?,?,?)",
                (run_id, json.dumps(data), 'completed')
            )

        # Persist the recommended candidate's shading analysis, if one was computed.
        if use_local_shading and ranked:
            rec_shading = ranked[0].get('shading')
            if rec_shading and rec_shading.get('status') not in (None, 'not_supported_geometry'):
                try:
                    db_module.save_shading_analysis({
                        'project_id': data.get('project_id'),
                        'shading_mode': shading_mode,
                        'lat': lat, 'lon': lon,
                        'panel_center_height_m': panel_center_height_m,
                        'height_mode': rec_shading.get('height_mode'),
                        'provider_confidence': rec_shading.get('confidence'),
                        'annual_direct_shadow_loss_pct': rec_shading.get('annual_direct_shadow_loss_pct'),
                        'annual_total_shadow_loss_pct': rec_shading.get('annual_total_shadow_loss_pct'),
                        'monthly_shadow_loss_pct': rec_shading.get('monthly_shadow_loss_pct', []),
                        'critical_month_shadow_loss_pct': rec_shading.get('critical_month_shadow_loss_pct'),
                        'status': 'applied' if rec_shading.get('shadow_correction_applied') else 'not_applied',
                    })
                except Exception as exc:
                    print(f'[shadowmap] failed to persist shading analysis: {exc}')

        return jsonify({
            'simulation_id': run_id,
            'recommended_product_id': recommended_id,
            'candidates': ranked + error_candidates,
            'monthly_consumption_wh': [round(v, 0) for v in monthly_consumption_wh],
            'annual_consumption_wh': round(consumo_result['annual_wh'], 0),
            'avg_night_consumption_wh': round(avg_night_wh, 1),
            'smartec_profile': smartec_profile,
            'simulation_params': {
                'lat': lat, 'lon': lon,
                'system_power_w': system_power_w,
                'soiling_env': soiling_env,
                'pvgis_db': pvgis_db_override or pvgis_mod.auto_select_pvgis_db(lat, lon),
                'use_local_shading': use_local_shading,
                'shading_mode': shading_mode if use_local_shading else None,
                'panel_center_height_m': panel_center_height_m if use_local_shading else None,
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug-sim', methods=['POST'])
def debug_sim():
    """
    Diagnostic endpoint — devuelve valores intermedios del pipeline de simulacion
    para verificar que consumo, produccion y deteccion de fallos funcionan correctamente.
    """
    data = request.get_json() or {}
    lat   = float(data.get('lat', 41.39))
    lon   = float(data.get('lon', 2.17))
    pw    = float(data.get('system_power_w', 90))
    pid   = data.get('product_id', 'SIL_M_60')
    year  = int(data.get('year', 2024))
    se    = data.get('soiling_env', 'urbana_normal')
    mg_on = int(data.get('margin_on_min', -15))
    mg_of = int(data.get('margin_off_min', 15))
    periods_def = data.get('night_profile', [
        {'duration_pct': 0.333, 'presence_ratio': 0.5, 'dimming_presence': 1.0, 'dimming_no_presence': 0.3},
        {'duration_pct': 0.333, 'presence_ratio': 0.2, 'dimming_presence': 0.8, 'dimming_no_presence': 0.2},
        {'duration_pct': 0.334, 'presence_ratio': 0.3, 'dimming_presence': 0.8, 'dimming_no_presence': 0.2},
    ])

    try:
        product = prod_mod.get_product(pid)
        if not product:
            return jsonify({'error': f'Producto {pid} no encontrado'}), 404

        schedule = geo.build_annual_schedule(lat, lon, year, mg_on, mg_of)
        night_hours = [e['duration_h'] for e in schedule]
        avg_night_h = sum(night_hours) / len(night_hours)

        consumo_result = consumo.calcular_consumo_anual(pw, lat, lon, year, periods_def, 0, mg_on, mg_of)
        consumo_h = consumo_result['hourly_wh']
        nonzero_consumption = sum(1 for v in consumo_h if v > 0)
        total_consumption_wh = sum(consumo_h)

        pvgis_db = pvgis_mod.auto_select_pvgis_db(lat, lon)
        pvgis_result = pvgis_mod.fetch_pvgis_geometry(
            lat, lon, product['geometry_type'], product['pv_peak_power_wp'],
            losses_pct=14, pvgis_db=pvgis_db
        )
        solar_raw = pvgis_result['hourly_wh']
        soiling_loss = geometrias.get_soiling_loss(se, product['geometry_type'])
        solar_h = geometrias.apply_soiling(solar_raw, soiling_loss)
        nonzero_solar = sum(1 for v in solar_h if v > 0)
        total_solar_wh = sum(solar_h)

        night_map = {}
        for entry in schedule:
            d = entry['day_of_year'] - 1
            on_h, off_h = entry['on_hour'], entry['off_hour']
            for h in range(int(on_h), int(off_h) + 2):
                ah = d * 24 + h
                if 0 <= ah < 8760:
                    night_map[ah] = d
        nm_entries = len(night_map)

        night_hours_with_load = sum(1 for h, d in night_map.items() if consumo_h[h] > 0)
        night_hours_without_load = nm_entries - night_hours_with_load

        bat_result = bateria.simular_bateria_anual(
            solar_h, consumo_h, product['battery_nominal_wh'],
            smartec_protection=True, annual_schedule=schedule
        )
        bn = bat_result['new']

        trace = []
        bat_nom = product['battery_nominal_wh']
        bat_usable = bat_nom * 0.85
        min_soc_wh = bat_nom * 0.15
        prot_thr = bat_usable * 0.5
        soc = bat_nom
        for h in range(min(72, 8760)):
            pv   = solar_h[h]
            load = consumo_h[h]
            load_eff = load
            if load > 0 and soc < prot_thr:
                load_eff = load * max(0.2, soc / prot_thr)
            net = pv * 0.97 - load_eff / 0.97
            new_soc = max(0.0, min(bat_nom, soc + net))
            crit = new_soc < min_soc_wh and load_eff > 0 and h in night_map
            if load > 0 or pv > 0 or crit:
                trace.append({
                    'h': h, 'soc': round(soc, 1), 'pv': round(pv, 2),
                    'load': round(load, 3), 'load_eff': round(load_eff, 3),
                    'new_soc': round(new_soc, 1), 'in_night_map': h in night_map,
                    'critical': crit,
                })
            soc = new_soc

        return jsonify({
            'product': {'id': pid, 'name': product['name'],
                        'pv_wp': product['pv_peak_power_wp'],
                        'bat_wh': product['battery_nominal_wh'],
                        'geometry': product['geometry_type']},
            'schedule': {
                'days': len(schedule),
                'avg_night_h': round(avg_night_h, 2),
                'sample_day1': schedule[0],
                'sample_day180': schedule[180] if len(schedule) > 180 else None,
            },
            'consumption': {
                'system_power_w': pw,
                'nonzero_hours': nonzero_consumption,
                'total_annual_wh': round(total_consumption_wh, 1),
                'avg_night_wh': round(consumo_result['avg_night_wh'], 1),
                'h16_jan1': round(consumo_h[16], 3),
                'h25_jan1': round(consumo_h[25], 3),
            },
            'solar': {
                'pvgis_db': pvgis_db,
                'pvgis_cached': pvgis_result.get('cached', False),
                'geometry': pvgis_result.get('geometry', {}),
                'soiling_loss_pct': round(soiling_loss * 100, 1),
                'nonzero_hours': nonzero_solar,
                'total_annual_wh': round(total_solar_wh, 1),
                'monthly_kwh': [round(v, 2) for v in pvgis_result['monthly_kwh']],
            },
            'night_map': {
                'total_entries': nm_entries,
                'night_hours_with_load': night_hours_with_load,
                'night_hours_without_load': night_hours_without_load,
                'h16_in_map': 16 in night_map,
                'h25_in_map': 25 in night_map,
            },
            'simulation': {
                'annual_failure_rate_pct': bn['annual_failure_rate_pct'],
                'critical_nights': bn['critical_nights'],
                'monthly_failures': bn['monthly_failures'],
                'monthly_soc_avg_pct': bn['monthly_soc_avg_pct'],
            },
            'trace_hours_0_72': trace,
        })

    except ConnectionError as e:
        return jsonify({'error': f'PVGIS no disponible: {e}'}), 503
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/report', methods=['POST'])
def generate_report():
    """Generate a Word (.docx) report from simulation results."""
    from io import BytesIO
    data = request.get_json() or {}
    try:
        docx_bytes = report_docx.generate_report(data)
        project_name = (data.get('project', {}).get('name') or 'informe').replace(' ', '_')
        filename = f'SALVI_Solar_{project_name}.docx'
        return send_file(
            BytesIO(docx_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/validate', methods=['POST'])
def validate_calculation():
    """
    Validation endpoint: reproduce PVGIS off-grid reference scenario.
    """
    data = request.get_json() or {}
    lat          = float(data.get('lat', 41.38))
    lon          = float(data.get('lon', 2.18))
    peak_wp      = float(data.get('peak_power_wp', 260.0))
    battery_wh   = float(data.get('battery_wh', 1330.0))
    consumption_wh_night = float(data.get('consumption_wh_night', 400.0))
    tilt         = float(data.get('tilt_deg', 0.0))
    azimuth      = float(data.get('azimuth_deg', 0.0))
    losses_pct   = float(data.get('losses_pct', 14.0))
    soiling_pct  = float(data.get('soiling_pct', 0.0))
    dod_max      = float(data.get('dod_max', 0.85))
    charge_eff   = float(data.get('charge_eff', 0.97))
    discharge_eff= float(data.get('discharge_eff', 0.97))
    year         = int(data.get('year', 2020))
    margin_on    = int(data.get('margin_on_min', -15))
    margin_off   = int(data.get('margin_off_min', 15))

    try:
        from modules import db as db_module, pvgis as pvgis_mod, geo, bateria as bat_mod
        import hashlib

        pvgis_db = pvgis_mod.auto_select_pvgis_db(lat, lon)

        def _cache_key_direct(lat, lon, tilt, az, kw, loss, db):
            s = f"{lat:.4f}|{lon:.4f}|{tilt:.1f}|{az:.1f}|{kw:.5f}|{loss:.1f}|{db}"
            return hashlib.sha256(s.encode()).hexdigest()[:20]

        peak_kw = peak_wp / 1000.0
        ckey = _cache_key_direct(lat, lon, tilt, azimuth, peak_kw, losses_pct, pvgis_db)
        cached = db_module.get_pvgis_cache(ckey)
        if cached:
            hourly_raw = cached['hourly_wh']
            monthly_kwh = cached['monthly_kwh']
            annual_kwh  = cached['annual_kwh']
            was_cached  = True
        else:
            hourly_raw = pvgis_mod._fetch_seriescalc(lat, lon, tilt, azimuth, peak_kw, losses_pct, pvgis_db)
            days_in_month = [31,28,31,30,31,30,31,31,30,31,30,31]
            monthly_kwh = []
            h = 0
            for m_days in days_in_month:
                m_hours = m_days * 24
                monthly_kwh.append(sum(hourly_raw[h:h+m_hours]) / 1000)
                h += m_hours
            annual_kwh = sum(monthly_kwh)
            db_module.set_pvgis_cache(ckey, lat, lon, tilt, azimuth, peak_kw, losses_pct, pvgis_db,
                                       {'hourly_wh': hourly_raw, 'monthly_kwh': monthly_kwh,
                                        'annual_kwh': annual_kwh,
                                        'geometry': {'tilt': tilt, 'azimuth': azimuth}})
            was_cached = False

        soiling_factor = 1.0 - soiling_pct / 100.0
        hourly_solar = [v * soiling_factor for v in hourly_raw]
        monthly_kwh_net = [round(v * soiling_factor, 3) for v in monthly_kwh]
        annual_kwh_net  = round(annual_kwh * soiling_factor, 3)

        schedule = geo.build_annual_schedule(lat, lon, year, margin_on, margin_off)
        consumo_hourly = [0.0] * 8760
        for entry in schedule:
            night_h = entry['duration_h']
            if night_h <= 0:
                continue
            wh_per_h = consumption_wh_night / max(night_h, 1)
            d = entry['day_of_year'] - 1
            on_h  = int(entry['on_hour'])
            off_h = int(entry['off_hour'])
            for h_off in range(on_h, off_h + 2):
                actual_h = d * 24 + h_off
                if 0 <= actual_h < 8760:
                    consumo_hourly[actual_h] = wh_per_h

        bat_result = bat_mod.simular_bateria_anual(
            hourly_solar, consumo_hourly, battery_wh,
            dod_max=dod_max, charge_eff=charge_eff, discharge_eff=discharge_eff,
            smartec_protection=False, annual_schedule=schedule
        )
        bn = bat_result['new']

        avg_night_h = sum(e['duration_h'] for e in schedule) / len(schedule) if schedule else 0
        monthly_night_h = [0.0] * 12
        for e in schedule:
            monthly_night_h[e['month'] - 1] += e['duration_h']

        return jsonify({
            'params': {
                'lat': lat, 'lon': lon, 'peak_wp': peak_wp, 'battery_wh': battery_wh,
                'tilt_deg': tilt, 'azimuth_deg': azimuth,
                'consumption_wh_night': consumption_wh_night,
                'losses_pct': losses_pct, 'soiling_pct': soiling_pct,
                'pvgis_db': pvgis_db, 'pvgis_year': year,
            },
            'production': {
                'monthly_kwh': monthly_kwh_net,
                'annual_kwh': annual_kwh_net,
                'pvgis_cached': was_cached,
            },
            'consumption': {
                'wh_per_night': consumption_wh_night,
                'avg_night_hours': round(avg_night_h, 2),
                'monthly_night_hours': [round(v, 1) for v in monthly_night_h],
            },
            'reliability': {
                'annual_failure_rate_pct': bn['annual_failure_rate_pct'],
                'critical_nights': bn['critical_nights'],
                'monthly_failures': bn['monthly_failures'],
                'monthly_soc_avg_pct': bn['monthly_soc_avg_pct'],
                'protected_mode_hours': bn['protected_mode_hours'],
            },
            'methodology': {
                'our_metric': 'Noches criticas: noches donde el SOC baja del minimo en algun momento nocturno',
                'pvgis_metric': 'f_e: fraccion de energia no suministrada (energia no cubierta / demanda total)',
                'comparison_note': (
                    'Nuestro % tiende a ser mas alto que PVGIS f_e: contamos la noche entera como fallo '
                    'aunque el deficit sea solo de unos minutos al amanecer. '
                    'Para alumbrado (la luz debe estar encendida TODA la noche) nuestro criterio es mas exigente y correcto.'
                ),
                'pvgis_reference_fe_pct': 7.25,
                'pvgis_reference_source': 'PVGIS Off-grid SAM: Barcelona 41.38N, 260Wp, 1330Wh, 0deg, 400Wh/d, losses=14%',
            }
        })

    except ConnectionError as e:
        return jsonify({'error': f'PVGIS no disponible: {e}'}), 503
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/climate')
def get_climate():
    import requests as req
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'error': 'lat and lon required'}), 400
    result = {'irradiance': None, 'precip': None, 'temp': None, 'errors': []}

    try:
        params = {'lat': lat, 'lon': lon, 'horirrad': 1,
                  'outputformat': 'json', 'browser': 0}
        r = req.get('https://re.jrc.ec.europa.eu/api/v5_2/MRcalc',
                    params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        monthly_raw = d.get('outputs', {}).get('monthly', [])
        if isinstance(monthly_raw, dict):
            months = monthly_raw.get('fixed', monthly_raw.get('variable', []))
        elif isinstance(monthly_raw, list):
            months = monthly_raw
        else:
            months = []
        print(f'[climate] PVGIS months={len(months)}, sample keys={list(months[0].keys()) if months else []}')
        if months:
            mo_sum = [0.0]*12; mo_cnt = [0]*12
            H_KEYS = ['H(h)_d', 'Hh', 'H_d', 'Gh', 'G(h)']
            days   = [31,28,31,30,31,30,31,31,30,31,30,31]
            for m in months:
                mo = int(m.get('month', 0)) - 1
                if not (0 <= mo < 12):
                    continue
                val = None
                for k in H_KEYS:
                    if k in m: val = float(m[k]); break
                if val is None and 'H(h)_m' in m:
                    val = float(m['H(h)_m']) / days[mo]
                if val is not None:
                    mo_sum[mo] += val; mo_cnt[mo] += 1
            result['irradiance'] = [
                round(mo_sum[i]/mo_cnt[i], 3) if mo_cnt[i] else 0.0
                for i in range(12)
            ]
            print(f'[climate] irradiance OK: {result["irradiance"]}')
    except Exception as e:
        result['errors'].append(f'PVGIS: {e}')
        print(f'[climate] PVGIS error: {e}')

    try:
        params = {
            'latitude': lat, 'longitude': lon,
            'start_date': '2022-01-01', 'end_date': '2023-12-31',
            'daily': 'precipitation_sum,temperature_2m_mean,wind_speed_10m_max',
            'timezone': 'UTC'
        }
        r = req.get('https://archive-api.open-meteo.com/v1/archive',
                    params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        daily = d.get('daily', {})
        times  = daily.get('time', [])
        p_vals = daily.get('precipitation_sum', [])
        t_vals = daily.get('temperature_2m_mean', [])
        w_vals = daily.get('wind_speed_10m_max', [])
        print(f'[climate] Open-Meteo daily records={len(times)}')
        if times:
            p_sum = [0.0]*12; t_sum = [0.0]*12; w_sum = [0.0]*12
            p_cnt = [0]*12;   t_cnt = [0]*12;   w_cnt = [0]*12
            for i, ts in enumerate(times):
                mo = int(ts[5:7]) - 1
                if i < len(p_vals) and p_vals[i] is not None:
                    p_sum[mo] += p_vals[i]; p_cnt[mo] += 1
                if i < len(t_vals) and t_vals[i] is not None:
                    t_sum[mo] += t_vals[i]; t_cnt[mo] += 1
                if i < len(w_vals) and w_vals[i] is not None:
                    w_sum[mo] += w_vals[i]; w_cnt[mo] += 1
            result['precip'] = [round(p_sum[i]/p_cnt[i], 1) if p_cnt[i] else 0 for i in range(12)]
            result['temp']   = [round(t_sum[i]/t_cnt[i], 1) if t_cnt[i] else 0 for i in range(12)]
            result['wind']   = [round(w_sum[i]/w_cnt[i], 1) if w_cnt[i] else 0 for i in range(12)]
    except Exception as e:
        result['errors'].append(f'Open-Meteo: {e}')
        print(f'[climate] Open-Meteo error: {e}')

    return jsonify(result)

# --- Road power estimation ---

@app.route('/api/road', methods=['POST'])
def api_road():
    body = request.get_json(silent=True) or {}
    lat        = body.get('lat')
    lon        = body.get('lon')
    skip_osm   = body.get('skip_osm', False)

    result = {
        'road':        None,
        'disposicion': None,
        'opticas':     None,
        'potencia':    None,
        'clase_labels': via_mod.clase_labels(),
        'lentes':      via_mod.lentes_catalog(),
    }

    if not skip_osm and lat is not None and lon is not None:
        road_data = via_mod.fetch_road_osm(float(lat), float(lon))
        result['road'] = road_data

    road = result['road'] or {}
    lighting_class = body.get('lighting_class') or road.get('lighting_class', 'ME4a')
    E_lux          = via_mod.iluminancia_desde_clase(lighting_class)
    road_width     = float(body.get('road_width_m')  or road.get('width_m') or 7.0)
    safety_margin  = float(body.get('safety_margin_m', 1.0))
    ancho_total    = road_width + 2.0 * safety_margin
    pole_height    = float(body.get('pole_height_m',  8.0))
    spacing        = float(body.get('spacing_m',      30.0))

    disp   = via_mod.calcular_disposicion(ancho_total, pole_height)
    opticas = via_mod.sugerir_optica(disp['w_H'], lighting_class)
    result['disposicion'] = disp
    result['opticas']     = opticas

    optica_id   = body.get('optica_id') or opticas[0]['id']
    CU_override = body.get('CU') if body.get('CU') else None
    MF          = float(body.get('MF',      0.75))
    eta_led     = float(body.get('eta_led', 130.0))

    pot = via_mod.calcular_potencia(
        E_lux, ancho_total, spacing, disp, optica_id,
        MF=MF, eta_led=eta_led, CU_override=CU_override
    )
    pot['lighting_class'] = lighting_class
    pot['ancho_calzada']  = road_width
    pot['safety_margin']  = safety_margin
    pot['pole_height']    = pole_height
    result['potencia'] = pot

    return jsonify(result)


if __name__ == '__main__':
    print(f"[SALVI Solar] Starting on http://localhost:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=os.environ.get('DEBUG', 'False').lower() == 'true')
