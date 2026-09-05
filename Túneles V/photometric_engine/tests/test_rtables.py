"""
Tests for CIE 144 r-table interpolation.
"""
import pytest
from ..salvi_photometry.rtables import r_value, TABLES, METADATA


def test_r2_at_known_point():
    """R2 table: at β=0°, tan_gamma=0 → r should be 0.0 (or clipped minimum)."""
    r = r_value("R2", beta_deg=0.0, tan_gamma=0.0)
    assert r >= 0.0


def test_r2_peak():
    """R2 table: peak r should be near β=0°, tan_gamma~0.25."""
    r_peak = r_value("R2", beta_deg=0.0, tan_gamma=0.25)
    r_high = r_value("R2", beta_deg=90.0, tan_gamma=2.0)
    # Peak should be significantly higher than a far-off-axis value
    assert r_peak > r_high


def test_clamp_beta():
    """Values outside β range should be clamped, not raise errors."""
    r_neg = r_value("R2", beta_deg=-10.0, tan_gamma=0.5)
    r_pos = r_value("R2", beta_deg=200.0, tan_gamma=0.5)
    assert r_neg >= 0.0
    assert r_pos >= 0.0


def test_clamp_tan_gamma():
    """tan_gamma > 4.0 should be clamped to last row."""
    r_clamped = r_value("R2", beta_deg=0.0, tan_gamma=10.0)
    r_max = r_value("R2", beta_deg=0.0, tan_gamma=4.0)
    assert abs(r_clamped - r_max) < 1e-9


def test_all_tables_exist():
    """All standard CIE 144 tables should be present."""
    for name in ["C1", "C2", "R1", "R2", "R3", "R4", "N1", "N2", "N3", "N4"]:
        assert name in TABLES, f"Table {name} missing"
        assert name in METADATA, f"Metadata for {name} missing"


def test_qd_values():
    """Spot-check Qd (diffuse luminance coefficient) from metadata."""
    # R2: Qd = 0.057 per CIE 144:2001 Table B2
    assert abs(METADATA["R2"]["Qd"] - 0.057) < 0.01


def test_r_value_positive():
    """r-values should always be non-negative."""
    for table in TABLES:
        for beta in [0, 10, 45, 90, 135, 180]:
            for tg in [0, 0.5, 1.0, 2.0, 4.0]:
                r = r_value(table, beta, tg)
                assert r >= 0.0, f"Negative r in {table} β={beta} tg={tg}: {r}"
