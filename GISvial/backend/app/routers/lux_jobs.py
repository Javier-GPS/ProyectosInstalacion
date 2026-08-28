"""Public and internal endpoints for the durable GIS→Lux workflow."""
from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import (
    GisLuxJob, GisLuxJobItem, GisLuxMaterialization, GisLuxOutbox,
    GisPlanningDraft, GisZone, GisZoneOsmData,
)
from ..schemas.lux_jobs import LuxJobCreate, LuxJobItemView, LuxJobView
from ..services.access import project_for
from ..services.lux_jobs import JobItemError, digest, effective_patch, materialization_points, refresh_job
from ..services.planning import normalize_inventory
from .deps import Principal, current_principal, worker_principal

router = APIRouter()


def _target_lock_id(project_id: int, zone_id: str, target_ref: str) -> int:
    raw = int.from_bytes(
        hashlib.sha256(f"{project_id}:{zone_id}:{target_ref}".encode()).digest()[:8],
        "big",
        signed=False,
    )
    return raw - (1 << 64) if raw >= (1 << 63) else raw


def _deliver_outbox(db: Session, item_id: str) -> None:
    outbox = db.query(GisLuxOutbox).filter(GisLuxOutbox.item_id == item_id).first()
    if outbox:
        outbox.delivered_at = datetime.now(timezone.utc)


def _item_view(item: GisLuxJobItem) -> LuxJobItemView:
    return LuxJobItemView(
        id=item.id,
        target_ref=item.target_ref,
        state=item.state,
        calculation_status=item.calculation_status,
        materialization_status=item.materialization_status,
        error_code=item.error_code,
        error_message=item.error_message,
        result_hash=item.result_hash,
    )


def _job_view(job: GisLuxJob, items: list[GisLuxJobItem]) -> LuxJobView:
    return LuxJobView(
        id=job.id,
        project_id=job.project_id,
        zone_id=job.zone_id,
        intent_id=job.intent_id,
        state=job.state,
        state_version=job.state_version,
        total=job.total,
        succeeded=job.succeeded,
        failed=job.failed,
        blocked=job.blocked,
        unknown=job.unknown,
        materialize_valid=job.materialize_valid,
        partial_policy=job.partial_policy,
        mode=job.mode,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        items=[_item_view(item) for item in items],
    )


def _get_job(db: Session, project_id: int, job_id: str) -> tuple[GisLuxJob, list[GisLuxJobItem]]:
    job = db.get(GisLuxJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Lux job not found")
    items = db.query(GisLuxJobItem).filter(
        GisLuxJobItem.job_id == job.id,
    ).order_by(GisLuxJobItem.created_at, GisLuxJobItem.id).all()
    return job, items


@router.post("/api/projects/{project_id}/lux/jobs", status_code=202)
async def create_lux_job(
    project_id: int,
    body: LuxJobCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    if not settings.lux_job_enabled:
        raise HTTPException(status_code=503, detail="Lux jobs are disabled")
    if not idempotency_key or len(idempotency_key) > 64:
        raise HTTPException(status_code=400, detail="Idempotency-Key is required")
    project_for(principal, db, project_id, write=True)
    zone = db.get(GisZone, body.zone_id)
    if zone is None or zone.project_id != project_id:
        raise HTTPException(status_code=404, detail="Zone not found in project")
    osm = db.get(GisZoneOsmData, body.zone_id)
    if osm is None or not isinstance(osm.ways, list):
        raise HTTPException(status_code=409, detail="OSM inventory unavailable")
    inventory = normalize_inventory(body.zone_id, osm.ways)
    if inventory["base_inventory_hash"] != body.base_inventory_hash:
        raise HTTPException(status_code=409, detail="STALE_OSM_INVENTORY")
    targets = {target["target_ref"]: target for target in inventory["targets"]}
    target_refs = list(dict.fromkeys(body.target_refs))
    if len(target_refs) != len(body.target_refs) or any(ref not in targets for ref in target_refs):
        raise HTTPException(status_code=422, detail="Unknown or duplicate target_ref")
    if any(not targets[ref].get("geometry") for ref in target_refs):
        raise HTTPException(status_code=422, detail="Selected target has no geometry")
    draft = db.get(GisPlanningDraft, body.zone_id)
    draft_revision = draft.revision if draft else 0
    payload = draft.payload if draft else {"group_defaults": {}, "target_overrides": {}}
    request_digest = digest({
        "project_id": project_id,
        "zone_id": body.zone_id,
        "target_refs": target_refs,
        "base_inventory_hash": body.base_inventory_hash,
        "draft_revision": draft_revision,
        "materialize_valid": True,
        "mode": body.mode,
    })
    existing = db.query(GisLuxJob).filter(
        GisLuxJob.project_id == project_id,
        GisLuxJob.intent_id == idempotency_key,
    ).first()
    if existing:
        if existing.request_digest != request_digest:
            raise HTTPException(status_code=409, detail="INTENT_REUSE_CONFLICT")
        items = db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == existing.id).all()
        return JSONResponse(
            status_code=202,
            content=_job_view(existing, items).model_dump(),
            headers={"Location": f"/api/projects/{project_id}/lux/jobs/{existing.id}", "ETag": f'"job:{existing.id}:{existing.state_version}"'},
        )

    job_id = uuid.uuid4().hex
    job = GisLuxJob(
        id=job_id,
        project_id=project_id,
        zone_id=body.zone_id,
        intent_id=idempotency_key,
        request_digest=request_digest,
        base_inventory_hash=body.base_inventory_hash,
        draft_revision=draft_revision,
        materialize_valid=True,
        partial_policy="ALLOW_PARTIAL",
        mode=body.mode,
        state="queued",
        total=len(target_refs),
        requested_by_user_id=principal.user.id,
        requested_by_issuer=principal.issuer,
        requested_by_sub=principal.subject,
    )
    db.add(job)
    for target_ref in target_refs:
        target = dict(targets[target_ref])
        group = next((g for g in inventory["groups"] if g["group_ref"] == target.get("group_ref")), {})
        target["road_type"] = group.get("road_type")
        snapshot = {
            "target": target,
            "params": effective_patch(payload, target),
            "base_inventory_hash": body.base_inventory_hash,
            "draft_revision": draft_revision,
            "osm_loaded_at": osm.loaded_at.isoformat() if osm.loaded_at else None,
            "mode": body.mode,
        }
        item_id = uuid.uuid4().hex
        input_hash = digest(snapshot)
        operation_key = digest({"project_id": project_id, "target_ref": target_ref, "input_hash": input_hash})
        db.add(GisLuxJobItem(
            id=item_id,
            job_id=job_id,
            project_id=project_id,
            zone_id=body.zone_id,
            target_ref=target_ref,
            operation_key=operation_key,
            target_snapshot=snapshot,
            input_hash=input_hash,
        ))
        db.add(GisLuxOutbox(item_id=item_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(GisLuxJob).filter(
            GisLuxJob.project_id == project_id,
            GisLuxJob.intent_id == idempotency_key,
        ).first()
        if existing is None:
            raise
        if existing.request_digest != request_digest:
            raise HTTPException(status_code=409, detail="INTENT_REUSE_CONFLICT")
        items = db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == existing.id).all()
        return JSONResponse(
            status_code=202,
            content=_job_view(existing, items).model_dump(),
            headers={"Location": f"/api/projects/{project_id}/lux/jobs/{existing.id}", "ETag": f'"job:{existing.id}:{existing.state_version}"'},
        )
    db.refresh(job)
    items = db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all()
    return JSONResponse(
        status_code=202,
        content=_job_view(job, items).model_dump(),
        headers={"Location": f"/api/projects/{project_id}/lux/jobs/{job.id}", "ETag": f'"job:{job.id}:{job.state_version}"'},
    )


@router.get("/api/projects/{project_id}/lux/jobs/{job_id}")
async def get_lux_job(
    project_id: int,
    job_id: str,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project_for(principal, db, project_id)
    job, items = _get_job(db, project_id, job_id)
    etag = f'"job:{job.id}:{job.state_version}"'
    if if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(content=_job_view(job, items).model_dump(), headers={"ETag": etag})


@router.post("/api/projects/{project_id}/lux/jobs/{job_id}/cancel")
async def cancel_lux_job(
    project_id: int,
    job_id: str,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project_for(principal, db, project_id, write=True)
    job, items = _get_job(db, project_id, job_id)
    if job.state in {"succeeded", "partial", "failed", "cancelled", "unknown"}:
        raise HTTPException(status_code=409, detail="JOB_ALREADY_TERMINAL")
    job.cancel_requested = True
    for item in items:
        if item.state in {"pending", "running", "materializing"}:
            item.state = "cancelled"
            item.calculation_status = "cancelled"
            item.materialization_status = "cancelled"
            _deliver_outbox(db, item.id)
    refresh_job(job, items)
    db.commit()
    return _job_view(job, items)


@router.post("/api/internal/lux/items/{item_id}/materialize")
async def materialize_lux_item(
    item_id: str,
    project_id: int | None = Header(default=None, alias="X-Project-ID"),
    lease_token: int | None = Header(default=None, alias="X-Lux-Lease-Token"),
    _worker: dict = Depends(worker_principal),
    db: Session = Depends(get_db),
):
    item = db.query(GisLuxJobItem).filter(
        GisLuxJobItem.id == item_id,
    ).with_for_update().one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Job item not found")
    if project_id is None:
        raise HTTPException(status_code=400, detail="X-Project-ID required")
    if item.project_id != project_id:
        raise HTTPException(status_code=403, detail="Project mismatch")
    now = datetime.now(timezone.utc)
    if item.lease_until is not None and item.lease_until.tzinfo is None:
        now = now.replace(tzinfo=None)
    if lease_token is None or item.lease_token != lease_token or item.lease_until is None or item.lease_until <= now:
        raise HTTPException(status_code=409, detail="LEASE_FENCED")
    job = db.get(GisLuxJob, item.job_id)
    if (
        job is None
        or job.project_id != item.project_id
        or job.zone_id != item.zone_id
        or not job.materialize_valid
        or job.cancel_requested
    ):
        raise HTTPException(status_code=409, detail="MATERIALIZATION_BLOCKED")
    if item.calculation_status != "conforming" or not item.result_json or not item.result_hash:
        raise HTTPException(status_code=409, detail="RESULT_NOT_CONFORMING")
    zone = db.get(GisZone, item.zone_id)
    draft = db.get(GisPlanningDraft, item.zone_id)
    current_draft_revision = draft.revision if draft else 0
    if zone is None or zone.project_id != item.project_id:
        item.state = "stale"
        item.materialization_status = "stale"
        item.error_code = "STALE_ZONE"
        item.error_message = "Zone project scope changed"
        refresh_job(job, db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all())
        _deliver_outbox(db, item.id)
        db.commit()
        raise HTTPException(status_code=409, detail="STALE_ZONE")
    if current_draft_revision != job.draft_revision or (
        draft is not None and draft.base_inventory_hash != job.base_inventory_hash
    ):
        item.state = "stale"
        item.materialization_status = "stale"
        item.error_code = "STALE_DRAFT"
        item.error_message = "Planning draft changed; create a new intent"
        refresh_job(job, db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all())
        _deliver_outbox(db, item.id)
        db.commit()
        raise HTTPException(status_code=409, detail="STALE_DRAFT")
    osm = db.get(GisZoneOsmData, item.zone_id)
    if osm is None or not isinstance(osm.ways, list):
        item.state = "stale"
        item.materialization_status = "stale"
        item.error_code = "STALE_OSM"
        item.error_message = "OSM inventory is no longer available"
        _deliver_outbox(db, item.id)
        db.commit()
        raise HTTPException(status_code=409, detail="STALE_OSM")
    current_inventory = normalize_inventory(item.zone_id, osm.ways)
    if current_inventory["base_inventory_hash"] != job.base_inventory_hash:
        item.state = "stale"
        item.materialization_status = "stale"
        item.error_code = "STALE_OSM"
        item.error_message = "OSM inventory changed; create a new intent"
        _deliver_outbox(db, item.id)
        db.commit()
        raise HTTPException(status_code=409, detail="STALE_OSM")
    snapshot = item.target_snapshot
    try:
        points = materialization_points(snapshot, item.result_json)
    except JobItemError as exc:
        item.state = "blocked"
        item.materialization_status = "blocked"
        item.error_code = exc.code
        item.error_message = exc.message
        _deliver_outbox(db, item.id)
        db.commit()
        raise HTTPException(status_code=422, detail=exc.message) from exc
    key = item.materialization_key or digest({"item_id": item.id, "result_hash": item.result_hash})
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {
        "lock_id": _target_lock_id(item.project_id, item.zone_id, item.target_ref),
    })
    existing = db.query(GisLuxMaterialization).filter(GisLuxMaterialization.materialization_key == key).first()
    if existing:
        if existing.result_hash != item.result_hash:
            raise HTTPException(status_code=409, detail="MATERIALIZATION_KEY_CONFLICT")
        item.materialization_key = key
        item.state = "succeeded"
        item.materialization_status = "applied"
        refresh_job(job, db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all())
        _deliver_outbox(db, item.id)
        db.commit()
        return {"status": "applied", "materialization_id": existing.id, "points": len(existing.points)}

    current = db.query(GisLuxMaterialization).filter(
        GisLuxMaterialization.project_id == item.project_id,
        GisLuxMaterialization.zone_id == item.zone_id,
        GisLuxMaterialization.target_ref == item.target_ref,
        GisLuxMaterialization.state == "current",
    ).first()
    if current:
        current.state = "history"
        current.stale_relative_to = item.result_hash
    materialization = GisLuxMaterialization(
        id=uuid.uuid4().hex,
        materialization_key=key,
        job_id=job.id,
        item_id=item.id,
        project_id=item.project_id,
        zone_id=item.zone_id,
        target_ref=item.target_ref,
        result_hash=item.result_hash,
        input_hash=item.input_hash,
        target_revision=digest({"inventory": job.base_inventory_hash, "target": snapshot["target"]}),
        state="current",
        points=points,
    )
    db.add(materialization)
    item.materialization_key = key
    item.materialization_status = "applied"
    item.state = "succeeded"
    item.error_code = None
    item.error_message = None
    items = db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all()
    refresh_job(job, items)
    _deliver_outbox(db, item.id)
    db.commit()
    readback = db.get(GisLuxMaterialization, materialization.id)
    if readback is None or readback.result_hash != item.result_hash or readback.state != "current":
        raise HTTPException(status_code=409, detail="READBACK_MISMATCH")
    return {"status": "applied", "materialization_id": readback.id, "points": len(readback.points)}
