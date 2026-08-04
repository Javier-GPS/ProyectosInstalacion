import pytest

from road_ldt_designer.road_ldt.candidate_generator import (
    DEFAULT_RESOLUTION_STAGES,
    PhotometricFamilyParameters,
    generate_symmetric_candidate,
)
from road_ldt_designer.road_ldt.direct_illuminance import (
    evaluate_direct_illuminance,
)
from road_ldt_designer.road_ldt.domain import (
    AdjacentBuilding,
    LuminaireArrangement,
    LuminairePlacement,
    OptimizationRequest,
    QualityTargets,
    RoadGeometry,
    StreetBand,
)
from road_ldt_designer.road_ldt.evaluator import (
    EvaluationOptions,
    evaluate_candidate,
)
from road_ldt_designer.road_ldt.numpy_backend import (
    evaluate_direct_illuminance_numpy,
    evaluate_street_luminance_numpy,
)
from road_ldt_designer.road_ldt.road_luminance import (
    evaluate_street_luminance,
)
from road_ldt_designer.road_ldt.street_geometry import (
    build_street_calculation_grid,
)


def _geometry():
    return RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.5, 3.5),
        calculation_length_m=20.0,
        longitudinal_points=4,
        transverse_points_per_lane=3,
        side_bands=(StreetBand("acera", "left", 2.0),),
        buildings=(
            AdjacentBuilding(
                "edificio",
                "left",
                setback_m=5.0,
                facade_height_m=8.0,
                length_m=20.0,
                window_bottom_m=1.0,
                window_top_m=6.0,
            ),
        ),
    )


def _candidate():
    return generate_symmetric_candidate(
        PhotometricFamilyParameters(flux_lm=10000.0),
        resolution=DEFAULT_RESOLUTION_STAGES[0],
    )


def _luminaires():
    return tuple(
        LuminairePlacement(
            float(x_m),
            -1.0,
            8.0,
            10000.0,
            orientation_deg=5.0,
            tilt_deg=3.0,
        )
        for x_m in (-20, 0, 20, 40)
    )


def test_numpy_direct_illuminance_matches_scalar_reference():
    grid = build_street_calculation_grid(
        _geometry(),
        include_intrusion_surfaces=True,
    )
    scalar = evaluate_direct_illuminance(
        _candidate(),
        _luminaires(),
        grid.all_points,
        maintenance_factor=0.8,
    )
    vectorized = evaluate_direct_illuminance_numpy(
        _candidate(),
        _luminaires(),
        grid.all_points,
        maintenance_factor=0.8,
    )

    assert [item.illuminance_lx for item in vectorized] == pytest.approx(
        [item.illuminance_lx for item in scalar],
        rel=1e-11,
        abs=1e-12,
    )


def test_numpy_road_luminance_matches_scalar_reference():
    geometry = _geometry()
    grid = build_street_calculation_grid(geometry)
    scalar = evaluate_street_luminance(
        _candidate(),
        _luminaires(),
        geometry,
        grid,
        maintenance_factor=0.8,
    )
    vectorized = evaluate_street_luminance_numpy(
        _candidate(),
        _luminaires(),
        geometry,
        grid,
        maintenance_factor=0.8,
    )

    assert vectorized.luminance_avg_cd_m2 == pytest.approx(
        scalar.luminance_avg_cd_m2,
        rel=1e-11,
    )
    assert vectorized.uo == pytest.approx(scalar.uo, rel=1e-11)
    assert vectorized.ul == pytest.approx(scalar.ul, rel=1e-11)


def test_unified_numpy_backend_matches_scalar_with_optional_intrusion():
    request = OptimizationRequest(
        geometry=_geometry(),
        arrangement=LuminaireArrangement(
            placements=(
                LuminairePlacement(
                    0.0,
                    -1.0,
                    8.0,
                    10000.0,
                    orientation_deg=5.0,
                    tilt_deg=3.0,
                ),
            ),
            nominal_spacing_m=20.0,
        ),
        targets=QualityTargets(uo_min=0.0, ul_min=0.0, ti_max_pct=1000.0),
    )
    scalar = evaluate_candidate(
        request,
        _candidate(),
        options=EvaluationOptions(
            evaluate_intrusion=True,
            calculation_backend="scalar",
        ),
    )
    vectorized = evaluate_candidate(
        request,
        _candidate(),
        options=EvaluationOptions(
            evaluate_intrusion=True,
            calculation_backend="numpy",
        ),
    )

    assert vectorized.metrics.luminance_avg_cd_m2 == pytest.approx(
        scalar.metrics.luminance_avg_cd_m2,
        rel=1e-10,
    )
    assert vectorized.metrics.uo == pytest.approx(scalar.metrics.uo, rel=1e-10)
    assert vectorized.metrics.ul == pytest.approx(scalar.metrics.ul, rel=1e-10)
    assert vectorized.metrics.ti_pct == pytest.approx(
        scalar.metrics.ti_pct,
        rel=1e-10,
    )
    assert vectorized.metrics.rei == pytest.approx(
        scalar.metrics.rei,
        rel=1e-10,
    )
    assert vectorized.metrics.band_illuminance_lx == pytest.approx(
        scalar.metrics.band_illuminance_lx,
        rel=1e-10,
    )
    assert vectorized.metrics.building_vertical_illuminance_lx == pytest.approx(
        scalar.metrics.building_vertical_illuminance_lx,
        rel=1e-10,
    )
    assert vectorized.metrics.building_window_illuminance_lx == pytest.approx(
        scalar.metrics.building_window_illuminance_lx,
        rel=1e-10,
    )
