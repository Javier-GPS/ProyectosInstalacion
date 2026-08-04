"""
Salvi Studio · Columns — Seguridad y autenticación
JWT + RBAC por rol. P-04: separación de responsabilidades.
P-09: IA no autoritativa — ningún token puede bypasear validaciones normativas.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class Role(str, Enum):
    """Roles del sistema (P-04, sección 5 Fase 1)."""
    COMMERCIAL = "commercial"          # Técnico comercial
    ENGINEER = "engineer"              # Ingeniero de producto
    TECHNICAL_OFFICE = "technical_office"  # Oficina Técnica
    LIBRARY_ADMIN = "library_admin"    # Administrador de bibliotecas
    SYSTEM_ADMIN = "system_admin"      # Administrador del sistema
    AUDITOR = "auditor"               # Solo lectura
    SERVICE = "service"               # Cuenta técnica para servicios automáticos


class MaturityLevel(str, Enum):
    """Niveles de madurez M0-M4 (sección 6 Fase 1)."""
    M0 = "M0"  # Borrador comercial
    M1 = "M1"  # Predimensionamiento
    M2 = "M2"  # Cálculo interno
    M3 = "M3"  # Validado por Oficina Técnica
    M4 = "M4"  # Liberado para fabricación (Fase 15)


class ProjectStatus(str, Enum):
    """Estados operativos del proyecto (sección 6.1 Fase 1)."""
    DRAFT = "draft"                    # Borrador
    IN_PREPARATION = "in_preparation"  # En preparación
    IN_REVIEW = "in_review"            # En revisión
    OBSERVED = "observed"              # Observado
    VALIDATED = "validated"            # Validado (M3)
    RELEASED = "released"              # Liberado (M4, futuro)
    ARCHIVED = "archived"              # Archivado
    CANCELLED = "cancelled"            # Cancelado
    BLOCKED = "blocked"                # Bloqueado


# ── Permisos por acción (sección 5.1 Fase 1) ────────────────────────────────

PERMISSIONS: dict[str, set[Role]] = {
    "project:create":          {Role.COMMERCIAL, Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN},
    "project:edit_m0_m1":      {Role.COMMERCIAL, Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN},
    "project:create_scenario":  {Role.COMMERCIAL, Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN},
    "project:freeze_revision":  {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN},
    "project:validate_m3":      {Role.TECHNICAL_OFFICE},
    "project:release_m4":       set(),  # Desactivado hasta Fase 15
    "library:propose":          {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.LIBRARY_ADMIN},
    "library:publish":          {Role.LIBRARY_ADMIN},
    "audit:view_full":          {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.LIBRARY_ADMIN, Role.SYSTEM_ADMIN, Role.AUDITOR},
    "project:delete_permanent": set(),  # Solo proceso excepcional, nunca por rol
}


def has_permission(role: Role, action: str) -> bool:
    """Comprueba si un rol tiene permiso para una acción."""
    return role in PERMISSIONS.get(action, set())


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
