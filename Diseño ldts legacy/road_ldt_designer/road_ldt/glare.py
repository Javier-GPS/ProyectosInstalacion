"""Threshold increment fTI for road-lighting observers.

The calculation uses initial photometric values, a conventional 23-year-old
observer at 1.5 m, and a line of sight one degree below horizontal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .direct_illuminance import direct_illuminance_from_luminaire
from .domain import LuminairePlacement, PhotometricCandidate, RoadGeometry
from .road_luminance import (
    RoadObserver,
    build_lane_observers,
    evaluate_road_luminance_for_observer,
)
from .street_geometry import CalculationPoint, StreetCalculationGrid


@dataclass(frozen=True)
class VeilingLuminanceContribution:
    luminaire_index: int
    theta_deg: float
    eye_illuminance_lx: float
    veiling_luminance_cd_m2: float


@dataclass(frozen=True)
class ThresholdIncrementResult:
    observer: RoadObserver
    initial_road_luminance_cd_m2: float
    veiling_luminance_cd_m2: float
    ti_pct: float
    contributions: tuple[VeilingLuminanceContribution, ...]


@dataclass(frozen=True)
class StreetThresholdIncrementResult:
    """Operative maximum fTI over all evaluated lanes and positions."""

    position_results: tuple[ThresholdIncrementResult, ...]
    ti_pct: float
    critical_result: ThresholdIncrementResult


def line_of_sight_unit_vector(
    *,
    downward_angle_deg: float = 1.0,
) -> tuple[float, float, float]:
    """Unit vector along the driver's line of sight."""

    if not 0.0 <= downward_angle_deg < 90.0:
        raise ValueError("downward_angle_deg debe estar entre 0 y 90")
    angle = math.radians(downward_angle_deg)
    return (
        math.cos(angle),
        0.0,
        -math.sin(angle),
    )


def angle_from_line_of_sight_deg(
    observer: RoadObserver,
    luminaire: LuminairePlacement,
    *,
    downward_angle_deg: float = 1.0,
) -> float:
    """Angle theta between line of sight and the luminaire centre."""

    sight = line_of_sight_unit_vector(
        downward_angle_deg=downward_angle_deg,
    )
    vector = (
        luminaire.x_m - observer.x_m,
        luminaire.y_m - observer.y_m,
        luminaire.mounting_height_m - observer.height_m,
    )
    distance = math.sqrt(sum(component * component for component in vector))
    if distance <= 1e-12:
        raise ValueError("el observador coincide con el centro fotométrico")
    cosine = sum(sight[index] * vector[index] for index in range(3)) / distance
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def eye_illuminance_from_luminaire(
    candidate: PhotometricCandidate,
    luminaire: LuminairePlacement,
    observer: RoadObserver,
    *,
    downward_angle_deg: float = 1.0,
) -> float:
    """Initial illuminance on a plane normal to the line of sight."""

    sight = line_of_sight_unit_vector(
        downward_angle_deg=downward_angle_deg,
    )
    eye_point = CalculationPoint(
        x_m=observer.x_m,
        y_m=observer.y_m,
        z_m=observer.height_m,
        normal_x=sight[0],
        normal_y=sight[1],
        normal_z=sight[2],
        surface_name=f"observer_lane_{observer.lane_index + 1}",
        surface_kind="observer_eye",
        lane_index=observer.lane_index,
    )
    return direct_illuminance_from_luminaire(
        candidate,
        luminaire,
        eye_point,
        maintenance_factor=1.0,
    )


def veiling_luminance_contribution(
    eye_illuminance_lx: float,
    theta_deg: float,
    *,
    observer_age_years: float = 23.0,
) -> float:
    """Equivalent veiling luminance from one luminaire [cd/m2]."""

    if eye_illuminance_lx < 0:
        raise ValueError("eye_illuminance_lx no puede ser negativa")
    if observer_age_years <= 0:
        raise ValueError("observer_age_years debe ser mayor que cero")
    if not 0.1 < theta_deg <= 60.0:
        return 0.0
    if theta_deg <= 1.5:
        return eye_illuminance_lx * (
            10.0 / (theta_deg**3)
            + 5.0
            * (1.0 + (observer_age_years / 62.5) ** 4)
            / (theta_deg**2)
        )
    return (
        9.86
        * (1.0 + (observer_age_years / 66.4) ** 4)
        * eye_illuminance_lx
        / (theta_deg**2)
    )


def _is_in_glare_field(
    observer: RoadObserver,
    luminaire: LuminairePlacement,
    *,
    screening_elevation_deg: float,
    maximum_distance_m: float,
) -> bool:
    dx = luminaire.x_m - observer.x_m
    if dx <= 0.0 or dx > maximum_distance_m:
        return False
    dy = luminaire.y_m - observer.y_m
    dz = luminaire.mounting_height_m - observer.height_m
    elevation = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return elevation <= screening_elevation_deg


def calculate_threshold_increment(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    observer: RoadObserver,
    initial_road_luminance_cd_m2: float,
    *,
    observer_age_years: float = 23.0,
    downward_angle_deg: float = 1.0,
    screening_elevation_deg: float = 20.0,
    maximum_distance_m: float = 500.0,
) -> ThresholdIncrementResult:
    """Calculate fTI at one observer position using initial quantities."""

    if not 0.05 < initial_road_luminance_cd_m2 <= 5.0:
        raise ValueError(
            "la fórmula fTI requiere 0.05 < luminancia inicial <= 5 cd/m2"
        )
    if maximum_distance_m <= 0:
        raise ValueError("maximum_distance_m debe ser mayor que cero")

    contributions: list[VeilingLuminanceContribution] = []
    for index, luminaire in enumerate(luminaires):
        if not _is_in_glare_field(
            observer,
            luminaire,
            screening_elevation_deg=screening_elevation_deg,
            maximum_distance_m=maximum_distance_m,
        ):
            continue
        theta_deg = angle_from_line_of_sight_deg(
            observer,
            luminaire,
            downward_angle_deg=downward_angle_deg,
        )
        eye_illuminance = eye_illuminance_from_luminaire(
            candidate,
            luminaire,
            observer,
            downward_angle_deg=downward_angle_deg,
        )
        veiling = veiling_luminance_contribution(
            eye_illuminance,
            theta_deg,
            observer_age_years=observer_age_years,
        )
        if veiling > 0.0:
            contributions.append(
                VeilingLuminanceContribution(
                    luminaire_index=index,
                    theta_deg=theta_deg,
                    eye_illuminance_lx=eye_illuminance,
                    veiling_luminance_cd_m2=veiling,
                )
            )

    total_veiling = sum(item.veiling_luminance_cd_m2 for item in contributions)
    ti_pct = (
        65.0
        * total_veiling
        / (initial_road_luminance_cd_m2**0.8)
    )
    return ThresholdIncrementResult(
        observer=observer,
        initial_road_luminance_cd_m2=initial_road_luminance_cd_m2,
        veiling_luminance_cd_m2=total_veiling,
        ti_pct=ti_pct,
        contributions=tuple(contributions),
    )


def build_threshold_increment_observers(
    geometry: RoadGeometry,
    grid: StreetCalculationGrid,
    luminaires: Sequence[LuminairePlacement],
    *,
    observer_height_m: float = 1.5,
) -> tuple[RoadObserver, ...]:
    """Build EN 13201 longitudinal observer positions for each lane.

    One initial series is generated for every transverse luminaire row. The
    observer then advances with the same spacing and count as the longitudinal
    luminance calculation points.
    """

    if not luminaires:
        raise ValueError("se requiere al menos una luminaria")
    x_rows = sorted({point.x_m for point in grid.road_points})
    if len(x_rows) < 2:
        raise ValueError("la malla requiere al menos dos filas longitudinales")
    longitudinal_step = x_rows[1] - x_rows[0]
    field_start = x_rows[0]

    rows: dict[float, list[LuminairePlacement]] = {}
    for luminaire in luminaires:
        rows.setdefault(round(luminaire.y_m, 6), []).append(luminaire)

    initial_positions: list[float] = []
    for row in rows.values():
        candidates = tuple(
            luminaire for luminaire in row if luminaire.x_m >= field_start
        )
        if not candidates:
            continue
        first_luminaire = min(candidates, key=lambda item: item.x_m)
        initial_distance = 2.75 * (
            first_luminaire.mounting_height_m - observer_height_m
        )
        if initial_distance <= 0:
            raise ValueError("la luminaria debe estar por encima del observador")
        initial_positions.append(first_luminaire.x_m - initial_distance)
    if not initial_positions:
        raise ValueError(
            "no hay luminarias por delante del inicio del campo de cálculo"
        )

    lane_observers = build_lane_observers(
        geometry,
        grid,
        height_m=observer_height_m,
    )
    observers: dict[tuple[float, float], RoadObserver] = {}
    for initial_x in initial_positions:
        for longitudinal_index in range(len(x_rows)):
            x_m = initial_x + longitudinal_index * longitudinal_step
            for lane_observer in lane_observers:
                observer = RoadObserver(
                    x_m=x_m,
                    y_m=lane_observer.y_m,
                    lane_index=lane_observer.lane_index,
                    height_m=observer_height_m,
                )
                observers[(round(x_m, 9), round(observer.y_m, 9))] = observer
    return tuple(
        sorted(
            observers.values(),
            key=lambda item: (item.x_m, item.lane_index),
        )
    )


def evaluate_street_threshold_increment(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    geometry: RoadGeometry,
    grid: StreetCalculationGrid,
    *,
    observer_age_years: float = 23.0,
    observer_height_m: float = 1.5,
    initial_luminance_by_lane: dict[int, float] | None = None,
) -> StreetThresholdIncrementResult:
    """Return the maximum fTI across all lane and longitudinal observers."""

    if initial_luminance_by_lane is None:
        luminance_observers = build_lane_observers(
            geometry,
            grid,
            height_m=observer_height_m,
        )
        initial_luminance_by_lane = {
            observer.lane_index: evaluate_road_luminance_for_observer(
                candidate,
                luminaires,
                grid.road_points,
                observer,
                r_table=geometry.r_table,
                maintenance_factor=1.0,
            ).luminance_avg_cd_m2
            for observer in luminance_observers
        }
    ti_observers = build_threshold_increment_observers(
        geometry,
        grid,
        luminaires,
        observer_height_m=observer_height_m,
    )
    results = tuple(
        calculate_threshold_increment(
            candidate,
            luminaires,
            observer,
            initial_luminance_by_lane[observer.lane_index],
            observer_age_years=observer_age_years,
        )
        for observer in ti_observers
    )
    critical = max(results, key=lambda item: item.ti_pct)
    return StreetThresholdIncrementResult(
        position_results=results,
        ti_pct=critical.ti_pct,
        critical_result=critical,
    )
