"""Luminaires — CRUD, bulk, delete + inventory."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import GisLuminaire, GisInventoryLuminaire, User
from ..schemas.luminaires import GisBulkLuminaire
from .deps import current_user

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


@router.get("/api/luminaires")
async def gis_luminaires_list(zone_id: str | None = Query(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(GisLuminaire)
    if zone_id:
        q = q.filter(GisLuminaire.zone_id == zone_id)
    return [_lum_to_dict(r) for r in q.order_by(GisLuminaire.id).all()]


@router.post("/api/luminaires/bulk", status_code=201)
async def gis_luminaires_bulk(body: list[GisBulkLuminaire], user: User = Depends(current_user), db: Session = Depends(get_db)):
    created = []
    for item in body:
        lum = GisLuminaire(
            project_id=item.project_id, zone_id=item.zone_id,
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
async def gis_luminaires_delete(zone_id: str, lum_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lum = db.get(GisLuminaire, lum_id)
    if not lum or lum.zone_id != zone_id:
        raise HTTPException(status_code=404, detail="Luminaire not found")
    db.delete(lum)
    db.commit()


@router.get("/api/zones/{zone_id}/inventory")
async def gis_zone_inventory(zone_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
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


