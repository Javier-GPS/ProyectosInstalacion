"""
Salvi Studio · Columns — API v1: Hormigón Pretensado (Fase 7).
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.concrete_service import (
    ConcreteMaterialService,
    PrestressLossService,
    ConcreteSectionEngine,
    ConcreteVerificationService,
    ConcreteFatigueService,
    ConcreteProductionService,
    ConcreteNormativeClassifier,
    ConcreteOptimizer,
    PrestressCandidate,
)
from app.models.db.concrete import (
    PrestressingSteelClass,
)

router = APIRouter(prefix="/concrete", tags=["concrete"])


# ── Request / Response schemas (inline para simplicidad) ─────────────────────

class AgePropertiesRequest(BaseModel):
    fcm_28_mpa: float = Field(..., gt=0)
    fctm_28_mpa: float = Field(..., gt=0)
    Ecm_28_mpa: float = Field(..., gt=0)
    s_cement: float = Field(..., description="0.20, 0.25 o 0.38")
    t_days: float = Field(..., gt=0)
    epsilon_ca_inf: float = Field(50.0, gt=0)


class TransferStrengthRequest(BaseModel):
    fcm_t_mpa: float = Field(..., gt=0)
    min_required_mpa: float = Field(..., gt=0)


class AnchorSlipRequest(BaseModel):
    Ap_mm2: float = Field(..., gt=0)
    Ep_mpa: float = Field(..., gt=0)
    delta_slip_mm: float = Field(..., ge=0)
    L_active_mm: float = Field(..., gt=0)
    P0_kn: float = Field(..., gt=0)


class ElasticShorteningRequest(BaseModel):
    Ap_mm2: float = Field(..., gt=0)
    Ep_mpa: float = Field(..., gt=0)
    sigma_cp_mpa: float = Field(..., gt=0)
    Ecm_t_mpa: float = Field(..., gt=0)
    n_strands: int = Field(..., ge=1)
    P0_kn: float = Field(..., gt=0)


class RelaxationRequest(BaseModel):
    sigma_pi_mpa: float = Field(..., gt=0)
    fpk_mpa: float = Field(..., gt=0)
    relaxation_class: PrestressingSteelClass
    rho1000_pct: float = Field(..., gt=0)
    t_hours: float = Field(..., gt=0)
    Ap_mm2: float = Field(..., gt=0)
    P0_kn: float = Field(..., gt=0)


class ThermalLossRequest(BaseModel):
    Ap_mm2: float = Field(..., gt=0)
    Ep_mpa: float = Field(..., gt=0)
    alpha_T: float = Field(1e-5)
    delta_T_celsius: float
    P0_kn: float = Field(..., gt=0)


class LongTermLossRequest(BaseModel):
    Ap_mm2: float = Field(..., gt=0)
    Ep_mpa: float = Field(..., gt=0)
    Ecm_mpa: float = Field(..., gt=0)
    Ac_m2: float = Field(..., gt=0)
    Ic_m4: float = Field(..., gt=0)
    e_mm: float
    epsilon_cs: float
    delta_sigma_pr_mpa: float = Field(..., ge=0)
    phi: float = Field(..., ge=0)
    sigma_cp_mpa: float = Field(..., gt=0)
    P0_kn: float = Field(..., gt=0)


class TransferLengthRequest(BaseModel):
    phi_mm: float = Field(..., gt=0)
    sigma_pm0_mpa: float = Field(..., gt=0)
    sigma_pd_mpa: float = Field(..., gt=0)
    sigma_pm_inf_mpa: float = Field(..., ge=0)
    fctd_t_mpa: float = Field(..., gt=0)
    eta1: float = Field(1.0)
    eta2: float = Field(1.0)
    alpha1: float = Field(1.25)
    alpha2_transfer: float = Field(0.25)
    alpha2_anchor: float = Field(0.25)


class AnnularSectionRequest(BaseModel):
    D_ext_mm: float = Field(..., gt=0)
    D_int_mm: float = Field(..., gt=0)
    rho_kg_m3: float = Field(2450.0, gt=0)


class StressCheckRequest(BaseModel):
    sigma_c_mpa: float
    fck_mpa: float = Field(..., gt=0)
    stage: str
    is_tension: bool = False
    fctm_t_mpa: Optional[float] = None


class ShearCheckRequest(BaseModel):
    V_ed_kn: float = Field(..., ge=0)
    fck_mpa: float = Field(..., gt=0)
    bw_m: float = Field(..., gt=0)
    d_m: float = Field(..., gt=0)
    rho_l: float = Field(..., ge=0, le=0.02)
    N_ed_kn: float = Field(0.0)
    Ac_m2: float = Field(0.01, gt=0)


class TorsionBredtRequest(BaseModel):
    T_ed_knm: float = Field(..., ge=0)
    D_ext_mm: float = Field(..., gt=0)
    D_int_mm: float = Field(..., gt=0)
    fck_mpa: float = Field(..., gt=0)


class CrackWidthRequest(BaseModel):
    sigma_s_mpa: float = Field(..., ge=0)
    Es_mpa: float = Field(200000.0, gt=0)
    fctm_mpa: float = Field(..., gt=0)
    cover_c_mm: float = Field(..., ge=0)
    phi_bar_mm: float = Field(..., gt=0)
    rho_eff: float = Field(..., gt=0)
    wk_limit_mm: float = Field(0.2, gt=0)


class DecompressionRequest(BaseModel):
    sigma_min_mpa: float


class StrandFatigueRequest(BaseModel):
    delta_sigma_p_mpa: float = Field(..., ge=0)
    fatigue_category_mpa: float = Field(150.0, gt=0)
    gamma_s_fat: float = Field(1.15, gt=0)


class MinerBlock(BaseModel):
    delta_sigma_mpa: float
    n_cycles: float
    N_ref: float
    source: Optional[str] = None


class MinerRequest(BaseModel):
    blocks: List[MinerBlock]
    D_limit: float = Field(1.0, gt=0)


class LiftingRequest(BaseModel):
    L_m: float = Field(..., gt=0)
    n_points: int = Field(2, ge=1)
    Mcr_knm: float = Field(..., gt=0)
    w_kn_per_m: float = Field(..., gt=0)
    safety_factor: float = Field(0.85)


class StrandClearanceRequest(BaseModel):
    strand_r_mm: float = Field(..., gt=0)
    strand_phi_mm: float = Field(..., gt=0)
    insert_r_mm: float = Field(..., gt=0)
    insert_phi_mm: float = Field(..., gt=0)
    insert_theta_deg: float
    strand_theta_deg: float
    D_ext_mm: float = Field(..., gt=0)
    min_clearance_mm: float = Field(25.0, ge=0)


class SpinWindowRequest(BaseModel):
    rpm: float = Field(..., ge=0)
    min_rpm: float = Field(..., ge=0)
    max_rpm: float = Field(..., gt=0)


class NormativeRouteRequest(BaseModel):
    height_m: float = Field(..., gt=0)
    has_catenary_cables: bool = False
    mix_in_library: bool = True
    steel_in_library: bool = True
    domain_ok: bool = True
    checks_defined: bool = True
    evidence_ok: bool = True


class OptimizationRequest(BaseModel):
    candidates: List[dict] = Field(..., min_length=1)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/materials/age-properties", summary="Propiedades del hormigón por edad")
def age_properties(req: AgePropertiesRequest):
    try:
        result = ConcreteMaterialService.age_properties(
            fcm_28_mpa=req.fcm_28_mpa,
            fctm_28_mpa=req.fctm_28_mpa,
            Ecm_28_mpa=req.Ecm_28_mpa,
            s_cement=req.s_cement,
            t_days=req.t_days,
            epsilon_ca_inf=req.epsilon_ca_inf,
        )
        return {
            "t_days": result.t_days,
            "fcm_t_mpa": result.fcm_t_mpa,
            "Ecm_t_mpa": result.Ecm_t_mpa,
            "fctm_t_mpa": result.fctm_t_mpa,
            "fctk_005_t_mpa": result.fctk_005_t_mpa,
            "epsilon_ca_t": result.epsilon_ca_t,
            "governing_rule": result.governing_rule,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/materials/transfer-strength-check", summary="Verificación resistencia en transferencia")
def transfer_strength_check(req: TransferStrengthRequest):
    result = ConcreteMaterialService.check_transfer_strength(
        fcm_t_mpa=req.fcm_t_mpa,
        min_required_mpa=req.min_required_mpa,
    )
    return {
        "check_type": result.check_type,
        "status": result.status.value,
        "solicitation": result.solicitation,
        "resistance": result.resistance,
        "utilization": result.utilization,
        "governing_rule": result.governing_rule,
        "error_code": result.error_code,
    }


@router.post("/losses/anchor-slip", summary="Pérdida por asiento de anclaje")
def loss_anchor_slip(req: AnchorSlipRequest):
    try:
        r = PrestressLossService.anchor_slip_loss(
            Ap_mm2=req.Ap_mm2, Ep_mpa=req.Ep_mpa,
            delta_slip_mm=req.delta_slip_mm, L_active_mm=req.L_active_mm,
            P0_kn=req.P0_kn,
        )
        return {"loss_type": r.loss_type, "delta_P_kn": r.delta_P_kn,
                "delta_sigma_mpa": r.delta_sigma_mpa, "loss_pct": r.loss_pct,
                "governing_rule": r.governing_rule, "intermediate_values": r.intermediate_values}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/losses/elastic-shortening", summary="Pérdida por acortamiento elástico")
def loss_elastic_shortening(req: ElasticShorteningRequest):
    r = PrestressLossService.elastic_shortening_loss(
        Ap_mm2=req.Ap_mm2, Ep_mpa=req.Ep_mpa, sigma_cp_mpa=req.sigma_cp_mpa,
        Ecm_t_mpa=req.Ecm_t_mpa, n_strands=req.n_strands, P0_kn=req.P0_kn,
    )
    return {"loss_type": r.loss_type, "delta_P_kn": r.delta_P_kn,
            "delta_sigma_mpa": r.delta_sigma_mpa, "loss_pct": r.loss_pct,
            "governing_rule": r.governing_rule, "intermediate_values": r.intermediate_values}


@router.post("/losses/relaxation", summary="Relajación del acero (EC2 §3.3.2)")
def loss_relaxation(req: RelaxationRequest):
    r = PrestressLossService.relaxation_loss(
        sigma_pi_mpa=req.sigma_pi_mpa, fpk_mpa=req.fpk_mpa,
        relaxation_class=req.relaxation_class, rho1000_pct=req.rho1000_pct,
        t_hours=req.t_hours, Ap_mm2=req.Ap_mm2, P0_kn=req.P0_kn,
    )
    return {"loss_type": r.loss_type, "delta_P_kn": r.delta_P_kn,
            "delta_sigma_mpa": r.delta_sigma_mpa, "loss_pct": r.loss_pct,
            "governing_rule": r.governing_rule, "intermediate_values": r.intermediate_values}


@router.post("/losses/thermal", summary="Pérdida por diferencia térmica")
def loss_thermal(req: ThermalLossRequest):
    r = PrestressLossService.thermal_loss(
        Ap_mm2=req.Ap_mm2, Ep_mpa=req.Ep_mpa,
        alpha_T=req.alpha_T, delta_T_celsius=req.delta_T_celsius,
        P0_kn=req.P0_kn,
    )
    return {"loss_type": r.loss_type, "delta_P_kn": r.delta_P_kn,
            "delta_sigma_mpa": r.delta_sigma_mpa, "loss_pct": r.loss_pct,
            "governing_rule": r.governing_rule}


@router.post("/losses/long-term", summary="Pérdidas diferidas combinadas (EC2 §5.10.6)")
def loss_long_term(req: LongTermLossRequest):
    r = PrestressLossService.long_term_loss_simplified(
        Ap_mm2=req.Ap_mm2, Ep_mpa=req.Ep_mpa, Ecm_mpa=req.Ecm_mpa,
        Ac_m2=req.Ac_m2, Ic_m4=req.Ic_m4, e_mm=req.e_mm,
        epsilon_cs=req.epsilon_cs, delta_sigma_pr_mpa=req.delta_sigma_pr_mpa,
        phi=req.phi, sigma_cp_mpa=req.sigma_cp_mpa, P0_kn=req.P0_kn,
    )
    return {"loss_type": r.loss_type, "delta_P_kn": r.delta_P_kn,
            "delta_sigma_mpa": r.delta_sigma_mpa, "loss_pct": r.loss_pct,
            "governing_rule": r.governing_rule, "intermediate_values": r.intermediate_values}


@router.post("/losses/transfer-length", summary="Longitudes de transferencia y anclaje")
def transfer_length(req: TransferLengthRequest):
    r = PrestressLossService.transfer_length(
        phi_mm=req.phi_mm, sigma_pm0_mpa=req.sigma_pm0_mpa,
        sigma_pd_mpa=req.sigma_pd_mpa, sigma_pm_inf_mpa=req.sigma_pm_inf_mpa,
        fctd_t_mpa=req.fctd_t_mpa, eta1=req.eta1, eta2=req.eta2,
        alpha1=req.alpha1, alpha2_transfer=req.alpha2_transfer,
        alpha2_anchor=req.alpha2_anchor,
    )
    return {"fbpt_mpa": r.fbpt_mpa, "l_pt_mm": r.l_pt_mm,
            "l_bpd_mm": r.l_bpd_mm, "governing_rule": r.governing_rule}


@router.post("/sections/annular", summary="Propiedades de sección anular")
def annular_section(req: AnnularSectionRequest):
    try:
        r = ConcreteSectionEngine.annular_properties(
            D_ext_mm=req.D_ext_mm, D_int_mm=req.D_int_mm, rho_kg_m3=req.rho_kg_m3,
        )
        return {
            "D_ext_mm": r.D_ext_mm, "D_int_mm": r.D_int_mm, "t_wall_mm": r.t_wall_mm,
            "A_m2": r.A_m2, "Iy_m4": r.Iy_m4, "Iz_m4": r.Iz_m4, "J_m4": r.J_m4,
            "Wel_y_m3": r.Wel_y_m3, "Wpl_y_m3": r.Wpl_y_m3, "iy_m": r.iy_m,
            "mass_per_m_kg": r.mass_per_m_kg,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/verifications/stress", summary="Verificación de tensiones en hormigón (ELS)")
def verify_stress(req: StressCheckRequest):
    r = ConcreteSectionEngine.check_stress_concrete(
        sigma_c_mpa=req.sigma_c_mpa, fck_mpa=req.fck_mpa, stage=req.stage,
        is_tension=req.is_tension, fctm_t_mpa=req.fctm_t_mpa,
    )
    return {"check_type": r.check_type, "status": r.status.value,
            "solicitation": r.solicitation, "resistance": r.resistance,
            "utilization": r.utilization, "unit": r.unit, "governing_rule": r.governing_rule,
            "intermediate_values": r.intermediate_values}


@router.post("/verifications/shear", summary="Cortante sin armadura (EC2 §6.2.2)")
def verify_shear(req: ShearCheckRequest):
    r = ConcreteSectionEngine.check_shear(
        V_ed_kn=req.V_ed_kn, fck_mpa=req.fck_mpa, bw_m=req.bw_m, d_m=req.d_m,
        rho_l=req.rho_l, N_ed_kn=req.N_ed_kn, Ac_m2=req.Ac_m2,
    )
    return {"check_type": r.check_type, "status": r.status.value,
            "solicitation": r.solicitation, "resistance": r.resistance,
            "utilization": r.utilization, "unit": r.unit, "governing_rule": r.governing_rule,
            "intermediate_values": r.intermediate_values}


@router.post("/verifications/torsion", summary="Torsión (Bredt, EC2 §6.3)")
def verify_torsion(req: TorsionBredtRequest):
    try:
        r = ConcreteSectionEngine.check_torsion_bredt(
            T_ed_knm=req.T_ed_knm, D_ext_mm=req.D_ext_mm,
            D_int_mm=req.D_int_mm, fck_mpa=req.fck_mpa,
        )
        return {"check_type": r.check_type, "status": r.status.value,
                "solicitation": r.solicitation, "resistance": r.resistance,
                "utilization": r.utilization, "unit": r.unit, "governing_rule": r.governing_rule,
                "intermediate_values": r.intermediate_values}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/verifications/crack-width", summary="Ancho de fisura (EC2 §7.3.4)")
def verify_crack_width(req: CrackWidthRequest):
    r = ConcreteVerificationService.check_crack_width(
        sigma_s_mpa=req.sigma_s_mpa, Es_mpa=req.Es_mpa, fctm_mpa=req.fctm_mpa,
        cover_c_mm=req.cover_c_mm, phi_bar_mm=req.phi_bar_mm, rho_eff=req.rho_eff,
        wk_limit_mm=req.wk_limit_mm,
    )
    return {"check_type": r.check_type, "status": r.status.value,
            "solicitation": r.solicitation, "resistance": r.resistance,
            "utilization": r.utilization, "unit": r.unit, "governing_rule": r.governing_rule}


@router.post("/verifications/decompression", summary="Verificación de descompresión")
def verify_decompression(req: DecompressionRequest):
    r = ConcreteVerificationService.check_decompression(sigma_min_mpa=req.sigma_min_mpa)
    return {"check_type": r.check_type, "status": r.status.value,
            "solicitation": r.solicitation, "resistance": r.resistance,
            "utilization": r.utilization, "governing_rule": r.governing_rule}


@router.post("/fatigue/strand", summary="Fatiga de cordón (EC2 §6.8.4)")
def fatigue_strand(req: StrandFatigueRequest):
    r = ConcreteFatigueService.strand_fatigue_check(
        delta_sigma_p_mpa=req.delta_sigma_p_mpa,
        fatigue_category_mpa=req.fatigue_category_mpa,
        gamma_s_fat=req.gamma_s_fat,
    )
    return {"check_type": r.check_type, "status": r.status.value,
            "solicitation": r.solicitation, "resistance": r.resistance,
            "utilization": r.utilization, "unit": r.unit, "governing_rule": r.governing_rule}


@router.post("/fatigue/miner", summary="Daño acumulado Palmgren-Miner")
def fatigue_miner(req: MinerRequest):
    blocks = [b.model_dump() for b in req.blocks]
    r = ConcreteFatigueService.miner_damage(blocks=blocks, D_limit=req.D_limit)
    return {"total_damage": r.total_damage, "individual_damages": r.individual_damages,
            "status": r.status, "duplicate_source_detected": r.duplicate_source_detected,
            "governing_source": r.governing_source, "governing_rule": r.governing_rule}


@router.post("/production/lifting", summary="Verificación de puntos de izado")
def production_lifting(req: LiftingRequest):
    r = ConcreteProductionService.check_lifting_positions(
        L_m=req.L_m, n_points=req.n_points, Mcr_knm=req.Mcr_knm,
        w_kn_per_m=req.w_kn_per_m, safety_factor=req.safety_factor,
    )
    return {"point_positions_m": r.point_positions_m, "M_max_knm": r.M_max_knm,
            "utilization_vs_Mcr": r.utilization_vs_Mcr, "compliant": r.compliant,
            "governing_rule": r.governing_rule}


@router.post("/production/strand-clearance", summary="Distancia mínima cordón-inserto")
def production_strand_clearance(req: StrandClearanceRequest):
    r = ConcreteProductionService.check_strand_clearance(
        strand_r_mm=req.strand_r_mm, strand_phi_mm=req.strand_phi_mm,
        insert_r_mm=req.insert_r_mm, insert_phi_mm=req.insert_phi_mm,
        insert_theta_deg=req.insert_theta_deg, strand_theta_deg=req.strand_theta_deg,
        D_ext_mm=req.D_ext_mm, min_clearance_mm=req.min_clearance_mm,
    )
    return {"check_type": r.check_type, "status": r.status.value,
            "solicitation": r.solicitation, "resistance": r.resistance,
            "utilization": r.utilization, "unit": r.unit, "governing_rule": r.governing_rule,
            "error_code": r.error_code}


@router.post("/production/spin-window", summary="Verificación ventana de centrifugado")
def production_spin_window(req: SpinWindowRequest):
    r = ConcreteProductionService.check_spin_within_window(
        rpm=req.rpm, min_rpm=req.min_rpm, max_rpm=req.max_rpm,
    )
    return {"check_type": r.check_type, "status": r.status.value,
            "solicitation": r.solicitation, "resistance": r.resistance,
            "utilization": r.utilization, "unit": r.unit, "governing_rule": r.governing_rule,
            "error_code": r.error_code}


@router.post("/normative/classify", summary="Clasificador normativo (7 pasos)")
def normative_classify(req: NormativeRouteRequest):
    r = ConcreteNormativeClassifier.classify(
        height_m=req.height_m,
        has_catenary_cables=req.has_catenary_cables,
        mix_in_library=req.mix_in_library,
        steel_in_library=req.steel_in_library,
        domain_ok=req.domain_ok,
        checks_defined=req.checks_defined,
        evidence_ok=req.evidence_ok,
    )
    return {
        "route": r.route.value,
        "steps_passed": r.steps_passed,
        "blocking_step": r.blocking_step,
        "decision_trace": r.decision_trace,
        "input_hash": r.input_hash,
    }


@router.post("/optimization/pareto", summary="Optimización Pareto del pretensado")
def optimization_pareto(req: OptimizationRequest):
    candidates = []
    for d in req.candidates:
        try:
            c = PrestressCandidate(
                n_strands=d.get("n_strands", 1),
                strand_diameter_mm=d.get("strand_diameter_mm", 12.5),
                crown_radius_mm=d.get("crown_radius_mm", 100.0),
                initial_force_per_strand_kn=d.get("initial_force_per_strand_kn", 100.0),
                total_cost_eur=d.get("total_cost_eur", 0.0),
                total_mass_kg=d.get("total_mass_kg", 0.0),
                total_co2_kg=d.get("total_co2_kg", 0.0),
                robustness_score=d.get("robustness_score", 0.0),
                feasible=d.get("feasible", True),
                transportable=d.get("transportable", True),
            )
            candidates.append(c)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Candidato inválido: {e}")

    pareto = ConcreteOptimizer.build_pareto_front(candidates)
    solutions = ConcreteOptimizer.select_solutions(pareto)

    def _ser(c: Optional[PrestressCandidate]):
        if c is None:
            return None
        return {
            "n_strands": c.n_strands,
            "strand_diameter_mm": c.strand_diameter_mm,
            "crown_radius_mm": c.crown_radius_mm,
            "initial_force_per_strand_kn": c.initial_force_per_strand_kn,
            "total_cost_eur": c.total_cost_eur,
            "total_mass_kg": c.total_mass_kg,
            "total_co2_kg": c.total_co2_kg,
            "robustness_score": c.robustness_score,
        }

    return {
        "pareto_size": len(pareto),
        "min_cost": _ser(solutions["min_cost"]),
        "min_weight": _ser(solutions["min_weight"]),
        "min_co2": _ser(solutions["min_co2"]),
        "balanced": _ser(solutions["balanced"]),
    }
