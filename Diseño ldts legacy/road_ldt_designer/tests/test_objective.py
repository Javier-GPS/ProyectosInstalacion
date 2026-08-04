import pytest

from road_ldt_designer.road_ldt.candidate_generator import (
    DEFAULT_RESOLUTION_STAGES,
    PhotometricFamilyParameters,
    generate_symmetric_candidate,
)
from road_ldt_designer.road_ldt.compliance import ComplianceResult
from road_ldt_designer.road_ldt.domain import (
    CalculationMetrics,
    LuminaireArrangement,
    LuminairePlacement,
    OptimizationRequest,
    QualityTargets,
    RoadGeometry,
)
from road_ldt_designer.road_ldt.evaluator import (
    CandidateEvaluation,
    EvaluationOptions,
)
from road_ldt_designer.road_ldt.objective import score_candidate


def _request():
    return OptimizationRequest(
        geometry=RoadGeometry(
            carriageway_width_m=7.0,
            lane_widths_m=(3.5, 3.5),
        ),
        arrangement=LuminaireArrangement(
            placements=(LuminairePlacement(0.0, -1.0, 8.0, 10000.0),),
            nominal_spacing_m=20.0,
        ),
        targets=QualityTargets(
            luminance_avg_min_cd_m2=1.0,
            uo_min=0.4,
            ul_min=0.6,
            ti_max_pct=15.0,
            rei_min=0.3,
        ),
    )


def _evaluation(metrics):
    return CandidateEvaluation(
        metrics=metrics,
        compliance=ComplianceResult(True, {}),
        options=EvaluationOptions(),
        calculation_grid=None,
        evaluated_luminaires=(),
        luminance=None,
        threshold_increment=None,
        edge_illuminance=None,
    )


def test_objective_is_feasible_when_all_hard_constraints_are_met():
    candidate = generate_symmetric_candidate(
        PhotometricFamilyParameters(),
        resolution=DEFAULT_RESOLUTION_STAGES[0],
    )
    evaluation = _evaluation(
        CalculationMetrics(
            luminance_avg_cd_m2=1.0,
            uo=0.4,
            ul=0.6,
            ti_pct=15.0,
            rei=0.3,
        )
    )

    score = score_candidate(_request(), candidate, evaluation)

    assert score.feasible
    assert score.maximum_violation == 0.0
    assert score.constraint_penalty == 0.0


def test_objective_uses_normalized_squared_constraint_violations():
    candidate = generate_symmetric_candidate(
        PhotometricFamilyParameters(),
        resolution=DEFAULT_RESOLUTION_STAGES[0],
    )
    evaluation = _evaluation(
        CalculationMetrics(
            luminance_avg_cd_m2=1.0,
            uo=0.2,
            ul=0.6,
            ti_pct=30.0,
            rei=0.3,
        )
    )

    score = score_candidate(_request(), candidate, evaluation)

    assert not score.feasible
    assert score.maximum_violation == pytest.approx(1.0)
    assert score.constraint_penalty == pytest.approx(0.5**2 + 1.0**2)
    assert {item.name for item in score.constraints} == {
        "Lavg",
        "Uo",
        "Ul",
        "TI",
        "REI",
    }
