from typing import Optional

from sqlalchemy.orm import Session

from ..core.interpolate import interpolate
from ..core.led_flux import led_flux_factor
from ..salvi_lighting import evaluate, Photometry
from ..schemas.models import CalculationConfig, CalculationResult, CriterionResult, ElementResult, FotometriaInfo
from .catalog_service import get_eficiencia
from .electrical import total_system_power
from .geometry import effective_overhang, luminaire_mounting_height
from .ldt_loader import get_all_ldts, get_ldt_by_id, get_photometry
from .ldt_matcher import require_ldt_for_config
from .luminaire_catalog import clamp_power_to_pmax
from .pcb_selector import select_pcb_for_config

POWER_LAW_EXPONENT = 0.832


def prepare_config_for_calculation(db: Session, config: CalculationConfig) -> CalculationConfig:
    if config.target_flux and config.target_flux > 0:
        has_catalog_selection = all(
            [config.gama, config.difusor, config.lente, config.led_type]
        )
        if has_catalog_selection:
            detail = select_pcb_for_config(db, config)
            if detail is not None and detail.p_total > 0:
                driver_eff = detail.driver_eficiencia or config.driver_eficiencia
                system_power = total_system_power(detail.p_total, driver_eff)
                config = config.model_copy(
                    update={
                        "power": round(system_power, 2),
                        "target_flux": detail.flux,
                    }
                )
        return clamp_power_to_pmax(db, config)
    # ponytail: normal EN/DIALux calculation is power-based; flux/PCB mode stays in /optimize/flux and /ldt/flux-detail.
    return clamp_power_to_pmax(db, config.model_copy(update={"target_flux": None}))


def calculate_config(db: Session, config: CalculationConfig, *, lente_eficiencia: float | None = None, difusor_eficiencia: float | None = None) -> CalculationResult:
    config = prepare_config_for_calculation(db, config)
    if lente_eficiencia is None or difusor_eficiencia is None:
        lente_eff, difusor_eff = get_eficiencia(db, config.lente, config.difusor)
    else:
        lente_eff, difusor_eff = lente_eficiencia, difusor_eficiencia
    ldt_id, _ = require_ldt_for_config(config)
    return run_calculation(config, ldt_id, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)


def _power_law_flux(ref_power: float, ref_flux: float, target_power: float) -> float:
    if ref_power <= 0 or target_power <= 0:
        return ref_flux
    return ref_flux * (target_power / ref_power) ** POWER_LAW_EXPONENT


def _effective_mf(config_mf: float, ldt_info: dict | None) -> float:
    """Return the maintenance factor actually applied to the candela values.

    Salvi LDTs are exported at LOR=1.0 (no MF baked in), so ``mf_origen``
    defaults to 1.0 and the user-supplied ``config.mf`` is applied verbatim.
    For the rare case of an LDT that already has a depreciation factor
    baked in (``mf_origen<1``), the effective factor is ``config.mf /
    ldt.mf_origen`` to avoid double-applying the loss.
    """
    mf_origen = float((ldt_info or {}).get("mf_origen", 1.0) or 1.0)
    if mf_origen <= 0:
        return float(config_mf)
    return float(config_mf) / mf_origen


def run_calculation(config: CalculationConfig, ldt_id: str, lente_eficiencia: float = 1.0, difusor_eficiencia: float = 1.0) -> CalculationResult:
    photometry = get_photometry(ldt_id)
    if photometry is None:
        raise ValueError(f"LDT not found: {ldt_id}")

    ldt_info = get_ldt_by_id(ldt_id)
    if ldt_info is None:
        raise ValueError(f"LDT metadata not found: {ldt_id}")

    if ldt_id.startswith("temp-"):
        raise ValueError(
            f"External LDTs (temp-) are no longer supported: {ldt_id}"
        )

    target_info = _target_luminaire_info(config, photometry, ldt_info, lente_eficiencia, difusor_eficiencia)
    flux_scale = target_info["flux"] / photometry.flux if photometry.flux else 1.0
    return run_calculation_with_photometry(config, photometry, target_info, flux_scale=flux_scale)


def run_calculation_with_photometry(
    config: CalculationConfig,
    photometry: Photometry,
    ldt_info: dict,
    flux_scale: float = 1.0,
) -> CalculationResult:
    cfg = _config_to_cfg(config, photometry, ldt_info)
    result = evaluate(cfg, photometry, flux_scale=flux_scale, road=config.pavement)
    criteria = _build_criteria(result)
    el_results = [ElementResult(**er) for er in (result.get("_element_results") or [])]

    return CalculationResult(
        config=config,
        compliant=all(c.passed for c in criteria if c.is_compliance_criterion) if criteria else result.get("compliant", False),
        mode=result.get("mode", "ME"),
        elements=el_results,
        luminaire=FotometriaInfo(
            id=ldt_info["id"],
            filename=ldt_info["filename"],
            luminaire_name=ldt_info["luminaire_name"],
            manufacturer=ldt_info.get("manufacturer", "Unknown"),
            model_family=ldt_info.get("model_family", "UNKNOWN"),
            cct=ldt_info.get("cct", config.cct),
            cri=ldt_info.get("cri", config.cri),
            optic_family=ldt_info["optic_family"],
            power=ldt_info["power"],
            flux=ldt_info["flux"],
            efficiency=ldt_info["efficiency"],
            LORL=ldt_info["LORL"],
            isym=ldt_info["isym"],
            gama=ldt_info.get("gama"),
            difusor=ldt_info.get("difusor"),
            lente=ldt_info.get("lente"),
            led_type=ldt_info.get("led_type"),
            fotometria=ldt_info.get("fotometria"),
            mf_origen=float(ldt_info.get("mf_origen", 1.0) or 1.0),
        ),
        criteria=criteria,
        Lavg=result.get("Lavg"),
        Uo=result.get("Uo"),
        Ul=result.get("Ul"),
        TI=result.get("TI"),
        SR=result.get("SR"),
        EIR=result.get("EIR"),
        Eavg=result.get("Eavg"),
        Emin=result.get("Emin"),
        sidewalk_left_Eavg=result.get("sidewalk_left_Eavg"),
        sidewalk_left_Emin=result.get("sidewalk_left_Emin"),
        sidewalk_left_class=result.get("sidewalk_left_class"),
        sidewalk_right_Eavg=result.get("sidewalk_right_Eavg"),
        sidewalk_right_Emin=result.get("sidewalk_right_Emin"),
        sidewalk_right_class=result.get("sidewalk_right_class"),
    )


def _config_to_cfg(config: CalculationConfig, photometry: Photometry, ldt_info: dict | None = None) -> dict:
    cfg: dict = {
        "arrangement": config.arrangement,
        "h": luminaire_mounting_height(config),
        "S": config.spacing,
        "arm": effective_overhang(config),
        "tilt": config.tilt,
        "mf": _effective_mf(config.mf, ldt_info),
        "pole_side": config.pole_side,
        "sidewalk_left": config.sidewalk_left,
        "sidewalk_right": config.sidewalk_right,
        "sidewalk_left_class": config.sidewalk_left_class,
        "sidewalk_right_class": config.sidewalk_right_class,
        "median_width": config.median_width,
    }

    if config.road_elements:
        elements = []
        y_pos = 0.0
        for el in config.road_elements:
            entry: dict = {
                "type": el.type,
                "width": el.width,
                "y_start": y_pos,
                "y_end": y_pos + el.width,
            }
            if el.type == "carriageway":
                entry["lanes"] = el.lanes or 2
                entry["lighting_class"] = el.lighting_class or "M3"
            elif el.type == "sidewalk":
                entry["pedestrian_class"] = el.pedestrian_class or "P4"
            elements.append(entry)
            y_pos += el.width
        cfg["W"] = y_pos
        cfg["road_elements"] = elements
        cfg["lanes"] = elements[0].get("lanes", config.lanes) if elements else config.lanes
        cfg["class"] = elements[0].get("lighting_class", config.lighting_class) if elements else config.lighting_class
    else:
        cfg["W"] = config.road_width
        cfg["lanes"] = config.lanes
        cfg["class"] = config.lighting_class

    return cfg


def _target_luminaire_info(config: CalculationConfig, photometry: Photometry, reference_info: dict, lente_eficiencia: float = 1.0, difusor_eficiencia: float = 1.0) -> dict:
    target = dict(reference_info)
    ref_cri = int(reference_info.get("cri", 70) or 70)
    ref_cct = int(reference_info.get("cct", config.cct) or config.cct)

    if config.target_flux is not None and config.target_flux > 0:
        target_flux = float(config.target_flux)
        eff_divisor = max(float(config.power), 0.01)
        # EULUMDAT wattage is total system power including control gear, so
        # target-flux configurations already use input power.  Applying the
        # driver factor here again would double-count its losses.
        efficiency = round(target_flux / eff_divisor, 1)
    elif all([bool(config.gama), bool(config.difusor), bool(config.lente), bool(config.led_type)]):
        target_flux = _linear_flux_from_reference(
            float(photometry.power), float(photometry.flux), float(config.power),
        )
        target_flux *= led_flux_factor(config.cct, config.cri, ref_cct, ref_cri)
        target_flux *= lente_eficiencia * difusor_eficiencia
        efficiency = round(target_flux / max(float(config.power), 0.01), 1)
    elif abs(config.power - photometry.power) / max(photometry.power, 0.1) < 0.01:
        target_flux = float(photometry.flux) * led_flux_factor(config.cct, config.cri, ref_cct, ref_cri)
        efficiency = round(target_flux / max(float(config.power), 0.01), 1)
    else:
        target_flux = _estimate_flux_for_config(config, reference_info)
        if target_flux is None:
            ref_eff = reference_info.get("efficiency") or getattr(photometry, "eff", None)
            target_flux = float(config.power) * float(ref_eff) if ref_eff else _power_law_flux(photometry.power, photometry.flux, float(config.power))
        target_flux *= led_flux_factor(config.cct, config.cri, ref_cct, ref_cri)
        target_flux *= lente_eficiencia * difusor_eficiencia
        efficiency = round(target_flux / max(float(config.power), 0.01), 1)

    target.update(power=float(config.power), cct=int(config.cct), cri=int(config.cri),
                  flux=float(target_flux), efficiency=efficiency)
    return target


def _linear_flux_from_reference(ref_power: float, ref_flux: float, target_power: float) -> float:
    """Scale a catalog photometry to the selected commercial power.

    The BBDD workbook selects the photometric curve for a 4-tuple while
    the Salvi references workbook defines the usable LED power range.
    DIALux keeps the LDT intensity shape and scales the cd/klm curve by
    the luminaire flux, so catalog calculations must preserve the
    reference lm/W instead of applying the legacy sub-linear extrapolator.
    """
    if ref_power <= 0 or target_power <= 0:
        return ref_flux
    return ref_flux * (target_power / ref_power)


def _estimate_flux_for_config(config: CalculationConfig, reference_info: dict) -> Optional[float]:
    candidates = [
        ldt for ldt in get_all_ldts()
        if ldt.get("manufacturer", "Unknown") == reference_info.get("manufacturer", "Unknown")
        and ldt.get("model_family", "UNKNOWN") == reference_info.get("model_family", "UNKNOWN")
        and ldt.get("optic_family") == reference_info.get("optic_family")
        and int(ldt.get("cri", 70) or 70) == int(reference_info.get("cri", 70) or 70)
    ]
    if not candidates:
        return None

    cct_points = []
    for cct in sorted({int(item.get("cct", config.cct)) for item in candidates}):
        power_points = sorted(
            (
                (float(item["power"]), float(item["flux"]))
                for item in candidates
                if int(item.get("cct", config.cct)) == cct and float(item.get("power", 0)) > 0
            ),
            key=lambda point: point[0],
        )
        if len(power_points) == 1 and abs(power_points[0][0] - config.power) > 1e-9:
            flux_at_power = _power_law_flux(power_points[0][0], power_points[0][1], config.power)
        else:
            flux_at_power = interpolate(config.power, power_points)
        if flux_at_power is not None:
            cct_points.append((float(cct), flux_at_power))

    return interpolate(config.cct, cct_points)


def _build_criteria(result: dict) -> list[CriterionResult]:
    criteria = []
    mode = result.get("mode", "ME")
    req = result.get("req", {})

    if mode == "ME":
        # SR is the aggregate surround ratio used for ME compliance.
        # EIR/REI (min side ratio) is shown for information only.
        for key, name, fmt in [
            ("Lavg", "Lavg (cd/m²)", ".2f"),
            ("Uo", "Uo", ".2f"),
            ("Ul", "Ul", ".2f"),
            ("TI", "TI (%)", ".2f"),
            ("SR", "SR", ".2f"),
            ("EIR", "REI (info)", ".2f"),
        ]:
            ok_key = f"ok_{key.split('(')[0].strip()}"
            if key == "Lavg":
                ok_key = "ok_L"
            elif key in ("SR", "EIR"):
                ok_key = "ok_SR"
            is_info_only = key == "EIR"
            criteria.append(CriterionResult(
                name=name,
                value=result.get(key) or 0,
                required=req.get({"Lavg": "L", "Uo": "Uo", "Ul": "Ul", "TI": "TI", "SR": "SR", "EIR": "SR"}.get(key, key)) or 0,
                passed=result.get(ok_key, False) if not is_info_only else True,
                is_compliance_criterion=not is_info_only,
            ))
    elif mode == "P":
        for key, name in [("Eavg", "Eavg (lux)"), ("Emin", "Emin (lux)")]:
            ok_key = f"ok_{key}"
            criteria.append(CriterionResult(
                name=name,
                value=result.get(key) or 0,
                required=req.get(key) or 0,
                passed=result.get(ok_key, False),
            ))

    # Sidewalk criteria — handles legacy "left"/"right" and element-based "e0", "e1", …
    sw_keys = {k.replace("sidewalk_", "").replace("_class", "") for k in result if k.startswith("sidewalk_") and k.endswith("_class")}
    sw_labels = {"left": "Izquierda", "right": "Derecha"}
    for sw_key in sorted(sw_keys, key=lambda key: (0, int(key[1:])) if key.startswith("e") and key[1:].isdigit() else (1, key)):
        sw_class = result.get(f"sidewalk_{sw_key}_class")
        if not sw_class:
            continue
        sw_req = result.get(f"sidewalk_{sw_key}_req", {})
        if sw_key.startswith("e") and sw_key[1:].isdigit():
            label = f"SW {int(sw_key[1:]) + 1}"
        else:
            label = sw_labels.get(sw_key, f"#{sw_key}")
        for key, name in [("Eavg", "Eavg (lux)"), ("Emin", "Emin (lux)")]:
            criteria.append(CriterionResult(
                name=f"Acera {label} - {name}",
                value=result.get(f"sidewalk_{sw_key}_{key}") or 0,
                required=sw_req.get(key) or 0,
                passed=result.get(f"sidewalk_{sw_key}_ok_{key}", True),
            ))

    return criteria
