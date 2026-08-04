from road_ldt_designer.road_ldt.candidate_generator import (
    DEFAULT_RESOLUTION_STAGES,
)
from road_ldt_designer.road_ldt.domain import (
    LuminaireArrangement,
    LuminairePlacement,
    OptimizationRequest,
    QualityTargets,
    RoadGeometry,
)
from road_ldt_designer.road_ldt.optimizer import (
    OptimizationConfig,
    optimize_candidate,
)
from road_ldt_designer.road_ldt.photometric_symmetry import (
    is_longitudinally_symmetric,
)


def _small_request():
    return OptimizationRequest(
        geometry=RoadGeometry(
            carriageway_width_m=7.0,
            lane_widths_m=(3.5, 3.5),
            calculation_length_m=20.0,
            longitudinal_points=2,
            transverse_points_per_lane=1,
        ),
        arrangement=LuminaireArrangement(
            placements=(LuminairePlacement(0.0, -1.0, 8.0, 10000.0),),
            nominal_spacing_m=20.0,
        ),
        targets=QualityTargets(
            uo_min=0.0,
            ul_min=0.0,
            ti_max_pct=10000.0,
        ),
        max_candidates=2,
    )


def test_progressive_optimizer_respects_budget_and_round_trips_ldt():
    coarse = DEFAULT_RESOLUTION_STAGES[0]
    config = OptimizationConfig(
        stages=(coarse,),
        samples_per_stage=(2,),
        mutation_scales=(1.0,),
        elite_count=2,
        random_seed=123,
        export_resolution=coarse,
    )

    result = optimize_candidate(_small_request(), config=config)

    assert result.evaluated_candidates == 2
    assert len(result.stage_best_trials) == 1
    assert result.ldt_text.startswith("SALVI\n")
    assert is_longitudinally_symmetric(result.round_trip_candidate)
    assert result.export_evaluation.metrics.luminance_avg_cd_m2 is not None
