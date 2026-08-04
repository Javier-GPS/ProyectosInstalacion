"""Descriptors and target-versus-physical comparison for road LDT files."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .candidate_generator import integrated_flux_lm_per_klm
from .direct_illuminance import intensity_cd_per_klm
from .domain import PhotometricCandidate
from .photometric_symmetry import (
    longitudinal_symmetry_error,
    symmetrize_longitudinal,
)


@dataclass(frozen=True)
class PhotometricDescriptor:
    peak_intensity_cd_per_klm: float
    peak_c_deg: float
    peak_gamma_deg: float
    gamma_width_90_deg: float
    gamma_fwhm_deg: float
    high_angle_flux_fraction: float
    upward_flux_fraction: float
    backlight_flux_fraction: float
    longitudinal_symmetry_error_pct: float


@dataclass(frozen=True)
class PhotometricComparison:
    normalized_rmse_pct: float
    normalized_mean_absolute_error_pct: float
    shape_correlation: float
    peak_c_shift_deg: float
    peak_gamma_shift_deg: float
    gamma_width_90_delta_deg: float
    gamma_fwhm_delta_deg: float
    high_angle_flux_delta_pct_points: float
    upward_flux_delta_pct_points: float
    backlight_flux_delta_pct_points: float


@dataclass(frozen=True)
class AngularResidualMap:
    """Signed physical-minus-target error on a compact common grid."""

    c_angles_deg: tuple[float, ...]
    gamma_angles_deg: tuple[float, ...]
    error_pct_of_target_peak: tuple[tuple[float, ...], ...]
    minimum_error_pct: float
    maximum_error_pct: float


@dataclass(frozen=True)
class CompensationResult:
    """Regularized pre-distorted target for the next optical iteration."""

    candidate: PhotometricCandidate
    correction_gain: float
    smoothing_passes: int
    clipped_low_fraction: float
    capped_high_fraction: float
    maximum_adjustment_pct_of_target_peak: float
    integrated_flux_lm_per_klm: float


def _contiguous_gamma_width(
    candidate: PhotometricCandidate,
    c_index: int,
    peak_gamma_index: int,
    peak_value: float,
    fraction: float,
) -> float:
    row = candidate.intensity_cd_per_klm[c_index]
    threshold = peak_value * fraction
    lower = peak_gamma_index
    upper = peak_gamma_index
    while lower > 0 and row[lower - 1] >= threshold:
        lower -= 1
    while upper + 1 < len(row) and row[upper + 1] >= threshold:
        upper += 1
    return (
        candidate.gamma_angles_deg[upper]
        - candidate.gamma_angles_deg[lower]
    )


def _zonal_fluxes(
    candidate: PhotometricCandidate,
) -> tuple[float, float, float, float]:
    total = 0.0
    high_angle = 0.0
    upward = 0.0
    backlight = 0.0
    c_angles = candidate.c_angles_deg
    gamma_angles = candidate.gamma_angles_deg
    for c_index, c_deg in enumerate(c_angles):
        next_c = (
            c_angles[c_index + 1]
            if c_index + 1 < len(c_angles)
            else c_angles[0] + 360.0
        )
        delta_c = math.radians(next_c - c_deg)
        is_backlight = 180.0 < (c_deg % 360.0) < 360.0
        for gamma_index in range(len(gamma_angles) - 1):
            gamma_0_deg = gamma_angles[gamma_index]
            gamma_1_deg = gamma_angles[gamma_index + 1]
            gamma_0 = math.radians(gamma_0_deg)
            gamma_1 = math.radians(gamma_1_deg)
            value_0 = (
                candidate.intensity_cd_per_klm[c_index][gamma_index]
                * math.sin(gamma_0)
            )
            value_1 = (
                candidate.intensity_cd_per_klm[c_index][gamma_index + 1]
                * math.sin(gamma_1)
            )
            flux = (
                0.5
                * (value_0 + value_1)
                * (gamma_1 - gamma_0)
                * delta_c
            )
            total += flux
            midpoint = (gamma_0_deg + gamma_1_deg) / 2.0
            if 80.0 <= midpoint <= 90.0:
                high_angle += flux
            if midpoint > 90.0:
                upward += flux
            if is_backlight and midpoint <= 90.0:
                backlight += flux
    return total, high_angle, upward, backlight


def describe_photometry(
    candidate: PhotometricCandidate,
) -> PhotometricDescriptor:
    """Describe peak sharpness, zonal flux and required symmetry."""

    downward_indices = tuple(
        index
        for index, gamma in enumerate(candidate.gamma_angles_deg)
        if gamma <= 90.0
    )
    if not downward_indices:
        raise ValueError("el LDT no contiene ángulos gamma descendentes")
    peak_value, peak_c_index, peak_gamma_index = max(
        (
            float(candidate.intensity_cd_per_klm[c_index][gamma_index]),
            c_index,
            gamma_index,
        )
        for c_index in range(len(candidate.c_angles_deg))
        for gamma_index in downward_indices
    )
    total, high_angle, upward, backlight = _zonal_fluxes(candidate)
    if total <= 0:
        raise ValueError("el LDT no contiene flujo fotométrico integrable")
    _, symmetry_relative = longitudinal_symmetry_error(candidate)
    return PhotometricDescriptor(
        peak_intensity_cd_per_klm=peak_value,
        peak_c_deg=candidate.c_angles_deg[peak_c_index],
        peak_gamma_deg=candidate.gamma_angles_deg[peak_gamma_index],
        gamma_width_90_deg=_contiguous_gamma_width(
            candidate,
            peak_c_index,
            peak_gamma_index,
            peak_value,
            0.90,
        ),
        gamma_fwhm_deg=_contiguous_gamma_width(
            candidate,
            peak_c_index,
            peak_gamma_index,
            peak_value,
            0.50,
        ),
        high_angle_flux_fraction=high_angle / total,
        upward_flux_fraction=upward / total,
        backlight_flux_fraction=backlight / total,
        longitudinal_symmetry_error_pct=symmetry_relative * 100.0,
    )


def _normalized_samples(
    candidate: PhotometricCandidate,
) -> tuple[float, ...]:
    values = tuple(
        intensity_cd_per_klm(candidate, float(c_deg), float(gamma_deg))
        for c_deg in range(0, 360, 5)
        for gamma_deg in range(0, 91)
    )
    maximum = max(values, default=0.0)
    if maximum <= 0:
        raise ValueError("el LDT no contiene intensidad descendente")
    return tuple(value / maximum for value in values)


def _correlation(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    covariance = sum(
        (a - first_mean) * (b - second_mean)
        for a, b in zip(first, second)
    )
    first_energy = sum((value - first_mean) ** 2 for value in first)
    second_energy = sum((value - second_mean) ** 2 for value in second)
    denominator = math.sqrt(first_energy * second_energy)
    return covariance / denominator if denominator > 0 else 0.0


def _circular_signed_difference(first: float, second: float) -> float:
    return (first - second + 180.0) % 360.0 - 180.0


def compare_photometries(
    target: PhotometricCandidate,
    physical: PhotometricCandidate,
) -> PhotometricComparison:
    """Compare normalized shapes on a common 5° C × 1° gamma grid."""

    target_descriptor = describe_photometry(target)
    physical_descriptor = describe_photometry(physical)
    target_samples = _normalized_samples(target)
    physical_samples = _normalized_samples(physical)
    differences = tuple(
        physical_value - target_value
        for target_value, physical_value in zip(
            target_samples,
            physical_samples,
        )
    )
    return PhotometricComparison(
        normalized_rmse_pct=(
            math.sqrt(sum(value * value for value in differences) / len(differences))
            * 100.0
        ),
        normalized_mean_absolute_error_pct=(
            sum(abs(value) for value in differences)
            / len(differences)
            * 100.0
        ),
        shape_correlation=_correlation(target_samples, physical_samples),
        peak_c_shift_deg=_circular_signed_difference(
            physical_descriptor.peak_c_deg,
            target_descriptor.peak_c_deg,
        ),
        peak_gamma_shift_deg=(
            physical_descriptor.peak_gamma_deg
            - target_descriptor.peak_gamma_deg
        ),
        gamma_width_90_delta_deg=(
            physical_descriptor.gamma_width_90_deg
            - target_descriptor.gamma_width_90_deg
        ),
        gamma_fwhm_delta_deg=(
            physical_descriptor.gamma_fwhm_deg
            - target_descriptor.gamma_fwhm_deg
        ),
        high_angle_flux_delta_pct_points=(
            physical_descriptor.high_angle_flux_fraction
            - target_descriptor.high_angle_flux_fraction
        )
        * 100.0,
        upward_flux_delta_pct_points=(
            physical_descriptor.upward_flux_fraction
            - target_descriptor.upward_flux_fraction
        )
        * 100.0,
        backlight_flux_delta_pct_points=(
            physical_descriptor.backlight_flux_fraction
            - target_descriptor.backlight_flux_fraction
        )
        * 100.0,
    )


def angular_residual_map(
    target: PhotometricCandidate,
    physical: PhotometricCandidate,
    *,
    c_step_deg: int = 5,
    gamma_step_deg: int = 2,
) -> AngularResidualMap:
    """Return physical minus target error as percent of target peak intensity."""

    if c_step_deg <= 0 or 360 % c_step_deg:
        raise ValueError("c_step_deg debe dividir exactamente 360°")
    if gamma_step_deg <= 0 or 90 % gamma_step_deg:
        raise ValueError("gamma_step_deg debe dividir exactamente 90°")
    descriptor = describe_photometry(target)
    target_peak = descriptor.peak_intensity_cd_per_klm
    c_angles = tuple(float(value) for value in range(0, 360, c_step_deg))
    gamma_angles = tuple(
        float(value) for value in range(0, 91, gamma_step_deg)
    )
    rows = tuple(
        tuple(
            (
                intensity_cd_per_klm(physical, c_deg, gamma_deg)
                - intensity_cd_per_klm(target, c_deg, gamma_deg)
            )
            / target_peak
            * 100.0
            for gamma_deg in gamma_angles
        )
        for c_deg in c_angles
    )
    values = tuple(value for row in rows for value in row)
    return AngularResidualMap(
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        error_pct_of_target_peak=rows,
        minimum_error_pct=min(values),
        maximum_error_pct=max(values),
    )


def _smooth_downward_rows(
    rows: tuple[tuple[float, ...], ...],
    downward_count: int,
    passes: int,
) -> tuple[tuple[float, ...], ...]:
    current = [list(row) for row in rows]
    c_count = len(current)
    for _ in range(passes):
        across_c = [row[:] for row in current]
        for c_index in range(c_count):
            previous = current[(c_index - 1) % c_count]
            center = current[c_index]
            following = current[(c_index + 1) % c_count]
            for gamma_index in range(downward_count):
                across_c[c_index][gamma_index] = (
                    0.25 * previous[gamma_index]
                    + 0.50 * center[gamma_index]
                    + 0.25 * following[gamma_index]
                )
        next_rows = [row[:] for row in across_c]
        for c_index in range(c_count):
            for gamma_index in range(downward_count):
                lower = max(0, gamma_index - 1)
                upper = min(downward_count - 1, gamma_index + 1)
                next_rows[c_index][gamma_index] = (
                    0.25 * across_c[c_index][lower]
                    + 0.50 * across_c[c_index][gamma_index]
                    + 0.25 * across_c[c_index][upper]
                )
        current = next_rows
    return tuple(tuple(row) for row in current)


def _candidate_with_rows(
    target: PhotometricCandidate,
    rows: tuple[tuple[float, ...], ...],
) -> PhotometricCandidate:
    return replace(
        target,
        intensity_cd_per_klm=rows,
        luminaire_name="SALVI Compensated Optical Target",
        metadata={
            **target.metadata,
            "generator": "target-physical-residual-compensation-v1",
        },
    )


def compensate_target(
    target: PhotometricCandidate,
    physical: PhotometricCandidate,
    *,
    correction_gain: float = 0.60,
    smoothing_passes: int = 2,
    maximum_peak_multiplier: float = 2.50,
) -> CompensationResult:
    """Create the next optical target under an additive-error assumption.

    The physical-minus-target residual is smoothed, subtracted with a
    configurable gain, mirrored to the required road symmetry and normalized
    to the original integrated flux. This is a controlled next-iteration
    specification, not a prediction of the manufactured lens.
    """

    gain = float(correction_gain)
    if not 0.0 <= gain <= 1.0:
        raise ValueError("correction_gain debe estar entre 0 y 1")
    if int(smoothing_passes) != smoothing_passes or not 0 <= smoothing_passes <= 5:
        raise ValueError("smoothing_passes debe ser un entero entre 0 y 5")
    if maximum_peak_multiplier <= 1.0:
        raise ValueError("maximum_peak_multiplier debe ser mayor que 1")

    target_descriptor = describe_photometry(target)
    target_peak = target_descriptor.peak_intensity_cd_per_klm
    downward_count = sum(
        1 for gamma_deg in target.gamma_angles_deg if gamma_deg <= 90.0
    )
    raw_residual_rows = tuple(
        tuple(
            (
                intensity_cd_per_klm(
                    physical,
                    float(c_deg),
                    float(gamma_deg),
                )
                - float(target.intensity_cd_per_klm[c_index][gamma_index])
                if gamma_index < downward_count
                else 0.0
            )
            for gamma_index, gamma_deg in enumerate(target.gamma_angles_deg)
        )
        for c_index, c_deg in enumerate(target.c_angles_deg)
    )
    residual_rows = _smooth_downward_rows(
        raw_residual_rows,
        downward_count,
        int(smoothing_passes),
    )
    raw_corrected: list[tuple[float, ...]] = []
    clipped_low = 0
    downward_cells = len(target.c_angles_deg) * downward_count
    maximum_adjustment = 0.0
    for c_index, target_row in enumerate(target.intensity_cd_per_klm):
        row: list[float] = []
        for gamma_index, target_value in enumerate(target_row):
            if gamma_index < downward_count:
                adjustment = -gain * residual_rows[c_index][gamma_index]
                corrected = float(target_value) + adjustment
                maximum_adjustment = max(maximum_adjustment, abs(adjustment))
                if corrected < 0.0:
                    clipped_low += 1
                    corrected = 0.0
            else:
                corrected = float(target_value)
            row.append(corrected)
        raw_corrected.append(tuple(row))

    symmetric = symmetrize_longitudinal(
        _candidate_with_rows(target, tuple(raw_corrected))
    )
    target_flux = integrated_flux_lm_per_klm(target)
    if target_flux <= 0:
        raise ValueError("el LDT objetivo no contiene flujo integrable")
    cap = maximum_peak_multiplier * target_peak
    base_rows = symmetric.intensity_cd_per_klm

    def scaled_candidate(scale: float) -> PhotometricCandidate:
        return _candidate_with_rows(
            symmetric,
            tuple(
                tuple(min(float(value) * scale, cap) for value in row)
                for row in base_rows
            ),
        )

    lower_scale = 0.0
    upper_scale = 1.0
    while (
        integrated_flux_lm_per_klm(scaled_candidate(upper_scale))
        < target_flux
        and upper_scale < 1024.0
    ):
        upper_scale *= 2.0
    if upper_scale >= 1024.0:
        raise ValueError("la compensación no puede conservar el flujo objetivo")
    for _ in range(36):
        middle = (lower_scale + upper_scale) / 2.0
        if integrated_flux_lm_per_klm(scaled_candidate(middle)) < target_flux:
            lower_scale = middle
        else:
            upper_scale = middle
    corrected_candidate = symmetrize_longitudinal(
        scaled_candidate(upper_scale)
    )
    capped_high = sum(
        1
        for row in corrected_candidate.intensity_cd_per_klm
        for value in row[:downward_count]
        if math.isclose(value, cap, rel_tol=1e-8, abs_tol=1e-8)
    )
    final_flux = integrated_flux_lm_per_klm(corrected_candidate)
    return CompensationResult(
        candidate=corrected_candidate,
        correction_gain=gain,
        smoothing_passes=int(smoothing_passes),
        clipped_low_fraction=clipped_low / downward_cells,
        capped_high_fraction=capped_high / downward_cells,
        maximum_adjustment_pct_of_target_peak=(
            maximum_adjustment / target_peak * 100.0
        ),
        integrated_flux_lm_per_klm=final_flux,
    )
