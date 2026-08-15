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


def _relative_independent_profile(
    model: Hl2xModel,
    scenario: RoadScenario,
    influence: LuminanceInfluence,
    *,
    cct_k: int,
    cri: int,
    initial_current_ma: float,
) -> tuple[list[float], tuple[float, float, float], int]:
    """Find eight relative channel levels using only Uo and Ul.

    The influence matrix is linear in group flux, so the absolute scale is
    deliberately absent here. It is selected later with the thermal model.
    """
    levels = np.arange(0.0, HL2X_CURRENT_MAX_MA + HL2X_CURRENT_STEP_MA, HL2X_CURRENT_STEP_MA)
    flux_lookup = _reference_flux_lookup(model, cct_k, cri)

    def evaluate(currents: np.ndarray) -> tuple[float, float, float]:
        flux = flux_lookup[np.rint(currents / HL2X_CURRENT_STEP_MA).astype(int)]
        return luminance_uniformity(luminance_from_flux(influence, flux))

    vector = np.full(model.group_count, initial_current_ma, dtype=float)
    metrics = evaluate(vector)
    quality = _uniformity_quality(metrics[1], metrics[2], scenario)
    iterations = 0
    for _ in range(12):
        improved = False
        for group_index in range(model.group_count):
            local_vector = vector
            local_metrics = metrics
            local_quality = quality
            for level in levels:
                candidate = vector.copy()
                candidate[group_index] = level
                candidate_metrics = evaluate(candidate)
                candidate_quality = _uniformity_quality(
                    candidate_metrics[1], candidate_metrics[2], scenario,
                )
                if candidate_quality < local_quality:
                    local_vector, local_metrics, local_quality = (
                        candidate, candidate_metrics, candidate_quality,
                    )
                iterations += 1
            if local_quality < quality:
                vector, metrics, quality = local_vector, local_metrics, local_quality
                improved = True
        if not improved:
            break
    return vector.tolist(), metrics, iterations


def _scaled_symmetric_vector(pair_currents: list[float], maximum: int) -> list[float]:
    nonzero = max(pair_currents, default=0.0)
    if nonzero <= 0.0:
        return [0.0] * 8
    scale = maximum / nonzero
    pair = [round(value * scale / HL2X_CURRENT_STEP_MA) * HL2X_CURRENT_STEP_MA for value in pair_currents[:4]]
    pair = [max(0.0, min(HL2X_CURRENT_MAX_MA, value)) for value in pair]
    return _symmetric_vector(pair)


def _scaled_vector(relative_currents: list[float], maximum: int) -> list[float]:
    nonzero = max(relative_currents, default=0.0)
    if nonzero <= 0.0:
        return [0.0] * len(relative_currents)
    scale = maximum / nonzero
    return [
        max(0.0, min(HL2X_CURRENT_MAX_MA, round(value * scale / HL2X_CURRENT_STEP_MA) * HL2X_CURRENT_STEP_MA))
        for value in relative_currents
    ]


def _final_scale_candidates(
    relative_currents: list[float],
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    cct_k: int,
    cri: int,
    symmetric: bool,
) -> list[list[float]]:
    """Find the useful absolute scale with a short monotonic search."""
    if max(relative_currents, default=0.0) <= 0.0:
        return [[0.0] * (8 if symmetric else len(relative_currents))]

    scale_vector = _scaled_symmetric_vector if symmetric else _scaled_vector

    req = requirements_for(scenario.lighting_class)
    cache: dict[int, RoadCalculation] = {}

    def evaluate(maximum: int) -> RoadCalculation:
        maximum = int(max(HL2X_CURRENT_STEP_MA, min(HL2X_CURRENT_MAX_MA, maximum)))
        maximum -= maximum % int(HL2X_CURRENT_STEP_MA)
        if maximum not in cache:
            cache[maximum] = calculate_road(
                group_ldt, model, scale_vector(relative_currents, maximum),
                scenario, rtable, cct_k=cct_k, cri=cri,
                include_visual_grid=False, include_glare_metrics=True,
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
    return [scale_vector(relative_currents, level) for level in sorted(levels)]


def _final_quality(calculation: RoadCalculation, scenario: RoadScenario) -> tuple[float, ...]:
    req = requirements_for(scenario.lighting_class)
    metrics = calculation.metrics
    deficits = (
        max(0.0, req.luminance_avg_cd_m2 - metrics.lavg_cd_m2) / req.luminance_avg_cd_m2,
        max(0.0, req.uo_min - metrics.uo) / req.uo_min,
        max(0.0, req.ul_min - metrics.ul) / req.ul_min,
        max(0.0, metrics.ti_pct - req.ti_max_pct) / req.ti_max_pct,
        max(0.0, req.rei_min - metrics.rei) / req.rei_min,
        0.0 if metrics.power_limit_ok else 1.0,
        1.0 if metrics.warnings else 0.0,
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
        symmetric=True,
    )
    best_calculation = None
    best_quality = None
    for candidate_vector in candidates:
        try:
            calculation = calculate_road(
                group_ldt, model, candidate_vector, scenario, rtable,
                cct_k=cct_k, cri=cri,
                include_visual_grid=False, include_glare_metrics=True,
            )
        except ValueError:
            continue
        quality = _final_quality(calculation, scenario)
        if best_quality is None or quality < best_quality:
            best_calculation, best_quality = calculation, quality
        iterations += 1
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
    influence = precompute_luminance_influence(group_ldt, scenario, rtable)
    relative_vector, _, iterations = _relative_independent_profile(
        model, scenario, influence, cct_k=cct_k, cri=cri,
        initial_current_ma=initial_current_ma,
    )
    candidates = _final_scale_candidates(
        relative_vector, group_ldt, model, scenario, rtable,
        cct_k=cct_k, cri=cri, symmetric=False,
    )
    best_calculation = None
    best_quality = None
    for candidate_vector in candidates:
        try:
            calculation = calculate_road(
                group_ldt, model, candidate_vector, scenario, rtable,
                cct_k=cct_k, cri=cri,
                include_visual_grid=False, include_glare_metrics=True,
            )
        except ValueError:
            continue
        quality = _final_quality(calculation, scenario)
        if best_quality is None or quality < best_quality:
            best_calculation, best_quality = calculation, quality
        iterations += 1
    if best_calculation is None:
        raise ValueError("No se pudo evaluar ningún perfil independiente")
    final = calculate_road(
        group_ldt, model, list(best_calculation.operating_point.currents_ma),
        scenario, rtable, cct_k=cct_k, cri=cri, include_visual_grid=True,
    )
    message = "" if final.metrics.compliant else (
        "Perfil independiente optimizado en Uo/Ul; se conserva la mejor escala validada"
    )
    return OptimizationResult(
        tuple(final.operating_point.currents_ma), final, final.metrics.compliant,
        iterations + 1, message,
    )
