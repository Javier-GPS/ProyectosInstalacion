"""
Salvi Studio · Columns — API v1: Acciones, Ubicación y Combinaciones (Fase 3)
v0.2

Endpoints para resolver ubicación, crear y ejecutar ejecuciones de acciones,
consultar cargas, combinaciones y diagnósticos.
"""
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_roles
from app.core.security import Role
from app.models.db.users import User
from app.models.db.actions import (
    ActionRun, Location, GeoParameter, CableAction, LoadCase,
    CombinationInstance, SpatialLoad, MassItem, ActionDiagnostic, UserOverride,
    ActionRunStatus,
)
from app.models.schemas.actions import (
    LocationCreate, LocationRead, LocationResolveRequest, LocationResolveResponse,
    GeoParameterRead, GeoParameterOverride,
    ActionRunCreate, ActionRunRead, ActionRunManifest,
    CableActionCreate, CableActionRead,
    LoadCaseRead, CombinationInstanceRead, SpatialLoadRead,
    MassItemRead, ActionDiagnosticRead, UserOverrideRead,
    DiagnosticAcceptRequest, UserOverrideCreate,
    SensitivityRequest, SensitivityResponse,
    ActionValidateResponse,
)
from app.services.action_run_service import LocationService, ActionRunService

router = APIRouter(tags=["actions"])


def _primary_role(roles: list[Role]) -> Role:
    priority = [
        Role.SYSTEM_ADMIN, Role.TECHNICAL_OFFICE, Role.ENGINEER,
        Role.LIBRARY_ADMIN, Role.COMMERCIAL, Role.AUDITOR, Role.SERVICE,
    ]
    for r in priority:
        if r in roles:
            return r
    return Role.AUDITOR


# ── Location ───────────────────────────────────────────────────────────────────

@router.post(
    "/locations/resolve",
    response_model=LocationResolveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Resolver ubicación y proponer parámetros ambientales",
)
async def resolve_location(
    data: LocationResolveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Geocodifica la ubicación, determina jurisdicción y propone parámetros.
    GEO-001: cada parámetro incluye source, confidence y confirmation_state.
    GEO-002: no extrapola fuera de cobertura sin regla expresa.
    Requiere confirmación del usuario antes de congelar (6.2 de la spec).
    """
    svc = LocationService(db)
    result = await svc.resolve_location(data, _primary_role(current_roles))
    await db.commit()
    return result


@router.get(
    "/locations/{location_id}",
    response_model=LocationRead,
)
async def get_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Location).where(Location.id == str(location_id)))
    loc = result.scalar_one_or_none()
    if not loc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ubicación no encontrada")
    return LocationRead.model_validate(loc)


@router.get(
    "/locations/{location_id}/parameters",
    response_model=list[GeoParameterRead],
    summary="Consultar parámetros geográficos y su calidad",
)
async def get_location_parameters(
    location_id: uuid.UUID,
    parameter_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve parámetros resueltos con nivel de confianza (A–E).
    Confianza E → bloquea cálculo oficial (ACT-P-005).
    """
    q = select(GeoParameter).where(GeoParameter.location_id == str(location_id))
    if parameter_type:
        q = q.where(GeoParameter.parameter_type == parameter_type)
    result = await db.execute(q)
    return [GeoParameterRead.model_validate(p) for p in result.scalars().all()]


@router.patch(
    "/locations/{location_id}/parameters/{parameter_id}",
    response_model=GeoParameterRead,
    summary="Sustituir parámetro geográfico (GEO-003)",
)
async def override_location_parameter(
    location_id: uuid.UUID,
    parameter_id: uuid.UUID,
    data: GeoParameterOverride,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """Override de parámetro — conserva propuesto, adoptado y justificación (GEO-003)."""
    svc = LocationService(db)
    param = await svc.apply_override(str(location_id), data)
    await db.commit()
    await db.refresh(param)
    return GeoParameterRead.model_validate(param)


# ── Action runs ────────────────────────────────────────────────────────────────

@router.post(
    "/scenarios/{scenario_id}/actions/validate",
    response_model=ActionValidateResponse,
    summary="Validar completitud de datos para cálculo oficial",
)
async def validate_actions(
    scenario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Comprueba datos necesarios para ejecución oficial.
    ACT-P-005: dato obligatorio ausente bloquea; no sustituye por cero.
    Confianza C → advertencia, requiere validación OT para cálculo final (AC-27).
    """
    svc = ActionRunService(db)
    return await svc.validate_completeness(str(scenario_id))


@router.post(
    "/scenarios/{scenario_id}/actions/runs",
    response_model=ActionRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear ejecución del motor de acciones",
)
async def create_action_run(
    scenario_id: uuid.UUID,
    data: ActionRunCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Crea una ejecución de acciones (job asíncrono).
    API-301: acepta Idempotency-Key.
    DAT-301: cambio en entradas = nueva ejecución; no edita ejecuciones publicadas.
    ACT-FLOW-001: cada paso conserva hashes y versión de motor.
    """
    svc = ActionRunService(db)
    run = await svc.create_run(data, _primary_role(current_roles))
    await db.commit()
    await db.refresh(run)
    return ActionRunRead.model_validate(run)


@router.get(
    "/action-runs/{run_id}",
    response_model=ActionRunRead,
    summary="Estado y manifest de la ejecución",
)
async def get_action_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = ActionRunService(db)
    run = await svc.get_run(str(run_id))
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejecución no encontrada")
    return ActionRunRead.model_validate(run)


@router.get(
    "/action-runs/{run_id}/manifest",
    response_model=ActionRunManifest,
    summary="Manifest completo de la ejecución (DAT-303)",
)
async def get_action_run_manifest(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Manifest con todas las entradas, versiones, hashes y resultados.
    DAT-303: bibliotecas referenciadas resueltas a versiones exactas.
    AC-24: exportación contiene todas las versiones y fuentes.
    """
    svc = ActionRunService(db)
    run = await svc.get_run(str(run_id))
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejecución no encontrada")

    run_read = ActionRunRead.model_validate(run)

    cables = await svc.get_loads(str(run_id))  # placeholder
    cases = await svc.get_cases(str(run_id))
    combos = await svc.get_combinations(str(run_id))

    diag_result = await db.execute(
        select(ActionDiagnostic).where(ActionDiagnostic.action_run_id == str(run_id))
    )
    overrides_result = await db.execute(
        select(UserOverride).where(UserOverride.action_run_id == str(run_id))
    )

    return ActionRunManifest(
        action_run=run_read,
        load_cases=[LoadCaseRead.model_validate(c) for c in cases],
        combination_instances=[CombinationInstanceRead.model_validate(c) for c in combos],
        diagnostics=[ActionDiagnosticRead.model_validate(d) for d in diag_result.scalars().all()],
        user_overrides=[UserOverrideRead.model_validate(o) for o in overrides_result.scalars().all()],
        summary=run.manifest_json or {},
    )


@router.get(
    "/action-runs/{run_id}/loads",
    response_model=list[SpatialLoadRead],
    summary="Cargas espaciales de la ejecución",
)
async def get_action_run_loads(
    run_id: uuid.UUID,
    load_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    LOD-001: resultantes reconciliadas con resultantes físicas.
    LOD-002: transformación global-local validada por invariantes.
    """
    q = select(SpatialLoad).where(SpatialLoad.action_run_id == str(run_id))
    if load_type:
        q = q.where(SpatialLoad.load_type == load_type)
    result = await db.execute(q)
    return [SpatialLoadRead.model_validate(l) for l in result.scalars().all()]


@router.get(
    "/action-runs/{run_id}/cases",
    response_model=list[LoadCaseRead],
    summary="Casos de carga",
)
async def get_action_run_cases(
    run_id: uuid.UUID,
    direction_deg: Optional[float] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    DIR-002: la envolvente conserva el identificador del caso y dirección
    que produce cada máximo o mínimo.
    """
    svc = ActionRunService(db)
    cases = await svc.get_cases(str(run_id))
    if direction_deg is not None:
        cases = [c for c in cases if c.direction_deg == direction_deg]
    return [LoadCaseRead.model_validate(c) for c in cases]


@router.get(
    "/action-runs/{run_id}/combinations",
    response_model=list[CombinationInstanceRead],
    summary="Combinaciones ELU/ELS/fatiga",
)
async def get_action_run_combinations(
    run_id: uuid.UUID,
    limit_state: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    COM-005: sin duplicados algebraicamente equivalentes.
    COM-001..004: factores parciales, exclusiones y grupos de estado.
    """
    svc = ActionRunService(db)
    combos = await svc.get_combinations(str(run_id))
    if limit_state:
        combos = [c for c in combos if c.limit_state.value == limit_state]
    return [CombinationInstanceRead.model_validate(c) for c in combos]


@router.post(
    "/action-runs/{run_id}/sensitivity",
    response_model=SensitivityResponse,
    summary="Análisis de sensibilidad ±% (AC-26)",
)
async def sensitivity_analysis(
    run_id: uuid.UUID,
    data: SensitivityRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    Análisis de sensibilidad sobre variables críticas sin alterar el escenario base.
    AC-26: variación de ±10% actualiza resultados sin cambiar el escenario oficial.
    """
    svc = ActionRunService(db)
    return await svc.sensitivity_analysis(str(run_id), data)


# ── Cables ─────────────────────────────────────────────────────────────────────

@router.post(
    "/scenarios/{scenario_id}/cables",
    response_model=CableActionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear/actualizar cable en revisión editable",
)
async def create_cable(
    scenario_id: uuid.UUID,
    data: CableActionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    CAT-001: azimut numérico obligatorio.
    CAT-002: tensión como valor característico positivo.
    CAT-003: rotura accidental = estado de escenario.
    """
    # Find latest non-published run for this scenario or create a standalone cable record
    # For now, create a cable action linked to the scenario directly
    from app.models.db.actions import CableAction
    import hashlib, json

    cable = CableAction(
        id=str(uuid.uuid4()),
        action_run_id=str(scenario_id),  # will be linked to a run when created
        cable_id=str(data.cable_id) if data.cable_id else None,
        cable_identifier=data.cable_identifier,
        anchor_z_m=data.anchor_z_m,
        tension_n=data.tension_n,
        azimuth_rad=data.azimuth_rad,
        elevation_rad=data.elevation_rad,
        cable_state=data.cable_state,
        source=data.source,
        uncertainty_pct=data.uncertainty_pct,
    )

    # Compute force vector (CAT-010: sum shown in plan and elevation)
    import math
    fx = -data.tension_n * math.cos(data.elevation_rad) * math.cos(data.azimuth_rad)
    fy = -data.tension_n * math.cos(data.elevation_rad) * math.sin(data.azimuth_rad)
    fz = -data.tension_n * math.sin(data.elevation_rad)
    cable.force_vector_json = {"Fx_N": fx, "Fy_N": fy, "Fz_N": fz}

    db.add(cable)
    await db.commit()
    await db.refresh(cable)
    return CableActionRead.model_validate(cable)


# ── Diagnostics & Overrides ────────────────────────────────────────────────────

@router.get(
    "/action-runs/{run_id}/diagnostics",
    response_model=list[ActionDiagnosticRead],
)
async def get_diagnostics(
    run_id: uuid.UUID,
    severity: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ActionDiagnostic).where(ActionDiagnostic.action_run_id == str(run_id))
    if severity:
        q = q.where(ActionDiagnostic.severity == severity)
    result = await db.execute(q)
    return [ActionDiagnosticRead.model_validate(d) for d in result.scalars().all()]


@router.post(
    "/action-runs/{run_id}/diagnostics/{diagnostic_id}/accept",
    response_model=ActionDiagnosticRead,
    summary="Aceptar advertencia con justificación (AC-23)",
)
async def accept_diagnostic(
    run_id: uuid.UUID,
    diagnostic_id: uuid.UUID,
    data: DiagnosticAcceptRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """AC-23: usuario comercial no puede aprobar override de alta criticidad."""
    svc = ActionRunService(db)
    diag = await svc.accept_diagnostic(
        str(diagnostic_id),
        data.acceptance_note,
        str(current_user.id),
        _primary_role(current_roles),
    )
    await db.commit()
    await db.refresh(diag)
    return ActionDiagnosticRead.model_validate(diag)


@router.post(
    "/action-runs/{run_id}/overrides",
    response_model=UserOverrideRead,
    status_code=status.HTTP_201_CREATED,
    summary="Override de parámetro de cálculo (DAT-302)",
)
async def create_override(
    run_id: uuid.UUID,
    data: UserOverrideCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    current_roles: Annotated[list[Role], Depends(get_current_roles)],
    db: AsyncSession = Depends(get_db),
):
    """
    DAT-302: override almacenado como objeto separado con motivo, autor y evidencia.
    AC-23: alta criticidad requiere aprobación OT.
    """
    svc = ActionRunService(db)
    override = await svc.create_override(
        str(run_id), data, str(current_user.id), _primary_role(current_roles)
    )
    await db.commit()
    await db.refresh(override)
    return UserOverrideRead.model_validate(override)


@router.get(
    "/action-runs/{run_id}/overrides",
    response_model=list[UserOverrideRead],
)
async def list_overrides(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserOverride).where(UserOverride.action_run_id == str(run_id))
    )
    return [UserOverrideRead.model_validate(o) for o in result.scalars().all()]
