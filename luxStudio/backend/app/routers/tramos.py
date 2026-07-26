import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import inspect, text

from ..core.text_utils import norm
from ..database import SessionLocal, engine, get_db
from ..models import Project, Tramo, TramoDocument, User
from ..models.catalog import Difusor, Gama, LedType, Lente
from ..models.luminaire_catalog import LuminaireLED
from ..schemas.models import CalculationConfig
from ..schemas.models import (
    BulkCalculateProgressItem,
    BulkCalculateStatus,
    TramoBody,
    TramoBulkImportRequest,
    TramoBulkImportResponse,
    TramoBulkImportResult,
    TramoDocumentInfo,
    TramoInfo,
    TramoSummary,
)
from ._access import can_access_project
from .auth import current_user
from ..services.tramo_operations import (
    bulk_adjust_power_tramos,
    bulk_calculate_tramos as calculate_tramos_bulk,
    is_valid_combo,
)

_log = logging.getLogger(__name__)

# ── Background batch-calculate state ──────────────────────────────
_batch_states: dict[str, dict] = {}
_batch_lock = threading.Lock()
_BATCH_WORKERS = 1  # 1 CPU server — sequential avoids context-switch overhead

router = APIRouter()


def _ensure_tramos_tables() -> None:
    Tramo.__table__.create(bind=engine, checkfirst=True)
    TramoDocument.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        cols = {column["name"] for column in inspect(conn).get_columns("tramos")}
        for ddl in [
            ("parent_section_id", "ALTER TABLE tramos ADD COLUMN parent_section_id INTEGER"),
            ("base_name", "ALTER TABLE tramos ADD COLUMN base_name VARCHAR(255)"),
            ("variant_name", "ALTER TABLE tramos ADD COLUMN variant_name VARCHAR(255)"),
            ("sort_order", "ALTER TABLE tramos ADD COLUMN sort_order INTEGER DEFAULT 0"),
        ]:
            if ddl[0] not in cols:
                conn.execute(text(ddl[1]))
        conn.execute(text("UPDATE tramos SET base_name = name WHERE base_name IS NULL"))


def _can_access(project: Project, user: User) -> bool:
    return can_access_project(project, user)


def _document_to_info(document: TramoDocument) -> TramoDocumentInfo:
    return TramoDocumentInfo(
        id=document.id,
        filename=document.filename,
        document_type=document.document_type,
        created_at=document.created_at.isoformat() if document.created_at else "",
    )


def _compliance_summary(source: dict | str | None) -> Optional[dict]:
    if not source:
        return None
    if isinstance(source, dict):
        result = source
    else:
        try:
            result = json.loads(source)
        except (TypeError, ValueError):
            return None
    if not isinstance(result, dict):
        return None
    summary: dict = {}
    if "compliant" in result:
        summary["compliant"] = bool(result["compliant"])
    for key in ("Lavg", "Uo", "Ul", "TI", "SR", "EIR", "Eavg", "Emin"):
        value = result.get(key)
        if isinstance(value, (int, float)):
            summary[key] = value
    criteria = result.get("criteria")
    if isinstance(criteria, list):
        passed: dict[str, bool] = {}
        for c in criteria:
            if isinstance(c, dict) and "name" in c and "passed" in c:
                # Skip purely informational criteria when deciding compliance.
                if c.get("is_compliance_criterion") is False:
                    continue
                name_key = c["name"].split(" ")[0]
                passed[name_key] = bool(c["passed"])
        if passed:
            summary["criteria_passed"] = passed
            summary["compliant"] = all(passed.values())
    return summary or None


def _tramo_to_info(tramo: Tramo, *, include_documents: bool = False) -> TramoInfo:
    documents = sorted(list(tramo.documents or []), key=lambda d: d.id, reverse=True)
    has_pdf = any(d.document_type == "pdf" for d in documents)
    has_excel = any(d.document_type == "excel" for d in documents)
    document_ids: dict = {}
    for d in documents:
        document_ids.setdefault(d.document_type, d.id)
    display_name = tramo.base_name or tramo.name
    if tramo.parent_section_id and tramo.parent:
        display_name = f"{tramo.parent.base_name or tramo.parent.name} - {tramo.variant_name or tramo.base_name or tramo.name}"
    return TramoInfo(
        id=tramo.id,
        project_id=tramo.project_id,
        name=display_name,
        parent_section_id=tramo.parent_section_id,
        base_name=tramo.base_name,
        variant_name=tramo.variant_name,
        sort_order=tramo.sort_order or tramo.id,
        description=tramo.description,
        config_json=tramo.config_json,
        result_json=tramo.result_json,
        last_calculated_at=tramo.last_calculated_at.isoformat() if tramo.last_calculated_at else None,
        has_pdf=has_pdf,
        has_excel=has_excel,
        document_ids=document_ids,
        documents=[_document_to_info(d) for d in documents] if include_documents else [],
        compliance_summary=_compliance_summary(tramo.result_json),
        created_at=tramo.created_at.isoformat() if tramo.created_at else None,
        updated_at=tramo.updated_at.isoformat() if tramo.updated_at else None,
    )


def _has_pcb_mapping(db: Session, cfg: dict) -> bool:
    gama = str(cfg.get("gama") or "").strip()
    difusor = str(cfg.get("difusor") or "").strip()
    lente = str(cfg.get("lente") or "").strip()
    led_type = str(cfg.get("led_type") or "").strip()
    return db.query(LuminaireLED.id).join(Gama, LuminaireLED.gama_id == Gama.id).join(
        Difusor, LuminaireLED.difusor_id == Difusor.id
    ).join(Lente, LuminaireLED.lente_id == Lente.id).outerjoin(
        LedType, LuminaireLED.led_type_id == LedType.id
    ).filter(
        Gama.name.ilike(gama),
        Difusor.name.ilike(difusor),
        Lente.name.ilike(lente),
        LedType.name.ilike(led_type) if led_type else LedType.id.is_(None),
        LuminaireLED.pcb_id.isnot(None),
    ).first() is not None


def _combo_key(gama: object, difusor: object, lente: object, led_type: object) -> tuple[str, str, str, str]:
    return (
        norm(gama),
        norm(difusor),
        norm(lente),
        norm(led_type),
    )


def _build_status_context(db: Session) -> dict[str, set]:
    pcb_rows = (
        db.query(Gama.name, Difusor.name, Lente.name, LedType.name)
        .select_from(LuminaireLED)
        .join(Gama, LuminaireLED.gama_id == Gama.id)
        .join(Difusor, LuminaireLED.difusor_id == Difusor.id)
        .join(Lente, LuminaireLED.lente_id == Lente.id)
        .outerjoin(LedType, LuminaireLED.led_type_id == LedType.id)
        .filter(LuminaireLED.pcb_id.isnot(None))
        .all()
    )
    return {
        "gamas": {norm(name) for (name,) in db.query(Gama.name).all()},
        "difusores": {norm(name) for (name,) in db.query(Difusor.name).all()},
        "lentes": {norm(name) for (name,) in db.query(Lente.name).all()},
        "led_types": {norm(name) for (name,) in db.query(LedType.name).all()},
        "pcb_combos": {_combo_key(g, d, l, lt) for g, d, l, lt in pcb_rows},
    }


def _valid_config_values(db: Session, cfg: dict) -> bool:
    gama = str(cfg.get("gama") or "").strip()
    difusor = str(cfg.get("difusor") or "").strip()
    lente = str(cfg.get("lente") or "").strip()
    led_type_val = str(cfg.get("led_type") or "").strip()
    if not all([gama, difusor, lente]):
        return False
    g = db.query(Gama.id).filter(Gama.name.ilike(gama)).first()
    d = db.query(Difusor.id).filter(Difusor.name.ilike(difusor)).first()
    l = db.query(Lente.id).filter(Lente.name.ilike(lente)).first()
    if not all([g, d, l]):
        return False
    if led_type_val:
        lt = db.query(LedType.id).filter(LedType.name.ilike(led_type_val)).first()
        if not lt:
            return False
    return True


def _valid_config_values_from_context(context: dict[str, set], cfg: dict) -> bool:
    return (
        norm(cfg.get("gama")) in context["gamas"]
        and norm(cfg.get("difusor")) in context["difusores"]
        and norm(cfg.get("lente")) in context["lentes"]
        and norm(cfg.get("led_type")) in context["led_types"]
    )


def _has_pcb_mapping_in_context(context: dict[str, set], cfg: dict) -> bool:
    return _combo_key(cfg.get("gama"), cfg.get("difusor"), cfg.get("lente"), cfg.get("led_type")) in context["pcb_combos"]


def _tramo_status(tramo: Tramo, db: Session | None = None, status_context: dict[str, set] | None = None, *, result_dict: dict | None = None, compliance: dict | None = None) -> str:
    """Compute tramo status without loading JSON into the frontend."""
    config = tramo.config_json
    if not config:
        return "pending"
    try:
        cfg = json.loads(config)
    except (TypeError, ValueError):
        return "config_error"
    required = ("gama", "difusor", "lente", "led_type")
    if not all(str(cfg.get(k) or "").strip() for k in required):
        return "missing_config"
    if status_context is not None and not _valid_config_values_from_context(status_context, cfg):
        return "missing_config"
    if db is not None and status_context is None and not _valid_config_values(db, cfg):
        return "missing_config"
    if status_context is not None and not _has_pcb_mapping_in_context(status_context, cfg):
        return "no_pcb_capacity"
    if db is not None and status_context is None and not _has_pcb_mapping(db, cfg):
        return "no_pcb_capacity"
    if not tramo.result_json:
        return "calculation_pending"
    if result_dict is None:
        try:
            result_dict = json.loads(tramo.result_json)
        except (TypeError, ValueError):
            return "pending"
    if result_dict.get("__status") == "no_pcb_capacity":
        return "no_pcb_capacity"
    # Hash mismatch → config changed after last calculate
    try:
        from ..services.tramo_operations import calculation_config_hash
        cfg_hash = calculation_config_hash(cfg)
        res_hash = (result_dict.get("__configHash") or "").strip()
        if cfg_hash and res_hash and cfg_hash != res_hash:
            return "calculation_pending"
    except Exception:
        pass
    if compliance is None:
        compliance = _compliance_summary(tramo.result_json)
    if not compliance or compliance.get("compliant") is None:
        return "pending"
    return "compliant" if compliance["compliant"] else "non_compliant"


def _tramo_to_summary(tramo: Tramo, db: Session | None = None, status_context: dict[str, set] | None = None) -> TramoSummary:
    documents = list(tramo.documents or [])
    has_pdf = any(d.document_type == "pdf" for d in documents)
    has_excel = any(d.document_type == "excel" for d in documents)
    document_ids: dict = {}
    for d in documents:
        document_ids.setdefault(d.document_type, d.id)
    display_name = tramo.base_name or tramo.name
    if tramo.parent_section_id and tramo.parent:
        display_name = f"{tramo.parent.base_name or tramo.parent.name} - {tramo.variant_name or tramo.base_name or tramo.name}"
    result_dict = None
    if tramo.result_json:
        try:
            result_dict = json.loads(tramo.result_json)
        except (TypeError, ValueError):
            result_dict = None
    compliance = _compliance_summary(result_dict)
    status = _tramo_status(tramo, db, status_context, result_dict=result_dict, compliance=compliance)
    has_result = isinstance(result_dict, dict) and isinstance(result_dict.get("criteria"), list) and isinstance(result_dict.get("luminaire"), dict)
    return TramoSummary(
        id=tramo.id,
        project_id=tramo.project_id,
        name=display_name,
        parent_section_id=tramo.parent_section_id,
        base_name=tramo.base_name,
        variant_name=tramo.variant_name,
        sort_order=tramo.sort_order or tramo.id,
        description=tramo.description,
        last_calculated_at=tramo.last_calculated_at.isoformat() if tramo.last_calculated_at else None,
        has_pdf=has_pdf,
        has_excel=has_excel,
        document_ids=document_ids,
        compliance_summary=compliance,
        status=status,
        has_result=has_result,
        created_at=tramo.created_at.isoformat() if tramo.created_at else None,
        updated_at=tramo.updated_at.isoformat() if tramo.updated_at else None,
    )


def _resolve_project(db: Session, project_id: int, user: User) -> Project:
    project = db.get(Project, project_id)
    if not project or not _can_access(project, user):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _next_default_name(db: Session, project_id: int) -> str:
    count = (
        db.query(Tramo)
        .filter(Tramo.project_id == project_id)
        .count()
    )
    return f"Tramo {count + 1}"


def _root(tramo: Tramo) -> Tramo:
    return tramo.parent or tramo


def _next_variant_name(db: Session, parent: Tramo) -> str:
    used = {
        t.variant_name for t in db.query(Tramo).filter(
            Tramo.project_id == parent.project_id,
            Tramo.parent_section_id == parent.id,
        ).all()
    }
    n = 1
    while f"alternativa {n}" in used:
        n += 1
    return f"alternativa {n}"


def _resolve_tramo(db: Session, project_id: int, tramo_id: int) -> Tramo:
    tramo = db.query(Tramo).options(selectinload(Tramo.parent)).filter(Tramo.id == tramo_id).first()
    if not tramo or tramo.project_id != project_id:
        raise HTTPException(status_code=404, detail="Tramo not found")
    return tramo


@router.get("/api/projects/{project_id}/tramos", response_model=list[TramoSummary])
async def list_tramos(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lightweight list — no config_json / result_json blobs, uses eager loading."""
    _resolve_project(db, project_id, user)
    tramos = (
        db.query(Tramo)
        .options(selectinload(Tramo.documents), selectinload(Tramo.parent))
        .filter(Tramo.project_id == project_id)
        .order_by(Tramo.parent_section_id.isnot(None), Tramo.parent_section_id.asc(), Tramo.id.asc())
        .all()
    )
    roots = [t for t in tramos if not t.parent_section_id]
    children: dict = {}
    for t in tramos:
        if t.parent_section_id:
            children.setdefault(t.parent_section_id, []).append(t)
    ordered = []
    for r in roots:
        ordered.append(r)
        ordered.extend(sorted(children.get(r.id, []), key=lambda x: x.id))
    status_context = _build_status_context(db)
    return [_tramo_to_summary(t, status_context=status_context) for t in ordered]


@router.post("/api/projects/{project_id}/tramos", response_model=TramoInfo)
async def create_tramo(project_id: int, body: TramoBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _resolve_project(db, project_id, user)
    parent = db.get(Tramo, body.parent_section_id) if body.parent_section_id else None
    parent = _root(parent) if parent else None
    base_name = (body.base_name or body.name or "").strip() or _next_default_name(db, project_id)
    variant_name = (body.variant_name or "").strip() if body.variant_name else None
    if parent:
        base_name = parent.base_name or parent.name
        variant_name = variant_name or _next_variant_name(db, parent)
        exists = db.query(Tramo).filter(
            Tramo.project_id == project_id,
            Tramo.parent_section_id == parent.id,
            Tramo.variant_name == variant_name,
        ).first()
        if exists:
            variant_name = _next_variant_name(db, parent)
    name = f"{base_name} - {variant_name}" if parent else base_name
    tramo = Tramo(
        project_id=project_id,
        name=name,
        parent_section_id=parent.id if parent else None,
        base_name=base_name,
        variant_name=variant_name,
        description=body.description,
        config_json=body.config_json,
        result_json=body.result_json,
    )
    db.add(tramo)
    db.commit()
    db.refresh(tramo)
    return _tramo_to_info(tramo)


@router.get("/api/projects/{project_id}/tramos/{tramo_id}", response_model=TramoInfo)
async def get_tramo(project_id: int, tramo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _resolve_project(db, project_id, user)
    tramo = _resolve_tramo(db, project_id, tramo_id)
    return _tramo_to_info(tramo, include_documents=True)


@router.put("/api/projects/{project_id}/tramos/{tramo_id}", response_model=TramoInfo)
async def update_tramo(
    project_id: int,
    tramo_id: int,
    body: TramoBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    tramo = _resolve_tramo(db, project_id, tramo_id)


    if body.name is not None:
        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        if tramo.parent_section_id:
            tramo.variant_name = new_name
            parent_name = tramo.parent.base_name or tramo.parent.name
            tramo.name = f"{parent_name} - {new_name}"
        else:
            tramo.base_name = new_name
            tramo.name = new_name
            for child in db.query(Tramo).filter(Tramo.parent_section_id == tramo.id).all():
                child.base_name = new_name
                child.name = f"{new_name} - {child.variant_name or child.name}"
    if body.base_name is not None and not tramo.parent_section_id:
        tramo.base_name = body.base_name.strip()
        tramo.name = tramo.base_name
    if body.variant_name is not None and tramo.parent_section_id:
        tramo.variant_name = body.variant_name.strip()
        tramo.name = f"{tramo.parent.base_name or tramo.parent.name} - {tramo.variant_name}"
    if body.description is not None:
        tramo.description = body.description
    if body.config_json is not None:
        tramo.config_json = body.config_json
        tramo.result_json = None
        tramo.last_calculated_at = None
    if body.result_json is not None:
        tramo.result_json = body.result_json
        tramo.last_calculated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tramo)
    return _tramo_to_info(tramo, include_documents=True)


class BulkDeleteRequest(BaseModel):
    ids: list[int]


class BulkUpdateRequest(BaseModel):
    ids: list[int]
    config_fields: dict


class BulkCalculateRequest(BaseModel):
    ids: list[int]
    margen_lavg: Optional[float] = None


@router.post("/api/projects/{project_id}/tramos/bulk-delete")
async def bulk_delete_tramos(
    project_id: int,
    body: BulkDeleteRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    existing = db.query(Tramo).filter(
        Tramo.project_id == project_id,
        Tramo.id.in_(body.ids),
    ).all()
    found_ids = {t.id for t in existing}
    missing = [id for id in body.ids if id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Tramos not found: {missing}",
        )
    for t in existing:
        db.delete(t)
    db.commit()
    return {"ok": True, "deleted": len(existing)}


@router.post("/api/projects/{project_id}/tramos/bulk-update", response_model=list[TramoInfo])
async def bulk_update_tramos(
    project_id: int,
    body: BulkUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    existing = db.query(Tramo).filter(
        Tramo.project_id == project_id,
        Tramo.id.in_(body.ids),
    ).all()
    found_ids = {t.id for t in existing}
    missing = [id for id in body.ids if id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Tramos not found: {missing}")


    updated = []
    for tramo in existing:
        config = json.loads(tramo.config_json) if tramo.config_json else {}
        config.update(body.config_fields)
        gama = config.get("gama")
        difusor = config.get("difusor")
        lente = config.get("lente")
        led_type = config.get("led_type")
        if gama and difusor and lente:
            if not is_valid_combo(db, gama, difusor, lente, led_type):
                raise HTTPException(
                    status_code=400,
                    detail=f"Combinación no válida ({gama}, {difusor}, {lente}, {led_type or '—'}) en el tramo '{tramo.name}'",
                )
        tramo.config_json = json.dumps(config)
        tramo.result_json = None
        tramo.last_calculated_at = None
        updated.append(tramo)

    db.commit()
    for t in updated:
        db.refresh(t)
    return [_tramo_to_info(t) for t in updated]


class BulkCalculateFailure(BaseModel):
    id: int
    name: str
    error: str


class BulkCalculateResponse(BaseModel):
    updated: list[TramoInfo]
    errors: int
    message: str = ""
    failed: list[BulkCalculateFailure] = []


class BulkAdjustPowerItem(BaseModel):
    tramo_id: int
    success: bool
    previous_power: Optional[float] = None
    new_power: Optional[float] = None
    error: Optional[str] = None


class BulkAdjustPowerResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BulkAdjustPowerItem]


@router.post("/api/projects/{project_id}/tramos/bulk-calculate", response_model=BulkCalculateStatus)
async def bulk_calculate_tramos_start(
    project_id: int,
    body: BulkCalculateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Start an async batch calculation and return immediately with a batch_id.

    Progress is polled via ``GET …/bulk-calculate/{batch_id}/progress``.
    """
    _resolve_project(db, project_id, user)
    existing = db.query(Tramo).filter(
        Tramo.project_id == project_id,
        Tramo.id.in_(body.ids),
    ).options(selectinload(Tramo.parent)).all()
    found_ids = {t.id for t in existing}
    missing = [id for id in body.ids if id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Tramos not found: {missing}")

    project = db.get(Project, project_id)
    margen_lavg = body.margen_lavg if body.margen_lavg is not None else (project.margen_lavg if project else 0.0)
    project_config = {
        "t_amb_c": project.t_amb_c if project else 25.0,
        "i_op_ma": project.i_op_ma if project else None,
        "lm_w_min": project.lm_w_min if project else None,
    }

    batch_id = uuid.uuid4().hex[:12]
    items: list[dict] = [
        {"id": t.id, "name": _tramo_to_summary(t).name, "status": "pending", "error": None}
        for t in existing
    ]
    state = {
        "batch_id": batch_id,
        "project_id": project_id,
        "margen_lavg": margen_lavg,
        "project_config": project_config,
        "total": len(items),
        "completed": 0,
        "failed": 0,
        "cancelled": False,
        "items": {item["id"]: item for item in items},
        "order": [t.id for t in existing],
    }
    with _batch_lock:
        _batch_states[batch_id] = state

    # Fire background worker with IDs only (avoid cross-session ORM objects)
    _run_batch_calculation(batch_id, [t.id for t in existing])

    items_map = state["items"]
    return BulkCalculateStatus(
        batch_id=batch_id,
        total=state["total"],
        completed=0,
        failed=0,
        cancelled=False,
        items=[BulkCalculateProgressItem(**items_map[tid]) for tid in state["order"]],
    )


@router.get(
    "/api/projects/{project_id}/tramos/bulk-calculate/{batch_id}/progress",
    response_model=BulkCalculateStatus,
)
async def bulk_calculate_progress(
    project_id: int,
    batch_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    with _batch_lock:
        state = _batch_states.get(batch_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    items_map = state["items"]
    return BulkCalculateStatus(
        batch_id=batch_id,
        total=state["total"],
        completed=state["completed"],
        failed=state["failed"],
        cancelled=bool(state.get("cancelled")),
        items=[BulkCalculateProgressItem(**items_map[tid]) for tid in state["order"] if tid in items_map],
    )


@router.post(
    "/api/projects/{project_id}/tramos/bulk-calculate/{batch_id}/cancel",
    response_model=BulkCalculateStatus,
)
async def bulk_calculate_cancel(
    project_id: int,
    batch_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    with _batch_lock:
        state = _batch_states.get(batch_id)
        if state is None or state.get("project_id") != project_id:
            raise HTTPException(status_code=404, detail="Batch not found")
        state["cancelled"] = True
        items_map = state["items"]
        return BulkCalculateStatus(
            batch_id=batch_id,
            total=state["total"],
            completed=state["completed"],
            failed=state["failed"],
            cancelled=True,
            items=[BulkCalculateProgressItem(**items_map[tid]) for tid in state["order"] if tid in items_map],
        )


def _run_batch_calculation(batch_id: str, tramo_ids: list[int]) -> None:
    """Run calculations in a **background thread** so the POST returns immediately.
    
    Uses a ThreadPoolExecutor internally for parallel workers.
    """
    def _progress_callback(tramo_id: int, status: str, error: str | None = None, compliant: bool | None = None) -> None:
        with _batch_lock:
            state = _batch_states.get(batch_id)
            if not state:
                return
            item = state["items"].get(tramo_id)
            if not item:
                return
            previous_status = item["status"]
            item["status"] = status
            item["error"] = error
            if compliant is not None:
                item["compliant"] = compliant
            if status in ("done", "error", "cancelled") and previous_status not in ("done", "error", "cancelled"):
                state["completed"] += 1
            if status == "error" and previous_status != "error":
                state["failed"] += 1

    def _is_cancelled() -> bool:
        with _batch_lock:
            state = _batch_states.get(batch_id)
            return bool(state and state.get("cancelled"))

    def _cancel_pending() -> None:
        with _batch_lock:
            state = _batch_states.get(batch_id)
            if not state:
                return
            pending = [tid for tid, item in state["items"].items() if item["status"] == "pending"]
        for tid in pending:
            _progress_callback(tid, "cancelled")

    def _worker(tid: int) -> None:
        if _is_cancelled():
            _progress_callback(tid, "cancelled")
            return
        _progress_callback(tid, "calculating")
        try:
            _db = SessionLocal()
            try:
                tramo = _db.query(Tramo).options(
                    selectinload(Tramo.documents), selectinload(Tramo.parent),
                ).filter(Tramo.id == tid).first()
                if tramo is None:
                    _progress_callback(tid, "error", "Tramo not found")
                    return
                calculate_tramos_bulk(_db, [tramo], _tramo_to_info, margen_lavg=margen_lavg, **project_config)
                _progress_callback(tid, "done", compliant=_tramo_status(tramo, _db) == "compliant")
            finally:
                _db.close()
        except Exception as exc:
            _log.warning("async bulk-calc worker failed for tramo %s: %s", tid, exc)
            _progress_callback(tid, "error", str(exc)[:500])

    state = _batch_states.get(batch_id)
    if not state:
        return

    margen_lavg = state.get("margen_lavg", 0.0)
    project_config = state.get("project_config", {})

    def _run_pool() -> None:
        try:
            with ThreadPoolExecutor(max_workers=_BATCH_WORKERS) as pool:
                futures = {pool.submit(_worker, tid): tid for tid in tramo_ids}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        _log.warning("async bulk-calc worker future failed: %s", exc)
                    if _is_cancelled():
                        for pending in futures:
                            pending.cancel()
                        break
                if _is_cancelled():
                    _cancel_pending()
        finally:
            # Clean up stale states (keep last 20)
            with _batch_lock:
                keys = sorted(
                    _batch_states,
                    key=lambda k: _batch_states[k].get("_ts", 0),
                    reverse=True,
                )
                for k in keys[20:]:
                    _batch_states.pop(k, None)

    threading.Thread(target=_run_pool, daemon=True).start()


class BulkAdjustPowerRequest(BaseModel):
    tramo_ids: list[int]


@router.post("/api/projects/{project_id}/tramos/bulk-adjust-power", response_model=BulkAdjustPowerResponse)
async def bulk_adjust_power(
    project_id: int,
    body: BulkAdjustPowerRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    existing = db.query(Tramo).filter(
        Tramo.project_id == project_id,
        Tramo.id.in_(body.tramo_ids),
    ).all()
    found_ids = {t.id for t in existing}
    missing = [id for id in body.tramo_ids if id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Tramos not found: {missing}")

    def _adjust_one(tramo_id: int) -> dict:
        _db = SessionLocal()
        try:
            tramo = _db.query(Tramo).options(
                selectinload(Tramo.documents), selectinload(Tramo.parent),
            ).filter(Tramo.id == tramo_id).first()
            if tramo is None:
                return {"tramo_id": tramo_id, "success": False, "error": "Tramo not found"}
            items = bulk_adjust_power_tramos(_db, [tramo])
            db_item = items[0] if items else {"tramo_id": tramo_id, "success": False, "error": "No result"}
            _db.commit()
            return db_item
        except Exception as exc:
            _db.rollback()
            _log.warning("bulk-adjust-power worker failed for tramo %s: %s", tramo_id, exc)
            return {"tramo_id": tramo_id, "success": False, "error": str(exc)[:500]}
        finally:
            _db.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        raw_items = list(pool.map(_adjust_one, [t.id for t in existing]))

    items = [BulkAdjustPowerItem(**item) for item in raw_items]
    succeeded = sum(1 for i in items if i.success)
    return BulkAdjustPowerResponse(total=len(items), succeeded=succeeded, failed=len(items) - succeeded, items=items)


@router.delete("/api/projects/{project_id}/tramos/{tramo_id}")
async def delete_tramo(project_id: int, tramo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _resolve_project(db, project_id, user)
    tramo = _resolve_tramo(db, project_id, tramo_id)
    db.delete(tramo)
    db.commit()
    return {"ok": True}


@router.post("/api/projects/{project_id}/tramos/{tramo_id}/duplicate", response_model=TramoInfo)
async def duplicate_tramo(project_id: int, tramo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _resolve_project(db, project_id, user)
    source = _resolve_tramo(db, project_id, tramo_id)
    parent = _root(source)
    variant = _next_variant_name(db, parent)
    copy = Tramo(
        project_id=project_id,
        parent_section_id=parent.id,
        base_name=parent.base_name or parent.name,
        variant_name=variant,
        name=f"{parent.base_name or parent.name} - {variant}",
        description=source.description,
        config_json=source.config_json,
        result_json=None,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _tramo_to_info(copy)


@router.get(
    "/api/projects/{project_id}/tramos/{tramo_id}/documents",
    response_model=list[TramoDocumentInfo],
)
async def list_tramo_documents(
    project_id: int,
    tramo_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    _resolve_tramo(db, project_id, tramo_id)
    documents = (
        db.query(TramoDocument)
        .filter(TramoDocument.tramo_id == tramo_id)
        .order_by(TramoDocument.id.desc())
        .all()
    )
    return [_document_to_info(d) for d in documents]


@router.get("/api/projects/{project_id}/tramos/{tramo_id}/documents/{document_id}/download")
async def download_tramo_document(
    project_id: int,
    tramo_id: int,
    document_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _resolve_project(db, project_id, user)
    _resolve_tramo(db, project_id, tramo_id)
    document = (
        db.query(TramoDocument)
        .filter(TramoDocument.tramo_id == tramo_id, TramoDocument.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=document.data,
        media_type=document.content_type,
        headers={"Content-Disposition": f"attachment; filename={document.filename}"},
    )


@router.post("/api/projects/{project_id}/tramos/bulk", response_model=TramoBulkImportResponse)
async def bulk_import_tramos(
    project_id: int,
    body: TramoBulkImportRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Create several tramos at once from an Excel-style import.

    Each item carries a raw ``config`` mapping; the endpoint validates
    it against :class:`CalculationConfig` row by row. Invalid rows are
    reported as ``error`` results, but the rest of the batch still
    goes through and is committed in a single transaction.
    """

    _resolve_project(db, project_id, user)

    results: list[TramoBulkImportResult] = []
    created = 0
    failed = 0
    next_index = (
        db.query(Tramo).filter(Tramo.project_id == project_id).count() + 1
    )

    def _format_validation_error(exc: ValidationError) -> str:
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []))
            parts.append(f"{loc}: {err.get('msg', '')}")
        return "; ".join(parts) or str(exc)

    try:
        for index, item in enumerate(body.items, start=1):
            try:
                config = CalculationConfig.model_validate(item.config or {})
            except ValidationError as exc:
                failed += 1
                results.append(TramoBulkImportResult(
                    row=index,
                    name=(item.name or "").strip() or f"Row {index}",
                    status="error",
                    error=_format_validation_error(exc),
                ))
                continue

            base_name = (item.name or "").strip()
            if not base_name:
                base_name = f"Tramo {next_index}"
            next_index += 1

            tramo = Tramo(
                project_id=project_id,
                name=base_name,
                base_name=base_name,
                description=item.description,
                config_json=json.dumps(config.model_dump(by_alias=True)),
            )
            try:
                with db.begin_nested():
                    db.add(tramo)
                    db.flush()
            except Exception as exc:
                failed += 1
                results.append(TramoBulkImportResult(
                    row=index,
                    name=base_name,
                    status="error",
                    error=str(exc),
                ))
                continue
            created += 1
            results.append(TramoBulkImportResult(
                row=index,
                name=base_name,
                status="created",
                tramo=_tramo_to_info(tramo),
            ))

        db.commit()
    except Exception:
        db.rollback()
        raise

    return TramoBulkImportResponse(created=created, failed=failed, items=results)
