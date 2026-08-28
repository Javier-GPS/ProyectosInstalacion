"""OIDC dependencies shared by the GIS API and its internal worker."""
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException
from jose import jwk, jwt
from jose.constants import Algorithms
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import engine, get_db
from ..models import User
from ..services.jwks import get_jwks_keys


@dataclass(frozen=True)
class Principal:
    user: User
    issuer: str
    subject: str
    claims: dict[str, Any]


async def _oidc_verify(token: str) -> dict[str, Any] | None:
    issuer = settings.oidc_issuer_url
    if not issuer:
        return None
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            return None
        keys = await get_jwks_keys(issuer)
        if kid not in keys:
            return None
        payload = jwt.decode(
            token,
            jwk.construct(keys[kid]),
            algorithms=[Algorithms.RS256, Algorithms.RS384, Algorithms.RS512],
            options={"verify_aud": False, "verify_exp": True},
        )
        if payload.get("iss") != issuer or not payload.get("sub"):
            return None
        token_audience = payload.get("aud", [])
        if isinstance(token_audience, str):
            token_audience = [token_audience]
        if settings.oidc_audiences and not set(settings.oidc_audiences).intersection(token_audience):
            return None
        if not settings.oidc_audiences:
            client_id = payload.get("azp")
            if client_id and client_id not in settings.oidc_allowed_clients:
                return None
        return payload
    except Exception:
        return None


async def _authenticate(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = await _oidc_verify(authorization.split(" ", 1)[1].strip())
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    issuer = str(payload["iss"])
    subject = str(payload["sub"])
    email = str(payload.get("email") or "").strip()
    user = db.query(User).filter(
        User.oidc_issuer == issuer, User.oidc_sub == subject,
    ).first()
    if user is None and email:
        user = db.query(User).filter(
            User.email == email,
            User.oidc_issuer.is_(None),
            User.oidc_sub.is_(None),
        ).first()
        if user is not None and not user.oidc_sub:
            user.oidc_issuer = issuer
            user.oidc_sub = subject
    if user is None:
        if email and db.query(User).filter(User.email == email).first() is not None:
            raise HTTPException(status_code=409, detail="Email is linked to another OIDC identity")
        identity_email = email or f"{subject}@oidc.invalid"
        realm_roles = payload.get("realm_access", {}).get("roles", [])
        user = User(
            name=str(payload.get("preferred_username") or email or subject),
            email=identity_email,
            oidc_issuer=issuer,
            oidc_sub=subject,
            password_hash="oidc",
            role="ADMIN" if "admin" in realm_roles else "USER",
            is_active=True,
            must_reset_password=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.must_reset_password:
        user.must_reset_password = False
        db.commit()
    return Principal(user=user, issuer=issuer, subject=subject, claims=payload)


async def current_principal(principal: Principal = Depends(_authenticate)) -> Principal:
    if not principal.user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")
    return principal


async def current_user(principal: Principal = Depends(current_principal)) -> User:
    return principal.user


async def worker_principal(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Require the fixed Keycloak client-credentials identity of the worker."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Worker token required")
    payload = await _oidc_verify(authorization.split(" ", 1)[1].strip())
    expected = settings.lux_worker_client_id
    if not payload or (
        payload.get("azp") != expected
        and payload.get("preferred_username") != f"service-account-{expected}"
    ):
        raise HTTPException(status_code=403, detail="Invalid worker client")
    return payload


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def ensure_users_table() -> None:
    User.__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oidc_issuer VARCHAR(255)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oidc_sub VARCHAR(255)"))
