"""Optimizacion global de flujo mediante matriz de influencia fotometrica.

Para geometria, optica y tilt fijos, la luminancia directa es lineal con el
flujo de cada luminaria. Este modulo calcula esa relacion una sola vez:

    L = A @ phi

y resuelve los flujos continuos antes de asignar modelo, driver y corriente.
"""

from __future__ import annotations

import math
import time
from typing import Iterable

import numpy as np

from photometric_engine.salvi_photometry.calculator import (
    LuminaireInstance,
    TunnelCalculator,
)
from photometric_engine.salvi_photometry.geometry import (
    LuminaireOrientation,
    Observer,
    mirror_c_for_interior_facing,
)
from photometric_engine.salvi_photometry.ldt_parser import load_ldt

from modules.tunnel.optimizer import (
    CHAIN_ORDER,
    _LDT_DIR,
    _OPTIC_LDT,
    flux_power_at_current,
    select_model_for_flux,
)
from modules.tunnel.required_luminance import build_requirement_samples


_UNIT_FLUX_LM = 10000.0


def _is_normative_requirement_zone(zone) -> bool:
    """Separa la envolvente CIE 88 de las capas físicas de control."""
    zone_type = str(getattr(zone, "zone_type", "") or "").lower()
    control_layer = str(
        getattr(zone, "control_layer", "legacy") or "legacy"
    ).lower()
    return (
        control_layer not in {"adaptation", "exterior"}
        and not zone_type.startswith("adaptation")
        and not zone_type.startswith("exterior")
    )


def _default_y_positions(arrangement: str, w: float, wall_offset: float) -> list[float]:
    wall_offset = min(
        max(0.05, float(wall_offset)),
        max(0.05, float(w) / 2.0 - 0.05),
    )
    if arrangement == "lateral_left":
        return [wall_offset]
    if arrangement in ("lateral_right", "unilateral"):
        return [w - wall_offset]
    if arrangement in ("bilateral_sym", "bilateral", "staggered"):
        return [wall_offset, w - wall_offset]
    if arrangement == "central_double":
        return [wall_offset, w - wall_offset]
    if arrangement == "central_offset":
        return [wall_offset]
    return [w / 2.0]


def _fixed_model_selection_for_flux(
    model: str,
    target_flux: float,
    *,
    cct: str,
    I_max_mA: float,
    I_min_pct: float,
) -> dict:
    """Punto de operación mínimo de un modelo físico ya instalado.

    A diferencia de ``select_model_for_flux``, nunca cambia de variante. Se
    usa para elevar la corriente de la BASE manteniendo su hardware y óptica.
    """
    i_min_mA = max(1.0, float(I_min_pct) * 350.0)
    i_max_mA = max(i_min_mA, float(I_max_mA))
    flux_min, power_min = flux_power_at_current(
        model, cct, i_min_mA, I_min_pct,
    )
    flux_max, power_max = flux_power_at_current(
        model, cct, i_max_mA, I_min_pct,
    )
    target = min(
        max(float(target_flux), float(flux_min)),
        float(flux_max),
    )
    if target <= float(flux_min) + 1e-6:
        current = i_min_mA
        flux, power = float(flux_min), float(power_min)
    elif target >= float(flux_max) - 1e-6:
        current = i_max_mA
        flux, power = float(flux_max), float(power_max)
    else:
        low, high = i_min_mA, i_max_mA
        for _ in range(40):
            middle = (low + high) / 2.0
            middle_flux, _ = flux_power_at_current(
                model, cct, middle, I_min_pct,
            )
            if float(middle_flux) >= target:
                high = middle
            else:
                low = middle
            if high - low <= 0.02:
                break
        current = high
        flux_value, power_value = flux_power_at_current(
            model, cct, current, I_min_pct,
        )
        flux, power = float(flux_value), float(power_value)
    return {
        "model": model,
        "mA": round(current, 1),
        "W": round(power, 1),
        "lm": round(flux, 0),
        "target_flux_lm": round(target, 3),
    }


def _transition_blocks(groups: list[dict]) -> list[list[int]]:
    """Índices por tramo ordenados hacia el portal.

    Tanto en transición como en umbral, dentro de una misma geometría la
    corriente no puede disminuir al acercarse a la boca. Además de responder
    a la curva CIE, esta restricción evita soluciones LP alternantes que
    cumplen Lavg pero destruyen Uo/Ul.
    """
    buckets: dict[tuple, list[tuple[float, int]]] = {}
    for i, group in enumerate(groups):
        zd = group["zd"]
        sp = group["sp"]
        zt = str(zd.zone_type or "")
        if "transition" not in zt and "threshold" not in zt:
            continue
        key = (
            id(zd),
            int(sp.get("spacing_stage", 0) or 0),
            round(float(sp.get("spacing_m", zd.d_used) or 0), 3),
            str(sp.get("optic") or zd.optic or ""),
            round(float(sp.get("tilt_deg", zd.tilt_deg) or 0), 2),
        )
        if "distance_from_interior_m" in sp:
            distance = float(sp["distance_from_interior_m"])
        elif zt.endswith("_b"):
            distance = abs(float(sp["s"]) - float(zd.s_start))
        else:
            distance = abs(float(zd.s_end) - float(sp["s"]))
        buckets.setdefault(key, []).append((distance, i))
    return [
        [idx for _, idx in sorted(items)]
        for items in buckets.values()
        if len(items) > 1
    ]


def _constant_flux_blocks(groups: list[dict]) -> list[list[int]]:
    """Luminarias del vano tipo Interior que deben compartir regulacion."""
    buckets: dict[tuple, list[int]] = {}
    for index, group in enumerate(groups):
        zd = group["zd"]
        sp = group["sp"]
        zone_type = str(zd.zone_type or "").lower()
        if "interior" not in zone_type or sp.get("support_candidate"):
            continue
        key = (
            id(zd),
            str(sp.get("optic") or zd.optic or ""),
            round(float(sp.get("tilt_deg", zd.tilt_deg) or 0), 2),
            round(float(sp.get("spacing_m", zd.d_used) or 0), 3),
        )
        buckets.setdefault(key, []).append(index)
    return [indices for indices in buckets.values() if len(indices) > 1]


def _relax_unreachable_targets(
    target: np.ndarray,
    maximum_available: np.ndarray,
    *,
    tolerance: float = 1e-7,
) -> tuple[np.ndarray, np.ndarray]:
    """Relaja solo los campos cuya demanda supera la capacidad instalada.

    Una muestra irrealizable no debe hacer que el optimizador abandone toda
    la solución y conserve el dimensionado uniforme inicial. Se limita su
    objetivo inferior al máximo físicamente disponible y se devuelve una
    máscara para poder informar del déficit residual; los demás campos siguen
    imponiendo la ``Lreq(s)`` completa.
    """
    requested = np.asarray(target, dtype=float)
    available = np.asarray(maximum_available, dtype=float)
    unreachable = available < requested - float(tolerance)
    relaxed = np.minimum(requested, available)
    return relaxed, unreachable


def _project_monotonic(phi: np.ndarray, blocks: Iterable[list[int]]) -> None:
    for block in blocks:
        values = np.maximum.accumulate(phi[block])
        phi[block] = values


def _monotonic_inequalities(
    n_fluxes: int,
    blocks: Iterable[list[int]],
    n_variables: int,
) -> tuple[list[np.ndarray], list[float]]:
    rows: list[np.ndarray] = []
    bounds: list[float] = []
    for block in blocks:
        for previous, current in zip(block, block[1:]):
            row = np.zeros(n_variables, dtype=float)
            row[previous] = 1.0
            row[current] = -1.0
            rows.append(row)
            bounds.append(0.0)
    return rows, bounds


def _solve_fluxes_numpy(
    A: np.ndarray,
    target: np.ndarray,
    phi_initial: np.ndarray,
    max_flux: float,
    monotonic_blocks: Iterable[list[int]],
    max_iters: int,
    fixed_fluxes: np.ndarray | None = None,
) -> tuple[np.ndarray, bool, str]:
    """Ruta de emergencia cuando SciPy no esta disponible."""
    phi = np.clip(np.asarray(phi_initial, dtype=float), 0.0, max_flux)
    fixed = (
        np.full(phi.shape, np.nan, dtype=float)
        if fixed_fluxes is None
        else np.asarray(fixed_fluxes, dtype=float)
    )
    fixed_mask = np.isfinite(fixed)
    phi[fixed_mask] = np.clip(fixed[fixed_mask], 0.0, max_flux)
    _project_monotonic(phi, monotonic_blocks)
    converged = False
    for _ in range(max(1, int(max_iters))):
        calculated = A @ phi
        deficit = target - calculated
        worst_idx = int(np.argmax(deficit))
        worst = float(deficit[worst_idx])
        if worst <= 1e-9:
            converged = True
            break
        row = A[worst_idx]
        available = np.where(
            (row > 0.0) & (phi < max_flux - 1e-6) & ~fixed_mask
        )[0]
        if not len(available):
            break
        best_col = int(available[np.argmax(row[available])])
        needed = worst / max(row[best_col], 1e-12)
        relative_deficit = worst / max(target[worst_idx], 1e-9)
        step_fraction = (
            0.20 if relative_deficit > 0.10
            else 0.10 if relative_deficit > 0.05
            else 0.05 if relative_deficit > 0.02
            else 0.01
        )
        adaptive_cap = max(
            max_flux * 0.005,
            max(phi[best_col], max_flux * 0.05) * step_fraction,
        )
        delta = min(needed, adaptive_cap, max_flux - phi[best_col])
        if delta <= 1e-9:
            break
        phi[best_col] += delta
        _project_monotonic(phi, monotonic_blocks)
        np.minimum(phi, max_flux, out=phi)

    if converged:
        calculated = A @ phi
        for col in np.argsort(-phi):
            if fixed_mask[col]:
                continue
            affected = A[:, col] > 0
            if not np.any(affected):
                phi[col] = 0.0
                continue
            removable = float(np.min(
                (calculated[affected] - target[affected])
                / A[affected, col]
            ))
            if removable <= 1e-6:
                continue
            delta = min(float(phi[col]), removable)
            phi[col] -= delta
            calculated -= A[:, col] * delta
        _project_monotonic(phi, monotonic_blocks)
    return phi, converged, "numpy"


def _solve_fluxes_minimax(
    A: np.ndarray,
    required: np.ndarray,
    target: np.ndarray,
    min_flux: float,
    max_flux: float,
    monotonic_blocks: Iterable[list[int]],
    constant_blocks: Iterable[list[int]],
    upper_mask: np.ndarray | None,
    phi_initial: np.ndarray,
    max_iters: int,
    fixed_fluxes: np.ndarray | None = None,
) -> tuple[np.ndarray, bool, str, float]:
    """LP en dos etapas: menor exceso maximo y despues menor flujo total."""
    try:
        import highspy
    except ImportError:
        phi, feasible, method = _solve_fluxes_numpy(
            A, target, phi_initial, max_flux, monotonic_blocks, max_iters,
            fixed_fluxes,
        )
        for block in constant_blocks:
            phi[block] = np.max(phi[block])
        if fixed_fluxes is not None:
            fixed = np.asarray(fixed_fluxes, dtype=float)
            fixed_mask = np.isfinite(fixed)
            phi[fixed_mask] = np.clip(
                fixed[fixed_mask], 0.0, max_flux,
            )
        ratios = (A @ phi) / np.maximum(required, 1e-9)
        return phi, feasible, method, max(0.0, float(np.max(ratios) - 1.0))

    n_fluxes = A.shape[1]
    n_variables = n_fluxes + 1
    # HiGHS trabaja mejor con x=phi/max_flux en [0,1] que mezclando
    # coeficientes fotometricos ~1e-4 con flujos ~1e5 lm.
    B = A * float(max_flux)
    lower_rows = np.hstack((-B, np.zeros((A.shape[0], 1))))
    if upper_mask is None:
        upper_mask = np.ones(A.shape[0], dtype=bool)
    else:
        upper_mask = np.asarray(upper_mask, dtype=bool)
    if not np.any(upper_mask):
        upper_mask[:] = True
    B_upper = B[upper_mask]
    required_upper = required[upper_mask]
    upper_rows = np.hstack((B_upper, -required_upper[:, None]))
    mono_rows, mono_bounds = _monotonic_inequalities(
        n_fluxes, monotonic_blocks, n_variables,
    )
    matrices = [lower_rows, upper_rows]
    rhs = [-target, required_upper]
    if mono_rows:
        matrices.append(np.vstack(mono_rows))
        rhs.append(np.asarray(mono_bounds, dtype=float))
    A_ub = np.vstack(matrices)
    b_ub = np.concatenate(rhs)
    equality_rows: list[np.ndarray] = []
    for block in constant_blocks:
        anchor = block[0]
        for index in block[1:]:
            row = np.zeros(n_variables, dtype=float)
            row[index] = 1.0
            row[anchor] = -1.0
            equality_rows.append(row)
    min_fraction = float(min_flux) / max(float(max_flux), 1e-9)

    objective = np.zeros(n_variables, dtype=float)
    objective[-1] = 1.0
    col_lower = np.concatenate((
        np.full(n_fluxes, min_fraction),
        np.array([0.0]),
    ))
    col_upper = np.concatenate((
        np.ones(n_fluxes),
        np.array([highspy.kHighsInf]),
    ))
    if fixed_fluxes is not None:
        fixed = np.asarray(fixed_fluxes, dtype=float)
        fixed_mask = np.isfinite(fixed)
        fixed_fraction = np.clip(
            fixed[fixed_mask] / max(float(max_flux), 1e-9),
            0.0,
            1.0,
        )
        col_lower[np.flatnonzero(fixed_mask)] = fixed_fraction
        col_upper[np.flatnonzero(fixed_mask)] = fixed_fraction
    row_matrix = A_ub
    row_lower = np.full(len(A_ub), -highspy.kHighsInf)
    row_upper = b_ub
    if equality_rows:
        equality_matrix = np.vstack(equality_rows)
        row_matrix = np.vstack((row_matrix, equality_matrix))
        row_lower = np.concatenate((
            row_lower, np.zeros(len(equality_rows)),
        ))
        row_upper = np.concatenate((
            row_upper, np.zeros(len(equality_rows)),
        ))

    row_indices, column_indices = np.nonzero(row_matrix)
    counts = np.bincount(row_indices, minlength=len(row_matrix))
    starts = np.concatenate(([0], np.cumsum(counts))).astype(np.int32)
    column_indices = column_indices.astype(np.int32)
    values = row_matrix[row_indices, column_indices].astype(float)

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    highs.addCols(
        n_variables,
        objective,
        col_lower,
        col_upper,
        0,
        np.zeros(n_variables + 1, dtype=np.int32),
        np.empty(0, dtype=np.int32),
        np.empty(0, dtype=float),
    )
    highs.addRows(
        len(row_matrix),
        row_lower,
        row_upper,
        len(values),
        starts,
        column_indices,
        values,
    )
    highs.run()
    if highs.getModelStatus() != highspy.HighsModelStatus.kOptimal:
        fallback = np.clip(
            np.asarray(phi_initial, dtype=float), 0.0, max_flux,
        )
        if fixed_fluxes is not None:
            fixed = np.asarray(fixed_fluxes, dtype=float)
            fixed_mask = np.isfinite(fixed)
            fallback[fixed_mask] = np.clip(
                fixed[fixed_mask], 0.0, max_flux,
            )
        return fallback, False, "highspy", float("inf")

    stage1_solution = np.asarray(highs.getSolution().col_value, dtype=float)
    u_opt = max(0.0, float(stage1_solution[-1]))
    objective[:] = 0.0
    # Coste relativo: un cd/m2 de exceso en Interior pesa mas que el mismo
    # cd/m2 en Umbral. Asi se ajusta toda la curva y no solo el flujo total.
    relative_weights = np.where(upper_mask, 1.0, 0.05)
    relative_cost = B.T @ (
        relative_weights / np.maximum(required, 1e-9)
    )
    scale = max(float(np.max(relative_cost)), 1e-12)
    objective[:n_fluxes] = relative_cost / scale
    all_columns = np.arange(n_variables, dtype=np.int32)
    highs.changeColsCost(
        n_variables,
        all_columns,
        objective,
    )
    highs.changeColBounds(n_fluxes, 0.0, u_opt + 1e-7)
    highs.run()
    stage2_success = (
        highs.getModelStatus() == highspy.HighsModelStatus.kOptimal
    )
    solution = (
        np.asarray(highs.getSolution().col_value, dtype=float)
        if stage2_success else stage1_solution
    )
    phi = np.asarray(solution[:n_fluxes], dtype=float) * float(max_flux)
    feasible = bool(np.all(A @ phi >= target - 1e-7))
    method = "highspy-2stage" if stage2_success else "highspy-1stage"
    return phi, feasible, method, u_opt


def _solve_semicontinuous_fluxes_minimax(
    A_scaled: np.ndarray,
    required: np.ndarray,
    target: np.ndarray,
    floor_fractions: np.ndarray,
    fixed_fractions: np.ndarray,
    *,
    monotonic_blocks: Iterable[list[int]] = (),
    quality_rows: np.ndarray | None = None,
    upper_mask: np.ndarray | None = None,
    continuous_mask: np.ndarray | None = None,
    cost_weights: np.ndarray | None = None,
    time_limit_s: float = 8.0,
) -> tuple[np.ndarray, bool, str, float]:
    """MILP mixto para regulación y selección de luminarias.

    Las columnas normales son semicontinuas: ``OFF`` o ``Imin..Imax``.
    Las marcadas en ``continuous_mask`` permanecen encendidas y pueden variar
    entre su fracción base y la máxima. Esto permite usar la línea BASE como
    refuerzo regulable sin autorizar su apagado.
    """
    try:
        import highspy
    except ImportError:
        return (
            np.zeros(A_scaled.shape[1], dtype=float),
            False,
            "highspy-unavailable",
            float("inf"),
        )

    n_fluxes = A_scaled.shape[1]
    n_variables = n_fluxes + 1
    lower_rows = np.hstack((
        -A_scaled,
        np.zeros((A_scaled.shape[0], 1), dtype=float),
    ))
    if upper_mask is None:
        upper_mask = np.ones(A_scaled.shape[0], dtype=bool)
    else:
        upper_mask = np.asarray(upper_mask, dtype=bool)
    if not np.any(upper_mask):
        upper_mask[:] = True
    upper_rows = np.hstack((
        A_scaled[upper_mask],
        -required[upper_mask, None],
    ))
    matrices = [lower_rows, upper_rows]
    upper_bounds = [-target, required[upper_mask]]
    monotonic_rows, monotonic_bounds = _monotonic_inequalities(
        n_fluxes, monotonic_blocks, n_variables,
    )
    if monotonic_rows:
        matrices.append(np.vstack(monotonic_rows))
        upper_bounds.append(np.asarray(monotonic_bounds, dtype=float))
    if quality_rows is not None and len(quality_rows):
        quality_matrix = np.hstack((
            np.asarray(quality_rows, dtype=float),
            np.zeros((len(quality_rows), 1), dtype=float),
        ))
        matrices.append(quality_matrix)
        upper_bounds.append(np.zeros(len(quality_rows), dtype=float))
    row_matrix = np.vstack(matrices)
    row_upper = np.concatenate(upper_bounds)
    row_lower = np.full(len(row_matrix), -highspy.kHighsInf)

    objective = np.zeros(n_variables, dtype=float)
    objective[-1] = 1.0
    floors = np.maximum(np.asarray(floor_fractions, dtype=float), 1e-6)
    continuous = (
        np.zeros(n_fluxes, dtype=bool)
        if continuous_mask is None
        else np.asarray(continuous_mask, dtype=bool)
    )
    col_lower = np.concatenate((
        floors,
        np.array([0.0]),
    ))
    col_upper = np.ones(n_variables, dtype=float)
    col_upper[-1] = highspy.kHighsInf
    fixed = np.asarray(fixed_fractions, dtype=float)
    fixed_mask = np.isfinite(fixed)
    fixed_indices = np.flatnonzero(fixed_mask)
    col_lower[fixed_indices] = fixed[fixed_indices]
    col_upper[fixed_indices] = fixed[fixed_indices]

    row_indices, column_indices = np.nonzero(row_matrix)
    counts = np.bincount(row_indices, minlength=len(row_matrix))
    starts = np.concatenate(([0], np.cumsum(counts))).astype(np.int32)
    column_indices = column_indices.astype(np.int32)
    values = row_matrix[row_indices, column_indices].astype(float)

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    highs.setOptionValue("time_limit", max(1.0, float(time_limit_s)))
    highs.setOptionValue("mip_rel_gap", 1e-2)
    highs.addCols(
        n_variables,
        objective,
        col_lower,
        col_upper,
        0,
        np.zeros(n_variables + 1, dtype=np.int32),
        np.empty(0, dtype=np.int32),
        np.empty(0, dtype=float),
    )
    for index in range(n_fluxes):
        if not fixed_mask[index] and not continuous[index]:
            highs.changeColIntegrality(
                index, highspy.HighsVarType.kSemiContinuous,
            )
    highs.addRows(
        len(row_matrix),
        row_lower,
        row_upper,
        len(values),
        starts,
        column_indices,
        values,
    )
    highs.run()
    status = highs.getModelStatus()
    acceptable = status in (
        highspy.HighsModelStatus.kOptimal,
        highspy.HighsModelStatus.kTimeLimit,
    )
    if not acceptable:
        return (
            np.zeros(n_fluxes, dtype=float),
            False,
            f"highspy-mip-{status.name}",
            float("inf"),
        )
    stage1_solution = np.asarray(
        highs.getSolution().col_value, dtype=float,
    )
    fractions = stage1_solution[:n_fluxes]
    if np.any(A_scaled @ fractions < target - 1e-6):
        return fractions, False, "highspy-mip-infeasible", float("inf")

    u_opt = max(0.0, float(stage1_solution[-1]))
    if status == highspy.HighsModelStatus.kTimeLimit:
        return (
            fractions,
            True,
            "highspy-mip-feasible",
            u_opt,
        )
    relative_cost = (
        A_scaled.T @ (1.0 / np.maximum(required, 1e-9))
        if cost_weights is None
        else np.maximum(np.asarray(cost_weights, dtype=float), 0.0)
    )
    scale = max(float(np.max(relative_cost)), 1e-12)
    objective[:] = 0.0
    objective[:n_fluxes] = relative_cost / scale
    all_columns = np.arange(n_variables, dtype=np.int32)
    highs.changeColsCost(n_variables, all_columns, objective)
    highs.changeColBounds(n_fluxes, 0.0, u_opt + 1e-6)
    highs.run()
    stage2_status = highs.getModelStatus()
    if stage2_status in (
        highspy.HighsModelStatus.kOptimal,
        highspy.HighsModelStatus.kTimeLimit,
    ):
        candidate = np.asarray(
            highs.getSolution().col_value, dtype=float,
        )[:n_fluxes]
        if np.all(A_scaled @ candidate >= target - 1e-6):
            fractions = candidate
    method = (
        "highspy-mip-2stage"
        if stage2_status == highspy.HighsModelStatus.kOptimal
        else "highspy-mip-feasible"
    )
    return fractions, True, method, u_opt


def optimize_layered_scene_fluxes(
    zone_designs,
    *,
    h: float,
    w: float,
    mf: float,
    rtable: str,
    cct: str,
    I_min_pct: float,
    I_max_mA: float,
    arrangement: str,
    wall_offset: float,
    tube_length_m: float,
    Lth: float,
    Lth_b: float,
    Lin: float,
    speed_kmh: float,
    scenarios: dict,
    scene_keys: tuple[str, ...] = ("sunny", "normal", "overcast", "dusk"),
    enforce_portal_edges: bool = True,
    design_margin: float = 0.003,
    max_iters: int = 1200,
    sample_step_m: float = 4.0,
    mip_time_limit_s: float = 2.0,
) -> tuple[list[str], dict]:
    """Regula globalmente escenas diurnas sobre el hardware ya instalado.

    La geometría, fotometría, tilt, modelo y driver quedan fijos. Las variables
    son solo las fracciones de flujo de cada punto de luz. La BASE y los
    refuerzos se regulan entre OFF/Imin e Imax de su driver. La BASE recibe
    prioridad de coste en las escenas diurnas: se aprovecha primero la
    instalación permanente antes de activar refuerzos adicionales.
    """
    started = time.perf_counter()
    messages: list[str] = []
    diagnostics: dict = {
        "elapsed_s": 0.0,
        "matrix_calls": 0,
        "samples": 0,
        "scenes": {},
    }
    # Las fuentes fotométricas y la envolvente normativa son conjuntos
    # distintos. Una zona puede quedarse sin luminarias propias porque recibe
    # luz de CTH u otra capa, pero su Lreq CIE 88 no puede desaparecer del
    # problema de control.
    requirement_zones = [
        zone for zone in zone_designs
        if float(getattr(zone, "s_end", 0.0)) >= 0.0
        and float(getattr(zone, "s_start", 0.0)) <= tube_length_m
        and _is_normative_requirement_zone(zone)
    ]
    active_zones = [
        zone for zone in zone_designs
        if getattr(zone, "setpoints", None)
        and float(getattr(zone, "s_end", 0.0)) >= 0.0
        and float(getattr(zone, "s_start", 0.0)) <= tube_length_m
    ]
    if not active_zones:
        diagnostics["elapsed_s"] = round(time.perf_counter() - started, 4)
        return messages, diagnostics

    phot_cache: dict = {}

    def _phot(optic_id):
        oid = optic_id or "F2MD"
        if oid not in phot_cache:
            filename = _OPTIC_LDT.get(oid, _OPTIC_LDT["F2MD"])
            phot_cache[oid] = load_ldt(_LDT_DIR / filename)
        return phot_cache[oid]

    ys_default = _default_y_positions(arrangement, w, wall_offset)

    def _ys_for_setpoint(sp):
        if arrangement in ("bilateral_stag", "staggered"):
            idx = int(sp.get("idx", 1) or 1)
            return [
                wall_offset if (idx - 1) % 2 == 0 else (w - wall_offset)
            ]
        return ys_default

    def _tilt_for_y(tilt_base, y_pos):
        return tilt_base if y_pos < w / 2.0 else -tilt_base

    groups: list[dict] = []
    for zone in active_zones:
        for index, setpoint in enumerate(zone.setpoints or []):
            optic_id = setpoint.get("optic") or zone.optic or "F2MD"
            tilt_base = float(
                setpoint.get("tilt_deg", zone.tilt_deg) or 0.0
            )
            groups.append({
                "zd": zone,
                "i": index,
                "sp": setpoint,
                "lums": [
                    LuminaireInstance(
                        x=float(setpoint["s"]),
                        y=float(y_pos),
                        H=h,
                        photometry=_phot(optic_id),
                        flux_lm=_UNIT_FLUX_LM,
                        orientation=LuminaireOrientation(
                            tilt_deg=_tilt_for_y(tilt_base, y_pos),
                            mirror_c=mirror_c_for_interior_facing(
                                y_pos, w, arrangement,
                            ),
                        ),
                    )
                    for y_pos in _ys_for_setpoint(setpoint)
                ],
            })
    if not groups:
        diagnostics["elapsed_s"] = round(time.perf_counter() - started, 4)
        return messages, diagnostics

    scene_definitions = {}
    for key in scene_keys:
        definition = scenarios.get(key, {})
        factor = float(definition.get("L20_factor", 0.0) or 0.0)
        if factor <= 0.0:
            continue
        samples = [
            meta for meta in build_requirement_samples(
                requirement_zones,
                tube_length_m=tube_length_m,
                Lth=max(float(Lin), float(Lth) * factor),
                Lth_b=max(float(Lin), float(Lth_b) * factor),
                Lin=Lin,
                speed_kmh=speed_kmh,
                step_m=min(5.0, max(1.0, float(sample_step_m or 4.0))),
                include_luminaire_midpoints=False,
            )
        ]
        if samples:
            scene_definitions[key] = {
                "factor": factor,
                "samples": samples,
            }
    if not scene_definitions:
        diagnostics["elapsed_s"] = round(time.perf_counter() - started, 4)
        return messages, diagnostics

    # Usa el mismo alcance conservador que la verificación CIE 140. Recortar
    # solo con el alcance de la óptica instalada descartaba pequeñas
    # contribuciones lejanas que, acumuladas en una BASE periódica, no son
    # despreciables y hacía que el control viera menos L que el cierre CIE 140.
    from modules.tunnel.photometric_verify import _max_reach_for_h
    reach = _max_reach_for_h(h)
    calculator = TunnelCalculator(rtable, mf, max_luminaire_dist=reach)
    observers = {
        1.0: Observer(
            lane_y_m=w / 2.0, d_observer_m=60.0, direction=1.0,
        ),
        -1.0: Observer(
            lane_y_m=w / 2.0, d_observer_m=60.0, direction=-1.0,
        ),
    }
    ys_calc = [(index + 0.5) * w / 5.0 for index in range(5)]
    sample_positions = sorted({
        float(meta["s"])
        for definition in scene_definitions.values()
        for meta in definition["samples"]
    })

    all_lums = []
    group_starts = []
    for group in groups:
        group_starts.append(len(all_lums))
        all_lums.extend(group["lums"])
    group_starts_array = np.asarray(group_starts, dtype=int)

    influence_by_direction: dict[float, np.ndarray] = {}
    directions_needed = sorted({
        float(meta["direction"])
        for definition in scene_definitions.values()
        for meta in definition["samples"]
    })
    for direction in directions_needed:
        points = [
            (position, y_pos)
            for position in sample_positions
            for y_pos in ys_calc
        ]
        physical = calculator.luminance_contributions_at_points_batch(
            points, all_lums, observers[direction],
        )
        physical_points = physical.reshape(
            len(sample_positions), len(ys_calc), len(all_lums),
        )
        grouped_points = (
            np.add.reduceat(
                physical_points, group_starts_array, axis=2,
            )
            / _UNIT_FLUX_LM
        )
        influence_by_direction[direction] = grouped_points.mean(axis=1)
        diagnostics["matrix_calls"] += 1
    position_index = {
        round(position, 6): index
        for index, position in enumerate(sample_positions)
    }
    diagnostics["samples"] = len(sample_positions)

    installed_fluxes = np.asarray([
        max(0.0, float(group["sp"].get("flux_lm", 0.0) or 0.0))
        for group in groups
    ])
    i_min_mA = max(1.0, float(I_min_pct) * 350.0)
    i_max_mA = max(i_min_mA, float(I_max_mA))
    # La corriente de diseño no es el límite disponible del driver. Tanto BASE
    # como las capas de refuerzo pueden usar el intervalo físico Imin..Imax
    # del modelo APHEX instalado en una escena diurna.
    max_fluxes = installed_fluxes.copy()
    for index, group in enumerate(groups):
        setpoint = group["sp"]
        zone = group["zd"]
        model = str(setpoint.get("model", zone.model) or zone.model)
        try:
            max_flux, _ = flux_power_at_current(
                model, cct, i_max_mA, I_min_pct,
            )
            max_fluxes[index] = max(
                max_fluxes[index], max(0.0, float(max_flux)),
            )
        except (KeyError, ValueError):
            # Preserve the known limit for legacy models.
            pass
    fixed_fractions = np.full(len(groups), np.nan, dtype=float)
    continuous_mask = np.zeros(len(groups), dtype=bool)
    for index, group in enumerate(groups):
        layer = str(
            getattr(group["zd"], "control_layer", "legacy") or "legacy"
        )
        if layer == "adaptation":
            # The layer is locked outside dusk and released per scene below.
            fixed_fractions[index] = 0.0
    monotonic_blocks = _transition_blocks(groups)
    portal_buffer = 5.0 * float(h)
    has_portal_a = any(
        "threshold" in str(zone.zone_type or "").lower()
        and not str(zone.zone_type or "").lower().endswith("_b")
        for zone in requirement_zones
    )
    has_portal_b = any(
        str(zone.zone_type or "").lower().endswith("_b")
        for zone in requirement_zones
    )
    has_adaptation = any(
        str(getattr(zone, "control_layer", "legacy") or "legacy")
        == "adaptation"
        for zone in active_zones
    )

    def _fixed_model_operation(
        group: dict,
        target_flux: float,
        *,
        max_current_mA: float | None = None,
    ) -> dict:
        setpoint = group["sp"]
        zone = group["zd"]
        model = str(setpoint.get("model", zone.model) or zone.model)
        installed_current = float(
            setpoint.get("current_mA", zone.current_mA) or 0.0
        )
        installed_flux = float(
            setpoint.get("flux_lm", zone.flux_lm) or 0.0
        )
        installed_power = float(
            setpoint.get("power_w", zone.power_w) or 0.0
        )
        current_limit = max(
            i_min_mA,
            float(max_current_mA or installed_current),
        )
        try:
            max_flux, max_power = flux_power_at_current(
                model, cct, current_limit, I_min_pct,
            )
        except (KeyError, ValueError):
            max_flux, max_power = installed_flux, installed_power
            current_limit = installed_current
        max_flux = max(float(installed_flux), float(max_flux))
        target = max(0.0, min(float(target_flux), max_flux))
        if target <= 1e-9:
            return {
                "state": "off",
                "current_mA": 0.0,
                "flux_lm": 0.0,
                "power_w": 0.0,
                "driver_floor": False,
                "target_flux_lm": 0.0,
            }
        if target >= max_flux - 1e-6:
            return {
                "state": "on",
                "current_mA": round(current_limit, 1),
                "flux_lm": round(max_flux, 3),
                "power_w": round(float(max_power), 3),
                "driver_floor": False,
                "target_flux_lm": round(target, 3),
            }
        flux_min, power_min = flux_power_at_current(
            model, cct, i_min_mA, I_min_pct,
        )
        if target <= float(flux_min) + 1e-9:
            return {
                "state": "on",
                "current_mA": round(i_min_mA, 1),
                "flux_lm": round(float(flux_min), 3),
                "power_w": round(float(power_min), 3),
                "driver_floor": True,
                "target_flux_lm": round(target, 3),
            }
        low = i_min_mA
        high = current_limit
        for _ in range(36):
            mid = (low + high) / 2.0
            flux_mid, _ = flux_power_at_current(
                model, cct, mid, I_min_pct,
            )
            if float(flux_mid) >= target:
                high = mid
            else:
                low = mid
            if high - low <= 0.05:
                break
        flux_actual, power_actual = flux_power_at_current(
            model, cct, high, I_min_pct,
        )
        return {
            "state": "on",
            "current_mA": round(high, 1),
            "flux_lm": round(float(flux_actual), 3),
            "power_w": round(float(power_actual), 3),
            "driver_floor": False,
            "target_flux_lm": round(target, 3),
        }

    floor_fractions = np.zeros(len(groups), dtype=float)
    power_costs = np.zeros(len(groups), dtype=float)
    for index, group in enumerate(groups):
        installed_power = max(
            0.0,
            float(group["sp"].get("power_w", 0.0) or 0.0),
        )
        power_costs[index] = (
            installed_power * max(1, len(group.get("lums", [])))
        )
        if max_fluxes[index] <= 1e-9:
            continue
        setpoint = group["sp"]
        zone = group["zd"]
        layer = str(
            getattr(zone, "control_layer", "legacy") or "legacy"
        )
        model = str(setpoint.get("model", zone.model) or zone.model)
        try:
            floor_flux, _ = flux_power_at_current(
                model, cct, i_min_mA, I_min_pct,
            )
            floor_fractions[index] = min(
                1.0,
                max(0.0, float(floor_flux) / max_fluxes[index]),
            )
        except (KeyError, ValueError):
            # Un modelo heredado sin curva regulable conserva su flujo
            # instalado como mínimo encendido.
            floor_fractions[index] = min(
                1.0, installed_fluxes[index] / max(max_fluxes[index], 1e-9),
            )
        if layer == "permanent":
            # Segundo criterio del MIP: a igualdad de Lcalc/Lreq y potencia,
            # se regula primero BASE. El coste físico se sigue publicando sin
            # alteración; este factor solo desempata la estrategia.
            power_costs[index] *= 0.15

    for key, definition in scene_definitions.items():
        # The dedicated adaptation layer is available only in dusk. At that
        # scene all other portal-reinforcement layers are locked off, while
        # the BASE retains its normal dimming interval.
        scene_fixed_fractions = fixed_fractions.copy()
        scene_continuous_mask = continuous_mask.copy()
        if has_adaptation:
            for index, group in enumerate(groups):
                layer = str(
                    getattr(group["zd"], "control_layer", "legacy")
                    or "legacy"
                )
                if layer == "adaptation":
                    scene_fixed_fractions[index] = (
                        np.nan if key == "dusk" else 0.0
                    )
                elif key == "dusk" and layer != "permanent":
                    scene_fixed_fractions[index] = 0.0
        scene_fixed_mask = np.isfinite(scene_fixed_fractions)
        samples = definition["samples"]
        rows = np.vstack([
            influence_by_direction[float(meta["direction"])][
                position_index[round(float(meta["s"]), 6)]
            ]
            for meta in samples
        ])
        required = np.asarray(
            [float(meta["target"]) for meta in samples], dtype=float,
        )
        representative_mask = np.ones(len(samples), dtype=bool)
        # El optimizador debe usar exactamente los mismos campos que se
        # publican y verifican al final. Los bordes 5H solo son diagnóstico
        # cuando el proyecto lo ha solicitado de forma expresa.
        if not enforce_portal_edges:
            for index, meta in enumerate(samples):
                if (
                    has_portal_a
                    and float(meta["direction"]) == 1.0
                    and float(meta["s"]) < portal_buffer
                ):
                    representative_mask[index] = False
                if (
                    has_portal_b
                    and float(meta["direction"]) == -1.0
                    and float(meta["s"]) > tube_length_m - portal_buffer
                ):
                    representative_mask[index] = False
        if not np.any(representative_mask):
            representative_mask[:] = True
        rows = rows[representative_mask]
        required = required[representative_mask]
        samples_used = [
            meta for index, meta in enumerate(samples)
            if representative_mask[index]
        ]

        def _field_diagnostic(
            calculated_values: np.ndarray,
            flux_values: np.ndarray,
            *,
            sample_index: int,
            operation_values: list[dict] | None = None,
            top_n: int = 8,
        ) -> dict:
            """Traza un campo hasta las luminarias que aportan su Lcalc."""
            meta = samples_used[sample_index]
            zone = meta["zone"]
            contributions = rows[sample_index] * flux_values
            layer_totals: dict[str, float] = {}
            portal_totals: dict[str, float] = {}
            for column, contribution in enumerate(contributions):
                if contribution <= 1e-12:
                    continue
                source_zone = groups[column]["zd"]
                layer = str(
                    getattr(source_zone, "control_layer", "legacy")
                    or "legacy"
                )
                portal = str(
                    getattr(source_zone, "portal", None) or "A-B"
                )
                layer_totals[layer] = (
                    layer_totals.get(layer, 0.0) + float(contribution)
                )
                portal_totals[portal] = (
                    portal_totals.get(portal, 0.0) + float(contribution)
                )

            strongest = np.argsort(contributions)[::-1]
            top_sources = []
            for column in strongest:
                contribution = float(contributions[column])
                if contribution <= 1e-9 or len(top_sources) >= top_n:
                    break
                group = groups[int(column)]
                source_zone = group["zd"]
                setpoint = group["sp"]
                operation = (
                    operation_values[int(column)]
                    if operation_values is not None
                    else setpoint["scenario_operating_points"][key]
                )
                top_sources.append({
                    "s_m": round(float(setpoint.get("s", 0.0) or 0.0), 3),
                    "zone": str(source_zone.zone_name),
                    "layer": str(
                        getattr(source_zone, "control_layer", "legacy")
                        or "legacy"
                    ),
                    "portal": getattr(source_zone, "portal", None),
                    "model": str(
                        setpoint.get("model", source_zone.model)
                        or source_zone.model
                    ),
                    "state": str(operation.get("state", "on")),
                    "current_mA": round(
                        float(operation.get("current_mA", 0.0) or 0.0), 1,
                    ),
                    "flux_lm": round(
                        float(operation.get("flux_lm", 0.0) or 0.0), 1,
                    ),
                    "L_contribution_cd_m2": round(contribution, 4),
                    "contribution_pct": round(
                        100.0
                        * contribution
                        / max(float(calculated_values[sample_index]), 1e-9),
                        2,
                    ),
                })

            L_required = float(required[sample_index])
            L_calculated = float(calculated_values[sample_index])
            return {
                "s_m": round(float(meta["s"]), 3),
                "zone": str(getattr(zone, "zone_name", "")),
                "zone_type": str(getattr(zone, "zone_type", "")),
                "direction": (
                    "B->A"
                    if float(meta["direction"]) < 0.0 else "A->B"
                ),
                "L_required_cd_m2": round(L_required, 4),
                "L_calculated_cd_m2": round(L_calculated, 4),
                "ratio": round(
                    L_calculated / max(L_required, 1e-9), 4,
                ),
                "excess_cd_m2": round(
                    max(0.0, L_calculated - L_required), 4,
                ),
                "contribution_by_layer_cd_m2": {
                    layer: round(value, 4)
                    for layer, value in sorted(layer_totals.items())
                },
                "contribution_by_portal_cd_m2": {
                    portal: round(value, 4)
                    for portal, value in sorted(portal_totals.items())
                },
                "top_luminaires": top_sources,
            }

        def _ratio_diagnostics(
            calculated_values: np.ndarray,
            flux_values: np.ndarray,
            operation_values: list[dict] | None = None,
        ) -> dict:
            ratios_here = calculated_values / np.maximum(required, 1e-9)
            minimum_index = int(np.argmin(ratios_here))
            maximum_index = int(np.argmax(ratios_here))
            return {
                "minimum_field": _field_diagnostic(
                    calculated_values,
                    flux_values,
                    sample_index=minimum_index,
                    operation_values=operation_values,
                ),
                "maximum_field": _field_diagnostic(
                    calculated_values,
                    flux_values,
                    sample_index=maximum_index,
                    operation_values=operation_values,
                ),
            }

        # Las variables son fracciones [0,1] del flujo disponible en cada
        # modelo instalado. Las capas no permanentes llegan hasta Imax.
        scaled_rows = rows * max_fluxes[None, :]
        initial = np.asarray([
            (
                float(
                    group["sp"]["scenario_operating_points"][key].get(
                        "flux_lm", 0.0,
                    )
                    or 0.0
                )
                / max(max_fluxes[index], 1e-9)
            )
            for index, group in enumerate(groups)
        ])
        local_fluxes = initial * max_fluxes
        local_ratios = (
            rows @ local_fluxes
        ) / np.maximum(required, 1e-9)
        local_calculated = rows @ local_fluxes
        local_minimum_ratio = float(np.min(local_ratios))
        # Una escena ya conforme no es necesariamente una escena bien
        # ajustada. La antigua salida anticipada conservaba las consignas
        # locales de normal y nublado en cuanto superaban Lreq; por eso
        # podían mantenerse excesos importantes en el umbral aunque el
        # hardware permitiera reducir corriente o apagar refuerzos. Todas las
        # escenas diurnas se resuelven ahora contra la misma envolvente
        # Lreq*(1+margen), y el minimax reduce primero el peor exceso y luego
        # la potencia. La arquitectura específica se fija por escena arriba.
        target = required * (1.0 + max(0.0, float(design_margin)))
        # Un driver no puede materializar flujos entre 0 e Imin. Resolver
        # Un driver no puede materializar flujos entre 0 e Imin. Esto aplica
        # igualmente a SOLEADO: usar LP continuo sólo allí hacía que BASE
        # quedase fija y que el redondeo posterior alterase su cierre CIE 140.
        fractions, feasible, method, excess = (
            _solve_semicontinuous_fluxes_minimax(
                scaled_rows,
                required,
                target,
                floor_fractions,
                scene_fixed_fractions,
                monotonic_blocks=monotonic_blocks,
                continuous_mask=scene_continuous_mask,
                cost_weights=power_costs,
                time_limit_s=min(8.0, max(2.0, float(mip_time_limit_s))),
            )
        )
        if not feasible:
            capacity_fractions = np.ones(len(groups), dtype=float)
            capacity_fractions[scene_fixed_mask] = (
                scene_fixed_fractions[scene_fixed_mask]
            )
            capacity_fluxes = capacity_fractions * max_fluxes
            capacity_calculated = rows @ capacity_fluxes
            capacity_target_ratios = (
                capacity_calculated / np.maximum(target, 1e-9)
            )
            capacity_sufficient = bool(
                np.all(capacity_calculated >= target - 1e-6)
            )
            diagnostics["scenes"][key] = {
                "applied": False,
                "solver": method,
                "reason": "infeasible",
                "infeasibility_type": (
                    "no_semicontinuous_pattern"
                    if capacity_sufficient
                    else "insufficient_installed_capacity"
                ),
                "local_min_ratio": round(
                    float(np.min(local_ratios)), 4,
                ),
                "local_max_ratio": round(
                    float(np.max(local_ratios)), 4,
                ),
                "capacity_min_target_ratio": round(
                    float(np.min(capacity_target_ratios)), 4,
                ),
                "capacity_sufficient": capacity_sufficient,
                "local_fields": _ratio_diagnostics(
                    local_calculated, local_fluxes,
                ),
                "capacity_fields": _ratio_diagnostics(
                    capacity_calculated, capacity_fluxes,
                ),
            }
            messages.append(
                f"Control global {key} no aplicado: la instalacion fija "
                + (
                    "tiene capacidad continua, pero no existe una pauta "
                    "OFF/Imin..Imax factible."
                    if capacity_sufficient else
                    "no ofrece capacidad máxima suficiente en toda la "
                    "envolvente normativa."
                )
            )
            continue

        target_fluxes = np.clip(fractions, 0.0, 1.0) * max_fluxes
        actual_fluxes = np.zeros(len(groups), dtype=float)
        operations: list[dict] = []
        for index, group in enumerate(groups):
            operation = _fixed_model_operation(
                group,
                float(target_fluxes[index]),
                max_current_mA=i_max_mA,
            )
            previous = group["sp"]["scenario_operating_points"][key]
            operation["target_total_cd_m2"] = previous.get(
                "target_total_cd_m2",
            )
            operation["target_layer_cd_m2"] = previous.get(
                "target_layer_cd_m2",
            )
            operation["global_optimized"] = True
            operations.append(operation)
            actual_fluxes[index] = float(operation["flux_lm"])

        calculated = rows @ actual_fluxes
        ratios = calculated / np.maximum(required, 1e-9)
        minimum_ratio = float(np.min(ratios))
        if minimum_ratio < 1.0 - 1e-7:
            diagnostics["scenes"][key] = {
                "applied": False,
                "solver": method,
                "reason": "driver_mapping_deficit",
                "min_ratio": round(minimum_ratio, 4),
            }
            messages.append(
                f"Control global {key} no aplicado: el mapeo a corrientes "
                f"deja Lcalc/Lreq={minimum_ratio:.4f}."
            )
            continue

        for group, operation in zip(groups, operations):
            group["sp"]["scenario_operating_points"][key] = operation
        diagnostics["scenes"][key] = {
            "applied": True,
            "solver": method,
            "samples": len(samples_used),
            "min_ratio": round(minimum_ratio, 4),
            "max_ratio": round(float(np.max(ratios)), 4),
            "continuous_excess_pct": round(float(excess) * 100.0, 3),
            **_ratio_diagnostics(
                calculated,
                actual_fluxes,
                operation_values=operations,
            ),
        }
        messages.append(
            f"Control global {key} {method}: deficit 0, "
            f"Lcalc/Lreq={minimum_ratio:.4f}..{float(np.max(ratios)):.4f}."
        )

        bucket = scenarios.setdefault(key, {})
        active = 0
        off = 0
        floors = 0
        power = 0.0
        flux = 0.0
        for group in groups:
            operation = group["sp"]["scenario_operating_points"][key]
            if operation["state"] == "off":
                off += 1
            else:
                active += 1
            floors += int(bool(operation.get("driver_floor", False)))
            power += float(operation.get("power_w", 0.0) or 0.0)
            flux += float(operation.get("flux_lm", 0.0) or 0.0)
        bucket.update({
            "active_luminaires": active,
            "off_luminaires": off,
            "driver_floor_luminaires": floors,
            "power_kw": round(power / 1000.0, 3),
            "flux_lm": round(flux, 0),
            "global_optimization": diagnostics["scenes"][key],
        })

    diagnostics["elapsed_s"] = round(time.perf_counter() - started, 4)
    return messages, diagnostics


def optimize_layout_fluxes(
    zone_designs,
    *,
    h: float,
    w: float,
    mf: float,
    rtable: str,
    cct: str,
    I_max_mA: float,
    I_min_pct: float,
    arrangement: str,
    wall_offset: float,
    tube_length_m: float,
    Lth: float,
    Lth_b: float,
    Lin: float,
    speed_kmh: float,
    optimization_goal: str = "min_luminaires",
    design_margin: float = 0.003,
    max_iters: int = 1200,
    enforce_portal_edges: bool = True,
    num_lanes: int | None = None,
    lane_width_m: float | None = None,
    shoulder_left_m: float = 0.0,
    shoulder_right_m: float = 0.0,
    sidewalk_left_m: float = 0.0,
    sidewalk_right_m: float = 0.0,
    sample_step_m: float = 4.0,
    mip_time_limit_s: float = 2.0,
) -> list[str]:
    """Resuelve flujos globales usando primero la capacidad de la BASE.

    Cada punto BASE conserva posición, óptica y modelo, pero puede regularse
    continuamente desde la corriente que satisface Interior hasta ``Imax``.
    Los refuerzos son variables semicontinuas (OFF o Imin..Imax). Para
    ``min_luminaires`` se penaliza ante todo encender refuerzos; para
    ``min_power`` se compara el consumo real de ambas alternativas.

    La aceptación final exige ``Lcalc >= Lreq``. ``design_margin`` no es una
    tolerancia de incumplimiento: crea una reserva positiva antes del mapeo a
    corrientes reales.
    """
    warnings_out: list[str] = []
    # La envolvente CIE 88 debe conservar todas las zonas geométricas, aunque
    # alguna no tenga luminarias propias. Las zonas activas solo determinan las
    # fuentes disponibles para satisfacer esa envolvente.
    requirement_zones = [
        zd for zd in zone_designs
        if float(zd.s_end) >= 0.0
        and float(zd.s_start) <= tube_length_m
        and _is_normative_requirement_zone(zd)
    ]
    active_zones = [
        zd for zd in zone_designs
        if zd.n_luminaires > 0 and (zd.setpoints or [])
        and float(zd.s_end) >= 0.0
        and float(zd.s_start) <= tube_length_m
    ]
    if not active_zones:
        return warnings_out

    # El cierre debe usar los mismos observadores y los tres puntos por carril
    # que la verificación CIE 140 final. El antiguo observador único centrado
    # podía aprobar la media de calzada y dejar corto el carril gobernante.
    if num_lanes is None:
        lane_specs = [{
            "index": 0,
            "observer_y": w / 2.0,
            "points_y": [(j + 0.5) * w / 5.0 for j in range(5)],
        }]
    else:
        n_lanes = max(1, int(num_lanes or 1))
        shoulder_left = max(0.0, float(shoulder_left_m or 0.0))
        shoulder_right = max(0.0, float(shoulder_right_m or 0.0))
        sidewalk_left = max(0.0, float(sidewalk_left_m or 0.0))
        sidewalk_right = max(0.0, float(sidewalk_right_m or 0.0))
        carriageway_width = max(0.1, float(w) - sidewalk_left - sidewalk_right)
        available_width = max(0.1, carriageway_width - shoulder_left - shoulder_right)
        lane_width = max(
            0.1,
            float(lane_width_m or available_width / n_lanes),
        )
        if n_lanes * lane_width > available_width + 1e-6:
            lane_width = available_width / n_lanes
        elif shoulder_left + shoulder_right <= 1e-9 and n_lanes * lane_width < carriageway_width:
            shoulder_left = (carriageway_width - n_lanes * lane_width) / 2.0
        lane_specs = [
            {
                "index": lane_index,
                "observer_y": sidewalk_left + shoulder_left + (lane_index + 0.5) * lane_width,
                "points_y": [
                    sidewalk_left + shoulder_left + lane_index * lane_width
                    + (point_index + 0.5) * lane_width / 3.0
                    for point_index in range(3)
                ],
            }
            for lane_index in range(n_lanes)
        ]
    lane_spec_by_index = {item["index"]: item for item in lane_specs}

    phot_cache = {}

    def _phot(optic_id):
        oid = optic_id or "F2MD"
        if oid not in phot_cache:
            filename = _OPTIC_LDT.get(oid, _OPTIC_LDT["F2MD"])
            phot_cache[oid] = load_ldt(_LDT_DIR / filename)
        return phot_cache[oid]

    ys_default = _default_y_positions(arrangement, w, wall_offset)

    def _ys_for_setpoint(sp):
        if arrangement in ("bilateral_stag", "staggered"):
            idx = int(sp.get("idx", 1) or 1)
            return [
                wall_offset if (idx - 1) % 2 == 0 else (w - wall_offset)
            ]
        return ys_default

    def _tilt_for_y(tilt_base, y_pos):
        return tilt_base if y_pos < w / 2.0 else -tilt_base

    groups = []
    for zd in active_zones:
        for i, sp in enumerate(zd.setpoints or []):
            optic_id = sp.get("optic") or zd.optic or "F2MD"
            tilt_base = float(sp.get("tilt_deg", zd.tilt_deg) or 0)
            unit_lums = [
                LuminaireInstance(
                    x=float(sp["s"]),
                    y=float(y_pos),
                    H=h,
                    photometry=_phot(optic_id),
                    flux_lm=_UNIT_FLUX_LM,
                    orientation=LuminaireOrientation(
                        tilt_deg=_tilt_for_y(tilt_base, y_pos),
                        mirror_c=mirror_c_for_interior_facing(
                            y_pos, w, arrangement,
                        ),
                    ),
                )
                for y_pos in _ys_for_setpoint(sp)
            ]
            groups.append({
                "zd": zd,
                "i": i,
                "sp": sp,
                "lums": unit_lums,
                "direction": -1.0 if str(zd.zone_type or "").endswith("_b") else 1.0,
            })
    if not groups:
        return warnings_out

    base_sample_meta = build_requirement_samples(
        requirement_zones,
        tube_length_m=tube_length_m,
        Lth=Lth,
        Lth_b=Lth_b,
        Lin=Lin,
        speed_kmh=speed_kmh,
        step_m=min(5.0, max(1.0, float(sample_step_m or 4.0))),
        include_luminaire_midpoints=False,
    )
    base_sample_meta = [
        meta for meta in base_sample_meta
        if str(
            getattr(meta["zone"], "control_layer", "legacy") or "legacy"
        ) != "permanent"
    ]
    # El perfil final CIE 140 gobierna por carril.  Un único observador en el
    # eje podía aceptar una solución que fallaba en uno de los carriles.
    sample_meta = [
        {**meta, "lane_index": lane_spec["index"]}
        for meta in base_sample_meta
        for lane_spec in lane_specs
    ]
    for meta in sample_meta:
        meta["zd"] = meta.pop("zone")
    if not sample_meta:
        return warnings_out

    from modules.tunnel.photometric_verify import _max_reach_for_h
    reach = _max_reach_for_h(h)
    calc = TunnelCalculator(rtable, mf, max_luminaire_dist=reach)
    observers = {
        (direction, lane_spec["index"]): Observer(
            lane_y_m=lane_spec["observer_y"],
            d_observer_m=60.0,
            direction=direction,
        )
        for direction in (1.0, -1.0)
        for lane_spec in lane_specs
    }

    n_samples = len(sample_meta)
    n_groups = len(groups)
    A = np.zeros((n_samples, n_groups), dtype=float)
    direction_lane_indices = {
        (direction, lane_spec["index"]): [
            i for i, meta in enumerate(sample_meta)
            if (
                meta["direction"] == direction
                and meta["lane_index"] == lane_spec["index"]
            )
        ]
        for direction in (1.0, -1.0)
        for lane_spec in lane_specs
    }

    all_lums = []
    group_starts = []
    for group in groups:
        group_starts.append(len(all_lums))
        all_lums.extend(group["lums"])
    group_starts = np.asarray(group_starts, dtype=int)

    # Una llamada vectorizada por combinación sentido/carril, empleando los
    # mismos tres puntos transversales de la verificación CIE 140.
    for (direction, lane_index), indices in direction_lane_indices.items():
        if not indices:
            continue
        ys_calc = lane_spec_by_index[lane_index]["points_y"]
        pts = [
            (sample_meta[i]["s"], y_pos)
            for i in indices for y_pos in ys_calc
        ]
        physical = calc.luminance_contributions_at_points_batch(
            pts, all_lums, observers[(direction, lane_index)],
        )
        grouped_points = (
            np.add.reduceat(
                physical.reshape(
                    len(indices), len(ys_calc), len(all_lums),
                ),
                group_starts,
                axis=2,
            )
            / _UNIT_FLUX_LM
        )
        means = grouped_points.mean(axis=1)
        A[indices, :] = means

    peak = float(np.max(A)) if A.size else 0.0
    if peak <= 0:
        warnings_out.append(
            "🔴 Matriz de influencia nula: no se pudieron resolver los flujos."
        )
        return warnings_out
    A[A < peak * 1e-7] = 0.0

    required = np.asarray(
        [meta["target"] for meta in sample_meta], dtype=float,
    )
    target = required * (1.0 + max(0.0, float(design_margin)))
    goal = str(optimization_goal or "min_luminaires").strip().lower()
    if goal not in {"min_luminaires", "min_power"}:
        goal = "min_luminaires"
    i_min_mA = max(1.0, float(I_min_pct) * 350.0)
    reinforcement_floor_flux, _ = flux_power_at_current(
        CHAIN_ORDER[0], cct, i_min_mA, I_min_pct,
    )
    reinforcement_max_flux, reinforcement_max_power = flux_power_at_current(
        CHAIN_ORDER[-1], cct, I_max_mA, I_min_pct,
    )
    phi_initial = np.asarray([
        max(
            0.0,
            float(
                group["sp"].get(
                    "target_flux_lm",
                    group["sp"].get("flux_lm", 0),
                ) or 0
            ),
        )
        for group in groups
    ], dtype=float)
    # El Interior ya ha sido optimizado sobre un vano tipo y validado en
    # calidad (U0/Ul/L). La fase global puede usar su contribucion, pero no
    # debe redimensionar su flujo ni su hardware por un deficit de otra zona.
    upper_fluxes = np.full(
        n_groups, float(reinforcement_max_flux), dtype=float,
    )
    floor_fractions = np.full(
        n_groups,
        min(
            1.0,
            float(reinforcement_floor_flux)
            / max(float(reinforcement_max_flux), 1e-9),
        ),
        dtype=float,
    )
    fixed_fractions = np.full(n_groups, np.nan, dtype=float)
    continuous_mask = np.zeros(n_groups, dtype=bool)
    power_costs = np.zeros(n_groups, dtype=float)
    for index, group in enumerate(groups):
        sp = group["sp"]
        zone = group["zd"]
        layer = str(
            getattr(zone, "control_layer", "legacy") or "legacy"
        )
        physical_units = max(1, len(group.get("lums", [])))
        if layer == "adaptation":
            # Capa exclusiva de crepúsculo: su contribución soleada es cero.
            upper_fluxes[index] = max(
                1.0, float(sp.get("flux_lm", 0.0) or 0.0),
            )
            floor_fractions[index] = 0.0
            fixed_fractions[index] = 0.0
            continue
        if layer == "exterior":
            exterior_flux = max(
                1.0, float(sp.get("flux_lm", phi_initial[index]) or 0.0),
            )
            upper_fluxes[index] = exterior_flux
            floor_fractions[index] = 1.0
            fixed_fractions[index] = 1.0
            continue
        if layer == "permanent":
            model = str(sp.get("model", zone.model) or zone.model)
            base_flux = max(
                1.0,
                float(
                    sp.get(
                        "base_flux_lm",
                        sp.get("flux_lm", phi_initial[index]),
                    )
                    or 0.0
                ),
            )
            model_max_flux, model_max_power = flux_power_at_current(
                model, cct, I_max_mA, I_min_pct,
            )
            upper_fluxes[index] = max(
                base_flux, float(model_max_flux),
            )
            floor_fractions[index] = min(
                1.0, base_flux / upper_fluxes[index],
            )
            continuous_mask[index] = (
                floor_fractions[index] < 1.0 - 1e-7
            )
            if not continuous_mask[index]:
                fixed_fractions[index] = 1.0
            if goal == "min_luminaires":
                power_costs[index] = (
                    max(float(model_max_power), 1.0)
                    * physical_units
                    * 1e-5
                )
            else:
                power_costs[index] = (
                    max(float(model_max_power), 1.0) * physical_units
                )
            continue
        power_costs[index] = (
            (
                1e6 * physical_units
                + max(float(reinforcement_max_power), 1.0) * physical_units
            )
            if goal == "min_luminaires"
            else max(float(reinforcement_max_power), 1.0) * physical_units
        )
    phi_initial = np.clip(phi_initial, 0.0, upper_fluxes)
    monotonic_blocks = _transition_blocks(groups)

    # La BASE forma una rampa de corriente monotónica desde Interior hacia
    # cada boca. En túneles cortos se divide por el punto medio para no imponer
    # dos sentidos opuestos sobre el mismo punto.
    a_end_candidates = [
        float(zone.s_end)
        for zone in requirement_zones
        if (
            any(
                token in str(zone.zone_type or "").lower()
                for token in ("threshold", "transition")
            )
            and not str(zone.zone_type or "").lower().endswith("_b")
        )
    ]
    b_start_candidates = [
        float(zone.s_start)
        for zone in requirement_zones
        if (
            any(
                token in str(zone.zone_type or "").lower()
                for token in ("threshold", "transition")
            )
            and str(zone.zone_type or "").lower().endswith("_b")
        )
    ]
    a_end = max(a_end_candidates) if a_end_candidates else None
    b_start = min(b_start_candidates) if b_start_candidates else None
    split_s = (
        (float(a_end) + float(b_start)) / 2.0
        if a_end is not None and b_start is not None else None
    )
    base_a: list[tuple[float, int]] = []
    base_b: list[tuple[float, int]] = []
    for index, group in enumerate(groups):
        if not continuous_mask[index]:
            continue
        layer = str(
            getattr(group["zd"], "control_layer", "legacy") or "legacy"
        )
        if layer != "permanent":
            continue
        position = float(group["sp"].get("s", 0.0) or 0.0)
        if (
            a_end is not None
            and position <= float(a_end) + 1e-7
            and (split_s is None or position <= split_s)
        ):
            base_a.append((float(a_end) - position, index))
        if (
            b_start is not None
            and position >= float(b_start) - 1e-7
            and (split_s is None or position >= split_s)
        ):
            base_b.append((position - float(b_start), index))
    if len(base_a) > 1:
        monotonic_blocks.append([
            index for _, index in sorted(base_a)
        ])
    if len(base_b) > 1:
        monotonic_blocks.append([
            index for _, index in sorted(base_b)
        ])

    # El salto normativo Umbral->Transicion no puede seguirse de forma
    # instantanea por el alcance longitudinal de las luminarias. Se mantiene
    # el requisito inferior, pero esa pequena franja no gobierna el minimax
    # del resto del tunel.
    upper_mask = np.ones(n_samples, dtype=bool)
    boundary_buffer = max(10.0, 3.0 * float(h))
    for direction in (1.0, -1.0):
        indices = [
            i for i, meta in enumerate(sample_meta)
            if meta["direction"] == direction
        ]
        indices.sort(key=lambda i: sample_meta[i]["s"])
        for previous, current in zip(indices, indices[1:]):
            req_previous = required[previous]
            req_current = required[current]
            high = max(req_previous, req_current)
            low = max(min(req_previous, req_current), 1e-9)
            if high / low <= 1.5:
                continue
            boundary = (
                sample_meta[previous]["s"] + sample_meta[current]["s"]
            ) / 2.0
            for index in indices:
                if abs(sample_meta[index]["s"] - boundary) <= boundary_buffer:
                    upper_mask[index] = False

    # El cierre estricto incluye los primeros/ultimos campos de umbral. Antes
    # se trataban como diagnostico y el solver podia rebajar su flujo despues
    # de que el cierre local ya hubiese eliminado el deficit.
    representative_mask = np.ones(n_samples, dtype=bool)
    if not enforce_portal_edges:
        portal_buffer = 5.0 * float(h)
        has_portal_a = any(
            "threshold" in str(zone.zone_type or "").lower()
            and not str(zone.zone_type or "").lower().endswith("_b")
            for zone in active_zones
        )
        has_portal_b = any(
            str(zone.zone_type or "").lower().endswith("_b")
            for zone in active_zones
        )
        for index, meta in enumerate(sample_meta):
            if (
                has_portal_a
                and meta["direction"] == 1.0
                and float(meta["s"]) < portal_buffer
            ):
                representative_mask[index] = False
            if (
                has_portal_b
                and meta["direction"] == -1.0
                and float(meta["s"]) > tube_length_m - portal_buffer
            ):
                representative_mask[index] = False

    # Prueba de capacidad con los límites reales de cada equipo. La BASE puede
    # subir hasta Imax sin cambiar modelo; el resto usa el máximo de la cadena
    # comercial permitida.
    capacity_phi = upper_fluxes.copy()
    fixed_mask = np.isfinite(fixed_fractions)
    capacity_phi[fixed_mask] = (
        fixed_fractions[fixed_mask] * upper_fluxes[fixed_mask]
    )
    maximum_available = A @ capacity_phi
    relaxed_target, capacity_limited = _relax_unreachable_targets(
        target,
        maximum_available,
    )
    # Si solo falta el margen de diseño, la exigencia normativa sigue siendo
    # alcanzable: no se debe forzar el campo a su capacidad maxima. Solo se
    # admite un objetivo inferior al normativo cuando ni siquiera ``required``
    # puede alcanzarse con toda la instalacion disponible.
    margin_only_limited = capacity_limited & (
        maximum_available >= required - 1e-7
    )
    relaxed_target[margin_only_limited] = required[margin_only_limited]
    normative_capacity_limited = capacity_limited & ~margin_only_limited
    # Si ni siquiera Lreq es alcanzable, imponer el maximo disponible aqui
    # propagaria ese maximo por los bloques monotónicos hacia el portal y
    # recrearía precisamente el sobredimensionamiento que estamos evitando.
    # El campo queda como diagnóstico de capacidad, no como cota inferior del
    # ajuste; los demás campos siguen gobernando la solución.
    relaxed_target[normative_capacity_limited] = 0.0
    representative_indices = np.flatnonzero(representative_mask)
    if not len(representative_indices):
        warnings_out.append(
            "Optimizacion global no aplicada: no existe un campo "
            "representativo fuera de los bordes de portal."
        )
        return warnings_out
    limited_representative = representative_indices[capacity_limited[
        representative_indices
    ]]
    if len(limited_representative):
        worst_capacity_idx = int(limited_representative[
            np.argmax(
                target[limited_representative]
                - maximum_available[limited_representative]
            )
        ])
        meta = sample_meta[worst_capacity_idx]
        if margin_only_limited[worst_capacity_idx]:
            capacity_label = "el margen de diseño"
            capacity_action = (
                "Ese campo se fija en la Lreq normativa; el resto mantiene "
                "la Lreq(s) completa."
            )
        else:
            capacity_label = "la Lreq normativa"
            capacity_action = (
                "Ese campo queda como diagnóstico de capacidad y no bloquea "
                "el ajuste del resto de la Lreq(s)."
            )
        warnings_out.append(
                f"Optimizacion global parcial: la geometria previa no cubre "
                f"{capacity_label} en s={meta['s']:.1f} m, "
                f"carril {int(meta['lane_index']) + 1} "
            f"(deficit de capacidad "
            f"{float(target[worst_capacity_idx] - maximum_available[worst_capacity_idx]):.3f} cd/m2). "
            f"{capacity_action}"
        )

    excluded_portal_samples = int(np.count_nonzero(~representative_mask))
    if excluded_portal_samples:
        warnings_out.append(
            f"CIE 140: {excluded_portal_samples} puntos dentro de 5H de "
            "los portales se muestran como diagnostico de borde, pero no "
            "gobiernan el campo tipico de optimizacion."
        )
        A = A[representative_mask]
        required = required[representative_mask]
        target = target[representative_mask]
        relaxed_target = relaxed_target[representative_mask]
        capacity_limited = capacity_limited[representative_mask]
        normative_capacity_limited = normative_capacity_limited[
            representative_mask
        ]
        upper_mask = upper_mask[representative_mask]
        sample_meta = [
            meta for index, meta in enumerate(sample_meta)
            if representative_mask[index]
        ]
        n_samples = len(sample_meta)

    # Si una zona completa solo contiene campos inalcanzables, no existe una
    # referencia representativa que permita reducir sus luminarias de forma
    # segura. En ese caso se conserva su flujo previo; de lo contrario, al
    # quedar todas sus cotas inferiores relajadas, el LP podría apagarla por
    # completo aunque siga siendo la única solución física disponible.
    supported_zone_ids = {
        id(meta["zd"])
        for meta, limited in zip(sample_meta, normative_capacity_limited)
        if not limited
    }
    protected_groups = np.asarray([
        (
            str(
                getattr(group["zd"], "control_layer", "legacy")
                or "legacy"
            ) != "permanent"
        )
        and (not fixed_mask[index])
        and id(group["zd"]) not in supported_zone_ids
        for index, group in enumerate(groups)
    ], dtype=bool)

    scaled_A = A * upper_fluxes[None, :]
    fractions, converged, solver_method, max_relative_excess = (
        _solve_semicontinuous_fluxes_minimax(
            scaled_A,
            required,
            relaxed_target,
            floor_fractions,
            fixed_fractions,
            monotonic_blocks=monotonic_blocks,
            upper_mask=upper_mask,
            continuous_mask=continuous_mask,
            cost_weights=power_costs,
            # El MIP mejora la economia del montaje, no sustituye la
            # verificaciÃ³n CIE 140 final. Una soluciÃ³n factible temprana es
            # vÃ¡lida y evita consumir decenas de segundos buscando el Ãºltimo
            # decimal de una soluciÃ³n entera para cada recÃ¡lculo.
            time_limit_s=min(8.0, max(2.0, float(mip_time_limit_s))),
        )
    )
    phi = np.clip(fractions, 0.0, 1.0) * upper_fluxes
    if not converged:
        warnings_out.append(
            "Optimizacion global no aplicada: el solver no encontro una "
            "solucion factible. Se conserva el diseno por zonas, incluido "
            "el Interior."
        )
        return warnings_out

    # Asignacion discreta en memoria: no se modifica ningun setpoint hasta
    # comprobar que el redondeo a hardware comercial mantiene deficit cero.
    selections: list[dict | None] = []
    actual_phi = np.zeros_like(phi)
    off_groups: list[dict] = []
    for col, group in enumerate(groups):
        if fixed_mask[col]:
            selections.append(None)
            actual_phi[col] = (
                float(fixed_fractions[col]) * float(upper_fluxes[col])
            )
            continue
        if protected_groups[col]:
            selections.append(None)
            actual_phi[col] = float(
                group["sp"].get("flux_lm", phi_initial[col]) or 0.0
            )
            continue
        if float(phi[col]) <= 1e-6:
            selections.append({"off": True})
            actual_phi[col] = 0.0
            off_groups.append(group)
            continue
        layer = str(
            getattr(group["zd"], "control_layer", "legacy") or "legacy"
        )
        if layer == "permanent":
            selected = _fixed_model_selection_for_flux(
                str(
                    group["sp"].get("model", group["zd"].model)
                    or group["zd"].model
                ),
                float(phi[col]),
                cct=cct,
                I_max_mA=I_max_mA,
                I_min_pct=I_min_pct,
            )
        else:
            selected = select_model_for_flux(
                float(phi[col]), cct, I_max_mA, I_min_pct,
            )
        selections.append(selected)
        actual_phi[col] = float(selected["lm"])

    calculated_actual = A @ actual_phi
    actual_deficit = required - calculated_actual
    # Se conserva para el mensaje diagnostico final; los deficits de campos
    # marcados como capacity_limited no provocan fallback al diseno uniforme.
    worst_actual = float(np.max(actual_deficit))
    worst_idx = int(np.argmax(actual_deficit))
    strict_mask = ~normative_capacity_limited
    strict_worst = float(
        np.max(actual_deficit[strict_mask])
        if np.any(strict_mask) else -np.inf
    )
    strict_worst_idx = int(
        np.flatnonzero(strict_mask)[np.argmax(actual_deficit[strict_mask])]
        if np.any(strict_mask) else np.argmax(actual_deficit)
    )
    if strict_worst > 1e-9:
        meta = sample_meta[strict_worst_idx]
        warnings_out.append(
            f"Optimizacion global no aplicada: el redondeo comercial deja "
            f"un deficit de {strict_worst:.6f} cd/m2 en "
            f"s={meta['s']:.1f} m, carril {int(meta['lane_index']) + 1}. "
            "Se conserva el diseno por zonas."
        )
        return warnings_out

    capacity_residual = actual_deficit[normative_capacity_limited]
    if len(capacity_residual) and float(np.max(capacity_residual)) > 1e-9:
        residual_idx = int(np.flatnonzero(normative_capacity_limited)[
            np.argmax(capacity_residual)
        ])
        meta = sample_meta[residual_idx]
        warnings_out.append(
            f"Optimizacion global: deficit residual inevitable de "
            f"{float(actual_deficit[residual_idx]):.3f} cd/m2 en "
            f"s={meta['s']:.1f} m, carril {int(meta['lane_index']) + 1}; "
            "se optimizan sin deficit los demas "
            "campos representativos."
        )

    # La condicion se ha comprobado con actual_phi, que ya incluye ceros para
    # los refuerzos retirados y los flujos comerciales de los restantes.
    # Eliminarlos fisicamente conserva coherencia entre la curva soleada,
    # totales CAPEX y las posteriores escenas DALI: si no hacen falta en la
    # condicion de maxima exigencia, tampoco son capacidad necesaria.
    for group in off_groups:
        try:
            group["zd"].setpoints.remove(group["sp"])
        except ValueError:
            pass
    if off_groups:
        warnings_out.append(
            f"Optimizacion global: retiradas {len(off_groups)} luminarias "
            "de refuerzo redundantes tras validar deficit cero."
        )

    for col, group in enumerate(groups):
        selected = selections[col]
        if selected is None or selected.get("off"):
            continue
        sp = group["sp"]
        sp["target_flux_lm"] = round(float(phi[col]), 3)
        sp["model"] = selected["model"]
        sp["current_mA"] = selected["mA"]
        sp["power_w"] = selected["W"]
        sp["flux_lm"] = selected["lm"]
        layer = str(
            getattr(group["zd"], "control_layer", "legacy") or "legacy"
        )
        if layer == "permanent":
            base_flux = float(
                sp.get("base_flux_lm", selected["lm"]) or selected["lm"]
            )
            sp["day_flux_lm"] = selected["lm"]
            sp["base_boosted"] = bool(
                float(selected["lm"]) > base_flux * 1.001
            )
            sp["base_boost_delta_lm"] = round(
                max(0.0, float(selected["lm"]) - base_flux), 3,
            )

    boosted_base = [
        group for group in groups
        if (
            str(
                getattr(group["zd"], "control_layer", "legacy")
                or "legacy"
            ) == "permanent"
            and bool(group["sp"].get("base_boosted", False))
        )
    ]
    if boosted_base:
        boosted_physical = sum(
            max(1, len(group.get("lums", []))) for group in boosted_base
        )
        boosted_currents = [
            float(group["sp"].get("current_mA", 0.0) or 0.0)
            for group in boosted_base
        ]
        warnings_out.append(
            "Rampa BASE aplicada antes del refuerzo: "
            f"{len(boosted_base)} posiciones "
            f"({boosted_physical} luminarias físicas) reguladas entre "
            f"{min(boosted_currents):.0f} y {max(boosted_currents):.0f} mA."
        )

    for group in groups:
        # La BASE permanente se cierra previamente con su perfil CIE 140
        # propio. Este solver no tiene muestras de BASE (optimiza solo el
        # residual de umbrales/transiciones), por lo que asignarle la muestra
        # residual mas cercana convertiría su L_est en una luminancia ajena.
        if str(
            getattr(group["zd"], "control_layer", "legacy") or "legacy"
        ) == "permanent":
            continue
        s_pos = float(group["sp"]["s"])
        nearest = min(
            range(n_samples),
            key=lambda j: abs(sample_meta[j]["s"] - s_pos),
        )
        group["sp"]["L_est"] = round(float(calculated_actual[nearest]), 3)

    profile_by_zone: dict[int, dict[str, list[float]]] = {}
    for meta, value in zip(sample_meta, calculated_actual):
        bucket = profile_by_zone.setdefault(
            id(meta["zd"]), {"values": [], "ratios": []},
        )
        bucket["values"].append(float(value))
        bucket["ratios"].append(
            float(value) / max(float(meta["target"]), 1e-9)
        )

    for zd in active_zones:
        setpoints = zd.setpoints or []
        if not setpoints:
            continue
        zd.n_luminaires = len(setpoints)
        zd.power_zone_w = round(
            sum(float(sp.get("power_w", 0) or 0) for sp in setpoints), 1,
        )
        zd.flux_zone_lm = round(
            sum(float(sp.get("flux_lm", 0) or 0) for sp in setpoints), 0,
        )
        zd.power_density_wm2 = round(
            zd.power_zone_w / max(float(zd.zone_length) * w, 1e-9), 3,
        )
        dominant = max(
            setpoints, key=lambda sp: float(sp.get("L_req", 0) or 0),
        )
        zd.model = dominant.get("model", zd.model)
        zd.current_mA = round(float(dominant.get("current_mA", 0) or 0))
        zd.power_w = round(float(dominant.get("power_w", 0) or 0), 1)
        zd.flux_lm = round(float(dominant.get("flux_lm", 0) or 0), 0)

        # Conservar L_estimated/profile_* obtenidos por el cierre CIE 140 de
        # la BASE, en vez de promediar muestras que deliberadamente excluyen
        # dicha capa permanente.
        if str(
            getattr(zd, "control_layer", "legacy") or "legacy"
        ) == "permanent":
            continue
        zd.L_estimated = round(
            sum(float(sp.get("L_est", 0) or 0) for sp in setpoints)
            / len(setpoints),
            3,
        )
        profile_stats = profile_by_zone.get(id(zd))
        if profile_stats and profile_stats["values"]:
            zd.profile_L_avg = round(
                float(np.mean(profile_stats["values"])), 3,
            )
            zd.profile_L_min = round(
                float(np.min(profile_stats["values"])), 3,
            )
            zd.profile_min_ratio = round(
                float(np.min(profile_stats["ratios"])), 4,
            )
            zd.profile_median_ratio = round(
                float(np.median(profile_stats["ratios"])), 4,
            )
            zd.profile_p95_ratio = round(
                float(np.percentile(profile_stats["ratios"], 95)), 4,
            )
            zd.profile_max_ratio = round(
                float(np.max(profile_stats["ratios"])), 4,
            )

    if not converged:
        meta = sample_meta[worst_idx]
        warnings_out.append(
            f"🔴 Flujo global infactible en s={meta['s']:.1f} m: "
            f"faltan {max(0.0, worst_actual):.3f} cd/m2 incluso con "
            "las luminarias disponibles al maximo."
        )
    elif worst_actual > 1e-9:
        meta = sample_meta[worst_idx]
        warnings_out.append(
            f"🔴 Deficit residual en s={meta['s']:.1f} m: "
            f"{worst_actual:.6f} cd/m2."
        )
    else:
        min_ratio = float(np.min(
            calculated_actual / np.maximum(required, 1e-9)
        ))
        max_ratio = float(np.max(
            calculated_actual / np.maximum(required, 1e-9)
        ))
        densification_text = ""
        warnings_out.append(
            f"Optimizacion global {solver_method} convergida{densification_text}: "
            f"deficit 0 en {n_samples} puntos, "
            f"ratio Lcalc/Lreq={min_ratio:.4f}..{max_ratio:.4f}, "
            f"exceso minimax fuera de fronteras="
            f"{max_relative_excess * 100.0:.2f}%."
        )
    return warnings_out
