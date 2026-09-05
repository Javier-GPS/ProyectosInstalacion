import numpy as np
import pytest
from types import SimpleNamespace

from modules.tunnel.influence_optimizer import (
    _fixed_model_selection_for_flux,
    _is_normative_requirement_zone,
    _relax_unreachable_targets,
    _solve_fluxes_minimax,
    _solve_semicontinuous_fluxes_minimax,
)


def test_physical_adaptation_layer_is_not_a_normative_zone():
    transition = SimpleNamespace(
        zone_type="transition",
        control_layer="reinforcement",
    )
    adaptation = SimpleNamespace(
        zone_type="adaptation_a",
        control_layer="adaptation",
    )
    assert _is_normative_requirement_zone(transition)
    assert not _is_normative_requirement_zone(adaptation)


def test_minimax_solver_finds_zero_excess_solution():
    A = np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [0.5, 0.5],
    ])
    required = np.ones(3)
    phi, feasible, method, excess = _solve_fluxes_minimax(
        A,
        required,
        required,
        min_flux=0.0,
        max_flux=2.0,
        monotonic_blocks=[],
        constant_blocks=[],
        upper_mask=None,
        phi_initial=np.zeros(2),
        max_iters=100,
    )
    assert feasible
    assert method.startswith("highs")
    assert np.allclose(phi, [1.0, 1.0], atol=1e-7)
    assert excess <= 1e-7


def test_minimax_solver_respects_transition_monotonicity():
    A = np.eye(2)
    required = np.array([0.5, 1.0])
    phi, feasible, _, _ = _solve_fluxes_minimax(
        A,
        required,
        required,
        min_flux=0.0,
        max_flux=2.0,
        monotonic_blocks=[[0, 1]],
        constant_blocks=[],
        upper_mask=None,
        phi_initial=np.zeros(2),
        max_iters=100,
    )
    assert feasible
    assert phi[1] >= phi[0] - 1e-9
    assert np.all(A @ phi >= required - 1e-8)


def test_minimax_solver_keeps_validated_interior_flux_fixed():
    A = np.eye(2)
    required = np.array([0.5, 1.0])
    fixed_fluxes = np.array([0.75, np.nan])
    phi, feasible, _, _ = _solve_fluxes_minimax(
        A,
        required,
        required,
        min_flux=0.0,
        max_flux=2.0,
        monotonic_blocks=[],
        constant_blocks=[],
        upper_mask=None,
        phi_initial=np.array([0.75, 0.0]),
        max_iters=100,
        fixed_fluxes=fixed_fluxes,
    )
    assert feasible
    assert phi[0] == pytest.approx(0.75)
    assert phi[1] == pytest.approx(1.0)


def test_infeasible_solver_preserves_initial_flux_instead_of_using_maximum():
    A = np.zeros((1, 2))
    required = np.ones(1)
    initial = np.array([0.25, 0.40])
    phi, feasible, _, _ = _solve_fluxes_minimax(
        A,
        required,
        required,
        min_flux=0.0,
        max_flux=2.0,
        monotonic_blocks=[],
        constant_blocks=[],
        upper_mask=None,
        phi_initial=initial,
        max_iters=10,
    )
    assert not feasible
    assert np.allclose(phi, initial)


def test_unreachable_field_is_relaxed_without_relaxing_other_fields():
    relaxed, limited = _relax_unreachable_targets(
        np.array([1.0, 1.0, 0.5]),
        np.array([1.0, 0.4, 0.5]),
    )
    assert np.allclose(relaxed, [1.0, 0.4, 0.5])
    assert limited.tolist() == [False, True, False]


def test_semicontinuous_solver_respects_driver_floor_or_off():
    A = np.array([[1.0, 1.0]])
    required = np.array([0.5])
    fractions, feasible, method, _ = (
        _solve_semicontinuous_fluxes_minimax(
            A,
            required,
            required,
            floor_fractions=np.array([0.6, 0.6]),
            fixed_fractions=np.array([np.nan, np.nan]),
            time_limit_s=2.0,
        )
    )
    assert feasible
    assert method.startswith("highspy-mip")
    assert float((A @ fractions)[0]) >= 0.5 - 1e-7
    assert all(
        value <= 1e-7 or value >= 0.6 - 1e-7
        for value in fractions
    )


def test_semicontinuous_solver_switches_off_redundant_floor_driver():
    A = np.array([[1.0, 1.0]])
    fractions, feasible, method, _ = _solve_semicontinuous_fluxes_minimax(
        A,
        np.array([0.7]),
        np.array([0.7]),
        floor_fractions=np.array([0.6, 0.6]),
        fixed_fractions=np.array([np.nan, np.nan]),
        time_limit_s=2.0,
    )
    assert feasible
    assert method.startswith("highspy-mip")
    assert float((A @ fractions)[0]) >= 0.7 - 1e-7
    assert sum(value <= 1e-7 for value in fractions) == 1


def test_continuous_base_is_boosted_before_expensive_reinforcement():
    """Menor número usa primero la capacidad regulable de la BASE."""
    A = np.array([[1.0, 1.0]])
    fractions, feasible, _, _ = _solve_semicontinuous_fluxes_minimax(
        A,
        np.array([0.8]),
        np.array([0.8]),
        floor_fractions=np.array([0.3, 0.5]),
        fixed_fractions=np.array([np.nan, np.nan]),
        continuous_mask=np.array([True, False]),
        cost_weights=np.array([1e-5, 1e6]),
        time_limit_s=2.0,
    )
    assert feasible
    assert fractions[0] == pytest.approx(0.8, abs=1e-6)
    assert fractions[1] <= 1e-7


def test_minimum_power_can_keep_base_at_floor_and_use_cheaper_reinforcement():
    """El objetivo energético compara consumos en vez de contar equipos."""
    A = np.array([[1.0, 1.0]])
    fractions, feasible, _, _ = _solve_semicontinuous_fluxes_minimax(
        A,
        np.array([0.8]),
        np.array([0.8]),
        floor_fractions=np.array([0.3, 0.5]),
        fixed_fractions=np.array([np.nan, np.nan]),
        continuous_mask=np.array([True, False]),
        cost_weights=np.array([100.0, 1.0]),
        time_limit_s=2.0,
    )
    assert feasible
    assert fractions[0] == pytest.approx(0.3, abs=1e-6)
    assert fractions[1] == pytest.approx(0.5, abs=1e-6)


def test_semicontinuous_solver_enforces_linear_uniformity_rows():
    A = np.array([[1.0, 1.0]])
    # x0 no puede superar x1 / 0.60.
    quality_rows = np.array([[0.60, -1.0]])
    fractions, feasible, _, _ = _solve_semicontinuous_fluxes_minimax(
        A,
        np.array([1.0]),
        np.array([1.0]),
        floor_fractions=np.array([0.2, 0.2]),
        fixed_fractions=np.array([np.nan, np.nan]),
        quality_rows=quality_rows,
        continuous_mask=np.array([True, True]),
        cost_weights=np.array([1.0, 100.0]),
        time_limit_s=2.0,
    )
    assert feasible
    assert 0.60 * fractions[0] <= fractions[1] + 1e-7
    assert float((A @ fractions)[0]) >= 1.0 - 1e-7


def test_base_flux_mapping_never_changes_installed_model():
    selected = _fixed_model_selection_for_flux(
        "APHEX_S_100W",
        15000.0,
        cct="3000K",
        I_max_mA=750.0,
        I_min_pct=0.30,
    )
    assert selected["model"] == "APHEX_S_100W"
    assert 105.0 <= selected["mA"] <= 750.0
    assert selected["lm"] >= 15000.0
