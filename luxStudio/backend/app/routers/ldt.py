from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.catalog import Gama, Difusor, Lente, LedType, ValidCombination
from ..schemas.models import (
    FluxDetail,
    FotometriaInfo,
    LDTFamily,
    LedFluxFactorRequest,
    LedFluxFactorResponse,
)
from ..services import ldt_loader
from ..core.led_flux import led_flux_factor as _led_flux_factor
from ..services.led_calculator import LedModelError
from ..services.luminaire_catalog import build_pmax_maps
from ..services.pcb_selector import select_pcb_for_config

router = APIRouter()


@router.get("/dimensions")
async def get_catalog_dimensions(db: Session = Depends(get_db)):
    """Public endpoint: all dimension tables + valid combinations for cascading UI."""
    gamas = [{"id": g.id, "name": g.name} for g in db.query(Gama).order_by(Gama.name).all()]
    difusores = [{"id": d.id, "name": d.name, "eficiencia": d.eficiencia} for d in db.query(Difusor).order_by(Difusor.name).all()]
    lentes = [{"id": l.id, "name": l.name, "eficiencia": l.eficiencia} for l in db.query(Lente).order_by(Lente.name).all()]
    led_types = [{"id": lt.id, "name": lt.name} for lt in db.query(LedType).order_by(LedType.name).all()]

    vcs = (
        db.query(ValidCombination)
        .options(
            joinedload(ValidCombination.gama),
            joinedload(ValidCombination.difusor),
            joinedload(ValidCombination.lente),
            joinedload(ValidCombination.led_type),
        )
        .all()
    )
    valid_combos = []
    for vc in vcs:
        valid_combos.append({
            "gama": vc.gama.name if vc.gama else None,
            "difusor": vc.difusor.name if vc.difusor else None,
            "lente": vc.lente.name if vc.lente else None,
            "led_type": vc.led_type.name if vc.led_type else None,
        })

    pmax_by_combo, pmax_source_by_combo = build_pmax_maps(db)

    return {
        "gamas": gamas,
        "difusores": difusores,
        "lentes": lentes,
        "led_types": led_types,
        "valid_combinations": valid_combos,
        "pmax_by_combo": pmax_by_combo,
        "pmax_source_by_combo": pmax_source_by_combo,
    }


@router.post("/led-flux-factor", response_model=LedFluxFactorResponse)
async def led_flux_factor(body: LedFluxFactorRequest):
    """LED bin flux ratio between the reference LDT CCT/CRI and the target.

    The FE uses this to align the live flux shown next to the power slider
    with the value the calculation engine produces for the same selection.
    Pure function: no DB lookup, no caching needed.
    """
    factor = _led_flux_factor(
        target_cct=body.target_cct,
        target_cri=body.target_cri,
        reference_cct=body.ref_cct,
        reference_cri=body.ref_cri,
    )
    return LedFluxFactorResponse(factor=factor)


@router.get("/list", response_model=list[FotometriaInfo])
async def list_ldts():
    """List all luminaires registered in the database."""
    ldts = ldt_loader.get_all_ldts()
    return [FotometriaInfo(
        id=ldt["id"],
        filename=ldt["filename"],
        luminaire_name=ldt["luminaire_name"],
        manufacturer=ldt.get("manufacturer", "Unknown"),
        model_family=ldt.get("model_family", "UNKNOWN"),
        cct=ldt.get("cct", 4000),
        cri=ldt.get("cri", 70),
        optic_family=ldt["optic_family"],
        power=ldt["power"],
        flux=ldt["flux"],
        efficiency=ldt["efficiency"],
        LORL=ldt["LORL"],
        isym=ldt["isym"],
        gama=ldt.get("gama"),
        difusor=ldt.get("difusor"),
        lente=ldt.get("lente"),
        led_type=ldt.get("led_type"),
        fotometria=ldt.get("fotometria"),
    ) for ldt in ldts]


@router.get("/families", response_model=list[LDTFamily])
async def list_families():
    """List LDTs grouped by optic family."""
    families = ldt_loader.get_families()
    return [LDTFamily(**f) for f in families]


@router.get("/catalog")
async def list_catalog():
    """List every available LDT with product metadata for UI filtering."""
    return [
        {
            "id": ldt["id"],
            "filename": ldt["filename"],
            "luminaire_name": ldt["luminaire_name"],
            "manufacturer": ldt.get("manufacturer", "Unknown"),
            "model_family": ldt.get("model_family", "UNKNOWN"),
            "cct": ldt.get("cct", 4000),
            "cri": ldt.get("cri", 70),
            "optic_family": ldt["optic_family"],
            "power": ldt["power"],
            "flux": ldt["flux"],
            "efficiency": ldt["efficiency"],
            "LORL": ldt["LORL"],
            "isym": ldt["isym"],
            "gama": ldt.get("gama"),
            "difusor": ldt.get("difusor"),
            "lente": ldt.get("lente"),
            "led_type": ldt.get("led_type"),
            "fotometria": ldt.get("fotometria"),
        }
        for ldt in ldt_loader.get_all_ldts()
    ]


@router.post("/upload")
async def upload_ldt(
    file: UploadFile = File(...),
    persist: bool = Form(False),
    manufacturer: str = Form("Custom"),
):
    """Upload an external LDT for temporary calculation use only."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty LDT file")
    if persist:
        raise HTTPException(
            status_code=400,
            detail="Use /api/admin/luminaires/upload to save luminaires in the database.",
        )

    try:
        info = ldt_loader.save_temporary_ldt(file.filename or "external.ldt", data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid LDT file: {exc}") from exc

    return FotometriaInfo(**{k: v for k, v in info.items() if k in ("id", "filename", "luminaire_name", "manufacturer", "model_family", "cct", "cri", "optic_family", "power", "flux", "efficiency", "LORL", "isym", "gama", "difusor", "lente", "led_type", "fotometria")})


@router.get("/{ldt_id}", response_model=FotometriaInfo)
async def get_ldt(ldt_id: str):
    """Get details for a specific LDT."""
    info = ldt_loader.get_ldt_by_id(ldt_id)
    if info is None:
        raise HTTPException(status_code=404, detail="LDT not found")
    return FotometriaInfo(**{k: v for k, v in info.items() if k in ("id", "filename", "luminaire_name", "manufacturer", "model_family", "cct", "cri", "optic_family", "power", "flux", "efficiency", "LORL", "isym", "gama", "difusor", "lente", "led_type", "fotometria")})


@router.get("/{ldt_id}/curve")
async def get_ldt_curve(ldt_id: str):
    """Get full photometric curve data for graphing."""
    info = ldt_loader.get_ldt_by_id(ldt_id, include_curve=True)
    if info is None:
        raise HTTPException(status_code=404, detail="LDT not found")
    c0_idx = 0
    c_step = info["C"][1] - info["C"][0] if len(info["C"]) > 1 else 90
    c90_idx = int(round(90 / c_step)) % len(info["C"])
    return {
        "id": ldt_id,
        "gamma": info["G"],
        "C0": info["I"][c0_idx],
        "C90": info["I"][c90_idx],
        "Mc": info["Mc"],
        "Ng": info["Ng"],
    }


@router.get("/{ldt_id}/photometric")
async def get_ldt_photometric(ldt_id: str):
    """Get full photometric data for 3D visualization."""
    info = ldt_loader.get_ldt_by_id(ldt_id, include_curve=True)
    if info is None:
        raise HTTPException(status_code=404, detail="LDT not found")
    ph = ldt_loader.get_photometry(ldt_id)
    if ph is None:
        raise HTTPException(status_code=404, detail="Photometric data not found")
    return {
        "id": ldt_id,
        "c": info["C"],
        "gamma": info["G"],
        "intensity": info["I"],
        "conv": ph.conv,
        "flux": ph.flux,
        "power": ph.power,
        "Mc": ph.Mc,
        "Ng": ph.Ng,
        "isym": info.get("isym", 0),
        "LORL": info.get("LORL", 0),
        "mf_origen": float(info.get("mf_origen", 1.0) or 1.0),
    }


class _FluxDetailRequest(BaseModel):
    gama: Optional[str] = None
    difusor: Optional[str] = None
    lente: Optional[str] = None
    led_type: Optional[str] = None
    cct: int = 4000
    cri: int = 70
    power: float = 0
    target_flux: Optional[float] = None
    i_op_ma: Optional[float] = None
    lm_w_min: Optional[float] = None
    driver_eficiencia: Optional[float] = None
    selected_pcb_ref: Optional[str] = None
    t_amb_c: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


@router.post("/flux-detail", response_model=FluxDetail)
async def get_flux_detail(body: _FluxDetailRequest, db: Session = Depends(get_db)):
    """Flux detail for a catalog 4-tuple: PCB info, LED efficacy, flux estimate with I_op and lm/W validation.

    Two modes:
    - ``power`` (W): original behaviour — compute flux from power.
    - ``target_flux`` (lm): select PCB that can achieve the requested flux
      while respecting ``i_op_ma`` and ``lm_w_min`` constraints, then
      return the computed power in ``p_total``.
    When both are set ``target_flux`` takes precedence.
    """
    detail = None
    try:
        detail = select_pcb_for_config(db, body)
    except LedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail="No PCB data for selected combination. Cannot calculate without N_LEDs/I_max/V_nominal.",
        )
    return detail
