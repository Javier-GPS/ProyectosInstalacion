from types import SimpleNamespace

import pytest

from modules.tunnel.required_luminance import (
    build_requirement_samples,
    canonical_validation_positions,
    cie88_threshold_luminance,
    cie88_transition_luminance,
    required_luminance_for_zone,
)


def _zone(zone_type, s_start, s_end, L_required, setpoints=None):
    return SimpleNamespace(
        zone_type=zone_type,
        s_start=s_start,
        s_end=s_end,
        L_required=L_required,
        setpoints=setpoints or [],
    )


def test_transition_curve_is_monotonic_and_floored():
    values = [
        cie88_transition_luminance(s, 50.0, 120.0, 3.0, 80.0)
        for s in (50.0, 75.0, 125.0, 250.0, 1000.0)
    ]
    assert values == sorted(values, reverse=True)
    assert values[-1] == pytest.approx(3.0)


def test_threshold_curve_reaches_transition_without_jump():
    Lth = 200.0
    Lin = 3.0
    assert cie88_threshold_luminance(
        0.0, 0.0, 100.0, Lth, Lin,
    ) == pytest.approx(Lth)
    assert cie88_threshold_luminance(
        50.0, 0.0, 100.0, Lth, Lin,
    ) == pytest.approx(Lth)

    threshold_end = cie88_threshold_luminance(
        100.0, 0.0, 100.0, Lth, Lin,
    )
    transition_start = cie88_transition_luminance(
        100.0, 100.0, Lth, Lin, 80.0,
    )
    assert threshold_end == pytest.approx(transition_start)
    assert threshold_end == pytest.approx(0.4065 * Lth, rel=2e-3)


def test_threshold_curve_is_mirrored_at_portal_b():
    Lth = 300.0
    Lin = 3.0
    transition_start = cie88_transition_luminance(
        0.0, 0.0, Lth, Lin, 80.0,
    )
    assert cie88_threshold_luminance(
        500.0, 500.0, 600.0, Lth, Lin, reverse=True,
    ) == pytest.approx(transition_start)
    assert cie88_threshold_luminance(
        550.0, 500.0, 600.0, Lth, Lin, reverse=True,
    ) == pytest.approx(Lth)
    assert cie88_threshold_luminance(
        600.0, 500.0, 600.0, Lth, Lin, reverse=True,
    ) == pytest.approx(Lth)


def test_initial_design_dict_uses_the_same_threshold_curve():
    """El dimensionado recibe dicts; no puede volver a Lth uniforme."""
    zone = {
        "zone_type": "threshold_b",
        "s_start": 500.0,
        "s_end": 600.0,
        "L_min_required": 300.0,
    }
    at_transition = required_luminance_for_zone(
        zone, 500.0, Lth=200.0, Lth_b=300.0, Lin=3.0, speed_kmh=80.0,
    )
    at_portal = required_luminance_for_zone(
        zone, 600.0, Lth=200.0, Lth_b=300.0, Lin=3.0, speed_kmh=80.0,
    )
    assert at_transition == pytest.approx(0.4065 * 300.0, rel=2e-3)
    assert at_portal == pytest.approx(300.0)


def test_exit_requirement_is_continuous_and_defaults_to_interior_level():
    zone = _zone("exit", 100.0, 200.0, 2.0)
    assert required_luminance_for_zone(
        zone, 100.0, Lth=90.0, Lth_b=90.0, Lin=2.0, speed_kmh=80.0,
    ) == pytest.approx(2.0)
    assert required_luminance_for_zone(
        zone, 150.0, Lth=90.0, Lth_b=90.0, Lin=2.0, speed_kmh=80.0,
    ) == pytest.approx(2.0)
    assert required_luminance_for_zone(
        zone, 200.0, Lth=90.0, Lth_b=90.0, Lin=2.0, speed_kmh=80.0,
    ) == pytest.approx(2.0)


def test_exit_project_ratio_interpolates_to_lower_portal_target():
    zone = _zone("exit", 100.0, 200.0, 1.0)
    values = [
        required_luminance_for_zone(
            zone, position, Lth=90.0, Lth_b=90.0,
            Lin=2.0, speed_kmh=80.0,
        )
        for position in (100.0, 150.0, 200.0)
    ]
    assert values == pytest.approx([2.0, 1.5, 1.0])


def test_canonical_grid_adds_midspans_and_boundary_probes():
    positions = canonical_validation_positions(
        100.0,
        zone_boundaries=[40.3],
        luminaire_positions=[10.0, 24.0],
        step_m=1.0,
    )
    assert 17.0 in positions
    assert 39.8 in positions
    assert 40.8 in positions
    assert 0.0 not in positions
    assert 100.0 not in positions


def test_requirement_samples_use_cie_curve_in_transition():
    zones = [
        _zone("threshold", 0.0, 50.0, 120.0),
        _zone(
            "transition", 50.0, 317.6, 3.0,
            setpoints=[{"s": 60.0}, {"s": 80.0}],
        ),
        _zone("interior", 317.6, 500.0, 3.0),
    ]
    samples = build_requirement_samples(
        zones,
        tube_length_m=500.0,
        Lth=120.0,
        Lth_b=120.0,
        Lin=3.0,
        speed_kmh=80.0,
    )
    at_65 = min(samples, key=lambda item: abs(item["s"] - 65.0))
    expected = cie88_transition_luminance(
        at_65["s"], 50.0, 120.0, 3.0, 80.0,
    )
    assert at_65["zone"].zone_type == "transition"
    assert at_65["target"] == pytest.approx(expected)


def test_truncated_transition_tail_is_not_replaced_by_lin():
    zones = [
        _zone("threshold", 0.0, 50.0, 120.0),
        _zone("transition", 50.0, 150.0, 3.0),
        _zone("interior", 150.0, 250.0, 3.0),
    ]
    samples = build_requirement_samples(
        zones,
        tube_length_m=250.0,
        Lth=120.0,
        Lth_b=120.0,
        Lin=3.0,
        speed_kmh=80.0,
    )
    after_truncation = min(samples, key=lambda item: abs(item["s"] - 175.0))
    expected = cie88_transition_luminance(
        after_truncation["s"], 50.0, 120.0, 3.0, 80.0,
    )
    assert after_truncation["zone"].zone_type == "interior"
    assert after_truncation["target"] == pytest.approx(expected)
    assert after_truncation["target"] > 3.0


def test_engine_profile_validates_continuity_at_both_portals():
    from modules.tunnel.engine import run_tunnel_calculation

    result = run_tunnel_calculation({
        "length_m": 1000,
        "speed_kmh": 80,
        "traffic_direction": "two_way",
    })
    assert result["success"]
    assert result["validation"]["valid"], result["validation"]

    data = result["chart"]["data"]
    zones = result["zones"]
    Lth = result["summary"]["Lth"]
    Lin = result["summary"]["Lin"]
    speed = result["summary"]["speed_kmh"]

    a_boundary = zones["threshold"]["s_end"]
    a_at_boundary = min(data, key=lambda point: abs(point["s"] - a_boundary))
    assert a_at_boundary["L"] == pytest.approx(
        cie88_threshold_luminance(
            a_boundary, zones["threshold"]["s_start"], a_boundary,
            Lth, Lin,
        ),
        abs=0.01,
    )

    b_boundary = zones["threshold_b"]["s_start"]
    b_at_boundary = min(data, key=lambda point: abs(point["s"] - b_boundary))
    Lth_b = result["lth"]["Lth_b"]
    assert b_at_boundary["L"] == pytest.approx(
        cie88_transition_luminance(
            0.0, 0.0, Lth_b, Lin, speed,
        ),
        abs=0.01,
    )


def test_engine_exit_level_can_be_fixed_equal_to_interior_or_project_ratio():
    from modules.tunnel.engine import run_tunnel_calculation

    equal = run_tunnel_calculation({
        "length_m": 1000,
        "speed_kmh": 80,
        "exit_luminance_ratio_override": 100,
    })
    assert equal["success"]
    assert equal["zones"]["exit"]["L_min_required"] == pytest.approx(
        equal["summary"]["Lin"], abs=0.01,
    )

    reduced = run_tunnel_calculation({
        "length_m": 1000,
        "speed_kmh": 80,
        "exit_luminance_ratio_override": 50,
    })
    assert reduced["success"]
    assert reduced["zones"]["exit"]["L_min_required"] == pytest.approx(
        reduced["summary"]["Lin"] * 0.5, abs=0.01,
    )
    assert any(
        item["label"] == "L salida / Lin"
        for item in reduced["project_overrides"]["items"]
    )


def test_engine_treats_daylight_as_natural_not_controlled_equipment():
    from modules.tunnel.engine import run_tunnel_calculation

    result = run_tunnel_calculation({
        "length_m": 1000,
        "speed_kmh": 80,
        "traffic_direction": "two_way",
        "luminaire": {
            "daylight_contribution_enabled": True,
            "daylight_portal_a": True,
            "daylight_portal_b": True,
            "daylight_mouth_contribution_pct": 10,
        },
    })

    assert result["success"]
    assert not [
        group for group in result["control"]["groups"]
        if group["layer"] == "exterior"
    ]
    assert any(
        "no constituye un grupo DALI" in warning
        for warning in result["warnings"]
    )


def test_engine_separates_normal_and_reduced_night_levels():
    from modules.tunnel.engine import run_tunnel_calculation

    result = run_tunnel_calculation({
        "length_m": 1000,
        "speed_kmh": 80,
        "night_reduced_luminance_cd_m2": 1.0,
    })

    assert result["success"]
    assert result["summary"]["L_night_normal"] == result["summary"]["Lin"]
    assert result["summary"]["L_night_reduced"] == 1.0
    assert result["summary"]["L_night"] == 1.0
    scenes = {
        scene["scene_type"]: scene
        for scene in result["control"]["scenes"]
    }
    assert scenes["night_normal"]["name"] == "Noche normal"
    assert scenes["night"]["name"] == "Noche reducida"


def test_engine_accepts_independent_night_overrides():
    from modules.tunnel.engine import run_tunnel_calculation

    result = run_tunnel_calculation({
        "length_m": 1000,
        "speed_kmh": 80,
        "night_normal_luminance_cd_m2": 2.0,
        "night_reduced_luminance_cd_m2": 1.0,
    })

    assert result["success"]
    assert result["summary"]["L_night_normal"] == 2.0
    assert result["summary"]["L_night_reduced"] == 1.0
    assert result["interior"]["night_normal_source"] == "user_override"
    assert result["interior"]["night_reduced_source"] == "user_override"


def test_daylight_requirement_scales_with_each_scene_lth():
    from modules.tunnel.required_luminance import (
        required_luminance_for_zone,
    )

    zone = {
        "zone_type": "threshold",
        "s_start": 0.0,
        "s_end": 100.0,
        "daylight_profile": {
            "enabled": True,
            "penetration_length_m": 60.0,
            "mouth_contribution_pct": 10.0,
            "decay_exponent": 1.0,
            "tube_length_m": 1000.0,
            "portal_a": True,
            "portal_b": False,
        },
    }
    sunny = required_luminance_for_zone(
        zone, 0.0, Lth=180.0, Lth_b=120.0, Lin=3.0, speed_kmh=80.0,
    )
    overcast = required_luminance_for_zone(
        zone, 0.0, Lth=54.0, Lth_b=36.0, Lin=3.0, speed_kmh=80.0,
    )
    dusk = required_luminance_for_zone(
        zone, 0.0, Lth=9.0, Lth_b=6.0, Lin=3.0, speed_kmh=80.0,
    )
    night = required_luminance_for_zone(
        zone, 0.0, Lth=3.0, Lth_b=3.0, Lin=3.0, speed_kmh=80.0,
    )

    assert sunny == pytest.approx(162.0)
    assert overcast == pytest.approx(48.6)
    assert dusk == pytest.approx(8.1)
    assert night == pytest.approx(3.0)
