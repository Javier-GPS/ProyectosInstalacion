"""
Salvi Studio · Columns — Servicio de proyectos
Lógica de negocio: estados, madurez, permisos, auditoría.
P-01, P-03, P-04, P-05, P-08.
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.core.security import Role, MaturityLevel, ProjectStatus, has_permission
from app.models.db.projects import Project, DesignScenario, Revision, RevisionSnapshot
from app.models.db.audit import AuditLog
from app.models.schemas.projects import (
    ProjectCreate, ProjectUpdate, RevisionCreate,
    RevisionFreezeRequest, RevisionValidateRequest
)


# ── Máquina de estados del proyecto (sección 6.1, Fase 1) ───────────────────

VALID_STATUS_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.DRAFT: {ProjectStatus.IN_PREPARATION, ProjectStatus.ARCHIVED, ProjectStatus.CANCELLED},
    ProjectStatus.IN_PREPARATION: {ProjectStatus.IN_REVIEW, ProjectStatus.DRAFT, ProjectStatus.ARCHIVED},
    ProjectStatus.IN_REVIEW: {ProjectStatus.OBSERVED, ProjectStatus.VALIDATED, ProjectStatus.IN_PREPARATION},
    ProjectStatus.OBSERVED: {ProjectStatus.IN_REVIEW, ProjectStatus.IN_PREPARATION},
    ProjectStatus.VALIDATED: {ProjectStatus.IN_REVIEW, ProjectStatus.ARCHIVED},  # Nueva rama posible
    ProjectStatus.RELEASED: {ProjectStatus.ARCHIVED},
    ProjectStatus.ARCHIVED: {ProjectStatus.DRAFT},   # Restauración autorizada
    ProjectStatus.CANCELLED: set(),                  # Terminal — duplicar para reutilizar
    ProjectStatus.BLOCKED: {ProjectStatus.DRAFT, ProjectStatus.IN_PREPARATION},
}


# ── Generación de código de proyecto ─────────────────────────────────────────

async def generate_project_code(db: AsyncSession, country: str) -> str:
    """
    Genera código único: COL-{COUNTRY}-{YEAR}-{SEQ:04d}
    Ej: COL-ES-2026-0042
    """
    year = datetime.now(timezone.utc).year
    prefix = f"COL-{country.upper()}-{year}-"
    result = await db.execute(
        select(func.count()).where(Project.project_code.like(f"{prefix}%"))
    )
    seq = (result.scalar() or 0) + 1
    return f"{prefix}{seq:04d}"


# ── Servicio principal ────────────────────────────────────────────────────────

class ProjectService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_project(
        self, data: ProjectCreate, actor_id: uuid.UUID, actor_role: Role
    ) -> Project:
        """AC-01: Crear proyecto con datos mínimos."""
        if not has_permission(actor_role, "project:create"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para crear proyectos")

        code = await generate_project_code(self.db, data.country)

        # Si es clonación (AC-17): copiar sin aprobaciones ni estado validado
        if data.cloned_from_id:
            await self._validate_clone_source(data.cloned_from_id)

        project = Project(
            project_code=code,
            name=data.name,
            country=data.country,
            language=data.language,
            currency=data.currency,
            timezone=data.timezone,
            confidentiality=data.confidentiality,
            description=data.description,
            customer_id=data.customer_id,
            opportunity_ref=data.opportunity_ref,
            region=data.region,
            owner_user_id=actor_id,
            cloned_from_id=data.cloned_from_id,
            status=ProjectStatus.DRAFT,
            maturity=MaturityLevel.M0,
        )
        self.db.add(project)
        await self.db.flush()

        # Escenario base automático
        base_scenario = DesignScenario(
            project_id=project.id,
            name="Base",
            is_base=True,
            status="active",
        )
        self.db.add(base_scenario)

        # Auditoría
        await self._audit(
            action="project.create",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            actor_id=actor_id,
            actor_role=actor_role,
            after_state={"code": code, "status": "draft", "maturity": "M0"},
        )

        await self.db.flush()
        return project

    async def transition_status(
        self,
        project: Project,
        target: ProjectStatus,
        reason: str,
        actor_id: uuid.UUID,
        actor_role: Role,
    ) -> Project:
        """Cambia estado del proyecto validando la máquina de estados."""
        allowed = VALID_STATUS_TRANSITIONS.get(project.status, set())
        if target not in allowed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Transición no permitida: {project.status} → {target}"
            )

        # M3 solo Oficina Técnica
        if target == ProjectStatus.VALIDATED and actor_role != Role.TECHNICAL_OFFICE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo Oficina Técnica puede validar M3")

        before = project.status
        project.status = target

        await self._audit(
            action="project.status_transition",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            actor_id=actor_id,
            actor_role=actor_role,
            before_state={"status": before},
            after_state={"status": target},
            reason=reason,
        )
        return project

    async def freeze_revision(
        self,
        revision: Revision,
        data: RevisionFreezeRequest,
        actor_id: uuid.UUID,
        actor_role: Role,
    ) -> Revision:
        """
        Congela una revisión — P-01.
        Crea snapshot + hash de integridad. Revisión inmutable desde este momento.
        """
        if not has_permission(actor_role, "project:freeze_revision"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para congelar revisiones")

        if revision.is_frozen:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"La revisión {revision.revision_code} ya está congelada (P-01)"
            )

        # Calcular hash canónico de entradas (P-02)
        snapshot_data = await self._build_snapshot(revision)
        canonical = json.dumps(snapshot_data, sort_keys=True, ensure_ascii=False)
        canonical_hash = hashlib.sha256(canonical.encode()).hexdigest()

        # Marcar revisión como congelada
        revision.is_frozen = True
        revision.frozen_at = datetime.now(timezone.utc)
        revision.frozen_by_id = actor_id
        revision.maturity = data.maturity
        revision.change_summary = data.change_summary
        revision.input_hash = canonical_hash

        # Crear snapshot inmutable
        snapshot = RevisionSnapshot(
            revision_id=revision.id,
            canonical_hash=canonical_hash,
            **snapshot_data,
        )
        self.db.add(snapshot)

        await self._audit(
            action="revision.freeze",
            entity_type="revision",
            entity_id=revision.id,
            project_id=revision.project_id,
            actor_id=actor_id,
            actor_role=actor_role,
            after_state={
                "revision_code": revision.revision_code,
                "maturity": data.maturity,
                "hash": canonical_hash,
            },
            reason=data.change_summary,
        )

        return revision

    async def validate_m3(
        self,
        revision: Revision,
        data: RevisionValidateRequest,
        actor_id: uuid.UUID,
        actor_role: Role,
    ) -> Revision:
        """Validación OT — transición a M3. Solo Role.TECHNICAL_OFFICE."""
        if actor_role != Role.TECHNICAL_OFFICE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo Oficina Técnica puede validar M3")

        if not revision.is_frozen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Solo se pueden validar revisiones congeladas"
            )

        if not data.accept:
            # Rechazar — vuelve a IN_REVIEW / OBSERVED
            await self._audit(
                action="revision.m3_rejected",
                entity_type="revision",
                entity_id=revision.id,
                project_id=revision.project_id,
                actor_id=actor_id,
                actor_role=actor_role,
                reason=data.validation_comment,
            )
            return revision

        revision.maturity = MaturityLevel.M3
        revision.validated_at = datetime.now(timezone.utc)
        revision.validated_by_id = actor_id
        revision.validation_comment = data.validation_comment

        await self._audit(
            action="revision.m3_validated",
            entity_type="revision",
            entity_id=revision.id,
            project_id=revision.project_id,
            actor_id=actor_id,
            actor_role=actor_role,
            after_state={"maturity": "M3"},
            reason=data.validation_comment,
        )

        return revision

    async def _validate_clone_source(self, source_id: uuid.UUID) -> None:
        """AC-17: clonar sin aprobaciones ni estado validado."""
        result = await self.db.execute(select(Project).where(Project.id == source_id))
        source = result.scalar_one_or_none()
        if not source:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto origen no encontrado")

    async def _build_snapshot(self, revision: Revision) -> dict:
        """Construye el snapshot completo para una revisión (sección 9, Fase 1)."""
        # En Fase 1 el snapshot incluye lo disponible; se enriquece en fases 3-4
        return {
            "project_snapshot": {"revision_id": str(revision.id)},
            "normative_snapshot": {},    # Fase 6 (normas)
            "library_snapshot": {},      # Fase 5+ (materiales, etc.)
            "geo_snapshot": {},          # Fase 3 (geodatos)
            "configuration_snapshot": {"unit_system": "SI"},
            "software_snapshot": {"app_version": "0.1.0"},
            "input_snapshot": {},
            "artifact_manifest": {},
        }

    async def _audit(
        self,
        action: str,
        entity_type: str,
        actor_id: uuid.UUID,
        actor_role: Role,
        entity_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Registra entrada inmutable de auditoría (P-03)."""
        entry = AuditLog(
            actor_id=actor_id,
            actor_role=actor_role.value,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            action=action,
            action_result="success",
            before_state=before_state,
            after_state=after_state,
            reason=reason,
        )
        self.db.add(entry)
