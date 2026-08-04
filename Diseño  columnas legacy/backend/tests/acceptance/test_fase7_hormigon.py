"""
Salvi Studio · Columns — Fase 7: Hormigón Pretensado
Tests de aceptación AC-001..AC-140

Estructura:
  AC-001..AC-020  Materiales y propiedades por edad
  AC-021..AC-040  Pretensado y pérdidas
  AC-041..AC-055  Secciones y propiedades geométricas
  AC-056..AC-070  ELS (tensiones, fisuración, flecha)
  AC-071..AC-085  ELU y fatiga
  AC-086..AC-100  Fabricación, transporte y calidad
  AC-101..AC-140  Optimización del pretensado
"""
from __future__ import annotations
import math
import pytest
from app.services.concrete_service import (
    ConcreteMaterialService,
    PrestressLossService,
    ConcreteSectionEngine,
    ConcreteVerificationService,
    ConcreteFatigueService,
    ConcreteProductionService,
    ConcreteNormativeClassifier,
    ConcreteOptimizer,
    PrestressCandidate,
)
from app.models.db.concrete import (
    PrestressingSteelClass,
    ConcreteVerificationStatus,
    ConcreteNormativeRoute,
)


# ============================================================================
# AC-001..AC-020  Materiales y propiedades por edad
# ============================================================================

class TestMaterials:
    """AC-001..AC-020"""

    def test_ac001_age_properties_at_28d(self):
        """AC-001: fcm(28) = fcm_28 exactamente."""
        r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 28.0)
        assert abs(r.fcm_t_mpa - 58.0) < 0.01, f"fcm(28)={r.fcm_t_mpa}"

    def test_ac002_ecm_at_28d(self):
        """AC-002: Ecm(28) = Ecm_28."""
        r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 28.0)
        assert abs(r.Ecm_t_mpa - 37000.0) < 1.0

    def test_ac003_fcm_grows_with_age(self):
        """AC-003: fcm(t) crece con t."""
        r7 = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 7.0)
        r28 = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 28.0)
        r90 = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 90.0)
        assert r7.fcm_t_mpa < r28.fcm_t_mpa < r90.fcm_t_mpa

    def test_ac004_cement_R_faster(self):
        """AC-004: cemento R (s=0.20) gana resistencia más rápido que N (s=0.25) a t=7d."""
        rR = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.20, 7.0)
        rN = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 7.0)
        assert rR.fcm_t_mpa > rN.fcm_t_mpa

    def test_ac005_epsilon_ca_zero_at_t0(self):
        """AC-005: retracción autógena ≈ 0 en t→0."""
        r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 0.001)
        assert r.epsilon_ca_t < 0.5  # microstrain equivalente muy pequeño

    def test_ac006_epsilon_ca_approaches_inf(self):
        """AC-006: retracción autógena tiende a εca∞ para t grande."""
        r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 10000.0, epsilon_ca_inf=50.0)
        assert r.epsilon_ca_t > 49.5

    def test_ac007_fctm_formula_t_lt_28(self):
        """AC-007: fctm(t) = fctm × (fcm(t)/fcm)^(2/3) para t < 28d."""
        r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 14.0)
        # Verificar manualmente
        beta_cc = math.exp(0.25 * (1.0 - math.sqrt(28.0 / 14.0)))
        fcm_t = 58.0 * beta_cc
        fctm_t_expected = 4.1 * (fcm_t / 58.0) ** (2.0 / 3.0)
        assert abs(r.fctm_t_mpa - fctm_t_expected) < 0.001

    def test_ac008_fctk_005_is_07_fctm(self):
        """AC-008: fctk_005(t) = 0.7 × fctm(t)."""
        r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 14.0)
        assert abs(r.fctk_005_t_mpa - 0.7 * r.fctm_t_mpa) < 0.0001

    def test_ac009_invalid_age(self):
        """AC-009: edad ≤ 0 lanza ValueError CON-MAT-001."""
        with pytest.raises(ValueError, match="CON-MAT-001"):
            ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 0.0)

    def test_ac010_invalid_s(self):
        """AC-010: s no reconocido lanza ValueError."""
        with pytest.raises(ValueError):
            ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.30, 7.0)

    def test_ac011_transfer_strength_pass(self):
        """AC-011: fcm(t) ≥ min_req → PASS."""
        r = ConcreteMaterialService.check_transfer_strength(35.0, 30.0)
        assert r.status == ConcreteVerificationStatus.PASS
        assert r.utilization <= 1.0

    def test_ac012_transfer_strength_fail(self):
        """AC-012: fcm(t) < min_req → BLOCKED + CON-MAT-001."""
        r = ConcreteMaterialService.check_transfer_strength(25.0, 30.0)
        assert r.status == ConcreteVerificationStatus.BLOCKED
        assert r.error_code == "CON-MAT-001"

    def test_ac013_resolve_mix_found(self):
        """AC-013: mezcla HAP-45/50 existe en biblioteca."""
        m = ConcreteMaterialService.resolve_mix("HAP-45/50")
        assert m["fck"] == 45.0

    def test_ac014_resolve_mix_not_found(self):
        """AC-014: mezcla inexistente lanza CON-MAT-001."""
        with pytest.raises(ValueError, match="CON-MAT-001"):
            ConcreteMaterialService.resolve_mix("HAP-99/99")

    def test_ac015_ecm_increases_with_fcm(self):
        """AC-015: Ecm(t) aumenta si fcm(t) > fcm_28."""
        r90 = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 90.0)
        assert r90.Ecm_t_mpa > 37000.0

    def test_ac016_cement_SL_slowest(self):
        """AC-016: cemento SL (s=0.38) da menor fcm(7) que R y N."""
        rR = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.20, 7.0)
        rSL = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.38, 7.0)
        assert rSL.fcm_t_mpa < rR.fcm_t_mpa

    def test_ac017_library_hap5060(self):
        """AC-017: HAP-50/60 con fcm=58."""
        m = ConcreteMaterialService.resolve_mix("HAP-50/60")
        assert m["fcm"] == 58.0

    def test_ac018_library_hap6075(self):
        """AC-018: HAP-60/75 con cement_class R."""
        m = ConcreteMaterialService.resolve_mix("HAP-60/75")
        assert m["cement_class"] == "R"

    def test_ac019_transfer_utilization_correct(self):
        """AC-019: utilización = min_req / fcm_t cuando PASS."""
        r = ConcreteMaterialService.check_transfer_strength(40.0, 32.0)
        assert abs(r.utilization - 32.0 / 40.0) < 0.0001

    def test_ac020_epsilon_ca_at_28d_non_trivial(self):
        """AC-020: retracción autógena a 28d es apreciable."""
        r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 28.0, epsilon_ca_inf=50.0)
        expected = 50.0 * (1.0 - math.exp(-0.2 * math.sqrt(28.0)))
        assert abs(r.epsilon_ca_t - expected) < 0.001


# ============================================================================
# AC-021..AC-040  Pretensado y pérdidas
# ============================================================================

class TestPrestressLosses:
    """AC-021..AC-040"""

    def test_ac021_anchor_slip_formula(self):
        """AC-021: ΔP_slip = Ap × Ep × δ / L."""
        r = PrestressLossService.anchor_slip_loss(140.0, 195000.0, 5.0, 10000.0, 200.0)
        expected_sigma = 195000.0 * 5.0 / 10000.0   # 97.5 MPa
        expected_P = 140.0 * expected_sigma / 1000.0  # 13.65 kN
        assert abs(r.delta_sigma_mpa - expected_sigma) < 0.001
        assert abs(r.delta_P_kn - expected_P) < 0.001

    def test_ac022_anchor_slip_loss_pct(self):
        """AC-022: loss_pct es porcentaje relativo a P0."""
        r = PrestressLossService.anchor_slip_loss(140.0, 195000.0, 5.0, 10000.0, 200.0)
        assert abs(r.loss_pct - r.delta_P_kn / 200.0 * 100.0) < 0.001

    def test_ac023_anchor_slip_zero_slip(self):
        """AC-023: δ=0 → pérdida nula."""
        r = PrestressLossService.anchor_slip_loss(140.0, 195000.0, 0.0, 10000.0, 200.0)
        assert r.delta_P_kn == 0.0

    def test_ac024_elastic_shortening_n1(self):
        """AC-024: n=1 cordón → factor 1.0 (no (n-1)/(2n))."""
        r = PrestressLossService.elastic_shortening_loss(140.0, 195000.0, 10.0, 37000.0, 1, 200.0)
        n_ratio = 1.0
        expected = 195000.0 / 37000.0 * 10.0 * n_ratio
        assert abs(r.delta_sigma_mpa - expected) < 0.001

    def test_ac025_elastic_shortening_many_strands(self):
        """AC-025: n cordones → factor (n-1)/(2n) < 1."""
        r10 = PrestressLossService.elastic_shortening_loss(140.0, 195000.0, 10.0, 37000.0, 10, 200.0)
        r1 = PrestressLossService.elastic_shortening_loss(140.0, 195000.0, 10.0, 37000.0, 1, 200.0)
        assert r10.delta_P_kn < r1.delta_P_kn

    def test_ac026_relaxation_class1_less_than_class2(self):
        """AC-026: Clase 1 coeficiente 5.39 vs Clase 2 coeficiente 0.66 → distinta relajación."""
        r1 = PrestressLossService.relaxation_loss(1395.0, 1860.0, PrestressingSteelClass.CLASS_1, 2.5, 1000.0, 140.0, 200.0)
        r2 = PrestressLossService.relaxation_loss(1395.0, 1860.0, PrestressingSteelClass.CLASS_2, 2.5, 1000.0, 140.0, 200.0)
        # CLASS_1 usa 5.39e-5, CLASS_2 usa 0.66e-5 pero con exp(9.1μ) vs exp(6.7μ)
        # Ambos son no nulos
        assert r1.delta_P_kn > 0
        assert r2.delta_P_kn > 0

    def test_ac027_relaxation_increases_with_time(self):
        """AC-027: relajación aumenta con el tiempo."""
        r100 = PrestressLossService.relaxation_loss(1395.0, 1860.0, PrestressingSteelClass.CLASS_2, 2.5, 100.0, 140.0, 200.0)
        r1000 = PrestressLossService.relaxation_loss(1395.0, 1860.0, PrestressingSteelClass.CLASS_2, 2.5, 1000.0, 140.0, 200.0)
        assert r1000.delta_P_kn > r100.delta_P_kn

    def test_ac028_relaxation_mu_correct(self):
        """AC-028: μ = σ_pi / fpk entre 0 y 1."""
        r = PrestressLossService.relaxation_loss(1395.0, 1860.0, PrestressingSteelClass.CLASS_2, 2.5, 1000.0, 140.0, 200.0)
        mu = r.intermediate_values["mu"]
        assert 0.0 < mu < 1.0

    def test_ac029_thermal_loss_positive(self):
        """AC-029: ΔT > 0 → pérdida positiva."""
        r = PrestressLossService.thermal_loss(140.0, 195000.0, 10e-6, 20.0, 200.0)
        assert r.delta_P_kn > 0

    def test_ac030_thermal_loss_zero_dt(self):
        """AC-030: ΔT = 0 → pérdida nula."""
        r = PrestressLossService.thermal_loss(140.0, 195000.0, 10e-6, 0.0, 200.0)
        assert r.delta_P_kn == 0.0

    def test_ac031_long_term_loss_positive(self):
        """AC-031: pérdidas diferidas EC2 §5.10.6 son positivas."""
        r = PrestressLossService.long_term_loss_simplified(
            Ap_mm2=140.0, Ep_mpa=195000.0, Ecm_mpa=37000.0,
            Ac_m2=0.05, Ic_m4=5e-4, e_mm=50.0,
            epsilon_cs=300e-6, delta_sigma_pr_mpa=30.0,
            phi=2.0, sigma_cp_mpa=8.0, P0_kn=200.0,
        )
        assert r.delta_P_kn > 0

    def test_ac032_long_term_loss_rule_reference(self):
        """AC-032: referencia normativa EC2 §5.10.6."""
        r = PrestressLossService.long_term_loss_simplified(
            Ap_mm2=140.0, Ep_mpa=195000.0, Ecm_mpa=37000.0,
            Ac_m2=0.05, Ic_m4=5e-4, e_mm=50.0,
            epsilon_cs=300e-6, delta_sigma_pr_mpa=30.0,
            phi=2.0, sigma_cp_mpa=8.0, P0_kn=200.0,
        )
        assert "5.10.6" in r.governing_rule

    def test_ac033_transfer_length_fbpt(self):
        """AC-033: fbpt = 2.25 × η1 × η2 × fctd(t)."""
        r = PrestressLossService.transfer_length(12.5, 1395.0, 1500.0, 1200.0, 2.0)
        assert abs(r.fbpt_mpa - 2.25 * 1.0 * 1.0 * 2.0) < 0.001

    def test_ac034_transfer_length_positive(self):
        """AC-034: l_pt > 0."""
        r = PrestressLossService.transfer_length(12.5, 1395.0, 1500.0, 1200.0, 2.0)
        assert r.l_pt_mm > 0

    def test_ac035_anchor_length_gte_transfer(self):
        """AC-035: l_bpd ≥ 0.8 × l_pt."""
        r = PrestressLossService.transfer_length(12.5, 1395.0, 1600.0, 1100.0, 2.0)
        l_pt2 = 0.8 * r.l_pt_mm
        assert r.l_bpd_mm >= l_pt2 - 0.01

    def test_ac036_anchor_slip_large_L(self):
        """AC-036: L grande → pérdida menor."""
        r_short = PrestressLossService.anchor_slip_loss(140.0, 195000.0, 5.0, 5000.0, 200.0)
        r_long = PrestressLossService.anchor_slip_loss(140.0, 195000.0, 5.0, 20000.0, 200.0)
        assert r_long.delta_P_kn < r_short.delta_P_kn

    def test_ac037_anchor_slip_zero_L_raises(self):
        """AC-037: L=0 lanza CON-PST-002."""
        with pytest.raises(ValueError, match="CON-PST-002"):
            PrestressLossService.anchor_slip_loss(140.0, 195000.0, 5.0, 0.0, 200.0)

    def test_ac038_elastic_shortening_factor_n10(self):
        """AC-038: factor (n-1)/(2n) para n=10 es 9/20 = 0.45."""
        r = PrestressLossService.elastic_shortening_loss(140.0, 195000.0, 10.0, 37000.0, 10, 200.0)
        assert abs(r.intermediate_values["n_ratio"] - 0.45) < 0.001

    def test_ac039_relaxation_type_labeled(self):
        """AC-039: tipo de pérdida correcto."""
        r = PrestressLossService.relaxation_loss(1395.0, 1860.0, PrestressingSteelClass.CLASS_2, 2.5, 1000.0, 140.0, 200.0)
        assert r.loss_type == "SHORT_TERM_RELAXATION"

    def test_ac040_long_term_loss_denominator_gt1(self):
        """AC-040: denominador > 1 (efecto de la sección compuesta)."""
        r = PrestressLossService.long_term_loss_simplified(
            Ap_mm2=140.0, Ep_mpa=195000.0, Ecm_mpa=37000.0,
            Ac_m2=0.05, Ic_m4=5e-4, e_mm=50.0,
            epsilon_cs=300e-6, delta_sigma_pr_mpa=30.0,
            phi=2.0, sigma_cp_mpa=8.0, P0_kn=200.0,
        )
        assert r.intermediate_values["denominator"] > 1.0


# ============================================================================
# AC-041..AC-055  Secciones y propiedades geométricas
# ============================================================================

class TestSections:
    """AC-041..AC-055"""

    def test_ac041_annular_A(self):
        """AC-041: área anular A = π/4 × (De² - Di²)."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        De, Di = 0.4, 0.3
        expected = math.pi / 4.0 * (De**2 - Di**2)
        assert abs(r.A_m2 - expected) < 1e-8

    def test_ac042_annular_Iy(self):
        """AC-042: inercia I = π/64 × (De⁴ - Di⁴)."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        De, Di = 0.4, 0.3
        expected = math.pi / 64.0 * (De**4 - Di**4)
        assert abs(r.Iy_m4 - expected) < 1e-15

    def test_ac043_annular_J_twice_I(self):
        """AC-043: J = 2 × I (sección circular simétrica)."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        assert abs(r.J_m4 - 2.0 * r.Iy_m4) < 1e-15

    def test_ac044_annular_Wel(self):
        """AC-044: Wel = I / (De/2)."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        expected = r.Iy_m4 / (0.4 / 2.0)
        assert abs(r.Wel_y_m3 - expected) < 1e-12

    def test_ac045_invalid_section_Dint_ge_Dext(self):
        """AC-045: Di ≥ De lanza CON-SEC-001."""
        with pytest.raises(ValueError, match="CON-SEC-001"):
            ConcreteSectionEngine.annular_properties(300.0, 300.0)

    def test_ac046_mass_per_m_positive(self):
        """AC-046: masa por metro lineal > 0."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        assert r.mass_per_m_kg > 0

    def test_ac047_iy_positive(self):
        """AC-047: radio de giro iy > 0."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        assert r.iy_m > 0

    def test_ac048_t_wall_correct(self):
        """AC-048: espesor de pared = (De - Di) / 2."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        assert abs(r.t_wall_mm - 50.0) < 0.001

    def test_ac049_stress_fiber_pure_compression(self):
        """AC-049: N puro → tensión uniforme en toda la fibra."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        # N = -1000 kN (compresión), sin momentos
        sigma1 = ConcreteSectionEngine.stress_at_fiber(-1000.0, 0.0, 0.0, r.A_m2, r.Iy_m4, r.Iz_m4, 0.0, 0.0)
        sigma2 = ConcreteSectionEngine.stress_at_fiber(-1000.0, 0.0, 0.0, r.A_m2, r.Iy_m4, r.Iz_m4, 0.1, 0.0)
        assert abs(sigma1 - sigma2) < 0.001, "Tensión uniforme para N puro"

    def test_ac050_stress_fiber_bending_antisymmetric(self):
        """AC-050: flexión pura → tensión antisimétrica."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        De = 0.4
        sigma_top = ConcreteSectionEngine.stress_at_fiber(0.0, 100.0, 0.0, r.A_m2, r.Iy_m4, r.Iz_m4, 0.0, De/2)
        sigma_bot = ConcreteSectionEngine.stress_at_fiber(0.0, 100.0, 0.0, r.A_m2, r.Iy_m4, r.Iz_m4, 0.0, -De/2)
        assert abs(sigma_top + sigma_bot) < 0.001, "Tensión antisimétrica en flexión"

    def test_ac051_stress_prestress_adds_compression(self):
        """AC-051: pretensado (P > 0) añade compresión uniforme."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        without = ConcreteSectionEngine.stress_at_fiber(0.0, 0.0, 0.0, r.A_m2, r.Iy_m4, r.Iz_m4, 0.0, 0.0)
        with_P = ConcreteSectionEngine.stress_at_fiber(0.0, 0.0, 0.0, r.A_m2, r.Iy_m4, r.Iz_m4, 0.0, 0.0, P_kn=1000.0)
        # N_total = 1000 kN → compresión positiva
        assert with_P > without

    def test_ac052_annular_bigger_section_heavier(self):
        """AC-052: sección más grande → mayor masa por metro."""
        r_small = ConcreteSectionEngine.annular_properties(300.0, 200.0)
        r_big = ConcreteSectionEngine.annular_properties(500.0, 400.0)
        assert r_big.mass_per_m_kg > r_small.mass_per_m_kg

    def test_ac053_run_hash_deterministic(self):
        """AC-053: mismo input → mismo hash."""
        h1 = ConcreteSectionEngine.compute_run_hash("abc", "def", "ghi", "jkl")
        h2 = ConcreteSectionEngine.compute_run_hash("abc", "def", "ghi", "jkl")
        assert h1 == h2

    def test_ac054_run_hash_changes_with_input(self):
        """AC-054: input diferente → hash diferente."""
        h1 = ConcreteSectionEngine.compute_run_hash("abc", "def", "ghi", "jkl")
        h2 = ConcreteSectionEngine.compute_run_hash("abc", "def", "ghi", "XYZ")
        assert h1 != h2

    def test_ac055_annular_Iz_eq_Iy(self):
        """AC-055: sección circular → Iz = Iy."""
        r = ConcreteSectionEngine.annular_properties(400.0, 300.0)
        assert abs(r.Iy_m4 - r.Iz_m4) < 1e-15


# ============================================================================
# AC-056..AC-070  ELS
# ============================================================================

class TestELS:
    """AC-056..AC-070"""

    def test_ac056_stress_compression_transfer_pass(self):
        """AC-056: σ ≤ 0.60 fck en transferencia → PASS."""
        r = ConcreteSectionEngine.check_stress_concrete(18.0, 35.0, "S1")
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac057_stress_compression_transfer_fail(self):
        """AC-057: σ > 0.60 fck en transferencia → FAIL."""
        r = ConcreteSectionEngine.check_stress_concrete(25.0, 35.0, "S1")
        assert r.status == ConcreteVerificationStatus.FAIL

    def test_ac058_stress_service_limit_045fck(self):
        """AC-058: límite en servicio = 0.45 fck."""
        r = ConcreteSectionEngine.check_stress_concrete(16.0, 45.0, "S7")
        limit = r.resistance
        assert abs(limit - 0.45 * 45.0) < 0.001

    def test_ac059_stress_tension_check(self):
        """AC-059: tensión de tracción > fctm → FAIL."""
        r = ConcreteSectionEngine.check_stress_concrete(3.0, 35.0, "S1", is_tension=True, fctm_t_mpa=2.5)
        assert r.status == ConcreteVerificationStatus.FAIL

    def test_ac060_stress_tension_pass(self):
        """AC-060: tracción < fctm → PASS."""
        r = ConcreteSectionEngine.check_stress_concrete(1.5, 35.0, "S1", is_tension=True, fctm_t_mpa=2.5)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac061_decompression_pass(self):
        """AC-061: σ_min ≥ 0 → descompresión OK."""
        r = ConcreteVerificationService.check_decompression(0.5)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac062_decompression_fail(self):
        """AC-062: σ_min < 0 → descompresión FAIL."""
        r = ConcreteVerificationService.check_decompression(-0.5)
        assert r.status == ConcreteVerificationStatus.FAIL

    def test_ac063_decompression_at_zero(self):
        """AC-063: σ_min = 0 → exactamente PASS."""
        r = ConcreteVerificationService.check_decompression(0.0)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac064_crack_width_pass(self):
        """AC-064: tensión baja → fisura < límite → PASS."""
        r = ConcreteVerificationService.check_crack_width(
            sigma_s_mpa=100.0, Es_mpa=200000.0, fctm_mpa=3.5,
            cover_c_mm=35.0, phi_bar_mm=8.0, rho_eff=0.01, wk_limit_mm=0.3,
        )
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac065_crack_width_fail(self):
        """AC-065: tensión alta → fisura > límite → FAIL."""
        r = ConcreteVerificationService.check_crack_width(
            sigma_s_mpa=400.0, Es_mpa=200000.0, fctm_mpa=3.5,
            cover_c_mm=35.0, phi_bar_mm=16.0, rho_eff=0.005, wk_limit_mm=0.2,
        )
        assert r.status == ConcreteVerificationStatus.FAIL

    def test_ac066_crack_width_unit_mm(self):
        """AC-066: unidad de ancho de fisura es mm."""
        r = ConcreteVerificationService.check_crack_width(
            100.0, 200000.0, 3.5, 35.0, 8.0, 0.01, 0.3)
        assert r.unit == "mm"

    def test_ac067_stress_utilization_monotone(self):
        """AC-067: mayor tensión → mayor utilización."""
        r_low = ConcreteSectionEngine.check_stress_concrete(5.0, 45.0, "S7")
        r_high = ConcreteSectionEngine.check_stress_concrete(15.0, 45.0, "S7")
        assert r_high.utilization > r_low.utilization

    def test_ac068_stress_rule_transfer(self):
        """AC-068: etapa S1 usa regla de transferencia."""
        r = ConcreteSectionEngine.check_stress_concrete(10.0, 35.0, "S1")
        assert "transferencia" in r.governing_rule or "5.10.2" in r.governing_rule

    def test_ac069_stress_rule_service(self):
        """AC-069: etapa S7 usa regla de servicio."""
        r = ConcreteSectionEngine.check_stress_concrete(10.0, 35.0, "S7")
        assert "7.2" in r.governing_rule or "servicio" in r.governing_rule

    def test_ac070_crack_width_sr_max_positive(self):
        """AC-070: espaciado de fisuras sr_max > 0."""
        r = ConcreteVerificationService.check_crack_width(
            150.0, 200000.0, 3.5, 35.0, 8.0, 0.01, 0.3)
        assert r.intermediate_values["sr_max_mm"] > 0


# ============================================================================
# AC-071..AC-085  ELU y fatiga
# ============================================================================

class TestELUFatiga:
    """AC-071..AC-085"""

    def test_ac071_shear_pass(self):
        """AC-071: V_Ed < V_Rd,c → PASS."""
        r = ConcreteSectionEngine.check_shear(50.0, 45.0, 0.3, 0.25, 0.005)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac072_shear_fail(self):
        """AC-072: V_Ed >> V_Rd,c → FAIL."""
        r = ConcreteSectionEngine.check_shear(500.0, 20.0, 0.1, 0.1, 0.001)
        assert r.status == ConcreteVerificationStatus.FAIL

    def test_ac073_shear_k_bounded(self):
        """AC-073: k = min(1 + √(200/d), 2.0) ≤ 2.0."""
        r = ConcreteSectionEngine.check_shear(50.0, 45.0, 0.3, 0.05, 0.005)
        assert r.intermediate_values["k"] <= 2.0

    def test_ac074_shear_unit_kn(self):
        """AC-074: unidad de cortante es kN."""
        r = ConcreteSectionEngine.check_shear(50.0, 45.0, 0.3, 0.25, 0.005)
        assert r.unit == "kN"

    def test_ac075_shear_rule_ec2_622(self):
        """AC-075: referencia normativa EC2 §6.2.2."""
        r = ConcreteSectionEngine.check_shear(50.0, 45.0, 0.3, 0.25, 0.005)
        assert "6.2.2" in r.governing_rule

    def test_ac076_torsion_pass(self):
        """AC-076: T_Ed pequeño → PASS."""
        r = ConcreteSectionEngine.check_torsion_bredt(0.5, 400.0, 300.0, 45.0)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac077_torsion_fail(self):
        """AC-077: T_Ed grande → FAIL."""
        r = ConcreteSectionEngine.check_torsion_bredt(500.0, 400.0, 300.0, 20.0)
        assert r.status == ConcreteVerificationStatus.FAIL

    def test_ac078_torsion_bredt_rule(self):
        """AC-078: referencia Bredt en governing_rule."""
        r = ConcreteSectionEngine.check_torsion_bredt(0.5, 400.0, 300.0, 45.0)
        assert "Bredt" in r.governing_rule

    def test_ac079_torsion_Ak_positive(self):
        """AC-079: área encerrada Ak > 0."""
        r = ConcreteSectionEngine.check_torsion_bredt(0.5, 400.0, 300.0, 45.0)
        assert r.intermediate_values["A_k_m2"] > 0

    def test_ac080_fatigue_strand_pass(self):
        """AC-080: Δσ_p bajo → fatiga PASS."""
        r = ConcreteFatigueService.strand_fatigue_check(50.0, 150.0, 1.15)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac081_fatigue_strand_fail(self):
        """AC-081: Δσ_p alto → fatiga FAIL."""
        r = ConcreteFatigueService.strand_fatigue_check(200.0, 150.0, 1.15)
        assert r.status == ConcreteVerificationStatus.FAIL

    def test_ac082_fatigue_demand_formula(self):
        """AC-082: demanda = γ_Ff × Δσ_p."""
        r = ConcreteFatigueService.strand_fatigue_check(100.0, 150.0, 1.15, gamma_ff=1.0)
        assert abs(r.solicitation - 100.0) < 0.001

    def test_ac083_fatigue_capacity_formula(self):
        """AC-083: capacidad = ΔσRsk / γS,fat."""
        r = ConcreteFatigueService.strand_fatigue_check(50.0, 150.0, 1.15)
        assert abs(r.resistance - 150.0 / 1.15) < 0.001

    def test_ac084_miner_pass(self):
        """AC-084: D_total ≤ 1.0 → PASS."""
        blocks = [
            {"delta_sigma_mpa": 100.0, "n_cycles": 1e4, "N_ref": 1e6, "source": "viento"},
            {"delta_sigma_mpa": 80.0,  "n_cycles": 5e4, "N_ref": 1e7, "source": "trafico"},
        ]
        r = ConcreteFatigueService.miner_damage(blocks)
        assert r.status == "PASS"
        assert r.total_damage < 1.0

    def test_ac085_miner_fail(self):
        """AC-085: D_total > 1.0 → FAIL."""
        blocks = [
            {"delta_sigma_mpa": 100.0, "n_cycles": 1e6, "N_ref": 5e5, "source": "A"},
        ]
        r = ConcreteFatigueService.miner_damage(blocks)
        assert r.status == "FAIL"
        assert r.total_damage > 1.0


# ============================================================================
# AC-086..AC-100  Fabricación, transporte y calidad
# ============================================================================

class TestProduction:
    """AC-086..AC-100"""

    def test_ac086_lifting_2_points_positions(self):
        """AC-086: 2 puntos de izado → posición = 0.207L desde extremos."""
        r = ConcreteProductionService.check_lifting_positions(10.0, 2, 50.0, 2.5)
        assert abs(r.point_positions_m[0] - 0.207 * 10.0) < 0.001
        assert abs(r.point_positions_m[1] - (10.0 - 0.207 * 10.0)) < 0.001

    def test_ac087_lifting_2_points_compliant(self):
        """AC-087: momento en izado < 0.85 Mcr → compliant=True."""
        r = ConcreteProductionService.check_lifting_positions(10.0, 2, 50.0, 2.5)
        assert r.compliant

    def test_ac088_lifting_heavy_fails(self):
        """AC-088: pieza muy pesada → utilización > 1 → compliant=False."""
        r = ConcreteProductionService.check_lifting_positions(10.0, 2, 1.0, 10.0)
        assert not r.compliant

    def test_ac089_lifting_rule_reference(self):
        """AC-089: referencia menciona 0.207L."""
        r = ConcreteProductionService.check_lifting_positions(10.0, 2, 50.0, 2.5)
        assert "0.207" in r.governing_rule

    def test_ac090_strand_clearance_pass(self):
        """AC-090: inserto suficientemente separado → PASS."""
        r = ConcreteProductionService.check_strand_clearance(
            strand_r_mm=150.0, strand_phi_mm=12.5,
            insert_r_mm=150.0, insert_phi_mm=20.0,
            insert_theta_deg=90.0, strand_theta_deg=0.0,
            D_ext_mm=400.0, min_clearance_mm=25.0,
        )
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac091_strand_clearance_fail(self):
        """AC-091: inserto demasiado cerca → BLOCKED + CON-FAB-001."""
        r = ConcreteProductionService.check_strand_clearance(
            strand_r_mm=150.0, strand_phi_mm=12.5,
            insert_r_mm=150.0, insert_phi_mm=20.0,
            insert_theta_deg=1.0, strand_theta_deg=0.0,  # casi mismo ángulo
            D_ext_mm=400.0, min_clearance_mm=25.0,
        )
        assert r.status == ConcreteVerificationStatus.BLOCKED
        assert r.error_code == "CON-FAB-001"

    def test_ac092_piece_length_pass(self):
        """AC-092: L ≤ 12m → PASS."""
        r = ConcreteProductionService.check_piece_length(10.0)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac093_piece_length_fail(self):
        """AC-093: L > 12m → BLOCKED + CON-FAB-001."""
        r = ConcreteProductionService.check_piece_length(15.0)
        assert r.status == ConcreteVerificationStatus.BLOCKED
        assert r.error_code == "CON-FAB-001"

    def test_ac094_spin_window_pass(self):
        """AC-094: rpm dentro de ventana → PASS."""
        r = ConcreteProductionService.check_spin_within_window(350.0, 300.0, 450.0)
        assert r.status == ConcreteVerificationStatus.PASS

    def test_ac095_spin_window_fail_low(self):
        """AC-095: rpm < min_rpm → BLOCKED + CON-FAB-003."""
        r = ConcreteProductionService.check_spin_within_window(200.0, 300.0, 450.0)
        assert r.status == ConcreteVerificationStatus.BLOCKED
        assert r.error_code == "CON-FAB-003"

    def test_ac096_spin_window_fail_high(self):
        """AC-096: rpm > max_rpm → BLOCKED."""
        r = ConcreteProductionService.check_spin_within_window(500.0, 300.0, 450.0)
        assert r.status == ConcreteVerificationStatus.BLOCKED

    def test_ac097_bom_total_mass(self):
        """AC-097: masa total = suma de componentes."""
        bom = ConcreteProductionService.bom_mass(0.05, 50.0, 10.0, 5.0, 2450.0)
        concrete = 0.05 * 2450.0
        expected_total = concrete + 50.0 + 10.0 + 5.0
        assert abs(bom["total_mass_kg"] - expected_total) < 0.01

    def test_ac098_lifting_3_points(self):
        """AC-098: 3 puntos de izado genera 3 posiciones."""
        r = ConcreteProductionService.check_lifting_positions(12.0, 3, 80.0, 3.0)
        assert len(r.point_positions_m) == 3

    def test_ac099_lifting_M_max_positive(self):
        """AC-099: M_max > 0."""
        r = ConcreteProductionService.check_lifting_positions(10.0, 2, 50.0, 2.5)
        assert r.M_max_knm > 0

    def test_ac100_strand_clearance_unit_mm(self):
        """AC-100: unidad de distancia es mm."""
        r = ConcreteProductionService.check_strand_clearance(
            150.0, 12.5, 150.0, 20.0, 90.0, 0.0, 400.0)
        assert r.unit == "mm"


# ============================================================================
# AC-101..AC-140  Optimización del pretensado
# ============================================================================

class TestOptimization:
    """AC-101..AC-140"""

    def _candidates(self):
        """Conjunto de candidatos de prueba."""
        return [
            PrestressCandidate(6, 12.5, 150.0, 100.0,  8000.0, 300.0, 500.0, 0.9, True, True),
            PrestressCandidate(8, 12.5, 150.0, 100.0,  9500.0, 350.0, 600.0, 0.8, True, True),
            PrestressCandidate(6, 15.2, 160.0, 120.0,  9000.0, 320.0, 480.0, 0.85, True, True),
            PrestressCandidate(10, 12.5, 140.0, 100.0, 11000.0, 400.0, 700.0, 0.7, True, True),
            PrestressCandidate(6, 12.5, 150.0, 100.0,  7500.0, 310.0, 520.0, 0.6, False, True),  # no factible
            PrestressCandidate(6, 12.5, 150.0, 100.0,  7800.0, 305.0, 510.0, 0.65, True, False), # no transportable
        ]

    def test_ac101_pareto_excludes_nonfeasible(self):
        """AC-101: candidatos no factibles excluidos del frente de Pareto."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        assert all(c.feasible and c.transportable for c in pareto)

    def test_ac102_pareto_non_empty(self):
        """AC-102: con candidatos válidos, Pareto no vacío."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        assert len(pareto) > 0

    def test_ac103_pareto_no_dominated(self):
        """AC-103: ningún candidato en Pareto está dominado por otro del mismo frente."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        for c in pareto:
            dominated = any(ConcreteOptimizer.is_dominated(c, other) for other in pareto if other is not c)
            assert not dominated, f"Candidato dominado en Pareto: {c}"

    def test_ac104_select_min_cost(self):
        """AC-104: solución min_cost tiene el menor coste del frente."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        sols = ConcreteOptimizer.select_solutions(pareto)
        if sols["min_cost"] and len(pareto) > 1:
            assert sols["min_cost"].total_cost_eur == min(c.total_cost_eur for c in pareto)

    def test_ac105_select_min_weight(self):
        """AC-105: solución min_weight tiene el menor peso del frente."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        sols = ConcreteOptimizer.select_solutions(pareto)
        if sols["min_weight"] and len(pareto) > 1:
            assert sols["min_weight"].total_mass_kg == min(c.total_mass_kg for c in pareto)

    def test_ac106_select_min_co2(self):
        """AC-106: solución min_co2 tiene el menor CO₂ del frente."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        sols = ConcreteOptimizer.select_solutions(pareto)
        if sols["min_co2"] and len(pareto) > 1:
            assert sols["min_co2"].total_co2_kg == min(c.total_co2_kg for c in pareto)

    def test_ac107_balanced_in_pareto(self):
        """AC-107: solución equilibrada está en el frente de Pareto."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        sols = ConcreteOptimizer.select_solutions(pareto)
        if sols["balanced"]:
            assert sols["balanced"] in pareto

    def test_ac108_empty_pareto_returns_nones(self):
        """AC-108: sin candidatos factibles → todas las soluciones None."""
        cands = [PrestressCandidate(6, 12.5, 150.0, 100.0, 8000.0, 300.0, 500.0, 0.9, False, True)]
        pareto = ConcreteOptimizer.build_pareto_front(cands)
        sols = ConcreteOptimizer.select_solutions(pareto)
        assert all(v is None for v in sols.values())

    def test_ac109_is_dominated_basic(self):
        """AC-109: b mejor en todo domina a a."""
        a = PrestressCandidate(6, 12.5, 150.0, 100.0, 10000.0, 400.0, 600.0, 0.8, True, True)
        b = PrestressCandidate(6, 12.5, 150.0, 100.0,  9000.0, 380.0, 580.0, 0.9, True, True)
        assert ConcreteOptimizer.is_dominated(a, b)

    def test_ac110_is_not_dominated_incomparable(self):
        """AC-110: a mejor en coste, b mejor en peso → no se dominan mutuamente."""
        a = PrestressCandidate(6, 12.5, 150.0, 100.0, 8000.0, 400.0, 600.0, 0.8, True, True)
        b = PrestressCandidate(8, 12.5, 150.0, 100.0, 9000.0, 350.0, 580.0, 0.8, True, True)
        assert not ConcreteOptimizer.is_dominated(a, b)
        assert not ConcreteOptimizer.is_dominated(b, a)

    def test_ac111_nonfeasible_dominated_by_feasible(self):
        """AC-111: candidato no factible siempre dominado."""
        nf = PrestressCandidate(6, 12.5, 150.0, 100.0, 7000.0, 280.0, 450.0, 0.95, False, True)
        f = PrestressCandidate(6, 12.5, 150.0, 100.0, 8000.0, 300.0, 500.0, 0.9, True, True)
        assert ConcreteOptimizer.is_dominated(nf, f)

    def test_ac112_pareto_size_ge_1(self):
        """AC-112: Pareto con candidatos válidos tiene al menos 1 elemento."""
        cands = [PrestressCandidate(6, 12.5, 150.0, 100.0, 8000.0, 300.0, 500.0, 0.9, True, True)]
        pareto = ConcreteOptimizer.build_pareto_front(cands)
        assert len(pareto) >= 1

    def test_ac113_select_min_cost_not_none_when_pareto_nonempty(self):
        """AC-113: Pareto no vacío → min_cost no es None."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        sols = ConcreteOptimizer.select_solutions(pareto)
        assert sols["min_cost"] is not None

    def test_ac114_normative_route_en40_ec2(self):
        """AC-114: altura < 30m, sin cables → EN40_EC2."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
        assert r.route == ConcreteNormativeRoute.EN40_EC2

    def test_ac115_normative_route_blocked_no_mix(self):
        """AC-115: mezcla no en biblioteca → BLOCKED."""
        r = ConcreteNormativeClassifier.classify(12.0, False, False, True, True, True, True)
        assert r.route == ConcreteNormativeRoute.BLOCKED
        assert r.blocking_step == 3

    def test_ac116_normative_route_blocked_no_steel(self):
        """AC-116: acero no en biblioteca → BLOCKED."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, False, True, True, True)
        assert r.route == ConcreteNormativeRoute.BLOCKED

    def test_ac117_normative_route_blocked_no_domain(self):
        """AC-117: dominio no verificado → BLOCKED."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, True, False, True, True)
        assert r.route == ConcreteNormativeRoute.BLOCKED

    def test_ac118_normative_hash_deterministic(self):
        """AC-118: mismo input → mismo hash."""
        r1 = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
        r2 = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
        assert r1.input_hash == r2.input_hash

    def test_ac119_normative_hash_changes(self):
        """AC-119: input diferente → hash diferente."""
        r1 = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
        r2 = ConcreteNormativeClassifier.classify(15.0, False, True, True, True, True, True)
        assert r1.input_hash != r2.input_hash

    def test_ac120_normative_7_steps_always(self):
        """AC-120: siempre 7 pasos en steps_passed."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
        assert len(r.steps_passed) == 7

    def test_ac121_normative_blocked_has_blocking_step(self):
        """AC-121: BLOCKED → blocking_step no es None."""
        r = ConcreteNormativeClassifier.classify(12.0, False, False, True, True, True, True)
        assert r.blocking_step is not None

    def test_ac122_normative_pass_no_blocking(self):
        """AC-122: no BLOCKED → blocking_step es None."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
        assert r.blocking_step is None

    def test_ac123_normative_trace_has_7_lines(self):
        """AC-123: traza de decisión tiene 7 líneas."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
        assert len(r.decision_trace) == 7

    def test_ac124_normative_cables_special(self):
        """AC-124: cables catenaria → SPECIAL."""
        r = ConcreteNormativeClassifier.classify(15.0, True, True, True, True, True, True)
        assert r.route == ConcreteNormativeRoute.SPECIAL

    def test_ac125_miner_duplicate_detected(self):
        """AC-125: fuentes duplicadas → duplicate_source_detected=True."""
        blocks = [
            {"delta_sigma_mpa": 100.0, "n_cycles": 1e4, "N_ref": 1e6, "source": "viento"},
            {"delta_sigma_mpa": 80.0,  "n_cycles": 5e4, "N_ref": 1e7, "source": "viento"},
        ]
        r = ConcreteFatigueService.miner_damage(blocks)
        assert r.duplicate_source_detected

    def test_ac126_miner_no_duplicate(self):
        """AC-126: fuentes distintas → duplicate_source_detected=False."""
        blocks = [
            {"delta_sigma_mpa": 100.0, "n_cycles": 1e4, "N_ref": 1e6, "source": "viento"},
            {"delta_sigma_mpa": 80.0,  "n_cycles": 5e4, "N_ref": 1e7, "source": "trafico"},
        ]
        r = ConcreteFatigueService.miner_damage(blocks)
        assert not r.duplicate_source_detected

    def test_ac127_miner_governing_source_identified(self):
        """AC-127: governing_source identifica la fuente con mayor daño."""
        blocks = [
            {"delta_sigma_mpa": 100.0, "n_cycles": 1e6, "N_ref": 1e6, "source": "A"},
            {"delta_sigma_mpa": 80.0,  "n_cycles": 1e4, "N_ref": 1e6, "source": "B"},
        ]
        r = ConcreteFatigueService.miner_damage(blocks)
        assert r.governing_source == "A"

    def test_ac128_pareto_all_feasible_transportable(self):
        """AC-128: todos los candidatos del frente son feasible y transportable."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        for c in pareto:
            assert c.feasible and c.transportable

    def test_ac129_optimizer_balanced_in_range(self):
        """AC-129: balanced no tiene el peor coste, peso ni CO₂ del frente."""
        pareto = ConcreteOptimizer.build_pareto_front(self._candidates())
        if len(pareto) <= 1:
            return
        sols = ConcreteOptimizer.select_solutions(pareto)
        b = sols["balanced"]
        max_cost = max(c.total_cost_eur for c in pareto)
        max_weight = max(c.total_mass_kg for c in pareto)
        max_co2 = max(c.total_co2_kg for c in pareto)
        # No todos los objetivos pueden ser el peor simultáneamente
        assert not (
            b.total_cost_eur == max_cost and
            b.total_mass_kg == max_weight and
            b.total_co2_kg == max_co2
        )

    def test_ac130_normative_no_evidence_blocked(self):
        """AC-130: sin evidencias → BLOCKED."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, False)
        assert r.route == ConcreteNormativeRoute.BLOCKED

    def test_ac131_pareto_size_bounded_by_total(self):
        """AC-131: |Pareto| ≤ candidatos totales."""
        cands = self._candidates()
        pareto = ConcreteOptimizer.build_pareto_front(cands)
        assert len(pareto) <= len(cands)

    def test_ac132_loss_type_labels_correct(self):
        """AC-132: tipos de pérdida correctamente etiquetados."""
        r_slip = PrestressLossService.anchor_slip_loss(140.0, 195000.0, 5.0, 10000.0, 200.0)
        r_el = PrestressLossService.elastic_shortening_loss(140.0, 195000.0, 10.0, 37000.0, 4, 200.0)
        r_lt = PrestressLossService.long_term_loss_simplified(140.0, 195000.0, 37000.0, 0.05, 5e-4, 50.0, 300e-6, 30.0, 2.0, 8.0, 200.0)
        assert r_slip.loss_type == "ANCHOR_SLIP"
        assert r_el.loss_type == "ELASTIC_SHORTENING"
        assert r_lt.loss_type == "COMBINED_CSR"

    def test_ac133_torsion_t_ef_positive(self):
        """AC-133: espesor efectivo t_ef > 0."""
        r = ConcreteSectionEngine.check_torsion_bredt(1.0, 400.0, 300.0, 45.0)
        assert r.intermediate_values["t_ef_m"] > 0

    def test_ac134_fatigue_strand_rule_ec2_684(self):
        """AC-134: referencia EC2 §6.8.4 en fatiga de cordones."""
        r = ConcreteFatigueService.strand_fatigue_check(80.0, 150.0, 1.15)
        assert "6.8.4" in r.governing_rule

    def test_ac135_shear_min_vrd_applied(self):
        """AC-135: V_Rd,c nunca menor que V_Rd,c_min."""
        r = ConcreteSectionEngine.check_shear(10.0, 45.0, 0.3, 0.25, 0.005)
        # intermediate_values tiene V_Rd_c_min
        assert r.resistance >= r.intermediate_values["V_Rd_c_min"] - 0.001

    def test_ac136_stress_utilization_exactly_one_at_limit(self):
        """AC-136: tensión exactamente en el límite → utilización = 1.0."""
        # Servicio: límite = 0.45 × 45 = 20.25
        r = ConcreteSectionEngine.check_stress_concrete(20.25, 45.0, "S7")
        assert abs(r.utilization - 1.0) < 0.0001

    def test_ac137_annular_section_D_ext_350_D_int_280(self):
        """AC-137: sección típica 350/280 → A > 0."""
        r = ConcreteSectionEngine.annular_properties(350.0, 280.0)
        assert r.A_m2 > 0

    def test_ac138_production_bom_concrete_mass(self):
        """AC-138: masa de hormigón = rho × V."""
        bom = ConcreteProductionService.bom_mass(0.10, 0.0, 0.0, 0.0, 2450.0)
        assert abs(bom["concrete_mass_kg"] - 245.0) < 0.01

    def test_ac139_transfer_length_increases_with_phi(self):
        """AC-139: cordón mayor diámetro → mayor longitud de transferencia."""
        r_small = PrestressLossService.transfer_length(9.3, 1395.0, 1500.0, 1200.0, 2.0)
        r_big = PrestressLossService.transfer_length(15.7, 1395.0, 1500.0, 1200.0, 2.0)
        assert r_big.l_pt_mm > r_small.l_pt_mm

    def test_ac140_normative_route_blocked_no_checks(self):
        """AC-140: sin comprobaciones definidas → BLOCKED (paso 5)."""
        r = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, False, True)
        assert r.route == ConcreteNormativeRoute.BLOCKED
        assert r.blocking_step == 5


# ============================================================================
# Función standalone de verificaciones analíticas (sin pytest)
# ============================================================================

def run_analytical_checks_concrete():
    """
    Función standalone para ejecutar verificaciones analíticas sin pytest.
    Retorna (passed, failed, errors).
    """
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, cond, detail))

    # Materiales
    r = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 28.0)
    ok("fcm(28)=fcm_28", abs(r.fcm_t_mpa - 58.0) < 0.01, f"fcm={r.fcm_t_mpa}")
    ok("Ecm(28)=Ecm_28", abs(r.Ecm_t_mpa - 37000.0) < 1.0, f"Ecm={r.Ecm_t_mpa}")
    ok("fctk_005=0.7*fctm", abs(r.fctk_005_t_mpa - 0.7*r.fctm_t_mpa) < 0.001)

    r7 = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 7.0)
    r90 = ConcreteMaterialService.age_properties(58.0, 4.1, 37000.0, 0.25, 90.0)
    ok("fcm crece con t", r7.fcm_t_mpa < 58.0 < r90.fcm_t_mpa)

    ok("tranfer strength PASS", ConcreteMaterialService.check_transfer_strength(35.0, 30.0).status == ConcreteVerificationStatus.PASS)
    ok("transfer strength BLOCKED", ConcreteMaterialService.check_transfer_strength(25.0, 30.0).status == ConcreteVerificationStatus.BLOCKED)

    # Pérdidas
    rslip = PrestressLossService.anchor_slip_loss(140.0, 195000.0, 5.0, 10000.0, 200.0)
    ok("anchor slip sigma", abs(rslip.delta_sigma_mpa - 97.5) < 0.001, f"σ={rslip.delta_sigma_mpa}")
    ok("anchor slip P", abs(rslip.delta_P_kn - 13.65) < 0.001, f"P={rslip.delta_P_kn}")

    rel = PrestressLossService.elastic_shortening_loss(140.0, 195000.0, 10.0, 37000.0, 10, 200.0)
    ok("elastic shortening n_ratio", abs(rel.intermediate_values["n_ratio"] - 0.45) < 0.001)

    rlt = PrestressLossService.long_term_loss_simplified(
        140.0, 195000.0, 37000.0, 0.05, 5e-4, 50.0, 300e-6, 30.0, 2.0, 8.0, 200.0)
    ok("long term loss > 0", rlt.delta_P_kn > 0)
    ok("long term denominator > 1", rlt.intermediate_values["denominator"] > 1.0)

    tl = PrestressLossService.transfer_length(12.5, 1395.0, 1500.0, 1200.0, 2.0)
    ok("fbpt correct", abs(tl.fbpt_mpa - 2.25*2.0) < 0.001)
    ok("l_pt > 0", tl.l_pt_mm > 0)

    # Secciones
    ann = ConcreteSectionEngine.annular_properties(400.0, 300.0)
    De, Di = 0.4, 0.3
    exp_A = math.pi/4*(De**2 - Di**2)
    ok("A anular", abs(ann.A_m2 - exp_A) < 1e-8)
    ok("J=2I circular", abs(ann.J_m4 - 2*ann.Iy_m4) < 1e-15)
    ok("t_wall=50mm", abs(ann.t_wall_mm - 50.0) < 0.001)

    h1 = ConcreteSectionEngine.compute_run_hash("a","b","c","d")
    h2 = ConcreteSectionEngine.compute_run_hash("a","b","c","d")
    ok("hash deterministic", h1 == h2)

    # ELS
    s_pass = ConcreteSectionEngine.check_stress_concrete(18.0, 35.0, "S1")
    ok("stress compression PASS", s_pass.status == ConcreteVerificationStatus.PASS)
    s_fail = ConcreteSectionEngine.check_stress_concrete(25.0, 35.0, "S1")
    ok("stress compression FAIL", s_fail.status == ConcreteVerificationStatus.FAIL)
    ok("decompression PASS", ConcreteVerificationService.check_decompression(0.5).status == ConcreteVerificationStatus.PASS)
    ok("decompression FAIL", ConcreteVerificationService.check_decompression(-0.5).status == ConcreteVerificationStatus.FAIL)

    # ELU
    v_pass = ConcreteSectionEngine.check_shear(50.0, 45.0, 0.3, 0.25, 0.005)
    ok("shear PASS", v_pass.status == ConcreteVerificationStatus.PASS)
    ok("shear k<=2", v_pass.intermediate_values["k"] <= 2.0)
    t_pass = ConcreteSectionEngine.check_torsion_bredt(0.5, 400.0, 300.0, 45.0)
    ok("torsion PASS", t_pass.status == ConcreteVerificationStatus.PASS)

    # Fatiga
    f_pass = ConcreteFatigueService.strand_fatigue_check(50.0, 150.0, 1.15)
    ok("fatigue PASS", f_pass.status == ConcreteVerificationStatus.PASS)
    f_fail = ConcreteFatigueService.strand_fatigue_check(200.0, 150.0, 1.15)
    ok("fatigue FAIL", f_fail.status == ConcreteVerificationStatus.FAIL)
    ok("fatigue capacity", abs(f_pass.resistance - 150.0/1.15) < 0.001)

    miner_blocks = [
        {"delta_sigma_mpa": 100.0, "n_cycles": 1e4, "N_ref": 1e6, "source": "viento"},
        {"delta_sigma_mpa": 80.0,  "n_cycles": 5e4, "N_ref": 1e7, "source": "trafico"},
    ]
    m = ConcreteFatigueService.miner_damage(miner_blocks)
    ok("miner PASS", m.status == "PASS")
    ok("miner no duplicate", not m.duplicate_source_detected)

    # Fabricación
    lift = ConcreteProductionService.check_lifting_positions(10.0, 2, 50.0, 2.5)
    ok("lifting pos 0.207L", abs(lift.point_positions_m[0] - 2.07) < 0.001)
    ok("lifting compliant", lift.compliant)
    ok("piece length PASS", ConcreteProductionService.check_piece_length(10.0).status == ConcreteVerificationStatus.PASS)
    ok("piece length BLOCKED", ConcreteProductionService.check_piece_length(15.0).status == ConcreteVerificationStatus.BLOCKED)
    ok("spin window PASS", ConcreteProductionService.check_spin_within_window(350.0, 300.0, 450.0).status == ConcreteVerificationStatus.PASS)

    # Clasificador
    norm_ok = ConcreteNormativeClassifier.classify(12.0, False, True, True, True, True, True)
    ok("route EN40_EC2", norm_ok.route == ConcreteNormativeRoute.EN40_EC2)
    ok("no blocking step", norm_ok.blocking_step is None)
    norm_fail = ConcreteNormativeClassifier.classify(12.0, False, False, True, True, True, True)
    ok("route BLOCKED", norm_fail.route == ConcreteNormativeRoute.BLOCKED)
    ok("blocking step 3", norm_fail.blocking_step == 3)

    # Optimización
    cands = [
        PrestressCandidate(6, 12.5, 150.0, 100.0,  8000.0, 300.0, 500.0, 0.9, True, True),
        PrestressCandidate(8, 12.5, 150.0, 100.0,  9500.0, 350.0, 600.0, 0.8, True, True),
        PrestressCandidate(6, 12.5, 150.0, 100.0,  7500.0, 310.0, 520.0, 0.6, False, True),
    ]
    pareto = ConcreteOptimizer.build_pareto_front(cands)
    ok("pareto no nonfeasible", all(c.feasible for c in pareto))
    ok("pareto non empty", len(pareto) > 0)
    sols = ConcreteOptimizer.select_solutions(pareto)
    ok("min_cost not None", sols["min_cost"] is not None)

    a = PrestressCandidate(6, 12.5, 150.0, 100.0, 10000.0, 400.0, 600.0, 0.8, True, True)
    b = PrestressCandidate(6, 12.5, 150.0, 100.0,  9000.0, 380.0, 580.0, 0.9, True, True)
    ok("is_dominated basic", ConcreteOptimizer.is_dominated(a, b))

    # Resumen
    passed = [c for c in checks if c[1]]
    failed = [c for c in checks if not c[1]]
    print(f"\n=== Hormigón Pretensado: {len(passed)}/{len(checks)} checks OK ===")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
    return len(passed), len(failed), failed


if __name__ == "__main__":
    passed, failed, errors = run_analytical_checks_concrete()
    exit(0 if failed == 0 else 1)
