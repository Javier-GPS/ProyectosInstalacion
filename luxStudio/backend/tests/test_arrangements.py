"""Test Bilateral and Central Doble arrangement calculations."""
import math

import pytest

from pathlib import Path

from app.salvi_lighting import parse_ldt, Photometry
from app.salvi_lighting import calc as calc_module
from app.salvi_lighting.calc import build_luminaires, calc_sidewalk, evaluate, _carriageway_splits, _edge_strip_illuminances

_BASE = Path(__file__).resolve().parent.parent


def _base_cfg(**overrides):
    cfg = {
        "W": 7.0, "S": 30.0, "h": 9.0, "arm": 1.0, "tilt": 0.0, "mf": 0.85,
        "class": "M3", "pole_side": "left", "median_width": 0.0,
    }
    cfg.update(overrides)
    return cfg


def _load_ldt():
    return Photometry(parse_ldt(_BASE / 'ldt/Salvi/CLAP_M_C35_30K_F151_VDR_SPUW_100W.ldt'))


def _load_clap_s_ldt():
    return Photometry(parse_ldt(_BASE / 'fotometrias/CLAPS-5050HE-F151-ANTIRFLX.txt'))


def _load_clap_s_f2md_ldt():
    return Photometry(parse_ldt(_BASE / 'fotometrias/CLAPS-5050HE-F2MD-ANTIRFLX..ldt'))


def test_bilateral_illuminance_twice_unilateral():
    p = _load_ldt()
    cfg1 = _base_cfg(arrangement="Lineal")
    cfg2 = _base_cfg(arrangement="Bilateral")
    r1 = evaluate(cfg1, p, flux_scale=5.0)
    r2 = evaluate(cfg2, p, flux_scale=5.0)
    # 2 luminaires, each at full flux → 2× total flux ≈ 2× Eavg
    ratio = r2["Eavg"] / r1["Eavg"]
    assert 1.9 < ratio < 2.1, f"Expected ~2x, got {ratio:.3f}"


def test_bilateral_illuminance_symmetric_around_center():
    p = _load_ldt()
    cfg = _base_cfg(arrangement="Bilateral", arm=0.0)
    lums = build_luminaires(cfg, p, flux_scale=5.0)
    for y_test in [0.5, 2.0, 3.5]:
        e_a = sum(lum.E_at(15.0, y_test) for lum in lums)
        e_b = sum(lum.E_at(15.0, cfg["W"] - y_test) for lum in lums)
        assert abs(e_a - e_b) < 0.01, f"y={y_test}: {e_a} vs {e_b}"


def test_bilateral_equal_sidewalks_are_symmetric_like_model_101():
    p = _load_clap_s_ldt()
    cfg = _base_cfg(
        arrangement="Bilateral", W=5.0, S=15.0, h=8.0, arm=1.0,
        tilt=5.0, sidewalk_left=1.5, sidewalk_right=1.5,
    )

    left = calc_sidewalk(cfg, p, flux_scale=2651.2 / p.flux, side="left")
    right = calc_sidewalk(cfg, p, flux_scale=2651.2 / p.flux, side="right")

    assert left["Eavg"] == pytest.approx(right["Eavg"])
    assert left["Emin"] == pytest.approx(right["Emin"])


def test_central_doble_illuminance_symmetric_around_center():
    p = _load_ldt()
    cfg = _base_cfg(arrangement="Central Doble")
    lums = build_luminaires(cfg, p, flux_scale=5.0)
    for y_test in [0.5, 2.0, 3.5]:
        e_a = sum(lum.E_at(15.0, y_test) for lum in lums)
        e_b = sum(lum.E_at(15.0, cfg["W"] - y_test) for lum in lums)
        assert abs(e_a - e_b) < 0.01, f"y={y_test}: {e_a} vs {e_b}"


def test_central_doble_twice_central_simple():
    p = _load_ldt()
    cfg1 = _base_cfg(arrangement="En Isleta")
    cfg2 = _base_cfg(arrangement="Central Doble")
    r1 = evaluate(cfg1, p, flux_scale=5.0)
    r2 = evaluate(cfg2, p, flux_scale=5.0)
    ratio = r2["Eavg"] / r1["Eavg"]
    assert 1.9 < ratio < 2.1, f"Expected ~2x, got {ratio:.3f}"


def test_central_doble_median_splits_carriageway():
    """Central Doble with median divides road into two sub-carriageways."""
    cfg = _base_cfg(arrangement="Central Doble", median_width=2.0)
    splits = _carriageway_splits(cfg)
    assert len(splits) == 2
    y0s, y0e = splits[0]
    y1s, y1e = splits[1]
    assert y0s == 0.0
    assert y0e < cfg["W"] / 2.0
    assert y1s > cfg["W"] / 2.0
    assert y1e == cfg["W"]
    assert y0e + (y1s - y0e) + (cfg["W"] - y1s) == cfg["W"]


def test_central_doble_no_median_is_single_carriageway():
    cfg = _base_cfg(arrangement="Central Doble", median_width=0.0)
    assert len(_carriageway_splits(cfg)) == 1


def test_bilateral_no_median_split():
    cfg = _base_cfg(arrangement="Bilateral", median_width=2.0)
    assert len(_carriageway_splits(cfg)) == 1


def test_central_doble_median_wider_than_road_no_split():
    """If median exceeds road width, no split (edge case)."""
    cfg = _base_cfg(arrangement="Central Doble", median_width=8.0)
    assert len(_carriageway_splits(cfg)) == 1


def test_bilateral_luminaires_per_period():
    p = _load_ldt()
    cfg = _base_cfg(arrangement="Bilateral")
    lums = build_luminaires(cfg, p, flux_scale=5.0)
    in_period = [lum for lum in lums if 0 <= lum.x0 < cfg["S"]]
    assert len(in_period) == 2
    y_positions = sorted([l.y0 for l in in_period])
    assert y_positions[0] == cfg["arm"]
    assert y_positions[1] == cfg["W"] - cfg["arm"]


def test_central_doble_luminaires_at_center():
    p = _load_ldt()
    cfg = _base_cfg(arrangement="Central Doble")
    lums = build_luminaires(cfg, p, flux_scale=5.0)
    in_period = [lum for lum in lums if 0 <= lum.x0 < cfg["S"]]
    assert len(in_period) == 2
    for lum in in_period:
        assert lum.y0 == cfg["W"] / 2.0
    mirrors = [lum.mirror_y for lum in in_period]
    assert mirrors.count(True) == 1
    assert mirrors.count(False) == 1


def test_bilateral_right_luminaire_is_mirrored():
    p = _load_ldt()
    cfg = _base_cfg(arrangement="Bilateral")
    lums = build_luminaires(cfg, p, flux_scale=5.0)
    in_period = [lum for lum in lums if 0 <= lum.x0 < cfg["S"]]
    right_lum = [l for l in in_period if l.y0 > cfg["W"] / 2.0][0]
    assert right_lum.mirror_y == True
    left_lum = [l for l in in_period if l.y0 < cfg["W"] / 2.0][0]
    assert left_lum.mirror_y == False


def test_multi_element_ti_uses_absolute_luminaire_positions(monkeypatch):
    p = _load_clap_s_f2md_ldt()
    cfg = _base_cfg(
        arrangement="Bilateral Alternada", W=13.0, S=30.0, h=9.0, arm=0.0,
        road_elements=[
            {"type": "sidewalk", "width": 4.0, "y_start": 0.0, "y_end": 4.0, "pedestrian_class": "P4"},
            {"type": "carriageway", "width": 7.0, "y_start": 4.0, "y_end": 11.0, "lanes": 2, "lighting_class": "M3"},
            {"type": "sidewalk", "width": 2.0, "y_start": 11.0, "y_end": 13.0, "pedestrian_class": "P4"},
        ],
    )
    seen = []

    def fake_ti(luminaires, *args):
        seen.append(sorted({round(l.y0, 6) for l in luminaires}))
        return 0.0, 0.0

    monkeypatch.setattr(calc_module, "_ti_for_lane", fake_ti)

    evaluate(cfg, p, flux_scale=1.0)

    assert seen and all(ys == [4.0, 11.0] for ys in seen)


def test_multi_element_results_keep_source_order_and_metric_statuses():
    p = _load_clap_s_f2md_ldt()
    cfg = _base_cfg(
        arrangement="Lineal",
        road_elements=[
            {"type": "sidewalk", "width": 1.5, "y_start": 0.0, "y_end": 1.5, "pedestrian_class": "P4"},
            {"type": "carriageway", "width": 7.0, "y_start": 1.5, "y_end": 8.5, "lanes": 2, "lighting_class": "M3"},
            {"type": "sidewalk", "width": 1.5, "y_start": 8.5, "y_end": 10.0, "pedestrian_class": "P4"},
        ],
        W=10.0,
    )

    elements = evaluate(cfg, p, flux_scale=1.0)["_element_results"]

    assert [element["index"] for element in elements] == [0, 1, 2]
    assert set(elements[0]["criteria_passed"]) == {"Eavg", "Emin"}
    assert set(elements[1]["criteria_passed"]) == {"Lavg", "Uo", "Ul", "TI", "SR", "EIR"}
    assert elements[1]["criteria_required"]["Lavg"] == 1.0
    assert elements[1]["criteria_required"]["EIR"] == 0.5
    assert elements[0]["criteria_required"]["Eavg"] == 5.0


def test_central_doble_with_median_edge_strips():
    """Edge strips for sub-carriageways sample median on inner edges."""
    p = _load_ldt()
    cfg = _base_cfg(arrangement="Central Doble", median_width=1.0)
    lums = build_luminaires(cfg, p, flux_scale=5.0)
    splits = _carriageway_splits(cfg)
    for y_start, y_end in splits:
        inner_L, outer_L, inner_R, outer_R = _edge_strip_illuminances(
            cfg, p, flux_scale=5.0, _luminaires=lums,
            y_start=y_start, y_end=y_end)
        assert inner_L > 0
        assert inner_R > 0
        sr = (outer_L + outer_R) / (inner_L + inner_R)
        assert 0 < sr <= 1.0, f"SR={sr:.3f} out of expected range"


def test_single_lane_sr_uses_half_carriageway_strip_like_dialux():
    p = _load_clap_s_f2md_ldt()
    cfg = _base_cfg(arrangement="Lineal", W=3.5, S=16.0, h=4.0, arm=0.0, lanes=1, **{"class": "M4"})

    r = evaluate(cfg, p, flux_scale=2000.0 / p.flux, road="R3")

    assert r["Lavg"] == pytest.approx(0.95, abs=0.01)
    assert r["SR"] == pytest.approx(0.61, abs=0.02)


def test_positive_tilt_pitches_optic_toward_road():
    p = _load_clap_s_ldt()
    cfg_flat = _base_cfg(
        arrangement="Central Doble", W=9.0, S=20.0, h=10.0,
        arm=1.0, tilt=0.0, lanes=3, **{"class": "M1"},
    )
    cfg_tilt = dict(cfg_flat, tilt=5.0)
    r_flat = evaluate(cfg_flat, p, flux_scale=7798.1 / p.flux, road="R3")
    r_tilt = evaluate(cfg_tilt, p, flux_scale=7798.1 / p.flux, road="R3")
    assert r_tilt["SR"] > r_flat["SR"]


def test_positive_tilt_axis_intersects_road_side():
    p = _load_clap_s_ldt()
    cfg = _base_cfg(
        arrangement="Lineal",
        W=3.5,
        S=16.0,
        h=4.0,
        arm=0.0,
        tilt=10.0,
        pole_offset=1.0,
        pole_side="left",
    )

    left = build_luminaires(cfg, p)[0]
    left_inward_y = left.y0 + left.h * math.tan(math.radians(cfg["tilt"]))
    left_outward_y = left.y0 - left.h * math.tan(math.radians(cfg["tilt"]))
    _, _, left_inward_gamma = left._candela(
        *left._world_to_lum_frame(0.0, left_inward_y - left.y0)
    )
    _, _, left_outward_gamma = left._candela(
        *left._world_to_lum_frame(0.0, left_outward_y - left.y0)
    )

    assert left_inward_gamma == pytest.approx(0.0, abs=1e-9)
    assert left_outward_gamma > left_inward_gamma

    right_cfg = {**cfg, "pole_side": "right"}
    right = build_luminaires(right_cfg, p)[0]
    right_inward_y = right.y0 - right.h * math.tan(math.radians(right_cfg["tilt"]))
    right_outward_y = right.y0 + right.h * math.tan(math.radians(right_cfg["tilt"]))
    _, _, right_inward_gamma = right._candela(
        *right._world_to_lum_frame(0.0, right_inward_y - right.y0)
    )
    _, _, right_outward_gamma = right._candela(
        *right._world_to_lum_frame(0.0, right_outward_y - right.y0)
    )

    assert right_inward_gamma == pytest.approx(0.0, abs=1e-9)
    assert right_outward_gamma > right_inward_gamma
