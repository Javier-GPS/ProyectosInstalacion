"""Durable GIS worker. Run with ``python -m app.worker``."""
from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from .core.config import settings
from .core.database import SessionLocal
from .models import GisLuxJob, GisLuxJobItem, GisLuxOutbox
from .services.lux_jobs import JobItemError, build_lux_config, digest, refresh_job


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_url() -> str:
    if settings.oidc_token_url:
        return settings.oidc_token_url
    issuer = settings.oidc_issuer_url.rstrip("/")
    return f"{issuer}/protocol/openid-connect/token"


def _service_token(client: httpx.Client) -> str:
    response = client.post(
        _token_url(),
        data={
            "grant_type": "client_credentials",
            "client_id": settings.lux_worker_client_id,
            "client_secret": settings.lux_worker_client_secret,
        },
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Keycloak returned no worker access token")
    return str(token)


def _claim(db: Session) -> tuple[str, int] | None:
    now = _now()
    item = db.query(GisLuxJobItem).join(
        GisLuxJob, GisLuxJob.id == GisLuxJobItem.job_id,
    ).join(
        GisLuxOutbox, GisLuxOutbox.item_id == GisLuxJobItem.id,
    ).filter(
        GisLuxJob.cancel_requested.is_(False),
        GisLuxOutbox.delivered_at.is_(None),
        GisLuxOutbox.available_at <= now,
        GisLuxJobItem.state.in_(["pending", "running", "materializing"]),
        (GisLuxJobItem.lease_until.is_(None) | (GisLuxJobItem.lease_until < now)),
    ).order_by(GisLuxJobItem.created_at).with_for_update(skip_locked=True).first()
    if item is None:
        return None
    item.state = "running"
    item.lease_owner = settings.lux_worker_id or socket.gethostname()
    item.lease_token += 1
    item.lease_until = now + timedelta(seconds=settings.lux_job_lease_seconds)
    item.attempt += 1
    outbox = db.query(GisLuxOutbox).filter(GisLuxOutbox.item_id == item.id).one()
    outbox.attempts += 1
    job = db.get(GisLuxJob, item.job_id)
    if job and job.state == "queued":
        job.state = "running"
    if job:
        job.state_version += 1
    db.commit()
    return item.id, item.lease_token


def _mark_outbox_delivered(db: Session, item_id: str) -> None:
    outbox = db.query(GisLuxOutbox).filter(GisLuxOutbox.item_id == item_id).first()
    if outbox:
        outbox.delivered_at = _now()


def _set_failure(db: Session, item_id: str, lease_token: int, state: str, code: str, message: str) -> None:
    item = db.get(GisLuxJobItem, item_id)
    if item is None or item.lease_token != lease_token:
        return
    job = db.get(GisLuxJob, item.job_id)
    if job and job.cancel_requested and state != "unknown":
        state, code, message = "cancelled", "CANCELLED", "Job cancelado"
    item.state = state
    if state == "unknown":
        item.calculation_status = "unknown"
    elif state == "cancelled":
        item.calculation_status = "cancelled"
    elif not (state in {"blocked", "stale"} and item.calculation_status == "conforming"):
        item.calculation_status = "failed"
    item.materialization_status = (
        "unknown" if state == "unknown"
        else "cancelled" if state == "cancelled"
        else "blocked"
    )
    item.error_code = code
    item.error_message = message[:500]
    if job:
        refresh_job(job, db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all())
    _mark_outbox_delivered(db, item_id)
    db.commit()


def _process(item_id: str, lease_token: int, client: httpx.Client, token: str) -> None:
    with SessionLocal() as db:
        item = db.get(GisLuxJobItem, item_id)
        if item is None or item.lease_token != lease_token:
            return
        job = db.get(GisLuxJob, item.job_id)
        if job is None or job.cancel_requested:
            _set_failure(db, item_id, lease_token, "cancelled", "CANCELLED", "Job cancelado")
            return
        try:
            config = build_lux_config(item.target_snapshot)
        except JobItemError as exc:
            _set_failure(db, item_id, lease_token, "blocked", exc.code, exc.message)
            return

    url = f"{settings.luxstudio_api_url.rstrip('/')}/api/internal/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": item.operation_key,
        "X-Project-ID": str(job.project_id),
        "X-Lux-Lease-Token": str(lease_token),
    }
    try:
        if job.mode == "optimize":
            response = client.post(
                f"{url}optimize",
                json={
                    "config": config,
                    "variables": {"power": True, "spacing": False, "height": False, "arm_length": False, "tilt": False, "optic_family": False},
                    "limits": {},
                    "objective": "technical_limits",
                },
                headers=headers,
            )
        else:
            response = client.post(
                f"{url}calculate",
                params={"skip_optimization": "true"},
                json=config,
                headers=headers,
            )
        response.raise_for_status()
        raw_result = response.json()
        if job.mode == "optimize":
            if not raw_result.get("result"):
                raise RuntimeError(raw_result.get("message") or "Lux optimization produced no result")
            result = raw_result["result"]
        else:
            result = raw_result
    except httpx.TimeoutException as exc:
        with SessionLocal() as db:
            _set_failure(db, item_id, lease_token, "unknown", "LUX_TIMEOUT", str(exc))
        return
    except httpx.HTTPStatusError as exc:
        with SessionLocal() as db:
            _set_failure(db, item_id, lease_token, "failed", "LUX_HTTP", f"Lux HTTP {exc.response.status_code}")
        return
    except Exception as exc:
        with SessionLocal() as db:
            _set_failure(db, item_id, lease_token, "unknown", "LUX_UNKNOWN", str(exc))
        return

    result_hash = digest(result)
    conforming = result.get("compliant") is True
    with SessionLocal() as db:
        item = db.get(GisLuxJobItem, item_id)
        job = db.get(GisLuxJob, item.job_id) if item else None
        if item is None or job is None or item.lease_token != lease_token:
            return
        if job.cancel_requested:
            item.state = "cancelled"
            item.calculation_status = "cancelled"
            item.materialization_status = "cancelled"
            refresh_job(job, db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all())
            _mark_outbox_delivered(db, item_id)
            db.commit()
            return
        item.result_json = result
        item.result_hash = result_hash
        item.calculation_status = "conforming" if conforming else "non_conforming"
        item.state = "materializing" if conforming else "blocked"
        item.materialization_status = "pending" if conforming else "blocked"
        item.error_code = None if conforming else "NON_CONFORMING"
        item.error_message = None if conforming else "Lux no confirma todos los criterios"
        job.state_version += 1
        job.updated_at = _now()
        db.commit()
        if not conforming:
            with SessionLocal() as final_db:
                final_item = final_db.get(GisLuxJobItem, item_id)
                final_job = final_db.get(GisLuxJob, job.id)
                if final_item and final_job:
                    refresh_job(final_job, final_db.query(GisLuxJobItem).filter(GisLuxJobItem.job_id == job.id).all())
                    _mark_outbox_delivered(final_db, item_id)
                    final_db.commit()
            return

    try:
        response = client.post(
            f"{settings.gis_internal_api_url.rstrip('/')}/api/internal/lux/items/{item_id}/materialize",
            headers=headers,
        )
        response.raise_for_status()
        with SessionLocal() as db:
            _mark_outbox_delivered(db, item_id)
            db.commit()
    except httpx.TimeoutException as exc:
        with SessionLocal() as db:
            _set_failure(db, item_id, lease_token, "unknown", "GIS_TIMEOUT", str(exc))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            detail = exc.response.text
            if "LEASE_FENCED" in detail:
                return
            code = next((candidate for candidate in ("STALE_OSM", "STALE_DRAFT", "STALE_ZONE") if candidate in detail), "GIS_CONFLICT")
            state = "stale"
        elif exc.response.status_code == 422:
            code, state = "MATERIALIZATION_BLOCKED", "blocked"
        else:
            code, state = "GIS_HTTP", "failed"
        with SessionLocal() as db:
            _set_failure(db, item_id, lease_token, state, code, exc.response.text)
    except Exception as exc:
        with SessionLocal() as db:
            _set_failure(db, item_id, lease_token, "unknown", "GIS_UNKNOWN", str(exc))


def run_once() -> bool:
    with SessionLocal() as db:
        claimed = _claim(db)
    if claimed is None:
        return False
    item_id, lease_token = claimed
    with httpx.Client(timeout=settings.lux_worker_timeout_seconds) as client:
        token = _service_token(client)
        _process(item_id, lease_token, client, token)
    return True


def main() -> None:
    oneshot = os.getenv("LUX_WORKER_ONESHOT", "false").lower() == "true"
    while True:
        try:
            worked = run_once()
        except Exception:
            worked = False
        if oneshot:
            return
        if not worked:
            time.sleep(settings.lux_job_poll_seconds)


if __name__ == "__main__":
    main()
