"""Zones — CRUD, OSM, config, trees, Nominatim."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.database import get_db, SessionLocal
from ..core.helpers import fval
from ..models import (
    GisPlanningDraft, GisProjectMembership, GisRoadWorkScope, GisZone, GisZoneConfig,
    GisZoneOsmData, GisZoneTrees, Project,
)
from ..schemas.zones import GisCreateZoneBody, GisPlanningDraftPut, GisRoadScopePut, GisRoutePreview
from ..services.planning import compact_payload, normalize_inventory
from ..services.overpass import fetch_roads, filter_ways_to_polygon
from ..services.building_width import enrich_widths, fetch_buildings
from ..services.nominatim import search as _nom_search, reverse as _nom_reverse
from ..services.zone_geometry import normalize_zone_geometry
from ..services.road_scope import calculate_route, geometry_hash, normalize_scope_boundary
from .deps import Principal, current_principal
from ..services.access import project_for, zone_for

router = APIRouter()

# Tracks background building enrichment tasks per zone
_building_tasks: dict[str, asyncio.Task] = {}

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
        return await _nom_search(q, featuretype)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/nominatim/reverse")
async def gis_nominatim_reverse(lat: float = Query(...), lon: float = Query(...), zoom: int = 14):
    try:
        return await _nom_reverse(lat, lon, zoom)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Zones CRUD ──────────────────────────────────────────────────────────
@router.get("/api/zones")
async def gis_zones_list(
    project_id: Optional[int] = None,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    query = db.query(GisZone, GisZoneConfig.spacing).outerjoin(
        GisZoneConfig, GisZone.id == GisZoneConfig.zone_id
    )
    if project_id is not None:
        project_for(principal, db, project_id)
        query = query.filter(GisZone.project_id == project_id)
    elif principal.user.role != "ADMIN":
        owned = db.query(Project.id).filter(Project.owner_user_id == principal.user.id)
        member = db.query(GisProjectMembership.project_id).filter(
            GisProjectMembership.issuer == principal.issuer,
            GisProjectMembership.subject == principal.subject,
            GisProjectMembership.active.is_(True),
        )
        query = query.filter(GisZone.project_id.in_(owned.union(member)))
    query = query.order_by(GisZone.created_at.desc())
    return [_zone_to_dict(z, sp or 30) for z, sp in query.all()]


@router.post("/api/zones", status_code=201)
async def gis_zones_create(body: GisCreateZoneBody, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if body.project_id is not None:
        project_for(principal, db, body.project_id, write=True)
    elif principal.user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="project_id is required")
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
async def gis_zones_update(zone_id: str, body: dict, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone = zone_for(principal, db, zone_id, write=True)
    field_map = {
        "name": "name", "type": "type", "color": "color", "priority": "priority",
        "center_lat": "center_lat", "center_lon": "center_lon", "zoom": "zoom",
        "bbox": "bbox", "description": "description", "source": "source",
        "project_id": "project_id", "osm_relation": "osm_relation",
    }
    if "project_id" in body and body["project_id"] != zone.project_id:
        if body["project_id"] is None:
            if principal.user.role != "ADMIN":
                raise HTTPException(status_code=403, detail="project_id is required")
        else:
            project_for(principal, db, int(body["project_id"]), write=True)
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
async def gis_zones_delete(zone_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone = zone_for(principal, db, zone_id, write=True)
    db.delete(zone)
    db.commit()
    return {"ok": True}


# ── OSM data ────────────────────────────────────────────────────────────
@router.get("/api/zones/osm/all")
async def gis_zones_osm_all(project_id: Optional[int] = None, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    query = db.query(GisZoneOsmData).join(GisZone)
    if project_id is not None:
        project_for(principal, db, project_id)
        query = query.filter(GisZone.project_id == project_id)
    elif principal.user.role != "ADMIN":
        owned = db.query(Project.id).filter(Project.owner_user_id == principal.user.id)
        member = db.query(GisProjectMembership.project_id).filter(
            GisProjectMembership.issuer == principal.issuer,
            GisProjectMembership.subject == principal.subject,
            GisProjectMembership.active.is_(True),
        )
        query = query.filter(GisZone.project_id.in_(owned.union(member)))
    return {
        r.zone_id: {
            "zone_id": r.zone_id, "km_by_type": r.km_by_type or {},
            "ways": r.ways or [], "source": r.source or "",
            "loaded_at": r.loaded_at.isoformat() if r.loaded_at else None,
        }
        for r in query.all()
    }


@router.get("/api/zones/{zone_id}/osm")
async def gis_zone_osm(zone_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id)
    row = db.get(GisZoneOsmData, zone_id)
    if not row:
        return {}
    return {
        "zone_id": row.zone_id, "km_by_type": row.km_by_type or {},
        "ways": row.ways or [], "source": row.source or "",
        "loaded_at": row.loaded_at.isoformat() if row.loaded_at else None,
    }


@router.put("/api/zones/{zone_id}/osm")
async def gis_zone_osm_save(zone_id: str, body: dict, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id, write=True)
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
    force: bool = Query(default=False, description="Ignore cached data and force re-fetch from OSM"),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    zone = zone_for(principal, db, zone_id, write=True)
    bbox = zone.bbox or ""
    polygon = zone.bounds_polygon or []

    # Check cache (skip if force=True)
    cached_row = db.get(GisZoneOsmData, zone_id)
    if cached_row and cached_row.ways and not force:
        logger.info("Using cached OSM data for zone %s (force=False)", zone_id)
        if not cached_row.buildings:
            # Trigger background enrichment without blocking response
            task = _building_tasks.get(zone_id)
            if task is None or task.done():
                _building_tasks[zone_id] = asyncio.create_task(
                    _enrich_buildings_background(zone_id, bbox, cached_row.ways)
                )
        return normalize_inventory(zone_id, cached_row.ways)

    try:
        ways, source = await fetch_roads(bbox, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        if cached_row and cached_row.ways:
            logger.warning("Overpass failed, falling back to cached data: %s", exc)
            return normalize_inventory(zone_id, cached_row.ways)
        raise HTTPException(
            status_code=502,
            detail="No se pudo conectar con OpenStreetMap. "
                   "Los servidores de OSM están temporalmente sobrecargados. "
                   "Inténtalo de nuevo en unos minutos.",
        ) from exc

    # Re-check zone hasn't changed
    current_zone = db.query(GisZone).filter(GisZone.id == zone_id).populate_existing().first()
    if not current_zone:
        raise HTTPException(status_code=404, detail="Zone was deleted while loading OSM")
    if (current_zone.bbox or "") != bbox:
        raise HTTPException(status_code=409, detail="Zone bounds changed while loading OSM; retry required")

    ways = filter_ways_to_polygon(ways, polygon)

    km_by_type: dict[str, float] = {}
    for way in ways:
        road_type = way.get("type") or "unclassified"
        km_by_type[way.get("type", road_type)] = km_by_type.get(road_type, 0.0) + (way.get("len") or 0.0)

    # Save ways immediately WITHOUT buildings (fast response)
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
            zone_id=zone_id, ways=ways,
            km_by_type=km_by_type, source=source,
            loaded_at=datetime.now(timezone.utc),
        ))
    db.commit()

    # Fire background enrichment (Catastro WFS) — non-blocking
    _building_tasks[zone_id] = asyncio.create_task(
        _enrich_buildings_background(zone_id, bbox, ways)
    )

    return normalize_inventory(zone_id, ways)


async def _enrich_buildings_background(zone_id: str, bbox: str, ways: list) -> None:
    """Fetch Catastro WFS and enrich road widths in the background."""
    try:
        buildings = await fetch_buildings(bbox)
        ways = enrich_widths(ways, buildings)
        # Count enriched ways
        enriched = sum(1 for w in ways if w.get("widthSrc") == "catastro")
        logger.info(
            "Catastro enrichment: %d buildings, %d/%d ways enriched for zone %s",
            len(buildings) if buildings else 0, enriched, len(ways), zone_id,
        )
        db = SessionLocal()
        try:
            row = db.get(GisZoneOsmData, zone_id)
            if row:
                row.buildings = buildings
                row.ways = ways
                db.commit()
                logger.info(
                    "Background building enrichment completed for zone %s: "
                    "%d ways enriched with Catastro data out of %d total",
                    zone_id, enriched, len(ways),
                )
        except Exception as exc:
            logger.warning("Background DB update failed for zone %s: %s", zone_id, exc)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Background building enrichment failed for zone %s: %s", zone_id, exc)
    finally:
        _building_tasks.pop(zone_id, None)


@router.get("/api/zones/{zone_id}/building-widths")
async def gis_building_widths_status(
    zone_id: str,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Check the status of building width enrichment for a zone."""
    zone_for(principal, db, zone_id)
    row = db.get(GisZoneOsmData, zone_id)
    if not row:
        raise HTTPException(status_code=404, detail="ZONE_NOT_FOUND")
    task = _building_tasks.get(zone_id)
    if task and not task.done():
        return {
            "zone_id": zone_id,
            "status": "computing",
            "buildings": None,
            "enriched_ways": None,
            "computed_at": None,
        }
    if row.buildings:
        return {
            "zone_id": zone_id,
            "status": "available",
            "buildings": row.buildings,
            "enriched_ways": row.ways,
            "computed_at": row.loaded_at.isoformat() if row.loaded_at else None,
        }
    return {
        "zone_id": zone_id,
        "status": "unavailable",
        "buildings": None,
        "enriched_ways": None,
        "computed_at": None,
        "message": "No building data available",
    }


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
    refresh: bool = Query(default=False, description="Force recalculate inventory from DB (no Overpass call)"),
    if_none_match: Optional[str] = Header(default=None, alias="If-None-Match"),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    zone_for(principal, db, zone_id)
    inventory = _planning_inventory(zone_id, db, allow_missing=True)
    if inventory is None:
        return Response(status_code=204)
    etag = f'"inventory:{inventory["base_inventory_hash"]}"'
    # Skip ETag check if refresh is requested (buildings may have been enriched in background)
    if not refresh and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(content=inventory, headers={"ETag": etag})


@router.get("/api/zones/{zone_id}/planning-draft")
async def gis_planning_draft_get(
    zone_id: str,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    zone_for(principal, db, zone_id)
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
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    zone_for(principal, db, zone_id, write=True)
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
            updated_by=principal.user.id,
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
        GisPlanningDraft.updated_by: principal.user.id,
    }, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=412, detail="Draft revision conflict")
    db.commit()
    db.expire_all()
    return _draft_response(db.get(GisPlanningDraft, zone_id))


@router.get("/api/zones/{zone_id}/road-scope")
async def gis_road_scope_get(zone_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone = zone_for(principal, db, zone_id)
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
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    zone_for(principal, db, zone_id, write=True)
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
            updated_by=principal.user.id,
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
        row.updated_by = principal.user.id
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
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    zone_for(principal, db, zone_id, write=True)
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
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    zone = zone_for(principal, db, zone_id)
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
async def gis_zone_config_get(zone_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id)
    cfg = db.get(GisZoneConfig, zone_id)
    if not cfg:
        return {"zone_id": zone_id, "spacing": 30, "watt_hps": 150, "watt_led": 60, "efficacy": 130, "hours_night": 11.5, "updated_at": None}
    return {
        "zone_id": cfg.zone_id, "spacing": cfg.spacing, "watt_hps": cfg.watt_hps,
        "watt_led": cfg.watt_led, "efficacy": cfg.efficacy, "hours_night": cfg.hours_night,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.put("/api/zones/{zone_id}/config")
async def gis_zone_config(zone_id: str, body: dict, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id, write=True)
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
async def gis_zone_trees_get(zone_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id)
    row = db.get(GisZoneTrees, zone_id)
    return {
        "trees": row.trees if row else [],
        "loaded_at": row.loaded_at.isoformat() if row and row.loaded_at else None,
    }


@router.put("/api/zones/{zone_id}/trees")
async def gis_zone_trees_put(zone_id: str, body: dict, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id, write=True)
    existing = db.get(GisZoneTrees, zone_id)
    trees = body.get("trees", [])
    if existing:
        existing.trees = trees
        existing.loaded_at = datetime.now(timezone.utc)
    else:
        db.add(GisZoneTrees(zone_id=zone_id, trees=trees))
    db.commit()
    return {"ok": True}


