"""
Salvi Studio · Columns — Servicio de usuarios y autenticación
P-04: separación entre crear, asignar roles y validar.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import Role, hash_password, verify_password, create_access_token
from app.models.db.users import User, UserRole
from app.models.schemas.users import UserCreate, TokenResponse


class UserService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, data: UserCreate, actor_role: Role) -> User:
        """Solo admin del sistema puede crear usuarios."""
        if actor_role != Role.SYSTEM_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador puede crear usuarios")

        existing = await self.db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email ya registrado")

        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            preferred_language=data.preferred_language,
            preferred_unit_system=data.preferred_unit_system,
            is_active=True,
            is_sso=False,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        """Autentica credenciales. P-05: fallo seguro ante dato ausente."""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not user.hashed_password:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales incorrectas")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cuenta desactivada")
        if not verify_password(password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales incorrectas")
        return user

    async def get_user_roles(self, user_id: uuid.UUID) -> list[Role]:
        result = await self.db.execute(
            select(UserRole.role).where(
                UserRole.user_id == user_id,
                (UserRole.expires_at == None) | (UserRole.expires_at > datetime.now(timezone.utc))
            )
        )
        return [row[0] for row in result.all()]

    async def assign_role(
        self,
        user_id: uuid.UUID,
        role: Role,
        granted_by_id: uuid.UUID,
        actor_role: Role,
        note: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> UserRole:
        """P-04: solo admin asigna roles."""
        if actor_role != Role.SYSTEM_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador asigna roles")

        user_role = UserRole(
            user_id=user_id,
            role=role,
            granted_by_id=granted_by_id,
            note=note,
            expires_at=expires_at,
        )
        self.db.add(user_role)
        await self.db.flush()
        return user_role

    def create_tokens(self, user: User, roles: list[Role]) -> TokenResponse:
        role_values = [r.value for r in roles]
        payload = {"sub": str(user.id), "email": user.email, "roles": role_values}

        access_token = create_access_token(
            payload,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
        )
        refresh_token = create_access_token(
            {**payload, "type": "refresh"},
            expires_delta=timedelta(days=settings.refresh_token_expire_days)
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.access_token_expire_minutes * 60,
        )
