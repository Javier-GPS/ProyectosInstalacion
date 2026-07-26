"""Zones — CRUD, OSM, config, trees, Nominatim."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import (
    GisZone, GisZoneConfig, GisZoneOsmData, GisZoneTrees, User, ensure_gis_tables,
)
from ..schemas.zones import GisCreateZoneBody
from ..services.nominatim import search as _nom_search, reverse as _nom_reverse
from .deps import current_user

router = APIRouter()

DEFAULT_COLORS = [
    '#4caf82', '#e67e22', '#3498db', '#9b59b6', '#e74c3c',
    '#1abc9c', '#f39c12', '#2980b9', '#8e44ad', '#c0392b',
]


def _fval(v):
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _zone_to_dict(z: GisZone, spacing: int = 30) -> dict:
    return {
        "id": z.id, "name": z.name, "type": z.type or "",
        "color": z.color or DEFAULT_COLORS[0],
        "priority": z.priority if z.priority is not None else 2,
        "center_lat": z.center_lat, "center_lon": z.center_lon,
        "zoom": z.zoom if z.zoom is not None else 12,
        "bbox": z.bbox or "", "description": z.description or "",
        "corridors": z.corridors or [],
        "bounds_polygon": z.bounds_polygon or [],
        "est": z.est or {},
        "source": z.source or "manual", "project_id": z.project_id,
        "created_at": z.created_at.isoformat() if z.created_at else None,
        "spacing": spacing,
    }


# ── Nominatim proxy ─────────────────────────────────────────────────────
@router.get("/api/nominatim/search")
async def gis_nominatim_search(q: str = Query(...), featuretype: Optional[str] = None):
    try:
        return _nom_search(q, featuretype)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/nominatim/reverse")
async def gis_nominatim_reverse(lat: float = Query(...), lon: float = Query(...), zoom: int = 14):
    try:
        return _nom_reverse(lat, lon, zoom)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Zones CRUD ──────────────────────────────────────────────────────────
@router.get("/api/zones")
async def gis_zones_list(
    project_id: Optional[int] = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ensure_gis_tables()
    query = db.query(GisZone, GisZoneConfig.spacing).outerjoin(
        GisZoneConfig, GisZone.id == GisZoneConfig.zone_id
    )
    if project_id is not None:
        query = query.filter(GisZone.project_id == project_id)
    query = query.order_by(GisZone.created_at.desc())
    return [_zone_to_dict(z, sp or 30) for z, sp in query.all()]


@router.post("/api/zones", status_code=201)
async def gis_zones_create(body: GisCreateZoneBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    zid = body.id or uuid.uuid4().hex[:12]
    clat = body.center_lat or (body.center[0] if len(body.center) > 0 else None)
    clon = body.center_lon or (body.center[1] if len(body.center) > 1 else None)
    zone = GisZone(
        id=zid, name=body.name.strip(), type=body.type,
        color=body.color or DEFAULT_COLORS[0], priority=body.priority,
        center_lat=_fval(clat), center_lon=_fval(clon), zoom=body.zoom,
        bbox=body.bbox, description=body.description,
        est=body.est, corridors=body.corridors,
        bounds_polygon=body.bounds_polygon, source=body.source,
        project_id=body.project_id, osm_relation=body.osm_relation,
    )
    db.add(zone)
    db.add(GisZoneConfig(zone_id=zid))
    db.commit()
    db.refresh(zone)
    sp = db.get(GisZoneConfig, zid)
    return _zone_to_dict(zone, spacing=sp.spacing if sp else 30)


@router.put("/api/zones/{zone_id}")
async def gis_zones_update(zone_id: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    zone = db.get(GisZone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    field_map = {
        "name": "name", "type": "type", "color": "color", "priority": "priority",
        "center_lat": "center_lat", "center_lon": "center_lon", "zoom": "zoom",
        "bbox": "bbox", "description": "description", "source": "source",
        "project_id": "project_id",
    }
    for gk, ok_ in field_map.items():
        if gk in body:
            setattr(zone, ok_, body[gk])
    if "corridors" in body and isinstance(body["corridors"], (list, dict)):
        zone.corridors = body["corridors"]
    if "bounds_polygon" in body and isinstance(body["bounds_polygon"], (list, dict)):
        zone.bounds_polygon = body["bounds_polygon"]
    if "est" in body and isinstance(body["est"], dict):
        zone.est = body["est"]
    db.commit()
    return {"ok": True}


@router.delete("/api/zones/{zone_id}")
async def gis_zones_delete(zone_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    zone = db.get(GisZone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete(zone)
    db.commit()
    return {"ok": True}


# ── OSM data ────────────────────────────────────────────────────────────
@router.get("/api/zones/osm/all")
async def gis_zones_osm_all(project_id: Optional[int] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    query = db.query(GisZoneOsmData).join(GisZone)
    if project_id is not None:
        query = query.filter(GisZone.project_id == project_id)
    return {
        r.zone_id: {
            "zone_id": r.zone_id, "km_by_type": r.km_by_type or {},
            "ways": r.ways or [], "source": r.source or "",
            "loaded_at": r.loaded_at.isoformat() if r.loaded_at else None,
        }
        for r in query.all()
    }


@router.get("/api/zones/{zone_id}/osm")
async def gis_zone_osm(zone_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    row = db.get(GisZoneOsmData, zone_id)
    if not row:
        return {}
    return {
        "zone_id": row.zone_id, "km_by_type": row.km_by_type or {},
        "ways": row.ways or [], "source": row.source or "",
        "loaded_at": row.loaded_at.isoformat() if row.loaded_at else None,
    }


@router.put("/api/zones/{zone_id}/osm")
async def gis_zone_osm_save(zone_id: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    existing = db.get(GisZoneOsmData, zone_id)
    data = {
        "km_by_type": body.get("kmByType", body.get("km_by_type", {})),
        "ways": body.get("ways", []),
        "source": body.get("source", "osm"),
    }
    if existing:
        existing.km_by_type = data["km_by_type"]
        existing.ways = data["ways"]
        existing.source = data["source"]
        existing.loaded_at = datetime.now(timezone.utc)
    else:
        db.add(GisZoneOsmData(zone_id=zone_id, **data))
    db.commit()
    return {"ok": True}


# ── Zone config ─────────────────────────────────────────────────────────
@router.put("/api/zones/{zone_id}/config")
async def gis_zone_config(zone_id: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    cfg = db.get(GisZoneConfig, zone_id)
    if not cfg:
        cfg = GisZoneConfig(zone_id=zone_id)
        db.add(cfg)
    for key in ("spacing", "watt_hps", "watt_led", "efficacy", "hours_night"):
        if key in body:
            setattr(cfg, key, body[key])
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ── Trees ───────────────────────────────────────────────────────────────
@router.get("/api/zones/{zone_id}/trees")
async def gis_zone_trees_get(zone_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    row = db.get(GisZoneTrees, zone_id)
    return {
        "trees": row.trees if row else [],
        "loaded_at": row.loaded_at.isoformat() if row and row.loaded_at else None,
    }


@router.put("/api/zones/{zone_id}/trees")
async def gis_zone_trees_put(zone_id: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_gis_tables()
    existing = db.get(GisZoneTrees, zone_id)
    trees = body.get("trees", [])
    if existing:
        existing.trees = trees
        existing.loaded_at = datetime.now(timezone.utc)
    else:
        db.add(GisZoneTrees(zone_id=zone_id, trees=trees))
    db.commit()
    return {"ok": True}
