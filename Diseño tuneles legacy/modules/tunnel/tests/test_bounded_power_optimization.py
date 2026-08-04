from types import SimpleNamespace

import pytest

from modules.tunnel import luminaires
from modules.tunnel.luminaires import (
    TunnelLuminaireResult,
    _bounded_power_base_spacing,
    _select_bounded_power_result,
    calculate_luminaire_layout,
    calculate_quality_sensitivity,
)


def _result(n_luminaires, power_kw, base_spacing_m):
    zone = SimpleNamespace(
        n_luminaires=n_luminaires,
        power_zone_w=power_kw * 1000.0,
        flux_zone_lm=0.0,
        control_layer="permanent",
        d_used=base_spacing_m,
    )
    return TunnelLuminaireResult(
        tube_id="T1",
        luminaire=None,
        road_surface_type="R3",
        rho_eff=0.07,
        road_width_m=10.0,
        tube_length_m=1000.0,
        arrangement="central_single",
        zones=[zone],
        performance={"base_spacing_m": base_spacing_m},
    )


def test_bounded_spacing_uses_stricter_user_limit():
    assert _bounded_power_base_spacing(25.0, 15.0, 20.0, 0.5) == 22.0
    assert _bounded_power_base_spacing(25.0, 50.0, 10.0, 0.5) == 22.5
    assert _bounded_power_base_spacing(25.0, 0.0, 95.0, 0.5) == 25.0


def test_lower_power_candidate_is_accepted_within_luminaire_limit():
    reference = _result(100, 25.0, 25.0)
    candidate = _result(112, 23.0, 22.0)

    selected = _select_bounded_power_result(
        reference,
        candidate,
        max_luminaire_increase_pct=15.0,
        max_base_spacing_reduction_pct=20.0,
        min_base_spacing_m=22.0,
    )

    assert selected is candidate
    comparison = selected.optimization_comparison
    assert comparison["decision"]["accepted"] is True
    assert comparison["limits"]["max_luminaires"] == 115
    assert comparison["selected_power_saving_kw"] == pytest.approx(2.0)
    assert comparison["candidate"]["luminaire_increase_pct"] == 12.0


def test_candidate_over_total_count_limit_keeps_reference():
    reference = _result(100, 25.0, 25.0)
    candidate = _result(116, 22.0, 22.0)

    selected = _select_bounded_power_result(
        reference,
        candidate,
        max_luminaire_increase_pct=15.0,
        max_base_spacing_reduction_pct=20.0,
        min_base_spacing_m=22.0,
    )

    assert selected is reference
    comparison = selected.optimization_comparison
    assert comparison["decision"]["reason"] == "luminaire_limit"
    assert comparison["selected_power_saving_kw"] == 0.0
    assert "superan el limite de 115" in selected.warnings[-1]


def test_calculate_builds_reference_then_bounded_candidate(monkeypatch):
    calls = []

    def fake_design(*, zones_list, params, road_width_m, tube_length_m, tube_id):
        calls.append(dict(params))
        if params["optimization_goal"] == "min_luminaires":
            return _result(100, 25.0, 25.0)
        return _result(112, 23.0, params["_power_base_d_min_m"])

    monkeypatch.setattr(
        luminaires, "design_aphex_tunnel_optimized", fake_design,
    )
    selected = calculate_luminaire_layout(
        zones_list=[],
        luminaire_params={
            "I_max_mA": 750,
            "optimization_goal": "min_power",
            "max_luminaire_increase_pct": 15,
            "max_base_spacing_reduction_pct": 20,
            "spacing_quantum_m": 0.5,
        },
        road_width_m=10.0,
        tube_length_m=1000.0,
    )

    assert len(calls) == 2
    assert calls[0]["optimization_goal"] == "min_luminaires"
    assert calls[1]["optimization_goal"] == "min_power"
    assert calls[1]["_power_base_d_min_m"] == 22.0
    assert selected.optimization_comparison["decision"]["accepted"] is True


def _scene_result(
    base_spacing_m,
    *,
    shortfall=False,
    shortfall_reason="infeasible",
    with_adaptation=False,
):
    zone = SimpleNamespace(
        n_luminaires=10,
        power_zone_w=1000.0,
        flux_zone_lm=20000.0,
        control_layer="permanent",
        d_used=base_spacing_m,
        setpoints=[{"model": "APHEX_S_75W"}],
    )
    zones = [zone]
    if with_adaptation:
        zones.append(SimpleNamespace(
            n_luminaires=4,
            power_zone_w=200.0,
            flux_zone_lm=4000.0,
            control_layer="adaptation",
            d_used=8.0,
            setpoints=[{"model": "APHEX_S_75W"}],
        ))
    diagnostic = (
        {
            "dusk": {
                "reason": shortfall_reason,
                "infeasibility_type": "no_semicontinuous_pattern",
            },
        }
        if shortfall else {}
    )
    return TunnelLuminaireResult(
        tube_id="T1",
        luminaire=None,
        road_surface_type="R3",
        rho_eff=0.07,
        road_width_m=10.0,
        tube_length_m=100.0,
        arrangement="central_single",
        zones=zones,
        scenarios={"global_control_optimization": {"scenes": diagnostic}},
        performance={"base_spacing_m": base_spacing_m},
    )


def test_scene_reoptimization_redesigns_positions_only_after_current_fails(monkeypatch):
    baseline = _scene_result(10.0, shortfall=True)
    candidate = _scene_result(7.0, shortfall=False)
    calls = []

    def fake_design(*, zones_list, params, road_width_m, tube_length_m, tube_id):
        calls.append(params["d_fixed"])
        return candidate

    monkeypatch.setattr(luminaires, "design_aphex_tunnel_optimized", fake_design)
    selected = luminaires._reoptimize_physical_layout_for_scenes(
        baseline,
        zones_list=[],
        params={
            "calculation_phase": "full",
            "auto_physical_reoptimization": True,
            "d_min": 1.0,
            "spacing_quantum_m": 0.5,
            "scene_reoptimization_max_spacing_reduction_pct": 35,
            "scene_reoptimization_max_attempts": 3,
        },
        road_width_m=10.0,
        tube_length_m=100.0,
        tube_id="T1",
    )

    metadata = selected.performance["scene_physical_reoptimization"]
    assert selected is candidate
    assert calls == [8.5]
    assert metadata["status"] == "applied"
    assert metadata["reference"]["base_spacing_m"] == 10.0
    assert metadata["selected"]["base_spacing_m"] == 7.0


def test_scene_reoptimization_preserves_manual_layout(monkeypatch):
    baseline = _scene_result(10.0, shortfall=True)

    def unexpected_design(**_kwargs):
        raise AssertionError("A manually locked layout must not be redesigned")

    monkeypatch.setattr(luminaires, "design_aphex_tunnel_optimized", unexpected_design)
    selected = luminaires._reoptimize_physical_layout_for_scenes(
        baseline,
        zones_list=[],
        params={
            "calculation_phase": "full",
            "auto_physical_reoptimization": True,
            "_physical_layout_locked": True,
        },
        road_width_m=10.0,
        tube_length_m=100.0,
        tube_id="T1",
    )

    assert selected is baseline
    assert selected.performance["scene_physical_reoptimization"]["status"] == "locked_manual"


def test_dusk_verification_deficit_redesigns_only_adaptation_layer(monkeypatch):
    baseline = _scene_result(
        10.0,
        shortfall=True,
        shortfall_reason="verification_deficit",
        with_adaptation=True,
    )
    candidate = _scene_result(10.0, shortfall=False, with_adaptation=True)
    calls = []

    def fake_design(*, zones_list, params, road_width_m, tube_length_m, tube_id):
        calls.append(dict(params))
        return candidate

    monkeypatch.setattr(luminaires, "design_aphex_tunnel_optimized", fake_design)
    selected = luminaires._reoptimize_physical_layout_for_scenes(
        baseline,
        zones_list=[],
        params={
            "calculation_phase": "full",
            "auto_physical_reoptimization": True,
            "d_min": 1.0,
            "spacing_quantum_m": 0.5,
            "scene_reoptimization_max_spacing_reduction_pct": 35,
            "scene_reoptimization_max_attempts": 3,
        },
        road_width_m=10.0,
        tube_length_m=100.0,
        tube_id="T1",
    )

    metadata = selected.performance["scene_physical_reoptimization"]
    assert selected is candidate
    assert calls[0]["_scene_reoptimization_adaptation_spacing_m"] == 7.0
    assert "d_fixed" not in calls[0]
    assert metadata["selected_scope"] == "adaptation"
    assert metadata["attempts"][0]["scope"] == "adaptation"


def test_dusk_targeted_failure_reserves_a_global_layout_retry(monkeypatch):
    baseline = _scene_result(
        10.0,
        shortfall=True,
        shortfall_reason="verification_deficit",
        with_adaptation=True,
    )
    successful_global = _scene_result(8.0, shortfall=False)
    calls = []

    def fake_design(*, zones_list, params, road_width_m, tube_length_m, tube_id):
        calls.append(dict(params))
        if "_scene_reoptimization_adaptation_spacing_m" in params:
            return baseline
        return successful_global

    monkeypatch.setattr(luminaires, "design_aphex_tunnel_optimized", fake_design)
    selected = luminaires._reoptimize_physical_layout_for_scenes(
        baseline,
        zones_list=[],
        params={
            "calculation_phase": "full",
            "auto_physical_reoptimization": True,
            "d_min": 1.0,
            "spacing_quantum_m": 0.5,
            "scene_reoptimization_max_spacing_reduction_pct": 35,
            "scene_reoptimization_max_attempts": 3,
        },
        road_width_m=10.0,
        tube_length_m=100.0,
        tube_id="T1",
    )

    metadata = selected.performance["scene_physical_reoptimization"]
    assert selected is successful_global
    assert len(calls) == 3
    assert all(
        "_scene_reoptimization_adaptation_spacing_m" in call
        for call in calls[:2]
    )
    assert calls[-1]["d_fixed"] == 8.5
    assert metadata["selected_scope"] == "global"
    assert [attempt["scope"] for attempt in metadata["attempts"]] == [
        "adaptation", "adaptation", "global",
    ]


def test_scene_reoptimization_default_reaches_installable_dense_floor():
    """A severe Ul deficit must not stop a half-metre above its floor."""
    candidates = luminaires._scene_reoptimization_spacings(
        24.0,
        {"d_min": 1.0, "spacing_quantum_m": 0.5},
    )

    assert candidates[-1] == 13.0


def test_quality_sensitivity_builds_u0_columns_and_ul_rows(monkeypatch):
    calls = []

    def fake_calculate(
        zones_list, luminaire_params, road_width_m, tube_length_m, tube_id,
    ):
        u0 = luminaire_params["U0_obj"]
        ul = luminaire_params["Ul_obj"]
        calls.append((u0, ul, luminaire_params["calculation_phase"]))
        return _result(
            int(round(100 + u0 * 10 + ul * 20)),
            20.0 + u0 + ul,
            25.0 - u0,
        )

    monkeypatch.setattr(
        luminaires, "calculate_luminaire_layout", fake_calculate,
    )
    matrix = calculate_quality_sensitivity(
        zones_list=[],
        luminaire_params={"optimization_goal": "min_luminaires"},
        road_width_m=10.0,
        tube_length_m=1000.0,
        tube_id="T1",
        u0_values=[0.4, 0.5, 0.6],
        ul_values=[0.6, 0.7, 0.8],
        max_workers=1,
    )

    assert matrix["u0_values"] == [0.4, 0.5, 0.6]
    assert matrix["ul_values"] == [0.6, 0.7, 0.8]
    assert matrix["n_combinations"] == 9
    assert matrix["n_successful"] == 9
    assert matrix["rows"][0]["Ul"] == 0.6
    assert matrix["rows"][0]["cells"][1]["U0"] == 0.5
    assert matrix["rows"][0]["cells"][1]["power_kw"] == pytest.approx(21.1)
    assert matrix["rows"][2]["cells"][2]["n_luminaires"] == 122
    assert all(phase == "base" for _u0, _ul, phase in calls)


def test_quality_sensitivity_active_cell_matches_current_layout():
    matrix = calculate_quality_sensitivity(
        zones_list=[],
        luminaire_params={
            "U0_obj": 0.40,
            "Ul_obj": 0.60,
            "optimization_goal": "min_luminaires",
        },
        road_width_m=10.0,
        tube_length_m=1000.0,
        tube_id="T1",
        u0_values=[0.40],
        ul_values=[0.60],
        reference_layout={
            "totals": {
                "n_luminaires": 152,
                "n_positions": 152,
                "power_kw": 26.35,
            },
            "zones": [{
                "control_layer": "permanent",
                "d_used": 8.5,
            }],
        },
        max_workers=1,
    )

    cell = matrix["rows"][0]["cells"][0]
    assert cell["n_luminaires"] == 152
    assert cell["power_kw"] == pytest.approx(26.35)
    assert cell["optimization_decision"] == "current_layout_reference"
    assert cell["approximate"] is False
