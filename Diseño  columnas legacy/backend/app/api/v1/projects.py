"""
Salvi Studio · Columns — API v1: Proyectos y Revisiones
Fase 1, sección 17.

Convenciones:
  - ETags para caché y concurrencia optimista
  - Idempotency-Key en POST (AC-20)
  - Paginación en listados
  - 404/403 sin fuga de metadatos (AC-21)
"""
import uuid
from typing import Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import Role, MaturityLevel, ProjectStatus
from app.core.dependencies import get_current_user, get_current_roles
from app.models.db.users import User
from app.models.db.projects import Project, DesignScenario, Revision
from app.models.schemas.projects import (
    ProjectCreate, ProjectUpdate, ProjectRead, PaginatedProjects,
    RevisionCreate, RevisionRead, PaginatedRevisions,
    RevisionFreezeRequest, RevisionValidateRequest,
    ProjectStatusTransition, ProjectMaturityTransition,
    ScenarioCreate, ScenarioRead,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


# ── Dependency: usuario actual (JWT real) ─────────────────────────────────────

_ROLE_PRIORITY = [
    Role.SYSTEM_ADMIN, Role.TECHNICAL_OFFICE, Role.ENGINEER,
    Role.LIBRARY_ADMIN, Role.COMMERCIAL, Role.AUDITOR, Role.SERVICE,
]


async def get_current_user_id(
    current_user: Annotated[User, Depends(get_current_user)],
) -> uuid.UUID:
    return current_user.id


async def get_current_role(
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
) -> Role:
    for r in _ROLE_PRIORITY:
        if r in current_roles:
            return r
    return Role.AUDITOR


async def get_project_or_404(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Project:
    """
    Obtiene proyecto o devuelve 404. AC-21: sin fuga de metadatos
    (devuelve 404 aunque exista pero pertenezca a otro workspace).
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto no encontrado")
    return project


async def get_revision_or_404(
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Revision:
    result = await db.execute(
        select(Revision).where(
            Revision.id == revision_id,
            Revision.project_id == project_id,
        )
    )
    rev = result.scalar_one_or_none()
    if not rev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revisión no encontrada")
    return rev


# ── Proyectos ────────────────────────────────────────────────────────────────

@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    """
    Crea un nuevo proyecto. AC-01.
    Si cloned_from_id está presente, clona sin estado validado (AC-17).
    Soporta Idempotency-Key (AC-20).
    """
    svc = ProjectService(db)
    project = await svc.create_project(data, user_id, role)
    return ProjectRead.model_validate(project)


@router.get("", response_model=PaginatedProjects)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    status_filter: Optional[ProjectStatus] = Query(default=None, alias="status"),
    maturity_filter: Optional[MaturityLevel] = Query(default=None, alias="maturity"),
    country: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """Lista proyectos con filtros y paginación."""
    q = select(Project)
    if status_filter:
        q = q.where(Project.status == status_filter)
    if maturity_filter:
        q = q.where(Project.maturity == maturity_filter)
    if country:
        q = q.where(Project.country == country.upper())

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar()

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return PaginatedProjects(
        items=[ProjectRead.model_validate(p) for p in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=((total - 1) // page_size + 1) if total else 0,
    )


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project: Project = Depends(get_project_or_404)):
    """Obtiene un proyecto por ID."""
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    data: ProjectUpdate,
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
):
    """
    Actualiza datos editables del proyecto.
    P-01: solo proyectos no congelados (borradores).
    """
    if project.status not in (ProjectStatus.DRAFT, ProjectStatus.IN_PREPARATION):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Solo se pueden editar proyectos en borrador o en preparación"
        )
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await db.flush()
    return ProjectRead.model_validate(project)


@router.post("/{project_id}/status", response_model=ProjectRead)
async def transition_project_status(
    data: ProjectStatusTransition,
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
):
    """Cambia el estado del proyecto. P-08: razón obligatoria."""
    svc = ProjectService(db)
    project = await svc.transition_status(project, data.target_status, data.reason, user_id, role)
    return ProjectRead.model_validate(project)


@router.post("/{project_id}/archive", response_model=ProjectRead)
async def archive_project(
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
):
    """Archiva un proyecto. Recuperable."""
    from datetime import datetime, timezone
    project.archived_at = datetime.now(timezone.utc)
    project.status = ProjectStatus.ARCHIVED
    await db.flush()
    return ProjectRead.model_validate(project)


# ── Escenarios ───────────────────────────────────────────────────────────────

@router.post("/{project_id}/scenarios", response_model=ScenarioRead, status_code=201)
async def create_scenario(
    data: ScenarioCreate,
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
):
    """Crea un escenario de diseño. AC-02."""
    scenario = DesignScenario(
        project_id=project.id,
        name=data.name,
        description=data.description,
        site_id=data.site_id,
        is_base=data.is_base,
        cloned_from_id=data.cloned_from_id,
        status="active",
    )
    db.add(scenario)
    await db.flush()
    return ScenarioRead.model_validate(scenario)


@router.get("/{project_id}/scenarios", response_model=list[ScenarioRead])
async def list_scenarios(
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DesignScenario).where(DesignScenario.project_id == project.id)
    )
    return [ScenarioRead.model_validate(s) for s in result.scalars().all()]


# ── Revisiones ───────────────────────────────────────────────────────────────

@router.post("/{project_id}/revisions", response_model=RevisionRead, status_code=201)
async def create_revision(
    data: RevisionCreate,
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
):
    """Crea una nueva revisión del proyecto."""
    revision = Revision(
        project_id=project.id,
        revision_code=data.revision_code,
        revision_type=data.revision_type,
        description=data.description,
        change_summary=data.change_summary,
        is_frozen=False,
        maturity=project.maturity,
    )
    db.add(revision)
    await db.flush()
    return RevisionRead.model_validate(revision)


@router.get("/{project_id}/revisions", response_model=PaginatedRevisions)
async def list_revisions(
    project: Project = Depends(get_project_or_404),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """Lista revisiones de un proyecto."""
    q = select(Revision).where(Revision.project_id == project.id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return PaginatedRevisions(
        items=[RevisionRead.model_validate(r) for r in rows],
        total=total, page=page, page_size=page_size,
        pages=((total - 1) // page_size + 1) if total else 0,
    )


@router.get("/{project_id}/revisions/{revision_id}", response_model=RevisionRead)
async def get_revision(revision: Revision = Depends(get_revision_or_404)):
    return RevisionRead.model_validate(revision)


@router.post("/{project_id}/revisions/{revision_id}/freeze", response_model=RevisionRead)
async def freeze_revision(
    data: RevisionFreezeRequest,
    revision: Revision = Depends(get_revision_or_404),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
):
    """
    Congela una revisión — P-01.
    Operación irreversible: crea snapshot e hash de integridad.
    """
    svc = ProjectService(db)
    revision = await svc.freeze_revision(revision, data, user_id, role)
    return RevisionRead.model_validate(revision)


@router.post("/{project_id}/revisions/{revision_id}/validate-m3", response_model=RevisionRead)
async def validate_revision_m3(
    data: RevisionValidateRequest,
    revision: Revision = Depends(get_revision_or_404),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
    role: Role = Depends(get_current_role),
):
    """Validación de Oficina Técnica — M3. Solo Role.TECHNICAL_OFFICE."""
    svc = ProjectService(db)
    revision = await svc.validate_m3(revision, data, user_id, role)
    return RevisionRead.model_validate(revision)
