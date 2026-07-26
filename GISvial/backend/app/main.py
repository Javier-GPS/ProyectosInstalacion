"""GIS — FastAPI application (microservice).

Serves SALVI GIS endpoints independently from LuxStudio.
Shares the same PostgreSQL database (``gis_*`` tables).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.database import engine
from .models import ensure_gis_tables
from .routers import auth, zones, luminaires, photometric, exports, admin

app = FastAPI(title=settings.app_name, version=settings.app_version)

# CORS
origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, tags=["Auth & Users"])
app.include_router(zones.router, tags=["Zones, OSM, Nominatim"])
app.include_router(luminaires.router, tags=["Luminaires & Inventory"])
app.include_router(photometric.router, tags=["Photometric"])
app.include_router(exports.router, tags=["Exports"])
app.include_router(admin.router, tags=["Admin, AI, DB"])


@app.on_event("startup")
async def startup():
    ensure_gis_tables()


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gis-backend"}


@app.get("/api/gis/health")
async def gis_health():
    return {"status": "ok", "service": "gis-backend", "version": settings.app_version}
