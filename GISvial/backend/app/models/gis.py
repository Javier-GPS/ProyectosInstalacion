"""GIS SQLAlchemy models.

All tables are prefixed ``gis_`` to coexist with LuxStudio tables in the same DB.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, PrimaryKeyConstraint,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base, engine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Zone ───────────────────────────────────────────────────────────────────
class GisZone(Base):
    __tablename__ = "gis_zones"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="")
    color: Mapped[str] = mapped_column(String(20), default="#4caf82")
    priority: Mapped[int] = mapped_column(Integer, default=2)
    center_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    center_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    zoom: Mapped[int] = mapped_column(Integer, default=12)
    bbox: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    est: Mapped[dict] = mapped_column(JSONB, default=dict)
    corridors: Mapped[list] = mapped_column(JSONB, default=list)
    bounds_polygon: Mapped[list] = mapped_column(JSONB, default=list)
    osm_relation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    config: Mapped["GisZoneConfig | None"] = relationship(
        "GisZoneConfig", back_populates="zone", uselist=False, cascade="all, delete-orphan"
    )
    osm_data: Mapped["GisZoneOsmData | None"] = relationship(
        "GisZoneOsmData", back_populates="zone", uselist=False, cascade="all, delete-orphan"
    )
    trees: Mapped["GisZoneTrees | None"] = relationship(
        "GisZoneTrees", back_populates="zone", uselist=False, cascade="all, delete-orphan"
    )


class GisZoneConfig(Base):
    __tablename__ = "gis_zone_config"
    zone_id: Mapped[str] = mapped_column(String(50), ForeignKey("gis_zones.id", ondelete="CASCADE"), primary_key=True)
    spacing: Mapped[int] = mapped_column(Integer, default=30)
    watt_hps: Mapped[float] = mapped_column(Float, default=150.0)
    watt_led: Mapped[float] = mapped_column(Float, default=60.0)
    efficacy: Mapped[float] = mapped_column(Float, default=90.0)
    hours_night: Mapped[float] = mapped_column(Float, default=11.5)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    zone: Mapped[GisZone] = relationship("GisZone", back_populates="config")


class GisZoneOsmData(Base):
    __tablename__ = "gis_zone_osm_data"
    zone_id: Mapped[str] = mapped_column(String(50), ForeignKey("gis_zones.id", ondelete="CASCADE"), primary_key=True)
    km_by_type: Mapped[dict] = mapped_column(JSONB, default=dict)
    ways: Mapped[list] = mapped_column(JSONB, default=list)
    source: Mapped[str] = mapped_column(String(50), default="estimated")
    loaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    zone: Mapped[GisZone] = relationship("GisZone", back_populates="osm_data")


class GisZoneTrees(Base):
    __tablename__ = "gis_zone_trees"
    zone_id: Mapped[str] = mapped_column(String(50), ForeignKey("gis_zones.id", ondelete="CASCADE"), primary_key=True)
    trees: Mapped[list] = mapped_column(JSONB, default=list)
    loaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    zone: Mapped[GisZone] = relationship("GisZone", back_populates="trees")


# ── Luminaires ─────────────────────────────────────────────────────────────
class GisLuminaire(Base):
    __tablename__ = "gis_luminaires"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    zone_id: Mapped[str] = mapped_column(String(50), ForeignKey("gis_zones.id", ondelete="CASCADE"), nullable=False)
    road_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lighting_class: Mapped[str | None] = mapped_column(String(10), nullable=True)
    street_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    watts: Mapped[float | None] = mapped_column(Float, nullable=True)
    spacing: Mapped[float | None] = mapped_column(Float, nullable=True)
    tilt: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    arm_len: Mapped[float | None] = mapped_column(Float, nullable=True)
    distribution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class GisInventoryLuminaire(Base):
    __tablename__ = "gis_inventory_luminaires"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[str] = mapped_column(String(50), ForeignKey("gis_zones.id", ondelete="CASCADE"), nullable=False)
    point_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lamp_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    support_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    circuit_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    line_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    way_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    road_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Photometric results ────────────────────────────────────────────────────
class GisPhotometricResult(Base):
    __tablename__ = "gis_photometric_results"
    __table_args__ = (UniqueConstraint("zone_id", "match_key", name="uq_gis_photo_zone_match"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[str] = mapped_column(String(50), ForeignKey("gis_zones.id", ondelete="CASCADE"), nullable=False)
    segment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    road_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    spacing: Mapped[float | None] = mapped_column(Float, nullable=True)
    lighting_class: Mapped[str | None] = mapped_column(String(10), nullable=True)
    power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    lm_em: Mapped[float | None] = mapped_column(Float, nullable=True)
    uo: Mapped[float | None] = mapped_column(Float, nullable=True)
    ui: Mapped[float | None] = mapped_column(Float, nullable=True)
    ti: Mapped[float | None] = mapped_column(Float, nullable=True)
    sr: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lente: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tilt: Mapped[float | None] = mapped_column(Float, nullable=True)
    phi_lm: Mapped[float | None] = mapped_column(Float, nullable=True)
    cumple: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Project UI config ──────────────────────────────────────────────────────
class GisProjectUiConfig(Base):
    __tablename__ = "gis_project_ui_config"
    __table_args__ = (PrimaryKeyConstraint("project_id", "config_key", name="pk_gis_ui_config"),)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False)
    config_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ── Helper ─────────────────────────────────────────────────────────────────
def ensure_gis_tables() -> None:
    GisZone.__table__.create(bind=engine, checkfirst=True)
    GisZoneConfig.__table__.create(bind=engine, checkfirst=True)
    GisZoneOsmData.__table__.create(bind=engine, checkfirst=True)
    GisZoneTrees.__table__.create(bind=engine, checkfirst=True)
    GisLuminaire.__table__.create(bind=engine, checkfirst=True)
    GisInventoryLuminaire.__table__.create(bind=engine, checkfirst=True)
    GisPhotometricResult.__table__.create(bind=engine, checkfirst=True)
    GisProjectUiConfig.__table__.create(bind=engine, checkfirst=True)
