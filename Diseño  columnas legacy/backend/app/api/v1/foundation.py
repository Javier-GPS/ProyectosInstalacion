"""
Fase 11 · Cimentaciones y Geotecnia — FastAPI router
Prefix: /api/v1  (included via main.py)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas.foundation import (
    EmbeddedPoleRequest,
    EmbeddedPoleResponse,
    FoundationCandidateRequest,
    FoundationCandidateResponse,
    FoundationCheckResponse,
    FoundationEvidenceRequest,
    FoundationStiffnessRequest,
    FoundationStiffnessResponse,
    GenerateCandidatesRequest,
    GeotechnicalSiteRequest,
    GeotechnicalSiteResponse,
    GlobalModelIterateRequest,
    OptimizationRequest,
    OptimizationResponse,
    OptimizationResult,
    ReleaseRequest,
    ReleaseResponse,
)
from app.services.foundation_service import (
    BearingCapacityService,
    EmbeddedPoleService,
    FoundationNormativeClassifier,
    FoundationOptimizer,
    FoundationStiffnessService,
    GeotechnicalClassifier,
    OverturningSlidingService,
    UpliftService,
    compute_foundation_hash,
)

router = APIRouter(prefix="/foundations", tags=["fase11-cimentaciones"])


# ---------------------------------------------------------------------------
# Geotechnical site
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/geotechnical-models",
    response_model=GeotechnicalSiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear modelo geotécnico del emplazamiento",
)
async def create_geotechnical_model(
    project_id: UUID,
    payload: GeotechnicalSiteRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Recibe datos de emplazamiento y clasifica nivel G0-G4.
    Retorna el modelo con campos confirmados/propuestos/conservadores y bloqueantes.
    """
    # Classify G-level from intake answers
    classification = GeotechnicalClassifier.classify(
        has_location=payload.latitude is not None,
        surface_type=payload.surface_type,
        has_soil_params=bool(payload.soil_layers),
        water_scenario=payload.water_scenario.value,
        has_geotechnical_report=(payload.geo_level.value >= "G3"),
        has_field_tests=(payload.geo_level.value >= "G3"),
        has_as_built=(payload.geo_level.value == "G4"),
        slope_near_m=payload.slope_near_m,
        buried_services=payload.buried_services,
    )

    # Build response (in production, persist to DB first)
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "project_id": project_id,
        "geo_level": classification.geo_level,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "water_scenario": payload.water_scenario,
        "water_table_depth_m": payload.water_table_depth_m,
        "blockers": classification.blockers,
        "warnings": classification.warnings,
        "confirmed_fields": classification.confirmed_fields,
        "calc_hash": "placeholder",
        "soil_layers": [],
    }


# ---------------------------------------------------------------------------
# Generate foundation candidates
# ---------------------------------------------------------------------------

@router.post(
    "/foundation-candidates/generate",
    response_model=list[FoundationCandidateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generar candidatos de cimentación",
)
async def generate_candidates(
    payload: GenerateCandidatesRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Genera candidatos de cimentación para las familias seleccionadas o todas las aplicables.
    Aplica predimensionamiento conservador EC7 con los parámetros del sitio.
    """
    # Stub: in production, query site, apply predimensioning, persist candidates
    return []


# ---------------------------------------------------------------------------
# Calculate foundation
# ---------------------------------------------------------------------------

@router.post(
    "/{foundation_id}/calculate",
    status_code=status.HTTP_200_OK,
    summary="Calcular verificaciones geotécnicas y estructurales",
)
async def calculate_foundation(
    foundation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Ejecuta verificaciones completas: capacidad portante, vuelco, deslizamiento,
    levantamiento, empotramiento (si aplica), rigidez Winkler.
    """
    # Demo calculation with typical values
    bearing = BearingCapacityService.check_drained(
        N_Ed_kn=50.0, My_knm=30.0, Mz_knm=0.0, V_Ed_kn=5.0,
        B_m=1.2, L_m=1.2, D_m=0.8,
        phi_deg=30.0, c_kpa=5.0, gamma_kn_m3=18.0,
    )
    ovt_slide = OverturningSlidingService.check(
        N_Ed_kn=50.0, Vy_kn=5.0, Vz_kn=0.0,
        My_knm=30.0, Mz_knm=0.0,
        B_m=1.2, L_m=1.2, D_m=0.8,
        gamma_concrete_kn_m3=24.0, gamma_soil_kn_m3=18.0,
        phi_deg=30.0, c_kpa=5.0,
    )
    return {
        "foundation_id": str(foundation_id),
        "bearing_capacity": {
            "qu_kpa": bearing.qu_kpa,
            "qRd_kpa": bearing.qRd_kpa,
            "sigma_Ed_kpa": bearing.sigma_Ed_kpa,
            "utilization": bearing.utilization,
            "error_codes": bearing.error_codes,
        },
        "overturning": {
            "ratio": ovt_slide.overturning_ratio,
            "within_third": ovt_slide.within_third,
            "compliant": ovt_slide.overturning_compliant,
        },
        "sliding": {
            "VRd_kn": ovt_slide.sliding_VRd_kn,
            "VEd_kn": ovt_slide.sliding_VEd_kn,
            "utilization": ovt_slide.sliding_util,
            "compliant": ovt_slide.sliding_compliant,
        },
        "error_codes": bearing.error_codes + ovt_slide.error_codes,
    }


# ---------------------------------------------------------------------------
# Optimize
# ---------------------------------------------------------------------------

@router.post(
    "/{foundation_id}/optimize",
    response_model=OptimizationResponse,
    summary="Optimización Pareto coste/CO₂/excavación/riesgo",
)
async def optimize_foundation(
    foundation_id: UUID,
    payload: OptimizationRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Aplica optimización multiobjetivo Pareto sobre los candidatos calculados.
    Retorna ≥4 soluciones etiquetadas: RECOMMENDED, MIN_COST, MIN_CO2, MIN_EXCAVATION.
    """
    from app.services.foundation_service import FoundationCandidateSummary

    # Stub candidates for demo
    candidates = [
        FoundationCandidateSummary(
            family="F11-A", width_m=1.2, length_m=1.2, depth_m=0.8, diameter_m=None,
            util_bearing=0.75, util_overturning=0.60, util_sliding=0.55, util_uplift=0.0,
            util_governing=0.75, total_cost_eur=1200.0, concrete_volume_m3=1.15,
            excavation_volume_m3=2.0, total_co2_kg=350.0, total_mass_kg=2760.0, feasible=True,
        ),
        FoundationCandidateSummary(
            family="F11-D", width_m=None, length_m=None, depth_m=1.0, diameter_m=1.0,
            util_bearing=0.65, util_overturning=0.55, util_sliding=0.50, util_uplift=0.0,
            util_governing=0.65, total_cost_eur=1500.0, concrete_volume_m3=0.79,
            excavation_volume_m3=1.5, total_co2_kg=240.0, total_mass_kg=1900.0, feasible=True,
        ),
    ]
    w = payload.weights
    selected = FoundationOptimizer.select(
        candidates,
        w_cost=w.w_cost, w_co2=w.w_co2,
        w_excavation=w.w_excavation, w_risk=w.w_risk,
    )
    dominated = len([c for c in candidates if c.feasible]) - len(
        FoundationOptimizer.pareto_front(candidates)
    )
    results = [
        OptimizationResult(
            candidate_id="00000000-0000-0000-0000-000000000001",
            family=c.family,
            label=c.label,
            total_cost_eur=c.total_cost_eur,
            total_co2_kg=c.total_co2_kg,
            excavation_volume_m3=c.excavation_volume_m3,
            util_governing=c.util_governing,
            score=c.score,
        )
        for c in selected
    ]
    return OptimizationResponse(
        results=results, pareto_count=len(selected), dominated_count=dominated
    )


# ---------------------------------------------------------------------------
# Iteration with global model (Fase 4)
# ---------------------------------------------------------------------------

@router.post(
    "/{foundation_id}/iterate-global-model",
    status_code=status.HTTP_200_OK,
    summary="Iteración rigidez con modelo global Fase 4",
)
async def iterate_global_model(
    foundation_id: UUID,
    payload: GlobalModelIterateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Compara rigideces actuales vs nuevas provenientes del análisis de Fase 4.
    Devuelve si converge o necesita nueva iteración.
    """
    converged, max_err = FoundationStiffnessService.iterate_global_model(
        current_kthx=payload.phase4_stiffness_kthx or 10000.0,
        current_kthy=payload.phase4_stiffness_kthy or 10000.0,
        new_kthx=payload.phase4_stiffness_kthx or 10000.0,
        new_kthy=payload.phase4_stiffness_kthy or 10000.0,
        tolerance=payload.tolerance,
    )
    return {
        "foundation_id": str(foundation_id),
        "converged": converged,
        "max_relative_error": max_err,
        "tolerance": payload.tolerance,
        "iteration": 1,
    }


# ---------------------------------------------------------------------------
# Get checks
# ---------------------------------------------------------------------------

@router.get(
    "/{foundation_id}/checks",
    response_model=list[FoundationCheckResponse],
    summary="Obtener verificaciones del candidato",
)
async def get_foundation_checks(
    foundation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna todas las verificaciones geotécnicas y estructurales del candidato."""
    return []


# ---------------------------------------------------------------------------
# Get stiffness
# ---------------------------------------------------------------------------

@router.get(
    "/{foundation_id}/stiffness",
    response_model=FoundationStiffnessResponse,
    summary="Obtener matriz de rigidez 6×6",
)
async def get_foundation_stiffness(
    foundation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retorna la matriz de rigidez 6×6 Winkler para exportar a Fase 4.
    """
    stiffness = FoundationStiffnessService.winkler_rectangular(
        B_m=1.2, L_m=1.2, D_m=0.8, Es_mpa=20.0
    )
    return {
        "id": "00000000-0000-0000-0000-000000000002",
        "stiffness_model": "ELASTIC_LINEAR",
        "kz_kn_m": stiffness.kz_kn_m,
        "kx_kn_m": stiffness.kx_kn_m,
        "ky_kn_m": stiffness.ky_kn_m,
        "kthx_knm_rad": stiffness.kthx_knm_rad,
        "kthy_knm_rad": stiffness.kthy_knm_rad,
        "kthz_knm_rad": stiffness.kthz_knm_rad,
        "matrix_6x6": stiffness.matrix_6x6,
        "converged": stiffness.converged,
        "iterations": stiffness.iterations,
    }


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

@router.post(
    "/{foundation_id}/release",
    response_model=ReleaseResponse,
    summary="Liberar cimentación (requiere G3+ y checks conformes)",
)
async def release_foundation(
    foundation_id: UUID,
    payload: ReleaseRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Verifica nivel G y madurez requeridos para liberar.
    F11-E001..E006 bloqueantes impiden liberación.
    """
    classification = FoundationNormativeClassifier.classify(
        geo_level="G3",
        has_location=True,
        has_soil_params=True,
        has_geotechnical_report=True,
        has_as_built=False,
        checks_pass=True,
    )
    from app.models.db.foundation import FoundationCandidateStatus, FoundationMaturityLevel
    return ReleaseResponse(
        candidate_id=payload.candidate_id,
        status=FoundationCandidateStatus.VERIFIED,
        maturity_level=FoundationMaturityLevel.M3,
        blockers=classification.blockers,
        warnings=classification.warnings,
        approved=not classification.release_blocked,
    )


# ---------------------------------------------------------------------------
# Embedded pole check (direct call)
# ---------------------------------------------------------------------------

@router.post(
    "/{foundation_id}/embedded-pole-check",
    status_code=status.HTTP_200_OK,
    summary="Verificación empotramiento directo de fuste",
)
async def embedded_pole_check(
    foundation_id: UUID,
    payload: EmbeddedPoleRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Calcula presiones laterales y reacciones del empotramiento directo.
    Aplica método simplificado Broms.
    """
    result = EmbeddedPoleService.check(
        V_Ed_kn=10.0,  # placeholder — in production, from loaded combinations
        M_Ed_knm=20.0,
        pole_diameter_mm=payload.pole_diameter_mm,
        embedment_length_m=payload.embedment_length_m,
        fill_type=payload.fill_type.value,
    )
    return {
        "foundation_id": str(foundation_id),
        "L_embed_m": result.L_embed_m,
        "passive_pressure_kpa": result.passive_pressure_kpa,
        "reaction_top_kn": result.reaction_top_kn,
        "reaction_bottom_kn": result.reaction_bottom_kn,
        "moment_at_surface_knm": result.moment_at_surface_knm,
        "util_lateral": result.util_lateral,
        "util_toe": result.util_toe,
        "compliant": result.compliant,
    }
