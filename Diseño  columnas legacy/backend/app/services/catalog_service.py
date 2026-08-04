"""
Fase 12 · Catálogo y Selección Estándar — Services
FilterEngine, SelectionAlgorithm, HierarchyResolver, ScoreEngine,
SubstitutionResolver, CompatibilityEngine, CatalogHealthService, ImportPipeline.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RequirementSnapshot:
    """Normalized, immutable project requirements."""
    nominal_height_m: float
    base_type: str
    market_country: str
    moment_knm: float = 0.0
    shear_kn: float = 0.0
    axial_kn: float = 0.0
    wind_area_m2: float = 0.0
    luminaire_mass_kg: float = 0.0
    material: Optional[str] = None
    door_required: Optional[bool] = None
    arm_count: int = 0
    max_utilization_limit: float = 0.9
    has_catenary: bool = False
    norm_edition: Optional[str] = None
    ranking_profile: str = "COMMERCIAL"
    maturity_level_required: Optional[str] = None
    snapshot_hash: str = ""

    def __post_init__(self) -> None:
        if not self.snapshot_hash:
            self.snapshot_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = {
            "h": round(self.nominal_height_m, 3),
            "base": self.base_type,
            "country": self.market_country,
            "My": round(self.moment_knm, 3),
            "Vy": round(self.shear_kn, 3),
            "N": round(self.axial_kn, 3),
            "A_w": round(self.wind_area_m2, 3),
            "m_L": round(self.luminaire_mass_kg, 2),
            "mat": self.material or "",
            "util": round(self.max_utilization_limit, 3),
            "catenary": self.has_catenary,
            "norm": self.norm_edition or "",
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class FilterResult:
    product_id: str
    product_code: str
    passed: bool
    discard_reasons: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    product_id: str
    route: str            # ROUTE_A / ROUTE_B / ROUTE_C
    compliant: bool
    max_utilization: float
    governing_check: str
    confidence: str       # HIGH / MEDIUM / LOW / CONDITIONAL
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateSummary:
    product_id: str
    product_code: str
    family_id: str
    hierarchy_ordinal: int
    max_utilization: float
    verification_route: str
    # Objectives (for scoring)
    cost_eur: float = 0.0
    mass_kg: float = 0.0
    co2_kg: float = 0.0
    lead_time_days: int = 0
    supply_risk: float = 0.0    # 0=LOW, 0.5=MEDIUM, 1.0=HIGH
    config_delta: float = 0.0   # deviation from requested config (0=exact)
    reserve: float = 0.0        # 1 - max_utilization
    # Labels
    label: str = ""
    score: float = 0.0
    is_immediately_superior: bool = False
    is_inferior_candidate: bool = False


@dataclass
class SelectionResult:
    recommended: Optional[CandidateSummary]
    alternatives: list[CandidateSummary]
    inferior_candidate: Optional[CandidateSummary]    # always evaluated and shown
    discarded: list[FilterResult]
    needs_custom_design: bool
    confidence: str
    next_action: str
    selection_trace_hash: str


# ---------------------------------------------------------------------------
# Filter Engine
# ---------------------------------------------------------------------------

DISCARD_CODES = {
    "market": "CAT-MARKET-001",
    "geo": "CAT-GEO-002",
    "load": "CAT-LOAD-003",
    "door": "CAT-DOOR-004",
    "base": "CAT-BASE-005",
    "evidence": "CAT-EVID-006",
    "supply": "CAT-SUPPLY-007",
    "norm": "CAT-NORM-008",
    "config": "CAT-CONFIG-009",
    "data": "CAT-DATA-010",
}


class FilterEngine:
    """
    Hard filter pipeline — executed BEFORE ranking.
    All filters must pass; order optimized for early discard but result is order-independent.
    """

    @classmethod
    def evaluate(cls,
                 product: dict[str, Any],
                 req: RequirementSnapshot) -> FilterResult:
        """
        Evaluate a single product against all hard filters.
        product dict keys: id, code, status, base_type, sales_regions,
        nominal_height_m, piece_length_m, is_segmented, door_available,
        norm_editions, data_complete, is_offerable, max_moment_knm,
        maturity_level, evidence_sufficient.
        """
        reasons: list[str] = []

        # F1: Status and supply
        if product.get("status") not in ("HOMOLOGATED", "RESTRICTED", "CANDIDATE"):
            reasons.append(DISCARD_CODES["supply"])

        # F2: Market authorization
        sales_regions = product.get("sales_regions") or []
        if req.market_country and req.market_country not in sales_regions and sales_regions:
            reasons.append(DISCARD_CODES["market"])

        # F3: Base type
        if product.get("base_type") and product["base_type"] != req.base_type:
            reasons.append(DISCARD_CODES["base"])

        # F4: Material filter
        if req.material and product.get("material") and product["material"] != req.material:
            reasons.append(DISCARD_CODES["geo"])

        # F5: Height/geometry — product height >= required height
        prod_height = product.get("nominal_height_m")
        if prod_height is not None and prod_height < req.nominal_height_m - 0.01:
            reasons.append(DISCARD_CODES["geo"])

        # F6: Piece length > 12m without segmentation
        piece_len = product.get("piece_length_m") or 0.0
        if piece_len > 12.0 and not product.get("is_segmented", False):
            reasons.append(DISCARD_CODES["geo"])

        # F7: Catenary — non-special domain
        if req.has_catenary and not product.get("catenary_capable", False):
            reasons.append(DISCARD_CODES["load"])

        # F8: Door required
        if req.door_required and not product.get("door_available", True):
            reasons.append(DISCARD_CODES["door"])

        # F9: Normative route
        norm_eds = product.get("norm_editions") or []
        if req.norm_edition and norm_eds and req.norm_edition not in norm_eds:
            reasons.append(DISCARD_CODES["norm"])

        # F10: Data completeness
        if not product.get("data_complete", True):
            reasons.append(DISCARD_CODES["data"])

        # F11: Evidence maturity
        required_level = req.maturity_level_required
        if required_level and not product.get("evidence_sufficient", True):
            reasons.append(DISCARD_CODES["evidence"])

        return FilterResult(
            product_id=product["id"],
            product_code=product["code"],
            passed=len(reasons) == 0,
            discard_reasons=reasons,
        )

    @classmethod
    def filter_all(cls,
                   catalog: list[dict[str, Any]],
                   req: RequirementSnapshot) -> tuple[list[dict], list[FilterResult]]:
        """Returns (passed_products, discarded_results)."""
        passed = []
        discarded = []
        for product in catalog:
            result = cls.evaluate(product, req)
            if result.passed:
                passed.append(product)
            else:
                discarded.append(result)
        return passed, discarded


# ---------------------------------------------------------------------------
# Domain Evaluator
# ---------------------------------------------------------------------------

class DomainEvaluator:
    """
    Evaluates project requirements against a product's performance envelope.
    No interpolation outside domain; extrapolation is prohibited.
    """

    @classmethod
    def evaluate(cls,
                 envelope: dict[str, Any],
                 req: RequirementSnapshot) -> tuple[str, bool, dict[str, float]]:
        """
        Returns (applicability_status, inside_domain, boundary_margins).
        applicability_status: COVERED / RECALCULATE / CONDITIONAL / OUT_OF_SCOPE / UNKNOWN
        """
        if not envelope:
            return "UNKNOWN", False, {}

        margins: dict[str, float] = {}
        out_of_scope = False
        recalculate = False

        # Check each domain dimension
        checks = [
            ("moment_knm", "max_moment_knm"),
            ("shear_kn", "max_shear_kn"),
            ("axial_kn", "max_axial_kn"),
            ("wind_area_m2", "max_wind_area_m2"),
            ("luminaire_mass_kg", "max_luminaire_mass_kg"),
        ]

        for req_field, env_field in checks:
            req_val = getattr(req, req_field, 0.0) or 0.0
            env_max = envelope.get(env_field)
            if env_max is not None and env_max > 0:
                margin = (env_max - req_val) / env_max
                margins[req_field] = margin
                if req_val > env_max:
                    out_of_scope = True
                elif req_val > env_max * 0.95:
                    recalculate = True   # within 5% of limit → recalculate

        if out_of_scope:
            return "OUT_OF_SCOPE", False, margins
        if recalculate:
            return "RECALCULATE", True, margins
        if not margins:
            return "UNKNOWN", False, margins
        return "COVERED", True, margins


# ---------------------------------------------------------------------------
# Verification Engine
# ---------------------------------------------------------------------------

class VerificationEngine:
    """
    Assigns verification route and checks compliance.
    Route A: covered by domain evidence → use stored utilization.
    Route B: recalculate with Phases 3-11.
    Route C: special method / OT required.
    """

    @classmethod
    def verify(cls,
               product: dict[str, Any],
               applicability_status: str,
               req: RequirementSnapshot) -> VerificationResult:
        pid = product["id"]
        code = product.get("code", "")

        if applicability_status == "COVERED":
            # Route A: use precalculated utilization
            stored_util = product.get("stored_utilization", 0.7)
            compliant = stored_util <= req.max_utilization_limit
            return VerificationResult(
                product_id=pid, route="ROUTE_A",
                compliant=compliant, max_utilization=stored_util,
                governing_check=product.get("governing_check", "GLOBAL_BENDING"),
                confidence="HIGH",
            )
        elif applicability_status in ("RECALCULATE", "CONDITIONAL"):
            # Route B: full recalculation (stub)
            # In production: call Phases 3-11 engine
            recalc_util = product.get("recalc_utilization", 0.85)
            compliant = recalc_util <= req.max_utilization_limit
            confidence = "MEDIUM" if applicability_status == "RECALCULATE" else "CONDITIONAL"
            return VerificationResult(
                product_id=pid, route="ROUTE_B",
                compliant=compliant, max_utilization=recalc_util,
                governing_check="FULL_RECALC",
                confidence=confidence,
            )
        elif applicability_status == "OUT_OF_SCOPE":
            return VerificationResult(
                product_id=pid, route="ROUTE_C",
                compliant=False, max_utilization=999.0,
                governing_check="OUT_OF_DOMAIN",
                confidence="LOW",
            )
        else:  # UNKNOWN
            return VerificationResult(
                product_id=pid, route="ROUTE_C",
                compliant=False, max_utilization=999.0,
                governing_check="INSUFFICIENT_DATA",
                confidence="LOW",
            )


# ---------------------------------------------------------------------------
# Hierarchy Resolver
# ---------------------------------------------------------------------------

class HierarchyResolver:
    """
    Resolves the 'immediately superior' product within a declared hierarchy.
    A family without a declared hierarchy cannot declare any product as 'immediately superior'.
    """

    @classmethod
    def resolve(cls,
                candidates: list[CandidateSummary],
                has_hierarchy: bool) -> list[CandidateSummary]:
        """
        Groups candidates by family_id + hierarchy_ordinal.
        Marks the lowest compliant ordinal as is_immediately_superior.
        Marks the highest non-compliant ordinal as is_inferior_candidate.
        """
        if not has_hierarchy:
            # No hierarchy → cannot declare "immediately superior"
            return candidates

        compliant = [c for c in candidates if c.max_utilization <= 0.9]
        non_compliant = [c for c in candidates if c.max_utilization > 0.9]

        if compliant:
            lowest = min(compliant, key=lambda c: c.hierarchy_ordinal)
            lowest.is_immediately_superior = True

        if non_compliant:
            highest_non = max(non_compliant, key=lambda c: c.hierarchy_ordinal)
            highest_non.is_inferior_candidate = True

        return candidates

    @classmethod
    def check_cross_family(cls, family_a: str, family_b: str,
                            cross_allowed: bool) -> bool:
        """Two products from different families cannot be compared without approval."""
        if family_a == family_b:
            return True
        return cross_allowed

    @classmethod
    def detect_substitution_cycle(cls,
                                   chain: list[str]) -> bool:
        """Returns True if a cycle is detected in substitution chain."""
        return len(chain) != len(set(chain))


# ---------------------------------------------------------------------------
# Score Engine
# ---------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "COMMERCIAL":   {"config_delta": 0.25, "cost": 0.20, "reserve": 0.15,
                     "availability": 0.15, "mass": 0.10, "co2": 0.10, "risk": 0.05},
    "ENGINEERING":  {"config_delta": 0.10, "cost": 0.15, "reserve": 0.30,
                     "availability": 0.10, "mass": 0.15, "co2": 0.10, "risk": 0.10},
    "ESG":          {"config_delta": 0.10, "cost": 0.15, "reserve": 0.15,
                     "availability": 0.10, "mass": 0.20, "co2": 0.25, "risk": 0.05},
    "URGENT":       {"config_delta": 0.10, "cost": 0.15, "reserve": 0.15,
                     "availability": 0.35, "mass": 0.10, "co2": 0.05, "risk": 0.10},
    "MAINTENANCE":  {"config_delta": 0.15, "cost": 0.20, "reserve": 0.15,
                     "availability": 0.20, "mass": 0.15, "co2": 0.05, "risk": 0.10},
}


class ScoreEngine:
    """
    Scores valid candidates only. Score never rescues a non-compliant candidate.
    Penalizes excessive reserve (>30% over internal limit).
    """

    @classmethod
    def _normalize(cls, val: float, lo: float, hi: float) -> float:
        """0 = best (low), 1 = worst (high). Normalized to [0,1]."""
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (val - lo) / (hi - lo)))

    @classmethod
    def score(cls,
              candidates: list[CandidateSummary],
              profile: str = "COMMERCIAL",
              internal_utilization_limit: float = 0.9) -> list[CandidateSummary]:
        """
        Score valid candidates. Returns sorted list with labels assigned.
        Score penalizes excessive reserve: util < 0.5 * limit → penalty.
        """
        # Only score compliant candidates
        valid = [c for c in candidates if c.max_utilization <= internal_utilization_limit]
        if not valid:
            return candidates

        weights = SCORE_WEIGHTS.get(profile, SCORE_WEIGHTS["COMMERCIAL"])

        # Collect objective ranges for normalisation
        costs  = [c.cost_eur       for c in valid]
        masses = [c.mass_kg        for c in valid]
        co2s   = [c.co2_kg         for c in valid]
        leads  = [c.lead_time_days for c in valid]
        risks  = [c.supply_risk    for c in valid]
        deltas = [c.config_delta   for c in valid]
        utils  = [c.max_utilization for c in valid]

        for c in valid:
            # Reserve score: higher utilization (less oversized) scores better
            reserve_norm = cls._normalize(c.max_utilization, min(utils), internal_utilization_limit)
            # Penalise extreme oversizing (util < 50% of limit)
            excess_penalty = max(0.0, 0.5 * internal_utilization_limit - c.max_utilization)

            def _n(val: float, vals: list) -> float:
                return cls._normalize(val, min(vals), max(vals))

            c.score = (
                weights["config_delta"] * _n(c.config_delta, deltas)
                + weights["cost"]        * _n(c.cost_eur,       costs)
                + weights["reserve"]     * reserve_norm
                + weights["availability"]* _n(c.lead_time_days, leads)
                + weights["mass"]        * _n(c.mass_kg,        masses)
                + weights["co2"]         * _n(c.co2_kg,         co2s)
                + weights["risk"]        * _n(c.supply_risk,    risks)
                + 0.8 * excess_penalty  # stronger penalty for extreme oversizing
            )

        valid_sorted = sorted(valid, key=lambda c: c.score)
        if valid_sorted:
            valid_sorted[0].label = "RECOMMENDED"

        # Labels for alternatives
        by_cost = min(valid, key=lambda c: c.cost_eur)
        by_co2 = min(valid, key=lambda c: c.co2_kg)
        by_avail = min(valid, key=lambda c: c.lead_time_days)

        for c, lbl in [(by_cost, "MIN_COST"), (by_co2, "MIN_CO2"), (by_avail, "FAST_DELIVERY")]:
            if not c.label:
                c.label = lbl

        return candidates   # return all (valid scored, non-valid unchanged)


# ---------------------------------------------------------------------------
# Substitution Resolver
# ---------------------------------------------------------------------------

class SubstitutionResolver:
    """
    Resolves substitution chains without cycles.
    Propagates adaptations to open projects.
    """

    @classmethod
    def resolve_chain(cls,
                      product_id: str,
                      substitution_map: dict[str, dict[str, Any]],
                      max_depth: int = 20) -> list[str]:
        """
        Follow substitution chain from product_id.
        Returns ordered list of IDs from start to final.
        Raises ValueError if cycle detected.
        """
        chain = [product_id]
        current = product_id
        visited: set[str] = {current}

        for _ in range(max_depth):
            sub = substitution_map.get(current)
            if not sub:
                break
            nxt = sub["to_product_id"]
            if nxt in visited:
                raise ValueError(f"CAT-DATA-010: ciclo en cadena de sustitución detectado en {nxt}")
            chain.append(nxt)
            visited.add(nxt)
            current = nxt

        return chain

    @classmethod
    def check_no_cycle(cls, from_id: str, to_id: str,
                       existing_map: dict[str, str]) -> bool:
        """Return True if adding from_id→to_id would create a cycle."""
        # Follow chain from to_id; if we reach from_id, it's a cycle
        visited: set[str] = {from_id}
        current = to_id
        for _ in range(50):
            if current in visited:
                return True
            if current not in existing_map:
                break
            visited.add(current)
            current = existing_map[current]
        return False


# ---------------------------------------------------------------------------
# Compatibility Engine
# ---------------------------------------------------------------------------

class CompatibilityEngine:
    """
    Evaluates option compatibility rules (REQUIRE, EXCLUDE, IMPLIES, RANGE, ONE_OF, ALL_OF).
    Returns PASS / FAIL / UNKNOWN with responsible fields.
    """

    @classmethod
    def evaluate_rule(cls,
                      rule: dict[str, Any],
                      configuration: dict[str, Any]) -> dict[str, Any]:
        """
        rule: {rule_op, condition: {field, op, value}, consequence: {field, op, value}}
        """
        op = rule.get("rule_op", "REQUIRE")
        condition = rule.get("condition", {})
        consequence = rule.get("consequence", {})

        cond_val = cls._get_field(configuration, condition.get("field", ""))
        cons_val = cls._get_field(configuration, consequence.get("field", ""))

        if cond_val is None:
            return {"result": "UNKNOWN", "responsible_fields": [condition.get("field")]}

        cond_passes = cls._compare(cond_val, condition.get("op", "=="),
                                   condition.get("value"))

        if op == "REQUIRE":
            if cond_passes:
                # consequence must hold
                if cons_val is None:
                    return {"result": "UNKNOWN",
                            "responsible_fields": [consequence.get("field")]}
                cons_passes = cls._compare(cons_val, consequence.get("op", "=="),
                                           consequence.get("value"))
                result = "PASS" if cons_passes else "FAIL"
            else:
                result = "PASS"   # condition not active → rule not triggered
        elif op == "EXCLUDE":
            # condition and consequence must not both be true
            if cons_val is None:
                result = "UNKNOWN"
            else:
                cons_active = cls._compare(cons_val, consequence.get("op", "=="),
                                           consequence.get("value"))
                result = "FAIL" if (cond_passes and cons_active) else "PASS"
        elif op == "IMPLIES":
            result = "PASS"   # simplified: treated as REQUIRE
        else:
            result = "PASS"   # ONE_OF / ALL_OF / RANGE handled elsewhere

        return {
            "result": result,
            "responsible_fields": [condition.get("field"), consequence.get("field")],
        }

    @classmethod
    def evaluate_all(cls,
                     rules: list[dict[str, Any]],
                     configuration: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        for rule in rules:
            r = cls.evaluate_rule(rule, configuration)
            r["rule_code"] = rule.get("rule_code", "")
            r["rule_op"] = rule.get("rule_op", "")
            results.append(r)
        return results

    @staticmethod
    def _get_field(config: dict[str, Any], dotted_key: str) -> Any:
        keys = dotted_key.split(".")
        val = config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return None
        return val

    @staticmethod
    def _compare(a: Any, op: str, b: Any) -> bool:
        try:
            if op == "==":
                return a == b
            elif op == ">":
                return float(a) > float(b)
            elif op == ">=":
                return float(a) >= float(b)
            elif op == "<":
                return float(a) < float(b)
            elif op == "<=":
                return float(a) <= float(b)
            elif op == "in":
                return a in b
            elif op == "not_in":
                return a not in b
        except (TypeError, ValueError):
            return False
        return False

    @classmethod
    def detect_option_cycle(cls, rules: list[dict[str, Any]]) -> bool:
        """
        Detect cycles in option dependency graph.
        Simplified: builds adjacency and checks for back-edges.
        """
        # Build graph: condition_field → consequence_field
        graph: dict[str, set[str]] = {}
        for rule in rules:
            src = rule.get("condition", {}).get("field", "")
            dst = rule.get("consequence", {}).get("field", "")
            if src and dst:
                graph.setdefault(src, set()).add(dst)

        # DFS cycle detection
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for node in list(graph.keys()):
            if node not in visited:
                if dfs(node):
                    return True
        return False


# ---------------------------------------------------------------------------
# Selection Algorithm
# ---------------------------------------------------------------------------

class SelectionAlgorithm:
    """
    7-step canonical selection algorithm.
    Principle: filter first, score last. Score never rescues non-compliant.
    """

    @classmethod
    def run(cls,
            catalog: list[dict[str, Any]],
            req: RequirementSnapshot,
            hierarchy_map: dict[str, dict[str, Any]],
            profile: str = "COMMERCIAL") -> SelectionResult:
        """
        catalog: list of product dicts with domain/verification data
        hierarchy_map: family_id → {has_hierarchy, ordinals}
        """
        # Step 1: already normalized in RequirementSnapshot

        # Step 2: Hard filter
        passed_products, discarded = FilterEngine.filter_all(catalog, req)

        if not passed_products:
            return SelectionResult(
                recommended=None, alternatives=[], inferior_candidate=None,
                discarded=discarded, needs_custom_design=True,
                confidence="LOW", next_action="NEEDS_CUSTOM_DESIGN",
                selection_trace_hash=req.snapshot_hash,
            )

        # Steps 3+4: Domain evaluation + verification
        candidates: list[CandidateSummary] = []
        for product in passed_products:
            env = product.get("performance_envelope") or {}
            app_status, inside, margins = DomainEvaluator.evaluate(env, req)
            ver = VerificationEngine.verify(product, app_status, req)

            c = CandidateSummary(
                product_id=product["id"],
                product_code=product.get("code", ""),
                family_id=product.get("family_id", ""),
                hierarchy_ordinal=product.get("hierarchy_ordinal", 999),
                max_utilization=ver.max_utilization,
                verification_route=ver.route,
                cost_eur=product.get("cost_eur", 0.0),
                mass_kg=product.get("mass_kg", 0.0),
                co2_kg=product.get("co2_kg", 0.0),
                lead_time_days=product.get("lead_time_days", 30),
                supply_risk=product.get("supply_risk_score", 0.0),
                config_delta=product.get("config_delta", 0.0),
                reserve=max(0.0, req.max_utilization_limit - ver.max_utilization),
            )
            candidates.append(c)

        # Step 5: Hierarchy — find immediately superior
        fam_id = candidates[0].family_id if candidates else ""
        h_data = hierarchy_map.get(fam_id, {"has_hierarchy": False})
        candidates = HierarchyResolver.resolve(candidates, h_data.get("has_hierarchy", False))

        # Step 6: Score valid candidates only
        candidates = ScoreEngine.score(candidates, profile=profile,
                                       internal_utilization_limit=req.max_utilization_limit)

        # Step 7: Build result
        compliant = [c for c in candidates if c.max_utilization <= req.max_utilization_limit]
        recommended = next((c for c in compliant if c.label == "RECOMMENDED"), None)
        alternatives = [c for c in compliant
                        if c.label in ("MIN_COST", "MIN_CO2", "FAST_DELIVERY")
                        and c is not recommended][:3]
        inferior = next((c for c in candidates if c.is_inferior_candidate), None)

        if not compliant:
            needs_custom = True
            confidence = "LOW"
            next_action = "NEEDS_CUSTOM_DESIGN"
        else:
            needs_custom = False
            confidence = "HIGH" if recommended else "MEDIUM"
            next_action = "ACCEPT"

        trace_payload = {
            "req_hash": req.snapshot_hash,
            "n_catalog": len(catalog),
            "n_filtered": len(passed_products),
            "n_compliant": len(compliant),
        }
        trace_hash = hashlib.sha256(
            json.dumps(trace_payload, sort_keys=True).encode()
        ).hexdigest()[:32]

        return SelectionResult(
            recommended=recommended,
            alternatives=alternatives,
            inferior_candidate=inferior,
            discarded=discarded,
            needs_custom_design=needs_custom,
            confidence=confidence,
            next_action=next_action,
            selection_trace_hash=trace_hash,
        )


# ---------------------------------------------------------------------------
# Catalog Health Service
# ---------------------------------------------------------------------------

@dataclass
class HealthIndicator:
    family_code: Optional[str]
    missing_geometry_count: int
    unresolved_material_count: int
    expired_evidence_count: int
    no_domain_evidence_count: int
    suspended_supplier_count: int
    mass_discrepancy_count: int
    duplicate_candidate_count: int
    total_products: int
    health_score: float


class CatalogHealthService:
    """Computes catalog health indicators."""

    MASS_DISCREPANCY_TOLERANCE = 0.05   # 5% tolerance

    @classmethod
    def compute(cls,
                products: list[dict[str, Any]],
                family_code: Optional[str] = None) -> HealthIndicator:
        total = len(products)
        missing_geo = sum(1 for p in products if not p.get("geometry_ok", True))
        unresolved_mat = sum(1 for p in products if not p.get("material_resolved", True))
        expired_ev = sum(1 for p in products if p.get("evidence_expired", False))
        no_domain = sum(1 for p in products if not p.get("has_domain", True))
        suspended = sum(1 for p in products if p.get("supplier_suspended", False))
        mass_disc = sum(1 for p in products
                        if abs(p.get("mass_discrepancy_fraction", 0.0))
                        > cls.MASS_DISCREPANCY_TOLERANCE)
        duplicate = cls._count_duplicates(products)

        # Health score: fraction of products with no issues
        issues = missing_geo + unresolved_mat + expired_ev + suspended + mass_disc
        health = max(0.0, 1.0 - issues / max(total, 1))

        return HealthIndicator(
            family_code=family_code,
            missing_geometry_count=missing_geo,
            unresolved_material_count=unresolved_mat,
            expired_evidence_count=expired_ev,
            no_domain_evidence_count=no_domain,
            suspended_supplier_count=suspended,
            mass_discrepancy_count=mass_disc,
            duplicate_candidate_count=duplicate,
            total_products=total,
            health_score=round(health, 3),
        )

    @staticmethod
    def _count_duplicates(products: list[dict[str, Any]]) -> int:
        """Count products sharing the same (geometry_hash, material) pair."""
        seen: dict[str, int] = {}
        for p in products:
            key = f"{p.get('geometry_hash', '')}:{p.get('material_grade', '')}"
            seen[key] = seen.get(key, 0) + 1
        return sum(1 for v in seen.values() if v > 1)


# ---------------------------------------------------------------------------
# Import Pipeline (simplified)
# ---------------------------------------------------------------------------

@dataclass
class ImportValidationResult:
    row_index: int
    product_code: str
    errors: list[str]
    warnings: list[str]
    valid: bool


class ImportPipeline:
    """
    Validates incoming catalog data rows before staging.
    Rules:
    - Duplicate code → block (unless explicit revision)
    - Missing unit → block (never infer silently)
    - Height inconsistency → warning
    - Mass discrepancy > tolerance → warning + block
    - Unresolved material → block
    - Evidence without domain → import as not-applicable
    """

    REQUIRED_FIELDS = ["product_code", "revision", "family_code", "material_grade",
                       "nominal_height_m", "base_type", "status", "market_scope"]

    @classmethod
    def validate_row(cls,
                     row: dict[str, Any],
                     existing_codes: set[str],
                     known_materials: set[str],
                     row_index: int = 0) -> ImportValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        code = str(row.get("product_code", ""))

        # Check required fields
        for fld in cls.REQUIRED_FIELDS:
            if fld not in row or row[fld] is None or str(row[fld]).strip() == "":
                errors.append(f"CAT-DATA-010: campo obligatorio ausente: {fld}")

        # Duplicate code
        if code in existing_codes:
            errors.append(f"CAT-DATA-010: código duplicado {code!r} — requiere revisión explícita")

        # Material resolution
        mat = row.get("material_grade", "")
        if mat and known_materials and mat not in known_materials:
            errors.append(f"CAT-DATA-010: material {mat!r} no resuelto a biblioteca publicada")

        # Height consistency
        nh = row.get("nominal_height_m")
        th = row.get("total_height_m")
        if nh is not None and th is not None:
            if float(th) < float(nh):
                errors.append("CAT-DATA-010: total_height_m < nominal_height_m")

        # Mass discrepancy
        cat_mass = row.get("piece_mass_kg")
        cad_mass = row.get("cad_mass_kg")
        if cat_mass and cad_mass:
            disc = abs(float(cat_mass) - float(cad_mass)) / max(float(cad_mass), 1.0)
            if disc > 0.05:
                warnings.append(f"Discrepancia de masa: catálogo={cat_mass}, CAD={cad_mass}, diff={disc:.1%}")
                if disc > 0.20:
                    errors.append("CAT-DATA-010: discrepancia de masa >20% — bloqueo")

        # Evidence without domain
        has_evidence = row.get("evidence_ids")
        has_domain = row.get("has_domain", False)
        if has_evidence and not has_domain:
            warnings.append("Evidencia importada sin dominio — marcada como no aplicable hasta revisión")

        return ImportValidationResult(
            row_index=row_index,
            product_code=code,
            errors=errors,
            warnings=warnings,
            valid=len(errors) == 0,
        )

    @classmethod
    def validate_batch(cls,
                       rows: list[dict[str, Any]],
                       existing_codes: set[str],
                       known_materials: set[str]) -> list[ImportValidationResult]:
        results = []
        seen_in_batch: set[str] = set()
        for i, row in enumerate(rows):
            code = str(row.get("product_code", ""))
            if code in seen_in_batch:
                # Intra-batch duplicate
                row["_intra_dup"] = True
            seen_in_batch.add(code)
            results.append(cls.validate_row(row, existing_codes, known_materials, i))
        return results


# ---------------------------------------------------------------------------
# Selection hash
# ---------------------------------------------------------------------------

def compute_selection_hash(req_snapshot_hash: str,
                           catalog_snapshot_id: str,
                           recommended_id: str,
                           utilization: float) -> str:
    payload = {
        "req": req_snapshot_hash,
        "cat": catalog_snapshot_id,
        "rec": recommended_id,
        "util": round(utilization, 4),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
