import pytest

from road_ldt_designer.road_ldt.domain import PhotometricCandidate
from road_ldt_designer.road_ldt.photometric_symmetry import (
    is_longitudinally_symmetric,
    longitudinal_mirror_c_deg,
    longitudinal_symmetry_error,
    symmetrize_longitudinal,
    validate_longitudinal_symmetry,
)


def _candidate(rows):
    return PhotometricCandidate(
        c_angles_deg=(0.0, 90.0, 180.0, 270.0),
        gamma_angles_deg=(0.0, 90.0),
        intensity_cd_per_klm=rows,
        flux_lm=1000.0,
    )


def test_longitudinal_mirror_angle_uses_perpendicular_road_plane():
    assert longitudinal_mirror_c_deg(0.0) == pytest.approx(180.0)
    assert longitudinal_mirror_c_deg(45.0) == pytest.approx(135.0)
    assert longitudinal_mirror_c_deg(90.0) == pytest.approx(90.0)
    assert longitudinal_mirror_c_deg(270.0) == pytest.approx(270.0)


def test_asymmetric_candidate_is_detected_and_rejected():
    candidate = _candidate(
        (
            (100.0, 200.0),
            (50.0, 50.0),
            (0.0, 100.0),
            (50.0, 50.0),
        )
    )

    absolute, relative = longitudinal_symmetry_error(candidate)

    assert absolute == pytest.approx(100.0)
    assert relative == pytest.approx(1.0)
    assert not is_longitudinally_symmetric(candidate)
    with pytest.raises(ValueError, match="no es simétrico"):
        validate_longitudinal_symmetry(candidate)


def test_symmetrization_averages_mirrored_planes():
    candidate = _candidate(
        (
            (100.0, 200.0),
            (50.0, 50.0),
            (0.0, 100.0),
            (25.0, 75.0),
        )
    )

    symmetric = symmetrize_longitudinal(candidate)

    assert symmetric.intensity_cd_per_klm[0] == pytest.approx((50.0, 150.0))
    assert symmetric.intensity_cd_per_klm[2] == pytest.approx((50.0, 150.0))
    assert symmetric.intensity_cd_per_klm[1] == pytest.approx((50.0, 50.0))
    assert symmetric.intensity_cd_per_klm[3] == pytest.approx((25.0, 75.0))
    assert is_longitudinally_symmetric(symmetric)


def test_symmetry_requires_mirrored_c_planes_in_candidate_grid():
    candidate = PhotometricCandidate(
        c_angles_deg=(0.0, 60.0, 180.0),
        gamma_angles_deg=(0.0, 90.0),
        intensity_cd_per_klm=((1.0, 1.0), (1.0, 1.0), (1.0, 1.0)),
        flux_lm=1000.0,
    )

    with pytest.raises(ValueError, match="falta C=120"):
        longitudinal_symmetry_error(candidate)
