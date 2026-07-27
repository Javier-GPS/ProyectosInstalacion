from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import SessionLocal
from .routers import ldt, calculate, report, admin, projects, auth, tramos, catalog
from .routers.deps import ensure_users_table

app = FastAPI(title="LUX Studio API", version="0.2.0")

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
app.include_router(catalog.router, prefix="/api/admin", tags=["Catalog"])


@app.on_event("startup")
async def startup():
    ensure_users_table()
    # Ensure tramos tables exist at startup, not per-request
    from .routers.tramos import _ensure_tramos_tables
    _ensure_tramos_tables()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
