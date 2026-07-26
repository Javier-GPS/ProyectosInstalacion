import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Fotometria
from ..schemas.models import FotometriaInfo
from ..services import admin_service
from ..services.ldt_loader import refresh_ldt_cache


class UpdateLuminaireBody(BaseModel):
    manufacturer: Optional[str] = None
    model_family: Optional[str] = None
    optic_family: Optional[str] = None
    luminaire_name: Optional[str] = None
    power: Optional[float] = None
    cct: Optional[int] = None
    cri: Optional[int] = None
    flux: Optional[float] = None
    efficiency: Optional[float] = None
    LORL: Optional[float] = None
    isym: Optional[int] = None
    gama: Optional[str] = None
    difusor: Optional[str] = None
    lente: Optional[str] = None
    led_type: Optional[str] = None
    mf_origen: Optional[float] = None

router = APIRouter()


def _lum_to_info(lum: Fotometria) -> FotometriaInfo:
    return FotometriaInfo(
        id=str(lum.id),
        filename=Path(lum.photometric_path).name,
        luminaire_name=lum.name,
        manufacturer=lum.manufacturer.name if lum.manufacturer else "Unknown",
        model_family=lum.type,
        cct=lum.cct,
        cri=getattr(lum, "cri", 70) or 70,
        optic_family=lum.optic_family,
        power=lum.power,
        flux=lum.flux,
        efficiency=lum.efficiency,
        LORL=lum.LORL,
        isym=lum.isym,
        gama=getattr(getattr(lum, "gama", None), "name", None),
        difusor=getattr(getattr(lum, "difusor", None), "name", None),
        lente=getattr(getattr(lum, "lente", None), "name", None),
        led_type=getattr(getattr(lum, "led_type", None), "name", None),
        fotometria=getattr(lum, "fotometria", None),
        mf_origen=float(getattr(lum, "mf_origen", 1.0) or 1.0),
    )


@router.post("/parse-ldt")
async def parse_ldt(file: UploadFile = File(...)):
    """Upload an LDT and return extracted fields for admin form preview. Does NOT save."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty LDT file")
    try:
        result = admin_service.parse_ldt_preview(data, file.filename or "unknown.ldt")
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid LDT file: {exc}")


@router.post("/luminaires/upload")
async def upload_luminaire(
    file: UploadFile = File(...),
    manufacturer: str = Form(...),
    model_family: str = Form(...),
    optic_family: str = Form(...),
    luminaire_name: str = Form(...),
    power: float = Form(...),
    cct: int = Form(...),
    cri: int = Form(70),
    flux: float = Form(...),
    efficiency: float = Form(...),
    LORL: float = Form(...),
    isym: int = Form(...),
    gama: Optional[str] = Form(None),
    difusor: Optional[str] = Form(None),
    lente: Optional[str] = Form(None),
    led_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload an LDT and save as a new luminaire."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty LDT file")

    fd, tmp_path = tempfile.mkstemp(suffix=".ldt")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        lum = admin_service.create_luminaire(db, {
            "ldt_temp_path": tmp_path,
            "filename": file.filename or "unknown.ldt",
            "manufacturer": manufacturer,
            "model_family": model_family,
            "optic_family": optic_family,
            "luminaire_name": luminaire_name,
            "power": power,
            "cct": cct,
            "cri": cri,
            "flux": flux,
            "efficiency": efficiency,
            "LORL": LORL,
            "isym": isym,
            "gama": gama,
            "difusor": difusor,
            "lente": lente,
            "led_type": led_type,
        })
        refresh_ldt_cache()
        return _lum_to_info(lum)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/luminaires", response_model=list[FotometriaInfo])
async def list_luminaires(db: Session = Depends(get_db)):
    """List all luminaires from the database."""
    luminaires = admin_service.get_all_luminaires(db)
    return [_lum_to_info(l) for l in luminaires]


@router.get("/luminaires/{lum_id}", response_model=FotometriaInfo)
async def get_luminaire(lum_id: int, db: Session = Depends(get_db)):
    """Get a single luminaire by ID."""
    lum = admin_service.get_luminaire_by_id(db, lum_id)
    if not lum:
        raise HTTPException(status_code=404, detail="Luminaire not found")
    return _lum_to_info(lum)


@router.put("/luminaires/{lum_id}")
async def update_luminaire(
    lum_id: int,
    body: UpdateLuminaireBody,
    db: Session = Depends(get_db),
):
    """Update a luminaire. Body can include any subset of fields."""
    data = body.model_dump(exclude_none=True)
    if "mf_origen" in data:
        if not 0.5 <= float(data["mf_origen"]) <= 1.0:
            raise HTTPException(
                status_code=400,
                detail="mf_origen must be between 0.5 and 1.0",
            )
    lum = admin_service.update_luminaire(db, lum_id, data)
    if not lum:
        raise HTTPException(status_code=404, detail="Luminaire not found")
    refresh_ldt_cache()
    return _lum_to_info(lum)


@router.delete("/luminaires/{lum_id}")
async def delete_luminaire(lum_id: int, db: Session = Depends(get_db)):
    """Delete a luminaire and its LDT file."""
    ok = admin_service.delete_luminaire(db, lum_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Luminaire not found")
    refresh_ldt_cache()
    return {"ok": True}


@router.get("/manufacturers")
async def list_manufacturers(db: Session = Depends(get_db)):
    """List all manufacturers."""
    mfrs = admin_service.get_manufacturers(db)
    return [{"id": m.id, "name": m.name} for m in mfrs]
