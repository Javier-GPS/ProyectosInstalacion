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
from sqlalchemy import text
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


async def require_service_account(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Validate the fixed GIS worker client for internal calculation calls."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Service token required")
    payload = await _oidc_verify(authorization.split(" ", 1)[1].strip())
    expected = os.getenv("LUX_WORKER_CLIENT_ID", "gisvial-worker")
    if not payload or (
        payload.get("azp") != expected
        and payload.get("preferred_username") != f"service-account-{expected}"
    ):
        raise HTTPException(status_code=403, detail="Invalid service client")
    return payload


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
        if payload.get("iss") != issuer or not payload.get("sub"):
            return None
        allowed_clients = {
            value.strip() for value in os.getenv(
                "OIDC_ALLOWED_CLIENTS", "portal,gisvial,gateway,luxstudio,gisvial-worker",
            ).split(",") if value.strip()
        }
        if payload.get("azp") and payload["azp"] not in allowed_clients:
            return None
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

    issuer = str(payload["iss"])
    subject = str(payload["sub"])
    email = payload.get("email", "") or f"{subject}@oidc.invalid"
    user = db.query(User).filter(
        User.oidc_issuer == issuer, User.oidc_sub == subject,
    ).first()
    if user is None and email:
        user = db.query(User).filter(
            User.email == email,
            User.oidc_issuer.is_(None),
            User.oidc_sub.is_(None),
        ).first()
        if user is not None:
            user.oidc_issuer = issuer
            user.oidc_sub = subject
            db.commit()
    if not user:
        if email and db.query(User).filter(User.email == email).first() is not None:
            raise HTTPException(status_code=409, detail="Email is linked to another OIDC identity")
        realm_roles = payload.get("realm_access", {}).get("roles", [])
        user = User(
            name=payload.get("preferred_username", email),
            email=email,
            oidc_issuer=issuer,
            oidc_sub=subject,
            company_name="SALVI LIGHTING",
            password_hash="oidc",
            role="ADMIN" if "admin" in realm_roles else "USER",
            is_active=True,
            must_reset_password=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")
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
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oidc_issuer VARCHAR(255)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oidc_sub VARCHAR(255)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_oidc_issuer ON users (oidc_issuer)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_oidc_sub ON users (oidc_sub)"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_oidc_identity "
            "ON users (oidc_issuer, oidc_sub) "
            "WHERE oidc_issuer IS NOT NULL AND oidc_sub IS NOT NULL"
        ))
