"""
Salvi Studio · Columns — API v1: Geometría Paramétrica (Fase 2)
SS-COL-F02-GEO v0.2

Endpoints para crear, leer, modificar, validar y derivar modelos geométricos.
"""
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_roles
from app.core.security import Role
from app.models.db.users import User
from app.models.db.geometry import (
    GeometryModel, Mast, GeometryValidation, GeometryArtifact,
    GeometryQualityState,
)
from app.models.schemas.geometry import (
    GeometryModelCreate, GeometryModelUpdate, GeometryModelRead,
    MastCreate, MastRead,
    ValidationSummary, GeometryValidationRead,
    ArtifactGenerateRequest, GeometryArtifactRead,
    SectionAtZResponse,
    GeometryCloneRequest, GeometryCompareResponse,
)
from app.services.geometry_service import GeometryService

router = APIRouter(prefix="/geometry-models", tags=["geometry"])


def _primary_role(roles: list[Role]) -> Role:
    priority = [
        Role.SYSTEM_ADMIN, Role.TECHNICAL_OFFICE, Role.ENGINEER,
        Role.LIBRARY_ADMIN, Role.COMMERCIAL, Role.AUDITOR, Role.SERVICE,
    ]
    for r in priority:
        if r in roles:
            return r
    return Role.AUDITOR


# ── Geometry models ────────────────────────────────────────────────────────────

@router.post("", response_model=GeometryModelRead, status_code=status.HTTP_201_CREATED)
async def create_geometry_model(
    data: GeometryModelCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo modelo geométrico en estado DRAFT para una revisión de proyecto."""
    svc = GeometryService(db)
    model = await svc.create_geometry_model(data, _primary_role(current_roles))
    await db.commit()
    await db.refresh(model)
    return GeometryModelRead.model_validate(model)


@router.get("/{model_id}", response_model=GeometryModelRead)
async def get_geometry_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GeometryModel).where(GeometryModel.id == str(model_id)))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo geométrico no encontrado")
    return GeometryModelRead.model_validate(model)


@router.patch("/{model_id}", response_model=GeometryModelRead)
async def update_geometry_model(
    model_id: uuid.UUID,
    data: GeometryModelUpdate,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Modifica un modelo geométrico. Usa ETag/If-Match para evitar sobrescritura concurrente (AC-15).
    """
    result = await db.execute(select(GeometryModel).where(GeometryModel.id == str(model_id)))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo geométrico no encontrado")

    if model.quality_state in {GeometryQualityState.CAD_READY}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Modelo en estado cad_ready; cree una nueva revisión")

    if data.lod is not None:
        model.lod = data.lod
    if data.notes is not None:
        model.notes = data.notes
    if data.source is not None:
        model.source = data.source

    # Invalidate hash
    model.geometry_hash = None
    model.quality_state = GeometryQualityState.DRAFT

    await db.commit()
    await db.refresh(model)
    return GeometryModelRead.model_validate(model)


# ── Mast ───────────────────────────────────────────────────────────────────────

@router.post("/{model_id}/masts", response_model=MastRead, status_code=status.HTTP_201_CREATED)
async def add_mast(
    model_id: uuid.UUID,
    data: MastCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """Añade un fuste con todos sus componentes al modelo geométrico."""
    svc = GeometryService(db)
    mast = await svc.add_mast(str(model_id), data, _primary_role(current_roles))
    await db.commit()
    await db.refresh(mast)
    return MastRead.model_validate(mast)


@router.get("/{model_id}/masts", response_model=list[MastRead])
async def list_masts(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Mast).where(Mast.geometry_model_id == str(model_id)))
    return [MastRead.model_validate(m) for m in result.scalars().all()]


# ── Validate ───────────────────────────────────────────────────────────────────

@router.post("/{model_id}/validate", response_model=ValidationSummary)
async def validate_geometry(
    model_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Ejecuta las reglas GEO-001..GEO-012 y actualiza quality_state.
    Cada ejecución crea registros inmutables en geometry_validations.
    """
    svc = GeometryService(db)
    summary = await svc.validate(str(model_id))
    await db.commit()
    return summary


@router.get("/{model_id}/validations", response_model=list[GeometryValidationRead])
async def list_validations(
    model_id: uuid.UUID,
    rule_code: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    q = select(GeometryValidation).where(GeometryValidation.geometry_model_id == str(model_id))
    if rule_code:
        q = q.where(GeometryValidation.rule_code == rule_code)
    result = await db.execute(q)
    return [GeometryValidationRead.model_validate(v) for v in result.scalars().all()]


# ── Derive / sections ──────────────────────────────────────────────────────────

@router.post("/{model_id}/derive", response_model=GeometryModelRead)
async def derive_geometry(
    model_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Genera estaciones y propiedades derivadas (áreas, inercias, masas, CG).
    Recalcula el geometry_hash. Determinista: misma entrada = mismo resultado.
    """
    result = await db.execute(select(GeometryModel).where(GeometryModel.id == str(model_id)))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo geométrico no encontrado")

    svc = GeometryService(db)
    new_hash = await svc._compute_hash(str(model_id))
    model.geometry_hash = new_hash

    await db.commit()
    await db.refresh(model)
    return GeometryModelRead.model_validate(model)


@router.get("/{model_id}/sections", response_model=SectionAtZResponse)
async def get_section_at_z(
    model_id: uuid.UUID,
    z: float = Query(..., description="Cota en metros sobre G0"),
    db: AsyncSession = Depends(get_db),
):
    """Consulta la sección exacta en la cota z_m. Determinista."""
    svc = GeometryService(db)
    return await svc.derive_section_at_z(str(model_id), z)


# ── Artifacts ──────────────────────────────────────────────────────────────────

@router.post("/{model_id}/artifacts", response_model=GeometryArtifactRead, status_code=status.HTTP_202_ACCEPTED)
async def generate_artifact(
    model_id: uuid.UUID,
    data: ArtifactGenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Crea un job asíncrono para generar un artefacto geométrico (STEP, DXF, glTF, etc.).
    El artefacto queda OBSOLETE si el geometry_hash cambia (AC-14).
    """
    result = await db.execute(select(GeometryModel).where(GeometryModel.id == str(model_id)))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo geométrico no encontrado")

    from app.models.db.geometry import GeometryArtifact, GeometryArtifactStatus
    artifact = GeometryArtifact(
        id=str(uuid.uuid4()),
        geometry_model_id=str(model_id),
        geometry_hash=model.geometry_hash or "pending",
        artifact_format=data.artifact_format,
        lod=data.lod,
        status=GeometryArtifactStatus.GENERATING,
        generator_version="2.0.0-preliminary",
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return GeometryArtifactRead.model_validate(artifact)


@router.get("/{model_id}/artifacts", response_model=list[GeometryArtifactRead])
async def list_artifacts(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeometryArtifact).where(GeometryArtifact.geometry_model_id == str(model_id))
    )
    return [GeometryArtifactRead.model_validate(a) for a in result.scalars().all()]


# ── Clone & Compare ────────────────────────────────────────────────────────────

@router.post("/{model_id}/clone", response_model=GeometryModelRead, status_code=status.HTTP_201_CREATED)
async def clone_geometry_model(
    model_id: uuid.UUID,
    data: GeometryCloneRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """Clona el modelo geométrico. AC-16: nuevo UUID, trazabilidad de origen."""
    svc = GeometryService(db)
    cloned = await svc.clone_geometry_model(
        str(model_id),
        str(data.target_revision_id) if data.target_revision_id else None,
        _primary_role(current_roles),
    )
    await db.commit()
    await db.refresh(cloned)
    return GeometryModelRead.model_validate(cloned)


@router.post("/{model_id}/compare", response_model=GeometryCompareResponse)
async def compare_geometry_models(
    model_id: uuid.UUID,
    other_model_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Compara dos modelos geométricos por geometry_hash.
    AC-17: mismo hash = geométricamente idénticos.
    """
    svc = GeometryService(db)
    result = await svc.compare_models(str(model_id), str(other_model_id))
    return GeometryCompareResponse(**result)
