"""Durable GIS-owned orchestration state for LuxStudio jobs."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GisProjectMembership(Base):
    __tablename__ = "gis_project_memberships"
    __table_args__ = (
        UniqueConstraint("project_id", "issuer", "subject", name="uq_gis_project_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="editor")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class GisLuxJob(Base):
    __tablename__ = "gis_lux_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "intent_id", name="uq_gis_lux_job_intent"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    zone_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    intent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    base_inventory_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    materialize_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    partial_policy: Mapped[str] = mapped_column(String(30), nullable=False, default="ALLOW_PARTIAL")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="optimize")
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="queued", index=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by_issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_by_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class GisLuxJobItem(Base):
    __tablename__ = "gis_lux_job_items"
    __table_args__ = (
        UniqueConstraint("job_id", "target_ref", name="uq_gis_lux_job_target"),
        UniqueConstraint("job_id", "operation_key", name="uq_gis_lux_operation"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    zone_id: Mapped[str] = mapped_column(String(50), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    target_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    calculation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    materialization_status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_requested")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    materialization_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class GisLuxOutbox(Base):
    __tablename__ = "gis_lux_outbox"
    __table_args__ = (UniqueConstraint("item_id", name="uq_gis_lux_outbox_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GisLuxMaterialization(Base):
    __tablename__ = "gis_lux_materializations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    materialization_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    zone_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="current", index=True)
    stale_relative_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    points: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
