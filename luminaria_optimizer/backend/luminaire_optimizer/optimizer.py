"""Continuous critical-point guided optimizer for the eight-channel luminaire."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .hl2x import HL2X_CURRENT_MAX_MA, Hl2xModel, calculate_luminaire_operating_point
from .ldt import LdtPhotometry
from .normative import requirements_for
from .road import (
    LuminanceInfluence,
    RoadCalculation,
    RoadScenario,
    calculate_road,
    luminance_from_flux,
    luminance_uniformity,
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
    relative_currents_ma: tuple[float, ...] = ()


def _symmetric_vector(pair_currents: list[float] | tuple[float, ...]) -> list[float]:
    if len(pair_currents) != 4:
        raise ValueError("symmetric HL2X optimization requires four pair currents")
    return [pair_currents[0], pair_currents[1], pair_currents[2], pair_currents[3],
            pair_currents[3], pair_currents[2], pair_currents[1], pair_currents[0]]


def _uniformity_quality(uo: float, ul: float) -> tuple[float, ...]:
    """Rank relative profiles by the weakest uniformity first."""
    return (-min(uo, ul), -(uo + ul), -uo, -ul)


def _grid_quality(luminance: np.ndarray, scenario: RoadScenario) -> tuple[float, ...]:
    lavg, uo, ul = luminance_uniformity(luminance)
    req = requirements_for(scenario.lighting_class)
    deficits = (
        max(0.0, req.luminance_avg_cd_m2 - lavg) / req.luminance_avg_cd_m2,
        max(0.0, req.uo_min - uo) / req.uo_min,
        max(0.0, req.ul_min - ul) / req.ul_min,
    )
    return (
        deficits[0],
        max(deficits[1:]),
        sum(deficits[1:]),
        -min(uo, ul),
        -(uo + ul),
    )


def _critical_uniformity_sensitivity(
    luminance: np.ndarray,
    influence: LuminanceInfluence,
    flux_derivative: np.ndarray,
) -> tuple[float, float]:
    """Estimate Uo/Ul sensitivity from the current worst points."""
    lane_averages = np.mean(luminance, axis=(1, 2))
    lane_mins = np.min(luminance, axis=(1, 2))
    lane_uos = np.divide(lane_mins, lane_averages, out=np.zeros_like(lane_mins), where=lane_averages != 0)
    uo_lane = int(np.argmin(lane_uos))
    uo_x, uo_y = np.unravel_index(int(np.argmin(luminance[uo_lane])), luminance[uo_lane].shape)
    uo_field = influence.lane_matrices[uo_lane]
    d_min_uo = float(uo_field[uo_x, uo_y] @ flux_derivative)
    d_avg_uo = float(np.mean(uo_field, axis=(0, 1)) @ flux_derivative)
    avg_uo = lane_averages[uo_lane]
    min_uo = luminance[uo_lane, uo_x, uo_y]
    d_uo = (d_min_uo * avg_uo - min_uo * d_avg_uo) / avg_uo**2 if avg_uo else 0.0

    centre_index = luminance.shape[2] // 2
    centreline = luminance[:, :, centre_index]
    centre_minimums = np.min(centreline, axis=1)
    centre_maximums = np.max(centreline, axis=1)
    lane_uls = np.divide(centre_minimums, centre_maximums, out=np.zeros_like(centre_minimums), where=centre_maximums != 0)
    ul_lane = int(np.argmin(lane_uls))
    min_x = int(np.argmin(centreline[ul_lane]))
    max_x = int(np.argmax(centreline[ul_lane]))
    ul_field = influence.lane_matrices[ul_lane, :, centre_index]
    d_min_ul = float(ul_field[min_x] @ flux_derivative)
    d_max_ul = float(ul_field[max_x] @ flux_derivative)
    min_ul = centreline[ul_lane, min_x]
    max_ul = centreline[ul_lane, max_x]
    d_ul = (d_min_ul * max_ul - min_ul * d_max_ul) / max_ul**2 if max_ul else 0.0
    return d_uo, d_ul


def _guided_relative_profile(
    model: Hl2xModel,
    scenario: RoadScenario,
    influence: LuminanceInfluence,
    *,
    cct_k: int,
    cri: int,
    initial_current_ma: float,
    symmetric: bool,
) -> tuple[list[float], tuple[float, float, float], int]:
    """Adjust only groups that influence the current Uo/Ul critical points."""
    current = np.full(model.group_count, float(initial_current_ma), dtype=float)
    variables = [(index,) for index in range(model.group_count)] if not symmetric else [(0, 7), (1, 6), (2, 5), (3, 4)]
    step = 100.0
    iterations = 0

    def evaluate(vector: np.ndarray):
        operating = calculate_luminaire_operating_point(vector.tolist(), model, cct_k, cri)
        flux = np.array([group.group_flux_lm for group in operating.groups], dtype=float)
        luminance = luminance_from_flux(influence, flux)
        return _grid_quality(luminance, scenario), luminance, operating

    quality, luminance, operating = evaluate(current)
    for _ in range(60):
        base_flux = np.array([group.group_flux_lm for group in operating.groups], dtype=float)
        derivatives = []
        for variable in variables:
            probe = current.copy()
            probe[list(variable)] += 1.0
            try:
                probe_operating = calculate_luminaire_operating_point(probe.tolist(), model, cct_k, cri)
            except ValueError:
                derivatives.append(np.zeros(model.group_count))
                continue
            probe_flux = np.array([group.group_flux_lm for group in probe_operating.groups], dtype=float)
            derivatives.append(probe_flux - base_flux)
        sensitivity = np.array([
            min(_critical_uniformity_sensitivity(luminance, influence, derivative))
            for derivative in derivatives
        ])
        order = np.argsort(-np.abs(sensitivity))
        best = (quality, current, luminance, operating)
        for variable_index in order[:max(2, min(4, len(order)))]:
            for direction in (1.0, -1.0):
                candidate = current.copy()
                candidate[list(variables[variable_index])] += direction * step
                if np.any(candidate < 0.0) or np.any(candidate > HL2X_CURRENT_MAX_MA):
                    continue
                try:
                    candidate_quality, candidate_luminance, candidate_operating = evaluate(candidate)
                except ValueError:
                    continue
                iterations += 1
                if candidate_quality < best[0]:
                    best = (candidate_quality, candidate, candidate_luminance, candidate_operating)
        if best[0] < quality:
            quality, current, luminance, operating = best
            step = min(200.0, step * 1.15)
        else:
            step *= 0.5
        if best[0] >= quality and step < 0.5:
            break
    return current.tolist(), luminance_uniformity(luminance), iterations


def _scaled_symmetric_vector(pair_currents: list[float], maximum: float) -> list[float]:
    nonzero = max(pair_currents, default=0.0)
    if nonzero <= 0.0:
        return [0.0] * 8
    scale = maximum / nonzero
    pair = [value * scale for value in pair_currents[:4]]
    pair = [max(0.0, min(HL2X_CURRENT_MAX_MA, value)) for value in pair]
    return _symmetric_vector(pair)


def _scaled_vector(relative_currents: list[float], maximum: float) -> list[float]:
    nonzero = max(relative_currents, default=0.0)
    if nonzero <= 0.0:
        return [0.0] * len(relative_currents)
    scale = maximum / nonzero
    return [max(0.0, min(HL2X_CURRENT_MAX_MA, value * scale)) for value in relative_currents]


def _final_scale_candidates(
    relative_currents: list[float],
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    influence: LuminanceInfluence,
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
    def evaluate_lavg(maximum: float) -> float:
        maximum = max(0.0, min(HL2X_CURRENT_MAX_MA, float(maximum)))
        operating = calculate_luminaire_operating_point(
            scale_vector(relative_currents, maximum), model, cct_k, cri,
        )
        flux = np.array([group.group_flux_lm for group in operating.groups], dtype=float)
        return luminance_uniformity(luminance_from_flux(influence, flux))[0]

    low, high = 0.0, float(HL2X_CURRENT_MAX_MA)
    if evaluate_lavg(high) >= req.luminance_avg_cd_m2:
        for _ in range(24):
            middle = (low + high) / 2.0
            if evaluate_lavg(middle) >= req.luminance_avg_cd_m2:
                high = middle
            else:
                low = middle
        target = high
    else:
        target = int(HL2X_CURRENT_MAX_MA)

    levels = {0.0, float(HL2X_CURRENT_MAX_MA), target}
    levels.update(max(0.0, min(float(HL2X_CURRENT_MAX_MA), target + offset)) for offset in (-200.0, -100.0, -25.0, 25.0, 100.0, 200.0))
    return [scale_vector(relative_currents, level) for level in sorted(levels)]


def _final_quality(calculation: RoadCalculation, scenario: RoadScenario) -> tuple[float, ...]:
    req = requirements_for(scenario.lighting_class)
    metrics = calculation.metrics
    lavg_deficit = max(0.0, req.luminance_avg_cd_m2 - metrics.lavg_cd_m2) / req.luminance_avg_cd_m2
    uniformity_deficits = (
        max(0.0, req.uo_min - metrics.uo) / req.uo_min,
        max(0.0, req.ul_min - metrics.ul) / req.ul_min,
    )
    return (
        lavg_deficit,
        max(uniformity_deficits),
        sum(uniformity_deficits),
        -min(metrics.uo, metrics.ul),
        -(metrics.uo + metrics.ul),
        max(0.0, metrics.ti_pct - req.ti_max_pct) / req.ti_max_pct,
        max(0.0, req.rei_min - metrics.rei) / req.rei_min,
        0.0 if metrics.power_limit_ok else 1.0,
        1.0 if metrics.warnings else 0.0,
        calculation.operating_point.total_driver_power_w,
    )


def optimize_currents_symmetric(
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    cct_k: int,
    cri: int,
    initial_current_ma: float = 700.0,
    include_visual_grid: bool = True,
) -> OptimizationResult:
    """Optimize mirrored groups first, then apply thermal/power scaling."""
    # The mode only constrains currents. Never alter or symmetrise the LDT.
    scenario = replace(scenario, photometry_symmetry="asymmetric")
    influence = precompute_luminance_influence(group_ldt, scenario, rtable)
    relative_vector, _, iterations = _guided_relative_profile(
        model, scenario, influence, cct_k=cct_k, cri=cri,
        initial_current_ma=initial_current_ma, symmetric=True,
    )
    pair_currents = relative_vector[:4]
    candidates = _final_scale_candidates(
        pair_currents, group_ldt, model, scenario, rtable,
        influence,
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
        scenario, rtable, cct_k=cct_k, cri=cri, include_visual_grid=include_visual_grid,
    )
    return OptimizationResult(
        tuple(final.operating_point.currents_ma), final, final.metrics.compliant,
        iterations + 1, message,
        tuple(_scaled_symmetric_vector(pair_currents, int(HL2X_CURRENT_MAX_MA))),
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
    include_visual_grid: bool = True,
) -> OptimizationResult:
    # Independent and symmetric modes both use the measured LDT as supplied.
    scenario = replace(scenario, photometry_symmetry="asymmetric")
    influence = precompute_luminance_influence(group_ldt, scenario, rtable)
    relative_vector, _, iterations = _guided_relative_profile(
        model, scenario, influence, cct_k=cct_k, cri=cri,
        initial_current_ma=initial_current_ma, symmetric=False,
    )
    candidates = _final_scale_candidates(
        relative_vector, group_ldt, model, scenario, rtable,
        influence,
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
        scenario, rtable, cct_k=cct_k, cri=cri, include_visual_grid=include_visual_grid,
    )
    message = "" if final.metrics.compliant else (
        "Perfil independiente optimizado en Uo/Ul; se conserva la mejor escala validada"
    )
    return OptimizationResult(
        tuple(final.operating_point.currents_ma), final, final.metrics.compliant,
        iterations + 1, message,
        tuple(_scaled_vector(relative_vector, int(HL2X_CURRENT_MAX_MA))),
    )


def optimize_currents_and_tilt(
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    cct_k: int,
    cri: int,
    optimization_mode: str,
    initial_current_ma: float = 700.0,
) -> OptimizationResult:
    """Optimize relative currents and tilt on the discrete engineering grid."""
    if optimization_mode not in {"symmetric", "independent"}:
        raise ValueError("optimization_mode must be symmetric or independent")
    best_result: OptimizationResult | None = None
    best_quality: tuple[float, ...] | None = None
    total_iterations = 0
    evaluated_tilts: set[float] = set()
    current_best_tilt = max(-10.0, min(10.0, round(scenario.tilt_deg * 2.0) / 2.0))
    for step in (5.0, 2.0, 1.0, 0.5):
        if not evaluated_tilts:
            candidates = [round(-10.0 + index * step, 1) for index in range(int(20.0 / step) + 1)]
            candidates.append(current_best_tilt)
        else:
            candidates = [round(current_best_tilt + offset * step, 1) for offset in (-2, -1, 0, 1, 2)]
        for tilt_deg in sorted({max(-10.0, min(10.0, value)) for value in candidates}):
            if tilt_deg in evaluated_tilts:
                continue
            evaluated_tilts.add(tilt_deg)
            candidate_scenario = replace(scenario, tilt_deg=tilt_deg)
            if optimization_mode == "symmetric":
                candidate = optimize_currents_symmetric(
                    group_ldt, model, candidate_scenario, rtable,
                    cct_k=cct_k, cri=cri, initial_current_ma=initial_current_ma,
                    include_visual_grid=False,
                )
            else:
                candidate = optimize_currents(
                    group_ldt, model, candidate_scenario, rtable,
                    cct_k=cct_k, cri=cri, initial_current_ma=initial_current_ma,
                    include_visual_grid=False,
                )
            total_iterations += candidate.iterations
            quality = _final_quality(candidate.calculation, candidate_scenario) + (abs(tilt_deg),)
            if best_quality is None or quality < best_quality:
                best_result, best_quality = candidate, quality
                current_best_tilt = tilt_deg

    if best_result is None:
        raise ValueError("No se pudo evaluar ningún tilt")
    selected_scenario = replace(
        best_result.calculation.scenario,
        tilt_deg=best_result.calculation.scenario.tilt_deg,
        photometry_symmetry="asymmetric",
    )
    if optimization_mode == "symmetric":
        refined = optimize_currents_symmetric(
            group_ldt, model, selected_scenario, rtable,
            cct_k=cct_k, cri=cri, initial_current_ma=initial_current_ma,
            include_visual_grid=True,
        )
    else:
        refined = optimize_currents(
            group_ldt, model, selected_scenario, rtable,
            cct_k=cct_k, cri=cri, initial_current_ma=initial_current_ma,
            include_visual_grid=True,
        )
    message = refined.message
    tilt_message = f"Tilt optimizado: {selected_scenario.tilt_deg:+.1f}°."
    message = f"{message} {tilt_message}".strip()
    return OptimizationResult(
        tuple(refined.calculation.operating_point.currents_ma), refined.calculation,
        refined.feasible, total_iterations + refined.iterations, message,
        refined.relative_currents_ma,
    )
