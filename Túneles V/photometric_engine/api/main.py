"""
Salvi Photometric Engine — FastAPI application entry point.

Start with:
    uvicorn photometric_engine.api.main:app --reload --port 8080

Or via Docker Compose (see docker-compose.yml).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..db.database import create_tables
from .routers import calculations, photometries, tunnels


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (idempotent — uses CREATE IF NOT EXISTS)."""
    create_tables()
    yield


app = FastAPI(
    title="Salvi Photometric Engine",
    description=(
        "CIE 140:2019 road/tunnel luminance calculation engine.\n\n"
        "Implements:\n"
        "- CIE 140:2019 point-by-point luminance using CIE 144:2001 r-tables\n"
        "- CIE 88:2004 tunnel zone model (threshold / transition / interior)\n"
        "- Optic selection optimiser (F2MD / F2M2 / F151, APHEX S/M/L)\n"
        "- Radiosity inter-reflection engine for walls/ceiling\n"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tunnels.router)
app.include_router(calculations.router)
app.include_router(photometries.router)


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": "salvi-photometric-engine", "version": "1.0.0"}


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
