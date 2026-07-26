"""Power and flux optimization search loops.

Binary-search the smallest power (or flux) that satisfies the active
EN 13201 criteria.  Used by the public ``run_simple_optimization`` and
``run_flux_optimization`` in :mod:`app.services.optimizer`.
"""
from __future__ import annotations

from typing import Callable, Optional

from ...schemas.models import CalculationConfig, CalculationResult
from ...services.calculator import run_calculation
from ...services.electrical import total_system_power
from ...services.pcb_selector import select_pcb_for_flux
from ._constants import (
    OPTIMIZATION_MAX_POWER,
    OPTIMIZATION_MIN_POWER,
    OPTIMIZATION_PRECISION,
)


# ---------------------------------------------------------------------------
# Criterion helpers
# ---------------------------------------------------------------------------

def failed_criteria(result: CalculationResult) -> str:
    failed = [item for item in result.criteria if not item.passed]
    if not failed:
        return "none"
    return ", ".join(
        f"{item.name}: {item.value:.3g} / required {item.required:.3g}"
        for item in failed
    )


def power_can_fix_failures(result: CalculationResult) -> bool:
    """Return whether increasing flux can plausibly fix the failed criteria.

    Average/minimum light level failures can be solved by more power. Uniformity,
    TI and SR are effectively geometry/optic problems in this optimizer, so
    pushing watts higher just hides the real lever and can select worse setups.
    """
    failed = [item.name.upper() for item in result.criteria if not item.passed]
    if not failed:
        return True
    return all(name.startswith(("LAVG", "EAVG", "EMIN")) for name in failed)


def lavg_compliant(result: CalculationResult) -> bool:
    """Check only whether the average luminance/illuminance criterion passes."""
    for c in result.criteria:
        name = c.name.upper()
        if name.startswith("LAVG") or name.startswith("EAVG"):
            return c.passed
    return result.compliant


def lavg_requirement(result: CalculationResult) -> Optional[float]:
    """Return the required Lavg (or Eavg for P classes) for the result's class.

    Returns ``None`` when the class has no average-luminance/illuminance
    requirement (e.g. P7 or a class that the calc engine does not
    populate the criterion for).
    """
    for c in result.criteria:
        name = c.name.upper()
        if name.startswith("LAVG") or name.startswith("EAVG"):
            value = float(c.required or 0)
            return value if value > 0 else None
    return None


# ---------------------------------------------------------------------------
# Config builders
# ---------------------------------------------------------------------------

def with_power(config: CalculationConfig, power: float, ldt_id: str) -> CalculationConfig:
    return config.model_copy(update={"power": power, "target_flux": None, "ldt_id": ldt_id})


def with_updates(config: CalculationConfig, updates: dict, ldt_id: str) -> CalculationConfig:
    return config.model_copy(update={**updates, "ldt_id": ldt_id})


# ---------------------------------------------------------------------------
# Power-driven search
# ---------------------------------------------------------------------------

def optimize_power_for_config(
    config: CalculationConfig,
    ldt_id: str,
    max_power: Optional[float] = None,
    initial_result: Optional[CalculationResult] = None,
    compliant_check: Optional[Callable[[CalculationResult], bool]] = None,
    lente_eficiencia: float = 1.0,
    difusor_eficiencia: float = 1.0,
) -> tuple[bool, int, CalculationResult, str]:
    checked = 0
    results_by_power: dict[float, CalculationResult] = {}
    power_ceiling = max(OPTIMIZATION_MIN_POWER, min(OPTIMIZATION_MAX_POWER, float(max_power or OPTIMIZATION_MAX_POWER)))
    initial_key: Optional[float] = None
    if initial_result is not None and not (initial_result.config.target_flux and initial_result.config.target_flux > 0):
        initial_power = float(initial_result.config.power or 0)
        if OPTIMIZATION_MIN_POWER <= initial_power <= power_ceiling:
            initial_key = round(initial_power, 4)

    def _compliant(r: CalculationResult) -> bool:
        return compliant_check(r) if compliant_check else r.compliant

    def calculate_power(power: float) -> CalculationResult:
        nonlocal checked
        key = round(max(OPTIMIZATION_MIN_POWER, min(power_ceiling, power)), 4)
        if key not in results_by_power:
            if key == initial_key:
                results_by_power[key] = initial_result  # type: ignore[assignment]
            else:
                results_by_power[key] = run_calculation(
                    with_power(config, key, ldt_id),
                    ldt_id,
                    lente_eficiencia=lente_eficiencia,
                    difusor_eficiencia=difusor_eficiencia,
                )
                checked += 1
        return results_by_power[key]

    current_power = max(OPTIMIZATION_MIN_POWER, min(power_ceiling, float(config.power)))
    current_result = calculate_power(current_power)
    high: Optional[float] = None
    low: float = OPTIMIZATION_MIN_POWER

    if _compliant(current_result):
        high = current_power
        probe = current_power
        while probe > OPTIMIZATION_MIN_POWER:
            next_probe = max(OPTIMIZATION_MIN_POWER, probe / 2.0)
            probe_result = calculate_power(next_probe)
            if _compliant(probe_result):
                high = next_probe
                probe = next_probe
            else:
                low = next_probe
                break
    else:
        if not compliant_check and not power_can_fix_failures(current_result):
            return False, checked, current_result, failed_criteria(current_result)
        max_power_result = calculate_power(power_ceiling)
        if _compliant(max_power_result):
            low = current_power
            high = power_ceiling

    if high is None:
        max_result = results_by_power.get(power_ceiling) or calculate_power(power_ceiling)
        return False, checked, current_result, failed_criteria(max_result)

    while high - low > OPTIMIZATION_PRECISION / 2.0:
        mid = (low + high) / 2.0
        result = calculate_power(mid)
        if _compliant(result):
            high = mid
        else:
            low = mid

    final_power = round(high, 1)
    final_result = calculate_power(final_power)

    while not _compliant(final_result) and final_power < power_ceiling:
        final_power = round(min(power_ceiling, final_power + 0.1), 1)
        final_result = calculate_power(final_power)

    return True, checked, final_result, "none"


# ---------------------------------------------------------------------------
# Flux-driven search
# ---------------------------------------------------------------------------

def optimize_flux_for_config(
    db,
    config: CalculationConfig,
    ldt_id: str,
    target_lavg: float,
    lente_eficiencia: float = 1.0,
    difusor_eficiencia: float = 1.0,
    min_flux: float = 100.0,
    max_flux: float = 200000.0,
    max_system_power: Optional[float] = None,
) -> tuple[bool, int, CalculationResult, str, CalculationConfig]:
    """Find the smallest ``target_flux`` so the resulting Lavg is >= ``target_lavg``.

    The relationship between ``target_flux`` and Lavg is approximately
    linear (Lavg ∝ flux_scale and the calc engine scales I(C, gamma)
    by flux_scale), so we seed the search with a linear estimate and
    then refine with a binary search until the relative precision is
    below 0.5 %.  The V2 LED model introduces small non-linearities
    (different PCBs selected at different fluxes, thermal derating)
    which the refinement handles.

    Returns ``(feasible, checked, result, failures, optimized_config)``.
    ``optimized_config`` carries the new ``target_flux`` and total system
    ``power`` derived from the LED operating point and driver efficiency,
    ready to be persisted or applied to the editor.
    """
    checked = 0
    required_lavg = target_lavg + max(0.01, abs(target_lavg) * 0.01)
    results_by_flux: dict[float, CalculationResult] = {}
    configs_by_flux: dict[float, CalculationConfig] = {}

    def probe(flux: float) -> Optional[CalculationResult]:
        nonlocal checked
        key = round(max(min_flux, min(max_flux, flux)), 1)
        if key in results_by_flux:
            return results_by_flux[key]
        trial = config.model_copy(update={"target_flux": key, "power": 0.0})
        detail = select_pcb_for_flux(
            db,
            trial.gama or "",
            trial.difusor or "",
            trial.lente or "",
            trial.led_type or "",
            target_flux=key,
            t_amb_c=trial.t_amb_c or 25.0,
            lm_w_min=trial.lm_w_min,
            driver_eficiencia=trial.driver_eficiencia or 1.0,
            selected_pcb_ref=trial.selected_pcb_ref,
            ignore_lm_w_min=False,
        )
        if detail is None or not detail.p_total or detail.p_total <= 0:
            results_by_flux[key] = None  # type: ignore[assignment]
            return None
        # ``p_total`` is LED electrical power.  The persisted/user-facing
        # value is total input power, including the driver loss.
        driver_eff = detail.driver_eficiencia or trial.driver_eficiencia
        system_power = total_system_power(detail.p_total, driver_eff)
        if max_system_power is not None and system_power > float(max_system_power) + 0.01:
            results_by_flux[key] = None  # type: ignore[assignment]
            return None
        powered = trial.model_copy(update={"power": round(system_power, 2), "target_flux": detail.flux})
        result = run_calculation(
            powered, ldt_id,
            lente_eficiencia=lente_eficiencia,
            difusor_eficiencia=difusor_eficiencia,
        )
        results_by_flux[key] = result
        configs_by_flux[key] = powered
        checked += 1
        return result

    # Step 1: probe with the current config to set the search bounds.
    current_flux = config.target_flux if (config.target_flux and config.target_flux > 0) else None
    current_result: Optional[CalculationResult] = None
    if current_flux is not None:
        current_result = probe(current_flux)

    if current_result is None or (current_result.Lavg or 0) <= 0:
        # Fall back to evaluating the current power once to seed the
        # search with whatever flux the LDT produces for the current
        # operating point.  The optimizer cannot reason about flux
        # without at least one valid point on the curve.
        current_result = run_calculation(
            config, ldt_id,
            lente_eficiencia=lente_eficiencia,
            difusor_eficiencia=difusor_eficiencia,
        )
        checked += 1
        current_flux = float(current_result.luminaire.flux or 0) or 10000.0
        configs_by_flux[round(current_flux, 1)] = config

    current_lavg = float(current_result.Lavg or 0)

    # Step 2: linear estimate seeded by the current operating point.
    if current_lavg > 0 and target_lavg > 0:
        estimated_flux = current_flux * required_lavg / current_lavg
    else:
        estimated_flux = max_flux
    estimated_flux = max(min_flux, min(max_flux, estimated_flux))

    estimate_result = probe(estimated_flux)
    if estimate_result is None:
        return False, checked, current_result, "no_pcb", current_result.config

    estimate_lavg = float(estimate_result.Lavg or 0)

    # Step 3: set up binary search bounds.
    if estimate_lavg >= required_lavg:
        # The estimate already passes.  Search downward from the
        # current point so the lower bound is anchored on a known
        # passing value.
        low, high = min(estimated_flux, current_flux), max(estimated_flux, current_flux)
    else:
        # The estimate fails.  Search upward from the current point.
        low, high = min(estimated_flux, current_flux), max_flux
        max_result = probe(max_flux)
        if max_result is None or float(max_result.Lavg or 0) < required_lavg:
            fallback = max_result or estimate_result
            return False, checked, fallback, "max_flux_insufficient", fallback.config

    # Step 4: Secant-method refinement (Lavg ∝ flux is near-linear,
    # so 1-3 iterations converge vs 8-10 for binary search).
    # Brackets [low, high] and the precision check stay the same,
    # only the probe-point selection changes.
    _sec_lavg_low = 0.0
    _sec_lavg_high = required_lavg * 2.0
    _r = results_by_flux.get(round(low, 1))
    if _r is not None:
        _sec_lavg_low = float(_r.Lavg or 0)
    _r = results_by_flux.get(round(high, 1))
    if _r is not None:
        _sec_lavg_high = float(_r.Lavg or 0)

    # If even the low bound passes, probe downward to find a failing point
    if _sec_lavg_low >= required_lavg:
        _lower = max(min_flux, round(low * 0.8, 1))
        _r = probe(_lower)
        if _r is not None and float(_r.Lavg or 0) < required_lavg:
            low = _lower
            _sec_lavg_low = float(_r.Lavg or 0)

    for _ in range(12):
        if (high - low) / max(high, 1.0) <= 0.005:
            break
        if abs(_sec_lavg_high - _sec_lavg_low) > 0.01:
            _f_c = low + (required_lavg - _sec_lavg_low) * (high - low) / (_sec_lavg_high - _sec_lavg_low)
        else:
            _f_c = (low + high) / 2.0
        _f_c = max(low * 1.001, min(high * 0.999, _f_c))
        _r_c = probe(_f_c)
        if _r_c is None:
            _f_c = (low + high) / 2.0
            _r_c = probe(_f_c)
            if _r_c is None:
                low = _f_c
                continue
        _l_c = float(_r_c.Lavg or 0)
        if _l_c >= required_lavg:
            high = _f_c
            _sec_lavg_high = _l_c
        else:
            low = _f_c
            _sec_lavg_low = _l_c

    # Step 5: round and verify the final point actually passes.
    final_flux = round(high, 1)
    final_result = probe(final_flux)
    while (final_result is None or float(final_result.Lavg or 0) < required_lavg) and final_flux < max_flux:
        final_flux = round(min(max_flux, final_flux + 1.0), 1)
        final_result = probe(final_flux)

    if final_result is None or float(final_result.Lavg or 0) < required_lavg:
        fallback = final_result or estimate_result
        return False, checked, fallback, failed_criteria(fallback), fallback.config

    return True, checked, final_result, "none", configs_by_flux[round(final_flux, 1)]
