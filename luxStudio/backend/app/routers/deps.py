"""Shared dependencies — OIDC-only auth check.

No more HS256 local JWTs. All authentication goes through
Keycloak (OIDC) via the portal login flow.
"""
import os
from typing import Any

from fastapi import Depends, Header, HTTPException
from jose import jwk, jwt
from jose.constants import Algorithms
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import engine, get_db
from ..models import User
from ..services.jwks import get_jwks_keys


class UserInfo(BaseModel):
    id: int
    company_name: str
    email: str
    name: str
    role: str
    is_active: bool
    must_reset_password: bool


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
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()

    # OIDC (Keycloak) — only auth method
    payload = await _oidc_verify(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

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


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def ensure_users_table() -> None:
    User.__table__.create(bind=engine, checkfirst=True)
