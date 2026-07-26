from ..salvi_lighting import calc_luminance, calc_road, calc_sidewalk
from ..schemas.models import CalculationConfig, CalculationResult
from .geometry import effective_overhang, luminaire_mounting_height
from .i18n import translator
from .ldt_loader import get_photometry


def calculation_config_dict(config: CalculationConfig) -> dict:
    return {
        "arrangement": config.arrangement,
        "h": luminaire_mounting_height(config),
        "S": config.spacing,
        "W": config.road_width,
        "arm": effective_overhang(config),
        "tilt": config.tilt,
        "mf": config.mf,
        "class": config.lighting_class,
        "pole_side": config.pole_side,
        "sidewalk_left": config.sidewalk_left,
        "sidewalk_right": config.sidewalk_right,
    }


def calculation_grids(result: CalculationResult, ldt_id: str) -> dict:
    t = translator(result.config.language)
    photometry = get_photometry(ldt_id)
    if photometry is None:
        return {}
    cfg = calculation_config_dict(result.config)
    flux_scale = 1.0
    if getattr(photometry, "flux", 0):
        flux_scale = result.luminaire.flux / photometry.flux
    grids = {}
    try:
        road = calc_road(cfg, photometry, flux_scale=flux_scale)
        grids["illuminance"] = {
            "title": t("svg.roadway_illuminance"),
            "unit": "lux",
            "xs": road["xs"],
            "ys": road["ys"],
            "values": road["Egrid"],
            "avg": road["Eavg"],
            "min": road["Emin"],
            "max": road["Emax"],
            "zone": "roadway",
        }
    except Exception:
        pass
    if result.mode == "ME":
        try:
            lum = calc_luminance(cfg, photometry, flux_scale=flux_scale, road=result.config.pavement)
            grids["luminance"] = {
                "title": t("svg.roadway_luminance"),
                "unit": "cd/m²",
                "xs": lum["xs"],
                "ys": lum["ys"],
                "values": lum["Lgrid"],
                "avg": lum["Lavg"],
                "min": lum["Lmin"],
                "max": lum["Lmax"],
                "zone": "observer",
                "observer": lum.get("obs"),
                "pavement": result.config.pavement,
            }
        except Exception:
            pass
    for side, skey in [("left", "sidewalk_left"), ("right", "sidewalk_right")]:
        if cfg.get(skey, 0) <= 0:
            continue
        try:
            sw = calc_sidewalk(cfg, photometry, flux_scale=flux_scale, side=side)
            if sw:
                sname = f"sidewalk_{side}"
                label = {"left": "Izquierda", "right": "Derecha"}[side]
                grids[sname] = {
                    "title": f"Acera {label}",
                    "unit": "lux",
                    "xs": sw["xs"],
                    "ys": sw["ys"],
                    "values": sw["Egrid"],
                    "avg": sw["Eavg"],
                    "min": sw["Emin"],
                    "max": sw["Emax"],
                    "zone": "sidewalk",
                }
        except Exception:
            pass
    return grids
