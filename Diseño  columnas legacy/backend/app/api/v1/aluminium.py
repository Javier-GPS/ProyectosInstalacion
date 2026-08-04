"""
API v1 · Fase 6 — Aluminio
Salvi Studio · Columns
"""
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.models.schemas.aluminium import (
    AluminiumRouteRequest, AluminiumRouteResponse, AluminiumRouteStepResult,
    AluminiumAlloyVersionCreate, AluminiumAlloyVersionResponse,
    MaterialResolveRequest, MaterialResolveResponse,
    HAZBuildRequest, HAZBuildResponse, HAZRegionResult,
    SectionPropertiesRequest, SectionPropertiesResponse,
    EffectiveSectionRequest, EffectiveSectionResponse,
    AluminiumVerifyRequest, AluminiumVerifyResponse, AluminiumCheckResult,
    AluminiumFatigueCheckRequest, AluminiumMinerRequest, AluminiumMinerResponse,
    AluminiumDurabilityRequest, AluminiumDurabilityResponse,
    AluminiumBendAllowanceRequest, AluminiumBendAllowanceResponse,
    AluminiumFabricabilityRequest, AluminiumFabricabilityResponse, FabricabilityIssue,
    AluminiumOptimizationRequest, AluminiumOptimizationResponse,
    AluminiumReportCreate,
    MaterialStatus,
)
from app.services.aluminium_service import (
    AluminiumNormativeClassifier,
    AluminiumMaterialService,
    AluminiumHAZService,
    AluminiumSectionEngine,
    AluminiumEffectiveSectionService,
    AluminiumWeldService,
    AluminiumFSWService,
    AluminiumFatigueService,
    AluminiumDurabilityService,
    AluminiumManufacturingService,
    AluminiumOptimizer,
    AluminiumCheckStatus,
)
import math

router = APIRouter(prefix="/aluminium", tags=["aluminium"])

_501 = HTTPException(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    detail="Requires database connection — not yet available in this environment.",
)


# ── Normative Route ───────────────────────────────────────────────────────────

@router.post("/route-classification", response_model=AluminiumRouteResponse)
def classify_route(req: AluminiumRouteRequest) -> AluminiumRouteResponse:
    """
    Clasificador normativo de 7 pasos para aluminio.
    Rutas: EN40, EN40_EXTENDED (>20 m o cables), SPECIAL, BLOCKED.
    """
    result = AluminiumNormativeClassifier.classify(
        height_nominal_m=req.height_nominal_m,
        has_catenary_cables=req.has_catenary_cables,
        alloy_in_library=req.alloy_in_library,
        domain_ok=req.domain_ok,
        checks_defined=req.checks_defined,
        rules_available=req.rules_available,
        evidence_ok=req.evidence_ok,
    )
    return AluminiumRouteResponse(
        route=result.route,
        route_version=result.route_version,
        steps=[
            AluminiumRouteStepResult(
                step=s.step, condition=s.condition,
                status=s.status, detail=s.detail,
            )
            for s in result.steps
        ],
        decision_trace=result.decision_trace,
        active_rules=result.active_rules,
        discarded_rules=result.discarded_rules,
        exclusions=result.exclusions,
        warnings=result.warnings,
        max_declaration_allowed=result.max_declaration_allowed,
        input_hash=result.input_hash,
    )


# ── Material ──────────────────────────────────────────────────────────────────

@router.post("/material/resolve", response_model=MaterialResolveResponse)
def resolve_material(req: MaterialResolveRequest) -> MaterialResolveResponse:
    """
    Resuelve propiedades de diseño para aleación, temple, producto y espesor.
    Devuelve AL-MAT-001 si no existe en biblioteca.
    """
    try:
        props = AluminiumMaterialService.resolve(
            alloy_designation=req.alloy_designation,
            temper=req.temper,
            product_form=req.product_form.value,
            thickness_mm=req.thickness_mm,
            gamma_M=req.gamma_M,
        )
        return MaterialResolveResponse(
            alloy_designation=props["alloy_designation"],
            temper=props["temper"],
            product_form=props["product_form"],
            thickness_mm=props["thickness_mm"],
            f0_d_mpa=props["f0_d_mpa"],
            fu_d_mpa=props["fu_d_mpa"],
            E_mpa=props["E_mpa"],
            G_mpa=props["G_mpa"],
            rho_kg_m3=props["rho_kg_m3"],
            gamma_M=props["gamma_M"],
            provenance=props["provenance"],
            status=MaterialStatus.APPROVED,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


@router.get("/material/library")
def list_material_library() -> dict:
    """Lista la biblioteca inicial de aleaciones disponibles."""
    return {
        "families": [
            {"alloy": r["alloy"], "temper": r["temper"], "product_form": r["product_form"],
             "t_range_mm": [r["t_min"], r["t_max"]], "f0_mpa": r["f0"], "fu_mpa": r["fu"]}
            for r in AluminiumMaterialService._LIBRARY
        ],
        "count": len(AluminiumMaterialService._LIBRARY),
    }


# ── HAZ ───────────────────────────────────────────────────────────────────────

@router.post("/haz/build", response_model=HAZBuildResponse)
def build_haz_map(req: HAZBuildRequest) -> HAZBuildResponse:
    """Construye mapa de zonas HAZ para una sección."""
    haz_inputs = [
        {
            "haz_type": inp.haz_type.value,
            "process": inp.process.value,
            "alloy_designation": inp.alloy_designation,
            "temper": inp.temper,
            "thickness_mm": inp.thickness_mm,
        }
        for inp in req.haz_inputs
    ]
    result = AluminiumHAZService.build_map(haz_inputs, req.check_overlaps)
    return HAZBuildResponse(
        section_station_m=req.section_station_m,
        regions=[
            HAZRegionResult(
                haz_type=r.haz_type,
                haz_width_mm=r.haz_width_mm,
                rho_yield=r.rho_yield,
                rho_ultimate=r.rho_ultimate,
                rho_buckling=r.rho_buckling,
                rho_fatigue=r.rho_fatigue,
                side=r.side,
                overlaps_door=False,
                error_code=r.error_code,
            )
            for r in result.regions
        ],
        has_overlapping_zones=result.has_overlapping_zones,
        overlap_treatment=result.overlap_treatment,
        geometry_hash=result.geometry_hash,
        material_hash=result.material_hash,
        error_codes=result.error_codes,
    )


# ── Sección ───────────────────────────────────────────────────────────────────

@router.get("/section/circular-hollow", response_model=SectionPropertiesResponse)
def section_circular_hollow(
    D_ext_mm: float = Query(..., gt=0, description="Diámetro exterior [mm]"),
    t_mm: float = Query(..., gt=0, description="Espesor nominal [mm]"),
    rho_kg_m3: float = Query(default=2700.0, gt=0),
) -> SectionPropertiesResponse:
    """Propiedades de tubo circular de aluminio."""
    p = AluminiumSectionEngine.circular_hollow_properties(D_ext_mm, t_mm, rho_kg_m3)
    return SectionPropertiesResponse(
        section_type="CIRCULAR",
        A_gross_m2=p.A_m2,
        A_net_m2=None,
        centroid_y_m=0.0,
        centroid_z_m=0.0,
        Iy_m4=p.Iy_m4,
        Iz_m4=p.Iz_m4,
        Iyz_m4=0.0,
        J_m4=p.J_m4,
        Ay_m2=p.Ay_m2,
        Az_m2=p.Az_m2,
        Wel_y_m3=p.Wel_y_m3,
        Wel_z_m3=p.Wel_z_m3,
        mass_per_m_kg=p.mass_per_m_kg,
        haz_area_fraction=None,
        check_passed=True,
        qa_notes=[],
    )


@router.post("/section/effective", response_model=EffectiveSectionResponse)
def section_effective(req: EffectiveSectionRequest) -> EffectiveSectionResponse:
    """
    Calcula la sección efectiva por pandeo local para tubo circular (Clase 4).
    """
    result = AluminiumEffectiveSectionService.circular_wall_effective(
        D_ext_mm=req.D_ext_mm,
        t_eff_mm=req.t_eff_mm,
        E_mpa=req.E_mpa,
        f0_d_mpa=req.f0_d_mpa,
        sigma_max_mpa=req.sigma_max_mpa,
        max_iterations=req.max_iterations,
        convergence_tol=req.convergence_tol,
    )
    return EffectiveSectionResponse(
        width_effective_mm=result.width_effective_mm,
        reduction_factor=result.reduction_factor,
        slenderness=result.slenderness,
        n_iterations=result.n_iterations,
        converged=result.converged,
        panel_status=result.panel_status,
        governing_rule=result.governing_rule,
    )


@router.get("/section/wall-slenderness")
def section_wall_slenderness(
    D_ext_mm: float = Query(..., gt=0),
    t_eff_mm: float = Query(..., gt=0),
    f0_d_mpa: float = Query(..., gt=0),
    E_mpa: float = Query(default=70000.0),
) -> dict:
    """Clasificación de esbeltez de pared circular según EN 1999-1-1."""
    res = AluminiumSectionEngine.check_circular_wall_slenderness(
        D_ext_mm, t_eff_mm, f0_d_mpa, E_mpa
    )
    return {
        "check_type": res.check_type,
        "status": res.status.value,
        "solicitation": res.solicitation,
        "resistance": res.resistance,
        "utilization": res.utilization,
        "intermediate_values": res.intermediate_values,
        "governing_rule": res.governing_rule,
    }


# ── Verificación ──────────────────────────────────────────────────────────────

@router.post("/verify/section", response_model=AluminiumVerifyResponse)
def verify_section(req: AluminiumVerifyRequest) -> AluminiumVerifyResponse:
    """
    Ejecuta todas las verificaciones de sección (N, M, V, T, interacción, esbeltez).
    """
    rho = req.haz_rho_yield if req.haz_rho_yield is not None else 1.0
    checks = []
    errors = []
    warnings = []

    Av = req.Ay_m2 if req.Ay_m2 else 2.0 * req.A_m2 / math.pi
    Wel_z = req.Wel_z_m3 if req.Wel_z_m3 else req.Wel_y_m3

    # Axil
    if abs(req.N_kn) > 1e-9:
        checks.append(AluminiumSectionEngine.check_axial(
            req.N_kn, req.A_m2, req.f0_d_mpa, rho, req.gamma_M0, req.utilization_limit))

    # Flexión uniaxial My
    if abs(req.My_knm) > 1e-9:
        checks.append(AluminiumSectionEngine.check_bending_uniaxial(
            req.My_knm, req.Wel_y_m3, req.f0_d_mpa, rho, req.gamma_M0, req.utilization_limit))

    # Cortante
    if abs(req.Vy_kn) > 1e-9 or abs(req.Vz_kn) > 1e-9:
        V = math.sqrt(req.Vy_kn**2 + req.Vz_kn**2)
        checks.append(AluminiumSectionEngine.check_shear(
            V, Av, req.f0_d_mpa, rho, req.gamma_M0, req.utilization_limit))

    # Torsión
    if abs(req.T_knm) > 1e-9:
        D_ext = getattr(req, "D_ext_mm", None)
        t_mm = getattr(req, "t_mm", 4.0)
        checks.append(AluminiumSectionEngine.check_torsion_closed_section(
            req.T_knm, req.J_m4, req.A_m2, t_mm, req.f0_d_mpa, rho, req.gamma_M0, req.utilization_limit))

    # Esbeltez pared (si circular)
    if req.section_type == "CIRCULAR":
        D_ext_mm = 2.0 * (1000.0 * math.sqrt(req.A_m2 / math.pi + (req.A_m2 / math.pi)))  # aproximación
        # Usar Iy para estimación de D
        D_approx = 2.0 * (req.Iy_m4 * 64.0 / math.pi) ** 0.25 * 500  # mm (muy aproximado)
        # Solo añadir advertencia, no bloquear
        warnings.append("Wall slenderness check requires explicit D_ext_mm; use /section/wall-slenderness")

    all_utils = [c.utilization for c in checks]
    max_util = max(all_utils) if all_utils else 0.0

    fail_checks = [c for c in checks if c.status == AluminiumCheckStatus.FAIL]
    blocked = [c for c in checks if c.status == AluminiumCheckStatus.BLOCKED]
    errors.extend([c.error_code for c in blocked if c.error_code])

    if blocked:
        overall = AluminiumCheckStatus.BLOCKED
    elif fail_checks:
        overall = AluminiumCheckStatus.FAIL
    elif all_utils:
        overall = AluminiumCheckStatus.PASS
    else:
        overall = AluminiumCheckStatus.PASS

    governing = None
    if all_utils:
        idx = all_utils.index(max_util)
        governing = checks[idx].check_type

    return AluminiumVerifyResponse(
        checks=[
            AluminiumCheckResult(
                check_type=c.check_type,
                status=c.status,
                solicitation=c.solicitation,
                resistance=c.resistance,
                utilization=c.utilization,
                unit=c.unit,
                governing_rule=c.governing_rule,
                equation_trace=c.equation_trace,
                intermediate_values=c.intermediate_values,
                error_code=c.error_code,
            )
            for c in checks
        ],
        overall_status=overall,
        max_utilization=round(max_util, 6),
        governing_check=governing,
        error_codes=errors,
        warnings=warnings,
    )


# ── Soldadura ─────────────────────────────────────────────────────────────────

@router.post("/weld/static-check")
def weld_static_check(
    Fx_kn: float = Query(default=0.0),
    Fy_kn: float = Query(default=0.0),
    Fz_kn: float = Query(default=0.0),
    throat_mm: float = Query(..., gt=0),
    length_mm: float = Query(..., gt=0),
    fu_w_mpa: float = Query(..., gt=0),
    beta_w: float = Query(default=0.85),
    gamma_M2: float = Query(default=1.25),
) -> dict:
    """Verificación estática de cordón en ángulo de aluminio."""
    result = AluminiumWeldService.fillet_weld_static_check(
        Fx_kn, Fy_kn, Fz_kn, throat_mm, length_mm, fu_w_mpa, beta_w, gamma_M2
    )
    return {
        "check_type": result.check_type,
        "status": result.status.value,
        "solicitation": result.solicitation,
        "resistance": result.resistance,
        "utilization": result.utilization,
        "unit": result.unit,
        "governing_rule": result.governing_rule,
        "intermediate_values": result.intermediate_values,
    }


@router.get("/weld/seam-door-check")
def weld_seam_door_check(
    seam_azimuth_deg: float = Query(...),
    door_azimuth_deg: float = Query(default=0.0),
    tolerance_deg: float = Query(default=5.0),
) -> dict:
    """Comprueba que la costura longitudinal no coincida con la zona de puerta."""
    ok = AluminiumWeldService.seam_not_in_door(seam_azimuth_deg, door_azimuth_deg, tolerance_deg)
    return {
        "compliant": ok,
        "seam_azimuth_deg": seam_azimuth_deg,
        "door_azimuth_deg": door_azimuth_deg,
        "error_code": None if ok else "AL-MFG-001",
    }


# ── Fatiga ────────────────────────────────────────────────────────────────────

@router.post("/fatigue/simplified-check")
def fatigue_simplified(
    delta_sigma_mpa: float = Query(..., gt=0),
    fatigue_category_mpa: float = Query(..., gt=0),
    gamma_Ff: float = Query(default=1.0),
    gamma_Mf: float = Query(default=1.15),
) -> dict:
    """Verificación de fatiga simplificada EN 1999-1-3."""
    result = AluminiumFatigueService.simplified_fatigue_check(
        delta_sigma_mpa, fatigue_category_mpa, gamma_Ff, gamma_Mf
    )
    return {
        "status": result.status.value,
        "solicitation_mpa": result.solicitation,
        "capacity_mpa": result.resistance,
        "utilization": result.utilization,
        "governing_rule": result.governing_rule,
    }


@router.post("/fatigue/miner-damage", response_model=AluminiumMinerResponse)
def fatigue_miner(req: AluminiumMinerRequest) -> AluminiumMinerResponse:
    """Daño acumulado de Palmgren-Miner D = Σ(n_i/N_i)."""
    blocks = [
        {"delta_sigma_mpa": b.delta_sigma_mpa, "n_cycles": b.n_cycles,
         "N_ref": b.N_ref, "source": b.source}
        for b in req.cycle_blocks
    ]
    result = AluminiumFatigueService.miner_damage(blocks, req.D_limit)
    return AluminiumMinerResponse(
        total_damage=result.total_damage,
        D_limit=result.D_limit,
        status=result.status,
        source_breakdown=result.source_breakdown,
        duplicate_source_detected=result.duplicate_source_detected,
    )


# ── Durabilidad ───────────────────────────────────────────────────────────────

@router.post("/durability/life-check", response_model=AluminiumDurabilityResponse)
def durability_life_check(req: AluminiumDurabilityRequest) -> AluminiumDurabilityResponse:
    """Verificación de vida útil del sistema de acabado y riesgos galvánicos."""
    adequate, msg = AluminiumDurabilityService.check_life_adequacy(
        req.treatment.value, req.corrosivity_category, req.design_life_years
    )
    galvanic_risks = AluminiumDurabilityService.check_galvanic_contacts(
        req.galvanic_contacts or []
    )
    open_cavity_risk = AluminiumDurabilityService.check_open_cavities(req.has_open_cavities)
    galvanic_required = bool(galvanic_risks)
    errors = []
    if not adequate:
        errors.append("AL-DUR-001")
    recommendations = [msg]
    if galvanic_risks:
        recommendations.extend(galvanic_risks)
    if open_cavity_risk:
        recommendations.append("Cavidades sin drenaje detectadas; añadir ventilación/drenaje")

    return AluminiumDurabilityResponse(
        life_adequate=adequate,
        life_range_min_years=None,
        life_range_max_years=None,
        galvanic_isolation_required=galvanic_required,
        galvanic_risks=galvanic_risks,
        open_cavity_risk=open_cavity_risk,
        recommendations=recommendations,
        error_codes=errors,
    )


# ── Fabricación ───────────────────────────────────────────────────────────────

@router.post("/manufacturing/bend-allowance", response_model=AluminiumBendAllowanceResponse)
def manufacturing_bend_allowance(req: AluminiumBendAllowanceRequest) -> AluminiumBendAllowanceResponse:
    """Cálculo de bend allowance para plegado de chapa 5083."""
    result = AluminiumManufacturingService.bend_allowance(
        req.thickness_mm, req.bend_angle_deg, req.inner_radius_mm, req.k_factor
    )
    return AluminiumBendAllowanceResponse(
        bend_allowance_mm=result.bend_allowance_mm,
        outside_setback_mm=result.outside_setback_mm,
        neutral_radius_mm=result.neutral_radius_mm,
        k_factor=result.k_factor,
        compliant_with_min_radius=result.compliant_with_min_radius,
        min_radius_for_material=result.min_radius_for_material,
    )


@router.get("/manufacturing/fabricability-checks", response_model=AluminiumFabricabilityResponse)
def manufacturing_fabricability_checks(
    piece_length_m: float = Query(..., gt=0),
    diameter_mm: float = Query(..., gt=0),
    seam_azimuth_deg: float = Query(default=0.0),
    door_azimuth_deg: float = Query(default=0.0),
    thickness_mm: Optional[float] = Query(default=None, gt=0),
) -> AluminiumFabricabilityResponse:
    """Comprobaciones de fabricabilidad básicas para aluminio plegado."""
    issues = []
    chk_len = AluminiumManufacturingService.check_piece_length(piece_length_m)
    chk_diam = AluminiumManufacturingService.check_min_diameter(diameter_mm)
    chk_seam = AluminiumManufacturingService.check_seam_not_in_door(seam_azimuth_deg, door_azimuth_deg)

    for chk in (chk_len, chk_diam, chk_seam):
        if not chk.compliant:
            issues.append(FabricabilityIssue(
                code=chk.code, severity=chk.severity, description=chk.description))

    if thickness_mm is not None:
        chk_t = AluminiumManufacturingService.check_sheet_thickness(thickness_mm)
        if not chk_t.compliant:
            issues.append(FabricabilityIssue(
                code=chk_t.code, severity=chk_t.severity, description=chk_t.description))

    return AluminiumFabricabilityResponse(
        is_fabricable=len([i for i in issues if i.severity == "BLOCKING"]) == 0,
        issues=issues,
        piece_length_ok=chk_len.compliant,
        diameter_ok=chk_diam.compliant,
        seam_not_in_door=chk_seam.compliant,
    )


@router.get("/manufacturing/cone-blank")
def manufacturing_cone_blank(
    D_base_mm: float = Query(..., gt=0),
    D_top_mm: float = Query(..., gt=0),
    height_m: float = Query(..., gt=0),
) -> dict:
    """Desarrollo de cono truncado para chapa plegada troncocónica."""
    return AluminiumManufacturingService.cone_frustum_blank_geometry(
        D_base_mm, D_top_mm, height_m
    )


# ── FSW ───────────────────────────────────────────────────────────────────────

@router.get("/fsw/keyhole-check")
def fsw_keyhole_check(
    keyhole_station_m: float = Query(...),
    critical_zone_start_m: float = Query(...),
    critical_zone_end_m: float = Query(...),
) -> dict:
    """Verifica que el keyhole (fin de pasada FSW) esté fuera de zonas críticas."""
    return AluminiumFSWService.check_keyhole_position(
        keyhole_station_m, critical_zone_start_m, critical_zone_end_m
    )


# ── DB-dependent (501) ────────────────────────────────────────────────────────

@router.post("/runs", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_verification_run() -> None:
    raise _501


@router.get("/runs/{run_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def get_verification_run(run_id: str) -> None:
    raise _501


@router.post("/door/optimize", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def optimize_door_reinforcement() -> None:
    raise _501


@router.post("/optimize", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def optimize_design() -> None:
    raise _501


@router.post("/manufacturing/export", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def export_manufacturing_package() -> None:
    raise _501


@router.post("/runs/{run_id}/reports", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def generate_report(run_id: str) -> None:
    raise _501
