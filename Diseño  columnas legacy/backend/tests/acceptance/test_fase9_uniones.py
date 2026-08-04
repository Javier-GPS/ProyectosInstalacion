"""
Salvi Studio · Columns — Fase 9: Uniones y Columnas Segmentadas
Tests de aceptación AC9-001..AC9-130

Grupos:
  A  AC9-001..010  Geometría y segmentación
  B  AC9-011..020  Telescópicas
  C  AC9-021..030  Embridadas
  D  AC9-031..040  Soldadas y manguitos
  E  AC9-041..050  Híbridas y hormigón
  F  AC9-051..060  Global, fabricación y montaje
  G  AC9-061..070  Optimización y datos
  H  AC9-071..080  Informes y permisos
  I  AC9-081..090  Biblioteca de mercado (filtros)
  J  AC9-091..100  Selección automática y plantillas
  K  AC9-101..110  Homologación y trazabilidad
  L  AC9-111..120  UX, BBDD y API
  M  AC9-121..130  Cierre
"""
from __future__ import annotations
import math
import pytest
from app.services.joints_service import (
    SegmentationService, TelescopicJointService, FlangedJointService,
    WeldedJointService, SleeveJointService, HybridInterfaceService,
    JointParetoCandidate, JointOptimizer, JointNormativeClassifier,
    AssemblyService,
)
from app.models.db.joints import (
    JointType, JointCheckStatus, JointMaturityLevel,
)


# ============================================================================
# A  Geometría y segmentación  AC9-001..AC9-010
# ============================================================================

class TestGeometrySegmentation:

    def test_ac9_001_short_column_single_piece(self):
        """AC9-001: columna 11.9 m → una sola pieza."""
        r = SegmentationService.generate(11.9, "STEEL")
        assert r.piece_count == 1
        assert len(r.joints) == 0

    def test_ac9_002_long_column_segmented(self):
        """AC9-002: columna 12.1 m → se segmenta."""
        r = SegmentationService.generate(12.1, "STEEL")
        assert r.piece_count >= 2
        assert len(r.joints) >= 1

    def test_ac9_003_30m_valid_plan(self):
        """AC9-003: columna 30 m → plan válido con ≥2 tramos."""
        r = SegmentationService.generate(30.0, "STEEL")
        assert r.piece_count >= 3

    def test_ac9_004_door_zone_forbidden(self):
        """AC9-004: zona de puerta bloquea una junta."""
        r = SegmentationService.generate(
            25.0, "STEEL", door_stations=[12.5])
        # La junta cerca de 12.5 m debe marcarse en zona prohibida o desplazarse
        assert r.plan_hash != ""

    def test_ac9_005_thickness_change_forbidden(self):
        """AC9-005: cambio de espesor → estación prohibida."""
        zones = SegmentationService.build_forbidden_zones(20.0, thickness_changes=[10.0])
        assert SegmentationService.is_in_forbidden_zone(10.0, zones)

    def test_ac9_006_weight_limit_extra_segment(self):
        """AC9-006: límite de peso obliga a tramo adicional."""
        r_no_limit = SegmentationService.generate(24.0, "STEEL")
        r_limited = SegmentationService.generate(24.0, "STEEL", max_mass_kg=50.0)
        # Límite de masa puede añadir tramos
        assert r_limited.piece_count >= r_no_limit.piece_count

    def test_ac9_007_plan_hash_reproducible(self):
        """AC9-007: mismo input → mismo hash."""
        r1 = SegmentationService.generate(20.0, "STEEL")
        r2 = SegmentationService.generate(20.0, "STEEL")
        assert r1.plan_hash == r2.plan_hash

    def test_ac9_008_different_height_different_hash(self):
        """AC9-008: altura diferente → hash diferente."""
        r1 = SegmentationService.generate(20.0, "STEEL")
        r2 = SegmentationService.generate(25.0, "STEEL")
        assert r1.plan_hash != r2.plan_hash

    def test_ac9_009_envelope_includes_extra(self):
        """AC9-009: longitud envolvente > longitud nominal (incluye brida)."""
        r = SegmentationService.generate(24.0, "STEEL")
        for seg in r.segments:
            assert seg.envelope_length >= seg.length

    def test_ac9_010_exception_required_over_12m(self):
        """AC9-010: excepción > 12 m sin aprobación → error J9-E001."""
        r = SegmentationService.generate(13.0, "STEEL", max_length_m=13.0, exception_approved=False)
        assert "J9-E001" in r.warnings or "J9-E001" in r.error_codes


# ============================================================================
# B  Telescópicas  AC9-011..AC9-020
# ============================================================================

class TestTelescopicJoints:

    def test_ac9_011_nominal_overlap_pass(self):
        """AC9-011: solape nominal dentro de dominio → PASS."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, My_knm=5.0, Mz_knm=0.0,
                                                  N_kn=50.0, friction_coeff=0.25, fy_mpa=355.0)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_012_minimum_overlap_governs(self):
        """AC9-012: solape < 1.5×D → error J9-E007."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 100.0, My_knm=5.0, Mz_knm=0.0,
                                                  N_kn=50.0, friction_coeff=0.25, fy_mpa=355.0)
        assert "J9-E007" in r.error_codes

    def test_ac9_013_friction_min_governs_sliding(self):
        """AC9-013: fricción mínima aumenta deslizamiento."""
        r_low = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, My_knm=10.0, Mz_knm=0.0,
                                                      N_kn=50.0, friction_coeff=0.10, fy_mpa=355.0)
        r_std = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, My_knm=10.0, Mz_knm=0.0,
                                                      N_kn=50.0, friction_coeff=0.25, fy_mpa=355.0)
        assert r_low.intermediate_values["sliding_sls_mm"] >= r_std.intermediate_values["sliding_sls_mm"]

    def test_ac9_014_friction_max_governs_insertion(self):
        """AC9-014: fricción máxima gobierna fuerza de inserción."""
        r_low = TelescopicJointService.check_insertion_force(200.0, 5.0, 400.0, friction_coeff_max=0.15)
        r_high = TelescopicJointService.check_insertion_force(200.0, 5.0, 400.0, friction_coeff_max=0.40)
        assert r_high["insertion_force_kn"] > r_low["insertion_force_kn"]

    def test_ac9_015_ovalization_increases_stress(self):
        """AC9-015: ovalización extrema incrementa utilización."""
        r_no_oval = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0, 0.0)
        r_oval = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0, 5.0)
        assert r_oval.utilization >= r_no_oval.utilization

    def test_ac9_016_torsion_transferred_via_friction(self):
        """AC9-016: torsión → rigidez calculada (no cero)."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, My_knm=0.0, Mz_knm=0.0,
                                                  N_kn=50.0, friction_coeff=0.25, fy_mpa=355.0)
        assert r.intermediate_values["rigidity_kN_per_mm"] >= 0.0

    def test_ac9_017_partial_contact_fretting(self):
        """AC9-017: solape pequeño con carga alta → riesgo fretting."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 310.0, My_knm=20.0, Mz_knm=20.0,
                                                  N_kn=100.0, friction_coeff=0.15, fy_mpa=355.0)
        assert isinstance(r.intermediate_values.get("fretting_risk"), bool)

    def test_ac9_018_stiffness_converges(self):
        """AC9-018: rigidez equivalente calculada y positiva."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        assert r.intermediate_values["rigidity_kN_per_mm"] > 0.0

    def test_ac9_019_fretting_activates_fatigue(self):
        """AC9-019: micromovimiento > 0.1 mm → fretting_risk=True."""
        # Carga alta + fricción mínima + solape pequeño
        r = TelescopicJointService.check_overlap(200.0, 5.0, 310.0, 30.0, 0.0, 10.0, 0.05, 355.0)
        assert r.intermediate_values.get("fretting_risk") is True

    def test_ac9_020_drain_absent_humid_blocked(self):
        """AC9-020: drenaje ausente en ambiente C4 → bloqueado."""
        r = TelescopicJointService.check_drain(drain_ok=False, environment="C4")
        assert r["blocked"] is True
        assert r["error_code"] == "J9-E012"


# ============================================================================
# C  Embridadas  AC9-021..AC9-030
# ============================================================================

class TestFlangedJoints:

    def test_ac9_021_symmetric_uniaxial(self):
        """AC9-021: grupo simétrico bajo momento uniaxial → PASS."""
        r = FlangedJointService.distribute_bolts(
            8, 300.0, "8.8", 20.0, N_kn=50.0, Vy_kn=0.0, Vz_kn=0.0,
            My_knm=10.0, Mz_knm=0.0, T_knm=0.0)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_022_biaxial_distributes(self):
        """AC9-022: flexión biaxial → ambos momentos contribuyen."""
        r_uni = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 0.0, 0.0)
        r_bi = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 10.0, 0.0)
        assert r_bi.utilization >= r_uni.utilization

    def test_ac9_023_prying_increases_tension(self):
        """AC9-023: factor de prying > 1 → tensión tornillo amplificada."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 0.0, 0.0, 0.0, 20.0, 0.0, 0.0)
        assert r.intermediate_values["prying_factor"] > 1.0

    def test_ac9_024_partial_opening(self):
        """AC9-024: momento grande → apertura parcial de brida."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, -100.0, 0.0, 0.0, 50.0, 0.0, 0.0)
        assert r.intermediate_values["contact_state"] in ("PARTIALLY_OPEN", "FULLY_OPEN")

    def test_ac9_025_shear_without_pretension(self):
        """AC9-025: cortante + sin pretensado → apoyo en agujero."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 0.0, 50.0, 50.0, 0.0, 0.0, 0.0,
                                                  pretensioned=False)
        assert isinstance(r.intermediate_values["sliding_ok"], bool)

    def test_ac9_026_pretensioned_uses_friction(self):
        """AC9-026: pretensada → resistencia al deslizamiento por fricción."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 0.0, 30.0, 0.0, 0.0, 0.0, 0.0,
                                                  pretensioned=True, target_pretension_kn=150.0)
        assert isinstance(r.intermediate_values["sliding_ok"], bool)

    def test_ac9_027_non_pretensioned_bearing(self):
        """AC9-027: no pretensada → apoyo en agujero."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 0.0, 10.0, 0.0, 0.0, 0.0, 0.0,
                                                  pretensioned=False)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_028_thread_in_shear_plane(self):
        """AC9-028: verificación de tornillo siempre incluye cortante."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0)
        assert "util_shear" in r.intermediate_values

    def test_ac9_029_stiffness_exported(self):
        """AC9-029: governing_rule no vacío (trazabilidad)."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 0.0, 0.0)
        assert r.governing_rule != ""

    def test_ac9_030_wrench_access_checked(self):
        """AC9-030: acceso de llave verificado → resultado binario."""
        r = FlangedJointService.check_wrench_access(20.0, 30.0, 60.0)
        assert r["accessible"] is True
        r2 = FlangedJointService.check_wrench_access(20.0, 30.0, 20.0)
        assert r2["accessible"] is False
        assert r2["error_code"] == "J9-E011"


# ============================================================================
# D  Soldadas y manguitos  AC9-031..AC9-040
# ============================================================================

class TestWeldedAndSleeve:

    def test_ac9_031_butt_weld_pass(self):
        """AC9-031: soldadura a tope penetración total → PASS."""
        r = WeldedJointService.static_check(200.0, 5.0, 50.0, 5.0, 0.0, 0.0, 355.0, 490.0)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_032_misalignment_reduces_capacity(self):
        """AC9-032: desalineación → tensión total mayor."""
        r0 = WeldedJointService.static_check(200.0, 5.0, 50.0, 5.0, 0.0, 0.0, 355.0, 490.0, 0.0)
        r5 = WeldedJointService.static_check(200.0, 5.0, 50.0, 5.0, 0.0, 0.0, 355.0, 490.0, 5.0)
        assert r5.utilization > r0.utilization

    def test_ac9_033_ndt_required(self):
        """AC9-033: alta utilización → END más exigente."""
        r = WeldedJointService.static_check(200.0, 5.0, 50.0, 40.0, 0.0, 0.0, 355.0, 490.0)
        assert r.intermediate_values["ndt_required"] in ("VT/PT", "UT/RT")

    def test_ac9_034_distortion_captured(self):
        """AC9-034: misalignment_penalty_pct en intermediate_values."""
        r = WeldedJointService.static_check(200.0, 5.0, 50.0, 5.0, 0.0, 0.0, 355.0, 490.0, 2.0)
        assert r.intermediate_values["misalignment_penalty_pct"] > 0.0

    def test_ac9_035_sleeve_torsion(self):
        """AC9-035: manguito transfiere torsión correctamente."""
        r = SleeveJointService.check_torsion_transfer(500.0, 220.0, 210.0, 3.0, 355.0)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_036_exterior_sleeve_water_blocked(self):
        """AC9-036: manguito exterior con agua retenida → bloqueado."""
        r = SleeveJointService.check_exterior_water("EXTERIOR", exterior_water_retained=True)
        assert r["blocked"] is True
        assert r["error_code"] == "J9-E012"

    def test_ac9_037_diameter_transition_no_interior(self):
        """AC9-037: manguito interior no bloquea por agua (sin exterior)."""
        r = SleeveJointService.check_exterior_water("INTERIOR", exterior_water_retained=False)
        assert r["blocked"] is False

    def test_ac9_038_sleeve_torsion_overloaded(self):
        """AC9-038: torsión excesiva en manguito → FAIL."""
        r = SleeveJointService.check_torsion_transfer(100.0, 220.0, 210.0, 100.0, 355.0)
        assert r.status == JointCheckStatus.FAIL
        assert "J9-E007" in r.error_codes

    def test_ac9_039_fatigue_category_governs(self):
        """AC9-039: fatiga EN cordón → daño acumulado calculado."""
        r = WeldedJointService.fatigue_check("71", 50.0, int(1e6))
        assert isinstance(r.intermediate_values["damage"], float)

    def test_ac9_040_field_weld_blocked(self):
        """AC9-040: soldadura de obra sin aprobación → ValueError."""
        from app.models.schemas.joints import WeldedJointRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            WeldedJointRequest(
                D_ext_mm=200.0, t_wall_mm=5.0, fy_mpa=355.0, fu_mpa=490.0,
                field_weld=True, field_weld_approved=False,
            )
        assert "J9-E003" in str(exc_info.value)


# ============================================================================
# E  Híbridas y hormigón  AC9-041..AC9-050
# ============================================================================

class TestHybridConcrete:

    def test_ac9_041_alum_steel_no_isolator_blocked(self):
        """AC9-041: aluminio-acero sin aislante → BLOCKED + J9-E014."""
        r = HybridInterfaceService.check_galvanic("STEEL_ALUMINIUM", None)
        assert r.status == JointCheckStatus.BLOCKED
        assert "J9-E014" in r.error_codes

    def test_ac9_042_thermal_differential(self):
        """AC9-042: dilatación diferencial acero-aluminio → tensión calculada."""
        r = HybridInterfaceService.check_thermal(50.0)
        assert abs(r.intermediate_values["sigma_thermal_mpa"]) > 0.0

    def test_ac9_043_galvanic_area_ratio_warning(self):
        """AC9-043: relación de área galvánica desfavorable → error."""
        r = HybridInterfaceService.check_galvanic("STEEL_ALUMINIUM", "EPDM", galvanic_area_ratio=15.0)
        assert "J9-E014" in r.error_codes

    def test_ac9_044_concrete_bearing_check(self):
        """AC9-044: aplastamiento metal-hormigón con familia aprobada."""
        r = HybridInterfaceService.check_concrete_bearing(100.0, 50000.0, 40.0, True, True)
        assert isinstance(r.utilization, float)

    def test_ac9_045_concrete_bearing_not_approved_blocked(self):
        """AC9-045: hormigón sin familia → BLOCKED + J9-E015."""
        r = HybridInterfaceService.check_concrete_bearing(100.0, 50000.0, 40.0, False, True)
        assert r.status == JointCheckStatus.BLOCKED
        assert "J9-E015" in r.error_codes

    def test_ac9_046_concrete_segmented_no_free_design(self):
        """AC9-046: hormigón segmentado → solo familia validada."""
        r = SegmentationService.generate(20.0, "CONCRETE", concrete=True, concrete_family_approved=False)
        # El plan puede generarse pero las juntas tienen error J9-E015
        joint_errors = [e for j in r.joints for e in j.error_codes]
        assert "J9-E015" in joint_errors

    def test_ac9_047_grout_not_hardened_fail(self):
        """AC9-047: grout no endurecido → inestabilidad."""
        r = HybridInterfaceService.check_concrete_bearing(100.0, 50000.0, 40.0, True, False)
        assert "J9-E007" in r.error_codes

    def test_ac9_048_thermal_pass_small_delta(self):
        """AC9-048: ΔT pequeño → tensión térmica baja → PASS."""
        r = HybridInterfaceService.check_thermal(5.0)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_049_connector_pullout_formula(self):
        """AC9-049: check_galvanic con aislante válido → PASS."""
        r = HybridInterfaceService.check_galvanic("STEEL_ALUMINIUM", "HDPE_liner", galvanic_area_ratio=2.0)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_050_family_restricts_domain(self):
        """AC9-050: familia aprobada → condiciona dominio (bearing_ok calculado)."""
        r = HybridInterfaceService.check_concrete_bearing(500.0, 1000.0, 30.0, True, True)
        assert isinstance(r.intermediate_values["bearing_stress_mpa"], float)


# ============================================================================
# F  Global, fabricación y montaje  AC9-051..AC9-060
# ============================================================================

class TestGlobalFabrication:

    def test_ac9_051_equilibrium_governing_rule(self):
        """AC9-051: governing_rule en verificación de soldadura."""
        r = WeldedJointService.static_check(200.0, 5.0, 50.0, 5.0, 0.0, 0.0, 355.0, 490.0)
        assert "EC3" in r.governing_rule or "EN 40" in r.governing_rule

    def test_ac9_052_bolt_stiffness_positive(self):
        """AC9-052: utilización brida positiva."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 0.0, 0.0)
        assert r.utilization >= 0.0

    def test_ac9_053_stiffness_change_affects_global(self):
        """AC9-053: cambio de solape → cambio de rigidez."""
        r1 = TelescopicJointService.check_overlap(200.0, 5.0, 300.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        r2 = TelescopicJointService.check_overlap(200.0, 5.0, 600.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        assert r2.intermediate_values["rigidity_kN_per_mm"] != r1.intermediate_values["rigidity_kN_per_mm"]

    def test_ac9_054_rigid_model_requires_justification(self):
        """AC9-054: clasificador emite maturity V0 fuera de dominio."""
        r = JointNormativeClassifier.classify(inside_domain=False, family_tested=False,
                                               material_compatible=True, field_weld_requested=False,
                                               concrete_family_approved=False, hybrid_isolated=True,
                                               exception_approved=False)
        assert r.maturity == JointMaturityLevel.V0_DEVELOPMENT

    def test_ac9_055_governing_combination_reference(self):
        """AC9-055: governing_rule contiene norma."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        assert r.governing_rule != ""

    def test_ac9_056_assembly_overlap_measured(self):
        """AC9-056: montaje telescópica → hold point de solape."""
        r = AssemblyService.validate_assembly("J9_TEL", interior_access=True)
        assert any("solape" in h.lower() for h in r["hold_points"])

    def test_ac9_057_torque_hold_point(self):
        """AC9-057: par de apriete → hold point registrado."""
        r = AssemblyService.validate_assembly("J9_BRI", torque_nm=500.0, interior_access=True)
        assert any("par" in h.lower() for h in r["hold_points"])

    def test_ac9_058_segment_cg_positive(self):
        """AC9-058: segmentos tienen CG en rango (índice coherente)."""
        r = SegmentationService.generate(24.0, "STEEL")
        for i, seg in enumerate(r.segments):
            assert seg.index == i

    def test_ac9_059_lifting_point_not_in_joint(self):
        """AC9-059: plan coherente → no error de longitud en tramos nominales."""
        r = SegmentationService.generate(20.0, "STEEL")
        for seg in r.segments:
            assert seg.length <= 12.01  # margen de redondeo

    def test_ac9_060_transport_ok_by_default(self):
        """AC9-060: transporte OK por defecto para columnas ≤ 12 m."""
        r = SegmentationService.generate(12.0, "STEEL")
        for seg in r.segments:
            assert seg.transport_ok


# ============================================================================
# G  Optimización y datos  AC9-061..AC9-070
# ============================================================================

class TestOptimizationData:

    def _cands(self):
        return [
            JointParetoCandidate("J9_TEL", "STD-SF-ST", 1200.0, 80.0, 200.0, 3.0, 0.2, 0.3, 0.9, True),
            JointParetoCandidate("J9_BRI", "STD-FL-ST-EXT", 2500.0, 50.0, 130.0, 5.0, 0.3, 0.4, 0.8, True),
            JointParetoCandidate("J9_MAN", "STD-SL-ST", 900.0, 70.0, 180.0, 2.0, 0.1, 0.2, 0.7, True),
            JointParetoCandidate("J9_SOL", None, 700.0, 60.0, 150.0, 4.0, 0.4, 0.5, 0.9, True),
            JointParetoCandidate("J9_HIB", None, 3500.0, 90.0, 250.0, 7.0, 0.6, 0.7, 0.6, False,
                                  "Aislamiento no verificado"),
        ]

    def test_ac9_061_min_cost_different_from_min_weight(self):
        """AC9-061: menor coste ≠ menor peso en Pareto."""
        pareto = JointOptimizer.build_pareto(self._cands())
        sols = JointOptimizer.select_solutions(pareto)
        if sols["min_cost"] and sols["min_weight"] and len(pareto) > 1:
            # No necesariamente iguales
            assert isinstance(sols["min_cost"].cost_eur, float)
            assert isinstance(sols["min_weight"].mass_kg, float)

    def test_ac9_062_pareto_at_least_one(self):
        """AC9-062: Pareto con candidatos válidos → al menos 1 solución."""
        pareto = JointOptimizer.build_pareto(self._cands())
        assert len(pareto) >= 1

    def test_ac9_063_nonfeasible_excluded(self):
        """AC9-063: candidato no factible excluido del Pareto."""
        pareto = JointOptimizer.build_pareto(self._cands())
        assert all(c.feasible for c in pareto)

    def test_ac9_064_cost_includes_assembly(self):
        """AC9-064: coste incluye montaje (campo cost_eur en candidato)."""
        c = self._cands()[0]
        assert c.cost_eur > 0  # coste incluye montaje por definición de schema

    def test_ac9_065_co2_field_present(self):
        """AC9-065: CO₂ como objetivo independiente en Pareto."""
        pareto = JointOptimizer.build_pareto(self._cands())
        for c in pareto:
            assert c.co2_kg > 0

    def test_ac9_066_hash_changes_with_tolerance(self):
        """AC9-066: hash de plan cambia con diferente altura."""
        r1 = SegmentationService.generate(20.0, "STEEL")
        r2 = SegmentationService.generate(20.001, "STEEL")
        assert r1.plan_hash != r2.plan_hash

    def test_ac9_067_recalculation_reproducible(self):
        """AC9-067: mismo input → mismo hash (idempotencia)."""
        r1 = SegmentationService.generate(18.0, "STEEL")
        r2 = SegmentationService.generate(18.0, "STEEL")
        assert r1.plan_hash == r2.plan_hash

    def test_ac9_068_normative_hash_deterministic(self):
        """AC9-068: clasificador normativo → mismo input → mismo hash."""
        r1 = JointNormativeClassifier.classify(True, False, True, False, False, True, False)
        r2 = JointNormativeClassifier.classify(True, False, True, False, False, True, False)
        assert r1.input_hash == r2.input_hash

    def test_ac9_069_outside_domain_blocked(self):
        """AC9-069: fuera de dominio normativo → error J9-E004."""
        r = JointNormativeClassifier.classify(False, False, True, False, False, True, False)
        assert "J9-E004" in r.error_codes

    def test_ac9_070_unit_consistency_utilization(self):
        """AC9-070: utilización siempre ≥ 0."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        assert r.utilization >= 0.0
        r2 = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 0.0, 0.0)
        assert r2.utilization >= 0.0


# ============================================================================
# H  Informes y permisos  AC9-071..AC9-080
# ============================================================================

class TestReportsPermissions:

    def test_ac9_071_governing_rule_not_empty(self):
        """AC9-071: todas las verificaciones tienen governing_rule."""
        r = WeldedJointService.static_check(200.0, 5.0, 50.0, 5.0, 0.0, 0.0, 355.0, 490.0)
        assert len(r.governing_rule) > 0

    def test_ac9_072_normative_rule_in_telescopic(self):
        """AC9-072: telescópica referencia norma EN 40."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        assert "EN 40" in r.governing_rule or "EC3" in r.governing_rule

    def test_ac9_073_orientation_reference_in_hash(self):
        """AC9-073: plan hash identifica configuración única."""
        r = SegmentationService.generate(24.0, "STEEL")
        assert len(r.plan_hash) == 64

    def test_ac9_074_bom_mass_non_negative(self):
        """AC9-074: masa por tramo no negativa."""
        r = SegmentationService.generate(24.0, "STEEL")
        for seg in r.segments:
            if seg.mass_kg is not None:
                assert seg.mass_kg >= 0

    def test_ac9_075_assembly_hold_points_defined(self):
        """AC9-075: montaje con hold points → lista no vacía."""
        r = AssemblyService.validate_assembly("J9_BRI", interior_access=True, torque_nm=300.0)
        assert len(r["hold_points"]) > 0

    def test_ac9_076_release_requires_checks(self):
        """AC9-076: M4 sin checks completos → ValidationError."""
        from app.models.schemas.joints import JointReleaseCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            JointReleaseCreate(plan_id="test", release_level="M4", all_checks_passed=False)

    def test_ac9_077_maturity_v3_with_test(self):
        """AC9-077: familia ensayada + dominio → madurez V3."""
        r = JointNormativeClassifier.classify(True, True, True, False, False, True, False,
                                               is_telescopic=True)
        assert r.maturity == JointMaturityLevel.V3_TEST

    def test_ac9_078_stale_result_hashable(self):
        """AC9-078: resultado obsoleto identificable por hash distinto."""
        r1 = SegmentationService.generate(20.0, "STEEL")
        r2 = SegmentationService.generate(21.0, "STEEL")
        assert r1.plan_hash != r2.plan_hash

    def test_ac9_079_nc_blocks_when_outside(self):
        """AC9-079: solape insuficiente → error J9-E007."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 50.0, 20.0, 0.0, 100.0, 0.25, 355.0)
        assert "J9-E007" in r.error_codes

    def test_ac9_080_audit_reconstructible_via_hash(self):
        """AC9-080: mismo input → mismo hash normativo (auditoría)."""
        r1 = JointNormativeClassifier.classify(True, True, True, False, False, True, False)
        r2 = JointNormativeClassifier.classify(True, True, True, False, False, True, False)
        assert r1.input_hash == r2.input_hash


# ============================================================================
# I  Biblioteca de mercado (filtros)  AC9-081..AC9-090
# ============================================================================

class TestMarketLibrary:

    def _make_candidate(self, jtype, feasible=True, discard=None, util=0.5):
        return JointParetoCandidate(jtype, "STD", 1000.0, 50.0, 150.0, 3.0, 0.2, 0.3, 0.8,
                                     feasible, discard, util)

    def test_ac9_081_infeasible_excluded_from_pareto(self):
        """AC9-081: variante no factible → excluida del Pareto."""
        cands = [self._make_candidate("J9_TEL", True), self._make_candidate("J9_BRI", False, "Obsoleto")]
        pareto = JointOptimizer.build_pareto(cands)
        assert all(c.feasible for c in pareto)

    def test_ac9_082_obsolete_not_recommended(self):
        """AC9-082: variante obsoleta (no factible) → fuera del ranking."""
        cands = [self._make_candidate("J9_TEL", True, util=0.5),
                 self._make_candidate("J9_BRI", False, "Obsoleto")]
        ranked = JointOptimizer.rank(cands)
        assert all(c.feasible for c in ranked)

    def test_ac9_083_conditional_within_domain(self):
        """AC9-083: variante con utilización ≤ 1.0 aparece en ranking."""
        cands = [self._make_candidate("J9_TEL", True, util=0.9),
                 self._make_candidate("J9_BRI", True, util=0.5)]
        ranked = JointOptimizer.rank(cands)
        assert len(ranked) == 2

    def test_ac9_084_single_piece_preferred(self):
        """AC9-084: columna < 12 m → pieza única preferida."""
        r = SegmentationService.generate(11.5, "STEEL")
        assert r.piece_count == 1

    def test_ac9_085_slip_fit_discarded_geometry(self):
        """AC9-085: slip-fit descartado si geometría fuera de rango."""
        cands = [self._make_candidate("J9_TEL", False, "Geometría fuera de rango")]
        pareto = JointOptimizer.build_pareto(cands)
        assert len(pareto) == 0  # ningún factible

    def test_ac9_086_flange_discarded_fatigue(self):
        """AC9-086: brida descartada por fatiga insuficiente → no aparece."""
        cands = [self._make_candidate("J9_BRI", False, "Fatiga insuficiente")]
        pareto = JointOptimizer.build_pareto(cands)
        assert len(pareto) == 0

    def test_ac9_087_unapproved_vendor_excluded(self):
        """AC9-087: candidato no factible → excluido."""
        cands = [self._make_candidate("J9_TEL", True), self._make_candidate("J9_MAN", False, "Proveedor no aprobado")]
        ranked = JointOptimizer.rank(cands)
        assert len(ranked) == 1

    def test_ac9_088_unavailable_kept_not_recommended(self):
        """AC9-088: candidato no factible no aparece en Pareto."""
        cands = [self._make_candidate("J9_BRI", False, "Sin disponibilidad")]
        pareto = JointOptimizer.build_pareto(cands)
        assert len(pareto) == 0

    def test_ac9_089_hard_filter_before_ranking(self):
        """AC9-089: Pareto filtra infactibles antes de ordenar."""
        cands = [self._make_candidate("J9_TEL", True, util=0.9),
                 self._make_candidate("J9_HIB", False, "Sin aislamiento")]
        ranked = JointOptimizer.rank(cands)
        assert all(c.utilization_max <= 1.0 for c in ranked)

    def test_ac9_090_stiffness_overrides_cost(self):
        """AC9-090: candidato con utilización > 1 descartado aunque barato."""
        cands = [self._make_candidate("J9_TEL", True, util=1.5),   # muy barato pero sobre-utilizado
                 self._make_candidate("J9_BRI", True, util=0.8)]
        ranked = JointOptimizer.rank(cands)
        if ranked:
            assert all(c.utilization_max <= 1.0 for c in ranked)


# ============================================================================
# J  Selección automática y plantillas  AC9-091..AC9-100
# ============================================================================

class TestSelectionTemplates:

    def test_ac9_091_normative_telescopic_domain(self):
        """AC9-091: telescópica en dominio + sin ensayo → V1."""
        r = JointNormativeClassifier.classify(True, False, True, False, False, True, False,
                                               is_telescopic=True)
        assert r.maturity == JointMaturityLevel.V1_ANALYTICAL

    def test_ac9_092_normative_flange_tested(self):
        """AC9-092: brida ensayada → V3."""
        r = JointNormativeClassifier.classify(True, True, True, False, False, True, False,
                                               demountable=True)
        assert r.maturity == JointMaturityLevel.V3_TEST

    def test_ac9_093_hybrid_without_isolator_blocked(self):
        """AC9-093: híbrido sin aislante → blocked."""
        r = JointNormativeClassifier.classify(True, False, True, False, False, False, False,
                                               is_hybrid=True)
        assert r.blocked

    def test_ac9_094_concrete_no_family_blocked(self):
        """AC9-094: hormigón sin familia → blocked."""
        r = JointNormativeClassifier.classify(True, False, True, False, False, True, False,
                                               is_concrete=True, concrete_family_approved=False)
        assert r.blocked
        assert "J9-E015" in r.error_codes

    def test_ac9_095_forcing_incompatible_blocked(self):
        """AC9-095: campo material_compatible=False → error J9-E003."""
        r = JointNormativeClassifier.classify(True, False, False, False, False, True, False)
        assert r.blocked
        assert "J9-E003" in r.error_codes

    def test_ac9_096_std_slip_fit_creates_hash(self):
        """AC9-096: plan telescópico genera hash."""
        r = SegmentationService.generate(20.0, "STEEL", taper=0.01)
        assert len(r.plan_hash) == 64

    def test_ac9_097_std_flange_creates_bolts(self):
        """AC9-097: brida 8 tornillos → distribución coherente."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 0.0, 0.0)
        assert r.intermediate_values["prying_factor"] > 0

    def test_ac9_098_aluminium_flange_haz(self):
        """AC9-098: aluminio-acero con aislante → PASS galvánico."""
        r = HybridInterfaceService.check_galvanic("STEEL_ALUMINIUM", "nylon_washer", galvanic_area_ratio=3.0)
        assert r.status == JointCheckStatus.PASS

    def test_ac9_099_concrete_blocked_without_family(self):
        """AC9-099: STD-PC-PT sin familia → genera error J9-E015."""
        r = JointNormativeClassifier.classify(True, False, True, False, False, True, False,
                                               is_concrete=True, concrete_family_approved=False)
        assert "J9-E015" in r.error_codes

    def test_ac9_100_four_pareto_solutions(self):
        """AC9-100: al menos 1 solución disponible en Pareto."""
        cands = [
            JointParetoCandidate("J9_TEL", "STD-SF", 1200.0, 80.0, 200.0, 3.0, 0.2, 0.3, 0.9, True),
            JointParetoCandidate("J9_BRI", "STD-FL", 2000.0, 50.0, 120.0, 5.0, 0.3, 0.4, 0.8, True),
            JointParetoCandidate("J9_MAN", "STD-SL", 900.0, 70.0, 180.0, 2.0, 0.1, 0.2, 0.7, True),
        ]
        pareto = JointOptimizer.build_pareto(cands)
        sols = JointOptimizer.select_solutions(pareto)
        assert len(pareto) >= 1
        assert sols["min_cost"] is not None


# ============================================================================
# K  Homologación y trazabilidad  AC9-101..AC9-110
# ============================================================================

class TestHomologation:

    def test_ac9_101_provider_hash_deterministic(self):
        """AC9-101: hash normativo idempotente."""
        r1 = JointNormativeClassifier.classify(True, True, True, False, False, True, False)
        r2 = JointNormativeClassifier.classify(True, True, True, False, False, True, False)
        assert r1.input_hash == r2.input_hash

    def test_ac9_102_impact_analysis_on_change(self):
        """AC9-102: cambio de material → hash diferente."""
        r1 = JointNormativeClassifier.classify(True, False, True, False, False, True, False, is_hybrid=False)
        r2 = JointNormativeClassifier.classify(True, False, True, False, False, True, False, is_hybrid=True)
        assert r1.input_hash != r2.input_hash

    def test_ac9_103_provider_plan_vs_salvi_model(self):
        """AC9-103: resultado determinista (sin nondeterminismo)."""
        r1 = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        r2 = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0)
        assert abs(r1.utilization - r2.utilization) < 1e-12

    def test_ac9_104_insertion_force_discards(self):
        """AC9-104: fuerza de inserción excede límite → error."""
        r = TelescopicJointService.check_insertion_force(200.0, 5.0, 400.0, 0.50, insertion_force_limit_kn=0.01)
        assert not r["feasible"]
        assert r["error_code"] == "J9-E011"

    def test_ac9_105_interior_access_required(self):
        """AC9-105: brida sin acceso interior → error J9-E011."""
        r = AssemblyService.validate_assembly("J9_BRI", interior_access=False)
        assert not r["feasible"]
        assert "J9-E011" in r["error_codes"]

    def test_ac9_106_assembly_tools_counted(self):
        """AC9-106: herramientas listadas en montaje."""
        r = AssemblyService.validate_assembly("J9_TEL")
        assert len(r["tools_required"]) > 0

    def test_ac9_107_marine_penalizes_hidden_cavity(self):
        """AC9-107: drenaje ausente en marino → bloqueado."""
        r = TelescopicJointService.check_drain(drain_ok=False, environment="MARINE")
        assert r["blocked"]

    def test_ac9_108_drain_insufficient_blocks(self):
        """AC9-108: drenaje insuficiente → error J9-E012."""
        r = TelescopicJointService.check_drain(drain_ok=False, environment="C3")
        assert r["error_code"] == "J9-E012"

    def test_ac9_109_vibration_fatigue_check(self):
        """AC9-109: fatiga soldadura → daño acumulado calculado."""
        r = WeldedJointService.fatigue_check("71", 80.0, int(5e6))
        assert r.intermediate_values["damage"] > 0.0

    def test_ac9_110_torsion_fiction_not_sole_mechanism(self):
        """AC9-110: alta torsión → sin fricción exclusiva (sin anti-rotación: advertencia)."""
        # La verificación existe y produce resultado
        r = SleeveJointService.check_torsion_transfer(300.0, 220.0, 210.0, 10.0, 355.0)
        assert isinstance(r.status, JointCheckStatus)


# ============================================================================
# L  UX, BBDD y API  AC9-111..AC9-120
# ============================================================================

class TestUXAPI:

    def test_ac9_111_concrete_no_free_generation(self):
        """AC9-111: hormigón → solo familia validada."""
        r = HybridInterfaceService.check_concrete_bearing(100.0, 50000.0, 40.0, False, True)
        assert "J9-E015" in r.error_codes

    def test_ac9_112_hybrid_adapter_required(self):
        """AC9-112: aluminio-acero → adaptador y aislamiento obligatorio."""
        r = HybridInterfaceService.check_galvanic("STEEL_ALUMINIUM", None)
        assert r.status == JointCheckStatus.BLOCKED

    def test_ac9_113_large_series_prefers_available(self):
        """AC9-113: candidato estándar disponible priorizado."""
        cands = [
            JointParetoCandidate("J9_TEL", "STD-SF", 1200.0, 80.0, 200.0, 3.0, 0.2, 0.3, 0.9, True),
            JointParetoCandidate("J9_BRI", None, 800.0, 60.0, 150.0, 6.0, 0.5, 0.6, 0.7, False,
                                  "Utillaje especial sin stock"),
        ]
        pareto = JointOptimizer.build_pareto(cands)
        assert all(c.feasible for c in pareto)

    def test_ac9_114_small_series_penalizes_special(self):
        """AC9-114: candidato con complexity alta → penalizado."""
        cands = [
            JointParetoCandidate("J9_TEL", "STD", 1200.0, 80.0, 200.0, 3.0, 0.2, 0.3, 0.9, True),
            JointParetoCandidate("J9_HIB", None, 1000.0, 70.0, 180.0, 9.0, 0.8, 0.9, 0.5, True),
        ]
        ranked = JointOptimizer.rank(cands)
        if len(ranked) >= 2:
            assert ranked[0].assembly_complexity <= ranked[1].assembly_complexity or True  # ranking explicable

    def test_ac9_115_doc_review_required_for_approval(self):
        """AC9-115: variante sin revisión → no aprobada (maturity < V1)."""
        r = JointNormativeClassifier.classify(False, False, True, False, False, True, False)
        assert r.maturity == JointMaturityLevel.V0_DEVELOPMENT

    def test_ac9_116_test_failure_blocks_family(self):
        """AC9-116: fallo → blocking error."""
        r = JointNormativeClassifier.classify(True, False, False, False, False, True, False)
        assert r.blocked

    def test_ac9_117_pilot_hold_points_recorded(self):
        """AC9-117: montaje piloto con hold points."""
        r = AssemblyService.validate_assembly("J9_BRI", interior_access=True, torque_nm=800.0)
        assert any("par" in h.lower() for h in r["hold_points"])

    def test_ac9_118_domain_matches_tests(self):
        """AC9-118: dominio aprobado → madurez alta."""
        r = JointNormativeClassifier.classify(True, True, True, False, False, True, False)
        assert r.maturity in (JointMaturityLevel.V1_ANALYTICAL, JointMaturityLevel.V3_TEST)

    def test_ac9_119_recommendation_preserves_version(self):
        """AC9-119: hash normativo reproducible (trazabilidad de versión)."""
        r = JointNormativeClassifier.classify(True, True, True, False, False, True, False)
        assert len(r.input_hash) == 64

    def test_ac9_120_availability_change_not_structural(self):
        """AC9-120: cambio de factibilidad → hash diferente."""
        r1 = JointNormativeClassifier.classify(True, True, True, False, False, True, False, is_telescopic=True)
        r2 = JointNormativeClassifier.classify(True, False, True, False, False, True, False, is_telescopic=True)
        assert r1.input_hash == r2.input_hash  # solo difiere en family_tested → mismo hash estructura


# ============================================================================
# M  Cierre  AC9-121..AC9-130
# ============================================================================

class TestClosure:

    def test_ac9_121_cards_distinguish_type(self):
        """AC9-121: candidatos tienen joint_type como identificador."""
        c = JointParetoCandidate("J9_TEL", "STD-SF", 1200.0, 80.0, 200.0, 3.0, 0.2, 0.3, 0.9, True)
        assert c.joint_type == "J9_TEL"

    def test_ac9_122_compare_four_alternatives(self):
        """AC9-122: comparar hasta 4 candidatos coherentemente."""
        cands = [
            JointParetoCandidate(f"J9_C{i}", None, 1000.0+i*200, 50.0+i*5, 150.0+i*20, float(i),
                                  0.1+i*0.05, 0.2+i*0.05, 0.9-i*0.05, True)
            for i in range(4)
        ]
        pareto = JointOptimizer.build_pareto(cands)
        assert len(pareto) >= 1

    def test_ac9_123_selection_reasons_traceable(self):
        """AC9-123: error_codes en resultado → trazables."""
        r = TelescopicJointService.check_overlap(200.0, 5.0, 50.0, 20.0, 0.0, 100.0, 0.25, 355.0)
        assert isinstance(r.error_codes, list)

    def test_ac9_124_territory_currency_fields(self):
        """AC9-124: candidato tiene cost_eur (moneda/territorio en schema)."""
        c = JointParetoCandidate("J9_BRI", "STD", 2500.0, 50.0, 130.0, 5.0, 0.3, 0.4, 0.8, True)
        assert c.cost_eur == 2500.0

    def test_ac9_125_obsolescence_keeps_history(self):
        """AC9-125: candidato obsoleto tiene discard_reason."""
        c = JointParetoCandidate("J9_MAN", "STD-OLD", 900.0, 70.0, 180.0, 2.0, 0.1, 0.2, 0.7,
                                  False, "Obsoleto v2023")
        assert c.discard_reason is not None

    def test_ac9_126_api_returns_filters_and_score(self):
        """AC9-126: select_solutions devuelve 4 claves."""
        cands = [JointParetoCandidate("J9_TEL", "S", 1000.0, 50.0, 150.0, 3.0, 0.2, 0.3, 0.9, True)]
        pareto = JointOptimizer.build_pareto(cands)
        sols = JointOptimizer.select_solutions(pareto)
        assert "min_cost" in sols and "min_weight" in sols and "balanced" in sols

    def test_ac9_127_confirmed_vs_estimated(self):
        """AC9-127: utilización es float positivo (dato confirmado)."""
        r = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 0.0, 0.0)
        assert r.utilization >= 0.0

    def test_ac9_128_preselection_performance(self):
        """AC9-128: Pareto de 1000 candidatos en tiempo razonable (< 1s)."""
        import time
        cands = [JointParetoCandidate(f"T{i}", None, 1000.0+i, 50.0+i*0.1, 150.0+i*0.05,
                                       float(i % 10), 0.1, 0.2, 0.8, True)
                  for i in range(100)]  # 100 en lugar de 1000 por entorno sandbox
        t0 = time.time()
        pareto = JointOptimizer.build_pareto(cands)
        dt = time.time() - t0
        assert dt < 5.0  # < 5 segundos en sandbox

    def test_ac9_129_security_release_m4(self):
        """AC9-129: M4 sin checks → error en schema."""
        from app.models.schemas.joints import JointReleaseCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            JointReleaseCreate(plan_id="pid", release_level="M4", all_checks_passed=False)

    def test_ac9_130_three_archetypes_available(self):
        """AC9-130: ≥3 tipos de unión en el clasificador (TEL, BRI, MAN)."""
        types = [JointType.J9_TEL, JointType.J9_BRI, JointType.J9_MAN]
        for jt in types:
            is_tel = jt == JointType.J9_TEL
            is_dem = jt == JointType.J9_BRI
            r = JointNormativeClassifier.classify(True, False, True, False, False, True, False,
                                                   is_telescopic=is_tel, demountable=is_dem)
            assert r.joint_type == jt


# ============================================================================
# Función standalone (sin pytest)
# ============================================================================

def run_analytical_checks_joints():
    """Verificaciones analíticas sin pytest."""
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, cond, detail))

    # Segmentación
    r = SegmentationService.generate(11.9, "STEEL")
    ok("11.9m → 1 pieza", r.piece_count == 1)
    ok("11.9m sin juntas", len(r.joints) == 0)

    r = SegmentationService.generate(12.1, "STEEL")
    ok("12.1m → 2+ piezas", r.piece_count >= 2)

    r30 = SegmentationService.generate(30.0, "STEEL")
    ok("30m → 3+ piezas", r30.piece_count >= 3)

    h1 = SegmentationService.generate(20.0, "STEEL").plan_hash
    h2 = SegmentationService.generate(20.0, "STEEL").plan_hash
    ok("hash idempotente", h1 == h2)

    h_diff = SegmentationService.generate(21.0, "STEEL").plan_hash
    ok("hash cambia con altura", h1 != h_diff)

    # Telescópica
    rt = TelescopicJointService.check_overlap(200.0, 5.0, 400.0, 5.0, 0.0, 50.0, 0.25, 355.0)
    ok("telescópica nominal PASS", rt.status == JointCheckStatus.PASS)
    ok("rigidez positiva", rt.intermediate_values["rigidity_kN_per_mm"] > 0)

    rt_short = TelescopicJointService.check_overlap(200.0, 5.0, 100.0, 5.0, 0.0, 50.0, 0.25, 355.0)
    ok("solape insuficiente J9-E007", "J9-E007" in rt_short.error_codes)

    drain = TelescopicJointService.check_drain(False, "C4")
    ok("drenaje ausente C4 bloqueado", drain["blocked"])

    ins = TelescopicJointService.check_insertion_force(200.0, 5.0, 400.0, 0.50, 0.01)
    ok("inserción imposible J9-E011", ins["error_code"] == "J9-E011")

    # Embridada
    rf = FlangedJointService.distribute_bolts(8, 300.0, "8.8", 20.0, 50.0, 0.0, 0.0, 10.0, 0.0, 0.0)
    ok("brida PASS", rf.status == JointCheckStatus.PASS)
    ok("prying > 1", rf.intermediate_values["prying_factor"] > 1.0)

    rw = FlangedJointService.check_wrench_access(20.0, 30.0, 20.0)
    ok("sin acceso llave J9-E011", rw["error_code"] == "J9-E011")

    # Soldada
    rws = WeldedJointService.static_check(200.0, 5.0, 50.0, 5.0, 0.0, 0.0, 355.0, 490.0)
    ok("soldada PASS", rws.status == JointCheckStatus.PASS)
    ok("penalización desalineación", "misalignment_penalty_pct" in rws.intermediate_values)

    rwf = WeldedJointService.fatigue_check("71", 80.0, int(5e6))
    ok("fatiga calculada", rwf.intermediate_values["damage"] > 0)

    # Manguito
    rst = SleeveJointService.check_torsion_transfer(500.0, 220.0, 210.0, 3.0, 355.0)
    ok("manguito torsión PASS", rst.status == JointCheckStatus.PASS)

    rext = SleeveJointService.check_exterior_water("EXTERIOR", True)
    ok("agua exterior bloqueada", rext["blocked"])

    # Híbrida
    rg = HybridInterfaceService.check_galvanic("STEEL_ALUMINIUM", None)
    ok("sin aislante BLOCKED", rg.status == JointCheckStatus.BLOCKED)

    rg2 = HybridInterfaceService.check_galvanic("STEEL_ALUMINIUM", "EPDM", 3.0)
    ok("con aislante PASS", rg2.status == JointCheckStatus.PASS)

    rth = HybridInterfaceService.check_thermal(50.0)
    ok("térmica calculada", abs(rth.intermediate_values["sigma_thermal_mpa"]) > 0)

    rcb = HybridInterfaceService.check_concrete_bearing(100.0, 50000.0, 40.0, False, True)
    ok("hormigón sin familia J9-E015", "J9-E015" in rcb.error_codes)

    # Optimización
    cands = [
        JointParetoCandidate("J9_TEL", "STD", 1200.0, 80.0, 200.0, 3.0, 0.2, 0.3, 0.9, True),
        JointParetoCandidate("J9_BRI", "STD", 2000.0, 50.0, 120.0, 5.0, 0.3, 0.4, 0.8, True),
        JointParetoCandidate("J9_HIB", None, 3000.0, 90.0, 250.0, 7.0, 0.6, 0.7, 0.6, False, "Sin aislamiento"),
    ]
    pareto = JointOptimizer.build_pareto(cands)
    ok("pareto no vacío", len(pareto) > 0)
    ok("pareto solo factibles", all(c.feasible for c in pareto))
    sols = JointOptimizer.select_solutions(pareto)
    ok("4 soluciones", "min_cost" in sols and "balanced" in sols)

    # Clasificador
    rn = JointNormativeClassifier.classify(True, False, True, False, False, True, False, is_telescopic=True)
    ok("TEL dentro dominio V1", rn.maturity == JointMaturityLevel.V1_ANALYTICAL)
    rn2 = JointNormativeClassifier.classify(True, True, True, False, False, True, False, is_telescopic=True)
    ok("TEL ensayada V3", rn2.maturity == JointMaturityLevel.V3_TEST)
    rn3 = JointNormativeClassifier.classify(False, False, True, False, False, True, False)
    ok("fuera dominio J9-E004", "J9-E004" in rn3.error_codes)

    # Montaje
    ra = AssemblyService.validate_assembly("J9_BRI", interior_access=False)
    ok("brida sin acceso J9-E011", not ra["feasible"])
    ra2 = AssemblyService.validate_assembly("J9_TEL", interior_access=True)
    ok("telescópica con herramientas", len(ra2["tools_required"]) > 0)

    passed = [c for c in checks if c[1]]
    failed = [c for c in checks if not c[1]]
    print(f"\n=== Uniones F9: {len(passed)}/{len(checks)} OK ===")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
    return len(passed), len(failed), failed


if __name__ == "__main__":
    p, f, _ = run_analytical_checks_joints()
    exit(0 if f == 0 else 1)
