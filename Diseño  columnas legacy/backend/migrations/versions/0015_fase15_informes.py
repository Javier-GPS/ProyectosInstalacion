"""Fase 15: Informes, Validacion Documental y Liberacion

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums con sufijo 15 ───────────────────────────────────────────────────
    maturitystate15 = postgresql.ENUM(
        "DRAFT", "PREDIM", "CALC_INTERNO", "VALIDADO_OT", "LIBERADO",
        name="maturitystate15", create_type=True
    )
    releasegate15 = postgresql.ENUM(
        "G0", "G1", "G2", "G3", "G4", "G5", "G6",
        name="releasegate15", create_type=True
    )
    docpurpose15 = postgresql.ENUM(
        "PKG_COM", "PKG_CLI", "PKG_CAL", "PKG_PRD",
        "PKG_SUB", "PKG_SIT", "PKG_QA", "PKG_REG", "PKG_SRV",
        name="docpurpose15", create_type=True
    )
    validationseverity15 = postgresql.ENUM(
        "BLOQUEANTE", "GRAVE", "ADVERTENCIA", "INFO",
        name="validationseverity15", create_type=True
    )
    reviewdecision15 = postgresql.ENUM(
        "APPROVED", "REJECTED", "ABSTAINED", "REQUESTED_CHANGES",
        name="reviewdecision15", create_type=True
    )
    authoringmode15 = postgresql.ENUM(
        "DETERMINISTA", "PLANTILLA", "IA_REVISADA", "COMENTARIO_HUMANO",
        name="authoringmode15", create_type=True
    )
    approvalstate15 = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED", "EXPIRED",
        name="approvalstate15", create_type=True
    )
    distributionstate15 = postgresql.ENUM(
        "PENDING", "SENT", "ACCEPTED", "REVOKED", "EXPIRED",
        name="distributionstate15", create_type=True
    )
    changekind15 = postgresql.ENUM(
        "IDENTIDAD", "ENTRADA_TECNICA", "REGLA_NORMATIVA", "RESULTADO",
        "INDUSTRIAL", "EDITORIAL", "TRADUCCION", "PERMISO",
        name="changekind15", create_type=True
    )
    authlevel15 = postgresql.ENUM(
        "A0", "A1", "A2", "A3", "A4",
        name="authlevel15", create_type=True
    )
    distributionchannel15 = postgresql.ENUM(
        "PORTAL_CLIENTE", "PORTAL_PROVEEDOR", "ERP",
        "CORREO_SEGURO", "EXPORTACION_OFFLINE", "API",
        name="distributionchannel15", create_type=True
    )

    for enum_type in [
        maturitystate15, releasegate15, docpurpose15,
        validationseverity15, reviewdecision15, authoringmode15,
        approvalstate15, distributionstate15, changekind15,
        authlevel15, distributionchannel15,
    ]:
        enum_type.create(op.get_bind(), checkfirst=True)

    # ── release_snapshots15 ───────────────────────────────────────────────────
    op.create_table(
        "release_snapshots15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.String(20), nullable=False),
        sa.Column("maturity", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("gate_passed", sa.String(5), nullable=True),
        sa.Column("product_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("analysis_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("library_set_hash", sa.String(64), nullable=True),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("cad_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("signature_hash", sa.String(128), nullable=True),
        sa.Column("auth_level", sa.String(5), nullable=False, server_default="A0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["supersedes_id"], ["release_snapshots15.id"]),
    )
    op.create_index("ix_release_snapshots15_project_id", "release_snapshots15", ["project_id"])

    # ── document_templates15 ──────────────────────────────────────────────────
    op.create_table(
        "document_templates15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_code", sa.String(40), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False, server_default="es"),
        sa.Column("market", sa.String(40), nullable=False, server_default="EU"),
        sa.Column("allowed_maturity", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("data_bindings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("inclusion_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("format_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("visibility_policies", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("render_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approval_state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("template_hash", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("template_code", "version", "locale", name="uq_template_version_locale15"),
    )
    op.create_index("ix_document_templates15_code", "document_templates15", ["template_code"])

    # ── document_instances15 ──────────────────────────────────────────────────
    op.create_table(
        "document_instances15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("release_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False, server_default="es"),
        sa.Column("recipient_role", sa.String(60), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("lineage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("render_qa_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("accessibility_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pdf_a_compliant", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("has_manual_edits", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_snapshot_id"], ["release_snapshots15.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["document_templates15.id"]),
    )
    op.create_index("ix_document_instances15_release", "document_instances15", ["release_snapshot_id"])

    # ── validation_runs15 ─────────────────────────────────────────────────────
    op.create_table(
        "validation_runs15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("release_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gate", sa.String(5), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("blocking_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grave_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("advertencia_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("run_hash", sa.String(64), nullable=True),
        sa.Column("run_by", sa.String(120), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_snapshot_id"], ["release_snapshots15.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_validation_runs15_release", "validation_runs15", ["release_snapshot_id"])

    # ── review_tasks15 ────────────────────────────────────────────────────────
    op.create_table(
        "review_tasks15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("release_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to", sa.String(120), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision", sa.String(30), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("open_items_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_snapshot_id"], ["release_snapshots15.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_review_tasks15_release", "review_tasks15", ["release_snapshot_id"])

    # ── review_comments15 ─────────────────────────────────────────────────────
    op.create_table(
        "review_comments15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author", sa.String(120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("target_section", sa.String(120), nullable=True),
        sa.Column("is_blocking", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_by", sa.String(120), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["review_task_id"], ["review_tasks15.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_review_comments15_task", "review_comments15", ["review_task_id"])

    # ── approval_records15 ────────────────────────────────────────────────────
    op.create_table(
        "approval_records15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("release_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver", sa.String(120), nullable=False),
        sa.Column("role", sa.String(60), nullable=False),
        sa.Column("gate", sa.String(5), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("auth_level", sa.String(5), nullable=False, server_default="A1"),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_snapshot_id"], ["release_snapshots15.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_approval_records15_release", "approval_records15", ["release_snapshot_id"])

    # ── distribution_records15 ────────────────────────────────────────────────
    op.create_table(
        "distribution_records15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("release_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient", sa.String(120), nullable=False),
        sa.Column("recipient_role", sa.String(60), nullable=True),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("can_download", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("can_print", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("can_forward", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("requires_acceptance", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("watermark", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("package_hash", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_snapshot_id"], ["release_snapshots15.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_distribution_records15_release", "distribution_records15", ["release_snapshot_id"])

    # ── change_sets15 ─────────────────────────────────────────────────────────
    op.create_table(
        "change_sets15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("blocking_changes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("technical_changes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("editorial_changes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("docs_to_regenerate", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approvals_invalidated", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recipients_notified", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("computed_by", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(["from_release_id"], ["release_snapshots15.id"]),
        sa.ForeignKeyConstraint(["to_release_id"], ["release_snapshots15.id"]),
    )
    op.create_index("ix_change_sets15_project", "change_sets15", ["project_id"])

    # ── ai_generation_records15 ───────────────────────────────────────────────
    op.create_table(
        "ai_generation_records15",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", sa.String(80), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("generated_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="es"),
        sa.Column("model_version", sa.String(60), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("accepted_by", sa.String(120), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_instance_id"], ["document_instances15.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ai_generation_records15_doc", "ai_generation_records15", ["document_instance_id"])


def downgrade() -> None:
    op.drop_table("ai_generation_records15")
    op.drop_table("change_sets15")
    op.drop_table("distribution_records15")
    op.drop_table("approval_records15")
    op.drop_table("review_comments15")
    op.drop_table("review_tasks15")
    op.drop_table("validation_runs15")
    op.drop_table("document_instances15")
    op.drop_table("document_templates15")
    op.drop_table("release_snapshots15")

    for enum_name in [
        "distributionchannel15", "authlevel15", "changekind15",
        "distributionstate15", "approvalstate15", "authoringmode15",
        "reviewdecision15", "validationseverity15", "docpurpose15",
        "releasegate15", "maturitystate15",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
