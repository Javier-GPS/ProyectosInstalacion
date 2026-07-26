import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import jwk, jwt
from jose.constants import Algorithms
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services.auth import (
    COMPANY_NAME,
    create_token,
    decode_token,
    ensure_users_table,
    hash_password,
    verify_password,
)
from ..services.jwks import get_jwks_keys

router = APIRouter()


class LoginBody(BaseModel):
    email: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


class UserInfo(BaseModel):
    id: int
    company_name: str
    email: str
    name: str
    role: str
    is_active: bool
    must_reset_password: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


def _user_info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        company_name=user.company_name,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        must_reset_password=user.must_reset_password,
    )


async def _oidc_verify(token: str) -> dict[str, Any] | None:
    issuer = os.getenv("OIDC_ISSUER_URL", "")
    if not issuer:
        return None
    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        if not kid:
            return None
        keys = await get_jwks_keys(issuer)
        if kid not in keys:
            return None
        key = jwk.construct(keys[kid])
        payload = jwt.decode(
            token, key,
            algorithms=[Algorithms.RS256, Algorithms.RS384, Algorithms.RS512],
            options={"verify_aud": False, "verify_exp": True},
        )
        return payload
    except Exception:
        return None


async def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    ensure_users_table()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()

    # 1. Try OIDC (Keycloak)
    payload = await _oidc_verify(token)
    if payload:
        email = payload.get("email", "") or ""
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                name=payload.get("preferred_username", email),
                email=email,
                company_name="SALVI LIGHTING",
                password_hash="oidc",
                role="ADMIN",
                is_active=True,
                must_reset_password=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif user.must_reset_password:
            user.must_reset_password = False
            db.commit()
        return user

    # 2. Fallback: HS256 (existing auth)
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive or missing user")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginBody, db: Session = Depends(get_db)):
    ensure_users_table()
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales no validas")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return LoginResponse(access_token=create_token(user), user=_user_info(user))


@router.get("/me", response_model=UserInfo)
async def me(user: User = Depends(current_user)):
    return _user_info(user)


@router.post("/change-password", response_model=UserInfo)
async def change_password(
    body: ChangePasswordBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="La contrasena actual no es correcta")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nueva contrasena debe tener al menos 8 caracteres")

    user.password_hash = hash_password(body.new_password)
    user.must_reset_password = False
    user.company_name = COMPANY_NAME
    db.commit()
    db.refresh(user)
    return _user_info(user)
