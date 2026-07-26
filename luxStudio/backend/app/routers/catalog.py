"""Admin CRUD endpoints for the four catalog dimension tables.

All endpoints require admin role (``Depends(require_admin)``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..routers.auth import require_admin
from ..database import get_db
from ..schemas.models import LuminaireMaxPowerInfo
from ..services import catalog_service
from ..services.luminaire_catalog import get_pmax_for_selection


router = APIRouter()


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class NameBody(BaseModel):
    name: str


class VCBody(BaseModel):
    gama_id: int
    difusor_id: int
    lente_id: int
    led_type_id: int | None = None


class LuminaireLEDBody(BaseModel):
    gama: str
    difusor: str
    lente: str
    led_ref: str
    led_type: str | None = None
    pcb_ref: str | None = None
    n_pcbs: int | None = None
    n_leds_per_pcb: int | None = None


class PCBBody(BaseModel):
    pcb_ref: str
    pcb_descripcion: str | None = None
    pcb_no_drivers: int | None = None
    pcb_v_nominal: float | None = None
    pcb_no_led: int | None = None
    pcb_no_circuitos: int | None = None
    pcb_imax_led: float | None = None


# ---------------------------------------------------------------------------
# Generic dimension CRUD — gamas
# ---------------------------------------------------------------------------

@router.get("/gamas", dependencies=[Depends(require_admin)])
async def list_gamas(db: Session = Depends(get_db)):
    return catalog_service.list_items(db, "gama")


@router.post("/gamas", dependencies=[Depends(require_admin)], status_code=201)
async def create_gama(body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.create_item(db, "gama", body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/gamas/{item_id}", dependencies=[Depends(require_admin)])
async def update_gama(item_id: int, body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.update_item(db, "gama", item_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400 if "already exists" in str(e) else 404, detail=str(e))


@router.delete("/gamas/{item_id}", dependencies=[Depends(require_admin)])
async def delete_gama(item_id: int, db: Session = Depends(get_db)):
    try:
        catalog_service.delete_item(db, "gama", item_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400 if "still reference" in str(e) else 404, detail=str(e))


# ---------------------------------------------------------------------------
# difusores
# ---------------------------------------------------------------------------

@router.get("/difusores", dependencies=[Depends(require_admin)])
async def list_difusores(db: Session = Depends(get_db)):
    return catalog_service.list_items(db, "difusor")


@router.post("/difusores", dependencies=[Depends(require_admin)], status_code=201)
async def create_difusor(body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.create_item(db, "difusor", body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/difusores/{item_id}", dependencies=[Depends(require_admin)])
async def update_difusor(item_id: int, body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.update_item(db, "difusor", item_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400 if "already exists" in str(e) else 404, detail=str(e))


@router.delete("/difusores/{item_id}", dependencies=[Depends(require_admin)])
async def delete_difusor(item_id: int, db: Session = Depends(get_db)):
    try:
        catalog_service.delete_item(db, "difusor", item_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400 if "still reference" in str(e) else 404, detail=str(e))


# ---------------------------------------------------------------------------
# lentes
# ---------------------------------------------------------------------------

@router.get("/lentes", dependencies=[Depends(require_admin)])
async def list_lentes(db: Session = Depends(get_db)):
    return catalog_service.list_items(db, "lente")


@router.post("/lentes", dependencies=[Depends(require_admin)], status_code=201)
async def create_lente(body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.create_item(db, "lente", body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/lentes/{item_id}", dependencies=[Depends(require_admin)])
async def update_lente(item_id: int, body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.update_item(db, "lente", item_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400 if "already exists" in str(e) else 404, detail=str(e))


@router.delete("/lentes/{item_id}", dependencies=[Depends(require_admin)])
async def delete_lente(item_id: int, db: Session = Depends(get_db)):
    try:
        catalog_service.delete_item(db, "lente", item_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400 if "still reference" in str(e) else 404, detail=str(e))


# ---------------------------------------------------------------------------
# led-types
# ---------------------------------------------------------------------------

@router.get("/led-types", dependencies=[Depends(require_admin)])
async def list_led_types(db: Session = Depends(get_db)):
    return catalog_service.list_items(db, "led_type")


@router.post("/led-types", dependencies=[Depends(require_admin)], status_code=201)
async def create_led_type(body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.create_item(db, "led_type", body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/led-types/{item_id}", dependencies=[Depends(require_admin)])
async def update_led_type(item_id: int, body: NameBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.update_item(db, "led_type", item_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400 if "already exists" in str(e) else 404, detail=str(e))


@router.delete("/led-types/{item_id}", dependencies=[Depends(require_admin)])
async def delete_led_type(item_id: int, db: Session = Depends(get_db)):
    try:
        catalog_service.delete_item(db, "led_type", item_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400 if "still reference" in str(e) else 404, detail=str(e))


# ---------------------------------------------------------------------------
# valid-combinations
# ---------------------------------------------------------------------------

@router.get("/valid-combinations", dependencies=[Depends(require_admin)])
async def list_valid_combinations(db: Session = Depends(get_db)):
    return catalog_service.list_valid_combinations(db)


@router.post("/valid-combinations", dependencies=[Depends(require_admin)], status_code=201)
async def create_valid_combination(body: VCBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.create_valid_combination(
            db, body.gama_id, body.difusor_id, body.lente_id, body.led_type_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/valid-combinations/{vc_id}", dependencies=[Depends(require_admin)])
async def delete_valid_combination(vc_id: int, db: Session = Depends(get_db)):
    try:
        catalog_service.delete_valid_combination(db, vc_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Catalog tables (LED, PCB, Driver, LuminaireLED) — read-only
# ---------------------------------------------------------------------------


@router.get("/leds", dependencies=[Depends(require_admin)])
async def list_leds(db: Session = Depends(get_db)):
    return catalog_service.list_leds(db)


@router.get("/pcbs", dependencies=[Depends(require_admin)])
async def list_pcbs(db: Session = Depends(get_db)):
    return catalog_service.list_pcbs(db)


@router.post("/pcbs", dependencies=[Depends(require_admin)], status_code=201)
async def create_pcb(body: PCBBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.create_pcb(db, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/drivers", dependencies=[Depends(require_admin)])
async def list_drivers(db: Session = Depends(get_db)):
    return catalog_service.list_drivers(db)


@router.get("/luminaire-leds", dependencies=[Depends(require_admin)])
async def list_luminaire_leds(db: Session = Depends(get_db)):
    return catalog_service.list_luminaire_leds(db)


@router.post("/luminaire-leds", dependencies=[Depends(require_admin)], status_code=201)
async def create_luminaire_led(body: LuminaireLEDBody, db: Session = Depends(get_db)):
    try:
        return catalog_service.create_luminaire_led(
            db,
            gama=body.gama,
            difusor=body.difusor,
            lente=body.lente,
            led_ref=body.led_ref,
            led_type=body.led_type,
            pcb_ref=body.pcb_ref,
            n_pcbs=body.n_pcbs,
            n_leds_per_pcb=body.n_leds_per_pcb,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 4-tuple -> LED power cap (read-only audit endpoint)
# ---------------------------------------------------------------------------


class LuminairePmaxBody(BaseModel):
    gama: str
    difusor: str
    lente: str
    led_type: str | None = None


@router.post("/luminaire-pmax", response_model=LuminaireMaxPowerInfo, dependencies=[Depends(require_admin)])
async def get_luminaire_pmax(body: LuminairePmaxBody, db: Session = Depends(get_db)):
    """Return the LED power cap for a single 4-tuple.

    404 when the 4-tuple is not in the catalog (the cap cannot be
    enforced and the configurator must allow any power).
    """
    info = get_pmax_for_selection(
        db, body.gama, body.difusor, body.lente, body.led_type,
    )
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No hay LED catalogado para la selección "
                f"({body.gama}/{body.difusor}/{body.lente}/{body.led_type or '—'})."
            ),
        )
    return LuminaireMaxPowerInfo(
        gama=body.gama,
        difusor=body.difusor,
        lente=body.lente,
        led_type=body.led_type,
        led_ref=info["led_ref"],
        led_desc_corta=info.get("led_desc_corta"),
        pmax_lum=info.get("pmax_lum"),
        pmax_ajustada=info.get("pmax_ajustada"),
        i_max_led=info.get("i_max_led"),
    )
