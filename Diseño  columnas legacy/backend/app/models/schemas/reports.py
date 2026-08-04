"""
Salvi Studio · Columns — Schemas Pydantic v2 Fase 15
Informes, Validación Documental y Liberación.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Constantes de validación ─────────────────────────────────────────────────

VALID_MATURITY_STATES = {"DRAFT", "PREDIM", "CALC_INTERNO", "VALIDADO_OT", "LIBERADO"}
VALID_GATES = {"G0", "G1", "G2", "G3", "G4", "G5", "G6"}
VALID_DOC_PURPOSES = {
    "PKG_COM", "PKG_CLI", "PKG_CAL", "PKG_PRD",
    "PKG_SUB", "PKG_SIT", "PKG_QA", "PKG_REG", "PKG_SRV",
}
VALID_SEVERITIES = {"BLOQUEANTE", "GRAVE", "ADVERTENCIA", "INFO"}
VALID_REVIEW_DECISIONS = {"APPROVED", "REJECTED", "ABSTAINED", "REQUESTED_CHANGES"}
VALID_AUTHORING_MODES = {"DETERMINISTA", "PLANTILLA", "IA_REVISADA", "COMENTARIO_HUMANO"}
VALID_APPROVAL_STATES = {"PENDING", "APPROVED", "REJECTED", "EXPIRED"}
VALID_DISTRIBUTION_STATES = {"PENDING", "SENT", "ACCEPTED", "REVOKED", "EXPIRED"}
VALID_CHANGE_KINDS = {
    "IDENTIDAD", "ENTRADA_TECNICA", "REGLA_NORMATIVA", "RESULTADO",
    "INDUSTRIAL", "EDITORIAL", "TRADUCCION", "PERMISO",
}
VALID_AUTH_LEVELS = {"A0", "A1", "A2", "A3", "A4"}
VALID_DISTRIBUTION_CHANNELS = {
    "PORTAL_CLIENTE", "PORTAL_PROVEEDOR", "ERP",
    "CORREO_SEGURO", "EXPORTACION_OFFLINE", "API",
}


# ── ValidationCheck ───────────────────────────────────────────────────────────

class ValidationCheck(BaseModel):
    code: str
    severity: str
    message: str
    passed: bool
    entity: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(f"severity debe ser uno de {VALID_SEVERITIES}")
        return v


class ValidationReport(BaseModel):
    checks: List[ValidationCheck] = Field(default_factory=list)
    gate: str
    passed: bool

    @property
    def blocking(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.severity == "BLOQUEANTE"]

    @property
    def errors(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.severity in ("BLOQUEANTE", "GRAVE")]

    @property
    def warnings(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.severity == "ADVERTENCIA"]


# ── ReleaseSnapshot ───────────────────────────────────────────────────────────

class ReleaseCreate(BaseModel):
    project_id: uuid.UUID
    revision: str = Field(..., min_length=1, max_length=20)
    product_snapshot_hash: Optional[str] = None
    analysis_snapshot_hash: Optional[str] = None
    library_set_hash: Optional[str] = None
    geometry_hash: Optional[str] = None
    cad_snapshot_hash: Optional[str] = None
    created_by: str


class ReleaseOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    revision: str
    maturity: str
    gate_passed: Optional[str]
    product_snapshot_hash: Optional[str]
    analysis_snapshot_hash: Optional[str]
    library_set_hash: Optional[str]
    geometry_hash: Optional[str]
    cad_snapshot_hash: Optional[str]
    manifest: Optional[dict]
    signature_hash: Optional[str]
    auth_level: str
    published_at: Optional[datetime]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    supersedes_id: Optional[uuid.UUID]
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Validation ────────────────────────────────────────────────────────────────

class ValidationRequest(BaseModel):
    release_id: uuid.UUID
    gate: str
    run_by: str

    @field_validator("gate")
    @classmethod
    def validate_gate(cls, v: str) -> str:
        if v not in VALID_GATES:
            raise ValueError(f"gate debe ser uno de {VALID_GATES}")
        return v


class ValidationRunOut(BaseModel):
    id: uuid.UUID
    release_snapshot_id: uuid.UUID
    gate: str
    checks: Optional[List[dict]]
    blocking_count: int
    grave_count: int
    advertencia_count: int
    passed: bool
    run_hash: Optional[str]
    run_by: str
    run_at: datetime

    model_config = {"from_attributes": True}


# ── Documents ─────────────────────────────────────────────────────────────────

class DocumentComposeRequest(BaseModel):
    release_id: uuid.UUID
    template_id: uuid.UUID
    purpose: str
    locale: str = "es"
    recipient_role: Optional[str] = None
    created_by: str

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        if v not in VALID_DOC_PURPOSES:
            raise ValueError(f"purpose debe ser uno de {VALID_DOC_PURPOSES}")
        return v


class DocumentInstanceOut(BaseModel):
    id: uuid.UUID
    release_snapshot_id: uuid.UUID
    template_id: uuid.UUID
    purpose: str
    locale: str
    recipient_role: Optional[str]
    content_hash: Optional[str]
    render_qa_passed: bool
    accessibility_passed: bool
    pdf_a_compliant: bool
    is_blocked: bool
    block_reason: Optional[str]
    has_manual_edits: bool
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── DocumentTemplate ──────────────────────────────────────────────────────────

class DocumentTemplateCreate(BaseModel):
    template_code: str = Field(..., min_length=1, max_length=40)
    version: str = Field(..., min_length=1, max_length=20)
    purpose: str
    locale: str = "es"
    market: str = "EU"
    allowed_maturity: Optional[List[str]] = None
    sections: Optional[List[dict]] = None
    data_bindings: Optional[List[dict]] = None
    inclusion_rules: Optional[List[dict]] = None
    format_rules: Optional[List[dict]] = None
    visibility_policies: Optional[List[dict]] = None
    validation_rules: Optional[List[dict]] = None
    render_policy: Optional[dict] = None
    created_by: str

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        if v not in VALID_DOC_PURPOSES:
            raise ValueError(f"purpose debe ser uno de {VALID_DOC_PURPOSES}")
        return v


class DocumentTemplateOut(BaseModel):
    id: uuid.UUID
    template_code: str
    version: str
    purpose: str
    locale: str
    market: str
    approval_state: str
    template_hash: Optional[str]
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── ReviewTask ────────────────────────────────────────────────────────────────

class ReviewTaskCreate(BaseModel):
    release_id: uuid.UUID
    assigned_to: str
    scope: Optional[str] = None
    checklist: Optional[List[dict]] = None
    created_by: str


class ReviewDecisionRequest(BaseModel):
    review_id: uuid.UUID
    decision: str
    decision_notes: Optional[str] = None
    decided_by: str

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        if v not in VALID_REVIEW_DECISIONS:
            raise ValueError(f"decision debe ser uno de {VALID_REVIEW_DECISIONS}")
        return v


class ReviewTaskOut(BaseModel):
    id: uuid.UUID
    release_snapshot_id: uuid.UUID
    assigned_to: str
    scope: Optional[str]
    decision: Optional[str]
    decision_at: Optional[datetime]
    decision_notes: Optional[str]
    open_items_count: int
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewCommentCreate(BaseModel):
    review_task_id: uuid.UUID
    author: str
    text: str
    target_section: Optional[str] = None
    is_blocking: bool = False


class ReviewCommentOut(BaseModel):
    id: uuid.UUID
    review_task_id: uuid.UUID
    author: str
    text: str
    target_section: Optional[str]
    is_blocking: bool
    resolved: bool
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Approval ──────────────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    release_id: uuid.UUID
    approver: str
    role: str
    gate: str
    auth_level: str = "A1"
    mfa_verified: bool = False
    notes: Optional[str] = None

    @field_validator("gate")
    @classmethod
    def validate_gate(cls, v: str) -> str:
        if v not in VALID_GATES:
            raise ValueError(f"gate debe ser uno de {VALID_GATES}")
        return v

    @field_validator("auth_level")
    @classmethod
    def validate_auth_level(cls, v: str) -> str:
        if v not in VALID_AUTH_LEVELS:
            raise ValueError(f"auth_level debe ser uno de {VALID_AUTH_LEVELS}")
        return v


class ApprovalRecordOut(BaseModel):
    id: uuid.UUID
    release_snapshot_id: uuid.UUID
    approver: str
    role: str
    gate: str
    state: str
    decision_at: Optional[datetime]
    notes: Optional[str]
    auth_level: str
    mfa_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Distribution ──────────────────────────────────────────────────────────────

class DistributionRequest(BaseModel):
    release_id: uuid.UUID
    recipient: str
    recipient_role: Optional[str] = None
    purpose: str
    channel: str
    expires_at: Optional[datetime] = None
    can_download: bool = True
    can_print: bool = False
    can_forward: bool = False
    requires_acceptance: bool = False
    watermark: bool = False
    created_by: str

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        if v not in VALID_DOC_PURPOSES:
            raise ValueError(f"purpose debe ser uno de {VALID_DOC_PURPOSES}")
        return v

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in VALID_DISTRIBUTION_CHANNELS:
            raise ValueError(f"channel debe ser uno de {VALID_DISTRIBUTION_CHANNELS}")
        return v


class DistributionRecordOut(BaseModel):
    id: uuid.UUID
    release_snapshot_id: uuid.UUID
    recipient: str
    recipient_role: Optional[str]
    purpose: str
    channel: str
    state: str
    expires_at: Optional[datetime]
    can_download: bool
    can_print: bool
    can_forward: bool
    requires_acceptance: bool
    watermark: bool
    sent_at: Optional[datetime]
    accepted_at: Optional[datetime]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    package_hash: Optional[str]
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Publish / Revoke ──────────────────────────────────────────────────────────

class PublishRequest(BaseModel):
    release_id: uuid.UUID
    auth_level: str = "A2"
    signature_hash: Optional[str] = None
    published_by: str

    @field_validator("auth_level")
    @classmethod
    def validate_auth_level(cls, v: str) -> str:
        if v not in VALID_AUTH_LEVELS:
            raise ValueError(f"auth_level debe ser uno de {VALID_AUTH_LEVELS}")
        return v


class RevokeRequest(BaseModel):
    release_id: uuid.UUID
    reason: str = Field(..., min_length=5)
    revoked_by: str
    notify_recipients: bool = True


class RevokeResult(BaseModel):
    release_id: uuid.UUID
    revoked: bool
    recipients_notified: int
    new_maturity: str


# ── Manifest ──────────────────────────────────────────────────────────────────

class ManifestOut(BaseModel):
    release_id: uuid.UUID
    project_id: uuid.UUID
    revision: str
    maturity: str
    product_snapshot_hash: Optional[str]
    analysis_snapshot_hash: Optional[str]
    library_set_hash: Optional[str]
    documents: List[dict] = Field(default_factory=list)
    evidence: List[dict] = Field(default_factory=list)
    approvals: List[dict] = Field(default_factory=list)
    validations: List[dict] = Field(default_factory=list)
    distribution_policy: Optional[dict] = None
    created_at: datetime
    published_at: Optional[datetime]
    supersedes: Optional[uuid.UUID]
    signature: Optional[str]


# ── SemanticDiff ──────────────────────────────────────────────────────────────

class ChangeItem(BaseModel):
    kind: str
    path: str
    from_value: Any = None
    to_value: Any = None
    criticality: str  # BLOQUEANTE / GRAVE / ADVERTENCIA / INFO
    affected_docs: List[str] = Field(default_factory=list)
    affected_approvals: List[str] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in VALID_CHANGE_KINDS:
            raise ValueError(f"kind debe ser uno de {VALID_CHANGE_KINDS}")
        return v


class DiffResult(BaseModel):
    from_release_id: uuid.UUID
    to_release_id: uuid.UUID
    changes: List[ChangeItem] = Field(default_factory=list)
    blocking_changes: int = 0
    technical_changes: int = 0
    editorial_changes: int = 0
    docs_to_regenerate: List[str] = Field(default_factory=list)
    approvals_invalidated: List[str] = Field(default_factory=list)
    recipients_notified: List[str] = Field(default_factory=list)


class ChangeSetOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    from_release_id: uuid.UUID
    to_release_id: uuid.UUID
    changes: Optional[List[dict]]
    blocking_changes: int
    technical_changes: int
    editorial_changes: int
    docs_to_regenerate: Optional[List[str]]
    approvals_invalidated: Optional[List[str]]
    recipients_notified: Optional[List[str]]
    computed_at: datetime
    computed_by: str

    model_config = {"from_attributes": True}


# ── AI Generation ─────────────────────────────────────────────────────────────

class AiGenerationCreate(BaseModel):
    document_instance_id: uuid.UUID
    section_id: str
    generated_text: str
    language: str = "es"
    model_version: Optional[str] = None
    prompt_hash: Optional[str] = None


class AiAcceptRequest(BaseModel):
    generation_id: uuid.UUID
    accepted: bool
    accepted_by: str
    rejection_reason: Optional[str] = None


class AiGenerationRecordOut(BaseModel):
    id: uuid.UUID
    document_instance_id: uuid.UUID
    section_id: str
    generated_text: str
    language: str
    model_version: Optional[str]
    accepted: bool
    accepted_by: Optional[str]
    accepted_at: Optional[datetime]
    rejection_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Lineage ───────────────────────────────────────────────────────────────────

class LineageField(BaseModel):
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

    @field_validator("authoring_mode")
    @classmethod
    def validate_authoring_mode(cls, v: str) -> str:
        if v not in VALID_AUTHORING_MODES:
            raise ValueError(f"authoring_mode debe ser uno de {VALID_AUTHORING_MODES}")
        return v
