import pytest

from road_ldt_designer.road_ldt.domain import (
    AdjacentBuilding,
    IntrusionLimits,
    LuminaireArrangement,
    LuminairePlacement,
    OptimizationRequest,
    PhotometricCandidate,
    QualityTargets,
    RoadGeometry,
    StreetBand,
)
from road_ldt_designer.road_ldt.evaluator import (
    EvaluationOptions,
    evaluate_candidate,
)


def _constant_candidate(intensity_cd_per_klm_value: float = 1000.0):
    return PhotometricCandidate(
        c_angles_deg=(0.0, 90.0, 180.0, 270.0),
        gamma_angles_deg=(0.0, 45.0, 90.0, 135.0, 180.0),
        intensity_cd_per_klm=tuple(
            tuple(intensity_cd_per_klm_value for _ in range(5))
            for _ in range(4)
        ),
        flux_lm=1000.0,
    )


def _request() -> OptimizationRequest:
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.5, 3.5),
        calculation_length_m=20.0,
        longitudinal_points=4,
        transverse_points_per_lane=3,
        side_bands=(
            StreetBand(
                "acera izquierda",
                "left",
                2.0,
                target_illuminance_min_lx=0.01,
            ),
            StreetBand("acera derecha", "right", 2.0),
        ),
        buildings=(
            AdjacentBuilding(
                "edificio izquierdo",
                "left",
                setback_m=5.0,
                facade_height_m=10.0,
                length_m=20.0,
                window_bottom_m=1.0,
                window_top_m=8.0,
                max_vertical_illuminance_lx=100.0,
                max_window_illuminance_lx=100.0,
            ),
        ),
    )
    arrangement = LuminaireArrangement(
        placements=(
            LuminairePlacement(0.0, -1.0, 8.0, 1000.0),
        ),
        nominal_spacing_m=20.0,
    )
    return OptimizationRequest(
        geometry=geometry,
        arrangement=arrangement,
        targets=QualityTargets(
            uo_min=0.0,
            ul_min=0.0,
            ti_max_pct=10000.0,
        ),
        intrusion_limits=IntrusionLimits(
            max_vertical_illuminance_lx=100.0,
            max_window_illuminance_lx=100.0,
        ),
    )


def test_intrusion_is_disabled_by_default_and_not_part_of_compliance():
    result = evaluate_candidate(_request(), _constant_candidate())

    assert not result.options.evaluate_intrusion
    assert result.metrics.building_vertical_illuminance_lx == {}
    assert result.metrics.building_window_illuminance_lx == {}
    assert result.metrics.intrusion_max_lx is None
    assert result.calculation_grid.facade_grids == ()
    assert result.calculation_grid.window_grids == ()
    assert not any(
        name.startswith(("facade:", "window:", "intrusion:"))
        for name in result.compliance.checks
    )


def test_intrusion_can_be_enabled_explicitly():
    result = evaluate_candidate(
        _request(),
        _constant_candidate(),
        options=EvaluationOptions(evaluate_intrusion=True),
    )

    assert result.metrics.building_vertical_illuminance_lx[
        "edificio izquierdo"
    ] > 0.0
    assert result.metrics.building_window_illuminance_lx[
        "edificio izquierdo"
    ] > 0.0
    assert result.metrics.intrusion_max_lx is not None
    assert result.calculation_grid.facade_grids
    assert result.calculation_grid.window_grids
    assert "facade:edificio izquierdo" in result.compliance.checks
    assert "window:edificio izquierdo" in result.compliance.checks
    assert "intrusion:vertical" in result.compliance.checks
    assert "intrusion:window" in result.compliance.checks


def test_unified_evaluator_returns_core_metrics_and_periodic_extension():
    result = evaluate_candidate(_request(), _constant_candidate())

    assert result.metrics.luminance_avg_cd_m2 is not None
    assert result.metrics.uo is not None
    assert result.metrics.ul is not None
    assert result.metrics.ti_pct is not None
    assert result.metrics.rei is not None
    assert result.metrics.sr is not None
    assert "acera izquierda" in result.metrics.band_illuminance_lx
    assert len(result.evaluated_luminaires) > 1
    assert "band:acera izquierda:min" in result.compliance.checks


def test_evaluator_rejects_asymmetric_candidate():
    asymmetric = PhotometricCandidate(
        c_angles_deg=(0.0, 90.0, 180.0, 270.0),
        gamma_angles_deg=(0.0, 90.0),
        intensity_cd_per_klm=(
            (100.0, 100.0),
            (100.0, 100.0),
            (0.0, 0.0),
            (100.0, 100.0),
        ),
        flux_lm=1000.0,
    )

    with pytest.raises(ValueError, match="no es simétrico"):
        evaluate_candidate(_request(), asymmetric)


def test_evaluation_options_validate_maintenance_factor():
    with pytest.raises(ValueError, match="maintenance_factor"):
        EvaluationOptions(maintenance_factor=1.1)
