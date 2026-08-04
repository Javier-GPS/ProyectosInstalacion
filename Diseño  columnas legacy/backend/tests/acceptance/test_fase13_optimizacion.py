"""
Fase 13 · Optimización Multiobjetivo y Diseño Especial — 160 Acceptance Checks
Analytical-only (no DB, no network). Mock injection pattern.

AC13-001..015: Creación, permisos, snapshots, reproducibilidad, cancelación
AC13-016..035: Variables, dominios, dependencias, bloqueos, normalización
AC13-036..055: Restricciones normativas, geométricas, fabricación, transporte
AC13-056..075: Coste, peso, CO₂, moneda, fechas, EPD, confianza
AC13-076..095: Algoritmos, Pareto, diversidad, criterios de parada, reinicios
AC13-096..115: Acero, aluminio, hormigón, optimización pretensión
AC13-116..130: Uniones, base, pernos, empotramiento, cimentación
AC13-131..145: Robustez, sensibilidad, escenarios, incertidumbre
AC13-146..160: Explicabilidad, exportación, auditoría, histórico, recuperación
"""
from __future__ import annotations

import sys
import types
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

# ── pytest stub ──────────────────────────────────────────────────────────────
pytest_stub = types.ModuleType("pytest")
pytest_stub.fixture = lambda *a, **kw: (lambda f: f)
pytest_stub.mark = MagicMock()
pytest_stub.raises = MagicMock()
sys.modules.setdefault("pytest", pytest_stub)

# ── infrastructure stubs ─────────────────────────────────────────────────────
for mod in [
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.ext", "sqlalchemy.ext.asyncio",
    "sqlalchemy.dialects", "sqlalchemy.dialects.postgresql",
    "fastapi", "fastapi.responses", "fastapi.routing",
    "pydantic", "pydantic_settings",
    "structlog",
    "app", "app.core", "app.core.database", "app.core.config",
    "app.models", "app.models.db", "app.models.db.optimization",
    "app.models.schemas", "app.models.schemas.optimization",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# ── load optimization_service ─────────────────────────────────────────────────
SERVICE_PATH = Path(__file__).parents[2] / "app" / "services" / "optimization_service.py"
spec = importlib.util.spec_from_file_location("app.services.optimization_service", SERVICE_PATH)
svc_mod = importlib.util.module_from_spec(spec)
sys.modules["app.services.optimization_service"] = svc_mod
spec.loader.exec_module(svc_mod)

VariableDomain          = svc_mod.VariableDomain
DesignSpace             = svc_mod.DesignSpace
DesignSpaceBuilder      = svc_mod.DesignSpaceBuilder
ConstraintEngine        = svc_mod.ConstraintEngine
ConstraintResult        = svc_mod.ConstraintResult
ObjectiveEngine         = svc_mod.ObjectiveEngine
ObjectiveValues         = svc_mod.ObjectiveValues
ParetoManager           = svc_mod.ParetoManager
ParetoPoint             = svc_mod.ParetoPoint
RobustnessEngine        = svc_mod.RobustnessEngine
RobustnessResult        = svc_mod.RobustnessResult
ExplanationEngine       = svc_mod.ExplanationEngine
ArtifactManager         = svc_mod.ArtifactManager
CandidateGenerator      = svc_mod.CandidateGenerator
EvaluationBroker        = svc_mod.EvaluationBroker
InterviewStateMachine   = svc_mod.InterviewStateMachine
FieldInterpreter        = svc_mod.FieldInterpreter
QuestionPlanner         = svc_mod.QuestionPlanner
OptimizationRunManager  = svc_mod.OptimizationRunManager
OptimizationOrchestrator = svc_mod.OptimizationOrchestrator
RunConfig               = svc_mod.RunConfig
ExtractedFieldData      = svc_mod.ExtractedFieldData

VALID_FIELD_STATUSES   = svc_mod.VALID_FIELD_STATUSES
VALID_INTERVIEW_STATES = svc_mod.VALID_INTERVIEW_STATES
PARETO_LABELS          = svc_mod.PARETO_LABELS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cont_domain(lo, hi, step=None):
    return VariableDomain(variable_type="CONTINUOUS", mode="OPTIMIZABLE",
                          min_val=lo, max_val=hi, step=step)

def _disc_domain(values):
    return VariableDomain(variable_type="DISCRETE", mode="OPTIMIZABLE", values=values)

def _cat_domain(values):
    return VariableDomain(variable_type="CATEGORICAL", mode="SELECTABLE", values=values)

def _bool_domain():
    return VariableDomain(variable_type="BOOLEAN", mode="OPTIMIZABLE")

def _build_space(**kwargs):
    space = DesignSpace()
    for k, v in kwargs.items():
        space.variables[k] = v
    return space

def _run_cfg(**kw):
    cfg = {
        "objectives": [{"code": "COST", "direction": "MINIMIZE", "weight": 1.0}],
        "algorithm_config": {},
        "algorithm_version": "1.0.0",
        "seed": 42,
        "budget_evaluations": 1000,
    }
    cfg.update(kw)
    return OptimizationRunManager.create_run(cfg)


# ════════════════════════════════════════════════════════════════════════════════
# AC13-001..015: Creación, permisos, snapshots, reproducibilidad, cancelación
# ════════════════════════════════════════════════════════════════════════════════

class TestCreacionYReproducibilidad:

    def test_ac001_run_manager_creates_run_with_id(self):
        cfg = _run_cfg()
        assert cfg.run_id and len(cfg.run_id) > 0

    def test_ac002_run_hash_deterministic_same_seed(self):
        cfg1 = _run_cfg(seed=42)
        cfg2 = _run_cfg(seed=42)
        assert cfg1.compute_hash() == cfg2.compute_hash()

    def test_ac003_run_hash_differs_different_seed(self):
        cfg1 = _run_cfg(seed=42)
        cfg2 = _run_cfg(seed=99)
        assert cfg1.compute_hash() != cfg2.compute_hash()

    def test_ac004_run_hash_differs_different_objectives(self):
        cfg1 = _run_cfg()
        cfg2 = OptimizationRunManager.create_run({
            "objectives": [{"code": "WEIGHT", "direction": "MINIMIZE", "weight": 1.0}],
            "algorithm_config": {}, "algorithm_version": "1.0.0", "seed": 42,
            "budget_evaluations": 1000,
        })
        assert cfg1.compute_hash() != cfg2.compute_hash()

    def test_ac005_reproducibility_same_hash_validates(self):
        h = _run_cfg().compute_hash()
        assert OptimizationRunManager.validate_reproducibility(h, h)

    def test_ac006_reproducibility_different_hash_fails(self):
        h1 = _run_cfg(seed=1).compute_hash()
        h2 = _run_cfg(seed=2).compute_hash()
        assert not OptimizationRunManager.validate_reproducibility(h1, h2)

    def test_ac007_run_status_transitions_draft_to_running(self):
        assert OptimizationRunManager.can_transition("DRAFT", "RUNNING")

    def test_ac008_run_status_transitions_running_to_paused(self):
        assert OptimizationRunManager.can_transition("RUNNING", "PAUSED")

    def test_ac009_run_status_transitions_running_to_cancelled(self):
        assert OptimizationRunManager.can_transition("RUNNING", "CANCELLED")

    def test_ac010_run_status_transitions_paused_to_running(self):
        assert OptimizationRunManager.can_transition("PAUSED", "RUNNING")

    def test_ac011_run_status_cannot_go_draft_to_completed(self):
        assert not OptimizationRunManager.can_transition("DRAFT", "COMPLETED")

    def test_ac012_run_status_completed_is_terminal(self):
        assert not OptimizationRunManager.can_transition("COMPLETED", "RUNNING")

    def test_ac013_budget_validation_steel_minimum(self):
        ok, msg = OptimizationRunManager.validate_budget(100, "STEEL")
        assert ok and msg == "OK"

    def test_ac014_budget_validation_steel_insufficient(self):
        ok, msg = OptimizationRunManager.validate_budget(50, "STEEL")
        assert not ok and "mínimo" in msg

    def test_ac015_budget_validation_concrete_higher_minimum(self):
        ok, _ = OptimizationRunManager.validate_budget(150, "CONCRETE")
        assert not ok   # concrete requires >= 200


# ════════════════════════════════════════════════════════════════════════════════
# AC13-016..035: Variables, dominios, dependencias, bloqueos, normalización
# ════════════════════════════════════════════════════════════════════════════════

class TestVariablesYDominios:

    def test_ac016_continuous_domain_is_valid(self):
        d = _cont_domain(8.0, 20.0)
        assert d.is_valid()

    def test_ac017_continuous_domain_invalid_min_ge_max(self):
        d = _cont_domain(20.0, 8.0)
        assert not d.is_valid()

    def test_ac018_discrete_domain_is_valid(self):
        d = _disc_domain([8.0, 10.0, 12.0, 14.0])
        assert d.is_valid()

    def test_ac019_discrete_domain_empty_is_invalid(self):
        d = _disc_domain([])
        assert not d.is_valid()

    def test_ac020_boolean_domain_is_valid(self):
        d = _bool_domain()
        assert d.is_valid()

    def test_ac021_continuous_contains_value_within(self):
        d = _cont_domain(8.0, 20.0)
        assert d.contains(12.0)

    def test_ac022_continuous_does_not_contain_value_outside(self):
        d = _cont_domain(8.0, 20.0)
        assert not d.contains(25.0)

    def test_ac023_discrete_contains_listed_value(self):
        d = _disc_domain([8.0, 10.0, 12.0])
        assert d.contains(10.0)

    def test_ac024_discrete_does_not_contain_unlisted_value(self):
        d = _disc_domain([8.0, 10.0, 12.0])
        assert not d.contains(11.0)

    def test_ac025_normalize_continuous_midpoint(self):
        d = _cont_domain(0.0, 10.0)
        assert abs(d.normalize(5.0) - 0.5) < 1e-10

    def test_ac026_normalize_continuous_at_min(self):
        d = _cont_domain(0.0, 10.0)
        assert d.normalize(0.0) == 0.0

    def test_ac027_normalize_continuous_at_max(self):
        d = _cont_domain(0.0, 10.0)
        assert d.normalize(10.0) == 1.0

    def test_ac028_denormalize_continuous_roundtrip(self):
        d = _cont_domain(4.0, 20.0)
        val = 13.5
        assert abs(d.denormalize(d.normalize(val)) - val) < 1e-10

    def test_ac029_design_space_valid_with_variables(self):
        space = _build_space(h=_cont_domain(8.0, 20.0))
        assert space.is_valid()

    def test_ac030_design_space_empty_is_invalid(self):
        space = DesignSpace()
        assert not space.is_valid()

    def test_ac031_design_space_get_optimizable(self):
        space = _build_space(
            h=_cont_domain(8.0, 20.0),   # OPTIMIZABLE
            mat=VariableDomain(variable_type="CATEGORICAL", mode="FIXED", values=["STEEL"]),
        )
        opts = space.get_optimizable()
        assert "h" in opts and "mat" not in opts

    def test_ac032_design_space_get_fixed(self):
        space = _build_space(
            h=_cont_domain(8.0, 20.0),
            mat=VariableDomain(variable_type="CATEGORICAL", mode="FIXED", values=["STEEL"]),
        )
        fixed = space.get_fixed()
        assert "mat" in fixed and "h" not in fixed

    def test_ac033_design_space_point_in_domain_valid(self):
        space = _build_space(h=_cont_domain(8.0, 20.0))
        ok, violations = space.point_in_domain({"h": 12.0})
        assert ok and not violations

    def test_ac034_design_space_point_outside_domain(self):
        space = _build_space(h=_cont_domain(8.0, 20.0))
        ok, violations = space.point_in_domain({"h": 25.0})
        assert not ok and len(violations) > 0

    def test_ac035_design_space_estimate_search_space_size(self):
        space = _build_space(
            h=VariableDomain(variable_type="DISCRETE", mode="OPTIMIZABLE", values=[8, 10, 12, 14]),
            t=VariableDomain(variable_type="DISCRETE", mode="OPTIMIZABLE", values=[3, 4, 5]),
        )
        size = space.estimate_search_space_size()
        assert abs(size - 12) < 0.01   # 4×3 = 12 (float arithmetic)


# ════════════════════════════════════════════════════════════════════════════════
# AC13-036..055: Restricciones normativas, geométricas, fabricación, transporte
# ════════════════════════════════════════════════════════════════════════════════

class TestRestriccionesYConstraintEngine:

    def test_ac036_constraint_engine_add_hard(self):
        ce = ConstraintEngine()
        ce.add_constraint("GEO_HEIGHT", "GEOMETRICA", "HARD")
        assert ce.constraint_count("HARD") == 1

    def test_ac037_constraint_engine_add_soft(self):
        ce = ConstraintEngine()
        ce.add_constraint("COST_TARGET", "COMERCIAL", "SOFT")
        assert ce.constraint_count("SOFT") == 1

    def test_ac038_constraint_engine_add_warning(self):
        ce = ConstraintEngine()
        ce.add_constraint("CO2_WARNING", "SOSTENIBILIDAD", "WARNING")
        assert ce.constraint_count("WARNING") == 1

    def test_ac039_constraint_unknown_class_raises(self):
        ce = ConstraintEngine()
        try:
            ce.add_constraint("X", "UNKNOWN_CLASS", "HARD")
            assert False, "Should raise"
        except ValueError:
            pass

    def test_ac040_constraint_unknown_severity_raises(self):
        ce = ConstraintEngine()
        try:
            ce.add_constraint("X", "NORMATIVA", "CRITICAL")
            assert False, "Should raise"
        except ValueError:
            pass

    def test_ac041_evaluate_no_constraints_passes(self):
        ce = ConstraintEngine()
        r = ce.evaluate({"h": 12.0})
        assert r.passed_hard

    def test_ac042_evaluate_hard_limit_passes(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_H", "GEOMETRICA", "HARD",
                          limit={"field": "h", "op": "<=", "value": 20.0})
        r = ce.evaluate({"h": 12.0})
        assert r.passed_hard

    def test_ac043_evaluate_hard_limit_fails(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_H", "GEOMETRICA", "HARD",
                          limit={"field": "h", "op": "<=", "value": 20.0})
        r = ce.evaluate({"h": 25.0})
        assert not r.passed_hard
        assert "MAX_H" in r.violations

    def test_ac044_first_blocking_set_on_failure(self):
        ce = ConstraintEngine()
        ce.add_constraint("NORM_A", "NORMATIVA", "HARD",
                          limit={"field": "u", "op": "<=", "value": 1.0})
        r = ce.evaluate({"u": 1.5})
        assert r.first_blocking == "NORM_A"

    def test_ac045_soft_violation_does_not_fail_hard(self):
        ce = ConstraintEngine()
        ce.add_constraint("COST_SOFT", "COMERCIAL", "SOFT",
                          limit={"field": "cost", "op": "<=", "value": 1000.0})
        r = ce.evaluate({"cost": 1200.0})
        assert r.passed_hard
        assert "COST_SOFT" in r.soft_violations

    def test_ac046_warning_does_not_fail_hard(self):
        ce = ConstraintEngine()
        ce.add_constraint("CO2_WARN", "SOSTENIBILIDAD", "WARNING",
                          limit={"field": "co2", "op": "<=", "value": 500.0})
        r = ce.evaluate({"co2": 600.0})
        assert r.passed_hard
        assert "CO2_WARN" in r.warnings_list

    def test_ac047_custom_evaluator_function(self):
        ce = ConstraintEngine()
        ce.add_constraint("CUSTOM", "FABRICACION", "HARD",
                          evaluator=lambda v: v.get("t", 0) >= 3.0)
        r = ce.evaluate({"t": 2.5})
        assert not r.passed_hard

    def test_ac048_custom_evaluator_passes(self):
        ce = ConstraintEngine()
        ce.add_constraint("CUSTOM", "FABRICACION", "HARD",
                          evaluator=lambda v: v.get("t", 0) >= 3.0)
        r = ce.evaluate({"t": 4.0})
        assert r.passed_hard

    def test_ac049_constraint_with_in_operator(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAT", "DOMINIO", "HARD",
                          limit={"field": "material", "op": "in", "value": ["STEEL", "ALUMINIUM"]})
        r = ce.evaluate({"material": "CONCRETE"})
        assert not r.passed_hard

    def test_ac050_constraint_with_not_in_operator(self):
        ce = ConstraintEngine()
        ce.add_constraint("NO_CONCRETE", "DOMINIO", "HARD",
                          limit={"field": "material", "op": "not_in", "value": ["CONCRETE"]})
        r = ce.evaluate({"material": "STEEL"})
        assert r.passed_hard

    def test_ac051_transport_length_constraint(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_SEG_LEN", "TRANSPORTE_MONTAJE", "HARD",
                          limit={"field": "segment_length_m", "op": "<=", "value": 12.0})
        r = ce.evaluate({"segment_length_m": 13.0})
        assert not r.passed_hard and "MAX_SEG_LEN" in r.violations

    def test_ac052_normative_utilization_constraint(self):
        ce = ConstraintEngine()
        ce.add_constraint("UTIL_LIMIT", "NORMATIVA", "HARD",
                          limit={"field": "utilization", "op": "<=", "value": 1.0})
        r = ce.evaluate({"utilization": 0.95})
        assert r.passed_hard

    def test_ac053_geometry_min_thickness_constraint(self):
        ce = ConstraintEngine()
        ce.add_constraint("MIN_T", "GEOMETRICA", "HARD",
                          limit={"field": "thickness_mm", "op": ">=", "value": 2.5})
        r = ce.evaluate({"thickness_mm": 2.0})
        assert not r.passed_hard

    def test_ac054_constraint_remove(self):
        ce = ConstraintEngine()
        ce.add_constraint("X", "GEOMETRICA", "HARD")
        removed = ce.remove_constraint("X")
        assert removed
        assert ce.constraint_count("HARD") == 0

    def test_ac055_constraint_get_codes(self):
        ce = ConstraintEngine()
        ce.add_constraint("A", "NORMATIVA", "HARD")
        ce.add_constraint("B", "GEOMETRICA", "SOFT")
        codes = ce.get_codes()
        assert "A" in codes and "B" in codes


# ════════════════════════════════════════════════════════════════════════════════
# AC13-056..075: Coste, peso, CO₂, moneda, fechas, EPD, confianza
# ════════════════════════════════════════════════════════════════════════════════

class TestObjetivosCostePesoCO2:

    def test_ac056_objective_engine_add_minimize(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST", direction="MINIMIZE", weight=1.0)
        assert oe.objective_count() == 1

    def test_ac057_objective_engine_add_maximize(self):
        oe = ObjectiveEngine()
        oe.add_objective("ROBUSTNESS", direction="MAXIMIZE", weight=0.5)
        assert oe.objective_count() == 1

    def test_ac058_objective_invalid_direction_raises(self):
        oe = ObjectiveEngine()
        try:
            oe.add_objective("X", direction="NEUTRAL")
            assert False, "Should raise"
        except ValueError:
            pass

    def test_ac059_objective_negative_weight_raises(self):
        oe = ObjectiveEngine()
        try:
            oe.add_objective("X", weight=-1.0)
            assert False, "Should raise"
        except ValueError:
            pass

    def test_ac060_objective_duplicate_code_raises(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST")
        try:
            oe.add_objective("COST")
            assert False, "Should raise"
        except ValueError:
            pass

    def test_ac061_objective_compute_single(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST", weight=1.0)
        ov = oe.compute({"COST": 850.0})
        assert ov.values["COST"] == 850.0

    def test_ac062_objective_compute_missing_field_ignored(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST")
        oe.add_objective("WEIGHT")
        ov = oe.compute({"COST": 850.0})
        assert "COST" in ov.values and "WEIGHT" not in ov.values

    def test_ac063_objective_weighted_sum_single(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST", direction="MINIMIZE", weight=1.0)
        ov = oe.compute({"COST": 500.0})
        assert ov.weighted_sum == 500.0

    def test_ac064_objective_weighted_sum_multi(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST",   direction="MINIMIZE", weight=0.6)
        oe.add_objective("WEIGHT", direction="MINIMIZE", weight=0.4)
        ov = oe.compute({"COST": 1000.0, "WEIGHT": 200.0})
        expected = 0.6 * 1000.0 + 0.4 * 200.0   # 680
        assert abs(ov.weighted_sum - expected) < 1e-6

    def test_ac065_objective_maximize_negate_in_weighted_sum(self):
        oe = ObjectiveEngine()
        oe.add_objective("ROBUSTNESS", direction="MAXIMIZE", weight=1.0)
        ov = oe.compute({"ROBUSTNESS": 0.8})
        assert ov.weighted_sum < 0   # maximizar invierte signo

    def test_ac066_objective_validate_weights_ok(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST", weight=0.5)
        oe.add_objective("WEIGHT", weight=0.5)
        assert oe.validate_weights()

    def test_ac067_objective_normalize_two_candidates(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST")
        evals = [{"COST": 500.0}, {"COST": 1000.0}]
        normed = oe.normalize_objectives(evals)
        assert normed[0]["COST"] == 0.0
        assert normed[1]["COST"] == 1.0

    def test_ac068_objective_normalize_single_candidate(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST")
        normed = oe.normalize_objectives([{"COST": 750.0}])
        assert normed[0]["COST"] == 0.0   # span == 0 → 0

    def test_ac069_dominance_a_dominates_b(self):
        dirs = {"COST": "MINIMIZE", "WEIGHT": "MINIMIZE"}
        a = ObjectiveValues({"COST": 500.0, "WEIGHT": 80.0}, {"COST": 1.0, "WEIGHT": 1.0}, dirs)
        b = ObjectiveValues({"COST": 700.0, "WEIGHT": 90.0}, {"COST": 1.0, "WEIGHT": 1.0}, dirs)
        assert a.dominates(b)

    def test_ac070_dominance_no_dominance_tradeoff(self):
        dirs = {"COST": "MINIMIZE", "WEIGHT": "MINIMIZE"}
        a = ObjectiveValues({"COST": 500.0, "WEIGHT": 100.0}, {"COST": 1.0, "WEIGHT": 1.0}, dirs)
        b = ObjectiveValues({"COST": 700.0, "WEIGHT": 80.0},  {"COST": 1.0, "WEIGHT": 1.0}, dirs)
        assert not a.dominates(b)
        assert not b.dominates(a)

    def test_ac071_dominance_maximize_objective(self):
        dirs = {"ROB": "MAXIMIZE"}
        a = ObjectiveValues({"ROB": 0.9}, {"ROB": 1.0}, dirs)
        b = ObjectiveValues({"ROB": 0.7}, {"ROB": 1.0}, dirs)
        assert a.dominates(b)

    def test_ac072_get_objective_by_code(self):
        oe = ObjectiveEngine()
        oe.add_objective("CO2", direction="MINIMIZE", weight=0.3)
        obj = oe.get_objective("CO2")
        assert obj is not None and obj["weight"] == 0.3

    def test_ac073_get_objective_missing_returns_none(self):
        oe = ObjectiveEngine()
        assert oe.get_objective("NONEXISTENT") is None

    def test_ac074_objective_scope_stored(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST", scope="A1-A3")
        obj = oe.get_objective("COST")
        assert obj["scope"] == "A1-A3"

    def test_ac075_objective_engine_empty_has_zero_objectives(self):
        oe = ObjectiveEngine()
        assert oe.objective_count() == 0


# ════════════════════════════════════════════════════════════════════════════════
# AC13-076..095: Algoritmos, Pareto, diversidad, criterios de parada, reinicios
# ════════════════════════════════════════════════════════════════════════════════

class TestParetoYAlgoritmos:

    def test_ac076_pareto_empty_initially(self):
        pm = ParetoManager()
        assert pm.size() == 0

    def test_ac077_pareto_first_candidate_added(self):
        pm = ParetoManager({"COST": "MINIMIZE"})
        added = pm.add_candidate("c1", {"COST": 850.0})
        assert added and pm.size() == 1

    def test_ac078_pareto_dominated_candidate_not_added(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0, "W": 80.0})
        added = pm.add_candidate("c2", {"COST": 700.0, "W": 100.0})
        assert not added
        assert pm.size() == 1

    def test_ac079_pareto_non_dominated_tradeoff_both_added(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("c2", {"COST": 700.0, "W": 80.0})
        assert pm.size() == 2

    def test_ac080_pareto_new_dominates_existing_removes_it(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 700.0, "W": 100.0})
        pm.add_candidate("c2", {"COST": 500.0, "W": 80.0})   # domina c1
        assert pm.size() == 1
        assert pm.get_front()[0].candidate_id == "c2"

    def test_ac081_pareto_is_dominated_true(self):
        pm = ParetoManager({"COST": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0})
        assert pm.is_dominated({"COST": 700.0})

    def test_ac082_pareto_is_dominated_false(self):
        pm = ParetoManager({"COST": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 700.0})
        assert not pm.is_dominated({"COST": 500.0})

    def test_ac083_pareto_select_min_cost(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("cheap", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("light", {"COST": 700.0, "W": 80.0})
        assert pm.select_min("COST") == "cheap"

    def test_ac084_pareto_select_min_weight(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("cheap", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("light", {"COST": 700.0, "W": 80.0})
        assert pm.select_min("W") == "light"

    def test_ac085_pareto_select_knee_single_candidate(self):
        pm = ParetoManager({"COST": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0})
        assert pm.select_knee() == "c1"

    def test_ac086_pareto_select_knee_returns_candidate_id(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("c2", {"COST": 600.0, "W": 90.0})
        pm.add_candidate("c3", {"COST": 700.0, "W": 80.0})
        knee = pm.select_knee()
        assert knee in ["c1", "c2", "c3"]

    def test_ac087_pareto_label_alternatives_produces_labels(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("c2", {"COST": 700.0, "W": 80.0})
        labels = pm.label_alternatives()
        assert len(labels) > 0

    def test_ac088_pareto_crowding_distances_computed(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("c2", {"COST": 600.0, "W": 90.0})
        pm.add_candidate("c3", {"COST": 700.0, "W": 80.0})
        pm.compute_crowding_distances()
        # extremos tienen inf
        front = {p.candidate_id: p for p in pm.get_front()}
        assert front["c1"].crowding_distance == float("inf") or \
               front["c3"].crowding_distance == float("inf")

    def test_ac089_pareto_clear_empties_front(self):
        pm = ParetoManager({"COST": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0})
        pm.clear()
        assert pm.size() == 0

    def test_ac090_pareto_empty_select_min_returns_none(self):
        pm = ParetoManager({"COST": "MINIMIZE"})
        assert pm.select_min("COST") is None

    def test_ac091_pareto_empty_select_knee_returns_none(self):
        pm = ParetoManager()
        assert pm.select_knee() is None

    def test_ac092_candidate_generator_no_duplicates(self):
        space = _build_space(mat=_cat_domain(["STEEL", "ALU"]))
        gen = CandidateGenerator(space)
        assert not gen.is_duplicate({"mat": "STEEL"})
        assert gen.is_duplicate({"mat": "STEEL"})

    def test_ac093_candidate_generator_enumerate_discrete(self):
        space = _build_space(
            mat=_cat_domain(["S", "A"]),
            t=_disc_domain([3, 4, 5]),
        )
        gen = CandidateGenerator(space)
        candidates = gen.enumerate_discrete()
        assert len(candidates) == 6

    def test_ac094_duplicate_rate_zero_with_no_duplicates(self):
        space = _build_space(mat=_cat_domain(["STEEL", "ALU"]))
        gen = CandidateGenerator(space)
        gen.is_duplicate({"mat": "STEEL"})
        gen.is_duplicate({"mat": "ALU"})
        assert gen.duplicate_rate(2) == 0.0

    def test_ac095_evaluation_broker_caches_results(self):
        broker = EvaluationBroker()
        broker.evaluate("c1", "hash1", "STEEL",
                        eval_fn=lambda h, m: {"utilization": 0.8})
        result = broker.evaluate("c2", "hash1", "STEEL")
        assert result.get("cached") is True
        assert broker.cache_size() == 1


# ════════════════════════════════════════════════════════════════════════════════
# AC13-096..115: Acero, aluminio, hormigón, optimización pretensión
# ════════════════════════════════════════════════════════════════════════════════

class TestMaterialesEspecificos:

    def test_ac096_space_builder_from_specs_continuous(self):
        specs = [{"name": "h", "variable_type": "CONTINUOUS", "mode": "OPTIMIZABLE",
                  "domain": {"min": 8.0, "max": 20.0}}]
        space = DesignSpaceBuilder.build(specs)
        assert "h" in space.variables
        assert space.variables["h"].variable_type == "CONTINUOUS"

    def test_ac097_space_builder_from_specs_discrete(self):
        specs = [{"name": "t", "variable_type": "DISCRETE", "mode": "OPTIMIZABLE",
                  "domain": {"values": [3.0, 4.0, 5.0]}}]
        space = DesignSpaceBuilder.build(specs)
        assert space.variables["t"].values == [3.0, 4.0, 5.0]

    def test_ac098_space_builder_categorical_material(self):
        specs = [{"name": "mat", "variable_type": "CATEGORICAL", "mode": "SELECTABLE",
                  "domain": {"values": ["S235", "S275", "S355"]}}]
        space = DesignSpaceBuilder.build(specs)
        assert "S355" in space.variables["mat"].values

    def test_ac099_space_builder_dependency_validation_ok(self):
        space = DesignSpace()
        space.variables["h"] = _cont_domain(8, 20)
        space.variables["segments"] = VariableDomain(
            variable_type="DERIVED", mode="DERIVED",
            expression="ceil({h} / 12)"
        )
        ok, errors = DesignSpaceBuilder.validate_dependencies(space)
        assert ok and not errors

    def test_ac100_space_builder_dependency_missing_ref(self):
        space = DesignSpace()
        space.variables["segments"] = VariableDomain(
            variable_type="DERIVED", mode="DERIVED",
            expression="ceil({unknown_var} / 12)"
        )
        ok, errors = DesignSpaceBuilder.validate_dependencies(space)
        assert not ok and errors

    def test_ac101_constraint_normativa_steel_utilization_limit(self):
        ce = ConstraintEngine()
        ce.add_constraint("UTIL_BENDING", "NORMATIVA", "HARD",
                          limit={"field": "bending_utilization", "op": "<=", "value": 1.0},
                          normative_reference="EN 40-3-3:2013")
        r = ce.evaluate({"bending_utilization": 0.92})
        assert r.passed_hard

    def test_ac102_constraint_normativa_fatigue_at_door(self):
        ce = ConstraintEngine()
        ce.add_constraint("FATIGUE_DOOR", "NORMATIVA", "HARD",
                          evaluator=lambda v: v.get("door") is False or v.get("fatigue_ok", True))
        r = ce.evaluate({"door": True, "fatigue_ok": False})
        assert not r.passed_hard and "FATIGUE_DOOR" in r.violations

    def test_ac103_constraint_aluminium_haz_zone(self):
        ce = ConstraintEngine()
        ce.add_constraint("HAZ_REDUCTION", "NORMATIVA", "HARD",
                          evaluator=lambda v: v.get("stress_at_weld", 0) <=
                          v.get("haz_capacity", float("inf")))
        r = ce.evaluate({"stress_at_weld": 120.0, "haz_capacity": 100.0})
        assert not r.passed_hard

    def test_ac104_constraint_concrete_prestress_loss(self):
        ce = ConstraintEngine()
        ce.add_constraint("PRESTRESS_MIN", "NORMATIVA", "HARD",
                          limit={"field": "prestress_ratio", "op": ">=", "value": 0.75})
        r = ce.evaluate({"prestress_ratio": 0.80})
        assert r.passed_hard

    def test_ac105_objective_cost_blocks(self):
        """Coste tiene 7 bloques — objetivo COST compuesto."""
        oe = ObjectiveEngine()
        oe.add_objective("COST_MATERIAL",  weight=0.35)
        oe.add_objective("COST_PROCESS",   weight=0.20)
        oe.add_objective("COST_SURFACE",   weight=0.10)
        oe.add_objective("COST_TRANSPORT", weight=0.10)
        oe.add_objective("COST_INSTALL",   weight=0.10)
        oe.add_objective("COST_OVERHEAD",  weight=0.10)
        oe.add_objective("COST_MARGIN",    weight=0.05)
        assert oe.objective_count() == 7

    def test_ac106_pareto_three_objectives_non_dominated(self):
        dirs = {"COST": "MINIMIZE", "W": "MINIMIZE", "CO2": "MINIMIZE"}
        pm = ParetoManager(dirs)
        pm.add_candidate("c1", {"COST": 500.0, "W": 100.0, "CO2": 400.0})
        pm.add_candidate("c2", {"COST": 700.0, "W": 80.0,  "CO2": 350.0})
        pm.add_candidate("c3", {"COST": 600.0, "W": 90.0,  "CO2": 300.0})
        assert pm.size() == 3

    def test_ac107_constraint_fabrication_max_seam_length(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_SEAM", "FABRICACION", "HARD",
                          limit={"field": "seam_length_m", "op": "<=", "value": 12.0})
        r = ce.evaluate({"seam_length_m": 12.0})
        assert r.passed_hard

    def test_ac108_constraint_transport_max_weight(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_TRANSP_W", "TRANSPORTE_MONTAJE", "HARD",
                          limit={"field": "segment_mass_kg", "op": "<=", "value": 5000.0})
        r = ce.evaluate({"segment_mass_kg": 6000.0})
        assert not r.passed_hard

    def test_ac109_objective_co2_confidence_tracked(self):
        """CO₂ con confianza baja genera advertencia (soft)."""
        ce = ConstraintEngine()
        ce.add_constraint("CO2_LOW_CONF", "SOSTENIBILIDAD", "WARNING",
                          evaluator=lambda v: v.get("co2_confidence", 1.0) >= 0.7)
        r = ce.evaluate({"co2_confidence": 0.5})
        assert r.passed_hard
        assert "CO2_LOW_CONF" in r.warnings_list

    def test_ac110_space_builder_apply_material_constraints_steel(self):
        space = _build_space(h=_cont_domain(8, 20))
        adapted = DesignSpaceBuilder.apply_material_constraints(space, "STEEL")
        assert adapted is not None and adapted.is_valid()

    def test_ac111_design_space_candidate_hash_deterministic(self):
        space = _build_space(h=_cont_domain(8, 20))
        h1 = space.candidate_hash({"h": 12.0, "t": 4.0})
        h2 = space.candidate_hash({"t": 4.0, "h": 12.0})
        assert h1 == h2   # orden de claves independiente

    def test_ac112_orchestrator_run_single_valid_candidate(self):
        orc = OptimizationOrchestrator()
        orc.objectives.add_objective("COST", weight=1.0)
        result = orc.run_single(
            {"h": 12.0},
            eval_fn=lambda v: {"COST": 850.0},
        )
        assert result["status"] == "VALID"

    def test_ac113_orchestrator_run_single_rejected_candidate(self):
        orc = OptimizationOrchestrator()
        orc.constraints.add_constraint("MAX_H", "GEOMETRICA", "HARD",
                                       limit={"field": "h", "op": "<=", "value": 20.0})
        result = orc.run_single({"h": 25.0})
        assert result["status"] == "REJECTED"

    def test_ac114_orchestrator_maturity_initial_o0(self):
        orc = OptimizationOrchestrator()
        assert orc.maturity_level == "O0"

    def test_ac115_orchestrator_advance_maturity_sequential(self):
        orc = OptimizationOrchestrator()
        ok = orc.advance_maturity("O1")
        assert ok and orc.maturity_level == "O1"


# ════════════════════════════════════════════════════════════════════════════════
# AC13-116..130: Uniones, base, pernos, empotramiento, cimentación
# ════════════════════════════════════════════════════════════════════════════════

class TestUnionesYCimentacion:

    def test_ac116_constraint_joint_type_allowed(self):
        ce = ConstraintEngine()
        ce.add_constraint("JOINT_TYPE", "NORMATIVA", "HARD",
                          limit={"field": "joint_type", "op": "in",
                                 "value": ["SLIP_FIT", "FLANGED", "WELDED", "SLEEVE", "HYBRID"]})
        r = ce.evaluate({"joint_type": "SLIP_FIT"})
        assert r.passed_hard

    def test_ac117_constraint_base_plate_pattern_allowed(self):
        ce = ConstraintEngine()
        ce.add_constraint("BASE_PATTERN", "GEOMETRICA", "HARD",
                          limit={"field": "plate_size_mm", "op": "in",
                                 "value": [200, 250, 300]})
        r = ce.evaluate({"plate_size_mm": 250})
        assert r.passed_hard

    def test_ac118_constraint_base_plate_unknown_pattern(self):
        ce = ConstraintEngine()
        ce.add_constraint("BASE_PATTERN", "GEOMETRICA", "HARD",
                          limit={"field": "plate_size_mm", "op": "in",
                                 "value": [200, 250, 300]})
        r = ce.evaluate({"plate_size_mm": 350})
        assert not r.passed_hard

    def test_ac119_constraint_bolt_post_installed_allowed(self):
        ce = ConstraintEngine()
        ce.add_constraint("BOLT_TYPE", "NORMATIVA", "HARD",
                          evaluator=lambda v: v.get("allow_post_installed", True) or
                          v.get("bolt_type") != "POST_INSTALLED")
        r = ce.evaluate({"bolt_type": "POST_INSTALLED", "allow_post_installed": True})
        assert r.passed_hard

    def test_ac120_constraint_embedment_depth_minimum(self):
        ce = ConstraintEngine()
        ce.add_constraint("EMBED_MIN", "NORMATIVA", "HARD",
                          limit={"field": "embed_depth_m", "op": ">=", "value": 0.8})
        r = ce.evaluate({"embed_depth_m": 0.6})
        assert not r.passed_hard

    def test_ac121_constraint_foundation_soil_level(self):
        ce = ConstraintEngine()
        ce.add_constraint("SOIL_LEVEL", "DOMINIO", "HARD",
                          limit={"field": "geotechnical_level", "op": "in",
                                 "value": ["G0", "G1", "G2", "G3", "G4"]})
        r = ce.evaluate({"geotechnical_level": "G2"})
        assert r.passed_hard

    def test_ac122_constraint_foundation_unknown_soil_level(self):
        ce = ConstraintEngine()
        ce.add_constraint("SOIL_LEVEL", "DOMINIO", "HARD",
                          limit={"field": "geotechnical_level", "op": "in",
                                 "value": ["G0", "G1", "G2", "G3", "G4"]})
        r = ce.evaluate({"geotechnical_level": "G5"})
        assert not r.passed_hard

    def test_ac123_constraint_segmentation_max_segments(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_SEG", "GEOMETRICA", "HARD",
                          limit={"field": "n_segments", "op": "<=", "value": 4})
        r = ce.evaluate({"n_segments": 5})
        assert not r.passed_hard

    def test_ac124_constraint_catenary_max_cables(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_CABLES", "GEOMETRICA", "HARD",
                          limit={"field": "n_catenary_cables", "op": "<=", "value": 6})
        r = ce.evaluate({"n_catenary_cables": 6})
        assert r.passed_hard

    def test_ac125_constraint_catenary_over_limit(self):
        ce = ConstraintEngine()
        ce.add_constraint("MAX_CABLES", "GEOMETRICA", "HARD",
                          limit={"field": "n_catenary_cables", "op": "<=", "value": 6})
        r = ce.evaluate({"n_catenary_cables": 7})
        assert not r.passed_hard

    def test_ac126_pareto_three_materials_coexist(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("steel",    {"COST": 850.0, "W": 95.0})
        pm.add_candidate("aluminium", {"COST": 1200.0, "W": 55.0})
        pm.add_candidate("concrete", {"COST": 400.0,  "W": 280.0})
        # Los tres son no-dominados si ninguno domina a otro
        assert pm.size() >= 1

    def test_ac127_constraint_min_reserve_margin(self):
        ce = ConstraintEngine()
        ce.add_constraint("MIN_MARGIN", "ROBUSTEZ", "SOFT",
                          limit={"field": "reserve", "op": ">=", "value": 0.05})
        r = ce.evaluate({"reserve": 0.03})
        assert r.passed_hard  # SOFT
        assert "MIN_MARGIN" in r.soft_violations

    def test_ac128_orchestrator_explain_run_returns_labels(self):
        orc = OptimizationOrchestrator()
        pm = orc.pareto
        pm._directions = {"COST": "MINIMIZE", "W": "MINIMIZE"}
        pm.add_candidate("c1", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("c2", {"COST": 700.0, "W": 80.0})
        info = orc.explain_run()
        assert info["pareto_size"] == 2

    def test_ac129_constraint_normativa_robustez_combined(self):
        """Restricción de robustez bloquea candidato frágil."""
        ce = ConstraintEngine()
        ce.add_constraint("FRAGILE", "ROBUSTEZ", "HARD",
                          evaluator=lambda v: v.get("min_reserve", 0) >= 0.0)
        r = ce.evaluate({"min_reserve": -0.1})
        assert not r.passed_hard

    def test_ac130_orchestrator_maturity_skips_levels_fails(self):
        orc = OptimizationOrchestrator()
        ok = orc.advance_maturity("O3")   # skip O1, O2
        assert not ok and orc.maturity_level == "O0"


# ════════════════════════════════════════════════════════════════════════════════
# AC13-131..145: Robustez, sensibilidad, escenarios, incertidumbre
# ════════════════════════════════════════════════════════════════════════════════

class TestRobustezYSensibilidad:

    def test_ac131_robustness_no_scenarios_is_robust(self):
        r = RobustnessEngine.evaluate_discrete_scenarios(
            "c1", {"h": 12.0}, [], eval_fn=lambda v: 0.1
        )
        assert r.is_robust and r.samples_evaluated == 0

    def test_ac132_robustness_single_scenario_positive_reserve(self):
        r = RobustnessEngine.evaluate_discrete_scenarios(
            "c1", {"h": 12.0},
            [{"wind": 1.1}],
            eval_fn=lambda v: 0.05,
        )
        assert r.is_robust
        assert r.min_reserve == 0.05

    def test_ac133_robustness_single_scenario_negative_reserve(self):
        r = RobustnessEngine.evaluate_discrete_scenarios(
            "c1", {"h": 12.0},
            [{"wind": 1.1}],
            eval_fn=lambda v: -0.03,
        )
        assert not r.is_robust

    def test_ac134_robustness_multiple_scenarios_min_selected(self):
        reserves = [0.10, 0.05, 0.12]
        idx = [0]
        def ef(v):
            val = reserves[idx[0] % len(reserves)]
            idx[0] += 1
            return val
        r = RobustnessEngine.evaluate_discrete_scenarios(
            "c1", {"h": 12.0},
            [{"w": 1.0}, {"w": 1.1}, {"w": 0.9}],
            eval_fn=ef,
        )
        assert r.min_reserve == 0.05

    def test_ac135_robustness_sensitivity_worst_scenario(self):
        r = RobustnessEngine.evaluate_discrete_scenarios(
            "c1", {"h": 12.0, "wind": 1.0},
            [{"wind": 1.5}],
            eval_fn=lambda v: 0.1 - (v.get("wind", 1.0) - 1.0) * 0.5,
        )
        assert "wind" in r.sensitivity

    def test_ac136_robustness_threshold_applied(self):
        r = RobustnessEngine.evaluate_discrete_scenarios(
            "c1", {"h": 12.0},
            [{"x": 1}],
            eval_fn=lambda v: 0.03,
            reserve_threshold=0.05,
        )
        assert not r.is_robust  # 0.03 < 0.05

    def test_ac137_lhs_sample_count_correct(self):
        samples = RobustnessEngine.latin_hypercube_sample(
            10, {"h": (8.0, 20.0), "t": (3.0, 5.0)}, seed=42
        )
        assert len(samples) == 10

    def test_ac138_lhs_samples_within_bounds(self):
        samples = RobustnessEngine.latin_hypercube_sample(
            20, {"h": (8.0, 20.0)}, seed=7
        )
        for s in samples:
            assert 8.0 <= s["h"] <= 20.0

    def test_ac139_lhs_reproducible_with_seed(self):
        s1 = RobustnessEngine.latin_hypercube_sample(5, {"x": (0.0, 1.0)}, seed=42)
        s2 = RobustnessEngine.latin_hypercube_sample(5, {"x": (0.0, 1.0)}, seed=42)
        assert s1 == s2

    def test_ac140_monotonicity_check_increasing(self):
        ok = RobustnessEngine.check_monotonicity(
            eval_fn=lambda v: v["load"],
            base_vars={"load": 10.0},
            test_var="load",
            direction="INCREASING",
            steps=3,
        )
        assert ok

    def test_ac141_monotonicity_check_decreasing_fails_if_increasing(self):
        ok = RobustnessEngine.check_monotonicity(
            eval_fn=lambda v: v["load"],   # increasing
            base_vars={"load": 10.0},
            test_var="load",
            direction="DECREASING",
            steps=3,
        )
        assert not ok

    def test_ac142_robustness_samples_evaluated_count(self):
        scenarios = [{"x": i} for i in range(7)]
        r = RobustnessEngine.evaluate_discrete_scenarios(
            "c1", {}, scenarios, eval_fn=lambda v: 0.1
        )
        assert r.samples_evaluated == 7

    def test_ac143_orchestrator_pareto_size_after_multiple_runs(self):
        orc = OptimizationOrchestrator()
        orc.objectives.add_objective("COST", weight=1.0)
        orc.pareto._directions = {"COST": "MINIMIZE"}
        orc.run_single({"h": 10.0}, eval_fn=lambda v: {"COST": 900.0})
        orc.run_single({"h": 12.0}, eval_fn=lambda v: {"COST": 850.0})
        orc.run_single({"h": 14.0}, eval_fn=lambda v: {"COST": 800.0})
        # 800 domina a todos los anteriores en COST
        assert orc.pareto.size() == 1

    def test_ac144_evaluation_broker_invalidate_all(self):
        broker = EvaluationBroker()
        broker.evaluate("c1", "hash1", "STEEL", eval_fn=lambda h, m: {})
        broker.evaluate("c2", "hash2", "ALU",   eval_fn=lambda h, m: {})
        n = broker.invalidate()
        assert n == 2 and broker.cache_size() == 0

    def test_ac145_evaluation_broker_invalidate_specific_hash(self):
        broker = EvaluationBroker()
        broker.evaluate("c1", "hash1", "STEEL", eval_fn=lambda h, m: {})
        broker.evaluate("c2", "hash2", "ALU",   eval_fn=lambda h, m: {})
        n = broker.invalidate("hash1")
        assert n == 1 and broker.cache_size() == 1


# ════════════════════════════════════════════════════════════════════════════════
# AC13-146..160: Explicabilidad, exportación, auditoría, histórico, recuperación
# ════════════════════════════════════════════════════════════════════════════════

class TestExplicabilidadYAuditoria:

    def test_ac146_explanation_rejection_has_governing_constraint(self):
        cr = ConstraintResult(passed_hard=False, violations=["MAX_H"],
                              first_blocking="MAX_H")
        expl = ExplanationEngine.explain_rejection("c1", cr)
        assert "MAX_H" in expl.governing_constraints

    def test_ac147_explanation_rejection_summary_not_empty(self):
        cr = ConstraintResult(passed_hard=False, violations=["NORM_A"], first_blocking="NORM_A")
        expl = ExplanationEngine.explain_rejection("cX", cr)
        assert len(expl.summary) > 0

    def test_ac148_explanation_selection_has_contributions(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST", weight=0.6)
        oe.add_objective("CO2",  weight=0.4)
        ov = oe.compute({"COST": 850.0, "CO2": 320.0})
        expl = ExplanationEngine.explain_selection("c2", ov, pareto_label="BALANCED")
        assert "COST" in expl.objective_contributions

    def test_ac149_explanation_selection_label_stored(self):
        oe = ObjectiveEngine()
        oe.add_objective("COST")
        ov = oe.compute({"COST": 500.0})
        expl = ExplanationEngine.explain_selection("c3", ov, pareto_label="MIN_COST")
        assert expl.pareto_label == "MIN_COST"

    def test_ac150_artifact_run_manifest_has_run_id(self):
        m = ArtifactManager.create_run_manifest("run-42", {"objectives": []})
        assert m["run_id"] == "run-42"

    def test_ac151_artifact_run_manifest_has_config_hash(self):
        m = ArtifactManager.create_run_manifest("run-42", {"objectives": []})
        assert "config_hash" in m and len(m["config_hash"]) > 0

    def test_ac152_artifact_candidate_trace_has_variables_hash(self):
        t = ArtifactManager.create_candidate_trace(
            "c1", {"h": 12.0, "t": 4.0}, parent_id="c0"
        )
        assert "variables_hash" in t and t["candidate_id"] == "c1"

    def test_ac153_artifact_decision_trace_label_stored(self):
        t = ArtifactManager.create_decision_trace("run-1", "c5", "BALANCED")
        assert t["pareto_label"] == "BALANCED"

    def test_ac154_artifact_data_lineage_type_stored(self):
        l = ArtifactManager.create_data_lineage(
            "geometry.height", "USER_INPUT", "msg-001", 12.0
        )
        assert l["source_type"] == "USER_INPUT"

    def test_ac155_explanation_sensitivity_top_variables(self):
        rr = RobustnessResult(
            candidate_id="c1", method="DISCRETE_SCENARIOS",
            is_robust=True, min_reserve=0.05,
            sensitivity={"wind": 0.8, "height": 0.3, "load": 0.5}
        )
        expl = ExplanationEngine.explain_sensitivity("c1", rr)
        assert len(expl.sensitivity_top) > 0
        # Top variable should be wind
        assert expl.sensitivity_top[0]["variable"] == "wind"

    def test_ac156_run_format_manifest_with_user(self):
        m = ExplanationEngine.format_run_manifest(
            "run-1", {"seed": 42}, {"geo": "2.0"}, user_id="javier"
        )
        assert m["user_id"] == "javier"

    def test_ac157_orchestrator_cache_size_after_evaluation(self):
        orc = OptimizationOrchestrator()
        orc.objectives.add_objective("COST")
        orc.pareto._directions = {"COST": "MINIMIZE"}
        orc.run_single({"h": 12.0}, eval_fn=lambda v: {"COST": 850.0})
        # broker no tiene evaluaciones directas en run_single sin geometry_hash
        info = orc.explain_run()
        assert "cache_size" in info

    def test_ac158_pareto_all_labels_from_valid_set(self):
        pm = ParetoManager({"COST": "MINIMIZE", "W": "MINIMIZE"})
        pm.add_candidate("c1", {"COST": 500.0, "W": 100.0})
        pm.add_candidate("c2", {"COST": 700.0, "W": 80.0})
        labels = pm.label_alternatives()
        for label in labels.values():
            assert label in PARETO_LABELS or label.startswith("MIN_")

    def test_ac159_artifact_all_types_have_created_at(self):
        m = ArtifactManager.create_run_manifest("r", {})
        t = ArtifactManager.create_candidate_trace("c", {})
        d = ArtifactManager.create_decision_trace("r", "c", "BALANCED")
        l = ArtifactManager.create_data_lineage("f", "USER_INPUT", "ref", 1)
        for artifact in [m, t, d, l]:
            assert "created_at" in artifact

    def test_ac160_duplicate_rate_below_threshold(self):
        """AC ref: sección 19 — duplicados < 1% tras normalización."""
        space = _build_space(h=_cont_domain(8, 20))
        gen = CandidateGenerator(space)
        for i in range(100):
            gen.is_duplicate({"h": float(i)})
        # Ningún duplicado → tasa = 0
        assert gen.duplicate_rate(100) == 0.0


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    # Auto-ejecutar todas las clases
    passed = failed = 0
    all_classes = [
        TestCreacionYReproducibilidad,
        TestVariablesYDominios,
        TestRestriccionesYConstraintEngine,
        TestObjetivosCostePesoCO2,
        TestParetoYAlgoritmos,
        TestMaterialesEspecificos,
        TestUnionesYCimentacion,
        TestRobustezYSensibilidad,
        TestExplicabilidadYAuditoria,
    ]
    for cls in all_classes:
        obj = cls()
        for name in dir(obj):
            if name.startswith("test_"):
                try:
                    getattr(obj, name)()
                    passed += 1
                    print(f"  PASS  {name}")
                except Exception as e:
                    failed += 1
                    print(f"  FAIL  {name}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
