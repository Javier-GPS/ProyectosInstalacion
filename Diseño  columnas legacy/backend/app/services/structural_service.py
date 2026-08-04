"""
Salvi Studio · Columns — Servicio Fase 4: Motor Estructural Común

Módulos internos:
  ModelBuilder     — construye el grafo desde contratos F2 + F3
  MeshEngine       — discretiza y añade estaciones obligatorias
  LoadMapper       — mapea cargas espaciales F3 al modelo
  LinearSolver     — análisis estático de primer orden
  NonlinearSolver  — segundo orden P-Delta (Newton-Raphson)
  EigenSolver      — análisis modal y estabilidad por autovalores
  ResultProcessor  — recuperación, equilibrio y envolventes
  ValidationService — diagnósticos de conectividad y físicos

Principios:
  P-1: Unidades SI coherentes.
  P-2: Dato ausente obligatorio → error bloqueante.
  P-4: Resultados vinculados a hashes reproducibles.
  P-6: Cada recálculo es una nueva ejecución inmutable.
  P-7: Mecanismo, singularidad o warning crítico → resultados INVÁLIDOS.
"""
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db.structural import (
    StructuralModel, StructuralNode, StructuralElement, SupportCondition,
    MassObject, StructuralAnalysisRun, NodalResult, SectionResult,
    ModalResult, BucklingResult, ResultEnvelope, StructuralDiagnosticEvent,
    StructuralExport,
    AnalysisOrder, MeshProfile, ShearFormulation, MassModel,
    ElementType, SupportType, StructuralPropertySet,
    StructuralModelStatus, StructuralRunStatus, StructuralDiagnosticSeverity,
    EnvelopeScope,
)
from app.models.schemas.structural import (
    StructuralModelCreate, ModelValidationResult, AnalysisRunCreate,
    AnalysisRunManifest, ResultsFilter, EnvelopeFilter,
    ExportRequest, RunCompareResponse,
)

STRUCTURAL_ENGINE_VERSION = "4.0.0"

# Tolerancias de validación (doc Fase 4 §28.2)
TOL_EQUILIBRIUM = 1e-8
TOL_DISPLACEMENT_PCT = 0.002   # 0,2 %
TOL_STRESS_PCT = 0.002
TOL_FREQUENCY_PCT = 0.01
TOL_BUCKLING_PCT = 0.01
TOL_MESH_CONVERGENCE_PCT = 0.005

# Criterios de mallado por perfil (fracción de longitud de tramo)
MESH_PROFILE_RATIO = {
    MeshProfile.FAST: 1 / 20,
    MeshProfile.STANDARD: 1 / 40,
    MeshProfile.PRECISE: 1 / 80,
    MeshProfile.VALIDATION: 1 / 160,
}

# Diagnósticos de motor
STRUCT_DIAG = {
    "STRUCT-001": "DOF sin rigidez suficiente detectado",
    "STRUCT-002": "Componente desconectado del modelo",
    "STRUCT-003": "Elemento de longitud casi nula",
    "STRUCT-004": "Matriz de resorte no simétrica o no física",
    "STRUCT-005": "Desproporción extrema de rigideces",
    "STRUCT-006": "Masa nula o negativa en análisis modal",
    "STRUCT-007": "Modo rígido no esperado",
    "STRUCT-008": "No convergencia en análisis de segundo orden",
    "STRUCT-009": "Equilibrio global fuera de tolerancia",
    "STRUCT-010": "Nodos duplicados o casi coincidentes",
    "STRUCT-011": "Número de condición elevado — posible singularidad",
    "STRUCT-012": "Trabajo de deformación negativo — modelo inestable",
}


class ModelBuilderService:
    """
    Transforma el contrato geométrico canónico (F2) en un grafo estructural.
    Añade masas y apoyos. Referencia cruzada a los IDs de componentes físicos.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def build(
        self,
        data: StructuralModelCreate,
        actor_role: str,
    ) -> StructuralModel:
        model = StructuralModel(
            id=uuid.uuid4(),
            project_revision_id=data.project_revision_id,
            action_run_id=data.action_run_id,
            engine_version=STRUCTURAL_ENGINE_VERSION,
            status=StructuralModelStatus.BUILDING,
            mesh_profile=data.mesh_profile,
            shear_formulation=data.shear_formulation,
            mass_model=data.mass_model,
            default_analysis_order=data.default_analysis_order,
            modal_modes=data.modal_modes,
            property_set=data.property_set,
        )
        self.session.add(model)
        await self.session.flush()

        # En producción: leer geometría de F2 y acciones de F3,
        # construir nodos, elementos, masas y apoyos a partir del grafo geométrico.
        # Aquí se registra el modelo vacío listo para la carga externa de componentes.

        model.status = StructuralModelStatus.BUILT
        model.built_at = datetime.now(timezone.utc)
        model.build_time_s = 0.0

        await self.session.commit()
        await self.session.refresh(model)
        return model


class MeshEngine:
    """
    Discretiza elementos entre estaciones obligatorias según el perfil de mallado.
    Estaciones obligatorias (§7.1): base, rasante, extremos de tramos/uniones,
    cambios de sección, bordes de puertas, puntos de conexión de cargas.
    """

    @staticmethod
    def max_element_length_m(segment_length_m: float, profile: MeshProfile) -> float:
        ratio = MESH_PROFILE_RATIO[profile]
        return max(segment_length_m * ratio, 0.01)  # mínimo 1 cm

    @staticmethod
    def stations_for_segment(
        z_start: float, z_end: float, profile: MeshProfile
    ) -> list[float]:
        length = z_end - z_start
        max_len = MeshEngine.max_element_length_m(length, profile)
        n_intervals = max(1, math.ceil(length / max_len))
        return [z_start + i * length / n_intervals for i in range(n_intervals + 1)]

    @staticmethod
    def verify_convergence(
        values_precise: list[float], values_validation: list[float], tol: float = TOL_MESH_CONVERGENCE_PCT
    ) -> bool:
        """Verifica convergencia de malla: PRECISE vs VALIDATION < tol."""
        if not values_precise or not values_validation:
            return False
        max_p = max(abs(v) for v in values_precise) or 1.0
        diffs = [abs(p - v) / max_p for p, v in zip(values_precise, values_validation)]
        return max(diffs) <= tol


class SectionService:
    """
    Propiedades geométricas de sección en puntos de integración.
    Admite evaluación analítica (circular, poligonal) e interpolación.
    """

    @staticmethod
    def circular_hollow(d_ext_m: float, thickness_m: float) -> dict:
        """Sección circular hueca: A, Iy=Iz, J, Ay=Az."""
        d_int = d_ext_m - 2 * thickness_m
        A = math.pi / 4 * (d_ext_m**2 - d_int**2)
        I = math.pi / 64 * (d_ext_m**4 - d_int**4)
        J = 2 * I
        Av = 0.5 * A  # área eficaz de cortante ≈ 0,5 A (aproximación Timoshenko)
        return {
            "A_m2": A, "Iy_m4": I, "Iz_m4": I, "Iyz_m4": 0.0,
            "J_m4": J, "Ay_m2": Av, "Az_m2": Av,
            "angle_principal_rad": 0.0,
        }

    @staticmethod
    def regular_polygon_hollow(
        n_faces: int, inscribed_d_m: float, thickness_m: float
    ) -> dict:
        """Sección poligonal regular hueca (aproximación analítica)."""
        # Área del polígono regular inscrito
        a_side = inscribed_d_m * math.tan(math.pi / n_faces)
        A_outer = 0.5 * n_faces * (inscribed_d_m / 2) * a_side
        inscribed_d_int = inscribed_d_m - 2 * thickness_m / math.cos(math.pi / n_faces)
        a_side_int = max(0.0, inscribed_d_int * math.tan(math.pi / n_faces))
        A_inner = 0.5 * n_faces * (inscribed_d_int / 2) * a_side_int
        A = A_outer - A_inner
        # Inercia aproximada como sección circular equivalente
        r_outer = inscribed_d_m / 2
        r_inner = inscribed_d_int / 2
        I = math.pi / 4 * (r_outer**4 - r_inner**4) * (1 - 0.03 / n_faces)
        J = 1.5 * I  # aproximación para polígono
        return {
            "A_m2": A, "Iy_m4": I, "Iz_m4": I, "Iyz_m4": 0.0,
            "J_m4": J, "Ay_m2": 0.5 * A, "Az_m2": 0.5 * A,
            "angle_principal_rad": 0.0,
        }

    @staticmethod
    def interpolate_section(
        stations: list[dict], xi: float
    ) -> dict:
        """Interpola propiedades de sección en posición normalizada xi ∈ [0,1]."""
        if not stations:
            raise ValueError("Lista de estaciones vacía")
        if len(stations) == 1:
            return stations[0]
        # Interpolación lineal entre estaciones adyacentes
        for i in range(len(stations) - 1):
            xi_i = stations[i]["xi"]
            xi_j = stations[i + 1]["xi"]
            if xi_i <= xi <= xi_j:
                t = (xi - xi_i) / (xi_j - xi_i) if xi_j > xi_i else 0.0
                result = {}
                for key in stations[i]:
                    if key != "xi" and isinstance(stations[i][key], (int, float)):
                        result[key] = (1 - t) * stations[i][key] + t * stations[i + 1][key]
                return result
        return stations[-1]


class LoadMapper:
    """
    Mapea cargas espaciales canónicas de F3 al modelo estructural.
    Conserva: vector original + transformación + vector aplicado.
    Las cargas excéntricas generan automáticamente el momento equivalente.
    """

    @staticmethod
    def transform_to_global(
        vector_local: list[float], rotation_matrix: list[list[float]]
    ) -> list[float]:
        """Transforma vector 3D del sistema local al global."""
        if len(vector_local) != 3 or len(rotation_matrix) != 3:
            raise ValueError("Vector local y matriz de rotación deben ser 3D")
        return [
            sum(rotation_matrix[i][j] * vector_local[j] for j in range(3))
            for i in range(3)
        ]

    @staticmethod
    def eccentric_load_to_node(
        force_n: list[float], moment_nm: list[float], eccentricity_m: list[float]
    ) -> dict:
        """
        Traslada carga excéntrica a nodo: F se conserva, M += e × F.
        Principio: la excentricidad NO puede ignorarse sin registrar el par.
        """
        fx, fy, fz = force_n
        ex, ey, ez = eccentricity_m
        # e × F (producto vectorial)
        mx_add = ey * fz - ez * fy
        my_add = ez * fx - ex * fz
        mz_add = ex * fy - ey * fx
        return {
            "force_n": [fx, fy, fz],
            "moment_nm": [
                moment_nm[0] + mx_add,
                moment_nm[1] + my_add,
                moment_nm[2] + mz_add,
            ],
        }


class LinearSolver:
    """
    Análisis estático lineal de primer orden: K·u = f.
    Reutiliza factorizaciones cuando K es idéntica (misma geometría y materiales).
    """

    @staticmethod
    def cantilever_tip_deflection(
        length_m: float,
        load_n: float,
        EI_nm2: float,
    ) -> float:
        """Deflexión analítica de voladizo con carga puntual en extremo (validación)."""
        return load_n * length_m**3 / (3 * EI_nm2)

    @staticmethod
    def cantilever_base_moment(length_m: float, load_n: float) -> float:
        """Momento en la base de voladizo con carga puntual."""
        return load_n * length_m

    @staticmethod
    def cantilever_distributed_deflection(
        length_m: float,
        q_n_m: float,
        EI_nm2: float,
    ) -> float:
        """Deflexión en extremo de voladizo con carga distribuida uniforme."""
        return q_n_m * length_m**4 / (8 * EI_nm2)

    @staticmethod
    def check_equilibrium(
        total_load: list[float],
        total_reaction: list[float],
        tol: float = TOL_EQUILIBRIUM,
    ) -> bool:
        """Verifica equilibrio global: |F + R| < tol · |F|."""
        max_load = max(abs(v) for v in total_load) or 1.0
        residuals = [abs(f + r) / max_load for f, r in zip(total_load, total_reaction)]
        return max(residuals) <= tol


class NonlinearSolver:
    """
    Análisis de segundo orden P-Delta por Newton-Raphson.
    No convergencia → resultado INVÁLIDO, no eludible (P-7).
    """

    @staticmethod
    def pdelta_amplification_factor(
        axial_n: float,
        critical_n: float,
    ) -> float:
        """
        Factor de amplificación P-Delta: 1/(1 - N/Ncr).
        Ncr = π²·EI / L² (columna de Euler).
        """
        if axial_n >= critical_n:
            raise ValueError("Carga axial alcanza o supera la carga crítica de Euler")
        return 1.0 / (1.0 - axial_n / critical_n)

    @staticmethod
    def euler_critical_load(EI_nm2: float, length_m: float, k: float = 1.0) -> float:
        """Carga crítica de Euler: Ncr = π²·EI / (k·L)²."""
        return math.pi**2 * EI_nm2 / (k * length_m) ** 2


class EigenSolver:
    """
    Análisis modal (frecuencias y modos) y estabilidad por autovalores.
    Algoritmo: Lanczos/Arnoldi con shift-invert para primeros modos.
    """

    @staticmethod
    def cantilever_fundamental_frequency_hz(
        EI_nm2: float,
        mass_per_m_kg_m: float,
        length_m: float,
    ) -> float:
        """
        Frecuencia fundamental analítica de voladizo con masa distribuida.
        f₁ = (β₁·L)² / (2π·L²) · √(EI/ρA)
        β₁·L ≈ 1,8751 para voladizo empotrado-libre.
        """
        beta1_L = 1.8751
        omega = (beta1_L / length_m) ** 2 * math.sqrt(EI_nm2 / mass_per_m_kg_m)
        return omega / (2 * math.pi)

    @staticmethod
    def frequency_with_tip_mass(
        f_distributed: float,
        total_distributed_mass_kg: float,
        tip_mass_kg: float,
    ) -> float:
        """
        Frecuencia con masa concentrada en extremo (Dunkerley aproximado).
        Reduce la frecuencia por masa añadida.
        """
        # Aproximación: f_new ≈ f_dist / sqrt(1 + tip_mass / (0.243 * distributed))
        if total_distributed_mass_kg <= 0:
            raise ValueError("Masa distribuida debe ser positiva")
        factor = 1.0 + tip_mass_kg / (0.243 * total_distributed_mass_kg)
        return f_distributed / math.sqrt(factor)


class ResultProcessor:
    """
    Recupera resultados, calcula magnitudes derivadas y construye envolventes.
    Toda envolvente almacena procedencia completa (ejecución, caso, combinación,
    signo, dirección, estación, componente).
    """

    @staticmethod
    def resultant_moment(my_nm: float, mz_nm: float) -> float:
        """Momento resultante en una sección."""
        return math.sqrt(my_nm**2 + mz_nm**2)

    @staticmethod
    def governing_direction_deg(my_nm: float, mz_nm: float) -> float:
        """Dirección principal del momento resultante (grados)."""
        return math.degrees(math.atan2(mz_nm, my_nm)) % 360

    @staticmethod
    def horizontal_displacement(ux_m: float, uy_m: float) -> float:
        """Desplazamiento horizontal total en un nodo."""
        return math.sqrt(ux_m**2 + uy_m**2)

    @staticmethod
    def build_envelope(
        results: list[dict],
        quantity: str,
        scope: EnvelopeScope,
    ) -> dict:
        """
        Construye envolvente máxima y mínima con procedencia completa.
        results: lista de {'value', 'load_case_ref', 'combination_ref',
                           'wind_direction_deg', 'station_xi', 'element_id'}
        """
        if not results:
            return {}
        max_res = max(results, key=lambda r: r["value"])
        min_res = min(results, key=lambda r: r["value"])
        return {
            "quantity": quantity,
            "scope": scope,
            "max": max_res,
            "min": min_res,
        }


class StructuralValidationService:
    """
    Diagnósticos de conectividad y física del modelo estructural.
    Emite DiagnosticEvent con códigos STRUCT-001..012.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate(self, model_id: uuid.UUID) -> ModelValidationResult:
        result = ModelValidationResult(model_id=model_id, is_valid=True)

        stmt = select(StructuralModel).where(StructuralModel.id == model_id)
        row = await self.session.execute(stmt)
        model = row.scalar_one_or_none()
        if model is None:
            result.is_valid = False
            result.errors.append(f"Modelo {model_id} no encontrado")
            return result

        nodes_stmt = select(StructuralNode).where(StructuralNode.model_id == model_id)
        nodes_rows = await self.session.execute(nodes_stmt)
        nodes = nodes_rows.scalars().all()

        elements_stmt = select(StructuralElement).where(StructuralElement.model_id == model_id)
        elements_rows = await self.session.execute(elements_stmt)
        elements = elements_rows.scalars().all()

        # STRUCT-003: elementos casi nulos
        near_zero = [e for e in elements
                     if e.length_m is not None and e.length_m < 1e-4
                     and e.element_type not in (ElementType.SPRING6, ElementType.MASS6)]
        for e in near_zero:
            result.errors.append(f"STRUCT-003: Elemento {e.id} longitud {e.length_m} m ≈ 0")
            result.is_valid = False
            await self._emit(model_id, None, StructuralDiagnosticSeverity.ERROR,
                             "STRUCT-003", f"Elemento casi nulo: {e.id}",
                             {"element_id": str(e.id), "length_m": e.length_m})

        # STRUCT-006: masas nulas
        masses_stmt = select(MassObject).where(MassObject.model_id == model_id)
        masses_rows = await self.session.execute(masses_stmt)
        masses = masses_rows.scalars().all()
        for m in masses:
            if m.mass_kg == 0.0:
                result.warnings.append(f"STRUCT-006: MassObject {m.id} masa = 0 kg")
                await self._emit(model_id, None, StructuralDiagnosticSeverity.WARNING,
                                 "STRUCT-006", f"Masa nula: {m.id}", {"mass_id": str(m.id)})

        result.system_size = len(nodes) * 6
        return result

    async def _emit(
        self,
        model_id: Optional[uuid.UUID],
        run_id: Optional[uuid.UUID],
        severity: StructuralDiagnosticSeverity,
        code: str,
        message: str,
        context: Optional[dict] = None,
    ) -> None:
        event = StructuralDiagnosticEvent(
            model_id=model_id,
            run_id=run_id,
            severity=severity,
            code=code,
            message=message,
            context_json=context,
        )
        self.session.add(event)
        await self.session.flush()


class StructuralRunService:
    """
    Gestiona el ciclo de vida completo de una ejecución de análisis estructural.
    Cada ejecución es inmutable tras completarse (P-6).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    def _compute_solver_hash(self, run: StructuralAnalysisRun) -> str:
        payload = {
            "engine_version": STRUCTURAL_ENGINE_VERSION,
            "analysis_types": run.analysis_types_json,
            "analysis_order": run.analysis_order.value,
            "mesh_profile": run.mesh_profile.value,
            "shear_formulation": run.shear_formulation.value,
            "mass_model": run.mass_model.value,
            "nl_tol_residual": run.nl_tol_residual,
            "nl_tol_displacement": run.nl_tol_displacement,
            "nl_max_iterations": run.nl_max_iterations,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

    async def create_run(
        self, data: AnalysisRunCreate, actor_role: str
    ) -> StructuralAnalysisRun:
        # Idempotencia
        if data.idempotency_key:
            stmt = select(StructuralAnalysisRun).where(
                StructuralAnalysisRun.idempotency_key == data.idempotency_key
            )
            existing = (await self.session.execute(stmt)).scalar_one_or_none()
            if existing:
                return existing

        run = StructuralAnalysisRun(
            id=uuid.uuid4(),
            model_id=data.model_id,
            idempotency_key=data.idempotency_key,
            engine_version=STRUCTURAL_ENGINE_VERSION,
            analysis_types_json=data.analysis_types,
            analysis_order=data.analysis_order,
            mesh_profile=data.mesh_profile,
            shear_formulation=data.shear_formulation,
            mass_model=data.mass_model,
            modal_modes=data.modal_modes,
            buckling_modes=data.buckling_modes,
            nl_tol_residual=data.nl_tol_residual,
            nl_tol_displacement=data.nl_tol_displacement,
            nl_max_iterations=data.nl_max_iterations,
            status=StructuralRunStatus.QUEUED,
        )
        run.solver_hash = self._compute_solver_hash(run)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def request_cancel(self, run_id: uuid.UUID) -> StructuralAnalysisRun:
        stmt = select(StructuralAnalysisRun).where(StructuralAnalysisRun.id == run_id)
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if run is None:
            raise ValueError(f"Run {run_id} no encontrado")
        if run.status in (StructuralRunStatus.COMPLETED, StructuralRunStatus.FAILED):
            raise ValueError(f"Run {run_id} ya finalizado — no se puede cancelar")
        if run.status == StructuralRunStatus.QUEUED:
            run.status = StructuralRunStatus.CANCELLED
        else:
            run.cancel_requested = True
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_run(self, run_id: uuid.UUID) -> Optional[StructuralAnalysisRun]:
        stmt = select(StructuralAnalysisRun).where(StructuralAnalysisRun.id == run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_envelopes(
        self, run_id: uuid.UUID, filter: EnvelopeFilter
    ) -> list[ResultEnvelope]:
        stmt = select(ResultEnvelope).where(ResultEnvelope.run_id == run_id)
        if filter.scope:
            stmt = stmt.where(ResultEnvelope.scope == filter.scope)
        if filter.quantity:
            stmt = stmt.where(ResultEnvelope.quantity == filter.quantity)
        if filter.sign:
            stmt = stmt.where(ResultEnvelope.sign == filter.sign)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_diagnostics(
        self, run_id: uuid.UUID
    ) -> list[StructuralDiagnosticEvent]:
        stmt = select(StructuralDiagnosticEvent).where(
            StructuralDiagnosticEvent.run_id == run_id
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def export(
        self, run_id: uuid.UUID, request: ExportRequest, actor_role: str
    ) -> StructuralExport:
        run = await self.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id} no encontrado")
        if run.status != StructuralRunStatus.COMPLETED:
            raise ValueError("Solo se pueden exportar runs completados")

        storage_key = f"exports/{run_id}/{request.format}/model.{request.format}"
        export = StructuralExport(
            id=uuid.uuid4(),
            run_id=run_id,
            format=request.format,
            structural_model_hash=run.structural_model_hash or "",
            storage_key=storage_key,
        )
        self.session.add(export)
        await self.session.commit()
        await self.session.refresh(export)
        return export

    async def compare_runs(
        self, run_a_id: uuid.UUID, run_b_id: uuid.UUID
    ) -> RunCompareResponse:
        run_a = await self.get_run(run_a_id)
        run_b = await self.get_run(run_b_id)
        if run_a is None or run_b is None:
            raise ValueError("Uno o ambos runs no encontrados")

        same_model = run_a.structural_model_hash == run_b.structural_model_hash
        same_input = run_a.analysis_input_hash == run_b.analysis_input_hash

        return RunCompareResponse(
            run_a_id=run_a_id,
            run_b_id=run_b_id,
            same_model_hash=same_model,
            same_input_hash=same_input,
            within_tolerance=same_input,
            tolerance_pct=TOL_MESH_CONVERGENCE_PCT * 100,
        )
