"""
Salvi Studio · Columns — API v1: Autenticación
Login, refresh de token. SSO corporativo se añadirá como proveedor OAuth2.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token, Role
from app.models.schemas.users import TokenResponse, RefreshRequest
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Login con email y contraseña. Devuelve access_token + refresh_token.
    username = email (convención OAuth2PasswordRequestForm).
    """
    svc = UserService(db)
    user = await svc.authenticate(form.username, form.password)
    roles = await svc.get_user_roles(user.id)
    return svc.create_tokens(user, roles)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Renueva el access_token a partir de un refresh_token válido."""
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de refresco inválido")

    from sqlalchemy import select
    from app.models.db.users import User
    import uuid

    result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo")

    svc = UserService(db)
    roles = await svc.get_user_roles(user.id)
    return svc.create_tokens(user, roles)
