"""Shared dependencies — auth checks with OIDC + HS256 fallback."""
import json
from typing import Any

from fastapi import Depends, Header, HTTPException
from jose import jwk, jwt
from jose.constants import Algorithms
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.security import decode_token as hs256_decode
from ..models import User
from ..services.jwks import get_jwks_keys


async def _oidc_verify(token: str) -> dict[str, Any] | None:
    """Verify JWT against Keycloak JWKS. Returns payload or None."""
    issuer = settings.oidc_issuer_url
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
            token,
            key,
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

    # 1. Try OIDC (Keycloak)
    payload = await _oidc_verify(token)
    if payload:
        email = payload.get("email", "") or ""
        sub = payload.get("sub", "")
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                name=payload.get("preferred_username", email),
                email=email,
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
        payload = hs256_decode(token)
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
