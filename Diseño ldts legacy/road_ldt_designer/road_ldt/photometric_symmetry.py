"""Longitudinal mirror symmetry for road-lighting photometry.

The road axis is the local x axis and C=0 degrees points along +x. Reflection
in the vertical plane perpendicular to the road maps C to 180-C.
"""
from __future__ import annotations

import math
from dataclasses import replace

from .domain import PhotometricCandidate


def longitudinal_mirror_c_deg(c_deg: float) -> float:
    """Return the C angle mirrored front-to-back along the road."""

    return (180.0 - float(c_deg)) % 360.0


def _mirror_index(candidate: PhotometricCandidate, c_deg: float) -> int:
    target = longitudinal_mirror_c_deg(c_deg)
    for index, candidate_c in enumerate(candidate.c_angles_deg):
        if math.isclose(candidate_c % 360.0, target, abs_tol=1e-9):
            return index
    raise ValueError(
        "la malla C debe contener cada plano y su reflejo longitudinal; "
        f"falta C={target:g}°"
    )


def longitudinal_symmetry_error(
    candidate: PhotometricCandidate,
) -> tuple[float, float]:
    """Return maximum absolute and relative front/back intensity errors."""

    maximum_absolute = 0.0
    maximum_relative = 0.0
    for c_index, c_deg in enumerate(candidate.c_angles_deg):
        mirror_index = _mirror_index(candidate, c_deg)
        for gamma_index in range(len(candidate.gamma_angles_deg)):
            value = float(candidate.intensity_cd_per_klm[c_index][gamma_index])
            mirrored = float(
                candidate.intensity_cd_per_klm[mirror_index][gamma_index]
            )
            absolute = abs(value - mirrored)
            scale = max(abs(value), abs(mirrored), 1e-12)
            maximum_absolute = max(maximum_absolute, absolute)
            maximum_relative = max(maximum_relative, absolute / scale)
    return maximum_absolute, maximum_relative


def is_longitudinally_symmetric(
    candidate: PhotometricCandidate,
    *,
    absolute_tolerance_cd_per_klm: float = 1e-6,
    relative_tolerance: float = 1e-6,
) -> bool:
    """Check the front/back symmetry required by the design space."""

    absolute, relative = longitudinal_symmetry_error(candidate)
    return (
        absolute <= absolute_tolerance_cd_per_klm
        or relative <= relative_tolerance
    )


def validate_longitudinal_symmetry(
    candidate: PhotometricCandidate,
    *,
    absolute_tolerance_cd_per_klm: float = 1e-6,
    relative_tolerance: float = 1e-6,
) -> None:
    """Reject a candidate that violates the project symmetry constraint."""

    absolute, relative = longitudinal_symmetry_error(candidate)
    if (
        absolute > absolute_tolerance_cd_per_klm
        and relative > relative_tolerance
    ):
        raise ValueError(
            "el LDT no es simétrico respecto al plano perpendicular a la vía "
            f"(error máximo {absolute:.6g} cd/klm; {relative:.3%})"
        )


def symmetrize_longitudinal(
    candidate: PhotometricCandidate,
) -> PhotometricCandidate:
    """Average every C plane with its longitudinal mirror plane."""

    rows: list[tuple[float, ...]] = []
    for c_index, c_deg in enumerate(candidate.c_angles_deg):
        mirror_index = _mirror_index(candidate, c_deg)
        rows.append(
            tuple(
                (
                    float(candidate.intensity_cd_per_klm[c_index][gamma_index])
                    + float(
                        candidate.intensity_cd_per_klm[mirror_index][gamma_index]
                    )
                )
                / 2.0
                for gamma_index in range(len(candidate.gamma_angles_deg))
            )
        )
    metadata = dict(candidate.metadata)
    metadata["longitudinal_symmetry"] = "perpendicular-road-plane"
    return replace(
        candidate,
        intensity_cd_per_klm=tuple(rows),
        metadata=metadata,
    )
