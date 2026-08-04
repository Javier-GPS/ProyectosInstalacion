"""
Salvi Studio · Columns — Fase 17: Servicio analítico de validación V&V
Implementa los 8 servicios del framework: métricas de correlación, dominios,
gates, no conformidades, trazabilidad y gestión de regresión.
Sin dependencias de Pydantic ni SQLAlchemy (apto para tests en sandbox).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Constantes y códigos de error
# ──────────────────────────────────────────────────────────────────────────────

EVIDENCE_LEVELS = ["E0", "E1", "E2", "E3", "E4", "E5"]
VALIDATION_LEVELS = ["V0", "V1", "V2", "V3", "V4", "V5"]
CRITICALITY_LEVELS = ["C1", "C2", "C3", "C4", "C5"]
NCM_SEVERITIES = ["S1", "S2", "S3", "S4"]
GATE_IDS = ["G17_1", "G17_2", "G17_3", "G17_4", "G17_5", "G17_6", "G17_7"]

# Tolerancias objetivo por tipo de cantidad
DEFAULT_TOLERANCES: Dict[str, float] = {
    "stress":      0.01,   # ±1 %  — casos lineales globales
    "reaction":    0.01,
    "force":       0.01,
    "deformation": 0.02,   # ±2 %
    "deflection":  0.02,
    "frequency":   0.03,   # ±3 %
    "mass":        0.01,   # ≤1 %
    "default":     0.05,
}

# Nivel de evidencia mínimo por criticidad para poder cerrar un gate
MIN_EVIDENCE_FOR_CRITICALITY: Dict[str, str] = {
    "C1": "E1",
    "C2": "E2",
    "C3": "E2",
    "C4": "E3",
    "C5": "E4",
}

# Nivel de validación requerido para cada gate (en orden)
GATE_REQUIRED_VALIDATION_LEVEL: Dict[str, str] = {
    "G17_1": "V0",
    "G17_2": "V1",
    "G17_3": "V2",
    "G17_4": "V3",
    "G17_5": "V4",
    "G17_6": "V4",
    "G17_7": "V5",
}

ERROR_CODES_F17: Dict[str, Tuple[str, str]] = {
    "VAL-REQ-001": ("BLOQUEANTE", "Requisito sin evidencia o criticidad C4/C5 sin nivel mínimo"),
    "VAL-REQ-002": ("GRAVE",      "Trazabilidad incompleta: requisito sin prueba asociada"),
    "VAL-COR-001": ("BLOQUEANTE", "Error relativo supera tolerancia objetivo"),
    "VAL-COR-002": ("GRAVE",      "Sesgo sistemático detectado: |bias| > 0.5·tolerancia"),
    "VAL-COR-003": ("GRAVE",      "Factor de modelo fuera de [0.90, 1.10]"),
    "VAL-CAL-001": ("BLOQUEANTE", "Equipo sin calibración vigente"),
    "VAL-DOM-001": ("BLOQUEANTE", "Candidato fuera del dominio de cualificación"),
    "VAL-DOM-002": ("AVISO",      "Candidato en zona de extrapolación permitida"),
    "VAL-NCM-001": ("BLOQUEANTE", "No conformidad S3/S4 abierta bloquea gate"),
    "VAL-NCM-002": ("GRAVE",      "No conformidad sin causa raíz ni CAPA definidos"),
    "VAL-GAT-001": ("BLOQUEANTE", "Gate en estado BLOCKED: no se puede avanzar"),
    "VAL-GAT-002": ("GRAVE",      "Gate sin todas las evidencias requeridas"),
    "VAL-REG-001": ("BLOQUEANTE", "Regresión detectada: golden case con resultado diferente"),
    "VAL-UNC-001": ("GRAVE",      "Incertidumbre combinada supera límite aceptable"),
}


# ──────────────────────────────────────────────────────────────────────────────
# Tipos de datos (dataclasses — sin Pydantic)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ErrorInfo:
    code: str
    severity: str
    detail: str


@dataclass
class CorrelationMetrics:
    n_points: int
    e_rel_max: float
    e_rel_mean: float
    rmse: float
    bias: float
    model_factor: float         # θ = mean(y_ref / y_calc)
    passed: bool
    tolerance_target: float
    error_codes: List[str] = dc_field(default_factory=list)
    detail: Dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class UncertaintyBudget:
    components: List[Dict[str, float]]   # [{"name": ..., "u_i": ...}, ...]
    k: float                              # coverage factor (typically 2)
    U: float                              # expanded uncertainty = k·sqrt(Σ ui²)
    exceeded: bool
    limit: Optional[float] = None


@dataclass
class DomainCheckResult:
    in_domain: bool
    violations: List[Dict[str, Any]]
    warnings: List[str]
    validation_level: str
    error_codes: List[str] = dc_field(default_factory=list)


@dataclass
class RegressionResult:
    tc_id: str
    passed: bool
    expected: Dict[str, Any]
    computed: Dict[str, Any]
    delta: Dict[str, float]        # {quantity: relative_delta}
    error_codes: List[str] = dc_field(default_factory=list)
    detail: str = ""


@dataclass
class GateCheckResult:
    gate_id: str
    can_pass: bool
    missing_evidences: List[str]
    blocking_ncms: List[str]
    validation_level_ok: bool
    error_codes: List[str] = dc_field(default_factory=list)


@dataclass
class TraceabilityNode:
    req_id: str
    source: str
    criticality: str
    evidence_level: str
    state: str
    test_case_refs: List[str]
    run_states: List[str]
    evidence_refs: List[str]
    compliant: bool
    error_codes: List[str] = dc_field(default_factory=list)


@dataclass
class ImpactResult:
    changed_element: str
    affected_modules: List[str]
    affected_test_cases: List[str]
    revalidation_required: bool
    severity: str                   # HIGH | MEDIUM | LOW
    detail: str = ""


@dataclass
class NcmAssessment:
    ncm_id: str
    severity: str
    blocks_gate: Optional[str]
    capa_defined: bool
    root_cause_defined: bool
    can_close: bool
    error_codes: List[str] = dc_field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _evidence_index(level: str) -> int:
    try:
        return EVIDENCE_LEVELS.index(level)
    except ValueError:
        return -1


def _validation_index(level: str) -> int:
    try:
        return VALIDATION_LEVELS.index(level)
    except ValueError:
        return -1


def _stable_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


# ──────────────────────────────────────────────────────────────────────────────
# CorrelationService
# ──────────────────────────────────────────────────────────────────────────────

class CorrelationService:
    """Calcula métricas de correlación modelo–ensayo conforme a Fase 17 §13."""

    Y_FLOOR = 1e-6   # denominador mínimo para e_rel

    @staticmethod
    def e_rel(y_calc: float, y_ref: float, y_floor: float = 1e-6) -> float:
        """Error relativo: |y_calc - y_ref| / max(|y_ref|, y_floor)."""
        denom = max(abs(y_ref), y_floor)
        return abs(y_calc - y_ref) / denom

    @classmethod
    def compute_metrics(
        cls,
        predicted: List[float],
        measured: List[float],
        quantity: str = "default",
        tolerance_target: Optional[float] = None,
        y_floor: float = 1e-6,
    ) -> CorrelationMetrics:
        n = len(predicted)
        if n == 0:
            raise ValueError("La lista de valores predichos no puede estar vacía.")
        if len(measured) != n:
            raise ValueError("Las listas predicted y measured deben tener la misma longitud.")

        tol = tolerance_target if tolerance_target is not None else DEFAULT_TOLERANCES.get(
            quantity, DEFAULT_TOLERANCES["default"]
        )

        e_rels = [cls.e_rel(p, m, y_floor) for p, m in zip(predicted, measured)]
        diffs  = [p - m for p, m in zip(predicted, measured)]
        ratios = [(m / p) if abs(p) > y_floor else 1.0 for p, m in zip(predicted, measured)]

        e_rel_max  = max(e_rels)
        e_rel_mean = sum(e_rels) / n
        rmse = math.sqrt(sum(d**2 for d in diffs) / n)
        bias = sum(diffs) / n
        model_factor = sum(ratios) / n

        error_codes: List[str] = []
        if e_rel_max > tol:
            error_codes.append("VAL-COR-001")
        if abs(bias) > 0.5 * tol * (sum(abs(m) for m in measured) / n):
            error_codes.append("VAL-COR-002")
        if not (0.90 <= model_factor <= 1.10):
            error_codes.append("VAL-COR-003")

        return CorrelationMetrics(
            n_points=n,
            e_rel_max=e_rel_max,
            e_rel_mean=e_rel_mean,
            rmse=rmse,
            bias=bias,
            model_factor=model_factor,
            passed=(len(error_codes) == 0),
            tolerance_target=tol,
            error_codes=error_codes,
            detail={"y_floor": y_floor, "quantity": quantity},
        )


# ──────────────────────────────────────────────────────────────────────────────
# UncertaintyService
# ──────────────────────────────────────────────────────────────────────────────

class UncertaintyService:
    """Presupuesto de incertidumbre combinada U = k·sqrt(Σ ui²)."""

    @staticmethod
    def compute(
        components: List[Dict[str, float]],
        k: float = 2.0,
        limit: Optional[float] = None,
    ) -> UncertaintyBudget:
        """
        components: lista de {"name": str, "u_i": float}
        k: factor de cobertura (normalmente 2 para ~95 %)
        limit: si se proporciona, comprueba si U supera el límite
        """
        if not components:
            raise ValueError("Se necesita al menos un componente de incertidumbre.")

        u_combined = math.sqrt(sum(c["u_i"] ** 2 for c in components))
        U = k * u_combined
        exceeded = (limit is not None) and (U > limit)
        return UncertaintyBudget(
            components=components,
            k=k,
            U=U,
            exceeded=exceeded,
            limit=limit,
        )


# ──────────────────────────────────────────────────────────────────────────────
# QualificationService
# ──────────────────────────────────────────────────────────────────────────────

class QualificationService:
    """Evalúa si un candidato está dentro del dominio de cualificación."""

    @staticmethod
    def evaluate_domain(
        geometric_limits: Dict[str, Any],
        material_limits: Dict[str, Any],
        load_limits: Dict[str, Any],
        process_limits: Dict[str, Any],
        candidate: Dict[str, Any],
        validation_level: str = "V0",
    ) -> DomainCheckResult:
        violations: List[Dict[str, Any]] = []
        warnings:   List[str] = []

        all_limits: Dict[str, Any] = {}
        all_limits.update(geometric_limits)
        all_limits.update(material_limits)
        all_limits.update(load_limits)
        all_limits.update(process_limits)

        for key, spec in all_limits.items():
            if key not in candidate:
                continue
            val = candidate[key]
            if isinstance(spec, dict):
                lo = spec.get("min")
                hi = spec.get("max")
                extrapolation = spec.get("extrapolation_factor", 0.0)

                strict_lo = lo
                strict_hi = hi
                if lo is not None and val < lo:
                    # Check extrapolation zone
                    ext_lo = lo * (1.0 - extrapolation) if extrapolation > 0 else lo
                    if val >= ext_lo and extrapolation > 0:
                        warnings.append(
                            f"{key}={val} en zona de extrapolación [{ext_lo:.4g}, {lo:.4g})"
                        )
                    else:
                        violations.append({"param": key, "value": val, "limit": {"min": lo}})
                elif hi is not None and val > hi:
                    ext_hi = hi * (1.0 + extrapolation) if extrapolation > 0 else hi
                    if val <= ext_hi and extrapolation > 0:
                        warnings.append(
                            f"{key}={val} en zona de extrapolación ({hi:.4g}, {ext_hi:.4g}]"
                        )
                    else:
                        violations.append({"param": key, "value": val, "limit": {"max": hi}})

        in_domain = len(violations) == 0
        error_codes: List[str] = []
        if not in_domain:
            error_codes.append("VAL-DOM-001")
        if warnings:
            error_codes.append("VAL-DOM-002")

        return DomainCheckResult(
            in_domain=in_domain,
            violations=violations,
            warnings=warnings,
            validation_level=validation_level,
            error_codes=error_codes,
        )


# ──────────────────────────────────────────────────────────────────────────────
# RegressionService
# ──────────────────────────────────────────────────────────────────────────────

class RegressionService:
    """Compara resultados computados con golden cases congelados."""

    def __init__(self, tolerance: float = 1e-6):
        self.tolerance = tolerance

    def compare(
        self,
        tc_id: str,
        expected: Dict[str, Any],
        computed: Dict[str, Any],
    ) -> RegressionResult:
        delta: Dict[str, float] = {}
        error_codes: List[str] = []

        for key, ref_val in expected.items():
            if key not in computed:
                delta[key] = float("inf")
                error_codes.append("VAL-REG-001")
                continue
            comp_val = computed[key]
            if isinstance(ref_val, (int, float)) and isinstance(comp_val, (int, float)):
                denom = max(abs(ref_val), 1e-12)
                d = abs(comp_val - ref_val) / denom
                delta[key] = d
                if d > self.tolerance:
                    error_codes.append("VAL-REG-001")
            else:
                if ref_val != comp_val:
                    delta[key] = float("inf")
                    error_codes.append("VAL-REG-001")
                else:
                    delta[key] = 0.0

        passed = len(error_codes) == 0
        detail = "Golden case OK" if passed else f"Regresión detectada en: {list(delta.keys())}"
        return RegressionResult(
            tc_id=tc_id,
            passed=passed,
            expected=expected,
            computed=computed,
            delta=delta,
            error_codes=list(set(error_codes)),
            detail=detail,
        )


# ──────────────────────────────────────────────────────────────────────────────
# TraceabilityService
# ──────────────────────────────────────────────────────────────────────────────

class TraceabilityService:
    """Mantiene el grafo requisito → implementación → prueba → evidencia."""

    @staticmethod
    def check_requirement(
        req_id: str,
        source: str,
        criticality: str,
        evidence_level: str,
        state: str,
        test_case_refs: List[str],
        run_states: List[str],
        evidence_refs: List[str],
    ) -> TraceabilityNode:
        error_codes: List[str] = []
        min_evidence = MIN_EVIDENCE_FOR_CRITICALITY.get(criticality, "E1")

        if _evidence_index(evidence_level) < _evidence_index(min_evidence):
            error_codes.append("VAL-REQ-001")

        if not test_case_refs:
            error_codes.append("VAL-REQ-002")

        compliant = (
            len(error_codes) == 0
            and state == "CLOSED"
            and all(s == "PASSED" for s in run_states)
        )

        return TraceabilityNode(
            req_id=req_id,
            source=source,
            criticality=criticality,
            evidence_level=evidence_level,
            state=state,
            test_case_refs=test_case_refs,
            run_states=run_states,
            evidence_refs=evidence_refs,
            compliant=compliant,
            error_codes=error_codes,
        )

    @staticmethod
    def coverage_report(
        nodes: List[TraceabilityNode],
    ) -> Dict[str, Any]:
        """Calcula métricas de cobertura sobre un conjunto de requisitos."""
        total = len(nodes)
        if total == 0:
            return {"total": 0, "compliant": 0, "coverage_pct": 0.0, "high_crit_covered": True}

        compliant = sum(1 for n in nodes if n.compliant)
        high_crit = [n for n in nodes if n.criticality in ("C4", "C5")]
        high_crit_covered = all(n.compliant for n in high_crit)

        return {
            "total": total,
            "compliant": compliant,
            "coverage_pct": round(100.0 * compliant / total, 2),
            "high_crit_covered": high_crit_covered,
            "c4_c5_count": len(high_crit),
            "c4_c5_compliant": sum(1 for n in high_crit if n.compliant),
        }


# ──────────────────────────────────────────────────────────────────────────────
# ReleaseService
# ──────────────────────────────────────────────────────────────────────────────

class ReleaseService:
    """Controla los gates de liberación G17.1 … G17.7."""

    @staticmethod
    def check_gate(
        gate_id: str,
        gate_state: str,
        required_evidences: List[str],
        provided_evidences: List[str],
        blocking_ncms: List[str],
        current_validation_level: str,
    ) -> GateCheckResult:
        error_codes: List[str] = []

        if gate_state == "BLOCKED":
            error_codes.append("VAL-GAT-001")

        missing = [e for e in required_evidences if e not in provided_evidences]
        if missing:
            error_codes.append("VAL-GAT-002")

        if blocking_ncms:
            error_codes.append("VAL-NCM-001")

        required_level = GATE_REQUIRED_VALIDATION_LEVEL.get(gate_id, "V0")
        level_ok = _validation_index(current_validation_level) >= _validation_index(required_level)

        can_pass = (
            len(error_codes) == 0
            and level_ok
            and gate_state != "BLOCKED"
        )

        return GateCheckResult(
            gate_id=gate_id,
            can_pass=can_pass,
            missing_evidences=missing,
            blocking_ncms=blocking_ncms,
            validation_level_ok=level_ok,
            error_codes=error_codes,
        )

    @staticmethod
    def gate_sequence_ok(gates: List[Dict[str, str]]) -> bool:
        """Verifica que los gates se cierran en orden secuencial."""
        passed_indices: List[int] = []
        for g in gates:
            gid = g.get("gate_id", "")
            state = g.get("gate_state", "")
            if state == "PASSED" and gid in GATE_IDS:
                passed_indices.append(GATE_IDS.index(gid))

        if not passed_indices:
            return True
        return passed_indices == sorted(passed_indices) and passed_indices == list(
            range(passed_indices[0], passed_indices[-1] + 1)
        )


# ──────────────────────────────────────────────────────────────────────────────
# NcmService
# ──────────────────────────────────────────────────────────────────────────────

class NcmService:
    """Gestión de no conformidades: severidad, CAPA y bloqueo de gates."""

    @staticmethod
    def assess(
        ncm_id: str,
        severity: str,
        root_cause: Optional[str],
        containment: Optional[str],
        capa: Dict[str, Any],
        state: str,
        blocks_gate: Optional[str],
    ) -> NcmAssessment:
        error_codes: List[str] = []

        capa_defined = bool(capa and capa.get("actions"))
        root_cause_defined = bool(root_cause and root_cause.strip())

        if severity in ("S3", "S4") and state == "OPEN":
            error_codes.append("VAL-NCM-001")

        if not root_cause_defined or not capa_defined:
            error_codes.append("VAL-NCM-002")

        can_close = bool(
            (root_cause_defined and capa_defined and severity not in ("S3", "S4"))
            or (severity in ("S3", "S4") and bool(capa.get("approved_by")))
        )

        return NcmAssessment(
            ncm_id=ncm_id,
            severity=severity,
            blocks_gate=blocks_gate,
            capa_defined=capa_defined,
            root_cause_defined=root_cause_defined,
            can_close=can_close,
            error_codes=error_codes,
        )

    @staticmethod
    def severity_from_string(s: str) -> str:
        s = s.upper().strip()
        if s in NCM_SEVERITIES:
            return s
        raise ValueError(f"Severidad inválida: {s!r}. Valores válidos: {NCM_SEVERITIES}")


# ──────────────────────────────────────────────────────────────────────────────
# ImpactService
# ──────────────────────────────────────────────────────────────────────────────

class ImpactService:
    """Propaga cambios y determina qué módulos y casos de prueba necesitan revalidación."""

    # Mapa simplificado de propagación: qué módulos dependen de cada módulo
    DEPENDENCY_MAP: Dict[str, List[str]] = {
        "geometry":   ["actions", "structural", "steel", "aluminium", "concrete",
                       "details", "joints", "baseplate", "foundation", "cad_bom"],
        "actions":    ["structural", "steel", "aluminium", "concrete", "details",
                       "joints", "baseplate", "foundation"],
        "structural": ["steel", "aluminium", "concrete", "details", "joints",
                       "baseplate", "foundation", "catenary"],
        "steel":      ["details", "joints", "baseplate", "cad_bom", "reports"],
        "aluminium":  ["details", "joints", "baseplate", "cad_bom", "reports"],
        "concrete":   ["details", "joints", "baseplate", "foundation", "cad_bom", "reports"],
        "baseplate":  ["foundation", "cad_bom", "reports"],
        "foundation": ["cad_bom", "reports"],
        "catenary":   ["structural", "cad_bom", "reports"],
    }

    @classmethod
    def propagate(
        cls,
        changed_element: str,
        test_cases_by_module: Dict[str, List[str]],
    ) -> ImpactResult:
        affected_modules = cls.DEPENDENCY_MAP.get(changed_element, [])
        affected_tcs: List[str] = []
        for mod in affected_modules:
            affected_tcs.extend(test_cases_by_module.get(mod, []))

        revalidation = len(affected_modules) > 0
        severity = "HIGH" if changed_element in ("structural", "geometry", "actions") else \
                   "MEDIUM" if changed_element in ("steel", "aluminium", "concrete") else "LOW"

        return ImpactResult(
            changed_element=changed_element,
            affected_modules=affected_modules,
            affected_test_cases=list(set(affected_tcs)),
            revalidation_required=revalidation,
            severity=severity,
            detail=f"Cambio en '{changed_element}' impacta {len(affected_modules)} módulos "
                   f"y {len(set(affected_tcs))} casos de prueba.",
        )


# ──────────────────────────────────────────────────────────────────────────────
# ValidationOrchestrator
# ──────────────────────────────────────────────────────────────────────────────

class ValidationOrchestrator:
    """Coordina suites de prueba, dependencias y evaluación de nivel de madurez."""

    def __init__(self) -> None:
        self.correlation_svc = CorrelationService()
        self.uncertainty_svc = UncertaintyService()
        self.qualification_svc = QualificationService()
        self.regression_svc = RegressionService()
        self.traceability_svc = TraceabilityService()
        self.release_svc = ReleaseService()
        self.ncm_svc = NcmService()
        self.impact_svc = ImpactService()

    def compute_maturity_level(
        self,
        nodes: List[TraceabilityNode],
        gates: List[Dict[str, str]],
        has_physical_tests: bool,
        has_fpc: bool,
        has_external_cert: bool,
    ) -> str:
        """Determina el nivel de madurez V0-V5 a partir del estado de validación."""
        coverage = self.traceability_svc.coverage_report(nodes)

        # V0: por defecto
        if coverage["compliant"] == 0:
            return "V0"

        # V1: pruebas unitarias y analíticas aprobadas
        e1_nodes = [n for n in nodes if _evidence_index(n.evidence_level) >= 1]
        if not e1_nodes or not all(n.compliant for n in e1_nodes):
            return "V0"
        if not any(g["gate_state"] == "PASSED" and g["gate_id"] == "G17_2" for g in gates):
            return "V1"

        # V2: comparación independiente y regresión
        if not any(g["gate_state"] == "PASSED" and g["gate_id"] == "G17_3" for g in gates):
            return "V2"

        # V3: correlación con ensayos
        if not has_physical_tests:
            return "V2"
        if not any(g["gate_state"] == "PASSED" and g["gate_id"] == "G17_4" for g in gates):
            return "V3"

        # V4: FPC y validación industrial
        if not has_fpc:
            return "V3"
        if not any(g["gate_state"] == "PASSED" and g["gate_id"] == "G17_5" for g in gates):
            return "V4"

        # V5: certificación externa
        if has_external_cert:
            return "V5"
        return "V4"

    def summary_report(
        self,
        plan_code: str,
        nodes: List[TraceabilityNode],
        gates: List[Dict[str, str]],
        open_ncms: List[NcmAssessment],
        has_physical_tests: bool = False,
        has_fpc: bool = False,
        has_external_cert: bool = False,
    ) -> Dict[str, Any]:
        coverage = self.traceability_svc.coverage_report(nodes)
        maturity = self.compute_maturity_level(
            nodes, gates, has_physical_tests, has_fpc, has_external_cert
        )
        blocking = [n for n in open_ncms if n.severity in ("S3", "S4")]
        gate_seq_ok = self.release_svc.gate_sequence_ok(gates)

        return {
            "plan_code": plan_code,
            "maturity_level": maturity,
            "coverage": coverage,
            "gates_sequence_ok": gate_seq_ok,
            "blocking_ncms": len(blocking),
            "open_ncms": len(open_ncms),
            "overall_blocked": len(blocking) > 0 or not gate_seq_ok,
        }


# ──────────────────────────────────────────────────────────────────────────────
# InputHasher (para snapshots reproducibles)
# ──────────────────────────────────────────────────────────────────────────────

class InputHasher:
    """Genera un hash determinista a partir de los inputs de un test run."""

    @staticmethod
    def hash_inputs(inputs: Dict[str, Any]) -> str:
        return _stable_hash(inputs)

    @staticmethod
    def hash_results(results: Dict[str, Any]) -> str:
        return _stable_hash(results)
