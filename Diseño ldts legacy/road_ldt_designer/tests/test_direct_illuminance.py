import math

import pytest

from road_ldt_designer.road_ldt.direct_illuminance import (
    direct_illuminance_at_point,
    direct_illuminance_from_luminaire,
    intensity_cd_per_klm,
    photometric_angles,
)
from road_ldt_designer.road_ldt.domain import (
    LuminairePlacement,
    PhotometricCandidate,
)
from road_ldt_designer.road_ldt.street_geometry import CalculationPoint


def _constant_candidate(intensity_cd_per_klm_value: float = 100.0):
    return PhotometricCandidate(
        c_angles_deg=(0.0, 90.0, 180.0, 270.0),
        gamma_angles_deg=(0.0, 45.0, 90.0, 135.0, 180.0),
        intensity_cd_per_klm=tuple(
            tuple(intensity_cd_per_klm_value for _ in range(5))
            for _ in range(4)
        ),
        flux_lm=1000.0,
    )


def _point(x, y, z, normal):
    return CalculationPoint(
        x_m=x,
        y_m=y,
        z_m=z,
        normal_x=normal[0],
        normal_y=normal[1],
        normal_z=normal[2],
        surface_name="test",
        surface_kind="test",
    )


def test_bilinear_interpolation_wraps_between_last_and_first_c_plane():
    candidate = PhotometricCandidate(
        c_angles_deg=(0.0, 90.0, 180.0, 270.0),
        gamma_angles_deg=(0.0, 90.0),
        intensity_cd_per_klm=(
            (100.0, 100.0),
            (0.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
        ),
        flux_lm=1000.0,
    )

    assert intensity_cd_per_klm(candidate, 315.0, 45.0) == pytest.approx(50.0)
    assert intensity_cd_per_klm(candidate, 45.0, 45.0) == pytest.approx(50.0)


def test_nadir_horizontal_illuminance_matches_inverse_square_law():
    candidate = _constant_candidate()
    luminaire = LuminairePlacement(0.0, 0.0, 10.0, 1000.0)
    point = _point(0.0, 0.0, 0.0, (0.0, 0.0, 1.0))

    angles = photometric_angles(luminaire, point)
    illuminance = direct_illuminance_from_luminaire(candidate, luminaire, point)

    assert angles.gamma_deg == pytest.approx(0.0)
    assert illuminance == pytest.approx(1.0)


def test_oblique_horizontal_illuminance_includes_incidence_cosine():
    candidate = _constant_candidate()
    luminaire = LuminairePlacement(0.0, 0.0, 10.0, 1000.0)
    point = _point(10.0, 0.0, 0.0, (0.0, 0.0, 1.0))

    illuminance = direct_illuminance_from_luminaire(candidate, luminaire, point)
    expected = 100.0 * (10.0 / math.sqrt(200.0)) / 200.0

    assert illuminance == pytest.approx(expected)


def test_facade_receives_light_only_when_its_normal_faces_the_luminaire():
    candidate = _constant_candidate()
    luminaire = LuminairePlacement(0.0, 0.0, 10.0, 1000.0)
    facing = _point(0.0, 10.0, 5.0, (0.0, -1.0, 0.0))
    away = _point(0.0, 10.0, 5.0, (0.0, 1.0, 0.0))

    facing_e = direct_illuminance_from_luminaire(candidate, luminaire, facing)
    away_e = direct_illuminance_from_luminaire(candidate, luminaire, away)

    assert facing_e > 0.0
    assert away_e == 0.0


def test_multiple_luminaires_and_maintenance_factor_are_summed():
    candidate = _constant_candidate()
    luminaires = (
        LuminairePlacement(0.0, 0.0, 10.0, 1000.0),
        LuminairePlacement(0.0, 0.0, 10.0, 1000.0),
    )
    point = _point(0.0, 0.0, 0.0, (0.0, 0.0, 1.0))

    illuminance = direct_illuminance_at_point(
        candidate,
        luminaires,
        point,
        maintenance_factor=0.80,
    )

    assert illuminance == pytest.approx(1.60)
