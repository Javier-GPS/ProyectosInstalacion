import pytest

from road_ldt_designer.road_ldt.rtables import list_tables, r_value


def test_exact_r2_values_use_physical_scale():
    assert r_value("R2", 0.0, 0.0) == pytest.approx(0.0390)
    assert r_value("r2", 0.0, 0.25) == pytest.approx(0.0411)


def test_rtable_interpolates_between_beta_and_tan_epsilon():
    expected_raw = (390.0 + 390.0 + 411.0 + 411.0) / 4.0
    assert r_value("R2", 1.0, 0.125) == pytest.approx(expected_raw / 10_000.0)


def test_rtable_clamps_outside_its_domain():
    assert r_value("R2", -20.0, -1.0) == pytest.approx(0.0390)
    assert r_value("R2", 200.0, 8.0) == pytest.approx(0.0017)


def test_standard_tables_are_available():
    assert list_tables() == ("R1", "R2", "R3", "R4")


def test_unknown_rtable_is_rejected():
    with pytest.raises(ValueError, match="no disponible"):
        r_value("RX", 0.0, 0.0)
