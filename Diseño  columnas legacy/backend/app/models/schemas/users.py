"""
Salvi Studio · Columns — Schemas Pydantic para usuarios y autenticación
"""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

from app.core.security import Role


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., max_length=180)
    password: str = Field(..., min_length=8)
    preferred_language: str = Field(default="es", pattern="^(es|en|fr|ca|it|pt)$")
    preferred_unit_system: str = Field(default="SI", pattern="^(SI|imperial)$")


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_sso: bool
    preferred_language: str
    preferred_unit_system: str
    roles: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=180)
    preferred_language: Optional[str] = Field(default=None, pattern="^(es|en|fr|ca|it|pt)$")
    preferred_unit_system: Optional[str] = Field(default=None, pattern="^(SI|imperial)$")


class RoleAssign(BaseModel):
    role: Role
    note: Optional[str] = Field(default=None, max_length=500)
    expires_at: Optional[datetime] = None


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    username: str   # email en OAuth2PasswordRequestForm
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int   # segundos


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPayload(BaseModel):
    sub: str          # user_id como string
    email: str
    roles: List[str]
    exp: int
