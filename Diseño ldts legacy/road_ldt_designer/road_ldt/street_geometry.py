"""3D calculation grids for complete street sections.

Coordinate convention
---------------------
* x: longitudinal street direction.
* y: transverse direction; carriageway spans 0 .. carriageway_width_m.
* z: height above carriageway datum.

Left roadside elements use y < 0. Right roadside elements use y > W.
Surface normals always point toward the incident-light side evaluated by the
photometric calculator: horizontal surfaces point upward and facades point
toward the street.
"""
from __future__ import annotations

from dataclasses import dataclass

from .domain import AdjacentBuilding, RoadGeometry, StreetBand


@dataclass(frozen=True)
class CalculationPoint:
    """One point and its receiving-surface normal."""

    x_m: float
    y_m: float
    z_m: float
    normal_x: float
    normal_y: float
    normal_z: float
    surface_name: str
    surface_kind: str
    lane_index: int | None = None


@dataclass(frozen=True)
class SurfaceGrid:
    """Named group of calculation points belonging to one surface."""

    name: str
    kind: str
    points: tuple[CalculationPoint, ...]


@dataclass(frozen=True)
class StreetCalculationGrid:
    """All calculation surfaces generated from one street geometry."""

    lane_grids: tuple[SurfaceGrid, ...]
    band_grids: tuple[SurfaceGrid, ...]
    facade_grids: tuple[SurfaceGrid, ...]
    window_grids: tuple[SurfaceGrid, ...]

    @property
    def road_points(self) -> tuple[CalculationPoint, ...]:
        return tuple(point for grid in self.lane_grids for point in grid.points)

    @property
    def horizontal_points(self) -> tuple[CalculationPoint, ...]:
        return self.road_points + tuple(
            point for grid in self.band_grids for point in grid.points
        )

    @property
    def intrusion_points(self) -> tuple[CalculationPoint, ...]:
        return tuple(
            point
            for grid in self.facade_grids + self.window_grids
            for point in grid.points
        )

    @property
    def all_points(self) -> tuple[CalculationPoint, ...]:
        return self.horizontal_points + self.intrusion_points


def _cell_centres(start: float, end: float, count: int) -> tuple[float, ...]:
    if count < 1:
        raise ValueError("count debe ser al menos 1")
    if end <= start:
        raise ValueError("end debe ser mayor que start")
    step = (end - start) / count
    return tuple(start + (index + 0.5) * step for index in range(count))


def _longitudinal_centres(length_m: float, count: int) -> tuple[float, ...]:
    return _cell_centres(-length_m / 2.0, length_m / 2.0, count)


def _horizontal_grid(
    *,
    name: str,
    kind: str,
    x_values: tuple[float, ...],
    y_values: tuple[float, ...],
    z_m: float,
    lane_index: int | None = None,
) -> SurfaceGrid:
    points = tuple(
        CalculationPoint(
            x_m=x_m,
            y_m=y_m,
            z_m=z_m,
            normal_x=0.0,
            normal_y=0.0,
            normal_z=1.0,
            surface_name=name,
            surface_kind=kind,
            lane_index=lane_index,
        )
        for x_m in x_values
        for y_m in y_values
    )
    return SurfaceGrid(name=name, kind=kind, points=points)


def _lane_grids(
    geometry: RoadGeometry,
    x_values: tuple[float, ...],
) -> tuple[SurfaceGrid, ...]:
    grids: list[SurfaceGrid] = []
    y_start = 0.0
    for lane_index, lane_width in enumerate(geometry.resolved_lane_widths_m):
        y_end = y_start + lane_width
        y_values = _cell_centres(
            y_start,
            y_end,
            geometry.transverse_points_per_lane,
        )
        grids.append(
            _horizontal_grid(
                name=f"lane_{lane_index + 1}",
                kind="carriageway",
                x_values=x_values,
                y_values=y_values,
                z_m=0.0,
                lane_index=lane_index,
            )
        )
        y_start = y_end
    return tuple(grids)


def _band_y_limits(band: StreetBand, carriageway_width_m: float) -> tuple[float, float]:
    if band.side.lower() == "left":
        return (
            -(band.offset_from_carriageway_m + band.width_m),
            -band.offset_from_carriageway_m,
        )
    return (
        carriageway_width_m + band.offset_from_carriageway_m,
        carriageway_width_m + band.offset_from_carriageway_m + band.width_m,
    )


def _band_grids(
    geometry: RoadGeometry,
    x_values: tuple[float, ...],
    transverse_points: int,
) -> tuple[SurfaceGrid, ...]:
    grids: list[SurfaceGrid] = []
    for band in geometry.side_bands:
        y_start, y_end = _band_y_limits(band, geometry.carriageway_width_m)
        grids.append(
            _horizontal_grid(
                name=band.name,
                kind=band.surface,
                x_values=x_values,
                y_values=_cell_centres(y_start, y_end, transverse_points),
                z_m=band.elevation_m,
            )
        )
    return tuple(grids)


def _facade_y_and_normal(
    building: AdjacentBuilding,
    carriageway_width_m: float,
) -> tuple[float, float]:
    if building.side.lower() == "left":
        return -building.setback_m, 1.0
    return carriageway_width_m + building.setback_m, -1.0


def _vertical_grid(
    *,
    building: AdjacentBuilding,
    carriageway_width_m: float,
    z_start_m: float,
    z_end_m: float,
    longitudinal_points: int,
    vertical_points: int,
    kind: str,
) -> SurfaceGrid:
    y_m, normal_y = _facade_y_and_normal(building, carriageway_width_m)
    x_values = _longitudinal_centres(building.length_m, longitudinal_points)
    z_values = _cell_centres(z_start_m, z_end_m, vertical_points)
    name = building.name if kind == "facade" else f"{building.name}:windows"
    points = tuple(
        CalculationPoint(
            x_m=x_m,
            y_m=y_m,
            z_m=z_m,
            normal_x=0.0,
            normal_y=normal_y,
            normal_z=0.0,
            surface_name=name,
            surface_kind=kind,
        )
        for x_m in x_values
        for z_m in z_values
    )
    return SurfaceGrid(name=name, kind=kind, points=points)


def _building_grids(
    geometry: RoadGeometry,
    vertical_points: int,
) -> tuple[tuple[SurfaceGrid, ...], tuple[SurfaceGrid, ...]]:
    facades: list[SurfaceGrid] = []
    windows: list[SurfaceGrid] = []
    for building in geometry.buildings:
        facades.append(
            _vertical_grid(
                building=building,
                carriageway_width_m=geometry.carriageway_width_m,
                z_start_m=0.0,
                z_end_m=building.facade_height_m,
                longitudinal_points=geometry.longitudinal_points,
                vertical_points=vertical_points,
                kind="facade",
            )
        )
        if building.window_bottom_m is not None and building.window_top_m is not None:
            window_fraction = (
                (building.window_top_m - building.window_bottom_m)
                / building.facade_height_m
            )
            window_vertical_points = max(1, round(vertical_points * window_fraction))
            windows.append(
                _vertical_grid(
                    building=building,
                    carriageway_width_m=geometry.carriageway_width_m,
                    z_start_m=building.window_bottom_m,
                    z_end_m=building.window_top_m,
                    longitudinal_points=geometry.longitudinal_points,
                    vertical_points=window_vertical_points,
                    kind="window",
                )
            )
    return tuple(facades), tuple(windows)


def build_street_calculation_grid(
    geometry: RoadGeometry,
    *,
    band_transverse_points: int = 3,
    facade_vertical_points: int = 6,
    include_intrusion_surfaces: bool = True,
) -> StreetCalculationGrid:
    """Build calculation surfaces for road lighting and intrusion checks."""

    if band_transverse_points < 1:
        raise ValueError("band_transverse_points debe ser al menos 1")
    if facade_vertical_points < 1:
        raise ValueError("facade_vertical_points debe ser al menos 1")

    x_values = _longitudinal_centres(
        geometry.calculation_length_m,
        geometry.longitudinal_points,
    )
    facades, windows = (
        _building_grids(geometry, facade_vertical_points)
        if include_intrusion_surfaces
        else ((), ())
    )
    return StreetCalculationGrid(
        lane_grids=_lane_grids(geometry, x_values),
        band_grids=_band_grids(geometry, x_values, band_transverse_points),
        facade_grids=facades,
        window_grids=windows,
    )
