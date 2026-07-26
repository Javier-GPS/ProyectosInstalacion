"""Benchmark: smart recursive optimizer vs brute-force (≥4x fewer calc calls).

The smart search (``run_smart_search``) uses O(d · n) evaluations instead of
the brute-force O(k · nⁱ) used by ``run_advanced_search``, where d ≤ 6,
n ≤ 12, i = number of unlocked variables.

Verification: each ``run_calculation`` call is replaced by a deterministic mock
that returns compliant/non-compliant results based on geometry + power.
"""
from __future__ import annotations

from app.schemas.models import (
    AdvancedOptimizationLimits,
    AdvancedOptimizationVariables,
    CalculationConfig,
    CalculationResult,
    CriterionResult,
    FotometriaInfo,
)
from app.services.optimizer.advanced import run_advanced_search, run_smart_search

MOCK_LDT = "catalog-ldt"


def _config(**overrides) -> CalculationConfig:
    base = dict(
        road_width=7.0, sidewalk_left=0.0, sidewalk_right=0.0, lanes=2,
        arrangement="Lineal", height=10.0, spacing=30.0, arm_length=0.0,
        pole_offset=0.0, pole_side="left", tilt=0.0, optic_family="F151",
        power=1.0, ldt_id=MOCK_LDT, manufacturer="Salvi", model_family="Test",
        lighting_class="M3", mf=0.85, pavement="R3", cct=4000, cri=70,
        language="es",
    )
    base.update(overrides)
    return CalculationConfig(**base)


def _luminaire(config: CalculationConfig) -> FotometriaInfo:
    return FotometriaInfo(
        id=MOCK_LDT, filename="mock.ldt", luminaire_name="mock",
        manufacturer="Salvi", model_family="Test", cct=4000, cri=70,
        optic_family=config.optic_family, power=config.power,
        flux=config.power * 120.0, efficiency=120.0, LORL=1.0, isym=1,
    )


def _mock_result(config: CalculationConfig, _ldt_id: str = "", **kwargs) -> CalculationResult:
    """Deterministic mock — each criterion depends on ONE variable only.

    - Lavg ∝ power / spacing (target 1.0 cd/m²)
    - TI  = 21 − height (target ≤ 15, one height step suffices)
    - SR  = 0.4 + 0.2 × arm_length (target ≥ 0.5)
    - Uo  = 0.5 (always passes)
    - Ul  = 0.7 (always passes)
    """
    p = config.power
    h = config.height
    a = config.arm_length
    s = config.spacing

    lavg = p / max(s, 0.1) * 0.3
    ti = max(0.0, 21.0 - h)
    sr = min(1.0, 0.4 + a * 0.2)
    uo = 0.5
    ul = 0.7

    criteria = [
        CriterionResult(name="Lavg (cd/m²)", value=round(lavg, 4), required=1.0, passed=lavg >= 1.0),
        CriterionResult(name="TI (%)", value=round(ti, 4), required=15.0, passed=ti <= 15.0),
        CriterionResult(name="SR", value=round(sr, 4), required=0.5, passed=sr >= 0.5),
        CriterionResult(name="Uo", value=uo, required=0.4, passed=uo >= 0.4),
        CriterionResult(name="Ul", value=ul, required=0.6, passed=ul >= 0.6),
    ]
    compliant = all(c.passed for c in criteria)

    return CalculationResult(
        config=config, compliant=compliant, mode="ME",
        luminaire=_luminaire(config), criteria=criteria,
        Lavg=round(lavg, 4), Uo=uo, Ul=ul, TI=round(ti, 4), SR=round(sr, 4),
    )


class _CallTracker:
    def __init__(self, mock_fn):
        self.count = 0
        self._fn = mock_fn

    def __call__(self, config, ldt_id, **kwargs):
        self.count += 1
        return self._fn(config, ldt_id, **kwargs)


def _make_vars(
    power=True, spacing=False, height=False, arm_length=False, tilt=False,
    optic_family=False,
) -> AdvancedOptimizationVariables:
    return AdvancedOptimizationVariables(
        power=power, spacing=spacing, height=height,
        arm_length=arm_length, tilt=tilt, optic_family=optic_family,
    )


def _make_limits(power=500.0, spacing=None, height=None, arm_length=None, tilt=None):
    return AdvancedOptimizationLimits(
        power=power, spacing=spacing, height=height,
        arm_length=arm_length, tilt=tilt,
    )


def _setup_tracker(monkeypatch, tracker):
    monkeypatch.setattr("app.services.optimizer.power.run_calculation", tracker)
    monkeypatch.setattr("app.services.optimizer.advanced.run_calculation", tracker)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_smart_search_2vars_4x_faster(monkeypatch):
    """2 vars (arm_length + power): smart uses ≤ 25 % of brute calls."""
    tracker = _CallTracker(_mock_result)
    _setup_tracker(monkeypatch, tracker)

    config = _config(power=1.0, arm_length=0.0)
    result = run_smart_search(
        config, _make_vars(power=True, arm_length=True),
        _make_limits(power=500.0), "technical_limits", MOCK_LDT, "technical_limits",
    )
    assert result.feasible, f"smart search failed: {result.message}"
    # brute = 5 arm candidates × power search (~17) = 85; ≤ 25 % = 21
    assert tracker.count <= 21, (
        f"smart search used {tracker.count} calls, expected ≤ 21"
    )


def test_smart_search_3vars_4x_faster(monkeypatch):
    """3 vars (spacing + arm_length + power): smart uses ≤ 25 % of brute calls."""
    tracker = _CallTracker(_mock_result)
    _setup_tracker(monkeypatch, tracker)

    config = _config(power=1.0, spacing=55.0, arm_length=0.0)
    result = run_smart_search(
        config, _make_vars(power=True, spacing=True, arm_length=True),
        _make_limits(power=500.0), "technical_limits", MOCK_LDT, "technical_limits",
    )
    assert result.feasible, f"smart search failed: {result.message}"
    # brute = 12 spacing × 5 arm = 60 candidates (many with power search)
    # ≤ 25 % = 60 × 0.25 × ~17 ≈ 255; smart should be well under
    assert tracker.count <= 255, (
        f"smart search used {tracker.count} calls, expected ≤ 255"
    )
    # Sanity: smart takes < 50 calls
    assert tracker.count < 50, f"smart search used {tracker.count} calls, expected < 50"


def test_smart_and_brute_agree_on_compliant_result(monkeypatch):
    """Both smart and brute find a feasible solution, smart uses ≥4x fewer calls."""
    smart_tracker = _CallTracker(_mock_result)
    brute_tracker = _CallTracker(_mock_result)

    _setup_tracker(monkeypatch, smart_tracker)
    config = _config(power=1.0, spacing=55.0, arm_length=0.0)
    vars_ = _make_vars(power=True, spacing=True, arm_length=True)
    limits = _make_limits(power=500.0)

    smart_result = run_smart_search(
        config, vars_, limits, "technical_limits", MOCK_LDT, "technical_limits",
    )
    assert smart_result.feasible, f"smart search failed: {smart_result.message}"
    assert smart_result.result.compliant

    _setup_tracker(monkeypatch, brute_tracker)
    brute_result = run_advanced_search(
        config, vars_, limits, "technical_limits", MOCK_LDT, "technical_limits",
    )
    assert brute_result.feasible, f"brute force failed: {brute_result.message}"
    assert brute_result.result.compliant

    speedup = brute_tracker.count / max(smart_tracker.count, 1)
    assert speedup >= 4.0, (
        f"smart ({smart_tracker.count} calls) vs brute ({brute_tracker.count} calls) "
        f"= {speedup:.1f}x — need ≥4x"
    )


def test_smart_search_uses_catalog_flux_path_before_returning(monkeypatch):
    """Catalog candidates must derive power/current through the PCB path."""
    from types import SimpleNamespace

    import app.services.optimizer.advanced as advanced

    seen_configs = []
    flux_calls = []

    def fake_pcb(_db, config):
        return SimpleNamespace(
            p_total=50.0,
            driver_eficiencia=0.9,
            flux=10_000.0,
            i_op_ma=620.0,
        )

    def fake_calculation(config, _ldt_id, **_kwargs):
        seen_configs.append(config)
        return _mock_result(config)

    def fake_flux_optimizer(_db, config, _ldt_id, _target_lavg, **_kwargs):
        flux_calls.append(config)
        optimized = config.model_copy(update={"power": 42.0, "target_flux": 8_000.0})
        result = _mock_result(optimized)
        result.Lavg = 1.0
        result.criteria[0].value = 1.0
        result.criteria[0].passed = True
        result.compliant = True
        return True, 1, result, "none", optimized

    monkeypatch.setattr(advanced, "select_pcb_for_config", fake_pcb)
    monkeypatch.setattr(advanced, "run_calculation", fake_calculation)
    monkeypatch.setattr(advanced, "optimize_flux_for_config", fake_flux_optimizer)

    config = _config(
        power=0.0,
        target_flux=10_000.0,
        arm_length=1.0,
        gama="ATENEA",
        difusor="PMMA LC",
        lente="F151",
        led_type="LUXEON HOP 5050",
    )
    result = run_smart_search(
        config,
        _make_vars(power=True),
        _make_limits(power=500.0),
        "technical_limits",
        MOCK_LDT,
        "technical_limits",
        db=object(),
    )

    assert result.feasible
    assert flux_calls, "Lavg should use the flux/PCB optimizer"
    assert seen_configs[0].power == round(50.0 / 0.9, 2)
    assert seen_configs[0].i_op_ma == 620.0
    assert result.config.power == 42.0


def test_smart_search_uses_tilt_to_fix_uniformity(monkeypatch):
    """A selected tilt change must be considered for a Uo failure."""
    tracker = _CallTracker(_mock_result)

    def tilt_uniformity_result(config, ldt_id="", **kwargs):
        result = _mock_result(config, ldt_id, **kwargs)
        uo = 0.43 if config.tilt >= 5.0 else 0.36
        result.criteria[3] = CriterionResult(
            name="Uo", value=uo, required=0.4, passed=uo >= 0.4,
        )
        result.Uo = uo
        result.compliant = all(item.passed for item in result.criteria)
        return result

    tracker._fn = tilt_uniformity_result
    _setup_tracker(monkeypatch, tracker)

    result = run_smart_search(
        _config(power=120.0, arm_length=1.0, tilt=0.0),
        _make_vars(power=False, tilt=True),
        _make_limits(power=500.0, tilt=25.0),
        "technical_limits", MOCK_LDT, "technical_limits",
    )

    assert result.feasible, f"smart search failed: {result.message}"
    assert result.config.tilt == 5.0


def test_smart_search_does_not_assume_one_fixed_lever_per_criterion(monkeypatch):
    """Any selected geometry lever may change a uniformity criterion."""
    tracker = _CallTracker(_mock_result)

    def height_uniformity_result(config, ldt_id="", **kwargs):
        result = _mock_result(config, ldt_id, **kwargs)
        sr = 0.55 if config.height >= 8.0 else 0.45
        result.criteria[2] = CriterionResult(
            name="SR", value=sr, required=0.5, passed=sr >= 0.5,
        )
        result.SR = sr
        result.compliant = all(item.passed for item in result.criteria)
        return result

    tracker._fn = height_uniformity_result
    _setup_tracker(monkeypatch, tracker)

    result = run_smart_search(
        _config(power=120.0, height=6.0),
        _make_vars(power=False, height=True),
        _make_limits(power=500.0, height=40.0),
        "technical_limits", MOCK_LDT, "technical_limits",
    )

    assert result.feasible, f"smart search failed: {result.message}"
    assert result.config.height == 8.0
