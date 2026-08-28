"""Exports — DXF + plantilla Excel."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.helpers import parse_json
from ..models import GisZoneOsmData, GisZoneTrees, GisLuminaire, GisInventoryLuminaire
from ..schemas.luminaires import GisPlantillaRequest
from ..services.dxf import build_dxf
from ..services.plantilla import build_plantilla
from ..services.access import zone_for
from .deps import Principal, current_principal

router = APIRouter()



@router.get("/api/export/dxf")
async def gis_export_dxf(zone_id: str = Query(...), principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone = zone_for(principal, db, zone_id)

    osm_row = db.get(GisZoneOsmData, zone_id)
    ways = parse_json(osm_row.ways if osm_row else None, [])
    lum_rows = db.query(GisLuminaire).filter(GisLuminaire.zone_id == zone_id).all()
    inv_rows = db.query(GisInventoryLuminaire).filter(GisInventoryLuminaire.zone_id == zone_id).all()
    trees_row = db.get(GisZoneTrees, zone_id)
    tree_data = parse_json(trees_row.trees if trees_row else None, [])
    boundary = parse_json(zone.bounds_polygon if zone else None, [])

    dxf_bytes = build_dxf(ways, lum_rows, inv_rows, tree_data, boundary)
    return Response(
        content=dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="zone_{zone_id}.dxf"'},
    )


@router.post("/api/export/plantilla_luminotecnica")
async def gis_export_plantilla(body: GisPlantillaRequest, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, body.zone_id)
    rows_dicts = [r.model_dump() for r in body.rows]
    xlsx_bytes = build_plantilla(body.zone_id, rows_dicts)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="plantilla_{body.zone_id}.xlsx"'},
    )


