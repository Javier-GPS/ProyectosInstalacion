"""
Salvi Studio · Columns — API v1: Usuarios y roles
P-04: crear, asignar roles y validar son acciones separadas.
"""
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_roles, require_role
from app.core.security import Role
from app.models.db.users import User, UserRole
from app.models.schemas.users import UserCreate, UserRead, UserUpdate, RoleAssign
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _user_to_read(user: User, roles: list[str]) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_sso=user.is_sso,
        preferred_language=user.preferred_language,
        preferred_unit_system=user.preferred_unit_system,
        roles=roles,
        created_at=user.created_at,
    )


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
):
    """Devuelve el usuario autenticado y sus roles activos."""
    return _user_to_read(current_user, [r.value for r in current_roles])


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(Role.SYSTEM_ADMIN))],
)
async def create_user(
    data: UserCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """Crea un usuario. Solo SYSTEM_ADMIN."""
    svc = UserService(db)
    user = await svc.create_user(data, current_roles[0] if current_roles else Role.AUDITOR)
    return _user_to_read(user, [])


@router.get(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_role(Role.SYSTEM_ADMIN))],
)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    roles_result = await db.execute(select(UserRole.role).where(UserRole.user_id == user_id))
    roles = [r[0].value for r in roles_result.all()]
    return _user_to_read(user, roles)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Un usuario puede editar sus propios datos. Admin puede editar cualquiera."""
    from fastapi import HTTPException
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    if user.id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes editar tu propio perfil")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.flush()

    roles_result = await db.execute(select(UserRole.role).where(UserRole.user_id == user_id))
    roles = [r[0].value for r in roles_result.all()]
    return _user_to_read(user, roles)


@router.post(
    "/{user_id}/roles",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(Role.SYSTEM_ADMIN))],
)
async def assign_role(
    user_id: uuid.UUID,
    data: RoleAssign,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """Asigna un rol a un usuario. Solo SYSTEM_ADMIN. P-04."""
    svc = UserService(db)
    await svc.assign_role(
        user_id=user_id,
        role=data.role,
        granted_by_id=current_user.id,
        actor_role=Role.SYSTEM_ADMIN,
        note=data.note,
        expires_at=data.expires_at,
    )
    return {"detail": f"Rol {data.role.value} asignado correctamente"}


@router.delete(
    "/{user_id}/roles/{role}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(Role.SYSTEM_ADMIN))],
)
async def revoke_role(
    user_id: uuid.UUID,
    role: Role,
    db: AsyncSession = Depends(get_db),
):
    """Revoca un rol de un usuario. Solo SYSTEM_ADMIN."""
    from fastapi import HTTPException
    result = await db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role == role)
    )
    user_role = result.scalar_one_or_none()
    if not user_role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rol no encontrado para este usuario")
    await db.delete(user_role)
