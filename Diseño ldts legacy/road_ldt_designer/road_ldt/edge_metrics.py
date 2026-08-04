"""Edge illuminance ratio REI and historical surround ratio SR."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .direct_illuminance import direct_illuminance_at_point
from .domain import LuminairePlacement, PhotometricCandidate, RoadGeometry
from .street_geometry import CalculationPoint


@dataclass(frozen=True)
class EdgeStripGrid:
    width_m: float
    left_outside: tuple[CalculationPoint, ...]
    left_inside: tuple[CalculationPoint, ...]
    right_inside: tuple[CalculationPoint, ...]
    right_outside: tuple[CalculationPoint, ...]


@dataclass(frozen=True)
class EdgeIlluminanceResult:
    strip_width_m: float
    left_outside_avg_lx: float
    left_inside_avg_lx: float
    right_inside_avg_lx: float
    right_outside_avg_lx: float
    rei_left: float
    rei_right: float
    rei: float
    sr: float


def _cell_centres(start: float, end: float, count: int) -> tuple[float, ...]:
    step = (end - start) / count
    return tuple(start + (index + 0.5) * step for index in range(count))


def _contiguous_outside_width(geometry: RoadGeometry, side: str) -> float:
    """Infer unobstructed width from adjacent bands and facades."""

    intervals = sorted(
        (
            band.offset_from_carriageway_m,
            band.offset_from_carriageway_m + band.width_m,
        )
        for band in geometry.side_bands
        if band.side.lower() == side
    )
    reach = 0.0
    for start, end in intervals:
        if start > reach + 1e-9:
            break
        reach = max(reach, end)

    setbacks = tuple(
        building.setback_m
        for building in geometry.buildings
        if building.side.lower() == side
    )
    if setbacks:
        nearest_facade = min(setbacks)
        reach = min(reach, nearest_facade) if reach > 0 else nearest_facade
    return reach


def _edge_strip_width(geometry: RoadGeometry) -> float:
    left_lane_width = geometry.resolved_lane_widths_m[0]
    right_lane_width = geometry.resolved_lane_widths_m[-1]
    left_available = _contiguous_outside_width(geometry, "left")
    right_available = _contiguous_outside_width(geometry, "right")
    candidates = [left_lane_width, right_lane_width]
    if left_available > 0:
        candidates.append(left_available)
    if right_available > 0:
        candidates.append(right_available)
    return min(candidates)


def _points(
    name: str,
    x_values: tuple[float, ...],
    y_values: tuple[float, ...],
) -> tuple[CalculationPoint, ...]:
    return tuple(
        CalculationPoint(
            x_m=x_m,
            y_m=y_m,
            z_m=0.0,
            normal_x=0.0,
            normal_y=0.0,
            normal_z=1.0,
            surface_name=name,
            surface_kind="edge_strip",
        )
        for x_m in x_values
        for y_m in y_values
    )


def build_edge_strip_grid(
    geometry: RoadGeometry,
    *,
    transverse_points: int = 3,
) -> EdgeStripGrid:
    """Build four equal-width strips adjacent to the carriageway edges."""

    if transverse_points < 1:
        raise ValueError("transverse_points debe ser al menos 1")
    width = _edge_strip_width(geometry)
    x_values = _cell_centres(
        -geometry.calculation_length_m / 2.0,
        geometry.calculation_length_m / 2.0,
        geometry.longitudinal_points,
    )
    carriageway_width = geometry.carriageway_width_m
    return EdgeStripGrid(
        width_m=width,
        left_outside=_points(
            "edge_left_outside",
            x_values,
            _cell_centres(-width, 0.0, transverse_points),
        ),
        left_inside=_points(
            "edge_left_inside",
            x_values,
            _cell_centres(0.0, width, transverse_points),
        ),
        right_inside=_points(
            "edge_right_inside",
            x_values,
            _cell_centres(
                carriageway_width - width,
                carriageway_width,
                transverse_points,
            ),
        ),
        right_outside=_points(
            "edge_right_outside",
            x_values,
            _cell_centres(
                carriageway_width,
                carriageway_width + width,
                transverse_points,
            ),
        ),
    )


def summarize_edge_illuminance(
    strip_width_m: float,
    left_outside_lx: Sequence[float],
    left_inside_lx: Sequence[float],
    right_inside_lx: Sequence[float],
    right_outside_lx: Sequence[float],
) -> EdgeIlluminanceResult:
    """Calculate side-specific REI and combined historical SR."""

    groups = tuple(
        tuple(float(value) for value in group)
        for group in (
            left_outside_lx,
            left_inside_lx,
            right_inside_lx,
            right_outside_lx,
        )
    )
    if any(not group for group in groups):
        raise ValueError("cada banda debe contener al menos un valor")
    means = tuple(sum(group) / len(group) for group in groups)
    left_outside, left_inside, right_inside, right_outside = means
    rei_left = left_outside / left_inside if left_inside > 0 else 0.0
    rei_right = right_outside / right_inside if right_inside > 0 else 0.0
    inside_sum = left_inside + right_inside
    sr = (
        (left_outside + right_outside) / inside_sum
        if inside_sum > 0
        else 0.0
    )
    return EdgeIlluminanceResult(
        strip_width_m=strip_width_m,
        left_outside_avg_lx=left_outside,
        left_inside_avg_lx=left_inside,
        right_inside_avg_lx=right_inside,
        right_outside_avg_lx=right_outside,
        rei_left=rei_left,
        rei_right=rei_right,
        rei=min(rei_left, rei_right),
        sr=sr,
    )


def evaluate_edge_illuminance(
    candidate: PhotometricCandidate,
    luminaires: Sequence[LuminairePlacement],
    grid: EdgeStripGrid,
    *,
    maintenance_factor: float = 1.0,
) -> EdgeIlluminanceResult:
    """Evaluate direct horizontal illuminance on all four edge strips."""

    def values(points: Sequence[CalculationPoint]) -> tuple[float, ...]:
        return tuple(
            direct_illuminance_at_point(
                candidate,
                luminaires,
                point,
                maintenance_factor=maintenance_factor,
            )
            for point in points
        )

    return summarize_edge_illuminance(
        grid.width_m,
        values(grid.left_outside),
        values(grid.left_inside),
        values(grid.right_inside),
        values(grid.right_outside),
    )
