"""
Salvi Studio · Columns — Dependencies FastAPI para auth real con JWT
Sustituye los stubs en projects.py una vez activado este módulo.
"""
import uuid
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import Role, decode_token
from app.models.db.users import User, UserRole
from datetime import datetime, timezone

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado o inactivo")
    return user


async def get_current_roles(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> list[Role]:
    result = await db.execute(
        select(UserRole.role).where(
            UserRole.user_id == current_user.id,
            (UserRole.expires_at == None) | (UserRole.expires_at > datetime.now(timezone.utc))
        )
    )
    return [row[0] for row in result.all()]


def require_role(*roles: Role):
    """Dependency factory: exige al menos uno de los roles indicados."""
    async def _check(
        current_roles: Annotated[list[Role], Depends(get_current_roles)]
    ) -> list[Role]:
        if not any(r in current_roles for r in roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Se requiere uno de los roles: {[r.value for r in roles]}"
            )
        return current_roles
    return _check
