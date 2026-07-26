from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services.auth import COMPANY_NAME, ensure_users_table, hash_password
from .auth import UserInfo, require_admin

router = APIRouter()


class CreateUserBody(BaseModel):
    name: str
    email: str
    role: str = "USER"
    password: str
    is_active: bool = True
    must_reset_password: bool = True


class UpdateUserBody(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    must_reset_password: Optional[bool] = None


class ResetPasswordBody(BaseModel):
    password: str
    must_reset_password: bool = True


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


@router.get("", response_model=list[UserInfo])
async def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_users_table()
    return [_user_info(user) for user in db.query(User).order_by(User.id.asc()).all()]


@router.post("", response_model=UserInfo)
async def create_user(body: CreateUserBody, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_users_table()
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    role = body.role.upper()
    if role not in {"ADMIN", "USER"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    user = User(
        company_name=COMPANY_NAME,
        email=email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=role,
        is_active=body.is_active,
        must_reset_password=body.must_reset_password,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_info(user)


@router.patch("/{user_id}", response_model=UserInfo)
async def update_user(user_id: int, body: UpdateUserBody, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_users_table()
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = body.model_dump(exclude_none=True)
    if "email" in data:
        data["email"] = data["email"].lower().strip()
    if "role" in data:
        data["role"] = data["role"].upper()
        if data["role"] not in {"ADMIN", "USER"}:
            raise HTTPException(status_code=400, detail="Invalid role")
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return _user_info(user)


@router.post("/{user_id}/reset-password", response_model=UserInfo)
async def reset_password(user_id: int, body: ResetPasswordBody, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(body.password)
    user.must_reset_password = body.must_reset_password
    db.commit()
    db.refresh(user)
    return _user_info(user)


@router.post("/{user_id}/activate", response_model=UserInfo)
async def activate_user(user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    db.refresh(user)
    return _user_info(user)


@router.post("/{user_id}/deactivate", response_model=UserInfo)
async def deactivate_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate current user")
    user.is_active = False
    db.commit()
    db.refresh(user)
    return _user_info(user)
