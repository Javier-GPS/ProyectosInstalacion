import pytest

from app.services.lux_jobs import JobItemError, build_lux_config, digest, materialization_points


def _snapshot(lighting_class="M3"):
    return {
        "target": {
            "target_ref": "s:0:abc",
            "group_ref": "g:road",
            "name": "Calle Test",
            "road_type": "residential",
            "estWidth": 7.0,
            "geometry": [[-3.70, 40.40], [-3.699, 40.40]],
        },
        "params": {
            "lighting_class": lighting_class,
            "spacing": 30,
            "distribution": "unilateral_r",
            "luxParams": {"optic": "F151", "poleH": 9, "power": 80},
        },
    }


def test_build_lux_config_rejects_classes_not_supported_by_lux():
    with pytest.raises(JobItemError) as error:
        build_lux_config(_snapshot("C0"))
    assert error.value.code == "UNSUPPORTED_CLASS"


def test_materialization_points_are_deterministic_and_on_the_line():
    snapshot = _snapshot()
    result = {"config": build_lux_config(snapshot)}
    first = materialization_points(snapshot, result)
    second = materialization_points(snapshot, result)
    assert first == second
    assert first
    assert all(-3.70 <= point["lon"] <= -3.699 for point in first)
    assert all(point["lat"] == pytest.approx(40.40) for point in first)


def test_digest_is_order_independent_for_mapping_keys():
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})
