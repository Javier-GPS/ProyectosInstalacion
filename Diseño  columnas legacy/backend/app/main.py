"""
Salvi Studio · Columns — Aplicación FastAPI principal
Fase 1: Núcleo de proyecto, revisiones y bibliotecas maestras.
"""
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.core.config import settings
from app.api.v1 import projects, auth, users, libraries, units, geometry, actions, structural, steel, aluminium, concrete, details, joints, baseplate, foundation, catalog, optimization, cad_bom, reports, catenary, validation

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("salvi_columns_startup", version=settings.app_version, env=settings.environment)
    yield
    logger.info("salvi_columns_shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API para diseño, cálculo, selección y definición industrial de "
        "columnas de alumbrado público. Fase 1: Núcleo de proyecto y revisiones."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Correlation ID middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


# ── Manejador de error global (P-05: fallo seguro) ───────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", exc=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "Error interno. Contacte con soporte indicando el X-Correlation-ID.",
        },
    )


# ── Routers v1 ───────────────────────────────────────────────────────────────
API_V1 = "/api/v1"
app.include_router(auth.router, prefix=API_V1)
app.include_router(users.router, prefix=API_V1)
app.include_router(projects.router, prefix=API_V1)
app.include_router(libraries.router, prefix=API_V1)
app.include_router(units.router, prefix=API_V1)
app.include_router(geometry.router, prefix=API_V1)
app.include_router(actions.router, prefix=API_V1)
app.include_router(structural.router, prefix=API_V1)
app.include_router(steel.router, prefix=API_V1)
app.include_router(aluminium.router, prefix=API_V1)
app.include_router(concrete.router, prefix=API_V1)
app.include_router(details.router, prefix=API_V1)
app.include_router(joints.router, prefix=API_V1)
app.include_router(baseplate.router, prefix=API_V1)
app.include_router(foundation.router, prefix=API_V1)
app.include_router(catalog.router, prefix=API_V1)
app.include_router(optimization.router, prefix=API_V1)
app.include_router(cad_bom.router, prefix=API_V1)
app.include_router(reports.router, prefix=API_V1)
app.include_router(catenary.router, prefix=API_V1)
app.include_router(catenary.runs_router, prefix=API_V1)
app.include_router(validation.router, prefix=API_V1)
app.include_router(validation.runs_router, prefix=API_V1)
app.include_router(validation.phys_router, prefix=API_V1)
app.include_router(validation.corr_router, prefix=API_V1)
app.include_router(validation.qual_router, prefix=API_V1)
app.include_router(validation.gate_router, prefix=API_V1)
app.include_router(validation.trace_router, prefix=API_V1)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "version": settings.app_version, "env": settings.environment}





@app.get("/", include_in_schema=False)
async def root():
    return {"name": settings.app_name, "docs": "/docs"}
