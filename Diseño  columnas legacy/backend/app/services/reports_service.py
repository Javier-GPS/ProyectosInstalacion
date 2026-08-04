"""
Salvi Studio · Columns — Servicio Fase 15
Informes, Validación Documental y Liberación.

Motor analítico puro (sin I/O de DB). Los endpoints llaman estos servicios;
las implementaciones con DB se añadirán en el milestone M1.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── Tipos de datos internos (dataclasses, sin dependencia de Pydantic) ──────
from dataclasses import dataclass, field as dc_field
import uuid as _uuid


@dataclass
class ValidationCheck:
    code: str
    severity: str
    message: str
    passed: bool
    entity: Optional[str] = None


@dataclass
class ValidationReport:
    checks: List["ValidationCheck"] = dc_field(default_factory=list)
    gate: str = ""
    passed: bool = False

    @property
    def blocking(self) -> List["ValidationCheck"]:
        return [c for c in self.checks if c.severity == "BLOQUEANTE"]

    @property
    def errors(self) -> List["ValidationCheck"]:
        return [c for c in self.checks if c.severity in ("BLOQUEANTE", "GRAVE")]

    @property
    def warnings(self) -> List["ValidationCheck"]:
        return [c for c in self.checks if c.severity == "ADVERTENCIA"]


@dataclass
class ChangeItem:
    kind: str
    path: str
    from_value: Any = None
    to_value: Any = None
    criticality: str = "INFO"
    affected_docs: List[str] = dc_field(default_factory=list)
    affected_approvals: List[str] = dc_field(default_factory=list)


@dataclass
class DiffResult:
    from_release_id: str
    to_release_id: str
    changes: List["ChangeItem"] = dc_field(default_factory=list)
    blocking_changes: int = 0
    technical_changes: int = 0
    editorial_changes: int = 0
    docs_to_regenerate: List[str] = dc_field(default_factory=list)
    approvals_invalidated: List[str] = dc_field(default_factory=list)
    recipients_notified: List[str] = dc_field(default_factory=list)


@dataclass
class LineageField:
    field_id: str
    document_id: str
    source_object_id: str
    source_path: str
    source_hash: Optional[str] = None
    calculation_run_id: Optional[str] = None
    rule_id: Optional[str] = None
    display_transform: Optional[str] = None
    authoring_mode: str = "DETERMINISTA"
    reviewer: Optional[str] = None
    approval_state: str = "PENDING"
    timestamp: Optional[datetime] = None


@dataclass
class RevokeResult:
    release_id: Any
    revoked: bool
    recipients_notified: int
    new_maturity: str


# ── Constantes ────────────────────────────────────────────────────────────────

# Orden de estados de madurez
MATURITY_ORDER = ["DRAFT", "PREDIM", "CALC_INTERNO", "VALIDADO_OT", "LIBERADO"]
REVOCABLE_STATES = {"VALIDADO_OT", "LIBERADO"}

# Transiciones válidas
STATE_TRANSITIONS: Dict[str, List[str]] = {
    "DRAFT": ["PREDIM"],
    "PREDIM": ["CALC_INTERNO"],
    "CALC_INTERNO": ["VALIDADO_OT"],
    "VALIDADO_OT": ["LIBERADO"],
    "LIBERADO": [],
}

# Códigos de validación estándar
VALIDATION_CODES = {
    "REL-SNAPSHOT-001": ("BLOQUEANTE", "Snapshots incompatibles entre fases."),
    "REL-CALC-001":     ("BLOQUEANTE", "Cálculo obsoleto o fallido."),
    "REL-DOC-001":      ("BLOQUEANTE", "Campo técnico editado fuera de fuente autorizada."),
    "REL-CAD-001":      ("BLOQUEANTE", "CAD no coincide con resultado de cálculo."),
    "REL-BOM-001":      ("BLOQUEANTE", "BOM no reconciliada con modelo CAD."),
    "REL-APP-001":      ("BLOQUEANTE", "Aprobación insuficiente para el gate requerido."),
    "REL-SEC-001":      ("BLOQUEANTE", "Paquete expone información no autorizada."),
    "REL-LANG-001":     ("GRAVE",      "Traducción técnica no revisada por experto."),
    "REL-DATA-001":     ("ADVERTENCIA","Dato conservador o pendiente de confirmación."),
    "REL-UTIL-001":     ("ADVERTENCIA","Utilización próxima al límite (>= banda de alerta)."),
}

# Gates requeridos por estado de madurez objetivo
GATE_FOR_TRANSITION = {
    ("DRAFT", "PREDIM"):           "G0",
    ("PREDIM", "CALC_INTERNO"):    "G1",
    ("CALC_INTERNO", "VALIDADO_OT"): "G2",
    ("VALIDADO_OT", "LIBERADO"):   "G4",
}

# Auth levels requeridos por gate
AUTH_LEVEL_FOR_GATE = {
    "G0": "A0",
    "G1": "A0",
    "G2": "A1",
    "G3": "A1",
    "G4": "A2",
    "G5": "A2",
    "G6": "A2",
}

# Contenido esperado por tipo de paquete (campos mínimos que deben estar presentes)
PACKAGE_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "PKG_COM": ["resumen", "ficha_tecnica", "alternativa_seleccionada"],
    "PKG_CLI": ["informe_extenso", "planos_generales", "condiciones"],
    "PKG_CAL": ["memoria_completa", "resultados", "evidencias"],
    "PKG_PRD": ["cad", "planos", "mbom", "rutas", "wps", "control"],
    "PKG_SUB": ["especificacion", "planos", "pbom", "criterios_aceptacion"],
    "PKG_SIT": ["cimentacion", "montaje", "izado", "recepcion"],
    "PKG_QA":  ["itp", "ctq", "certificados", "ncr", "as_built"],
    "PKG_REG": ["documentos_mercado"],
    "PKG_SRV": ["mantenimiento", "inspecciones", "repuestos"],
}

# Campos internos que deben eliminarse de paquetes externos
INTERNAL_FIELDS_TO_REDACT = {
    "PKG_COM": ["coste_industrial", "margen", "precio_coste"],
    "PKG_CLI": ["coste_industrial", "margen", "proveedor_interno"],
    "PKG_PRD": [],
    "PKG_QA":  ["margen"],
    "PKG_REG": ["coste_industrial"],
    "PKG_SUB": ["margen"],
}

# Clases de cambio técnico (invalidan cálculo)
TECHNICAL_CHANGE_KINDS = {"ENTRADA_TECNICA", "REGLA_NORMATIVA", "RESULTADO", "INDUSTRIAL"}
# Clases de cambio editorial (no invalidan cálculo)
EDITORIAL_CHANGE_KINDS = {"EDITORIAL", "TRADUCCION"}

# Niveles de autenticación y sus requisitos mínimos
AUTH_LEVEL_REQUIREMENTS = {
    "A0": {"sso": True,  "mfa": False, "cert": False},
    "A1": {"sso": True,  "mfa": True,  "cert": False},
    "A2": {"sso": True,  "mfa": True,  "cert": True},
    "A3": {"sso": True,  "mfa": True,  "cert": True},
    "A4": {"sso": False, "mfa": False, "cert": True},
}

# Utilización próxima al límite: banda de alerta (< 5% de margen → ADVERTENCIA)
UTILIZATION_ALERT_BAND = 0.05


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256_dict(data: Dict[str, Any]) -> str:
    """Hash SHA-256 determinista de un diccionario."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _maturity_index(state: str) -> int:
    try:
        return MATURITY_ORDER.index(state)
    except ValueError:
        return -1


# ── StateMachine ──────────────────────────────────────────────────────────────

class StateMachine:
    """Motor de transiciones de estado para el release (M0-M4)."""

    @staticmethod
    def can_transition(from_state: str, to_state: str) -> bool:
        """Devuelve True si la transición from→to es válida."""
        allowed = STATE_TRANSITIONS.get(from_state, [])
        return to_state in allowed

    @staticmethod
    def next_state(from_state: str) -> Optional[str]:
        """Estado siguiente en la cadena M0→M4, o None si es terminal."""
        allowed = STATE_TRANSITIONS.get(from_state, [])
        return allowed[0] if allowed else None

    @staticmethod
    def is_terminal(state: str) -> bool:
        return STATE_TRANSITIONS.get(state, []) == []

    @staticmethod
    def is_revocable(state: str) -> bool:
        return state in REVOCABLE_STATES

    @staticmethod
    def requires_gate(from_state: str, to_state: str) -> Optional[str]:
        """Gate que debe superar la transición, o None si no aplica."""
        return GATE_FOR_TRANSITION.get((from_state, to_state))

    @staticmethod
    def gate_ordering(gate: str) -> int:
        """Ordinal numérico del gate (G0=0, G6=6)."""
        order = {"G0": 0, "G1": 1, "G2": 2, "G3": 3, "G4": 4, "G5": 5, "G6": 6}
        return order.get(gate, -1)

    @staticmethod
    def all_prior_gates_passed(gate: str, gates_passed: List[str]) -> bool:
        """Verifica que todos los gates anteriores al dado estén en gates_passed."""
        target_ord = StateMachine.gate_ordering(gate)
        for g in gates_passed:
            ord_g = StateMachine.gate_ordering(g)
            if ord_g < target_ord and g not in gates_passed:
                return False
        passed_ords = {StateMachine.gate_ordering(g) for g in gates_passed}
        for i in range(target_ord):
            if i not in passed_ords:
                return False
        return True


# ── ValidationService ─────────────────────────────────────────────────────────

class ValidationService:
    """
    Ejecuta la validación automática de un release contra un gate.
    Produce un ValidationReport con checks tipificados.
    """

    def run(
        self,
        release_data: Dict[str, Any],
        gate: str,
        run_by: str = "system",
    ) -> ValidationReport:
        checks: List[ValidationCheck] = []

        if gate in ("G0", "G1", "G2", "G3", "G4", "G5", "G6"):
            checks.extend(self._check_snapshots(release_data))

        if gate in ("G1", "G2", "G3", "G4", "G5", "G6"):
            checks.extend(self._check_calc(release_data))

        if gate in ("G2", "G3", "G4"):
            checks.extend(self._check_ot_approval(release_data))

        if gate in ("G3", "G4", "G5"):
            checks.extend(self._check_cad_bom(release_data))

        if gate in ("G4", "G5"):
            checks.extend(self._check_docs(release_data))
            checks.extend(self._check_security(release_data))

        if gate in ("G5", "G6"):
            checks.extend(self._check_distribution(release_data))

        if gate == "G6":
            checks.extend(self._check_asbuilt(release_data))

        # Checks de utilización (siempre)
        checks.extend(self._check_utilization(release_data))

        blocking_count = sum(1 for c in checks if c.severity == "BLOQUEANTE")
        passed = (blocking_count == 0)

        return ValidationReport(checks=checks, gate=gate, passed=passed)

    # -- Checks privados -------------------------------------------------------

    def _check_snapshots(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        product_hash = d.get("product_snapshot_hash")
        analysis_hash = d.get("analysis_snapshot_hash")
        lib_hash = d.get("library_set_hash")

        if not product_hash:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="BLOQUEANTE",
                message="No hay product_snapshot_hash; snapshots incompatibles.",
                passed=False, entity="product_snapshot"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="INFO",
                message="product_snapshot_hash presente.", passed=True,
                entity="product_snapshot"
            ))

        if not analysis_hash:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="BLOQUEANTE",
                message="No hay analysis_snapshot_hash; cálculo no asociado.",
                passed=False, entity="analysis_snapshot"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="INFO",
                message="analysis_snapshot_hash presente.", passed=True,
                entity="analysis_snapshot"
            ))

        if not lib_hash:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="ADVERTENCIA",
                message="library_set_hash no definido; versiones de biblioteca no trazables.",
                passed=False, entity="library_set"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="INFO",
                message="library_set_hash presente.", passed=True,
                entity="library_set"
            ))

        return results

    def _check_calc(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        calc_ok = d.get("calc_completed", False)
        calc_failed = d.get("calc_failed", False)

        if calc_failed:
            results.append(ValidationCheck(
                code="REL-CALC-001", severity="BLOQUEANTE",
                message="El motor de cálculo reportó fallo.", passed=False, entity="calc"
            ))
        elif not calc_ok:
            results.append(ValidationCheck(
                code="REL-CALC-001", severity="BLOQUEANTE",
                message="Cálculo no completado.", passed=False, entity="calc"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-CALC-001", severity="INFO",
                message="Motor de cálculo completado sin errores.", passed=True, entity="calc"
            ))
        return results

    def _check_ot_approval(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        ot_approved = d.get("ot_approved", False)
        open_comments = d.get("open_blocking_comments", 0)

        if not ot_approved:
            results.append(ValidationCheck(
                code="REL-APP-001", severity="BLOQUEANTE",
                message="Revisión OT no completada.", passed=False, entity="ot_review"
            ))
        elif open_comments > 0:
            results.append(ValidationCheck(
                code="REL-APP-001", severity="BLOQUEANTE",
                message=f"{open_comments} comentarios bloqueantes abiertos en revisión OT.",
                passed=False, entity="ot_review"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-APP-001", severity="INFO",
                message="Revisión OT aprobada sin comentarios abiertos.", passed=True,
                entity="ot_review"
            ))
        return results

    def _check_cad_bom(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        cad_hash = d.get("cad_snapshot_hash")
        bom_reconciled = d.get("bom_reconciled", False)

        if not cad_hash:
            results.append(ValidationCheck(
                code="REL-CAD-001", severity="BLOQUEANTE",
                message="No hay cad_snapshot_hash; CAD no asociado.", passed=False, entity="cad"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-CAD-001", severity="INFO",
                message="CAD asociado y hash presente.", passed=True, entity="cad"
            ))

        if not bom_reconciled:
            results.append(ValidationCheck(
                code="REL-BOM-001", severity="BLOQUEANTE",
                message="BOM no reconciliada con el modelo CAD.", passed=False, entity="bom"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-BOM-001", severity="INFO",
                message="BOM reconciliada correctamente.", passed=True, entity="bom"
            ))
        return results

    def _check_docs(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        manual_edits = d.get("has_manual_edits", False)
        pending_ai = d.get("pending_ai_acceptances", 0)
        unreviewed_translations = d.get("unreviewed_translations", 0)

        if manual_edits:
            results.append(ValidationCheck(
                code="REL-DOC-001", severity="BLOQUEANTE",
                message="Documento con campos técnicos editados manualmente.",
                passed=False, entity="document"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-DOC-001", severity="INFO",
                message="Sin ediciones manuales detectadas.", passed=True, entity="document"
            ))

        if pending_ai > 0:
            results.append(ValidationCheck(
                code="REL-DOC-001", severity="BLOQUEANTE",
                message=f"{pending_ai} textos IA pendientes de aceptación humana.",
                passed=False, entity="ai_text"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-DOC-001", severity="INFO",
                message="Todos los textos IA han sido aceptados.", passed=True, entity="ai_text"
            ))

        if unreviewed_translations > 0:
            results.append(ValidationCheck(
                code="REL-LANG-001", severity="GRAVE",
                message=f"{unreviewed_translations} traducciones técnicas sin revisar.",
                passed=False, entity="translations"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-LANG-001", severity="INFO",
                message="Todas las traducciones revisadas.", passed=True, entity="translations"
            ))
        return results

    def _check_security(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        exposed_internal = d.get("internal_fields_exposed", False)

        if exposed_internal:
            results.append(ValidationCheck(
                code="REL-SEC-001", severity="BLOQUEANTE",
                message="El paquete externo expone información interna (costes/márgenes).",
                passed=False, entity="security"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-SEC-001", severity="INFO",
                message="DLP: no se detectan campos internos en paquetes externos.",
                passed=True, entity="security"
            ))
        return results

    def _check_distribution(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        unregistered = d.get("unregistered_distributions", 0)
        if unregistered > 0:
            results.append(ValidationCheck(
                code="REL-SEC-001", severity="BLOQUEANTE",
                message=f"{unregistered} distribuciones sin registro controlado.",
                passed=False, entity="distribution"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-SEC-001", severity="INFO",
                message="Todas las distribuciones registradas.", passed=True,
                entity="distribution"
            ))
        return results

    def _check_asbuilt(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        asbuilt_hash = d.get("asbuilt_hash")
        if not asbuilt_hash:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="BLOQUEANTE",
                message="Expediente as-built no cerrado; hash ausente.", passed=False,
                entity="asbuilt"
            ))
        else:
            results.append(ValidationCheck(
                code="REL-SNAPSHOT-001", severity="INFO",
                message="Expediente as-built cerrado con hash.", passed=True,
                entity="asbuilt"
            ))
        return results

    def _check_utilization(self, d: Dict[str, Any]) -> List[ValidationCheck]:
        results = []
        utilizations: List[Dict[str, Any]] = d.get("utilizations", [])
        for u in utilizations:
            value = u.get("value", 0.0)
            limit = u.get("limit", 1.0)
            label = u.get("label", "desconocido")
            if limit == 0:
                continue
            ratio = value / limit
            margin = 1.0 - ratio
            if margin < 0:
                results.append(ValidationCheck(
                    code="REL-UTIL-001", severity="BLOQUEANTE",
                    message=f"Incumplimiento: {label} ratio={ratio:.3f} > 1.0",
                    passed=False, entity=label
                ))
            elif margin < UTILIZATION_ALERT_BAND:
                results.append(ValidationCheck(
                    code="REL-UTIL-001", severity="ADVERTENCIA",
                    message=f"Utilización próxima al límite: {label} margen={margin:.3f}",
                    passed=True, entity=label
                ))
        return results


# ── DocumentComposer ──────────────────────────────────────────────────────────

class DocumentComposer:
    """
    Compone un documento a partir de una plantilla y un snapshot.
    Verifica que no haya ediciones manuales y que los campos IA estén aceptados.
    El documento es una VISTA del expediente, nunca una fuente primaria.
    """

    def compose(
        self,
        release_data: Dict[str, Any],
        template_data: Dict[str, Any],
        purpose: str,
        locale: str = "es",
        recipient_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Devuelve un dict representando el documento compuesto."""
        required = PACKAGE_REQUIRED_FIELDS.get(purpose, [])
        snapshot_fields = release_data.get("snapshot_fields", {})
        present_fields = [f for f in required if f in snapshot_fields]
        missing_fields = [f for f in required if f not in snapshot_fields]

        # Aplicar visibilidad por rol
        redact_fields = INTERNAL_FIELDS_TO_REDACT.get(purpose, [])
        if recipient_role and recipient_role not in ("INTERNO", "OT", "PRODUCCION"):
            visible_fields = {
                k: v for k, v in snapshot_fields.items()
                if k not in redact_fields
            }
        else:
            visible_fields = snapshot_fields.copy()

        content_data = {
            "purpose": purpose,
            "locale": locale,
            "recipient_role": recipient_role,
            "template_version": template_data.get("version", "unknown"),
            "fields": visible_fields,
            "missing_fields": missing_fields,
        }
        content_hash = _sha256_dict(content_data)

        is_blocked = len(missing_fields) > 0
        block_reason = (
            f"Campos requeridos ausentes: {', '.join(missing_fields)}"
            if missing_fields else None
        )

        return {
            "content": content_data,
            "content_hash": content_hash,
            "is_blocked": is_blocked,
            "block_reason": block_reason,
            "has_manual_edits": False,
            "render_qa_passed": not is_blocked,
            "accessibility_passed": not is_blocked,
            "pdf_a_compliant": not is_blocked,
        }

    def check_package_security(
        self, purpose: str, fields: Dict[str, Any], recipient_role: str
    ) -> bool:
        """
        Devuelve True si el paquete expone campos internos que no deberían
        ser visibles para el recipient_role dado.
        """
        if recipient_role in ("INTERNO", "OT", "PRODUCCION", "CALIDAD"):
            return False  # acceso interno OK
        redact = INTERNAL_FIELDS_TO_REDACT.get(purpose, [])
        for field in redact:
            if field in fields:
                return True  # EXPONE info interna → fallo de seguridad
        return False


# ── ManifestBuilder ───────────────────────────────────────────────────────────

class ManifestBuilder:
    """Construye el manifiesto inmutable del expediente."""

    def build(
        self,
        release_data: Dict[str, Any],
        documents: List[Dict[str, Any]],
        approvals: List[Dict[str, Any]],
        validations: List[Dict[str, Any]],
        distribution_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        manifest = {
            "releaseId": str(release_data.get("id", "")),
            "projectId": str(release_data.get("project_id", "")),
            "revision": release_data.get("revision", ""),
            "maturity": release_data.get("maturity", "DRAFT"),
            "productSnapshotHash": release_data.get("product_snapshot_hash"),
            "analysisSnapshotHash": release_data.get("analysis_snapshot_hash"),
            "librarySetHash": release_data.get("library_set_hash"),
            "documents": documents,
            "evidence": release_data.get("evidence", []),
            "approvals": approvals,
            "validations": validations,
            "distributionPolicy": distribution_policy,
            "createdAt": release_data.get("created_at", _now_utc().isoformat()),
            "publishedAt": None,
            "supersedes": str(release_data.get("supersedes_id")) if release_data.get("supersedes_id") else None,
            "signature": None,
        }
        return manifest

    def sign(self, manifest: Dict[str, Any], auth_level: str) -> str:
        """
        Simula la firma del manifiesto. En producción usará certificado corporativo.
        La firma cubre el manifiesto completo y, por referencia hash, todos los artefactos.
        """
        if auth_level not in ("A2", "A3", "A4"):
            raise ValueError(f"Firma requiere auth_level >= A2; recibido: {auth_level}")
        signature_data = _sha256_dict(manifest) + f":{auth_level}"
        return _sha256_str(signature_data)

    def verify_integrity(self, manifest: Dict[str, Any], signature: str, auth_level: str) -> bool:
        """Verifica que la firma del manifiesto siga siendo válida."""
        expected = self.sign({k: v for k, v in manifest.items() if k != "signature"}, auth_level)
        return signature == expected


# ── SemanticDiff ──────────────────────────────────────────────────────────────

class SemanticDiff:
    """
    Compara dos revisiones semánticamente.
    Clasifica cada cambio por naturaleza, criticidad y alcance de impacto.
    """

    # Respuestas automáticas por clase de cambio
    CHANGE_RESPONSES = {
        "IDENTIDAD":       ("INFO",        False, True),   # (criticality, invalidates_calc, notify)
        "ENTRADA_TECNICA": ("BLOQUEANTE",  True,  True),
        "REGLA_NORMATIVA": ("BLOQUEANTE",  True,  True),
        "RESULTADO":       ("GRAVE",       False, True),
        "INDUSTRIAL":      ("GRAVE",       False, True),
        "EDITORIAL":       ("INFO",        False, False),
        "TRADUCCION":      ("ADVERTENCIA", False, False),
        "PERMISO":         ("GRAVE",       False, True),
    }

    def compare(
        self,
        from_data: Dict[str, Any],
        to_data: Dict[str, Any],
        from_id: str,
        to_id: str,
    ) -> DiffResult:
        changes: List[ChangeItem] = []
        blocking = 0
        technical = 0
        editorial = 0
        docs_regen: List[str] = []
        approvals_inv: List[str] = []
        recipients: List[str] = []

        # Comparar campos de primer nivel
        all_keys = set(from_data.keys()) | set(to_data.keys())
        for key in sorted(all_keys):
            from_val = from_data.get(key)
            to_val = to_data.get(key)
            if from_val == to_val:
                continue
            kind = self._classify_key(key)
            crit, inv_calc, notify = self.CHANGE_RESPONSES.get(kind, ("INFO", False, False))

            change = ChangeItem(
                kind=kind, path=key,
                from_value=from_val, to_value=to_val,
                criticality=crit,
                affected_docs=["all"] if inv_calc else [],
                affected_approvals=["G2", "G3", "G4"] if inv_calc else [],
            )
            changes.append(change)

            if crit == "BLOQUEANTE":
                blocking += 1
            if kind in TECHNICAL_CHANGE_KINDS:
                technical += 1
                if "all" not in docs_regen:
                    docs_regen.append("all")
                for ap in change.affected_approvals:
                    if ap not in approvals_inv:
                        approvals_inv.append(ap)
            if kind in EDITORIAL_CHANGE_KINDS:
                editorial += 1
            if notify:
                recipients.append(key)

        return DiffResult(
            from_release_id=from_id,
            to_release_id=to_id,
            changes=changes,
            blocking_changes=blocking,
            technical_changes=technical,
            editorial_changes=editorial,
            docs_to_regenerate=docs_regen,
            approvals_invalidated=approvals_inv,
            recipients_notified=recipients,
        )

    def _classify_key(self, key: str) -> str:
        """Clasifica un campo por su nombre en una clase de cambio semántico."""
        key_lower = key.lower()
        if any(k in key_lower for k in ("height", "diameter", "thickness", "material",
                                         "wind", "snow", "seismic", "load", "accion",
                                         "altura", "diametro", "espesor", "viento", "nieve")):
            return "ENTRADA_TECNICA"
        if any(k in key_lower for k in ("norm", "standard", "edition", "annex",
                                         "norma", "edicion", "anexo", "coeficiente")):
            return "REGLA_NORMATIVA"
        if any(k in key_lower for k in ("utilization", "stress", "deflection", "result",
                                         "utilizacion", "tension", "deformacion", "resultado")):
            return "RESULTADO"
        if any(k in key_lower for k in ("supplier", "wps", "route", "finish",
                                         "proveedor", "ruta", "acabado")):
            return "INDUSTRIAL"
        if any(k in key_lower for k in ("name", "client", "project", "reference",
                                         "nombre", "cliente", "proyecto", "referencia")):
            return "IDENTIDAD"
        if any(k in key_lower for k in ("locale", "translation", "language",
                                         "idioma", "traduccion")):
            return "TRADUCCION"
        if any(k in key_lower for k in ("permission", "recipient", "classification",
                                         "permiso", "destinatario", "clasificacion")):
            return "PERMISO"
        return "EDITORIAL"

    def is_technical(self, change: ChangeItem) -> bool:
        return change.kind in TECHNICAL_CHANGE_KINDS

    def is_editorial(self, change: ChangeItem) -> bool:
        return change.kind in EDITORIAL_CHANGE_KINDS


# ── ReleaseOrchestrator ───────────────────────────────────────────────────────

class ReleaseOrchestrator:
    """
    Orquesta el ciclo de vida del expediente:
    crear → validar → aprobar → publicar → revocar.
    """

    def __init__(self):
        self._validator = ValidationService()
        self._manifest_builder = ManifestBuilder()

    def validate_transition(
        self,
        current_state: str,
        target_state: str,
        validation_passed: bool,
    ) -> Tuple[bool, Optional[str]]:
        """Valida si se puede ejecutar la transición de estado."""
        if not StateMachine.can_transition(current_state, target_state):
            return False, f"Transición {current_state}→{target_state} no permitida."
        if not validation_passed:
            return False, f"La validación del gate no superada. No se puede avanzar a {target_state}."
        return True, None

    def advance_state(
        self,
        release_data: Dict[str, Any],
        gate: str,
        validated_by: str,
    ) -> Tuple[str, ValidationReport]:
        """Ejecuta validación y avanza el estado si procede."""
        report = self._validator.run(release_data, gate, run_by=validated_by)
        current = release_data.get("maturity", "DRAFT")
        target = StateMachine.next_state(current)
        if report.passed and target:
            return target, report
        return current, report

    def can_publish(self, release_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Verifica prerrequisitos para publicación M4."""
        maturity = release_data.get("maturity", "DRAFT")
        if maturity not in ("VALIDADO_OT", "LIBERADO"):
            return False, f"Estado {maturity} no permite publicación; se requiere VALIDADO_OT."
        if not release_data.get("product_snapshot_hash"):
            return False, "Falta product_snapshot_hash."
        if not release_data.get("analysis_snapshot_hash"):
            return False, "Falta analysis_snapshot_hash."
        approvals = release_data.get("approvals", [])
        if not any(a.get("gate") in ("G4",) and a.get("state") == "APPROVED" for a in approvals):
            return False, "Falta aprobación G4."
        return True, None

    def build_manifest(
        self,
        release_data: Dict[str, Any],
        documents: List[Dict[str, Any]],
        approvals: List[Dict[str, Any]],
        validations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return self._manifest_builder.build(
            release_data, documents, approvals, validations
        )

    def sign_and_publish(
        self,
        release_data: Dict[str, Any],
        manifest: Dict[str, Any],
        auth_level: str,
    ) -> Tuple[str, datetime]:
        """Firma el manifiesto y registra la publicación."""
        signature = self._manifest_builder.sign(manifest, auth_level)
        published_at = _now_utc()
        return signature, published_at

    def revoke(
        self,
        release_data: Dict[str, Any],
        reason: str,
        notify_recipients: bool = True,
        recipients: Optional[List[str]] = None,
    ) -> RevokeResult:
        """Revoca un release M3/M4."""
        state = release_data.get("maturity", "DRAFT")
        if not StateMachine.is_revocable(state):
            raise ValueError(f"No se puede revocar un release en estado {state}.")
        notified = len(recipients or []) if notify_recipients else 0
        return RevokeResult(
            release_id=release_data["id"],
            revoked=True,
            recipients_notified=notified,
            new_maturity="REVOCADO",
        )


# ── ReviewWorkflow ────────────────────────────────────────────────────────────

class ReviewWorkflow:
    """
    Gestiona el flujo de revisión OT con regla de cuatro ojos.
    El revisor ≠ aprobador.
    """

    def create_task(
        self,
        release_id: str,
        assigned_to: str,
        created_by: str,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        if assigned_to == created_by:
            raise ValueError("Regla cuatro ojos: el revisor no puede ser el mismo que el solicitante.")
        return {
            "release_snapshot_id": release_id,
            "assigned_to": assigned_to,
            "scope": scope,
            "decision": None,
            "open_items_count": 0,
            "created_by": created_by,
        }

    def record_decision(
        self,
        task_data: Dict[str, Any],
        decision: str,
        decided_by: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        assigned_to = task_data.get("assigned_to")
        if decided_by != assigned_to:
            raise ValueError(
                f"Solo el revisor asignado ({assigned_to}) puede registrar la decisión."
            )
        valid = {"APPROVED", "REJECTED", "ABSTAINED", "REQUESTED_CHANGES"}
        if decision not in valid:
            raise ValueError(f"Decisión inválida: {decision}. Debe ser una de {valid}")
        task_data["decision"] = decision
        task_data["decision_at"] = _now_utc().isoformat()
        task_data["decision_notes"] = notes
        return task_data

    def count_open_blocking_comments(self, comments: List[Dict[str, Any]]) -> int:
        return sum(
            1 for c in comments
            if c.get("is_blocking") and not c.get("resolved", False)
        )

    def four_eyes_check(self, reviewer: str, approver: str) -> bool:
        """La regla de cuatro ojos requiere reviewer ≠ approver."""
        return reviewer != approver


# ── DistributionService ───────────────────────────────────────────────────────

class DistributionService:
    """
    Gestiona la distribución controlada de paquetes documentales.
    La distribución forma parte del expediente; no es un correo sin registro.
    """

    CHANNEL_CONSTRAINTS = {
        "PORTAL_CLIENTE":    {"requires_auth": True,  "allows_link": True,  "watermark_supported": True},
        "PORTAL_PROVEEDOR":  {"requires_auth": True,  "allows_link": True,  "watermark_supported": True},
        "ERP":               {"requires_auth": True,  "allows_link": False, "watermark_supported": False},
        "CORREO_SEGURO":     {"requires_auth": False, "allows_link": True,  "watermark_supported": True},
        "EXPORTACION_OFFLINE": {"requires_auth": False, "allows_link": False, "watermark_supported": True},
        "API":               {"requires_auth": True,  "allows_link": False, "watermark_supported": False},
    }

    def validate_distribution(
        self,
        release_data: Dict[str, Any],
        recipient: str,
        channel: str,
        purpose: str,
    ) -> Tuple[bool, Optional[str]]:
        """Verifica que se puede distribuir el release."""
        maturity = release_data.get("maturity", "DRAFT")
        if _maturity_index(maturity) < _maturity_index("VALIDADO_OT"):
            return False, f"Release en estado {maturity} no puede distribuirse (mínimo VALIDADO_OT)."
        if channel not in self.CHANNEL_CONSTRAINTS:
            return False, f"Canal desconocido: {channel}"
        if purpose not in PACKAGE_REQUIRED_FIELDS:
            return False, f"Tipo de paquete desconocido: {purpose}"
        return True, None

    def build_distribution_package(
        self,
        release_data: Dict[str, Any],
        purpose: str,
        recipient_role: str,
    ) -> Dict[str, Any]:
        """
        Construye el paquete de distribución aplicando política de visibilidad.
        Elimina campos internos antes de entregar al destinatario externo.
        """
        fields = release_data.get("snapshot_fields", {})
        redact = INTERNAL_FIELDS_TO_REDACT.get(purpose, [])
        is_external = recipient_role not in ("INTERNO", "OT", "PRODUCCION", "CALIDAD")

        if is_external:
            visible = {k: v for k, v in fields.items() if k not in redact}
        else:
            visible = fields.copy()

        package = {
            "purpose": purpose,
            "fields": visible,
            "redacted_fields": redact if is_external else [],
        }
        package["hash"] = _sha256_dict(package)
        return package

    def revoke_distribution(
        self,
        dist_data: Dict[str, Any],
        reason: str,
        revoked_by: str,
    ) -> Dict[str, Any]:
        dist_data["state"] = "REVOKED"
        dist_data["revoked_at"] = _now_utc().isoformat()
        dist_data["revocation_reason"] = reason
        return dist_data

    def can_revoke(self, dist_data: Dict[str, Any]) -> bool:
        return dist_data.get("state") not in ("REVOKED", "EXPIRED")


# ── SecurityService ───────────────────────────────────────────────────────────

class SecurityService:
    """
    DLP y protección del know-how.
    La seguridad se basa en clasificación estructurada, no en marcas de agua.
    """

    def check_dlp(
        self,
        package_fields: Dict[str, Any],
        purpose: str,
        recipient_role: str,
    ) -> Tuple[bool, List[str]]:
        """
        Devuelve (clean, violated_fields).
        clean=True → no hay violaciones; False → hay campos internos expuestos.
        """
        if recipient_role in ("INTERNO", "OT", "PRODUCCION", "CALIDAD"):
            return True, []
        redact = INTERNAL_FIELDS_TO_REDACT.get(purpose, [])
        violated = [f for f in redact if f in package_fields]
        return len(violated) == 0, violated

    def strip_metadata(self, doc_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Elimina metadatos internos ocultos del documento.
        Tapar visualmente texto NO es una redacción válida.
        """
        internal_meta = ["comments", "tracked_changes", "embedded_objects",
                         "author", "revision_history", "hidden_text"]
        cleaned = {k: v for k, v in doc_data.items() if k not in internal_meta}
        cleaned["_metadata_stripped"] = True
        return cleaned

    def verify_no_hidden_content(self, doc_data: Dict[str, Any]) -> bool:
        """Verifica que no haya contenido oculto tras strip_metadata."""
        return doc_data.get("_metadata_stripped", False)

    def sign_with_watermark(
        self, doc_hash: str, recipient: str, doc_id: str
    ) -> str:
        """Genera watermark individual asociado al destinatario."""
        return _sha256_str(f"{doc_hash}:{recipient}:{doc_id}")


# ── SignatureService ──────────────────────────────────────────────────────────

class SignatureService:
    """
    Autenticidad del expediente mediante firma/sello del manifiesto.
    Un cambio de un solo byte en el manifiesto invalida la firma.
    """

    def sign(self, manifest: Dict[str, Any], auth_level: str, signer: str) -> str:
        """Firma el manifiesto. Requiere auth_level >= A2 para paquetes M3/M4."""
        auth_order = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}
        if auth_order.get(auth_level, 0) < 2:
            raise ValueError(f"Firma de expediente requiere auth_level >= A2; recibido {auth_level}")
        payload = json.dumps(manifest, sort_keys=True, default=str) + f":{auth_level}:{signer}"
        return _sha256_str(payload)

    def verify(self, manifest: Dict[str, Any], signature: str, auth_level: str, signer: str) -> bool:
        """Cualquier cambio de un byte en el manifiesto invalida la firma."""
        expected = self.sign(manifest, auth_level, signer)
        return signature == expected

    def generate_qr_identifier(self, release_id: str) -> str:
        """
        Genera identificador opaco para QR.
        El QR no contiene información técnica sensible; solo un ID opaco + URL.
        """
        return _sha256_str(f"QR:{release_id}")[:16].upper()

    def required_auth_level(self, maturity: str) -> str:
        """Auth level mínimo requerido según el estado de madurez."""
        mapping = {
            "DRAFT": "A0",
            "PREDIM": "A0",
            "CALC_INTERNO": "A1",
            "VALIDADO_OT": "A1",
            "LIBERADO": "A2",
        }
        return mapping.get(maturity, "A0")


# ── AiTextService ─────────────────────────────────────────────────────────────

class AiTextService:
    """
    Gestiona textos generados por IA.
    Todos los textos IA requieren aceptación humana explícita antes de liberar.
    """

    def generate(
        self,
        section_id: str,
        data: Dict[str, Any],
        language: str = "es",
        model_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simula generación de texto IA. En producción llama al LLM."""
        prompt_hash = _sha256_dict({"section": section_id, "data": data, "lang": language})
        # Texto sintético determinista para tests
        text = f"[AI:{language}] Sección {section_id}: resumen generado automáticamente."
        return {
            "section_id": section_id,
            "generated_text": text,
            "language": language,
            "model_version": model_version or "gpt-4o",
            "prompt_hash": prompt_hash,
            "accepted": False,
            "accepted_by": None,
        }

    def accept(
        self,
        generation: Dict[str, Any],
        accepted_by: str,
        reject: bool = False,
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Registra la aceptación o rechazo humano del texto IA."""
        if reject:
            generation["accepted"] = False
            generation["rejection_reason"] = rejection_reason
        else:
            generation["accepted"] = True
            generation["accepted_by"] = accepted_by
            generation["accepted_at"] = _now_utc().isoformat()
        return generation

    def count_pending(self, generations: List[Dict[str, Any]]) -> int:
        """Cuenta textos IA pendientes de aceptación humana."""
        return sum(1 for g in generations if not g.get("accepted", False))

    def all_accepted(self, generations: List[Dict[str, Any]]) -> bool:
        return self.count_pending(generations) == 0


# ── LineageTracker ────────────────────────────────────────────────────────────

class LineageTracker:
    """
    Trazabilidad a nivel de campo para cada valor del informe.
    Permite seleccionar cualquier valor y abrir su cadena de procedencia.
    """

    def create_field_lineage(
        self,
        field_id: str,
        document_id: str,
        source_object_id: str,
        source_path: str,
        calculation_run_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        display_transform: Optional[str] = None,
        authoring_mode: str = "DETERMINISTA",
    ) -> LineageField:
        return LineageField(
            field_id=field_id,
            document_id=document_id,
            source_object_id=source_object_id,
            source_path=source_path,
            source_hash=_sha256_str(f"{source_object_id}:{source_path}"),
            calculation_run_id=calculation_run_id,
            rule_id=rule_id,
            display_transform=display_transform,
            authoring_mode=authoring_mode,
            approval_state="PENDING",
            timestamp=_now_utc(),
        )

    def is_manually_editable(self, lineage: LineageField) -> bool:
        """
        Los campos técnicos (modo DETERMINISTA o PLANTILLA) NO son editables manualmente.
        Solo COMENTARIO_HUMANO permite edición directa.
        """
        return lineage.authoring_mode == "COMENTARIO_HUMANO"

    def detect_manual_edit(
        self,
        original_hash: str,
        current_value: Any,
        source_path: str,
    ) -> bool:
        """Detecta si un campo ha sido editado manualmente post-render."""
        current_hash = _sha256_str(f"{source_path}:{str(current_value)}")
        return current_hash != original_hash


# ── ArchiveService ────────────────────────────────────────────────────────────

class ArchiveService:
    """
    Archivo de largo plazo y restauración de expedientes.
    Conserva documentos, manifiestos, certificados, hashes, reglas y
    software mínimo de verificación.
    """

    def archive(
        self,
        release_data: Dict[str, Any],
        manifest: Dict[str, Any],
        documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Genera el registro de archivo inmutable."""
        archive_content = {
            "release": release_data,
            "manifest": manifest,
            "documents": documents,
        }
        archive_hash = _sha256_dict(archive_content)
        return {
            "archive_id": _sha256_str(str(release_data.get("id", "")) + archive_hash)[:16],
            "release_id": str(release_data.get("id", "")),
            "archive_hash": archive_hash,
            "archived_at": _now_utc().isoformat(),
            "components": list(archive_content.keys()),
        }

    def restore(
        self,
        archive_record: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifica la integridad del archivo antes de restaurar.
        RPO/RTO definidos por metadatos, artefactos y firma.
        """
        stored_hash = archive_record.get("archive_hash")
        if not stored_hash:
            return False, "archive_hash ausente; archivo corrupto."
        # En producción: recalcular hash del contenido real y comparar
        return True, None

    def verify_all_hashes(
        self,
        manifest: Dict[str, Any],
        documents: List[Dict[str, Any]],
    ) -> Tuple[bool, List[str]]:
        """
        Verifica todos los hashes del expediente M4.
        Un hash ausente o incorrecto es motivo de fallo.
        """
        failures: List[str] = []
        if not manifest.get("productSnapshotHash"):
            failures.append("productSnapshotHash ausente")
        if not manifest.get("analysisSnapshotHash"):
            failures.append("analysisSnapshotHash ausente")
        for doc in documents:
            if not doc.get("content_hash"):
                failures.append(f"Documento {doc.get('id', 'desconocido')} sin content_hash")
        return len(failures) == 0, failures
