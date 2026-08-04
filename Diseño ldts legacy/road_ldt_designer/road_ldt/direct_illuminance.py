"""Direct illuminance from an EULUMDAT intensity table.

This module is independent of road-luminance reflection tables. It evaluates
the luminous intensity emitted toward a 3D point and projects it onto the
receiving surface normal. The same calculation therefore serves carriageways,
sidewalks, facades and windows.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Sequence

from .domain import LuminairePlacement, PhotometricCandidate
from .street_geometry import CalculationPoint


@dataclass(frozen=True)
class PhotometricAngles:
    c_deg: float
    gamma_deg: float
    distance_m: float


@dataclass(frozen=True)
class IlluminanceAtPoint:
    point: CalculationPoint
    illuminance_lx: float


def _bracket(values: tuple[float, ...], value: float) -> tuple[int, int, float]:
    value = min(max(value, values[0]), values[-1])
    lower = bisect.bisect_right(values, value) - 1
    lower = max(0, min(lower, len(values) - 2))
    upper = lower + 1
    span = values[upper] - values[lower]
    weight = (value - values[lower]) / span if span > 0 else 0.0
    return lower, upper, weight


def intensity_cd_per_klm(
    candidate: PhotometricCandidate,
    c_deg: float,
    gamma_deg: float,
) -> float:
    """Bilinear interpolation with circular interpolation between C planes."""

    c_values = tuple(float(value) for value in candidate.c_angles_deg)
    g_values = tuple(float(value) for value in candidate.gamma_angles_deg)
    matrix = candidate.intensity_cd_per_klm

    c_normalized = float(c_deg) % 360.0
    while c_normalized < c_values[0]:
        c_normalized += 360.0

    c_extended = c_values + (c_values[0] + 360.0,)
    c_lower = bisect.bisect_right(c_extended, c_normalized) - 1
    c_lower = max(0, min(c_lower, len(c_values) - 1))
    c_upper = (c_lower + 1) % len(c_values)
    c0 = c_extended[c_lower]
    c1 = c_extended[c_lower + 1]
    c_weight = (c_normalized - c0) / (c1 - c0) if c1 > c0 else 0.0

    g_lower, g_upper, g_weight = _bracket(g_values, float(gamma_deg))
    i00 = float(matrix[c_lower][g_lower])
    i01 = float(matrix[c_lower][g_upper])
    i10 = float(matrix[c_upper][g_lower])
    i11 = float(matrix[c_upper][g_upper])

    lower_c = (1.0 - g_weight) * i00 + g_weight * i01
    upper_c = (1.0 - g_weight) * i10 + g_weight * i11
    return max(0.0, (1.0 - c_weight) * lower_c + c_weight * upper_c)


def photometric_angles(
    luminaire: LuminairePlacement,
    point: CalculationPoint,
) -> PhotometricAngles:
    """Transform a world-space light path into the luminaire C-gamma frame.

    C=0 follows the luminaire orientation in the street plane. Positive tilt
    rotates the photometric frame about the local C0 axis. `rotation_deg`
    applies an additional rotation of the C-plane reference.
    """

    dx = point.x_m - luminaire.x_m
    dy = point.y_m - luminaire.y_m
    dz = point.z_m - luminaire.mounting_height_m
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    if distance <= 1e-12:
        raise ValueError("el punto de cálculo coincide con el centro fotométrico")

    yaw = math.radians(luminaire.orientation_deg + luminaire.rotation_deg)
    local_x = math.cos(yaw) * dx + math.sin(yaw) * dy
    local_y = -math.sin(yaw) * dx + math.cos(yaw) * dy
    local_down = -dz

    inverse_tilt = -math.radians(luminaire.tilt_deg)
    tilted_y = (
        math.cos(inverse_tilt) * local_y
        - math.sin(inverse_tilt) * local_down
    )
    tilted_down = (
        math.sin(inverse_tilt) * local_y
        + math.cos(inverse_tilt) * local_down
    )

    c_deg = math.degrees(math.atan2(tilted_y, local_x)) % 360.0
    cos_gamma = max(-1.0, min(1.0, tilted_down / distance))
    gamma_deg = math.degrees(math.acos(cos_gamma))
    return PhotometricAngles(c_deg=c_deg, gamma_deg=gamma_deg, distance_m=distance)


def direct_illuminance_from_luminaire(
    candidate: PhotometricCandidate,
    luminaire: LuminairePlacement,
    point: CalculationPoint,
    *,
    maintenance_factor: float = 1.0,
) -> float:
    """Direct illuminance [lx] received at one oriented surface point."""

    if maintenance_factor < 0.0 or maintenance_factor > 1.0:
        raise ValueError("maintenance_factor debe estar entre 0 y 1")

    angles = photometric_angles(luminaire, point)
    intensity = intensity_cd_per_klm(
        candidate,
        angles.c_deg,
        angles.gamma_deg,
    ) * (luminaire.flux_lm / 1000.0)

    to_luminaire_x = (luminaire.x_m - point.x_m) / angles.distance_m
    to_luminaire_y = (luminaire.y_m - point.y_m) / angles.distance_m
    to_luminaire_z = (
        luminaire.mounting_height_m - point.z_m
    ) / angles.distance_m
    incidence_cosine = max(
        0.0,
        point.normal_x * to_luminaire_x
        + point.normal_y * to_luminaire_y
        + point.normal_z * to_luminaire_z,
    )
    return (
        intensity
        * incidence_cosine
        * maintenance_factor
        / (angles.distance_m * angles.distance_m)
    )


def direct_illuminance_at_point(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    point: CalculationPoint,
    *,
    maintenance_factor: float = 1.0,
) -> float:
    """Sum direct illuminance from all luminaires at one point."""

    return sum(
        direct_illuminance_from_luminaire(
            candidate,
            luminaire,
            point,
            maintenance_factor=maintenance_factor,
        )
        for luminaire in luminaires
    )


def evaluate_direct_illuminance(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    points: Sequence[CalculationPoint],
    *,
    maintenance_factor: float = 1.0,
) -> tuple[IlluminanceAtPoint, ...]:
    """Evaluate direct illuminance for a complete calculation surface."""

    return tuple(
        IlluminanceAtPoint(
            point=point,
            illuminance_lx=direct_illuminance_at_point(
                candidate,
                luminaires,
                point,
                maintenance_factor=maintenance_factor,
            ),
        )
        for point in points
    )
