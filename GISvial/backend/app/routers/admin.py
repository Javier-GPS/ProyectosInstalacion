"""Admin — UI config, AI proxy, DB query."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.database import engine, get_db
from ..models import (
    GisProjectUiConfig, GisZone, GisZoneConfig, GisZoneOsmData,
    GisLuminaire, Project, User, ensure_gis_tables,
)
from ..services.anthropic import ask_claude
from .deps import current_user

router = APIRouter()


def _parse_json(v, default=None):
    if v is None:
        return default if default is not None else {}
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, str):
        try:
            return __import__("json").loads(v)
        except Exception:
            return default if default is not None else {}
    return v


# ── UI Config ─────────────────────────────────────────────────────────────
@router.get("/api/projects/{project_id}/ui-config")
async def gis_ui_config_get(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    rows = db.query(GisProjectUiConfig).filter(GisProjectUiConfig.project_id == project_id).all()
    return {r.config_key: r.config_value for r in rows}


@router.put("/api/projects/{project_id}/ui-config")
async def gis_ui_config_put(project_id: int, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    for key, value in body.items():
        existing = db.query(GisProjectUiConfig).filter(
            GisProjectUiConfig.project_id == project_id,
            GisProjectUiConfig.config_key == key,
        ).first()
        data = value if isinstance(value, dict) else {"value": value}
        if existing:
            existing.config_value = data
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(GisProjectUiConfig(project_id=project_id, config_key=key, config_value=data))
    db.commit()
    return {"ok": True}


# ── AI — Anthropic ────────────────────────────────────────────────────────
_DB_SCHEMA_SUMMARY = """
ESQUEMA DE LA BASE DE DATOS (PostgreSQL):
- projects(id, project_name, client, location, ...)
- gis_zones(id, name, type, color, ...)
- gis_zone_config(zone_id, spacing[m], watt_hps, watt_led, ...)
- gis_zone_osm_data(zone_id, km_by_type[JSON], ways[JSON], source)
- gis_luminaires(id, zone_id, road_type, lighting_class, lat, lon, watts, ...)
- gis_inventory_luminaires(id, zone_id, lat, lon, power_w, ...)
- gis_photometric_results(id, zone_id, segment_name, match_key, road_width, spacing, ...)
"""


@router.post("/api/ai/ask")
async def gis_ai_ask(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_id = body.get("project_id")
    question = body.get("question", "")
    if not question:
        raise HTTPException(status_code=400, detail="question required")

    context_parts = [_DB_SCHEMA_SUMMARY.strip(), ""]
    if project_id:
        proj = db.get(Project, project_id)
        if proj:
            context_parts.append(f"PROYECTO: {proj.project_name} (id={proj.id})")
            zones = db.query(GisZone).filter(GisZone.project_id == proj.id).all()
            for z in zones:
                osm = db.get(GisZoneOsmData, z.id)
                km_by_type = _parse_json(osm.km_by_type if osm else None, {})
                lum_count = db.query(GisLuminaire).filter(GisLuminaire.zone_id == z.id).count()
                total_km = sum(float(v) for v in km_by_type.values() if v)
                cfg = db.get(GisZoneConfig, z.id)
                sp = cfg.spacing if cfg else 30
                wl = cfg.watt_led if cfg else 60
                hr = cfg.hours_night if cfg else 11.5
                n_est = int(total_km * 1000 / sp) if sp else 0
                kw_tot = n_est * wl / 1000
                mwh_yr = kw_tot * hr * 365 / 1000
                context_parts.append(f"\nZONA: {z.name} (id={z.id})")
                if km_by_type:
                    for t, km in sorted(km_by_type.items(), key=lambda x: -float(x[1] or 0)):
                        if km:
                            context_parts.append(f"  - {t}: {float(km):.2f} km")
                    context_parts.append(f"  Total red: {total_km:.2f} km")
                context_parts.append(f"  Config: espaciado={sp}m, LED={wl}W, {hr}h/noche")
                context_parts.append(f"  Lums: {n_est} est | {kw_tot:.1f} kW | {mwh_yr:.1f} MWh/ano")
                if lum_count:
                    context_parts.append(f"  Lums disenadas: {lum_count}")

    try:
        result = ask_claude(question, "\n".join(context_parts))
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── DB query (safe read-only SQL) ─────────────────────────────────────────
@router.post("/api/db/query")
async def gis_db_query(body: dict, user: User = Depends(current_user)):
    sql = body.get("query", "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="query required")
    upper = sql.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise HTTPException(status_code=400, detail="Solo SELECT o WITH")
    if sql.count(";") > 1 or (sql.endswith(";") and sql[:-1].count(";") > 0):
        raise HTTPException(status_code=400, detail="Multiples sentencias no permitidas")
    with engine.connect() as conn:
        result = conn.exec_driver_sql(sql)
        cols = list(result.keys()) if result.keys() else []
        rows_data = [list(r) for r in result.fetchmany(500)]
    return {"columns": cols, "rows": rows_data}
