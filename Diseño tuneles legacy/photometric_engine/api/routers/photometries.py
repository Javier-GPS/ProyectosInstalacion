"""
Photometry info router — list available LDT files and their metadata.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...salvi_photometry.ldt_parser import load_ldt
from ..schemas import PhotometryInfo

router = APIRouter(prefix="/photometries", tags=["photometries"])

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "photometries"


@router.get("/", response_model=list[PhotometryInfo])
def list_photometries():
    """List all LDT photometric files available in the data directory."""
    result = []
    for ldt_path in sorted(_DATA_DIR.glob("*.ldt")):
        try:
            phot = load_ldt(ldt_path)
            result.append(PhotometryInfo(
                optic_id=phot.optic_id(),
                filename=ldt_path.name,
                c_planes=len(phot.c_angles),
                g_angles=len(phot.g_angles),
                flux_file_lm=phot._flux_file_lm,
            ))
        except Exception as exc:
            # Log but don't crash the listing
            result.append(PhotometryInfo(
                optic_id="ERROR",
                filename=ldt_path.name,
                c_planes=0,
                g_angles=0,
                flux_file_lm=0.0,
            ))
    return result


@router.get("/{optic_id}", response_model=PhotometryInfo)
def get_photometry(optic_id: str):
    """Return metadata for a specific optic by ID (e.g. F2MD, F2M2, F151)."""
    for ldt_path in _DATA_DIR.glob("*.ldt"):
        try:
            phot = load_ldt(ldt_path)
            if phot.optic_id().upper() == optic_id.upper():
                return PhotometryInfo(
                    optic_id=phot.optic_id(),
                    filename=ldt_path.name,
                    c_planes=len(phot.c_angles),
                    g_angles=len(phot.g_angles),
                    flux_file_lm=phot._flux_file_lm,
                )
        except Exception:
            pass
    raise HTTPException(status_code=404, detail=f"Photometry '{optic_id}' not found")
