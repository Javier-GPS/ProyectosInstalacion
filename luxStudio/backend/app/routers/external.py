import base64
import hashlib
import json
import logging
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Organization, OrganizationTramo, User
from ..services.auth import hash_password, verify_password

_log = logging.getLogger(__name__)

router = APIRouter()

# ── Hardcoded test credentials ──────────────────────────────────────
_TEST_EMAIL = "test@external.com"
_TEST_PASSWORD = "test123"


def _ensure_test_user(db: Session) -> User:
    user = db.query(User).filter(User.email == _TEST_EMAIL).first()
    if not user:
        user = User(
            email=_TEST_EMAIL,
            name="Test External",
            password_hash=hash_password(_TEST_PASSWORD),
            role="USER",
            is_active=True,
            must_reset_password=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _log.info("Created test user %s (id=%s)", _TEST_EMAIL, user.id)
    return user


def verify_hardcoded_auth(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("basic "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        decoded = base64.b64decode(authorization.split(" ", 1)[1].strip()).decode("utf-8")
        email, password = decoded.split(":", 1)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    user = _ensure_test_user(db)
    if email != _TEST_EMAIL or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


def _resolve_org(db: Session, org_id: int, user: User) -> Organization:
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.user_id == user.id,
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _config_hash(config_json: str | None) -> str | None:
    if not config_json:
        return None
    try:
        normalized = json.dumps(json.loads(config_json), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode()).hexdigest()
    except (TypeError, ValueError):
        return None


# ── Schemas ─────────────────────────────────────────────────────────


class TramoImportItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    config_json: Optional[str] = None


class ExternalImportRequest(BaseModel):
    organization: str = Field(..., min_length=1, max_length=255)
    tramos: list[TramoImportItem] = Field(..., min_length=1, max_length=1000)


class TramoImportResult(BaseModel):
    name: str
    status: str  # "created" | "skipped" | "error"
    config_sha256: Optional[str] = None
    error: Optional[str] = None


class ExternalImportResponse(BaseModel):
    organization_id: int
    organization_name: str
    created: int
    skipped: int
    errors: int
    groups: int
    tramos: list[TramoImportResult]


class TramoGroupItem(BaseModel):
    id: int
    name: str


class TramoGroup(BaseModel):
    config_sha256: Optional[str]
    config_json: Optional[str]
    tramo_count: int
    tramos: list[TramoGroupItem]


class OrganizationTramosResponse(BaseModel):
    organization_id: int
    organization_name: str
    total_tramos: int
    total_groups: int
    groups: list[TramoGroup]


class OrganizationInfo(BaseModel):
    id: int
    name: str
    tramo_count: int


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationInfo]


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/api/external/import", response_model=ExternalImportResponse)
async def import_organization(
    body: ExternalImportRequest,
    user: User = Depends(verify_hardcoded_auth),
    db: Session = Depends(get_db),
):
    org_name = body.organization.strip()

    org = db.query(Organization).filter(
        Organization.user_id == user.id,
        Organization.name.ilike(org_name),
    ).first()

    if org:
        org.name = org_name
    else:
        org = Organization(user_id=user.id, name=org_name)
        db.add(org)
        db.flush()

    existing_names = {
        t.name for t in db.query(OrganizationTramo).filter(
            OrganizationTramo.organization_id == org.id,
        ).all()
    }

    seen_configs: set[str] = set()
    results: list[TramoImportResult] = []
    created = skipped = errors = 0

    for item in body.tramos:
        name = item.name.strip()
        if not name:
            errors += 1
            results.append(TramoImportResult(name="", status="error", error="Name cannot be empty"))
            continue

        if name in existing_names:
            skipped += 1
            results.append(TramoImportResult(name=name, status="skipped"))
            continue

        config = item.config_json
        ch = _config_hash(config)
        if config is not None and ch is None:
            errors += 1
            results.append(TramoImportResult(name=name, status="error", error="Invalid config_json"))
            continue

        tramo = OrganizationTramo(
            organization_id=org.id,
            name=name,
            config_json=config,
            config_sha256=ch,
        )
        db.add(tramo)
        existing_names.add(name)
        seen_configs.add(ch) if ch else None
        created += 1
        results.append(TramoImportResult(name=name, status="created", config_sha256=ch))

    db.commit()

    return ExternalImportResponse(
        organization_id=org.id,
        organization_name=org.name,
        created=created,
        skipped=skipped,
        errors=errors,
        groups=len(seen_configs),
        tramos=results,
    )


@router.get("/api/external/organizations", response_model=OrganizationListResponse)
async def list_organizations(
    user: User = Depends(verify_hardcoded_auth),
    db: Session = Depends(get_db),
):
    orgs = db.query(Organization).filter(Organization.user_id == user.id).order_by(Organization.name).all()
    return OrganizationListResponse(organizations=[
        OrganizationInfo(
            id=o.id,
            name=o.name,
            tramo_count=db.query(OrganizationTramo).filter(OrganizationTramo.organization_id == o.id).count(),
        ) for o in orgs
    ])


@router.get("/api/external/organizations/{org_id}/tramos", response_model=OrganizationTramosResponse)
async def list_organization_tramos(
    org_id: int,
    user: User = Depends(verify_hardcoded_auth),
    db: Session = Depends(get_db),
):
    org = _resolve_org(db, org_id, user)
    tramos = db.query(OrganizationTramo).filter(
        OrganizationTramo.organization_id == org.id,
    ).order_by(OrganizationTramo.id).all()

    groups_dict: dict[str | None, list[OrganizationTramo]] = defaultdict(list)
    for t in tramos:
        groups_dict[t.config_sha256].append(t)

    groups: list[TramoGroup] = []
    for ch, members in groups_dict.items():
        sample_cfg = next((m.config_json for m in members if m.config_json), None)
        groups.append(TramoGroup(
            config_sha256=ch,
            config_json=sample_cfg,
            tramo_count=len(members),
            tramos=[TramoGroupItem(id=m.id, name=m.name) for m in members],
        ))

    groups.sort(key=lambda g: g.tramos[0].id)

    return OrganizationTramosResponse(
        organization_id=org.id,
        organization_name=org.name,
        total_tramos=len(tramos),
        total_groups=len(groups),
        groups=groups,
    )
