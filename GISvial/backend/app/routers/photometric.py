"""Photometric — results import/export."""
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.helpers import fval, sval
from ..models import GisPhotometricResult
from ..services.access import zone_for
from .deps import Principal, current_principal

router = APIRouter()



def sval(v):
    return str(v).strip() if v is not None else None


@router.get("/api/zones/{zone_id}/photometric")
async def gis_zone_photometric(zone_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    zone_for(principal, db, zone_id)
    rows = db.query(GisPhotometricResult).filter(
        GisPhotometricResult.zone_id == zone_id
    ).order_by(GisPhotometricResult.id).all()
    return [{
        "id": r.id, "zone_id": r.zone_id,
        "segment_name": r.segment_name, "match_key": r.match_key,
        "road_width": r.road_width, "spacing": r.spacing,
        "lighting_class": r.lighting_class, "power_w": r.power_w,
        "lm_em": r.lm_em, "uo": r.uo, "ui": r.ui, "ti": r.ti, "sr": r.sr,
        "model": r.model, "lente": r.lente, "tilt": r.tilt, "phi_lm": r.phi_lm,
        "cumple": r.cumple, "notes": r.notes,
        "imported_at": r.imported_at.isoformat() if r.imported_at else None,
    } for r in rows]


@router.post("/api/import/photometric")
async def gis_import_photometric(request: Request, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    import openpyxl
    raw = await request.body()
    zone_id = request.query_params.get("zone_id", "")
    if not zone_id:
        raise HTTPException(status_code=400, detail="zone_id query parameter required")
    zone_for(principal, db, zone_id, write=True)

    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    ws = wb.active
    rows_raw = list(ws.iter_rows(values_only=True))
    if not rows_raw:
        return {"imported": 0, "rows": []}

    headers = [str(h).lower().strip() if h else "" for h in rows_raw[0]]
    def _col(names):
        for n in names:
            if n in headers:
                return headers.index(n)
        return None
    ci = {
        "segment_name": _col(["segmento", "segment", "name", "tramo"]),
        "match_key": _col(["match_key", "key", "clave"]),
        "road_width": _col(["ancho", "road_width", "w_m", "width"]),
        "spacing": _col(["espaciado", "spacing", "sp"]),
        "lighting_class": _col(["clase", "class", "lc", "lighting_class"]),
        "power_w": _col(["w", "potencia", "power", "watts"]),
        "lm_em": _col(["lm/m2", "lm_em", "em", "e_m"]),
        "uo": _col(["uo", "u0"]), "ui": _col(["ui"]), "ti": _col(["ti"]), "sr": _col(["sr"]),
        "model": _col(["modelo", "model"]), "lente": _col(["lente", "lens"]),
        "tilt": _col(["tilt", "inclinacion"]),
        "phi_lm": _col(["phi", "flujo", "phi_lm", "lm"]),
        "cumple": _col(["cumple", "ok", "pass", "resultado"]),
        "notes": _col(["notas", "notes", "observaciones"]),
    }
    imported = 0
    rows_out = []
    for row in rows_raw[1:]:
        if not any(row):
            continue
        def g(k):
            idx = ci.get(k)
            return row[idx] if idx is not None and idx < len(row) else None
        road_w = fval(g("road_width"))
        sp_val = fval(g("spacing"))
        lc = sval(g("lighting_class"))
        mk = sval(g("match_key")) or (f"{road_w}|{sp_val}|{lc}" if road_w and sp_val and lc else None)
        if not mk:
            continue
        existing = db.query(GisPhotometricResult).filter(
            GisPhotometricResult.zone_id == zone_id,
            GisPhotometricResult.match_key == mk,
        ).first()
        data = {
            "segment_name": sval(g("segment_name")), "match_key": mk,
            "road_width": road_w, "spacing": sp_val, "lighting_class": lc,
            "power_w": fval(g("power_w")), "lm_em": fval(g("lm_em")),
            "uo": fval(g("uo")), "ui": fval(g("ui")), "ti": fval(g("ti")), "sr": fval(g("sr")),
            "model": sval(g("model")), "lente": sval(g("lente")),
            "tilt": fval(g("tilt")), "phi_lm": fval(g("phi_lm")),
            "cumple": sval(g("cumple")), "notes": sval(g("notes")),
        }
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            db.add(GisPhotometricResult(zone_id=zone_id, **data))
        rows_out.append(data)
        imported += 1
    db.commit()
    return {"imported": imported, "rows": rows_out}


