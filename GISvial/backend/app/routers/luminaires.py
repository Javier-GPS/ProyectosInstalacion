"""Luminaires — CRUD, bulk, delete + current auto-materializations."""
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import GisLuminaire, GisInventoryLuminaire, GisLuxMaterialization, GisZone, Project
from ..schemas.luminaires import GisBulkLuminaire
from ..models import GisProjectMembership
from ..services.access import zone_for
from ..routers.deps import current_principal, Principal

router = APIRouter()


def _lum_to_dict(r: GisLuminaire) -> dict:
    return {
        "id": r.id, "project_id": str(r.project_id) if r.project_id else None,
        "zone_id": r.zone_id, "road_type": r.road_type or "",
        "lighting_class": r.lighting_class or "", "street_name": r.street_name or "",
        "lat": r.lat, "lon": r.lon, "watts": r.watts, "spacing": r.spacing,
        "tilt": r.tilt, "height_m": r.height_m, "arm_len": r.arm_len,
        "distribution": r.distribution,
        "placed_at": r.placed_at.isoformat() if r.placed_at else None,
    }


def _materialized_to_dict(materialization: GisLuxMaterialization, point: dict, index: int) -> dict:
    raw_id = int(hashlib.sha256(f"{materialization.id}:{index}".encode()).hexdigest()[:12], 16)
    return {
        "id": -(raw_id % 2_000_000_000 or 1),
        "project_id": str(materialization.project_id),
        "zone_id": materialization.zone_id,
        "road_type": point.get("road_type", ""),
        "lighting_class": point.get("lighting_class", ""),
        "street_name": point.get("street_name", ""),
        "lat": point.get("lat"), "lon": point.get("lon"),
        "watts": point.get("watts"), "spacing": point.get("spacing"),
        "tilt": point.get("tilt"), "height_m": point.get("height_m"),
        "arm_len": point.get("arm_len"), "distribution": point.get("distribution"),
        "placed_at": materialization.created_at.isoformat() if materialization.created_at else None,
        "materialization_id": materialization.id,
        "materialization_state": materialization.state,
    }


@router.get("/api/luminaires")
async def gis_luminaires_list(zone_id: str | None = Query(None), principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if zone_id:
        zone_for(principal, db, zone_id)
    q = db.query(GisLuminaire)
    if zone_id:
        q = q.filter(GisLuminaire.zone_id == zone_id)
    elif principal.user.role != "ADMIN":
        owned = db.query(Project.id).filter(Project.owner_user_id == principal.user.id)
        member = db.query(GisProjectMembership.project_id).filter(
            GisProjectMembership.issuer == principal.issuer,
            GisProjectMembership.subject == principal.subject,
            GisProjectMembership.active.is_(True),
        )
        q = q.join(GisZone).filter(GisZone.project_id.in_(owned.union(member)))
    result = [_lum_to_dict(r) for r in q.order_by(GisLuminaire.id).all()]
    current_query = db.query(GisLuxMaterialization).filter(GisLuxMaterialization.state == "current")
    if zone_id:
        current_query = current_query.filter(GisLuxMaterialization.zone_id == zone_id)
    elif principal.user.role != "ADMIN":
        owned = db.query(Project.id).filter(Project.owner_user_id == principal.user.id)
        member = db.query(GisProjectMembership.project_id).filter(
            GisProjectMembership.issuer == principal.issuer,
            GisProjectMembership.subject == principal.subject,
            GisProjectMembership.active.is_(True),
        )
        current_query = current_query.filter(GisLuxMaterialization.project_id.in_(owned.union(member)))
    for materialization in current_query.order_by(GisLuxMaterialization.created_at).all():
        result.extend(
            _materialized_to_dict(materialization, point, index)
            for index, point in enumerate(materialization.points or [])
        )
    return result


@router.post("/api/luminaires/bulk", status_code=201)
async def gis_luminaires_bulk(body: list[GisBulkLuminaire], principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    created = []
    for item in body:
        zone = zone_for(principal, db, item.zone_id, write=True)
        if item.project_id is not None and item.project_id != zone.project_id:
            raise HTTPException(status_code=422, detail="project_id does not match zone")
        lum = GisLuminaire(
            project_id=zone.project_id if item.project_id is None else item.project_id, zone_id=item.zone_id,
            road_type=item.road_type, lighting_class=item.lighting_class,
            street_name=item.street_name, lat=item.lat, lon=item.lon,
            watts=item.watts, spacing=item.spacing,
            tilt=item.tilt, height_m=item.height_m, arm_len=item.arm_len,
            distribution=item.distribution,
        )
        db.add(lum)
        db.flush()
        created.append(_lum_to_dict(lum))
    db.commit()
    return created


@router.delete("/api/luminaires/{zone_id}/{lum_id}", status_code=204)
async def gis_luminaires_delete(zone_id: str, lum_id: int, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id, write=True)
    lum = db.get(GisLuminaire, lum_id)
    if not lum or lum.zone_id != zone_id:
        raise HTTPException(status_code=404, detail="Luminaire not found")
    db.delete(lum)
    db.commit()


@router.get("/api/zones/{zone_id}/inventory")
async def gis_zone_inventory(zone_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id)
    rows = db.query(GisInventoryLuminaire).filter(GisInventoryLuminaire.zone_id == zone_id).order_by(GisInventoryLuminaire.id).all()
    return [{
        "id": r.id, "zone_id": r.zone_id, "point_id": r.point_id,
        "lat": r.lat, "lon": r.lon, "power_w": r.power_w, "height_m": r.height_m,
        "brand": r.brand, "model": r.model, "lamp_type": r.lamp_type,
        "support_type": r.support_type, "circuit_id": r.circuit_id,
        "line_id": r.line_id, "extra": r.extra, "way_key": r.way_key,
        "road_type": r.road_type,
        "imported_at": r.imported_at.isoformat() if r.imported_at else None,
    } for r in rows]


