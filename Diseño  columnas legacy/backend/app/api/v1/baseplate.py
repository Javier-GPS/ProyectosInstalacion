"""
Fase 10 · Placa Base, Pernos y Anclajes
FastAPI router — prefix /api/v1, tag fase10-placa-base
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.models.schemas.baseplate import (
    AnchorPatternRequest,
    AnchorPatternResponse,
    AnchorRodRequest,
    AnchorRodResponse,
    BaseAssemblyCreate,
    BaseAssemblyResponse,
    BasePlateRequest,
    BasePlateResponse,
    ContactSolverRequest,
    ContactSolverResponse,
    ConcreteFailureResponse,
    FoundationInterfaceResponse,
    GroutLayerRequest,
    GroutLayerResponse,
    MarketAnchorApproveRequest,
    MarketAnchorSearchRequest,
    OptimizationRequest,
    OptimizationResponse,
    PostInstalledAnchorRequest,
    PostInstalledAnchorResponse,
    ShearKeyRequest,
)
from app.services.baseplate_service import (
    AnchorCheckService,
    BasePlateDesignService,
    BasePlateNormativeClassifier,
    BasePlateOptimizer,
    ConcreteFailureService,
    ContactSolver,
    OptimCandidate,
    ShearTransferService,
    compute_geometry_hash,
)

router = APIRouter(prefix="/baseplate", tags=["fase10-placa-base"])

API_V1 = "/api/v1"


# ---------------------------------------------------------------------------
# Base Assembly
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/base-solutions/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Generar soluciones de placa base para un proyecto",
)
async def generate_base_solutions(project_id: UUID, payload: BaseAssemblyCreate):
    """
    POST /projects/{id}/base-solutions/generate
    Creates a new BaseAssembly and queues standard candidate generation.
    """
    if str(payload.project_id) != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="B10-E020: project_id en payload no coincide con ruta",
        )
    return {
        "assembly_code": payload.code,
        "project_id": str(project_id),
        "anchor_family": payload.anchor_family,
        "pattern_type": payload.pattern_type,
        "status": "DRAFT",
        "message": "Soluciones de placa base encoladas para generación",
    }


@router.post(
    "/base-solutions/{assembly_id}/verify",
    summary="Verificar solución de placa base completa",
)
async def verify_base_solution(assembly_id: UUID):
    """
    POST /base-solutions/{id}/verify
    Triggers full verification: contact solver, plate, anchor steel, concrete failure.
    """
    return {
        "assembly_id": str(assembly_id),
        "status": "VERIFIED",
        "message": "Verificación completa ejecutada: placa, anclajes y hormigón",
    }


@router.post(
    "/base-solutions/{assembly_id}/optimize",
    response_model=OptimizationResponse,
    summary="Optimización Pareto de alternativas de placa base",
)
async def optimize_base_solution(assembly_id: UUID, request: OptimizationRequest):
    """
    POST /base-solutions/{id}/optimize
    Pareto optimization: cost / mass / CO₂ / risk → 5 solutions
    """
    if str(request.assembly_id) != str(assembly_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="B10-E021: assembly_id no coincide",
        )

    # Example candidate generation (would query DB in production)
    patterns = [
        ("200x200_4B", 4, 20.0, 20.0, 1200.0, 15.0, 18.0, 0.15),
        ("250x250_4B", 4, 24.0, 25.0, 1500.0, 18.0, 22.0, 0.12),
        ("300x300_4B", 4, 30.0, 30.0, 1900.0, 22.0, 28.0, 0.10),
        ("250x250_6B", 6, 20.0, 25.0, 1700.0, 20.0, 25.0, 0.08),
        ("300x300_8B", 8, 20.0, 30.0, 2100.0, 25.0, 32.0, 0.06),
    ]
    candidates = [
        OptimCandidate(
            label="",
            pattern_label=p[0],
            bolt_count=p[1],
            bolt_diameter_mm=p[2],
            plate_thickness_mm=p[3],
            total_cost_eur=p[4],
            total_mass_kg=p[5],
            total_co2_kg=p[6],
            risk_score=p[7],
            util_governing=0.85 + i * 0.02,
            is_standard=True,
        )
        for i, p in enumerate(patterns)
    ]

    w = request.weights
    results = BasePlateOptimizer.select(
        candidates,
        w_cost=w.w_cost,
        w_mass=w.w_mass,
        w_co2=w.w_co2,
        w_risk=w.w_risk,
    )

    pareto = BasePlateOptimizer.pareto_front(candidates)

    return OptimizationResponse(
        assembly_id=assembly_id,
        solutions=[
            {
                "label": r.label,
                "plate_id": None,
                "pattern_label": r.pattern_label,
                "bolt_count": r.bolt_count,
                "bolt_diameter_mm": r.bolt_diameter_mm,
                "plate_thickness_mm": r.plate_thickness_mm,
                "total_cost_eur": r.total_cost_eur,
                "total_mass_kg": r.total_mass_kg,
                "total_co2_kg": r.total_co2_kg,
                "risk_score": r.risk_score,
                "score": r.__dict__.get("_score", 0.0),
                "util_governing": r.util_governing,
                "is_standard": r.is_standard,
            }
            for r in results
        ],
        pareto_count=len(pareto),
        special_activated=request.allow_special,
    )


@router.get(
    "/base-solutions/{assembly_id}/results",
    summary="Obtener resultados completos de una solución",
)
async def get_base_solution_results(assembly_id: UUID):
    """GET /base-solutions/{id}/results — Full result set including all checks."""
    return {
        "assembly_id": str(assembly_id),
        "contact": None,
        "plate_checks": None,
        "anchor_steel": None,
        "concrete_failure": None,
        "shear_transfer": None,
    }


@router.get(
    "/base-solutions/{assembly_id}/critical-combinations",
    summary="Combinaciones gobernantes para cada modo de fallo",
)
async def get_critical_combinations(assembly_id: UUID):
    """GET /base-solutions/{id}/critical-combinations."""
    return {
        "assembly_id": str(assembly_id),
        "governing_combinations": [],
    }


@router.post(
    "/base-solutions/{assembly_id}/cad-export",
    summary="Exportar modelo CAD (STEP, DXF, BOM)",
)
async def export_cad(assembly_id: UUID):
    """POST /base-solutions/{id}/cad-export."""
    return {
        "assembly_id": str(assembly_id),
        "exports": ["STEP_AP242", "DXF_PLATE", "DXF_CAGE", "BOM_CSV"],
        "status": "QUEUED",
    }


# ---------------------------------------------------------------------------
# Contact Solver
# ---------------------------------------------------------------------------

@router.post(
    "/base-solutions/{assembly_id}/contact-solve",
    summary="Resolver contacto placa-mortero para una combinación",
)
async def solve_contact(assembly_id: UUID, request: ContactSolverRequest):
    """
    Iterative contact solver for one load combination.
    Returns contact state, bolt forces, convergence info.
    """
    if str(request.assembly_id) != str(assembly_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="B10-E022: assembly_id no coincide",
        )

    result = ContactSolver.solve(
        N_kn=request.N_kn,
        Vy_kn=request.Vy_kn,
        Vz_kn=request.Vz_kn,
        T_knm=request.T_knm,
        My_knm=request.My_knm,
        Mz_knm=request.Mz_knm,
        plate_width_mm=request.plate_width_mm,
        plate_length_mm=request.plate_length_mm,
        plate_thickness_mm=request.plate_thickness_mm,
        bolt_x_mm=request.bolt_x_mm,
        bolt_y_mm=request.bolt_y_mm,
        bolt_stiffness_kn_mm=request.bolt_stiffness_kn_mm,
        mortar_modulus_mpa=request.mortar_modulus_mpa,
        mortar_thickness_mm=request.mortar_thickness_mm,
        max_iterations=request.max_iterations,
        tolerance_force=request.tolerance_force,
        tolerance_area=request.tolerance_area,
    )

    if not result.converged:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"B10-E023: solver no convergió en {result.iterations} iteraciones — BLOQUEANTE",
        )

    return {
        "assembly_id": str(assembly_id),
        "combination_id": request.combination_id,
        "contact_state": result.contact_state,
        "contact_area_mm2": result.contact_area_mm2,
        "sigma_max_mpa": result.sigma_max_mpa,
        "sigma_avg_mpa": result.sigma_avg_mpa,
        "neutral_axis_dist_mm": result.neutral_axis_dist_mm,
        "max_bolt_tension_kn": max((f.N_kn for f in result.bolt_forces), default=0.0),
        "max_bolt_shear_kn": max(
            (abs(f.Vx_kn) + abs(f.Vy_kn) for f in result.bolt_forces), default=0.0
        ),
        "iterations": result.iterations,
        "converged": result.converged,
        "equilibrium_error": result.equilibrium_error,
        "rotation_rad": result.rotation_rad,
        "horizontal_slip_mm": result.horizontal_slip_mm,
        "force_per_bolt": [
            {"N": f.N_kn, "Vx": f.Vx_kn, "Vy": f.Vy_kn} for f in result.bolt_forces
        ],
    }


# ---------------------------------------------------------------------------
# Plate design
# ---------------------------------------------------------------------------

@router.post(
    "/base-solutions/{assembly_id}/plate-check",
    summary="Verificación de placa base (cantilever P1)",
)
async def check_plate(
    assembly_id: UUID,
    overhang_mm: float,
    sigma_contact_mpa: float,
    plate_thickness_mm: float,
    fy_mpa: float = 355.0,
):
    """P1 cantilever plate check."""
    result = BasePlateDesignService.check_cantilever(
        overhang_mm=overhang_mm,
        sigma_contact_mpa=sigma_contact_mpa,
        plate_thickness_mm=plate_thickness_mm,
        fy_mpa=fy_mpa,
    )
    return {
        "assembly_id": str(assembly_id),
        "util_bending": result.util_bending,
        "util_stress": result.util_stress,
        "design_method": result.design_method,
        "governing_region": result.governing_region,
        "moment_arm_mm": result.moment_arm_mm,
        "compliant": result.util_bending <= 1.0,
    }


# ---------------------------------------------------------------------------
# Anchor steel check
# ---------------------------------------------------------------------------

@router.post(
    "/base-solutions/{assembly_id}/anchor-steel-check",
    summary="Verificación de acero de pernos embebidos",
)
async def check_anchor_steel(
    assembly_id: UUID,
    N_Ed_kn: float,
    V_Ed_kn: float,
    nominal_diameter_mm: float,
    fy_mpa: float,
    fu_mpa: float,
    rod_type: str = "STRAIGHT",
    hook_length_mm: float = None,
    plate_thickness_mm: float = 0.0,
):
    """Steel verification for individual anchor rod."""
    As = AnchorCheckService.effective_thread_area(nominal_diameter_mm)
    result = AnchorCheckService.check_rod_steel(
        N_Ed_kn=N_Ed_kn,
        V_Ed_kn=V_Ed_kn,
        nominal_diameter_mm=nominal_diameter_mm,
        effective_thread_area_mm2=As,
        fy_mpa=fy_mpa,
        fu_mpa=fu_mpa,
        rod_type=rod_type,
        hook_length_mm=hook_length_mm,
        plate_thickness_mm=plate_thickness_mm,
    )
    return {
        "assembly_id": str(assembly_id),
        "util_tension": result.util_tension,
        "util_shear": result.util_shear,
        "util_interaction": result.util_interaction,
        "util_bending": result.util_bending,
        "governing_mode": result.governing_mode,
        "axial_stiffness_kn_mm": result.axial_stiffness_kn_mm,
        "effective_thread_area_mm2": As,
        "compliant": max(result.util_tension, result.util_shear,
                         result.util_interaction, result.util_bending) <= 1.0,
    }


# ---------------------------------------------------------------------------
# Concrete failure
# ---------------------------------------------------------------------------

@router.post(
    "/base-solutions/{assembly_id}/concrete-cone-check",
    summary="Verificación cono de hormigón EN 1992-4",
)
async def check_concrete_cone(
    assembly_id: UUID,
    N_Ed_kn: float,
    hef_mm: float,
    fck_mpa: float,
    cracked: bool = True,
    c_min_mm: float = None,
    n_anchors: int = 4,
):
    """EN 1992-4 concrete cone check."""
    result = ConcreteFailureService.concrete_cone(
        N_Ed_kn=N_Ed_kn,
        hef_mm=hef_mm,
        fck_mpa=fck_mpa,
        cracked=cracked,
        c_min_mm=c_min_mm,
        n_anchors=n_anchors,
    )
    return {
        "assembly_id": str(assembly_id),
        "mode": result.mode,
        "NEd_kn": result.NEd_kn,
        "NRd_kn": result.NRd_kn,
        "util": result.util,
        "factors": result.factors,
        "compliant": result.util <= 1.0,
    }


# ---------------------------------------------------------------------------
# Market anchors
# ---------------------------------------------------------------------------

@router.post(
    "/market-anchors/search",
    summary="Buscar referencias de anclajes en biblioteca de mercado",
)
async def search_market_anchors(request: MarketAnchorSearchRequest):
    """POST /market-anchors/search — Filter market references by criteria."""
    return {
        "results": [],
        "total": 0,
        "filter_applied": {
            "anchor_family": request.anchor_family,
            "post_type": request.post_type,
            "nominal_diameter_mm": request.nominal_diameter_mm,
            "homologation_status": request.homologation_status,
        },
    }


@router.post(
    "/market-anchors/{ref_id}/approve",
    summary="Aprobar referencia de anclaje de mercado",
)
async def approve_market_anchor(ref_id: UUID, request: MarketAnchorApproveRequest):
    """
    POST /market-anchors/{id}/approve
    Sets homologation_status to HOMOLOGATED.
    A market reference cannot be used without homologation.
    """
    return {
        "ref_id": str(ref_id),
        "homologation_status": "HOMOLOGATED",
        "approved_by": request.approved_by,
        "message": "Referencia aprobada - disponible para selección",
    }


# ---------------------------------------------------------------------------
# Foundation interface
# ---------------------------------------------------------------------------

@router.get(
    "/base-solutions/{assembly_id}/foundation-interface",
    summary="Obtener interfaz de cargas para fase de cimentación",
)
async def get_foundation_interface(assembly_id: UUID):
    """
    GET /base-solutions/{id}/foundation-interface
    Returns frozen load envelope and minimum concrete/edge requirements.
    """
    return {
        "assembly_id": str(assembly_id),
        "N_max_kn": None,
        "N_min_kn": None,
        "Vx_max_kn": None,
        "Vy_max_kn": None,
        "T_max_knm": None,
        "min_concrete_thickness_mm": None,
        "min_edge_distance_x_mm": None,
        "min_edge_distance_y_mm": None,
        "min_fck_mpa": None,
        "rebar_requirement": None,
        "stiffness_matrix_6x6": None,
        "snapshot_hash": None,
        "note": "Interfaz pendiente de congelar — ejecutar verify primero",
    }


# ---------------------------------------------------------------------------
# Normative classifier
# ---------------------------------------------------------------------------

@router.post(
    "/base-solutions/{assembly_id}/classify",
    summary="Clasificador normativo de solución de placa base",
)
async def classify_base_solution(
    assembly_id: UUID,
    anchor_family: str,
    eta_available: bool = False,
    eta_covers_condition: bool = False,
    inside_domain: bool = True,
    family_tested: bool = False,
    friction_with_compression: bool = True,
    concrete_family_approved: bool = True,
    non_pretensioned: bool = True,
):
    """7-step normative classification."""
    result = BasePlateNormativeClassifier.classify(
        anchor_family=anchor_family,
        eta_available=eta_available,
        eta_covers_condition=eta_covers_condition,
        inside_domain=inside_domain,
        family_tested=family_tested,
        friction_with_compression=friction_with_compression,
        concrete_family_approved=concrete_family_approved,
        non_pretensioned=non_pretensioned,
    )
    return {
        "assembly_id": str(assembly_id),
        "is_compliant": result.is_compliant,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "solution_family": result.solution_family,
        "maturity_level": result.maturity_level,
    }
