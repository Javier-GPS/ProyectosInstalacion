"""
Salvi Studio · Columns — Test Aceptación Fase 14
CAD paramétrico, BOM y documentación industrial
200 ACs — completamente analíticos, sin DB/red
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import pathlib
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

# ── Mock injection (sin DB ni SQLAlchemy) ────────────────────────────────────

for _mod in [
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql", "alembic", "alembic.op",
    "asyncpg", "fastapi", "fastapi.routing",
    "app.models.db.cad_bom",
    "app.models.schemas.cad_bom",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

SERVICE_PATH = (
    pathlib.Path(__file__).parents[2] / "app" / "services" / "cad_bom_service.py"
)

def _load_service():
    spec = importlib.util.spec_from_file_location(
        "app.services.cad_bom_service", SERVICE_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["app.services.cad_bom_service"] = mod
    spec.loader.exec_module(mod)
    return mod


svc = _load_service()

# Alias de clases
ProductDefinitionService  = svc.ProductDefinitionService
CadGenerationService      = svc.CadGenerationService
DrawingService            = svc.DrawingService
BomService                = svc.BomService
RoutingService            = svc.RoutingService
ValidationService         = svc.ValidationService
ReleaseService            = svc.ReleaseService
DocumentService           = svc.DocumentService
IntegrationService        = svc.IntegrationService
ArtifactStore             = svc.ArtifactStore
QualityService            = svc.QualityService
ArtifactManifestService   = svc.ArtifactManifestService

# Dataclasses
ProductSnapshotData       = svc.ProductSnapshotData
PhysicalProperties        = svc.PhysicalProperties
BendDevelopment           = svc.BendDevelopment
ValidationCheck           = svc.ValidationCheck
ValidationReport          = svc.ValidationReport
CadJobResult              = svc.CadJobResult
DrawingJobResult          = svc.DrawingJobResult
BomBuildResult            = svc.BomBuildResult
MassReconciliation        = svc.MassReconciliation
ReleaseGateResult         = svc.ReleaseGateResult
MakeBuyComparison         = svc.MakeBuyComparison
ArtifactEntry             = svc.ArtifactEntry
ManifestResult            = svc.ManifestResult

# Constantes
MASS_THRESHOLD            = svc.MASS_RECONCILIATION_THRESHOLD
STEEL_DENSITY             = svc.STEEL_DENSITY_KG_M3
ALUMINUM_DENSITY          = svc.ALUMINUM_DENSITY_KG_M3
K_FACTOR_DEFAULT          = svc.K_FACTOR_DEFAULT
K_FACTOR_ALUMINUM         = svc.K_FACTOR_ALUMINUM
DXF_LAYERS                = svc.DXF_LAYERS
RELEASE_GATES             = svc.RELEASE_GATES
SNAPSHOT_TRANSITIONS      = svc.SNAPSHOT_TRANSITIONS
CHANGE_CLASS_REQUIRES_RECALC = svc.CHANGE_CLASS_REQUIRES_RECALC


# ── Fixtures ─────────────────────────────────────────────────────────────────

def make_snapshot(
    product_code="STL-COL-001",
    revision="A",
    state="DRAFT",
    material="S355",
    cad_level="G2_ENGINEERING",
    geometry_params=None,
    structural_hashes=None,
    library_versions=None,
) -> ProductSnapshotData:
    gp = geometry_params or {"shape_type": "CONE", "height_mm": 4000}
    sh = structural_hashes or {"phase4_solver": "abc123"}
    lv = library_versions or {"columns_engine": "14.0.0"}
    return ProductDefinitionService.build_snapshot_data(
        snapshot_id=uuid4(),
        product_code=product_code,
        revision=revision,
        state=state,
        geometry_params=gp,
        structural_hashes=sh,
        library_versions=lv,
        material=material,
        cad_level=cad_level,
    )


def make_bom_lines(count: int = 3, mass_unit: float = 10.0) -> list:
    return [
        {
            "item_code": f"P-{i:03d}",
            "description": f"Part {i}",
            "line_type": "MANUFACTURED",
            "quantity": 1.0,
            "quantity_unit": "EA",
            "scrap_factor": 0.0,
            "mass_kg_unit": mass_unit,
            "cost_eur_unit": 50.0,
            "material": "S355",
        }
        for i in range(count)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# AC001-020: ProductSnapshot, inmutabilidad, estados, hashes
# ══════════════════════════════════════════════════════════════════════════════

class TestProductSnapshot:

    def test_ac001_snapshot_hash_deterministic(self):
        """AC001: Mismo input → mismo hash."""
        h1 = ProductDefinitionService.compute_snapshot_hash(
            "P-001","A",{"h":4000},{"k":"abc"},{"e":"1.0"}
        )
        h2 = ProductDefinitionService.compute_snapshot_hash(
            "P-001","A",{"h":4000},{"k":"abc"},{"e":"1.0"}
        )
        assert h1 == h2

    def test_ac002_snapshot_hash_sha256_format(self):
        """AC002: Hash es SHA-256 (64 hex chars)."""
        h = ProductDefinitionService.compute_snapshot_hash("P","A",{},{},{})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_ac003_different_product_codes_different_hash(self):
        """AC003: Códigos de producto distintos → hashes distintos."""
        h1 = ProductDefinitionService.compute_snapshot_hash("P-001","A",{},{},{})
        h2 = ProductDefinitionService.compute_snapshot_hash("P-002","A",{},{},{})
        assert h1 != h2

    def test_ac004_different_revision_different_hash(self):
        """AC004: Revisión distinta → hash distinto."""
        h1 = ProductDefinitionService.compute_snapshot_hash("P","A",{},{},{})
        h2 = ProductDefinitionService.compute_snapshot_hash("P","B",{},{},{})
        assert h1 != h2

    def test_ac005_geometry_params_affect_hash(self):
        """AC005: Cambio en geometry_params → hash distinto."""
        h1 = ProductDefinitionService.compute_snapshot_hash("P","A",{"h":4000},{},{})
        h2 = ProductDefinitionService.compute_snapshot_hash("P","A",{"h":5000},{},{})
        assert h1 != h2

    def test_ac006_structural_hashes_affect_snapshot_hash(self):
        """AC006: Cambio en structural_hashes → hash distinto."""
        h1 = ProductDefinitionService.compute_snapshot_hash("P","A",{},{"k":"abc"},{})
        h2 = ProductDefinitionService.compute_snapshot_hash("P","A",{},{"k":"def"},{})
        assert h1 != h2

    def test_ac007_library_versions_affect_hash(self):
        """AC007: Cambio en library_versions → hash distinto."""
        h1 = ProductDefinitionService.compute_snapshot_hash("P","A",{},{},{"e":"1.0"})
        h2 = ProductDefinitionService.compute_snapshot_hash("P","A",{},{},{"e":"2.0"})
        assert h1 != h2

    def test_ac008_build_snapshot_data_returns_dataclass(self):
        """AC008: build_snapshot_data devuelve ProductSnapshotData con hash."""
        snap = make_snapshot()
        assert isinstance(snap, ProductSnapshotData)
        assert snap.snapshot_hash is not None
        assert len(snap.snapshot_hash) == 64

    def test_ac009_immutability_released_state(self):
        """AC009: Estado RELEASED → validate_immutability retorna error."""
        err = ProductDefinitionService.validate_immutability("RELEASED", "update_geometry")
        assert err is not None
        assert "RELEASED" in err

    def test_ac010_immutability_obsolete_state(self):
        """AC010: Estado OBSOLETE → validate_immutability retorna error."""
        err = ProductDefinitionService.validate_immutability("OBSOLETE", "modify")
        assert err is not None

    def test_ac011_immutability_draft_allowed(self):
        """AC011: Estado DRAFT → validate_immutability retorna None."""
        err = ProductDefinitionService.validate_immutability("DRAFT", "update_geometry")
        assert err is None

    def test_ac012_valid_transitions_draft(self):
        """AC012: DRAFT puede transicionar a REVIEW."""
        assert ProductDefinitionService.can_transition("DRAFT", "REVIEW")

    def test_ac013_invalid_transition_draft_released(self):
        """AC013: DRAFT no puede ir directamente a RELEASED."""
        assert not ProductDefinitionService.can_transition("DRAFT", "RELEASED")

    def test_ac014_transition_approved_to_released(self):
        """AC014: APPROVED → RELEASED es válido."""
        assert ProductDefinitionService.can_transition("APPROVED", "RELEASED")

    def test_ac015_no_transition_from_released(self):
        """AC015: RELEASED sólo puede ir a OBSOLETE."""
        assert not ProductDefinitionService.can_transition("RELEASED", "DRAFT")
        assert ProductDefinitionService.can_transition("RELEASED", "OBSOLETE")

    def test_ac016_next_revision_alpha(self):
        """AC016: next_revision('A') == 'B'."""
        assert ProductDefinitionService.next_revision("A") == "B"

    def test_ac017_next_revision_z_to_aa(self):
        """AC017: next_revision('Z') == 'AA'."""
        assert ProductDefinitionService.next_revision("Z") == "AA"

    def test_ac018_next_revision_aa_to_ab(self):
        """AC018: next_revision('AA') == 'AB'."""
        assert ProductDefinitionService.next_revision("AA") == "AB"

    def test_ac019_cad_level_progression_valid(self):
        """AC019: G1 → G2 es progresión válida."""
        assert ProductDefinitionService.validate_cad_level_progression(
            "G1_CALC", "G2_ENGINEERING"
        )

    def test_ac020_cad_level_regression_invalid(self):
        """AC020: G3 → G1 es regresión inválida."""
        assert not ProductDefinitionService.validate_cad_level_progression(
            "G3_MANUFACTURING", "G1_CALC"
        )


# ══════════════════════════════════════════════════════════════════════════════
# AC021-040: Fustes, tramos, puertas, brazos — propiedades físicas
# ══════════════════════════════════════════════════════════════════════════════

class TestPhysicalProperties:

    def test_ac021_cylinder_volume_formula(self):
        """AC021: Volumen cilindro hueco = π(ro²-ri²)·L."""
        props = CadGenerationService.compute_cylinder_properties(
            outer_diameter_mm=114.3,
            inner_diameter_mm=110.0,
            length_mm=1000.0,
        )
        ro, ri = 0.05715, 0.055
        expected_vol = math.pi * (ro**2 - ri**2) * 1.0 * 1e6
        assert abs(props.volume_cm3 - expected_vol) < 0.01

    def test_ac022_cylinder_mass_steel(self):
        """AC022: Masa cilindro acero = volumen × 7850."""
        props = CadGenerationService.compute_cylinder_properties(
            outer_diameter_mm=114.3,
            inner_diameter_mm=110.0,
            length_mm=1000.0,
            material="STEEL",
        )
        assert props.mass_kg > 0
        vol_m3 = props.volume_cm3 / 1e6
        assert abs(props.mass_kg - vol_m3 * 7850) < 0.001

    def test_ac023_cylinder_mass_aluminum_lighter(self):
        """AC023: Misma geometría, aluminio < acero."""
        p_steel = CadGenerationService.compute_cylinder_properties(100, 96, 1000, "STEEL")
        p_alum  = CadGenerationService.compute_cylinder_properties(100, 96, 1000, "6082")
        assert p_alum.mass_kg < p_steel.mass_kg

    def test_ac024_cylinder_surface_area(self):
        """AC024: Superficie cilindro = 2π·ro·L."""
        props = CadGenerationService.compute_cylinder_properties(200, 194, 3000)
        ro = 0.1
        L  = 3.0
        expected = 2 * math.pi * ro * L
        assert abs(props.surface_area_m2 - expected) < 0.001

    def test_ac025_cylinder_cog_at_midheight(self):
        """AC025: Centro de gravedad cilindro = L/2."""
        props = CadGenerationService.compute_cylinder_properties(100, 96, 2000)
        assert abs(props.center_of_gravity[2] - 1.0) < 1e-6

    def test_ac026_cone_mass_positive(self):
        """AC026: Masa cono/troncocono siempre positiva."""
        props = CadGenerationService.compute_cone_properties(
            outer_diameter_top_mm=60,
            outer_diameter_bot_mm=120,
            thickness_mm=4,
            height_mm=5000,
        )
        assert props.mass_kg > 0

    def test_ac027_cone_volume_larger_base_heavier(self):
        """AC027: Base más ancha → mayor masa."""
        p1 = CadGenerationService.compute_cone_properties(60, 120, 4, 5000)
        p2 = CadGenerationService.compute_cone_properties(60, 80, 4, 5000)
        assert p1.mass_kg > p2.mass_kg

    def test_ac028_plate_volume(self):
        """AC028: Volumen chapa = L × W × T."""
        props = CadGenerationService.compute_plate_properties(500, 300, 10)
        expected_vol = 500 * 300 * 10 / 1000.0  # cm³
        assert abs(props.volume_cm3 - expected_vol) < 0.01

    def test_ac029_plate_mass_steel(self):
        """AC029: Masa chapa acero = vol × 7850."""
        props = CadGenerationService.compute_plate_properties(500, 300, 10, "S355")
        vol_m3 = props.volume_cm3 / 1e6
        assert abs(props.mass_kg - vol_m3 * 7850) < 0.001

    def test_ac030_plate_surface_area(self):
        """AC030: Superficie chapa incluye 6 caras."""
        L, W, T = 0.5, 0.3, 0.01
        expected = 2 * (L*W + L*T + W*T)
        props = CadGenerationService.compute_plate_properties(500, 300, 10)
        assert abs(props.surface_area_m2 - expected) < 1e-6

    def test_ac031_density_steel_constant(self):
        """AC031: Densidad acero constante = 7850 kg/m³."""
        assert STEEL_DENSITY == 7850.0

    def test_ac032_density_aluminum_constant(self):
        """AC032: Densidad aluminio constante = 2700 kg/m³."""
        assert ALUMINUM_DENSITY == 2700.0

    def test_ac033_aluminum_density_ratio(self):
        """AC033: Ratio densidades Al/Fe ≈ 0.344."""
        ratio = ALUMINUM_DENSITY / STEEL_DENSITY
        assert abs(ratio - 2700/7850) < 1e-6

    def test_ac034_zero_thickness_produces_zero_mass_plate(self):
        """AC034: Chapa grosor 0 → masa 0."""
        props = CadGenerationService.compute_plate_properties(500, 300, 0)
        assert props.mass_kg == pytest.approx(0.0)

    def test_ac035_cylinder_zero_wall_zero_volume(self):
        """AC035: Cilindro con D_ext == D_int → volumen ≈ 0."""
        props = CadGenerationService.compute_cylinder_properties(100, 100, 1000)
        assert abs(props.volume_cm3) < 1e-6


# ══════════════════════════════════════════════════════════════════════════════
# AC036-060: Desarrollos de chapa, plegados, DXF, capas
# ══════════════════════════════════════════════════════════════════════════════

class TestDevelopmentAndDxf:

    def test_ac036_k_factor_steel(self):
        """AC036: K-factor acero = 0.44."""
        assert K_FACTOR_DEFAULT == pytest.approx(0.44)

    def test_ac037_k_factor_aluminum(self):
        """AC037: K-factor aluminio = 0.40."""
        assert K_FACTOR_ALUMINUM == pytest.approx(0.40)

    def test_ac038_bend_neutral_radius(self):
        """AC038: Radio neutro = ri + k×t."""
        bd = CadGenerationService.compute_bend_development(10, 90, 4, "STEEL")
        assert abs(bd.neutral_radius_mm - (10 + K_FACTOR_DEFAULT * 4)) < 1e-6

    def test_ac039_bend_arc_length_90deg(self):
        """AC039: Arco 90° = π/2 × r_neutro."""
        bd = CadGenerationService.compute_bend_development(10, 90, 4, "STEEL")
        expected = bd.neutral_radius_mm * math.pi / 2
        assert abs(bd.arc_length_mm - expected) < 1e-6

    def test_ac040_bend_arc_length_180deg(self):
        """AC040: Arco 180° = π × r_neutro."""
        bd = CadGenerationService.compute_bend_development(5, 180, 3, "STEEL")
        expected = bd.neutral_radius_mm * math.pi
        assert abs(bd.arc_length_mm - expected) < 1e-6

    def test_ac041_bend_aluminum_smaller_k(self):
        """AC041: Plegado Al tiene arco más pequeño que acero (menor k)."""
        bd_steel = CadGenerationService.compute_bend_development(10, 90, 4, "STEEL")
        bd_alum  = CadGenerationService.compute_bend_development(10, 90, 4, "6082")
        assert bd_alum.arc_length_mm < bd_steel.arc_length_mm

    def test_ac042_developed_sheet_sum(self):
        """AC042: Longitud desarrollada = Σ_legs + Σ_arcos."""
        bends = [
            CadGenerationService.compute_bend_development(10, 90, 4),
            CadGenerationService.compute_bend_development(10, 90, 4),
        ]
        legs = [100.0, 200.0, 150.0]
        total = CadGenerationService.compute_developed_sheet(legs, bends)
        expected = sum(legs) + sum(b.arc_length_mm for b in bends)
        assert abs(total - expected) < 1e-6

    def test_ac043_zero_bends_sheet(self):
        """AC043: Sin plegados, longitud desarrollada = suma piernas."""
        total = CadGenerationService.compute_developed_sheet([300.0, 200.0], [])
        assert abs(total - 500.0) < 1e-6

    def test_ac044_dxf_layers_count(self):
        """AC044: Hay exactamente 8 capas DXF estándar."""
        assert len(DXF_LAYERS) == 8

    def test_ac045_dxf_layers_mandatory_present(self):
        """AC045: CUT_OUTER y CENTER están en la lista de capas."""
        assert "CUT_OUTER" in DXF_LAYERS
        assert "CENTER" in DXF_LAYERS

    def test_ac046_dxf_layer_spec_cut_outer(self):
        """AC046: CUT_OUTER tiene linetype CONTINUOUS."""
        spec = CadGenerationService.get_dxf_layer_spec("CUT_OUTER")
        assert spec is not None
        assert spec.linetype == "CONTINUOUS"

    def test_ac047_dxf_layer_spec_bend_up_dashed(self):
        """AC047: BEND_UP tiene linetype DASHED."""
        spec = CadGenerationService.get_dxf_layer_spec("BEND_UP")
        assert spec is not None
        assert "DASHED" in spec.linetype

    def test_ac048_dxf_layer_spec_unknown_returns_none(self):
        """AC048: Capa desconocida → None."""
        assert CadGenerationService.get_dxf_layer_spec("UNKNOWN_LAYER") is None

    def test_ac049_dxf_validate_missing_cut_outer(self):
        """AC049: Ausencia de CUT_OUTER → reportada como faltante."""
        missing = CadGenerationService.validate_dxf_layers(["CENTER", "BEND_UP"])
        assert "CUT_OUTER" in missing

    def test_ac050_dxf_validate_all_mandatory_present(self):
        """AC050: Con CUT_OUTER y CENTER → sin faltantes obligatorias."""
        missing = CadGenerationService.validate_dxf_layers(DXF_LAYERS)
        assert len(missing) == 0

    def test_ac051_artifact_checksum_sha256(self):
        """AC051: Checksum artefacto = SHA-256 del contenido."""
        content = b"fake step content"
        cs = CadGenerationService.compute_artifact_checksum(content)
        assert cs == hashlib.sha256(content).hexdigest()

    def test_ac052_cad_job_result_valid_state(self):
        """AC052: build_cad_job_result STEP → state='VALID', format='STEP'."""
        r = CadGenerationService.build_cad_job_result(uuid4(), "CAD_STEP")
        assert r.state == "VALID"
        assert r.format == "STEP"

    def test_ac053_cad_job_result_dxf_format(self):
        """AC053: build_cad_job_result DXF → format='DXF'."""
        r = CadGenerationService.build_cad_job_result(uuid4(), "CAD_DXF")
        assert r.format == "DXF"

    def test_ac054_cad_job_result_error_state(self):
        """AC054: Resultado con error → state='ERROR', checksum=None."""
        r = CadGenerationService.build_cad_job_result(
            uuid4(), "CAD_STEP", state="ERROR", error_message="Geometry error"
        )
        assert r.state == "ERROR"
        assert r.checksum is None
        assert r.error_message is not None

    def test_ac055_cad_job_has_generator_version(self):
        """AC055: Resultado CAD incluye generator_version."""
        r = CadGenerationService.build_cad_job_result(uuid4(), "CAD_GLB")
        assert r.generator_version is not None
        assert len(r.generator_version) > 0


# ══════════════════════════════════════════════════════════════════════════════
# AC056-080: Planos, cotas, soldaduras, tolerancias
# ══════════════════════════════════════════════════════════════════════════════

class TestDrawingService:

    def test_ac056_view_selection_cylinder_includes_section(self):
        """AC056: Cilindro → vistas incluyen SECTION_AA."""
        views = DrawingService.select_views({"shape_type": "CYLINDER"})
        assert "SECTION_AA" in views

    def test_ac057_view_selection_always_includes_front(self):
        """AC057: Cualquier geometría → FRONT siempre presente."""
        for shape in ("CYLINDER", "CONE", "PLATE", "BRACKET"):
            views = DrawingService.select_views({"shape_type": shape})
            assert "FRONT" in views, f"FRONT ausente para {shape}"

    def test_ac058_view_selection_door_adds_detail(self):
        """AC058: has_door=True → incluye DETAIL_DOOR."""
        views = DrawingService.select_views({"shape_type": "CONE", "has_door": True})
        assert "DETAIL_DOOR" in views

    def test_ac059_view_selection_no_duplicates(self):
        """AC059: Lista de vistas sin duplicados."""
        views = DrawingService.select_views(
            {"shape_type": "CYLINDER", "has_door": True, "has_holes": True}
        )
        assert len(views) == len(set(views))

    def test_ac060_cajetin_missing_field_blocking(self):
        """AC060: Campo obligatorio faltante en cajetín → BLOCKING."""
        # Omitir 'revision'
        fields = ["product_code","scale","material","mass","date","drawn_by","approved_by"]
        checks = DrawingService.validate_drawing_completeness(["FRONT"], fields, 50, 100.0)
        blocking = [c for c in checks if c.severity == "BLOCKING"]
        assert any("revision" in c.check_code.lower() or "revision" in c.message.lower()
                   for c in blocking)

    def test_ac061_cajetin_all_fields_no_blocking(self):
        """AC061: Todos los campos cajetín presentes → sin BLOCKING por cajetín."""
        fields = DrawingService.CAJETIN_REQUIRED_FIELDS
        checks = DrawingService.validate_drawing_completeness(["FRONT"], fields, 50, 100.0)
        blocking = [c for c in checks if c.check_code.startswith("DRW-CAJETIN")]
        assert len(blocking) == 0

    def test_ac062_missing_front_view_error(self):
        """AC062: Sin vista FRONT → ERROR."""
        fields = DrawingService.CAJETIN_REQUIRED_FIELDS
        checks = DrawingService.validate_drawing_completeness(
            ["SECTION_AA"], fields, 50, 100.0
        )
        codes = [c.check_code for c in checks]
        assert any("VIEW" in c for c in codes)

    def test_ac063_dimension_density_warning(self):
        """AC063: Densidad de cotas baja → WARNING."""
        fields = DrawingService.CAJETIN_REQUIRED_FIELDS
        checks = DrawingService.validate_drawing_completeness(
            ["FRONT"], fields, 1, 1000.0  # muy pocas cotas en área grande
        )
        warnings = [c for c in checks if c.severity == "WARNING" and "DIM" in c.check_code]
        assert len(warnings) > 0

    def test_ac064_dimension_density_ok_no_warning(self):
        """AC064: Alta densidad de cotas → sin WARNING de densidad."""
        fields = DrawingService.CAJETIN_REQUIRED_FIELDS
        checks = DrawingService.validate_drawing_completeness(
            ["FRONT"], fields, 100, 10.0  # muchas cotas, área pequeña
        )
        dim_warnings = [c for c in checks if "DIM-DENSITY" in c.check_code]
        assert len(dim_warnings) == 0

    def test_ac065_drawing_code_general_arrangement(self):
        """AC065: Código plano GENERAL_ARRANGEMENT = GA-..."""
        code = DrawingService.build_drawing_code("STL-001", "GENERAL_ARRANGEMENT", "A")
        assert code.startswith("GA-")

    def test_ac066_drawing_code_detail(self):
        """AC066: Código plano DETAIL = DT-..."""
        code = DrawingService.build_drawing_code("STL-001", "DETAIL", "A")
        assert code.startswith("DT-")

    def test_ac067_drawing_code_contains_product_code(self):
        """AC067: Código plano contiene product_code."""
        code = DrawingService.build_drawing_code("STL-001", "ASSEMBLY", "B")
        assert "STL-001" in code

    def test_ac068_drawing_result_fit_for_manufacture_no_blockers(self):
        """AC068: Sin bloqueantes → is_fit_for_manufacture=True."""
        result = DrawingService.build_drawing_result(
            uuid4(), "STL-001", "DETAIL", "A", []
        )
        assert result.is_fit_for_manufacture is True

    def test_ac069_drawing_result_not_fit_with_blocking(self):
        """AC069: Con BLOCKING → is_fit_for_manufacture=False."""
        blocker = ValidationCheck("DRW-X", "BLOCKING", "Test blocker")
        result = DrawingService.build_drawing_result(
            uuid4(), "STL-001", "DETAIL", "A", [blocker]
        )
        assert result.is_fit_for_manufacture is False

    def test_ac070_drawing_result_errors_propagated(self):
        """AC070: Errores de validación se incluyen en resultado."""
        err = ValidationCheck("DRW-ERR", "ERROR", "Missing dimension")
        result = DrawingService.build_drawing_result(
            uuid4(), "STL-001", "DETAIL", "A", [err]
        )
        assert len(result.validation_errors) > 0


# ══════════════════════════════════════════════════════════════════════════════
# AC071-100: EBOM/MBOM/PBOM/SBOM, cantidades, mermas, sustituciones
# ══════════════════════════════════════════════════════════════════════════════

class TestBomService:

    def test_ac071_quantity_with_zero_scrap(self):
        """AC071: scrap_factor=0 → cantidad bruta = neta."""
        qty = BomService.compute_quantity_with_scrap(10.0, 0.0)
        assert qty == pytest.approx(10.0)

    def test_ac072_quantity_with_scrap_10pct(self):
        """AC072: scrap_factor=0.10 → cantidad bruta = neta / 0.9."""
        qty = BomService.compute_quantity_with_scrap(9.0, 0.10)
        assert qty == pytest.approx(10.0)

    def test_ac073_scrap_factor_invalid_raises(self):
        """AC073: scrap_factor >= 1.0 → ValueError."""
        with pytest.raises(ValueError):
            BomService.compute_quantity_with_scrap(10.0, 1.0)

    def test_ac074_scrap_factor_negative_raises(self):
        """AC074: scrap_factor < 0 → ValueError."""
        with pytest.raises(ValueError):
            BomService.compute_quantity_with_scrap(10.0, -0.1)

    def test_ac075_lot_quantity_min_lot(self):
        """AC075: Cantidad redondeada al lote mínimo."""
        qty = BomService.compute_lot_quantity(3.0, min_lot=5.0)
        assert qty == pytest.approx(5.0)

    def test_ac076_lot_quantity_exceeds_min(self):
        """AC076: Cantidad > lote mínimo → sin cambio."""
        qty = BomService.compute_lot_quantity(10.0, min_lot=5.0)
        assert qty == pytest.approx(10.0)

    def test_ac077_lot_quantity_multiple_of(self):
        """AC077: Cantidad redondeada a múltiplo."""
        qty = BomService.compute_lot_quantity(7.0, min_lot=1.0, multiple_of=3.0)
        assert qty == pytest.approx(9.0)

    def test_ac078_mass_reconciliation_within_threshold(self):
        """AC078: Δmasa ≤ 0.5% → is_within_threshold=True."""
        lines = make_bom_lines(3, mass_unit=10.0)
        recon = BomService.reconcile_mass(30.1, lines)
        assert recon.is_within_threshold

    def test_ac079_mass_reconciliation_exceeds_threshold(self):
        """AC079: Δmasa > 0.5% → is_within_threshold=False."""
        lines = make_bom_lines(3, mass_unit=10.0)  # total BOM = 30 kg
        recon = BomService.reconcile_mass(31.0, lines)   # Δ=1 kg / 31 kg ≈ 3.2%
        assert not recon.is_within_threshold

    def test_ac080_mass_reconciliation_threshold_value(self):
        """AC080: Umbral de reconciliación = 0.5%."""
        assert MASS_THRESHOLD == pytest.approx(0.005)

    def test_ac081_mass_reconciliation_excludes_consumables(self):
        """AC081: Consumibles excluidos de masa BOM en reconciliación."""
        lines = make_bom_lines(2, mass_unit=10.0)
        consumable = {
            "item_code": "C-001",
            "description": "Grease",
            "line_type": "CONSUMABLE",
            "quantity": 1.0,
            "quantity_unit": "KG",
            "scrap_factor": 0.0,
            "mass_kg_unit": 100.0,  # enorme, pero debe excluirse
            "cost_eur_unit": 5.0,
        }
        lines_with_consumable = lines + [consumable]
        recon = BomService.reconcile_mass(20.0, lines_with_consumable)
        assert recon.mass_kg_bom == pytest.approx(20.0)  # consumible excluido

    def test_ac082_mass_reconciliation_excludes_waste(self):
        """AC082: Residuos excluidos de masa BOM."""
        lines = make_bom_lines(2, mass_unit=5.0)
        waste = {
            "item_code": "W-001",
            "description": "Scrap",
            "line_type": "WASTE",
            "quantity": 1.0,
            "quantity_unit": "KG",
            "scrap_factor": 0.0,
            "mass_kg_unit": 50.0,
            "cost_eur_unit": 0.0,
        }
        recon = BomService.reconcile_mass(10.0, lines + [waste])
        assert recon.mass_kg_bom == pytest.approx(10.0)

    def test_ac083_bom_hash_deterministic(self):
        """AC083: Mismo BOM → mismo hash."""
        sid = uuid4()
        lines = make_bom_lines(3)
        h1 = BomService.compute_bom_hash(sid, "EBOM", lines)
        h2 = BomService.compute_bom_hash(sid, "EBOM", lines)
        assert h1 == h2

    def test_ac084_bom_hash_different_views(self):
        """AC084: Misma BOM, distinta vista → hashes distintos."""
        sid = uuid4()
        lines = make_bom_lines(3)
        h_ebom = BomService.compute_bom_hash(sid, "EBOM", lines)
        h_mbom = BomService.compute_bom_hash(sid, "MBOM", lines)
        assert h_ebom != h_mbom

    def test_ac085_bom_build_result_line_count(self):
        """AC085: build_bom_result devuelve line_count correcto."""
        sid = uuid4()
        lines = make_bom_lines(5, mass_unit=10.0)
        result = BomService.build_bom_result(sid, "EBOM", lines, 50.0)
        assert result.line_count == 5

    def test_ac086_bom_build_total_cost(self):
        """AC086: Total coste = Σ(qty × coste_unit)."""
        sid = uuid4()
        lines = make_bom_lines(3, mass_unit=10.0)  # 3 × 50€ = 150€
        result = BomService.build_bom_result(sid, "EBOM", lines, 30.0)
        assert result.total_cost_eur == pytest.approx(150.0)

    def test_ac087_bom_reconciliation_ok_flag(self):
        """AC087: mass_reconciliation_ok=True cuando masa está dentro del umbral."""
        sid = uuid4()
        lines = make_bom_lines(3, mass_unit=10.0)
        result = BomService.build_bom_result(sid, "EBOM", lines, 30.0)
        assert result.mass_reconciliation_ok is True

    def test_ac088_substitution_same_material_ok(self):
        """AC088: Sustitución mismo material → compatible."""
        original  = {"material": "S355", "mass_kg_unit": 10.0}
        substitute= {"material": "S355", "mass_kg_unit": 10.2}
        ok, issues = BomService.check_substitution_compatibility(original, substitute)
        assert ok

    def test_ac089_substitution_steel_grades_ok(self):
        """AC089: Sustitución entre grados de acero S235/S275/S355 → compatible."""
        original  = {"material": "S235", "mass_kg_unit": 10.0}
        substitute= {"material": "S275", "mass_kg_unit": 10.0}
        ok, issues = BomService.check_substitution_compatibility(original, substitute)
        assert ok

    def test_ac090_substitution_steel_to_aluminum_incompatible(self):
        """AC090: Sustitución acero → aluminio → incompatible."""
        original  = {"material": "S355", "mass_kg_unit": 10.0}
        substitute= {"material": "6082", "mass_kg_unit": 3.5}
        ok, issues = BomService.check_substitution_compatibility(original, substitute)
        assert not ok

    def test_ac091_substitution_mass_difference_over_10pct(self):
        """AC091: Diferencia de masa >10% → issue reportado."""
        original  = {"material": "S355", "mass_kg_unit": 10.0}
        substitute= {"material": "S355", "mass_kg_unit": 12.0}
        ok, issues = BomService.check_substitution_compatibility(original, substitute)
        assert not ok
        assert any("masa" in i.lower() or "mass" in i.lower() for i in issues)

    def test_ac092_bom_hash_sha256_length(self):
        """AC092: Hash BOM es SHA-256 (64 chars)."""
        h = BomService.compute_bom_hash(uuid4(), "EBOM", [])
        assert len(h) == 64

    def test_ac093_phantom_excluded_from_cost(self):
        """AC093: Líneas PHANTOM excluidas de masa BOM."""
        phantom = {
            "item_code": "PH-001",
            "description": "Phantom assembly",
            "line_type": "PHANTOM",
            "quantity": 1.0,
            "quantity_unit": "EA",
            "scrap_factor": 0.0,
            "mass_kg_unit": 999.0,
            "cost_eur_unit": 0.0,
        }
        lines = make_bom_lines(1, mass_unit=10.0)
        recon = BomService.reconcile_mass(10.0, lines + [phantom])
        # PHANTOM se comporta como MANUFACTURED — verificar que solo lineas PHANTOM
        # que explícitamente se excluyen. En nuestra implementación solo excluimos
        # CONSUMABLE, WASTE, PHANTOM.
        # Si PHANTOM se excluye → mass_bom = 10.0
        assert recon.mass_kg_bom == pytest.approx(10.0)

    def test_ac094_bom_build_result_hash_present(self):
        """AC094: BomBuildResult tiene bom_hash no vacío."""
        result = BomService.build_bom_result(uuid4(), "MBOM", make_bom_lines(2), 20.0)
        assert len(result.bom_hash) == 64

    def test_ac095_bom_quantity_rule_types(self):
        """AC095: QUANTITY_RULES contiene DIRECT, GEOMETRIC, FORMULA, YIELD."""
        for rule in ("DIRECT", "GEOMETRIC", "FORMULA", "YIELD"):
            assert rule in BomService.QUANTITY_RULES


# ══════════════════════════════════════════════════════════════════════════════
# AC096-120: Rutas, operaciones, instrucciones, proveedores, make-or-buy
# ══════════════════════════════════════════════════════════════════════════════

class TestRoutingService:

    def test_ac096_steel_routing_has_reception_first(self):
        """AC096: Ruta acero comienza con RECEPTION."""
        seq = RoutingService.default_operation_sequence("S355")
        assert seq[0] == "RECEPTION"

    def test_ac097_aluminum_routing_different_from_steel(self):
        """AC097: Ruta aluminio difiere de ruta acero."""
        steel = RoutingService.default_operation_sequence("S355")
        alum  = RoutingService.default_operation_sequence("6082")
        assert steel != alum

    def test_ac098_steel_routing_includes_galvanizing(self):
        """AC098: Ruta acero incluye GALVANIZING."""
        seq = RoutingService.default_operation_sequence("S235")
        assert "GALVANIZING" in seq

    def test_ac099_aluminum_routing_no_galvanizing(self):
        """AC099: Ruta aluminio no incluye GALVANIZING."""
        seq = RoutingService.default_operation_sequence("ALUMINUM")
        assert "GALVANIZING" not in seq

    def test_ac100_steel_routing_release_last(self):
        """AC100: Ruta acero termina con RELEASE."""
        seq = RoutingService.default_operation_sequence("S355")
        assert seq[-1] == "RELEASE"

    def test_ac101_aluminum_routing_release_last(self):
        """AC101: Ruta aluminio termina con RELEASE."""
        seq = RoutingService.default_operation_sequence("6082")
        assert seq[-1] == "RELEASE"

    def test_ac102_make_buy_cheaper_to_make(self):
        """AC102: Fabricar más barato → recomendación MAKE."""
        result = RoutingService.make_buy_decision(100, 200, 5, 10)
        assert result.recommendation == "MAKE"

    def test_ac103_make_buy_cheaper_to_buy(self):
        """AC103: Comprar mucho más barato → recomendación BUY."""
        result = RoutingService.make_buy_decision(200, 50, 5, 10)
        assert result.recommendation == "BUY"

    def test_ac104_make_buy_strategic_always_make(self):
        """AC104: Pieza estratégica → MAKE aunque comprar sea más barato."""
        result = RoutingService.make_buy_decision(500, 100, 5, 3, strategic_part=True)
        assert result.recommendation == "MAKE"

    def test_ac105_make_buy_reason_nonempty(self):
        """AC105: Resultado make-or-buy incluye razón no vacía."""
        result = RoutingService.make_buy_decision(100, 120, 5, 7)
        assert len(result.reason) > 0

    def test_ac106_supplier_capability_match(self):
        """AC106: Proveedor con capacidades requeridas → compatible."""
        supplier = {"capabilities": ["WELDING_LONGITUDINAL", "CUTTING", "INSPECTION"]}
        ok, missing = RoutingService.validate_supplier_capability(
            supplier, ["WELDING_LONGITUDINAL", "CUTTING"]
        )
        assert ok
        assert len(missing) == 0

    def test_ac107_supplier_capability_missing(self):
        """AC107: Proveedor sin capacidad → incompatible, lista de faltantes."""
        supplier = {"capabilities": ["CUTTING"]}
        ok, missing = RoutingService.validate_supplier_capability(
            supplier, ["CUTTING", "GALVANIZING"]
        )
        assert not ok
        assert "GALVANIZING" in missing

    def test_ac108_routing_hash_deterministic(self):
        """AC108: Misma ruta → mismo hash."""
        ops = [{"sequence_no": 1, "operation_type": "CUTTING", "run_time_h": 2.0}]
        h1 = RoutingService.compute_routing_hash("P-001", ops)
        h2 = RoutingService.compute_routing_hash("P-001", ops)
        assert h1 == h2

    def test_ac109_routing_hash_different_parts(self):
        """AC109: Distinto part_code → hash distinto."""
        ops = [{"sequence_no": 1, "operation_type": "CUTTING"}]
        h1 = RoutingService.compute_routing_hash("P-001", ops)
        h2 = RoutingService.compute_routing_hash("P-002", ops)
        assert h1 != h2

    def test_ac110_total_time_sum(self):
        """AC110: Tiempo total = Σ(setup + run) por operación."""
        ops = [
            {"setup_time_h": 1.0, "run_time_h": 2.0},
            {"setup_time_h": 0.5, "run_time_h": 3.5},
        ]
        total = RoutingService.compute_total_time(ops)
        assert total == pytest.approx(7.0)

    def test_ac111_total_time_no_operations(self):
        """AC111: Sin operaciones → tiempo total = 0."""
        assert RoutingService.compute_total_time([]) == pytest.approx(0.0)

    def test_ac112_operation_sequence_steel_has_bending(self):
        """AC112: Ruta acero incluye BENDING."""
        seq = RoutingService.default_operation_sequence("S355")
        assert "BENDING" in seq

    def test_ac113_operation_sequence_aluminum_has_machining(self):
        """AC113: Ruta aluminio incluye MACHINING."""
        seq = RoutingService.default_operation_sequence("ALUMINUM")
        assert "MACHINING" in seq

    def test_ac114_routing_hash_sha256_length(self):
        """AC114: Hash ruta es SHA-256 (64 chars)."""
        h = RoutingService.compute_routing_hash("P-001", [])
        assert len(h) == 64

    def test_ac115_make_buy_near_parity_prefer_make(self):
        """AC115: Diferencia <15% con plazo make menor → MAKE."""
        result = RoutingService.make_buy_decision(100, 110, 5, 10)
        assert result.recommendation == "MAKE"


# ══════════════════════════════════════════════════════════════════════════════
# AC116-140: Validación automática, coherencia, hashes
# ══════════════════════════════════════════════════════════════════════════════

class TestValidationService:

    def test_ac116_hash_integrity_match(self):
        """AC116: Hashes iguales → sin check de error."""
        c = ValidationService.check_hash_integrity("abc123", "abc123")
        assert c is None

    def test_ac117_hash_integrity_mismatch_blocking(self):
        """AC117: Hashes distintos → check BLOCKING."""
        c = ValidationService.check_hash_integrity("abc", "def")
        assert c is not None
        assert c.severity == "BLOCKING"

    def test_ac118_mass_reconciliation_ok_no_check(self):
        """AC118: Reconciliación dentro del umbral → sin check."""
        recon = MassReconciliation(30.0, 30.1, 0.1, 0.1/30.0, True)
        c = ValidationService.check_mass_reconciliation(recon)
        assert c is None

    def test_ac119_mass_reconciliation_exceeded_blocking(self):
        """AC119: Reconciliación fuera de umbral → check BLOCKING."""
        recon = MassReconciliation(30.0, 32.0, 2.0, 2.0/30.0, False)
        c = ValidationService.check_mass_reconciliation(recon)
        assert c is not None
        assert c.severity == "BLOCKING"

    def test_ac120_bolt_count_match_no_check(self):
        """AC120: Pernos coinciden → sin check."""
        c = ValidationService.check_bolt_count(4, 4)
        assert c is None

    def test_ac121_bolt_count_mismatch_error(self):
        """AC121: Pernos no coinciden → ERROR."""
        c = ValidationService.check_bolt_count(4, 6)
        assert c is not None
        assert c.severity == "ERROR"

    def test_ac122_weld_symbols_present_ok(self):
        """AC122: Soldaduras con símbolos → sin check."""
        c = ValidationService.check_weld_symbols(True, True)
        assert c is None

    def test_ac123_weld_symbols_missing_error(self):
        """AC123: Soldaduras sin símbolos → ERROR."""
        c = ValidationService.check_weld_symbols(False, True)
        assert c is not None
        assert c.severity == "ERROR"

    def test_ac124_no_welds_no_symbols_ok(self):
        """AC124: Sin soldaduras y sin símbolos → sin check."""
        c = ValidationService.check_weld_symbols(False, False)
        assert c is None

    def test_ac125_structural_hash_match_ok(self):
        """AC125: Hashes solver == snapshot → sin checks."""
        checks = ValidationService.check_structural_hash_match(
            {"ph4": "abc"}, {"ph4": "abc"}
        )
        assert len(checks) == 0

    def test_ac126_structural_hash_mismatch_blocking(self):
        """AC126: Hash solver distinto → BLOCKING."""
        checks = ValidationService.check_structural_hash_match(
            {"ph4": "abc"}, {"ph4": "xyz"}
        )
        assert any(c.severity == "BLOCKING" for c in checks)

    def test_ac127_structural_hash_missing_warning(self):
        """AC127: Hash en snapshot pero no en solver → WARNING."""
        checks = ValidationService.check_structural_hash_match(
            {"ph4": "abc"}, {}
        )
        assert any(c.severity == "WARNING" for c in checks)

    def test_ac128_dxf_layers_missing_error(self):
        """AC128: Capas obligatorias ausentes → ERROR."""
        c = ValidationService.check_dxf_reconstruction(["BEND_UP"], True)
        assert c is not None
        assert c.severity == "ERROR"

    def test_ac129_dxf_cannot_reconstruct_blocking(self):
        """AC129: No se puede reconstruir DXF → BLOCKING."""
        c = ValidationService.check_dxf_reconstruction(DXF_LAYERS, False)
        assert c is not None
        assert c.severity == "BLOCKING"

    def test_ac130_full_validation_clean_snapshot(self):
        """AC130: Snapshot limpio → ValidationReport sin bloqueantes."""
        snap = make_snapshot()
        recon = MassReconciliation(100.0, 100.3, 0.3, 0.003, True)
        report = ValidationService.run_full_validation(
            snap,
            mass_reconciliation=recon,
            solver_hashes=snap.structural_hashes,
            dxf_layers=DXF_LAYERS,
            can_reconstruct_dxf=True,
            bolt_count_drawing=4,
            bolt_count_bom=4,
            has_welded_joints=True,
            weld_symbols_present=True,
        )
        assert report.is_fit_for_release

    def test_ac131_full_validation_hash_mismatch_blocks(self):
        """AC131: Hash mismatch en full_validation → no apto para liberar."""
        snap = make_snapshot()
        # Solver tiene hash diferente
        report = ValidationService.run_full_validation(
            snap,
            solver_hashes={"phase4_solver": "WRONG_HASH_000"},
        )
        assert not report.is_fit_for_release

    def test_ac132_validation_report_categorization(self):
        """AC132: ValidationReport categoriza bloqueantes, errores, warnings."""
        snap = make_snapshot()
        recon_bad = MassReconciliation(100.0, 105.0, 5.0, 0.05, False)
        report = ValidationService.run_full_validation(
            snap,
            mass_reconciliation=recon_bad,
        )
        assert len(report.blockers) > 0
        assert len(report.errors) >= len(report.blockers)  # blockers ⊆ errors

    def test_ac133_missing_dxf_layers_list(self):
        """AC133: check_missing_dxf_layers retorna sólo las faltantes."""
        missing = ValidationService.check_missing_dxf_layers(["CENTER"])
        assert "CUT_OUTER" in missing
        assert "CENTER" not in missing

    def test_ac134_valid_snapshot_hash_regeneratable(self):
        """AC134: Snapshot hash puede regenerarse para verificación."""
        snap = make_snapshot()
        regenerated = ProductDefinitionService.compute_snapshot_hash(
            snap.product_code,
            snap.revision,
            snap.geometry_params,
            snap.structural_hashes,
            snap.library_versions,
        )
        assert regenerated == snap.snapshot_hash

    def test_ac135_validation_check_context_populated(self):
        """AC135: ValidationCheck incluye contexto con datos relevantes."""
        c = ValidationService.check_bolt_count(4, 6)
        assert "drawing" in c.context or "bom" in c.context


# ══════════════════════════════════════════════════════════════════════════════
# AC136-155: Liberación, puertas, ERP, cambios
# ══════════════════════════════════════════════════════════════════════════════

class TestReleaseAndChange:

    def _all_artifacts_ready(self):
        return {
            "CAD_STEP": True, "CAD_DXF": True, "DRAWING_PDF": True,
            "BOM_EBOM": True, "ROUTING": True,
            "INSPECTION_PLAN": True, "DOC_PACKAGE": True,
        }

    def test_ac136_gate_cad_valid_passes(self):
        """AC136: CAD_VALID pasa con STEP + DXF presentes y válidos."""
        g = ReleaseService.evaluate_gate("CAD_VALID", artifacts_ready=self._all_artifacts_ready())
        assert g.status == "PASSED"

    def test_ac137_gate_cad_valid_fails_missing_step(self):
        """AC137: CAD_VALID falla sin STEP."""
        arts = self._all_artifacts_ready()
        arts["CAD_STEP"] = False
        g = ReleaseService.evaluate_gate("CAD_VALID", artifacts_ready=arts)
        assert g.status == "FAILED"

    def test_ac138_gate_waived_always_passes(self):
        """AC138: Puerta dispensada (WAIVED) → status=WAIVED."""
        g = ReleaseService.evaluate_gate("CAD_VALID", waived=True)
        assert g.status == "WAIVED"

    def test_ac139_all_gates_evaluated(self):
        """AC139: evaluate_all_gates evalúa las 6 puertas."""
        results = ReleaseService.evaluate_all_gates(None, self._all_artifacts_ready())
        assert len(results) == len(RELEASE_GATES)

    def test_ac140_all_gates_pass_fit_for_release(self):
        """AC140: Todas las puertas PASSED → is_fit_for_release=True."""
        results = ReleaseService.evaluate_all_gates(None, self._all_artifacts_ready())
        ok, failed = ReleaseService.is_fit_for_release(results)
        assert ok

    def test_ac141_failed_gate_blocks_release(self):
        """AC141: Una puerta FAILED → no apto para liberar."""
        arts = self._all_artifacts_ready()
        arts["BOM_EBOM"] = False
        results = ReleaseService.evaluate_all_gates(None, arts)
        ok, failed = ReleaseService.is_fit_for_release(results)
        assert not ok
        assert "BOM_RECONCILED" in failed

    def test_ac142_release_hash_deterministic(self):
        """AC142: Mismo release_code + gates → mismo hash."""
        sid = uuid4()
        gates = [ReleaseGateResult("CAD_VALID", "PASSED", "")]
        h1 = ReleaseService.compute_release_hash(sid, "REL-001", gates)
        h2 = ReleaseService.compute_release_hash(sid, "REL-001", gates)
        assert h1 == h2

    def test_ac143_release_hash_different_code(self):
        """AC143: Distinto release_code → hash distinto."""
        sid = uuid4()
        gates = [ReleaseGateResult("CAD_VALID", "PASSED", "")]
        h1 = ReleaseService.compute_release_hash(sid, "REL-001", gates)
        h2 = ReleaseService.compute_release_hash(sid, "REL-002", gates)
        assert h1 != h2

    def test_ac144_change_editorial_no_recalc(self):
        """AC144: Cambio EDITORIAL no requiere recálculo."""
        assert not CHANGE_CLASS_REQUIRES_RECALC["EDITORIAL"]

    def test_ac145_change_structural_requires_recalc(self):
        """AC145: Cambio STRUCTURAL requiere recálculo."""
        assert CHANGE_CLASS_REQUIRES_RECALC["STRUCTURAL"]

    def test_ac146_change_geometric_requires_recalc(self):
        """AC146: Cambio GEOMETRIC requiere recálculo."""
        assert CHANGE_CLASS_REQUIRES_RECALC["GEOMETRIC"]

    def test_ac147_change_regulatory_requires_recalc(self):
        """AC147: Cambio REGULATORY requiere recálculo."""
        assert CHANGE_CLASS_REQUIRES_RECALC["REGULATORY"]

    def test_ac148_erp_payload_contains_product_code(self):
        """AC148: ERP payload contiene product_code."""
        snap = make_snapshot()
        bom = BomBuildResult(uuid4(), snap.snapshot_id, "EBOM", "hash", 30.0, 150.0, 3, True, 0.1)
        payload = IntegrationService.build_erp_payload(snap, bom, "routing_hash_abc", "REL-001")
        assert payload["product_code"] == snap.product_code

    def test_ac149_erp_payload_validation_missing_keys(self):
        """AC149: ERP payload sin campos requeridos → lista de faltantes."""
        errors = IntegrationService.validate_erp_payload({"product_code": "P-001"})
        assert len(errors) > 0

    def test_ac150_erp_payload_valid_no_errors(self):
        """AC150: ERP payload completo → sin errores de validación."""
        payload = {
            "product_code": "P-001",
            "revision": "A",
            "release_code": "REL-001",
            "snapshot_hash": "abc" * 21 + "a",
            "bom_hash": "def" * 21 + "d",
        }
        errors = IntegrationService.validate_erp_payload(payload)
        assert len(errors) == 0

    def test_ac151_pdm_metadata_has_cad_level(self):
        """AC151: Metadata PDM incluye cad_level."""
        snap = make_snapshot()
        meta = IntegrationService.build_pdm_metadata(snap)
        assert "cad_level" in meta

    def test_ac152_pdm_metadata_has_snapshot_hash(self):
        """AC152: Metadata PDM incluye snapshot_hash."""
        snap = make_snapshot()
        meta = IntegrationService.build_pdm_metadata(snap)
        assert "snapshot_hash" in meta

    def test_ac153_six_release_gates(self):
        """AC153: Hay exactamente 6 puertas de liberación."""
        assert len(RELEASE_GATES) == 6

    def test_ac154_release_gates_names(self):
        """AC154: Puertas incluyen CAD_VALID y BOM_RECONCILED."""
        assert "CAD_VALID" in RELEASE_GATES
        assert "BOM_RECONCILED" in RELEASE_GATES

    def test_ac155_gate_bom_reconciled_fails_without_bom(self):
        """AC155: BOM_RECONCILED falla si BOM_EBOM no está listo."""
        arts = self._all_artifacts_ready()
        arts["BOM_EBOM"] = False
        g = ReleaseService.evaluate_gate("BOM_RECONCILED", artifacts_ready=arts)
        assert g.status == "FAILED"


# ══════════════════════════════════════════════════════════════════════════════
# AC156-175: Calidad, as-built, no conformidades, recalificación
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityService:

    def test_ac156_conformant_measurement(self):
        """AC156: Medida dentro de tolerancia → conforme."""
        ok, dev = QualityService.is_conformant(100.2, 100.0, 0.5, 0.5)
        assert ok
        assert abs(dev - 0.2) < 1e-9

    def test_ac157_nonconformant_over_usl(self):
        """AC157: Medida sobre USL → no conforme."""
        ok, dev = QualityService.is_conformant(101.0, 100.0, 0.5, 0.5)
        assert not ok

    def test_ac158_nonconformant_below_lsl(self):
        """AC158: Medida bajo LSL → no conforme."""
        ok, dev = QualityService.is_conformant(99.0, 100.0, 0.5, 0.5)
        assert not ok

    def test_ac159_deviation_positive_above_nominal(self):
        """AC159: Medida sobre nominal → desviación positiva."""
        _, dev = QualityService.is_conformant(100.3, 100.0, 0.5, 0.5)
        assert dev > 0

    def test_ac160_deviation_negative_below_nominal(self):
        """AC160: Medida bajo nominal → desviación negativa."""
        _, dev = QualityService.is_conformant(99.7, 100.0, 0.5, 0.5)
        assert dev < 0

    def test_ac161_cpk_requires_min_5_measurements(self):
        """AC161: < 5 mediciones → cpk = None."""
        cpk = QualityService.compute_cpk([100, 100.1, 99.9, 100.2], 100.0, 0.5, 0.5)
        assert cpk is None

    def test_ac162_cpk_perfect_process(self):
        """AC162: Proceso perfectamente centrado → Cpk > 1.33."""
        meas = [100.0 + i * 0.0001 for i in range(20)]
        cpk = QualityService.compute_cpk(meas, 100.0, 0.5, 0.5)
        assert cpk is not None
        assert cpk > 1.33

    def test_ac163_cpk_off_center_lower(self):
        """AC163: Cpk < 1.0 para proceso fuera de control."""
        meas = [103.0] * 20  # fuera del rango ±0.5
        cpk = QualityService.compute_cpk(meas, 100.0, 0.5, 0.5)
        assert cpk is not None
        assert cpk < 0

    def test_ac164_requalification_blocking_severity(self):
        """AC164: NC BLOCKING requiere recalificación."""
        assert QualityService.requires_requalification("BLOCKING", False)

    def test_ac165_requalification_error_structural(self):
        """AC165: NC ERROR + pieza estructural requiere recalificación."""
        assert QualityService.requires_requalification("ERROR", True)

    def test_ac166_no_requalification_warning(self):
        """AC166: NC WARNING → no requiere recalificación."""
        assert not QualityService.requires_requalification("WARNING", True)

    def test_ac167_nc_disposition_blocking_can_repair(self):
        """AC167: NC BLOCKING con reparación → REPAIR_AND_REINSPECT."""
        disp = QualityService.nc_disposition("BLOCKING", 10.0, True)
        assert disp == "REPAIR_AND_REINSPECT"

    def test_ac168_nc_disposition_blocking_no_repair(self):
        """AC168: NC BLOCKING sin reparación → SCRAP."""
        disp = QualityService.nc_disposition("BLOCKING", 10.0, False)
        assert disp == "SCRAP"

    def test_ac169_nc_disposition_info_accept(self):
        """AC169: NC INFO → ACCEPT."""
        disp = QualityService.nc_disposition("INFO", 0.1, True)
        assert disp == "ACCEPT"

    def test_ac170_inspection_characteristics_generated(self):
        """AC170: Genera características de inspección para acero soldado."""
        chars = QualityService.generate_inspection_characteristics(
            material="S355",
            has_welds=True,
            has_coating=True,
            structural=True,
        )
        assert len(chars) > 0

    def test_ac171_weld_characteristics_when_has_welds(self):
        """AC171: Con has_welds=True → incluye WLD-001."""
        chars = QualityService.generate_inspection_characteristics("S355", True, False, False)
        codes = [c["code"] for c in chars]
        assert any(c.startswith("WLD") for c in codes)

    def test_ac172_no_weld_characteristics_when_no_welds(self):
        """AC172: Con has_welds=False → sin características WLD."""
        chars = QualityService.generate_inspection_characteristics("S355", False, False, False)
        codes = [c["code"] for c in chars]
        assert not any(c.startswith("WLD") for c in codes)

    def test_ac173_coating_characteristics_when_has_coating(self):
        """AC173: Con has_coating=True → incluye CTG-001."""
        chars = QualityService.generate_inspection_characteristics("S355", False, True, False)
        codes = [c["code"] for c in chars]
        assert any(c.startswith("CTG") for c in codes)

    def test_ac174_structural_characteristics_when_structural(self):
        """AC174: Pieza estructural → incluye STR-001."""
        chars = QualityService.generate_inspection_characteristics("S355", False, False, True)
        codes = [c["code"] for c in chars]
        assert any(c.startswith("STR") for c in codes)

    def test_ac175_dimensional_characteristics_always_present(self):
        """AC175: DIM-001 (altura) siempre presente."""
        chars = QualityService.generate_inspection_characteristics("S355", False, False, False)
        codes = [c["code"] for c in chars]
        assert "DIM-001" in codes


# ══════════════════════════════════════════════════════════════════════════════
# AC176-200: Documentos, artefacto-manifiesto, idempotencia, seguridad
# ══════════════════════════════════════════════════════════════════════════════

class TestDocumentAndManifest:

    def test_ac176_document_types_for_client(self):
        """AC176: Audiencia CLIENT incluye DRAWING_PDF."""
        types = DocumentService.document_types_for_audience("CLIENT")
        assert "DRAWING_PDF" in types

    def test_ac177_document_types_for_production(self):
        """AC177: Audiencia PRODUCTION incluye ROUTING."""
        types = DocumentService.document_types_for_audience("PRODUCTION")
        assert "ROUTING" in types

    def test_ac178_document_types_for_quality(self):
        """AC178: Audiencia QUALITY incluye INSPECTION_PLAN."""
        types = DocumentService.document_types_for_audience("QUALITY")
        assert "INSPECTION_PLAN" in types

    def test_ac179_document_types_unknown_audience(self):
        """AC179: Audiencia desconocida → lista vacía."""
        types = DocumentService.document_types_for_audience("UNKNOWN")
        assert types == []

    def test_ac180_package_hash_deterministic(self):
        """AC180: Mismo paquete → mismo hash."""
        sid = uuid4()
        h1 = DocumentService.compute_package_hash(sid, "CLIENT", "es", ["DRAWING_PDF"])
        h2 = DocumentService.compute_package_hash(sid, "CLIENT", "es", ["DRAWING_PDF"])
        assert h1 == h2

    def test_ac181_package_hash_different_language(self):
        """AC181: Distinto idioma → hash distinto."""
        sid = uuid4()
        h1 = DocumentService.compute_package_hash(sid, "CLIENT", "es", ["DRAWING_PDF"])
        h2 = DocumentService.compute_package_hash(sid, "CLIENT", "en", ["DRAWING_PDF"])
        assert h1 != h2

    def test_ac182_language_unsupported_warning(self):
        """AC182: Idioma no soportado para audiencia → WARNING."""
        c = DocumentService.validate_language_support("zh", "CLIENT")
        assert c is not None
        assert c.severity == "WARNING"

    def test_ac183_language_supported_ok(self):
        """AC183: Idioma soportado → sin check."""
        c = DocumentService.validate_language_support("es", "CLIENT")
        assert c is None

    def test_ac184_artifact_store_store_and_retrieve(self):
        """AC184: ArtifactStore guarda y recupera contenido."""
        store = ArtifactStore()
        content = b"fake CAD content"
        store.store("art-001", content, {"snapshot_id": "s-001", "type": "CAD_STEP"})
        retrieved = store.retrieve("art-001")
        assert retrieved == content

    def test_ac185_artifact_store_verify_integrity(self):
        """AC185: verify() retorna True para artefacto íntegro."""
        store = ArtifactStore()
        store.store("art-001", b"content", {})
        assert store.verify("art-001")

    def test_ac186_artifact_store_verify_missing(self):
        """AC186: verify() retorna False para artefacto inexistente."""
        store = ArtifactStore()
        assert not store.verify("nonexistent")

    def test_ac187_artifact_store_list_by_snapshot(self):
        """AC187: list_artifacts filtra por snapshot_id."""
        store = ArtifactStore()
        store.store("a1", b"x", {"snapshot_id": "S-001"})
        store.store("a2", b"y", {"snapshot_id": "S-001"})
        store.store("a3", b"z", {"snapshot_id": "S-002"})
        arts = store.list_artifacts("S-001")
        assert set(arts) == {"a1", "a2"}

    def test_ac188_idempotency_key_deterministic(self):
        """AC188: Misma clave de idempotencia para mismos argumentos."""
        sid = uuid4()
        k1 = ArtifactStore.idempotency_key(sid, "CAD_STEP", "G3_MANUFACTURING")
        k2 = ArtifactStore.idempotency_key(sid, "CAD_STEP", "G3_MANUFACTURING")
        assert k1 == k2

    def test_ac189_idempotency_key_different_type(self):
        """AC189: Distinto artifact_type → clave distinta."""
        sid = uuid4()
        k1 = ArtifactStore.idempotency_key(sid, "CAD_STEP", "G3_MANUFACTURING")
        k2 = ArtifactStore.idempotency_key(sid, "CAD_DXF", "G3_MANUFACTURING")
        assert k1 != k2

    def test_ac190_manifest_hash_deterministic(self):
        """AC190: Mismo conjunto de artefactos → mismo hash de manifiesto."""
        entries = [
            ArtifactEntry(uuid4(), "CAD_STEP", "chk001", "STEP", "14.0", datetime.now(timezone.utc)),
        ]
        h1 = ArtifactManifestService.compute_manifest_hash(entries)
        h2 = ArtifactManifestService.compute_manifest_hash(entries)
        assert h1 == h2

    def test_ac191_manifest_completeness_g3(self):
        """AC191: G3 completo requiere CAD_STEP, CAD_DXF, DRAWING_PDF, BOM_EBOM."""
        required = ArtifactManifestService.REQUIRED_ARTIFACT_TYPES["G3_MANUFACTURING"]
        assert "CAD_STEP" in required
        assert "CAD_DXF" in required
        assert "DRAWING_PDF" in required
        assert "BOM_EBOM" in required

    def test_ac192_manifest_incomplete_missing(self):
        """AC192: Manifiesto sin artefactos requeridos → is_complete=False."""
        entries = [
            ArtifactEntry(uuid4(), "CAD_STEP", "chk001", "STEP", "14.0", datetime.now(timezone.utc)),
        ]
        ok, missing = ArtifactManifestService.check_completeness(entries, "G3_MANUFACTURING")
        assert not ok
        assert len(missing) > 0

    def test_ac193_manifest_complete_g3(self):
        """AC193: Todos los artefactos G3 presentes → is_complete=True."""
        required = ArtifactManifestService.REQUIRED_ARTIFACT_TYPES["G3_MANUFACTURING"]
        entries = [
            ArtifactEntry(uuid4(), t, f"chk{i}", "FMT", "14.0", datetime.now(timezone.utc))
            for i, t in enumerate(required)
        ]
        ok, missing = ArtifactManifestService.check_completeness(entries, "G3_MANUFACTURING")
        assert ok
        assert len(missing) == 0

    def test_ac194_manifest_build_returns_result(self):
        """AC194: build_manifest devuelve ManifestResult."""
        snap_id = uuid4()
        entries = [
            ArtifactEntry(uuid4(), "CAD_STEP", "chk001", "STEP", "14.0", datetime.now(timezone.utc)),
        ]
        result = ArtifactManifestService.build_manifest(snap_id, entries, "G2_ENGINEERING")
        assert isinstance(result, ManifestResult)
        assert result.snapshot_id == snap_id

    def test_ac195_manifest_idempotency_same_entries(self):
        """AC195: Dos manifiestos del mismo snapshot son idempotentes."""
        snap_id = uuid4()
        entry_id = uuid4()
        entries = [
            ArtifactEntry(entry_id, "CAD_STEP", "chk001", "STEP", "14.0", datetime.now(timezone.utc)),
        ]
        m1 = ArtifactManifestService.build_manifest(snap_id, entries, "G2_ENGINEERING")
        m2 = ArtifactManifestService.build_manifest(snap_id, entries, "G2_ENGINEERING")
        assert ArtifactManifestService.verify_idempotency(m1, m2)

    def test_ac196_manifest_idempotency_different_entries(self):
        """AC196: Manifiestos con distintos artefactos no son idempotentes."""
        snap_id = uuid4()
        e1 = ArtifactEntry(uuid4(), "CAD_STEP", "aaa", "STEP", "14.0", datetime.now(timezone.utc))
        e2 = ArtifactEntry(uuid4(), "CAD_DXF", "bbb", "DXF", "14.0", datetime.now(timezone.utc))
        m1 = ArtifactManifestService.build_manifest(snap_id, [e1], "G2_ENGINEERING")
        m2 = ArtifactManifestService.build_manifest(snap_id, [e2], "G2_ENGINEERING")
        assert not ArtifactManifestService.verify_idempotency(m1, m2)

    def test_ac197_service_file_syntax_valid(self):
        """AC197: Archivo cad_bom_service.py tiene sintaxis Python válida."""
        src = SERVICE_PATH.read_text()
        tree = ast.parse(src)
        assert tree is not None

    def test_ac198_all_dxf_layers_have_specs(self):
        """AC198: Todos los DXF_LAYERS tienen spec definida."""
        for layer in DXF_LAYERS:
            spec = CadGenerationService.get_dxf_layer_spec(layer)
            assert spec is not None, f"Sin spec para capa {layer}"

    def test_ac199_snapshot_transitions_complete(self):
        """AC199: Todos los estados tienen entrada en SNAPSHOT_TRANSITIONS."""
        states = {"DRAFT","REVIEW","APPROVED","RELEASED","OBSOLETE"}
        for s in states:
            assert s in SNAPSHOT_TRANSITIONS

    def test_ac200_manifest_artifact_count(self):
        """AC200: artifact_count en ManifestResult == len(entries)."""
        snap_id = uuid4()
        entries = [
            ArtifactEntry(uuid4(), "CAD_STEP", f"chk{i}", "STEP", "14.0", datetime.now(timezone.utc))
            for i in range(4)
        ]
        result = ArtifactManifestService.build_manifest(snap_id, entries, "G2_ENGINEERING")
        assert result.artifact_count == 4
