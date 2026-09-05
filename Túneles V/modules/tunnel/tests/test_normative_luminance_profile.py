from types import SimpleNamespace

import pytest

from modules.tunnel.photometric_verify import (
    _lane_layout,
    compute_real_luminance_profile,
    unify_zone_verification_with_profile,
)


def test_sidewalks_are_physical_width_but_excluded_from_cie140_road_grid():
    params = {
        "num_lanes": 2,
        "lane_width_m": 3.5,
        "shoulder_left_m": 1.0,
        "shoulder_right_m": 1.0,
        "sidewalk_left_m": 1.5,
        "sidewalk_right_m": 1.5,
    }

    layout = _lane_layout(params, road_width_m=12.0)

    assert layout["carriageway_width_m"] == 9.0
    assert layout["lane_centres_m"] == [4.25, 7.75]
    assert layout["transverse_points_m"] == [
        3.0833333333333335, 4.25, 5.416666666666666,
        6.583333333333333, 7.75, 8.916666666666666,
    ]
    assert not layout["includes_shoulders"]

    legacy_shoulder_flag = _lane_layout(
        {**params, "include_shoulders_in_luminance_grid": True},
        road_width_m=12.0,
    )
    assert not legacy_shoulder_flag["includes_shoulders"]
    assert legacy_shoulder_flag["shoulder_centres_m"] == []
    assert legacy_shoulder_flag["transverse_points_m"] == layout["transverse_points_m"]


def test_profile_reports_cie140_field_average_metadata():
    setpoints = [
        {
            "idx": index + 1,
            "s": float(s),
            "optic": "F151",
            "flux_lm": 11535.0,
            "tilt_deg": 5.0,
            "spacing_m": 20.0,
        }
        for index, s in enumerate(range(0, 101, 20))
    ]
    zone = SimpleNamespace(
        n_luminaires=len(setpoints),
        s_start=0.0,
        s_end=100.0,
        zone_type="interior",
        setpoints=setpoints,
        d_used=20.0,
    )
    lum_result = SimpleNamespace(
        road_surface_type="dark_asphalt",
        optic="F151",
        zones=[zone],
    )
    params = {
        "mounting_height_m": 4.5,
        "maintenance_factor": 0.70,
        "arrangement": "bilateral_sym",
        "wall_offset_m": 1.25,
        "num_lanes": 2,
        "lane_width_m": 3.5,
        "shoulder_left_m": 1.0,
        "shoulder_right_m": 1.0,
    }

    result = compute_real_luminance_profile(
        lum_result,
        params,
        road_width_m=9.0,
        step_size=20.0,
    )

    assert result["available"]
    assert result["metric"] == "CIE140_Lavg"
    assert result["grid"]["transverse_points_per_lane"] == 3
    assert result["grid"]["num_lanes"] == 2
    assert result["grid"]["num_observers"] == 2
    assert result["grid"]["selection"] == "peor observador"
    assert result["grid"]["representation"].startswith("un valor Lavg por campo")
    assert result["points"]
    assert len(result["points"]) == len(setpoints) - 1
    assert result["points"][0]["field_start"] == 0.0
    assert result["points"][0]["field_end"] == 20.0
    assert result["points"][0]["s"] == 10.0
    assert all(point["L"] > 0.0 for point in result["points"])
    assert len(result["fields"]) == len(result["points"])
    assert len(result["fields"][0]["grid_points"]) == 60
    assert result["fields"][0]["observer_lane_y_m"] in (2.75, 6.25)
    assert result["fields"][0]["observer_direction"] == 1
    assert result["fields"][0]["U0"] > 0.0
    assert result["fields"][0]["Ul"] > 0.0
    assert result["fields"][0]["TI"] >= 0.0
    assert len(result["fields"][0]["lane_results"]) == 2
    assert {
        lane["lane_number"]
        for lane in result["fields"][0]["lane_results"]
    } == {1, 2}
    assert all(
        lane["direction"] == 1
        for lane in result["fields"][0]["lane_results"]
    )
    assert len(result["fields"][0]["observer_grids"]) == 2
    assert all(
        len(observer["values"])
        == len(result["fields"][0]["grid_points"])
        for observer in result["fields"][0]["observer_grids"]
    )
    assert set(result["fields"][0]["metric_governors"]) == {
        "L", "U0", "Ul", "TI",
    }
    assert all(point["L"] > 0.0 for point in result["fields"][0]["grid_points"])
    # La vista lateral reutiliza los resultados reales CIE 140 de pared: tres
    # posiciones longitudinales y cuatro alturas en cada paramento.
    wall = result["fields"][0]["wall"]
    assert len(wall["sample_x_m"]) == len(wall["L_left_grid"]) == 3
    assert len(wall["sample_z_m"]) == 4
    assert all(len(row) == len(wall["sample_z_m"]) for row in wall["L_left_grid"])
    assert all(len(row) == len(wall["sample_z_m"]) for row in wall["L_right_grid"])
    assert all(value >= 0.0 for row in wall["L_left_grid"] for value in row)


def test_radiosity_profile_adds_the_same_indirect_component_to_cie140_grid():
    """El modo de reflexiones debe modificar la malla real, no sólo la pared.

    La curva longitudinal, la tabla de campo y la planta proceden de esta
    misma malla, por lo que se comprueba que el término indirecto está presente
    y que L es exactamente directa + indirecta para cada punto de la malla.
    """
    setpoints = [
        {
            "idx": index + 1,
            "s": float(s),
            "optic": "F151",
            "flux_lm": 11535.0,
            "tilt_deg": 5.0,
            "spacing_m": 20.0,
        }
        for index, s in enumerate(range(0, 101, 20))
    ]
    zone = SimpleNamespace(
        n_luminaires=len(setpoints), s_start=0.0, s_end=100.0,
        zone_type="interior", setpoints=setpoints, d_used=20.0,
    )
    lum_result = SimpleNamespace(
        road_surface_type="dark_asphalt", optic="F151", zones=[zone],
    )
    params = {
        "mounting_height_m": 4.5,
        "maintenance_factor": 0.70,
        "arrangement": "bilateral_sym",
        "wall_offset_m": 1.25,
        "num_lanes": 2,
        "lane_width_m": 3.5,
        "rho_wall": 0.40,
        "rho_ceiling": 0.25,
        "calc_mode": "radiosity",
    }

    profile = compute_real_luminance_profile(
        lum_result, params, road_width_m=9.0, step_size=20.0,
    )

    assert profile["calc_mode"] == "radiosity"
    assert profile["radiosity"]["road_indirect_included"]
    assert any(field["L_indirect"] > 0.0 for field in profile["fields"])
    for field in profile["fields"]:
        assert field["L"] == pytest.approx(
            field["L_direct"] + field["L_indirect"], abs=2e-3,
        )
        assert all(
            point["L"] == pytest.approx(
                point["L_direct"] + point["L_indirect"], abs=2e-3,
            )
            for point in field["grid_points"]
        )


def test_profile_keeps_base_fields_when_portal_reinforcement_is_off():
    """Una escena tenue no puede dejar huecos de Lcalc en el umbral.

    La BASE tiene las luminarias activas; el refuerzo sigue existiendo para
    aportar la etiqueta/requisito CIE del umbral, aunque sus luminarias estén
    apagadas por la consigna de la escena.
    """
    base_setpoints = [
        {
            "idx": index + 1,
            "s": float(s),
            "optic": "F151",
            "flux_lm": 11535.0,
            "tilt_deg": 5.0,
            "spacing_m": 20.0,
        }
        for index, s in enumerate(range(0, 101, 20))
    ]
    base = SimpleNamespace(
        n_luminaires=len(base_setpoints),
        s_start=0.0,
        s_end=100.0,
        zone_type="interior",
        zone_name="BASE",
        control_layer="permanent",
        setpoints=base_setpoints,
        d_used=20.0,
    )
    reinforcement = SimpleNamespace(
        n_luminaires=3,
        s_start=0.0,
        s_end=60.0,
        zone_type="threshold",
        zone_name="CTH",
        control_layer="reinforcement",
        setpoints=[
            {
                "idx": index + 1,
                "s": float(s),
                "optic": "F151",
                "flux_lm": 0.0,
                "tilt_deg": 5.0,
                "spacing_m": 20.0,
            }
            for index, s in enumerate((0, 20, 40))
        ],
        d_used=20.0,
    )
    result = compute_real_luminance_profile(
        SimpleNamespace(
            road_surface_type="dark_asphalt",
            optic="F151",
            zones=[base, reinforcement],
        ),
        {
            "mounting_height_m": 4.5,
            "maintenance_factor": 0.70,
            "arrangement": "bilateral_sym",
            "wall_offset_m": 1.25,
            "num_lanes": 2,
            "lane_width_m": 3.5,
        },
        road_width_m=9.0,
    )

    assert result["available"]
    threshold_fields = [
        field for field in result["fields"]
        if field["zone_type"] == "threshold"
    ]
    assert threshold_fields
    assert all(field["L"] > 0.0 for field in threshold_fields)
    assert max(field["field_end"] for field in threshold_fields) >= 60.0


def test_zone_summary_and_lane_breakdown_share_the_real_profile():
    zone = SimpleNamespace(
        zone_name="CIN",
        zone_type="interior",
        L_required=3.0,
        L_total_required=3.0,
        s_start=0.0,
        s_end=100.0,
        control_layer="permanent",
    )
    lum_result = SimpleNamespace(
        zones=[zone],
        road_width_m=7.0,
        tube_length_m=100.0,
    )
    lane_results = [
        {
            "lane_index": 0,
            "lane_number": 1,
            "observer_lane_y_m": 1.75,
            "direction": 1,
            "full_L_avg": 3.4,
            "full_L_min": 1.7,
            "U0": 0.5,
            "lane_L_avg": 3.2,
            "lane_L_min": 1.6,
            "lane_U0": 0.5,
            "Ul": 0.65,
            "TI": 10.0,
        },
        {
            "lane_index": 1,
            "lane_number": 2,
            "observer_lane_y_m": 5.25,
            "direction": 1,
            "full_L_avg": 3.3,
            "full_L_min": 1.55,
            "U0": 0.4697,
            "lane_L_avg": 3.1,
            "lane_L_min": 1.45,
            "lane_U0": 0.4677,
            "Ul": 0.62,
            "TI": 11.0,
        },
    ]
    profile = {
        "available": True,
        "fields": [{
            "s": 50.0,
            "zone_name": "CIN",
            "zone_type": "interior",
            "L": 3.3,
            "L_min": 1.55,
            "U0": 0.4697,
            "Ul": 0.62,
            "TI": 11.0,
            "lane_results": lane_results,
            "metric_governors": {},
        }],
    }
    photometric = {
        "available": True,
        "zones": {
            "CIN": {
                "L_indirect": 0.0,
                "E_h_avg": 30.0,
                "radiosity": {},
            },
        },
    }
    params = {
        "road_width_m": 7.0,
        "num_lanes": 2,
        "lane_width_m": 3.5,
        "Lth": 90.0,
        "Lth_b": 90.0,
        "Lin": 3.0,
        "speed_kmh": 80.0,
        "mounting_height_m": 5.0,
        "U0_obj": 0.4,
        "Ul_obj": 0.6,
        "TI_max": 15.0,
    }

    result = unify_zone_verification_with_profile(
        photometric,
        profile,
        lum_result,
        params,
    )

    verified = result["zones"]["CIN"]
    assert verified["source"] == "CIE140_real_profile_by_lane"
    assert verified["L_avg"] == 3.3
    assert verified["U0"] == 0.47
    assert verified["Ul"] == 0.62
    assert verified["TI"] == 11.0
    assert verified["compliant"]
    assert len(verified["by_lane"]) == 2
    assert verified["by_lane"][0]["L_avg"] == 3.2
    assert verified["by_lane"][1]["U0"] == 0.4677
    assert result["lane_verification"]["worst_case_governs"]


def test_unified_zone_does_not_add_radiosity_twice():
    zone = SimpleNamespace(
        zone_name="CIN", zone_type="interior", L_required=3.0,
        L_total_required=3.0, s_start=0.0, s_end=100.0,
        control_layer="permanent",
    )
    lum_result = SimpleNamespace(
        zones=[zone], road_width_m=7.0, tube_length_m=100.0,
    )
    lane = {
        "lane_index": 0, "lane_number": 1, "observer_lane_y_m": 1.75,
        "direction": 1, "full_L_avg": 3.5, "full_L_min": 2.1,
        "U0": 0.6, "lane_L_avg": 3.5, "lane_L_min": 2.1,
        "lane_U0": 0.6, "Ul": 0.7, "TI": 8.0,
    }
    profile = {
        "available": True,
        "radiosity": {"road_indirect_included": True},
        "fields": [{
            "s": 50.0, "zone_name": "CIN", "zone_type": "interior",
            # Estos valores ya son total (directa 3.0 + indirecta 0.5).
            "L": 3.5, "L_min": 2.1, "L_direct": 3.0,
            "L_indirect": 0.5, "U0": 0.6, "Ul": 0.7, "TI": 8.0,
            "lane_results": [lane], "metric_governors": {},
        }],
    }
    photometric = {
        "available": True,
        # La cifra heredada, si existiera, no debe volver a sumarse.
        "zones": {"CIN": {"L_indirect": 9.0, "radiosity": {}}},
    }
    params = {
        "road_width_m": 7.0, "num_lanes": 2, "lane_width_m": 3.5,
        "Lth": 90.0, "Lth_b": 90.0, "Lin": 3.0, "speed_kmh": 80.0,
        "mounting_height_m": 5.0, "U0_obj": 0.4, "Ul_obj": 0.6,
        "TI_max": 15.0,
    }

    verified = unify_zone_verification_with_profile(
        photometric, profile, lum_result, params,
    )["zones"]["CIN"]

    assert verified["L_avg"] == 3.5
    assert verified["L_direct"] == 3.0
    assert verified["L_indirect"] == 0.5
