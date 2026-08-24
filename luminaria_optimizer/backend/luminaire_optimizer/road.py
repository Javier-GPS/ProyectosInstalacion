"""Point-by-point road evaluation for the low-height luminaire."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from .composition import DEFAULT_GROUP_ANGLES_DEG, group_c_rotation_deg
from .hl2x import Hl2xModel, LuminaireOperatingPoint, calculate_luminaire_operating_point
from .ldt import LdtPhotometry
from .normative import MClassRequirements, passes_maximum, passes_minimum, requirements_for
from .r_tables import ReducedLuminanceTable


@dataclass(frozen=True)
class RoadScenario:
    height_m: float
    spacing_m: float
    carriageway_width_m: float = 3.5
    lane_widths_m: tuple[float, ...] = (3.5,)
    arrangement: str = "unilateral"
    pole_side: str = "left"
    arm_length_m: float = 0.0
    edge_offset_m: float = 0.0
    tilt_deg: float = 0.0
    maintenance_factor: float = 0.85
    lighting_class: str = "M3"
    photometry_symmetry: str = "asymmetric"
    observer_distance_m: float = 60.0
    longitudinal_points: int = 10
    transverse_points_per_lane: int = 3

    def __post_init__(self) -> None:
        if self.height_m <= 0 or self.spacing_m <= 0 or self.carriageway_width_m <= 0:
            raise ValueError("height, spacing and road width must be positive")
        if self.edge_offset_m < 0:
            raise ValueError("edge_offset_m cannot be negative")
        if not -10.0 <= self.tilt_deg <= 10.0:
            raise ValueError("tilt_deg must be between -10 and 10 degrees")
        if abs(sum(self.lane_widths_m) - self.carriageway_width_m) > 1e-6:
            raise ValueError("lane widths must sum to carriageway_width_m")
        if self.arrangement not in {"unilateral", "bilateral_paired", "bilateral_staggered"}:
            raise ValueError("unsupported arrangement")
        if self.pole_side not in {"left", "right"}:
            raise ValueError("pole_side must be left or right")
        if self.photometry_symmetry not in {"symmetric", "asymmetric"}:
            raise ValueError("photometry_symmetry must be symmetric or asymmetric")
        if not 0 < self.maintenance_factor <= 1:
            raise ValueError("maintenance_factor must be in (0, 1]")


@dataclass(frozen=True)
class RoadMetrics:
    lavg_cd_m2: float
    uo: float
    ul: float
    ti_pct: float
    rei: float
    emin_luminance_cd_m2: float
    max_luminance_cd_m2: float
    compliant: bool
    criteria: dict[str, bool]
    warnings: tuple[str, ...] = ()
    ti_implemented: bool = False
    power_limit_ok: bool = True


@dataclass(frozen=True)
class RoadCalculation:
    scenario: RoadScenario
    operating_point: LuminaireOperatingPoint
    metrics: RoadMetrics
    visual_grid: dict[str, object] | None = None


@dataclass(frozen=True)
class ReferenceRoadCalculation:
    """Road result evaluated directly from a complete luminaire LDT."""

    metrics: RoadMetrics
    visual_grid: dict[str, object] | None = None


@dataclass(frozen=True)
class VirtualGroupSource:
    """One independently driven group sharing the luminaire position."""

    azimuth_deg: float
    flux_lm: float
    directional_c0_c180: bool = True


@dataclass(frozen=True)
class LuminanceInfluence:
    """Precomputed luminance contribution per lumen of every group."""

    xs_m: tuple[float, ...]
    ys_m: tuple[float, ...]
    lane_matrices: np.ndarray


def precompute_luminance_influence(
    group_ldt: LdtPhotometry,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    angles_deg: tuple[float, ...] = DEFAULT_GROUP_ANGLES_DEG,
) -> LuminanceInfluence:
    """Build the road matrix once, independently of LED currents.

    Each matrix entry is the luminance at one road point produced by one
    lumen from one optical group. This makes relative-current searches a
    matrix multiplication instead of a complete photometric recalculation.
    """
    xs, _, _ = _road_points(scenario)
    lane_ys = _lane_y_points(scenario)
    lane_centres = []
    start = 0.0
    for width in scenario.lane_widths_m:
        lane_centres.append(start + width / 2.0)
        start += width
    matrices = np.zeros((len(lane_ys), len(xs), len(lane_ys[0]), len(angles_deg)), dtype=float)
    positions = _positions(scenario)
    geometry_factor = scenario.maintenance_factor / scenario.height_m**2
    c_rotation = group_c_rotation_deg(group_ldt)
    for lane_index, observer_y in enumerate(lane_centres):
        for x_index, x in enumerate(xs):
            for y_index, y in enumerate(lane_ys[lane_index]):
                for lum_x, lum_y, orientation in positions:
                    distance, c, gamma = _angles_to_point(
                        x - lum_x, y - lum_y, -scenario.height_m, orientation, scenario.tilt_deg,
                    )
                    if distance <= 0:
                        continue
                    if not 0.0 <= c <= 180.0:
                        continue
                    beta = _beta(
                        x, y, lum_x, lum_y,
                        -scenario.observer_distance_m, observer_y,
                    )
                    tan_gamma = math.hypot(x - lum_x, y - lum_y) / scenario.height_m
                    reflection = rtable.value(tan_gamma, beta)
                    if reflection == 0.0:
                        continue
                    factor = reflection * geometry_factor / 1000.0
                    for group_index, angle in enumerate(angles_deg):
                        symmetric = scenario.photometry_symmetry == "symmetric"
                        contribution = _base_group_intensity(
                            group_ldt, c - angle - c_rotation, gamma, symmetric=symmetric,
                        )
                        if symmetric:
                            contribution = 0.5 * (
                                contribution
                                + _base_group_intensity(
                                    group_ldt, 180.0 - c - angle - c_rotation, gamma, symmetric=True,
                                )
                            )
                        matrices[lane_index, x_index, y_index, group_index] += contribution * factor
    return LuminanceInfluence(tuple(xs), tuple(y for lane in lane_ys for y in lane), matrices)


def luminance_from_flux(influence: LuminanceInfluence, group_flux_lm: np.ndarray) -> np.ndarray:
    """Evaluate all road luminance points for one group-flux vector."""
    return np.einsum("lxyg,g->lxy", influence.lane_matrices, group_flux_lm)


def luminance_uniformity(luminance: np.ndarray) -> tuple[float, float, float]:
    """Return worst average luminance, Uo and Ul for influence results."""
    if luminance.size == 0:
        return 0.0, 0.0, 0.0
    averages = np.mean(luminance, axis=(1, 2))
    minima = np.min(luminance, axis=(1, 2))
    uo = np.divide(minima, averages, out=np.zeros_like(minima), where=averages != 0)
    centre_index = luminance.shape[2] // 2
    centreline = luminance[:, :, centre_index]
    longitudinal_min = np.min(centreline, axis=1)
    longitudinal_max = np.max(centreline, axis=1)
    ul = np.divide(
        longitudinal_min, longitudinal_max,
        out=np.zeros_like(longitudinal_min), where=longitudinal_max != 0,
    )
    return float(np.min(averages)), float(np.min(uo)), float(np.min(ul))


def luminance_uniformity_batch(luminance: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return worst average, Uo and Ul for a batch of candidate grids."""
    if luminance.size == 0:
        empty = np.zeros(luminance.shape[0], dtype=float)
        return empty, empty, empty
    averages_by_lane = np.mean(luminance, axis=(2, 3))
    minima_by_lane = np.min(luminance, axis=(2, 3))
    uo_by_lane = np.divide(
        minima_by_lane, averages_by_lane,
        out=np.zeros_like(minima_by_lane), where=averages_by_lane != 0,
    )
    centre_index = luminance.shape[3] // 2
    centreline = luminance[:, :, :, centre_index]
    longitudinal_min = np.min(centreline, axis=2)
    longitudinal_max = np.max(centreline, axis=2)
    ul_by_lane = np.divide(
        longitudinal_min, longitudinal_max,
        out=np.zeros_like(longitudinal_min), where=longitudinal_max != 0,
    )
    return (
        np.min(averages_by_lane, axis=1),
        np.min(uo_by_lane, axis=1),
        np.min(ul_by_lane, axis=1),
    )


def _virtual_sources(operating: LuminaireOperatingPoint, angles_deg: tuple[float, ...] = DEFAULT_GROUP_ANGLES_DEG) -> tuple[VirtualGroupSource, ...]:
    if len(angles_deg) != len(operating.groups):
        raise ValueError("group angle count does not match operating point")
    return tuple(
        VirtualGroupSource(angle, point.group_flux_lm)
        for angle, point in zip(angles_deg, operating.groups)
    )


def _group_intensity_cd(
    group_ldt: LdtPhotometry,
    sources: tuple[VirtualGroupSource, ...],
    c_luminaire_deg: float,
    gamma_deg: float,
    *,
    symmetric: bool = False,
) -> float:
    """Return the absolute candela from the eight virtual groups.

    ``c_luminaire_deg`` is already expressed in the complete luminaire frame.
    Each group samples the unchanged base LDT at the azimuth relative to its
    own optical axis. No composed LDT is generated during road optimization.
    """
    c_rotation = group_c_rotation_deg(group_ldt)

    def total_at(c_deg: float) -> float:
        if any(source.directional_c0_c180 for source in sources) and not 0.0 <= c_deg % 360.0 <= 180.0:
            return 0.0
        return sum(
            _base_group_intensity(
                group_ldt, c_deg - source.azimuth_deg - c_rotation, gamma_deg,
                symmetric=symmetric,
            )
            * source.flux_lm / 1000.0
            for source in sources
        )

    value = total_at(c_luminaire_deg)
    if not symmetric:
        return value
    # Mirror the complete composed luminaire after all group azimuth shifts.
    return 0.5 * (value + total_at((180.0 - c_luminaire_deg) % 360.0))


def _base_group_intensity(
    group_ldt: LdtPhotometry,
    c_deg: float,
    gamma_deg: float,
    *,
    symmetric: bool,
) -> float:
    value = group_ldt.intensity_cd_per_klm(c_deg, gamma_deg)
    if not symmetric:
        return value
    reflected_c = (180.0 - c_deg) % 360.0
    return 0.5 * (value + group_ldt.intensity_cd_per_klm(reflected_c, gamma_deg))


def photometric_azimuth_profile(
    group_ldt: LdtPhotometry,
    operating: LuminaireOperatingPoint,
    *,
    gamma_deg: float = 45.0,
    samples: int = 360,
    symmetric: bool = False,
) -> dict[str, object]:
    """Return the real oriented luminaire profile at one gamma angle.

    The profile is calculated directly from the base group LDT and the eight
    virtual sources. It is intended for orientation diagnostics and export,
    not as a replacement for the point-by-point road calculation.
    """
    if not 0 <= gamma_deg <= 180:
        raise ValueError("gamma_deg must be between 0 and 180")
    if samples < 8:
        raise ValueError("samples must be at least 8")
    sources = _virtual_sources(operating)
    c_rotation = group_c_rotation_deg(group_ldt)
    c_angles = [360.0 * index / samples for index in range(samples)]
    values_cd = [
        _group_intensity_cd(group_ldt, sources, c, gamma_deg, symmetric=symmetric)
        for c in c_angles
    ]
    maximum = max(values_cd, default=0.0)
    group_profiles = []
    for source in sources:
        group_values = [
            (
                _base_group_intensity(
                    group_ldt, c - source.azimuth_deg - c_rotation, gamma_deg, symmetric=symmetric,
                )
                * source.flux_lm / 1000.0
                if 0.0 <= c <= 180.0 else 0.0
            )
            for c in c_angles
        ]
        group_max = max(group_values, default=0.0)
        group_profiles.append({
            "azimuth_deg": source.azimuth_deg,
            "flux_lm": source.flux_lm,
            "intensity_cd": group_values,
            "max_intensity_cd": group_max,
            "normalized": [value / group_max if group_max > 0 else 0.0 for value in group_values],
        })
    return {
        "gamma_deg": gamma_deg,
        "c_angles_deg": c_angles,
        "intensity_cd": values_cd,
        "max_intensity_cd": maximum,
        "normalized": [value / maximum if maximum > 0 else 0.0 for value in values_cd],
        "group_angles_deg": list(DEFAULT_GROUP_ANGLES_DEG),
        "groups": group_profiles,
    }


def _positions(
    scenario: RoadScenario,
    *,
    k_min: int | None = None,
    k_max: int | None = None,
) -> list[tuple[float, float, float]]:
    # International road-lighting convention: C0/C180 are longitudinal and
    # C90/C270 are transverse. Reverse the right row so C90 points inward on
    # both sides while preserving the directional C0..C180 half-plane.
    width = scenario.carriageway_width_m
    periods = max(5, math.ceil(5.0 * scenario.height_m / scenario.spacing_m) + 1)
    k_min = -periods if k_min is None else k_min
    k_max = periods if k_max is None else k_max
    left_y = -scenario.edge_offset_m if scenario.pole_side == "left" else width + scenario.edge_offset_m
    right_y = width + scenario.edge_offset_m if scenario.pole_side == "left" else -scenario.edge_offset_m
    left_orientation = 0.0 if scenario.pole_side == "left" else 180.0
    right_orientation = 180.0 if scenario.pole_side == "left" else 0.0
    if scenario.arrangement == "unilateral":
        return [(k * scenario.spacing_m, left_y, left_orientation) for k in range(k_min, k_max + 1)]
    result = []
    for k in range(k_min, k_max + 1):
        x = k * scenario.spacing_m
        result.append((x, left_y, left_orientation))
        x_right = x if scenario.arrangement == "bilateral_paired" else x + scenario.spacing_m / 2.0
        result.append((x_right, right_y, right_orientation))
    return result


def _world_to_luminaire(dx: float, dy: float, height: float, orientation_deg: float) -> tuple[float, float, float, float]:
    angle = math.radians(-orientation_deg)
    rx = math.cos(angle) * dx - math.sin(angle) * dy
    ry = math.sin(angle) * dx + math.cos(angle) * dy
    distance = math.sqrt(rx * rx + ry * ry + height * height)
    gamma = math.degrees(math.acos(max(-1.0, min(1.0, height / distance))))
    c = math.degrees(math.atan2(ry, rx)) % 360.0
    return rx, ry, distance, c if distance > 0 else 0.0


def _angles_to_point(dx: float, dy: float, dz: float, orientation_deg: float, tilt_deg: float = 0.0) -> tuple[float, float, float]:
    """Return distance, C and gamma for a point in 3D.

    ``gamma=0`` is nadir, matching EULUMDAT. A point above the luminaire can
    therefore produce gamma > 90 degrees; the LDT sampler then applies its
    explicit boundary policy instead of silently inventing upper-hemisphere
    photometry.
    """
    angle = math.radians(-orientation_deg)
    rx = math.cos(angle) * dx - math.sin(angle) * dy
    ry = math.sin(angle) * dx + math.cos(angle) * dy
    tilt = math.radians(tilt_deg)
    tilted_rx = math.cos(tilt) * rx + math.sin(tilt) * dz
    tilted_dz = -math.sin(tilt) * rx + math.cos(tilt) * dz
    rx, dz = tilted_rx, tilted_dz
    distance = math.sqrt(rx * rx + ry * ry + dz * dz)
    if distance <= 0:
        return 0.0, 0.0, 0.0
    return distance, math.degrees(math.atan2(ry, rx)) % 360.0, math.degrees(math.acos(max(-1.0, min(1.0, -dz / distance))))


def _beta(point_x: float, point_y: float, lum_x: float, lum_y: float, observer_x: float, observer_y: float) -> float:
    """Return CIE 140 beta, not the raw plan-angle difference.

    The CIE/luxStudio convention is ``beta = 180 - theta`` where theta is the
    angle between observer-to-point and luminaire-to-point directions. Using
    theta directly selects the wrong C2/R-table column and can inflate road
    luminance substantially.
    """
    lp = math.atan2(point_y - lum_y, point_x - lum_x)
    op = math.atan2(point_y - observer_y, point_x - observer_x)
    theta = abs(math.degrees(lp - op)) % 360.0
    if theta > 180.0:
        theta = 360.0 - theta
    return 180.0 - theta


def _road_points(scenario: RoadScenario) -> tuple[list[float], list[float], list[int]]:
    longitudinal_count = (
        10 if scenario.spacing_m <= 30.0
        else max(10, math.ceil(scenario.spacing_m / 3.0))
    )
    xs = [
        (2 * index - 1) * scenario.spacing_m / (2 * longitudinal_count)
        for index in range(1, longitudinal_count + 1)
    ]
    ys: list[float] = []
    lane_for_y: list[int] = []
    y_start = 0.0
    for lane_index, lane_width in enumerate(scenario.lane_widths_m):
        for index in range(scenario.transverse_points_per_lane):
            ys.append(y_start + (index + 0.5) * lane_width / scenario.transverse_points_per_lane)
            lane_for_y.append(lane_index)
        y_start += lane_width
    return xs, ys, lane_for_y


def _lane_y_points(scenario: RoadScenario) -> tuple[tuple[float, ...], ...]:
    lanes: list[tuple[float, ...]] = []
    y_start = 0.0
    for lane_width in scenario.lane_widths_m:
        lanes.append(tuple(
            y_start + (index + 0.5) * lane_width / scenario.transverse_points_per_lane
            for index in range(scenario.transverse_points_per_lane)
        ))
        y_start += lane_width
    return tuple(lanes)


def _luminance_grid(
    group_ldt: LdtPhotometry,
    sources: tuple[VirtualGroupSource, ...],
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    observer_y: float,
    ys: list[float] | tuple[float, ...] | None = None,
) -> list[list[float]]:
    xs, road_ys, _ = _road_points(scenario)
    ys = road_ys if ys is None else ys
    luminance: list[list[float]] = []
    for x in xs:
        row: list[float] = []
        for y in ys:
            value = 0.0
            for lx, ly, orientation in _positions(scenario):
                distance, c, gamma = _angles_to_point(x - lx, y - ly, -scenario.height_m, orientation, scenario.tilt_deg)
                if distance <= 0:
                    continue
                intensity = _group_intensity_cd(
                    group_ldt, sources, c, gamma,
                    symmetric=scenario.photometry_symmetry == "symmetric",
                )
                beta = _beta(x, y, lx, ly, -scenario.observer_distance_m, observer_y)
                tan_gamma = math.hypot(x - lx, y - ly) / scenario.height_m
                value += intensity * rtable.value(tan_gamma, beta) / scenario.height_m**2 * scenario.maintenance_factor
            row.append(value)
        luminance.append(row)
    return luminance


def _illuminance_grid(
    group_ldt: LdtPhotometry,
    sources: tuple[VirtualGroupSource, ...],
    scenario: RoadScenario,
) -> list[list[float]]:
    xs, ys, _ = _road_points(scenario)
    grid: list[list[float]] = []
    for x in xs:
        row: list[float] = []
        for y in ys:
            value = 0.0
            for lx, ly, orientation in _positions(scenario):
                distance, c, gamma = _angles_to_point(x - lx, y - ly, -scenario.height_m, orientation, scenario.tilt_deg)
                if distance <= 0:
                    continue
                intensity = _group_intensity_cd(
                    group_ldt, sources, c, gamma,
                    symmetric=scenario.photometry_symmetry == "symmetric",
                )
                value += intensity * scenario.height_m / distance**3 * scenario.maintenance_factor
            row.append(value)
        grid.append(row)
    return grid


def _calculate_road_for_sources(
    group_ldt: LdtPhotometry,
    sources: tuple[VirtualGroupSource, ...],
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    include_visual_grid: bool,
    include_glare_metrics: bool,
    power_limit_ok: bool,
    power_input_w: float | None = None,
) -> tuple[RoadMetrics, dict[str, object] | None]:
    xs, ys, _ = _road_points(scenario)
    lane_ys = _lane_y_points(scenario)
    lane_centres = []
    start = 0.0
    for width in scenario.lane_widths_m:
        lane_centres.append(start + width / 2.0)
        start += width
    per_lane = [
        _luminance_grid(
            group_ldt, sources, scenario, rtable,
            observer_y=observer_y, ys=lane_ys[lane_index],
        )
        for lane_index, observer_y in enumerate(lane_centres)
    ]
    lane_metrics = []
    for grid in per_lane:
        flat = [value for row in grid for value in row]
        average = sum(flat) / len(flat) if flat else 0.0
        minimum = min(flat) if flat else 0.0
        maximum = max(flat) if flat else 0.0
        uo = minimum / average if average else 0.0
        centre_index = len(grid[0]) // 2 if grid and grid[0] else 0
        centreline = [row[centre_index] for row in grid if row]
        ul = min(centreline) / max(centreline) if centreline and max(centreline) else 0.0
        lane_metrics.append((average, minimum, maximum, uo, ul))
    worst_lane_index = min(range(len(lane_metrics)), key=lambda index: lane_metrics[index][0])
    worst_lavg, _, _, worst_uo, _ = lane_metrics[worst_lane_index]
    worst_uo = min(item[3] for item in lane_metrics)
    worst_ul = min(item[4] for item in lane_metrics)
    worst_minimum = min(item[1] for item in lane_metrics)
    worst_maximum = max(item[2] for item in lane_metrics)
    ti = max(
        _calculate_ti(
            group_ldt, sources, scenario,
            average / scenario.maintenance_factor,
        )
        for average, *_ in lane_metrics
    ) if include_glare_metrics else 0.0
    rei = _calculate_rei(group_ldt, sources, scenario) if include_glare_metrics else 0.0
    req = requirements_for(scenario.lighting_class)
    criteria = {
        "Lavg": passes_minimum(worst_lavg, req.luminance_avg_cd_m2, 2),
        "Uo": passes_minimum(worst_uo, req.uo_min, 2),
        "Ul": passes_minimum(worst_ul, req.ul_min, 2),
        "TI": passes_maximum(ti, req.ti_max_pct, 0) if include_glare_metrics else True,
        "REI": passes_minimum(rei, req.rei_min, 2) if include_glare_metrics else True,
    }
    warnings = []
    if include_glare_metrics and group_ldt.gamma_angles_deg[-1] < 180.0:
        warnings.append("El LDT no contiene gamma > 90 grados; el TI no puede certificarse para esta altura")
    criteria["Power"] = power_limit_ok
    if not power_limit_ok:
        power_text = f"{power_input_w:.1f} W" if power_input_w is not None else "el límite"
        warnings.append(f"Potencia de entrada {power_text} supera el limite de 30.0 W")
    metrics = RoadMetrics(
        worst_lavg, worst_uo, worst_ul, ti, rei, worst_minimum, worst_maximum,
        all(criteria.values()) and not warnings, criteria, tuple(warnings), True,
        power_limit_ok,
    )
    visual_grid = None
    if include_visual_grid:
        lane_visual_grids = []
        lane_profiles = []
        for lane_index, observer_y in enumerate(lane_centres):
            lane_luminance = _luminance_grid(
                group_ldt, sources, scenario, rtable,
                observer_y=observer_y, ys=ys,
            )
            lane_visual_grids.append({
                "lane_index": lane_index,
                "observer_y_m": observer_y,
                "luminance_cd_m2": lane_luminance,
            })
            lane_profiles.append({
                "lane_index": lane_index,
                "observer_y_m": observer_y,
                "luminance_cd_m2": [
                    sum(row) / len(row) if row else 0.0 for row in per_lane[lane_index]
                ],
            })
        visual_luminance = lane_visual_grids[0]["luminance_cd_m2"]
        visual_grid = {
            "xs_m": list(xs),
            "ys_m": list(ys),
            "illuminance_lx": _illuminance_grid(group_ldt, sources, scenario),
            "luminance_cd_m2": visual_luminance,
            "lane_grids": lane_visual_grids,
            "lane_profiles": lane_profiles,
            "worst_lane_index": worst_lane_index,
            "normative_profile": lane_profiles[worst_lane_index],
            "lane_centres_m": lane_centres,
            "lane_widths_m": list(scenario.lane_widths_m),
            "observer_x_m": -scenario.observer_distance_m,
            "observer_distance_m": scenario.observer_distance_m,
        }
    return metrics, visual_grid


def calculate_road(
    group_ldt: LdtPhotometry,
    model: Hl2xModel,
    currents_ma: list[float] | tuple[float, ...],
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    cct_k: int,
    cri: int,
    include_visual_grid: bool = True,
    include_glare_metrics: bool = True,
) -> RoadCalculation:
    operating = calculate_luminaire_operating_point(currents_ma, model, cct_k, cri)
    metrics, visual_grid = _calculate_road_for_sources(
        group_ldt,
        _virtual_sources(operating),
        scenario,
        rtable,
        include_visual_grid=include_visual_grid,
        include_glare_metrics=include_glare_metrics,
        power_limit_ok=operating.power_limit_ok,
        power_input_w=operating.total_driver_power_w,
    )
    return RoadCalculation(scenario, operating, metrics, visual_grid)


def calculate_reference_road(
    luminaire_ldt: LdtPhotometry,
    scenario: RoadScenario,
    rtable: ReducedLuminanceTable,
    *,
    include_visual_grid: bool = True,
    include_glare_metrics: bool = True,
) -> ReferenceRoadCalculation:
    """Evaluate a complete LDT independently from the eight-group model."""
    # The uploaded reference must remain an exact photometric benchmark even
    # when the active design scenario is configured for optional symmetry.
    reference_scenario = replace(scenario, photometry_symmetry="asymmetric")
    metrics, visual_grid = _calculate_road_for_sources(
        luminaire_ldt,
        (VirtualGroupSource(0.0, luminaire_ldt.flux_lm, directional_c0_c180=False),),
        reference_scenario,
        rtable,
        include_visual_grid=include_visual_grid,
        include_glare_metrics=include_glare_metrics,
        power_limit_ok=True,
    )
    return ReferenceRoadCalculation(metrics, visual_grid)


def _calculate_ti(
    group_ldt: LdtPhotometry,
    sources: tuple[VirtualGroupSource, ...],
    scenario: RoadScenario,
    lavg: float,
) -> float:
    """Implement the EN 13201-3 veiling-luminance sweep used by SALVI."""
    # Use the centre of every lane and the operative longitudinal sweep.
    best = 0.0
    longitudinal_count = (
        10 if scenario.spacing_m <= 30.0
        else max(10, math.ceil(scenario.spacing_m / 3.0))
    )
    ti_periods = max(5, math.ceil(500.0 / max(scenario.spacing_m, 0.1)) + 2)
    for lane_start, lane_width in _lane_ranges(scenario):
        y_obs = lane_start + lane_width / 2.0
        for index in range(longitudinal_count):
            observer_x = -2.75 * max(0.0, scenario.height_m - 1.5) + index * scenario.spacing_m / longitudinal_count
            lv = 0.0
            for lx, ly, orientation in _positions(
                scenario, k_min=-ti_periods, k_max=ti_periods,
            ):
                dx, dy = lx - observer_x, ly - y_obs
                vertical = 1.5 - scenario.height_m
                distance, c, gamma = _angles_to_point(-dx, -dy, vertical, orientation, scenario.tilt_deg)
                if distance <= 0 or dx <= 0 or dx > 500:
                    continue
                lum_vertical = scenario.height_m - 1.5
                cos_theta = (dx * math.cos(math.radians(-1.0)) + lum_vertical * math.sin(math.radians(-1.0))) / distance
                cos_theta = max(-1.0, min(1.0, cos_theta))
                theta = math.degrees(math.acos(cos_theta))
                if theta <= 0.1 or theta > 60.0:
                    continue
                intensity = _group_intensity_cd(
                    group_ldt, sources, c, gamma,
                    symmetric=scenario.photometry_symmetry == "symmetric",
                )
                e_eye = intensity * cos_theta / (distance * distance)
                if theta <= 1.5:
                    lv += e_eye * (10.0 / theta**3 + 5.0 / theta**2 * (1.0 + (23.0 / 62.5) ** 4))
                else:
                    lv += 9.86 * (1.0 + (23.0 / 66.4) ** 4) * e_eye / theta**2
            ti = 65.0 * lv / lavg**0.8 if 0.05 <= lavg <= 5 else 95.0 * lv / lavg**1.05 if lavg > 5 else 999.0
            best = max(best, ti)
    return best


def _lane_ranges(scenario: RoadScenario):
    start = 0.0
    for width in scenario.lane_widths_m:
        yield start, width
        start += width


def _calculate_rei(
    group_ldt: LdtPhotometry,
    sources: tuple[VirtualGroupSource, ...],
    scenario: RoadScenario,
) -> float:
    """Calculate the minimum outer/inner illuminance strip ratio."""
    lane_width = scenario.carriageway_width_m / max(len(scenario.lane_widths_m), 1)
    strip_width = min(lane_width, scenario.carriageway_width_m / 2.0)
    samples = max(3, math.ceil(strip_width / 1.5))
    left_outer = [-strip_width + (i + 0.5) * strip_width / samples for i in range(samples)]
    right_outer = [scenario.carriageway_width_m + (i + 0.5) * strip_width / samples for i in range(samples)]
    left_inner = [(i + 0.5) * strip_width / samples for i in range(samples)]
    right_start = scenario.carriageway_width_m - strip_width
    right_inner = [right_start + (i + 0.5) * strip_width / samples for i in range(samples)]
    xs, _, _ = _road_points(scenario)

    def average_at(points):
        values = []
        for y in points:
            for x in xs:
                value = 0.0
                for lx, ly, orientation in _positions(scenario):
                    distance, c, gamma = _angles_to_point(x - lx, y - ly, -scenario.height_m, orientation, scenario.tilt_deg)
                    if distance:
                        value += _group_intensity_cd(
                            group_ldt, sources, c, gamma,
                            symmetric=scenario.photometry_symmetry == "symmetric",
                        ) * scenario.height_m / distance**3 * scenario.maintenance_factor
                values.append(value)
        return sum(values) / len(values) if values else 0.0
    left_inner_average = average_at(left_inner)
    right_inner_average = average_at(right_inner)
    left = average_at(left_outer) / left_inner_average if left_inner_average else 0.0
    right = average_at(right_outer) / right_inner_average if right_inner_average else 0.0
    return min(left, right)
