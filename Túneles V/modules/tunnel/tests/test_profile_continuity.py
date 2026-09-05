from types import SimpleNamespace

import pytest

from modules.tunnel.models import TrafficDirection
from modules.tunnel.profile import build_profile


def _zone(zone_type, s_start, s_end):
    return SimpleNamespace(
        zone_type=zone_type,
        s_start=s_start,
        s_end=s_end,
    )


def test_required_profile_is_continuous_at_both_threshold_boundaries():
    zones = SimpleNamespace(
        tube_id="T1",
        traffic_direction=TrafficDirection.TWO_WAY,
        threshold=_zone("threshold", 0.0, 100.0),
        transition=_zone("transition", 100.0, 200.0),
        interior=_zone("interior", 200.0, 300.0),
        transition_b=_zone("transition_b", 300.0, 400.0),
        threshold_b=_zone("threshold_b", 400.0, 500.0),
        exit=None,
    )
    profile = build_profile(
        tube_length=500.0,
        stopping_distance=100.0,
        speed_kmh=80.0,
        Lth=200.0,
        Lth_b=300.0,
        Lin=3.0,
        L_night=1.0,
        zones=zones,
        step_size=1.0,
    )
    values = {point.s: point.L_required for point in profile.points}

    # Portal A: final de Umbral y primer metro de Transicion.
    assert values[100.0] == pytest.approx(200.0 * 1.9 ** -1.4, abs=1e-3)
    assert abs(values[101.0] - values[100.0]) / values[100.0] < 0.04

    # Portal B: ultimo metro de Transicion y comienzo del Umbral espejado.
    assert values[400.0] == pytest.approx(300.0 * 1.9 ** -1.4, abs=1e-3)
    assert abs(values[401.0] - values[400.0]) / values[400.0] < 0.04
