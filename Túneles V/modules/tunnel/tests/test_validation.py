from modules.tunnel.validation import validate_tunnel_params


def test_valid_tunnel_definition_does_not_require_geolocation():
    result = validate_tunnel_params({
        "project_name": "Prueba",
        "length_m": 300,
        "width_m": 10.5,
        "height_m": 5.5,
        "num_lanes": 2,
        "lane_width_m": 3.5,
        "speed_kmh": 80,
        "portal_orientation": "S",
        "traffic_direction": "one_way",
    })
    assert result["valid"]


def test_validation_rejects_calzada_wider_than_tunnel():
    result = validate_tunnel_params({
        "length_m": 300,
        "width_m": 5,
        "height_m": 5,
        "num_lanes": 2,
        "lane_width_m": 3.5,
        "speed_kmh": 80,
        "portal_orientation": "S",
    })
    assert not result["valid"]
    assert any("calzada" in error.lower() for error in result["errors"])

