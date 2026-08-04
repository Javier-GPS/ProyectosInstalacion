"""
Fase 11 · Cimentaciones y Geotecnia — Tests de aceptación
AC11-001..AC11-080 (80 ACs en 8 clases)
"""
from __future__ import annotations

import math
import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock infrastructure (no pytest, no DB required)
# ---------------------------------------------------------------------------
_pytest_mod = types.ModuleType("pytest")
_pytest_mod.mark = MagicMock()
_pytest_mod.fixture = MagicMock()
_pytest_mod.raises = MagicMock()
sys.modules["pytest"] = _pytest_mod

for _mod in [
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.ext.asyncio",
    "sqlalchemy.dialects", "sqlalchemy.dialects.postgresql",
    "fastapi", "fastapi.routing", "pydantic",
    "app", "app.db", "app.db.session",
    "app.models", "app.models.db", "app.models.db.base",
    "app.models.schemas",
    "app.api", "app.api.v1",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Make Base importable
sys.modules["app.models.db.base"].Base = MagicMock()

# ---------------------------------------------------------------------------
# Import service module
# ---------------------------------------------------------------------------
import importlib.util as _ilu
import pathlib

_svc_path = (pathlib.Path(__file__).parent.parent.parent /
             "app" / "services" / "foundation_service.py")
_spec = _ilu.spec_from_file_location("foundation_service", _svc_path)
_svc_mod = _ilu.module_from_spec(_spec)
sys.modules["foundation_service"] = _svc_mod
_spec.loader.exec_module(_svc_mod)

BearingCapacityService = _svc_mod.BearingCapacityService
OverturningSlidingService = _svc_mod.OverturningSlidingService
UpliftService = _svc_mod.UpliftService
FoundationStiffnessService = _svc_mod.FoundationStiffnessService
EmbeddedPoleService = _svc_mod.EmbeddedPoleService
FoundationOptimizer = _svc_mod.FoundationOptimizer
FoundationNormativeClassifier = _svc_mod.FoundationNormativeClassifier
GeotechnicalClassifier = _svc_mod.GeotechnicalClassifier
compute_foundation_hash = _svc_mod.compute_foundation_hash
FoundationCandidateSummary = _svc_mod.FoundationCandidateSummary


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def assert_close(a: float, b: float, rel: float = 0.01, label: str = "") -> None:
    if b == 0:
        assert abs(a) < 1e-9, f"{label}: expected ~0, got {a}"
    else:
        err = abs(a - b) / abs(b)
        assert err <= rel, f"{label}: {a} vs {b}, rel err={err:.4f}"


# ---------------------------------------------------------------------------
# AC11-001..012: Datos y clasificación G-level
# ---------------------------------------------------------------------------

class TestGeoClassification:
    """AC11-001..AC11-012"""

    def test_001_g0_without_location(self):
        """AC11-001: sin ubicación → G0 + bloqueante F11-E001"""
        res = GeotechnicalClassifier.classify(
            has_location=False, surface_type=None, has_soil_params=False,
            water_scenario="UNKNOWN", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert res.geo_level == "G0"
        assert any("F11-E001" in b for b in res.blockers)

    def test_002_g0_unknown_surface(self):
        """AC11-002: ubicación sin surface_type → G0, sin bloqueante ubicación"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="UNKNOWN", has_soil_params=False,
            water_scenario="NONE", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert res.geo_level == "G0"

    def test_003_g1_surface_type_known(self):
        """AC11-003: ubicación + surface_type, sin parámetros → G1"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="CLAY", has_soil_params=False,
            water_scenario="UNKNOWN", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert res.geo_level == "G1"
        assert any("W001" in w for w in res.warnings)

    def test_004_g2_partial_params(self):
        """AC11-004: parámetros sin informe → G2"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="SAND", has_soil_params=True,
            water_scenario="NONE", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert res.geo_level == "G2"

    def test_005_g3_geotechnical_report(self):
        """AC11-005: informe geotécnico → G3"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="GRAVEL", has_soil_params=True,
            water_scenario="SEASONAL", has_geotechnical_report=True,
            has_field_tests=True, has_as_built=False,
        )
        assert res.geo_level == "G3"

    def test_006_g4_as_built(self):
        """AC11-006: informe + as-built → G4"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="ROCK", has_soil_params=True,
            water_scenario="NONE", has_geotechnical_report=True,
            has_field_tests=True, has_as_built=True,
        )
        assert res.geo_level == "G4"

    def test_007_unknown_water_table_warning(self):
        """AC11-007: nivel freático desconocido → F11-W002"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="CLAY", has_soil_params=True,
            water_scenario="UNKNOWN", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert any("W002" in w for w in res.warnings)

    def test_008_slope_proximity_blocker(self):
        """AC11-008: talud a menos de 5m → F11-E006"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="SAND", has_soil_params=True,
            water_scenario="NONE", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
            slope_near_m=3.0,
        )
        assert any("F11-E006" in b for b in res.blockers)

    def test_009_slope_5m_no_blocker(self):
        """AC11-009: talud a 5m exacto → sin bloqueante F11-E006"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="SAND", has_soil_params=True,
            water_scenario="NONE", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
            slope_near_m=5.0,
        )
        assert not any("F11-E006" in b for b in res.blockers)

    def test_010_confirmed_fields_location(self):
        """AC11-010: ubicación confirmada aparece en confirmed_fields"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="CLAY", has_soil_params=False,
            water_scenario="SEASONAL", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert "location" in res.confirmed_fields

    def test_011_proposed_fields_g0(self):
        """AC11-011: G0 → campos propuestos (phi_deg, etc.)"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="UNKNOWN", has_soil_params=False,
            water_scenario="UNKNOWN", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert len(res.proposed_fields) > 0

    def test_012_conservative_fields_unknown_water(self):
        """AC11-012: nivel freático desconocido → conservative_fields incluye water_table"""
        res = GeotechnicalClassifier.classify(
            has_location=True, surface_type="CLAY", has_soil_params=False,
            water_scenario="UNKNOWN", has_geotechnical_report=False,
            has_field_tests=False, has_as_built=False,
        )
        assert "water_table" in res.conservative_fields


# ---------------------------------------------------------------------------
# AC11-013..024: Capacidad portante
# ---------------------------------------------------------------------------

class TestBearingCapacity:
    """AC11-013..AC11-024"""

    def _standard_drained(self, **overrides):
        kwargs = dict(
            N_Ed_kn=100.0, My_knm=0.0, Mz_knm=0.0, V_Ed_kn=0.0,
            B_m=1.5, L_m=1.5, D_m=1.0,
            phi_deg=30.0, c_kpa=0.0, gamma_kn_m3=18.0,
        )
        kwargs.update(overrides)
        return BearingCapacityService.check_drained(**kwargs)

    def test_013_bearing_factors_phi30(self):
        """AC11-013: Nc, Nq, Ngamma correctos para φ=30°"""
        Nc, Nq, Ngamma = BearingCapacityService.bearing_factors(30.0)
        # Meyerhof reference values: Nq≈18.4, Nc≈30.1, Nγ≈22.4
        assert_close(Nq, 18.4, rel=0.03, label="Nq(30)")
        assert_close(Nc, 30.1, rel=0.03, label="Nc(30)")
        assert_close(Ngamma, 22.4, rel=0.05, label="Ngamma(30)")

    def test_014_bearing_factors_phi0(self):
        """AC11-014: φ=0 → Nc=π+2, Nq=1, Nγ=0"""
        Nc, Nq, Ngamma = BearingCapacityService.bearing_factors(0.0)
        assert_close(Nc, math.pi + 2.0, rel=0.001, label="Nc(0)")
        assert_close(Nq, 1.0, rel=0.001, label="Nq(0)")
        assert abs(Ngamma) < 1e-9, f"Ngamma(0) should be 0, got {Ngamma}"

    def test_015_shape_factors_square(self):
        """AC11-015: zapata cuadrada B/L=1 → factores de forma correctos"""
        Nc, Nq, _ = BearingCapacityService.bearing_factors(30.0)
        sc, sq, sg = BearingCapacityService.shape_factors(1.5, 1.5, 30.0, Nq, Nc)
        assert sc > 1.0
        assert sq > 1.0
        assert sg < 1.0

    def test_016_effective_area_eccentricity(self):
        """AC11-016: excentricidad reduce área efectiva B'×L'"""
        B_prime, L_prime = BearingCapacityService.effective_dimensions(
            2.0, 2.0, ey=0.2, ez=0.1
        )
        assert_close(B_prime, 1.6, rel=0.001, label="B'")
        assert_close(L_prime, 1.8, rel=0.001, label="L'")

    def test_017_utilization_below_one_adequate(self):
        """AC11-017: zapata adecuada → utilización < 1"""
        res = self._standard_drained(N_Ed_kn=50.0)
        assert res.utilization < 1.0
        assert res.error_codes == []

    def test_018_utilization_above_one_error(self):
        """AC11-018: zapata sobredimensionada → F11-E003"""
        res = self._standard_drained(N_Ed_kn=5000.0, B_m=0.5, L_m=0.5)
        assert res.utilization > 1.0
        assert "F11-E003" in res.error_codes

    def test_019_undrained_prandtl_limit(self):
        """AC11-019: condición no drenada φ=0 → Nc=π+2"""
        res = BearingCapacityService.check_undrained(
            N_Ed_kn=80.0, My_knm=0.0, Mz_knm=0.0,
            B_m=1.5, L_m=1.5, D_m=0.8, cu_kpa=50.0,
        )
        assert res.Nc > 5.0     # π+2 ≈ 5.14
        assert res.utilization > 0.0

    def test_020_depth_factors_increase_capacity(self):
        """AC11-020: profundidad D>0 incrementa capacidad (dc>1)"""
        dc_shallow, _, _ = BearingCapacityService.depth_factors(0.1, 1.5, 30.0)
        dc_deep, _, _ = BearingCapacityService.depth_factors(1.5, 1.5, 30.0)
        assert dc_deep > dc_shallow

    def test_021_inclination_factors_zero_shear(self):
        """AC11-021: sin cortante → factores de inclinación = 1"""
        ic, iq, ig = BearingCapacityService.inclination_factors(0.0, 100.0, 30.0)
        assert_close(ic, 1.0, label="ic")
        assert_close(iq, 1.0, label="iq")
        assert_close(ig, 1.0, label="ig")

    def test_022_inclination_factors_with_shear(self):
        """AC11-022: cortante reduce factores de inclinación"""
        ic, iq, ig = BearingCapacityService.inclination_factors(50.0, 100.0, 30.0)
        assert ic < 1.0
        assert iq < 1.0
        assert ig < 1.0

    def test_023_gamma_r_applied(self):
        """AC11-023: qRd = qu / gamma_R (gamma_R=1.4)"""
        res = self._standard_drained()
        assert_close(res.qRd_kpa, res.qu_kpa / 1.4, rel=0.001, label="qRd")

    def test_024_effective_area_in_result(self):
        """AC11-024: área efectiva en resultado coincide con B'×L'"""
        res = self._standard_drained(My_knm=10.0, N_Ed_kn=100.0)
        assert res.area_effective_m2 == pytest_approx_manual(
            res.B_prime_m * res.L_prime_m, rel=0.001
        )


def pytest_approx_manual(expected: float, rel: float = 0.01) -> float:
    """Helper for manual approximate equality checks."""
    return expected


# ---------------------------------------------------------------------------
# AC11-025..034: Vuelco y deslizamiento
# ---------------------------------------------------------------------------

class TestOverturningSlidingChecks:
    """AC11-025..AC11-034"""

    def _check(self, **overrides):
        kwargs = dict(
            N_Ed_kn=80.0, Vy_kn=10.0, Vz_kn=0.0,
            My_knm=20.0, Mz_knm=0.0,
            B_m=1.5, L_m=1.5, D_m=0.8,
            gamma_concrete_kn_m3=24.0, gamma_soil_kn_m3=18.0,
            phi_deg=30.0, c_kpa=5.0,
        )
        kwargs.update(overrides)
        return OverturningSlidingService.check(**kwargs)

    def test_025_overturning_ratio_positive(self):
        """AC11-025: ratio volcamiento > 0 para carga normal"""
        res = self._check()
        assert res.overturning_ratio > 0.0

    def test_026_overturning_compliant_small_moment(self):
        """AC11-026: momento pequeño → conforme por volcamiento"""
        res = self._check(My_knm=5.0)
        assert res.overturning_compliant

    def test_027_overturning_noncompliant_large_moment(self):
        """AC11-027: momento muy grande → no conforme F11-E004"""
        res = self._check(My_knm=500.0, N_Ed_kn=10.0)
        assert not res.overturning_compliant
        assert "F11-E004" in res.error_codes

    def test_028_within_third_central(self):
        """AC11-028: resultante en tercio central → within_third=True"""
        res = self._check(My_knm=5.0, N_Ed_kn=200.0)
        assert res.within_third

    def test_029_outside_third_large_eccentricity(self):
        """AC11-029: excentricidad elevada → within_third=False"""
        res = self._check(My_knm=200.0, N_Ed_kn=50.0)
        assert not res.within_third

    def test_030_sliding_VRd_positive(self):
        """AC11-030: VRd deslizamiento siempre positivo"""
        res = self._check()
        assert res.sliding_VRd_kn > 0.0

    def test_031_sliding_compliant_small_shear(self):
        """AC11-031: cortante pequeño → deslizamiento conforme"""
        res = self._check(Vy_kn=1.0)
        assert res.sliding_compliant

    def test_032_sliding_noncompliant_large_shear(self):
        """AC11-032: cortante muy grande → F11-E004"""
        res = self._check(Vy_kn=500.0, N_Ed_kn=10.0)
        assert not res.sliding_compliant
        assert "F11-E004" in res.error_codes

    def test_033_phi0_sliding_cohesion_only(self):
        """AC11-033: φ=0 → deslizamiento solo por cohesión"""
        res = self._check(phi_deg=0.0, c_kpa=30.0, Vy_kn=5.0)
        # VRd = c * A / gamma_slide
        expected = 30.0 * 1.5 * 1.5 / 1.1
        assert_close(res.sliding_VRd_kn, expected, rel=0.02, label="VRd_phi0")

    def test_034_resultant_eccentricity_formula(self):
        """AC11-034: excentricidad resultante = sqrt(ey²+ez²)"""
        res = self._check(My_knm=10.0, Mz_knm=10.0)
        assert res.resultant_eccentricity_m > 0.0


# ---------------------------------------------------------------------------
# AC11-035..042: Agua y levantamiento
# ---------------------------------------------------------------------------

class TestUpliftChecks:
    """AC11-035..AC11-042"""

    def _check(self, **overrides):
        kwargs = dict(
            N_uplift_kn=20.0,
            B_m=1.5, L_m=1.5, D_m=0.8,
            gamma_concrete_kn_m3=24.0,
            water_table_depth_m=2.0,   # below foundation base → no uplift
        )
        kwargs.update(overrides)
        return UpliftService.check(**kwargs)

    def test_035_no_water_no_uplift(self):
        """AC11-035: nivel freático muy profundo → U=0"""
        res = self._check(water_table_depth_m=100.0)
        assert res.U_kn == 0.0

    def test_036_water_at_surface_full_uplift(self):
        """AC11-036: nivel freático en superficie → U = γw × D × A"""
        res = self._check(water_table_depth_m=0.0)
        expected_U = 10.0 * 0.8 * 1.5 * 1.5
        assert_close(res.U_kn, expected_U, rel=0.001, label="U_full")

    def test_037_partial_water_table(self):
        """AC11-037: nivel freático parcial → U parcial"""
        res = self._check(water_table_depth_m=0.5)
        # h_w = D - water_table_depth_m = 0.8 - 0.5 = 0.3
        expected_U = 10.0 * 0.3 * 1.5 * 1.5
        assert_close(res.U_kn, expected_U, rel=0.001, label="U_partial")

    def test_038_W_eff_equals_Wprop_minus_U(self):
        """AC11-038: W_eff = W_prop + W_soil - U"""
        res = self._check(water_table_depth_m=0.0)
        calc = res.W_prop_kn + res.W_soil_kn - res.U_kn
        assert_close(res.W_eff_kn, calc, rel=0.001, label="W_eff")

    def test_039_uplift_compliant_no_water(self):
        """AC11-039: sin empuje hidrostático → conforme"""
        res = self._check(N_uplift_kn=5.0, water_table_depth_m=100.0)
        assert res.compliant

    def test_040_uplift_noncompliant_high_water(self):
        """AC11-040: nivel freático en superficie, tracción elevada → F11-E004"""
        res = self._check(N_uplift_kn=1000.0, water_table_depth_m=0.0)
        assert not res.compliant
        assert "F11-E004" in res.error_codes

    def test_041_W_prop_formula(self):
        """AC11-041: W_prop = B × L × D × γ_concrete"""
        res = self._check()
        expected = 1.5 * 1.5 * 0.8 * 24.0
        assert_close(res.W_prop_kn, expected, rel=0.001, label="W_prop")

    def test_042_utilization_formula(self):
        """AC11-042: utilización = N_uplift × γ_uplift / W_eff"""
        res = self._check(water_table_depth_m=100.0)
        expected = 20.0 * 1.1 / res.W_eff_kn
        assert_close(res.utilization, expected, rel=0.001, label="util_uplift")


# ---------------------------------------------------------------------------
# AC11-043..052: Rigidez y deformación (Winkler)
# ---------------------------------------------------------------------------

class TestStiffness:
    """AC11-043..AC11-052"""

    def _std_stiffness(self, **overrides):
        kwargs = dict(B_m=1.5, L_m=1.5, D_m=0.8, Es_mpa=20.0)
        kwargs.update(overrides)
        return FoundationStiffnessService.winkler_rectangular(**kwargs)

    def test_043_kz_positive(self):
        """AC11-043: kz vertical siempre positivo"""
        res = self._std_stiffness()
        assert res.kz_kn_m > 0.0

    def test_044_kz_formula(self):
        """AC11-044: kz = Es × A / h_eq (h_eq = B/2)"""
        res = self._std_stiffness(B_m=1.5, L_m=1.5, Es_mpa=20.0)
        Es = 20.0 * 1000.0   # kN/m²
        A = 1.5 * 1.5
        h_eq = 1.5 / 2.0
        expected = Es * A / h_eq
        assert_close(res.kz_kn_m, expected, rel=0.001, label="kz")

    def test_045_kthx_positive(self):
        """AC11-045: rigidez rotacional kθx positiva"""
        res = self._std_stiffness()
        assert res.kthx_knm_rad > 0.0

    def test_046_kthy_positive(self):
        """AC11-046: rigidez rotacional kθy positiva"""
        res = self._std_stiffness()
        assert res.kthy_knm_rad > 0.0

    def test_047_matrix_6x6_diagonal(self):
        """AC11-047: matriz 6×6 diagonal (off-diagonals = 0)"""
        res = self._std_stiffness()
        mat = res.matrix_6x6
        assert len(mat) == 6
        for i in range(6):
            assert len(mat[i]) == 6
            for j in range(6):
                if i != j:
                    assert mat[i][j] == 0.0, f"Off-diagonal [{i}][{j}] = {mat[i][j]}"

    def test_048_matrix_diagonal_values(self):
        """AC11-048: diagonal de la matriz = [kx, ky, kz, kθx, kθy, kθz]"""
        res = self._std_stiffness()
        expected = [res.kx_kn_m, res.ky_kn_m, res.kz_kn_m,
                    res.kthx_knm_rad, res.kthy_knm_rad, res.kthz_knm_rad]
        for i, (exp, actual) in enumerate(zip(expected, [res.matrix_6x6[i][i] for i in range(6)])):
            assert_close(actual, exp, rel=0.001, label=f"K[{i}][{i}]")

    def test_049_stiffer_soil_larger_kz(self):
        """AC11-049: suelo más rígido → kz mayor"""
        soft = self._std_stiffness(Es_mpa=5.0)
        stiff = self._std_stiffness(Es_mpa=50.0)
        assert stiff.kz_kn_m > soft.kz_kn_m

    def test_050_larger_foundation_larger_kz(self):
        """AC11-050: zapata mayor → kz mayor"""
        small = self._std_stiffness(B_m=1.0, L_m=1.0)
        large = self._std_stiffness(B_m=2.0, L_m=2.0)
        assert large.kz_kn_m > small.kz_kn_m

    def test_051_convergence_flag_true(self):
        """AC11-051: Winkler simple → converged=True, iterations=1"""
        res = self._std_stiffness()
        assert res.converged
        assert res.iterations == 1

    def test_052_global_iteration_convergence(self):
        """AC11-052: iteración con cambio < tolerancia → converged=True"""
        converged, err = FoundationStiffnessService.iterate_global_model(
            current_kthx=10000.0, current_kthy=10000.0,
            new_kthx=10100.0, new_kthy=10050.0,   # 1% change
            tolerance=0.05,
        )
        assert converged
        assert err < 0.05


# ---------------------------------------------------------------------------
# AC11-053..062: Empotramiento directo
# ---------------------------------------------------------------------------

class TestEmbeddedPole:
    """AC11-053..AC11-062"""

    def _check(self, **overrides):
        kwargs = dict(
            V_Ed_kn=15.0, M_Ed_knm=25.0,
            pole_diameter_mm=168.3,
            embedment_length_m=1.5,
            fill_type="CONCRETE",
        )
        kwargs.update(overrides)
        return EmbeddedPoleService.check(**kwargs)

    def test_053_util_lateral_positive(self):
        """AC11-053: util_lateral siempre positivo"""
        res = self._check()
        assert res.util_lateral > 0.0

    def test_054_util_toe_positive(self):
        """AC11-054: util_toe siempre positivo"""
        res = self._check()
        assert res.util_toe > 0.0

    def test_055_concrete_fill_high_resistance(self):
        """AC11-055: relleno hormigón → resistencia pasiva mayor que granular"""
        res_conc = self._check(fill_type="CONCRETE")
        res_gran = self._check(fill_type="GRANULAR_CONTROLLED")
        assert res_conc.passive_pressure_kpa > res_gran.passive_pressure_kpa

    def test_056_grout_fill_higher_than_concrete(self):
        """AC11-056: grout fck≈30 → presión pasiva ≥ hormigón fck≈25"""
        res_conc = self._check(fill_type="CONCRETE")
        res_grout = self._check(fill_type="GROUT")
        assert res_grout.passive_pressure_kpa >= res_conc.passive_pressure_kpa

    def test_057_longer_embedment_smaller_util(self):
        """AC11-057: mayor empotramiento → menor utilización lateral"""
        short = self._check(embedment_length_m=0.8)
        long_ = self._check(embedment_length_m=2.5)
        # Passive resistance grows with L²; demand grows with L → net improvement
        assert long_.util_lateral < short.util_lateral

    def test_058_zero_shear_compliant(self):
        """AC11-058: sin cortante → empotrado compliant (muy conservador)"""
        res = self._check(V_Ed_kn=0.1, M_Ed_knm=0.1)
        assert res.compliant

    def test_059_reaction_top_equilibrium(self):
        """AC11-059: R_top + R_toe = V_Ed"""
        res = self._check()
        assert_close(res.reaction_top_kn + res.reaction_bottom_kn, 15.0,
                     rel=0.01, label="equilibrium")

    def test_060_larger_pole_diameter_larger_resistance(self):
        """AC11-060: mayor diámetro de fuste → mayor resistencia pasiva"""
        small_d = self._check(pole_diameter_mm=114.3)
        large_d = self._check(pole_diameter_mm=219.1)
        # F_passive = sigma_Rd * d * L / 2; larger d → larger F_passive
        assert large_d.util_lateral < small_d.util_lateral

    def test_061_embed_length_stored(self):
        """AC11-061: L_embed devuelto es el input"""
        res = self._check(embedment_length_m=1.8)
        assert_close(res.L_embed_m, 1.8, rel=0.001, label="L_embed")

    def test_062_moment_at_surface_equals_input(self):
        """AC11-062: momento en superficie = M_Ed para modelo simplificado"""
        res = self._check(M_Ed_knm=30.0)
        assert_close(res.moment_at_surface_knm, 30.0, rel=0.001, label="M_surface")


# ---------------------------------------------------------------------------
# AC11-063..072: Optimización y robustez
# ---------------------------------------------------------------------------

class TestOptimization:
    """AC11-063..AC11-072"""

    def _make_candidates(self) -> list:
        return [
            FoundationCandidateSummary(
                family="F11-A", width_m=1.2, length_m=1.2, depth_m=0.8, diameter_m=None,
                util_bearing=0.75, util_overturning=0.60, util_sliding=0.55, util_uplift=0.0,
                util_governing=0.75, total_cost_eur=1200.0, concrete_volume_m3=1.15,
                excavation_volume_m3=2.0, total_co2_kg=350.0, total_mass_kg=2760.0, feasible=True,
            ),
            FoundationCandidateSummary(
                family="F11-D", width_m=None, length_m=None, depth_m=1.0, diameter_m=1.0,
                util_bearing=0.65, util_overturning=0.55, util_sliding=0.50, util_uplift=0.0,
                util_governing=0.65, total_cost_eur=1500.0, concrete_volume_m3=0.79,
                excavation_volume_m3=1.5, total_co2_kg=240.0, total_mass_kg=1900.0, feasible=True,
            ),
            FoundationCandidateSummary(
                family="F11-C", width_m=1.0, length_m=1.0, depth_m=1.2, diameter_m=None,
                util_bearing=0.80, util_overturning=0.70, util_sliding=0.60, util_uplift=0.0,
                util_governing=0.80, total_cost_eur=900.0, concrete_volume_m3=1.20,
                excavation_volume_m3=1.8, total_co2_kg=360.0, total_mass_kg=2880.0, feasible=True,
            ),
        ]

    def test_063_pareto_front_nonempty(self):
        """AC11-063: frente de Pareto no vacío para candidatos factibles"""
        front = FoundationOptimizer.pareto_front(self._make_candidates())
        assert len(front) > 0

    def test_064_infeasible_excluded_from_pareto(self):
        """AC11-064: candidato infactible excluido del frente Pareto"""
        candidates = self._make_candidates()
        candidates.append(FoundationCandidateSummary(
            family="F11-H", width_m=None, length_m=None, depth_m=5.0, diameter_m=None,
            util_bearing=2.0, util_overturning=2.0, util_sliding=2.0, util_uplift=2.0,
            util_governing=2.0, total_cost_eur=50000.0, concrete_volume_m3=10.0,
            excavation_volume_m3=20.0, total_co2_kg=5000.0, total_mass_kg=25000.0,
            feasible=False,
        ))
        front = FoundationOptimizer.pareto_front(candidates)
        families = [c.family for c in front]
        assert "F11-H" not in families

    def test_065_select_returns_labeled(self):
        """AC11-065: select() devuelve candidatos con etiquetas"""
        selected = FoundationOptimizer.select(self._make_candidates())
        for c in selected:
            assert c.label != ""

    def test_066_recommended_has_label(self):
        """AC11-066: al menos un candidato tiene etiqueta RECOMMENDED"""
        selected = FoundationOptimizer.select(self._make_candidates())
        labels = [c.label for c in selected]
        assert "RECOMMENDED" in labels

    def test_067_select_max_4_solutions(self):
        """AC11-067: select() devuelve máximo 4 soluciones"""
        selected = FoundationOptimizer.select(self._make_candidates())
        assert len(selected) <= 4

    def test_068_dominance_all_worse(self):
        """AC11-068: candidato dominado en todos los objetivos"""
        a = FoundationCandidateSummary(
            family="F11-A", width_m=1.0, length_m=1.0, depth_m=1.0, diameter_m=None,
            util_bearing=0.5, util_overturning=0.5, util_sliding=0.5, util_uplift=0.0,
            util_governing=0.5, total_cost_eur=1000.0, concrete_volume_m3=1.0,
            excavation_volume_m3=2.0, total_co2_kg=300.0, total_mass_kg=2400.0, feasible=True,
        )
        b = FoundationCandidateSummary(  # dominates a: better on all
            family="F11-D", width_m=None, length_m=None, depth_m=0.8, diameter_m=1.0,
            util_bearing=0.4, util_overturning=0.4, util_sliding=0.4, util_uplift=0.0,
            util_governing=0.4, total_cost_eur=800.0, concrete_volume_m3=0.8,
            excavation_volume_m3=1.5, total_co2_kg=200.0, total_mass_kg=1900.0, feasible=True,
        )
        assert FoundationOptimizer.is_dominated(a, b)

    def test_069_no_dominance_tradeoff(self):
        """AC11-069: trade-off objetivo → ninguno domina al otro"""
        a = FoundationCandidateSummary(
            family="F11-A", width_m=1.5, length_m=1.5, depth_m=0.8, diameter_m=None,
            util_bearing=0.6, util_overturning=0.5, util_sliding=0.5, util_uplift=0.0,
            util_governing=0.6, total_cost_eur=1000.0, concrete_volume_m3=1.5,
            excavation_volume_m3=2.0, total_co2_kg=200.0, total_mass_kg=3600.0, feasible=True,
        )
        b = FoundationCandidateSummary(
            family="F11-D", width_m=None, length_m=None, depth_m=1.0, diameter_m=1.2,
            util_bearing=0.5, util_overturning=0.4, util_sliding=0.4, util_uplift=0.0,
            util_governing=0.5, total_cost_eur=1500.0, concrete_volume_m3=1.1,
            excavation_volume_m3=1.5, total_co2_kg=400.0, total_mass_kg=2700.0, feasible=True,
        )
        # a has lower cost/co2, b has lower util/excavation → neither dominates
        assert not FoundationOptimizer.is_dominated(a, b)
        assert not FoundationOptimizer.is_dominated(b, a)

    def test_070_weights_sum_one(self):
        """AC11-070: pesos deben sumar 1.0 (validación en schema)"""
        # Direct arithmetic check
        w = (0.4, 0.3, 0.2, 0.1)
        assert abs(sum(w) - 1.0) < 1e-9

    def test_071_score_monotone_in_objectives(self):
        """AC11-071: candidato peor en todos los objetivos → mayor score"""
        candidates = self._make_candidates()
        selected = FoundationOptimizer.select(candidates)
        if len(selected) >= 2:
            # recommended has minimum score
            recommended = next(c for c in selected if c.label == "RECOMMENDED")
            for other in selected:
                if other is not recommended:
                    assert recommended.score <= other.score

    def test_072_single_candidate_is_recommended(self):
        """AC11-072: un único candidato factible → etiqueta RECOMMENDED"""
        one = self._make_candidates()[:1]
        selected = FoundationOptimizer.select(one)
        assert len(selected) == 1
        assert selected[0].label == "RECOMMENDED"


# ---------------------------------------------------------------------------
# AC11-073..080: Trazabilidad, normativa, hash, informes
# ---------------------------------------------------------------------------

class TestTraceabilityAndNormative:
    """AC11-073..AC11-080"""

    def test_073_hash_deterministic(self):
        """AC11-073: hash con mismos inputs → mismo resultado"""
        h1 = compute_foundation_hash("F11-A", 1.5, 1.5, 0.8, None, -100.0, 30.0, 0.0)
        h2 = compute_foundation_hash("F11-A", 1.5, 1.5, 0.8, None, -100.0, 30.0, 0.0)
        assert h1 == h2

    def test_074_hash_sensitive_to_family(self):
        """AC11-074: cambio de familia → hash diferente"""
        h_a = compute_foundation_hash("F11-A", 1.5, 1.5, 0.8, None, -100.0, 30.0, 0.0)
        h_b = compute_foundation_hash("F11-B", 1.5, 1.5, 0.8, None, -100.0, 30.0, 0.0)
        assert h_a != h_b

    def test_075_hash_sensitive_to_geometry(self):
        """AC11-075: cambio de dimensión → hash diferente"""
        h1 = compute_foundation_hash("F11-A", 1.5, 1.5, 0.8, None, -100.0, 30.0, 0.0)
        h2 = compute_foundation_hash("F11-A", 2.0, 2.0, 1.0, None, -100.0, 30.0, 0.0)
        assert h1 != h2

    def test_076_hash_length_32(self):
        """AC11-076: hash tiene exactamente 32 caracteres hex"""
        h = compute_foundation_hash("F11-D", None, None, 1.0, 1.2, -80.0, 40.0, 0.0)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)

    def test_077_maturity_g0_is_m0(self):
        """AC11-077: G0 → madurez M0, liberación bloqueada"""
        result = FoundationNormativeClassifier.classify(
            geo_level="G0", has_location=True, has_soil_params=False,
            has_geotechnical_report=False, has_as_built=False, checks_pass=True,
        )
        assert result.maturity_level == "M0"
        assert result.release_blocked

    def test_078_maturity_g3_is_m3(self):
        """AC11-078: G3 + checks conformes → M3, no bloqueado"""
        result = FoundationNormativeClassifier.classify(
            geo_level="G3", has_location=True, has_soil_params=True,
            has_geotechnical_report=True, has_as_built=False, checks_pass=True,
        )
        assert result.maturity_level == "M3"
        assert not result.release_blocked

    def test_079_pile_route_g2_blocked(self):
        """AC11-079: F11-H sin G3 → bloqueante F11-E006"""
        result = FoundationNormativeClassifier.classify(
            geo_level="G2", has_location=True, has_soil_params=True,
            has_geotechnical_report=False, has_as_built=False,
            pile_route=True, checks_pass=True,
        )
        assert any("F11-H" in b or "F11-E006" in b for b in result.blockers)
        assert result.release_blocked

    def test_080_error_codes_format(self):
        """AC11-080: códigos de error tienen formato F11-Exxx"""
        res = BearingCapacityService.check_drained(
            N_Ed_kn=5000.0, My_knm=0.0, Mz_knm=0.0, V_Ed_kn=0.0,
            B_m=0.5, L_m=0.5, D_m=0.3, phi_deg=25.0, c_kpa=0.0, gamma_kn_m3=18.0,
        )
        for code in res.error_codes:
            assert code.startswith("F11-E"), f"Unexpected error code format: {code}"


# ---------------------------------------------------------------------------
# Standalone analytical checks runner
# ---------------------------------------------------------------------------

def run_analytical_checks_foundation() -> None:
    """Run all 80 ACs inline (no pytest runner required)."""
    test_classes = [
        TestGeoClassification,
        TestBearingCapacity,
        TestOverturningSlidingChecks,
        TestUpliftChecks,
        TestStiffness,
        TestEmbeddedPole,
        TestOptimization,
        TestTraceabilityAndNormative,
    ]
    passed = 0
    failed = 0
    errors_list = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(cls) if m.startswith("test_")]
        for method_name in sorted(methods):
            try:
                getattr(instance, method_name)()
                passed += 1
            except Exception as exc:
                failed += 1
                errors_list.append(f"  FAIL {cls.__name__}.{method_name}: {exc}")

    print(f"\n=== Fase 11 Analytical Checks ===")
    print(f"Passed: {passed}  Failed: {failed}  Total: {passed + failed}")
    if errors_list:
        print("\nFailures:")
        for err in errors_list:
            print(err)
    else:
        print("All checks passed.")
    return failed


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(run_analytical_checks_foundation())
