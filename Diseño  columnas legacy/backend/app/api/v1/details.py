"""
Salvi Studio · Columns — API v1: Detalles Locales (Fase 8).
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.details_service import (
    OpeningService, LocalSectionService, DetailCheckService,
    WeldService, SupportConfigurator, LocalFEAService,
    ReinforcementOptimizer, ReinfCandidate, DetailNormativeClassifier,
)
from app.models.db.details import (
    OpeningType, DetailRoute, ReinforcementFamily, WeldProcess,
    DetailCheckStatus, FEAStatus, DetailReleaseLevel,
)

router = APIRouter(prefix="/details", tags=["details"])


# ── Request schemas ────────────────────────────────────────────────────────────

class OpeningValidateRequest(BaseModel):
    D_ext_mm: float = Field(..., gt=0.0)
    t_wall_mm: float = Field(..., gt=0.0)
    width_mm: float = Field(..., gt=0.0)
    height_mm: float = Field(..., gt=0.0)
    corner_radius_mm: float = Field(0.0, ge=0.0)
    orientation_deg: float = Field(0.0, ge=0.0, lt=360.0)
    station_bottom_m: float = Field(..., ge=0.0)
    station_top_m: float = Field(..., gt=0.0)
    height_total_m: float = Field(..., gt=0.0)
    opening_type: OpeningType = OpeningType.RECTANGULAR_ROUNDED
    nearby_joint_m: Optional[float] = None
    nearby_openings: Optional[List[dict]] = None


class SectionComputeRequest(BaseModel):
    D_ext_mm: float = Field(..., gt=0.0)
    t_wall_mm: float = Field(..., gt=0.0)
    width_mm: float = Field(..., gt=0.0)
    height_mm: float = Field(..., gt=0.0)
    corner_radius_mm: float = Field(0.0, ge=0.0)
    orientation_deg: float = Field(0.0, ge=0.0, lt=360.0)
    contrast_tolerance_pct: float = Field(0.5, gt=0.0)


class NetStressCheckRequest(BaseModel):
    sigma_nom_mpa: float
    fy_mpa: float = Field(..., gt=0.0)
    gamma_M0: float = Field(1.0, gt=0.0)


class LigamentCheckRequest(BaseModel):
    b_free_mm: float = Field(..., gt=0.0)
    t_mm: float = Field(..., gt=0.0)
    fy_mpa: float = Field(..., gt=0.0)
    E_mpa: float = Field(210000.0, gt=0.0)


class PanelBucklingRequest(BaseModel):
    a_mm: float = Field(..., gt=0.0)
    b_mm: float = Field(..., gt=0.0)
    t_mm: float = Field(..., gt=0.0)
    E_mpa: float = Field(210000.0, gt=0.0)
    nu: float = Field(0.3)
    sigma_applied_mpa: float = Field(0.0)
    fy_mpa: float = Field(355.0, gt=0.0)


class VMInteractionRequest(BaseModel):
    sigma_nom_mpa: float
    tau_mpa: float = Field(..., ge=0.0)
    fy_mpa: float = Field(..., gt=0.0)


class FatigueHotspotRequest(BaseModel):
    sigma_hotspot_mpa: float = Field(..., ge=0.0)
    delta_sigma_Rsk_mpa: float = Field(71.0, gt=0.0)
    gamma_Ff: float = Field(1.0, gt=0.0)
    gamma_Mf: float = Field(1.15, gt=0.0)


class WeldGroupSegment(BaseModel):
    x1_mm: float; y1_mm: float; x2_mm: float; y2_mm: float; throat_mm: float = Field(..., gt=0.0)


class WeldGroupRequest(BaseModel):
    segments: List[WeldGroupSegment] = Field(..., min_length=1)
    weld_process: WeldProcess
    fu_mpa: float = Field(..., gt=0.0)
    gamma_M2: float = Field(1.25, gt=0.0)
    beta_w: float = Field(0.8, gt=0.0)
    haz_factor: float = Field(1.0, gt=0.0)
    Fx_kn: float = Field(0.0)
    Fy_kn: float = Field(0.0)
    M_knm: float = Field(0.0)


class HAZCheckRequest(BaseModel):
    sigma_nom_mpa: float
    f0_mpa: float = Field(..., gt=0.0)
    haz_factor: float = Field(..., gt=0.0, le=1.0)
    gamma_M1: float = Field(1.1, gt=0.0)


class PulloutRequest(BaseModel):
    F_applied_kn: float = Field(..., ge=0.0)
    thread_diameter_mm: float = Field(..., gt=0.0)
    embedded_length_mm: float = Field(..., gt=0.0)
    fu_bolt_mpa: float = Field(..., gt=0.0)
    fu_plate_mpa: float = Field(..., gt=0.0)
    gamma_M2: float = Field(1.25, gt=0.0)


class EquipmentItem(BaseModel):
    reference: Optional[str] = None
    length_mm: float = Field(..., gt=0.0)
    width_mm: float = Field(..., gt=0.0)
    height_mm: float = Field(..., gt=0.0)
    mass_kg: float = Field(..., gt=0.0)


class AccessibilityRequest(BaseModel):
    opening_width_mm: float = Field(..., gt=0.0)
    opening_height_mm: float = Field(..., gt=0.0)
    equipment_list: List[EquipmentItem]
    D_int_mm: float = Field(..., gt=0.0)
    tool_clearance_required_mm: float = Field(50.0, ge=0.0)
    cable_radius_min_mm: float = Field(25.0, ge=0.0)
    available_clearance_mm: float = Field(100.0, ge=0.0)


class FEAActivationRequest(BaseModel):
    multiple_openings_close: bool = False
    outside_formula_domain: bool = False
    high_torsion: bool = False
    complex_open_section: bool = False
    discontinuous_reinforcement: bool = False
    near_joint: bool = False
    analytic_utilization: float = Field(0.0, ge=0.0)
    new_detail_no_test: bool = False


class FEAValidateRequest(BaseModel):
    convergence_ratio: float = Field(..., ge=0.0)
    equilibrium_residual_pct: float = Field(..., ge=0.0)
    max_stress_mpa: float = Field(..., ge=0.0)
    buckling_factor: float = Field(1.0, ge=0.0)
    analytic_ref_stress_mpa: float = Field(..., ge=0.0)


class ReinforcementCandidateInput(BaseModel):
    family: ReinforcementFamily
    material_code: str
    thickness_mm: float = Field(..., gt=0.0)
    width_mm: Optional[float] = None
    cost_eur: float = Field(..., ge=0.0)
    mass_kg: float = Field(..., ge=0.0)
    co2_kg: float = Field(..., ge=0.0)
    feasible: bool = True


class ReinforcementOptRequest(BaseModel):
    candidates: List[ReinforcementCandidateInput] = Field(..., min_length=1)


class NormativeClassifyRequest(BaseModel):
    entry_complete: bool = True
    has_tested_family: bool = False
    within_analytic_domain: bool = True
    complex_geometry: bool = False
    has_evidence: bool = True
    new_detail: bool = False
    high_torsion: bool = False


class DrainageCheckRequest(BaseModel):
    has_drain_opening: bool
    drainage_area_mm2: float = Field(0.0, ge=0.0)


class ClosedCavityRequest(BaseModel):
    has_closed_cavity: bool
    material: str = "STEEL"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _check_result_dict(r):
    return {
        "check_type": r.check_type,
        "status": r.status.value,
        "demand": r.demand,
        "resistance": r.resistance,
        "utilization": r.utilization,
        "unit": r.unit,
        "governing_rule": r.governing_rule,
        "error_code": r.error_code,
        "intermediate_values": r.intermediate_values,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/openings/validate", summary="Validar geometría de hueco y ruta normativa")
def validate_opening(req: OpeningValidateRequest):
    try:
        r = OpeningService.validate_geometry(
            D_ext_mm=req.D_ext_mm, t_wall_mm=req.t_wall_mm,
            width_mm=req.width_mm, height_mm=req.height_mm,
            corner_radius_mm=req.corner_radius_mm, orientation_deg=req.orientation_deg,
            station_bottom_m=req.station_bottom_m, station_top_m=req.station_top_m,
            height_total_m=req.height_total_m, opening_type=req.opening_type,
            nearby_joint_m=req.nearby_joint_m, nearby_openings=req.nearby_openings,
        )
        return {
            "route": r.route.value,
            "status": r.status.value,
            "blocking_step": r.blocking_step,
            "decision_trace": r.decision_trace,
            "geometric_hash": r.geometric_hash,
            "errors": r.errors,
            "warnings": r.warnings,
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/sections/compute", summary="Calcular sección neta y compuesta")
def compute_section(req: SectionComputeRequest):
    try:
        r = LocalSectionService.net_section(
            D_ext_mm=req.D_ext_mm, t_wall_mm=req.t_wall_mm,
            width_mm=req.width_mm, height_mm=req.height_mm,
            corner_radius_mm=req.corner_radius_mm, orientation_deg=req.orientation_deg,
            contrast_tolerance_pct=req.contrast_tolerance_pct,
        )
        return {
            "A_gross_m2": r.A_gross_m2, "A_net_m2": r.A_net_m2,
            "A_reduction_pct": r.A_reduction_pct,
            "centroid_x_m": r.centroid_x_m, "centroid_y_m": r.centroid_y_m,
            "Iy_net_m4": r.Iy_net_m4, "Iz_net_m4": r.Iz_net_m4,
            "Iyz_net_m4": r.Iyz_net_m4, "J_net_m4": r.J_net_m4,
            "alpha_principal_deg": r.alpha_principal_deg,
            "I1_m4": r.I1_m4, "I2_m4": r.I2_m4,
            "Wel_y_m3": r.Wel_y_m3, "Wel_z_m3": r.Wel_z_m3,
            "contrast_delta_pct": r.contrast_delta_pct,
            "contrast_passed": r.contrast_passed,
            "governing_rule": r.governing_rule,
            "method": r.method,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/checks/net-stress", summary="Tensión nominal en sección neta")
def check_net_stress(req: NetStressCheckRequest):
    return _check_result_dict(DetailCheckService.check_net_section_stress(
        sigma_nom_mpa=req.sigma_nom_mpa, fy_mpa=req.fy_mpa, gamma_M0=req.gamma_M0))


@router.post("/checks/ligament", summary="Esbeltez de ligamento lateral")
def check_ligament(req: LigamentCheckRequest):
    return _check_result_dict(DetailCheckService.check_ligament_slenderness(
        b_free_mm=req.b_free_mm, t_mm=req.t_mm, fy_mpa=req.fy_mpa, E_mpa=req.E_mpa))


@router.post("/checks/panel-buckling", summary="Pandeo de panel plano")
def check_panel_buckling(req: PanelBucklingRequest):
    return _check_result_dict(DetailCheckService.check_panel_buckling(
        a_mm=req.a_mm, b_mm=req.b_mm, t_mm=req.t_mm, E_mpa=req.E_mpa,
        nu=req.nu, sigma_applied_mpa=req.sigma_applied_mpa, fy_mpa=req.fy_mpa))


@router.post("/checks/interaction-vm", summary="Interacción Von Mises (normal + cortante)")
def check_vm(req: VMInteractionRequest):
    return _check_result_dict(DetailCheckService.check_combined_interaction(
        sigma_nom_mpa=req.sigma_nom_mpa, tau_mpa=req.tau_mpa, fy_mpa=req.fy_mpa))


@router.post("/checks/fatigue-hotspot", summary="Fatiga por hot-spot")
def check_fatigue_hotspot(req: FatigueHotspotRequest):
    return _check_result_dict(DetailCheckService.check_fatigue_hotspot(
        sigma_hotspot_mpa=req.sigma_hotspot_mpa,
        delta_sigma_Rsk_mpa=req.delta_sigma_Rsk_mpa,
        gamma_Ff=req.gamma_Ff, gamma_Mf=req.gamma_Mf))


@router.post("/welds/group", summary="Distribución elástica de grupo de soldaduras")
def weld_group(req: WeldGroupRequest):
    try:
        segs = [{"x1_mm": s.x1_mm, "y1_mm": s.y1_mm,
                 "x2_mm": s.x2_mm, "y2_mm": s.y2_mm,
                 "throat_mm": s.throat_mm} for s in req.segments]
        r = WeldService.compute_weld_group(
            segments=segs, fu_mpa=req.fu_mpa, Fx_kn=req.Fx_kn, Fy_kn=req.Fy_kn,
            M_knm=req.M_knm, gamma_M2=req.gamma_M2, beta_w=req.beta_w,
            haz_factor=req.haz_factor,
        )
        return {
            "total_length_mm": r.total_length_mm,
            "centroid_x_mm": r.centroid_x_mm, "centroid_y_mm": r.centroid_y_mm,
            "Ip_polar_mm4": r.Ip_polar_mm4,
            "f_res_max_n_mm": r.f_res_max_n_mm, "capacity_n_mm": r.capacity_n_mm,
            "utilization": r.utilization, "status": r.status.value,
            "governing_rule": r.governing_rule,
            "intermediate_values": r.intermediate_values,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/welds/haz", summary="Resistencia reducida en HAZ de aluminio")
def weld_haz(req: HAZCheckRequest):
    return _check_result_dict(WeldService.check_haz_reduction(
        sigma_nom_mpa=req.sigma_nom_mpa, f0_mpa=req.f0_mpa,
        haz_factor=req.haz_factor, gamma_M1=req.gamma_M1))


@router.post("/welds/pullout", summary="Arrancamiento de inserto atornillado")
def weld_pullout(req: PulloutRequest):
    return _check_result_dict(WeldService.check_pullout(
        F_applied_kn=req.F_applied_kn, thread_diameter_mm=req.thread_diameter_mm,
        embedded_length_mm=req.embedded_length_mm, fu_bolt_mpa=req.fu_bolt_mpa,
        fu_plate_mpa=req.fu_plate_mpa, gamma_M2=req.gamma_M2))


@router.post("/supports/accessibility", summary="Accesibilidad y extracción de equipos")
def support_accessibility(req: AccessibilityRequest):
    equip = [e.model_dump() for e in req.equipment_list]
    r = SupportConfigurator.check_equipment_fits(
        opening_width_mm=req.opening_width_mm,
        opening_height_mm=req.opening_height_mm,
        equipment_list=equip,
        D_int_mm=req.D_int_mm,
    )
    tool = SupportConfigurator.check_tool_clearance(req.available_clearance_mm, req.tool_clearance_required_mm)
    cable = SupportConfigurator.check_cable_radius(req.available_clearance_mm, req.cable_radius_min_mm)
    return {
        "accessible": r.accessible,
        "tool_clearance_ok": tool.status.value == "PASS",
        "cable_radius_ok": cable.status.value == "PASS",
        "all_equipment_fit": r.all_equipment_fit,
        "extraction_sequence": r.extraction_sequence,
        "blocking_equipment": r.blocking_equipment,
        "error_code": r.error_code,
        "governing_rule": r.governing_rule,
    }


@router.post("/supports/drainage", summary="Verificación de drenaje y ventilación")
def support_drainage(req: DrainageCheckRequest):
    return _check_result_dict(SupportConfigurator.check_drainage(
        has_drain_opening=req.has_drain_opening, drainage_area_mm2=req.drainage_area_mm2))


@router.post("/supports/closed-cavity", summary="Detección de cavidad cerrada (galvanizado)")
def support_closed_cavity(req: ClosedCavityRequest):
    return _check_result_dict(SupportConfigurator.check_closed_cavity(
        has_closed_cavity=req.has_closed_cavity, material=req.material))


@router.post("/fea/activation", summary="Determinar si el FEM local es obligatorio")
def fea_activation(req: FEAActivationRequest):
    r = LocalFEAService.should_activate_fea(
        multiple_openings_close=req.multiple_openings_close,
        outside_formula_domain=req.outside_formula_domain,
        high_torsion=req.high_torsion,
        complex_open_section=req.complex_open_section,
        discontinuous_reinforcement=req.discontinuous_reinforcement,
        near_joint=req.near_joint,
        analytic_utilization=req.analytic_utilization,
        new_detail_no_test=req.new_detail_no_test,
    )
    return {
        "fea_required": r.fea_required,
        "activation_reasons": r.activation_reasons,
        "route": r.route.value,
    }


@router.post("/fea/validate", summary="Validar modelo FEM local (convergencia, equilibrio)")
def fea_validate(req: FEAValidateRequest):
    r = LocalFEAService.validate_fea_model(
        convergence_ratio=req.convergence_ratio,
        equilibrium_residual_pct=req.equilibrium_residual_pct,
        max_stress_mpa=req.max_stress_mpa,
        buckling_factor=req.buckling_factor,
        analytic_ref_stress_mpa=req.analytic_ref_stress_mpa,
    )
    return r


@router.post("/reinforcements/optimize", summary="Optimización Pareto de familias de refuerzo")
def reinf_optimize(req: ReinforcementOptRequest):
    candidates = [
        ReinfCandidate(
            family=c.family, material_code=c.material_code,
            thickness_mm=c.thickness_mm, width_mm=c.width_mm,
            cost_eur=c.cost_eur, mass_kg=c.mass_kg, co2_kg=c.co2_kg,
            feasible=c.feasible,
        )
        for c in req.candidates
    ]
    pareto = ReinforcementOptimizer.build_pareto(candidates)
    sols = ReinforcementOptimizer.select_solutions(pareto)

    def _ser(c):
        if c is None:
            return None
        return {
            "family": c.family.value, "material_code": c.material_code,
            "thickness_mm": c.thickness_mm, "width_mm": c.width_mm,
            "cost_eur": c.cost_eur, "mass_kg": c.mass_kg, "co2_kg": c.co2_kg,
        }

    return {
        "pareto_size": len(pareto),
        "min_cost": _ser(sols["min_cost"]),
        "min_weight": _ser(sols["min_weight"]),
        "min_co2": _ser(sols["min_co2"]),
        "balanced": _ser(sols["balanced"]),
    }


@router.post("/normative/classify", summary="Clasificador normativo de ruta (R8-A..E)")
def normative_classify(req: NormativeClassifyRequest):
    r = DetailNormativeClassifier.classify(
        entry_complete=req.entry_complete,
        has_tested_family=req.has_tested_family,
        within_analytic_domain=req.within_analytic_domain,
        complex_geometry=req.complex_geometry,
        has_evidence=req.has_evidence,
        new_detail=req.new_detail,
        high_torsion=req.high_torsion,
    )
    return {
        "route": r.route.value,
        "steps_passed": r.steps_passed,
        "blocking_step": r.blocking_step,
        "decision_trace": r.decision_trace,
        "input_hash": r.input_hash,
    }
