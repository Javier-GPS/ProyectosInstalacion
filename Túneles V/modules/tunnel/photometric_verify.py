"""
modules/tunnel/photometric_verify.py
=====================================
CIE 140:2019 photometric verification for APHEX tunnel zone designs.

After design_aphex_tunnel() selects luminaires for each zone using the
inside-out UF-table algorithm, this module verifies the actual luminance
quality (L_avg, U0, Ul, TI) using the full CIE 140:2019 point-by-point
calculation with real LDT angular distributions and CIE 144:2001 r-tables.

All S/M/L APHEX models share the same photometric distribution (same optics
F2MD/F2M2/F151). The LDT files for APHEX M are used as reference; flux is
scaled to the operating point of each zone's selected luminaire.

Road surface -> r-table mapping (CIE 144:2001):
    dark_asphalt   -> R3
    medium_asphalt -> R2
    light_asphalt  -> R1
    concrete       -> C1
    bright_concrete-> C2
"""
from __future__ import annotations

import sys
import math
import time
import numpy as np
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

# ── Resolve project root so photometric_engine is importable ─────────────────
_HERE        = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[2]          # .../CALCULO FOTOMETRICO SALVI/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_LDT_DIR = _PROJECT_ROOT / "photometric_engine" / "data" / "photometries"

# ── Road surface → CIE 144 r-table ──────────────────────────────────────────
_SURFACE_RTABLE: dict[str, str] = {
    "dark_asphalt":    "R3",
    "medium_asphalt":  "R2",
    "light_asphalt":   "R1",
    "concrete":        "C1",
    "bright_concrete": "C2",
}

# ── Optic → APHEX M LDT filename (all models share the same distribution) ───
_OPTIC_LDT: dict[str, str] = {
    "F2MD": "APHEX_M_H10_40K_F2MD_VDR_SPUW_200W.ldt",
    "F2M2": "APHEX_M_H10_40K_F2M2_VDR_SPUW_200W.ldt",
    "F151": "APHEX_M_H10_40K_F151_VDR_SPUW_200W.ldt",
}

# CIE 140 compliance thresholds
_U0_MIN  = 0.40
_UL_MIN  = 0.60
_TI_MAX  = 15.0

_REACH_CACHE: dict = {}


def _lane_layout(params: dict, road_width_m: float) -> dict:
    """Geometría única de carriles para malla, observadores y resultados."""
    width = max(0.1, float(road_width_m))
    n_lanes = max(1, int(params.get("num_lanes", 1) or 1))
    lane_width = max(
        0.1, float(params.get("lane_width_m", width / n_lanes) or 0.1),
    )
    shoulder_left = max(
        0.0, float(params.get("shoulder_left_m", 0.0) or 0.0),
    )
    shoulder_right = max(
        0.0, float(params.get("shoulder_right_m", 0.0) or 0.0),
    )
    # La anchura de túnel es pared-a-pared. Las aceras/pasos técnicos son
    # geometría física, pero quedan fuera de la calzada CIE 140 (L, U0, Ul).
    sidewalk_left = max(
        0.0, float(params.get("sidewalk_left_m", 0.0) or 0.0),
    )
    sidewalk_right = max(
        0.0, float(params.get("sidewalk_right_m", 0.0) or 0.0),
    )
    carriageway_width = max(0.1, width - sidewalk_left - sidewalk_right)
    available_width = max(0.1, carriageway_width - shoulder_left - shoulder_right)
    if n_lanes * lane_width > available_width + 1e-6:
        lane_width = available_width / n_lanes
    elif (
        shoulder_left + shoulder_right <= 1e-9
        and n_lanes * lane_width < carriageway_width
    ):
        shoulder_left = (carriageway_width - n_lanes * lane_width) / 2.0
        shoulder_right = carriageway_width - shoulder_left - n_lanes * lane_width

    lane_starts = [
        sidewalk_left + shoulder_left + lane_index * lane_width
        for lane_index in range(n_lanes)
    ]
    lane_centres = [
        lane_start + lane_width / 2.0 for lane_start in lane_starts
    ]
    transverse_points = [
        lane_start + (point_index + 0.5) * lane_width / 3.0
        for lane_start in lane_starts
        for point_index in range(3)
    ]
    # La malla normativa se limita estrictamente a los carriles de circulación.
    # Los arcenes son parte de la geometría física, no de L/U0/Ul CIE 140;
    # las aceras quedan igualmente excluidas y se tratan con criterios propios.
    # Se conserva la clave de salida por compatibilidad con resultados previos.
    shoulder_centres = []
    return {
        "width_m": width,
        "carriageway_width_m": carriageway_width,
        "carriageway_start_m": sidewalk_left,
        "carriageway_end_m": sidewalk_left + carriageway_width,
        "num_lanes": n_lanes,
        "lane_width_m": lane_width,
        "shoulder_left_m": shoulder_left,
        "shoulder_right_m": shoulder_right,
        "sidewalk_left_m": sidewalk_left,
        "sidewalk_right_m": sidewalk_right,
        "lane_starts_m": lane_starts,
        "lane_centres_m": lane_centres,
        "transverse_points_m": transverse_points,
        "shoulder_centres_m": shoulder_centres,
        "includes_shoulders": bool(shoulder_centres),
    }


def _max_reach_for_h(H: float) -> float:
    """Distancia [m] mas alla de la cual NINGUNA de las opticas Aphex
    contribuye de forma apreciable a esta altura de montaje — envolvente
    conservadora (maximo de las 3 opticas) usada como max_luminaire_dist,
    para que el corte de luminarias lejanas coincida con el mismo criterio
    fotometrico que ya usa el diseño (ver optimizer._reach_for). Una zona
    puede usar cualquiera de las 3 opticas, y aqui no sabemos cual sin
    reconstruir antes el layout, asi que se toma el maximo de las 3 —
    conservador (nunca corta de menos), no afecta a la precision."""
    key = round(float(H), 2)
    if key not in _REACH_CACHE:
        from photometric_engine.salvi_photometry.ldt_parser import load_ldt
        reaches = []
        for fname in _OPTIC_LDT.values():
            try:
                reaches.append(load_ldt(_LDT_DIR / fname).reach_distance(float(H)))
            except Exception:
                continue
        _REACH_CACHE[key] = max(reaches) if reaches else 300.0
    return _REACH_CACHE[key]

# Diffuse reflectance of road surface (Lambertian component, for radiosity)
_RHO_ROAD: dict[str, float] = {
    "dark_asphalt":    0.07,
    "medium_asphalt":  0.10,
    "light_asphalt":   0.15,
    "concrete":        0.28,
    "bright_concrete": 0.40,
}


def _wall_luminance_criterion(params: dict) -> dict:
    """Criterio CIE 88 para la franja baja de ambas paredes.

    Clases 2 y 3: 60 % de la luminancia media de calzada; clase 4: 100 %;
    clase 1: 25 %. El proyecto puede fijar otro valor, que se identifica como
    tal en la salida para no confundirlo con la referencia normativa.
    """
    try:
        tunnel_class = int(params.get("tunnel_class", 2) or 2)
    except (TypeError, ValueError):
        tunnel_class = 2
    automatic = {1: 0.25, 2: 0.60, 3: 0.60, 4: 1.00}.get(
        tunnel_class, 0.60,
    )
    raw_override = params.get("wall_ratio_override")
    override = None
    if raw_override not in (None, ""):
        try:
            override = float(str(raw_override).replace(",", "."))
        except (TypeError, ValueError):
            override = None
    ratio = override if override is not None else automatic
    if not 0.05 <= ratio <= 2.0:
        raise ValueError("El ratio pared/calzada debe estar entre 0,05 y 2,00")
    try:
        height_m = float(params.get("wall_luminance_height_m", 2.0) or 2.0)
    except (TypeError, ValueError):
        height_m = 2.0
    return {
        "ratio": ratio,
        "ratio_automatic": automatic,
        "height_m": min(max(height_m, 0.25), 3.0),
        "source": "project_override" if override is not None else "cie88_class",
        "tunnel_class": tunnel_class,
    }


def _is_available() -> bool:
    """Check that photometric_engine can be imported."""
    try:
        import photometric_engine.salvi_photometry.ldt_parser  # noqa: F401
        return True
    except ImportError:
        return False


def verify_luminaire_result(lum_result, params: dict, use_radiosity: bool = False) -> dict:
    """
    Run CIE 140:2019 photometric verification for every zone in a
    TunnelLuminaireResult produced by design_aphex_tunnel().

    Parameters
    ----------
    lum_result : TunnelLuminaireResult
        Output of design_aphex_tunnel() / calculate_luminaire_layout().
    params : dict
        Original luminaire params dict (needs mounting_height_m, maintenance_factor).

    Returns
    -------
    dict with structure:
        {
          "available": bool,
          "error": str | None,
          "rtable": "R2",
          "zones": {
            "CIN": {
              "L_avg": 12.94, "L_min": 7.45,
              "U0": 0.576, "Ul": 0.970, "TI": 1.3,
              "E_h_avg": 165.3,
              "compliant": true, "L_req": 10.0,
              "checks": {"L_avg": true, "U0": true, "Ul": true, "TI": true}
            },
            ...
          },
          "overall_compliant": bool
        }
    """
    out: dict = {"available": False, "error": None, "zones": {}, "overall_compliant": False}

    if not _is_available():
        out["error"] = "photometric_engine no disponible (importación fallida)"
        return out

    try:
        from photometric_engine.salvi_photometry.ldt_parser import load_ldt
        from photometric_engine.salvi_photometry.geometry   import (
            Observer, mirror_c_for_interior_facing,
        )
        from photometric_engine.salvi_photometry.calculator import TunnelCalculator, LuminaireInstance, LuminaireOrientation
        from photometric_engine.salvi_photometry.radiosity  import TunnelSection, build_patches, solve_radiosity, indirect_illuminance_on_road
    except ImportError as exc:
        out["error"] = f"Error importando photometric_engine: {exc}"
        return out

    # ── Parámetros generales ─────────────────────────────────────────────────
    # NOTA: cada zona puede haber sido diseñada con una óptica distinta
    # (Umbral/Transición se optimizan independientemente de Interior y pueden
    # elegir F2M2/F2MD/F151 diferentes) — lum_result.optic es solo la óptica
    # de la zona Interior, usada aquí unicamente como fallback si a una zona
    # le faltara el campo. Usar siempre zd.optic por zona (ver _phot() abajo)
    # es lo que corrige que la verificación CIE 140 comprobara la distribución
    # fotométrica equivocada en zonas con óptica distinta a la de Interior.
    optic   = lum_result.optic or "F2MD"
    surface = lum_result.road_surface_type or "medium_asphalt"
    rtable  = _SURFACE_RTABLE.get(surface, "R2")
    W       = float(lum_result.road_width_m)
    H       = float(params.get("mounting_height_m", 5.0))
    mf      = float(params.get("maintenance_factor", 0.70))
    wall_criterion = _wall_luminance_criterion(params)
    wall_height_m = min(float(wall_criterion["height_m"]), max(0.25, H - 0.05))
    rho_wall = min(max(float(params.get("rho_wall", 0.40) or 0.40), 0.01), 0.95)

    # ── LDT por óptica, cacheado (cada zona puede usar una distinta) ─────────
    _phot_cache: dict = {}

    def _phot(optic_id: str):
        oid = optic_id or optic
        if oid not in _phot_cache:
            fname = _OPTIC_LDT.get(oid, _OPTIC_LDT["F2MD"])
            fpath = _LDT_DIR / fname
            if not fpath.exists():
                raise FileNotFoundError(f"LDT no encontrado: {fname}")
            _phot_cache[oid] = load_ldt(fpath)
        return _phot_cache[oid]

    try:
        _phot(optic)   # valida que la óptica por defecto carga correctamente
    except Exception as exc:
        out["error"] = str(exc)
        return out

    calc = TunnelCalculator(rtable, mf, max_luminaire_dist=_max_reach_for_h(H))
    # Observer at road centre, 60 m ahead (CIE 140 §6.2.2). El sentido de
    # circulacion se fija por zona mas abajo (zonas "_b" = trafico entrando
    # por el portal B, observador 60 m por delante en -x en vez de +x).
    def _obs_for_zone(zd_obj) -> "Observer":
        zt = str(getattr(zd_obj, "zone_type", "") or "")
        direction = -1.0 if zt.endswith("_b") else 1.0
        return Observer(lane_y_m=W / 2, d_observer_m=60.0, direction=direction)

    out["available"] = True
    out["rtable"]    = rtable
    out["optic"]     = optic
    out["H_m"]       = H

    zone_results: dict = {}
    all_compliant = True

    for zd in lum_result.zones:
        if zd.n_luminaires <= 0 or zd.zone_length <= 0:
            continue

        S        = float(zd.d_used)
        flux_lm  = float(zd.flux_lm)
        L_req    = float(zd.L_required)
        zone_key = zd.zone_name

        if S <= 0.1 or flux_lm <= 0:
            continue

        try:
            zone_phot = _phot(getattr(zd, "optic", None))
        except Exception as exc:
            zone_results[zone_key] = {"error": str(exc), "compliant": False}
            all_compliant = False
            continue

        # ── Luminaire array: replicas suficientes para cubrir el alcance real
        #    de esta optica a esta altura (ver Photometry.reach_distance) ────
        n_side  = max(2, math.ceil(zone_phot.reach_distance(H) / max(S, 0.1)))
        WALL_Y  = float(params.get('wall_offset_m', 0.30))  # m from wall to luminaire
        arr     = params.get('arrangement', 'central_single') or 'central_single'

        # ── Tandem support: 2 physical luminaires per position, offset along x ──
        # ZoneLuminaireDesign.n_tandem==2 means each nominal position i*S actually
        # holds a real A/B pair separated by tandem_offset_m (each carrying zd.flux_lm,
        # matching the per-unit flux convention used when the zone was designed).
        is_tandem   = int(getattr(zd, 'n_tandem', 1) or 1) == 2
        tandem_off  = float(getattr(zd, 'tandem_offset_m', 0.0) or 0.0)

        def _x_positions(i: int) -> list:
            """Physical x offsets for nominal position i (single, or A/B tandem pair)."""
            if is_tandem and tandem_off > 0:
                return [i * S - tandem_off / 2.0, i * S + tandem_off / 2.0]
            return [i * S]

        tilt_base = float(getattr(zd, "tilt_deg", 0) or 0)

        # El tilt (rotacion transversal, CIE 140 Anexo A) se espeja segun el
        # lado: cada fila se inclina hacia el eje del tunel, nunca ambas hacia
        # el mismo lado — igual que optimizer._build_lums y la vista previa.
        def _tilt_for_y(y_pos: float) -> float:
            return tilt_base if y_pos < W / 2 else -tilt_base

        if arr in ('bilateral_stag', 'staggered'):
            # Alternating sides: even index → left wall, odd → right wall
            lums = [
                LuminaireInstance(
                    x           = x_p,
                    y           = (y_pos := (WALL_Y if abs(i) % 2 == 0 else W - WALL_Y)),
                    H           = H,
                    photometry  = zone_phot,
                    flux_lm     = flux_lm,
                    orientation = LuminaireOrientation(
                        tilt_deg=_tilt_for_y(y_pos),
                        mirror_c=mirror_c_for_interior_facing(y_pos, W, arr),
                    ),
                )
                for i in range(-n_side, n_side + 1)
                for x_p in _x_positions(i)
            ]
        else:
            # Determine y positions per arrangement
            if arr == 'lateral_left':
                ys = [WALL_Y]
            elif arr in ('lateral_right', 'unilateral'):
                ys = [W - WALL_Y]
            elif arr == 'bilateral_sym':
                ys = [WALL_Y, W - WALL_Y]
            elif arr == 'central_double':
                ys = [WALL_Y, W - WALL_Y]
            elif arr == 'central_offset':
                ys = [WALL_Y]
            else:                        # central_single / auto
                ys = [W / 2]
            lums = [
                LuminaireInstance(
                    x           = x_p,
                    y           = y,
                    H           = H,
                    photometry  = zone_phot,
                    flux_lm     = flux_lm,
                    orientation = LuminaireOrientation(
                        tilt_deg=_tilt_for_y(y),
                        mirror_c=mirror_c_for_interior_facing(y, W, arr),
                    ),
                )
                for i in range(-n_side, n_side + 1)
                for y in ys
                for x_p in _x_positions(i)
            ]

        # ── CIE 140 §6.3 calculation grid over one representative span ───────
        n_long, n_trans = 10, 5
        xs  = [(-S / 2) + (i + 0.5) * S / n_long for i in range(n_long)]
        ys  = [(j + 0.5) * W / n_trans             for j in range(n_trans)]
        pts = [(x, y) for x in xs for y in ys]

        try:
            zr = calc.calculate_zone(
                zone_name   = zd.zone_type,
                zone_type   = zd.zone_type,
                s_start     = -S / 2,
                s_end       =  S / 2,
                L_req       = L_req,
                calc_points = pts,
                luminaires  = lums,
                observer    = _obs_for_zone(zd),
            )
            # ── Optional radiosity pass ───────────────────────────────────
            L_indirect = 0.0
            rad_info = {}
            if use_radiosity:
                try:
                    import math as _math
                    rho_road    = _RHO_ROAD.get(surface, 0.10)
                    rho_wall    = float(params.get('rho_wall',    0.40))
                    rho_ceiling = float(params.get('rho_ceiling', 0.25))
                    H_t         = float(params.get('height_m', H + 1.0))
                    section = TunnelSection(
                        width_m=W, height_m=H_t,
                        rho_road=rho_road, rho_wall=rho_wall,
                        rho_ceiling=rho_ceiling,
                    )
                    patches = build_patches(section)
                    # Compute direct E on each patch from luminaire array
                    n_side_rad = 5
                    for p in patches:
                        e_direct = 0.0
                        for lum in lums:
                            for xi in range(-n_side_rad, n_side_rad+1):
                                x_l = lum.x + xi * S
                                dy = p.y_center - lum.y
                                dz = p.z_center - lum.H
                                dx = 0.0 - x_l
                                r2 = dx*dx + dy*dy + dz*dz
                                if r2 < 0.01: continue
                                r  = _math.sqrt(r2)
                                # cos of angle of incidence on patch
                                cos_inc = -(dy*p.normal[0] + dz*p.normal[1]) / r
                                if cos_inc <= 0: continue
                                # photometric angles (3D generalization)
                                d_plan = _math.sqrt(dx*dx + dy*dy)
                                g_rad  = _math.atan2(d_plan, max(0.001, lum.H - p.z_center))
                                g_deg  = _math.degrees(g_rad)
                                c_deg  = (_math.degrees(_math.atan2(dy, dx)) + 360) % 360
                                I_cd   = lum.photometry.intensity(c_deg, g_deg,
                                            scale_flux_lm=lum.flux_lm)
                                e_direct += I_cd * cos_inc / r2 * mf
                        p.E_direct = e_direct
                    solve_radiosity(patches)
                    # Indirect luminance on road = E_indirect * rho_road / pi
                    y_pts = list(set(yP for _, yP in pts))
                    e_ind_avg = _math.fsum(
                        indirect_illuminance_on_road(patches, yP) for yP in y_pts
                    ) / max(1, len(y_pts))
                    L_indirect = e_ind_avg * rho_road / _math.pi
                    rad_info = {
                        'rho_wall': rho_wall, 'rho_ceiling': rho_ceiling,
                        'L_indirect': round(L_indirect, 3),
                        'pct': round(100*L_indirect/max(zr.L_avg,0.01), 1),
                    }
                except Exception as rad_err:
                    rad_info = {'error': str(rad_err)}

            # La celda periodica de la zona sigue siendo la referencia para
            # U0/Ul/TI. Para L, en cambio, usar el cierre del layout fisico
            # completo cuando este disponible: en transicion la contribucion
            # de las zonas vecinas es real y una celda aislada puede declarar
            # falsamente Lavg<Lreq aunque el perfil completo cumpla.
            profile_L_avg = getattr(zd, "profile_L_avg", None)
            profile_L_min = getattr(zd, "profile_L_min", None)
            profile_ratio = getattr(zd, "profile_min_ratio", None)
            has_profile = profile_L_avg is not None and profile_ratio is not None

            L_direct_display = float(profile_L_avg) if has_profile else zr.L_avg
            L_min_direct_display = (
                float(profile_L_min)
                if has_profile and profile_L_min is not None
                else zr.L_min
            )
            L_avg_total = L_direct_display + L_indirect
            L_min_total = L_min_direct_display + L_indirect

            # La uniformidad no se calcula sobre todo el gradiente de una
            # transicion; se conserva la rejilla CIE 140 de la celda local.
            U0_rad = (
                (zr.L_min + L_indirect) / (zr.L_avg + L_indirect)
                if zr.L_avg + L_indirect > 0 else zr.U0
            )
            Ul_rad = zr.Ul  # Ul shape unchanged by uniform indirect term

            L_ok = (
                float(profile_ratio) >= 0.995
                if has_profile
                else (L_avg_total >= L_req if L_req > 0 else True)
            )
            U0_ok = U0_rad >= _U0_MIN
            Ul_ok = Ul_rad >= _UL_MIN
            TI_ok = zr.TI  <= _TI_MAX

            compliant = all([L_ok, U0_ok, Ul_ok, TI_ok])
            if not compliant:
                all_compliant = False

            zone_results[zone_key] = {
                "L_avg":      round(L_avg_total, 2),
                "L_min":      round(L_min_total, 2),
                "L_direct":   round(L_direct_display, 2),
                "L_indirect": round(L_indirect, 3),
                "U0":         round(U0_rad, 3),
                "Ul":         round(Ul_rad, 3),
                "TI":         round(zr.TI,  1),
                "E_h_avg":    round(zr.E_h_avg, 1),
                "L_req":      round(L_req, 1),
                "profile_min_ratio": round(float(profile_ratio), 4) if has_profile else None,
                "compliant":  compliant,
                "radiosity":  rad_info,
                "checks": {
                    "L_avg": L_ok,
                    "U0":    U0_ok,
                    "Ul":    Ul_ok,
                    "TI":    TI_ok,
                },
            }
        except Exception as exc:
            zone_results[zone_key] = {
                "error": str(exc),
                "compliant": False,
            }
            all_compliant = False

    out["zones"]            = zone_results
    out["overall_compliant"] = all_compliant and bool(zone_results)
    return out


def compute_real_luminance_profile(
    lum_result,
    params: dict,
    road_width_m: float,
    step_size: float = 1.0,
    *,
    include_quality_metrics: bool = True,
    include_ti: bool | None = None,
    include_wall_metrics: bool | None = None,
    _influence_cache: dict | None = None,
) -> dict:
    """
    Perfil normativo Lavg(s). Cada valor es la media aritmetica de una malla
    bidimensional CIE 140 completa: N puntos longitudinales y tres puntos
    transversales por carril. Se calcula con cada observador de carril y se
    representa el caso mas desfavorable, usando el layout fisico completo.

    ``include_quality_metrics=False`` se reserva para iteraciones internas
    que cierran exclusivamente Lavg (por ejemplo, la BASE permanente antes
    de congelar su flujo). La comprobacion final y todas las graficas siguen
    usando la malla completa con U0, Ul, TI y paredes.
    """
    profile_started = time.perf_counter()
    if include_ti is None:
        include_ti = bool(include_quality_metrics)
    if include_wall_metrics is None:
        include_wall_metrics = bool(include_quality_metrics)
    _ = step_size  # Conservado por compatibilidad con la API anterior.
    out: dict = {"available": False, "error": None, "points": []}

    if not _is_available():
        out["error"] = "photometric_engine no disponible (importación fallida)"
        return out

    try:
        from photometric_engine.salvi_photometry.ldt_parser import load_ldt
        from photometric_engine.salvi_photometry.geometry   import (
            Observer, LuminaireOrientation, luminaire_to_point_angles,
            luminaire_to_point_angles_batch, mirror_c_for_interior_facing,
        )
        from photometric_engine.salvi_photometry.calculator import TunnelCalculator, LuminaireInstance
    except ImportError as exc:
        out["error"] = f"Error importando photometric_engine: {exc}"
        return out

    surface = lum_result.road_surface_type or "medium_asphalt"
    rtable  = _SURFACE_RTABLE.get(surface, "R2")
    W       = float(road_width_m)
    H       = float(params.get("mounting_height_m", 5.0))
    mf      = float(params.get("maintenance_factor", 0.70))
    arr     = params.get('arrangement', 'central_single') or 'central_single'
    WALL_Y  = float(params.get('wall_offset_m', 0.30))
    wall_criterion = _wall_luminance_criterion(params)
    wall_height_m = min(
        float(wall_criterion["height_m"]), max(0.25, H - 0.05),
    )
    rho_wall = min(max(float(params.get("rho_wall", 0.40) or 0.40), 0.01), 0.95)

    if arr == 'lateral_left':
        ys_default = [WALL_Y]
    elif arr in ('lateral_right', 'unilateral'):
        ys_default = [W - WALL_Y]
    elif arr in ('bilateral_sym', 'bilateral', 'staggered'):
        ys_default = [WALL_Y, W - WALL_Y]
    elif arr == 'central_double':
        ys_default = [WALL_Y, W - WALL_Y]
    elif arr == 'central_offset':
        ys_default = [WALL_Y]
    else:
        ys_default = [W / 2]

    _phot_cache: dict = {}

    def _phot(optic: str):
        if optic not in _phot_cache:
            fname = _OPTIC_LDT.get(optic, _OPTIC_LDT["F2MD"])
            _phot_cache[optic] = load_ldt(_LDT_DIR / fname)
        return _phot_cache[optic]

    def _tilt_for_y(tilt_base: float, y_pos: float) -> float:
        return tilt_base if y_pos < W / 2 else -tilt_base

    # ── Reconstruir el layout físico completo del túnel a partir de los
    #    setpoints reales de cada zona (posición, óptica, tilt, flujo) ──────
    lums: list = []
    # Posiciones por capa/zona y fila fisica. En un tunel con BASE permanente
    # y refuerzos solapados no se puede formar un campo CIE 140 mezclando las
    # posiciones de todas las capas: un refuerzo a 0,5 m de una BASE crearia
    # artificialmente un "campo" de 0,5 m. Cada campo se define por dos
    # luminarias consecutivas de la disposicion que gobierna ese tramo.
    zone_row_positions: dict[int, dict[float, list[float]]] = {}

    def _register_row_position(zone, y_pos: float, x_pos: float) -> None:
        rows = zone_row_positions.setdefault(id(zone), {})
        rows.setdefault(round(float(y_pos), 4), []).append(float(x_pos))

    tube_length = 0.0
    try:
        for zd in lum_result.zones:
            if zd.n_luminaires <= 0:
                continue
            tube_length = max(tube_length, float(getattr(zd, 's_end', 0) or 0))
            sps = zd.setpoints or []
            for sp in sps:
                x_pos    = float(sp['s'])
                optic_id = sp.get('optic') or 'F2MD'
                flux     = float(sp.get('flux_lm', 0) or 0)
                tilt0    = float(sp.get('tilt_deg', 0) or 0)
                if flux <= 0:
                    continue
                if arr in ('bilateral_stag', 'staggered'):
                    # Lado alternado por índice de posición física (par A/B
                    # incluido, ya expandido en 's' individuales).
                    y_pos = WALL_Y if (sp.get('idx', 1) - 1) % 2 == 0 else (W - WALL_Y)
                    lums.append(LuminaireInstance(
                        x=x_pos, y=y_pos, H=H, photometry=_phot(optic_id), flux_lm=flux,
                        orientation=LuminaireOrientation(
                            tilt_deg=_tilt_for_y(tilt0, y_pos),
                            mirror_c=mirror_c_for_interior_facing(y_pos, W, arr),
                        ),
                    ))
                    _register_row_position(zd, y_pos, x_pos)
                else:
                    for y_pos in ys_default:
                        lums.append(LuminaireInstance(
                            x=x_pos, y=y_pos, H=H, photometry=_phot(optic_id), flux_lm=flux,
                            orientation=LuminaireOrientation(
                                tilt_deg=_tilt_for_y(tilt0, y_pos),
                                mirror_c=mirror_c_for_interior_facing(y_pos, W, arr),
                            ),
                        ))
                        _register_row_position(zd, y_pos, x_pos)
    except Exception as exc:
        out["error"] = f"Error reconstruyendo el layout de luminarias: {exc}"
        return out

    if not lums or tube_length <= 0:
        out["error"] = "Sin luminarias posicionadas para calcular el perfil"
        return out

    # Cache de influencia: la luminancia es lineal en el flujo. La parte
    # geometrica (posiciones, optica, orientacion, r-tabla) no depende de
    # la corriente, asi que la matriz punto x luminaria por unidad de flujo
    # se reutiliza entre verificaciones del optimizador que solo cambian
    # corrientes. La firma no incluye el flujo: si cambia una posicion,
    # optica o el estado ON/OFF, la firma cambia y se recalcula.
    _influence_flux = np.asarray(
        [float(l.flux_lm) for l in lums], dtype=float,
    )
    _influence_sig = None
    if _influence_cache is not None:
        _influence_sig = (
            arr, round(W, 4), round(WALL_Y, 4), round(H, 4),
            tuple(
                (
                    round(float(sp['s']), 6),
                    int(sp.get('idx', 0) or 0),
                    sp.get('optic') or 'F2MD',
                    round(float(sp.get('tilt_deg', 0) or 0), 4),
                    str(getattr(zd, 'zone_name', '')),
                )
                for zd in lum_result.zones
                for sp in (zd.setpoints or [])
                if float(sp.get('flux_lm', 0) or 0) > 0
            ),
        )

    calc = TunnelCalculator(rtable, mf, max_luminaire_dist=_max_reach_for_h(H))

    # Sentido de circulacion por zona: las zonas "_b" (transition_b,
    # threshold_b) son trafico entrando por el portal B, que viaja en -x, asi
    # que su observador CIE 140 (60 m "por delante") va en -x en vez de +x —
    # ver Observer.direction. Sin esto, el beta usado para TODO el tunel
    # asumia trafico A->B tambien en las zonas ancladas a B, sesgando
    # sistematicamente su luminancia calculada (la tabla r no es simetrica
    # en beta).
    zones_sorted = sorted(lum_result.zones, key=lambda z: float(z.s_start))

    def _zone_for_s(s_val):
        matches = [
            zone for zone in zones_sorted
            if float(zone.s_start) - 1e-6
            <= s_val
            <= float(zone.s_end) + 1e-6
        ]
        if not matches:
            return None
        # La BASE A–B solapa deliberadamente todas las zonas. Para etiquetar
        # el campo se prioriza la zona normativa/refuerzo; la BASE gobierna
        # únicamente donde no existe otra zona interior.
        normative = [
            zone for zone in matches
            if str(getattr(zone, "control_layer", "legacy") or "legacy")
            != "permanent"
        ]
        if normative:
            return max(
                normative,
                key=lambda zone: float(
                    getattr(zone, "L_total_required", None)
                    or getattr(zone, "L_required", 0.0)
                    or 0.0
                ),
            )
        return matches[0]

    def _direction_for_zone(zd_obj) -> float:
        zt = str(getattr(zd_obj, "zone_type", "") or "") if zd_obj is not None else ""
        return -1.0 if zt.endswith("_b") else 1.0

    # ── Lavg CIE 140 a lo largo del tunel ─────────────────────────────────
    # Lth/Ltr/Lin son luminancias medias sobre un campo de evaluacion. Cada
    # ordenada debe proceder de una malla bidimensional completa, nunca de la
    # media transversal de una sola seccion.
    # CIE 140: tres puntos transversales por carril. Los arcenes quedan fuera
    # de la malla de luminancia de la calzada.
    _N_LONG_PROFILE = 10
    _lanes = _lane_layout(params, W)
    _n_lanes = _lanes["num_lanes"]
    _lane_width = _lanes["lane_width_m"]
    _shoulder_left = _lanes["shoulder_left_m"]
    _shoulder_right = _lanes["shoulder_right_m"]
    _lane_starts = _lanes["lane_starts_m"]
    _lane_centres = _lanes["lane_centres_m"]
    _quality_centrelines = _lane_centres + _lanes["shoulder_centres_m"]
    _ys_profile = _lanes["transverse_points_m"]
    _N_TRANS_PROFILE = len(_ys_profile)
    _has_portal_b = any(
        str(getattr(zone, "zone_type", "") or "").endswith("_b")
        for zone in lum_result.zones
    ) or str(params.get("traffic_direction", "one_way")) == "two_way"

    def _directions_for_zone(zd_obj) -> list[float]:
        zone_type = str(
            getattr(zd_obj, "zone_type", "") or "",
        ).lower()
        if _has_portal_b and "interior" in zone_type:
            return [1.0, -1.0]
        return [_direction_for_zone(zd_obj)]

    def _observers_for_direction(direction: float):
        return [
            (
                lane_index,
                Observer(
                    lane_y_m=lane_y,
                    d_observer_m=60.0,
                    direction=direction,
                ),
            )
            for lane_index, lane_y in enumerate(_lane_centres)
        ]

    def _n_long_for_spacing(spacing: float) -> int:
        return 10 if spacing <= 30.0 else int(math.ceil(spacing / 3.0))

    def _has_field_intervals(zone) -> bool:
        """Indica si una capa activa puede definir sus propios campos.

        En una escena de bajo nivel los refuerzos de umbral/transición pueden
        estar apagados. La BASE sigue iluminando esos metros, pero la etiqueta
        normativa debe seguir siendo la del umbral o la transición. No se debe
        perder entonces la serie CIE 140 de la BASE sólo porque no sea la capa
        que etiqueta el requisito en ese punto.
        """
        return any(
            len(set(positions)) >= 2
            for positions in zone_row_positions.get(id(zone), {}).values()
        )

    # ── Campos de calculo normativos ───────────────────────────────────────
    # CIE 140 define la Lavg de un campo comprendido entre dos luminarias
    # consecutivas de una misma fila. Por tanto la representacion longitudinal
    # es una sucesion de resultados de campo, no una media transversal ni una
    # malla deslizante arbitraria cada `step_size` metros.
    interval_sources: dict[tuple[int, float, float], set[float]] = {}
    for zone in zones_sorted:
        for row_y, positions in zone_row_positions.get(id(zone), {}).items():
            ordered = sorted(set(round(x, 6) for x in positions))
            for field_start, field_end in zip(ordered, ordered[1:]):
                if field_end - field_start <= 0.05:
                    continue
                field_centre = (field_start + field_end) / 2.0
                # En los solapes se conserva el refuerzo activo. Si el
                # refuerzo está apagado (por ejemplo, crepúsculo), la BASE
                # debe seguir proporcionando sus intervalos físicos para que
                # no desaparezca Lcalc en ese tramo.
                governing_zone = _zone_for_s(field_centre)
                if governing_zone is None:
                    continue
                if (
                    governing_zone is not zone
                    and _has_field_intervals(governing_zone)
                ):
                    continue
                key = (id(zone), field_start, field_end)
                interval_sources.setdefault(key, set()).add(row_y)

    fields = []
    for (zone_id, raw_start, raw_end), source_rows in sorted(
        interval_sources.items(), key=lambda item: (item[0][1], item[0][2])
    ):
        field_start = max(0.0, float(raw_start))
        field_end = min(float(tube_length), float(raw_end))
        if field_end - field_start <= 0.05:
            continue
        field_centre = (field_start + field_end) / 2.0
        # ``source_zone`` es la fila física que proporciona las dos
        # luminarias consecutivas; ``governing_zone`` aporta el requisito CIE
        # y el sentido de observación. Normalmente son la misma zona. Cuando
        # el refuerzo está apagado, se permite que la BASE forme el campo pero
        # se conserva la etiqueta normativa del tramo. Así Lcalc aparece
        # también en todo el umbral/transición crepuscular y nocturno.
        source_zone = next(
            (zone for zone in zones_sorted if id(zone) == zone_id), None,
        )
        governing_zone = _zone_for_s(field_centre)
        if source_zone is None or governing_zone is None:
            continue
        if (
            governing_zone is not source_zone
            and _has_field_intervals(governing_zone)
        ):
            continue
        spacing = field_end - field_start
        n_long = _n_long_for_spacing(spacing)
        xs = [
            field_start + (j + 0.5) * spacing / n_long
            for j in range(n_long)
        ]
        fields.append({
            "s": field_centre,
            "field_start": field_start,
            "field_end": field_end,
            "spacing": spacing,
            "source_rows": tuple(sorted(source_rows)),
            "zone": governing_zone,
            "source_zone": source_zone,
            "points": [(x, y) for x in xs for y in _ys_profile],
            "directions": _directions_for_zone(governing_zone),
            "observer_results": [],
        })

    if not fields:
        out["error"] = "No hay dos posiciones consecutivas para formar un campo CIE 140"
        return out

    # Los campos interiores de una zona estrictamente periodica son
    # traslaciones exactas. Se resuelve uno por cada fase/fila y se reutiliza;
    # los bordes y toda configuracion variable se calculan individualmente.
    uniform_zones: set[int] = set()
    for zone in lum_result.zones:
        sps = zone.setpoints or []
        if len(sps) < 4:
            continue
        fluxes = {round(float(sp.get("flux_lm", 0) or 0), 1) for sp in sps}
        tilts = {round(float(sp.get("tilt_deg", 0) or 0), 2) for sp in sps}
        optics = {sp.get("optic") or "F2MD" for sp in sps}
        spacings = {
            round(float(sp.get("spacing_m", zone.d_used) or zone.d_used), 3)
            for sp in sps
        }
        if len(fluxes) == len(tilts) == len(optics) == len(spacings) == 1:
            uniform_zones.add(id(zone))

    representative_by_key: dict[tuple, int] = {}
    aliases: dict[int, int] = {}
    solve_indices: list[int] = []
    buffer = calc.max_lum_dist
    foreign_positions_by_zone: dict[int, list[float]] = {}
    for zone in zones_sorted:
        foreign_positions_by_zone[id(zone)] = [
            float(position)
            for other in zones_sorted
            if other is not zone
            for positions in zone_row_positions.get(id(other), {}).values()
            for position in positions
        ]

    def _has_foreign_luminaire_in_reach(field) -> bool:
        """Un campo repetible debe estar libre de capas no periodicas.

        La BASE cubre A--B, por lo que mirar solo sus extremos permitia usar
        como representante un campo aun iluminado por el refuerzo de portal.
        Esa L se reutilizaba despues por todo el interior comprimido.
        """
        reach_start = float(field["field_start"]) - buffer
        reach_end = float(field["field_end"]) + buffer
        return any(
            reach_start <= position <= reach_end
            for position in foreign_positions_by_zone.get(
                id(field.get("source_zone", field["zone"])), []
            )
        )

    for index, field in enumerate(fields):
        source_zone = field.get("source_zone", field["zone"])
        safely_periodic = (
            id(source_zone) in uniform_zones
            and field["field_start"] >= float(source_zone.s_start) + buffer
            and field["field_end"] <= float(source_zone.s_end) - buffer
            and not _has_foreign_luminaire_in_reach(field)
        )
        cache_key = None
        if safely_periodic:
            cache_key = (
                id(source_zone),
                round(field["spacing"], 3),
                tuple(round(y, 3) for y in field["source_rows"]),
            )
        if cache_key is not None and cache_key in representative_by_key:
            aliases[index] = representative_by_key[cache_key]
        else:
            solve_indices.append(index)
            if cache_key is not None:
                representative_by_key[cache_key] = index

    # Resolver campos completos en lotes. El minimo de las Lavg obtenidas con
    # todos los observadores de carril y sentidos aplicables es el gobernante.
    batch_calls = 0
    evaluated_points = 0
    for direction in (1.0, -1.0):
        indices = [
            index for index in solve_indices
            if direction in fields[index]["directions"]
        ]
        for chunk_start in range(0, len(indices), 20):
            chunk_indices = indices[chunk_start:chunk_start + 20]
            batch_points = []
            slices = []
            for index in chunk_indices:
                begin = len(batch_points)
                batch_points.extend(fields[index]["points"])
                slices.append((begin, len(batch_points)))
            for observer_lane_index, observer in _observers_for_direction(
                direction,
            ):
                batch_calls += 1
                evaluated_points += len(batch_points)
                if _influence_sig is not None and _influence_cache is not None:
                    key = (
                        _influence_sig, direction, observer_lane_index,
                        chunk_start, len(batch_points),
                    )
                    influence = _influence_cache.get(key)
                    if influence is None:
                        contrib = (
                            calc.luminance_contributions_at_points_batch(
                                batch_points, lums, observer,
                            )
                        )
                        influence = contrib / np.maximum(
                            _influence_flux[None, :], 1e-12,
                        )
                        _influence_cache[key] = influence
                        # Primera llamada: identica a la ruta directa.
                        raw = contrib.sum(axis=1)
                    else:
                        # Re-verificaciones: recombinacion lineal exacta.
                        raw = influence @ _influence_flux
                else:
                    raw = calc.luminance_at_points_batch(
                        batch_points, lums, observer,
                    )
                for index, (begin, end) in zip(chunk_indices, slices):
                    values = np.asarray(raw[begin:end], dtype=float)
                    fields[index]["observer_results"].append({
                        "mean": float(np.mean(values)),
                        "lane_index": observer_lane_index,
                        "lane_y_m": float(observer.lane_y_m),
                        "direction": float(direction),
                        "values": values.tolist(),
                    })

    for alias_index, representative_index in aliases.items():
        # Las series se reutilizan solo en vanos periódicos seguros. Copiar
        # también los valores evita modificar dos campos a la vez al añadir la
        # componente indirecta específica de la radiosidad.
        fields[alias_index]["observer_results"] = [
            {**result, "values": list(result["values"])}
            for result in fields[representative_index]["observer_results"]
        ]

    # Paredes: dos hastiales, desde calzada hasta la altura normativa
    # (2 m por defecto). La luminancia se obtiene a partir de la iluminancia
    # directa LDT sobre la superficie difusa: L = rho * E / pi. Se calcula
    # en cada campo longitudinal, nunca como una media de toda la zona.
    wall_heights = [
        (index + 0.5) * wall_height_m / 4.0 for index in range(4)
    ]

    use_radiosity = str(params.get("calc_mode", "direct")).lower() == "radiosity"
    use_wall_radiosity = use_radiosity
    if use_radiosity:
        from photometric_engine.salvi_photometry.radiosity import (
            TunnelSection, build_patches, solve_radiosity,
            indirect_illuminance_on_road,
        )

    def _surface_illuminance_at(x_pos: float, y_pos: float, z_pos: float,
                                normal_y: float, normal_z: float) -> float:
        """Iluminancia LDT directa sobre una superficie de sección del túnel."""
        illuminance = 0.0
        for lum in lums:
            if abs(float(lum.x) - x_pos) > calc.max_lum_dist:
                continue
            vertical_drop = float(lum.H) - z_pos
            if vertical_drop <= 0.02:
                continue
            dx = x_pos - float(lum.x)
            dy = y_pos - float(lum.y)
            distance_sq = dx * dx + dy * dy + vertical_drop * vertical_drop
            if distance_sq <= 1e-9:
                continue
            distance = math.sqrt(distance_sq)
            cos_incidence = (
                normal_y * (float(lum.y) - y_pos)
                + normal_z * vertical_drop
            ) / distance
            if cos_incidence <= 0.0:
                continue
            angles = luminaire_to_point_angles(
                x_pos, y_pos, float(lum.x), float(lum.y), vertical_drop,
                lum.orientation,
            )
            intensity = lum.photometry.intensity(
                angles.C_deg, angles.gamma_deg, scale_flux_lm=lum.flux_lm,
            )
            illuminance += intensity * cos_incidence / distance_sq * mf
        return illuminance

    def _surface_illuminance_batch(surface_points: list[tuple[float, float, float, float, float]]) -> np.ndarray:
        """Iluminancia directa LDT sobre puntos de pared, vectorizada.

        El calculo previo evaluaba cada punto de pared contra cada luminaria
        en Python. En un perfil largo esa malla domina el tiempo de las
        escenas DALI. Se conserva la misma geometria e interpolacion LDT,
        pero se resuelve por bloques de fotometria y altura de muestra.
        """
        if not surface_points:
            return np.zeros(0, dtype=float)
        values = np.zeros(len(surface_points), dtype=float)
        x_all = np.asarray([item[0] for item in surface_points], dtype=float)
        y_all = np.asarray([item[1] for item in surface_points], dtype=float)
        z_all = np.asarray([item[2] for item in surface_points], dtype=float)
        ny_all = np.asarray([item[3] for item in surface_points], dtype=float)
        nz_all = np.asarray([item[4] for item in surface_points], dtype=float)
        phot_groups: dict[int, list] = {}
        for lum in lums:
            phot_groups.setdefault(id(lum.photometry), []).append(lum)

        for z_value in np.unique(z_all):
            point_indices = np.flatnonzero(np.isclose(z_all, z_value))
            x_pos = x_all[point_indices]
            y_pos = y_all[point_indices]
            ny_pos = ny_all[point_indices]
            nz_pos = nz_all[point_indices]
            for group in phot_groups.values():
                phot = group[0].photometry
                x_lum = np.asarray([float(lum.x) for lum in group], dtype=float)
                y_lum = np.asarray([float(lum.y) for lum in group], dtype=float)
                h_eff = np.asarray(
                    [float(lum.H) - float(z_value) for lum in group],
                    dtype=float,
                )
                flux = np.asarray([float(lum.flux_lm) for lum in group], dtype=float)
                nu = np.asarray([float(lum.orientation.nu_deg) for lum in group], dtype=float)
                tilt = np.asarray([float(lum.orientation.tilt_deg) for lum in group], dtype=float)
                psi = np.asarray([float(lum.orientation.psi_deg) for lum in group], dtype=float)
                mirror_c = np.asarray([bool(lum.orientation.mirror_c) for lum in group], dtype=bool)
                valid_height = h_eff > 0.02
                if not np.any(valid_height):
                    continue
                c_deg, gamma_deg, _tan_gamma = luminaire_to_point_angles_batch(
                    x_pos, y_pos, x_lum, y_lum, h_eff, nu, tilt, psi, mirror_c,
                )
                dx = x_pos[:, None] - x_lum[None, :]
                dy = y_pos[:, None] - y_lum[None, :]
                distance_sq = dx * dx + dy * dy + h_eff[None, :] ** 2
                distance = np.sqrt(np.maximum(distance_sq, 1e-12))
                cos_incidence = (
                    ny_pos[:, None] * (y_lum[None, :] - y_pos[:, None])
                    + nz_pos[:, None] * h_eff[None, :]
                ) / distance
                in_range = np.abs(dx) <= calc.max_lum_dist
                valid = (
                    valid_height[None, :]
                    & in_range
                    & (cos_incidence > 0.0)
                )
                intensity = phot.intensity_batch(
                    c_deg, gamma_deg, scale_flux_lm=flux[None, :],
                )
                values[point_indices] += np.sum(
                    np.where(
                        valid,
                        intensity * cos_incidence / distance_sq * mf,
                        0.0,
                    ),
                    axis=1,
                )
        return values

    def _road_radiosity_for_field(field: dict) -> dict:
        """Resuelve la interreflexión en el centro físico de un campo CIE 140.

        La iluminación directa de cada parche se obtiene de las luminarias
        realmente instaladas, con su LDT, tilt, orientación y corriente. La
        contribución indirecta se evalúa después en cada ordenada transversal
        de la malla CIE 140, para que Lavg, U0, Ul y la planta compartan los
        mismos valores. No se replica una celda periódica ni se traslada un
        incremento constante de una zona a todos sus campos.
        """
        rho_road = _RHO_ROAD.get(surface, 0.10)
        section = TunnelSection(
            width_m=W,
            height_m=float(params.get("height_m", H + 1.0) or (H + 1.0)),
            rho_road=rho_road,
            rho_wall=rho_wall,
            rho_ceiling=min(max(float(params.get("rho_ceiling", 0.25) or 0.25), 0.01), 0.95),
            n_road=max(8, _N_TRANS_PROFILE * 2),
            n_wall=max(4, int(math.ceil(float(params.get("height_m", H + 1.0) or (H + 1.0)) / 0.5))),
            n_ceiling=max(8, _N_TRANS_PROFILE * 2),
        )
        patches = build_patches(section)
        x_centre = float(field["s"])
        # Las superficies de una sección se resuelven en bloque con la misma
        # ruta vectorizada que las paredes. Así se conserva exactamente el
        # LDT/orientación de cada luminaria sin que la radiosidad de seis
        # escenas convierta las pequeñas evaluaciones de parches en miles de
        # bucles Python luminaria × parche.
        patch_surfaces = [
            (
                x_centre, patch.y_center, patch.z_center,
                patch.normal[0], patch.normal[1],
            )
            for patch in patches
        ]
        patch_direct = _surface_illuminance_batch(patch_surfaces)
        for patch, illuminance in zip(patches, patch_direct):
            patch.E_direct = float(illuminance)
        solve_radiosity(patches)
        indirect_by_y = {
            round(float(y_value), 8): max(
                0.0,
                float(indirect_illuminance_on_road(patches, float(y_value)))
                * rho_road / math.pi,
            )
            for y_value in _ys_profile
        }
        return {
            "patches": patches,
            "indirect_by_y": indirect_by_y,
            "rho_road": rho_road,
        }

    # La radiosidad se resuelve por cada campo físico que ya ha pasado la
    # comprobación de repetibilidad. Los alias periódicos reutilizan la misma
    # solución transversal; no se usa nunca un promedio de zona.
    radiosity_by_field: dict[int, dict] = {}
    if use_radiosity and include_quality_metrics:
        for index in solve_indices:
            radiosity_by_field[index] = _road_radiosity_for_field(fields[index])
        for alias_index, representative_index in aliases.items():
            radiosity_by_field[alias_index] = radiosity_by_field.get(
                representative_index, {}
            )
        for field_index, field in enumerate(fields):
            radiosity = radiosity_by_field.get(field_index)
            if not radiosity:
                continue
            indirect_values = np.asarray([
                float(radiosity["indirect_by_y"].get(round(float(y), 8), 0.0))
                for _x, y in field["points"]
            ], dtype=float)
            for observer_result in field["observer_results"]:
                direct_values = np.asarray(
                    observer_result["values"], dtype=float,
                )
                observer_result["direct_values"] = direct_values.tolist()
                observer_result["indirect_values"] = indirect_values.tolist()
                observer_result["values"] = (
                    direct_values + indirect_values
                ).tolist()
                observer_result["mean"] = float(
                    np.mean(observer_result["values"])
                )
            field["_radiosity_solution"] = radiosity

    def _wall_metrics(field: dict) -> dict:
        spacing = float(field["field_end"]) - float(field["field_start"])
        sample_x = [
            float(field["field_start"]) + (index + 0.5) * spacing / 3.0
            for index in range(3)
        ]
        # La componente directa de las paredes es idéntica en ambos modos;
        # usar siempre el lote vectorizado evita que el modo radiosidad vuelva
        # a introducir un bucle Python por luminaria y punto de pared.
        left_points = [
            (x_pos, 0.0, z_pos, 1.0, 0.0)
            for x_pos in sample_x for z_pos in wall_heights
        ]
        right_points = [
            (x_pos, W, z_pos, -1.0, 0.0)
            for x_pos in sample_x for z_pos in wall_heights
        ]
        left = (
            rho_wall * _surface_illuminance_batch(left_points) / math.pi
        ).tolist()
        right = (
            rho_wall * _surface_illuminance_batch(right_points) / math.pi
        ).tolist()
        radio_left = radio_right = 0.0
        if use_wall_radiosity:
            centre_x = float(field["s"])
            # Reutiliza la misma solución de radiosidad que alimenta la
            # calzada del campo. Si el perfil se calculó en modo rápido sin
            # métricas de calidad, se genera aquí la solución local.
            solution = field.get("_radiosity_solution", {})
            patches = solution.get("patches")
            if not patches:
                patches = _road_radiosity_for_field(field)["patches"]
            left_total = [
                patch.B / math.pi for patch in patches
                if patch.surface == "wall_left" and patch.z_center <= wall_height_m
            ]
            right_total = [
                patch.B / math.pi for patch in patches
                if patch.surface == "wall_right" and patch.z_center <= wall_height_m
            ]
            left_direct_mid = (
                rho_wall * _surface_illuminance_batch([
                    (centre_x, 0.0, z_pos, 1.0, 0.0)
                    for z_pos in wall_heights
                ]) / math.pi
            ).tolist()
            right_direct_mid = (
                rho_wall * _surface_illuminance_batch([
                    (centre_x, W, z_pos, -1.0, 0.0)
                    for z_pos in wall_heights
                ]) / math.pi
            ).tolist()
            radio_left = max(0.0, (float(np.mean(left_total)) if left_total else 0.0)
                              - (float(np.mean(left_direct_mid)) if left_direct_mid else 0.0))
            radio_right = max(0.0, (float(np.mean(right_total)) if right_total else 0.0)
                                - (float(np.mean(right_direct_mid)) if right_direct_mid else 0.0))
        n_wall_heights = len(wall_heights)
        left_grid = [
            [
                round(float(left[x_index * n_wall_heights + z_index]) + radio_left, 4)
                for z_index in range(n_wall_heights)
            ]
            for x_index in range(len(sample_x))
        ]
        right_grid = [
            [
                round(float(right[x_index * n_wall_heights + z_index]) + radio_right, 4)
                for z_index in range(n_wall_heights)
            ]
            for x_index in range(len(sample_x))
        ]
        return {
            "height_m": wall_height_m,
            "L_left_avg": (float(np.mean(left)) if left else 0.0) + radio_left,
            "L_right_avg": (float(np.mean(right)) if right else 0.0) + radio_right,
            "L_left_min": (float(np.min(left)) if left else 0.0) + radio_left,
            "L_right_min": (float(np.min(right)) if right else 0.0) + radio_right,
            # Valores espacialmente resueltos para la vista lateral: tres
            # secciones longitudinales y cuatro alturas en la franja CIE 88.
            # Si hay radiosidad, el incremento difuso local se suma como lo
            # hace ya la métrica media que gobierna la comprobación.
            "sample_x_m": [round(float(value), 4) for value in sample_x],
            "sample_z_m": [round(float(value), 4) for value in wall_heights],
            "L_left_grid": left_grid,
            "L_right_grid": right_grid,
            "L_indirect_left": radio_left,
            "L_indirect_right": radio_right,
            "available": True,
            "method": (
                "LDT_direct_plus_radiosity" if use_wall_radiosity
                else "LDT_direct_diffuse_wall"
            ),
        }

    if include_wall_metrics:
        for index in solve_indices:
            fields[index]["wall"] = _wall_metrics(fields[index])
        for alias_index, representative_index in aliases.items():
            fields[alias_index]["wall"] = dict(
                fields[representative_index].get("wall", {}),
            )
    else:
        for field in fields:
            field["wall"] = {}

    def _observer_field_metrics(field: dict, result: dict) -> dict:
        values = np.asarray(result["values"], dtype=float)
        lane_index = int(result["lane_index"])
        full_mean = float(np.mean(values))
        full_min = float(np.min(values))
        if not include_quality_metrics:
            # El cierre iterativo de la BASE usa exclusivamente Lavg. Evitar
            # TI (que vuelve a recorrer todas las luminarias) y las mallas de
            # uniformidad en cada iteracion no altera el resultado del flujo.
            return {
                "lane_index": lane_index,
                "lane_number": lane_index + 1,
                "observer_lane_y_m": round(float(result["lane_y_m"]), 3),
                "direction": int(result["direction"]),
                "full_L_avg": round(full_mean, 4),
                "full_L_min": round(full_min, 4),
                "U0": 0.0,
                "lane_L_avg": 0.0,
                "lane_L_min": 0.0,
                "lane_U0": 0.0,
                "Ul": 0.0,
                "TI": 0.0,
            }
        lane_start = _lane_starts[lane_index]
        lane_end = lane_start + _lane_width
        lane_pairs = [
            ((x, y), float(value))
            for (x, y), value in zip(field["points"], values)
            if lane_start - 1e-8 <= y <= lane_end + 1e-8
        ]
        lane_values = np.asarray(
            [value for _point, value in lane_pairs], dtype=float,
        )
        def _line_values(line_y: float) -> list[float]:
            values_on_line = []
            for x_value in sorted({round(x, 8) for x, _y in field["points"]}):
                column = [
                    ((x, y), float(value))
                    for (x, y), value in zip(field["points"], values)
                    if abs(x - x_value) < 1e-7
                ]
                if column:
                    values_on_line.append(min(
                        column,
                        key=lambda item: abs(item[0][1] - line_y),
                    )[1])
            return values_on_line

        centreline_values = _line_values(_lane_centres[lane_index])
        longitudinal_uniformities = [
            min(line_values) / max(max(line_values), 1e-9)
            for line_y in _quality_centrelines
            for line_values in [_line_values(line_y)]
            if line_values
        ]

        lane_mean = (
            float(np.mean(lane_values)) if lane_values.size else 0.0
        )
        lane_min = (
            float(np.min(lane_values)) if lane_values.size else 0.0
        )
        lane_max_line = (
            max(centreline_values) if centreline_values else 0.0
        )
        # TI se verifica con la escena de potencia maxima y con noche. Las
        # escenas diurnas reguladas se comprueban por Lavg/U0/Ul y paredes;
        # no repetir aquÃ­ el recorrido escalar de cada luminaria reduce de
        # forma importante el tiempo sin ocultar un criterio normativo.
        ti_value = 0.0
        if include_ti:
            point_results = [
                SimpleNamespace(x=x, y=y, L=float(value))
                for (x, y), value in zip(field["points"], values)
            ]
            observer = Observer(
                lane_y_m=float(result["lane_y_m"]),
                d_observer_m=60.0,
                direction=float(result["direction"]),
            )
            ti_value = calc._threshold_increment(
                point_results, lums, observer,
            )
        return {
            "lane_index": lane_index,
            "lane_number": lane_index + 1,
            "observer_lane_y_m": round(float(result["lane_y_m"]), 3),
            "direction": int(result["direction"]),
            "full_L_avg": round(full_mean, 4),
            "full_L_min": round(full_min, 4),
            "U0": round(
                full_min / max(full_mean, 1e-9), 4,
            ),
            "lane_L_avg": round(lane_mean, 4),
            "lane_L_min": round(lane_min, 4),
            "lane_U0": round(
                lane_min / max(lane_mean, 1e-9), 4,
            ),
            "Ul": round(min(longitudinal_uniformities) if longitudinal_uniformities else 0.0, 4),
            "TI": round(float(ti_value), 3),
        }

    points = []
    field_details = []
    lane_metrics_by_field: dict[int, list[dict]] = {}
    for field_index, field in enumerate(fields):
        if not field["observer_results"]:
            continue
        representative_index = aliases.get(field_index)
        if representative_index in lane_metrics_by_field:
            # Un alias solo se crea para un vano periodico sin luminarias
            # ajenas en su alcance. U0/Ul/TI son por ello los mismos que los
            # del vano representativo; recalcularlos era el principal coste
            # evitable de perfiles largos.
            lane_results = [
                dict(metrics)
                for metrics in lane_metrics_by_field[representative_index]
            ]
        else:
            lane_results = [
                _observer_field_metrics(field, result)
                for result in field["observer_results"]
            ]
        lane_metrics_by_field[field_index] = lane_results
        governing = min(
            field["observer_results"],
            key=lambda result: result["mean"],
        )
        governing_lane = min(
            lane_results, key=lambda result: result["full_L_avg"],
        )
        governing_u0 = min(
            lane_results, key=lambda result: result["U0"],
        )
        governing_ul = min(
            lane_results, key=lambda result: result["Ul"],
        )
        governing_ti = max(
            lane_results, key=lambda result: result["TI"],
        )
        governing_direct_values = np.asarray(
            governing.get("direct_values", governing["values"]), dtype=float,
        )
        governing_indirect_values = np.asarray(
            governing.get("indirect_values", np.zeros_like(governing_direct_values)),
            dtype=float,
        )
        governing_L_direct = float(np.mean(governing_direct_values))
        governing_L_indirect = float(np.mean(governing_indirect_values))
        wall = dict(field.get("wall", {}))
        wall_left = float(wall.get("L_left_avg", 0.0) or 0.0)
        wall_right = float(wall.get("L_right_avg", 0.0) or 0.0)
        road_lavg = float(governing_lane["full_L_avg"])
        wall_ratio = min(wall_left, wall_right) / max(road_lavg, 1e-9)
        wall.update({
            "L_min_avg": round(min(wall_left, wall_right), 4),
            "L_avg": round((wall_left + wall_right) / 2.0, 4),
            "ratio": round(wall_ratio, 5),
            "ratio_required": round(float(wall_criterion["ratio"]), 4),
            "compliant": bool(wall_ratio + 1e-9 >= float(wall_criterion["ratio"])),
            "governing_side": "left" if wall_left <= wall_right else "right",
        })
        point_summary = {
            "s": round(field["s"], 3),
            "field_start": round(field["field_start"], 3),
            "field_end": round(field["field_end"], 3),
            "L": round(governing_lane["full_L_avg"], 3),
            "L_min": round(governing_lane["full_L_min"], 3),
            "L_direct": round(governing_L_direct, 4),
            "L_indirect": round(governing_L_indirect, 4),
            "U0": round(governing_u0["U0"], 4),
            "Ul": round(governing_ul["Ul"], 4),
            "TI": round(governing_ti["TI"], 3),
        }
        points.append(point_summary)
        field_details.append({
            **point_summary,
            "wall": wall,
            "zone_type": str(getattr(field["zone"], "zone_type", "") or ""),
            "zone_name": str(getattr(field["zone"], "zone_name", "") or ""),
            "observer_lane_y_m": round(governing["lane_y_m"], 3),
            "observer_direction": int(governing["direction"]),
            "observer_lane_number": int(governing["lane_index"]) + 1,
            "lane_results": lane_results,
            "metric_governors": {
                "L": {
                    "lane": governing_lane["lane_number"],
                    "direction": governing_lane["direction"],
                },
                "U0": {
                    "lane": governing_u0["lane_number"],
                    "direction": governing_u0["direction"],
                },
                "Ul": {
                    "lane": governing_ul["lane_number"],
                    "direction": governing_ul["direction"],
                },
                "TI": {
                    "lane": governing_ti["lane_number"],
                    "direction": governing_ti["direction"],
                },
            },
            "radiosity": {
                "enabled": bool(use_radiosity and include_quality_metrics),
                "L_indirect": round(governing_L_indirect, 4),
                "pct": round(
                    100.0 * governing_L_indirect
                    / max(governing_L_direct, 1e-9), 2,
                ),
            },
            "observer_grids": [
                {
                    "lane_index": metrics["lane_index"],
                    "lane_number": metrics["lane_number"],
                    "observer_lane_y_m": metrics["observer_lane_y_m"],
                    "direction": metrics["direction"],
                    "L": metrics["full_L_avg"],
                    "U0": metrics["U0"],
                    "Ul": metrics["Ul"],
                    "TI": metrics["TI"],
                    "values": [
                        round(float(value), 3)
                        for value in result["values"]
                    ],
                    "direct_values": [
                        round(float(value), 3)
                        for value in result.get("direct_values", result["values"])
                    ],
                    "indirect_values": [
                        round(float(value), 3)
                        for value in result.get(
                            "indirect_values", np.zeros(len(result["values"]))
                        )
                    ],
                }
                for result, metrics in zip(
                    field["observer_results"],
                    lane_results,
                )
            ],
            "grid_points": [
                {
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "L": round(float(value), 3),
                    "L_direct": round(float(direct_value), 3),
                    "L_indirect": round(float(indirect_value), 3),
                }
                for (x, y), value, direct_value, indirect_value in zip(
                    field["points"],
                    governing["values"],
                    governing_direct_values,
                    governing_indirect_values,
                )
            ],
        })

    out["available"]    = True
    out["points"]       = points
    out["fields"]       = field_details
    out["n_luminaires"] = len(lums)
    out["performance"] = {
        "elapsed_s": round(time.perf_counter() - profile_started, 4),
        "fields_total": len(fields),
        "fields_solved": len(solve_indices),
        "fields_reused": len(aliases),
        "quality_metrics_solved": len(lane_metrics_by_field) - len(aliases),
        "TI_evaluated": bool(include_ti),
        "wall_metrics_evaluated": bool(include_wall_metrics),
        "batch_calls": batch_calls,
        "evaluated_points": evaluated_points,
        "physical_luminaires": len(lums),
    }
    out["metric"] = "CIE140_Lavg"
    out["calc_mode"] = "radiosity" if use_radiosity else "direct"
    out["radiosity"] = {
        "road_indirect_included": bool(
            use_radiosity and include_quality_metrics
        ),
        "method": (
            "Radiosidad 2D por campo CIE 140 con LDT, tilt y orientación reales"
            if use_radiosity else "No aplicado"
        ),
    }
    out["wall_luminance"] = {
        **wall_criterion,
        "reflectance": rho_wall,
        "method": (
            "LDT directo + radiosidad sobre pared difusa"
            if use_wall_radiosity else "LDT directo sobre pared difusa (L=rho·E/pi)"
        ),
        "scope": "ambas paredes, por campo longitudinal",
    }
    out["grid"] = {
        "longitudinal": "N=10 si S<=30 m; si no, D<=3 m",
        "transverse_points_per_lane": 3,
        "num_lanes": _n_lanes,
        "sidewalks_excluded": True,
        "shoulders_included": False,
        "num_observers": _n_lanes,
        "observers_per_direction": _n_lanes,
        "directions_in_bidirectional_interior": 2 if _has_portal_b else 1,
        "selection": "peor observador",
        "governing_by_metric": True,
        "lane_results": "un resultado por carril, sentido y campo",
        "U0_scope": "carriles de circulación (arcenes y aceras excluidos)",
        "Ul_scope": "eje longitudinal de cada carril de circulación",
        "representation": "un valor Lavg por campo entre luminarias consecutivas",
    }
    return out


def _profile_field_quality(profile: dict, params: dict) -> list[dict]:
    """Devuelve las métricas unificadas de cada campo CIE 140."""
    road_width = max(
        0.1, float(params.get("road_width_m", 0.0) or 0.1)
    )
    lane_centres = _lane_layout(
        params, road_width,
    )["lane_centres_m"]
    field_metrics = []
    for field in profile.get("fields", []):
        if all(key in field for key in ("U0", "Ul", "TI")):
            field_metrics.append({
                "s": float(field["s"]),
                "field_start": float(field.get("field_start", field["s"])),
                "field_end": float(field.get("field_end", field["s"])),
                "zone_type": field.get("zone_type", ""),
                "zone_name": field.get("zone_name", ""),
                "Lavg": float(field["L"]),
                "Lmin": float(field.get("L_min", 0.0) or 0.0),
                "L_direct": float(field.get("L_direct", field["L"]) or 0.0),
                "L_indirect": float(field.get("L_indirect", 0.0) or 0.0),
                "U0": float(field["U0"]),
                "Ul": float(field["Ul"]),
                "TI": float(field["TI"]),
                "lane_results": list(field.get("lane_results", [])),
                "metric_governors": dict(
                    field.get("metric_governors", {}),
                ),
                "wall": dict(field.get("wall", {})),
                "radiosity": dict(field.get("radiosity", {})),
            })
            continue

        # Compatibilidad con perfiles guardados antes de la unificación.
        grid = field.get("grid_points", [])
        values = [
            float(point["L"]) for point in grid
            if point.get("L") is not None
        ]
        if not values:
            continue
        mean_value = float(np.mean(values))
        U0 = float(np.min(values)) / max(mean_value, 1e-9)
        xs = sorted({round(float(point["x"]), 6) for point in grid})
        lane_uniformities = []
        for lane_y in lane_centres:
            line_values = []
            for x_value in xs:
                column = [
                    point for point in grid
                    if abs(float(point["x"]) - x_value) < 1e-5
                ]
                if not column:
                    continue
                nearest = min(
                    column,
                    key=lambda point: abs(float(point["y"]) - lane_y),
                )
                line_values.append(float(nearest["L"]))
            if line_values:
                lane_uniformities.append(
                    min(line_values) / max(max(line_values), 1e-9)
                )
        field_metrics.append({
            "s": float(field["s"]),
            "field_start": float(field.get("field_start", field["s"])),
            "field_end": float(field.get("field_end", field["s"])),
            "zone_type": field.get("zone_type", ""),
            "zone_name": field.get("zone_name", ""),
            "Lavg": float(field["L"]),
            "Lmin": float(np.min(values)),
            "L_direct": float(field.get("L_direct", field["L"]) or 0.0),
            "L_indirect": float(field.get("L_indirect", 0.0) or 0.0),
            "U0": U0,
            "Ul": (
                min(lane_uniformities) if lane_uniformities else 0.0
            ),
            "TI": 0.0,
            "lane_results": [],
            "metric_governors": {},
            "wall": dict(field.get("wall", {})),
            "radiosity": dict(field.get("radiosity", {})),
        })
    return field_metrics


def unify_zone_verification_with_profile(
    photometric: dict,
    profile: dict,
    lum_result,
    params: dict,
) -> dict:
    """Hace que la tabla de zonas y el desglose por carril usen la misma malla.

    ``verify_luminaire_result`` se conserva como verificación auxiliar LDT,
    pero el perfil físico completo gobierna L/U0/Ul/TI y, cuando procede, la
    radiosidad campo a campo.
    """
    if not profile.get("available") or not profile.get("fields"):
        return photometric

    from modules.tunnel.required_luminance import (
        required_luminance_for_zone,
    )

    profile_params = dict(params)
    profile_params["road_width_m"] = float(
        getattr(lum_result, "road_width_m", 0.0) or 0.0
    )
    metrics = _profile_field_quality(profile, profile_params)
    zones_by_name = {
        str(getattr(zone, "zone_name", "") or ""): zone
        for zone in getattr(lum_result, "zones", [])
    }
    old_zones = dict(photometric.get("zones", {}))
    profile_includes_radiosity = bool(
        profile.get("radiosity", {}).get("road_indirect_included", False)
    )
    U0_required = float(params.get("U0_obj", _U0_MIN) or _U0_MIN)
    Ul_required = float(params.get("Ul_obj", _UL_MIN) or _UL_MIN)
    TI_required = float(params.get("TI_max", _TI_MAX) or _TI_MAX)
    wall_criterion = _wall_luminance_criterion(params)
    Lin = max(0.0, float(params.get("Lin", 0.0) or 0.0))
    Lth = max(0.0, float(params.get("Lth", Lin) or Lin))
    Lth_b = max(
        0.0, float(params.get("Lth_b", Lth) or Lth),
    )
    speed = float(params.get("speed_kmh", 80.0) or 80.0)
    mounting_height = float(
        params.get("mounting_height_m", 5.0) or 5.0
    )
    enforce_portal_edges = bool(
        params.get("enforce_portal_edge_luminance", True)
    )
    portal_buffer = 5.0 * mounting_height
    tube_length = float(
        getattr(lum_result, "tube_length_m", 0.0) or 0.0
    )
    has_portal_b = any(
        str(getattr(zone, "zone_type", "") or "").lower().endswith("_b")
        for zone in getattr(lum_result, "zones", [])
    ) or str(params.get("traffic_direction", "one_way")) == "two_way"

    def _required(zone, s_value: float) -> float:
        if zone is None:
            return Lin
        try:
            return float(required_luminance_for_zone(
                zone,
                s_value,
                Lth=Lth,
                Lth_b=Lth_b,
                Lin=Lin,
                speed_kmh=speed,
            ))
        except Exception:
            return float(
                getattr(zone, "L_total_required", None)
                or getattr(zone, "L_required", Lin)
                or Lin
            )

    prepared = []
    for item in metrics:
        zone_name = str(item.get("zone_name", "") or "")
        zone = zones_by_name.get(zone_name)
        L_required = _required(zone, float(item["s"]))
        legacy = old_zones.get(zone_name, {})
        if profile_includes_radiosity:
            # La malla CIE 140 ya contiene la interreflexión por punto. No se
            # puede sumar aquí una media zonal sin duplicar energía.
            L_indirect = max(0.0, float(item.get("L_indirect", 0.0) or 0.0))
            direct_avg = float(item.get("L_direct", item["Lavg"]) or 0.0)
            total_avg = float(item["Lavg"])
        else:
            L_indirect = max(
                0.0, float(legacy.get("L_indirect", 0.0) or 0.0),
            )
            direct_avg = float(item["Lavg"])
            total_avg = direct_avg + L_indirect
        direct_min = float(
            item.get("Lmin", direct_avg * float(item["U0"]))
            or 0.0
        )
        total_min = (
            float(item["Lmin"])
            if profile_includes_radiosity
            else direct_min + L_indirect
        )
        lane_results = []
        for lane in item.get("lane_results", []):
            lane_copy = dict(lane)
            full_avg = float(lane_copy.get("full_L_avg", 0.0) or 0.0)
            full_min = float(lane_copy.get("full_L_min", 0.0) or 0.0)
            lane_avg = float(lane_copy.get("lane_L_avg", 0.0) or 0.0)
            lane_min = float(lane_copy.get("lane_L_min", 0.0) or 0.0)
            direct_ti = float(lane_copy.get("TI", 0.0) or 0.0)
            if profile_includes_radiosity:
                # Estas magnitudes ya proceden de los valores por punto con
                # L directa + L indirecta. Preservarlas evita sumar dos veces.
                lane_copy.update({
                    "L_required": round(L_required, 4),
                    "s": float(item["s"]),
                })
            else:
                lane_copy.update({
                    "full_L_avg": round(full_avg + L_indirect, 4),
                    "full_L_min": round(full_min + L_indirect, 4),
                    "U0": round(
                        (full_min + L_indirect)
                        / max(full_avg + L_indirect, 1e-9),
                        4,
                    ),
                    "lane_L_avg": round(lane_avg + L_indirect, 4),
                    "lane_L_min": round(lane_min + L_indirect, 4),
                    "lane_U0": round(
                        (lane_min + L_indirect)
                        / max(lane_avg + L_indirect, 1e-9),
                        4,
                    ),
                    "TI": round(
                        direct_ti
                        * (
                            full_avg / max(full_avg + L_indirect, 1e-9)
                        ) ** 0.8
                        if full_avg > 0 else direct_ti,
                        3,
                    ),
                    "L_required": round(L_required, 4),
                    "s": float(item["s"]),
                })
            lane_results.append(lane_copy)
        wall = dict(item.get("wall", {}))
        wall_available = (
            "L_left_avg" in wall and "L_right_avg" in wall
        )
        wall_left = float(wall.get("L_left_avg", 0.0) or 0.0)
        wall_right = float(wall.get("L_right_avg", 0.0) or 0.0)
        wall_ratio = min(wall_left, wall_right) / max(total_avg, 1e-9)
        wall.update({
            "ratio": wall_ratio,
            "ratio_required": float(wall_criterion["ratio"]),
            "available": wall_available,
            "compliant": (
                wall_ratio + 1e-9 >= float(wall_criterion["ratio"])
                if wall_available else True
            ),
            "governing_side": "left" if wall_left <= wall_right else "right",
        })
        prepared.append({
            **item,
            "zone_name": zone_name,
            "Lavg": total_avg,
            "Lmin": total_min,
            "L_direct": direct_avg,
            "L_required": L_required,
            "L_ratio": total_avg / max(L_required, 1e-9),
            "U0": total_min / max(total_avg, 1e-9),
            "TI": max(
                [float(lane.get("TI", 0.0)) for lane in lane_results]
                or [float(item.get("TI", 0.0) or 0.0)]
            ),
            "lane_results": lane_results,
            # En modo de cierre estricto los campos junto a las bocas también
            # forman parte de la conformidad, no solo del diagnóstico visual.
            "representative": enforce_portal_edges or (
                float(item["s"]) >= portal_buffer - 1e-9
                and (
                    not has_portal_b
                    or float(item["s"])
                    <= tube_length - portal_buffer + 1e-9
                )
            ),
            "L_indirect": L_indirect,
            "radiosity": dict(item.get("radiosity", {})),
            "wall": wall,
        })

    # Publicar en cada campo la magnitud que realmente gobierna el
    # cumplimiento. ``field['L']`` queda intacto para las vistas de malla;
    # los valores enriquecidos incluyen la radiosidad cuando corresponde y
    # permiten a la lista de luminarias no confundir una lectura puntual con
    # la media CIE 140 del campo entre luminarias.
    prepared_by_field = {
        (
            item["zone_name"],
            round(float(item["s"]), 4),
            round(float(item.get("field_start", item["s"])), 4),
            round(float(item.get("field_end", item["s"])), 4),
        ): item
        for item in prepared
    }
    for field in profile.get("fields", []):
        key = (
            str(field.get("zone_name", "") or ""),
            round(float(field.get("s", 0.0) or 0.0), 4),
            round(float(field.get("field_start", field.get("s", 0.0)) or 0.0), 4),
            round(float(field.get("field_end", field.get("s", 0.0)) or 0.0), 4),
        )
        item = prepared_by_field.get(key)
        if item is None:
            continue
        governor = item.get("metric_governors", {}).get("L", {})
        Lavg = float(item["Lavg"])
        L_required = float(item["L_required"])
        field.update({
            "Lavg_governing": round(Lavg, 4),
            "L_direct": round(float(item.get("L_direct", Lavg)), 4),
            "L_indirect": round(float(item.get("L_indirect", 0.0)), 4),
            "L_required": round(L_required, 4),
            "L_ratio": round(Lavg / max(L_required, 1e-9), 4),
            "luminance_compliant": bool(Lavg + 1e-9 >= L_required),
            "governing_lane_number": int(
                governor.get("lane", field.get("observer_lane_number", 1))
            ),
            "governing_direction": int(
                governor.get("direction", field.get("observer_direction", 1))
            ),
            "wall": {
                **item["wall"],
                "ratio": round(float(item["wall"]["ratio"]), 5),
                "ratio_required": round(float(item["wall"]["ratio_required"]), 4),
            },
            "radiosity": dict(item.get("radiosity", {})),
        })

    unified_zones = {}
    for zone_name in dict.fromkeys(
        item["zone_name"] for item in prepared if item["zone_name"]
    ):
        zone_fields_all = [
            item for item in prepared if item["zone_name"] == zone_name
        ]
        zone_fields = [
            item for item in zone_fields_all if item["representative"]
        ] or zone_fields_all
        if not zone_fields:
            continue

        worst_L = min(zone_fields, key=lambda item: item["L_ratio"])
        worst_U0 = min(zone_fields, key=lambda item: item["U0"])
        worst_Ul = min(zone_fields, key=lambda item: item["Ul"])
        worst_TI = max(zone_fields, key=lambda item: item["TI"])
        worst_wall = min(
            zone_fields,
            key=lambda item: float(item.get("wall", {}).get("ratio", 0.0)),
        )

        by_lane = []
        lane_keys = sorted({
            (
                int(lane.get("direction", 1)),
                int(lane.get("lane_index", 0)),
            )
            for item in zone_fields
            for lane in item.get("lane_results", [])
        })
        for direction, lane_index in lane_keys:
            samples = [
                lane
                for item in zone_fields
                for lane in item.get("lane_results", [])
                if int(lane.get("direction", 1)) == direction
                and int(lane.get("lane_index", 0)) == lane_index
            ]
            if not samples:
                continue
            worst_lane_L = min(
                samples,
                key=lambda lane: float(lane["lane_L_avg"])
                / max(float(lane["L_required"]), 1e-9),
            )
            worst_lane_U0 = min(
                samples, key=lambda lane: float(lane["lane_U0"]),
            )
            worst_lane_Ul = min(
                samples, key=lambda lane: float(lane["Ul"]),
            )
            worst_lane_TI = max(
                samples, key=lambda lane: float(lane["TI"]),
            )
            lane_ok = (
                float(worst_lane_L["lane_L_avg"]) + 1e-9
                >= float(worst_lane_L["L_required"])
                and float(worst_lane_U0["lane_U0"]) + 1e-9
                >= U0_required
                and float(worst_lane_Ul["Ul"]) + 1e-9
                >= Ul_required
                and float(worst_lane_TI["TI"]) <= TI_required + 1e-9
            )
            by_lane.append({
                "lane_index": lane_index,
                "lane_number": lane_index + 1,
                "direction": direction,
                "observer_lane_y_m": worst_lane_L[
                    "observer_lane_y_m"
                ],
                "L_avg": round(float(worst_lane_L["lane_L_avg"]), 3),
                "L_required": round(
                    float(worst_lane_L["L_required"]), 3,
                ),
                "L_ratio": round(
                    float(worst_lane_L["lane_L_avg"])
                    / max(float(worst_lane_L["L_required"]), 1e-9),
                    4,
                ),
                "U0": round(float(worst_lane_U0["lane_U0"]), 4),
                "Ul": round(float(worst_lane_Ul["Ul"]), 4),
                "TI": round(float(worst_lane_TI["TI"]), 3),
                "U0_required": round(U0_required, 3),
                "Ul_required": round(Ul_required, 3),
                "TI_max": round(TI_required, 1),
                "critical_s_m": round(float(worst_lane_L["s"]), 3),
                "diagnostic_compliant": lane_ok,
            })

        L_ok = float(worst_L["L_ratio"]) + 1e-9 >= 0.995
        U0_ok = float(worst_U0["U0"]) + 1e-9 >= U0_required
        Ul_ok = float(worst_Ul["Ul"]) + 1e-9 >= Ul_required
        TI_ok = float(worst_TI["TI"]) <= TI_required + 1e-9
        wall_ok = bool(worst_wall.get("wall", {}).get("compliant", True))
        legacy = old_zones.get(zone_name, {})
        unified_zones[zone_name] = {
            "L_avg": round(float(worst_L["Lavg"]), 2),
            "L_min": round(float(worst_L["Lmin"]), 2),
            "L_direct": round(float(worst_L.get("L_direct", worst_L["Lavg"])), 2),
            "L_indirect": round(float(worst_L["L_indirect"]), 3),
            "U0": round(float(worst_U0["U0"]), 3),
            "Ul": round(float(worst_Ul["Ul"]), 3),
            "TI": round(float(worst_TI["TI"]), 1),
            "E_h_avg": legacy.get("E_h_avg"),
            "L_req": round(float(worst_L["L_required"]), 2),
            "profile_min_ratio": round(float(worst_L["L_ratio"]), 4),
            "wall": {
                **worst_wall.get("wall", {}),
                "L_left_avg": round(float(worst_wall.get("wall", {}).get("L_left_avg", 0.0)), 3),
                "L_right_avg": round(float(worst_wall.get("wall", {}).get("L_right_avg", 0.0)), 3),
                "ratio": round(float(worst_wall.get("wall", {}).get("ratio", 0.0)), 4),
                "ratio_required": round(float(wall_criterion["ratio"]), 4),
                "critical_s_m": round(float(worst_wall["s"]), 3),
            },
            "compliant": all((L_ok, U0_ok, Ul_ok, TI_ok, wall_ok)),
            "checks": {
                "L_avg": L_ok,
                "U0": U0_ok,
                "Ul": Ul_ok,
                "TI": TI_ok,
                "wall": wall_ok,
            },
            "radiosity": dict(worst_L.get("radiosity", {})),
            "by_lane": by_lane,
            "n_fields": len(zone_fields),
            "n_edge_diagnostic_fields": (
                len(zone_fields_all) - len(zone_fields)
            ),
            "source": "CIE140_real_profile_by_lane",
            "governing": {
                "L_s_m": round(float(worst_L["s"]), 3),
                "U0_s_m": round(float(worst_U0["s"]), 3),
                "Ul_s_m": round(float(worst_Ul["s"]), 3),
                "TI_s_m": round(float(worst_TI["s"]), 3),
                "wall_s_m": round(float(worst_wall["s"]), 3),
            },
        }

    if unified_zones:
        photometric["zones"] = unified_zones
        photometric["overall_compliant"] = all(
            zone["compliant"] for zone in unified_zones.values()
        )
        photometric["verification_source"] = (
            "Perfil físico CIE 140 por carril, sentido y campo"
        )
        photometric["wall_luminance"] = {
            **wall_criterion,
            "reflectance": float(params.get("rho_wall", 0.40) or 0.40),
            "method": "LDT directo sobre pared difusa (L=rho·E/pi)",
            "scope": "ambas paredes, por campo longitudinal",
            "method": profile.get("wall_luminance", {}).get(
                "method", "LDT directo sobre pared difusa (L=rho·E/pi)"
            ),
        }
        grid_scope = profile.get("grid", {})
        photometric["lane_verification"] = {
            "available": True,
            "num_lanes": _lane_layout(
                profile_params,
                profile_params["road_width_m"],
            )["num_lanes"],
            "U0_scope": grid_scope.get(
                "U0_scope", "calzada (arcenes excluidos)",
            ),
            "Ul_scope": grid_scope.get(
                "Ul_scope", "eje de cada carril",
            ),
            "TI_scope": "cada observador de carril",
            "worst_case_governs": True,
        }
    return photometric


def verify_layered_operating_scenario(
    lum_result,
    params: dict,
    scenario_key: str,
    *,
    existing_profile: dict | None = None,
    include_profile: bool = False,
    include_ti: bool = True,
    include_wall_metrics: bool = True,
    _influence_cache: dict | None = None,
) -> dict:
    """Verifica Lavg/Uo/Ul con el estado físico DALI de una escena diurna."""
    import copy
    from modules.tunnel.required_luminance import (
        daylight_contribution_for_zone,
        required_luminance_for_zone,
    )

    factor_by_scene = {
        "sunny": 1.00,
        "normal": 0.70,
        "overcast": 0.30,
        "dusk": 0.05,
    }
    key = str(scenario_key or "").lower()
    if key not in factor_by_scene:
        return {
            "available": False,
            "error": f"Escena diurna desconocida: {scenario_key}",
        }
    scenario_result = copy.deepcopy(lum_result)
    has_operations = False
    for zone in scenario_result.zones:
        for setpoint in zone.setpoints or []:
            operation = (
                setpoint.get("scenario_operating_points", {}).get(key)
            )
            if operation is None:
                continue
            has_operations = True
            setpoint["flux_lm"] = float(
                operation.get("flux_lm", 0.0) or 0.0
            )
            setpoint["target_flux_lm"] = float(
                operation.get(
                    "target_flux_lm", setpoint["flux_lm"],
                ) or setpoint["flux_lm"]
            )
            setpoint["current_mA"] = float(
                operation.get("current_mA", 0.0) or 0.0
            )
            setpoint["power_w"] = float(
                operation.get("power_w", 0.0) or 0.0
            )
        zone.power_zone_w = round(sum(
            float(sp.get("power_w", 0.0) or 0.0)
            for sp in zone.setpoints or []
        ), 3)
        zone.flux_zone_lm = round(sum(
            float(sp.get("flux_lm", 0.0) or 0.0)
            for sp in zone.setpoints or []
        ), 3)
    if not has_operations:
        return {
            "available": False,
            "error": "La instalación no contiene consignas para la escena.",
        }
    scenario_result._compute_totals()

    factor = factor_by_scene[key]
    Lin = max(0.0, float(params.get("Lin", 0.0) or 0.0))
    Lth_scene = max(
        Lin, float(params.get("Lth", 0.0) or 0.0) * factor,
    )
    Lth_b_scene = max(
        Lin,
        float(params.get("Lth_b", params.get("Lth", 0.0)) or 0.0)
        * factor,
    )
    scenario_params = dict(params)
    scenario_params["Lth"] = Lth_scene
    scenario_params["Lth_b"] = Lth_b_scene
    scenario_params["road_width_m"] = float(
        getattr(scenario_result, "road_width_m", 0.0) or 0.0
    )
    profile = existing_profile or compute_real_luminance_profile(
        scenario_result,
        scenario_params,
        scenario_result.road_width_m,
        step_size=(
            1.0 if scenario_result.tube_length_m <= 500.0 else 2.0
        ),
        include_ti=include_ti,
        include_wall_metrics=include_wall_metrics,
        _influence_cache=_influence_cache,
    )
    if not profile.get("available") or not profile.get("fields"):
        return {
            "available": False,
            "error": profile.get(
                "error", "No se pudieron formar campos CIE 140.",
            ),
        }
    metrics = _profile_field_quality(profile, scenario_params)
    zones_by_name = {
        str(zone.zone_name): zone for zone in scenario_result.zones
    }
    U0_required = float(params.get("U0_obj", 0.40) or 0.40)
    Ul_required = float(params.get("Ul_obj", 0.60) or 0.60)
    for item in metrics:
        zone = zones_by_name.get(str(item["zone_name"]))
        if zone is None:
            item["L_required"] = Lin
        else:
            item["L_required"] = required_luminance_for_zone(
                zone,
                item["s"],
                Lth=Lth_scene,
                Lth_b=Lth_b_scene,
                Lin=Lin,
                speed_kmh=float(params.get("speed_kmh", 80.0) or 80.0),
            )
        item["L_natural"] = (
            daylight_contribution_for_zone(
                zone,
                item["s"],
                Lth=Lth_scene,
                Lth_b=Lth_b_scene,
            )
            if zone is not None else 0.0
        )
        item["L_required_total"] = (
            float(item["L_required"]) + float(item["L_natural"])
        )
        item["L_ratio"] = (
            item["Lavg"] / max(item["L_required"], 1e-9)
        )
    required_by_s = {
        round(float(item["s"]), 6): float(item["L_required"])
        for item in metrics
    }
    for field, item in zip(profile.get("fields", []), metrics):
        # Publicar el mismo valor gobernante que usa la verificación CIE 140
        # para que la curva, el tooltip y la tabla de luminarias no mezclen
        # ``field['L']`` con una media de otro observador/carril.
        field["Lavg_governing"] = round(float(item["Lavg"]), 4)
        field["L_min_governing"] = round(float(item["Lmin"]), 4)
        field["U0"] = round(float(item["U0"]), 4)
        field["Ul"] = round(float(item["Ul"]), 4)
        field["TI"] = round(float(item["TI"]), 3)
        field["L_required"] = round(float(item["L_required"]), 4)
        field["L_required_total"] = round(
            float(item["L_required_total"]), 4,
        )
        field["natural_daylight_cd_m2"] = round(
            float(item["L_natural"]), 4,
        )
        field["L_ratio"] = round(float(item["L_ratio"]), 5)
    for point in profile.get("points", []):
        point["L_required"] = round(
            required_by_s.get(
                round(float(point.get("s", 0.0)), 6),
                Lin,
            ),
            4,
        )
        matching = next(
            (
                item for item in metrics
                if abs(
                    float(item["s"])
                    - float(point.get("s", 0.0))
                ) < 1e-6
            ),
            None,
        )
        point["natural_daylight_cd_m2"] = round(
            float(matching["L_natural"]) if matching else 0.0,
            4,
        )
        point["L_required_total"] = round(
            float(matching["L_required_total"])
            if matching else float(point["L_required"]),
            4,
        )
    profile["scene"] = key
    profile["L20_factor"] = factor
    profile["Lth_cd_m2"] = round(Lth_scene, 4)
    profile["Lth_b_cd_m2"] = round(Lth_b_scene, 4)
    if not metrics:
        return {
            "available": False,
            "error": "Los campos no contienen valores de luminancia.",
        }
    # El alcance de los campos de borde debe coincidir con el diseño y con la
    # curva publicada. Por defecto el cierre de este proyecto es estricto:
    # los primeros/últimos campos de umbral gobiernan. Solo se excluyen como
    # diagnóstico 5H cuando el usuario desactiva expresamente ese criterio.
    portal_buffer = 5.0 * float(
        params.get("mounting_height_m", 5.0) or 5.0
    )
    has_portal_b = any(
        str(getattr(zone, "zone_type", "") or "").lower().endswith("_b")
        for zone in scenario_result.zones
    )
    enforce_portal_edges = bool(
        params.get("enforce_portal_edge_luminance", True)
    )
    representative = list(metrics) if enforce_portal_edges else [
        item for item in metrics
        if item["s"] >= portal_buffer - 1e-9
        and (
            not has_portal_b
            or item["s"]
            <= scenario_result.tube_length_m - portal_buffer + 1e-9
        )
    ]
    if not representative:
        return {
            "available": False,
            "error": "No existe un campo típico fuera de los bordes 5H.",
        }
    minimum_L_ratio = min(item["L_ratio"] for item in representative)
    minimum_U0 = min(item["U0"] for item in representative)
    minimum_Ul = min(item["Ul"] for item in representative)
    wall_criterion = _wall_luminance_criterion(scenario_params)
    wall_fields = [
        item for item in representative
        if item.get("wall", {}).get("available", False)
    ]
    minimum_wall_ratio = min(
        (float(item["wall"]["ratio"]) for item in wall_fields),
        default=float("inf"),
    )
    wall_ok = (
        minimum_wall_ratio + 1e-9 >= float(wall_criterion["ratio"])
        if wall_fields else True
    )
    # Las paredes se calculan y reportan en la verificacion final, pero
    # no gobiernan el diseno: el resultado que cumple se encuentra por
    # L/U0/Ul y la luminancia de pared es un valor del informe.
    compliant = (
        minimum_L_ratio + 1e-9 >= 1.0
        and minimum_U0 + 1e-9 >= U0_required
        and minimum_Ul + 1e-9 >= Ul_required
    )
    worst = min(representative, key=lambda item: item["L_ratio"])
    highest = max(representative, key=lambda item: item["L_ratio"])
    worst_U0 = min(representative, key=lambda item: item["U0"])
    worst_Ul = min(representative, key=lambda item: item["Ul"])
    edge_worst = min(metrics, key=lambda item: item["L_ratio"])
    verification = {
        "available": True,
        "scene": key,
        "L20_factor": factor,
        "Lth_cd_m2": round(Lth_scene, 3),
        "Lth_b_cd_m2": round(Lth_b_scene, 3),
        "minimum_L_ratio": round(minimum_L_ratio, 4),
        "maximum_L_ratio": round(float(highest["L_ratio"]), 4),
        "minimum_U0": round(minimum_U0, 4),
        "minimum_Ul": round(minimum_Ul, 4),
        "minimum_wall_ratio": (
            round(minimum_wall_ratio, 4) if wall_fields else None
        ),
        "wall_ratio_required": round(float(wall_criterion["ratio"]), 4),
        "minimum_U0_s_m": round(worst_U0["s"], 3),
        "minimum_Ul_s_m": round(worst_Ul["s"], 3),
        "worst_field_s_m": round(worst["s"], 3),
        "worst_field_Lavg_cd_m2": round(worst["Lavg"], 3),
        "worst_field_Lreq_cd_m2": round(worst["L_required"], 3),
        "maximum_field_s_m": round(highest["s"], 3),
        "maximum_field_Lavg_cd_m2": round(highest["Lavg"], 3),
        "maximum_field_Lreq_cd_m2": round(
            highest["L_required"], 3,
        ),
        "n_fields": len(representative),
        "n_edge_diagnostic_fields": len(metrics) - len(representative),
        "profile_performance": profile.get("performance", {}),
        "edge_minimum_L_ratio": round(edge_worst["L_ratio"], 4),
        "edge_worst_s_m": round(edge_worst["s"], 3),
        "compliant": compliant,
        "TI_status": "verificado en diseño máximo y noche",
        "operating_power_kw": round(
            float(getattr(scenario_result, "total_power_kw", 0.0) or 0.0),
            3,
        ),
    }
    try:
        from modules.tunnel.luminaires import (
            physical_luminaires_per_setpoint,
        )
        physical_factor = physical_luminaires_per_setpoint(
            getattr(scenario_result, "arrangement", ""),
        )
    except Exception:
        physical_factor = 1
    active_positions = sum(
        1
        for zone in scenario_result.zones
        for setpoint in zone.setpoints or []
        if float(setpoint.get("flux_lm", 0.0) or 0.0) > 1e-9
    )
    verification["active_luminaires"] = (
        active_positions * physical_factor
    )
    # El perfil completo se usa para alimentar la gráfica longitudinal de la
    # escena activa.  No se adjunta por defecto porque las verificaciones de
    # control DALI se serializan al cliente y no deben duplicar esta malla.
    if include_profile:
        verification["profile"] = profile
    return verification


def verify_night_base_scenario(
    lum_result, params: dict, scene_key: str = "night"
) -> dict:
    """Verifica una escena nocturna usando solo la capa BASE instalada.

    ``night_normal`` conserva los puntos de operación diurnos de la BASE.
    ``night`` y ``night_reduced`` usan los puntos regulados ``night_*``.
    """
    import copy
    from modules.tunnel.luminaires import physical_luminaires_per_setpoint

    base_result = copy.deepcopy(lum_result)
    base_result.zones = [
        zone for zone in base_result.zones
        if str(getattr(zone, "control_layer", "legacy") or "legacy")
        == "permanent"
    ]
    if not base_result.zones:
        return {
            "available": False,
            "error": "La instalación no contiene una capa BASE permanente.",
        }

    normal_night = scene_key == "night_normal"
    resolved_scene = "night_normal" if normal_night else "night_reduced"
    L_night = max(0.0, float(
        params.get(
            "L_night_normal" if normal_night else "L_night_reduced",
            params.get("Lin" if normal_night else "L_night", 1.0),
        ) or 1.0
    ))
    for zone in base_result.zones:
        zone.zone_name = "NOCHE BASE"
        zone.L_required = L_night
        zone.L_total_required = L_night
        for setpoint in zone.setpoints or []:
            setpoint["L_req"] = L_night
            setpoint["L_total_req"] = L_night
            # Una consigna manual de escena se guarda sin tocar el diseÃ±o
            # instalado. Si existe, sustituye el punto nocturno que llega a la
            # malla CIE 140 tanto en noche normal como en noche reducida.
            scene_operation = setpoint.get(
                "scenario_operating_points", {}
            ).get(resolved_scene)
            if scene_operation is not None:
                setpoint["flux_lm"] = float(
                    scene_operation.get("flux_lm", 0.0) or 0.0
                )
                setpoint["target_flux_lm"] = float(
                    scene_operation.get(
                        "target_flux_lm", setpoint["flux_lm"],
                    ) or setpoint["flux_lm"]
                )
                setpoint["current_mA"] = float(
                    scene_operation.get("current_mA", 0.0) or 0.0
                )
                setpoint["power_w"] = float(
                    scene_operation.get("power_w", 0.0) or 0.0
                )
            elif not normal_night:
                setpoint["flux_lm"] = float(
                    setpoint.get(
                        "night_flux_lm",
                        setpoint.get("night_target_flux_lm", 0.0),
                    ) or 0.0
                )
                setpoint["target_flux_lm"] = float(
                    setpoint.get(
                        "night_target_flux_lm", setpoint["flux_lm"]
                    ) or setpoint["flux_lm"]
                )
                setpoint["current_mA"] = float(
                    setpoint.get("night_current_mA", 0.0) or 0.0
                )
                setpoint["power_w"] = float(
                    setpoint.get("night_power_w", 0.0) or 0.0
                )
                setpoint["L_est"] = float(
                    setpoint.get("night_L_est", L_night) or L_night
                )
        if zone.setpoints:
            zone.n_luminaires = len(zone.setpoints)
            zone.flux_lm = round(float(zone.setpoints[0]["flux_lm"]), 0)
            zone.current_mA = round(float(zone.setpoints[0]["current_mA"]))
            zone.power_w = round(float(zone.setpoints[0]["power_w"]), 2)
            zone.L_estimated = round(float(zone.setpoints[0]["L_est"]), 3)
            zone.flux_zone_lm = round(sum(
                float(sp["flux_lm"]) for sp in zone.setpoints
            ), 0)
            zone.power_zone_w = round(sum(
                float(sp["power_w"]) for sp in zone.setpoints
            ), 2)
    base_result._compute_totals()

    # El perfil CIE 140 que se calcula a continuación ya contiene L, U0, Ul
    # y TI por campo/carril. Ejecutar además ``verify_luminaire_result``
    # duplicaba una segunda malla nocturna y no aportaba ninguna magnitud que
    # gobierne el resultado final.
    verification = {
        "available": True,
        "source": "CIE140_real_profile_by_lane",
    }
    profile = compute_real_luminance_profile(
        base_result,
        params,
        float(getattr(base_result, "road_width_m", 0.0) or 0.0),
        step_size=(
            1.0
            if float(getattr(base_result, "tube_length_m", 0.0) or 0.0)
            <= 500.0 else 2.0
        ),
    )
    if not profile.get("available") or not profile.get("fields"):
        return {
            "available": False,
            "error": profile.get(
                "error", "No se pudieron formar campos CIE 140 nocturnos."
            ),
            "verification": {
                "available": False,
                "source": "CIE140_real_profile_by_lane",
            },
        }

    night_params = dict(params)
    night_params["road_width_m"] = float(
        getattr(base_result, "road_width_m", 0.0) or 0.0
    )
    field_metrics = _profile_field_quality(profile, night_params)

    if not field_metrics:
        return {
            "available": False,
            "error": "Los campos nocturnos no contienen valores de luminancia.",
        }
    for field in profile.get("fields", []):
        field["L_required"] = round(L_night, 4)
        field["L_ratio"] = round(
            float(field.get("L", 0.0) or 0.0)
            / max(L_night, 1e-9),
            5,
        )
    for point in profile.get("points", []):
        point["L_required"] = round(L_night, 4)
    profile["scene"] = resolved_scene
    profile["L20_factor"] = 0.0
    profile["Lth_cd_m2"] = round(L_night, 4)
    TI_values = [
        float(item.get("TI", 0.0) or 0.0)
        for item in field_metrics
    ]
    minimum_Lavg = min(item["Lavg"] for item in field_metrics)
    minimum_U0 = min(item["U0"] for item in field_metrics)
    minimum_Ul = min(item["Ul"] for item in field_metrics)
    wall_criterion = _wall_luminance_criterion(params)
    wall_fields = [
        item for item in field_metrics
        if item.get("wall", {}).get("available", False)
    ]
    minimum_wall_ratio = min(
        (float(item["wall"]["ratio"]) for item in wall_fields),
        default=float("inf"),
    )
    wall_ok = (
        minimum_wall_ratio + 1e-9 >= float(wall_criterion["ratio"])
        if wall_fields else True
    )
    # Paredes: reportadas, no gobiernan el diseno (igual que en diurnas).
    maximum_TI = max(TI_values) if TI_values else None
    U0_required = float(params.get("U0_obj", 0.40) or 0.40)
    Ul_required = float(params.get("Ul_obj", 0.60) or 0.60)
    # Paredes: reportadas, no gobiernan el diseno (igual que en diurnas).
    compliant = (
        minimum_Lavg + 1e-9 >= L_night
        and minimum_U0 + 1e-9 >= U0_required
        and minimum_Ul + 1e-9 >= Ul_required
        and (maximum_TI is None or maximum_TI <= 15.0 + 1e-9)
    )
    return {
        "available": True,
        "scene": resolved_scene,
        "L20_factor": 0.0,
        "target_cd_m2": round(L_night, 3),
        "minimum_field_Lavg_cd_m2": round(minimum_Lavg, 3),
        "minimum_U0": round(minimum_U0, 4),
        "minimum_Ul": round(minimum_Ul, 4),
        "minimum_wall_ratio": (
            round(minimum_wall_ratio, 4) if wall_fields else None
        ),
        "wall_ratio_required": round(float(wall_criterion["ratio"]), 4),
        "maximum_TI_pct": (
            round(maximum_TI, 2) if maximum_TI is not None else None
        ),
        "n_fields": len(field_metrics),
        "compliant": compliant,
        "operating_power_kw": round(
            float(getattr(base_result, "total_power_kw", 0.0) or 0.0),
            3,
        ),
        "active_luminaires": (
            sum(
                1
                for zone in base_result.zones
                for setpoint in zone.setpoints or []
                if float(setpoint.get("flux_lm", 0.0) or 0.0) > 1e-9
            ) * physical_luminaires_per_setpoint(
                getattr(base_result, "arrangement", "") or ""
            )
        ),
        "profile": profile,
        "verification": verification,
    }
