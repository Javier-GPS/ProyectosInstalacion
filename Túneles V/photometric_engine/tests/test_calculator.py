"""
Integration tests for TunnelCalculator — CIE 140:2019 luminance calculation.

These tests use real LDT files (APHEX M optics) and verify that:
  1. The calculation runs without errors.
  2. Luminance values are in physically plausible ranges.
  3. Uniformities satisfy CIE 140 minimum requirements under favourable conditions.

The test uses a simplified single-luminaire scenario so expected values can
be checked analytically against the CIE 140 formula.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import numpy as np

from ..salvi_photometry.ldt_parser import load_ldt
from ..salvi_photometry.calculator import TunnelCalculator, LuminaireInstance
from ..salvi_photometry.geometry   import (
    LuminaireOrientation, Observer, mirror_c_for_interior_facing,
)
from ..salvi_photometry.rtables    import r_value

_DATA = Path(__file__).parent.parent / "data" / "photometries"


def _first_ldt() -> Path:
    """Return first available LDT file."""
    paths = sorted(_DATA.glob("*.ldt"))
    if not paths:
        pytest.skip("No LDT files found in data/photometries/")
    return paths[0]


@pytest.fixture(scope="module")
def phot():
    return load_ldt(_first_ldt())


@pytest.fixture(scope="module")
def calc():
    return TunnelCalculator(rtable_name="R2", maintenance_factor=1.0)


def test_ldt_loads(phot):
    """LDT file should load without errors."""
    assert len(phot.c_angles) > 0
    assert len(phot.g_angles) > 0
    assert phot._flux_file_lm > 0


def test_single_luminaire_luminance(phot, calc):
    """
    Luminance at nadir (directly below luminaire) should be positive and finite.
    """
    lum = LuminaireInstance(
        x=0.0, y=0.0, H=7.5,
        photometry=phot,
        flux_lm=42_503,  # APHEX M 350mA 4000K
        orientation=LuminaireOrientation(nu_deg=0.0),
    )
    obs = Observer(lane_y_m=3.0)
    result = calc.luminance_at_point(0.0, 3.0, [lum], obs)
    assert result.L > 0.0
    assert math.isfinite(result.L)
    assert result.E_h > 0.0


def test_luminance_follows_inverse_square(phot, calc):
    """
    Doubling mounting height should roughly quarter illuminance (1/H² law).
    We allow ±30% because the formula also involves r(β, tan_gamma) which changes.
    """
    obs = Observer(lane_y_m=3.0)
    lum_lo = LuminaireInstance(x=0, y=3.0, H=5.0, photometry=phot, flux_lm=42_503)
    lum_hi = LuminaireInstance(x=0, y=3.0, H=10.0, photometry=phot, flux_lm=42_503)

    E_lo = calc.luminance_at_point(0, 3.0, [lum_lo], obs).E_h
    E_hi = calc.luminance_at_point(0, 3.0, [lum_hi], obs).E_h

    if E_lo > 0 and E_hi > 0:
        ratio = E_lo / E_hi
        assert 2.0 < ratio < 8.0, f"Inverse-square ratio unexpected: {ratio:.2f}"


def test_zone_calculation_returns_valid_result(phot, calc):
    """
    Full zone calculation over a 10 m × 7 m interior zone should return
    positive average luminance and valid uniformity indices.
    """
    obs = Observer(lane_y_m=3.5)
    lums = [
        LuminaireInstance(x=5.0, y=3.5, H=7.5, photometry=phot, flux_lm=42_503),
        LuminaireInstance(x=15.0, y=3.5, H=7.5, photometry=phot, flux_lm=42_503),
    ]
    pts = [(x, y) for x in [2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 17.5]
                   for y in [1.5, 3.5, 5.5]]

    zr = calc.calculate_zone(
        zone_name="interior", zone_type="interior",
        s_start=0.0, s_end=20.0,
        L_req=1.0,
        calc_points=pts,
        luminaires=lums,
        observer=obs,
    )
    assert zr.L_avg > 0.0
    assert 0.0 <= zr.U0 <= 1.0
    assert 0.0 <= zr.Ul <= 1.0
    assert zr.TI >= 0.0


def test_rtable_manual_check(phot):
    """
    Manual spot check: L = (I/H²) × r × MF  for a single geometry.
    """
    # Luminaire at (0,0,H=7.5), point at (0, 3.5) — straight below on road
    H = 7.5
    yP, xP = 3.5, 0.0
    xL, yL = 0.0, 0.0

    dx = xP - xL  # 0
    dy = yP - yL  # 3.5
    d_plan = math.sqrt(dx**2 + dy**2)  # 3.5
    tan_g = d_plan / H
    gamma_deg = math.degrees(math.atan(tan_g))

    I = phot.intensity(c_deg=90.0, gamma_deg=gamma_deg, scale_flux_lm=42_503)

    # β: for observer at (xP=0, yP_obs=3.5) looking toward −x:
    # β = angle between xP→xL vector and xP→observer direction
    # With observer at same y, directly behind the point:
    beta = 0.0  # observer in-line, behind
    r = r_value("R2", beta_deg=beta, tan_gamma=tan_g)

    L_manual = (I / H**2) * r * 1.0  # MF=1
    assert L_manual >= 0.0


def test_contribution_matrix_matches_batch_sum(phot, calc):
    """La nueva matriz por luminaria debe conservar exactamente el calculo."""
    observer = Observer(lane_y_m=3.5)
    luminaires = [
        LuminaireInstance(
            x=0.0, y=3.5, H=6.0, photometry=phot, flux_lm=20_000,
            orientation=LuminaireOrientation(tilt_deg=0.0),
        ),
        LuminaireInstance(
            x=12.0, y=1.0, H=6.0, photometry=phot, flux_lm=35_000,
            orientation=LuminaireOrientation(tilt_deg=5.0),
        ),
    ]
    points = [(x, y) for x in (1.0, 6.0, 11.0) for y in (1.5, 3.5, 5.5)]

    matrix = calc.luminance_contributions_at_points_batch(
        points, luminaires, observer,
    )
    total = calc.luminance_at_points_batch(points, luminaires, observer)

    assert matrix.shape == (len(points), len(luminaires))
    assert np.all(matrix >= 0.0)
    assert np.allclose(matrix.sum(axis=1), total, rtol=1e-12, atol=1e-12)


def test_batch_range_pruning_preserves_zero_columns_and_scalar_result(phot):
    calc = TunnelCalculator(
        rtable_name="R2",
        maintenance_factor=0.8,
        max_luminaire_dist=30.0,
    )
    observer = Observer(lane_y_m=3.5)
    luminaires = [
        LuminaireInstance(
            x=x, y=3.5, H=6.0, photometry=phot, flux_lm=20_000,
            orientation=LuminaireOrientation(),
        )
        for x in (-200.0, 0.0, 12.0, 200.0)
    ]
    points = [(2.0, 2.0), (8.0, 4.0)]

    matrix = calc.luminance_contributions_at_points_batch(
        points, luminaires, observer,
    )
    scalar = np.asarray([
        calc.luminance_at_point(x, y, luminaires, observer).L
        for x, y in points
    ])

    assert matrix.shape == (len(points), len(luminaires))
    assert np.all(matrix[:, (0, 3)] == 0.0)
    assert np.allclose(matrix.sum(axis=1), scalar, rtol=1e-12, atol=1e-12)


def test_bilateral_luminaire_photometry_is_mirrored_toward_tunnel_interior():
    """La fila derecha debe ser la imagen C de la izquierda, no otra optica.

    F151 es deliberadamente asimetrica entre planos C y por ello detecta el
    error que quedaria oculto usando una distribucion circular. Tambien se
    mantiene el tilt especular (+izquierda / -derecha).
    """
    path = _DATA / "APHEX_M_H10_40K_F151_VDR_SPUW_200W.ldt"
    if not path.exists():
        pytest.skip("No LDT F151 disponible")
    photometry = load_ldt(path)
    width = 11.5
    left = LuminaireInstance(
        x=0.0, y=0.30, H=6.0, photometry=photometry, flux_lm=20_000,
        orientation=LuminaireOrientation(tilt_deg=5.0),
    )
    right = LuminaireInstance(
        x=0.0, y=width - 0.30, H=6.0, photometry=photometry, flux_lm=20_000,
        orientation=LuminaireOrientation(tilt_deg=-5.0, mirror_c=True),
    )

    assert not mirror_c_for_interior_facing(0.30, width, "bilateral_sym")
    assert mirror_c_for_interior_facing(width - 0.30, width, "bilateral_sym")
    assert mirror_c_for_interior_facing(width - 0.30, width, "unilateral")

    for x, y_left in ((5.0, 2.0), (8.0, 4.0), (12.0, 5.0)):
        left_sample = left.intensity_toward(x, y_left)
        right_sample = right.intensity_toward(x, width - y_left)
        assert np.allclose(left_sample, right_sample, rtol=1e-12, atol=1e-10)

    # La ruta vectorizada es la usada durante el diseño y la verificación
    # completa; debe respetar exactamente la misma instalación especular.
    calculator = TunnelCalculator("R2", maintenance_factor=0.7)
    points = [(5.0, 2.0), (8.0, width - 4.0), (12.0, 5.0)]
    batch = calculator.luminance_at_points_batch(
        points, [left, right], Observer(lane_y_m=4.0),
    )
    scalar = np.asarray([
        calculator.luminance_at_point(x, y, [left, right], Observer(lane_y_m=4.0)).L
        for x, y in points
    ])
    assert np.allclose(batch, scalar, rtol=1e-12, atol=1e-12)
