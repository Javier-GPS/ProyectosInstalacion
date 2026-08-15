"""Discrete eight-channel current optimizer.

This first solver is deliberately deterministic and conservative. It uses
coordinate descent on the real 50 mA grid and always validates candidates with
the complete road calculation. A matrix/influence solver can replace it once
benchmark scenarios are available.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .hl2x import HL2X_CURRENT_MAX_MA, HL2X_CURRENT_STEP_MA, Hl2xModel
from .ldt import LdtPhotometry
from .normative import requirements_for
from .road import (
    LuminanceInfluence,
    RoadCalculation,
    RoadScenario,
    calculate_road,
    luminance_from_flux,
    luminance_uniformity,
    luminance_uniformity_batch,
    precompute_luminance_influence,
)
from .r_tables import ReducedLuminanceTable


@dataclass(frozen=True)
class OptimizationResult:
    currents_ma: tuple[float, ...]
    calculation: RoadCalculation
    feasible: bool
    iterations: int
    message: str


def _symmetric_vector(pair_currents: list[float] | tuple[float, ...]) -> list[float]:
    if len(pair_currents) != 4:
        raise ValueError("symmetric HL2X optimization requires four pair currents")
    return [pair_currents[0], pair_currents[1], pair_currents[2], pair_currents[3],
            pair_currents[3], pair_currents[2], pair_currents[1], pair_currents[0]]


def _uniformity_quality(uo: float, ul: float, scenario: RoadScenario) -> tuple[float, ...]:
    req = requirements_for(scenario.lighting_class)
    deficits = (
        max(0.0, req.uo_min - uo) / req.uo_min,
        max(0.0, req.ul_min - ul) / req.ul_min,
    )
    return (max(deficits), sum(deficits), -min(uo / req.uo_min, ul / req.ul_min))


def _reference_flux_lookup(model: Hl2xModel, cct_k: int, cri: int) -> np.ndarray:
    return np.array(
        [model.point(current, cct_k, cri, tj_c=model.reference_tj_c).group_flux_lm
         for current in np.arange(0.0, HL2X_CURRENT_MAX_MA + HL2X_CURRENT_STEP_MA, HL2X_CURRENT_STEP_MA)],
        dtype=float,
    )


def _relative_symmetric_profile(
    model: Hl2xModel,
    scenario: RoadScenario,
    influence: LuminanceInfluence,
    *,
    cct_k: int,
    cri: int,
    initial_current_ma: float,
) -> tuple[list[float], tuple[float, float, float], int]:
    """Find the best mirrored profile using fixed-temperature photometry."""
    levels = np.arange(0.0, HL2X_CURRENT_MAX_MA + HL2X_CURRENT_STEP_MA, HL2X_CURRENT_STEP_MA)
    flux_lookup = _reference_flux_lookup(model, cct_k, cri)
    pair_indices = ((0, 7), (1, 6), (2, 5), (3, 4))
    pair_influence = np.stack(
        [influence.lane_matrices[..., left] + influence.lane_matrices[..., right]
         for left, right in pair_indices],
        axis=-1,
    )

    def evaluate(pair_currents: np.ndarray) -> tuple[float, float, float]:
        pair_flux = flux_lookup[np.rint(pair_currents / HL2X_CURRENT_STEP_MA).astype(int)]
        luminance = np.einsum("lxyg,g->lxy", pair_influence, pair_flux)
        return luminance_uniformity(luminance)

    def evaluate_batch(pair_currents: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pair_flux = flux_lookup[np.rint(pair_currents / HL2X_CURRENT_STEP_MA).astype(int)]
        luminance = np.einsum("lxyg,ng->nlxy", pair_influence, pair_flux)
        return luminance_uniformity_batch(luminance)

    requirements = requirements_for(scenario.lighting_class)
    best_vector = np.full(4, initial_current_ma, dtype=float)
    best_metrics = evaluate(best_vector)
    best_quality = _uniformity_quality(best_metrics[1], best_metrics[2], scenario) + (float(np.sum(best_vector)),)
    total = len(levels) ** 4
    iterations = 0
    # 41^4 is small enough for an exhaustive discrete search, but the road
    # grids are evaluated in chunks to avoid allocating hundreds of MB.
    for start in range(0, total, 16384):
        flat = np.arange(start, min(start + 16384, total), dtype=np.int64)
        candidates = np.column_stack((
            levels[flat % len(levels)],
            levels[(flat // len(levels)) % len(levels)],
            levels[(flat // len(levels) ** 2) % len(levels)],
            levels[(flat // len(levels) ** 3) % len(levels)],
        ))
        averages, uos, uls = evaluate_batch(candidates)
        uo_deficit = np.maximum(0.0, requirements.uo_min - uos) / requirements.uo_min
        ul_deficit = np.maximum(0.0, requirements.ul_min - uls) / requirements.ul_min
        qualities = np.column_stack((
            np.maximum(uo_deficit, ul_deficit),
            uo_deficit + ul_deficit,
            -np.minimum(uos / requirements.uo_min, uls / requirements.ul_min),
            np.sum(candidates, axis=1),
        ))
        selected = int(np.lexsort((qualities[:, 3], qualities[:, 2], qualities[:, 1], qualities[:, 0]))[0])
        candidate_quality = tuple(qualities[selected])
        if candidate_quality < best_quality:
            best_vector = candidates[selected]
            best_metrics = (averages[selected], uos[selected], uls[selected])
            best_quality = candidate_quality
        iterations += len(flat)
    return _symmetric_vector(best_vector.tolist()), best_metrics, iterations


def _scaled_symmetric_vector(pair_currents: list[float], maximum: int) -> list[float]:
    nonzero = max(pair_currents, default=0.0)
    if nonzero <= 0.0:
        return [0.0] * 8
    scale = maximum / nonzero
    pair = [round(value * scale / HL2X_CURRENT_STEP_MA) * HL2X_CURRENT_STEP_MA for value in pair_currents[:4]]
    pair = [max(0.0, min(HL2X_CURRENT_MAX_MA, value)) for value in pair]
    return _symmetric_vector(pair)


def _final_scale_candidates(
    pair_currents: list[float],
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    cct_k: int,
    cri: int,
) -> list[list[float]]:
    """Find the useful absolute scale with a short monotonic search."""
    if max(pair_currents, default=0.0) <= 0.0:
        return [[0.0] * 8]

    req = requirements_for(scenario.lighting_class)
    cache: dict[int, RoadCalculation] = {}

    def evaluate(maximum: int) -> RoadCalculation:
        maximum = int(max(HL2X_CURRENT_STEP_MA, min(HL2X_CURRENT_MAX_MA, maximum)))
        maximum -= maximum % int(HL2X_CURRENT_STEP_MA)
        if maximum not in cache:
            cache[maximum] = calculate_road(
                group_ldt, model, _scaled_symmetric_vector(pair_currents, maximum),
                scenario, rtable, cct_k=cct_k, cri=cri,
                include_visual_grid=False, include_glare_metrics=False,
            )
        return cache[maximum]

    low, high = int(HL2X_CURRENT_STEP_MA), int(HL2X_CURRENT_MAX_MA)
    if evaluate(high).metrics.lavg_cd_m2 >= req.luminance_avg_cd_m2:
        while low < high:
            middle = ((low + high) // 2 // int(HL2X_CURRENT_STEP_MA)) * int(HL2X_CURRENT_STEP_MA)
            middle = max(low, middle)
            if evaluate(middle).metrics.lavg_cd_m2 >= req.luminance_avg_cd_m2:
                high = middle
            else:
                low = middle + int(HL2X_CURRENT_STEP_MA)
        target = low
    else:
        target = int(HL2X_CURRENT_MAX_MA)

    levels = {int(HL2X_CURRENT_STEP_MA), int(HL2X_CURRENT_MAX_MA), target}
    levels.update(range(max(50, target - 200), min(2000, target + 200) + 1, 50))
    return [_scaled_symmetric_vector(pair_currents, level) for level in sorted(levels)]


def _final_quality(calculation: RoadCalculation, scenario: RoadScenario) -> tuple[float, ...]:
    req = requirements_for(scenario.lighting_class)
    metrics = calculation.metrics
    deficits = (
        max(0.0, req.luminance_avg_cd_m2 - metrics.lavg_cd_m2) / req.luminance_avg_cd_m2,
        max(0.0, req.uo_min - metrics.uo) / req.uo_min,
        max(0.0, req.ul_min - metrics.ul) / req.ul_min,
        0.0 if metrics.power_limit_ok else 1.0,
    )
    return (max(deficits), sum(deficits), calculation.operating_point.total_driver_power_w)


def optimize_currents_symmetric(
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    cct_k: int,
    cri: int,
    initial_current_ma: float = 700.0,
) -> OptimizationResult:
    """Optimize mirrored groups first, then apply thermal/power scaling."""
    if initial_current_ma % HL2X_CURRENT_STEP_MA:
        raise ValueError("initial_current_ma must use 50 mA steps")
    # The mode only constrains currents. Never alter or symmetrise the LDT.
    scenario = replace(scenario, photometry_symmetry="asymmetric")
    influence = precompute_luminance_influence(group_ldt, scenario, rtable)
    relative_vector, _, iterations = _relative_symmetric_profile(
        model, scenario, influence, cct_k=cct_k, cri=cri,
        initial_current_ma=initial_current_ma,
    )
    pair_currents = relative_vector[:4]
    candidates = _final_scale_candidates(
        pair_currents, group_ldt, model, scenario, rtable,
        cct_k=cct_k, cri=cri,
    )
    best_calculation = None
    best_quality = None
    for candidate_vector in candidates:
        try:
            calculation = calculate_road(
                group_ldt, model, candidate_vector, scenario, rtable,
                cct_k=cct_k, cri=cri,
                include_visual_grid=False, include_glare_metrics=False,
            )
        except ValueError:
            continue
        quality = _final_quality(calculation, scenario)
        if best_quality is None or quality < best_quality:
            best_calculation, best_quality = calculation, quality
        iterations += 1
        if calculation.metrics.criteria["Lavg"] and calculation.metrics.power_limit_ok:
            break
    if best_calculation is None:
        raise ValueError("No se pudo evaluar ningún perfil simétrico")
    message = ""
    if not best_calculation.metrics.compliant:
        message = "Perfil simétrico optimizado en Uo/Ul; se conserva la mejor escala térmica evaluada"
    # Build maps only once, after the current profile has been selected.
    final = calculate_road(
        group_ldt, model, list(best_calculation.operating_point.currents_ma),
        scenario, rtable, cct_k=cct_k, cri=cri, include_visual_grid=True,
    )
    return OptimizationResult(
        tuple(final.operating_point.currents_ma), final, final.metrics.compliant,
        iterations + 1, message,
    )


def _quality(calculation: RoadCalculation) -> tuple[float, ...]:
    """Rank infeasible candidates by their worst normalized deficit."""
    metrics = calculation.metrics
    requirements = {
        "Lavg": (metrics.lavg_cd_m2, calculation.scenario.lighting_class),
    }
    del requirements
    criteria = metrics.criteria
    # Before feasibility, prefer candidates that reduce the largest relative
    # deficit. The metric values are compared against the same hard limits as
    # ``calculate_road``; values are deliberately conservative here.
    deficits = []
    if not criteria.get("Lavg", False):
        deficits.append(1.0 / max(metrics.lavg_cd_m2, 1e-9))
    if not criteria.get("Uo", False):
        deficits.append(1.0 / max(metrics.uo, 1e-9))
    if not criteria.get("Ul", False):
        deficits.append(1.0 / max(metrics.ul, 1e-9))
    if not criteria.get("REI", False):
        deficits.append(1.0 / max(metrics.rei, 1e-9))
    if not criteria.get("TI", False):
        deficits.append(max(metrics.ti_pct, 1.0))
    if not criteria.get("Power", True):
        deficits.append(metrics.power_limit_ok and 0.0 or 1.0 + calculation.operating_point.total_driver_power_w / 30.0)
    return (max(deficits, default=0.0), sum(deficits), metrics.lavg_cd_m2)


def optimize_currents(
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    cct_k: int,
    cri: int,
    initial_current_ma: float = 700.0,
) -> OptimizationResult:
    if initial_current_ma % HL2X_CURRENT_STEP_MA:
        raise ValueError("initial_current_ma must use 50 mA steps")
    # Independent and symmetric modes both use the measured LDT as supplied.
    scenario = replace(scenario, photometry_symmetry="asymmetric")
    current = max(0.0, min(HL2X_CURRENT_MAX_MA, initial_current_ma))
    vector = [current] * model.group_count
    calculation = calculate_road(
        group_ldt, model, vector, scenario, rtable,
        cct_k=cct_k, cri=cri, include_visual_grid=False,
    )
    iterations = 1

    # Coordinate ascent finds a useful independent profile even when the
    # equal-current profile cannot meet uniformity. At each step it tests all
    # 41 hardware levels for the group with the largest current need.
    best_quality = _quality(calculation)
    for _ in range(12):
        improved = False
        for group_index in range(model.group_count):
            local_best = calculation
            local_vector = vector
            local_quality = best_quality
            for trial in range(41):
                candidate_vector = vector[:]
                candidate_vector[group_index] = trial * HL2X_CURRENT_STEP_MA
                candidate = calculate_road(
                    group_ldt, model, candidate_vector, scenario, rtable,
                    cct_k=cct_k, cri=cri, include_visual_grid=False,
                )
                iterations += 1
                quality = _quality(candidate)
                if quality < local_quality or (candidate.metrics.compliant and not local_best.metrics.compliant):
                    local_best, local_vector, local_quality = candidate, candidate_vector, quality
            if local_quality < best_quality or (local_best.metrics.compliant and not calculation.metrics.compliant):
                vector, calculation, best_quality = local_vector, local_best, local_quality
                improved = True
        if calculation.metrics.compliant or not improved:
            break

    if not calculation.metrics.compliant:
        final = calculate_road(
            group_ldt, model, vector, scenario, rtable,
            cct_k=cct_k, cri=cri, include_visual_grid=True,
        )
        return OptimizationResult(
            tuple(vector), final, False, iterations + 1,
            "No se cumplen todos los criterios con corrientes independientes hasta 2.000 mA",
        )

    # Once feasible, reduce each group independently. Every trial uses the
    # eight virtual sources directly, not a regenerated LDT.
    for group_index in range(model.group_count):
        for trial in range(int(vector[group_index] / HL2X_CURRENT_STEP_MA) - 1, -1, -1):
            candidate_vector = vector[:]
            candidate_vector[group_index] = trial * HL2X_CURRENT_STEP_MA
            candidate = calculate_road(
                group_ldt, model, candidate_vector, scenario, rtable,
                cct_k=cct_k, cri=cri, include_visual_grid=False,
            )
            iterations += 1
            if candidate.metrics.compliant:
                vector = candidate_vector
                calculation = candidate
            else:
                break
    calculation = calculate_road(
        group_ldt, model, vector, scenario, rtable,
        cct_k=cct_k, cri=cri, include_visual_grid=True,
    )
    return OptimizationResult(tuple(vector), calculation, calculation.metrics.compliant, iterations, "")
