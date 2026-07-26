"""Advanced multi-variable optimization (spacing/height/arm/tilt/optic).

Exhaustive search over installation variables with optional power
sub-search per candidate.  Used by the public
``run_advanced_optimization`` and ``run_advanced_optimization_batch``
in :mod:`app.services.optimizer`.
"""
from __future__ import annotations

import heapq
from typing import Optional

from ...schemas.models import (
    CalculationConfig,
    CalculationResult,
    OptimizationResponse,
)
from ...services.calculator import run_calculation
from ...services.electrical import total_system_power
from ...services.i18n import translator
from ...services.ldt_loader import get_all_ldts
from ...services.pcb_selector import select_pcb_for_config
from ._constants import (
    ADVANCED_OPTIMIZATION_OBJECTIVE,
    ARM_LENGTH_CANDIDATES,
    ARM_TILT_CANDIDATES,
    HEIGHT_CANDIDATES,
    OPTIMIZATION_FIXED_PARAMETERS,
    SPACING_CANDIDATES,
)
from .power import (
    failed_criteria,
    lavg_requirement,
    optimize_power_for_config,
    optimize_flux_for_config,
    with_updates,
)


def advanced_objective_label(objective: str) -> str:
    from ._constants import ADVANCED_OBJECTIVE_LABELS
    return ADVANCED_OBJECTIVE_LABELS.get(objective, ADVANCED_OPTIMIZATION_OBJECTIVE)


def fixed_parameters_for(unlocked: set[str]) -> list[str]:
    return [item for item in OPTIMIZATION_FIXED_PARAMETERS if item not in unlocked]


def unique_candidates(
    values: list[float],
    current: float,
    bound: Optional[str] = None,
    bound_value: Optional[float] = None,
) -> list[float]:
    rounded = {round(value, 2) for value in values}
    rounded.add(round(current, 2))
    if bound_value is not None and bound in ("upper", "lower"):
        cap = round(bound_value, 2)
        if bound == "upper":
            rounded = {value for value in rounded if value <= cap}
            rounded.add(cap)
            return sorted(rounded, reverse=True)
        rounded = {value for value in rounded if value >= cap}
        rounded.add(cap)
        return sorted(rounded)
    return sorted(rounded, reverse=True)


def advanced_score(result: CalculationResult, original: CalculationConfig, objective: str) -> tuple[float, ...]:
    movement = (
        abs(result.config.height - original.height)
        + abs(result.config.spacing - original.spacing)
        + abs(result.config.arm_length - original.arm_length)
        + abs(result.config.tilt - original.tilt) / 10.0
    )
    if objective == "min_power":
        return (
            result.config.power,
            result.config.power / max(result.config.spacing, 0.1),
            movement,
        )
    if objective == "max_spacing":
        technical_score, largest_margin = technical_limit_score(result)
        return (
            -result.config.spacing,
            result.config.power,
            technical_score,
            largest_margin,
            movement,
        )
    technical_score, largest_margin = technical_limit_score(result)
    return (
        result.config.power,
        technical_score,
        largest_margin,
        movement,
    )


def technical_limit_score(result: CalculationResult) -> tuple[float, float]:
    margins = []
    for criterion in result.criteria:
        required = float(criterion.required or 0)
        value = float(criterion.value or 0)
        if required <= 0:
            continue
        if criterion.name.upper().startswith("TI"):
            margin = max(0.0, (required - value) / required)
        else:
            margin = max(0.0, (value - required) / required)
        margins.append(margin)

    if not margins:
        return 0.0, 0.0
    return sum(margin * margin for margin in margins), max(margins)


def advanced_unlocked(variables) -> set[str]:
    unlocked = set()
    if variables.power:
        unlocked.add("power")
    if variables.spacing:
        unlocked.add("spacing")
    if variables.height:
        unlocked.add("height")
    if getattr(variables, "arm_length", False):
        unlocked.add("armLength")
    if getattr(variables, "tilt", False):
        unlocked.add("armTiltAngle")
    if getattr(variables, "optic_family", False):
        unlocked.add("optic_family")
    return unlocked


def run_advanced_search(
    config: CalculationConfig,
    variables,
    limits,
    objective: str,
    ldt_id: str,
    objective_label: str,
    lente_eficiencia: float = 1.0,
    difusor_eficiencia: float = 1.0,
) -> OptimizationResponse:
    t = translator(config.language)
    spacing_values = (
        unique_candidates(SPACING_CANDIDATES, config.spacing, bound="lower", bound_value=limits.spacing)
        if variables.spacing
        else [config.spacing]
    )
    height_values = unique_candidates(HEIGHT_CANDIDATES, config.height, limits.height) if variables.height else [config.height]
    arm_length_values = unique_candidates(ARM_LENGTH_CANDIDATES, config.arm_length, limits.arm_length) if variables.arm_length else [config.arm_length]
    tilt_values = unique_candidates(ARM_TILT_CANDIDATES, config.tilt, limits.tilt) if variables.tilt else [config.tilt]
    unlocked = advanced_unlocked(variables)

    if objective == "max_spacing":
        spacing_values = sorted(spacing_values, reverse=True)
    elif objective == "min_power":
        spacing_values = sorted(spacing_values)

    checked = 0
    best_result: Optional[CalculationResult] = None
    best_score: Optional[tuple[float, float, float]] = None
    first_failure = "none"
    last_result: Optional[CalculationResult] = None

    for spacing in spacing_values:
        for height in height_values:
            for arm_length in arm_length_values:
                for tilt in tilt_values:
                    if objective == "max_spacing" and best_result is not None and spacing < best_result.config.spacing:
                        return OptimizationResponse(
                            feasible=True,
                            message=t(
                                "opt.best_advanced",
                                power=best_result.config.power,
                                spacing=best_result.config.spacing,
                                height=best_result.config.height,
                                arm=best_result.config.arm_length,
                                tilt=best_result.config.tilt,
                            ),
                            objective=objective_label,
                            fixed_parameters=fixed_parameters_for(unlocked),
                            checked=checked,
                            config=best_result.config,
                            result=best_result,
                        )

                    candidate_config = with_updates(
                        config,
                        {"spacing": spacing, "height": height, "arm_length": arm_length, "tilt": tilt},
                        ldt_id,
                    )
                    if variables.power:
                        margen_pct = config.margen_lavg or 0.0
                        compliant_check = None
                        if margen_pct > 0:
                            def _make_checker(m):
                                def checker(r):
                                    found_lavg = False
                                    for c in r.criteria:
                                        n = c.name.upper()
                                        if n.startswith("LAVG") or n.startswith("EAVG"):
                                            found_lavg = True
                                            req = float(c.required or 0)
                                            val = float(c.value or 0)
                                            if req > 0 and val < req * (1.0 + m / 100.0):
                                                return False
                                        elif not c.passed:
                                            return False
                                    return found_lavg or r.compliant
                                return checker
                            compliant_check = _make_checker(margen_pct)
                        feasible, candidate_checked, result, failures = optimize_power_for_config(candidate_config, ldt_id, limits.power, compliant_check=compliant_check, lente_eficiencia=lente_eficiencia, difusor_eficiencia=difusor_eficiencia)
                        checked += candidate_checked
                    else:
                        result = run_calculation(candidate_config, ldt_id, lente_eficiencia=lente_eficiencia, difusor_eficiencia=difusor_eficiencia)
                        checked += 1
                        feasible = result.compliant
                        failures = failed_criteria(result)

                    last_result = result
                    if not feasible:
                        if first_failure == "none":
                            first_failure = failures
                        continue

                    score = advanced_score(result, config, objective)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_result = result

    if best_result is None:
        fallback = last_result or run_calculation(config, ldt_id, lente_eficiencia=lente_eficiencia, difusor_eficiencia=difusor_eficiencia)
        if last_result is None:
            checked += 1
        return OptimizationResponse(
            feasible=False,
            message=t("opt.no_advanced", failures=first_failure),
            objective=objective_label,
            fixed_parameters=fixed_parameters_for(unlocked),
            checked=checked,
            config=config,
            result=fallback,
        )

    return OptimizationResponse(
        feasible=True,
        message=t(
            "opt.best_advanced",
            power=best_result.config.power,
            spacing=best_result.config.spacing,
            height=best_result.config.height,
            arm=best_result.config.arm_length,
            tilt=best_result.config.tilt,
        ),
        objective=objective_label,
        fixed_parameters=fixed_parameters_for(unlocked),
        checked=checked,
        config=best_result.config,
        result=best_result,
    )


def optic_candidates(config: CalculationConfig, requested: Optional[list[str]]) -> list[str]:
    requested_set = set(requested or [])
    candidates = [
        item.get("optic_family")
        for item in get_all_ldts()
        if (not config.manufacturer or item.get("manufacturer", "Unknown") == config.manufacturer)
        and (not config.model_family or item.get("model_family", "UNKNOWN") == config.model_family)
        and item.get("optic_family")
        and (not requested_set or item.get("optic_family") in requested_set)
    ]
    unique = sorted(set(candidates))
    return unique or [config.optic_family]


# ---------------------------------------------------------------------------
# Smart recursive optimizer (criterion-driven, not brute force)
# ---------------------------------------------------------------------------

_PARAM_ATTRS = {
    "spacing": "spacing",
    "height": "height",
    "arm_length": "arm_length",
    "tilt": "tilt",
    "power": "power",
}

_PARAM_CANDIDATES = {
    "spacing": SPACING_CANDIDATES,
    "height": HEIGHT_CANDIDATES,
    "arm_length": ARM_LENGTH_CANDIDATES,
    "tilt": ARM_TILT_CANDIDATES,
    # Power is only an independent search dimension for power-driven LDTs.
    # Flux/PCB configurations derive power from the selected operating point.
    "power": [1.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 60.0, 75.0, 100.0, 150.0, 200.0, 300.0, 500.0],
}

# Map param name → unlocked-set name (see advanced_unlocked for camelCase keys)
_PARAM_TO_UNLOCKED = {
    "spacing": "spacing",
    "height": "height",
    "arm_length": "armLength",
    "tilt": "armTiltAngle",
    "power": "power",
}

# The sensitivity test against the real photometric engine shows that each of
# spacing, height, arm length and tilt changes every roadway criterion.  Their
# effect is optic/geometry dependent and therefore is not safely monotonic.
# The recursive search must try both adjacent values of every selected
# geometric parameter for every failed criterion, then rank the resulting
# candidates by the actual violation.  ``power`` is added only in power-driven
# mode; in flux mode it is derived from flux/current/PCB.
_GEOMETRIC_PARAMS = ("spacing", "height", "arm_length", "tilt")

# A beam of two candidates was too aggressive: a good solution can require
# changing two different levers before any one intermediate result looks
# better.  The search below is still recursive/criterion-driven, but keeps a
# priority frontier and backtracks through every useful neighbour until it
# finds a compliant configuration (or reaches this safety cap).
_MAX_RECURSION_DEPTH = 64
_MAX_SEARCH_NODES = 600


def _failing_by_severity(result: CalculationResult) -> list[tuple[str, float]]:
    items: list[tuple[str, float, float]] = []
    for c in result.criteria:
        if c.passed:
            continue
        req = float(c.required or 0)
        val = float(c.value or 0)
        if req <= 0:
            continue
        if c.name.upper().startswith("TI"):
            margin = (req - val) / req
        else:
            margin = (val - req) / req
        items.append((c.name, margin, abs(margin)))
    items.sort(key=lambda x: x[2], reverse=True)
    return [(n, m) for n, m, _ in items]


def _next_value(param: str, current: float, direction: int, limits) -> Optional[float]:
    candidates = sorted(_PARAM_CANDIDATES[param])
    limit = getattr(limits, param, None)
    if direction > 0:
        for v in candidates:
            if v > current + 0.01:
                if limit is None or v <= limit:
                    return v
    else:
        for v in reversed(candidates):
            if v < current - 0.01:
                if limit is None:
                    return v
                if param == "spacing":
                    if v >= limit:  # spacing is a lower bound (minimum)
                        return v
                elif v <= limit:   # height/arm/tilt are upper bounds (maximum)
                    return v
    return None


def _make_compliant_check(margen_pct: float):
    if margen_pct <= 0:
        return None

    def checker(r):
        found_lavg = False
        for c in r.criteria:
            n = c.name.upper()
            if n.startswith(("LAVG", "EAVG")):
                found_lavg = True
                req = float(c.required or 0)
                val = float(c.value or 0)
                if req > 0 and val < req * (1.0 + margen_pct / 100.0):
                    return False
            elif not c.passed:
                return False
        return found_lavg or r.compliant
    return checker


def _has_catalog_selection(config: CalculationConfig) -> bool:
    return all((config.gama, config.difusor, config.lente, config.led_type))


def _calculate_candidate(
    db,
    config: CalculationConfig,
    ldt_id: str,
    lente_eficiencia: float,
    difusor_eficiencia: float,
) -> tuple[CalculationResult, CalculationConfig]:
    """Calculate one candidate using the same PCB path as the HTTP API.

    ``run_calculation`` only knows about photometry.  When a candidate carries
    a target flux, the catalog layer must resolve the operating current and
    system power first; otherwise the optimizer compares stale power values
    and never sees the electrical configuration it is actually selecting.
    """
    if db is not None and config.target_flux and config.target_flux > 0 and _has_catalog_selection(config):
        detail = select_pcb_for_config(db, config)
        if detail is not None and detail.p_total > 0:
            driver_eff = detail.driver_eficiencia or config.driver_eficiencia or 1.0
            prepared = config.model_copy(update={
                "power": round(total_system_power(detail.p_total, driver_eff), 2),
                "target_flux": detail.flux,
                "i_op_ma": detail.i_op_ma,
            })
            return run_calculation(
                prepared,
                ldt_id,
                lente_eficiencia=lente_eficiencia,
                difusor_eficiencia=difusor_eficiencia,
            ), prepared

    return run_calculation(
        config,
        ldt_id,
        lente_eficiencia=lente_eficiencia,
        difusor_eficiencia=difusor_eficiencia,
    ), config


def _violation_score(result: CalculationResult) -> float:
    total = 0.0
    for c in result.criteria:
        if c.passed:
            continue
        req = float(c.required or 0)
        val = float(c.value or 0)
        if req <= 0:
            continue
        if c.name.upper().startswith("TI"):
            gap = max(0.0, (val - req) / req)
        else:
            gap = max(0.0, (req - val) / req)
        total += gap * gap
    return total


def run_smart_search(
    config: CalculationConfig,
    variables,
    limits,
    objective: str,
    ldt_id: str,
    objective_label: str,
    lente_eficiencia: float = 1.0,
    difusor_eficiencia: float = 1.0,
    db=None,
) -> OptimizationResponse:
    """Recursive constraint-driven optimization.

    Instead of brute-forcing all parameter combinations, this function:
    1. Evaluates the current config (with power binary-search inner loop)
    2. Identifies which criteria fail and by how much
    3. Picks the unlocked parameter that best addresses the worst failure
    4. Adjusts that parameter by one candidate step in the right direction
    5. Recurses until compliant or no further improvement

    Complexity O(d * n) instead of O(k * n^k) where:
      d = recursion depth (≤ _MAX_RECURSION_DEPTH)
      n = candidate values per parameter
      k = number of unlocked variables
    """
    t = translator(config.language)
    unlocked = advanced_unlocked(variables)
    margen_pct = config.margen_lavg or 0.0
    compliant_check = _make_compliant_check(margen_pct) if margen_pct > 0 else None
    total_checked = 0
    first_failure = "none"
    best_result: Optional[CalculationResult] = None
    best_score_val: Optional[tuple] = None

    # Clamp the starting point to the user limits before entering the search.
    clamp_updates: dict[str, float] = {}
    if limits.spacing is not None and "spacing" in unlocked:
        clamp_updates["spacing"] = max(config.spacing, limits.spacing)
    if limits.height is not None and "height" in unlocked and config.height > limits.height:
        clamp_updates["height"] = limits.height
    if limits.arm_length is not None and "armLength" in unlocked and config.arm_length > limits.arm_length:
        clamp_updates["arm_length"] = limits.arm_length
    if limits.tilt is not None and "armTiltAngle" in unlocked and config.tilt > limits.tilt:
        clamp_updates["tilt"] = limits.tilt
    if clamp_updates:
        config = config.model_copy(update=clamp_updates)

    def _level_only_failures(failures: str) -> bool:
        if not failures:
            return False
        parts = [p.strip() for p in failures.split(",") if p.strip()]
        return all(any(p.upper().startswith(prefix) for prefix in ("LAVG", "EAVG", "EMIN")) for p in parts)

    def _consider(result: CalculationResult) -> tuple[bool, bool]:
        nonlocal best_result, best_score_val
        feasible = result.compliant
        failures = failed_criteria(result)
        fixable = variables.power and not feasible and _level_only_failures(failures)
        viable = feasible or fixable
        best_viable = False
        if best_result is not None:
            best_failures = failed_criteria(best_result)
            best_viable = best_result.compliant or (
                variables.power and _level_only_failures(best_failures)
            )

        score = advanced_score(result, config, objective)
        if best_result is None or (viable and not best_viable):
            best_result = result
            best_score_val = score
        elif viable == best_viable and best_score_val is not None:
            if viable:
                if score < best_score_val:
                    best_result = result
                    best_score_val = score
            else:
                rv = _violation_score(result)
                bv = _violation_score(best_result)
                if rv < bv or (rv == bv and score < best_score_val):
                    best_result = result
                    best_score_val = score
        return feasible, fixable

    def _evaluate(cfg: CalculationConfig) -> tuple[CalculationResult, bool, str, bool, CalculationConfig]:
        nonlocal total_checked, first_failure
        result, effective_cfg = _calculate_candidate(
            db, cfg, ldt_id, lente_eficiencia, difusor_eficiencia,
        )
        total_checked += 1
        failures = failed_criteria(result)
        feasible, fixable = _consider(result)
        if first_failure == "none" and not feasible:
            first_failure = failures
        return result, feasible, failures, fixable, effective_cfg

    def _optimize_level(
        cfg: CalculationConfig,
        initial_result: CalculationResult,
    ) -> tuple[bool, int, CalculationResult, str, CalculationConfig]:
        """Resolve Lavg through the catalog when available, otherwise by W."""
        if not variables.power:
            return False, 0, initial_result, failed_criteria(initial_result), cfg

        if db is not None and _has_catalog_selection(cfg):
            required = lavg_requirement(initial_result)
            if required is not None:
                target = required * (1.0 + margen_pct / 100.0)
                return optimize_flux_for_config(
                    db,
                    cfg,
                    ldt_id,
                    target,
                    lente_eficiencia=lente_eficiencia,
                    difusor_eficiencia=difusor_eficiencia,
                    max_system_power=limits.power,
                )

        feasible, checked, result, failures = optimize_power_for_config(
            cfg,
            ldt_id,
            limits.power,
            initial_result=initial_result,
            compliant_check=compliant_check,
            lente_eficiencia=lente_eficiencia,
            difusor_eficiencia=difusor_eficiencia,
        )
        return feasible, checked, result, failures, result.config

    def _directions_for(result: CalculationResult) -> dict[str, list[int]]:
        """Return all selected levers that can change this candidate's failures.

        The photometric engine is nonlinear: the same parameter can improve
        Uo for one optic and worsen it for another.  A fixed rule such as
        ``Uo -> height+`` is therefore incomplete.  We use the measured
        sensitivity of the engine and explore both adjacent values for every
        selected geometric lever, letting the actual recalculated violation
        decide which branch wins.
        """
        directions: dict[str, set[int]] = {param: set() for param in _PARAM_ATTRS}
        failed = _failing_by_severity(result)
        if not failed:
            return {}

        for param in _GEOMETRIC_PARAMS:
            if _PARAM_TO_UNLOCKED[param] in unlocked:
                directions[param].update((-1, 1))

        # A power value is an independent input only when the candidate is
        # power-driven.  In flux mode the PCB selector owns power, so changing
        # ``config.power`` would be overwritten before calculation.
        if "power" in unlocked and not (result.config.target_flux and result.config.target_flux > 0):
            directions["power"].update((-1, 1))

        return {param: sorted(vals) for param, vals in directions.items() if vals}

    def _neighbors(cfg: CalculationConfig, result: CalculationResult) -> list[CalculationConfig]:
        neighbors: list[CalculationConfig] = []
        param_directions = _directions_for(result)
        combined: dict[str, float] = {}
        for param, directions in param_directions.items():
            current = float(getattr(cfg, param))
            for direction in directions:
                nv = _next_value(param, current, direction, limits)
                if nv is not None:
                    neighbors.append(with_updates(cfg, {param: nv}, ldt_id))
                    combined.setdefault(param, nv)
        if len(combined) > 1:
            neighbors.append(with_updates(cfg, combined, ldt_id))
        return neighbors

    def _cfg_key(cfg: CalculationConfig) -> tuple[float, ...]:
        power_key = (
            round(cfg.power, 2)
            if "power" in unlocked and not (cfg.target_flux and cfg.target_flux > 0)
            else -1.0
        )
        return (
            round(cfg.spacing, 2),
            round(cfg.height, 2),
            round(cfg.arm_length, 2),
            round(cfg.tilt, 2),
            power_key,
        )

    def _success(result: CalculationResult) -> OptimizationResponse:
        return OptimizationResponse(
            feasible=True,
            message=t(
                "opt.best_advanced",
                power=result.config.power,
                spacing=result.config.spacing,
                height=result.config.height,
                arm=result.config.arm_length,
                tilt=result.config.tilt,
            ),
            objective=objective_label,
            fixed_parameters=fixed_parameters_for(unlocked),
            checked=total_checked,
            config=result.config,
            result=result,
        )

    initial_result, initial_feasible, initial_failures, initial_fixable, initial_cfg = _evaluate(config)
    if variables.power and (initial_feasible or initial_fixable):
        feasible_power, checked, optimized_result, _, optimized_cfg = _optimize_level(initial_cfg, initial_result)
        total_checked += checked
        _consider(optimized_result)
        initial_result = optimized_result
        initial_cfg = optimized_cfg
        initial_feasible = feasible_power and optimized_result.compliant
        initial_failures = failed_criteria(optimized_result)
        initial_fixable = variables.power and not initial_feasible and _level_only_failures(initial_failures)
        if initial_feasible:
            return _success(optimized_result)
    elif initial_feasible:
        return _success(initial_result)

    # Keep the result together with its config: directions must come from the
    # candidate currently being explored, never from the global best result.
    # Use a priority frontier instead of a width-two beam.  The old beam could
    # discard the only branch that later fixes a second failed criterion.
    frontier: list[tuple[float, tuple[float, ...], int, int, CalculationConfig, CalculationResult]] = []
    seen: set[tuple[float, ...]] = {_cfg_key(initial_cfg)}
    sequence = 0

    def _push(cfg: CalculationConfig, result: CalculationResult, depth: int) -> None:
        nonlocal sequence
        if depth > _MAX_RECURSION_DEPTH:
            return
        sequence += 1
        heapq.heappush(
            frontier,
            (
                _violation_score(result),
                advanced_score(result, config, objective),
                depth,
                sequence,
                cfg,
                result,
            ),
        )

    _push(initial_cfg, initial_result, 0)
    search_nodes = 1
    while frontier and search_nodes < _MAX_SEARCH_NODES:
        _, _, depth, _, cfg, cfg_result = heapq.heappop(frontier)
        for neighbor in _neighbors(cfg, cfg_result):
            key = _cfg_key(neighbor)
            if key in seen:
                continue
            seen.add(key)
            search_nodes += 1
            result, feasible, failures, fixable, effective_cfg = _evaluate(neighbor)
            candidate_cfg = effective_cfg

            # Once all non-level criteria pass, solve Lavg through the
            # catalog: flux -> current -> smallest valid PCB -> system W.
            # The result is then checked again, because changing PCB/current
            # can expose a new photometric failure.
            if variables.power and (feasible or fixable):
                feasible_power, checked, optimized_result, _, optimized_cfg = _optimize_level(
                    effective_cfg, result,
                )
                total_checked += checked
                result = optimized_result
                candidate_cfg = optimized_cfg
                _consider(result)
                feasible = feasible_power and result.compliant
                failures = failed_criteria(result)
                fixable = variables.power and not feasible and _level_only_failures(failures)
                if feasible:
                    return _success(result)
            elif feasible:
                return _success(result)

            if search_nodes >= _MAX_SEARCH_NODES:
                break
            _push(candidate_cfg, result, depth + 1)

    if best_result is not None and best_result.compliant:
        return _success(best_result)

    if best_result is not None and variables.power and _level_only_failures(failed_criteria(best_result)):
        feasible_power, checked, final_result, _, _ = _optimize_level(best_result.config, best_result)
        total_checked += checked
        _consider(final_result)
        if feasible_power and final_result.compliant:
            return _success(final_result)

    fallback = best_result or run_calculation(
        config,
        ldt_id,
        lente_eficiencia=lente_eficiencia,
        difusor_eficiencia=difusor_eficiencia,
    )
    if best_result is None:
        total_checked += 1
    # Report the criteria from the configuration actually returned.  The
    # previous implementation kept the first failure seen, which made the UI
    # show stale values after the recursive search had already improved the
    # candidate (and looked as if no optimisation had happened).
    final_failures = failed_criteria(fallback)
    return OptimizationResponse(
        feasible=False,
        message=t("opt.no_advanced", failures=final_failures if final_failures != "none" else first_failure),
        objective=objective_label,
        fixed_parameters=fixed_parameters_for(unlocked),
        checked=total_checked,
        config=fallback.config,
        result=fallback,
    )
