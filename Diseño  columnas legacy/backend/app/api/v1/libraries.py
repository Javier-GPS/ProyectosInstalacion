"""
Salvi Studio · Columns — API v1: Bibliotecas maestras
Fase 1, sección 11. Ciclo: borrador → revisión → publicado → deprecado.
P-07: versión publicada inmutable.
"""
import uuid
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_roles
from app.core.security import Role
from app.models.db.users import User
from app.models.db.libraries import Library, LibraryVersion, Material
from app.models.schemas.libraries import (
    LibraryCreate, LibraryRead,
    LibraryVersionCreate, LibraryVersionRead,
    LibraryVersionPublish, LibraryVersionDeprecate,
    MaterialCreate, MaterialRead,
)
from app.services.library_service import LibraryService

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _primary_role(roles: list[Role]) -> Role:
    """Rol de mayor privilegio del usuario."""
    priority = [
        Role.SYSTEM_ADMIN, Role.LIBRARY_ADMIN, Role.TECHNICAL_OFFICE,
        Role.ENGINEER, Role.COMMERCIAL, Role.AUDITOR, Role.SERVICE
    ]
    for r in priority:
        if r in roles:
            return r
    return Role.AUDITOR


# ── Bibliotecas ──────────────────────────────────────────────────────────────

@router.post("", response_model=LibraryRead, status_code=status.HTTP_201_CREATED)
async def create_library(
    data: LibraryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    svc = LibraryService(db)
    library = await svc.create_library(data, _primary_role(current_roles))
    return LibraryRead.model_validate(library)


@router.get("", response_model=list[LibraryRead])
async def list_libraries(
    library_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Library)
    if library_type:
        q = q.where(Library.library_type == library_type)
    result = await db.execute(q)
    return [LibraryRead.model_validate(lib) for lib in result.scalars().all()]


@router.get("/{library_id}", response_model=LibraryRead)
async def get_library(library_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    result = await db.execute(select(Library).where(Library.id == library_id))
    lib = result.scalar_one_or_none()
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Biblioteca no encontrada")
    return LibraryRead.model_validate(lib)


# ── Versiones ────────────────────────────────────────────────────────────────

@router.post("/{library_id}/versions", response_model=LibraryVersionRead, status_code=201)
async def create_version(
    library_id: uuid.UUID,
    data: LibraryVersionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    svc = LibraryService(db)
    version = await svc.create_version(library_id, data, _primary_role(current_roles))
    return LibraryVersionRead.model_validate(version)


@router.get("/{library_id}/versions", response_model=list[LibraryVersionRead])
async def list_versions(
    library_id: uuid.UUID,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    q = select(LibraryVersion).where(LibraryVersion.library_id == library_id)
    if status_filter:
        q = q.where(LibraryVersion.status == status_filter)
    result = await db.execute(q)
    return [LibraryVersionRead.model_validate(v) for v in result.scalars().all()]


@router.get("/{library_id}/versions/{version_id}", response_model=LibraryVersionRead)
async def get_version(
    library_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    result = await db.execute(
        select(LibraryVersion).where(
            LibraryVersion.id == version_id,
            LibraryVersion.library_id == library_id,
        )
    )
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versión no encontrada")
    return LibraryVersionRead.model_validate(v)


@router.post("/{library_id}/versions/{version_id}/publish", response_model=LibraryVersionRead)
async def publish_version(
    library_id: uuid.UUID,
    version_id: uuid.UUID,
    data: LibraryVersionPublish,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Publica una versión → INMUTABLE (P-07).
    Solo LIBRARY_ADMIN. AC-19: sin segunda aprobación si se requiere → bloquea.
    """
    svc = LibraryService(db)
    version = await svc.publish_version(
        library_id, version_id, data, current_user.id, _primary_role(current_roles)
    )
    return LibraryVersionRead.model_validate(version)


@router.post("/{library_id}/versions/{version_id}/deprecate", response_model=LibraryVersionRead)
async def deprecate_version(
    library_id: uuid.UUID,
    version_id: uuid.UUID,
    data: LibraryVersionDeprecate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Depreca versión — impide nuevos usos pero NO invalida proyectos históricos.
    AC-23: genera notificación de impacto (implementación completa en sprint de notificaciones).
    """
    svc = LibraryService(db)
    version = await svc.deprecate_version(
        library_id, version_id, data, _primary_role(current_roles)
    )
    return LibraryVersionRead.model_validate(version)


# ── Materiales ───────────────────────────────────────────────────────────────

@router.post(
    "/{library_id}/versions/{version_id}/materials",
    response_model=MaterialRead,
    status_code=201,
)
async def add_material(
    library_id: uuid.UUID,
    version_id: uuid.UUID,
    data: MaterialCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Añade un material a una versión de biblioteca en borrador.
    P-07: no se puede añadir a una versión publicada.
    Propiedades mecánicas en SI (P-06): Pa, kg/m³, K.
    """
    svc = LibraryService(db)
    material = await svc.create_material(version_id, data, _primary_role(current_roles))
    return MaterialRead.model_validate(material)


@router.get(
    "/{library_id}/versions/{version_id}/materials",
    response_model=list[MaterialRead],
)
async def list_materials(
    library_id: uuid.UUID,
    version_id: uuid.UUID,
    family: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Material).where(Material.library_version_id == version_id)
    if family:
        q = q.where(Material.material_family == family)
    result = await db.execute(q)
    return [MaterialRead.model_validate(m) for m in result.scalars().all()]
