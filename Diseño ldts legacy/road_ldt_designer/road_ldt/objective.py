"""Normalized constraint penalties for inverse photometric design."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .domain import NormativeProfile, OptimizationRequest, PhotometricCandidate
from .evaluator import CandidateEvaluation


@dataclass(frozen=True)
class ObjectiveWeights:
    constraint_weight: float = 1000.0
    peak_intensity_weight: float = 0.10
    smoothness_weight: float = 0.10
    high_angle_flux_weight: float = 2.0
    backlight_excess_weight: float = 0.50
    maximum_intensity_cd_per_klm: float = 1000.0
    preferred_high_angle_flux_fraction: float = 0.015
    permitted_backlight_fraction: float = 0.20


@dataclass(frozen=True)
class ConstraintPenalty:
    name: str
    actual: float | None
    limit: float
    sense: str
    normalized_violation: float


@dataclass(frozen=True)
class ObjectiveScore:
    total: float
    feasible: bool
    maximum_violation: float
    constraint_penalty: float
    peak_intensity_penalty: float
    smoothness_penalty: float
    high_angle_flux_penalty: float
    backlight_excess_penalty: float
    constraints: tuple[ConstraintPenalty, ...]

    @property
    def ranking_key(self) -> tuple[bool, float, float]:
        """Feasible candidates rank first, then violation and total score."""

        return (not self.feasible, self.maximum_violation, self.total)


def _minimum_penalty(
    name: str,
    actual: float | None,
    required: float | None,
) -> ConstraintPenalty | None:
    if required is None:
        return None
    violation = (
        2.0
        if actual is None
        else max(0.0, (required - actual) / max(abs(required), 1e-12))
    )
    return ConstraintPenalty(name, actual, required, "minimum", violation)


def _maximum_penalty(
    name: str,
    actual: float | None,
    limit: float | None,
) -> ConstraintPenalty | None:
    if limit is None:
        return None
    violation = (
        2.0
        if actual is None
        else max(0.0, (actual - limit) / max(abs(limit), 1e-12))
    )
    return ConstraintPenalty(name, actual, limit, "maximum", violation)


def _candidate_roughness(candidate: PhotometricCandidate) -> float:
    matrix = candidate.intensity_cd_per_klm
    maximum = max(max(row) for row in matrix)
    if maximum <= 0:
        return 0.0

    differences: list[float] = []
    c_count = len(matrix)
    gamma_count = len(matrix[0])
    for c_index in range(c_count):
        previous_row = matrix[(c_index - 1) % c_count]
        row = matrix[c_index]
        next_row = matrix[(c_index + 1) % c_count]
        for gamma_index in range(gamma_count):
            differences.append(
                abs(
                    previous_row[gamma_index]
                    - 2.0 * row[gamma_index]
                    + next_row[gamma_index]
                )
                / maximum
            )
        for gamma_index in range(1, gamma_count - 1):
            differences.append(
                abs(
                    row[gamma_index - 1]
                    - 2.0 * row[gamma_index]
                    + row[gamma_index + 1]
                )
                / maximum
            )
    return sum(differences) / len(differences)


def _zonal_flux_fractions(
    candidate: PhotometricCandidate,
) -> tuple[float, float]:
    """Return gamma>=80° and road-back-side fractions of integrated flux."""

    c_angles = candidate.c_angles_deg
    gamma_angles = candidate.gamma_angles_deg
    total = 0.0
    high_angle = 0.0
    backlight = 0.0
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
            if gamma_0_deg >= 80.0:
                high_angle += flux
            elif gamma_1_deg > 80.0:
                fraction = (gamma_1_deg - 80.0) / (
                    gamma_1_deg - gamma_0_deg
                )
                high_angle += flux * fraction
            if is_backlight:
                backlight += flux
    if total <= 0:
        return 1.0, 1.0
    return high_angle / total, backlight / total


def score_candidate(
    request: OptimizationRequest,
    candidate: PhotometricCandidate,
    evaluation: CandidateEvaluation,
    *,
    weights: ObjectiveWeights | None = None,
) -> ObjectiveScore:
    """Score hard photometric requirements and manufacturability terms."""

    selected = weights or ObjectiveWeights()
    metrics = evaluation.metrics
    targets = request.targets
    constraints: list[ConstraintPenalty] = []

    def add(item: ConstraintPenalty | None) -> None:
        if item is not None:
            constraints.append(item)

    add(_minimum_penalty("Lavg", metrics.luminance_avg_cd_m2, targets.luminance_avg_min_cd_m2))
    add(_minimum_penalty("Uo", metrics.uo, targets.uo_min))
    add(_minimum_penalty("Ul", metrics.ul, targets.ul_min))
    add(_maximum_penalty("TI", metrics.ti_pct, targets.ti_max_pct))

    if request.normative_profile == NormativeProfile.EN13201_2003:
        add(_minimum_penalty("SR", metrics.sr, targets.sr_min))
    elif targets.rei_min is not None:
        add(_minimum_penalty("REI", metrics.rei, targets.rei_min))
    elif targets.sr_min is not None:
        add(_minimum_penalty("SR", metrics.sr, targets.sr_min))

    if evaluation.options.evaluate_side_bands:
        for band in request.geometry.side_bands:
            actual = metrics.band_illuminance_lx.get(band.name)
            add(_minimum_penalty(f"band:{band.name}:min", actual, band.target_illuminance_min_lx))
            add(_maximum_penalty(f"band:{band.name}:max", actual, band.target_illuminance_max_lx))

    if evaluation.options.evaluate_intrusion:
        for building in request.geometry.buildings:
            add(
                _maximum_penalty(
                    f"facade:{building.name}",
                    metrics.building_vertical_illuminance_lx.get(building.name),
                    building.max_vertical_illuminance_lx,
                )
            )
            add(
                _maximum_penalty(
                    f"window:{building.name}",
                    metrics.building_window_illuminance_lx.get(building.name),
                    building.max_window_illuminance_lx,
                )
            )
        if metrics.building_vertical_illuminance_lx:
            add(
                _maximum_penalty(
                    "intrusion:vertical",
                    max(metrics.building_vertical_illuminance_lx.values()),
                    request.intrusion_limits.max_vertical_illuminance_lx,
                )
            )
        if metrics.building_window_illuminance_lx:
            add(
                _maximum_penalty(
                    "intrusion:window",
                    max(metrics.building_window_illuminance_lx.values()),
                    request.intrusion_limits.max_window_illuminance_lx,
                )
            )

    constraint_penalty = sum(
        item.normalized_violation**2 for item in constraints
    )
    maximum_violation = max(
        (item.normalized_violation for item in constraints),
        default=0.0,
    )
    maximum_intensity = max(
        max(row) for row in candidate.intensity_cd_per_klm
    )
    peak_excess = max(
        0.0,
        (
            maximum_intensity - selected.maximum_intensity_cd_per_klm
        )
        / selected.maximum_intensity_cd_per_klm,
    )
    peak_penalty = peak_excess**2
    smoothness_penalty = _candidate_roughness(candidate)
    high_angle_fraction, backlight_fraction = _zonal_flux_fractions(candidate)
    high_angle_penalty = max(
        0.0,
        high_angle_fraction - selected.preferred_high_angle_flux_fraction,
    ) ** 2
    backlight_penalty = max(
        0.0,
        backlight_fraction - selected.permitted_backlight_fraction,
    ) ** 2
    total = (
        selected.constraint_weight * constraint_penalty
        + selected.peak_intensity_weight * peak_penalty
        + selected.smoothness_weight * smoothness_penalty
        + selected.high_angle_flux_weight * high_angle_penalty
        + selected.backlight_excess_weight * backlight_penalty
    )
    return ObjectiveScore(
        total=total,
        feasible=maximum_violation <= 1e-12,
        maximum_violation=maximum_violation,
        constraint_penalty=constraint_penalty,
        peak_intensity_penalty=peak_penalty,
        smoothness_penalty=smoothness_penalty,
        high_angle_flux_penalty=high_angle_penalty,
        backlight_excess_penalty=backlight_penalty,
        constraints=tuple(constraints),
    )
