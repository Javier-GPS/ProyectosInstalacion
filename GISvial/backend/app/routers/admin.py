"""Admin — UI config, AI proxy, DB query (read-only with parameterized queries)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import (
    GisProjectUiConfig, GisZone, GisZoneConfig, GisZoneOsmData,
    GisLuminaire, GisProjectMembership, Project,
)
from ..services.anthropic import ask_claude
from .deps import current_principal, Principal
from ..services.access import project_for

router = APIRouter()


# ── Projects CRUD ─────────────────────────────────────────────────────────
@router.get("/api/projects")
async def gis_projects_list(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    query = db.query(Project)
    if principal.user.role != "ADMIN":
        owned = db.query(Project.id).filter(Project.owner_user_id == principal.user.id)
        member = db.query(GisProjectMembership.project_id).filter(
            GisProjectMembership.issuer == principal.issuer,
            GisProjectMembership.subject == principal.subject,
            GisProjectMembership.active.is_(True),
        )
        query = query.filter(Project.id.in_(owned.union(member)))
    rows = query.order_by(Project.created_at.desc()).all()
    memberships = {
        row.project_id: row.role
        for row in db.query(GisProjectMembership).filter(
            GisProjectMembership.issuer == principal.issuer,
            GisProjectMembership.subject == principal.subject,
            GisProjectMembership.active.is_(True),
        ).all()
    }
    return [{
        "id": str(r.id),
        "name": r.project_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "access_role": "admin" if principal.user.role == "ADMIN"
        else "owner" if r.owner_user_id == principal.user.id
        else memberships.get(r.id, "viewer"),
    } for r in rows]


@router.post("/api/projects", status_code=201)
async def gis_projects_create(body: dict, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    proj = Project(project_name=name, owner_user_id=principal.user.id)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return {"id": str(proj.id), "name": proj.project_name, "created_at": proj.created_at.isoformat() if proj.created_at else None}


@router.delete("/api/projects/{project_id}", status_code=204)
async def gis_projects_delete(project_id: int, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_for(principal, db, project_id, write=True)
    db.delete(proj)
    db.commit()


# ── UI Config ─────────────────────────────────────────────────────────────
@router.get("/api/projects/{project_id}/ui-config")
async def gis_ui_config_get(project_id: int, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_for(principal, db, project_id)
    rows = db.query(GisProjectUiConfig).filter(GisProjectUiConfig.project_id == project_id).all()
    return {r.config_key: r.config_value for r in rows}


@router.put("/api/projects/{project_id}/ui-config")
async def gis_ui_config_put(project_id: int, body: dict, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_for(principal, db, project_id, write=True)
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


@router.get("/api/projects/{project_id}/members")
async def gis_project_members(
    project_id: int,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project = project_for(principal, db, project_id)
    if principal.user.role != "ADMIN" and project.owner_user_id != principal.user.id:
        raise HTTPException(status_code=403, detail="Project owner required")
    rows = db.query(GisProjectMembership).filter(GisProjectMembership.project_id == project_id).all()
    return [{"id": row.id, "issuer": row.issuer, "subject": row.subject, "role": row.role, "active": row.active} for row in rows]


@router.post("/api/projects/{project_id}/members", status_code=201)
async def gis_project_member_upsert(
    project_id: int,
    body: dict,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project = project_for(principal, db, project_id)
    if principal.user.role != "ADMIN" and project.owner_user_id != principal.user.id:
        raise HTTPException(status_code=403, detail="Project owner required")
    issuer = str(body.get("issuer") or "").strip()
    subject = str(body.get("subject") or "").strip()
    role = str(body.get("role") or "editor").strip().lower()
    if not issuer or not subject or role not in {"viewer", "editor"}:
        raise HTTPException(status_code=422, detail="issuer, subject and role are required")
    row = db.query(GisProjectMembership).filter(
        GisProjectMembership.project_id == project_id,
        GisProjectMembership.issuer == issuer,
        GisProjectMembership.subject == subject,
    ).first()
    if row is None:
        row = GisProjectMembership(project_id=project_id, issuer=issuer, subject=subject, role=role, active=True)
        db.add(row)
    else:
        row.role = role
        row.active = True
    db.commit()
    db.refresh(row)
    return {"id": row.id, "issuer": row.issuer, "subject": row.subject, "role": row.role, "active": row.active}


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
async def gis_ai_ask(body: dict, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_id = body.get("project_id")
    question = body.get("question", "")
    if not question:
        raise HTTPException(status_code=400, detail="question required")
    if project_id:
        project_for(principal, db, int(project_id))

    context_parts = [_DB_SCHEMA_SUMMARY.strip(), ""]
    if project_id:
        proj = db.get(Project, project_id)
        if proj:
            context_parts.append(f"PROYECTO: {proj.project_name} (id={proj.id})")
            zones = db.query(GisZone).filter(GisZone.project_id == proj.id).all()
            for z in zones:
                osm = db.get(GisZoneOsmData, z.id)
                km_by_type = osm.km_by_type if osm else {}
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


# ── Legacy DB query (REMOVED — SQL injection risk) ────────────────────────
# The old /api/db/query endpoint was removed because its SELECT filter was
# trivially bypassable (e.g. `SELECT 1; DROP TABLE users`). If read-only
# SQL access is needed, implement it via parameterized queries with a strict
# allowlist of safe query templates.

