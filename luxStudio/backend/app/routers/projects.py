from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.orm import Session, load_only, selectinload

from ..database import engine, get_db
from ..models import Project, ProjectDocument, User
from ._access import can_access_project
from .deps import current_user

router = APIRouter()


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


class ProjectInfo(ProjectBody):
    id: int
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_opened_at: Optional[str] = None


class ProjectSummary(BaseModel):
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


class ProjectDocumentInfo(BaseModel):
    id: int
    project_id: int
    filename: str
    document_type: str
    created_at: str


def _ensure_projects_table() -> None:
    Project.__table__.create(bind=engine, checkfirst=True)
    ProjectDocument.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        existing = {column["name"] for column in inspect(conn).get_columns("projects")}
        columns = {
            "owner_user_id": "INTEGER",
            "status": "TEXT DEFAULT 'draft'",
            "config_json": "TEXT",
            "result_json": "TEXT",
            "last_opened_at": "DATETIME",
            "t_amb_c": "REAL DEFAULT 25.0",
            "margen_lavg": "REAL DEFAULT 0.0",
            "i_op_ma": "REAL",
            "lm_w_min": "REAL",
        }
        for name, ddl in columns.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE projects ADD COLUMN {name} {ddl}")


def _to_info(project: Project) -> ProjectInfo:
    return ProjectInfo(
        id=project.id,
        owner_user_id=project.owner_user_id,
        owner_name=getattr(getattr(project, "owner", None), "name", None),
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


def _to_summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        owner_user_id=project.owner_user_id,
        owner_name=getattr(getattr(project, "owner", None), "name", None),
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
        t_amb_c=project.t_amb_c,
        margen_lavg=project.margen_lavg,
        i_op_ma=project.i_op_ma,
        lm_w_min=project.lm_w_min,
        created_at=project.created_at.isoformat() if project.created_at else None,
        updated_at=project.updated_at.isoformat() if project.updated_at else None,
        last_opened_at=project.last_opened_at.isoformat() if project.last_opened_at else None,
    )


def _can_access(project: Project, user: User) -> bool:
    return can_access_project(project, user)


def _doc_to_info(document: ProjectDocument) -> ProjectDocumentInfo:
    return ProjectDocumentInfo(
        id=document.id,
        project_id=document.project_id,
        filename=document.filename,
        document_type=document.document_type,
        created_at=document.created_at.isoformat() if document.created_at else "",
    )


@router.post("", response_model=ProjectInfo)
async def create_project(body: ProjectBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    data = body.model_dump()
    # GIS compat: if only name provided (not project_name), use it
    if not data.get("project_name") and data.get("name"):
        data["project_name"] = data["name"]
    data.pop("name", None)
    body_owner = data.pop("owner_user_id", None)
    if user.role == "ADMIN" and body_owner is not None:
        owner_user_id = body_owner
    else:
        owner_user_id = user.id
    project = Project(**data, owner_user_id=owner_user_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_info(project)


@router.get("", response_model=list[ProjectSummary])
async def list_projects(owner_user_id: Optional[int] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    query = db.query(Project).options(
        load_only(
            Project.id,
            Project.owner_user_id,
            Project.project_name,
            Project.client,
            Project.location,
            Project.designer,
            Project.study_date,
            Project.reference,
            Project.calculation_type,
            Project.standard,
            Project.notes,
            Project.status,
            Project.t_amb_c,
            Project.margen_lavg,
            Project.i_op_ma,
            Project.lm_w_min,
            Project.created_at,
            Project.updated_at,
            Project.last_opened_at,
        ),
        selectinload(Project.owner),
    )
    if user.role == "ADMIN":
        if owner_user_id:
            query = query.filter(Project.owner_user_id == owner_user_id)
    else:
        query = query.filter(Project.owner_user_id == user.id)
    projects = query.order_by(Project.id.desc()).all()
    return [_to_summary(project) for project in projects]


@router.put("/{project_id}", response_model=ProjectInfo)
async def update_project(project_id: int, body: ProjectBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not _can_access(project, user):
        raise HTTPException(status_code=403, detail="Project access denied")

    data = body.model_dump(exclude_unset=True)
    if user.role != "ADMIN":
        data.pop("owner_user_id", None)
    for key, value in data.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return _to_info(project)


@router.delete("/{project_id}")
async def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not _can_access(project, user):
        raise HTTPException(status_code=403, detail="Project access denied")
    # Detach GIS zones before deleting project
    try:
        from ..models import GisZone
        db.query(GisZone).filter(GisZone.project_id == project_id).update({"project_id": None})
    except Exception:
        pass  # GIS tables may not exist yet
    db.delete(project)
    db.commit()
    return {"ok": True}


@router.get("/{project_id}/documents", response_model=list[ProjectDocumentInfo])
async def list_project_documents(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    project = db.get(Project, project_id)
    if not project or not _can_access(project, user):
        raise HTTPException(status_code=404, detail="Project not found")
    documents = (
        db.query(ProjectDocument)
        .filter(ProjectDocument.project_id == project_id)
        .order_by(ProjectDocument.id.desc())
        .all()
    )
    return [_doc_to_info(document) for document in documents]


@router.get("/{project_id}/documents/{document_id}/download")
async def download_project_document(project_id: int, document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    project = db.get(Project, project_id)
    if not project or not _can_access(project, user):
        raise HTTPException(status_code=404, detail="Project not found")
    document = (
        db.query(ProjectDocument)
        .filter(ProjectDocument.project_id == project_id, ProjectDocument.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=document.data,
        media_type=document.content_type,
        headers={"Content-Disposition": f"attachment; filename={document.filename}"},
    )


@router.get("/{project_id}", response_model=ProjectInfo)
async def get_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    project = db.get(Project, project_id)
    if not project or not _can_access(project, user):
        raise HTTPException(status_code=404, detail="Project not found")
    project.last_opened_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return _to_info(project)


@router.post("/{project_id}/duplicate", response_model=ProjectInfo)
async def duplicate_project(project_id: int, owner_user_id: Optional[int] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _ensure_projects_table()
    project = db.get(Project, project_id)
    if not project or not _can_access(project, user):
        raise HTTPException(status_code=404, detail="Project not found")
    target_owner = owner_user_id if user.role == "ADMIN" and owner_user_id else user.id
    copy = Project(
        owner_user_id=target_owner,
        project_name=f"{project.project_name} copia",
        client=project.client,
        location=project.location,
        designer=project.designer,
        study_date=project.study_date,
        reference=project.reference,
        calculation_type=project.calculation_type,
        standard=project.standard,
        notes=project.notes,
        status="draft",
        config_json=project.config_json,
        result_json=project.result_json,
        t_amb_c=project.t_amb_c,
        margen_lavg=project.margen_lavg,
        i_op_ma=project.i_op_ma,
        lm_w_min=project.lm_w_min,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _to_info(copy)
