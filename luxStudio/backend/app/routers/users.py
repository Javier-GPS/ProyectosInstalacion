from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services import keycloak_admin
from .deps import UserInfo, _user_info, require_admin


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
router = APIRouter()


class CreateUserBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name", "email")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacío")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.lower()
        if not _EMAIL_RE.fullmatch(value):
            raise ValueError("Introduce un email válido")
        return value


@router.post("/users", response_model=UserInfo, status_code=201)
async def create_user(
    body: CreateUserBody,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.query(User).filter(User.email == body.email).first() is not None:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email.")

    try:
        oidc_sub = await keycloak_admin.create_user(body.name, body.email, body.password)
    except keycloak_admin.KeycloakAdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    user = User(
        company_name="SALVI LIGHTING",
        email=body.email,
        oidc_issuer=os.getenv("OIDC_ISSUER_URL") or None,
        oidc_sub=oidc_sub,
        name=body.name,
        password_hash="oidc",
        role="USER",
        is_active=True,
        must_reset_password=False,
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        if oidc_sub:
            await keycloak_admin.delete_user(oidc_sub)
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email.") from exc
    return _user_info(user)
