import pytest

from modules.tunnel.engine import run_tunnel_calculation
from modules.tunnel.l20_lseq_lth import (
    calculate_Lseq,
    calculate_Lth,
    derive_tunnel_class_oc36,
    get_k_factor_oc36,
)
from modules.tunnel.models import L20Result


def test_oc36_k_interpolates_by_stopping_distance_and_class():
    assert get_k_factor_oc36(60, 2) == pytest.approx(0.03)
    assert get_k_factor_oc36(85, 2) == pytest.approx(0.03625)
    assert get_k_factor_oc36(100, 2) == pytest.approx(0.04)
    assert get_k_factor_oc36(130, 3) == pytest.approx(0.06)
    assert get_k_factor_oc36(200, 4) == pytest.approx(0.10)


@pytest.mark.parametrize(
    "traffic,lanes,direction,mixed,expected",
    [
        (3200, 2, "one_way", False, 3),
        (2000, 2, "one_way", True, 3),
        (1000, 2, "one_way", False, 2),
        (500, 2, "one_way", False, 1),
        (500, 2, "two_way", False, 2),
        (1600, 2, "two_way", True, 4),
    ],
)
def test_oc36_class_uses_traffic_per_lane_direction_and_type(
    traffic, lanes, direction, mixed, expected
):
    tunnel_class, _, _ = derive_tunnel_class_oc36(
        traffic, lanes, direction, mixed
    )
    assert tunnel_class == expected


def test_qc_does_not_change_oc36_k_method():
    l20 = L20Result(L20=3000, method="manual")
    low_qc = calculate_Lth(
        l20,
        speed_kmh=80,
        traffic_veh_h=1000,
        method="k_factor",
        qc_override=0.07,
        stopping_distance_m=85,
        tunnel_class=2,
    )
    high_qc = calculate_Lth(
        l20,
        speed_kmh=80,
        traffic_veh_h=1000,
        method="k_factor",
        qc_override=0.60,
        stopping_distance_m=85,
        tunnel_class=2,
    )

    assert low_qc.k_factor == pytest.approx(0.03625)
    assert high_qc.k_factor == pytest.approx(low_qc.k_factor)
    assert low_qc.Lth == high_qc.Lth == 109
    assert low_qc.qc_used is False


def test_lseq_method_uses_manual_lseq_qc_and_contrast():
    l20 = L20Result(L20=3000, method="manual")
    lseq = calculate_Lseq(3000, override=500)
    result = calculate_Lth(
        l20,
        speed_kmh=80,
        traffic_veh_h=1000,
        method="lseq",
        Lseq_result=lseq,
        qc_override=0.20,
        contrast_observation=0.04,
        stopping_distance_m=85,
        tunnel_class=2,
    )

    assert result.Lseq == 500
    assert result.Lth == 100
    assert result.qc_used is True
    assert result.C_obs == pytest.approx(0.04)


def test_engine_applies_all_manual_overrides_to_lth():
    result = run_tunnel_calculation(
        {
            "length_m": 300,
            "speed_kmh": 80,
            "gradient_pct": 0,
            "traffic_direction": "one_way",
            "num_lanes": 2,
            "traffic_veh_h": 1000,
            "portal_orientation": "S",
            "environment_type": "open_country_flat",
            "sky_condition": "clear",
            "mu_friction": 0.40,
            "t_reaction": 2.5,
            "stopping_distance_override_m": 85,
            "tunnel_class": "2",
            "l20_override": 2600,
            "k_lth_override": 0.035,
            "lth_method": "k_factor",
            "lth_standard": "oc36_2015",
        }
    )

    assert result["success"] is True
    assert result["summary"]["SD_m"] == 85
    assert result["summary"]["L20"] == 2600
    assert result["summary"]["Lth"] == 91
    assert result["summary"]["k_factor"] == pytest.approx(0.035)
    assert result["lth"]["L20_source"] == "override"
    assert result["lth"]["SD_source"] == "user_override"
    assert result["lth"]["k_source"] == "user_override"
    assert result["lth"]["tunnel_class_source"] == "user_override"


def test_engine_accepts_blank_curvature_radius_as_straight_tunnel():
    result = run_tunnel_calculation(
        {
            "length_m": 300,
            "speed_kmh": 80,
            "gradient_pct": 0,
            "curvature_radius_m": "",
            "traffic_direction": "two_way",
            "num_lanes": 2,
            "traffic_veh_h": 500,
            "portal_orientation": "S",
            "width_m": 11.4,
            "height_m": 9.0,
            "tunnel_shape": "circular",
        }
    )

    assert result["success"] is True
