"""Progressive deterministic optimizer for symmetric photometric families."""
from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .candidate_generator import (
    DEFAULT_RESOLUTION_STAGES,
    AngularResolutionStage,
    PhotometricFamilyParameters,
    generate_symmetric_candidate,
)
from .domain import OptimizationRequest, PhotometricCandidate
from .eulumdat import candidate_from_ldt_text, candidate_to_ldt
from .evaluator import CandidateEvaluation, EvaluationOptions, evaluate_candidate
from .objective import ObjectiveScore, ObjectiveWeights, score_candidate


@dataclass(frozen=True)
class PhotometricSearchSpace:
    """Bounds of the first manufacturable analytical LDT family."""

    peak_c_deg: tuple[float, float] = (5.0, 60.0)
    peak_gamma_deg: tuple[float, float] = (45.0, 78.0)
    c_spread_deg: tuple[float, float] = (6.0, 32.0)
    gamma_spread_deg: tuple[float, float] = (6.0, 24.0)
    gamma_outer_spread_deg: tuple[float, float] = (7.0, 16.0)
    crest_weight: tuple[float, float] = (0.15, 0.70)
    crest_spread_deg: tuple[float, float] = (4.0, 8.0)
    nadir_weight: tuple[float, float] = (0.05, 0.80)
    nadir_power: tuple[float, float] = (0.5, 6.0)
    cross_weight: tuple[float, float] = (0.0, 0.80)
    cross_gamma_deg: tuple[float, float] = (35.0, 65.0)
    cross_c_spread_deg: tuple[float, float] = (15.0, 60.0)
    cross_gamma_spread_deg: tuple[float, float] = (8.0, 30.0)
    cutoff_start_deg: tuple[float, float] = (70.0, 85.0)
    cutoff_end_deg: tuple[float, float] = (86.0, 90.0)

    def __post_init__(self) -> None:
        for name in _SEARCH_FIELDS:
            lower, upper = getattr(self, name)
            if upper <= lower:
                raise ValueError(f"límites no válidos para {name}")


@dataclass(frozen=True)
class OptimizationConfig:
    """Resolution schedule and search effort."""

    stages: tuple[AngularResolutionStage, ...] = DEFAULT_RESOLUTION_STAGES[:3]
    samples_per_stage: tuple[int, ...] = (40, 20, 10)
    mutation_scales: tuple[float, ...] = (1.0, 0.20, 0.08)
    elite_count: int = 5
    random_seed: int = 13201
    export_resolution: AngularResolutionStage = DEFAULT_RESOLUTION_STAGES[-1]

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("se requiere al menos una etapa de optimización")
        if len(self.samples_per_stage) != len(self.stages):
            raise ValueError("samples_per_stage no coincide con las etapas")
        if len(self.mutation_scales) != len(self.stages):
            raise ValueError("mutation_scales no coincide con las etapas")
        if any(count < 1 for count in self.samples_per_stage):
            raise ValueError("cada etapa requiere al menos una muestra")
        if any(scale <= 0 for scale in self.mutation_scales):
            raise ValueError("las escalas de mutación deben ser positivas")
        if self.elite_count < 1:
            raise ValueError("elite_count debe ser mayor que cero")


@dataclass(frozen=True)
class OptimizationTrial:
    stage: AngularResolutionStage
    parameters: PhotometricFamilyParameters
    candidate: PhotometricCandidate
    evaluation: CandidateEvaluation
    score: ObjectiveScore


@dataclass(frozen=True)
class OptimizationResult:
    best_trial: OptimizationTrial
    stage_best_trials: tuple[OptimizationTrial, ...]
    evaluated_candidates: int
    export_candidate: PhotometricCandidate
    export_evaluation: CandidateEvaluation
    export_score: ObjectiveScore
    ldt_text: str
    round_trip_candidate: PhotometricCandidate


_SEARCH_FIELDS = (
    "peak_c_deg",
    "peak_gamma_deg",
    "c_spread_deg",
    "gamma_spread_deg",
    "gamma_outer_spread_deg",
    "crest_weight",
    "crest_spread_deg",
    "nadir_weight",
    "nadir_power",
    "cross_weight",
    "cross_gamma_deg",
    "cross_c_spread_deg",
    "cross_gamma_spread_deg",
    "cutoff_start_deg",
    "cutoff_end_deg",
)


def _clamp_parameters(
    parameters: PhotometricFamilyParameters,
    search_space: PhotometricSearchSpace,
) -> PhotometricFamilyParameters:
    updates = {}
    for name in _SEARCH_FIELDS:
        lower, upper = getattr(search_space, name)
        updates[name] = min(max(getattr(parameters, name), lower), upper)
    return replace(parameters, **updates)


def _random_parameters(
    base: PhotometricFamilyParameters,
    search_space: PhotometricSearchSpace,
    generator: random.Random,
) -> PhotometricFamilyParameters:
    return replace(
        base,
        **{
            name: generator.uniform(*getattr(search_space, name))
            for name in _SEARCH_FIELDS
        },
    )


def _reference_seed_parameters(
    base: PhotometricFamilyParameters,
    search_space: PhotometricSearchSpace,
) -> tuple[PhotometricFamilyParameters, ...]:
    """Return manufacturable road-optic starting points for the first stage."""

    presets = (
        dict(
            peak_c_deg=15.0,
            peak_gamma_deg=65.0,
            c_spread_deg=12.0,
            gamma_spread_deg=12.0,
            gamma_outer_spread_deg=7.0,
            crest_weight=0.38,
            crest_spread_deg=4.5,
            nadir_weight=0.34,
            nadir_power=2.5,
            cross_weight=0.22,
            cross_gamma_deg=46.0,
            cross_c_spread_deg=34.0,
            cross_gamma_spread_deg=17.0,
            cutoff_start_deg=78.0,
            cutoff_end_deg=89.0,
        ),
        dict(
            peak_c_deg=30.0,
            peak_gamma_deg=60.0,
            c_spread_deg=18.0,
            gamma_spread_deg=14.0,
            gamma_outer_spread_deg=8.5,
            crest_weight=0.34,
            crest_spread_deg=5.0,
            nadir_weight=0.36,
            nadir_power=2.2,
            cross_weight=0.32,
            cross_gamma_deg=48.0,
            cross_c_spread_deg=40.0,
            cross_gamma_spread_deg=19.0,
            cutoff_start_deg=78.0,
            cutoff_end_deg=89.0,
        ),
        dict(
            peak_c_deg=10.0,
            peak_gamma_deg=72.0,
            c_spread_deg=10.0,
            gamma_spread_deg=10.0,
            gamma_outer_spread_deg=6.0,
            crest_weight=0.42,
            crest_spread_deg=4.0,
            nadir_weight=0.28,
            nadir_power=3.0,
            cross_weight=0.18,
            cross_gamma_deg=52.0,
            cross_c_spread_deg=30.0,
            cross_gamma_spread_deg=16.0,
            cutoff_start_deg=80.0,
            cutoff_end_deg=89.5,
        ),
        dict(
            peak_c_deg=38.0,
            peak_gamma_deg=58.0,
            c_spread_deg=22.0,
            gamma_spread_deg=17.0,
            gamma_outer_spread_deg=10.0,
            crest_weight=0.26,
            crest_spread_deg=6.0,
            nadir_weight=0.42,
            nadir_power=1.8,
            cross_weight=0.42,
            cross_gamma_deg=44.0,
            cross_c_spread_deg=48.0,
            cross_gamma_spread_deg=22.0,
            cutoff_start_deg=76.0,
            cutoff_end_deg=88.0,
        ),
    )
    return tuple(
        _clamp_parameters(replace(base, **preset), search_space)
        for preset in presets
    )


def _mutated_parameters(
    parent: PhotometricFamilyParameters,
    search_space: PhotometricSearchSpace,
    generator: random.Random,
    scale: float,
) -> PhotometricFamilyParameters:
    updates = {}
    for name in _SEARCH_FIELDS:
        lower, upper = getattr(search_space, name)
        value = generator.gauss(
            getattr(parent, name),
            (upper - lower) * scale,
        )
        updates[name] = min(max(value, lower), upper)
    return replace(parent, **updates)


def _evaluate_trial(
    request: OptimizationRequest,
    parameters: PhotometricFamilyParameters,
    stage: AngularResolutionStage,
    options: EvaluationOptions,
    weights: ObjectiveWeights,
) -> OptimizationTrial:
    candidate = generate_symmetric_candidate(parameters, resolution=stage)
    evaluation = evaluate_candidate(request, candidate, options=options)
    objective = score_candidate(
        request,
        candidate,
        evaluation,
        weights=weights,
    )
    return OptimizationTrial(
        stage=stage,
        parameters=parameters,
        candidate=candidate,
        evaluation=evaluation,
        score=objective,
    )


def optimize_candidate(
    request: OptimizationRequest,
    *,
    options: EvaluationOptions | None = None,
    config: OptimizationConfig | None = None,
    search_space: PhotometricSearchSpace | None = None,
    weights: ObjectiveWeights | None = None,
    initial_parameters: PhotometricFamilyParameters | None = None,
) -> OptimizationResult:
    """Search coarse-to-fine and verify the exported LDT by reimporting it."""

    selected_options = options or EvaluationOptions(calculation_backend="numpy")
    selected_config = config or OptimizationConfig()
    selected_space = search_space or PhotometricSearchSpace()
    selected_weights = weights or ObjectiveWeights()
    base = initial_parameters or PhotometricFamilyParameters(
        flux_lm=request.arrangement.placements[0].flux_lm,
        luminaire_name=request.candidate_name,
    )
    base = _clamp_parameters(base, selected_space)
    generator = random.Random(selected_config.random_seed)

    elites: tuple[OptimizationTrial, ...] = ()
    stage_bests: list[OptimizationTrial] = []
    evaluated_count = 0
    for stage_index, stage in enumerate(selected_config.stages):
        requested_samples = selected_config.samples_per_stage[stage_index]
        remaining_budget = request.max_candidates - evaluated_count
        sample_count = min(requested_samples, remaining_budget)
        if sample_count <= 0:
            break

        parameters_to_test: list[PhotometricFamilyParameters] = []
        if not elites:
            parameters_to_test.append(base)
            parameters_to_test.extend(
                _reference_seed_parameters(base, selected_space)
            )
            parameters_to_test = parameters_to_test[:sample_count]
            while len(parameters_to_test) < sample_count:
                parameters_to_test.append(
                    _random_parameters(base, selected_space, generator)
                )
        else:
            parameters_to_test.extend(
                item.parameters for item in elites[:sample_count]
            )
            mutation_scale = selected_config.mutation_scales[stage_index]
            parent_index = 0
            while len(parameters_to_test) < sample_count:
                parent = elites[parent_index % len(elites)].parameters
                parameters_to_test.append(
                    _mutated_parameters(
                        parent,
                        selected_space,
                        generator,
                        mutation_scale,
                    )
                )
                parent_index += 1

        trials = tuple(
            _evaluate_trial(
                request,
                parameters,
                stage,
                selected_options,
                selected_weights,
            )
            for parameters in parameters_to_test
        )
        evaluated_count += len(trials)
        ordered = tuple(sorted(trials, key=lambda item: item.score.ranking_key))
        elites = ordered[: min(selected_config.elite_count, len(ordered))]
        stage_bests.append(ordered[0])

    if not stage_bests:
        raise ValueError("el presupuesto no permite evaluar candidatos")
    best_trial = stage_bests[-1]

    export_candidate = generate_symmetric_candidate(
        best_trial.parameters,
        resolution=selected_config.export_resolution,
    )
    ldt_text = candidate_to_ldt(
        export_candidate,
        filename=f"{request.candidate_name}.ldt",
    )
    round_trip_candidate = candidate_from_ldt_text(ldt_text)
    export_evaluation = evaluate_candidate(
        request,
        round_trip_candidate,
        options=selected_options,
    )
    export_score = score_candidate(
        request,
        round_trip_candidate,
        export_evaluation,
        weights=selected_weights,
    )
    return OptimizationResult(
        best_trial=best_trial,
        stage_best_trials=tuple(stage_bests),
        evaluated_candidates=evaluated_count,
        export_candidate=export_candidate,
        export_evaluation=export_evaluation,
        export_score=export_score,
        ldt_text=ldt_text,
        round_trip_candidate=round_trip_candidate,
    )
