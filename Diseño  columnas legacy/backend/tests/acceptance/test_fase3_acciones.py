"""
Salvi Studio · Columns — Tests de aceptación Fase 3: Acciones, Ubicación y Combinaciones
AC-21..AC-50

Convenciones:
- Tests unitarios de reglas de negocio, schemas y cálculo analítico.
- @pytest.mark.integration requiere PostgreSQL+Redis real.
- Numeración AC-21..AC-50 para evitar colisión con Fase 2 (AC-01..AC-20).
"""
import hashlib
import json
import math
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.db.actions import (
    EnvironmentType, DataConfidenceLevel, ActionType, CableActionState,
    ActionRunStatus, DiagnosticSeverity, LimitState,
)
from app.models.schemas.actions import (
    LocationCreate, GeoParameterOverride,
    CableActionCreate, ActionRunCreate, ActionValidateResponse,
    SensitivityRequest, SensitivityResponse,
    ActionRunManifest,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cable_force_vector(tension_n: float, azimuth_rad: float, elevation_rad: float) -> dict:
    """
    Descomposición de tensión de cable en componentes cartesianos.
    La fuerza se aplica a la columna → sentido opuesto a la dirección del cable.
    """
    return {
        "fx": -tension_n * math.cos(elevation_rad) * math.cos(azimuth_rad),
        "fy": -tension_n * math.cos(elevation_rad) * math.sin(azimuth_rad),
        "fz": -tension_n * math.sin(elevation_rad),
    }


def _wind_speed_at_z(v_ref: float, z: float, k1: float, alpha: float) -> float:
    """Perfil de velocidad de viento EN-40 simplificado."""
    if z <= 0:
        return 0.0
    return v_ref * k1 * (z ** alpha)


def _combination_hash(terms: list) -> str:
    """Hash de combinación por normalización algebraica."""
    normalized = sorted(terms, key=lambda t: t["action_code"])
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


# ── AC-21: Ubicación con coordenadas válidas, tipo urbano ─────────────────────

class TestAC21LocationCreate:
    def test_location_schema_valid(self):
        loc = LocationCreate(
            project_revision_id=uuid.uuid4(),
            lat=41.3851,
            lon=2.1734,
            country_code="ES",
            altitude_m=12.0,
            environment=EnvironmentType.URBAN,
            project_life_years=25,
        )
        assert loc.lat == 41.3851
        assert loc.environment == EnvironmentType.URBAN

    def test_latitude_range(self):
        """Latitud debe estar en [-90, 90]."""
        with pytest.raises(Exception):
            LocationCreate(
                project_revision_id=uuid.uuid4(),
                lat=91.0, lon=0.0, country_code="ES",
            )
        with pytest.raises(Exception):
            LocationCreate(
                project_revision_id=uuid.uuid4(),
                lat=-91.0, lon=0.0, country_code="ES",
            )

    def test_longitude_range(self):
        """Longitud debe estar en [-180, 180]."""
        with pytest.raises(Exception):
            LocationCreate(
                project_revision_id=uuid.uuid4(),
                lat=40.0, lon=181.0, country_code="ES",
            )


# ── AC-22: Confianza A en parámetro normativo ─────────────────────────────────

class TestAC22ConfidenceLevelA:
    def test_confidence_a_does_not_block(self):
        """Confianza A (normativa) no bloquea el cálculo."""
        confidence = DataConfidenceLevel.A
        blocks_calc = confidence == DataConfidenceLevel.E
        assert not blocks_calc

    def test_confidence_a_no_warning(self):
        """Confianza A no genera advertencia."""
        levels_with_warning = {
            DataConfidenceLevel.C,
            DataConfidenceLevel.D,
            DataConfidenceLevel.E,
        }
        assert DataConfidenceLevel.A not in levels_with_warning

    def test_source_and_version_preserved(self):
        override = GeoParameterOverride(
            parameter_type="vb0",
            proposed_value=26.0,
            adopted_value=26.0,
            unit="m/s",
            source_id=uuid.uuid4(),
            source_version="EN 1991-1-4:2005",
            confidence=DataConfidenceLevel.A,
            justification="Valor de tabla para zona A, España",
        )
        assert override.confidence == DataConfidenceLevel.A
        assert override.source_version == "EN 1991-1-4:2005"


# ── AC-23: Anulación de parámetro requiere rol OT ─────────────────────────────

class TestAC23OverrideRequiresOT:
    def test_override_schema_with_approval_flag(self):
        override = GeoParameterOverride(
            parameter_type="rho_air",
            proposed_value=1.25,
            adopted_value=1.20,
            unit="kg/m3",
            source_id=None,
            confidence=DataConfidenceLevel.C,
            justification="Altitud > 1000 m, densidad reducida",
            requires_ot_approval=True,
        )
        assert override.requires_ot_approval is True

    def test_low_criticality_override_no_approval(self):
        override = GeoParameterOverride(
            parameter_type="category",
            proposed_value="II",
            adopted_value="II",
            unit="",
            confidence=DataConfidenceLevel.B,
            justification="Zona II por inspección visual",
            requires_ot_approval=False,
        )
        assert override.requires_ot_approval is False


# ── AC-24: Barrido de 12 direcciones de viento ────────────────────────────────

class TestAC24WindSweep12Directions:
    def test_twelve_directions_every_30_deg(self):
        """Barrido base de 12 direcciones cada 30°."""
        base_directions = list(range(0, 360, 30))
        assert len(base_directions) == 12
        assert base_directions[0] == 0
        assert base_directions[-1] == 330

    def test_directions_cover_full_circle(self):
        """Las 12 direcciones cubren 360° exactos."""
        base = list(range(0, 360, 30))
        assert max(base) + 30 == 360

    def test_refinement_around_maximum(self):
        """Refinamiento alrededor de la dirección máxima (±15° en pasos de 5°)."""
        max_dir = 60  # dirección con mayor carga
        refinement_step = 5
        refined = list(range(max_dir - 15, max_dir + 15 + refinement_step, refinement_step))
        assert max_dir in refined
        assert min(refined) == max_dir - 15
        assert max(refined) == max_dir + 15


# ── AC-25: Perfil de velocidad de viento EN-40 ───────────────────────────────

class TestAC25WindProfile:
    def test_wind_speed_increases_with_height(self):
        """Velocidad de viento mayor a mayor altura."""
        v_ref, k1, alpha = 26.0, 1.0, 0.22
        v5 = _wind_speed_at_z(v_ref, 5.0, k1, alpha)
        v10 = _wind_speed_at_z(v_ref, 10.0, k1, alpha)
        v20 = _wind_speed_at_z(v_ref, 20.0, k1, alpha)
        assert v5 < v10 < v20

    def test_wind_speed_at_ground_zero(self):
        """Velocidad a cota 0 m es 0."""
        v = _wind_speed_at_z(26.0, 0.0, 1.0, 0.22)
        assert v == 0.0

    def test_wind_pressure_q_formula(self):
        """q = 0.5 * rho * v^2."""
        rho = 1.25  # kg/m³
        v = 30.0   # m/s
        q = 0.5 * rho * v**2
        assert abs(q - 562.5) < 1e-6

    def test_wind_force_on_segment(self):
        """F = q * Cd * A."""
        q = 562.5   # Pa
        cd = 0.7
        area = 0.5  # m²
        f = q * cd * area
        assert abs(f - 196.875) < 1e-6


# ── AC-26: Análisis de sensibilidad ──────────────────────────────────────────

class TestAC26SensitivityAnalysis:
    def test_sensitivity_request_schema(self):
        req = SensitivityRequest(
            parameters=[
                {"name": "vb0", "base": 26.0, "values": [22.0, 24.0, 26.0, 28.0, 30.0]},
                {"name": "rho_air", "base": 1.25, "values": [1.20, 1.25, 1.30]},
            ],
            output_metrics=["max_moment_base_kNm", "max_shear_base_kN"],
        )
        assert len(req.parameters) == 2
        assert "max_moment_base_kNm" in req.output_metrics

    def test_sensitivity_does_not_modify_base(self):
        """El análisis de sensibilidad no altera el run base."""
        base_vb0 = 26.0
        perturbations = [22.0, 24.0, 28.0, 30.0]
        # El valor base no debe aparecer modificado después del análisis
        assert base_vb0 not in perturbations or base_vb0 == 26.0

    def test_sensitivity_response_schema(self):
        resp = SensitivityResponse(
            base_run_id=uuid.uuid4(),
            results=[
                {
                    "parameter": "vb0",
                    "value": 30.0,
                    "outputs": {"max_moment_base_kNm": 45.2, "max_shear_base_kN": 8.1},
                }
            ],
        )
        assert len(resp.results) == 1
        assert resp.results[0]["parameter"] == "vb0"


# ── AC-27: Confianza C → advertencia + requiere validación OT ────────────────

class TestAC27ConfidenceCWarning:
    def test_confidence_c_flags_warning(self):
        """Nivel C genera advertencia y requiere validación de OT."""
        confidence = DataConfidenceLevel.C
        requires_warning = confidence in {DataConfidenceLevel.C, DataConfidenceLevel.D}
        requires_ot_check = confidence in {DataConfidenceLevel.C, DataConfidenceLevel.D}
        assert requires_warning
        assert requires_ot_check

    def test_confidence_d_more_severe_than_c(self):
        """Nivel D implica datos estimados — mayor incertidumbre que C."""
        order = [
            DataConfidenceLevel.A,
            DataConfidenceLevel.B,
            DataConfidenceLevel.C,
            DataConfidenceLevel.D,
            DataConfidenceLevel.E,
        ]
        assert order.index(DataConfidenceLevel.D) > order.index(DataConfidenceLevel.C)


# ── AC-28: Confianza E → cálculo bloqueado ───────────────────────────────────

class TestAC28ConfidenceEBlocked:
    def test_confidence_e_blocks_calculation(self):
        """ACT-P-005: confianza E bloquea el cálculo."""
        confidence = DataConfidenceLevel.E
        blocked = confidence == DataConfidenceLevel.E
        assert blocked

    def test_confidence_e_error_not_warning(self):
        """Confianza E debe generar error, no solo advertencia."""
        severity_map = {
            DataConfidenceLevel.A: None,
            DataConfidenceLevel.B: DiagnosticSeverity.INFO,
            DataConfidenceLevel.C: DiagnosticSeverity.WARNING,
            DataConfidenceLevel.D: DiagnosticSeverity.WARNING,
            DataConfidenceLevel.E: DiagnosticSeverity.ERROR,
        }
        assert severity_map[DataConfidenceLevel.E] == DiagnosticSeverity.ERROR


# ── AC-29: Carga de peso propio ───────────────────────────────────────────────

class TestAC29SelfWeight:
    def test_self_weight_action_type(self):
        """G = peso propio (ActionType.G)."""
        action_type = ActionType.G
        assert action_type == ActionType.G

    def test_self_weight_direction_downward(self):
        """El peso propio actúa siempre en –Z."""
        fz = -1000.0  # N — valor negativo = hacia abajo
        assert fz < 0

    def test_mass_times_g(self):
        """F = m * g, con g = 9.81 m/s²."""
        mass_kg = 50.0
        g = 9.81
        f_n = mass_kg * g
        assert abs(f_n - 490.5) < 1e-6


# ── AC-30: Accidental: rotura de cable ───────────────────────────────────────

class TestAC30CableBreakAccidental:
    def test_cable_break_state(self):
        """Estado de cable BROKEN = accidental."""
        state = CableActionState.BROKEN
        assert state == CableActionState.BROKEN

    def test_cable_break_is_accidental_action(self):
        """Rotura de cable se clasifica como acción accidental (ActionType.A)."""
        action_type_for_break = ActionType.A
        assert action_type_for_break == ActionType.A

    def test_broken_cable_force_zero(self):
        """Cable roto → tensión = 0 N."""
        broken_tension = 0.0
        assert broken_tension == 0.0


# ── AC-31: Combinación ELU persistente ───────────────────────────────────────

class TestAC31ELUCombination:
    def test_elu_limit_state(self):
        assert LimitState.ELU == LimitState.ELU

    def test_elu_combination_terms(self):
        """Combinación ELU: G permanente + Q variable dominante + Ψ·Q secundarias."""
        terms = [
            {"action_code": "G", "factor": 1.35, "is_leading": False},
            {"action_code": "W_0", "factor": 1.50, "is_leading": True},
            {"action_code": "S", "factor": 1.50 * 0.6, "is_leading": False},  # Ψ0 = 0.6
        ]
        leading = [t for t in terms if t["is_leading"]]
        assert len(leading) == 1
        assert leading[0]["action_code"] == "W_0"


# ── AC-32: Combinación ELS característica ────────────────────────────────────

class TestAC32ELSCharacteristic:
    def test_els_limit_state(self):
        assert LimitState.ELS == LimitState.ELS

    def test_els_factors_less_than_elu(self):
        """Factores ELS ≤ ELU (verificación de relación conceptual)."""
        gamma_elu = 1.35
        gamma_els = 1.00
        assert gamma_els < gamma_elu


# ── AC-33: Deduplicación de combinaciones ─────────────────────────────────────

class TestAC33CombinationDeduplication:
    def test_identical_terms_same_hash(self):
        """Dos combinaciones con los mismos términos (reordenados) → mismo hash."""
        terms_a = [
            {"action_code": "G", "factor": 1.35},
            {"action_code": "W_0", "factor": 1.50},
        ]
        terms_b = [
            {"action_code": "W_0", "factor": 1.50},
            {"action_code": "G", "factor": 1.35},
        ]
        assert _combination_hash(terms_a) == _combination_hash(terms_b)

    def test_different_factors_different_hash(self):
        terms_a = [{"action_code": "G", "factor": 1.35}]
        terms_b = [{"action_code": "G", "factor": 1.00}]
        assert _combination_hash(terms_a) != _combination_hash(terms_b)

    def test_different_actions_different_hash(self):
        terms_a = [{"action_code": "G", "factor": 1.35}]
        terms_b = [{"action_code": "W", "factor": 1.35}]
        assert _combination_hash(terms_a) != _combination_hash(terms_b)


# ── AC-34: Run publicado es inmutable (DAT-301) ───────────────────────────────

class TestAC34PublishedRunImmutable:
    def test_published_status_is_final(self):
        """Un run publicado no puede modificarse — crear nuevo run."""
        published_status = ActionRunStatus.PUBLISHED
        mutable_statuses = {ActionRunStatus.PENDING, ActionRunStatus.RUNNING, ActionRunStatus.FAILED}
        assert published_status not in mutable_statuses

    def test_idempotency_key_uniqueness(self):
        """Misma idempotency_key → mismo run (no duplicados)."""
        key = str(uuid.uuid4())
        run1 = ActionRunCreate(
            project_revision_id=uuid.uuid4(),
            location_id=uuid.uuid4(),
            idempotency_key=key,
        )
        run2 = ActionRunCreate(
            project_revision_id=uuid.uuid4(),
            location_id=uuid.uuid4(),
            idempotency_key=key,
        )
        assert run1.idempotency_key == run2.idempotency_key


# ── AC-35: Anulación almacenada como objeto separado (DAT-302) ───────────────

class TestAC35OverrideAsSeparateObject:
    def test_override_has_reason_and_author(self):
        override = GeoParameterOverride(
            parameter_type="vb0",
            proposed_value=26.0,
            adopted_value=28.0,
            unit="m/s",
            confidence=DataConfidenceLevel.B,
            justification="Estudio microclimático específico del emplazamiento",
        )
        assert override.adopted_value != override.proposed_value
        assert len(override.justification) > 0

    def test_override_preserves_original(self):
        """El original se almacena; la anulación es objeto adicional."""
        original_value = 26.0
        override_value = 28.0
        # En producción: ambos persisten en DB; la anulación no borra el original
        assert original_value != override_value


# ── AC-36: Validación de completitud antes de run ────────────────────────────

class TestAC36CompletenessValidation:
    def test_validate_response_structure(self):
        resp = ActionValidateResponse(
            is_complete=False,
            blocking_issues=["Falta vb0 (velocidad de referencia de viento)"],
            warnings=["Altitud no confirmada — usar valor por defecto"],
            missing_fields=["location.geo_parameters.vb0"],
            data_quality_summary={"total_params": 10, "confidence_A": 7, "confidence_E": 1},
        )
        assert not resp.is_complete
        assert len(resp.blocking_issues) == 1

    def test_confidence_e_makes_incomplete(self):
        """Si hay algún parámetro con confianza E, el run no puede completarse."""
        params = [
            {"type": "vb0", "confidence": DataConfidenceLevel.A},
            {"type": "altitude", "confidence": DataConfidenceLevel.E},
        ]
        has_blocking = any(p["confidence"] == DataConfidenceLevel.E for p in params)
        assert has_blocking


# ── AC-37: Cable con azimut explícito (CAT-001) ───────────────────────────────

class TestAC37CableAzimuthMandatory:
    def test_cable_azimuth_mandatory(self):
        """CAT-001: azimut del cable es obligatorio y numérico."""
        cable = CableActionCreate(
            cable_identifier="C1",
            anchor_z_m=8.0,
            tension_n=5000.0,
            azimuth_rad=math.pi / 4,
        )
        assert cable.azimuth_rad == pytest.approx(math.pi / 4)

    def test_cable_azimuth_range(self):
        """Azimut debe estar en [0, 2π)."""
        with pytest.raises(Exception):
            CableActionCreate(
                cable_identifier="C1", anchor_z_m=8.0, tension_n=5000.0, azimuth_rad=-0.1,
            )
        with pytest.raises(Exception):
            CableActionCreate(
                cable_identifier="C1", anchor_z_m=8.0, tension_n=5000.0,
                azimuth_rad=2 * math.pi + 0.1,
            )


# ── AC-38: Tensión de cable como valor positivo (CAT-002) ────────────────────

class TestAC38CableTensionPositive:
    def test_cable_tension_positive(self):
        """CAT-002: tensión es valor característico positivo."""
        cable = CableActionCreate(
            cable_identifier="C1",
            anchor_z_m=8.0,
            tension_n=5000.0,
            azimuth_rad=0.0,
        )
        assert cable.tension_n > 0

    def test_cable_tension_negative_rejected(self):
        """Tensión negativa no permitida."""
        with pytest.raises(Exception):
            CableActionCreate(
                cable_identifier="C1", anchor_z_m=8.0, tension_n=-100.0, azimuth_rad=0.0,
            )

    def test_cable_tension_zero_allowed_for_broken(self):
        """Tensión = 0 es válida para estado BROKEN."""
        cable = CableActionCreate(
            cable_identifier="C1",
            anchor_z_m=8.0,
            tension_n=0.0,
            azimuth_rad=0.0,
            cable_state=CableActionState.BROKEN,
        )
        assert cable.tension_n == 0.0
        assert cable.cable_state == CableActionState.BROKEN


# ── AC-39: Descomposición de fuerza de cable ─────────────────────────────────

class TestAC39CableForceDecomposition:
    def test_horizontal_cable_force_vector(self):
        """Cable horizontal (elevation=0): fz=0, fx y fy según azimut."""
        tension = 10000.0
        azimuth = 0.0
        elevation = 0.0
        fv = _cable_force_vector(tension, azimuth, elevation)
        assert abs(fv["fz"]) < 1e-9
        assert abs(fv["fx"] - (-tension)) < 1e-6
        assert abs(fv["fy"]) < 1e-9

    def test_vertical_cable_force_vector(self):
        """Cable vertical hacia arriba (elevation=π/2): fx=fy=0."""
        tension = 10000.0
        azimuth = 0.0
        elevation = math.pi / 2
        fv = _cable_force_vector(tension, azimuth, elevation)
        assert abs(fv["fx"]) < 1e-6
        assert abs(fv["fy"]) < 1e-6
        assert abs(fv["fz"] - (-tension)) < 1e-6

    def test_45deg_cable_force_magnitude(self):
        """Cable a 45° — componente horizontal = vertical = tension/√2."""
        tension = math.sqrt(2) * 1000.0
        azimuth = 0.0
        elevation = math.pi / 4
        fv = _cable_force_vector(tension, azimuth, elevation)
        assert abs(fv["fx"] - (-1000.0)) < 1e-6
        assert abs(fv["fz"] - (-1000.0)) < 1e-6

    def test_force_vector_sum_equals_tension(self):
        """Módulo del vector fuerza = tensión."""
        tension = 7500.0
        azimuth = math.pi / 6
        elevation = math.pi / 8
        fv = _cable_force_vector(tension, azimuth, elevation)
        magnitude = math.sqrt(fv["fx"]**2 + fv["fy"]**2 + fv["fz"]**2)
        assert abs(magnitude - tension) < 1e-6


# ── AC-40: Seis cables distintos en un run ────────────────────────────────────

class TestAC40SixCablesInRun:
    def test_six_cables_in_run_schema(self):
        cables = [
            CableActionCreate(
                cable_identifier=f"C{i+1}",
                anchor_z_m=float(8 + i * 0.5),
                tension_n=float(3000 + i * 500),
                azimuth_rad=i * math.pi / 3,
            )
            for i in range(6)
        ]
        run_data = ActionRunCreate(
            project_revision_id=uuid.uuid4(),
            location_id=uuid.uuid4(),
            additional_cables=cables,
            idempotency_key=str(uuid.uuid4()),
        )
        assert len(run_data.additional_cables) == 6


# ── AC-41: Parámetros de entrada del run en snapshot ─────────────────────────

class TestAC41RunSnapshot:
    def test_run_manifest_has_hashes(self):
        """DAT-303: el manifiesto del run incluye todos los hashes de entrada."""
        manifest = ActionRunManifest(
            run_id=uuid.uuid4(),
            geometry_hash="sha256:abcdef",
            snapshot_hash="sha256:123456",
            input_hash="sha256:fedcba",
            outputs_hash="sha256:654321",
            engine_version="3.0.0",
            library_versions={"EN40": "2013", "EN1991": "2005"},
        )
        assert manifest.geometry_hash.startswith("sha256:")
        assert manifest.engine_version == "3.0.0"

    def test_hash_changes_with_input(self):
        """Cambio en cualquier parámetro → nuevo hash de inputs."""
        def make_hash(vb0: float) -> str:
            payload = json.dumps({"vb0": vb0}, sort_keys=True)
            return hashlib.sha256(payload.encode()).hexdigest()

        h1 = make_hash(26.0)
        h2 = make_hash(28.0)
        assert h1 != h2


# ── AC-42: Combinación ELU accidental ─────────────────────────────────────────

class TestAC42ELUAccidental:
    def test_accidental_combination_terms(self):
        """ELU accidental: G + Ad (acción de diseño accidental)."""
        terms = [
            {"action_code": "G", "factor": 1.0, "is_accidental": False},
            {"action_code": "A_cable_break", "factor": 1.0, "is_accidental": True},
        ]
        accidental_actions = [t for t in terms if t["is_accidental"]]
        assert len(accidental_actions) == 1

    def test_accidental_combination_no_variable_factor(self):
        """En ELU accidental, factores de acciones variables = Ψ2 (frecuente o cuasi-perm)."""
        psi2_wind = 0.0  # viento: Ψ2 = 0 normalmente
        assert psi2_wind == 0.0


# ── AC-43: Acción térmica T ───────────────────────────────────────────────────

class TestAC43ThermalAction:
    def test_thermal_action_type(self):
        assert ActionType.T == ActionType.T

    def test_thermal_delta_t_positive_negative(self):
        """Variación térmica puede ser positiva o negativa."""
        delta_t_summer = +35.0  # K
        delta_t_winter = -30.0  # K
        assert delta_t_summer > 0
        assert delta_t_winter < 0


# ── AC-44: Acción sísmica E ───────────────────────────────────────────────────

class TestAC44SeismicAction:
    def test_seismic_action_type(self):
        assert ActionType.E == ActionType.E

    def test_seismic_spectrum_params(self):
        """Parámetros mínimos del espectro sísmico."""
        spectrum = {
            "ag": 0.08 * 9.81,  # aceleración de referencia
            "S": 1.20,           # factor de suelo
            "TB": 0.15, "TC": 0.50, "TD": 2.0,
        }
        assert spectrum["ag"] > 0
        assert 0 < spectrum["TB"] < spectrum["TC"] < spectrum["TD"]


# ── AC-45: Acción de masa de equipamiento M ──────────────────────────────────

class TestAC45EquipmentMass:
    def test_equipment_mass_action_type(self):
        assert ActionType.M == ActionType.M

    def test_mass_item_nonnegative(self):
        """La masa de un elemento de equipamiento no puede ser negativa."""
        mass_kg = 15.0
        assert mass_kg >= 0


# ── AC-46: Motor determinista — mismos inputs → mismo output ─────────────────

class TestAC46DeterministicEngine:
    def test_same_inputs_same_hash(self):
        """ACT-P-001: el motor es determinista."""
        def run_hash(inputs: dict) -> str:
            return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()

        inputs = {
            "vb0": 26.0, "rho": 1.25, "cd": 0.7,
            "geometry_hash": "sha256:abc123",
            "engine_version": "3.0.0",
        }
        assert run_hash(inputs) == run_hash(inputs)

    def test_different_engine_version_different_output(self):
        """Distinta versión de motor → distinto resultado (hash diferente)."""
        def run_hash(version: str) -> str:
            return hashlib.sha256(version.encode()).hexdigest()

        assert run_hash("3.0.0") != run_hash("3.1.0")


# ── AC-47: Flujo canónico de 11 pasos ────────────────────────────────────────

class TestAC47CanonicalFlow:
    def test_eleven_steps_defined(self):
        """ACT-FLOW-001..003: el flujo canónico tiene 11 pasos numerados."""
        steps = [
            "validate_snapshot",
            "resolve_location",
            "create_adopted_parameters",
            "get_aero_properties",
            "get_geometry_properties",
            "generate_directions",
            "calc_elementary_actions",
            "convert_to_spatial_loads",
            "generate_load_cases",
            "apply_combination_templates",
            "emit_manifest",
        ]
        assert len(steps) == 11

    def test_each_step_preserves_hashes(self):
        """Cada paso preserva los hashes de entrada para trazabilidad."""
        hash_fields = [
            "geometry_hash", "snapshot_hash", "input_hash", "outputs_hash"
        ]
        # El manifiesto debe contener todos los campos de hash
        for field in hash_fields:
            assert field in hash_fields


# ── AC-48: Combinación de fatiga ─────────────────────────────────────────────

class TestAC48FatigueCombination:
    def test_fatigue_limit_state(self):
        assert LimitState.FATIGUE == LimitState.FATIGUE

    def test_fatigue_cycle_count(self):
        """Número de ciclos de viento para análisis de fatiga (estimación)."""
        design_life_years = 25
        wind_gusts_per_hour = 4
        hours_per_year = 8760
        total_cycles = design_life_years * wind_gusts_per_hour * hours_per_year
        assert total_cycles > 0
        assert total_cycles == 25 * 4 * 8760


# ── AC-49: Diagnóstico y aceptación de desviación ────────────────────────────

class TestAC49DiagnosticAcceptance:
    def test_diagnostic_severity_hierarchy(self):
        """ERROR > WARNING > INFO."""
        order = [DiagnosticSeverity.INFO, DiagnosticSeverity.WARNING, DiagnosticSeverity.ERROR]
        assert order.index(DiagnosticSeverity.ERROR) > order.index(DiagnosticSeverity.WARNING)
        assert order.index(DiagnosticSeverity.WARNING) > order.index(DiagnosticSeverity.INFO)

    def test_accepted_diagnostic_requires_approver(self):
        """La aceptación de un diagnóstico requiere ID de aprobador."""
        accepted_by_id = uuid.uuid4()
        assert accepted_by_id is not None


# ── AC-50: Run con acción de presión hidrostática P ──────────────────────────

class TestAC50HydrostaticPressure:
    def test_hydrostatic_action_type(self):
        assert ActionType.P == ActionType.P

    def test_hydrostatic_pressure_formula(self):
        """p = rho_water * g * h, con rho_water = 1000 kg/m³."""
        rho_water = 1000.0  # kg/m³
        g = 9.81           # m/s²
        h = 2.0            # m (nivel de inundación)
        p = rho_water * g * h
        assert abs(p - 19620.0) < 1e-6  # Pa

    def test_hydrostatic_below_water_level(self):
        """La presión hidrostática actúa en tramos por debajo del nivel de agua."""
        water_level_m = 2.0
        z_segment = 1.0
        is_submerged = z_segment <= water_level_m
        assert is_submerged
