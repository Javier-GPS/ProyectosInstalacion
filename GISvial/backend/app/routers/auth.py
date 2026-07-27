"""Auth — only /api/auth/me (OIDC validation via deps).

No more local login, register, or password endpoints.
All authentication flows through the Portal → Keycloak.
"""
from fastapi import APIRouter, Depends

from .deps import current_user

router = APIRouter()


@router.get("/api/auth/me")
async def gis_auth_me(user=Depends(current_user)):
    return {
        "id": str(user.id), "user_id": user.id,
        "username": user.name, "name": user.name,
        "email": user.email, "role": user.role,
        "company_name": user.company_name or "SALVI LIGHTING",
        "is_active": user.is_active,
        "must_reset_password": user.must_reset_password,
    }
