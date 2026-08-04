import pytest

from modules.tunnel import optimizer
from modules.tunnel.luminaires import (
    TunnelLuminaireResult,
    ZoneLuminaireDesign,
    physical_luminaires_per_setpoint,
)


def _zone(n_positions=3):
    setpoints = [
        {
            "idx": index + 1,
            "s": 5.0 + index * 10.0,
            "model": "APHEX_S_100W",
            "power_w": 100.0,
            "flux_lm": 1000.0,
        }
        for index in range(n_positions)
    ]
    return ZoneLuminaireDesign(
        zone_type="interior",
        zone_name="Interior",
        s_start=0.0,
        s_end=30.0,
        zone_length=30.0,
        L_required=3.0,
        E_required=45.0,
        model="APHEX_S_100W",
        pcb="50G",
        current_mA=350,
        flux_lm=1000.0,
        power_w=100.0,
        optic="F151",
        d_max_ul=10.0,
        d_used=10.0,
        n_luminaires=n_positions,
        L_estimated=3.1,
        UF=0.5,
        power_zone_w=100.0 * n_positions,
        flux_zone_lm=1000.0 * n_positions,
        power_density_wm2=1.0,
        setpoints=setpoints,
        Ul=0.7,
        control_layer="permanent",
    )


def _result(arrangement):
    return TunnelLuminaireResult(
        tube_id="T1",
        luminaire=None,
        road_surface_type="dark_asphalt",
        rho_eff=0.065,
        road_width_m=10.0,
        tube_length_m=30.0,
        arrangement=arrangement,
        architecture="permanent_base_plus_portal_reinforcement",
        zones=[_zone()],
        scenarios={
            "sunny": {
                "active_luminaires": 3,
                "off_luminaires": 1,
                "power_kw": 0.3,
                "flux_lm": 3000.0,
            },
        },
    )


@pytest.mark.parametrize(
    ("arrangement", "factor"),
    [
        ("central_single", 1),
        ("central_offset", 1),
        ("lateral_left", 1),
        ("bilateral_stag", 1),
        ("staggered", 1),
        ("central_double", 2),
        ("bilateral_sym", 2),
        ("bilateral", 2),
    ],
)
def test_physical_factor_by_arrangement(arrangement, factor):
    assert physical_luminaires_per_setpoint(arrangement) == factor


@pytest.mark.parametrize(
    ("arrangement", "expected_luminaires", "expected_power_kw"),
    [
        ("central_single", 3, 0.3),
        ("bilateral_stag", 3, 0.3),
        ("central_double", 6, 0.6),
        ("bilateral_sym", 6, 0.6),
    ],
)
def test_result_serializes_positions_and_physical_luminaires_separately(
    arrangement, expected_luminaires, expected_power_kw,
):
    payload = _result(arrangement).to_dict()

    assert payload["totals"]["n_positions"] == 3
    assert payload["totals"]["n_luminaires"] == expected_luminaires
    assert payload["totals"]["power_kw"] == expected_power_kw
    assert payload["totals"]["installed_power_kw"] == expected_power_kw
    assert payload["totals"]["installed_power_source"] == "sunny_scene_currents"

    zone = payload["zones"][0]
    assert zone["n_positions"] == 3
    assert zone["n_luminaires"] == expected_luminaires
    assert zone["power_zone_w"] == expected_power_kw * 1000
    assert zone["power_zone_positions_w"] == 300.0

    permanent = payload["layers"]["permanent"]
    assert permanent["n_positions"] == 3
    assert permanent["n_luminaires"] == expected_luminaires
    assert permanent["power_kw"] == expected_power_kw

    sunny = payload["scenarios"]["sunny"]
    factor = physical_luminaires_per_setpoint(arrangement)
    assert sunny["active_luminaires"] == 3 * factor
    assert sunny["off_luminaires"] == factor
    assert sunny["power_kw"] == expected_power_kw
    assert sunny["flux_lm"] == 3000.0 * factor


def test_installed_power_uses_final_sunny_currents_not_legacy_zone_total():
    result = _result("central_single")
    # El total zonal conserva los 3 x 100 W de partida, pero las consignas
    # DALI finales de Soleado han reducido la potencia a 245 W.
    result.scenarios["sunny"]["power_kw"] = 0.245

    payload = result.to_dict()

    assert payload["totals"]["power_kw"] == 0.3
    assert payload["totals"]["installed_power_kw"] == 0.245
    assert payload["totals"]["installed_power_source"] == "sunny_scene_currents"


def test_optimizer_builds_two_luminaires_per_symmetric_position(monkeypatch):
    monkeypatch.setattr(optimizer, "_load_phot", lambda _optic: object())

    luminaires = optimizer._build_lums(
        "F151", d=10.0, h=5.0, w=10.0, tilt=0.0,
        arrangement="bilateral_sym", n_side=1, wall_offset=0.5,
    )

    assert len(luminaires) == 6
    assert [(lum.x, lum.y) for lum in luminaires] == [
        (-10.0, 0.5), (-10.0, 9.5),
        (0.0, 0.5), (0.0, 9.5),
        (10.0, 0.5), (10.0, 9.5),
    ]


def test_optimizer_builds_one_alternating_luminaire_per_staggered_position(
    monkeypatch,
):
    monkeypatch.setattr(optimizer, "_load_phot", lambda _optic: object())

    luminaires = optimizer._build_lums(
        "F151", d=10.0, h=5.0, w=10.0, tilt=0.0,
        arrangement="bilateral_stag", n_side=1, wall_offset=0.5,
    )

    assert len(luminaires) == 3
    assert [(lum.x, lum.y) for lum in luminaires] == [
        (-10.0, 9.5),
        (0.0, 0.5),
        (10.0, 9.5),
    ]
