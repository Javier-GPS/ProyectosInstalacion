import pytest

from road_ldt_designer.road_ldt.candidate_generator import (
    DEFAULT_RESOLUTION_STAGES,
    PhotometricFamilyParameters,
    generate_symmetric_candidate,
)
from road_ldt_designer.road_ldt.eulumdat import (
    candidate_from_ldt_text,
    candidate_to_ldt,
)
from road_ldt_designer.road_ldt.photometric_symmetry import (
    is_longitudinally_symmetric,
)


def test_generated_candidate_survives_ldt_round_trip():
    original = generate_symmetric_candidate(
        PhotometricFamilyParameters(flux_lm=12500.0),
        resolution=DEFAULT_RESOLUTION_STAGES[0],
    )

    imported = candidate_from_ldt_text(candidate_to_ldt(original, "test.ldt"))

    assert imported.c_angles_deg == original.c_angles_deg
    assert imported.gamma_angles_deg == original.gamma_angles_deg
    assert imported.flux_lm == pytest.approx(12500.0)
    assert is_longitudinally_symmetric(imported)
    for imported_row, original_row in zip(
        imported.intensity_cd_per_klm,
        original.intensity_cd_per_klm,
    ):
        assert imported_row == pytest.approx(original_row, rel=1e-7)


def test_writer_uses_standard_eulumdat_lamp_set_positions():
    candidate = generate_symmetric_candidate(
        PhotometricFamilyParameters(flux_lm=12500.0),
        resolution=DEFAULT_RESOLUTION_STAGES[0],
    )
    lines = candidate_to_ldt(candidate, "test.ldt").splitlines()

    assert lines[24] == "0"  # L25 tilt
    assert lines[25] == "1"  # L26 lamp sets
    assert lines[26] == "1"  # L26a lamps in the set
    assert lines[28] == "12500"  # L26c total luminous flux
    assert lines[42] == "0"  # first C angle after the ten direct ratios


def test_reader_expands_both_plane_symmetry_from_standard_storage():
    lines = [
        "SALVI",
        "3",
        "4",
        "4",
        "90",
        "3",
        "45",
        "test",
        "symmetric fixture",
        "",
        "fixture.ldt",
        "2026-07-26",
        *(["100"] * 5),
        *(["0"] * 4),
        "0",
        "100",
        "1",
        "0",
        "1",
        "1",
        "LED",
        "1000",
        "4000K",
        "80",
        "10",
        *(["0"] * 10),
        "0",
        "90",
        "180",
        "270",
        "0",
        "45",
        "90",
        # Isym=4 stores only C0 and C90 intensity rows.
        "10",
        "20",
        "30",
        "40",
        "50",
        "60",
    ]

    imported = candidate_from_ldt_text("\n".join(lines) + "\n")

    assert imported.c_angles_deg == (0.0, 90.0, 180.0, 270.0)
    assert imported.intensity_cd_per_klm == (
        (10.0, 20.0, 30.0),
        (40.0, 50.0, 60.0),
        (10.0, 20.0, 30.0),
        (40.0, 50.0, 60.0),
    )
    assert imported.metadata["original_symmetry"] == 4


def test_reader_accepts_blank_photopia_lamp_text_fields():
    candidate = generate_symmetric_candidate(
        PhotometricFamilyParameters(flux_lm=12500.0),
        resolution=DEFAULT_RESOLUTION_STAGES[0],
    )
    lines = candidate_to_ldt(
        candidate,
        "photopia-blank-fields.ldt",
    ).splitlines()
    lines[27] = ""  # lamp type
    lines[29] = ""  # colour/CCT
    lines[30] = ""  # CRI

    imported = candidate_from_ldt_text("\n".join(lines) + "\n")

    assert imported.flux_lm == pytest.approx(candidate.flux_lm)
    assert imported.c_angles_deg == candidate.c_angles_deg
    assert imported.gamma_angles_deg == candidate.gamma_angles_deg


def test_truncated_ldt_is_rejected():
    with pytest.raises(ValueError, match="incompleto"):
        candidate_from_ldt_text("SALVI\n1\n")
