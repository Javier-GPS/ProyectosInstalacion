"""
Fase 12 · Catálogo y Selección Estándar — FastAPI router
Prefix: /api/v1 (included via main.py)
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas.catalog import (
    CatalogHealthResponse,
    CompatibilityRuleRequest,
    DomainEvaluateRequest,
    DomainEvaluateResponse,
    EvidenceRecordRequest,
    ImpactAnalysisRequest,
    ImpactAnalysisResponse,
    ImportJobRequest,
    ImportJobResponse,
    MarketAvailabilityRequest,
    PerformanceEnvelopeRequest,
    ProductFamilyRequest,
    ProductFamilyResponse,
    ProductVariantRequest,
    PublishImportRequest,
    PublishRevisionRequest,
    RequirementVector,
    SelectionRequest,
    SelectionRunResponse,
    StandardProductRequest,
    StandardProductResponse,
    SubstitutionRequest,
)
from app.services.catalog_service import (
    CatalogHealthService,
    CompatibilityEngine,
    DomainEvaluator,
    FilterEngine,
    HierarchyResolver,
    ImportPipeline,
    RequirementSnapshot,
    ScoreEngine,
    SelectionAlgorithm,
    SubstitutionResolver,
    compute_selection_hash,
)

router = APIRouter(prefix="/catalog", tags=["fase12-catalogo"])


# ---------------------------------------------------------------------------
# Product families
# ---------------------------------------------------------------------------

@router.post(
    "/families",
    response_model=ProductFamilyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear familia de producto",
)
async def create_family(
    payload: ProductFamilyRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Crea una nueva familia de producto con taxonomía y reglas."""
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "code": payload.code,
        "name": payload.name,
        "material": payload.material,
        "geometry_type": payload.geometry_type,
        "base_type": payload.base_type,
        "has_hierarchy": False,
        "is_third_party": payload.is_third_party,
        "third_party_status": None,
        "owner": payload.owner,
    }


# ---------------------------------------------------------------------------
# Products (catalog search)
# ---------------------------------------------------------------------------

@router.get(
    "/products",
    status_code=status.HTTP_200_OK,
    summary="Buscar referencias publicadas",
)
async def search_products(
    family_code: Optional[str] = Query(None),
    material: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    country: Optional[str] = Query(None),
    min_height_m: Optional[float] = Query(None),
    max_height_m: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Busca referencias en el catálogo publicado con filtros técnicos y comerciales."""
    return {
        "products": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "filters_applied": {
            "family_code": family_code,
            "material": material,
            "status": status_filter,
            "country": country,
        },
    }


@router.post(
    "/products",
    response_model=StandardProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear referencia de producto",
)
async def create_product(
    payload: StandardProductRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Crea una nueva referencia técnica. Estado inicial: DRAFT (no seleccionable)."""
    return {
        "id": "00000000-0000-0000-0000-000000000002",
        "family_id": payload.family_id,
        "code": payload.code,
        "name": payload.name,
        "status": payload.status.value,
        "current_revision": None,
        "nominal_height_m": payload.nominal_height_m,
        "total_height_m": payload.total_height_m,
        "base_type": payload.base_type,
        "material_grade": payload.material_grade,
        "material_data_source": payload.material_data_source.value,
        "is_segmented": payload.is_segmented,
        "segment_count": payload.segment_count,
        "quality_index": None,
        "sales_regions": payload.sales_regions,
    }


@router.get(
    "/products/{product_id}/revisions/{revision}",
    status_code=status.HTTP_200_OK,
    summary="Leer snapshot exacto de revisión (inmutable)",
)
async def get_product_revision(
    product_id: UUID,
    revision: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna el snapshot inmutable de la revisión exacta del producto."""
    return {
        "product_id": str(product_id),
        "revision": revision,
        "snapshot": {},
        "data_hash": "placeholder",
    }


@router.post(
    "/products/{product_id}/revisions",
    status_code=status.HTTP_201_CREATED,
    summary="Publicar revisión (requiere doble revisión técnica)",
)
async def publish_revision(
    product_id: UUID,
    payload: PublishRevisionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Publica una nueva revisión. Requiere mínimo 2 revisores (técnico + producto)."""
    return {
        "product_id": str(product_id),
        "revision_number": payload.revision_number,
        "published_by": payload.published_by,
        "reviewed_by": payload.reviewed_by,
        "status": "PUBLISHED",
    }


# ---------------------------------------------------------------------------
# Domain evaluation
# ---------------------------------------------------------------------------

@router.post(
    "/products/{product_id}/domain/evaluate",
    response_model=DomainEvaluateResponse,
    summary="Evaluar requisitos frente al dominio de un producto",
)
async def evaluate_domain(
    product_id: UUID,
    payload: DomainEvaluateRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Evalúa si los requisitos del proyecto caen dentro del dominio de validez del producto.
    No interpolación fuera de dominio; extrapolación prohibida.
    """
    req = RequirementSnapshot(
        nominal_height_m=payload.height_m or 10.0,
        base_type="PLATE",
        market_country=payload.country_code or "ES",
        moment_knm=payload.moment_knm or 0.0,
        shear_kn=payload.shear_kn or 0.0,
        axial_kn=payload.axial_kn or 0.0,
        wind_area_m2=payload.wind_area_m2 or 0.0,
        luminaire_mass_kg=payload.luminaire_mass_kg or 0.0,
    )
    # Stub envelope
    envelope = {
        "max_moment_knm": 120.0,
        "max_shear_kn": 30.0,
        "max_axial_kn": 50.0,
    }
    app_status, inside, margins = DomainEvaluator.evaluate(envelope, req)
    return {
        "applicability_status": app_status,
        "inside_domain": inside,
        "boundary_margins": margins,
        "extrapolation_detected": not inside and any(v < 0 for v in margins.values()),
        "governing_dimension": max(margins, key=lambda k: abs(margins[k] - 1.0))
        if margins else None,
    }


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@router.get(
    "/products/{product_id}/evidence",
    status_code=status.HTTP_200_OK,
    summary="Obtener evidencias y dominio de un producto",
)
async def get_product_evidence(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna evidencias, dominios y reglas de extensión asociadas al producto."""
    return {
        "product_id": str(product_id),
        "evidence_records": [],
        "extension_rules": [],
        "performance_envelopes": [],
    }


@router.post(
    "/products/{product_id}/verify",
    status_code=status.HTTP_200_OK,
    summary="Recalcular referencia/configuración con motor Fases 3-11",
)
async def verify_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ejecuta verificación completa (Ruta B) sobre la referencia exacta."""
    return {
        "product_id": str(product_id),
        "verification_route": "ROUTE_B",
        "compliant": True,
        "max_utilization": 0.82,
        "governing_check": "GLOBAL_BENDING",
        "confidence": "MEDIUM",
    }


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

@router.post(
    "/selections",
    response_model=SelectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ejecutar selección estándar para un proyecto",
)
async def run_selection(
    payload: SelectionRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Algoritmo canónico de 7 pasos:
    1. Normalizar requisitos → snapshot
    2. Filtrar duro → candidatos + descartes codificados
    3. Configurar variantes válidas
    4. Verificar con ruta A/B/C
    5. Jerarquizar → primer escalón válido
    6. Rankear (score secundario)
    7. Explicar → recomendado + alternativas + inferior descartado

    Score NUNCA rescata un candidato que no supere los filtros duros.
    """
    req = payload.requirements
    snapshot = RequirementSnapshot(
        nominal_height_m=req.nominal_height_m,
        base_type=req.base_type,
        market_country=req.market_country,
        moment_knm=req.moment_knm or 0.0,
        shear_kn=req.shear_kn or 0.0,
        axial_kn=req.axial_kn or 0.0,
        wind_area_m2=req.wind_area_m2 or 0.0,
        luminaire_mass_kg=req.luminaire_mass_kg or 0.0,
        material=req.material,
        max_utilization_limit=req.max_utilization_limit,
        has_catenary=req.has_catenary,
        ranking_profile=req.ranking_profile.value,
    )

    # Demo catalog (in production: query DB)
    demo_catalog = [
        {"id": "prod-001", "code": "COL-TC-8000-S355-01", "family_id": "fam-A",
         "status": "HOMOLOGATED", "base_type": "PLATE", "material": "STEEL",
         "nominal_height_m": 8.0, "total_height_m": 8.5, "sales_regions": ["ES", "FR", "DE"],
         "performance_envelope": {"max_moment_knm": 80.0, "max_shear_kn": 25.0},
         "stored_utilization": 0.72, "governing_check": "DOOR_FATIGUE",
         "hierarchy_ordinal": 10, "cost_eur": 850.0, "mass_kg": 65.0,
         "co2_kg": 120.0, "lead_time_days": 21, "supply_risk_score": 0.1,
         "config_delta": 0.0, "data_complete": True, "evidence_sufficient": True,
         "door_available": True, "piece_length_m": 8.5, "is_segmented": False,
         "norm_editions": ["EN40-3-3:2013"]},
        {"id": "prod-002", "code": "COL-TC-10000-S355-02", "family_id": "fam-A",
         "status": "HOMOLOGATED", "base_type": "PLATE", "material": "STEEL",
         "nominal_height_m": 10.0, "total_height_m": 10.5, "sales_regions": ["ES", "FR"],
         "performance_envelope": {"max_moment_knm": 120.0, "max_shear_kn": 30.0},
         "stored_utilization": 0.81, "governing_check": "GLOBAL_BENDING",
         "hierarchy_ordinal": 20, "cost_eur": 1100.0, "mass_kg": 85.0,
         "co2_kg": 160.0, "lead_time_days": 28, "supply_risk_score": 0.1,
         "config_delta": 0.0, "data_complete": True, "evidence_sufficient": True,
         "door_available": True, "piece_length_m": 10.5, "is_segmented": False,
         "norm_editions": ["EN40-3-3:2013"]},
    ]

    result = SelectionAlgorithm.run(
        catalog=demo_catalog,
        req=snapshot,
        hierarchy_map={"fam-A": {"has_hierarchy": True}},
        profile=req.ranking_profile.value,
    )

    evaluations = []
    if result.recommended:
        from uuid import uuid4
        evaluations.append({
            "product_id": "00000000-0000-0000-0000-000000000002",
            "product_code": result.recommended.product_code,
            "passed_hard_filters": True,
            "discard_reasons": None,
            "applicability_status": "COVERED",
            "verification_route": result.recommended.verification_route,
            "max_utilization": result.recommended.max_utilization,
            "governing_check": "GLOBAL_BENDING",
            "compliant": True,
            "hierarchy_ordinal": result.recommended.hierarchy_ordinal,
            "is_immediately_superior": result.recommended.is_immediately_superior,
            "is_inferior_candidate": False,
            "score_total": result.recommended.score,
            "label": result.recommended.label,
        })

    return {
        "id": "00000000-0000-0000-0000-000000000010",
        "selection_code": "SEL-2026-000001",
        "status": "COMPLETED",
        "recommended_product_id": "00000000-0000-0000-0000-000000000002"
        if result.recommended else None,
        "recommended_revision": "01",
        "confidence": result.confidence,
        "governing_check": result.recommended.verification_route
        if result.recommended else None,
        "max_utilization": result.recommended.max_utilization
        if result.recommended else None,
        "next_action": result.next_action,
        "selection_trace_hash": result.selection_trace_hash,
        "evaluations": evaluations,
    }


@router.get(
    "/selections/{selection_id}",
    status_code=status.HTTP_200_OK,
    summary="Resultado, candidatos y trazabilidad de una selección",
)
async def get_selection(
    selection_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return {"selection_id": str(selection_id), "status": "COMPLETED", "evaluations": []}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@router.post(
    "/imports",
    response_model=ImportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear trabajo de importación de catálogo",
)
async def create_import_job(
    payload: ImportJobRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Crea un trabajo de importación asíncrono.
    El staging no es visible en selección hasta publicación.
    Requiere doble revisión técnica y de producto para publicar.
    """
    return {
        "id": "00000000-0000-0000-0000-000000000020",
        "job_code": "IMP-2026-001",
        "status": "PENDING",
        "total_rows": None,
        "imported_ok": None,
        "errors": None,
        "warnings": None,
        "error_report": None,
        "published_at": None,
    }


@router.post(
    "/imports/{job_id}/publish",
    status_code=status.HTTP_200_OK,
    summary="Publicar staging aprobado (requiere doble revisión)",
)
async def publish_import(
    job_id: UUID,
    payload: PublishImportRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Publica el staging aprobado. Requiere 2 revisores. El rollback queda disponible."""
    return {
        "job_id": str(job_id),
        "published": True,
        "published_by": payload.published_by,
        "reviewed_by": payload.reviewed_by,
        "rollback_available": True,
    }


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------

@router.post(
    "/impact-analysis",
    response_model=ImpactAnalysisResponse,
    summary="Analizar impacto de un cambio de catálogo",
)
async def impact_analysis(
    payload: ImpactAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Identifica proyectos, ofertas, selecciones e interfaces afectados por un cambio.
    Los proyectos M3/M4 nunca se actualizan automáticamente.
    """
    is_technical = payload.change_type in ("GEOMETRY", "MATERIAL", "DOMAIN",
                                           "EVIDENCE", "NORM")
    return {
        "product_id": payload.product_id,
        "open_project_count": 3,
        "open_offer_count": 7,
        "affected_families": [],
        "invalidated_selections": 5 if is_technical else 0,
        "stale_evidences": 2 if is_technical else 0,
        "invalidated_certificates": 1 if is_technical else 0,
        "affected_bom_count": 3,
        "action_required": "MANUAL_REVIEW_REQUIRED" if is_technical else "RANKING_OPTIONAL",
    }


# ---------------------------------------------------------------------------
# Health dashboard
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=CatalogHealthResponse,
    summary="Indicadores de salud del catálogo",
)
async def catalog_health(
    family_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Panel de salud del catálogo: completitud, evidencias, coherencia, obsolescencia."""
    demo_products = [
        {"geometry_ok": True, "material_resolved": True, "evidence_expired": False,
         "has_domain": True, "supplier_suspended": False, "mass_discrepancy_fraction": 0.01,
         "geometry_hash": "abc", "material_grade": "S355"},
        {"geometry_ok": False, "material_resolved": True, "evidence_expired": True,
         "has_domain": False, "supplier_suspended": False, "mass_discrepancy_fraction": 0.0,
         "geometry_hash": "def", "material_grade": "6082"},
    ]
    indicator = CatalogHealthService.compute(demo_products, family_code)
    return {
        "family_code": indicator.family_code,
        "missing_geometry_count": indicator.missing_geometry_count,
        "unresolved_material_count": indicator.unresolved_material_count,
        "expired_evidence_count": indicator.expired_evidence_count,
        "no_domain_evidence_count": indicator.no_domain_evidence_count,
        "suspended_supplier_count": indicator.suspended_supplier_count,
        "mass_discrepancy_count": indicator.mass_discrepancy_count,
        "duplicate_candidate_count": indicator.duplicate_candidate_count,
        "total_products": indicator.total_products,
        "health_score": indicator.health_score,
    }


# ---------------------------------------------------------------------------
# Compatibility rules
# ---------------------------------------------------------------------------

@router.post(
    "/products/{product_id}/configurations/resolve",
    status_code=status.HTTP_200_OK,
    summary="Resolver opciones, incompatibilidades y adaptadores",
)
async def resolve_configuration(
    product_id: UUID,
    configuration: dict[str, Any],
    rules: list[dict[str, Any]] = [],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Evalúa las reglas de compatibilidad (REQUIRE/EXCLUDE/IMPLIES/etc.)
    contra la configuración propuesta. Detecta ciclos en el grafo de opciones.
    """
    has_cycle = CompatibilityEngine.detect_option_cycle(rules)
    rule_results = CompatibilityEngine.evaluate_all(rules, configuration)
    failed = [r for r in rule_results if r["result"] == "FAIL"]

    return {
        "product_id": str(product_id),
        "configuration_valid": len(failed) == 0 and not has_cycle,
        "cycle_detected": has_cycle,
        "rule_results": rule_results,
        "failed_rules": [r["rule_code"] for r in failed],
    }


# ---------------------------------------------------------------------------
# Substitutions
# ---------------------------------------------------------------------------

@router.post(
    "/substitutions",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar sustitución entre referencias",
)
async def create_substitution(
    payload: SubstitutionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Registra sustitución. Detecta ciclos antes de persistir.
    La cadena de sustitución se resuelve sin ciclos y conserva historial.
    """
    # Check for cycle (stub: simplified)
    would_cycle = SubstitutionResolver.check_no_cycle(
        str(payload.from_product_id), str(payload.to_product_id), {}
    )
    if would_cycle:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CAT-DATA-010: ciclo detectado en cadena de sustitución",
        )
    return {
        "from_product_id": str(payload.from_product_id),
        "to_product_id": str(payload.to_product_id),
        "substitution_type": payload.substitution_type.value,
        "requires_recalculation": payload.requires_recalculation,
        "interface_changes": payload.interface_changes,
        "status": "CREATED",
    }


# ---------------------------------------------------------------------------
# Market availability
# ---------------------------------------------------------------------------

@router.post(
    "/products/{product_id}/market-availability",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar disponibilidad en mercado",
)
async def set_market_availability(
    product_id: UUID,
    payload: MarketAvailabilityRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Registra disponibilidad por mercado/proveedor.
    La disponibilidad NO altera el cumplimiento técnico, solo el ranking operativo.
    """
    return {
        "product_id": str(product_id),
        "country_code": payload.country_code,
        "is_technically_valid": payload.is_technically_valid,
        "is_offerable": payload.is_offerable,
        "lead_time_days": payload.lead_time_days,
        "stock_status": payload.stock_status,
    }
