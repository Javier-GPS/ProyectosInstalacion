"""Zones — CRUD, OSM, config, trees, Nominatim."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.helpers import fval
from ..models import (
    GisPlanningDraft, GisRoadWorkScope, GisZone, GisZoneConfig, GisZoneOsmData, GisZoneTrees, User,
)
from ..schemas.zones import GisCreateZoneBody, GisPlanningDraftPut, GisRoadScopePut, GisRoutePreview
from ..services.planning import compact_payload, normalize_inventory
from ..services.overpass import fetch_roads
from ..services.nominatim import search as _nom_search, reverse as _nom_reverse
from ..services.zone_geometry import normalize_zone_geometry
from ..services.road_scope import calculate_route, geometry_hash, normalize_scope_boundary
from .deps import current_user, require_admin

router = APIRouter()
_osm_load_locks: dict[str, asyncio.Lock] = {}

DEFAULT_COLORS = [
    '#4caf82', '#e67e22', '#3498db', '#9b59b6', '#e74c3c',
    '#1abc9c', '#f39c12', '#2980b9', '#8e44ad', '#c0392b',
]



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
        "geometry": normalize_zone_geometry(z),
        "osm_relation": z.osm_relation,
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
    query = db.query(GisZone, GisZoneConfig.spacing).outerjoin(
        GisZoneConfig, GisZone.id == GisZoneConfig.zone_id
    )
    if project_id is not None:
        query = query.filter(GisZone.project_id == project_id)
    query = query.order_by(GisZone.created_at.desc())
    return [_zone_to_dict(z, sp or 30) for z, sp in query.all()]


@router.post("/api/zones", status_code=201)
async def gis_zones_create(body: GisCreateZoneBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    zid = body.id or uuid.uuid4().hex[:12]
    clat = body.center_lat or (body.center[0] if len(body.center) > 0 else None)
    clon = body.center_lon or (body.center[1] if len(body.center) > 1 else None)
    zone = GisZone(
        id=zid, name=body.name.strip(), type=body.type,
        color=body.color or DEFAULT_COLORS[0], priority=body.priority,
        center_lat=fval(clat), center_lon=fval(clon), zoom=body.zoom,
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
    zone = db.get(GisZone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    field_map = {
        "name": "name", "type": "type", "color": "color", "priority": "priority",
        "center_lat": "center_lat", "center_lon": "center_lon", "zoom": "zoom",
        "bbox": "bbox", "description": "description", "source": "source",
        "project_id": "project_id", "osm_relation": "osm_relation",
    }
    for gk, ok_ in field_map.items():
        if gk in body:
            setattr(zone, ok_, body[gk])
    if "corridors" in body and isinstance(body["corridors"], (list, dict)):
        zone.corridors = body["corridors"]
    if "bounds_polygon" in body and (body["bounds_polygon"] is None or isinstance(body["bounds_polygon"], (list, dict))):
        zone.bounds_polygon = body["bounds_polygon"]
    if "est" in body and isinstance(body["est"], dict):
        zone.est = body["est"]
    db.commit()
    db.refresh(zone)
    config = db.get(GisZoneConfig, zone_id)
    return _zone_to_dict(zone, config.spacing if config else 30)


@router.delete("/api/zones/{zone_id}")
async def gis_zones_delete(zone_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    zone = db.get(GisZone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete(zone)
    db.commit()
    return {"ok": True}


# ── OSM data ────────────────────────────────────────────────────────────
@router.get("/api/zones/osm/all")
async def gis_zones_osm_all(project_id: Optional[int] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
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


@router.post("/api/zones/{zone_id}/osm/load")
async def gis_zone_osm_load(
    zone_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    zone = db.get(GisZone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    bbox = zone.bbox or ""
    db.close()  # Release the pooled connection while waiting for the external provider.
    lock = _osm_load_locks.setdefault(zone_id, asyncio.Lock())
    async with lock:
        try:
            ways, source = await fetch_roads(bbox)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=f"Overpass unavailable: {exc}") from exc

    current_zone = db.query(GisZone).filter(GisZone.id == zone_id).populate_existing().first()
    if not current_zone:
        raise HTTPException(status_code=404, detail="Zone was deleted while loading OSM")
    if (current_zone.bbox or "") != bbox:
        raise HTTPException(status_code=409, detail="Zone bounds changed while loading OSM; retry required")

    km_by_type: dict[str, float] = {}
    for way in ways:
        road_type = way.get("type") or "unclassified"
        km_by_type[road_type] = km_by_type.get(road_type, 0.0) + (way.get("len") or 0.0)
    row = db.get(GisZoneOsmData, zone_id)
    if row and row.ways and not ways:
        raise HTTPException(status_code=502, detail="Overpass returned no roads; existing data was preserved")
    if row:
        row.ways = ways
        row.km_by_type = km_by_type
        row.source = source
        row.loaded_at = datetime.now(timezone.utc)
    else:
        db.add(GisZoneOsmData(
            zone_id=zone_id, ways=ways, km_by_type=km_by_type,
            source=source, loaded_at=datetime.now(timezone.utc),
        ))
    db.commit()
    return normalize_inventory(zone_id, ways)


# ── Road planning ──────────────────────────────────────────────────────
def _planning_inventory(zone_id: str, db: Session, allow_missing: bool = False) -> dict | None:
    if not db.get(GisZone, zone_id):
        raise HTTPException(status_code=404, detail="Zone not found")
    osm = db.get(GisZoneOsmData, zone_id)
    if not osm:
        if allow_missing:
            return None
        raise HTTPException(status_code=404, detail="No OSM data for zone")
    if not isinstance(osm.ways, list):
        raise HTTPException(status_code=422, detail="OSM ways must be a list")
    try:
        return normalize_inventory(zone_id, osm.ways)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid OSM data: {exc}") from exc


def _draft_dict(row: GisPlanningDraft) -> dict:
    return {
        "zone_id": row.zone_id,
        "revision": row.revision,
        "schema_version": row.schema_version,
        "base_inventory_hash": row.base_inventory_hash,
        "payload": row.payload or {"group_defaults": {}, "target_overrides": {}},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
    }


def _draft_response(row: GisPlanningDraft, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_draft_dict(row),
        headers={"ETag": f'"draft:{row.revision}"'},
    )


def _road_scope_response(row: GisRoadWorkScope, current_hash: str | None, current_boundary_hash: str | None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "zone_id": row.zone_id,
            "revision": row.revision,
            "schema_version": row.schema_version,
            "base_inventory_hash": row.base_inventory_hash,
            "current": row.base_inventory_hash == current_hash and row.zone_boundary_hash == current_boundary_hash,
            **(row.payload or {}),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by,
        },
        headers={"ETag": f'"road-scope:{row.revision}"'},
    )


@router.get("/api/zones/{zone_id}/planning-inventory")
async def gis_planning_inventory(
    zone_id: str,
    if_none_match: Optional[str] = Header(default=None, alias="If-None-Match"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    inventory = _planning_inventory(zone_id, db, allow_missing=True)
    if inventory is None:
        return Response(status_code=204)
    etag = f'"inventory:{inventory["base_inventory_hash"]}"'
    if if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(content=inventory, headers={"ETag": etag})


@router.get("/api/zones/{zone_id}/planning-draft")
async def gis_planning_draft_get(
    zone_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not db.get(GisZone, zone_id):
        raise HTTPException(status_code=404, detail="Zone not found")
    row = db.get(GisPlanningDraft, zone_id)
    if not row:
        return Response(status_code=204)
    return _draft_response(row)


@router.put("/api/zones/{zone_id}/planning-draft")
async def gis_planning_draft_put(
    zone_id: str,
    body: GisPlanningDraftPut,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    if_none_match: Optional[str] = Header(default=None, alias="If-None-Match"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    inventory = _planning_inventory(zone_id, db)
    current_hash = inventory["base_inventory_hash"]
    if body.base_inventory_hash != current_hash:
        raise HTTPException(status_code=409, detail="INVENTORY_STALE")

    valid_groups = {group["group_ref"] for group in inventory["groups"]}
    valid_targets = {target["target_ref"] for target in inventory["targets"]}
    if not set(body.payload.group_defaults).issubset(valid_groups):
        raise HTTPException(status_code=422, detail="Unknown planning group reference")
    if not set(body.payload.target_overrides).issubset(valid_targets):
        raise HTTPException(status_code=422, detail="Unknown planning target reference")

    payload = compact_payload(body.payload.model_dump(exclude_unset=True))
    row = db.get(GisPlanningDraft, zone_id)
    now = datetime.now(timezone.utc)

    if row is None:
        if body.mode != "update" or if_none_match != "*" or if_match is not None:
            raise HTTPException(status_code=412, detail="Draft creation precondition failed")
        row = GisPlanningDraft(
            zone_id=zone_id,
            revision=1,
            schema_version=body.schema_version,
            base_inventory_hash=current_hash,
            payload=payload,
            updated_at=now,
            updated_by=user.id,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=412, detail="Draft already exists") from exc
        db.refresh(row)
        return _draft_response(row, status_code=201)

    expected_etag = f'"draft:{row.revision}"'
    if if_match != expected_etag or if_none_match is not None:
        raise HTTPException(status_code=412, detail="Draft revision conflict")
    if body.mode == "update" and row.base_inventory_hash != current_hash:
        raise HTTPException(status_code=409, detail="DRAFT_BASE_MISMATCH")
    if body.mode == "recreate":
        payload = {"group_defaults": {}, "target_overrides": {}}

    expected_revision = row.revision
    updated = db.query(GisPlanningDraft).filter(
        GisPlanningDraft.zone_id == zone_id,
        GisPlanningDraft.revision == expected_revision,
    ).update({
        GisPlanningDraft.revision: expected_revision + 1,
        GisPlanningDraft.schema_version: body.schema_version,
        GisPlanningDraft.base_inventory_hash: current_hash,
        GisPlanningDraft.payload: payload,
        GisPlanningDraft.updated_at: now,
        GisPlanningDraft.updated_by: user.id,
    }, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=412, detail="Draft revision conflict")
    db.commit()
    db.expire_all()
    return _draft_response(db.get(GisPlanningDraft, zone_id))


@router.get("/api/zones/{zone_id}/road-scope")
async def gis_road_scope_get(zone_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    zone = db.get(GisZone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="ZONE_NOT_FOUND")
    row = db.get(GisRoadWorkScope, zone_id)
    if not row:
        return Response(status_code=204)
    inventory = _planning_inventory(zone_id, db, allow_missing=True)
    zone_boundary = normalize_zone_geometry(zone).get("boundary")
    return _road_scope_response(
        row,
        inventory["base_inventory_hash"] if inventory else None,
        geometry_hash(zone_boundary) if zone_boundary else None,
    )


@router.put("/api/zones/{zone_id}/road-scope")
async def gis_road_scope_put(
    zone_id: str,
    body: GisRoadScopePut,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    if_none_match: Optional[str] = Header(default=None, alias="If-None-Match"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    zone = db.query(GisZone).filter(GisZone.id == zone_id).with_for_update().one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="ZONE_NOT_FOUND")
    osm = db.query(GisZoneOsmData).filter(GisZoneOsmData.zone_id == zone_id).with_for_update().one_or_none()
    if not osm or not isinstance(osm.ways, list):
        raise HTTPException(status_code=422, detail="INVENTORY_UNAVAILABLE")
    inventory = normalize_inventory(zone_id, osm.ways)
    if body.base_inventory_hash != inventory["base_inventory_hash"]:
        raise HTTPException(status_code=409, detail="INVENTORY_STALE")
    zone_boundary = normalize_zone_geometry(zone).get("boundary")
    if not zone_boundary:
        raise HTTPException(status_code=422, detail="ZONE_BOUNDARY_MISSING")
    row = db.query(GisRoadWorkScope).filter(GisRoadWorkScope.zone_id == zone_id).with_for_update().one_or_none()
    if row is None:
        if if_none_match != "*" or if_match is not None:
            raise HTTPException(status_code=412, detail="SCOPE_CREATION_PRECONDITION_FAILED")
    elif if_match != f'"road-scope:{row.revision}"' or if_none_match is not None:
        raise HTTPException(status_code=412, detail="SCOPE_REVISION_CONFLICT")
    try:
        boundary = normalize_scope_boundary(body.boundary, zone_boundary)
        route = calculate_route(
            inventory,
            zone_boundary,
            boundary,
            set(body.allowed_group_refs),
            body.a.model_dump(),
            body.b.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = {
        "boundary": boundary,
        "allowed_group_refs": body.allowed_group_refs,
        "a": body.a.model_dump(),
        "b": body.b.model_dump(),
        **route,
        "topology_basis": "exact-coordinate",
    }
    now = datetime.now(timezone.utc)
    boundary_hash = geometry_hash(zone_boundary)
    if row is None:
        row = GisRoadWorkScope(
            zone_id=zone_id,
            revision=1,
            schema_version=body.schema_version,
            base_inventory_hash=inventory["base_inventory_hash"],
            zone_boundary_hash=boundary_hash,
            payload=payload,
            updated_at=now,
            updated_by=user.id,
        )
        db.add(row)
        status_code = 201
    else:
        row.revision += 1
        row.schema_version = body.schema_version
        row.base_inventory_hash = inventory["base_inventory_hash"]
        row.zone_boundary_hash = boundary_hash
        row.payload = payload
        row.updated_at = now
        row.updated_by = user.id
        status_code = 200
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=412, detail="SCOPE_REVISION_CONFLICT") from exc
    db.refresh(row)
    return _road_scope_response(row, inventory["base_inventory_hash"], boundary_hash, status_code)


@router.delete("/api/zones/{zone_id}/road-scope", status_code=204)
async def gis_road_scope_delete(
    zone_id: str,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.get(GisZone, zone_id):
        raise HTTPException(status_code=404, detail="ZONE_NOT_FOUND")
    row = db.query(GisRoadWorkScope).filter(GisRoadWorkScope.zone_id == zone_id).with_for_update().one_or_none()
    if not row:
        return Response(status_code=204)
    if if_match != f'"road-scope:{row.revision}"':
        raise HTTPException(status_code=412, detail="SCOPE_REVISION_CONFLICT")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.post("/api/zones/{zone_id}/route-preview")
async def gis_route_preview(
    zone_id: str,
    body: GisRoutePreview,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    zone = db.get(GisZone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="ZONE_NOT_FOUND")
    osm = db.get(GisZoneOsmData, zone_id)
    if not osm or not isinstance(osm.ways, list):
        raise HTTPException(status_code=422, detail="INVENTORY_UNAVAILABLE")
    inventory = normalize_inventory(zone_id, osm.ways)
    if body.base_inventory_hash != inventory["base_inventory_hash"]:
        raise HTTPException(status_code=409, detail="INVENTORY_STALE")
    zone_boundary = normalize_zone_geometry(zone).get("boundary")
    if not zone_boundary:
        raise HTTPException(status_code=422, detail="ZONE_BOUNDARY_MISSING")
    all_groups = {group["group_ref"] for group in inventory["groups"]}
    if body.a.target_ref not in {t["target_ref"] for t in inventory["targets"] if t["group_ref"] in all_groups and t.get("geometry")}:
        raise HTTPException(status_code=422, detail="INVALID_ANCHOR_A")
    if body.b.target_ref not in {t["target_ref"] for t in inventory["targets"] if t["group_ref"] in all_groups and t.get("geometry")}:
        raise HTTPException(status_code=422, detail="INVALID_ANCHOR_B")
    try:
        route = calculate_route(inventory, zone_boundary, zone_boundary, all_groups, body.a.model_dump(), body.b.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"path": route["path"], "length_m": route["length_m"], "members": route["members"]}


# ── Zone config ─────────────────────────────────────────────────────────
@router.get("/api/zones/{zone_id}/config")
async def gis_zone_config_get(zone_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cfg = db.get(GisZoneConfig, zone_id)
    if not cfg:
        return {"zone_id": zone_id, "spacing": 30, "watt_hps": 150, "watt_led": 60, "efficacy": 130, "hours_night": 11.5, "updated_at": None}
    return {
        "zone_id": cfg.zone_id, "spacing": cfg.spacing, "watt_hps": cfg.watt_hps,
        "watt_led": cfg.watt_led, "efficacy": cfg.efficacy, "hours_night": cfg.hours_night,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.put("/api/zones/{zone_id}/config")
async def gis_zone_config(zone_id: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
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
    row = db.get(GisZoneTrees, zone_id)
    return {
        "trees": row.trees if row else [],
        "loaded_at": row.loaded_at.isoformat() if row and row.loaded_at else None,
    }


@router.put("/api/zones/{zone_id}/trees")
async def gis_zone_trees_put(zone_id: str, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    existing = db.get(GisZoneTrees, zone_id)
    trees = body.get("trees", [])
    if existing:
        existing.trees = trees
        existing.loaded_at = datetime.now(timezone.utc)
    else:
        db.add(GisZoneTrees(zone_id=zone_id, trees=trees))
    db.commit()
    return {"ok": True}


