"""Projects — CRUD for the shared ``projects`` table.

Lightweight replication of LuxStudio's projects router, adapted to the
GISvial auth (Principal) and project-scope access model.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import GisProjectMembership, GisZone, Project, User
from ..routers.deps import Principal, current_principal
from ..services.access import project_for

router = APIRouter()


def _owner_names(db: Session, project_ids: list[int]) -> dict[int, str | None]:
    projects = db.query(Project.id, Project.owner_user_id).filter(Project.id.in_(project_ids)).all()
    user_ids = {owner for _, owner in projects if owner is not None}
    names: dict[int, str | None] = {}
    if user_ids:
        for uid, name in db.query(User.id, User.name).filter(User.id.in_(user_ids)).all():
            names[uid] = name
    result: dict[int, str | None] = {}
    for pid, owner in projects:
        result[pid] = names.get(owner) if owner is not None else None
    return result


def _owner_name(db: Session, owner_user_id: int | None) -> str | None:
    if owner_user_id is None:
        return None
    return db.query(User.name).filter(User.id == owner_user_id).scalar()


class ProjectBody(BaseModel):
    project_name: str = Field(default="", min_length=0)
    name: Optional[str] = None  # GIS compat: alias for project_name
    client: Optional[str] = None
    location: Optional[str] = None
    designer: Optional[str] = None
    study_date: Optional[str] = None
    reference: Optional[str] = None
    calculation_type: Optional[str] = None
    standard: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "draft"
    config_json: Optional[str] = None
    result_json: Optional[str] = None
    owner_user_id: Optional[int] = None
    t_amb_c: Optional[float] = 25.0
    margen_lavg: Optional[float] = 0.0
    i_op_ma: Optional[float] = None
    lm_w_min: Optional[float] = None


class ProjectInfo(BaseModel):
    id: int
    project_name: str
    name: Optional[str] = None  # GIS compat: mirrors project_name
    client: Optional[str] = None
    location: Optional[str] = None
    designer: Optional[str] = None
    study_date: Optional[str] = None
    reference: Optional[str] = None
    calculation_type: Optional[str] = None
    standard: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "draft"
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_opened_at: Optional[str] = None
    t_amb_c: Optional[float] = 25.0
    margen_lavg: Optional[float] = 0.0
    i_op_ma: Optional[float] = None
    lm_w_min: Optional[float] = None


def _to_info(project: Project, owner_name: str | None = None) -> ProjectInfo:
    return ProjectInfo(
        id=project.id,
        owner_user_id=project.owner_user_id,
        owner_name=owner_name,
        name=project.project_name,  # GIS compat
        project_name=project.project_name,
        client=project.client,
        location=project.location,
        designer=project.designer,
        study_date=project.study_date,
        reference=project.reference,
        calculation_type=project.calculation_type,
        standard=project.standard,
        notes=project.notes,
        status=project.status,
        config_json=project.config_json,
        result_json=project.result_json,
        t_amb_c=project.t_amb_c,
        margen_lavg=project.margen_lavg,
        i_op_ma=project.i_op_ma,
        lm_w_min=project.lm_w_min,
        created_at=project.created_at.isoformat() if project.created_at else None,
        updated_at=project.updated_at.isoformat() if project.updated_at else None,
        last_opened_at=project.last_opened_at.isoformat() if project.last_opened_at else None,
    )


def _visible_project_ids(principal: Principal, db: Session) -> Optional[set[int]]:
    """None → all (admin); otherwise the set of accessible project ids."""
    if principal.user.role == "ADMIN":
        return None
    membership_ids = {
        row.project_id
        for row in db.query(GisProjectMembership.project_id).filter(
            GisProjectMembership.issuer == principal.issuer,
            GisProjectMembership.subject == principal.subject,
            GisProjectMembership.active.is_(True),
        )
    }
    membership_ids.add(principal.user.id)
    return membership_ids


@router.post("/api/projects", response_model=ProjectInfo)
async def create_project(
    body: ProjectBody,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    data = body.model_dump()
    if not data.get("project_name") and data.get("name"):
        data["project_name"] = data["name"]
    data.pop("name", None)
    body_owner = data.pop("owner_user_id", None)
    owner_user_id = body_owner if principal.user.role == "ADMIN" and body_owner is not None else principal.user.id
    project = Project(**data, owner_user_id=owner_user_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_info(project, _owner_name(db, project.owner_user_id))


@router.get("/api/projects", response_model=list[ProjectInfo])
async def list_projects(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    query = select(Project)
    visible = _visible_project_ids(principal, db)
    if visible is not None:
        query = query.filter(Project.id.in_(visible))
    projects = db.scalars(query.order_by(Project.id.desc())).all()
    names = _owner_names(db, [p.id for p in projects])
    return [_to_info(project, names.get(project.id)) for project in projects]


@router.get("/api/projects/{project_id}", response_model=ProjectInfo)
async def get_project(
    project_id: int,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project = project_for(principal, db, project_id)
    project.last_opened_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return _to_info(project, _owner_name(db, project.owner_user_id))


@router.put("/api/projects/{project_id}", response_model=ProjectInfo)
async def update_project(
    project_id: int,
    body: ProjectBody,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project = project_for(principal, db, project_id, write=True)
    data = body.model_dump(exclude_unset=True)
    if principal.user.role != "ADMIN":
        data.pop("owner_user_id", None)
    for key, value in data.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return _to_info(project, _owner_name(db, project.owner_user_id))


@router.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: int,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project = project_for(principal, db, project_id, write=True)
    # Detach GIS zones before deleting the project.
    db.query(GisZone).filter(GisZone.project_id == project_id).update({"project_id": None})
    db.delete(project)
    db.commit()
    return {"ok": True}
