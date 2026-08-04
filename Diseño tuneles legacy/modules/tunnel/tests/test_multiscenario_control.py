import math

from modules.tunnel.classification import classify_tunnel
from modules.tunnel.control import (
    build_control_plan,
    dali_to_dimming,
    dimming_to_dali,
)
from modules.tunnel.models import TrafficDirection
from modules.tunnel.luminaires import (
    TunnelLuminaireResult,
    ZoneLuminaireDesign,
    _apply_solar_daylight_contribution,
    _attach_layered_scene_operating_points,
    _resolve_constructive_position_conflicts,
    apply_scene_current_overrides,
)
from modules.tunnel.zones import build_zones


def _zones(direction=TrafficDirection.ONE_WAY):
    classification = classify_tunnel(
        length_m=1200,
        stopping_distance_m=100,
        exit_visible=False,
        daylight_penetration="poor",
        traffic_veh_h=800,
        has_pedestrians=False,
        speed_kmh=80,
        wall_reflectance=0.4,
    )
    return build_zones(
        tube_length=1200,
        stopping_distance_m=100,
        speed_kmh=80,
        Lth=180,
        Lin=3,
        classification=classification,
        traffic_direction=direction,
        L_night=1,
        Lth_b=120,
        stopping_distance_b_m=100,
    )


def test_dali_standard_end_points_and_round_trip():
    assert dimming_to_dali(0) == 0
    assert dimming_to_dali(0.1) == 1
    assert dimming_to_dali(100) == 254
    assert dali_to_dimming(1) == 0.1
    assert dali_to_dimming(254) == 100.0
    for pct in (0.3, 1.0, 10.0, 50.0):
        recovered = dali_to_dimming(dimming_to_dali(pct))
        assert math.isclose(recovered, pct, rel_tol=0.035)


def test_night_keeps_only_permanent_base_on():
    plan = build_control_plan(
        tube_id="T1",
        L20_design=4500,
        Lth_design=180,
        Lin=3,
        L_night=1,
        k_factor=0.04,
        speed_kmh=80,
        zones=_zones(),
    )
    base = next(group for group in plan.groups if group.layer == "permanent")
    reinforcements = [
        group for group in plan.groups if group.layer == "reinforcement"
    ]
    assert base.dimming_levels[5] == 33.333
    assert base.off_allowed is False
    assert reinforcements
    assert all(group.dimming_levels[5] == 0 for group in reinforcements)
    assert all(group.dali_levels[5] == 0 for group in reinforcements)


def test_bidirectional_tunnel_has_independent_portal_reinforcement():
    plan = build_control_plan(
        tube_id="T1",
        L20_design=4500,
        Lth_design=180,
        Lin=3,
        L_night=1,
        k_factor=0.04,
        speed_kmh=80,
        zones=_zones(TrafficDirection.TWO_WAY),
        L20_design_b=3000,
        Lth_design_b=120,
        k_factor_b=0.04,
    )
    portals = {
        group.portal
        for group in plan.groups
        if group.layer == "reinforcement"
    }
    assert portals == {"A", "B"}
    assert plan.strategy["independent_portals"] is True


def test_solar_daylight_is_not_a_dali_or_luminaire_group():
    plan = build_control_plan(
        tube_id="T1",
        L20_design=4500,
        Lth_design=180,
        Lin=3,
        L_night=1,
        k_factor=0.04,
        speed_kmh=80,
        zones=_zones(TrafficDirection.TWO_WAY),
        L20_design_b=3000,
        Lth_design_b=120,
        k_factor_b=0.04,
        exterior_enabled=True,
        exterior_mouth_contribution_pct=12,
    )

    assert not [group for group in plan.groups if group.layer == "exterior"]
    assert not [
        curve for curve in plan.regulation_curves
        if curve.group_name.startswith("EXT-")
    ]
    assert any("no constituye un grupo DALI" in item for item in plan.warnings)
    threshold_a = next(
        group for group in plan.groups
        if group.name.startswith("REF-A-TH")
    )
    assert threshold_a.dimming_levels[1] == 100.0
    assert threshold_a.dimming_levels[2] < 70.0
    assert threshold_a.dimming_levels[3] < 30.0
    assert threshold_a.dimming_levels[4] < 5.0
    assert threshold_a.dimming_levels[5] == 0.0


def test_solar_daylight_reduces_artificial_requirement_without_new_luminaires(
    monkeypatch,
):
    from modules.tunnel import optimizer

    def fake_selection(*_args, **_kwargs):
        return {
            "model": "APHEX_S_75W",
            "mA": 350.0,
            "W": 50.0,
            "lm": 10000.0,
        }

    monkeypatch.setattr(optimizer, "select_model_for_flux", fake_selection)
    zone = ZoneLuminaireDesign(
        zone_type="threshold",
        zone_name="CTH",
        s_start=0.0,
        s_end=100.0,
        zone_length=100.0,
        L_required=177.0,
        L_total_required=180.0,
        E_required=0.0,
        model="APHEX_S_75W",
        pcb="Aphex S",
        current_mA=350,
        flux_lm=10000.0,
        power_w=50.0,
        optic="F2M2",
        d_max_ul=15.0,
        d_used=15.0,
        n_luminaires=3,
        L_estimated=177.0,
        UF=0.6,
        Ul=0.7,
        power_zone_w=150.0,
        flux_zone_lm=30000.0,
        power_density_wm2=0.0,
        setpoints=[
            {
                "s": position,
                "L_total_req": 180.0,
                "L_req": 177.0,
                "target_flux_lm": 10000.0,
                "flux_lm": 10000.0,
                "power_w": 50.0,
                "L_est": 177.0,
            }
            for position in (0.0, 15.0, 30.0)
        ],
        control_layer="reinforcement",
        portal="A",
    )
    messages, summary = _apply_solar_daylight_contribution(
        [zone],
        params={
            "daylight_contribution_enabled": True,
            "daylight_penetration_length_m": 30,
            "daylight_mouth_contribution_pct": 10,
            "daylight_portal_a": True,
            "daylight_portal_b": True,
        },
        tube_length_m=100,
        road_width_m=8,
        Lin=3,
        Lth=180,
        Lth_b=120,
        cct="4000K",
        I_max_mA=350,
        I_min_pct=0.3,
        two_way=True,
    )

    assert len(zone.setpoints) == 3
    assert [
        item["natural_daylight_cd_m2"] for item in zone.setpoints
    ] == [18.0, 9.0, 0.0]
    assert summary["counts_as_installed_luminaires"] is False
    assert summary["installed_power_kw"] == 0.0
    assert summary["scenes"]["sunny"]["portal_a_mouth_cd_m2"] == 18.0
    assert summary["scenes"]["overcast"]["portal_a_mouth_cd_m2"] == 5.4
    assert summary["scenes"]["dusk"]["portal_a_mouth_cd_m2"] == 0.9
    assert summary["scenes"]["night"]["portal_a_mouth_cd_m2"] == 0.0
    assert any("No añade luminarias" in item for item in messages)


def test_reinforcement_is_zero_when_daylight_curve_reaches_base():
    plan = build_control_plan(
        tube_id="T1",
        L20_design=4500,
        Lth_design=180,
        Lin=3,
        L_night=1,
        k_factor=0.04,
        speed_kmh=80,
        zones=_zones(),
    )
    for curve in plan.regulation_curves:
        if curve.group_name.startswith("REF-"):
            assert curve.points[0].dimming_pct == 0


def _zone(zone_type, layer, setpoints):
    return ZoneLuminaireDesign(
        zone_type=zone_type,
        zone_name="BASE" if layer == "permanent" else "CTH",
        s_start=0.0,
        s_end=100.0,
        zone_length=100.0,
        L_required=3.0 if layer == "permanent" else 27.0,
        L_total_required=3.0 if layer == "permanent" else 30.0,
        E_required=0.0,
        model="APHEX_S_75W",
        pcb="Aphex S 75W",
        current_mA=300,
        flux_lm=10000.0,
        power_w=50.0,
        optic="F2M2",
        d_max_ul=16.0,
        d_used=16.0,
        n_luminaires=len(setpoints),
        L_estimated=3.0,
        UF=0.4,
        Ul=0.6,
        power_zone_w=50.0 * len(setpoints),
        flux_zone_lm=10000.0 * len(setpoints),
        power_density_wm2=0.0,
        setpoints=setpoints,
        control_layer=layer,
        portal=None if layer == "permanent" else "A",
    )


def test_physical_scene_points_keep_hardware_and_switch_layers():
    base_setpoint = {
        "s": 0.0,
        "model": "APHEX_S_75W",
        "current_mA": 300.0,
        "flux_lm": 10000.0,
        "power_w": 50.0,
        "base_current_mA": 220.0,
        "base_flux_lm": 7600.0,
        "base_power_w": 37.0,
        "target_flux_lm": 10000.0,
        "night_current_mA": 105.0,
        "night_flux_lm": 3500.0,
        "night_target_flux_lm": 3333.0,
        "night_power_w": 18.0,
        "night_driver_floor": False,
    }
    reinforcement_setpoint = {
        "s": 10.0,
        "model": "APHEX_S_75W",
        "current_mA": 300.0,
        "flux_lm": 10000.0,
        "power_w": 50.0,
        "target_flux_lm": 10000.0,
    }
    zones = [
        _zone("interior_base", "permanent", [base_setpoint]),
        _zone("threshold", "reinforcement", [reinforcement_setpoint]),
    ]
    scenarios = _attach_layered_scene_operating_points(
        zones,
        Lth=30.0,
        Lth_b=30.0,
        Lin=3.0,
        L_night=1.0,
        speed_kmh=80.0,
        cct="4000K",
        I_min_pct=0.30,
    )

    base_ops = base_setpoint["scenario_operating_points"]
    ref_ops = reinforcement_setpoint["scenario_operating_points"]
    assert base_ops["sunny"]["state"] == "on"
    assert base_ops["sunny"]["current_mA"] == 300.0
    assert base_ops["normal"]["current_mA"] == 220.0
    assert base_ops["overcast"]["flux_lm"] == 7600.0
    assert base_ops["night"]["flux_lm"] == 3500.0
    assert ref_ops["night"]["state"] == "off"
    assert ref_ops["normal"]["current_mA"] <= 300.0
    assert scenarios["night"]["active_luminaires"] == 1
    assert scenarios["night"]["off_luminaires"] == 1


def test_adaptation_layer_is_exclusive_to_dusk():
    base_setpoint = {
        "s": 0.0,
        "model": "APHEX_S_75W",
        "current_mA": 300.0,
        "flux_lm": 10000.0,
        "power_w": 50.0,
        "target_flux_lm": 10000.0,
        "night_current_mA": 105.0,
        "night_flux_lm": 3500.0,
        "night_target_flux_lm": 3333.0,
        "night_power_w": 18.0,
    }
    adaptation_setpoint = dict(base_setpoint, s=10.0)
    base = _zone("interior_base", "permanent", [base_setpoint])
    adaptation = _zone("adaptation_a", "adaptation", [adaptation_setpoint])

    _attach_layered_scene_operating_points(
        [base, adaptation],
        Lth=30.0,
        Lth_b=30.0,
        Lin=3.0,
        L_night=1.0,
        speed_kmh=80.0,
        cct="4000K",
        I_min_pct=0.30,
    )

    ops = adaptation_setpoint["scenario_operating_points"]
    assert ops["dusk"]["state"] == "on"
    for scene in ("sunny", "normal", "overcast", "night"):
        assert ops[scene]["state"] == "off"
        assert ops[scene]["flux_lm"] == 0.0


def test_scene_current_override_changes_only_the_selected_dali_scene():
    base_setpoint = {
        "idx": 1,
        "s": 0.0,
        "model": "APHEX_S_75W",
        "current_mA": 300.0,
        "flux_lm": 10000.0,
        "power_w": 50.0,
        "base_current_mA": 220.0,
        "base_flux_lm": 7600.0,
        "base_power_w": 37.0,
        "night_current_mA": 105.0,
        "night_flux_lm": 3500.0,
        "night_power_w": 18.0,
    }
    base = _zone("interior_base", "permanent", [base_setpoint])
    _attach_layered_scene_operating_points(
        [base], Lth=30.0, Lth_b=30.0, Lin=3.0, L_night=1.0,
        speed_kmh=80.0, cct="4000K", I_min_pct=0.30,
    )
    layout = TunnelLuminaireResult(
        tube_id="T1", luminaire=None, road_surface_type="R3", rho_eff=0.07,
        road_width_m=9.0, tube_length_m=100.0, cct="4000K", I_max_mA=500,
        arrangement="central_single", zones=[base],
    )
    original_sunny = dict(base_setpoint["scenario_operating_points"]["sunny"])

    warnings = apply_scene_current_overrides(
        layout,
        {
            "dusk|BASE|1": {"current_mA": 180},
            "night_normal|BASE|1": {"current_mA": 200},
        },
        I_min_pct=0.30,
    )

    assert base_setpoint["scenario_operating_points"]["sunny"] == original_sunny
    assert base_setpoint["scenario_operating_points"]["dusk"]["current_mA"] == 180
    assert base_setpoint["scenario_operating_points"]["dusk"]["manual_current_override"]
    assert base_setpoint["scenario_operating_points"]["night_normal"]["current_mA"] == 200
    assert base_setpoint["current_mA"] == 300.0
    assert any("2 consignas manuales" in warning for warning in warnings)


def test_reinforcement_grid_is_shifted_without_moving_base():
    base_positions = [0.0, 2.0]
    reinforcement_positions = [0.0, 1.0, 2.0]
    base = _zone(
        "interior_base",
        "permanent",
        [
            {
                "s": position,
                "power_w": 50.0,
                "flux_lm": 10000.0,
            }
            for position in base_positions
        ],
    )
    reinforcement = _zone(
        "threshold",
        "reinforcement",
        [
            {
                "s": position,
                "power_w": 50.0,
                "flux_lm": 10000.0,
            }
            for position in reinforcement_positions
        ],
    )
    reinforcement.s_end = 2.0
    reinforcement.zone_length = 2.0

    messages = _resolve_constructive_position_conflicts(
        [base, reinforcement],
        spacing_quantum=0.5,
        minimum_separation_m=0.5,
    )

    assert [sp["s"] for sp in base.setpoints] == base_positions
    shifted = [sp["s"] for sp in reinforcement.setpoints]
    assert shifted == [0.5, 1.5]
    assert min(
        abs(base_s - ref_s)
        for base_s in base_positions
        for ref_s in shifted
    ) >= 0.5
    assert messages


def test_both_portal_reinforcements_avoid_the_permanent_base():
    base_positions = [0.0, 2.0, 98.0, 100.0]
    base = _zone(
        "interior_base",
        "permanent",
        [
            {
                "s": position,
                "power_w": 50.0,
                "flux_lm": 10000.0,
            }
            for position in base_positions
        ],
    )
    reinforcement_a = _zone(
        "threshold",
        "reinforcement",
        [
            {"s": position, "power_w": 50.0, "flux_lm": 10000.0}
            for position in (0.0, 1.0, 2.0)
        ],
    )
    reinforcement_a.s_end = 2.0
    reinforcement_a.zone_length = 2.0
    reinforcement_a.portal = "A"
    reinforcement_b = _zone(
        "threshold_b",
        "reinforcement",
        [
            {"s": position, "power_w": 50.0, "flux_lm": 10000.0}
            for position in (98.0, 99.0, 100.0)
        ],
    )
    reinforcement_b.s_start = 98.0
    reinforcement_b.s_end = 100.0
    reinforcement_b.zone_length = 2.0
    reinforcement_b.portal = "B"

    _resolve_constructive_position_conflicts(
        [base, reinforcement_a, reinforcement_b],
        spacing_quantum=0.5,
        minimum_separation_m=0.5,
    )

    assert [sp["s"] for sp in base.setpoints] == base_positions
    for reinforcement in (reinforcement_a, reinforcement_b):
        positions = [sp["s"] for sp in reinforcement.setpoints]
        assert positions
        assert min(
            abs(base_s - reinforcement_s)
            for base_s in base_positions
            for reinforcement_s in positions
        ) >= 0.5
