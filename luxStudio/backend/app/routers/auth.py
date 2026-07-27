"""Auth — only /api/auth/me (OIDC validation via deps).

No more local login, register, or password endpoints.
All authentication flows through the Portal → Keycloak.
"""
from fastapi import APIRouter, Depends

from .deps import UserInfo, _user_info, current_user

router = APIRouter()


@router.get("/me", response_model=UserInfo)
async def me(user=Depends(current_user)):
    return _user_info(user)
