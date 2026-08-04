import pytest

from road_ldt_designer.road_ldt.lighting_classes import (
    get_m_lighting_class,
    list_m_lighting_classes,
)


def test_en_13201_2015_m_class_catalogue_values():
    m1 = get_m_lighting_class("m1")
    m6 = get_m_lighting_class("M6")

    assert m1.luminance_avg_min_cd_m2 == pytest.approx(2.0)
    assert m1.uo_min == pytest.approx(0.40)
    assert m1.ul_min == pytest.approx(0.70)
    assert m1.ti_max_pct == pytest.approx(10.0)
    assert m1.rei_min == pytest.approx(0.35)
    assert m6.luminance_avg_min_cd_m2 == pytest.approx(0.30)
    assert m6.ti_max_pct == pytest.approx(20.0)


def test_m_class_can_omit_rei_when_adjacent_area_has_own_requirements():
    targets = get_m_lighting_class("M4").quality_targets(include_rei=False)

    assert targets.luminance_avg_min_cd_m2 == pytest.approx(0.75)
    assert targets.rei_min is None


def test_all_six_m_classes_are_listed():
    assert list_m_lighting_classes() == ("M1", "M2", "M3", "M4", "M5", "M6")


def test_unknown_m_class_is_rejected():
    with pytest.raises(ValueError, match="no disponible"):
        get_m_lighting_class("M7")
