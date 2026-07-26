"""Power and configuration optimizers for the calculation engine.

Public surface used by the routers:
- ``run_simple_optimization`` (drives ``/optimize/simple``)
- ``run_flux_optimization`` (drives ``/optimize/flux``)
- ``run_advanced_optimization`` (drives ``/optimize/advanced``)
- ``run_advanced_optimization_batch`` (drives ``/optimize/advanced-batch``)
- ``fixed_parameters_for`` (helper for the response payload)
- ``advanced_objective_label`` (translates the objective code to its label)

Internal layers:
- :mod:`._constants` — shared constants (candidates, fixed-parameter list)
- :mod:`.power` — power/flux binary search loops + criterion helpers
- :mod:`.advanced` — multi-variable exhaustive search + scoring
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ...database import SessionLocal
from ...schemas.models import (
    AdvancedOptimizationRequest,
    BatchCalculationItem,
    BatchCalculationResponse,
    CalculationConfig,
    OptimizationResponse,
)
from ..calculator import run_calculation
from ..catalog_service import get_eficiencia
from ..i18n import translator
from ..ldt_matcher import require_ldt_for_config
from ..luminaire_catalog import (
    clamp_power_to_pmax,
    max_power_for_optimizer,
)
from ..pcb_selector import select_pcb_for_flux
from ._constants import OPTIMIZATION_OBJECTIVE
from .power import (
    lavg_compliant,
    lavg_requirement,
    optimize_flux_for_config,
    optimize_power_for_config,
    power_can_fix_failures,  # noqa: F401 — re-exported for tramo_operations
    with_updates,
)
from . import power as _power_module
from .advanced import (
    advanced_objective_label,
    fixed_parameters_for,
    optic_candidates,
    run_smart_search,
)


def _optimize_flux_for_config(*args, **kwargs):
    """Back-compat wrapper preserving old module-level monkeypatch hooks."""
    _power_module.select_pcb_for_flux = select_pcb_for_flux
    _power_module.run_calculation = run_calculation
    return optimize_flux_for_config(*args, **kwargs)


def _lavg_compliant_with_margin(margen_pct: float):
    """Return a compliance checker that applies a percentage margin to Lavg."""
    if margen_pct <= 0:
        return lavg_compliant
    def checker(result: CalculationResult) -> bool:
        for c in result.criteria:
            name = c.name.upper()
            if name.startswith("LAVG") or name.startswith("EAVG"):
                required = float(c.required or 0)
                value = float(c.value or 0)
                if required > 0:
                    adjusted = required * (1.0 + margen_pct / 100.0)
                    return value >= adjusted
        return result.compliant
    return checker


def run_simple_optimization(
    db,
    config: CalculationConfig,
    *,
    lente_eficiencia: float | None = None,
    difusor_eficiencia: float | None = None,
) -> OptimizationResponse:
    """Find the lowest compliant power while keeping geometry and luminaire fixed."""
    config = clamp_power_to_pmax(db, config)
    if lente_eficiencia is None or difusor_eficiencia is None:
        lente_eff, difusor_eff = get_eficiencia(db, config.lente, config.difusor)
    else:
        lente_eff, difusor_eff = lente_eficiencia, difusor_eficiencia
    ldt_id, _ = require_ldt_for_config(config)
    t = translator(config.language)

    if ldt_id.startswith("temp-"):
        exact_result = run_calculation(config, ldt_id, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)
        return OptimizationResponse(
            feasible=False,
            message=t("opt.external_simple"),
            objective=OPTIMIZATION_OBJECTIVE,
            fixed_parameters=fixed_parameters_for({"power"}),
            checked=1,
            config=config,
            result=exact_result,
        )

    margen_pct = config.margen_lavg or 0.0
    compliant_check = _lavg_compliant_with_margin(margen_pct)

    pmax = max_power_for_optimizer(db, config)
    feasible, checked, result, failures = optimize_power_for_config(
        config, ldt_id, pmax, compliant_check=compliant_check, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff,
    )
    if not feasible:
        return OptimizationResponse(
            feasible=False,
            message=t("opt.no_power", failures=failures),
            objective=OPTIMIZATION_OBJECTIVE,
            fixed_parameters=fixed_parameters_for({"power"}),
            checked=checked,
            config=config,
            result=result,
        )

    return OptimizationResponse(
        feasible=True,
        message=t("opt.minimum_power", power=result.config.power),
        objective=OPTIMIZATION_OBJECTIVE,
        fixed_parameters=fixed_parameters_for({"power"}),
        checked=checked,
        config=result.config,
        result=result,
    )


def run_flux_optimization(
    db,
    config: CalculationConfig,
    *,
    lente_eficiencia: float | None = None,
    difusor_eficiencia: float | None = None,
) -> OptimizationResponse:
    """Find the smallest ``target_flux`` so Lavg is >= the class requirement.

    The optimization nudges the user-supplied luminous flux up or down
    (and lets the V2 LED model re-pick a PCB / current) until the
    resulting Lavg matches the EN 13201 class limit as closely as
    possible while staying above it.  Falls back to
    ``run_simple_optimization`` when the class has no Lavg
    requirement or the 4-tuple is incomplete.
    """
    t = translator(config.language)
    if lente_eficiencia is None or difusor_eficiencia is None:
        lente_eff, difusor_eff = get_eficiencia(db, config.lente, config.difusor)
    else:
        lente_eff, difusor_eff = lente_eficiencia, difusor_eficiencia

    if not all([config.gama, config.difusor, config.lente, config.led_type]):
        # Without a 4-tuple the PCB selector cannot resolve a flux;
        # delegate to the power-based optimizer.
        return run_simple_optimization(db, config, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)

    config = clamp_power_to_pmax(db, config)
    ldt_id, _ = require_ldt_for_config(config)

    if ldt_id.startswith("temp-"):
        exact_result = run_calculation(config, ldt_id, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)
        return OptimizationResponse(
            feasible=False,
            message=t("opt.external_simple"),
            objective=OPTIMIZATION_OBJECTIVE,
            fixed_parameters=fixed_parameters_for({"target_flux"}),
            checked=1,
            config=config,
            result=exact_result,
        )

    # Probe once at the current operating point to read the Lavg
    # requirement for the class.  We need this before we can target
    # the right value, and a single run is cheap.
    seed_config = config.model_copy(update={"target_flux": None}) if (config.target_flux and config.target_flux > 0) else config
    seed_result = run_calculation(
        seed_config, ldt_id,
        lente_eficiencia=lente_eff,
        difusor_eficiencia=difusor_eff,
    )
    target_lavg = lavg_requirement(seed_result)
    if target_lavg is None:
        return OptimizationResponse(
            feasible=False,
            message=t("opt.no_lavg"),
            objective=OPTIMIZATION_OBJECTIVE,
            fixed_parameters=fixed_parameters_for({"target_flux"}),
            checked=1,
            config=config,
            result=seed_result,
        )

    margen_pct = config.margen_lavg or 0.0
    if margen_pct > 0:
        target_lavg = target_lavg * (1.0 + margen_pct / 100.0)

    feasible, checked, result, failures, optimized_config = optimize_flux_for_config(
        db, config, ldt_id, target_lavg,
        lente_eficiencia=lente_eff,
        difusor_eficiencia=difusor_eff,
    )
    if not feasible:
        return OptimizationResponse(
            feasible=False,
            message=t("opt.no_flux", failures=failures) if failures != "max_flux_insufficient" and failures != "no_pcb" else t("opt.no_flux", failures=failures),
            objective=OPTIMIZATION_OBJECTIVE,
            fixed_parameters=fixed_parameters_for({"target_flux"}),
            checked=checked,
            config=optimized_config,
            result=result,
        )

    final_flux = float(result.luminaire.flux or optimized_config.target_flux or 0)
    optimized_config = optimized_config.model_copy(update={"target_flux": final_flux})
    result = result.model_copy(update={"config": optimized_config})

    return OptimizationResponse(
        feasible=True,
        message=t(
            "opt.target_flux",
            lavg=target_lavg,
            flux=final_flux,
            power=float(optimized_config.power or 0),
        ),
        objective=OPTIMIZATION_OBJECTIVE,
        fixed_parameters=fixed_parameters_for({"target_flux"}),
        checked=checked,
        config=optimized_config,
        result=result,
    )


def run_advanced_optimization(
    db,
    request: AdvancedOptimizationRequest,
) -> OptimizationResponse:
    """Optimize selected installation variables against installed W/m."""
    config = request.config
    config = clamp_power_to_pmax(db, config)
    variables = request.variables
    objective = request.objective
    objective_label = advanced_objective_label(objective)
    t = translator(config.language)

    if getattr(variables, "optic_family", False) and request.optic_families:
        families = optic_candidates(config, request.optic_families)
        if not families:
            families = [config.optic_family]
        best: OptimizationResponse | None = None
        total = 0
        for optic in families:
            try:
                oc = with_updates(config, {"optic_family": optic, "lente": optic, "ldt_id": None}, "")
                oc = clamp_power_to_pmax(db, oc)
                le, de = get_eficiencia(db, oc.lente, oc.difusor)
                lid, _ = require_ldt_for_config(oc)
                if lid.startswith("temp-"):
                    continue
                pm = max_power_for_optimizer(db, oc, request.limits.power)
                cl = request.limits.model_copy(update={"power": pm} if pm is not None else {})
                r = run_smart_search(oc, variables, cl, objective, lid, objective_label, lente_eficiencia=le, difusor_eficiencia=de, db=db)
                total += r.checked
                if best is None:
                    best = r
                elif r.feasible and not best.feasible:
                    best = r
                elif r.feasible and best.feasible and r.config and best.config and r.config.power < best.config.power:
                    best = r
                elif not r.feasible and not best.feasible and r.result and best.result:
                    rf = sum(1 for c in r.result.criteria if not c.passed)
                    bf = sum(1 for c in best.result.criteria if not c.passed)
                    if rf < bf:
                        best = r
            except Exception:
                continue
        if best is not None:
            return best.model_copy(update={"checked": total})
        lid, _ = require_ldt_for_config(config)
        fb = run_calculation(config, lid)
        return OptimizationResponse(feasible=False, message=t("opt.no_advanced", failures="none"), objective=objective_label, fixed_parameters=[], checked=total, config=config, result=fb)

    lente_eff, difusor_eff = get_eficiencia(db, config.lente, config.difusor)
    ldt_id, _ = require_ldt_for_config(config)

    if ldt_id.startswith("temp-"):
        exact_result = run_calculation(config, ldt_id, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)
        return OptimizationResponse(
            feasible=False,
            message=t("opt.external_advanced"),
            objective=objective_label,
            fixed_parameters=fixed_parameters_for(set()),
            checked=1,
            config=config,
            result=exact_result,
        )

    pmax = max_power_for_optimizer(db, config, request.limits.power)
    capped_limits = request.limits.model_copy(update={"power": pmax} if pmax is not None else {})
    return run_smart_search(config, variables, capped_limits, objective, ldt_id, objective_label, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff, db=db)


def _optimize_single_optic(
    optic_family: str,
    config: CalculationConfig,
    variables,
    limits,
    objective: str,
    objective_label: str,
    row: int,
    language: str,
) -> BatchCalculationItem:
    """Run advanced search for one optic family (thread-safe, no DB dependency)."""
    db = SessionLocal()
    try:
        optic_config = with_updates(config, {"optic_family": optic_family, "lente": optic_family, "ldt_id": None}, "")
        optic_config = clamp_power_to_pmax(db, optic_config)
        lente_eff, difusor_eff = get_eficiencia(db, optic_config.lente, optic_config.difusor)
        ldt_id, _ = require_ldt_for_config(optic_config)
        if ldt_id.startswith("temp-"):
            raise ValueError(translator(language)("opt.external_batch"))
        pmax = max_power_for_optimizer(db, optic_config, limits.power)
        capped_limits = limits.model_copy(update={"power": pmax} if pmax is not None else {})
        response = run_smart_search(optic_config, variables, capped_limits, objective, ldt_id, objective_label, lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff, db=db)
        if not response.result or not response.config:
            raise ValueError(response.message)
        if not response.feasible:
            return BatchCalculationItem(
                model_id=f"{config.model_family or 'Luminaire'} {optic_family}",
                row=row,
                error=response.message,
                config=response.config,
                result=response.result,
            )
        return BatchCalculationItem(
            model_id=f"{config.model_family or 'Luminaire'} {optic_family}",
            row=row,
            config=response.config,
            result=response.result,
        )
    except Exception as exc:
        return BatchCalculationItem(
            model_id=f"{config.model_family or 'Luminaire'} {optic_family}",
            row=row,
            error=str(exc),
        )
    finally:
        db.close()


def run_advanced_optimization_batch(
    db,
    request: AdvancedOptimizationRequest,
) -> BatchCalculationResponse:
    """Optimize each selected optic and return one downloadable row per lens."""
    config = request.config
    config = clamp_power_to_pmax(db, config)
    variables = request.variables.model_copy(update={"optic_family": True})
    objective = request.objective
    objective_label = advanced_objective_label(objective)
    language = config.language

    optic_families = optic_candidates(config, request.optic_families)
    worker_args = [
        (optic_family, config, variables, request.limits, objective, objective_label, row + 1, language)
        for row, optic_family in enumerate(optic_families)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        items = list(executor.map(lambda args: _optimize_single_optic(*args), worker_args))

    return BatchCalculationResponse(
        filename=f"Optimized lenses - {config.manufacturer or ''} {config.model_family or ''}".strip(),
        count=len(items),
        items=items,
    )


__all__ = [
    "run_simple_optimization",
    "run_flux_optimization",
    "run_advanced_optimization",
    "run_advanced_optimization_batch",
    "fixed_parameters_for",
    "advanced_objective_label",
]
