"""Road-surface luminance calculation using reduced luminance tables.

The implementation is independent from the tunnel application. It combines
the candidate EULUMDAT intensity distribution with a selected dry-road
R-table and evaluates one observer at the centre of every traffic lane.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .direct_illuminance import intensity_cd_per_klm, photometric_angles
from .domain import LuminairePlacement, PhotometricCandidate, RoadGeometry
from .rtables import r_value
from .street_geometry import CalculationPoint, StreetCalculationGrid


@dataclass(frozen=True)
class RoadObserver:
    """Driver eye position associated with one lane."""

    x_m: float
    y_m: float
    lane_index: int
    height_m: float = 1.5

    def __post_init__(self) -> None:
        if self.height_m <= 0:
            raise ValueError("height_m debe ser mayor que cero")
        if self.lane_index < 0:
            raise ValueError("lane_index no puede ser negativo")


@dataclass(frozen=True)
class RoadLuminanceAtPoint:
    """Maintained road luminance and per-luminaire contributions."""

    point: CalculationPoint
    luminance_cd_m2: float
    contributions_cd_m2: tuple[float, ...]


@dataclass(frozen=True)
class ObserverLuminanceResult:
    """Road metrics seen by one lane observer."""

    observer: RoadObserver
    point_results: tuple[RoadLuminanceAtPoint, ...]
    luminance_avg_cd_m2: float
    luminance_min_cd_m2: float
    luminance_max_cd_m2: float
    uo: float
    ul: float


@dataclass(frozen=True)
class StreetLuminanceResult:
    """Conservative summary across all lane observers."""

    observer_results: tuple[ObserverLuminanceResult, ...]
    luminance_avg_cd_m2: float
    uo: float
    ul: float


def _lane_centres(geometry: RoadGeometry) -> tuple[float, ...]:
    centres: list[float] = []
    y_start = 0.0
    for width in geometry.resolved_lane_widths_m:
        centres.append(y_start + width / 2.0)
        y_start += width
    return tuple(centres)


def build_lane_observers(
    geometry: RoadGeometry,
    grid: StreetCalculationGrid,
    *,
    distance_before_grid_m: float = 60.0,
    height_m: float = 1.5,
) -> tuple[RoadObserver, ...]:
    """Place one observer per lane, 60 m before the first calculation row."""

    if distance_before_grid_m <= 0:
        raise ValueError("distance_before_grid_m debe ser mayor que cero")
    if not grid.road_points:
        raise ValueError("la malla no contiene puntos de calzada")

    x_values = tuple(point.x_m for point in grid.road_points)
    observer_x = min(x_values) - distance_before_grid_m

    return tuple(
        RoadObserver(
            x_m=observer_x,
            y_m=y_m,
            lane_index=lane_index,
            height_m=height_m,
        )
        for lane_index, y_m in enumerate(_lane_centres(geometry))
    )


def deviation_angle_beta(
    point: CalculationPoint,
    luminaire: LuminairePlacement,
    observer: RoadObserver,
) -> float:
    """Return the plan deviation angle beta in the range 0..180 degrees."""

    point_to_luminaire_angle = math.atan2(
        luminaire.y_m - point.y_m,
        luminaire.x_m - point.x_m,
    )
    observer_to_point_angle = math.atan2(
        point.y_m - observer.y_m,
        point.x_m - observer.x_m,
    )
    beta = abs(
        math.degrees(point_to_luminaire_angle - observer_to_point_angle)
    ) % 360.0
    return 360.0 - beta if beta > 180.0 else beta


def luminance_from_luminaire(
    candidate: PhotometricCandidate,
    luminaire: LuminairePlacement,
    point: CalculationPoint,
    observer: RoadObserver,
    *,
    r_table: str = "R2",
    maintenance_factor: float = 1.0,
) -> float:
    """Maintained luminance contribution from one luminaire [cd/m2]."""

    if not 0.0 <= maintenance_factor <= 1.0:
        raise ValueError("maintenance_factor debe estar entre 0 y 1")
    height_above_point = luminaire.mounting_height_m - point.z_m
    if height_above_point <= 0:
        raise ValueError("la luminaria debe estar por encima del punto de calzada")

    angles = photometric_angles(luminaire, point)
    intensity_cd = intensity_cd_per_klm(
        candidate,
        angles.c_deg,
        angles.gamma_deg,
    ) * (luminaire.flux_lm / 1000.0)
    horizontal_distance = math.hypot(
        point.x_m - luminaire.x_m,
        point.y_m - luminaire.y_m,
    )
    tan_epsilon = horizontal_distance / height_above_point
    beta_deg = deviation_angle_beta(point, luminaire, observer)
    reduced_luminance = r_value(r_table, beta_deg, tan_epsilon)
    return (
        intensity_cd
        * reduced_luminance
        * maintenance_factor
        / (height_above_point * height_above_point)
    )


def road_luminance_at_point(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    point: CalculationPoint,
    observer: RoadObserver,
    *,
    r_table: str = "R2",
    maintenance_factor: float = 1.0,
) -> RoadLuminanceAtPoint:
    """Sum road luminance at one point and preserve each contribution."""

    contributions = tuple(
        luminance_from_luminaire(
            candidate,
            luminaire,
            point,
            observer,
            r_table=r_table,
            maintenance_factor=maintenance_factor,
        )
        for luminaire in luminaires
    )
    return RoadLuminanceAtPoint(
        point=point,
        luminance_cd_m2=sum(contributions),
        contributions_cd_m2=contributions,
    )


def summarize_observer_luminance(
    observer: RoadObserver,
    point_results: Sequence[RoadLuminanceAtPoint],
) -> ObserverLuminanceResult:
    """Calculate Lavg, Uo and Ul for one observer.

    Ul is evaluated on the longitudinal calculation line closest to the
    centre of the observer's lane.
    """

    results = tuple(point_results)
    if not results:
        raise ValueError("se requiere al menos un resultado de luminancia")

    values = tuple(result.luminance_cd_m2 for result in results)
    luminance_avg = sum(values) / len(values)
    luminance_min = min(values)
    luminance_max = max(values)
    uo = luminance_min / luminance_avg if luminance_avg > 0 else 0.0

    lane_results = tuple(
        result
        for result in results
        if result.point.lane_index == observer.lane_index
    )
    if not lane_results:
        raise ValueError("no hay puntos para el carril del observador")
    centreline_y = min(
        {result.point.y_m for result in lane_results},
        key=lambda y_m: abs(y_m - observer.y_m),
    )
    centreline_values = tuple(
        result.luminance_cd_m2
        for result in lane_results
        if math.isclose(result.point.y_m, centreline_y, abs_tol=1e-9)
    )
    centreline_max = max(centreline_values)
    ul = min(centreline_values) / centreline_max if centreline_max > 0 else 0.0

    return ObserverLuminanceResult(
        observer=observer,
        point_results=results,
        luminance_avg_cd_m2=luminance_avg,
        luminance_min_cd_m2=luminance_min,
        luminance_max_cd_m2=luminance_max,
        uo=uo,
        ul=ul,
    )


def evaluate_road_luminance_for_observer(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    road_points: Sequence[CalculationPoint],
    observer: RoadObserver,
    *,
    r_table: str = "R2",
    maintenance_factor: float = 1.0,
) -> ObserverLuminanceResult:
    """Evaluate every road point for a specific lane observer."""

    point_results = tuple(
        road_luminance_at_point(
            candidate,
            luminaires,
            point,
            observer,
            r_table=r_table,
            maintenance_factor=maintenance_factor,
        )
        for point in road_points
    )
    return summarize_observer_luminance(observer, point_results)


def evaluate_street_luminance(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    geometry: RoadGeometry,
    grid: StreetCalculationGrid,
    *,
    maintenance_factor: float = 1.0,
    observer_distance_m: float = 60.0,
    observer_height_m: float = 1.5,
) -> StreetLuminanceResult:
    """Evaluate all lane observers and return the worst maintained metrics."""

    if not luminaires:
        raise ValueError("se requiere al menos una luminaria")
    observers = build_lane_observers(
        geometry,
        grid,
        distance_before_grid_m=observer_distance_m,
        height_m=observer_height_m,
    )
    observer_results = tuple(
        evaluate_road_luminance_for_observer(
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
        observer_results=observer_results,
        luminance_avg_cd_m2=min(
            result.luminance_avg_cd_m2 for result in observer_results
        ),
        uo=min(result.uo for result in observer_results),
        ul=min(result.ul for result in observer_results),
    )
