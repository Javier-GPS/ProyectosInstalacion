import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from ..core.text_utils import extract_cct, extract_model_family, extract_optic_family
from ..database import LDT_DIR
from ..models import Manufacturer, Fotometria
from ..salvi_lighting import parse_ldt


def parse_ldt_preview(data: bytes, filename: str) -> dict:
    """Parse an LDT file and return extracted fields for admin form preview."""
    tmp = LDT_DIR / "__preview__.ldt"
    tmp.write_bytes(data)
    try:
        d = parse_ldt(str(tmp))
    finally:
        tmp.unlink(missing_ok=True)

    name = d.get("lum_name", Path(filename).stem)
    lamp = d["lamp_sets"][0]
    return {
        "filename": filename,
        "luminaire_name": name,
        "manufacturer": d.get("company", "").strip() or "Unknown",
        "model_family": extract_model_family(name),
        "optic_family": extract_optic_family(name),
        "cct": extract_cct(name or Path(filename).stem),
        "cri": 70,
        "power": lamp["wattage"],
        "flux": lamp["flux_lm"],
        "efficiency": round(lamp["flux_lm"] / lamp["wattage"], 1) if lamp["wattage"] > 0 else 0,
        "LORL": d["LORL"],
        "isym": d["Isym"],
    }


def _get_or_create_manufacturer(db: Session, name: str) -> Manufacturer:
    m = db.query(Manufacturer).filter(Manufacturer.name == name).first()
    if m:
        return m
    m = Manufacturer(name=name)
    db.add(m)
    db.flush()
    return m


def create_luminaire(db: Session, data: dict) -> Fotometria:
    """Create a luminaire in DB and copy LDT file to ldt/ directory."""
    manufacturer = _get_or_create_manufacturer(db, data["manufacturer"])
    safe_filename = Path(data["filename"]).name
    ldt_relative = str(Path(manufacturer.name) / safe_filename)
    src = Path(data["ldt_temp_path"])
    dst = LDT_DIR / ldt_relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))

    # Resolve dimension FKs from names.
    from ..models.catalog import Gama, Difusor, Lente, LedType
    gama_id = None
    difusor_id = None
    lente_id = None
    led_type_id = None

    if data.get("gama"):
        g = db.query(Gama).filter(Gama.name == data["gama"].strip().upper()).first()
        if g:
            gama_id = g.id
    if data.get("difusor"):
        d = db.query(Difusor).filter(Difusor.name == data["difusor"].strip().upper()).first()
        if d:
            difusor_id = d.id
    if data.get("lente"):
        l = db.query(Lente).filter(Lente.name == data["lente"].strip().upper()).first()
        if l:
            lente_id = l.id
    if data.get("led_type"):
        lt = db.query(LedType).filter(LedType.name == data["led_type"].strip().upper()).first()
        if lt:
            led_type_id = lt.id

    lum = Fotometria(
        manufacturer_id=manufacturer.id,
        type=data["model_family"],
        optic_family=data["optic_family"],
        name=data["luminaire_name"],
        power=float(data["power"]),
        cct=int(data["cct"]),
        cri=int(data.get("cri", 70)),
        flux=float(data["flux"]),
        efficiency=float(data["efficiency"]),
        LORL=float(data["LORL"]),
        isym=int(data["isym"]),
        photometric_path=ldt_relative,
        gama_id=gama_id,
        difusor_id=difusor_id or 1,  # fallback to __LEGACY__
        lente_id=lente_id or 1,  # fallback to first lente
        led_type_id=led_type_id,
        fotometria=Path(safe_filename).stem,
    )
    db.add(lum)
    db.commit()
    db.refresh(lum)
    return lum


def update_luminaire(db: Session, lum_id: int, data: dict) -> Optional[Fotometria]:
    lum = db.query(Fotometria).filter(Fotometria.id == lum_id).first()
    if not lum:
        return None

    if "manufacturer" in data:
        manufacturer = _get_or_create_manufacturer(db, data["manufacturer"])
        lum.manufacturer_id = manufacturer.id
    if "model_family" in data:
        lum.type = data["model_family"]
    if "optic_family" in data:
        lum.optic_family = data["optic_family"]
    if "luminaire_name" in data:
        lum.name = data["luminaire_name"]
    if "power" in data:
        lum.power = float(data["power"])
    if "cct" in data:
        lum.cct = int(data["cct"])
    if "cri" in data:
        lum.cri = int(data["cri"])
    if "flux" in data:
        lum.flux = float(data["flux"])
    if "efficiency" in data:
        lum.efficiency = float(data["efficiency"])
    if "LORL" in data:
        lum.LORL = float(data["LORL"])
    if "isym" in data:
        lum.isym = int(data["isym"])

    # Dimension FK fields — resolve names to IDs.
    from ..models.catalog import Gama, Difusor, Lente, LedType
    if "gama" in data and data["gama"]:
        g = db.query(Gama).filter(Gama.name == data["gama"].strip().upper()).first()
        if g:
            lum.gama_id = g.id
    if "difusor" in data and data["difusor"]:
        d = db.query(Difusor).filter(Difusor.name == data["difusor"].strip().upper()).first()
        if d:
            lum.difusor_id = d.id
    if "lente" in data and data["lente"]:
        l = db.query(Lente).filter(Lente.name == data["lente"].strip().upper()).first()
        if l:
            lum.lente_id = l.id
    if "led_type" in data:
        if data["led_type"]:
            lt = db.query(LedType).filter(LedType.name == data["led_type"].strip().upper()).first()
            if lt:
                lum.led_type_id = lt.id
        else:
            lum.led_type_id = None

    # Handle LDT file replacement
    if "ldt_temp_path" in data:
        manufacturer_name = data.get("manufacturer")
        if not manufacturer_name:
            mfr = db.query(Manufacturer).filter(Manufacturer.id == lum.manufacturer_id).first()
            manufacturer_name = mfr.name if mfr else "Custom"
        safe_filename = Path(data.get("filename", Path(lum.photometric_path).name)).name
        new_relative = str(Path(manufacturer_name) / safe_filename)
        dst = LDT_DIR / new_relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(Path(data["ldt_temp_path"])), str(dst))

        # Remove old LDT if path changed
        old_path = LDT_DIR / lum.photometric_path
        if old_path.exists() and str(old_path) != str(dst):
            old_path.unlink(missing_ok=True)

        lum.photometric_path = new_relative
        if "filename" in data:
            lum.name = data.get("luminaire_name", lum.name)

    lum.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lum)
    return lum


def delete_luminaire(db: Session, lum_id: int) -> bool:
    lum = db.query(Fotometria).filter(Fotometria.id == lum_id).first()
    if not lum:
        return False

    ldt_file = LDT_DIR / lum.photometric_path
    if ldt_file.exists():
        ldt_file.unlink(missing_ok=True)

    db.delete(lum)
    db.commit()
    return True


def get_manufacturers(db: Session) -> list[Manufacturer]:
    return db.query(Manufacturer).order_by(Manufacturer.name).all()


def get_all_luminaires(db: Session) -> list[Fotometria]:
    return (
        db.query(Fotometria)
        .options(
            joinedload(Fotometria.manufacturer),
            joinedload(Fotometria.gama),
            joinedload(Fotometria.difusor),
            joinedload(Fotometria.lente),
            joinedload(Fotometria.led_type),
        )
        .order_by(Fotometria.name)
        .all()
    )


def get_luminaire_by_id(db: Session, lum_id: int) -> Optional[Fotometria]:
    return db.query(Fotometria).filter(Fotometria.id == lum_id).first()
