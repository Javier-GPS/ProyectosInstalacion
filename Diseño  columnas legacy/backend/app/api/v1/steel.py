"""
API Router · Fase 5 — Acero: Diseño, Verificación y Fabricación
Salvi Studio · Columns
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas.steel import (
    DoorSectionModelCreate,
    DoorSectionModelResponse,
    DurabilitySystemCreate,
    DurabilitySystemResponse,
    FatigueDetailCreate,
    FatigueDetailResponse,
    ManufacturingRouteCreate,
    ManufacturingRouteResponse,
    NormativeRouteRequest,
    NormativeRouteResponse,
    NormativeRouteStepResult,
    ProductFamilyCreate,
    ProductFamilyResponse,
    SteelOptimizationRunCreate,
    SteelOptimizationRunResponse,
    SteelProductPropertyCreate,
    SteelProductPropertyResponse,
    SteelReportCreate,
    SteelReportResponse,
    SteelSectionCheckResponse,
    SteelSectionCheckRunCreate,
    SteelSectionCheckRunResponse,
    SteelJointCreate,
    SteelJointResponse,
    ThicknessPolicyResponse,
    ValidationEvidenceCreate,
    ValidationEvidenceResponse,
    WeldGroupCreate,
    WeldGroupResponse,
)
from app.services.steel_service import (
    DurabilityService,
    ManufacturingService,
    NormativeClassifier,
    SteelMaterialService,
    SteelSectionEngine,
    WeldEngine,
    FatigueEngine,
)

router = APIRouter(prefix="/steel", tags=["steel"])


# ---------------------------------------------------------------------------
# Material library
# ---------------------------------------------------------------------------

@router.post(
    "/materials",
    response_model=SteelProductPropertyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create steel material property record",
)
async def create_steel_material(
    payload: SteelProductPropertyCreate,
    db: AsyncSession = Depends(get_db),
) -> SteelProductPropertyResponse:
    """
    Crea un registro de propiedades de acero en la biblioteca.
    Clave canónica: norma + grado + subgrado + forma + condición + espesor + temperatura.
    Operación restringida a LIBRARY_ADMIN y SYSTEM_ADMIN.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación completa con conexión a BD",
    )


@router.get(
    "/materials",
    response_model=list[SteelProductPropertyResponse],
    summary="List steel material properties",
)
async def list_steel_materials(
    project_id: Optional[uuid.UUID] = Query(default=None),
    steel_grade: Optional[str] = Query(default=None),
    product_form: Optional[str] = Query(default=None),
    thickness_mm: Optional[float] = Query(default=None, gt=0),
    deprecated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> list[SteelProductPropertyResponse]:
    """
    Lista registros de la biblioteca de aceros, con filtros opcionales.
    Si se pasa thickness_mm, devuelve solo los registros que cubren ese espesor.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación completa con conexión a BD",
    )


@router.post(
    "/materials/thickness-policy",
    response_model=ThicknessPolicyResponse,
    summary="Compute thickness policy (t_nom, t_min, t_eff, t_mass)",
)
async def compute_thickness_policy(
    t_nom_mm: float = Query(..., gt=0),
    delta_t_tol_mm: float = Query(..., ge=0),
    delta_t_corr_mm: float = Query(default=0.0, ge=0),
    corrosion_already_applied: bool = Query(default=False),
) -> ThicknessPolicyResponse:
    """
    Calcula y devuelve simultáneamente t_nom, delta_t_tol, delta_t_corr,
    t_min (= t_nom - delta_t_tol), t_eff y t_mass.
    Detecta doble deducción de corrosión (AC-73).
    """
    try:
        policy = SteelMaterialService.compute_thickness_policy(
            t_nom_mm=t_nom_mm,
            delta_t_tol_mm=delta_t_tol_mm,
            delta_t_corr_mm=delta_t_corr_mm,
            corrosion_already_applied=corrosion_already_applied,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ThicknessPolicyResponse(
        t_nom_mm=policy.t_nom_mm,
        delta_t_tol_mm=policy.delta_t_tol_mm,
        delta_t_corr_mm=policy.delta_t_corr_mm,
        t_min_mm=policy.t_min_mm,
        t_eff_mm=policy.t_eff_mm,
        t_mass_mm=policy.t_mass_mm,
        double_deduction_check=policy.double_deduction_check,
    )


# ---------------------------------------------------------------------------
# Normative route classifier
# ---------------------------------------------------------------------------

@router.post(
    "/normative-route",
    response_model=NormativeRouteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run normative route classifier (7-step blocking tree)",
)
async def classify_normative_route(
    payload: NormativeRouteRequest,
    db: AsyncSession = Depends(get_db),
) -> NormativeRouteResponse:
    """
    Ejecuta el clasificador normativo de 7 pasos bloqueantes y almacena el resultado.
    Retorna la ruta (EN40 / EN40_EXTENDED / SPECIAL), la traza de decisión completa
    y la declaración máxima permitida.

    El resultado es una función determinista de los inputs: mismo payload → mismo hash.
    """
    result = NormativeClassifier.classify(
        height_nominal_m=payload.height_nominal_m,
        has_catenary_cables=payload.has_catenary_cables,
        has_excluded_actions=payload.has_excluded_actions,
        section_in_en40_domain=payload.section_in_en40_domain,
        door_in_approved_method=payload.door_in_approved_method,
        combinations_available=payload.combinations_available,
        all_rules_have_editions=payload.all_rules_have_editions,
    )

    steps_response = [
        NormativeRouteStepResult(
            step=s.step,
            condition=s.condition,
            status=s.status,
            detail=s.detail,
        )
        for s in result.steps
    ]

    decision_trace = {f"step_{s.step}": {"condition": s.condition, "status": s.status, "detail": s.detail}
                      for s in result.steps}

    return NormativeRouteResponse(
        id=uuid.uuid4(),   # En producción: ID del registro persistido en BD
        route=result.route.value,
        route_version=result.route_version,
        steps=steps_response,
        decision_trace=decision_trace,
        active_rules=result.active_rules,
        discarded_rules=result.discarded_rules,
        exclusions=result.exclusions,
        warnings=result.warnings,
        max_declaration_allowed=result.max_declaration_allowed,
        input_hash=result.input_hash,
    )


# ---------------------------------------------------------------------------
# Section verification runs
# ---------------------------------------------------------------------------

@router.post(
    "/section-check-runs",
    response_model=SteelSectionCheckRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create steel section verification run",
)
async def create_section_check_run(
    payload: SteelSectionCheckRunCreate,
    db: AsyncSession = Depends(get_db),
) -> SteelSectionCheckRunResponse:
    """
    Inicia una ejecución de verificación de secciones de acero.
    Consume resultados del run de Fase 4 indicado (structural_run_id).

    El flujo canónico de 10 pasos se aplica a cada estación × combinación.
    Prohibido construir combinaciones artificiales (máximo de cada componente
    de distintos casos).

    Responde 202 Accepted; estado consultable en GET /section-check-runs/{id}.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación completa con conexión a BD y motor F4",
    )


@router.get(
    "/section-check-runs/{run_id}",
    response_model=SteelSectionCheckRunResponse,
    summary="Get section check run status",
)
async def get_section_check_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SteelSectionCheckRunResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.get(
    "/section-check-runs/{run_id}/checks",
    response_model=list[SteelSectionCheckResponse],
    summary="Get individual section checks for a run",
)
async def get_section_checks(
    run_id: uuid.UUID,
    check_type: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    station_id: Optional[uuid.UUID] = Query(default=None),
    combination_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[SteelSectionCheckResponse]:
    """
    Devuelve las verificaciones individuales (estación × combinación × tipo)
    con filtros opcionales. Paginación por page/page_size.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


# ---------------------------------------------------------------------------
# Local buckling / effective section (pure calculation endpoint)
# ---------------------------------------------------------------------------

@router.get(
    "/section/circular-wall-slenderness",
    summary="Check circular tube wall slenderness class (local buckling)",
)
async def check_circular_wall_slenderness(
    D_ext_mm: float = Query(..., gt=0, description="Diámetro exterior en mm"),
    t_eff_mm: float = Query(..., gt=0, description="Espesor efectivo en mm"),
    fy_mpa: float = Query(..., gt=0, description="Límite elástico en MPa"),
) -> dict:
    """
    Comprueba la esbeltez de pared de un tubo circular (D/t) y determina
    la clase de sección (1, 2, 3 o 4). Clase 4 activa STEEL-SEC-001.
    """
    try:
        result = SteelSectionEngine.check_circular_wall_slenderness(
            D_ext_mm=D_ext_mm,
            t_eff_mm=t_eff_mm,
            fy_mpa=fy_mpa,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "check_type": result.check_type,
        "status": result.status,
        "utilization": result.utilization,
        "margin": result.margin,
        "D_over_t": result.intermediate_values["D_over_t"],
        "section_class": result.intermediate_values["section_class"],
        "class_limits": {
            "class_1": result.intermediate_values["class_limit_1"],
            "class_2": result.intermediate_values["class_limit_2"],
            "class_3": result.intermediate_values["class_limit_3"],
        },
        "domain_notes": result.domain_notes,
        "norm": result.norm,
        "norm_clause": result.norm_clause,
    }


# ---------------------------------------------------------------------------
# Door section models
# ---------------------------------------------------------------------------

@router.post(
    "/door-sections",
    response_model=DoorSectionModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create door section model",
)
async def create_door_section(
    payload: DoorSectionModelCreate,
    db: AsyncSession = Depends(get_db),
) -> DoorSectionModelResponse:
    """
    Crea un modelo de sección de puerta con sus propiedades netas/compuestas.
    Si la esquina de la puerta está fuera del método analítico, devuelve
    error STEEL-DOOR-001 y exige método local / FEM / ensayo.
    Verifica que la costura longitudinal no coincida con el hueco de puerta.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.get(
    "/door-sections/{door_id}",
    response_model=DoorSectionModelResponse,
    summary="Get door section model",
)
async def get_door_section(
    door_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DoorSectionModelResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


# ---------------------------------------------------------------------------
# Weld groups
# ---------------------------------------------------------------------------

@router.post(
    "/weld-groups",
    response_model=WeldGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create weld group and run static + fatigue check",
)
async def create_weld_group(
    payload: WeldGroupCreate,
    db: AsyncSession = Depends(get_db),
) -> WeldGroupResponse:
    """
    Crea un grupo de soldadura y ejecuta la comprobación estática y de fatiga.
    Si la soldadura no tiene WPS o no es inspeccionable, devuelve STEEL-WELD-001
    (no liberable, independientemente de la resistencia matemática).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.post(
    "/weld/static-check",
    summary="Run fillet weld static check (pure calculation)",
)
async def weld_static_check(
    Fx_kn: float = Query(default=0.0),
    Fy_kn: float = Query(default=0.0),
    Fz_kn: float = Query(default=0.0),
    effective_throat_mm: float = Query(..., gt=0),
    effective_length_mm: float = Query(..., gt=0),
    fu_w_mpa: float = Query(..., gt=0),
    beta_w: float = Query(default=0.85, gt=0, le=1.0),
    gamma_M2: float = Query(default=1.25, gt=0),
) -> dict:
    """
    Comprobación estática de soldadura a filete con los seis resultantes.
    σ_eq = √(σ_⊥² + 3·τ_⊥² + 3·τ_∥²) ≤ fu_w / (β_w · γM2)
    """
    try:
        result = WeldEngine.fillet_weld_static_check(
            Fx_kn=Fx_kn,
            Fy_kn=Fy_kn,
            Fz_kn=Fz_kn,
            effective_throat_mm=effective_throat_mm,
            effective_length_mm=effective_length_mm,
            fu_w_mpa=fu_w_mpa,
            beta_w=beta_w,
            gamma_M2=gamma_M2,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "check_type": result.check_type,
        "status": result.status,
        "utilization": result.utilization,
        "margin": result.margin,
        "sigma_eq_mpa": result.solicitation,
        "sigma_rd_mpa": result.resistance,
        "intermediate": result.intermediate_values,
        "norm": result.norm,
        "norm_clause": result.norm_clause,
    }


# ---------------------------------------------------------------------------
# Fatigue
# ---------------------------------------------------------------------------

@router.post(
    "/fatigue-details",
    response_model=FatigueDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create fatigue detail in catalogue",
)
async def create_fatigue_detail(
    payload: FatigueDetailCreate,
    db: AsyncSession = Depends(get_db),
) -> FatigueDetailResponse:
    """
    Registra un detalle de fatiga en el catálogo.
    La categoría de fatiga no se selecciona por texto libre; cada detalle tiene
    geometría elegible, orientación de tensión, curva S-N, dominio y evidencia.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.post(
    "/fatigue/simplified-check",
    summary="Simplified EN 40 fatigue check (pure calculation)",
)
async def fatigue_simplified_check(
    delta_sigma_mpa: float = Query(..., gt=0),
    fatigue_category_mpa: float = Query(..., gt=0),
    gamma_Ff: float = Query(default=1.0, gt=0),
    gamma_Mf: float = Query(default=1.15, gt=0),
) -> dict:
    """
    Comprobación simplificada de fatiga EN 40:
    γ_Ff · ΔσE ≤ ΔσC / γ_Mf
    """
    result = FatigueEngine.simplified_en40_fatigue_check(
        delta_sigma_mpa=delta_sigma_mpa,
        fatigue_category_mpa=fatigue_category_mpa,
        gamma_Ff=gamma_Ff,
        gamma_Mf=gamma_Mf,
    )
    return {
        "status": result.status,
        "utilization": result.utilization,
        "margin": result.margin,
        "demand_mpa": result.solicitation,
        "capacity_mpa": result.resistance,
        "intermediate": result.intermediate_values,
    }


@router.post(
    "/fatigue/miner-damage",
    summary="Palmgren-Miner damage accumulation",
)
async def fatigue_miner_damage(
    cycle_blocks: list[dict],
) -> dict:
    """
    Calcula el daño acumulado D = Σ(n_i/N_i).
    Detecta doble conteo por fuentes duplicadas (AC-85).
    Cada bloque: {delta_sigma_mpa, n_cycles, N_ref, source}
    """
    if FatigueEngine.check_duplicate_source(cycle_blocks):
        raise HTTPException(
            status_code=422,
            detail="STEEL-FAT-001: espectros duplicados de una misma fuente detectados (doble conteo). "
                   "Revisar ciclos de viento, vórtices y cable para eliminar superposición.",
        )
    result = FatigueEngine.miner_damage(cycle_blocks)
    return result


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------

@router.post(
    "/durability-systems",
    response_model=DurabilitySystemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create durability/corrosion protection system",
)
async def create_durability_system(
    payload: DurabilitySystemCreate,
    db: AsyncSession = Depends(get_db),
) -> DurabilitySystemResponse:
    """
    Define el sistema de protección anticorrosiva para un componente.
    Verifica automáticamente que el sistema cubra la vida útil de diseño
    en la categoría de corrosividad indicada.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.post(
    "/durability/life-check",
    summary="Check durability system adequacy for design life",
)
async def durability_life_check(
    protection_system: str = Query(...),
    corrosivity_category: str = Query(...),
    design_life_years: int = Query(..., gt=0),
) -> dict:
    """
    Comprueba si el sistema de protección indicado cubre la vida útil de diseño
    en la categoría de corrosividad dada.
    """
    compatible, message = DurabilityService.check_life_adequacy(
        protection_system=protection_system,
        corrosivity_category=corrosivity_category,
        design_life_years=design_life_years,
    )
    return {
        "compatible": compatible,
        "message": message,
        "error_code": None if compatible else "STEEL-COR-001",
    }


@router.post(
    "/durability/galvanizing-geometry-check",
    summary="Check galvanizing geometry (ventilation/drainage holes)",
)
async def galvanizing_geometry_check(
    closed_volumes: list[dict],
) -> dict:
    """
    Verifica que todas las cavidades cerradas tengan venteo y drenaje.
    Una cavidad sin ambos es un error de seguridad bloqueante (AC-88).
    """
    all_ok, errors = DurabilityService.check_galvanizing_geometry(closed_volumes)
    if not all_ok:
        return {
            "all_ok": False,
            "errors": errors,
            "error_code": "STEEL-COR-001",
            "blocking": True,
        }
    return {"all_ok": True, "errors": [], "error_code": None, "blocking": False}


# ---------------------------------------------------------------------------
# Manufacturing
# ---------------------------------------------------------------------------

@router.post(
    "/manufacturing-routes",
    response_model=ManufacturingRouteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create manufacturing route (BOM, cost, CO2)",
)
async def create_manufacturing_route(
    payload: ManufacturingRouteCreate,
    db: AsyncSession = Depends(get_db),
) -> ManufacturingRouteResponse:
    """
    Genera la ruta de fabricación completa: secuencia de proceso, BOM,
    desarrollo de chapa, nesting, tolerancias, coste y CO₂.
    Aplica reglas bloqueantes de Salvi (longitud ≤12m, diámetro ≥60mm, etc.).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.get(
    "/manufacturing/cone-blank",
    summary="Calculate cone frustum blank geometry (sector annulus)",
)
async def cone_blank_geometry(
    D_base_mm: float = Query(..., gt=0),
    D_top_mm: float = Query(..., gt=0),
    height_m: float = Query(..., gt=0),
) -> dict:
    """
    Desarrollo de tronco de cono: geometría exacta del sector anular.
    Cálculo verificable analíticamente (AC-90).
    """
    try:
        result = ManufacturingService.cone_frustum_blank_geometry(
            D_base_mm=D_base_mm,
            D_top_mm=D_top_mm,
            height_m=height_m,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return result


@router.get(
    "/manufacturing/fabricability-checks",
    summary="Run fabricability rule checks",
)
async def fabricability_checks(
    piece_length_m: Optional[float] = Query(default=None, gt=0),
    diameter_mm: Optional[float] = Query(default=None, gt=0),
    seam_azimuth_deg: Optional[float] = Query(default=None),
    door_azimuth_deg: Optional[float] = Query(default=None),
) -> dict:
    """
    Aplica las reglas bloqueantes de fabricabilidad de Salvi.
    Retorna lista de checks con estado y código de error si procede.
    """
    checks = []
    all_ok = True

    if piece_length_m is not None:
        chk = ManufacturingService.check_piece_length(piece_length_m)
        checks.append({"rule": chk.rule, "compliant": chk.compliant, "blocking": chk.blocking,
                        "detail": chk.detail, "error_code": chk.error_code})
        if not chk.compliant:
            all_ok = False

    if diameter_mm is not None:
        chk = ManufacturingService.check_min_diameter(diameter_mm)
        checks.append({"rule": chk.rule, "compliant": chk.compliant, "blocking": chk.blocking,
                        "detail": chk.detail, "error_code": chk.error_code})
        if not chk.compliant:
            all_ok = False

    if seam_azimuth_deg is not None and door_azimuth_deg is not None:
        chk = ManufacturingService.check_seam_not_in_door(seam_azimuth_deg, door_azimuth_deg)
        checks.append({"rule": chk.rule, "compliant": chk.compliant, "blocking": chk.blocking,
                        "detail": chk.detail, "error_code": chk.error_code})
        if not chk.compliant:
            all_ok = False

    return {"all_fabricable": all_ok, "checks": checks}


# ---------------------------------------------------------------------------
# Steel joints
# ---------------------------------------------------------------------------

@router.post(
    "/joints",
    response_model=SteelJointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create steel joint (telescopic, flanged, welded, bolted)",
)
async def create_steel_joint(
    payload: SteelJointCreate,
    db: AsyncSession = Depends(get_db),
) -> SteelJointResponse:
    """
    Define una unión entre tramos de acero.
    Las uniones telescópicas no son rígidas por defecto; se requiere modelo
    aprobado de transferencia por contacto/rozamiento (AC-31, AC-86).
    La rigidez calculada se retroalimenta a Fase 4 (AC-87).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

@router.post(
    "/optimization-runs",
    response_model=SteelOptimizationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create steel optimization run (Pareto front: cost / weight / CO2)",
)
async def create_optimization_run(
    payload: SteelOptimizationRunCreate,
    db: AsyncSession = Depends(get_db),
) -> SteelOptimizationRunResponse:
    """
    Lanza una optimización multiobjetivo de acero.
    Genera candidatos discretos fabricables → prefiltro → cálculo completo F4+F5 →
    frente de Pareto con 4 soluciones representativas (min coste, min peso, min CO₂,
    equilibrada). Ningún candidato no fabricable ni no transportable llega al frente.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.get(
    "/optimization-runs/{run_id}",
    response_model=SteelOptimizationRunResponse,
    summary="Get optimization run results",
)
async def get_optimization_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SteelOptimizationRunResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


# ---------------------------------------------------------------------------
# Product families and validation evidence
# ---------------------------------------------------------------------------

@router.post(
    "/product-families",
    response_model=ProductFamilyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create product family with validation domain",
)
async def create_product_family(
    payload: ProductFamilyCreate,
    db: AsyncSession = Depends(get_db),
) -> ProductFamilyResponse:
    """
    Crea una familia de producto con su dominio de extensión de ensayos y cálculos.
    Una variante dentro del dominio puede usar los ensayos de la familia.
    Una variante fuera del dominio requiere nuevo cálculo, ensayo o aprobación (AC-45).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.post(
    "/product-families/{family_id}/evidence",
    response_model=ValidationEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add validation evidence to a product family",
)
async def add_validation_evidence(
    family_id: uuid.UUID,
    payload: ValidationEvidenceCreate,
    db: AsyncSession = Depends(get_db),
) -> ValidationEvidenceResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.post(
    "/reports",
    response_model=SteelReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate steel report snapshot",
)
async def create_report(
    payload: SteelReportCreate,
    db: AsyncSession = Depends(get_db),
) -> SteelReportResponse:
    """
    Genera una instantánea inmutable de informe de acero.
    Tipos: CLIENT, ENGINEERING, INTERNAL, PRODUCTION, INSPECTION, CONFORMITY, COST, CO2.

    El informe CLIENT NO incluye datos internos de coste (AC-62).
    El informe INTERNAL muestra todos los intermedios (AC-63).
    La producción no puede liberarse desde estado comercial (AC-64).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


@router.get(
    "/reports/{report_id}",
    response_model=SteelReportResponse,
    summary="Get report snapshot metadata",
)
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SteelReportResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pendiente de implementación",
    )


# ---------------------------------------------------------------------------
# Section properties (pure calculation endpoints)
# ---------------------------------------------------------------------------

@router.get(
    "/section/circular-hollow",
    summary="Calculate circular hollow section properties",
)
async def section_circular_hollow(
    D_ext_mm: float = Query(..., gt=0),
    t_mm: float = Query(..., gt=0),
    rho_kg_m3: float = Query(default=7850.0, gt=0),
) -> dict:
    """
    Propiedades geométricas de una sección hueca circular:
    A, I, J, Av, Wel, masa lineal.
    """
    try:
        props = SteelSectionEngine.circular_hollow_properties(D_ext_mm, t_mm, rho_kg_m3)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "D_ext_mm": props.D_ext_mm,
        "t_mm": props.t_mm,
        "A_m2": props.A_m2,
        "Iy_m4": props.Iy_m4,
        "Iz_m4": props.Iy_m4,   # simétrica
        "J_m4": props.J_m4,
        "Ay_m2": props.Ay_m2,
        "Az_m2": props.Az_m2,
        "Wel_y_m3": props.Wel_y_m3,
        "mass_per_m_kg": props.mass_per_m_kg,
    }


@router.get(
    "/section/polygon-hollow",
    summary="Calculate regular polygonal hollow section properties",
)
async def section_polygon_hollow(
    n_faces: int = Query(..., ge=3, le=32),
    inscribed_d_mm: float = Query(..., gt=0),
    t_mm: float = Query(..., gt=0),
    rho_kg_m3: float = Query(default=7850.0, gt=0),
) -> dict:
    """
    Propiedades geométricas de una sección hueca poligonal regular.
    """
    try:
        props = SteelSectionEngine.regular_polygon_hollow_properties(
            n_faces=n_faces, inscribed_d_mm=inscribed_d_mm, t_mm=t_mm, rho_kg_m3=rho_kg_m3
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "n_faces": props.n_faces,
        "inscribed_d_mm": props.inscribed_d_mm,
        "t_mm": props.t_mm,
        "A_m2": props.A_m2,
        "Iy_m4": props.Iy_m4,
        "Iz_m4": props.Iz_m4,
        "J_m4": props.J_m4,
        "Ay_m2": props.Ay_m2,
        "Az_m2": props.Az_m2,
        "Wel_y_m3": props.Wel_y_m3,
        "mass_per_m_kg": props.mass_per_m_kg,
    }
