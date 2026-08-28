"""GIS — FastAPI application (microservice).

Serves SALVI GIS endpoints independently from LuxStudio.
Shares the same PostgreSQL database (``gis_*`` tables).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core.config import settings
from .core.database import engine
from .core.redis import close_redis, init_redis
from .models import ensure_gis_tables
from .routers import auth, zones, luminaires, photometric, exports, admin, lux_jobs
from .routers.deps import ensure_users_table


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init Redis on start, close on shutdown."""
    ensure_users_table()
    ensure_gis_tables()
    await init_redis()
    yield
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# Compress responses >1KB (big JSON inventories)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)

# Routers
app.include_router(auth.router, tags=["Auth"])
app.include_router(zones.router, tags=["Zones, OSM, Nominatim"])
app.include_router(luminaires.router, tags=["Luminaires & Inventory"])
app.include_router(photometric.router, tags=["Photometric"])
app.include_router(exports.router, tags=["Exports"])
app.include_router(admin.router, tags=["Admin, AI, DB"])
app.include_router(lux_jobs.router, tags=["Lux jobs"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "gis-backend"}
