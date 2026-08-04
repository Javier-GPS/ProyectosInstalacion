"""
Salvi Studio · Columns — API Fase 4: Motor Estructural Común

Endpoints:
  POST   /structural-models                    Construir modelo desde snapshot
  GET    /structural-models/{id}               Leer resumen y diagnósticos
  POST   /structural-models/{id}/validate      Validar conectividad y física
  POST   /analysis-runs                        Crear ejecución
  GET    /analysis-runs/{id}                   Estado, progreso y resumen
  POST   /analysis-runs/{id}/cancel            Solicitar cancelación
  GET    /analysis-runs/{id}/results           Resultados paginados/filtrados
  GET    /analysis-runs/{id}/envelopes         Envolventes
  GET    /analysis-runs/{id}/diagnostics       Logs técnicos y warnings
  POST   /analysis-runs/{id}/export            Exportar modelo/resultados neutros
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_session
from app.models.schemas.structural import (
    StructuralModelCreate, StructuralModelSummary, ModelValidationResult,
    AnalysisRunCreate, AnalysisRunSummary, AnalysisRunManifest,
    NodalResultResponse, SectionResultResponse, ModalResultResponse,
    BucklingResultResponse, EnvelopeResponse, EnvelopeFilter,
    DiagnosticEventResponse, ExportRequest, ExportResponse, RunCompareResponse,
    ResultsFilter,
)
from app.models.db.structural import (
    EnvelopeScope, StructuralRunStatus,
)
from app.services.structural_service import (
    ModelBuilderService, StructuralValidationService, StructuralRunService,
)

router = APIRouter(prefix="/structural", tags=["structural"])

ACTOR_ROLE = "ENGINEER"   # En producción: extraer del JWT


# ── Construcción del modelo ────────────────────────────────────────────────────

@router.post(
    "/models",
    response_model=StructuralModelSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Construir modelo estructural desde snapshot de F2+F3",
)
async def create_structural_model(
    data: StructuralModelCreate,
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = ModelBuilderService(session)
    model = await svc.build(data, ACTOR_ROLE)
    return StructuralModelSummary.model_validate(model)


@router.get(
    "/models/{model_id}",
    response_model=StructuralModelSummary,
    summary="Leer resumen del modelo estructural",
)
async def get_structural_model(
    model_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Any:
    from sqlalchemy import select
    from app.models.db.structural import StructuralModel
    stmt = select(StructuralModel).where(StructuralModel.id == model_id)
    model = (await session.execute(stmt)).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Modelo estructural no encontrado")
    return StructuralModelSummary.model_validate(model)


@router.post(
    "/models/{model_id}/validate",
    response_model=ModelValidationResult,
    summary="Validar conectividad y coherencia física del modelo",
)
async def validate_structural_model(
    model_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = StructuralValidationService(session)
    return await svc.validate(model_id)


# ── Ejecuciones de análisis ────────────────────────────────────────────────────

@router.post(
    "/runs",
    response_model=AnalysisRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear ejecución de análisis estructural (encolada)",
)
async def create_analysis_run(
    data: AnalysisRunCreate,
    idempotency_key: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Any:
    if idempotency_key:
        data.idempotency_key = idempotency_key
    svc = StructuralRunService(session)
    run = await svc.create_run(data, ACTOR_ROLE)
    return AnalysisRunSummary.model_validate(run)


@router.get(
    "/runs/{run_id}",
    response_model=AnalysisRunSummary,
    summary="Estado y resumen de la ejecución",
)
async def get_analysis_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = StructuralRunService(session)
    run = await svc.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")
    return AnalysisRunSummary.model_validate(run)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=AnalysisRunSummary,
    summary="Solicitar cancelación de ejecución en curso",
)
async def cancel_analysis_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = StructuralRunService(session)
    try:
        run = await svc.request_cancel(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return AnalysisRunSummary.model_validate(run)


# ── Resultados ────────────────────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}/results/nodal",
    response_model=list[NodalResultResponse],
    summary="Resultados nodales (desplazamientos, giros, reacciones)",
)
async def get_nodal_results(
    run_id: uuid.UUID,
    load_case_ref: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> Any:
    from sqlalchemy import select
    from app.models.db.structural import NodalResult
    stmt = select(NodalResult).where(NodalResult.run_id == run_id)
    if load_case_ref:
        stmt = stmt.where(NodalResult.load_case_ref == load_case_ref)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return [NodalResultResponse.model_validate(r) for r in rows]


@router.get(
    "/runs/{run_id}/results/sections",
    response_model=list[SectionResultResponse],
    summary="Esfuerzos internos por sección y caso",
)
async def get_section_results(
    run_id: uuid.UUID,
    load_case_ref: Optional[str] = Query(default=None),
    z_min_m: Optional[float] = Query(default=None),
    z_max_m: Optional[float] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> Any:
    from sqlalchemy import select
    from app.models.db.structural import SectionResult
    stmt = select(SectionResult).where(SectionResult.run_id == run_id)
    if load_case_ref:
        stmt = stmt.where(SectionResult.load_case_ref == load_case_ref)
    if z_min_m is not None:
        stmt = stmt.where(SectionResult.z_global_m >= z_min_m)
    if z_max_m is not None:
        stmt = stmt.where(SectionResult.z_global_m <= z_max_m)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return [SectionResultResponse.model_validate(r) for r in rows]


@router.get(
    "/runs/{run_id}/results/modal",
    response_model=list[ModalResultResponse],
    summary="Resultados modales: frecuencias, periodos y masas participantes",
)
async def get_modal_results(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Any:
    from sqlalchemy import select
    from app.models.db.structural import ModalResult
    stmt = select(ModalResult).where(
        ModalResult.run_id == run_id
    ).order_by(ModalResult.mode_number)
    rows = (await session.execute(stmt)).scalars().all()
    return [ModalResultResponse.model_validate(r) for r in rows]


@router.get(
    "/runs/{run_id}/results/buckling",
    response_model=list[BucklingResultResponse],
    summary="Factores críticos de estabilidad elástica",
)
async def get_buckling_results(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Any:
    from sqlalchemy import select
    from app.models.db.structural import BucklingResult
    stmt = select(BucklingResult).where(
        BucklingResult.run_id == run_id
    ).order_by(BucklingResult.mode_number)
    rows = (await session.execute(stmt)).scalars().all()
    return [BucklingResultResponse.model_validate(r) for r in rows]


# ── Envolventes ───────────────────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}/envelopes",
    response_model=list[EnvelopeResponse],
    summary="Envolventes de esfuerzos con procedencia completa",
)
async def get_envelopes(
    run_id: uuid.UUID,
    scope: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    sign: Optional[str] = Query(default=None, regex="^(max|min)$"),
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = StructuralRunService(session)
    filter_obj = EnvelopeFilter(
        scope=EnvelopeScope(scope) if scope else None,
        quantity=quantity,
        sign=sign,
    )
    envelopes = await svc.get_envelopes(run_id, filter_obj)
    return [EnvelopeResponse.model_validate(e) for e in envelopes]


# ── Diagnósticos ──────────────────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}/diagnostics",
    response_model=list[DiagnosticEventResponse],
    summary="Logs técnicos y warnings de la ejecución",
)
async def get_diagnostics(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = StructuralRunService(session)
    events = await svc.get_diagnostics(run_id)
    return [DiagnosticEventResponse.model_validate(e) for e in events]


# ── Exportación ───────────────────────────────────────────────────────────────

@router.post(
    "/runs/{run_id}/export",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Exportar modelo neutro para contraste externo",
)
async def export_model(
    run_id: uuid.UUID,
    request: ExportRequest,
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = StructuralRunService(session)
    try:
        export = await svc.export(run_id, request, ACTOR_ROLE)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ExportResponse.model_validate(export)


# ── Comparación de ejecuciones ────────────────────────────────────────────────

@router.get(
    "/runs/{run_id}/compare",
    response_model=RunCompareResponse,
    summary="Comparar dos ejecuciones (reproducibilidad y convergencia)",
)
async def compare_runs(
    run_id: uuid.UUID,
    other_run_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    svc = StructuralRunService(session)
    try:
        return await svc.compare_runs(run_id, other_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
