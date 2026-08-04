"""Parametric generation of longitudinally symmetric road-lighting I-tables."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Sequence

from .domain import PhotometricCandidate
from .photometric_symmetry import validate_longitudinal_symmetry


@dataclass(frozen=True)
class PhotometricFamilyParameters:
    """Compact design variables for the first inverse-design search space."""

    peak_c_deg: float = 60.0
    peak_gamma_deg: float = 65.0
    c_spread_deg: float = 25.0
    gamma_spread_deg: float = 15.0
    gamma_outer_spread_deg: float = 9.0
    crest_weight: float = 0.35
    crest_spread_deg: float = 5.0
    nadir_weight: float = 0.15
    nadir_power: float = 2.0
    cross_weight: float = 0.25
    cross_gamma_deg: float = 50.0
    cross_c_spread_deg: float = 35.0
    cross_gamma_spread_deg: float = 18.0
    cutoff_start_deg: float = 80.0
    cutoff_end_deg: float = 90.0
    c_step_deg: float = 5.0
    gamma_step_deg: float = 2.5
    flux_lm: float = 1000.0
    luminaire_name: str = "SALVI symmetric road candidate"

    def __post_init__(self) -> None:
        if not 0.0 <= self.peak_c_deg <= 180.0:
            raise ValueError("peak_c_deg debe estar entre 0 y 180")
        if not 0.0 <= self.peak_gamma_deg <= 90.0:
            raise ValueError("peak_gamma_deg debe estar entre 0 y 90")
        if (
            self.c_spread_deg <= 0
            or self.gamma_spread_deg <= 0
            or self.gamma_outer_spread_deg <= 0
        ):
            raise ValueError("las anchuras angulares deben ser positivas")
        if self.crest_weight < 0:
            raise ValueError("crest_weight no puede ser negativo")
        if self.crest_spread_deg <= 0:
            raise ValueError("crest_spread_deg debe ser positivo")
        if self.nadir_weight < 0:
            raise ValueError("nadir_weight no puede ser negativo")
        if self.nadir_power < 0:
            raise ValueError("nadir_power no puede ser negativo")
        if self.cross_weight < 0:
            raise ValueError("cross_weight no puede ser negativo")
        if not 0.0 <= self.cross_gamma_deg <= 90.0:
            raise ValueError("cross_gamma_deg debe estar entre 0 y 90")
        if self.cross_c_spread_deg <= 0 or self.cross_gamma_spread_deg <= 0:
            raise ValueError("las anchuras del lóbulo transversal deben ser positivas")
        if not 0.0 <= self.cutoff_start_deg < self.cutoff_end_deg <= 180.0:
            raise ValueError("los ángulos de corte no son válidos")
        if self.c_step_deg <= 0 or self.gamma_step_deg <= 0:
            raise ValueError("los pasos angulares deben ser positivos")
        if not math.isclose(360.0 / self.c_step_deg, round(360.0 / self.c_step_deg)):
            raise ValueError("c_step_deg debe dividir exactamente 360°")
        if not math.isclose(180.0 / self.gamma_step_deg, round(180.0 / self.gamma_step_deg)):
            raise ValueError("gamma_step_deg debe dividir exactamente 180°")
        if self.flux_lm <= 0:
            raise ValueError("flux_lm debe ser mayor que cero")


@dataclass(frozen=True)
class AngularResolutionStage:
    """One angular grid used during progressive optimization."""

    name: str
    c_step_deg: float
    gamma_step_deg: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("la etapa de resolución necesita un nombre")
        if self.c_step_deg <= 0 or self.gamma_step_deg <= 0:
            raise ValueError("los pasos angulares deben ser positivos")
        if not math.isclose(360.0 / self.c_step_deg, round(360.0 / self.c_step_deg)):
            raise ValueError("c_step_deg debe dividir exactamente 360°")
        if not math.isclose(180.0 / self.gamma_step_deg, round(180.0 / self.gamma_step_deg)):
            raise ValueError("gamma_step_deg debe dividir exactamente 180°")


DEFAULT_RESOLUTION_STAGES: tuple[AngularResolutionStage, ...] = (
    AngularResolutionStage("coarse", c_step_deg=10.0, gamma_step_deg=5.0),
    AngularResolutionStage("medium", c_step_deg=5.0, gamma_step_deg=2.5),
    AngularResolutionStage("fine", c_step_deg=2.5, gamma_step_deg=1.0),
    AngularResolutionStage("export", c_step_deg=1.0, gamma_step_deg=1.0),
)


def _circular_distance_deg(first: float, second: float) -> float:
    difference = abs((first - second) % 360.0)
    return min(difference, 360.0 - difference)


def _cutoff_multiplier(
    gamma_deg: float,
    start_deg: float,
    end_deg: float,
) -> float:
    if gamma_deg <= start_deg:
        return 1.0
    if gamma_deg >= end_deg:
        return 0.0
    phase = (gamma_deg - start_deg) / (end_deg - start_deg)
    return 0.5 * (1.0 + math.cos(math.pi * phase))


def _raw_intensity(
    c_deg: float,
    gamma_deg: float,
    parameters: PhotometricFamilyParameters,
) -> float:
    mirror_peak_c = (180.0 - parameters.peak_c_deg) % 360.0
    c_components = tuple(
        math.exp(
            -0.5
            * (
                _circular_distance_deg(c_deg, centre)
                / parameters.c_spread_deg
            )
            ** 2
        )
        for centre in (parameters.peak_c_deg, mirror_peak_c)
    )
    # A fourth-order smooth maximum preserves two longitudinal throw peaks
    # instead of merging broad Gaussian lobes into an artificial C90 maximum.
    c_lobe = sum(value**4 for value in c_components) ** 0.25
    gamma_delta = gamma_deg - parameters.peak_gamma_deg
    gamma_spread = (
        parameters.gamma_spread_deg
        if gamma_delta <= 0.0
        else parameters.gamma_outer_spread_deg
    )
    gamma_base = math.exp(
        -0.5
        * (
            gamma_delta / gamma_spread
        )
        ** 2
    )
    gamma_crest = parameters.crest_weight * math.exp(
        -0.5
        * (gamma_delta / parameters.crest_spread_deg) ** 2
    )
    gamma_lobe = gamma_base + gamma_crest
    gamma_rad = math.radians(gamma_deg)
    c_rad = math.radians(c_deg)
    directional_onset = max(math.sin(gamma_rad), 0.0) ** 0.5
    throw_lobes = c_lobe * gamma_lobe * directional_onset

    cross_lobe = (
        parameters.cross_weight
        * math.exp(
            -0.5
            * (
                _circular_distance_deg(c_deg, 90.0)
                / parameters.cross_c_spread_deg
            )
            ** 2
        )
        * math.exp(
            -0.5
            * (
                (gamma_deg - parameters.cross_gamma_deg)
                / parameters.cross_gamma_spread_deg
            )
            ** 2
        )
        * directional_onset
    )
    # Every C plane represents the same physical ray at gamma=0. The angular
    # side factor therefore fades in with sin(gamma), guaranteeing one common
    # nadir intensity while retaining road-side bias away from the axis.
    side_factor = max(0.0, 1.0 + 0.70 * math.sin(c_rad) * math.sin(gamma_rad))
    nadir_fill = (
        parameters.nadir_weight
        * max(math.cos(gamma_rad), 0.0) ** parameters.nadir_power
        * side_factor
    )
    return (
        throw_lobes + cross_lobe + nadir_fill
    ) * _cutoff_multiplier(
        gamma_deg,
        parameters.cutoff_start_deg,
        parameters.cutoff_end_deg,
    )


def integrated_flux_lm_per_klm(candidate: PhotometricCandidate) -> float:
    """Numerically integrate an I-table over the sphere [lm/klm]."""

    c_angles = candidate.c_angles_deg
    gamma_angles = candidate.gamma_angles_deg
    if len(c_angles) < 2 or len(gamma_angles) < 2:
        return 0.0

    total = 0.0
    for c_index, c_deg in enumerate(c_angles):
        next_c = (
            c_angles[c_index + 1]
            if c_index + 1 < len(c_angles)
            else c_angles[0] + 360.0
        )
        delta_c = math.radians(next_c - c_deg)
        for gamma_index in range(len(gamma_angles) - 1):
            gamma_0 = math.radians(gamma_angles[gamma_index])
            gamma_1 = math.radians(gamma_angles[gamma_index + 1])
            weighted_0 = (
                candidate.intensity_cd_per_klm[c_index][gamma_index]
                * math.sin(gamma_0)
            )
            weighted_1 = (
                candidate.intensity_cd_per_klm[c_index][gamma_index + 1]
                * math.sin(gamma_1)
            )
            total += (
                0.5
                * (weighted_0 + weighted_1)
                * (gamma_1 - gamma_0)
                * delta_c
            )
    return total


def generate_symmetric_candidate(
    parameters: PhotometricFamilyParameters,
    *,
    resolution: AngularResolutionStage | None = None,
) -> PhotometricCandidate:
    """Generate and normalize one candidate to 1000 lm per klm."""

    effective = (
        replace(
            parameters,
            c_step_deg=resolution.c_step_deg,
            gamma_step_deg=resolution.gamma_step_deg,
        )
        if resolution is not None
        else parameters
    )
    c_count = round(360.0 / effective.c_step_deg)
    gamma_count = round(180.0 / effective.gamma_step_deg)
    c_angles = tuple(
        index * effective.c_step_deg for index in range(c_count)
    )
    gamma_angles = tuple(
        index * effective.gamma_step_deg
        for index in range(gamma_count + 1)
    )
    raw_rows = tuple(
        tuple(
            _raw_intensity(c_deg, gamma_deg, effective)
            for gamma_deg in gamma_angles
        )
        for c_deg in c_angles
    )
    provisional = PhotometricCandidate(
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        intensity_cd_per_klm=raw_rows,
        flux_lm=effective.flux_lm,
        luminaire_name=effective.luminaire_name,
        metadata={
            "generator": "symmetric-road-basis-v2",
            "longitudinal_symmetry": "perpendicular-road-plane",
            "resolution_stage": resolution.name if resolution is not None else "custom",
        },
    )
    raw_flux = integrated_flux_lm_per_klm(provisional)
    if raw_flux <= 0:
        raise ValueError("los parámetros producen una distribución sin flujo")
    scale = 1000.0 / raw_flux
    candidate = PhotometricCandidate(
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        intensity_cd_per_klm=tuple(
            tuple(value * scale for value in row) for row in raw_rows
        ),
        flux_lm=effective.flux_lm,
        luminaire_name=effective.luminaire_name,
        metadata={
            **provisional.metadata,
            "parameters": {
                field: getattr(effective, field)
                for field in effective.__dataclass_fields__
                if field != "luminaire_name"
            },
        },
    )
    validate_longitudinal_symmetry(candidate)
    return candidate


def generate_resolution_pyramid(
    parameters: PhotometricFamilyParameters,
    stages: Sequence[AngularResolutionStage] = DEFAULT_RESOLUTION_STAGES,
) -> tuple[PhotometricCandidate, ...]:
    """Regenerate the same analytical distribution at every resolution."""

    if not stages:
        raise ValueError("se requiere al menos una etapa de resolución")
    return tuple(
        generate_symmetric_candidate(parameters, resolution=stage)
        for stage in stages
    )
