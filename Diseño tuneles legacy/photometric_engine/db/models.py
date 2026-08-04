"""
SQLAlchemy ORM models for the Photometric Engine.

Tables
------
tunnels           — Tunnel project definition
calculations      — Full photometric calculation run
zones             — Per-zone results within a calculation
luminaire_config  — Selected luminaire configuration for a zone
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ── Tunnel ────────────────────────────────────────────────────────────────────

class Tunnel(Base):
    __tablename__ = "tunnels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Geometry
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    width_m: Mapped[float] = mapped_column(Float, nullable=False)
    height_m: Mapped[float] = mapped_column(Float, nullable=False)
    n_lanes: Mapped[int] = mapped_column(Integer, default=2)
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=False)

    # CIE 88 inputs
    speed_kmh: Mapped[float] = mapped_column(Float, default=80.0)
    L20_cd_m2: Mapped[float] = mapped_column(Float, nullable=False)
    rtable: Mapped[str] = mapped_column(String(10), default="R2")
    maintenance_factor: Mapped[float] = mapped_column(Float, default=0.80)

    # Reflectances
    rho_road: Mapped[float] = mapped_column(Float, default=0.20)
    rho_wall: Mapped[float] = mapped_column(Float, default=0.60)
    rho_ceiling: Mapped[float] = mapped_column(Float, default=0.70)

    calculations: Mapped[list["Calculation"]] = relationship(
        back_populates="tunnel", cascade="all, delete-orphan"
    )


# ── Calculation ───────────────────────────────────────────────────────────────

class Calculation(Base):
    __tablename__ = "calculations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tunnel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tunnels.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )   # pending | running | done | failed
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Summary
    total_power_w: Mapped[Optional[float]] = mapped_column(Float)
    total_luminaires: Mapped[Optional[int]] = mapped_column(Integer)
    overall_compliant: Mapped[Optional[bool]] = mapped_column(Boolean)

    tunnel: Mapped["Tunnel"] = relationship(back_populates="calculations")
    zones: Mapped[list["ZoneCalc"]] = relationship(
        back_populates="calculation", cascade="all, delete-orphan"
    )


# ── Zone result ───────────────────────────────────────────────────────────────

class ZoneCalc(Base):
    __tablename__ = "zone_calculations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    calculation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("calculations.id", ondelete="CASCADE"), nullable=False
    )

    zone_type: Mapped[str] = mapped_column(String(30))
    s_start: Mapped[float] = mapped_column(Float)
    s_end: Mapped[float] = mapped_column(Float)

    # Normative requirements
    L_req: Mapped[float] = mapped_column(Float)
    U0_min: Mapped[float] = mapped_column(Float, default=0.40)
    Ul_min: Mapped[float] = mapped_column(Float, default=0.60)
    TI_max: Mapped[float] = mapped_column(Float, default=15.0)

    # Computed results
    L_avg: Mapped[Optional[float]] = mapped_column(Float)
    L_min: Mapped[Optional[float]] = mapped_column(Float)
    L_max: Mapped[Optional[float]] = mapped_column(Float)
    U0: Mapped[Optional[float]] = mapped_column(Float)
    Ul: Mapped[Optional[float]] = mapped_column(Float)
    E_h_avg: Mapped[Optional[float]] = mapped_column(Float)
    TI: Mapped[Optional[float]] = mapped_column(Float)
    EIR: Mapped[Optional[float]] = mapped_column(Float)
    compliant: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Selected design
    optic_id: Mapped[Optional[str]] = mapped_column(String(20))
    model: Mapped[Optional[str]] = mapped_column(String(10))
    current_mA: Mapped[Optional[int]] = mapped_column(Integer)
    flux_lm: Mapped[Optional[float]] = mapped_column(Float)
    power_w: Mapped[Optional[float]] = mapped_column(Float)
    spacing_m: Mapped[Optional[float]] = mapped_column(Float)
    mounting_H: Mapped[Optional[float]] = mapped_column(Float)
    arrangement: Mapped[Optional[str]] = mapped_column(String(20))
    n_luminaires: Mapped[Optional[int]] = mapped_column(Integer)
    power_total_w: Mapped[Optional[float]] = mapped_column(Float)

    # Full point grid stored as JSON (optional — can be large)
    point_grid_json: Mapped[Optional[dict]] = mapped_column(JSON)

    calculation: Mapped["Calculation"] = relationship(back_populates="zones")
