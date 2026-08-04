"""NumPy acceleration for repeated photometric candidate evaluation.

The scalar modules remain the reference implementation. Functions here return
the same public result dataclasses so both backends can be compared directly.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .direct_illuminance import IlluminanceAtPoint
from .domain import LuminairePlacement, PhotometricCandidate, RoadGeometry
from .edge_metrics import (
    EdgeIlluminanceResult,
    EdgeStripGrid,
    summarize_edge_illuminance,
)
from .road_luminance import (
    ObserverLuminanceResult,
    RoadLuminanceAtPoint,
    RoadObserver,
    StreetLuminanceResult,
    build_lane_observers,
    summarize_observer_luminance,
)
from .rtables import BETA_COLS, TABLES_RAW, TAN_EPSILON_ROWS
from .street_geometry import CalculationPoint, StreetCalculationGrid


def _geometry_arrays(
    luminaires: Sequence[LuminairePlacement],
    points: Sequence[CalculationPoint],
) -> tuple[np.ndarray, ...]:
    point_x = np.asarray([item.x_m for item in points], dtype=float)[:, None]
    point_y = np.asarray([item.y_m for item in points], dtype=float)[:, None]
    point_z = np.asarray([item.z_m for item in points], dtype=float)[:, None]
    lum_x = np.asarray([item.x_m for item in luminaires], dtype=float)[None, :]
    lum_y = np.asarray([item.y_m for item in luminaires], dtype=float)[None, :]
    lum_z = np.asarray(
        [item.mounting_height_m for item in luminaires],
        dtype=float,
    )[None, :]

    dx = point_x - lum_x
    dy = point_y - lum_y
    dz = point_z - lum_z
    distance = np.sqrt(dx * dx + dy * dy + dz * dz)
    if np.any(distance <= 1e-12):
        raise ValueError("un punto coincide con un centro fotométrico")

    yaw = np.radians(
        np.asarray(
            [
                item.orientation_deg + item.rotation_deg
                for item in luminaires
            ],
            dtype=float,
        )
    )[None, :]
    local_x = np.cos(yaw) * dx + np.sin(yaw) * dy
    local_y = -np.sin(yaw) * dx + np.cos(yaw) * dy
    local_down = -dz
    inverse_tilt = -np.radians(
        np.asarray([item.tilt_deg for item in luminaires], dtype=float)
    )[None, :]
    tilted_y = (
        np.cos(inverse_tilt) * local_y
        - np.sin(inverse_tilt) * local_down
    )
    tilted_down = (
        np.sin(inverse_tilt) * local_y
        + np.cos(inverse_tilt) * local_down
    )
    c_deg = np.degrees(np.arctan2(tilted_y, local_x)) % 360.0
    gamma_deg = np.degrees(
        np.arccos(np.clip(tilted_down / distance, -1.0, 1.0))
    )
    return (
        point_x,
        point_y,
        point_z,
        lum_x,
        lum_y,
        lum_z,
        dx,
        dy,
        dz,
        distance,
        c_deg,
        gamma_deg,
    )


def _intensity_numpy(
    candidate: PhotometricCandidate,
    c_deg: np.ndarray,
    gamma_deg: np.ndarray,
) -> np.ndarray:
    c_values = np.asarray(candidate.c_angles_deg, dtype=float)
    gamma_values = np.asarray(candidate.gamma_angles_deg, dtype=float)
    matrix = np.asarray(candidate.intensity_cd_per_klm, dtype=float)

    c_normalized = c_deg % 360.0
    c_lower = np.searchsorted(c_values, c_normalized, side="right") - 1
    c_lower = np.clip(c_lower, 0, len(c_values) - 1)
    c_upper = (c_lower + 1) % len(c_values)
    c0 = c_values[c_lower]
    c1 = np.where(c_upper == 0, c_values[0] + 360.0, c_values[c_upper])
    c_weight = np.divide(
        c_normalized - c0,
        c1 - c0,
        out=np.zeros_like(c_normalized),
        where=(c1 - c0) > 0,
    )

    gamma_clipped = np.clip(gamma_deg, gamma_values[0], gamma_values[-1])
    gamma_lower = np.searchsorted(
        gamma_values,
        gamma_clipped,
        side="right",
    ) - 1
    gamma_lower = np.clip(gamma_lower, 0, len(gamma_values) - 2)
    gamma_upper = gamma_lower + 1
    g0 = gamma_values[gamma_lower]
    g1 = gamma_values[gamma_upper]
    gamma_weight = np.divide(
        gamma_clipped - g0,
        g1 - g0,
        out=np.zeros_like(gamma_clipped),
        where=(g1 - g0) > 0,
    )

    i00 = matrix[c_lower, gamma_lower]
    i01 = matrix[c_lower, gamma_upper]
    i10 = matrix[c_upper, gamma_lower]
    i11 = matrix[c_upper, gamma_upper]
    lower_c = (1.0 - gamma_weight) * i00 + gamma_weight * i01
    upper_c = (1.0 - gamma_weight) * i10 + gamma_weight * i11
    return np.maximum(
        0.0,
        (1.0 - c_weight) * lower_c + c_weight * upper_c,
    )


def direct_illuminance_values_numpy(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    points: Sequence[CalculationPoint],
    *,
    maintenance_factor: float = 1.0,
) -> np.ndarray:
    if not 0.0 <= maintenance_factor <= 1.0:
        raise ValueError("maintenance_factor debe estar entre 0 y 1")
    if not luminaires:
        return np.zeros(len(points), dtype=float)
    if not points:
        return np.zeros(0, dtype=float)

    arrays = _geometry_arrays(luminaires, points)
    dx, dy, dz, distance, c_deg, gamma_deg = arrays[6:]
    intensity = _intensity_numpy(candidate, c_deg, gamma_deg)
    flux = np.asarray(
        [item.flux_lm / 1000.0 for item in luminaires],
        dtype=float,
    )[None, :]
    normals = np.asarray(
        [
            (item.normal_x, item.normal_y, item.normal_z)
            for item in points
        ],
        dtype=float,
    )
    incidence = np.maximum(
        0.0,
        (
            normals[:, 0, None] * (-dx)
            + normals[:, 1, None] * (-dy)
            + normals[:, 2, None] * (-dz)
        )
        / distance,
    )
    return np.sum(
        intensity
        * flux
        * incidence
        * maintenance_factor
        / (distance * distance),
        axis=1,
    )


def evaluate_direct_illuminance_numpy(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    points: Sequence[CalculationPoint],
    *,
    maintenance_factor: float = 1.0,
) -> tuple[IlluminanceAtPoint, ...]:
    values = direct_illuminance_values_numpy(
        candidate,
        luminaires,
        points,
        maintenance_factor=maintenance_factor,
    )
    return tuple(
        IlluminanceAtPoint(point=point, illuminance_lx=float(value))
        for point, value in zip(points, values)
    )


def _r_values_numpy(
    table_name: str,
    beta_deg: np.ndarray,
    tan_epsilon: np.ndarray,
) -> np.ndarray:
    name = str(table_name).upper()
    if name not in TABLES_RAW:
        raise ValueError(f"r-table no disponible: {table_name}")
    beta_axis = np.asarray(BETA_COLS, dtype=float)
    tan_axis = np.asarray(TAN_EPSILON_ROWS, dtype=float)
    table = np.asarray(TABLES_RAW[name], dtype=float) / 10_000.0

    beta = np.clip(beta_deg, beta_axis[0], beta_axis[-1])
    tan_value = np.clip(tan_epsilon, tan_axis[0], tan_axis[-1])
    bi0 = np.clip(
        np.searchsorted(beta_axis, beta, side="right") - 1,
        0,
        len(beta_axis) - 2,
    )
    bi1 = bi0 + 1
    ti0 = np.clip(
        np.searchsorted(tan_axis, tan_value, side="right") - 1,
        0,
        len(tan_axis) - 2,
    )
    ti1 = ti0 + 1
    wb = (beta - beta_axis[bi0]) / (beta_axis[bi1] - beta_axis[bi0])
    wt = (tan_value - tan_axis[ti0]) / (tan_axis[ti1] - tan_axis[ti0])
    return (
        (1.0 - wt)
        * ((1.0 - wb) * table[ti0, bi0] + wb * table[ti0, bi1])
        + wt * ((1.0 - wb) * table[ti1, bi0] + wb * table[ti1, bi1])
    )


def evaluate_road_luminance_for_observer_numpy(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    road_points: Sequence[CalculationPoint],
    observer: RoadObserver,
    *,
    r_table: str = "R2",
    maintenance_factor: float = 1.0,
) -> ObserverLuminanceResult:
    if not 0.0 <= maintenance_factor <= 1.0:
        raise ValueError("maintenance_factor debe estar entre 0 y 1")
    arrays = _geometry_arrays(luminaires, road_points)
    point_x, point_y, point_z, lum_x, lum_y, lum_z = arrays[:6]
    c_deg, gamma_deg = arrays[10:]
    intensity = _intensity_numpy(candidate, c_deg, gamma_deg)
    flux = np.asarray(
        [item.flux_lm / 1000.0 for item in luminaires],
        dtype=float,
    )[None, :]

    height = lum_z - point_z
    if np.any(height <= 0):
        raise ValueError("la luminaria debe estar por encima de la calzada")
    tan_epsilon = np.hypot(point_x - lum_x, point_y - lum_y) / height
    point_to_lum = np.arctan2(lum_y - point_y, lum_x - point_x)
    observer_to_point = np.arctan2(
        point_y - observer.y_m,
        point_x - observer.x_m,
    )
    beta = np.abs(np.degrees(point_to_lum - observer_to_point)) % 360.0
    beta = np.where(beta > 180.0, 360.0 - beta, beta)
    reduced = _r_values_numpy(r_table, beta, tan_epsilon)
    contributions = (
        intensity
        * flux
        * reduced
        * maintenance_factor
        / (height * height)
    )
    totals = np.sum(contributions, axis=1)
    point_results = tuple(
        RoadLuminanceAtPoint(
            point=point,
            luminance_cd_m2=float(totals[index]),
            contributions_cd_m2=tuple(float(value) for value in contributions[index]),
        )
        for index, point in enumerate(road_points)
    )
    return summarize_observer_luminance(observer, point_results)


def evaluate_street_luminance_numpy(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    geometry: RoadGeometry,
    grid: StreetCalculationGrid,
    *,
    maintenance_factor: float = 1.0,
    observer_distance_m: float = 60.0,
    observer_height_m: float = 1.5,
) -> StreetLuminanceResult:
    observers = build_lane_observers(
        geometry,
        grid,
        distance_before_grid_m=observer_distance_m,
        height_m=observer_height_m,
    )
    results = tuple(
        evaluate_road_luminance_for_observer_numpy(
            candidate,
            luminaires,
            grid.road_points,
            observer,
            r_table=geometry.r_table,
            maintenance_factor=maintenance_factor,
        )
        for observer in observers
    )
    return StreetLuminanceResult(
        observer_results=results,
        luminance_avg_cd_m2=min(item.luminance_avg_cd_m2 for item in results),
        uo=min(item.uo for item in results),
        ul=min(item.ul for item in results),
    )


def evaluate_edge_illuminance_numpy(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    grid: EdgeStripGrid,
    *,
    maintenance_factor: float = 1.0,
) -> EdgeIlluminanceResult:
    def values(points: Sequence[CalculationPoint]) -> np.ndarray:
        return direct_illuminance_values_numpy(
            candidate,
            luminaires,
            points,
            maintenance_factor=maintenance_factor,
        )

    return summarize_edge_illuminance(
        grid.width_m,
        values(grid.left_outside),
        values(grid.left_inside),
        values(grid.right_inside),
        values(grid.right_outside),
    )
