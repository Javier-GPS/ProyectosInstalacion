"""
Salvi Studio · Columns — Fase 17: API de Validación Industrial
7 endpoints HTTP 501 (Not Implemented) — implementación futura de la capa de BD.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/validation-plans", tags=["validation"])
phys_router = APIRouter(prefix="/physical-tests", tags=["validation"])
corr_router = APIRouter(prefix="/correlations", tags=["validation"])
qual_router = APIRouter(prefix="/qualification-domains", tags=["validation"])
gate_router = APIRouter(prefix="/release-gates", tags=["validation"])
runs_router = APIRouter(prefix="/test-runs", tags=["validation"])
trace_router = APIRouter(prefix="/traceability", tags=["validation"])

_501 = JSONResponse(
    status_code=501,
    content={"error": "not_implemented", "message": "Fase 17 — endpoint pendiente de implementación."},
)


# POST /api/v1/validation-plans
@router.post("", status_code=501)
async def create_validation_plan(body: dict):
    return _501


# POST /api/v1/test-runs
@runs_router.post("", status_code=501)
async def create_test_run(body: dict):
    return _501


# POST /api/v1/physical-tests/{id}/datasets
@phys_router.post("/{physical_test_id}/datasets", status_code=501)
async def create_physical_test_dataset(physical_test_id: str, body: dict):
    return _501


# POST /api/v1/correlations
@corr_router.post("", status_code=501)
async def create_correlation(body: dict):
    return _501


# POST /api/v1/qualification-domains/evaluate
@qual_router.post("/evaluate", status_code=501)
async def evaluate_qualification_domain(body: dict):
    return _501


# POST /api/v1/release-gates/{id}/decision
@gate_router.post("/{gate_id}/decision", status_code=501)
async def release_gate_decision(gate_id: str, body: dict):
    return _501


# GET /api/v1/traceability/requirements/{id}
@trace_router.get("/requirements/{req_id}", status_code=501)
async def get_traceability_requirement(req_id: str):
    return _501
