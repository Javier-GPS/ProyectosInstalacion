from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session, joinedload

from ..core.text_utils import extract_cct, extract_model_family, extract_optic_family
from ..database import BACKEND_DIR, DATA_DIR, LDT_DIR, SessionLocal
from ..models import Fotometria
from ..salvi_lighting import parse_ldt, Photometry

TEMP_LDT_DIR = DATA_DIR / "temp_ldt"
TEMP_LDT_DIR.mkdir(parents=True, exist_ok=True)
_TEMP_LDTS: OrderedDict[str, dict] = OrderedDict()
_TEMP_LDTS_MAX = 128


def _lum_to_dict(lum: Fotometria) -> dict:
    """Convert a DB Fotometria model to the dict format used by existing code."""
    return {
        "id": str(lum.id),
        "filename": Path(lum.photometric_path).name,
        "relative_path": lum.photometric_path,
        "luminaire_name": lum.name,
        "manufacturer": lum.manufacturer.name if lum.manufacturer else "Unknown",
        "model_family": lum.type,
        "cct": lum.cct,
        "cri": getattr(lum, "cri", 70) or 70,
        "optic_family": lum.optic_family,
        "power": lum.power,
        "flux": lum.flux,
        "efficiency": lum.efficiency,
        "LORL": lum.LORL,
        "isym": lum.isym,
        "gama": lum.gama.name if getattr(lum, "gama", None) else None,
        "difusor": lum.difusor.name if getattr(lum, "difusor", None) else None,
        "lente": lum.lente.name if getattr(lum, "lente", None) else None,
        "led_type": lum.led_type.name if getattr(lum, "led_type", None) else None,
        "fotometria": getattr(lum, "fotometria", None),
        "mf_origen": float(getattr(lum, "mf_origen", 1.0) or 1.0),
    }


def _parsed_to_info(parsed: dict, filename: str, temp_id: str, path: Path) -> dict:
    name = parsed.get("lum_name") or Path(filename).stem
    lamp = parsed["lamp_sets"][0]
    power = float(lamp["wattage"])
    flux = float(lamp["flux_lm"])
    return {
        "id": temp_id,
        "filename": Path(filename).name,
        "relative_path": str(path),
        "absolute_path": str(path),
        "luminaire_name": name,
        "manufacturer": parsed.get("company", "").strip() or "External",
        "model_family": extract_model_family(name or filename),
        "cct": extract_cct(name or filename),
        "cri": 70,
        "optic_family": extract_optic_family(name),
        "power": power,
        "flux": flux,
        "efficiency": round(flux / power, 1) if power > 0 else 0,
        "LORL": parsed["LORL"],
        "isym": parsed["Isym"],
        "mf_origen": 1.0,
    }


@lru_cache(maxsize=1)
def _load_all_cached() -> tuple[tuple[tuple[str, object], ...], ...]:
    """Load all fotometrias from the database. Returns [] when empty."""
    db: Session = SessionLocal()
    try:
        fotometrias = (
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
        return tuple(tuple(_lum_to_dict(l).items()) for l in fotometrias)
    finally:
        db.close()


@lru_cache(maxsize=1)
def _load_by_id_cached() -> dict[str, tuple[tuple[str, object], ...]]:
    return {str(dict(items)["id"]): items for items in _load_all_cached()}


def _resolve_photometric_path(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    path = Path(relative_path.replace("\\", "/"))
    if path.is_absolute():
        return path
    candidates = [
        BACKEND_DIR / path,
        LDT_DIR / path,
    ]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def get_all_ldts():
    """Get all luminaire entries from the database."""
    return [dict(items) for items in _load_all_cached()]


def refresh_ldt_cache():
    """Clear derived caches so data is re-fetched on next call."""
    _load_by_id_cached.cache_clear()
    _load_all_cached.cache_clear()
    get_photometry.cache_clear()
    return get_all_ldts()


def save_temporary_ldt(filename: str, data: bytes) -> dict:
    """Validate and store an external LDT for this backend process only."""
    safe_filename = Path(filename or "external.ldt").name
    temp_id = f"temp-{uuid4().hex}"
    temp_path = TEMP_LDT_DIR / f"{temp_id}_{safe_filename}"
    temp_path.write_bytes(data)
    try:
        parsed = parse_ldt(str(temp_path))
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    if len(_TEMP_LDTS) >= _TEMP_LDTS_MAX:
        _TEMP_LDTS.popitem(last=False)
    info = _parsed_to_info(parsed, safe_filename, temp_id, temp_path)
    _TEMP_LDTS[temp_id] = info
    get_photometry.cache_clear()
    refresh_ldt_curve_cache()
    return info


def get_families():
    """List LDTs grouped by optic family."""
    ldts = get_all_ldts()
    families: dict[str, list] = {}
    for ldt in ldts:
        families.setdefault(ldt["optic_family"], []).append(ldt)
    result = []
    for code, members in sorted(families.items()):
        members.sort(key=lambda x: x["power"])
        result.append({
            "code": code,
            "description": f"Optical family {code} ({len(members)} variants)",
            "ldts": [_ldt_to_info(m) for m in members],
        })
    return result


def _ldt_to_info(m):
    return {
        "id": m["id"],
        "filename": m["filename"],
        "luminaire_name": m["luminaire_name"],
        "manufacturer": m.get("manufacturer", "Unknown"),
        "model_family": m.get("model_family", "UNKNOWN"),
        "cct": m.get("cct", 4000),
        "cri": m.get("cri", 70),
        "optic_family": m["optic_family"],
        "power": m["power"],
        "flux": m["flux"],
        "efficiency": m["efficiency"],
        "LORL": m["LORL"],
        "isym": m["isym"],
        "gama": m.get("gama"),
        "difusor": m.get("difusor"),
        "lente": m.get("lente"),
        "led_type": m.get("led_type"),
        "fotometria": m.get("fotometria"),
        "mf_origen": float(m.get("mf_origen", 1.0) or 1.0),
    }


@lru_cache(maxsize=256)
def _parse_ldt_cached(path_str: str) -> dict | None:
    """Parse an LDT file from disk, cached by path."""
    try:
        return parse_ldt(path_str)
    except Exception:
        return None


def _with_curve_data(info: dict) -> dict:
    """Return LDT metadata plus parsed EULUMDAT arrays when the file exists."""
    result = dict(info)
    path = (
        Path(result["absolute_path"])
        if "absolute_path" in result
        else _resolve_photometric_path(result.get("relative_path"))
    )
    if path and path.exists():
        d = _parse_ldt_cached(str(path))
        if d:
            result["Mc"] = d["Mc"]
            result["Ng"] = d["Ng"]
            result["C"] = d["C"]
            result["G"] = d["G"]
            result["I"] = d["I"]
    return result


def get_ldt_by_id(ldt_id: str, include_curve: bool = False):
    """Get LDT info dict by ID.

    Metadata lookups stay lightweight for calculation paths. Endpoints
    that need C/G/I curve arrays can pass ``include_curve=True``.
    """
    if ldt_id in _TEMP_LDTS:
        result = dict(_TEMP_LDTS[ldt_id])
        return _with_curve_data(result) if include_curve else result

    cached = _load_by_id_cached().get(str(ldt_id))
    if cached is not None:
        result = dict(cached)
        return _with_curve_data(result) if include_curve else result
    return None


def get_ldt_path(ldt_id: str):
    """Get full filesystem path to an LDT file by ID."""
    info = get_ldt_by_id(ldt_id)
    if info is None:
        return None
    if "absolute_path" in info:
        return info["absolute_path"]
    path = _resolve_photometric_path(info.get("relative_path"))
    return str(path) if path else None


@lru_cache(maxsize=128)
def get_photometry(ldt_id: str):
    """Get Photometry object for a given LDT ID (cached in memory)."""
    path = get_ldt_path(ldt_id)
    if path is None:
        return None
    d = parse_ldt(path)
    return Photometry(d)


def refresh_ldt_curve_cache():
    """Clear the per-file curve parse cache (e.g. after temp LDT upload)."""
    _parse_ldt_cached.cache_clear()
