from __future__ import annotations

from app.services.optimizer.advanced import advanced_score as _advanced_score
from app.services.optimizer.power import power_can_fix_failures as _power_can_fix_failures
from app.services.optimizer.power import with_power as _with_power
from app.services.optimizer.advanced import unique_candidates as _unique_candidates
from app.schemas.models import CalculationConfig, CalculationResult, CriterionResult, FotometriaInfo


def _config(**overrides) -> CalculationConfig:
    base = dict(
        road_width=7.0,
        sidewalk_left=1.5,
        sidewalk_right=1.5,
        lanes=2,
        arrangement="Lineal",
        height=9.0,
        spacing=30.0,
        arm_length=2.0,
        pole_offset=0.0,
        pole_side="left",
        tilt=3.0,
        optic_family="F151",
        power=75.0,
        ldt_id="catalog-ldt",
        manufacturer="Salvi",
        model_family="Test",
        lighting_class="M3",
        mf=0.85,
        pavement="R3",
        cct=4000,
        cri=70,
        language="es",
    )
    base.update(overrides)
    return CalculationConfig(**base)


def _luminaire(power: float) -> FotometriaInfo:
    return FotometriaInfo(
        id="catalog-ldt",
        filename="test.ldt",
        luminaire_name="Test",
        manufacturer="Salvi",
        model_family="Test",
        optic_family="F151",
        cct=4000,
        cri=70,
        power=power,
        flux=power * 120.0,
        efficiency=120.0,
        LORL=1.0,
        isym=0,
    )


def _result(config: CalculationConfig, lavg: float) -> CalculationResult:
    return CalculationResult(
        config=config,
        compliant=True,
        mode="luminance",
        luminaire=_luminaire(config.power),
        criteria=[
            CriterionResult(name="Lavg", value=lavg, required=1.0, passed=True),
            CriterionResult(name="Uo", value=0.42, required=0.4, passed=True),
            CriterionResult(name="Ul", value=0.72, required=0.7, passed=True),
            CriterionResult(name="TI", value=9.5, required=10.0, passed=True),
            CriterionResult(name="SR", value=0.51, required=0.5, passed=True),
        ],
        Lavg=lavg,
        Uo=0.42,
        Ul=0.72,
        TI=9.5,
        SR=0.51,
    )


def test_technical_limits_prefers_lower_power_before_tighter_margin():
    original = _config()
    lower_power = _result(_config(power=75.0, arm_length=2.0, tilt=3.0), lavg=1.25)
    higher_power_tighter_margin = _result(_config(power=100.0, arm_length=3.0, tilt=15.0), lavg=1.02)

    assert _advanced_score(lower_power, original, "technical_limits") < _advanced_score(
        higher_power_tighter_margin,
        original,
        "technical_limits",
    )


def test_max_spacing_keeps_spacing_as_primary_objective():
    original = _config()
    closer_lower_power = _result(_config(power=75.0, spacing=30.0), lavg=1.05)
    wider_spacing = _result(_config(power=100.0, spacing=45.0), lavg=1.25)

    assert _advanced_score(wider_spacing, original, "max_spacing") < _advanced_score(
        closer_lower_power,
        original,
        "max_spacing",
    )


def test_power_only_search_only_treats_light_level_failures_as_power_fixable():
    low_lavg = _result(_config(power=75.0), lavg=0.95)
    low_lavg.criteria[0].passed = False

    bad_uniformity = _result(_config(power=75.0), lavg=1.20)
    bad_uniformity.criteria[1].value = 0.35
    bad_uniformity.criteria[1].passed = False
    bad_uniformity.compliant = False

    assert _power_can_fix_failures(low_lavg)
    assert not _power_can_fix_failures(bad_uniformity)


def test_unique_candidates_lower_bound_keeps_only_values_at_or_above_bound():
    candidates = [60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5]

    result = _unique_candidates(candidates, current=30, bound="lower", bound_value=35)

    assert result == [35, 40, 45, 50, 55, 60]


def test_unique_candidates_upper_bound_keeps_only_values_at_or_below_bound():
    candidates = [60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5]

    result = _unique_candidates(candidates, current=30, bound="upper", bound_value=40)

    assert result == [40, 35, 30, 25, 20, 15, 10, 5]


def test_unique_candidates_no_bound_returns_descending_unique_set():
    candidates = [60, 55, 50, 50, 45, 40]

    result = _unique_candidates(candidates, current=30)

    assert result == [60, 55, 50, 45, 40, 30]


def test_power_search_clears_target_flux():
    config = _config(power=80.0, target_flux=12000.0)

    result = _with_power(config, 1.0, "catalog-ldt")

    assert result.power == 1.0
    assert result.target_flux is None
