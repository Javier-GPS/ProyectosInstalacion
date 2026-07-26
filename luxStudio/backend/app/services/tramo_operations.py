import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from ..models import Tramo
from ..models.catalog import Difusor, Gama, LedType, Lente, ValidCombination
from ..schemas.models import CalculationConfig, TramoInfo
from .calculator import calculate_config
from .catalog_service import get_eficiencia
from .ldt_matcher import require_ldt_for_config
from .luminaire_catalog import clamp_power_to_pmax, max_power_for_optimizer
from .optimizer import lavg_compliant, optimize_power_for_config, power_can_fix_failures, run_flux_optimization

log = logging.getLogger(__name__)


def _is_no_pcb_capacity(optimization) -> bool:
    if getattr(optimization, "feasible", True):
        return False
    message = (getattr(optimization, "message", "") or "").lower()
    if not any(token in message for token in ("no_pcb", "max_flux_insufficient", "no hay una pcb", "no pcb")):
        return False
    result = getattr(optimization, "result", None)
    if result is not None and lavg_compliant(result):
        return False
    return True


def _is_no_pcb_error(exc: Exception) -> bool:
    message = (str(exc) or "").lower()
    return any(token in message for token in ("no pcb", "no hay una pcb", "ninguna pcb"))


def calculation_config_hash(config: dict) -> str:
    visual_only = {
        "illuminance_scale_mode", "illuminance_scale_min", "illuminance_scale_max",
        "photometric_display_unit", "generate_buildings", "building_height",
        "buildings_as_obstacles", "median_width", "language",
    }
    clean = {k: v for k, v in config.items() if k not in visual_only and k != "__configHash"}
    return json.dumps(clean, separators=(",", ":"))


def is_valid_combo(db: Session, gama: str, difusor: str, lente: str, led_type: Optional[str]) -> bool:
    g = db.query(Gama).filter(Gama.name == gama).first()
    d = db.query(Difusor).filter(Difusor.name == difusor).first()
    l = db.query(Lente).filter(Lente.name == lente).first()
    lt = db.query(LedType).filter(LedType.name == led_type).first() if led_type else None
    if not all([g, d, l]):
        return False

    combo = db.query(ValidCombination).filter(
        ValidCombination.gama_id == g.id,
        ValidCombination.difusor_id == d.id,
        ValidCombination.lente_id == l.id,
        ValidCombination.led_type_id == (lt.id if lt else None),
    ).first()
    return combo is not None


def _persist_calculation_result(db: Session, tramo: Tramo, raw: dict, result, *, no_pcb_capacity: bool, refresh: bool = True) -> None:
    persisted_config = dict(raw)
    persisted_config.update(result.config.model_dump())
    result_dict = result.model_dump()
    if no_pcb_capacity:
        result_dict["__status"] = "no_pcb_capacity"
    result_dict["__configHash"] = calculation_config_hash(persisted_config)
    tramo.config_json = json.dumps(persisted_config)
    tramo.result_json = json.dumps(result_dict)
    tramo.last_calculated_at = datetime.now(timezone.utc)
    db.commit()
    if refresh:
        db.refresh(tramo)


def bulk_calculate_tramos(
    db: Session,
    tramos: list[Tramo],
    to_info: Callable[[Tramo], TramoInfo],
    margen_lavg: float = 0.0,
    t_amb_c: float = 25.0,
    i_op_ma: float | None = None,
    lm_w_min: float | None = None,
) -> tuple[list[TramoInfo], list[dict]]:
    updated: list[TramoInfo] = []
    failed: list[dict] = []
    _eff_cache: dict[tuple[str | None, str | None], tuple[float, float]] = {}
    for tramo in tramos:
        raw: dict = {}
        try:
            raw = json.loads(tramo.config_json) if tramo.config_json else {}
            raw.pop("__configHash", None)
            missing_fields = [k for k in ("gama", "difusor", "lente", "led_type") if not str(raw.get(k) or "").strip()]
            if missing_fields:
                raise ValueError(f"Faltan datos de configuración: {', '.join(missing_fields)}")
            raw["margen_lavg"] = margen_lavg
            raw["t_amb_c"] = t_amb_c
            raw["i_op_ma"] = i_op_ma
            raw["lm_w_min"] = lm_w_min
            config = CalculationConfig(**raw)
            combo = (config.lente, config.difusor)
            if combo not in _eff_cache:
                _eff_cache[combo] = get_eficiencia(db, config.lente, config.difusor)
            lente_eff, difusor_eff = _eff_cache[combo]
            optimized = config
            no_pcb_capacity = False
            try:
                optimization = run_flux_optimization(db, config, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)
                if optimization.config is not None:
                    optimized = optimization.config
                no_pcb_capacity = _is_no_pcb_capacity(optimization)
            except Exception:
                log.warning(
                    "flux optimization failed for tramo id=%s: %s",
                    tramo.id, traceback.format_exc(),
                )
            try:
                result = calculate_config(db, optimized, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)
            except Exception as exc:
                if not _is_no_pcb_error(exc):
                    raise
                no_pcb_capacity = True
                fallback = optimized.model_copy(update={"target_flux": None})
                result = calculate_config(db, fallback, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)
            _persist_calculation_result(db, tramo, raw, result, no_pcb_capacity=no_pcb_capacity, refresh=False)
            updated.append(to_info(tramo))
        except Exception as exc:
            db.rollback()
            log.warning(
                "bulk-calculate failed for tramo id=%s name=%r: %s\n%s",
                tramo.id, tramo.name, exc, traceback.format_exc(),
            )
            failed.append({"id": tramo.id, "name": tramo.name, "error": str(exc) or exc.__class__.__name__})
    return updated, failed


def bulk_adjust_power_tramos(db: Session, tramos: list[Tramo]) -> list[dict]:
    items: list[dict] = []
    for tramo in tramos:
        try:
            raw = json.loads(tramo.config_json) if tramo.config_json else {}
            raw.pop("__configHash", None)
            missing_fields = [k for k in ("gama", "difusor", "lente", "led_type", "power") if not str(raw.get(k) or "").strip()]
            if missing_fields:
                raise ValueError(f"Faltan datos de configuración: {', '.join(missing_fields)}")

            config = CalculationConfig(**raw)
            prev_power = config.power
            config = clamp_power_to_pmax(db, config)
            ldt_id, _ = require_ldt_for_config(config)

            if ldt_id.startswith("temp-"):
                items.append({"tramo_id": tramo.id, "success": False, "previous_power": prev_power, "error": "LDT externa, no se puede optimizar"})
                continue

            pmax = max_power_for_optimizer(db, config)
            feasible, _checked, result, failures = optimize_power_for_config(config, ldt_id, pmax, compliant_check=lavg_compliant)

            if feasible:
                new_power = result.config.power
            elif power_can_fix_failures(result) and pmax != prev_power:
                new_power = pmax
            else:
                items.append({"tramo_id": tramo.id, "success": False, "previous_power": prev_power, "error": failures})
                continue

            if new_power == prev_power and feasible:
                items.append({"tramo_id": tramo.id, "success": True, "previous_power": prev_power, "new_power": new_power})
                continue

            raw["power"] = new_power
            tramo.config_json = json.dumps(raw)
            tramo.result_json = None
            tramo.last_calculated_at = None
            db.commit()
            db.refresh(tramo)
            items.append({"tramo_id": tramo.id, "success": True, "previous_power": prev_power, "new_power": new_power})
        except Exception as exc:
            db.rollback()
            log.warning("bulk-adjust-power failed for tramo id=%s name=%r: %s\n%s", tramo.id, tramo.name, exc, traceback.format_exc())
            items.append({"tramo_id": tramo.id, "success": False, "error": str(exc) or exc.__class__.__name__})
    return items
