"""Auth & Users — login, me, setup, reset, user CRUD."""
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import create_token, hash_password, verify_password, decode_token
from ..models import User, ensure_gis_tables
from ..schemas.auth import (
    GisLoginBody, GisSetupBody, GisResetRequest, GisResetApply,
    GisCreateUserBody, GisUpdateUserBody,
)
from .deps import current_user, require_admin

router = APIRouter()

# ── In-memory reset tokens (same as old api_server.py) ────────────────────
_RESET_TOKENS: dict[str, dict] = {}


# ── Login ─────────────────────────────────────────────────────────────────
@router.post("/api/auth/login")
async def gis_login(body: GisLoginBody, db: Session = Depends(get_db)):
    """Unified login — accepts ``email`` or ``username``."""
    ensure_gis_tables()
    user: User | None = None
    if body.email:
        user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user and body.username:
        user = db.query(User).filter(
            (User.email == body.username.lower().strip()) |
            (User.name == body.username.strip())
        ).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales no validas")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_token(user)
    return {
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id), "user_id": user.id,
            "username": user.name, "name": user.name,
            "email": user.email, "role": user.role,
            "company_name": user.company_name or "SALVI LIGHTING",
            "is_active": user.is_active,
            "must_reset_password": user.must_reset_password,
        },
    }


# ── Me ────────────────────────────────────────────────────────────────────
@router.get("/api/auth/me")
async def gis_auth_me(user: User = Depends(current_user)):
    return {
        "id": str(user.id), "user_id": user.id,
        "username": user.name, "name": user.name,
        "email": user.email, "role": user.role,
        "company_name": user.company_name or "SALVI LIGHTING",
        "is_active": user.is_active,
        "must_reset_password": user.must_reset_password,
    }


# ── Setup (initial admin) ────────────────────────────────────────────────
@router.post("/api/auth/setup")
async def gis_auth_setup(body: GisSetupBody, db: Session = Depends(get_db)):
    existing = db.query(User).count()
    if existing > 0:
        raise HTTPException(status_code=400, detail="Ya hay usuarios en el sistema")
    user = User(
        name=body.username.strip(),
        email=body.email.lower().strip() or f"{body.username.strip().lower()}@salvi.lighting",
        password_hash=hash_password(body.password),
        role="ADMIN", is_active=True, must_reset_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": {"id": str(user.id), "username": user.name, "email": user.email, "role": user.role}}


# ── Password reset ───────────────────────────────────────────────────────
@router.post("/api/auth/reset-request")
async def gis_reset_request(body: GisResetRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if user:
        token = secrets.token_urlsafe(32)
        _RESET_TOKENS[token] = {"uid": str(user.id), "email": user.email, "exp": time.time() + 3600}
        print(f"[GIS] Password-reset token for {user.email}: {token}")
    return {"ok": True, "message": "Si el email existe, recibiras un enlace"}


@router.post("/api/auth/reset-apply")
async def gis_reset_apply(body: GisResetApply, db: Session = Depends(get_db)):
    entry = _RESET_TOKENS.pop(body.token, None)
    if not entry or entry["exp"] < time.time():
        raise HTTPException(status_code=400, detail="Token invalido o expirado")
    user = db.get(User, int(entry["uid"]))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.password_hash = hash_password(body.password)
    db.commit()
    return {"ok": True}


# ── Users CRUD ──────────────────────────────────────────────────────────
@router.get("/api/users")
async def gis_users_list(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": str(u.id), "username": u.name, "email": u.email, "role": u.role} for u in users]


@router.post("/api/users")
async def gis_users_create(body: GisCreateUserBody, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(User).filter(
        (User.email == body.email.lower().strip()) | (User.name == body.username.strip())
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    new_user = User(
        name=body.username.strip(),
        email=body.email.lower().strip() or f"{body.username.strip().lower()}@salvi.lighting",
        password_hash=hash_password(body.password),
        role="ADMIN" if body.role.lower() == "admin" else "USER",
        is_active=True, must_reset_password=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": str(new_user.id), "username": new_user.name, "email": new_user.email, "role": new_user.role}


@router.put("/api/users/{user_id}")
async def gis_users_update(user_id: int, body: GisUpdateUserBody, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if body.username: target.name = body.username.strip()
    if body.email: target.email = body.email.lower().strip()
    if body.password: target.password_hash = hash_password(body.password)
    if body.role: target.role = "ADMIN" if body.role.lower() == "admin" else "USER"
    db.commit()
    return {"ok": True}


@router.delete("/api/users/{user_id}")
async def gis_users_delete(user_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    db.delete(target)
    db.commit()
    return {"ok": True}
