"""
Calculations router — trigger and retrieve photometric calculation runs.

Flow
----
POST /calculations/         → create Calculation record (status=pending)
                              then run synchronously (small tunnels fast enough)
                              returns full result when done.

GET  /calculations/{id}     → retrieve a stored result.
GET  /calculations/?tunnel_id=N → list all runs for a tunnel.

The actual computation delegates to:
  OpticSelector   (selects optic + model per zone)
  TunnelCalculator (CIE 140 luminance + uniformity)
  Radiosity engine (indirect component if requested)
"""
from __future__ import annotations

import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db.database import get_db
from ...db.models import Calculation, ZoneCalc, Tunnel
from ...salvi_photometry.radiosity import TunnelSection, build_patches, solve_radiosity
from ...salvi_photometry.geometry import Observer
from ...tunnel_domain.cie88 import CIE88Params, build_zones
from ...tunnel_domain.optic_selector import OpticSelector
from ..schemas import CalculationRequest, CalculationRead

router = APIRouter(prefix="/calculations", tags=["calculations"])

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "photometries"

# Map optic_id → LDT file path
def _ldt_paths() -> dict[str, Path]:
    paths = {}
    for p in _DATA_DIR.glob("*.ldt"):
        # Extract optic_id from filename
        stem = p.stem.upper()
        for optic in ("F2MD", "F2M2", "F151"):
            if optic in stem:
                paths[optic] = p
                break
    return paths


@router.post("/", response_model=CalculationRead, status_code=status.HTTP_201_CREATED)
def run_calculation(body: CalculationRequest, db: Session = Depends(get_db)):
    """
    Trigger a complete photometric calculation for a tunnel.
    Runs synchronously and returns the full result.
    """
    tunnel = db.get(Tunnel, body.tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    # Create calculation record
    calc = Calculation(tunnel_id=tunnel.id, status="running")
    db.add(calc)
    db.commit()
    db.refresh(calc)

    try:
        result = _run(tunnel, body, calc.id, db)
    except Exception as exc:
        calc.status = "failed"
        calc.error_message = traceback.format_exc()
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Calculation failed: {exc}",
        )

    db.refresh(calc)
    return calc


@router.get("/", response_model=list[CalculationRead])
def list_calculations(
    tunnel_id: int | None = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(Calculation)
    if tunnel_id is not None:
        q = q.filter(Calculation.tunnel_id == tunnel_id)
    return q.order_by(Calculation.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{calc_id}", response_model=CalculationRead)
def get_calculation(calc_id: int, db: Session = Depends(get_db)):
    calc = db.get(Calculation, calc_id)
    if not calc:
        raise HTTPException(status_code=404, detail="Calculation not found")
    return calc


# ── Internal runner ──────────────────────────────────────────────────────────

def _run(
    tunnel:  Tunnel,
    body:    CalculationRequest,
    calc_id: int,
    db:      Session,
) -> None:
    """
    Core calculation: CIE 88 zones → OpticSelector → ZoneCalc records.
    """
    ldt_paths = _ldt_paths()
    if not ldt_paths:
        raise RuntimeError(f"No LDT files found in {_DATA_DIR}")

    selector = OpticSelector(
        ldt_paths=ldt_paths,
        rtable_name=tunnel.rtable,
        mf=tunnel.maintenance_factor,
        I_max_mA=body.I_max_mA,
        cct=body.cct,
    )

    params = CIE88Params(
        L20=tunnel.L20_cd_m2,
        speed_kmh=tunnel.speed_kmh,
        tunnel_length=tunnel.length_m,
        bidirectional=tunnel.bidirectional,
    )
    zones = build_zones(params)

    # Radiosity section (for indirect contribution)
    section = TunnelSection(
        width_m=tunnel.width_m,
        height_m=tunnel.height_m,
        rho_road=tunnel.rho_road,
        rho_wall=tunnel.rho_wall,
        rho_ceiling=tunnel.rho_ceiling,
    )
    patches = build_patches(section) if body.include_radiosity else []

    observer = Observer(lane_y_m=tunnel.width_m / 4.0)

    total_power = 0.0
    total_lums  = 0
    all_compliant = True

    for zone in zones:
        if zone.length < 0.5:
            continue

        candidate = selector.select_for_zone(
            zone=zone,
            road_width_m=tunnel.width_m,
            n_lanes=tunnel.n_lanes,
            H_options=body.H_options,
            S_options=body.S_options,
            arrangements=body.arrangements,
            observer=observer,
            speed_kmh=tunnel.speed_kmh,
            Lth=params.Lth,
            Lin=params.Lin,
        )

        zr = candidate.zone_result

        # Optional: add radiosity indirect component
        if body.include_radiosity and patches and zr and zr.point_grid:
            # Set direct illuminance on road patches from first calc point average
            avg_Eh = zr.E_h_avg if zr else 0.0
            for p in patches:
                if p.surface == "road":
                    p.E_direct = avg_Eh
            solve_radiosity(patches)

        # Store zone result
        point_grid_data = None
        if body.include_point_grid and zr and zr.point_grid:
            point_grid_data = [
                {"x": pr.x, "y": pr.y, "L": pr.L, "E_h": pr.E_h}
                for pr in zr.point_grid
            ]

        zc = ZoneCalc(
            calculation_id=calc_id,
            zone_type=zone.zone_type,
            s_start=zone.s_start,
            s_end=zone.s_end,
            L_req=zone.L_req,
            U0_min=zone.U0_min,
            Ul_min=zone.Ul_min,
            TI_max=zone.TI_max,
            L_avg=zr.L_avg if zr else None,
            L_min=zr.L_min if zr else None,
            L_max=zr.L_max if zr else None,
            U0=zr.U0 if zr else None,
            Ul=zr.Ul if zr else None,
            E_h_avg=zr.E_h_avg if zr else None,
            TI=zr.TI if zr else None,
            EIR=zr.EIR if zr else None,
            compliant=candidate.compliant,
            optic_id=candidate.optic_id,
            model=candidate.model,
            current_mA=candidate.current_mA,
            flux_lm=candidate.flux_lm,
            power_w=candidate.power_w,
            spacing_m=candidate.spacing_m,
            mounting_H=candidate.mounting_H,
            arrangement=candidate.arrangement,
            n_luminaires=candidate.n_luminaires,
            power_total_w=candidate.power_total_w,
            point_grid_json=point_grid_data,
        )
        db.add(zc)

        total_power += candidate.power_total_w or 0.0
        total_lums  += candidate.n_luminaires or 0
        if not candidate.compliant:
            all_compliant = False

    # Update calculation summary
    calc = db.get(Calculation, calc_id)
    calc.status = "done"
    calc.total_power_w = total_power
    calc.total_luminaires = total_lums
    calc.overall_compliant = all_compliant
    db.commit()
