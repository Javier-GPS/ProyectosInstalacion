#!/usr/bin/env python3
"""PVGIS/JRC API integration with SQLite cache."""
import requests, json, hashlib, time

PVGIS_BASE = "https://re.jrc.ec.europa.eu/api/v5_3"
REQUEST_TIMEOUT = 45

def _cache_key(lat, lon, tilt, azimuth, peak_kw, losses, pvgis_db):
    s = f"{lat:.4f}|{lon:.4f}|{tilt:.1f}|{azimuth:.1f}|{peak_kw:.5f}|{losses:.1f}|{pvgis_db}"
    return hashlib.sha256(s.encode()).hexdigest()[:20]

def auto_select_pvgis_db(lat, lon):
    """Select best PVGIS database for location."""
    if -65 <= lat <= 65 and -25 <= lon <= 75:
        return "PVGIS-SARAH3"
    return "ERA5"

def _fetch_seriescalc(lat, lon, tilt, azimuth, peak_power_kw, losses_pct=14, pvgis_db="PVGIS-SARAH3"):
    """
    Call PVGIS seriescalc API. Returns list of 8760 hourly Wh values.
    Uses TMY (Typical Meteorological Year) -- no startyear/endyear.
    azimuth: 0=south, -90=east, +90=west, 180=north
    peak_power_kw: kWp (not Wp!)
    Raises ConnectionError on failure.
    """
    params = {
        'lat': lat, 'lon': lon,
        'raddatabase': pvgis_db,
        'pvcalculation': 1,
        'peakpower': peak_power_kw,
        'loss': losses_pct,
        'angle': tilt,
        'aspect': azimuth,
        'outputformat': 'json',
    }
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; SALVISolar/1.0)'}
    for attempt in range(2):
        try:
            resp = requests.get(f"{PVGIS_BASE}/seriescalc", params=params,
                                headers=headers, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                body = resp.text[:400].strip()
                raise ConnectionError(f"PVGIS HTTP {resp.status_code}: {body}")
            data = resp.json()
            hourly_raw = data.get('outputs', {}).get('hourly', [])
            hourly_wh = [float(h.get('P', 0)) for h in hourly_raw]
            if len(hourly_wh) < 8760:
                raise ConnectionError(f"PVGIS returned only {len(hourly_wh)} hourly values (expected 8760)")
            return hourly_wh[:8760]
        except requests.Timeout:
            if attempt == 0:
                time.sleep(2)
                continue
            raise ConnectionError("PVGIS timeout after 2 attempts")
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"PVGIS error: {e}")


def _fetch_seriescalc_components(lat, lon, tilt, azimuth, pvgis_db="PVGIS-SARAH3"):
    """
    Call PVGIS seriescalc in irradiance-components mode (pvcalculation=0, components=1).
    Returns dict of 4 lists (8760 values each): direct_wh_m2, diffuse_wh_m2, reflected_wh_m2,
    sun_altitude_deg — irradiance on the inclined plane (Gb(i)/Gd(i)/Gr(i)) and solar altitude.
    Used only for local-shading correction; the main production path still uses
    _fetch_seriescalc (pvcalculation=1) and is untouched by this function.
    """
    params = {
        'lat': lat, 'lon': lon,
        'raddatabase': pvgis_db,
        'pvcalculation': 0,
        'components': 1,
        'angle': tilt,
        'aspect': azimuth,
        'outputformat': 'json',
    }
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; SALVISolar/1.0)'}
    for attempt in range(2):
        try:
            resp = requests.get(f"{PVGIS_BASE}/seriescalc", params=params,
                                headers=headers, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                body = resp.text[:400].strip()
                raise ConnectionError(f"PVGIS HTTP {resp.status_code}: {body}")
            data = resp.json()
            hourly_raw = data.get('outputs', {}).get('hourly', [])
            direct    = [float(h.get('Gb(i)', 0)) for h in hourly_raw]
            diffuse   = [float(h.get('Gd(i)', 0)) for h in hourly_raw]
            reflected = [float(h.get('Gr(i)', 0)) for h in hourly_raw]
            sun_alt   = [float(h.get('H_sun', 0)) for h in hourly_raw]
            if len(direct) < 8760:
                raise ConnectionError(f"PVGIS returned only {len(direct)} hourly values (expected 8760)")
            return {
                'direct_wh_m2':    direct[:8760],
                'diffuse_wh_m2':   diffuse[:8760],
                'reflected_wh_m2': reflected[:8760],
                'sun_altitude_deg': sun_alt[:8760],
            }
        except requests.Timeout:
            if attempt == 0:
                time.sleep(2)
                continue
            raise ConnectionError("PVGIS timeout after 2 attempts")
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"PVGIS error: {e}")


def _fetch_components_cached(lat, lon, tilt, azimuth, pvgis_db, cache_db_tag):
    """Fetch (or read from cache) Gb(i)/Gd(i)/Gr(i)/H_sun for a single tilt/azimuth.
    Irradiance components don't depend on peak power, so they're cached with
    peak_kw=0/losses=0 placeholders under a '_COMPONENTS' tag, reusing pvgis_cache."""
    from modules import db as db_module
    key = _cache_key(lat, lon, tilt, azimuth, 0.0, 0.0, cache_db_tag + '_COMPONENTS')
    cached = db_module.get_pvgis_cache(key)
    if cached:
        return cached
    comp = _fetch_seriescalc_components(lat, lon, tilt, azimuth, pvgis_db)
    db_module.set_pvgis_cache(key, lat, lon, tilt, azimuth, 0.0, 0.0,
                               cache_db_tag + '_COMPONENTS', comp)
    return comp


def _sum_components(component_dicts):
    """Element-wise sum of direct/diffuse/reflected across multiple sub-planes/sectors
    (e.g. the 12 cylinder sectors, or east+west of the double-vertical geometry).
    Sun altitude is a property of time, not orientation — take it from the first entry."""
    n = len(component_dicts[0]['direct_wh_m2'])
    summed = {
        'direct_wh_m2':    [sum(c['direct_wh_m2'][i]    for c in component_dicts) for i in range(n)],
        'diffuse_wh_m2':   [sum(c['diffuse_wh_m2'][i]   for c in component_dicts) for i in range(n)],
        'reflected_wh_m2': [sum(c['reflected_wh_m2'][i] for c in component_dicts) for i in range(n)],
        'sun_altitude_deg': component_dicts[0]['sun_altitude_deg'],
    }
    return summed


def _split_hourly_by_components(hourly_wh, components):
    """Proportionally split the (already peak-power-scaled) combined hourly production
    into direct/diffuse/reflected shares, using the relative irradiance components from
    PVGIS. By construction, direct+diffuse+reflected == hourly_wh for every hour —
    this does not reinvent PVGIS's power-conversion model, it only distributes the
    already-validated P value across components using their measured irradiance ratio."""
    direct, diffuse, reflected = [], [], []
    for i, p in enumerate(hourly_wh):
        gb = components['direct_wh_m2'][i]
        gd = components['diffuse_wh_m2'][i]
        gr = components['reflected_wh_m2'][i]
        total = gb + gd + gr
        if total > 0 and p > 0:
            direct.append(p * gb / total)
            diffuse.append(p * gd / total)
            reflected.append(p * gr / total)
        else:
            direct.append(0.0); diffuse.append(0.0); reflected.append(0.0)
    return direct, diffuse, reflected


def fetch_pvgis_geometry(lat, lon, geometry_type, peak_power_wp, losses_pct=14,
                          pvgis_db=None, db_conn=None, road_orientation_deg=0,
                          max_tilt_deg=30, with_components=False):
    """
    Fetch hourly PVGIS data for a Salvi geometry type.
    Uses cache from DB if available.
    Returns: {hourly_wh, monthly_kwh, annual_kwh, cached, geometry}
    Cache keys use '_TMY' suffix to distinguish from old year-specific cached data.
    When with_components=True and the geometry has a single tilt/azimuth (sil_horizontal,
    sil_independent, custom_orientable), also returns hourly_direct_wh/hourly_diffuse_wh/
    hourly_reflected_wh/hourly_sun_altitude_deg for local-shading correction. Cylinder and
    double-vertical geometries (multi-plane) don't support components in this phase —
    the shadow-correction module falls back to a simpler all-or-nothing multiplier for them.
    """
    from modules import db as db_module
    if pvgis_db is None:
        pvgis_db = auto_select_pvgis_db(lat, lon)

    cache_db_tag = pvgis_db + '_TMY'

    peak_kw = peak_power_wp / 1000.0

    def _monthly_from_hourly(hourly):
        """Aggregate 8760 hourly values to 12 monthly values in kWh."""
        days_in_month = [31,28,31,30,31,30,31,31,30,31,30,31]
        monthly = []
        h = 0
        for m_days in days_in_month:
            m_hours = m_days * 24
            monthly.append(sum(hourly[h:h+m_hours]) / 1000)
            h += m_hours
        return monthly

    def _add_components(result, tilt, azimuth):
        if not with_components:
            return result
        comp = _fetch_components_cached(lat, lon, tilt, azimuth, pvgis_db, cache_db_tag)
        direct, diffuse, reflected = _split_hourly_by_components(result['hourly_wh'], comp)
        result['hourly_direct_wh']      = direct
        result['hourly_diffuse_wh']     = diffuse
        result['hourly_reflected_wh']   = reflected
        result['hourly_sun_altitude_deg'] = comp['sun_altitude_deg']
        return result

    if geometry_type in ('sil_horizontal',):
        tilt = 10
        azimuth = road_orientation_deg
        key = _cache_key(lat, lon, tilt, azimuth, peak_kw, losses_pct, cache_db_tag)
        cached_data = db_module.get_pvgis_cache(key)
        if cached_data:
            return _add_components({**cached_data, 'cached': True}, tilt, azimuth)
        hourly = _fetch_seriescalc(lat, lon, tilt, azimuth, peak_kw, losses_pct, pvgis_db)
        monthly = _monthly_from_hourly(hourly)
        result = {
            'hourly_wh': hourly, 'monthly_kwh': monthly,
            'annual_kwh': sum(monthly),
            'geometry': {'tilt': tilt, 'azimuth': azimuth},
            'cached': False
        }
        db_module.set_pvgis_cache(key, lat, lon, tilt, azimuth, peak_kw, losses_pct, cache_db_tag,
                                   {k: v for k, v in result.items() if k != 'cached'})
        return _add_components(result, tilt, azimuth)

    elif geometry_type == 'sil_independent':
        tilt = max_tilt_deg
        azimuth = 0
        key = _cache_key(lat, lon, tilt, azimuth, peak_kw, losses_pct, cache_db_tag)
        cached_data = db_module.get_pvgis_cache(key)
        if cached_data:
            return _add_components({**cached_data, 'cached': True}, tilt, azimuth)
        hourly = _fetch_seriescalc(lat, lon, tilt, azimuth, peak_kw, losses_pct, pvgis_db)
        monthly = _monthly_from_hourly(hourly)
        result = {
            'hourly_wh': hourly, 'monthly_kwh': monthly,
            'annual_kwh': sum(monthly),
            'geometry': {'tilt': tilt, 'azimuth': azimuth},
            'cached': False
        }
        db_module.set_pvgis_cache(key, lat, lon, tilt, azimuth, peak_kw, losses_pct, cache_db_tag,
                                   {k: v for k, v in result.items() if k != 'cached'})
        return _add_components(result, tilt, azimuth)

    elif geometry_type in ('cylinder_250', 'cylinder_300', 'cylinder_350'):
        sector_kw = peak_kw / 12
        sector_azimuths = [i * 30 for i in range(12)]
        def norm_az(a):
            if a > 180: return a - 360
            return a

        combined_key = _cache_key(lat, lon, 90, 9999, peak_kw, losses_pct, cache_db_tag + '_CYL12')
        cached_data = db_module.get_pvgis_cache(combined_key)
        if cached_data:
            result = {**cached_data, 'cached': True}
        else:
            # Fetch 12 sectors in parallel
            from concurrent.futures import ThreadPoolExecutor
            def _fetch_sector(az):
                return _fetch_seriescalc(lat, lon, 90, norm_az(az), sector_kw, losses_pct, pvgis_db)
            with ThreadPoolExecutor(max_workers=6) as ex:
                sector_results = list(ex.map(_fetch_sector, sector_azimuths))
            combined = [sum(vals) for vals in zip(*sector_results)]

            monthly = _monthly_from_hourly(combined)
            result = {
                'hourly_wh': combined, 'monthly_kwh': monthly,
                'annual_kwh': sum(monthly),
                'geometry': {'tilt': 90, 'sectors': 12, 'azimuths': sector_azimuths},
                'cached': False
            }
            db_module.set_pvgis_cache(combined_key, lat, lon, 90, 9999, peak_kw, losses_pct,
                                       cache_db_tag + '_CYL12',
                                       {k: v for k, v in result.items() if k != 'cached'})

        if with_components:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=6) as ex:
                sector_components = list(ex.map(
                    lambda az: _fetch_components_cached(lat, lon, 90, norm_az(az), pvgis_db, cache_db_tag),
                    sector_azimuths
                ))
            comp = _sum_components(sector_components)
            direct, diffuse, reflected = _split_hourly_by_components(result['hourly_wh'], comp)
            result['hourly_direct_wh']        = direct
            result['hourly_diffuse_wh']       = diffuse
            result['hourly_reflected_wh']     = reflected
            result['hourly_sun_altitude_deg'] = comp['sun_altitude_deg']
        return result

    elif geometry_type == 'double_vertical_eo':
        # peak_power_wp es la potencia TOTAL del sistema (suma de ambos paneles).
        # Cada panel recibe la mitad: half_kw = total / 2.
        # Si el producto tiene 2 × 200 Wp, registrar pv_peak_power_wp = 400.
        half_kw = peak_kw / 2
        combined_key = _cache_key(lat, lon, 90, 0, peak_kw, losses_pct, cache_db_tag + '_DVEO')

        cached_data = db_module.get_pvgis_cache(combined_key)
        if cached_data:
            result = {**cached_data, 'cached': True}
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_east = ex.submit(_fetch_seriescalc, lat, lon, 90, -90, half_kw, losses_pct, pvgis_db)
                f_west = ex.submit(_fetch_seriescalc, lat, lon, 90,  90, half_kw, losses_pct, pvgis_db)
                east, west = f_east.result(), f_west.result()
            combined = [e + w for e, w in zip(east, west)]
            monthly = _monthly_from_hourly(combined)
            result = {
                'hourly_wh': combined, 'monthly_kwh': monthly,
                'annual_kwh': sum(monthly),
                'geometry': {'panels': [{'tilt': 90, 'azimuth': -90}, {'tilt': 90, 'azimuth': 90}]},
                'cached': False
            }
            db_module.set_pvgis_cache(combined_key, lat, lon, 90, 0, peak_kw, losses_pct,
                                       cache_db_tag + '_DVEO',
                                       {k: v for k, v in result.items() if k != 'cached'})

        if with_components:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_east = ex.submit(_fetch_components_cached, lat, lon, 90, -90, pvgis_db, cache_db_tag)
                f_west = ex.submit(_fetch_components_cached, lat, lon, 90,  90, pvgis_db, cache_db_tag)
                comp_east, comp_west = f_east.result(), f_west.result()
            comp = _sum_components([comp_east, comp_west])
            direct, diffuse, reflected = _split_hourly_by_components(result['hourly_wh'], comp)
            result['hourly_direct_wh']        = direct
            result['hourly_diffuse_wh']       = diffuse
            result['hourly_reflected_wh']     = reflected
            result['hourly_sun_altitude_deg'] = comp['sun_altitude_deg']
        return result

    elif geometry_type == 'custom_orientable':
        # Panel fijo orientado al sur con inclinacion optima para la latitud.
        # Formula estandar: tilt aprox lat x 0.87, acotado entre 15 y 50 grados.
        tilt = max(15, min(50, round(abs(lat) * 0.87)))
        azimuth = 0
        key = _cache_key(lat, lon, tilt, azimuth, peak_kw, losses_pct, cache_db_tag + '_COPT')
        cached_data = db_module.get_pvgis_cache(key)
        if cached_data:
            return _add_components({**cached_data, 'cached': True}, tilt, azimuth)
        hourly = _fetch_seriescalc(lat, lon, tilt, azimuth, peak_kw, losses_pct, pvgis_db)
        monthly = _monthly_from_hourly(hourly)
        result = {
            'hourly_wh': hourly, 'monthly_kwh': monthly,
            'annual_kwh': sum(monthly),
            'geometry': {'tilt': tilt, 'azimuth': azimuth, 'note': f'optimal tilt for lat {lat:.1f}deg'},
            'cached': False
        }
        db_module.set_pvgis_cache(key, lat, lon, tilt, azimuth, peak_kw, losses_pct,
                                   cache_db_tag + '_COPT',
                                   {k: v for k, v in result.items() if k != 'cached'})
        return _add_components(result, tilt, azimuth)

    else:
        return fetch_pvgis_geometry(lat, lon, 'sil_horizontal', peak_power_wp,
                                    losses_pct, pvgis_db, db_conn, road_orientation_deg)



def fetch_monthly_diffuse(lat, lon, pvgis_db=None):
    """
    Fetch monthly diffuse irradiance fraction from PVGIS MRcalc.
    Returns list of 12 dicts: {month, diffuse_fraction, global_wh_m2, diffuse_wh_m2}
    or None on failure.
    PVGIS MRcalc returns monthly average daily irradiation in Wh/m2/day.
    """
    if pvgis_db is None:
        pvgis_db = auto_select_pvgis_db(lat, lon)
    params = {
        'lat': lat, 'lon': lon,
        'raddatabase': pvgis_db,
        'outputformat': 'json',
    }
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; SALVISolar/1.0)'}
    try:
        resp = requests.get(f"{PVGIS_BASE}/MRcalc", params=params,
                            headers=headers, timeout=20)
        if not resp.ok:
            return None
        data = resp.json()
        monthly_raw = (data.get('outputs', {})
                           .get('monthly', {})
                           .get('fixed', []))
        result = []
        for m in monthly_raw[:12]:
            h_h = float(m.get('H(h)', 0))
            h_d = float(m.get('Hd(h)', 0))
            frac = round(h_d / h_h, 3) if h_h > 0 else 0.45
            result.append({
                'month': int(m.get('month', 0)),
                'diffuse_fraction': frac,
                'global_wh_m2': round(h_h, 1),
                'diffuse_wh_m2': round(h_d, 1),
            })
        return result if len(result) == 12 else None
    except Exception:
        return None
