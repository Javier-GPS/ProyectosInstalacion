"""
Salvi Studio · Columns — Modelos de usuario y permisos
Fase 1, sección 5.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY

from app.core.database import Base, TimestampMixin
from app.core.security import Role
from app.models.db.base_types import UUIDPk, ShortStr, LongText


class User(Base, TimestampMixin):
    """Usuario del sistema. Compatible con SSO corporativo futuro."""
    __tablename__ = "users"

    id: Mapped[UUIDPk]
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    full_name: Mapped[ShortStr]
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Null si SSO
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_sso: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="es", nullable=False)
    preferred_unit_system: Mapped[str] = mapped_column(String(10), default="SI", nullable=False)

    # Relaciones
    roles: Mapped[List["UserRole"]] = relationship(
        back_populates="user",
        foreign_keys="[UserRole.user_id]",
        cascade="all, delete-orphan",
    )
    audit_entries: Mapped[List["AuditLog"]] = relationship(back_populates="actor")


class UserRole(Base, TimestampMixin):
    """Asignación de rol a usuario. Un usuario puede tener múltiples roles."""
    __tablename__ = "user_roles"

    id: Mapped[UUIDPk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role_enum", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    granted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[LongText]

    # Relaciones
    user: Mapped["User"] = relationship(back_populates="roles", foreign_keys=[user_id])
