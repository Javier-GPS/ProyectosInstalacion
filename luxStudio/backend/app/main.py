from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import SessionLocal
from .routers import ldt, calculate, report, admin, projects, auth, tramos, users, catalog, external
from .services.auth import ensure_initial_admin

app = FastAPI(title="LUX Studio API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LuxStudio core
app.include_router(ldt.router, prefix="/api/ldt", tags=["LDT"])
app.include_router(calculate.router, prefix="/api", tags=["Calculate"])
app.include_router(report.router, prefix="/api/report", tags=["Report"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(tramos.router, tags=["Tramos"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/admin/users", tags=["Users"])
app.include_router(catalog.router, prefix="/api/admin", tags=["Catalog"])
app.include_router(external.router, tags=["External"])


@app.on_event("startup")
async def startup():
    db = SessionLocal()
    try:
        ensure_initial_admin(db)
        # Ensure tramos tables exist at startup, not per-request
        from .routers.tramos import _ensure_tramos_tables
        _ensure_tramos_tables()
    finally:
        db.close()


@app.get("/api/health")
async def health():
    return {"status": "ok"}

# ── GIS is now a separate microservice at ``gis-backend/`` ────────────────
# See ``gis-backend/app/main.py`` and ``docker-compose.yml`` service ``gis-backend``.
