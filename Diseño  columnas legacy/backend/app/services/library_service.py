"""
Salvi Studio · Columns — Servicio de bibliotecas maestras
P-07: versión publicada INMUTABLE. Para cambiar → nueva versión.
Sección 11, Fase 1.
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.security import Role
from app.models.db.libraries import Library, LibraryVersion, Material
from app.models.schemas.libraries import (
    LibraryCreate, LibraryVersionCreate,
    LibraryVersionPublish, LibraryVersionDeprecate, MaterialCreate
)


class LibraryService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_library(self, data: LibraryCreate, actor_role: Role) -> Library:
        """Solo ingeniería, OT o admin de biblioteca puede crear bibliotecas."""
        allowed = {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.LIBRARY_ADMIN, Role.SYSTEM_ADMIN}
        if actor_role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para crear bibliotecas")

        existing = await self.db.execute(select(Library).where(Library.code == data.code))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, f"Código de biblioteca '{data.code}' ya existe")

        library = Library(**data.model_dump())
        self.db.add(library)
        await self.db.flush()
        return library

    async def create_version(
        self, library_id: uuid.UUID, data: LibraryVersionCreate, actor_role: Role
    ) -> LibraryVersion:
        """Crea versión en estado borrador."""
        allowed = {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.LIBRARY_ADMIN, Role.SYSTEM_ADMIN}
        if actor_role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para crear versiones")

        # Verificar que la biblioteca existe
        lib = await self._get_library_or_404(library_id)

        # Calcular hash del contenido
        content_hash = hashlib.sha256(
            json.dumps(data.content, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        version = LibraryVersion(
            library_id=library_id,
            version_number=data.version_number,
            description=data.description,
            change_notes=data.change_notes,
            content=data.content,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            status="draft",
            content_hash=content_hash,
        )
        self.db.add(version)
        await self.db.flush()
        return version

    async def publish_version(
        self,
        library_id: uuid.UUID,
        version_id: uuid.UUID,
        data: LibraryVersionPublish,
        actor_id: uuid.UUID,
        actor_role: Role,
    ) -> LibraryVersion:
        """
        Publica una versión. Solo LIBRARY_ADMIN puede publicar.
        P-07: tras publicar, la versión es INMUTABLE.
        AC-19: sin segunda aprobación si se requiere → bloquear.
        """
        if actor_role != Role.LIBRARY_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador de biblioteca puede publicar")

        version = await self._get_version_or_404(library_id, version_id)

        if version.status == "published":
            raise HTTPException(status.HTTP_409_CONFLICT, "La versión ya está publicada (P-07: inmutable)")
        if version.status in ("deprecated", "withdrawn"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No se puede publicar una versión retirada")
        if version.status != "draft" and version.status != "under_review":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Solo se pueden publicar versiones en borrador o revisión")

        version.status = "published"
        version.published_at = datetime.now(timezone.utc)
        version.published_by_id = actor_id
        if data.valid_from:
            version.valid_from = data.valid_from
        if data.valid_until:
            version.valid_until = data.valid_until

        await self.db.flush()
        return version

    async def deprecate_version(
        self,
        library_id: uuid.UUID,
        version_id: uuid.UUID,
        data: LibraryVersionDeprecate,
        actor_role: Role,
    ) -> LibraryVersion:
        """
        Depreca una versión. Impide nuevos usos pero NO invalida proyectos históricos.
        P-07, sección 11.
        """
        if actor_role not in {Role.LIBRARY_ADMIN, Role.SYSTEM_ADMIN}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para deprecar versiones")

        version = await self._get_version_or_404(library_id, version_id)
        if version.status not in ("published",):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Solo se pueden deprecar versiones publicadas")

        version.status = "deprecated"
        await self.db.flush()
        return version

    async def create_material(
        self, library_version_id: uuid.UUID, data: MaterialCreate, actor_role: Role
    ) -> Material:
        """Añade un material a una versión en borrador."""
        allowed = {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.LIBRARY_ADMIN, Role.SYSTEM_ADMIN}
        if actor_role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para añadir materiales")

        # Verificar que la versión es un borrador (no publicada)
        result = await self.db.execute(
            select(LibraryVersion).where(LibraryVersion.id == library_version_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Versión de biblioteca no encontrada")
        if version.status == "published":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "No se puede modificar una versión publicada. Cree una nueva versión (P-07)."
            )

        material = Material(library_version_id=library_version_id, **data.model_dump())
        self.db.add(material)
        await self.db.flush()
        return material

    async def _get_library_or_404(self, library_id: uuid.UUID) -> Library:
        result = await self.db.execute(select(Library).where(Library.id == library_id))
        lib = result.scalar_one_or_none()
        if not lib:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Biblioteca no encontrada")
        return lib

    async def _get_version_or_404(self, library_id: uuid.UUID, version_id: uuid.UUID) -> LibraryVersion:
        result = await self.db.execute(
            select(LibraryVersion).where(
                LibraryVersion.id == version_id,
                LibraryVersion.library_id == library_id,
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Versión no encontrada")
        return version
