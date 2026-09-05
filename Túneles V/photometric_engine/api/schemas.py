"""
Pydantic schemas for the Photometric Engine API.
"""
from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Tunnel ────────────────────────────────────────────────────────────────────

class TunnelCreate(BaseModel):
    name: str
    description: Optional[str] = None

    # Geometry
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    n_lanes: int = Field(default=2, ge=1, le=6)
    bidirectional: bool = False

    # CIE 88 inputs
    speed_kmh: float = Field(default=80.0, ge=30, le=140)
    L20_cd_m2: float = Field(gt=0)
    rtable: str = Field(default="R2", pattern="^(C1|C2|R[1-4]|N[1-4]|W[1-4])$")
    maintenance_factor: float = Field(default=0.80, gt=0, le=1)

    # Reflectances
    rho_road: float = Field(default=0.20, ge=0.05, le=0.50)
    rho_wall: float = Field(default=0.60, ge=0.10, le=0.95)
    rho_ceiling: float = Field(default=0.70, ge=0.10, le=0.95)


class TunnelRead(TunnelCreate):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ── Calculation ───────────────────────────────────────────────────────────────

class CalculationRequest(BaseModel):
    """Parameters to trigger a new calculation run."""
    tunnel_id: int
    cct: str = Field(default="4000K", pattern="^(4000K|3000K)$")
    I_max_mA: int = Field(default=750, ge=350, le=750)
    H_options: Optional[list[float]] = None   # mounting heights to try
    S_options: Optional[list[float]] = None   # spacings to try
    arrangements: Optional[list[str]] = None  # 'single', 'staggered', 'bilateral'
    include_radiosity: bool = True
    include_point_grid: bool = False           # store full point grid in DB


class ZoneResult(BaseModel):
    zone_type: str
    s_start: float
    s_end: float
    L_req: float

    L_avg: Optional[float] = None
    L_min: Optional[float] = None
    L_max: Optional[float] = None
    U0: Optional[float] = None
    Ul: Optional[float] = None
    E_h_avg: Optional[float] = None
    TI: Optional[float] = None
    EIR: Optional[float] = None
    compliant: Optional[bool] = None

    optic_id: Optional[str] = None
    model: Optional[str] = None
    current_mA: Optional[int] = None
    flux_lm: Optional[float] = None
    power_w: Optional[float] = None
    spacing_m: Optional[float] = None
    mounting_H: Optional[float] = None
    arrangement: Optional[str] = None
    n_luminaires: Optional[int] = None
    power_total_w: Optional[float] = None

    model_config = {"from_attributes": True}


class CalculationRead(BaseModel):
    id: int
    tunnel_id: int
    status: str
    created_at: datetime.datetime
    error_message: Optional[str] = None
    total_power_w: Optional[float] = None
    total_luminaires: Optional[int] = None
    overall_compliant: Optional[bool] = None
    zones: list[ZoneResult] = []

    model_config = {"from_attributes": True}


# ── Photometry info ───────────────────────────────────────────────────────────

class PhotometryInfo(BaseModel):
    optic_id: str
    filename: str
    c_planes: int
    g_angles: int
    flux_file_lm: float
