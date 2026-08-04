"""Unified evaluation of one symmetric road-lighting LDT candidate."""
from __future__ import annotations

from dataclasses import dataclass

from .compliance import ComplianceResult, evaluate_compliance
from .direct_illuminance import evaluate_direct_illuminance
from .domain import (
    CalculationMetrics,
    LuminairePlacement,
    OptimizationRequest,
    PhotometricCandidate,
)
from .edge_metrics import (
    EdgeIlluminanceResult,
    build_edge_strip_grid,
    evaluate_edge_illuminance,
)
from .glare import (
    StreetThresholdIncrementResult,
    evaluate_street_threshold_increment,
)
from .periodic import repeat_luminaire_pattern
from .photometric_symmetry import validate_longitudinal_symmetry
from .road_luminance import StreetLuminanceResult, evaluate_street_luminance
from .street_geometry import (
    StreetCalculationGrid,
    SurfaceGrid,
    build_street_calculation_grid,
)


@dataclass(frozen=True)
class EvaluationOptions:
    """Select optional calculation families for a candidate evaluation."""

    maintenance_factor: float = 0.80
    evaluate_edge_metrics: bool = True
    evaluate_side_bands: bool = True
    evaluate_intrusion: bool = False
    calculation_backend: str = "scalar"

    def __post_init__(self) -> None:
        if not 0.0 <= self.maintenance_factor <= 1.0:
            raise ValueError("maintenance_factor debe estar entre 0 y 1")
        if self.calculation_backend not in {"scalar", "numpy"}:
            raise ValueError("calculation_backend debe ser 'scalar' o 'numpy'")


@dataclass(frozen=True)
class CandidateEvaluation:
    """Traceable result returned to the future optimizer and API."""

    metrics: CalculationMetrics
    compliance: ComplianceResult
    options: EvaluationOptions
    calculation_grid: StreetCalculationGrid
    evaluated_luminaires: tuple[LuminairePlacement, ...]
    luminance: StreetLuminanceResult
    threshold_increment: StreetThresholdIncrementResult | None
    edge_illuminance: EdgeIlluminanceResult | None


def _expanded_luminaires(
    request: OptimizationRequest,
    grid: StreetCalculationGrid,
) -> tuple[LuminairePlacement, ...]:
    placements = request.arrangement.placements
    period = request.arrangement.nominal_spacing_m
    if period is None:
        return placements

    maximum_height = max(item.mounting_height_m for item in placements)
    x_values = tuple(point.x_m for point in grid.road_points)
    return repeat_luminaire_pattern(
        placements,
        period,
        x_min_m=min(x_values) - 5.0 * maximum_height,
        x_max_m=max(x_values) + max(12.0 * maximum_height, 500.0),
    )


def _surface_average_illuminance(
    candidate: PhotometricCandidate,
    luminaires: tuple[LuminairePlacement, ...],
    grids: tuple[SurfaceGrid, ...],
    maintenance_factor: float,
    calculation_backend: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for grid in grids:
        if calculation_backend == "numpy":
            from .numpy_backend import direct_illuminance_values_numpy

            result_values = direct_illuminance_values_numpy(
                candidate,
                luminaires,
                grid.points,
                maintenance_factor=maintenance_factor,
            )
            values[grid.name] = (
                float(result_values.mean()) if len(result_values) else 0.0
            )
        else:
            results = evaluate_direct_illuminance(
                candidate,
                luminaires,
                grid.points,
                maintenance_factor=maintenance_factor,
            )
            values[grid.name] = (
                sum(item.illuminance_lx for item in results) / len(results)
                if results
                else 0.0
            )
    return values


def _surface_maximum_illuminance(
    candidate: PhotometricCandidate,
    luminaires: tuple[LuminairePlacement, ...],
    grids: tuple[SurfaceGrid, ...],
    maintenance_factor: float,
    calculation_backend: str,
    *,
    remove_suffix: str = "",
) -> dict[str, float]:
    values: dict[str, float] = {}
    for grid in grids:
        if calculation_backend == "numpy":
            from .numpy_backend import direct_illuminance_values_numpy

            result_values = direct_illuminance_values_numpy(
                candidate,
                luminaires,
                grid.points,
                maintenance_factor=maintenance_factor,
            )
            maximum = float(result_values.max()) if len(result_values) else 0.0
        else:
            results = evaluate_direct_illuminance(
                candidate,
                luminaires,
                grid.points,
                maintenance_factor=maintenance_factor,
            )
            maximum = max(
                (item.illuminance_lx for item in results),
                default=0.0,
            )
        name = (
            grid.name.removesuffix(remove_suffix)
            if remove_suffix
            else grid.name
        )
        values[name] = maximum
    return values


def evaluate_candidate(
    request: OptimizationRequest,
    candidate: PhotometricCandidate,
    *,
    options: EvaluationOptions | None = None,
) -> CandidateEvaluation:
    """Evaluate one LDT candidate using only the selected calculation scope."""

    selected = options or EvaluationOptions()
    if request.require_longitudinal_symmetry:
        validate_longitudinal_symmetry(candidate)

    grid = build_street_calculation_grid(
        request.geometry,
        include_intrusion_surfaces=selected.evaluate_intrusion,
    )
    luminaires = _expanded_luminaires(request, grid)
    warnings: list[str] = []
    if request.arrangement.nominal_spacing_m is None:
        warnings.append(
            "TI y luminancia se han evaluado con las luminarias explícitas; "
            "no se ha aplicado extensión periódica"
        )

    if selected.calculation_backend == "numpy":
        from .numpy_backend import evaluate_street_luminance_numpy

        luminance = evaluate_street_luminance_numpy(
            candidate,
            luminaires,
            request.geometry,
            grid,
            maintenance_factor=selected.maintenance_factor,
        )
    else:
        luminance = evaluate_street_luminance(
            candidate,
            luminaires,
            request.geometry,
            grid,
            maintenance_factor=selected.maintenance_factor,
        )

    if selected.maintenance_factor > 0:
        initial_luminance_by_lane = {
            item.observer.lane_index: (
                item.luminance_avg_cd_m2 / selected.maintenance_factor
            )
            for item in luminance.observer_results
        }
    else:
        initial_luminance_by_lane = None

    threshold_increment: StreetThresholdIncrementResult | None
    try:
        threshold_increment = evaluate_street_threshold_increment(
            candidate,
            luminaires,
            request.geometry,
            grid,
            initial_luminance_by_lane=initial_luminance_by_lane,
        )
    except ValueError as error:
        if "fTI requiere" not in str(error):
            raise
        threshold_increment = None
        warnings.append(str(error))

    edge_illuminance: EdgeIlluminanceResult | None = None
    if selected.evaluate_edge_metrics:
        edge_grid = build_edge_strip_grid(request.geometry)
        if selected.calculation_backend == "numpy":
            from .numpy_backend import evaluate_edge_illuminance_numpy

            edge_illuminance = evaluate_edge_illuminance_numpy(
                candidate,
                luminaires,
                edge_grid,
                maintenance_factor=selected.maintenance_factor,
            )
        else:
            edge_illuminance = evaluate_edge_illuminance(
                candidate,
                luminaires,
                edge_grid,
                maintenance_factor=selected.maintenance_factor,
            )

    band_illuminance = (
        _surface_average_illuminance(
            candidate,
            luminaires,
            grid.band_grids,
            selected.maintenance_factor,
            selected.calculation_backend,
        )
        if selected.evaluate_side_bands
        else {}
    )

    facade_illuminance: dict[str, float] = {}
    window_illuminance: dict[str, float] = {}
    intrusion_max: float | None = None
    if selected.evaluate_intrusion:
        facade_illuminance = _surface_maximum_illuminance(
            candidate,
            luminaires,
            grid.facade_grids,
            selected.maintenance_factor,
            selected.calculation_backend,
        )
        window_illuminance = _surface_maximum_illuminance(
            candidate,
            luminaires,
            grid.window_grids,
            selected.maintenance_factor,
            selected.calculation_backend,
            remove_suffix=":windows",
        )
        intrusion_values = tuple(facade_illuminance.values()) + tuple(
            window_illuminance.values()
        )
        intrusion_max = max(intrusion_values, default=0.0)

    metrics = CalculationMetrics(
        luminance_avg_cd_m2=luminance.luminance_avg_cd_m2,
        uo=luminance.uo,
        ul=luminance.ul,
        ti_pct=(
            threshold_increment.ti_pct
            if threshold_increment is not None
            else None
        ),
        sr=edge_illuminance.sr if edge_illuminance is not None else None,
        rei=edge_illuminance.rei if edge_illuminance is not None else None,
        band_illuminance_lx=band_illuminance,
        building_vertical_illuminance_lx=facade_illuminance,
        building_window_illuminance_lx=window_illuminance,
        intrusion_max_lx=intrusion_max,
        warnings=tuple(warnings),
    )
    compliance = evaluate_compliance(
        metrics,
        request.targets,
        request.normative_profile,
        geometry=request.geometry if selected.evaluate_side_bands else None,
        intrusion_limits=(
            request.intrusion_limits if selected.evaluate_intrusion else None
        ),
        intrusion_evaluated=selected.evaluate_intrusion,
    )
    return CandidateEvaluation(
        metrics=metrics,
        compliance=compliance,
        options=selected,
        calculation_grid=grid,
        evaluated_luminaires=luminaires,
        luminance=luminance,
        threshold_increment=threshold_increment,
        edge_illuminance=edge_illuminance,
    )
