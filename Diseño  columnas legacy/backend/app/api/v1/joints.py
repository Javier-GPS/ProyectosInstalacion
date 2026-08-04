"""
Salvi Studio · Columns — Fase 9: Uniones y Columnas Segmentadas
API FastAPI v1
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status as http_status
from pydantic import BaseModel

from app.models.schemas.joints import (
    SegmentPlanRequest, SegmentPlanResult,
    TelescopicRequest, TelescopicCheckResult, TelescopicRobustRequest,
    BoltGroupRequest, BoltGroupResult,
    FlangeAccessCheck, FlangeAccessResult,
    WeldedJointRequest, WeldedJointResult,
    SleeveRequest, SleeveResult,
    HybridInterfaceRequest, HybridInterfaceResult,
    ConcreteInterfaceRequest, ConcreteInterfaceResult,
    JointCandidate as JointCandidateSchema,
    OptimizationWeights, OptimizationResult,
    AssemblyValidationRequest, AssemblyValidationResult,
    JointReleaseCreate,
)
from app.services.joints_service import (
    SegmentationService, SegmentationResult,
    TelescopicJointService,
    FlangedJointService,
    WeldedJointService,
    SleeveJointService,
    HybridInterfaceService,
    JointParetoCandidate, JointOptimizer,
    JointNormativeClassifier,
    AssemblyService,
)
from app.models.db.joints import JointCheckStatus

router = APIRouter(prefix="/joints", tags=["fase9-uniones"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_to_response(r, extra: dict = None) -> dict:
    data = {
        "status": r.status.value,
        "utilization": round(r.utilization, 4),
        "governing_rule": r.governing_rule,
        "intermediate_values": r.intermediate_values,
        "error_codes": r.error_codes,
    }
    if extra:
        data.update(extra)
    return data


# ── Segmentación ──────────────────────────────────────────────────────────────

@router.post("/segment-plans/generate", summary="Generar plan de segmentación")
async def generate_segment_plan(req: SegmentPlanRequest) -> dict:
    """Pasos 1-4 del algoritmo de segmentación."""
    result: SegmentationResult = SegmentationService.generate(
        total_height_m=req.total_height_m,
        material_route=req.material_route,
        max_length_m=req.constraints.max_piece_length_m,
        max_mass_kg=req.constraints.max_piece_mass_kg,
        preferred_stations=req.constraints.preferred_stations,
        exception_approved=req.constraints.exception_approved,
    )
    segments = [
        {
            "index": s.index,
            "z_start_m": s.z_start,
            "z_end_m": s.z_end,
            "length_m": s.length,
            "envelope_length_m": s.envelope_length,
            "mass_kg": s.mass_kg,
            "galvanizing_ok": s.galvanizing_ok,
            "transport_ok": s.transport_ok,
            "weight_ok": s.weight_ok,
            "error_codes": s.error_codes,
        }
        for s in result.segments
    ]
    joints = [
        {
            "joint_type": j.joint_type.value,
            "z_station_m": j.z_station,
            "in_forbidden_zone": j.in_forbidden_zone,
            "stiffness_model": j.stiffness_model,
            "error_codes": j.error_codes,
        }
        for j in result.joints
    ]
    return {
        "feasible": result.feasible,
        "piece_count": result.piece_count,
        "segments": segments,
        "joints": joints,
        "plan_hash": result.plan_hash,
        "error_codes": result.error_codes,
        "warnings": result.warnings,
    }


# ── Telescópica ───────────────────────────────────────────────────────────────

@router.post("/telescopic/analyze", summary="Verificar unión telescópica")
async def analyze_telescopic(req: TelescopicRequest) -> dict:
    r = TelescopicJointService.check_overlap(
        D_ext_mm=req.D_ext_mm, t_wall_mm=req.t_wall_mm,
        overlap_mm=req.overlap_mm, My_knm=req.My_knm, Mz_knm=req.Mz_knm,
        N_kn=req.N_kn, friction_coeff=req.friction_coeff,
        fy_mpa=req.fy_mpa, ovalization_mm=req.ovalization_mm,
    )
    drain = TelescopicJointService.check_drain(True, req.environment)
    result = _check_to_response(r)
    result["fretting_risk"] = r.intermediate_values.get("fretting_risk", False)
    result["rigidity_kN_per_mm"] = r.intermediate_values.get("rigidity_kN_per_mm", 0.0)
    result["drain_blocked"] = drain["blocked"]
    return result


@router.post("/telescopic/insertion-force", summary="Verificar fuerza de inserción telescópica")
async def check_insertion_force(
    D_ext_mm: float, t_wall_mm: float, overlap_mm: float,
    friction_coeff_max: float, insertion_force_limit_kn: Optional[float] = None,
) -> dict:
    return TelescopicJointService.check_insertion_force(
        D_ext_mm, t_wall_mm, overlap_mm, friction_coeff_max, insertion_force_limit_kn)


@router.post("/telescopic/robust", summary="Escenario robusto telescópica")
async def check_telescopic_robust(req: TelescopicRobustRequest) -> dict:
    base = TelescopicJointService.check_overlap(
        D_ext_mm=req.base.D_ext_mm, t_wall_mm=req.base.t_wall_mm,
        overlap_mm=req.base.overlap_mm, My_knm=req.base.My_knm, Mz_knm=req.base.Mz_knm,
        N_kn=req.base.N_kn, friction_coeff=req.base.friction_coeff,
        fy_mpa=req.base.fy_mpa, ovalization_mm=req.base.ovalization_mm,
    )
    # Robusto con solape mínimo
    overlap_factor = (req.overlap_min_mm / req.base.overlap_mm
                      if req.overlap_min_mm else 1.0)
    return TelescopicJointService.robust_check(
        base,
        overlap_factor=overlap_factor,
        friction_factor=(req.friction_min / req.base.friction_coeff if req.friction_min else 1.0),
        fy_factor=(req.fy_min_mpa / req.base.fy_mpa if req.fy_min_mpa else 1.0),
        ovalization_factor=(req.ovalization_max_mm / req.base.ovalization_mm
                            if req.ovalization_max_mm and req.base.ovalization_mm > 0 else 1.0),
    )


@router.post("/telescopic/drain", summary="Verificar drenaje telescópica")
async def check_drain(drain_ok: bool, environment: str = "C3") -> dict:
    return TelescopicJointService.check_drain(drain_ok, environment)


# ── Embridada ─────────────────────────────────────────────────────────────────

@router.post("/flanged/analyze", summary="Verificar unión embridada")
async def analyze_flanged(req: BoltGroupRequest) -> dict:
    r = FlangedJointService.distribute_bolts(
        bolt_count=req.bolt_count, bolt_pcd_mm=req.bolt_pcd_mm,
        bolt_class=req.bolt_class, bolt_diameter_mm=req.bolt_diameter_mm,
        N_kn=req.N_kn, Vy_kn=req.Vy_kn, Vz_kn=req.Vz_kn,
        My_knm=req.My_knm, Mz_knm=req.Mz_knm, T_knm=req.T_knm,
        pretensioned=req.pretensioned, target_pretension_kn=req.target_pretension_kn,
        friction_coeff=req.friction_coeff_flange,
    )
    return _check_to_response(r)


@router.post("/flanged/wrench-access", summary="Verificar acceso de llave")
async def check_wrench_access(req: FlangeAccessCheck) -> FlangeAccessResult:
    r = FlangedJointService.check_wrench_access(
        req.bolt_diameter_mm, req.wrench_size_mm, req.available_clearance_mm)
    return FlangeAccessResult(**r)


# ── Soldada ───────────────────────────────────────────────────────────────────

@router.post("/welded/analyze", summary="Verificar unión soldada")
async def analyze_welded(req: WeldedJointRequest) -> dict:
    r = WeldedJointService.static_check(
        D_ext_mm=req.D_ext_mm, t_wall_mm=req.t_wall_mm,
        N_kn=req.N_kn, My_knm=req.My_knm, Mz_knm=req.Mz_knm, T_knm=req.T_knm,
        fy_mpa=req.fy_mpa, fu_mpa=req.fu_mpa, misalignment_mm=req.misalignment_mm,
    )
    return _check_to_response(r, {"misalignment_penalty_pct": r.intermediate_values.get("misalignment_penalty_pct", 0.0)})


@router.post("/welded/fatigue", summary="Verificar fatiga cordón soldado")
async def check_weld_fatigue(
    weld_category: str, delta_sigma_mpa: float, n_cycles: int,
) -> dict:
    r = WeldedJointService.fatigue_check(weld_category, delta_sigma_mpa, n_cycles)
    return _check_to_response(r)


# ── Manguito ──────────────────────────────────────────────────────────────────

@router.post("/sleeve/analyze", summary="Verificar manguito")
async def analyze_sleeve(req: SleeveRequest) -> dict:
    r_torsion = SleeveJointService.check_torsion_transfer(
        req.length_mm, req.outer_d_mm, req.inner_d_mm, req.T_knm, req.fy_mpa)
    water = SleeveJointService.check_exterior_water(req.sleeve_type, req.exterior_water_retained)
    errors = r_torsion.error_codes[:]
    if water["blocked"]:
        errors.append(water["error_code"])
    status = JointCheckStatus.BLOCKED if water["blocked"] else r_torsion.status
    return {
        "status": status.value,
        "utilization": round(r_torsion.utilization, 4),
        "torsion_ok": r_torsion.status == JointCheckStatus.PASS,
        "water_retention_blocked": water["blocked"],
        "governing_rule": r_torsion.governing_rule,
        "error_codes": errors,
    }


# ── Híbrida ───────────────────────────────────────────────────────────────────

@router.post("/hybrid/galvanic", summary="Verificar compatibilidad galvánica")
async def check_galvanic(req: HybridInterfaceRequest) -> dict:
    r = HybridInterfaceService.check_galvanic(req.hybrid_type, req.isolator_type, req.galvanic_area_ratio)
    return _check_to_response(r)


@router.post("/hybrid/thermal", summary="Verificar tensiones térmicas")
async def check_thermal(req: HybridInterfaceRequest) -> dict:
    r = HybridInterfaceService.check_thermal(req.delta_T_k)
    return _check_to_response(r)


@router.post("/concrete/bearing", summary="Verificar aplastamiento hormigón")
async def check_concrete_bearing(req: ConcreteInterfaceRequest) -> dict:
    r = HybridInterfaceService.check_concrete_bearing(
        req.N_kn, req.bearing_area_mm2, req.fck_mpa,
        req.family_approved, req.grout_hardened,
    )
    return _check_to_response(r)


# ── Optimización ──────────────────────────────────────────────────────────────

@router.post("/optimization/pareto", summary="Optimización Pareto de uniones")
async def optimize_joints(candidates: List[JointCandidateSchema], weights: Optional[OptimizationWeights] = None) -> dict:
    pareto_cands = [
        JointParetoCandidate(
            joint_type=c.joint_type,
            template_ref=c.template_ref,
            cost_eur=c.cost_eur,
            mass_kg=c.mass_kg,
            co2_kg=c.co2_kg,
            assembly_complexity=c.assembly_complexity,
            risk_score=c.risk_score,
            logistics_score=c.logistics_score,
            durability_score=c.durability_score,
            feasible=c.feasible,
            discard_reason=c.discard_reason,
            utilization_max=c.utilization_max,
        )
        for c in candidates
    ]
    pareto = JointOptimizer.build_pareto(pareto_cands)
    solutions = JointOptimizer.select_solutions(pareto)
    w_hash = "default"
    if weights:
        import hashlib, json
        w_hash = hashlib.sha256(json.dumps(weights.model_dump(), sort_keys=True).encode()).hexdigest()[:16]

    def _ser(c):
        return None if c is None else {
            "joint_type": c.joint_type, "cost_eur": c.cost_eur,
            "mass_kg": c.mass_kg, "co2_kg": c.co2_kg,
        }

    return {
        "pareto_count": len(pareto),
        "recommended": _ser(solutions["min_cost"]),
        "min_cost": _ser(solutions["min_cost"]),
        "min_weight": _ser(solutions["min_weight"]),
        "min_co2": _ser(solutions["min_co2"]),
        "balanced": _ser(solutions["balanced"]),
        "weights_hash": w_hash,
        "discarded": [{"type": c.joint_type, "reason": c.discard_reason}
                       for c in candidates if not c.feasible and c.discard_reason],
    }


# ── Normativa ─────────────────────────────────────────────────────────────────

@router.post("/normative/classify", summary="Clasificación normativa de unión")
async def classify_joint(
    inside_domain: bool = True,
    family_tested: bool = False,
    material_compatible: bool = True,
    field_weld_requested: bool = False,
    concrete_family_approved: bool = False,
    hybrid_isolated: bool = True,
    exception_approved: bool = False,
    is_hybrid: bool = False,
    is_concrete: bool = False,
    is_telescopic: bool = True,
    demountable: bool = False,
) -> dict:
    r = JointNormativeClassifier.classify(
        inside_domain=inside_domain, family_tested=family_tested,
        material_compatible=material_compatible, field_weld_requested=field_weld_requested,
        concrete_family_approved=concrete_family_approved, hybrid_isolated=hybrid_isolated,
        exception_approved=exception_approved, is_hybrid=is_hybrid, is_concrete=is_concrete,
        is_telescopic=is_telescopic, demountable=demountable,
    )
    return {
        "joint_type": r.joint_type.value,
        "blocked": r.blocked,
        "maturity_level": r.maturity.value,
        "input_hash": r.input_hash,
        "error_codes": r.error_codes,
        "notes": r.notes,
    }


# ── Montaje ───────────────────────────────────────────────────────────────────

@router.post("/assembly/validate", summary="Validar secuencia de montaje")
async def validate_assembly(req: AssemblyValidationRequest) -> dict:
    return AssemblyService.validate_assembly(
        joint_type=req.joint_type,
        interior_access=req.interior_access,
        personnel_count=req.personnel_count,
        insertion_force_kn=req.insertion_force_kn,
        torque_nm=req.torque_nm,
    )


# ── Liberación ────────────────────────────────────────────────────────────────

@router.post("/release", summary="Solicitar liberación de ingeniería")
async def release_joint(req: JointReleaseCreate) -> dict:
    return {
        "plan_id": req.plan_id,
        "release_level": req.release_level,
        "all_checks_passed": req.all_checks_passed,
        "approved_by": req.approved_by,
        "status": "released",
    }
