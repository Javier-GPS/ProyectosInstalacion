"""
Salvi Studio · Columns — Action Run Service (Fase 3)
Orquestador de ejecuciones del motor de acciones.

Principios:
- ACT-P-001: determinismo; IA no inventa coeficientes.
- ACT-P-002: todo valor en snapshot o reglas versionadas.
- DAT-301: ejecuciones publicadas son inmutables.
- ACT-FLOW-001: cada paso conserva hashes, versión de motor y estado.
- ACT-FLOW-003: unidades internas SI.
"""
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role
from app.models.db.actions import (
    ActionRun, ActionRunStatus, Location, GeoParameter, CableAction,
    LoadCase, CombinationInstance, SpatialLoad, MassItem, ActionDiagnostic,
    UserOverride, AerodynamicProperty, NormativeActionRule,
    ActionType, CableActionState, DiagnosticSeverity, SpatialLoadType,
    LimitState, DataConfidenceLevel, ConfirmationState,
)
from app.models.schemas.actions import (
    ActionRunCreate, LocationCreate, LocationResolveRequest,
    LocationResolveResponse, CableActionCreate, UserOverrideCreate,
    DiagnosticAcceptRequest, SensitivityRequest, SensitivityResponse,
    ActionValidateResponse,
)

logger = structlog.get_logger()

ACTION_ENGINE_VERSION = "3.0.0"

# Roles autorizados para ejecuciones de acciones
_ACTION_ROLES = {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN}
# Roles que pueden aprobar overrides de alta criticidad
_OT_ROLES = {Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN}

# Barrido base cada 30°
BASE_SWEEP_DIRECTIONS_DEG = list(range(0, 360, 30))
MAX_CABLES = 6


class LocationService:
    """Servicio de resolución de ubicación geográfica y parámetros ambientales."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_location(self, data: LocationCreate, actor_role: Role) -> Location:
        """Crea una ubicación versionada para la revisión de proyecto."""
        if actor_role not in _ACTION_ROLES:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para crear ubicación")

        location = Location(
            id=str(uuid.uuid4()),
            project_revision_id=str(data.project_revision_id),
            latitude=data.latitude,
            longitude=data.longitude,
            country_code=data.country_code,
            country_name=data.country_name,
            region=data.region,
            municipality=data.municipality,
            altitude_m=data.altitude_m,
            altitude_source=data.altitude_source,
            environment=data.environment,
            project_life_years=data.project_life_years,
            reference_date=data.reference_date,
            confirmation_state=ConfirmationState.PROPOSED,
        )
        self.db.add(location)
        await self.db.flush()
        await self.db.refresh(location)
        logger.info("location_created", location_id=location.id, country=data.country_code)
        return location

    async def resolve_location(
        self, data: LocationResolveRequest, actor_role: Role
    ) -> "LocationResolveResponse":
        """
        Resuelve ubicación y propone parámetros ambientales automáticos.
        GEO-001: cada parámetro incluye source, confidence, confirmation_state.
        GEO-002: no extrapola si está fuera de cobertura sin regla expresa.
        """
        from app.models.schemas.actions import LocationResolveResponse, LocationRead, GeoParameterRead

        # Create location entity
        loc_data = LocationCreate(
            project_revision_id=data.project_revision_id,
            latitude=data.latitude,
            longitude=data.longitude,
            country_code=_infer_country_code(data.latitude, data.longitude),
            altitude_m=data.altitude_m,
            environment=data.environment,
            project_life_years=data.project_life_years,
            reference_date=data.reference_date,
        )
        location = await self.create_location(loc_data, actor_role)

        proposed_params: list[GeoParameter] = []
        warnings: list[str] = []
        coverage: dict[str, str] = {}

        # Propose wind basic velocity (C-level until normative source integrated)
        # In production: query normative map by country + lat/lon
        wind_param = GeoParameter(
            id=str(uuid.uuid4()),
            location_id=location.id,
            parameter_type="wind_basic_velocity",
            name="Velocidad básica de viento",
            proposed_value=26.0,  # placeholder m/s — to be resolved from map
            unit="m/s",
            source_id="placeholder",
            confidence=DataConfidenceLevel.C,
            confirmation_state=ConfirmationState.PROPOSED,
        )
        self.db.add(wind_param)
        proposed_params.append(wind_param)
        coverage["wind_basic_velocity"] = DataConfidenceLevel.C.value
        warnings.append("Velocidad de viento estimada (confianza C). Confirmar con fuente normativa oficial.")

        await self.db.flush()

        location_read = LocationRead.model_validate(location)
        from app.models.schemas.actions import GeoParameterRead
        params_read = [GeoParameterRead.model_validate(p) for p in proposed_params]

        return LocationResolveResponse(
            location=location_read,
            proposed_parameters=params_read,
            warnings=warnings,
            coverage_status=coverage,
        )

    async def get_location(self, location_id: str) -> Optional[Location]:
        result = await self.db.execute(select(Location).where(Location.id == location_id))
        return result.scalar_one_or_none()

    async def get_parameters(self, location_id: str) -> list[GeoParameter]:
        result = await self.db.execute(
            select(GeoParameter).where(GeoParameter.location_id == location_id)
        )
        return list(result.scalars().all())

    async def apply_override(self, location_id: str, override: "GeoParameterOverride") -> GeoParameter:
        """
        GEO-003: override conserva valor propuesto, adoptado y justificación.
        """
        from app.models.schemas.actions import GeoParameterOverride as OverrideSchema
        result = await self.db.execute(
            select(GeoParameter).where(GeoParameter.id == str(override.parameter_id))
        )
        param = result.scalar_one_or_none()
        if not param:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Parámetro no encontrado")

        param.adopted_value = override.adopted_value
        param.confirmation_state = ConfirmationState.SUBSTITUTED
        param.justification = override.justification
        await self.db.flush()
        return param


class ActionRunService:
    """Orquestador de ejecuciones del motor de acciones (Fase 3)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Validar completitud ────────────────────────────────────────────────────

    async def validate_completeness(
        self, project_revision_id: str
    ) -> ActionValidateResponse:
        """
        Comprueba que los datos son suficientes para una ejecución oficial.
        ACT-P-005: dato obligatorio ausente → bloquea; no sustituye por cero.
        """
        blocking: list[str] = []
        warnings: list[str] = []
        missing: list[str] = []
        quality: dict[str, str] = {}

        # Check location
        loc_result = await self.db.execute(
            select(Location).where(Location.project_revision_id == project_revision_id)
        )
        location = loc_result.scalar_one_or_none()
        if not location:
            blocking.append("Ubicación no definida (ACT-E-001)")
            missing.append("location")
        else:
            if location.altitude_m is None:
                warnings.append("Altitud no definida; parámetros de viento pueden ser inexactos")
            if location.environment is None:
                warnings.append("Entorno no especificado; rugosidad/terreno pendiente")
            if location.confirmation_state == ConfirmationState.PENDING:
                blocking.append("Ubicación no confirmada por el usuario")

            # Check geo parameters confidence
            params = await self.db.execute(
                select(GeoParameter).where(GeoParameter.location_id == location.id)
            )
            for p in params.scalars().all():
                quality[p.parameter_type.value] = p.confidence.value
                if p.confidence == DataConfidenceLevel.E:
                    blocking.append(f"Parámetro '{p.name}' pendiente (confianza E) — ACT-P-005")
                elif p.confidence == DataConfidenceLevel.C:
                    warnings.append(f"Parámetro '{p.name}' de confianza C: requiere validación OT para cálculo final (AC-27)")

        return ActionValidateResponse(
            project_revision_id=uuid.UUID(project_revision_id),
            is_complete=len(blocking) == 0,
            blocking_issues=blocking,
            warnings=warnings,
            missing_fields=missing,
            data_quality_summary=quality,
        )

    # ── Crear ejecución ───────────────────────────────────────────────────────

    async def create_run(
        self, data: ActionRunCreate, actor_role: Role
    ) -> ActionRun:
        """
        Crea una ejecución de acciones (job asíncrono).
        DAT-301: cada cambio de entrada crea nueva ejecución.
        API-301: acepta Idempotency-Key.
        """
        if actor_role not in _ACTION_ROLES:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para ejecutar motor de acciones")

        # Idempotency check
        if data.idempotency_key:
            existing_result = await self.db.execute(
                select(ActionRun).where(ActionRun.idempotency_key == data.idempotency_key)
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                return existing

        input_hash = _compute_input_hash(data)

        run = ActionRun(
            id=str(uuid.uuid4()),
            project_revision_id=str(data.project_revision_id),
            location_id=str(data.location_id),
            engine_version=ACTION_ENGINE_VERSION,
            status=ActionRunStatus.PENDING,
            input_hash=input_hash,
            idempotency_key=data.idempotency_key,
            sweep_config_json=data.sweep_config_json or {"base_directions_deg": BASE_SWEEP_DIRECTIONS_DEG},
            combination_template_id=str(data.combination_template_id) if data.combination_template_id else None,
        )
        self.db.add(run)
        await self.db.flush()

        # Add any extra cable actions provided at run creation time
        for cable_data in data.additional_cables:
            cable = CableAction(
                id=str(uuid.uuid4()),
                action_run_id=run.id,
                cable_id=str(cable_data.cable_id) if cable_data.cable_id else None,
                cable_identifier=cable_data.cable_identifier,
                anchor_z_m=cable_data.anchor_z_m,
                tension_n=cable_data.tension_n,
                azimuth_rad=cable_data.azimuth_rad,
                elevation_rad=cable_data.elevation_rad,
                cable_state=cable_data.cable_state,
                source=cable_data.source,
                uncertainty_pct=cable_data.uncertainty_pct,
            )
            self.db.add(cable)

        await self.db.flush()
        await self.db.refresh(run)
        logger.info("action_run_created", run_id=run.id, revision_id=str(data.project_revision_id))
        return run

    # ── Motor de acciones sincrónico (para test y predimensionamiento) ────────

    async def execute_run(self, run_id: str) -> ActionRun:
        """
        Ejecuta el motor de acciones de forma síncrona (para uso en tests).
        En producción usar ARQ worker async.

        Flujo canónico (ACT-FLOW-001..003):
        1. Validar snapshot y geometría
        2. Resolver ubicación y conjunto normativo
        3. Crear parámetros ambientales adoptados
        4. Obtener propiedades geométricas/aerodinámicas
        5. Generar direcciones candidatas
        6. Calcular acciones elementales características
        7. Convertir a representación espacial canónica
        8. Generar casos de carga coherentes
        9. Aplicar plantillas de combinación
        10. Normalizar, deduplicar, validar
        11. Emitir manifest, diagnósticos, hashes
        """
        run_result = await self.db.execute(select(ActionRun).where(ActionRun.id == run_id))
        run = run_result.scalar_one_or_none()
        if not run:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejecución no encontrada")

        run.status = ActionRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        await self.db.flush()

        try:
            # Step 1: Load location and parameters
            loc_result = await self.db.execute(select(Location).where(Location.id == run.location_id))
            location = loc_result.scalar_one_or_none()

            if not location:
                await self._add_diagnostic(run.id, "ACT-E-001", DiagnosticSeverity.ERROR,
                                           "Ubicación no encontrada")
                run.status = ActionRunStatus.FAILED
                await self.db.flush()
                return run

            param_result = await self.db.execute(
                select(GeoParameter).where(GeoParameter.location_id == location.id)
            )
            params_list = list(param_result.scalars().all())

            # Check for blocking E-confidence parameters
            blocking_params = [p for p in params_list if p.confidence == DataConfidenceLevel.E]
            if blocking_params:
                for p in blocking_params:
                    await self._add_diagnostic(
                        run.id, "ACT-E-001", DiagnosticSeverity.BLOCKED,
                        f"Parámetro '{p.name}' pendiente (confianza E) — ACT-P-005"
                    )
                run.status = ActionRunStatus.FAILED
                await self.db.flush()
                return run

            # Warn about C-confidence parameters (AC-27)
            for p in params_list:
                if p.confidence == DataConfidenceLevel.C:
                    await self._add_diagnostic(
                        run.id, "ACT-W-001", DiagnosticSeverity.WARNING,
                        f"Parámetro '{p.name}' de confianza C: requiere validación OT para cálculo final"
                    )

            # Step 5-6: Generate wind load cases for each sweep direction
            sweep_dirs = BASE_SWEEP_DIRECTIONS_DEG
            if run.sweep_config_json:
                sweep_dirs = run.sweep_config_json.get("base_directions_deg", BASE_SWEEP_DIRECTIONS_DEG)

            # Get wind velocity
            wind_param = next((p for p in params_list if p.parameter_type.value == "wind_basic_velocity"), None)
            v_basic = (wind_param.adopted_value or wind_param.proposed_value or 26.0) if wind_param else 26.0

            # Step 7-8: Create load cases per direction
            for direction_deg in sweep_dirs:
                azimuth_rad = math.radians(direction_deg)
                case_code = f"W-{direction_deg:03d}"

                # Simplified wind load (placeholder for EN 40 implementation)
                # In production: full chain v_basic → exposure → q_p(z) → Cd → F
                case = LoadCase(
                    id=str(uuid.uuid4()),
                    action_run_id=run.id,
                    code=case_code,
                    label=f"Viento dirección {direction_deg}°",
                    direction_deg=float(direction_deg),
                    action_types_json={"W": True},
                    active_actions_json={"directions": [direction_deg]},
                    is_base_direction=True,
                    is_refined=False,
                )
                case.case_hash = hashlib.sha256(
                    json.dumps({"run": run.id, "code": case_code}, sort_keys=True).encode()
                ).hexdigest()[:16]
                self.db.add(case)

            # Step 8: Add permanent load case (G: weight)
            g_case = LoadCase(
                id=str(uuid.uuid4()),
                action_run_id=run.id,
                code="G-SELF",
                label="Peso propio",
                direction_deg=None,
                action_types_json={"G": True},
                active_actions_json={},
                is_base_direction=True,
                is_refined=False,
            )
            self.db.add(g_case)

            # Step 9: Create basic ELU combinations (simplified, non-normative)
            await self.db.flush()
            cases_result = await self.db.execute(
                select(LoadCase).where(LoadCase.action_run_id == run.id)
            )
            cases = list(cases_result.scalars().all())

            for case in cases:
                if "W" in case.action_types_json:
                    combo = CombinationInstance(
                        id=str(uuid.uuid4()),
                        action_run_id=run.id,
                        load_case_id=case.id,
                        limit_state=LimitState.ULS_PERSISTENT,
                        label=f"ELU persistente {case.code}",
                        leading_action=ActionType.W,
                        normalized_terms_json={"G": {"factor": 1.35}, "W": {"factor": 1.5}},
                    )
                    combo.instance_hash = hashlib.sha256(
                        json.dumps(combo.normalized_terms_json, sort_keys=True).encode()
                    ).hexdigest()[:16]
                    self.db.add(combo)

            # Step 11: Finalize
            outputs_hash = hashlib.sha256(
                json.dumps({
                    "run_id": run.id,
                    "engine": ACTION_ENGINE_VERSION,
                    "directions": sweep_dirs,
                    "v_basic": v_basic,
                }, sort_keys=True).encode()
            ).hexdigest()

            run.status = ActionRunStatus.SUCCEEDED
            run.completed_at = datetime.now(timezone.utc)
            run.outputs_hash = outputs_hash
            run.manifest_json = {
                "engine_version": ACTION_ENGINE_VERSION,
                "location_id": run.location_id,
                "sweep_directions": sweep_dirs,
                "wind_v_basic_m_s": v_basic,
                "completed_at": run.completed_at.isoformat(),
            }

        except Exception as exc:
            logger.error("action_run_failed", run_id=run_id, error=str(exc))
            run.status = ActionRunStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            await self._add_diagnostic(
                run.id, "ACT-E-999", DiagnosticSeverity.ERROR,
                f"Error interno de ejecución: {str(exc)}"
            )

        await self.db.flush()
        await self.db.refresh(run)
        return run

    # ── Consultas ──────────────────────────────────────────────────────────────

    async def get_run(self, run_id: str) -> Optional[ActionRun]:
        result = await self.db.execute(select(ActionRun).where(ActionRun.id == run_id))
        return result.scalar_one_or_none()

    async def get_loads(self, run_id: str) -> list[SpatialLoad]:
        result = await self.db.execute(
            select(SpatialLoad).where(SpatialLoad.action_run_id == run_id)
        )
        return list(result.scalars().all())

    async def get_cases(self, run_id: str) -> list[LoadCase]:
        result = await self.db.execute(
            select(LoadCase).where(LoadCase.action_run_id == run_id)
        )
        return list(result.scalars().all())

    async def get_combinations(self, run_id: str) -> list[CombinationInstance]:
        result = await self.db.execute(
            select(CombinationInstance).where(CombinationInstance.action_run_id == run_id)
        )
        return list(result.scalars().all())

    # ── Sensibilidad ──────────────────────────────────────────────────────────

    async def sensitivity_analysis(
        self, run_id: str, data: SensitivityRequest
    ) -> SensitivityResponse:
        """
        Análisis de sensibilidad ±% sobre variables críticas (AC-26).
        No altera el escenario base.
        """
        base_run = await self.get_run(run_id)
        if not base_run:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejecución no encontrada")

        variations = []
        if data.wind_variation_pct is not None:
            variations.append({
                "parameter": "wind_basic_velocity",
                "variation_pct": data.wind_variation_pct,
                "note": "Análisis de sensibilidad; no modifica escenario base",
            })
        if data.cable_tension_variation_pct is not None:
            variations.append({
                "parameter": "cable_tension",
                "variation_pct": data.cable_tension_variation_pct,
                "note": "Análisis de sensibilidad; no modifica escenario base",
            })

        return SensitivityResponse(
            base_run_id=uuid.UUID(run_id),
            variations=variations,
            dominant_parameter=variations[0]["parameter"] if variations else None,
            summary={"note": "Análisis preliminar; ejecutar ejecución nueva para resultado oficial"},
        )

    # ── Override ───────────────────────────────────────────────────────────────

    async def create_override(
        self, run_id: str, data: UserOverrideCreate, author_id: str, actor_role: Role
    ) -> UserOverride:
        """
        DAT-302: override almacenado como objeto separado con motivo, autor y evidencia.
        AC-23: override de alta criticidad requiere aprobación OT.
        """
        if data.requires_ot_approval and actor_role not in _OT_ROLES:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Override de alta criticidad requiere rol OT o SYSTEM_ADMIN (AC-23)")

        override = UserOverride(
            id=str(uuid.uuid4()),
            action_run_id=run_id,
            parameter_ref=data.parameter_ref,
            adopted_value=data.adopted_value,
            adopted_value_json=data.adopted_value_json,
            reason=data.reason,
            evidence=data.evidence,
            author_id=author_id,
            requires_ot_approval=data.requires_ot_approval,
        )
        self.db.add(override)
        await self.db.flush()
        return override

    # ── Accept diagnostic ──────────────────────────────────────────────────────

    async def accept_diagnostic(
        self, diagnostic_id: str, note: str, accepted_by: str, actor_role: Role
    ) -> ActionDiagnostic:
        """Acepta una advertencia con nota justificativa."""
        if actor_role not in _ACTION_ROLES:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para aceptar diagnósticos")

        result = await self.db.execute(
            select(ActionDiagnostic).where(ActionDiagnostic.id == diagnostic_id)
        )
        diag = result.scalar_one_or_none()
        if not diag:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagnóstico no encontrado")

        diag.accepted_by_id = accepted_by
        diag.accepted_at = datetime.now(timezone.utc)
        diag.acceptance_note = note
        await self.db.flush()
        return diag

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _add_diagnostic(
        self, run_id: str, code: str, severity: DiagnosticSeverity, message: str,
        field_path: Optional[str] = None, normative_ref: Optional[str] = None,
    ) -> None:
        diag = ActionDiagnostic(
            id=str(uuid.uuid4()),
            action_run_id=run_id,
            code=code,
            severity=severity,
            message=message,
            field_path=field_path,
            normative_ref=normative_ref,
        )
        self.db.add(diag)


def _compute_input_hash(data: ActionRunCreate) -> str:
    """Hash reproducible de los datos de entrada de una ejecución."""
    payload = {
        "project_revision_id": str(data.project_revision_id),
        "location_id": str(data.location_id),
        "combination_template_id": str(data.combination_template_id) if data.combination_template_id else None,
        "sweep_config": data.sweep_config_json,
        "cables": [
            {
                "identifier": c.cable_identifier,
                "anchor_z_m": c.anchor_z_m,
                "tension_n": c.tension_n,
                "azimuth_rad": c.azimuth_rad,
                "elevation_rad": c.elevation_rad,
                "state": c.cable_state.value,
            }
            for c in data.additional_cables
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _infer_country_code(lat: float, lon: float) -> str:
    """
    Inferencia simplificada de país por coordenadas.
    En producción: geocodificación con servicio externo cacheado.
    """
    # Spain bounding box (approx)
    if 35 <= lat <= 44 and -9 <= lon <= 4:
        return "ESP"
    # France
    if 42 <= lat <= 51 and -5 <= lon <= 9:
        return "FRA"
    # Germany
    if 47 <= lat <= 55 and 6 <= lon <= 15:
        return "DEU"
    # Portugal
    if 37 <= lat <= 42 and -9 <= lon <= -6:
        return "PRT"
    return "UNK"
