"""
Salvi Studio · Columns — Fase 16: API de Catenarias y Alumbrado Suspendido.
9 endpoints HTTP 501 (implementación en M1).
"""
import uuid
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/cable-systems", tags=["cable-systems"])

_NOT_IMPL = {"detail": "Not implemented — Fase 16 M1 pendiente."}


@router.post("", status_code=501)
async def create_cable_system(payload: dict):
    """POST /cable-systems — Crear un sistema de catenarias."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


@router.post("/{system_id}/interpret", status_code=501)
async def interpret_cable_system(system_id: uuid.UUID, payload: dict):
    """POST /cable-systems/{id}/interpret — Interpretar texto NL del usuario."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


@router.post("/{system_id}/validate", status_code=501)
async def validate_cable_system(system_id: uuid.UUID):
    """POST /cable-systems/{id}/validate — Validar geometría y topología."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


@router.post("/{system_id}/analyze", status_code=501)
async def analyze_cable_system(system_id: uuid.UUID, payload: dict):
    """POST /cable-systems/{id}/analyze — Lanzar análisis no lineal."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


@router.post("/{system_id}/couple", status_code=501)
async def couple_cable_system(system_id: uuid.UUID, payload: dict):
    """POST /cable-systems/{id}/couple — Acoplamiento cable-columna."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


@router.post("/{system_id}/optimize", status_code=501)
async def optimize_cable_system(system_id: uuid.UUID, payload: dict):
    """POST /cable-systems/{id}/optimize — Generar alternativas Pareto."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


@router.post("/{system_id}/as-built", status_code=501)
async def register_as_built(system_id: uuid.UUID, payload: dict):
    """POST /cable-systems/{id}/as-built — Registrar mediciones reales."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


# ── Runs de análisis (prefijo independiente) ──────────────────────────────────

runs_router = APIRouter(prefix="/cable-analysis-runs", tags=["cable-systems"])


@runs_router.get("/{run_id}", status_code=501)
async def get_analysis_run(run_id: uuid.UUID):
    """GET /cable-analysis-runs/{runId} — Estado y resultados del run."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)


@runs_router.post("/{run_id}/report", status_code=501)
async def generate_run_report(run_id: uuid.UUID):
    """POST /cable-analysis-runs/{runId}/report — Generar informe de análisis."""
    return JSONResponse(status_code=501, content=_NOT_IMPL)
