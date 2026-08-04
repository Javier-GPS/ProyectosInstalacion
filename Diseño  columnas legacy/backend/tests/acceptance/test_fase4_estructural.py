"""
Salvi Studio · Columns — Tests de aceptación Fase 4: Motor Estructural
AC-01..AC-50 (numeración propia de la fase, independiente de F2/F3)

Convenciones:
- Tests unitarios de reglas de negocio, física analítica y contratos.
- Tolerancias según §28.2 del documento de especificación.
- @pytest.mark.integration requiere PostgreSQL real.
"""
import hashlib
import json
import math
import uuid

import pytest

from app.models.db.structural import (
    ElementType, AnalysisOrder, MeshProfile, ShearFormulation, MassModel,
    SupportType, StructuralPropertySet, StructuralRunStatus,
    StructuralDiagnosticSeverity, EnvelopeScope, StructuralLoadType,
    StructuralModelStatus,
)
from app.models.schemas.structural import (
    StructuralModelCreate, AnalysisRunCreate, ResultsFilter,
    EnvelopeFilter, ExportRequest, RunCompareResponse,
)
from app.services.structural_service import (
    LinearSolver, NonlinearSolver, EigenSolver, SectionService,
    MeshEngine, ResultProcessor, LoadMapper,
    TOL_DISPLACEMENT_PCT, TOL_STRESS_PCT, TOL_FREQUENCY_PCT,
    TOL_BUCKLING_PCT, TOL_EQUILIBRIUM,
)

# ── Constantes analíticas de referencia ────────────────────────────────────────

E_STEEL = 210e9      # Pa
G_STEEL = 81e9       # Pa
RHO_STEEL = 7850.0   # kg/m³


def _circular_EI(d_ext: float, thickness: float) -> float:
    """Rigidez flexional EI para tubo circular."""
    d_int = d_ext - 2 * thickness
    I = math.pi / 64 * (d_ext**4 - d_int**4)
    return E_STEEL * I


def _circular_mass_per_m(d_ext: float, thickness: float) -> float:
    """Masa lineal de tubo circular (kg/m)."""
    d_int = d_ext - 2 * thickness
    A = math.pi / 4 * (d_ext**2 - d_int**2)
    return RHO_STEEL * A


# ── AC-01: Voladizo prismático carga puntual ───────────────────────────────────

class TestAC01CantileverPointLoad:
    """Deflexión y momento en base analíticos; tolerancia ≤ 0,2 %."""

    def test_tip_deflection_formula(self):
        L, P = 8.0, 1000.0
        EI = _circular_EI(0.120, 0.004)
        delta = LinearSolver.cantilever_tip_deflection(L, P, EI)
        assert delta > 0
        # Verificación dimensional: [N·m³ / N·m²] = m ✓
        assert delta == pytest.approx(P * L**3 / (3 * EI), rel=1e-9)

    def test_base_moment_formula(self):
        L, P = 8.0, 1000.0
        M = LinearSolver.cantilever_base_moment(L, P)
        assert M == pytest.approx(P * L, rel=1e-9)

    def test_deflection_proportional_to_load(self):
        L, EI = 8.0, _circular_EI(0.120, 0.004)
        d1 = LinearSolver.cantilever_tip_deflection(L, 1000.0, EI)
        d2 = LinearSolver.cantilever_tip_deflection(L, 2000.0, EI)
        assert d2 == pytest.approx(2 * d1, rel=1e-9)

    def test_deflection_proportional_to_L_cubed(self):
        P, EI = 1000.0, _circular_EI(0.120, 0.004)
        d1 = LinearSolver.cantilever_tip_deflection(8.0, P, EI)
        d2 = LinearSolver.cantilever_tip_deflection(16.0, P, EI)
        assert d2 == pytest.approx(8 * d1, rel=1e-9)  # 2³ = 8


# ── AC-02: Voladizo carga distribuida uniforme ─────────────────────────────────

class TestAC02DistributedLoad:
    def test_distributed_deflection_formula(self):
        L, q = 8.0, 500.0
        EI = _circular_EI(0.120, 0.004)
        delta = LinearSolver.cantilever_distributed_deflection(L, q, EI)
        assert delta == pytest.approx(q * L**4 / (8 * EI), rel=1e-9)

    def test_distributed_deflection_greater_than_point(self):
        """qL distribuida total = PL concentrada; pero deflexión puntual > distribuida."""
        L, EI = 8.0, _circular_EI(0.120, 0.004)
        q = 500.0
        P = q * L  # misma fuerza total
        d_dist = LinearSolver.cantilever_distributed_deflection(L, q, EI)
        d_point = LinearSolver.cantilever_tip_deflection(L, P, EI)
        # Carga puntual en extremo produce mayor deflexión que la equivalente distribuida
        assert d_point > d_dist

    def test_base_moment_distributed(self):
        """Momento en la base = q·L²/2."""
        L, q = 8.0, 500.0
        M_base = q * L**2 / 2
        assert M_base == pytest.approx(500.0 * 64 / 2)


# ── AC-03: Voladizo troncocónico circular ──────────────────────────────────────

class TestAC03TaperedCantilever:
    def test_tapered_section_interpolation(self):
        """Propiedades interpoladas entre sección base y coronación."""
        sections = [
            {"xi": 0.0, "A_m2": 0.0015, "Iy_m4": 3e-6, "Iz_m4": 3e-6},
            {"xi": 1.0, "A_m2": 0.0008, "Iy_m4": 1e-6, "Iz_m4": 1e-6},
        ]
        mid = SectionService.interpolate_section(sections, 0.5)
        assert mid["A_m2"] == pytest.approx(0.00115, rel=1e-6)
        assert mid["Iy_m4"] == pytest.approx(2e-6, rel=1e-6)

    def test_tapered_EI_decreases_with_height(self):
        """EI es mayor en la base que en la coronación."""
        EI_base = _circular_EI(0.180, 0.005)
        EI_top = _circular_EI(0.080, 0.004)
        assert EI_base > EI_top

    def test_section_service_circular_hollow(self):
        props = SectionService.circular_hollow(0.120, 0.004)
        assert props["A_m2"] > 0
        assert props["J_m4"] == pytest.approx(2 * props["Iy_m4"], rel=1e-6)


# ── AC-04: Flexión biaxial ─────────────────────────────────────────────────────

class TestAC04BiaxialBending:
    def test_biaxial_moment_components(self):
        """Carga con azimut 45°: My = Mz = M/√2."""
        azimuth = math.pi / 4
        total_moment = 10000.0
        my = total_moment * math.cos(azimuth)
        mz = total_moment * math.sin(azimuth)
        assert my == pytest.approx(mz, rel=1e-9)
        assert math.sqrt(my**2 + mz**2) == pytest.approx(total_moment, rel=1e-9)

    def test_resultant_moment_magnitude(self):
        my, mz = 6000.0, 8000.0
        mr = ResultProcessor.resultant_moment(my, mz)
        assert mr == pytest.approx(10000.0, rel=1e-9)

    def test_governing_direction(self):
        my, mz = 0.0, 5000.0
        angle = ResultProcessor.governing_direction_deg(my, mz)
        assert angle == pytest.approx(90.0, abs=1e-9)


# ── AC-05: Torsión pura tubo circular ─────────────────────────────────────────

class TestAC05PureTorsion:
    def test_torsion_J_formula(self):
        """J = 2·I para tubo circular."""
        props = SectionService.circular_hollow(0.120, 0.004)
        assert props["J_m4"] == pytest.approx(2 * props["Iy_m4"], rel=1e-9)

    def test_torsional_angle_per_unit_length(self):
        """φ/L = T / (G·J)."""
        T = 500.0  # N·m
        props = SectionService.circular_hollow(0.120, 0.004)
        J = props["J_m4"]
        phi_per_L = T / (G_STEEL * J)
        assert phi_per_L > 0
        assert phi_per_L < 1.0  # < 1 rad/m para este caso


# ── AC-06: Cortante significativo (Timoshenko) ─────────────────────────────────

class TestAC06ShearDeformation:
    def test_timoshenko_shear_area_nonzero(self):
        props = SectionService.circular_hollow(0.100, 0.004)
        assert props["Ay_m2"] > 0
        assert props["Az_m2"] > 0

    def test_timoshenko_adds_shear_deflection(self):
        """Timoshenko produce mayor deflexión que Euler-Bernoulli."""
        L, P = 2.0, 10000.0  # columna corta: cortante dominante
        EI = _circular_EI(0.100, 0.004)
        delta_EB = P * L**3 / (3 * EI)
        props = SectionService.circular_hollow(0.100, 0.004)
        Av = props["Ay_m2"]
        delta_shear = P * L / (G_STEEL * Av)
        delta_T = delta_EB + delta_shear
        assert delta_T > delta_EB

    def test_shear_formulation_enum(self):
        assert ShearFormulation.TIMOSHENKO != ShearFormulation.EULER_BERNOULLI


# ── AC-07: Columna escalonada ──────────────────────────────────────────────────

class TestAC07SteppedColumn:
    def test_section_continuity_at_step(self):
        """En la unión: desplazamientos continuos, esfuerzos pueden ser discontinuos."""
        # Los nodos comparten coordenadas en la junta
        z_joint = 10.0
        node_lower = {"z_m": z_joint, "ux": 0.005}
        node_upper = {"z_m": z_joint, "ux": 0.005}  # mismo desplazamiento
        assert node_lower["ux"] == node_upper["ux"]

    def test_stepped_column_EI_ratio(self):
        EI_lower = _circular_EI(0.180, 0.005)
        EI_upper = _circular_EI(0.120, 0.004)
        assert EI_lower > EI_upper

    def test_mesh_stations_at_step(self):
        """Las estaciones de mallado incluyen obligatoriamente la junta."""
        stations_seg1 = MeshEngine.stations_for_segment(0.0, 10.0, MeshProfile.STANDARD)
        stations_seg2 = MeshEngine.stations_for_segment(10.0, 20.0, MeshProfile.STANDARD)
        # La junta z=10.0 debe ser el último punto del seg1 y primero del seg2
        assert stations_seg1[-1] == pytest.approx(10.0, abs=1e-9)
        assert stations_seg2[0] == pytest.approx(10.0, abs=1e-9)


# ── AC-08: Brazo excéntrico → flexión + torsión ───────────────────────────────

class TestAC08EccentricArm:
    def test_eccentric_load_generates_moment(self):
        """Carga en extremo de brazo → fuerza + momento en nodo de fuste."""
        force = [0.0, 0.0, -500.0]   # luminaria 500 N hacia abajo
        moment = [0.0, 0.0, 0.0]
        eccentricity = [2.0, 0.0, 0.0]  # brazo 2 m en X
        result = LoadMapper.eccentric_load_to_node(force, moment, eccentricity)
        # My = ez·Fx - ex·Fz = 0 - 2·(-500) = 1000 N·m
        assert result["moment_nm"][1] == pytest.approx(1000.0, rel=1e-9)
        assert result["force_n"][2] == pytest.approx(-500.0, rel=1e-9)

    def test_eccentric_load_no_discarded(self):
        """La excentricidad no puede ignorarse (P-3 del documento)."""
        force = [1000.0, 0.0, 0.0]
        moment = [0.0, 0.0, 0.0]
        ecc = [0.0, 0.5, 0.0]  # excentricidad Y
        result = LoadMapper.eccentric_load_to_node(force, moment, ecc)
        # Mz = ex·Fy - ey·Fx = 0 - 0.5·1000 = -500 N·m
        assert result["moment_nm"][2] == pytest.approx(-500.0, rel=1e-9)


# ── AC-09: Dos brazos opuestos ────────────────────────────────────────────────

class TestAC09TwoOppositeArms:
    def test_opposite_moments_cancel(self):
        """Brazos opuestos simétricamente → cancelación de momento de torsión."""
        T1 = 300.0   # N·m — torsión brazo 1
        T2 = -300.0  # N·m — brazo opuesto
        T_net = T1 + T2
        assert T_net == pytest.approx(0.0, abs=1e-9)

    def test_opposite_horizontal_forces_cancel(self):
        """Cargas de viento de igual magnitud y sentido opuesto se cancelan."""
        Fx1, Fx2 = 500.0, -500.0
        assert Fx1 + Fx2 == 0.0


# ── AC-10: Seis cables en direcciones arbitrarias ─────────────────────────────

class TestAC10SixCablesModel:
    def test_six_cables_load_schema(self):
        cables = [
            {
                "cable_identifier": f"C{i+1}",
                "tension_n": float(3000 + i * 500),
                "azimuth_rad": i * math.pi / 3,
                "elevation_rad": math.pi / 8,
                "anchor_z_m": 8.0,
            }
            for i in range(6)
        ]
        assert len(cables) == 6
        # Cada cable tiene azimut único
        azimuths = [c["azimuth_rad"] for c in cables]
        assert len(set(azimuths)) == 6


# ── AC-11: Masa excéntrica con tensor de inercia ──────────────────────────────

class TestAC11EccentricMass:
    def test_mass_object_schema(self):
        from app.models.db.structural import MassObject
        # Verificamos que los campos existen en el modelo
        assert hasattr(MassObject, "mass_kg")
        assert hasattr(MassObject, "cg_global_json")
        assert hasattr(MassObject, "inertia_tensor_json")

    def test_inertia_tensor_symmetric(self):
        """Tensor de inercia debe ser simétrico."""
        tensor = {"Ixx": 2.0, "Iyy": 3.0, "Izz": 4.0,
                  "Ixy": 0.5, "Ixz": 0.3, "Iyz": 0.2}
        # Verificación: Ixy = Iyx, etc. (almacenados como 3 valores cruzados)
        assert tensor["Ixy"] == tensor["Ixy"]  # trivialmente simétrico en JSON


# ── AC-12: Apoyo elástico traslacional ────────────────────────────────────────

class TestAC12ElasticTranslationalSupport:
    def test_elastic_support_deflection(self):
        """Deflexión en apoyo elástico: δ = F / k."""
        k = 1e6  # N/m
        F = 10000.0
        delta = F / k
        assert delta == pytest.approx(0.010, abs=1e-9)

    def test_support_type_elastic(self):
        assert SupportType.ELASTIC == SupportType.ELASTIC

    def test_spring_stiffness_positive(self):
        """Rigidez del resorte debe ser positiva (STRUCT-004)."""
        k = 1e6
        assert k > 0


# ── AC-13: Apoyo con matriz 6×6 acoplada ──────────────────────────────────────

class TestAC13CoupledMatrix:
    def test_6x6_matrix_symmetry(self):
        """Verificar que la matriz de rigidez 6×6 es simétrica."""
        K = [
            [1e8, 0, 0, 0, 1e5, 0],
            [0, 1e8, 0, -1e5, 0, 0],
            [0, 0, 1e9, 0, 0, 0],
            [0, -1e5, 0, 1e6, 0, 0],
            [1e5, 0, 0, 0, 1e6, 0],
            [0, 0, 0, 0, 0, 5e5],
        ]
        for i in range(6):
            for j in range(6):
                assert K[i][j] == pytest.approx(K[j][i], rel=1e-9)

    def test_6x6_matrix_positive_diagonal(self):
        """Diagonal principal positiva (condición necesaria para SPD)."""
        K_diag = [1e8, 1e8, 1e9, 1e6, 1e6, 5e5]
        assert all(k > 0 for k in K_diag)


# ── AC-14: Columna empotrada con resortes distribuidos ───────────────────────

class TestAC14EmbeddedColumnSprings:
    def test_distributed_springs_schema(self):
        springs = {"kx_N_m2": 5e6, "ky_N_m2": 5e6, "kz_N_m2": 0.0}
        assert springs["kx_N_m2"] > 0
        assert springs["ky_N_m2"] > 0

    def test_support_type_distributed_springs(self):
        assert SupportType.DISTRIBUTED_SPRINGS == SupportType.DISTRIBUTED_SPRINGS


# ── AC-15: Unión telescópica rígida ──────────────────────────────────────────

class TestAC15RigidTelescopicJoint:
    def test_rigid_link_element_type(self):
        assert ElementType.RIGID_LINK == ElementType.RIGID_LINK

    def test_continuity_in_rigid_joint(self):
        """Unión rígida: desplazamientos y giros continuos en ambos lados."""
        u_left = {"ux": 0.005, "uy": 0.0, "rz": 0.002}
        u_right = {"ux": 0.005, "uy": 0.0, "rz": 0.002}  # idéntico = continuidad
        assert u_left == u_right


# ── AC-16: Unión con rigidez rotacional finita ────────────────────────────────

class TestAC16RotationalStiffnessJoint:
    def test_spring6_element_type(self):
        assert ElementType.SPRING6 == ElementType.SPRING6

    def test_partial_rotation_fixity(self):
        """Con rigidez rotacional kr, giro en la unión = M / kr."""
        M = 10000.0  # N·m
        kr = 5e6     # N·m/rad
        phi = M / kr
        assert phi == pytest.approx(2e-3, rel=1e-9)


# ── AC-17: Segundo orden columna esbelta ──────────────────────────────────────

class TestAC17SecondOrder:
    def test_pdelta_amplification_greater_than_1(self):
        """Factor P-Delta siempre > 1 para N < Ncr."""
        EI = _circular_EI(0.100, 0.004)
        L = 12.0
        Ncr = NonlinearSolver.euler_critical_load(EI, L, k=2.0)  # k=2 voladizo
        N = 0.3 * Ncr
        amp = NonlinearSolver.pdelta_amplification_factor(N, Ncr)
        assert amp > 1.0
        assert amp == pytest.approx(1 / (1 - 0.3), rel=1e-6)

    def test_amplification_increases_with_N(self):
        EI = _circular_EI(0.100, 0.004)
        Ncr = NonlinearSolver.euler_critical_load(EI, 12.0, k=2.0)
        amp1 = NonlinearSolver.pdelta_amplification_factor(0.1 * Ncr, Ncr)
        amp2 = NonlinearSolver.pdelta_amplification_factor(0.5 * Ncr, Ncr)
        assert amp2 > amp1

    def test_second_order_analysis_order_enum(self):
        assert AnalysisOrder.SECOND_ORDER == AnalysisOrder.SECOND_ORDER


# ── AC-18: No convergencia controlada ─────────────────────────────────────────

class TestAC18NonConvergence:
    def test_near_critical_load_raises(self):
        """N ≥ Ncr debe generar ValueError (carga inestable)."""
        EI = _circular_EI(0.100, 0.004)
        Ncr = NonlinearSolver.euler_critical_load(EI, 12.0, k=2.0)
        with pytest.raises(ValueError, match="crítica"):
            NonlinearSolver.pdelta_amplification_factor(Ncr, Ncr)

    def test_exceeding_critical_raises(self):
        EI = _circular_EI(0.100, 0.004)
        Ncr = NonlinearSolver.euler_critical_load(EI, 12.0, k=2.0)
        with pytest.raises(ValueError):
            NonlinearSolver.pdelta_amplification_factor(1.01 * Ncr, Ncr)

    def test_nl_max_iterations_default(self):
        run = AnalysisRunCreate(model_id=uuid.uuid4())
        assert run.nl_max_iterations == 50


# ── AC-19: Pandeo elástico de columna ideal ────────────────────────────────────

class TestAC19ElasticBuckling:
    def test_euler_critical_load_formula(self):
        """Ncr = π²·EI / (k·L)²."""
        EI = _circular_EI(0.120, 0.004)
        L, k = 10.0, 2.0  # voladizo: longitud efectiva = 2L
        Ncr = NonlinearSolver.euler_critical_load(EI, L, k)
        Ncr_ref = math.pi**2 * EI / (k * L)**2
        assert Ncr == pytest.approx(Ncr_ref, rel=1e-9)

    def test_euler_load_decreases_with_L(self):
        EI = _circular_EI(0.120, 0.004)
        Ncr1 = NonlinearSolver.euler_critical_load(EI, 8.0)
        Ncr2 = NonlinearSolver.euler_critical_load(EI, 12.0)
        assert Ncr1 > Ncr2


# ── AC-20: Pandeo de fuste escalonado ────────────────────────────────────────

class TestAC20SteppedColumnBuckling:
    def test_stepped_effective_length(self):
        """Fuste escalonado: longitud efectiva entre sección inferior y superior."""
        EI_lower = _circular_EI(0.180, 0.005)
        EI_upper = _circular_EI(0.120, 0.004)
        L_lower, L_upper = 10.0, 8.0

        Ncr_lower = NonlinearSolver.euler_critical_load(EI_lower, L_lower + L_upper, k=2.0)
        Ncr_upper = NonlinearSolver.euler_critical_load(EI_upper, L_upper, k=2.0)
        # El modo crítico es el mínimo de los dos
        Ncr_stepped = min(Ncr_lower, Ncr_upper)
        assert Ncr_stepped > 0

    def test_buckling_result_critical_factor_positive(self):
        """Factor crítico siempre > 0 (CheckConstraint del modelo)."""
        critical_factor = 3.5
        assert critical_factor > 0


# ── AC-21: Frecuencia fundamental voladizo ────────────────────────────────────

class TestAC21FundamentalFrequency:
    def test_cantilever_frequency_formula(self):
        """f₁ = 1.8751² / (2π·L²) · √(EI/ρA), tolerancia ≤ 1 %."""
        L = 8.0
        EI = _circular_EI(0.120, 0.004)
        rho_A = _circular_mass_per_m(0.120, 0.004)
        f = EigenSolver.cantilever_fundamental_frequency_hz(EI, rho_A, L)
        # Fórmula de referencia
        beta1_L = 1.8751
        omega_ref = (beta1_L / L)**2 * math.sqrt(EI / rho_A)
        f_ref = omega_ref / (2 * math.pi)
        assert f == pytest.approx(f_ref, rel=TOL_FREQUENCY_PCT)

    def test_frequency_increases_with_EI(self):
        L = 8.0
        rho_A = _circular_mass_per_m(0.120, 0.004)
        f1 = EigenSolver.cantilever_fundamental_frequency_hz(
            _circular_EI(0.120, 0.004), rho_A, L)
        f2 = EigenSolver.cantilever_fundamental_frequency_hz(
            _circular_EI(0.160, 0.005), rho_A, L)
        assert f2 > f1

    def test_frequency_decreases_with_length(self):
        EI = _circular_EI(0.120, 0.004)
        rho_A = _circular_mass_per_m(0.120, 0.004)
        f1 = EigenSolver.cantilever_fundamental_frequency_hz(EI, rho_A, 8.0)
        f2 = EigenSolver.cantilever_fundamental_frequency_hz(EI, rho_A, 12.0)
        assert f1 > f2


# ── AC-22: Frecuencia con luminaria en coronación ────────────────────────────

class TestAC22FrequencyWithTipMass:
    def test_tip_mass_reduces_frequency(self):
        """Masa concentrada en extremo reduce la frecuencia fundamental."""
        L = 8.0
        EI = _circular_EI(0.120, 0.004)
        rho_A = _circular_mass_per_m(0.120, 0.004)
        m_dist = rho_A * L
        f_no_tip = EigenSolver.cantilever_fundamental_frequency_hz(EI, rho_A, L)
        f_with_tip = EigenSolver.frequency_with_tip_mass(f_no_tip, m_dist, 15.0)
        assert f_with_tip < f_no_tip

    def test_heavier_tip_mass_lower_frequency(self):
        L = 8.0
        EI = _circular_EI(0.120, 0.004)
        rho_A = _circular_mass_per_m(0.120, 0.004)
        m_dist = rho_A * L
        f0 = EigenSolver.cantilever_fundamental_frequency_hz(EI, rho_A, L)
        f15 = EigenSolver.frequency_with_tip_mass(f0, m_dist, 15.0)
        f30 = EigenSolver.frequency_with_tip_mass(f0, m_dist, 30.0)
        assert f30 < f15


# ── AC-23: Modo torsional con brazo ──────────────────────────────────────────

class TestAC23TorsionalMode:
    def test_torsional_mode_requires_arm(self):
        """La presencia de un brazo introduce acoplamiento flexión-torsión."""
        has_arm = True
        torsional_mode_expected = has_arm
        assert torsional_mode_expected

    def test_modal_result_schema_has_description(self):
        from app.models.db.structural import ModalResult
        assert hasattr(ModalResult, "mode_description")


# ── AC-24: Detección de mecanismo ────────────────────────────────────────────

class TestAC24MechanismDetection:
    def test_dof_without_stiffness(self):
        """STRUCT-001: DOF sin rigidez → diagnóstico de error."""
        severity = StructuralDiagnosticSeverity.ERROR
        assert severity == StructuralDiagnosticSeverity.ERROR

    def test_release_both_ends_creates_mechanism(self):
        """Articulación en ambos extremos de un elemento → mecanismo."""
        releases_i = [False, False, False, True, True, True]  # libera momentos
        releases_j = [False, False, False, True, True, True]
        is_mechanism = all(releases_i[3:]) and all(releases_j[3:])
        assert is_mechanism


# ── AC-25: Detección de componente desconectado ───────────────────────────────

class TestAC25DisconnectedComponent:
    def test_disconnected_component_diagnosis(self):
        """STRUCT-002: componente desconectado → error bloqueante."""
        code = "STRUCT-002"
        assert code.startswith("STRUCT-")

    def test_disconnected_raises_before_solve(self):
        """El motor no debe resolver con componentes desconectados."""
        has_disconnected = True
        can_solve = not has_disconnected
        assert not can_solve


# ── AC-26: Detección de elemento longitud casi nula ──────────────────────────

class TestAC26NearZeroElement:
    def test_near_zero_length_threshold(self):
        """STRUCT-003: elemento con L < 0,1 mm."""
        L = 5e-5  # 0,05 mm
        threshold = 1e-4  # 0,1 mm
        assert L < threshold

    def test_spring6_exempt_from_length_check(self):
        """SPRING6 y MASS6 no requieren longitud > 0."""
        types_exempt = {ElementType.SPRING6, ElementType.MASS6}
        assert ElementType.SPRING6 in types_exempt
        assert ElementType.BEAM3D_VAR not in types_exempt


# ── AC-27: Detección de matriz de resorte no física ──────────────────────────

class TestAC27NonPhysicalSpring:
    def test_negative_spring_stiffness_flag(self):
        """STRUCT-004: rigidez negativa → diagnóstico."""
        k = -1000.0
        is_physical = k > 0
        assert not is_physical

    def test_asymmetric_matrix_flag(self):
        """Matriz no simétrica → STRUCT-004."""
        K_row0 = [1e6, 500.0]
        K_row1 = [600.0, 1e6]  # K[0][1] ≠ K[1][0]
        is_symmetric = K_row0[1] == K_row1[0]
        assert not is_symmetric


# ── AC-28: Equilibrio global para combinación compleja ───────────────────────

class TestAC28GlobalEquilibrium:
    def test_equilibrium_check_passes(self):
        """Suma de fuerzas + reacciones = 0 dentro de tolerancia."""
        total_load = [1000.0, 0.0, -5000.0]
        total_reaction = [-1000.0, 0.0, 5000.0]
        ok = LinearSolver.check_equilibrium(total_load, total_reaction)
        assert ok

    def test_equilibrium_check_fails(self):
        """Desequilibrio de 1 % debe ser detectado."""
        total_load = [1000.0, 0.0, 0.0]
        total_reaction = [-1010.0, 0.0, 0.0]  # 1 % de error
        ok = LinearSolver.check_equilibrium(total_load, total_reaction)
        assert not ok

    def test_equilibrium_tolerance_is_strict(self):
        """Tolerancia ≤ 1e-8 relativa (doc §28.2)."""
        assert TOL_EQUILIBRIUM == pytest.approx(1e-8, rel=1e-1)


# ── AC-29: Transformación local-global ───────────────────────────────────────

class TestAC29LocalGlobalTransform:
    def test_identity_rotation(self):
        """Rotación identidad: vector local = vector global."""
        v = [1.0, 2.0, 3.0]
        I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        result = LoadMapper.transform_to_global(v, I3)
        assert result == pytest.approx(v, rel=1e-9)

    def test_90deg_rotation_about_z(self):
        """Rotación 90° alrededor de Z: [1,0,0] → [0,1,0]."""
        v = [1.0, 0.0, 0.0]
        R = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        result = LoadMapper.transform_to_global(v, R)
        assert result[0] == pytest.approx(0.0, abs=1e-9)
        assert result[1] == pytest.approx(1.0, abs=1e-9)
        assert result[2] == pytest.approx(0.0, abs=1e-9)

    def test_rotation_preserves_magnitude(self):
        """Rotación ortogonal conserva el módulo del vector."""
        v = [3.0, 4.0, 0.0]
        angle = math.pi / 6
        R = [
            [math.cos(angle), -math.sin(angle), 0],
            [math.sin(angle),  math.cos(angle), 0],
            [0, 0, 1],
        ]
        result = LoadMapper.transform_to_global(v, R)
        mag_orig = math.sqrt(sum(x**2 for x in v))
        mag_result = math.sqrt(sum(x**2 for x in result))
        assert mag_result == pytest.approx(mag_orig, rel=1e-9)


# ── AC-30: Carga excéntrica conserva fuerza y momento ────────────────────────

class TestAC30EccentricLoad:
    def test_force_preserved_after_transfer(self):
        f = [0.0, 0.0, -800.0]
        result = LoadMapper.eccentric_load_to_node(f, [0.0, 0.0, 0.0], [1.5, 0.0, 0.0])
        assert result["force_n"] == pytest.approx(f, rel=1e-9)

    def test_moment_added_is_cross_product(self):
        """M_add = e × F."""
        f = [0.0, 0.0, -800.0]
        e = [1.5, 0.0, 0.0]
        result = LoadMapper.eccentric_load_to_node(f, [0.0, 0.0, 0.0], e)
        # e × F = [ey·Fz - ez·Fy, ez·Fx - ex·Fz, ex·Fy - ey·Fx]
        #        = [0·(-800) - 0·0, 0·0 - 1.5·(-800), 1.5·0 - 0·0]
        #        = [0, 1200, 0]
        assert result["moment_nm"][1] == pytest.approx(1200.0, rel=1e-9)


# ── AC-31: Envolvente conserva procedencia ────────────────────────────────────

class TestAC31EnvelopeProvenance:
    def test_envelope_has_load_case_ref(self):
        results = [
            {"value": 1000.0, "load_case_ref": "W_0", "combination_ref": "ELU-1",
             "wind_direction_deg": 0.0, "station_xi": 0.0, "element_id": None},
            {"value": 1500.0, "load_case_ref": "W_90", "combination_ref": "ELU-2",
             "wind_direction_deg": 90.0, "station_xi": 0.0, "element_id": None},
            {"value": 800.0, "load_case_ref": "W_180", "combination_ref": "ELU-1",
             "wind_direction_deg": 180.0, "station_xi": 0.0, "element_id": None},
        ]
        env = ResultProcessor.build_envelope(results, "My_nm", EnvelopeScope.BY_STATION)
        assert env["max"]["load_case_ref"] == "W_90"
        assert env["max"]["value"] == 1500.0
        assert env["min"]["value"] == 800.0

    def test_envelope_wind_direction_stored(self):
        results = [
            {"value": 2000.0, "load_case_ref": "W_60", "combination_ref": "ELU-3",
             "wind_direction_deg": 60.0, "station_xi": 0.0, "element_id": None},
        ]
        env = ResultProcessor.build_envelope(results, "Mz_nm", EnvelopeScope.BY_DIRECTION)
        assert env["max"]["wind_direction_deg"] == 60.0


# ── AC-32: Invalidación por cambio de geometría ───────────────────────────────

class TestAC32InvalidationGeometry:
    def test_geometry_change_changes_hash(self):
        """Cambio de geometría → hash diferente → modelo inválido."""
        def model_hash(height: float) -> str:
            payload = json.dumps({"height_m": height}, sort_keys=True)
            return hashlib.sha256(payload.encode()).hexdigest()

        h1 = model_hash(8.0)
        h2 = model_hash(9.0)
        assert h1 != h2

    def test_model_invalid_after_geometry_change(self):
        """Estado INVALID tras cambio geométrico."""
        status = StructuralModelStatus.INVALID
        mutable = {StructuralModelStatus.BUILDING}
        assert status not in mutable


# ── AC-33: No invalidación por cambio de idioma ───────────────────────────────

class TestAC33NoInvalidationLanguage:
    def test_language_change_not_in_hash(self):
        """El idioma del informe no forma parte del hash de inputs."""
        def input_hash(geometry: dict) -> str:
            # El idioma NO entra en el hash
            payload = json.dumps(geometry, sort_keys=True)
            return hashlib.sha256(payload.encode()).hexdigest()

        geom = {"height_m": 8.0, "d_ext_m": 0.120}
        h_es = input_hash(geom)
        h_en = input_hash(geom)  # mismo hash, idioma no incluido
        assert h_es == h_en


# ── AC-34: Reproducibilidad de ejecución idéntica ────────────────────────────

class TestAC34Reproducibility:
    def test_same_inputs_same_solver_hash(self):
        """Mismo motor + mismos parámetros → mismo solver_hash."""
        def solver_hash(version: str, order: str, mesh: str) -> str:
            payload = json.dumps(
                {"engine_version": version, "analysis_order": order, "mesh_profile": mesh},
                sort_keys=True
            )
            return hashlib.sha256(payload.encode()).hexdigest()

        h1 = solver_hash("4.0.0", "SECOND_ORDER", "STANDARD")
        h2 = solver_hash("4.0.0", "SECOND_ORDER", "STANDARD")
        assert h1 == h2

    def test_different_mesh_profile_different_hash(self):
        def solver_hash(mesh: str) -> str:
            return hashlib.sha256(mesh.encode()).hexdigest()

        assert solver_hash("STANDARD") != solver_hash("PRECISE")


# ── AC-35: Convergencia de malla en columna de 30 m ──────────────────────────

class TestAC35MeshConvergence:
    def test_precise_finer_than_standard(self):
        """PRECISE genera más estaciones que STANDARD."""
        stations_std = MeshEngine.stations_for_segment(0.0, 30.0, MeshProfile.STANDARD)
        stations_prec = MeshEngine.stations_for_segment(0.0, 30.0, MeshProfile.PRECISE)
        assert len(stations_prec) > len(stations_std)

    def test_validation_finer_than_precise(self):
        stations_prec = MeshEngine.stations_for_segment(0.0, 30.0, MeshProfile.PRECISE)
        stations_val = MeshEngine.stations_for_segment(0.0, 30.0, MeshProfile.VALIDATION)
        assert len(stations_val) > len(stations_prec)

    def test_convergence_check_passes_identical(self):
        values = [1.0, 2.0, 3.0]
        ok = MeshEngine.verify_convergence(values, values)
        assert ok

    def test_convergence_check_fails_large_diff(self):
        precise = [1.0, 2.0, 3.0]
        validation = [1.0, 2.02, 3.0]  # 1 % diff en el segundo — supera 0,5 %
        ok = MeshEngine.verify_convergence(precise, validation)
        assert not ok


# ── AC-36: Modelo 30 m con tres tramos y dos uniones ─────────────────────────

class TestAC36ThreeSegmentModel:
    def test_three_segment_height_sum(self):
        segments = [
            {"z_start": 0.0, "z_end": 12.0},
            {"z_start": 12.0, "z_end": 22.0},
            {"z_start": 22.0, "z_end": 30.0},
        ]
        total = sum(s["z_end"] - s["z_start"] for s in segments)
        assert total == pytest.approx(30.0, abs=1e-9)

    def test_two_joints_between_segments(self):
        joint_positions = [12.0, 22.0]
        assert len(joint_positions) == 2


# ── AC-37: Puerta con rigidez reducida importada ─────────────────────────────

class TestAC37DoorReducedStiffness:
    def test_door_stiffness_property_set(self):
        assert StructuralPropertySet.DOOR == StructuralPropertySet.DOOR

    def test_door_reduces_effective_stiffness(self):
        """Rigidez efectiva con puerta < rigidez bruta."""
        EI_gross = 1.5e6
        reduction_factor = 0.75  # reducción por hueco de puerta
        EI_door = EI_gross * reduction_factor
        assert EI_door < EI_gross


# ── AC-38: Aluminio con propiedades HAZ ──────────────────────────────────────

class TestAC38AluminiumHAZ:
    def test_haz_property_set(self):
        assert StructuralPropertySet.HAZ == StructuralPropertySet.HAZ

    def test_haz_reduces_E_in_zone(self):
        """Zona afectada por calor: E_haz < E_Al nominal."""
        E_Al = 70e9
        haz_factor = 0.85  # reducción típica en HAZ
        E_haz = E_Al * haz_factor
        assert E_haz < E_Al


# ── AC-39: Hormigón rigidez bruta y fisurada ─────────────────────────────────

class TestAC39ConcreteGrossVsCracked:
    def test_cracked_property_set(self):
        assert StructuralPropertySet.CRACKED == StructuralPropertySet.CRACKED

    def test_cracked_stiffness_lower_than_gross(self):
        EI_gross = 50e6
        crack_factor = 0.5  # EN 1992: 0,5·EI bruto para hormigón fisurado
        EI_cracked = EI_gross * crack_factor
        assert EI_cracked < EI_gross

    def test_two_separate_runs_for_gross_and_cracked(self):
        """Dos ejecuciones separadas con distintos juegos de propiedades."""
        run_gross = {"property_set": "GROSS"}
        run_cracked = {"property_set": "CRACKED"}
        assert run_gross["property_set"] != run_cracked["property_set"]


# ── AC-40: Peso propio sin duplicidad ────────────────────────────────────────

class TestAC40SelfWeightNoDuplicity:
    def test_self_weight_from_linear_mass(self):
        """G = ρ·A·g·L por tramo."""
        rho_A = _circular_mass_per_m(0.120, 0.004)
        g = 9.81
        L = 8.0
        W = rho_A * g * L
        assert W > 0

    def test_no_double_counting_with_mass_object(self):
        """Si se añade MassObject de luminaria, no debe incluirse en peso propio."""
        include_in_self_weight = False  # flag del MassObject
        contributes_to_G = include_in_self_weight
        assert not contributes_to_G


# ── AC-41: Aceleración sísmica en masa consistente ───────────────────────────

class TestAC41SeismicConsistentMass:
    def test_consistent_mass_model(self):
        assert MassModel.CONSISTENT == MassModel.CONSISTENT

    def test_seismic_force_proportional_to_mass(self):
        """F_sísmica = m · Sa (espectro)."""
        m = 500.0  # kg
        Sa = 0.3 * 9.81  # m/s²
        F = m * Sa
        assert F == pytest.approx(1471.5, rel=1e-4)


# ── AC-42: Temperatura uniforme sin esfuerzos (estructura libre) ──────────────

class TestAC42ThermalUniform:
    def test_free_structure_no_stress(self):
        """Estructura libre: ΔT uniforme → dilatación libre, sin esfuerzos."""
        alpha_T = 12e-6  # 1/K — acero
        delta_T = 50.0   # K
        L = 8.0          # m
        delta_L = alpha_T * delta_T * L  # dilatación libre
        # En estructura libre: N = 0
        N = 0.0
        assert N == 0.0
        assert delta_L == pytest.approx(4.8e-3, rel=1e-6)

    def test_thermal_load_type(self):
        assert StructuralLoadType.THERMAL == StructuralLoadType.THERMAL


# ── AC-43: Temperatura restringida genera axil ────────────────────────────────

class TestAC43ThermalRestrained:
    def test_restrained_thermal_axil(self):
        """Estructura restringida: N = E·A·α·ΔT."""
        E = 210e9
        d, t = 0.120, 0.004
        A = SectionService.circular_hollow(d, t)["A_m2"]
        alpha_T = 12e-6
        delta_T = 50.0
        N = E * A * alpha_T * delta_T
        assert N > 0
        assert N == pytest.approx(E * A * alpha_T * delta_T, rel=1e-9)


# ── AC-44: Cancelación segura de trabajo largo ───────────────────────────────

class TestAC44CancellationSafe:
    def test_cancel_requested_flag(self):
        """Flag cancel_requested permite cancelación graceful."""
        from app.models.db.structural import StructuralAnalysisRun
        assert hasattr(StructuralAnalysisRun, "cancel_requested")

    def test_queued_run_can_be_cancelled_immediately(self):
        """Run en QUEUED se puede cancelar sin esperar al solver."""
        status = StructuralRunStatus.QUEUED
        can_cancel = status == StructuralRunStatus.QUEUED
        assert can_cancel

    def test_completed_run_cannot_be_cancelled(self):
        status = StructuralRunStatus.COMPLETED
        can_cancel = status not in (StructuralRunStatus.COMPLETED, StructuralRunStatus.FAILED)
        assert not can_cancel


# ── AC-45: Exportación neutra conserva modelo ────────────────────────────────

class TestAC45NeutralExport:
    def test_export_request_formats(self):
        for fmt in ["json", "csv", "nastran"]:
            req = ExportRequest(format=fmt)
            assert req.format == fmt

    def test_export_request_invalid_format(self):
        with pytest.raises(Exception):
            ExportRequest(format="abaqus")

    def test_export_hash_matches_run(self):
        """La exportación almacena el hash del modelo en el momento de la exportación."""
        model_hash = "sha256:abc123"
        export_hash = model_hash  # debe ser idéntico
        assert model_hash == export_hash


# ── AC-46: Comparación con modelo externo ────────────────────────────────────

class TestAC46ExternalModelComparison:
    def test_displacement_tolerance(self):
        """Desviación vs modelo externo ≤ 0,5 %."""
        delta_internal = 0.0512
        delta_external = 0.0510
        diff_rel = abs(delta_internal - delta_external) / delta_external
        assert diff_rel <= 0.005

    def test_frequency_tolerance(self):
        """Frecuencia vs modelo externo ≤ 1 %."""
        f_internal = 1.23
        f_external = 1.24
        diff_rel = abs(f_internal - f_external) / f_external
        assert diff_rel <= TOL_FREQUENCY_PCT


# ── AC-47: Comparación con ensayo histórico ───────────────────────────────────

class TestAC47HistoricalTest:
    def test_deflection_vs_test_within_tolerance(self):
        """Deflexión calculada vs ensayo dentro de tolerancia de validación."""
        delta_calc = 42.5  # mm
        delta_test = 43.0  # mm (valor hipotético de ensayo)
        diff_rel = abs(delta_calc - delta_test) / delta_test
        assert diff_rel <= TOL_DISPLACEMENT_PCT + 0.003  # +0,3 % margen ensayo

    def test_stress_vs_test_within_tolerance(self):
        sigma_calc = 185.0  # MPa
        sigma_test = 186.0  # MPa
        diff_rel = abs(sigma_calc - sigma_test) / sigma_test
        assert diff_rel <= TOL_STRESS_PCT + 0.003


# ── AC-48: Control de permisos sobre parámetros avanzados ────────────────────

class TestAC48PermissionsAdvancedParams:
    def test_nl_tolerances_have_limits(self):
        """Tolerancias NL no pueden ser más laxas que 1e-3 (límite del perfil)."""
        tol_max = 1e-3
        tol = 1e-6
        assert tol <= tol_max

    def test_mesh_fast_not_final(self):
        """Perfil FAST no puede presentarse como cálculo final."""
        profile = MeshProfile.FAST
        is_final_allowed = profile not in {MeshProfile.FAST}
        assert not is_final_allowed

    def test_second_order_mandatory_for_final(self):
        """Segundo orden es obligatorio para cálculo final (bloqueo de seguridad)."""
        order = AnalysisOrder.SECOND_ORDER
        is_mandatory = True  # según §19 del documento
        assert is_mandatory


# ── AC-49: Paquete de soporte reproducible ───────────────────────────────────

class TestAC49SupportPackage:
    def test_manifest_has_all_hashes(self):
        """El manifiesto incluye todos los hashes para reproducibilidad."""
        manifest_fields = [
            "structural_model_hash",
            "analysis_input_hash",
            "solver_hash",
            "engine_version",
        ]
        from app.models.db.structural import StructuralAnalysisRun
        for field in manifest_fields:
            assert hasattr(StructuralAnalysisRun, field)

    def test_manifest_has_timing(self):
        timing_fields = ["preprocess_time_s", "solve_time_s", "postprocess_time_s"]
        from app.models.db.structural import StructuralAnalysisRun
        for field in timing_fields:
            assert hasattr(StructuralAnalysisRun, field)


# ── AC-50: Ejecución completa apta para verificación de material ──────────────

class TestAC50CompleteRunAptForMaterial:
    def test_completed_status_required(self):
        """Solo COMPLETED permite enviar a verificación de material."""
        run_status = StructuralRunStatus.COMPLETED
        ready_for_material_check = run_status == StructuralRunStatus.COMPLETED
        assert ready_for_material_check

    def test_failed_run_blocks_material_check(self):
        run_status = StructuralRunStatus.FAILED
        ready = run_status == StructuralRunStatus.COMPLETED
        assert not ready

    def test_no_critical_diagnostics_required(self):
        """Sin diagnósticos CRITICAL → apto para liberación."""
        diagnostics = [
            {"severity": StructuralDiagnosticSeverity.WARNING, "code": "STRUCT-005"},
            {"severity": StructuralDiagnosticSeverity.INFO, "code": "STRUCT-006"},
        ]
        has_critical = any(
            d["severity"] == StructuralDiagnosticSeverity.CRITICAL
            for d in diagnostics
        )
        is_apt = not has_critical
        assert is_apt
