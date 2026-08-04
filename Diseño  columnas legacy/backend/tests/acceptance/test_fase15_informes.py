"""
Salvi Studio · Columns — Suite de aceptación Fase 15
Informes, Validación Documental y Liberación
150 casos de aceptación (AC15-001 … AC15-150)

Técnica: mock injection + importlib para cargar reports_service.py
sin dependencias de DB, FastAPI ni asyncpg.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List
from unittest.mock import MagicMock

# ── Mock injection ────────────────────────────────────────────────────────────
for _mod in [
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql", "alembic", "alembic.op",
    "asyncpg", "fastapi", "fastapi.routing",
    "app.models.db.reports", "app.models.schemas.reports",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# ── Cargar servicio ───────────────────────────────────────────────────────────
SERVICE_PATH = Path(
    "/sessions/determined-friendly-mayer/mnt/columnas"
    "/backend/app/services/reports_service.py"
)
if not SERVICE_PATH.exists():
    SERVICE_PATH = (
        Path(__file__).parents[3]
        / "app" / "services" / "reports_service.py"
    )

# Strip null bytes si los hay (OneDrive FUSE padding)
_raw = SERVICE_PATH.read_bytes().rstrip(b"\x00")
_tmp = Path("/tmp/reports_service_f15_test.py")
_tmp.write_bytes(_raw)

_svc_spec = importlib.util.spec_from_file_location("reports_service_f15", str(_tmp))
svc: ModuleType = importlib.util.module_from_spec(_svc_spec)
sys.modules["reports_service_f15"] = svc  # required for dataclass __module__ resolution
_svc_spec.loader.exec_module(svc)

# Exponer clases de servicio
StateMachine = svc.StateMachine
ValidationService = svc.ValidationService
DocumentComposer = svc.DocumentComposer
ManifestBuilder = svc.ManifestBuilder
SemanticDiff = svc.SemanticDiff
ReleaseOrchestrator = svc.ReleaseOrchestrator
ReviewWorkflow = svc.ReviewWorkflow
DistributionService = svc.DistributionService
SecurityService = svc.SecurityService
SignatureService = svc.SignatureService
AiTextService = svc.AiTextService
LineageTracker = svc.LineageTracker
ArchiveService = svc.ArchiveService

# Tipos de datos definidos en el servicio (dataclasses)
ValidationCheck = svc.ValidationCheck
ValidationReport = svc.ValidationReport
ChangeItem = svc.ChangeItem
DiffResult = svc.DiffResult
LineageField = svc.LineageField
RevokeResult = svc.RevokeResult

MATURITY_ORDER = svc.MATURITY_ORDER
VALIDATION_CODES = svc.VALIDATION_CODES
PACKAGE_REQUIRED_FIELDS = svc.PACKAGE_REQUIRED_FIELDS
INTERNAL_FIELDS_TO_REDACT = svc.INTERNAL_FIELDS_TO_REDACT
TECHNICAL_CHANGE_KINDS = svc.TECHNICAL_CHANGE_KINDS
EDITORIAL_CHANGE_KINDS = svc.EDITORIAL_CHANGE_KINDS
AUTH_LEVEL_REQUIREMENTS = svc.AUTH_LEVEL_REQUIREMENTS
UTILIZATION_ALERT_BAND = svc.UTILIZATION_ALERT_BAND

# ── Test runner sin pytest ────────────────────────────────────────────────────

class _ApproxScalar:
    def __init__(self, value, rel=None, abs=None):
        self.value = value
        self.rel = rel or 1e-6
        self.abs = abs
    def __eq__(self, other):
        if self.abs is not None:
            return builtins_abs(other - self.value) <= self.abs
        tol = self.rel * builtins_abs(self.value)
        return builtins_abs(other - self.value) <= tol
    def __repr__(self):
        return f"approx({self.value})"

import builtins
builtins_abs = builtins.abs

def approx(value, rel=None, abs=None):
    return _ApproxScalar(value, rel=rel, abs=abs)


class _Raises:
    def __init__(self, exc_type):
        self.exc_type = exc_type
        self.value = None
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, tb):
        if exc_type is None:
            raise AssertionError(f"Se esperaba {self.exc_type.__name__} pero no se lanzó ninguna excepción")
        if not issubclass(exc_type, self.exc_type):
            raise AssertionError(f"Se esperaba {self.exc_type.__name__} pero se obtuvo {exc_type.__name__}")
        self.value = exc_val
        return True  # suprimir excepción


def raises(exc_type):
    return _Raises(exc_type)


_PASS = []
_FAIL = []


def _run_all():
    import inspect
    test_classes = [
        TestGroupA_ReleaseSnapshot,
        TestGroupB_Documents,
        TestGroupC_Validation,
        TestGroupD_ProductionPackages,
        TestGroupE_WorkflowApproval,
        TestGroupF_SignatureDistribution,
        TestGroupG_AiMultilingual,
        TestGroupH_SecurityArchive,
    ]
    for cls in test_classes:
        obj = cls()
        methods = sorted(
            [m for m in dir(obj) if m.startswith("test_ac")],
            key=lambda m: int(m.split("_ac")[1].split("_")[0]) if m.split("_ac")[1].split("_")[0].isdigit() else 0
        )
        for method_name in methods:
            method = getattr(obj, method_name)
            try:
                method()
                _PASS.append(method_name)
            except Exception as exc:
                _FAIL.append((method_name, str(exc)))

    total = len(_PASS) + len(_FAIL)
    print(f"\n=== Fase 15 · {len(_PASS)}/{total} ACs superados ===")
    if _FAIL:
        print("\nFallos:")
        for name, err in _FAIL:
            print(f"  FAIL {name}: {err}")
    return len(_FAIL) == 0


# ── Grupo A: ReleaseSnapshot y máquina de estados (AC001-AC030) ───────────────

class TestGroupA_ReleaseSnapshot:

    def test_ac001_maturity_order_five_states(self):
        assert len(MATURITY_ORDER) == 5

    def test_ac002_maturity_order_correct(self):
        assert MATURITY_ORDER == ["DRAFT", "PREDIM", "CALC_INTERNO", "VALIDADO_OT", "LIBERADO"]

    def test_ac003_state_machine_draft_to_predim(self):
        assert StateMachine.can_transition("DRAFT", "PREDIM") is True

    def test_ac004_state_machine_predim_to_calc(self):
        assert StateMachine.can_transition("PREDIM", "CALC_INTERNO") is True

    def test_ac005_state_machine_calc_to_validado(self):
        assert StateMachine.can_transition("CALC_INTERNO", "VALIDADO_OT") is True

    def test_ac006_state_machine_validado_to_liberado(self):
        assert StateMachine.can_transition("VALIDADO_OT", "LIBERADO") is True

    def test_ac007_state_machine_liberado_terminal(self):
        assert StateMachine.is_terminal("LIBERADO") is True

    def test_ac008_state_machine_draft_not_terminal(self):
        assert StateMachine.is_terminal("DRAFT") is False

    def test_ac009_invalid_skip_transition(self):
        assert StateMachine.can_transition("DRAFT", "CALC_INTERNO") is False

    def test_ac010_invalid_reverse_transition(self):
        assert StateMachine.can_transition("LIBERADO", "DRAFT") is False

    def test_ac011_invalid_same_state(self):
        assert StateMachine.can_transition("DRAFT", "DRAFT") is False

    def test_ac012_invalid_skip_to_liberado(self):
        assert StateMachine.can_transition("DRAFT", "LIBERADO") is False

    def test_ac013_revocable_states(self):
        assert StateMachine.is_revocable("VALIDADO_OT") is True
        assert StateMachine.is_revocable("LIBERADO") is True

    def test_ac014_draft_not_revocable(self):
        assert StateMachine.is_revocable("DRAFT") is False

    def test_ac015_next_state_from_draft(self):
        assert StateMachine.next_state("DRAFT") == "PREDIM"

    def test_ac016_next_state_from_liberado_none(self):
        assert StateMachine.next_state("LIBERADO") is None

    def test_ac017_gate_for_draft_to_predim(self):
        gate = StateMachine.requires_gate("DRAFT", "PREDIM")
        assert gate == "G0"

    def test_ac018_gate_for_calc_to_validado(self):
        gate = StateMachine.requires_gate("CALC_INTERNO", "VALIDADO_OT")
        assert gate == "G2"

    def test_ac019_gate_for_validado_to_liberado(self):
        gate = StateMachine.requires_gate("VALIDADO_OT", "LIBERADO")
        assert gate == "G4"

    def test_ac020_gate_ordering(self):
        assert StateMachine.gate_ordering("G0") == 0
        assert StateMachine.gate_ordering("G6") == 6
        assert StateMachine.gate_ordering("G3") == 3

    def test_ac021_all_prior_gates_g2(self):
        passed = ["G0", "G1"]
        assert StateMachine.all_prior_gates_passed("G2", passed) is True

    def test_ac022_missing_prior_gate_fails(self):
        passed = ["G0"]  # falta G1 para llegar a G2
        assert StateMachine.all_prior_gates_passed("G2", passed) is False

    def test_ac023_manifest_builder_constructs(self):
        mb = ManifestBuilder()
        release = {
            "id": str(uuid.uuid4()), "project_id": str(uuid.uuid4()),
            "revision": "A", "maturity": "DRAFT",
            "product_snapshot_hash": "abc123",
            "analysis_snapshot_hash": "def456",
            "library_set_hash": "ghi789",
            "created_at": "2026-07-15T00:00:00Z",
        }
        manifest = mb.build(release, [], [], [])
        assert manifest["revision"] == "A"
        assert manifest["productSnapshotHash"] == "abc123"

    def test_ac024_manifest_includes_all_required_keys(self):
        mb = ManifestBuilder()
        release = {
            "id": str(uuid.uuid4()), "project_id": str(uuid.uuid4()),
            "revision": "B", "maturity": "DRAFT",
            "product_snapshot_hash": None,
            "analysis_snapshot_hash": None,
            "library_set_hash": None,
            "created_at": "2026-07-15T00:00:00Z",
        }
        manifest = mb.build(release, [], [], [])
        required_keys = [
            "releaseId", "projectId", "revision", "maturity",
            "documents", "approvals", "validations", "createdAt",
        ]
        for k in required_keys:
            assert k in manifest, f"Clave ausente: {k}"

    def test_ac025_manifest_sign_requires_a2(self):
        mb = ManifestBuilder()
        manifest = {"releaseId": "x", "maturity": "LIBERADO"}
        with raises(ValueError):
            mb.sign(manifest, "A1")

    def test_ac026_manifest_sign_a2_ok(self):
        mb = ManifestBuilder()
        manifest = {"releaseId": "x", "maturity": "LIBERADO"}
        sig = mb.sign(manifest, "A2")
        assert isinstance(sig, str) and len(sig) == 64

    def test_ac027_manifest_integrity_verify(self):
        mb = ManifestBuilder()
        manifest = {"releaseId": "xyz", "maturity": "LIBERADO", "revision": "A"}
        sig = mb.sign(manifest, "A2")
        assert mb.verify_integrity(manifest, sig, "A2") is True

    def test_ac028_manifest_any_change_breaks_signature(self):
        mb = ManifestBuilder()
        manifest = {"releaseId": "xyz", "maturity": "LIBERADO", "revision": "A"}
        sig = mb.sign(manifest, "A2")
        tampered = dict(manifest)
        tampered["revision"] = "B"  # cambio de un byte semántico
        assert mb.verify_integrity(tampered, sig, "A2") is False

    def test_ac029_maturity_index_ordering(self):
        assert svc._maturity_index("DRAFT") < svc._maturity_index("PREDIM")
        assert svc._maturity_index("PREDIM") < svc._maturity_index("LIBERADO")

    def test_ac030_sha256_dict_deterministic(self):
        d = {"a": 1, "b": [1, 2, 3]}
        h1 = svc._sha256_dict(d)
        h2 = svc._sha256_dict(d)
        assert h1 == h2 and len(h1) == 64


# ── Grupo B: Composición de documentos (AC031-AC050) ─────────────────────────

class TestGroupB_Documents:

    def test_ac031_package_required_fields_all_types(self):
        types = ["PKG_COM", "PKG_CLI", "PKG_CAL", "PKG_PRD",
                 "PKG_SUB", "PKG_SIT", "PKG_QA", "PKG_REG", "PKG_SRV"]
        for t in types:
            assert t in PACKAGE_REQUIRED_FIELDS, f"Tipo {t} sin campos requeridos"

    def test_ac032_pkg_cal_requires_memoria(self):
        assert "memoria_completa" in PACKAGE_REQUIRED_FIELDS["PKG_CAL"]

    def test_ac033_pkg_prd_requires_mbom(self):
        assert "mbom" in PACKAGE_REQUIRED_FIELDS["PKG_PRD"]

    def test_ac034_compose_with_all_fields_not_blocked(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "resumen": "ok", "ficha_tecnica": "ok", "alternativa_seleccionada": "opt_A"
        }}
        template = {"version": "1.0"}
        result = dc.compose(release, template, "PKG_COM")
        assert result["is_blocked"] is False

    def test_ac035_compose_missing_field_blocked(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {"resumen": "ok"}}  # faltan ficha y alternativa
        template = {"version": "1.0"}
        result = dc.compose(release, template, "PKG_COM")
        assert result["is_blocked"] is True
        assert "ficha_tecnica" in result["block_reason"] or "alternativa_seleccionada" in result["block_reason"]

    def test_ac036_compose_returns_content_hash(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "resumen": "ok", "ficha_tecnica": "ft", "alternativa_seleccionada": "A"
        }}
        template = {"version": "1.0"}
        result = dc.compose(release, template, "PKG_COM")
        assert isinstance(result["content_hash"], str) and len(result["content_hash"]) == 64

    def test_ac037_compose_redacts_internal_fields_external(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "resumen": "ok", "ficha_tecnica": "ft", "alternativa_seleccionada": "A",
            "coste_industrial": 5000, "margen": 0.3,
        }}
        template = {"version": "1.0"}
        result = dc.compose(release, template, "PKG_COM", recipient_role="CLIENTE")
        # Los campos internos deben estar redactados
        assert "coste_industrial" not in result["content"]["fields"]
        assert "margen" not in result["content"]["fields"]

    def test_ac038_compose_internal_role_sees_all_fields(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "resumen": "ok", "ficha_tecnica": "ft", "alternativa_seleccionada": "A",
            "coste_industrial": 5000,
        }}
        template = {"version": "1.0"}
        result = dc.compose(release, template, "PKG_COM", recipient_role="INTERNO")
        assert "coste_industrial" in result["content"]["fields"]

    def test_ac039_compose_no_manual_edits_by_default(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "resumen": "ok", "ficha_tecnica": "ft", "alternativa_seleccionada": "A"
        }}
        template = {"version": "1.0"}
        result = dc.compose(release, template, "PKG_COM")
        assert result["has_manual_edits"] is False

    def test_ac040_compose_content_hash_changes_with_locale(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "resumen": "ok", "ficha_tecnica": "ft", "alternativa_seleccionada": "A"
        }}
        template = {"version": "1.0"}
        r_es = dc.compose(release, template, "PKG_COM", locale="es")
        r_en = dc.compose(release, template, "PKG_COM", locale="en")
        assert r_es["content_hash"] != r_en["content_hash"]

    def test_ac041_pkg_reg_requires_documentos_mercado(self):
        assert "documentos_mercado" in PACKAGE_REQUIRED_FIELDS["PKG_REG"]

    def test_ac042_pkg_qa_requires_itp(self):
        assert "itp" in PACKAGE_REQUIRED_FIELDS["PKG_QA"]

    def test_ac043_pkg_sub_requires_pbom(self):
        assert "pbom" in PACKAGE_REQUIRED_FIELDS["PKG_SUB"]

    def test_ac044_pkg_sit_requires_montaje(self):
        assert "montaje" in PACKAGE_REQUIRED_FIELDS["PKG_SIT"]

    def test_ac045_pkg_srv_requires_mantenimiento(self):
        assert "mantenimiento" in PACKAGE_REQUIRED_FIELDS["PKG_SRV"]

    def test_ac046_security_check_exposed_internal(self):
        dc = DocumentComposer()
        fields = {"coste_industrial": 5000, "margen": 0.3, "resumen": "ok"}
        # PKG_COM envía coste_industrial a cliente externo
        exposed = dc.check_package_security("PKG_COM", fields, "CLIENTE")
        assert exposed is True

    def test_ac047_security_check_no_exposure_internal(self):
        dc = DocumentComposer()
        fields = {"coste_industrial": 5000, "margen": 0.3}
        exposed = dc.check_package_security("PKG_COM", fields, "INTERNO")
        assert exposed is False

    def test_ac048_internal_fields_to_redact_pkg_com(self):
        redact = INTERNAL_FIELDS_TO_REDACT.get("PKG_COM", [])
        assert "coste_industrial" in redact

    def test_ac049_internal_fields_to_redact_pkg_cli(self):
        redact = INTERNAL_FIELDS_TO_REDACT.get("PKG_CLI", [])
        assert "coste_industrial" in redact

    def test_ac050_compose_render_qa_failed_when_blocked(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {}}  # sin ningún campo para PKG_CAL
        template = {"version": "1.0"}
        result = dc.compose(release, template, "PKG_CAL")
        assert result["render_qa_passed"] is False


# ── Grupo C: Servicio de validación (AC051-AC075) ─────────────────────────────

class TestGroupC_Validation:

    def _full_release(self, **overrides) -> Dict[str, Any]:
        base = {
            "product_snapshot_hash": "abc" * 21,
            "analysis_snapshot_hash": "def" * 21,
            "library_set_hash": "ghi" * 21,
            "cad_snapshot_hash": "jkl" * 21,
            "calc_completed": True,
            "calc_failed": False,
            "ot_approved": True,
            "open_blocking_comments": 0,
            "bom_reconciled": True,
            "has_manual_edits": False,
            "pending_ai_acceptances": 0,
            "unreviewed_translations": 0,
            "internal_fields_exposed": False,
            "unregistered_distributions": 0,
            "utilizations": [],
        }
        base.update(overrides)
        return base

    def test_ac051_validation_codes_count(self):
        assert len(VALIDATION_CODES) == 10

    def test_ac052_all_blocking_codes_in_validation(self):
        blocking_codes = [
            "REL-SNAPSHOT-001", "REL-CALC-001", "REL-DOC-001",
            "REL-CAD-001", "REL-BOM-001", "REL-APP-001", "REL-SEC-001",
        ]
        for code in blocking_codes:
            assert code in VALIDATION_CODES
            assert VALIDATION_CODES[code][0] == "BLOQUEANTE"

    def test_ac053_lang001_is_grave(self):
        assert VALIDATION_CODES["REL-LANG-001"][0] == "GRAVE"

    def test_ac054_data001_advertencia(self):
        assert VALIDATION_CODES["REL-DATA-001"][0] == "ADVERTENCIA"

    def test_ac055_util001_advertencia(self):
        assert VALIDATION_CODES["REL-UTIL-001"][0] == "ADVERTENCIA"

    def test_ac056_validation_g0_no_snapshots_blocks(self):
        vs = ValidationService()
        release = {"product_snapshot_hash": None, "analysis_snapshot_hash": None, "library_set_hash": None}
        report = vs.run(release, "G0")
        assert report.passed is False
        assert any(c.severity == "BLOQUEANTE" for c in report.blocking)

    def test_ac057_validation_g0_with_snapshots_passes(self):
        vs = ValidationService()
        release = self._full_release()
        report = vs.run(release, "G0")
        assert report.passed is True

    def test_ac058_validation_g1_calc_failed_blocks(self):
        vs = ValidationService()
        release = self._full_release(calc_failed=True, calc_completed=False)
        report = vs.run(release, "G1")
        assert report.passed is False

    def test_ac059_validation_g1_calc_not_completed_blocks(self):
        vs = ValidationService()
        release = self._full_release(calc_completed=False)
        report = vs.run(release, "G1")
        assert report.passed is False

    def test_ac060_validation_g2_ot_not_approved_blocks(self):
        vs = ValidationService()
        release = self._full_release(ot_approved=False)
        report = vs.run(release, "G2")
        assert report.passed is False

    def test_ac061_validation_g2_open_comments_blocks(self):
        vs = ValidationService()
        release = self._full_release(open_blocking_comments=2)
        report = vs.run(release, "G2")
        assert report.passed is False

    def test_ac062_validation_g3_no_cad_blocks(self):
        vs = ValidationService()
        release = self._full_release(cad_snapshot_hash=None)
        report = vs.run(release, "G3")
        assert report.passed is False

    def test_ac063_validation_g3_bom_not_reconciled_blocks(self):
        vs = ValidationService()
        release = self._full_release(bom_reconciled=False)
        report = vs.run(release, "G3")
        assert report.passed is False

    def test_ac064_validation_g4_manual_edits_blocks(self):
        vs = ValidationService()
        release = self._full_release(has_manual_edits=True)
        report = vs.run(release, "G4")
        assert report.passed is False

    def test_ac065_validation_g4_pending_ai_blocks(self):
        vs = ValidationService()
        release = self._full_release(pending_ai_acceptances=3)
        report = vs.run(release, "G4")
        assert report.passed is False

    def test_ac066_validation_g4_unreviewed_translations_grave(self):
        vs = ValidationService()
        release = self._full_release(unreviewed_translations=2)
        report = vs.run(release, "G4")
        # GRAVE pero no BLOQUEANTE → puede no bloquear (pero es error)
        assert any(c.code == "REL-LANG-001" and c.severity == "GRAVE" for c in report.checks)

    def test_ac067_validation_g4_internal_fields_exposed_blocks(self):
        vs = ValidationService()
        release = self._full_release(internal_fields_exposed=True)
        report = vs.run(release, "G4")
        assert report.passed is False

    def test_ac068_validation_g5_unregistered_distributions_blocks(self):
        vs = ValidationService()
        release = self._full_release(unregistered_distributions=1)
        report = vs.run(release, "G5")
        assert report.passed is False

    def test_ac069_validation_g6_asbuilt_missing_blocks(self):
        vs = ValidationService()
        release = self._full_release(asbuilt_hash=None)
        report = vs.run(release, "G6")
        assert report.passed is False

    def test_ac070_validation_g6_asbuilt_present_passes(self):
        vs = ValidationService()
        release = self._full_release(asbuilt_hash="deadbeef" * 8)
        report = vs.run(release, "G6")
        assert report.passed is True

    def test_ac071_utilization_over_limit_blocks(self):
        vs = ValidationService()
        release = self._full_release(utilizations=[{"value": 1.05, "limit": 1.0, "label": "viento"}])
        report = vs.run(release, "G0")
        # > 1.0 → BLOQUEANTE
        blocking = [c for c in report.checks if c.severity == "BLOQUEANTE" and "viento" in c.entity]
        assert len(blocking) >= 1

    def test_ac072_utilization_near_limit_advertencia(self):
        vs = ValidationService()
        release = self._full_release(utilizations=[{"value": 0.97, "limit": 1.0, "label": "nieve"}])
        report = vs.run(release, "G0")
        adv = [c for c in report.checks if c.severity == "ADVERTENCIA" and "nieve" in (c.entity or "")]
        assert len(adv) >= 1

    def test_ac073_utilization_below_alert_no_warning(self):
        vs = ValidationService()
        release = self._full_release(utilizations=[{"value": 0.8, "limit": 1.0, "label": "sismo"}])
        report = vs.run(release, "G0")
        adv = [c for c in report.checks if c.severity == "ADVERTENCIA" and "sismo" in (c.entity or "")]
        assert len(adv) == 0

    def test_ac074_validation_report_errors_property_includes_blocking(self):
        vs = ValidationService()
        release = self._full_release(calc_completed=False)
        report = vs.run(release, "G1")
        assert len(report.errors) >= 1
        error_severities = {c.severity for c in report.errors}
        assert error_severities.issubset({"BLOQUEANTE", "GRAVE"})

    def test_ac075_validation_report_blocking_subset_of_errors(self):
        vs = ValidationService()
        release = self._full_release(
            calc_completed=False, unreviewed_translations=1
        )
        report = vs.run(release, "G1")
        blocking_codes = {c.code for c in report.blocking}
        error_codes = {c.code for c in report.errors}
        assert blocking_codes.issubset(error_codes)


# ── Grupo D: Paquetes producción/calidad (AC076-AC095) ────────────────────────

class TestGroupD_ProductionPackages:

    def test_ac076_pkg_prd_required_fields_all_present(self):
        required = PACKAGE_REQUIRED_FIELDS["PKG_PRD"]
        assert "cad" in required
        assert "planos" in required
        assert "mbom" in required
        assert "rutas" in required
        assert "wps" in required
        assert "control" in required

    def test_ac077_pkg_qa_required_fields(self):
        required = PACKAGE_REQUIRED_FIELDS["PKG_QA"]
        assert "itp" in required
        assert "ctq" in required
        assert "as_built" in required

    def test_ac078_compose_pkg_prd_missing_wps_blocked(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "cad": "x", "planos": "x", "mbom": "x", "rutas": "x", "control": "x"
            # wps ausente
        }}
        result = dc.compose(release, {}, "PKG_PRD")
        assert result["is_blocked"] is True

    def test_ac079_compose_pkg_qa_missing_ncr_blocked(self):
        dc = DocumentComposer()
        release = {"snapshot_fields": {
            "itp": "x", "ctq": "x", "certificados": "x", "as_built": "x"
            # ncr ausente
        }}
        result = dc.compose(release, {}, "PKG_QA")
        assert result["is_blocked"] is True

    def test_ac080_dlp_no_redact_for_prd(self):
        # PKG_PRD interno no tiene campos a redactar
        redact = INTERNAL_FIELDS_TO_REDACT.get("PKG_PRD", [])
        assert redact == []

    def test_ac081_validation_g4_full_clean_passes(self):
        vs = ValidationService()
        release = {
            "product_snapshot_hash": "p" * 64,
            "analysis_snapshot_hash": "a" * 64,
            "library_set_hash": "l" * 64,
            "cad_snapshot_hash": "c" * 64,
            "calc_completed": True, "calc_failed": False,
            "ot_approved": True, "open_blocking_comments": 0,
            "bom_reconciled": True,
            "has_manual_edits": False, "pending_ai_acceptances": 0,
            "unreviewed_translations": 0, "internal_fields_exposed": False,
            "unregistered_distributions": 0, "utilizations": [],
        }
        report = vs.run(release, "G4")
        assert report.passed is True

    def test_ac082_compose_pkg_sub_requires_criterios(self):
        required = PACKAGE_REQUIRED_FIELDS["PKG_SUB"]
        assert "criterios_aceptacion" in required

    def test_ac083_compose_pkg_sit_requires_izado(self):
        required = PACKAGE_REQUIRED_FIELDS["PKG_SIT"]
        assert "izado" in required

    def test_ac084_distribution_service_min_maturity(self):
        ds = DistributionService()
        release = {"maturity": "CALC_INTERNO", "snapshot_fields": {}}
        ok, reason = ds.validate_distribution(release, "cliente@x.com", "PORTAL_CLIENTE", "PKG_CLI")
        assert ok is False
        assert "VALIDADO_OT" in reason

    def test_ac085_distribution_service_validado_ok(self):
        ds = DistributionService()
        release = {"maturity": "VALIDADO_OT", "snapshot_fields": {}}
        ok, reason = ds.validate_distribution(release, "cliente@x.com", "PORTAL_CLIENTE", "PKG_CLI")
        assert ok is True

    def test_ac086_distribution_channel_constraints_all_present(self):
        channels = ["PORTAL_CLIENTE", "PORTAL_PROVEEDOR", "ERP",
                    "CORREO_SEGURO", "EXPORTACION_OFFLINE", "API"]
        for ch in channels:
            assert ch in DistributionService.CHANNEL_CONSTRAINTS

    def test_ac087_distribution_build_package_redacts_external(self):
        ds = DistributionService()
        release = {"snapshot_fields": {
            "coste_industrial": 9999, "margen": 0.4, "resumen": "ok"
        }}
        pkg = ds.build_distribution_package(release, "PKG_COM", "CLIENTE")
        assert "coste_industrial" not in pkg["fields"]
        assert len(pkg["redacted_fields"]) > 0

    def test_ac088_distribution_build_package_keeps_for_internal(self):
        ds = DistributionService()
        release = {"snapshot_fields": {"coste_industrial": 9999, "margen": 0.4}}
        pkg = ds.build_distribution_package(release, "PKG_COM", "INTERNO")
        assert "coste_industrial" in pkg["fields"]

    def test_ac089_distribution_package_has_hash(self):
        ds = DistributionService()
        release = {"snapshot_fields": {"resumen": "ok"}}
        pkg = ds.build_distribution_package(release, "PKG_SRV", "CLIENTE")
        assert isinstance(pkg.get("hash"), str) and len(pkg["hash"]) == 64

    def test_ac090_revoke_distribution_changes_state(self):
        ds = DistributionService()
        dist = {"state": "SENT", "recipient": "x@y.com"}
        result = ds.revoke_distribution(dist, "Error en datos", "admin")
        assert result["state"] == "REVOKED"

    def test_ac091_revoke_distribution_sets_reason(self):
        ds = DistributionService()
        dist = {"state": "SENT"}
        result = ds.revoke_distribution(dist, "Datos incorrectos", "admin")
        assert result["revocation_reason"] == "Datos incorrectos"

    def test_ac092_cannot_revoke_already_revoked(self):
        ds = DistributionService()
        dist = {"state": "REVOKED"}
        assert ds.can_revoke(dist) is False

    def test_ac093_can_revoke_sent(self):
        ds = DistributionService()
        dist = {"state": "SENT"}
        assert ds.can_revoke(dist) is True

    def test_ac094_cannot_revoke_expired(self):
        ds = DistributionService()
        dist = {"state": "EXPIRED"}
        assert ds.can_revoke(dist) is False

    def test_ac095_invalid_channel_fails_validation(self):
        ds = DistributionService()
        release = {"maturity": "LIBERADO"}
        ok, reason = ds.validate_distribution(release, "x", "WHATSAPP", "PKG_COM")
        assert ok is False


# ── Grupo E: Workflow revisión y aprobación (AC096-AC120) ─────────────────────

class TestGroupE_WorkflowApproval:

    def test_ac096_four_eyes_rule_enforced(self):
        rw = ReviewWorkflow()
        with raises(ValueError):
            rw.create_task("rel-1", assigned_to="javier", created_by="javier")

    def test_ac097_four_eyes_different_users_ok(self):
        rw = ReviewWorkflow()
        task = rw.create_task("rel-1", assigned_to="maria", created_by="javier")
        assert task["assigned_to"] == "maria"

    def test_ac098_review_decision_valid_options(self):
        rw = ReviewWorkflow()
        task = {"assigned_to": "maria"}
        for decision in ["APPROVED", "REJECTED", "ABSTAINED", "REQUESTED_CHANGES"]:
            result = rw.record_decision(task.copy(), decision, "maria")
            assert result["decision"] == decision

    def test_ac099_review_decision_wrong_user_fails(self):
        rw = ReviewWorkflow()
        task = {"assigned_to": "maria"}
        with raises(ValueError):
            rw.record_decision(task, "APPROVED", "javier")

    def test_ac100_review_decision_invalid_value_fails(self):
        rw = ReviewWorkflow()
        task = {"assigned_to": "maria"}
        with raises(ValueError):
            rw.record_decision(task, "MAYBE", "maria")

    def test_ac101_blocking_comments_count(self):
        rw = ReviewWorkflow()
        comments = [
            {"is_blocking": True, "resolved": False},
            {"is_blocking": True, "resolved": True},
            {"is_blocking": False, "resolved": False},
            {"is_blocking": True, "resolved": False},
        ]
        assert rw.count_open_blocking_comments(comments) == 2

    def test_ac102_no_open_blocking_comments(self):
        rw = ReviewWorkflow()
        comments = [{"is_blocking": True, "resolved": True}]
        assert rw.count_open_blocking_comments(comments) == 0

    def test_ac103_four_eyes_check_same_user(self):
        rw = ReviewWorkflow()
        assert rw.four_eyes_check("user_a", "user_a") is False

    def test_ac104_four_eyes_check_different_users(self):
        rw = ReviewWorkflow()
        assert rw.four_eyes_check("user_a", "user_b") is True

    def test_ac105_orchestrator_advance_state_g0(self):
        ro = ReleaseOrchestrator()
        release = {
            "maturity": "DRAFT",
            "product_snapshot_hash": "x" * 64,
            "analysis_snapshot_hash": "y" * 64,
            "library_set_hash": "z" * 64,
            "utilizations": [],
        }
        new_state, report = ro.advance_state(release, "G0", "javier")
        assert new_state == "PREDIM"
        assert report.passed is True

    def test_ac106_orchestrator_advance_state_g0_missing_hash_stays(self):
        ro = ReleaseOrchestrator()
        release = {"maturity": "DRAFT", "product_snapshot_hash": None,
                   "analysis_snapshot_hash": None, "library_set_hash": None}
        new_state, report = ro.advance_state(release, "G0", "javier")
        assert new_state == "DRAFT"
        assert report.passed is False

    def test_ac107_orchestrator_validate_transition_ok(self):
        ro = ReleaseOrchestrator()
        ok, reason = ro.validate_transition("DRAFT", "PREDIM", validation_passed=True)
        assert ok is True
        assert reason is None

    def test_ac108_orchestrator_validate_transition_invalid(self):
        ro = ReleaseOrchestrator()
        ok, reason = ro.validate_transition("DRAFT", "LIBERADO", validation_passed=True)
        assert ok is False
        assert reason is not None

    def test_ac109_orchestrator_validate_transition_not_passed(self):
        ro = ReleaseOrchestrator()
        ok, reason = ro.validate_transition("DRAFT", "PREDIM", validation_passed=False)
        assert ok is False

    def test_ac110_can_publish_draft_fails(self):
        ro = ReleaseOrchestrator()
        ok, reason = ro.can_publish({"maturity": "DRAFT", "approvals": []})
        assert ok is False

    def test_ac111_can_publish_validado_missing_g4_fails(self):
        ro = ReleaseOrchestrator()
        release = {
            "maturity": "VALIDADO_OT",
            "product_snapshot_hash": "p" * 64,
            "analysis_snapshot_hash": "a" * 64,
            "approvals": [{"gate": "G2", "state": "APPROVED"}],
        }
        ok, reason = ro.can_publish(release)
        assert ok is False

    def test_ac112_can_publish_validado_with_g4_approved_ok(self):
        ro = ReleaseOrchestrator()
        release = {
            "maturity": "VALIDADO_OT",
            "product_snapshot_hash": "p" * 64,
            "analysis_snapshot_hash": "a" * 64,
            "approvals": [{"gate": "G4", "state": "APPROVED"}],
        }
        ok, reason = ro.can_publish(release)
        assert ok is True

    def test_ac113_orchestrator_revoke_validado_ok(self):
        ro = ReleaseOrchestrator()
        release = {"id": str(uuid.uuid4()), "maturity": "VALIDADO_OT"}
        result = ro.revoke(release, "Error detectado")
        assert result.revoked is True

    def test_ac114_orchestrator_revoke_draft_fails(self):
        ro = ReleaseOrchestrator()
        release = {"id": str(uuid.uuid4()), "maturity": "DRAFT"}
        with raises(ValueError):
            ro.revoke(release, "razón")

    def test_ac115_orchestrator_revoke_liberado_ok(self):
        ro = ReleaseOrchestrator()
        release = {"id": str(uuid.uuid4()), "maturity": "LIBERADO"}
        result = ro.revoke(release, "Dato incorrecto", recipients=["a@b.com", "c@d.com"])
        assert result.recipients_notified == 2

    def test_ac116_auth_level_requirements_all_present(self):
        for level in ["A0", "A1", "A2", "A3", "A4"]:
            assert level in AUTH_LEVEL_REQUIREMENTS

    def test_ac117_auth_level_a2_requires_cert(self):
        assert AUTH_LEVEL_REQUIREMENTS["A2"]["cert"] is True

    def test_ac118_auth_level_a0_no_cert(self):
        assert AUTH_LEVEL_REQUIREMENTS["A0"]["cert"] is False

    def test_ac119_auth_level_a1_requires_mfa(self):
        assert AUTH_LEVEL_REQUIREMENTS["A1"]["mfa"] is True

    def test_ac120_auth_level_a0_no_mfa(self):
        assert AUTH_LEVEL_REQUIREMENTS["A0"]["mfa"] is False


# ── Grupo F: Firma y distribución (AC121-AC135) ───────────────────────────────

class TestGroupF_SignatureDistribution:

    def test_ac121_signature_service_sign_a2_ok(self):
        ss = SignatureService()
        manifest = {"releaseId": "x", "maturity": "LIBERADO"}
        sig = ss.sign(manifest, "A2", "javier")
        assert isinstance(sig, str) and len(sig) == 64

    def test_ac122_signature_service_sign_a1_fails(self):
        ss = SignatureService()
        manifest = {"releaseId": "x"}
        with raises(ValueError):
            ss.sign(manifest, "A1", "javier")

    def test_ac123_signature_verify_valid(self):
        ss = SignatureService()
        manifest = {"releaseId": "x", "maturity": "LIBERADO", "revision": "A"}
        sig = ss.sign(manifest, "A2", "javier")
        assert ss.verify(manifest, sig, "A2", "javier") is True

    def test_ac124_signature_verify_tampered_fails(self):
        ss = SignatureService()
        manifest = {"releaseId": "x", "maturity": "LIBERADO", "revision": "A"}
        sig = ss.sign(manifest, "A2", "javier")
        tampered = dict(manifest)
        tampered["revision"] = "B"
        assert ss.verify(tampered, sig, "A2", "javier") is False

    def test_ac125_one_byte_change_breaks_signature(self):
        ss = SignatureService()
        manifest = {"releaseId": "abc", "value": 100}
        sig = ss.sign(manifest, "A2", "user1")
        # Cambio mínimo: value 100 → 101
        tampered = {"releaseId": "abc", "value": 101}
        assert ss.verify(tampered, sig, "A2", "user1") is False

    def test_ac126_qr_identifier_is_opaque(self):
        ss = SignatureService()
        qr = ss.generate_qr_identifier("release-id-abc")
        assert isinstance(qr, str)
        assert "release-id-abc" not in qr  # no debe contener el ID en claro

    def test_ac127_qr_identifier_deterministic(self):
        ss = SignatureService()
        q1 = ss.generate_qr_identifier("r-123")
        q2 = ss.generate_qr_identifier("r-123")
        assert q1 == q2

    def test_ac128_required_auth_level_for_liberado(self):
        ss = SignatureService()
        assert ss.required_auth_level("LIBERADO") == "A2"

    def test_ac129_required_auth_level_for_draft(self):
        ss = SignatureService()
        assert ss.required_auth_level("DRAFT") == "A0"

    def test_ac130_required_auth_level_for_validado(self):
        ss = SignatureService()
        assert ss.required_auth_level("VALIDADO_OT") == "A1"

    def test_ac131_sign_and_publish_returns_signature_and_datetime(self):
        ro = ReleaseOrchestrator()
        release = {"id": str(uuid.uuid4()), "maturity": "VALIDADO_OT"}
        manifest = {"releaseId": str(uuid.uuid4()), "maturity": "VALIDADO_OT"}
        sig, published_at = ro.sign_and_publish(release, manifest, "A2")
        assert isinstance(sig, str)
        assert published_at is not None

    def test_ac132_watermark_generation(self):
        ss = SecurityService()
        w1 = ss.sign_with_watermark("hash1", "cliente@a.com", "doc-001")
        w2 = ss.sign_with_watermark("hash1", "otro@b.com", "doc-001")
        assert w1 != w2  # cada destinatario tiene watermark único

    def test_ac133_strip_metadata_removes_internal(self):
        ss = SecurityService()
        doc = {
            "content": "datos técnicos",
            "comments": "comentario interno",
            "tracked_changes": "cambios seguidos",
            "author": "javier",
            "revision_history": ["v1", "v2"],
        }
        cleaned = ss.strip_metadata(doc)
        assert "comments" not in cleaned
        assert "tracked_changes" not in cleaned
        assert "author" not in cleaned
        assert "content" in cleaned

    def test_ac134_verify_no_hidden_content_after_strip(self):
        ss = SecurityService()
        doc = {"content": "ok", "hidden_text": "secreto"}
        cleaned = ss.strip_metadata(doc)
        assert ss.verify_no_hidden_content(cleaned) is True

    def test_ac135_dlp_check_no_violation_internal_role(self):
        ss = SecurityService()
        fields = {"coste_industrial": 5000, "margen": 0.3}
        clean, violated = ss.check_dlp(fields, "PKG_COM", "INTERNO")
        assert clean is True
        assert len(violated) == 0


# ── Grupo G: IA y multilingüe (AC136-AC150) ───────────────────────────────────

class TestGroupG_AiMultilingual:

    def test_ac136_ai_service_generate_text(self):
        ai = AiTextService()
        gen = ai.generate("intro", {"height": 8.0}, language="es")
        assert "generated_text" in gen
        assert gen["accepted"] is False

    def test_ac137_ai_service_generate_deterministic(self):
        ai = AiTextService()
        g1 = ai.generate("intro", {"height": 8.0}, language="es")
        g2 = ai.generate("intro", {"height": 8.0}, language="es")
        assert g1["generated_text"] == g2["generated_text"]

    def test_ac138_ai_service_generate_prompt_hash(self):
        ai = AiTextService()
        gen = ai.generate("conclusion", {"material": "S355"})
        assert isinstance(gen["prompt_hash"], str) and len(gen["prompt_hash"]) == 64

    def test_ac139_ai_service_accept_sets_accepted_true(self):
        ai = AiTextService()
        gen = ai.generate("section_1", {})
        result = ai.accept(gen, accepted_by="javier")
        assert result["accepted"] is True
        assert result["accepted_by"] == "javier"

    def test_ac140_ai_service_reject_sets_accepted_false(self):
        ai = AiTextService()
        gen = ai.generate("section_1", {})
        result = ai.accept(gen, accepted_by="javier", reject=True, rejection_reason="Impreciso")
        assert result["accepted"] is False
        assert result["rejection_reason"] == "Impreciso"

    def test_ac141_ai_service_count_pending(self):
        ai = AiTextService()
        gens = [
            {"accepted": True}, {"accepted": False},
            {"accepted": False}, {"accepted": True},
        ]
        assert ai.count_pending(gens) == 2

    def test_ac142_ai_service_all_accepted_true(self):
        ai = AiTextService()
        gens = [{"accepted": True}, {"accepted": True}]
        assert ai.all_accepted(gens) is True

    def test_ac143_ai_service_all_accepted_false_if_any_pending(self):
        ai = AiTextService()
        gens = [{"accepted": True}, {"accepted": False}]
        assert ai.all_accepted(gens) is False

    def test_ac144_ai_different_language_different_text(self):
        ai = AiTextService()
        g_es = ai.generate("intro", {"height": 8.0}, language="es")
        g_en = ai.generate("intro", {"height": 8.0}, language="en")
        assert g_es["generated_text"] != g_en["generated_text"]

    def test_ac145_ai_generation_not_accepted_blocks_release(self):
        """Si hay textos IA sin aceptar, la validación G4 bloquea."""
        vs = ValidationService()
        release = {
            "product_snapshot_hash": "p" * 64,
            "analysis_snapshot_hash": "a" * 64,
            "library_set_hash": "l" * 64,
            "cad_snapshot_hash": "c" * 64,
            "calc_completed": True, "calc_failed": False,
            "ot_approved": True, "open_blocking_comments": 0,
            "bom_reconciled": True,
            "has_manual_edits": False, "pending_ai_acceptances": 2,
            "unreviewed_translations": 0, "internal_fields_exposed": False,
            "unregistered_distributions": 0, "utilizations": [],
        }
        report = vs.run(release, "G4")
        assert report.passed is False

    def test_ac146_lineage_tracker_create_field(self):
        lt = LineageTracker()
        lf = lt.create_field_lineage(
            field_id="utilization_viento",
            document_id="doc-001",
            source_object_id="steel_ver_A",
            source_path="results.utilization.wind",
            calculation_run_id="calc-123",
            rule_id="EN1993-1-1:6.3.1",
        )
        assert lf.field_id == "utilization_viento"
        assert lf.source_hash is not None

    def test_ac147_lineage_tracker_determinista_not_manually_editable(self):
        lt = LineageTracker()
        lf = lt.create_field_lineage("f1", "d1", "obj1", "path1", authoring_mode="DETERMINISTA")
        assert lt.is_manually_editable(lf) is False

    def test_ac148_lineage_tracker_comentario_humano_editable(self):
        lt = LineageTracker()
        lf = lt.create_field_lineage("f1", "d1", "obj1", "path1", authoring_mode="COMENTARIO_HUMANO")
        assert lt.is_manually_editable(lf) is True

    def test_ac149_lineage_detect_manual_edit(self):
        lt = LineageTracker()
        original_hash = svc._sha256_str("path.field:1.234")
        # Valor modificado
        assert lt.detect_manual_edit(original_hash, 1.999, "path.field") is True

    def test_ac150_archive_service_verify_hashes(self):
        arch = ArchiveService()
        manifest = {
            "productSnapshotHash": "p" * 64,
            "analysisSnapshotHash": "a" * 64,
        }
        docs = [{"id": "doc-1", "content_hash": "d" * 64}]
        ok, failures = arch.verify_all_hashes(manifest, docs)
        assert ok is True
        assert len(failures) == 0


# ── Grupo H: Seguridad, archivo y rendimiento (AC151+) ────────────────────────

class TestGroupH_SecurityArchive:

    def test_ac151_archive_build_record(self):
        arch = ArchiveService()
        release = {"id": str(uuid.uuid4()), "revision": "A", "maturity": "LIBERADO"}
        manifest = {"releaseId": release["id"]}
        record = arch.archive(release, manifest, [])
        assert "archive_hash" in record
        assert isinstance(record["archive_hash"], str)

    def test_ac152_archive_hash_is_64_chars(self):
        arch = ArchiveService()
        release = {"id": str(uuid.uuid4())}
        record = arch.archive(release, {}, [])
        assert len(record["archive_hash"]) == 64

    def test_ac153_archive_restore_ok_with_hash(self):
        arch = ArchiveService()
        record = {"archive_hash": "a" * 64}
        ok, err = arch.restore(record)
        assert ok is True
        assert err is None

    def test_ac154_archive_restore_fails_without_hash(self):
        arch = ArchiveService()
        record = {}
        ok, err = arch.restore(record)
        assert ok is False
        assert err is not None

    def test_ac155_verify_hashes_fails_if_doc_missing_hash(self):
        arch = ArchiveService()
        manifest = {
            "productSnapshotHash": "p" * 64,
            "analysisSnapshotHash": "a" * 64,
        }
        docs = [{"id": "doc-1", "content_hash": None}]  # sin hash
        ok, failures = arch.verify_all_hashes(manifest, docs)
        assert ok is False
        assert any("doc-1" in f for f in failures)

    def test_ac156_dlp_violation_detected(self):
        ss = SecurityService()
        fields = {"coste_industrial": 5000, "margen": 0.3, "resumen": "ok"}
        clean, violated = ss.check_dlp(fields, "PKG_COM", "CLIENTE")
        assert clean is False
        assert "coste_industrial" in violated

    def test_ac157_strip_metadata_embedded_objects(self):
        ss = SecurityService()
        doc = {"content": "ok", "embedded_objects": [{"type": "excel"}], "hidden_text": "secreto"}
        cleaned = ss.strip_metadata(doc)
        assert "embedded_objects" not in cleaned
        assert "hidden_text" not in cleaned

    def test_ac158_semantic_diff_technical_change_editorial(self):
        sd = SemanticDiff()
        from_d = {"altura": 8.0, "nota": "primer diseño"}
        to_d = {"altura": 10.0, "nota": "revisado"}
        result = sd.compare(from_d, to_d, "r1", "r2")
        # altura es ENTRADA_TECNICA
        tech = [c for c in result.changes if c.kind == "ENTRADA_TECNICA"]
        assert len(tech) >= 1

    def test_ac159_semantic_diff_editorial_no_invalidate_calc(self):
        sd = SemanticDiff()
        change = ChangeItem(
            kind="EDITORIAL", path="nota", from_value="v1", to_value="v2",
            criticality="INFO"
        )
        assert sd.is_editorial(change) is True
        assert sd.is_technical(change) is False

    def test_ac160_semantic_diff_technical_invalidates_approvals(self):
        sd = SemanticDiff()
        from_d = {"altura": 8.0}
        to_d = {"altura": 12.0}
        result = sd.compare(from_d, to_d, "r1", "r2")
        assert result.technical_changes >= 1
        assert len(result.approvals_invalidated) >= 1

    def test_ac161_semantic_diff_classify_norma_change(self):
        sd = SemanticDiff()
        # "edicion_norma" contiene "norma" (REGLA_NORMATIVA) sin keywords de acción
        kind = sd._classify_key("edicion_norma")
        assert kind == "REGLA_NORMATIVA"

    def test_ac162_semantic_diff_classify_nombre_change(self):
        sd = SemanticDiff()
        kind = sd._classify_key("nombre_proyecto")
        assert kind == "IDENTIDAD"

    def test_ac163_semantic_diff_classify_proveedor(self):
        sd = SemanticDiff()
        kind = sd._classify_key("proveedor_galvanizado")
        assert kind == "INDUSTRIAL"

    def test_ac164_semantic_diff_classify_traduccion(self):
        sd = SemanticDiff()
        kind = sd._classify_key("traduccion_titulo")
        assert kind == "TRADUCCION"

    def test_ac165_semantic_diff_no_changes_empty_result(self):
        sd = SemanticDiff()
        d = {"a": 1, "b": 2}
        result = sd.compare(d, d, "r1", "r2")
        assert len(result.changes) == 0
        assert result.blocking_changes == 0

    def test_ac166_utilization_alert_band_value(self):
        assert UTILIZATION_ALERT_BAND == 0.05

    def test_ac167_sha256_str_produces_64_chars(self):
        h = svc._sha256_str("test")
        assert len(h) == 64

    def test_ac168_sha256_dict_different_values_different_hash(self):
        h1 = svc._sha256_dict({"a": 1})
        h2 = svc._sha256_dict({"a": 2})
        assert h1 != h2

    def test_ac169_maturity_index_draft_zero(self):
        assert svc._maturity_index("DRAFT") == 0

    def test_ac170_maturity_index_liberado_four(self):
        assert svc._maturity_index("LIBERADO") == 4

    def test_ac171_maturity_index_unknown_minus_one(self):
        assert svc._maturity_index("UNKNOWN") == -1

    def test_ac172_lineage_field_source_hash_not_none(self):
        lt = LineageTracker()
        lf = lt.create_field_lineage("f1", "d1", "obj1", "path.to.field")
        assert lf.source_hash is not None and len(lf.source_hash) == 64

    def test_ac173_lineage_field_timestamp_set(self):
        lt = LineageTracker()
        lf = lt.create_field_lineage("f1", "d1", "obj1", "p1")
        assert lf.timestamp is not None

    def test_ac174_manifest_builder_sign_a3_ok(self):
        mb = ManifestBuilder()
        manifest = {"releaseId": "x", "maturity": "LIBERADO"}
        sig = mb.sign(manifest, "A3")
        assert len(sig) == 64

    def test_ac175_manifest_builder_sign_a0_fails(self):
        mb = ManifestBuilder()
        manifest = {"releaseId": "x"}
        with raises(ValueError):
            mb.sign(manifest, "A0")

    def test_ac176_review_workflow_decision_sets_timestamp(self):
        rw = ReviewWorkflow()
        task = {"assigned_to": "ana"}
        result = rw.record_decision(task, "APPROVED", "ana")
        assert result.get("decision_at") is not None

    def test_ac177_archive_components_in_record(self):
        arch = ArchiveService()
        release = {"id": str(uuid.uuid4())}
        record = arch.archive(release, {"releaseId": "x"}, [{"content": "doc"}])
        assert "release" in record["components"]
        assert "manifest" in record["components"]

    def test_ac178_security_service_watermark_deterministic(self):
        ss = SecurityService()
        w1 = ss.sign_with_watermark("hash1", "user@a.com", "doc-1")
        w2 = ss.sign_with_watermark("hash1", "user@a.com", "doc-1")
        assert w1 == w2

    def test_ac179_distribution_service_invalid_purpose_fails(self):
        ds = DistributionService()
        release = {"maturity": "LIBERADO"}
        ok, reason = ds.validate_distribution(release, "x", "PORTAL_CLIENTE", "PKG_INVALIDO")
        assert ok is False

    def test_ac180_syntax_check_all_f15_files(self):
        """Verificación AST de sintaxis para todos los archivos de Fase 15."""
        files = [
            "/sessions/determined-friendly-mayer/mnt/columnas/backend/app/models/db/reports.py",
            "/sessions/determined-friendly-mayer/mnt/columnas/backend/app/models/schemas/reports.py",
            "/sessions/determined-friendly-mayer/mnt/columnas/backend/app/services/reports_service.py",
            "/sessions/determined-friendly-mayer/mnt/columnas/backend/app/api/v1/reports.py",
            "/sessions/determined-friendly-mayer/mnt/columnas/backend/migrations/versions/0015_fase15_informes.py",
        ]
        for fpath in files:
            p = Path(fpath)
            if p.exists():
                src = p.read_bytes().rstrip(b"\x00").decode("utf-8")
                try:
                    ast.parse(src)
                except SyntaxError as e:
                    raise AssertionError(f"SyntaxError en {fpath}: {e}")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    success = _run_all()
    _sys.exit(0 if success else 1)
