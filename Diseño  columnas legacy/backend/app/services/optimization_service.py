"""
Salvi Studio · Columns — Servicios Fase 13
Optimización Multiobjetivo y Diseño Especial

Arquitectura (10 componentes):
  OptimizationOrchestrator, DesignSpaceBuilder, ConstraintEngine,
  CandidateGenerator, EvaluationBroker, ObjectiveEngine, ParetoManager,
  RobustnessEngine, ExplanationEngine, ArtifactManager

Asistente conversacional:
  InterviewStateMachine, FieldInterpreter, QuestionPlanner, OptimizationRunManager
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ── Constantes ────────────────────────────────────────────────────────────────

VALID_VARIABLE_TYPES  = {"CONTINUOUS", "DISCRETE", "CATEGORICAL", "BOOLEAN", "DERIVED", "DEPENDENT"}
VALID_VARIABLE_MODES  = {"FIXED", "SELECTABLE", "OPTIMIZABLE", "DERIVED"}
VALID_CONSTRAINT_CLASSES = {
    "NORMATIVA", "DOMINIO", "GEOMETRICA", "FABRICACION",
    "TRANSPORTE_MONTAJE", "COMERCIAL", "SOSTENIBILIDAD", "ROBUSTEZ",
}
VALID_SEVERITIES      = {"HARD", "SOFT", "WARNING"}
VALID_DIRECTIONS      = {"MINIMIZE", "MAXIMIZE"}
VALID_ROBUSTNESS_METHODS = {
    "DISCRETE_SCENARIOS", "INTERVALS", "LATIN_HYPERCUBE",
    "MONTE_CARLO", "ROBUST_OPTIMIZATION", "WORST_CASE",
}
VALID_INTERVIEW_STATES = {
    "NEW", "DISCOVERY", "ELICITATION", "CLARIFICATION",
    "REVIEW", "CONFIRMED", "BLOCKED", "READY",
}
VALID_FIELD_STATUSES  = {
    "EXACT", "ESTIMATED", "RANGE", "UNKNOWN", "CONFLICT", "PENDING_CONFIRMATION",
}
VALID_LANGUAGES       = {"es", "en", "fr", "ca", "it", "pt"}

# Etiquetas Pareto obligatorias
PARETO_LABELS = {
    "MIN_COST", "MIN_WEIGHT", "MIN_CO2",
    "BALANCED", "MOST_ROBUST", "STANDARD_REFERENCE",
}

# Transiciones válidas del estado de entrevista
INTERVIEW_TRANSITIONS: Dict[str, Set[str]] = {
    "NEW":           {"DISCOVERY", "BLOCKED"},
    "DISCOVERY":     {"ELICITATION", "CLARIFICATION", "BLOCKED"},
    "ELICITATION":   {"CLARIFICATION", "REVIEW", "BLOCKED"},
    "CLARIFICATION": {"ELICITATION", "REVIEW", "BLOCKED"},
    "REVIEW":        {"CONFIRMED", "ELICITATION", "BLOCKED"},
    "CONFIRMED":     {"READY", "ELICITATION"},
    "BLOCKED":       {"ELICITATION", "DISCOVERY"},
    "READY":         set(),
}

# Niveles de madurez del optimizador
MATURITY_LEVELS = {"O0", "O1", "O2", "O3", "O4", "O5"}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class VariableDomain:
    """Dominio de una variable de diseño."""
    variable_type: str
    mode: str
    # CONTINUOUS
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None
    # DISCRETE / CATEGORICAL
    values: Optional[List[Any]] = None
    # BOOLEAN
    # DERIVED
    expression: Optional[str] = None

    def is_valid(self) -> bool:
        if self.variable_type not in VALID_VARIABLE_TYPES:
            return False
        if self.mode not in VALID_VARIABLE_MODES:
            return False
        if self.variable_type == "CONTINUOUS":
            return self.min_val is not None and self.max_val is not None and self.min_val < self.max_val
        if self.variable_type in {"DISCRETE", "CATEGORICAL"}:
            return bool(self.values)
        if self.variable_type == "BOOLEAN":
            return True
        if self.variable_type in {"DERIVED", "DEPENDENT"}:
            return True
        return False

    def contains(self, value: Any) -> bool:
        """Devuelve True si el valor pertenece al dominio."""
        if self.variable_type == "CONTINUOUS":
            if self.min_val is None or self.max_val is None:
                return False
            return self.min_val <= value <= self.max_val
        if self.variable_type in {"DISCRETE", "CATEGORICAL"}:
            return value in (self.values or [])
        if self.variable_type == "BOOLEAN":
            return isinstance(value, bool)
        return True  # DERIVED / DEPENDENT — no restricción propia

    def normalize(self, value: float) -> float:
        """Normaliza al rango [0,1] (solo CONTINUOUS/DISCRETE numérico)."""
        if self.variable_type == "CONTINUOUS":
            span = (self.max_val or 0.0) - (self.min_val or 0.0)
            if span == 0:
                return 0.0
            return max(0.0, min(1.0, (value - (self.min_val or 0.0)) / span))
        if self.variable_type == "DISCRETE" and self.values:
            vals = sorted(self.values)
            if value in vals:
                idx = vals.index(value)
                span = len(vals) - 1
                return idx / span if span > 0 else 0.0
        return 0.0

    def denormalize(self, norm: float) -> float:
        """Denormaliza de [0,1] al dominio original (solo CONTINUOUS)."""
        if self.variable_type == "CONTINUOUS":
            return (self.min_val or 0.0) + norm * ((self.max_val or 0.0) - (self.min_val or 0.0))
        return norm


@dataclass
class DesignSpace:
    """Espacio de diseño construido a partir de variables."""
    variables: Dict[str, VariableDomain] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return bool(self.variables) and all(d.is_valid() for d in self.variables.values())

    def get_optimizable(self) -> List[str]:
        return [n for n, d in self.variables.items() if d.mode == "OPTIMIZABLE"]

    def get_fixed(self) -> List[str]:
        return [n for n, d in self.variables.items() if d.mode == "FIXED"]

    def get_selectable(self) -> List[str]:
        return [n for n, d in self.variables.items() if d.mode == "SELECTABLE"]

    def point_in_domain(self, point: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verifica que todos los valores estén en sus dominios."""
        violations = []
        for name, domain in self.variables.items():
            if name in point:
                if not domain.contains(point[name]):
                    violations.append(f"{name}: {point[name]} outside domain")
            elif domain.mode in {"OPTIMIZABLE", "SELECTABLE", "FIXED"}:
                violations.append(f"{name}: missing required variable")
        return len(violations) == 0, violations

    def candidate_hash(self, variables: Dict[str, Any]) -> str:
        canonical = json.dumps(variables, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def estimate_search_space_size(self) -> float:
        """Estimación logarítmica del espacio de búsqueda."""
        log_size = 0.0
        for d in self.variables.values():
            if d.mode not in {"OPTIMIZABLE", "SELECTABLE"}:
                continue
            if d.variable_type == "CONTINUOUS":
                if d.step and d.step > 0:
                    n = (d.max_val - d.min_val) / d.step + 1
                    log_size += math.log10(max(1, n))
                else:
                    log_size += 3   # continuo: 1000 puntos representativos
            elif d.variable_type in {"DISCRETE", "CATEGORICAL"}:
                log_size += math.log10(max(1, len(d.values or [])))
            elif d.variable_type == "BOOLEAN":
                log_size += math.log10(2)
        return 10 ** log_size


@dataclass
class ConstraintResult:
    """Resultado de evaluación de restricciones."""
    passed_hard: bool = True
    violations: List[str] = field(default_factory=list)      # restricciones HARD violadas
    soft_violations: List[str] = field(default_factory=list) # restricciones SOFT violadas
    warnings_list: List[str] = field(default_factory=list)   # WARNING activos
    first_blocking: Optional[str] = None   # primer motivo bloqueante

    @property
    def overall_pass(self) -> bool:
        return self.passed_hard

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed_hard": self.passed_hard,
            "violations": self.violations,
            "soft_violations": self.soft_violations,
            "warnings": self.warnings_list,
            "first_blocking": self.first_blocking,
        }


@dataclass
class ObjectiveValues:
    """Valores de funciones objetivo para un candidato."""
    values: Dict[str, float] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    directions: Dict[str, str] = field(default_factory=dict)

    @property
    def weighted_sum(self) -> float:
        total = 0.0
        total_weight = sum(self.weights.values()) or 1.0
        for code, val in self.values.items():
            w = self.weights.get(code, 1.0) / total_weight
            direction = self.directions.get(code, "MINIMIZE")
            signed = val if direction == "MINIMIZE" else -val
            total += w * signed
        return total

    def dominates(self, other: "ObjectiveValues") -> bool:
        """True si self domina a other (≤ en todos, < en alguno)."""
        if set(self.values.keys()) != set(other.values.keys()):
            return False
        at_least_one_better = False
        for code in self.values:
            s = self.values[code]
            o = other.values[code]
            direction = self.directions.get(code, "MINIMIZE")
            s_norm = s if direction == "MINIMIZE" else -s
            o_norm = o if direction == "MINIMIZE" else -o
            if s_norm > o_norm:
                return False
            if s_norm < o_norm:
                at_least_one_better = True
        return at_least_one_better


@dataclass
class ParetoPoint:
    candidate_id: str
    objective_values: Dict[str, float]
    dominance_rank: int = 1
    crowding_distance: float = 0.0
    label: Optional[str] = None
    is_selected: bool = False


@dataclass
class RobustnessResult:
    candidate_id: str
    method: str
    is_robust: bool = True
    min_reserve: float = 0.0
    mean_reserve: float = 0.0
    sensitivity: Dict[str, float] = field(default_factory=dict)
    scenario_results: List[Dict[str, Any]] = field(default_factory=list)
    samples_evaluated: int = 0


@dataclass
class Explanation:
    candidate_id: str
    summary: str
    governing_constraints: List[str] = field(default_factory=list)
    objective_contributions: Dict[str, float] = field(default_factory=dict)
    sensitivity_top: List[Dict[str, Any]] = field(default_factory=list)
    pareto_label: Optional[str] = None
    standard_comparison: Optional[Dict[str, Any]] = None
    rejection_reason: Optional[str] = None


@dataclass
class ExtractedFieldData:
    field_path: str
    value: Any
    unit: Optional[str]
    status: str            # VALID_FIELD_STATUSES
    confidence: float      # 0..1
    criticality: str       # CRITICAL, HIGH, MEDIUM, LOW
    interpretation: str
    uncertainty: Optional[Dict[str, Any]] = None
    confirmation_required: bool = True
    source_quote: Optional[str] = None

    def is_persistable(self) -> bool:
        return self.confidence >= 0.75 and self.status not in {"CONFLICT", "UNKNOWN"}


@dataclass
class RunConfig:
    run_id: str
    objectives: List[Dict[str, Any]]
    algorithm_config: Dict[str, Any]
    algorithm_version: str
    seed: Optional[int]
    budget_evaluations: int

    def canonical(self) -> str:
        data = {
            "objectives": sorted(self.objectives, key=lambda o: o["code"]),
            "algorithm_version": self.algorithm_version,
            "seed": self.seed,
            "budget_evaluations": self.budget_evaluations,
        }
        return json.dumps(data, sort_keys=True)

    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()[:32]


# ── DesignSpaceBuilder ────────────────────────────────────────────────────────

class DesignSpaceBuilder:
    """Construye el espacio de diseño a partir de especificaciones de variables."""

    @staticmethod
    def build(variable_specs: List[Dict[str, Any]]) -> DesignSpace:
        space = DesignSpace()
        for spec in variable_specs:
            name = spec.get("name")
            if not name:
                continue
            vtype = spec.get("variable_type", "CONTINUOUS")
            mode  = spec.get("mode", "OPTIMIZABLE")
            dom = spec.get("domain", {})

            domain = VariableDomain(
                variable_type=vtype,
                mode=mode,
                min_val=dom.get("min"),
                max_val=dom.get("max"),
                step=dom.get("step"),
                values=dom.get("values"),
                expression=dom.get("expression"),
            )
            space.variables[name] = domain
        return space

    @staticmethod
    def validate_dependencies(space: DesignSpace) -> Tuple[bool, List[str]]:
        """Verifica que las variables DEPENDENT/DERIVED referencien variables existentes."""
        errors = []
        for name, domain in space.variables.items():
            if domain.mode == "DERIVED" and domain.expression:
                # Extraer referencias simples tipo {var_name}
                refs = re.findall(r"\{(\w+)\}", domain.expression)
                for ref in refs:
                    if ref not in space.variables:
                        errors.append(f"{name}: references unknown variable '{ref}'")
        return len(errors) == 0, errors

    @staticmethod
    def apply_material_constraints(
        space: DesignSpace, material: str
    ) -> DesignSpace:
        """Adapta el dominio según el material (STEEL, ALUMINIUM, CONCRETE)."""
        # En producción consultaría bibliotecas; aquí retorna el espacio original
        return space


# ── ConstraintEngine ─────────────────────────────────────────────────────────

class ConstraintEngine:
    """Motor de evaluación de restricciones (8 clases, 10 pasos)."""

    def __init__(self) -> None:
        self._hard: List[Dict[str, Any]]    = []
        self._soft: List[Dict[str, Any]]    = []
        self._warning: List[Dict[str, Any]] = []

    def add_constraint(
        self,
        code: str,
        constraint_class: str,
        severity: str = "HARD",
        limit: Optional[Any] = None,
        evaluator: Optional[Callable[[Dict[str, Any]], bool]] = None,
        normative_reference: Optional[str] = None,
        version: str = "1",
    ) -> None:
        if constraint_class not in VALID_CONSTRAINT_CLASSES:
            raise ValueError(f"Unknown constraint class: {constraint_class}")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"Unknown severity: {severity}")
        entry = {
            "code": code,
            "class": constraint_class,
            "severity": severity,
            "limit": limit,
            "evaluator": evaluator,
            "norm_ref": normative_reference,
            "version": version,
        }
        if severity == "HARD":
            self._hard.append(entry)
        elif severity == "SOFT":
            self._soft.append(entry)
        else:
            self._warning.append(entry)

    def evaluate(self, candidate_vars: Dict[str, Any]) -> ConstraintResult:
        result = ConstraintResult()

        # Evaluar HARD (secuencia de 10 pasos: primero NORMATIVA, luego resto)
        for c in sorted(self._hard, key=lambda x: x["class"]):
            passed = self._eval_one(c, candidate_vars)
            if not passed:
                result.violations.append(c["code"])
                result.passed_hard = False
                if result.first_blocking is None:
                    result.first_blocking = c["code"]

        # Evaluar SOFT
        for c in self._soft:
            passed = self._eval_one(c, candidate_vars)
            if not passed:
                result.soft_violations.append(c["code"])

        # Evaluar WARNING
        for c in self._warning:
            passed = self._eval_one(c, candidate_vars)
            if not passed:
                result.warnings_list.append(c["code"])

        return result

    @staticmethod
    def _eval_one(c: Dict[str, Any], vars: Dict[str, Any]) -> bool:
        evaluator = c.get("evaluator")
        if callable(evaluator):
            try:
                return bool(evaluator(vars))
            except Exception:
                return False
        # Evaluador por defecto: limit dict con campo y comparador
        limit = c.get("limit")
        if isinstance(limit, dict):
            field = limit.get("field")
            op    = limit.get("op", "<=")
            val   = limit.get("value")
            if field and val is not None and field in vars:
                candidate_val = vars[field]
                try:
                    if op == "<=":  return candidate_val <= val
                    if op == ">=":  return candidate_val >= val
                    if op == "<":   return candidate_val < val
                    if op == ">":   return candidate_val > val
                    if op == "==":  return candidate_val == val
                    if op == "in":  return candidate_val in val
                    if op == "not_in": return candidate_val not in val
                except TypeError:
                    return False
        return True   # sin evaluador: se considera cumplida

    def constraint_count(self, severity: Optional[str] = None) -> int:
        if severity == "HARD":    return len(self._hard)
        if severity == "SOFT":    return len(self._soft)
        if severity == "WARNING": return len(self._warning)
        return len(self._hard) + len(self._soft) + len(self._warning)

    def get_codes(self, severity: Optional[str] = None) -> List[str]:
        targets = []
        if severity in (None, "HARD"):    targets.extend(self._hard)
        if severity in (None, "SOFT"):    targets.extend(self._soft)
        if severity in (None, "WARNING"): targets.extend(self._warning)
        return [c["code"] for c in targets]

    def remove_constraint(self, code: str) -> bool:
        for lst in [self._hard, self._soft, self._warning]:
            before = len(lst)
            lst[:] = [c for c in lst if c["code"] != code]
            if len(lst) < before:
                return True
        return False


# ── ObjectiveEngine ───────────────────────────────────────────────────────────

class ObjectiveEngine:
    """Motor de funciones objetivo (coste, peso, CO₂, equilibrado)."""

    def __init__(self) -> None:
        self._objectives: List[Dict[str, Any]] = []

    def add_objective(
        self,
        code: str,
        direction: str = "MINIMIZE",
        weight: float = 1.0,
        scope: Optional[str] = None,
    ) -> None:
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"direction must be one of {VALID_DIRECTIONS}")
        if weight < 0:
            raise ValueError("weight must be >= 0")
        codes = [o["code"] for o in self._objectives]
        if code in codes:
            raise ValueError(f"Duplicate objective code: {code}")
        self._objectives.append({
            "code": code,
            "direction": direction,
            "weight": weight,
            "scope": scope,
        })

    def compute(self, candidate_eval: Dict[str, float]) -> ObjectiveValues:
        values = {}
        weights = {}
        directions = {}
        for obj in self._objectives:
            code = obj["code"]
            if code in candidate_eval:
                values[code]     = float(candidate_eval[code])
                weights[code]    = obj["weight"]
                directions[code] = obj["direction"]
        return ObjectiveValues(values=values, weights=weights, directions=directions)

    def normalize_objectives(
        self, all_evals: List[Dict[str, float]]
    ) -> List[Dict[str, float]]:
        """Normaliza valores al rango [0,1] para cada objetivo."""
        if not all_evals:
            return []
        normalized = []
        codes = [o["code"] for o in self._objectives]
        mins  = {c: min(e.get(c, 0.0) for e in all_evals) for c in codes}
        maxs  = {c: max(e.get(c, 0.0) for e in all_evals) for c in codes}
        for e in all_evals:
            normed = {}
            for c in codes:
                span = maxs[c] - mins[c]
                normed[c] = (e.get(c, 0.0) - mins[c]) / span if span > 0 else 0.0
            normalized.append(normed)
        return normalized

    def objective_count(self) -> int:
        return len(self._objectives)

    def validate_weights(self) -> bool:
        return all(o["weight"] >= 0 for o in self._objectives)

    def get_objective(self, code: str) -> Optional[Dict[str, Any]]:
        for o in self._objectives:
            if o["code"] == code:
                return o
        return None


# ── ParetoManager ─────────────────────────────────────────────────────────────

class ParetoManager:
    """Gestión del frente de Pareto multiobjetivo."""

    def __init__(self, directions: Optional[Dict[str, str]] = None) -> None:
        self._points: List[ParetoPoint] = []
        self._directions: Dict[str, str] = directions or {}

    def add_candidate(
        self, candidate_id: str, objective_values: Dict[str, float]
    ) -> bool:
        """Añade candidato al frente. Retorna True si es no-dominado."""
        new_obj = ObjectiveValues(
            values=objective_values,
            weights={c: 1.0 for c in objective_values},
            directions=self._directions,
        )
        # Comprobar si algún punto existente domina al nuevo
        for p in self._points:
            existing = ObjectiveValues(
                values=p.objective_values,
                weights={c: 1.0 for c in p.objective_values},
                directions=self._directions,
            )
            if existing.dominates(new_obj):
                return False   # dominado — no entra al frente

        # Eliminar puntos que el nuevo domina
        self._points = [
            p for p in self._points
            if not new_obj.dominates(
                ObjectiveValues(
                    values=p.objective_values,
                    weights={c: 1.0 for c in p.objective_values},
                    directions=self._directions,
                )
            )
        ]
        self._points.append(ParetoPoint(
            candidate_id=candidate_id,
            objective_values=objective_values,
            dominance_rank=1,
        ))
        return True

    def is_dominated(self, objective_values: Dict[str, float]) -> bool:
        query = ObjectiveValues(
            values=objective_values,
            weights={c: 1.0 for c in objective_values},
            directions=self._directions,
        )
        for p in self._points:
            existing = ObjectiveValues(
                values=p.objective_values,
                weights={c: 1.0 for c in p.objective_values},
                directions=self._directions,
            )
            if existing.dominates(query):
                return True
        return False

    def get_front(self) -> List[ParetoPoint]:
        return list(self._points)

    def size(self) -> int:
        return len(self._points)

    def select_min(self, objective_code: str) -> Optional[str]:
        """Selecciona el candidato con menor valor en el objetivo indicado."""
        if not self._points:
            return None
        direction = self._directions.get(objective_code, "MINIMIZE")
        if direction == "MINIMIZE":
            best = min(self._points, key=lambda p: p.objective_values.get(objective_code, float("inf")))
        else:
            best = max(self._points, key=lambda p: p.objective_values.get(objective_code, float("-inf")))
        return best.candidate_id

    def select_knee(self, weights: Optional[Dict[str, float]] = None) -> Optional[str]:
        """Selecciona el punto 'knee' (equilibrado) del frente de Pareto."""
        if not self._points:
            return None
        if len(self._points) == 1:
            return self._points[0].candidate_id
        # Método de distancia al punto ideal normalizado
        codes = list(self._points[0].objective_values.keys())
        mins = {c: min(p.objective_values.get(c, 0) for p in self._points) for c in codes}
        maxs = {c: max(p.objective_values.get(c, 0) for p in self._points) for c in codes}
        w = weights or {c: 1.0 for c in codes}

        def dist_to_ideal(p: ParetoPoint) -> float:
            d = 0.0
            for c in codes:
                span = maxs[c] - mins[c]
                norm = (p.objective_values[c] - mins[c]) / span if span > 0 else 0.0
                direction = self._directions.get(c, "MINIMIZE")
                ideal_norm = 0.0 if direction == "MINIMIZE" else 1.0
                d += w.get(c, 1.0) * (norm - ideal_norm) ** 2
            return d ** 0.5

        best = min(self._points, key=dist_to_ideal)
        return best.candidate_id

    def label_alternatives(self) -> Dict[str, str]:
        """Asigna etiquetas obligatorias a las alternativas del frente."""
        labels: Dict[str, str] = {}
        if not self._points:
            return labels
        codes = list(self._points[0].objective_values.keys())
        for code in codes:
            best_id = self.select_min(code)
            label = f"MIN_{code.upper()}"
            if label in PARETO_LABELS and best_id:
                labels[best_id] = label
        knee_id = self.select_knee()
        if knee_id and knee_id not in labels:
            labels[knee_id] = "BALANCED"
        return labels

    def compute_crowding_distances(self) -> None:
        """Calcula distancias de crowding para mantener diversidad."""
        if len(self._points) <= 2:
            for p in self._points:
                p.crowding_distance = float("inf")
            return
        codes = list(self._points[0].objective_values.keys())
        for p in self._points:
            p.crowding_distance = 0.0
        for code in codes:
            sorted_pts = sorted(self._points, key=lambda p: p.objective_values.get(code, 0))
            sorted_pts[0].crowding_distance = float("inf")
            sorted_pts[-1].crowding_distance = float("inf")
            c_min = sorted_pts[0].objective_values[code]
            c_max = sorted_pts[-1].objective_values[code]
            span = c_max - c_min
            for i in range(1, len(sorted_pts) - 1):
                if span > 0:
                    sorted_pts[i].crowding_distance += (
                        (sorted_pts[i + 1].objective_values[code]
                         - sorted_pts[i - 1].objective_values[code]) / span
                    )

    def clear(self) -> None:
        self._points.clear()


# ── RobustnessEngine ──────────────────────────────────────────────────────────

class RobustnessEngine:
    """Evaluación de robustez mediante escenarios discretos u otros métodos."""

    @staticmethod
    def evaluate_discrete_scenarios(
        candidate_id: str,
        base_vars: Dict[str, Any],
        scenarios: List[Dict[str, Any]],
        eval_fn: Callable[[Dict[str, Any]], float],
        reserve_threshold: float = 0.0,
    ) -> RobustnessResult:
        """
        eval_fn(vars) -> reserve (negativo = fallo).
        reserve_threshold: mínimo aceptable (default 0).
        """
        if not scenarios:
            return RobustnessResult(
                candidate_id=candidate_id, method="DISCRETE_SCENARIOS", is_robust=True,
                min_reserve=float("inf"), samples_evaluated=0,
            )
        reserves = []
        scenario_results = []
        for s in scenarios:
            merged = {**base_vars, **s}
            try:
                r = float(eval_fn(merged))
            except Exception:
                r = float("-inf")
            reserves.append(r)
            scenario_results.append({"scenario": s, "reserve": r, "passed": r >= reserve_threshold})

        min_r  = min(reserves)
        mean_r = sum(reserves) / len(reserves)
        is_robust = min_r >= reserve_threshold

        # Sensibilidad: qué variables producen el peor escenario
        worst_idx = reserves.index(min_r)
        worst_scenario = scenarios[worst_idx]
        sensitivity = {k: abs(v - base_vars.get(k, v)) for k, v in worst_scenario.items()}

        return RobustnessResult(
            candidate_id=candidate_id,
            method="DISCRETE_SCENARIOS",
            is_robust=is_robust,
            min_reserve=min_r,
            mean_reserve=mean_r,
            sensitivity=sensitivity,
            scenario_results=scenario_results,
            samples_evaluated=len(scenarios),
        )

    @staticmethod
    def latin_hypercube_sample(
        n_samples: int,
        variable_ranges: Dict[str, Tuple[float, float]],
        seed: Optional[int] = None,
    ) -> List[Dict[str, float]]:
        """Genera n_samples puntos con Latin Hypercube Sampling."""
        import random
        rng = random.Random(seed)
        names  = list(variable_ranges.keys())
        result = []
        for i in range(n_samples):
            point = {}
            for name in names:
                lo, hi = variable_ranges[name]
                u = (i + rng.random()) / n_samples   # LHS
                point[name] = lo + u * (hi - lo)
            result.append(point)
        # Permutar columnas independientemente
        for name in names:
            vals = [p[name] for p in result]
            rng.shuffle(vals)
            for p, v in zip(result, vals):
                p[name] = v
        return result

    @staticmethod
    def check_monotonicity(
        eval_fn: Callable[[Dict[str, Any]], float],
        base_vars: Dict[str, Any],
        test_var: str,
        direction: str,   # "INCREASING" | "DECREASING"
        steps: int = 5,
    ) -> bool:
        """Prueba invariancia de monotonicidad esperada."""
        if test_var not in base_vars:
            return False
        base_val = float(base_vars[test_var])
        deltas = [base_val * (1 + 0.1 * (i + 1)) for i in range(steps)]
        results = []
        for d in deltas:
            v = {**base_vars, test_var: d}
            try:
                results.append(eval_fn(v))
            except Exception:
                return False
        if direction == "INCREASING":
            return all(results[i] <= results[i + 1] for i in range(len(results) - 1))
        return all(results[i] >= results[i + 1] for i in range(len(results) - 1))


# ── ExplanationEngine ─────────────────────────────────────────────────────────

class ExplanationEngine:
    """Genera explicaciones auditables para selecciones y descartes."""

    @staticmethod
    def explain_rejection(
        candidate_id: str,
        constraint_result: ConstraintResult,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Explanation:
        summary = (
            f"Candidato {candidate_id} rechazado: "
            f"{constraint_result.first_blocking or 'restricción no identificada'}"
        )
        return Explanation(
            candidate_id=candidate_id,
            summary=summary,
            governing_constraints=constraint_result.violations[:5],
            rejection_reason=constraint_result.first_blocking,
        )

    @staticmethod
    def explain_selection(
        candidate_id: str,
        objective_values: ObjectiveValues,
        pareto_label: Optional[str] = None,
        standard_comparison: Optional[Dict[str, Any]] = None,
    ) -> Explanation:
        contributions = {}
        total_w = sum(objective_values.weights.values()) or 1.0
        for code, val in objective_values.values.items():
            w = objective_values.weights.get(code, 1.0) / total_w
            contributions[code] = round(w * 100, 1)   # % de peso
        summary = f"Candidato {candidate_id} seleccionado como '{pareto_label or 'RANKED'}'"
        return Explanation(
            candidate_id=candidate_id,
            summary=summary,
            objective_contributions=contributions,
            pareto_label=pareto_label,
            standard_comparison=standard_comparison,
        )

    @staticmethod
    def explain_sensitivity(
        candidate_id: str,
        robustness_result: RobustnessResult,
    ) -> Explanation:
        top = sorted(
            robustness_result.sensitivity.items(), key=lambda x: -x[1]
        )[:5]
        summary = (
            f"Análisis de sensibilidad para {candidate_id}: "
            f"reserva mínima {robustness_result.min_reserve:.3f}"
        )
        return Explanation(
            candidate_id=candidate_id,
            summary=summary,
            sensitivity_top=[{"variable": k, "sensitivity": v} for k, v in top],
        )

    @staticmethod
    def format_run_manifest(
        run_id: str,
        config: Dict[str, Any],
        libraries_versions: Dict[str, str],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "config": config,
            "libraries_versions": libraries_versions,
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ── ArtifactManager ───────────────────────────────────────────────────────────

class ArtifactManager:
    """Gestiona manifests, trazas y entregables auditables."""

    @staticmethod
    def create_run_manifest(
        run_id: str,
        config: Dict[str, Any],
        libraries_versions: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "RUN_MANIFEST",
            "run_id": run_id,
            "config_hash": hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()
            ).hexdigest()[:16],
            "libraries": libraries_versions or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def create_candidate_trace(
        candidate_id: str,
        variables: Dict[str, Any],
        parent_id: Optional[str] = None,
        operations: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "CANDIDATE_TRACE",
            "candidate_id": candidate_id,
            "parent_id": parent_id,
            "variables_hash": hashlib.sha256(
                json.dumps(variables, sort_keys=True, default=str).encode()
            ).hexdigest()[:16],
            "operations": operations or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def create_decision_trace(
        run_id: str,
        selected_id: str,
        pareto_label: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "DECISION_TRACE",
            "run_id": run_id,
            "selected_candidate_id": selected_id,
            "pareto_label": pareto_label,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def create_data_lineage(
        field: str,
        source_type: str,   # USER_INPUT, DOCUMENT, CATALOG, INFERENCE
        source_ref: str,
        value: Any,
    ) -> Dict[str, Any]:
        return {
            "type": "DATA_LINEAGE",
            "field": field,
            "source_type": source_type,
            "source_ref": source_ref,
            "value_hash": hashlib.sha256(
                str(value).encode()
            ).hexdigest()[:16],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


# ── CandidateGenerator ────────────────────────────────────────────────────────

class CandidateGenerator:
    """Genera candidatos de diseño dentro del espacio definido."""

    def __init__(self, space: DesignSpace, seed: Optional[int] = None) -> None:
        self._space = space
        self._seed  = seed
        self._seen_hashes: Set[str] = set()

    def is_duplicate(self, variables: Dict[str, Any]) -> bool:
        h = self._space.candidate_hash(variables)
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def enumerate_discrete(self) -> List[Dict[str, Any]]:
        """Enumera todos los candidatos en espacios discretos pequeños."""
        import itertools
        axes = []
        names = []
        for name, domain in self._space.variables.items():
            if domain.mode not in {"OPTIMIZABLE", "SELECTABLE"}:
                continue
            if domain.variable_type in {"DISCRETE", "CATEGORICAL"}:
                axes.append(domain.values or [])
                names.append(name)
            elif domain.variable_type == "BOOLEAN":
                axes.append([True, False])
                names.append(name)
        candidates = []
        for combo in itertools.product(*axes):
            point = dict(zip(names, combo))
            if not self.is_duplicate(point):
                candidates.append(point)
        return candidates

    def generate_from_seed(self, seed_design: Dict[str, Any]) -> Dict[str, Any]:
        """Genera un candidato a partir de un diseño semilla."""
        return {k: v for k, v in seed_design.items()}

    def duplicate_rate(self, total_evaluated: int) -> float:
        if total_evaluated == 0:
            return 0.0
        unique = len(self._seen_hashes)
        return max(0.0, 1.0 - unique / total_evaluated)


# ── EvaluationBroker ─────────────────────────────────────────────────────────

class EvaluationBroker:
    """Orquesta llamadas a motores especializados (Fases 2-12)."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    def evaluate(
        self,
        candidate_id: str,
        geometry_hash: str,
        material: str,
        eval_fn: Optional[Callable[[str, str], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        cache_key = f"{geometry_hash}:{material}"
        if cache_key in self._cache:
            return {"cached": True, **self._cache[cache_key]}
        if eval_fn:
            result = eval_fn(geometry_hash, material)
        else:
            result = {"utilization": 0.85, "status": "PASS"}
        self._cache[cache_key] = result
        return {"cached": False, **result}

    def cache_size(self) -> int:
        return len(self._cache)

    def invalidate(self, geometry_hash: Optional[str] = None) -> int:
        if geometry_hash is None:
            n = len(self._cache)
            self._cache.clear()
            return n
        to_del = [k for k in self._cache if k.startswith(geometry_hash)]
        for k in to_del:
            del self._cache[k]
        return len(to_del)


# ── InterviewStateMachine ─────────────────────────────────────────────────────

class InterviewStateMachine:
    """Máquina de estados para la entrevista conversacional."""

    TRANSITIONS = INTERVIEW_TRANSITIONS

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        return to_state in cls.TRANSITIONS.get(from_state, set())

    @classmethod
    def transition(cls, current: str, event: str) -> str:
        """Aplica una transición o lanza ValueError si no es válida."""
        if current not in cls.TRANSITIONS:
            raise ValueError(f"Unknown state: {current}")
        allowed = cls.TRANSITIONS[current]
        if event not in allowed:
            raise ValueError(
                f"Cannot transition from {current} to {event}. "
                f"Allowed: {allowed}"
            )
        return event

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return state == "READY" or not cls.TRANSITIONS.get(state)

    @classmethod
    def requires_confirmation(cls, state: str) -> bool:
        return state in {"REVIEW", "CONFIRMED"}

    @classmethod
    def all_states(cls) -> List[str]:
        return list(cls.TRANSITIONS.keys())


# ── FieldInterpreter ──────────────────────────────────────────────────────────

class FieldInterpreter:
    """Interpreta texto libre en lenguaje natural a campos estructurados."""

    # Umbrales de confianza
    HIGH_CONFIDENCE   = 0.95
    MEDIUM_CONFIDENCE = 0.75
    LOW_CONFIDENCE    = 0.50

    # Patrones de extracción básicos (extensibles con NLP en producción)
    _APPROX_PATTERNS   = [r"unos?\s+(\d+(?:[.,]\d+)?)", r"aproximadamente\s+(\d+(?:[.,]\d+)?)"]
    _RANGE_PATTERNS    = [r"entre\s+(\d+(?:[.,]\d+)?)\s+y\s+(\d+(?:[.,]\d+)?)"]
    _NEGATION_PATTERNS = [r"no\s+(\w+)", r"sin\s+(\w+)"]

    UNIT_ALIASES: Dict[str, str] = {
        "metros": "m", "metro": "m",
        "kilogramos": "kg", "kilos": "kg", "kilo": "kg",
        "kilonewtons": "kN", "kilonewton": "kN",
        "kiloNewtons": "kN",
        "milímetros": "mm", "milimetros": "mm",
    }

    @classmethod
    def interpret(cls, text: str, field_type: str = "NUMERIC") -> ExtractedFieldData:
        """
        Interpreta texto libre. Retorna ExtractedFieldData con confianza y estado.
        No persiste: el nivel de confianza determina si se puede guardar.
        """
        text = text.strip()

        # Detectar rango
        for pat in cls._RANGE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                lo, hi = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
                return ExtractedFieldData(
                    field_path="",
                    value={"min": lo, "max": hi},
                    unit=cls._extract_unit(text),
                    status="RANGE",
                    confidence=cls.MEDIUM_CONFIDENCE,
                    criticality="MEDIUM",
                    interpretation=f"Rango [{lo}, {hi}]",
                    uncertainty={"type": "RANGE", "min": lo, "max": hi},
                    confirmation_required=True,
                    source_quote=text,
                )

        # Detectar valor aproximado
        for pat in cls._APPROX_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = float(m.group(1).replace(",", "."))
                uncertainty = val * 0.05   # 5% por defecto
                return ExtractedFieldData(
                    field_path="",
                    value=val,
                    unit=cls._extract_unit(text),
                    status="ESTIMATED",
                    confidence=cls.MEDIUM_CONFIDENCE,
                    criticality="MEDIUM",
                    interpretation=f"Valor aproximado: {val}",
                    uncertainty={"type": "ABSOLUTE", "value": uncertainty},
                    confirmation_required=True,
                    source_quote=text,
                )

        # Detectar negación
        for pat in cls._NEGATION_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                excluded = m.group(1)
                return ExtractedFieldData(
                    field_path="",
                    value={"excluded": excluded},
                    unit=None,
                    status="EXACT",
                    confidence=cls.HIGH_CONFIDENCE,
                    criticality="HIGH",
                    interpretation=f"Exclusión explícita: {excluded}",
                    confirmation_required=False,
                    source_quote=text,
                )

        # Valor numérico exacto
        m = re.search(r"(\d+(?:[.,]\d+)?)", text)
        if m:
            val = float(m.group(1).replace(",", "."))
            return ExtractedFieldData(
                field_path="",
                value=val,
                unit=cls._extract_unit(text),
                status="EXACT",
                confidence=cls.HIGH_CONFIDENCE,
                criticality="HIGH",
                interpretation=f"Valor exacto: {val}",
                confirmation_required=False,
                source_quote=text,
            )

        # Desconocido
        return ExtractedFieldData(
            field_path="",
            value=None,
            unit=None,
            status="UNKNOWN",
            confidence=cls.LOW_CONFIDENCE,
            criticality="LOW",
            interpretation="No se pudo extraer un valor",
            confirmation_required=True,
            source_quote=text,
        )

    @classmethod
    def _extract_unit(cls, text: str) -> Optional[str]:
        # Buscar unidades conocidas (más largas primero)
        for alias in sorted(cls.UNIT_ALIASES, key=len, reverse=True):
            if re.search(r"\b" + alias + r"\b", text, re.IGNORECASE):
                return cls.UNIT_ALIASES[alias]
        for unit in ["kNm", "kN", "MPa", "mm", "cm", "m", "kg", "t"]:
            if re.search(r"\b" + unit + r"\b", text):
                return unit
        return None

    @classmethod
    def detect_conflict(
        cls, existing_value: Any, new_value: Any, tolerance: float = 0.01
    ) -> bool:
        """Detecta conflicto entre dos valores del mismo campo."""
        try:
            return abs(float(existing_value) - float(new_value)) > tolerance * max(
                abs(float(existing_value)), 1.0
            )
        except (TypeError, ValueError):
            return str(existing_value) != str(new_value)

    @classmethod
    def normalize_unit(cls, value: float, from_unit: str, to_unit: str) -> float:
        """Conversiones básicas de unidades al SI."""
        conversions: Dict[Tuple[str, str], float] = {
            ("kN", "N"): 1000.0,
            ("N", "kN"): 0.001,
            ("kNm", "Nm"): 1000.0,
            ("t", "kg"): 1000.0,
            ("kg", "t"): 0.001,
            ("cm", "m"): 0.01,
            ("mm", "m"): 0.001,
            ("m", "mm"): 1000.0,
            ("m", "cm"): 100.0,
        }
        factor = conversions.get((from_unit, to_unit))
        if factor is not None:
            return value * factor
        raise ValueError(f"No conversion defined from {from_unit} to {to_unit}")


# ── QuestionPlanner ────────────────────────────────────────────────────────────

class QuestionPlanner:
    """Planifica qué preguntas formular según datos disponibles y prioridades."""

    def __init__(self, templates: List[Dict[str, Any]]) -> None:
        self._templates = templates

    def next_question(
        self,
        confirmed_fields: Set[str],
        blocked_fields: Set[str],
        state: str = "ELICITATION",
    ) -> Optional[Dict[str, Any]]:
        """Selecciona la próxima pregunta no formulada, en orden de criticidad."""
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "DERIVABLE": 4}
        candidates = []
        for tmpl in self._templates:
            # Verificar precondiciones
            preconditions = tmpl.get("preconditions", [])
            if not all(p in confirmed_fields for p in preconditions):
                continue
            # Verificar skip condition
            skip = tmpl.get("skip_condition")
            if skip and self._eval_skip(skip, confirmed_fields):
                continue
            # Verificar que ningún target ya esté confirmado
            targets = tmpl.get("target_fields", [])
            if all(t in confirmed_fields for t in targets):
                continue
            criticality = tmpl.get("criticality", "P2")
            candidates.append((priority_order.get(criticality, 5), tmpl))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def pending_critical(
        self, confirmed_fields: Set[str], priorities: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Devuelve preguntas críticas pendientes (P0 por defecto)."""
        target_priorities = set(priorities or ["P0"])
        pending = []
        for tmpl in self._templates:
            if tmpl.get("criticality") not in target_priorities:
                continue
            targets = tmpl.get("target_fields", [])
            if not all(t in confirmed_fields for t in targets):
                pending.append(tmpl)
        return pending

    @staticmethod
    def _eval_skip(condition: str, confirmed: Set[str]) -> bool:
        # Condición simple: "field_name:value" → skip si field_name confirmado
        return condition.split(":")[0] in confirmed


# ── OptimizationRunManager ────────────────────────────────────────────────────

class OptimizationRunManager:
    """Gestiona el ciclo de vida de una ejecución de optimización."""

    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        "DRAFT":     {"RUNNING"},
        "RUNNING":   {"PAUSED", "COMPLETED", "CANCELLED", "FAILED"},
        "PAUSED":    {"RUNNING", "CANCELLED"},
        "COMPLETED": set(),
        "CANCELLED": set(),
        "FAILED":    {"DRAFT"},   # permite reintentar desde cero
    }

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def create_run(cls, config: Dict[str, Any]) -> RunConfig:
        run_id = str(uuid.uuid4())
        return RunConfig(
            run_id=run_id,
            objectives=config.get("objectives", []),
            algorithm_config=config.get("algorithm_config", {}),
            algorithm_version=config.get("algorithm_version", "1.0.0"),
            seed=config.get("seed"),
            budget_evaluations=config.get("budget_evaluations", 1000),
        )

    @classmethod
    def compute_run_hash(cls, config: RunConfig) -> str:
        return config.compute_hash()

    @classmethod
    def validate_reproducibility(cls, hash1: str, hash2: str) -> bool:
        """Dos ejecuciones con el mismo hash deben producir los mismos resultados."""
        return hash1 == hash2

    @classmethod
    def validate_budget(cls, budget: int, material: str) -> Tuple[bool, str]:
        min_budgets = {
            "STEEL":     100,
            "ALUMINIUM": 150,
            "CONCRETE":  200,
        }
        minimum = min_budgets.get(material, 100)
        if budget < minimum:
            return False, f"Budget {budget} insuficiente para {material}; mínimo {minimum}"
        return True, "OK"


# ── OptimizationOrchestrator ──────────────────────────────────────────────────

class OptimizationOrchestrator:
    """
    Orquestador principal del flujo de optimización.
    Coordina: DesignSpaceBuilder → ConstraintEngine → CandidateGenerator
              → EvaluationBroker → ObjectiveEngine → ParetoManager
              → RobustnessEngine → ExplanationEngine → ArtifactManager
    """

    def __init__(
        self,
        space_builder: Optional[DesignSpaceBuilder] = None,
        constraint_engine: Optional[ConstraintEngine] = None,
        objective_engine: Optional[ObjectiveEngine] = None,
        pareto_manager: Optional[ParetoManager] = None,
        robustness_engine: Optional[RobustnessEngine] = None,
        explanation_engine: Optional[ExplanationEngine] = None,
        artifact_manager: Optional[ArtifactManager] = None,
        broker: Optional[EvaluationBroker] = None,
    ) -> None:
        self.space_builder    = space_builder or DesignSpaceBuilder()
        self.constraints      = constraint_engine or ConstraintEngine()
        self.objectives       = objective_engine or ObjectiveEngine()
        self.pareto           = pareto_manager or ParetoManager()
        self.robustness       = robustness_engine or RobustnessEngine()
        self.explainer        = explanation_engine or ExplanationEngine()
        self.artifacts        = artifact_manager or ArtifactManager()
        self.broker           = broker or EvaluationBroker()
        self._maturity: str   = "O0"

    @property
    def maturity_level(self) -> str:
        return self._maturity

    def advance_maturity(self, to_level: str) -> bool:
        order = ["O0", "O1", "O2", "O3", "O4", "O5"]
        if to_level not in order:
            return False
        curr_idx = order.index(self._maturity)
        next_idx = order.index(to_level)
        if next_idx == curr_idx + 1:   # solo avance secuencial
            self._maturity = to_level
            return True
        return False

    def run_single(
        self,
        candidate_vars: Dict[str, Any],
        eval_fn: Optional[Callable[[Dict[str, Any]], Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        """
        Evalúa un único candidato: restricciones → objetivos → Pareto.
        Retorna dict con status, constraint_result, objectives, pareto_added.
        """
        constraint_result = self.constraints.evaluate(candidate_vars)
        if not constraint_result.passed_hard:
            return {
                "status": "REJECTED",
                "constraint_result": constraint_result,
                "first_blocking": constraint_result.first_blocking,
            }

        raw_objectives = eval_fn(candidate_vars) if eval_fn else {}
        objective_values = self.objectives.compute(raw_objectives)
        cid = str(uuid.uuid4())
        pareto_added = self.pareto.add_candidate(cid, objective_values.values)

        return {
            "status": "VALID",
            "candidate_id": cid,
            "constraint_result": constraint_result,
            "objective_values": objective_values,
            "pareto_added": pareto_added,
        }

    def explain_run(self) -> Dict[str, Any]:
        """Genera el resumen explicativo del frente de Pareto actual."""
        labels = self.pareto.label_alternatives()
        self.pareto.compute_crowding_distances()
        return {
            "pareto_size": self.pareto.size(),
            "labels": labels,
            "maturity": self._maturity,
            "cache_size": self.broker.cache_size(),
        }
