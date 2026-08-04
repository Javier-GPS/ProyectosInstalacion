"""Fase 17 · Validación Industrial, Ensayos y Certificación

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE evidencelevel17 AS ENUM ('E0','E1','E2','E3','E4','E5')")
    op.execute("CREATE TYPE validationlevel17 AS ENUM ('V0','V1','V2','V3','V4','V5')")
    op.execute("CREATE TYPE criticalitylevel17 AS ENUM ('C1','C2','C3','C4','C5')")
    op.execute("CREATE TYPE testrunstate17 AS ENUM ('PENDING','RUNNING','PASSED','FAILED','BLOCKED','SKIPPED')")
    op.execute("CREATE TYPE ncmseverity17 AS ENUM ('S1','S2','S3','S4')")
    op.execute("CREATE TYPE gateid17 AS ENUM ('G17_1','G17_2','G17_3','G17_4','G17_5','G17_6','G17_7')")
    op.execute("CREATE TYPE gatestate17 AS ENUM ('OPEN','IN_REVIEW','PASSED','BLOCKED')")

    # ── validation_plans17 ─────────────────────────────────────────────────────
    op.create_table(
        "validation_plans17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, server_default="0.1"),
        sa.Column("validation_level", sa.String(4), nullable=False, server_default="V0"),
        sa.Column("scope", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("risks", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("acceptance_criteria", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("responsible", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_validation_plans17_project_id", "validation_plans17", ["project_id"])

    # ── requirement_traces17 ───────────────────────────────────────────────────
    op.create_table(
        "requirement_traces17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("validation_plans17.id", ondelete="CASCADE"), nullable=False),
        sa.Column("req_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("implementation_ref", sa.String(256), nullable=True),
        sa.Column("test_case_ref", sa.String(64), nullable=True),
        sa.Column("evidence_level", sa.String(4), nullable=False, server_default="E0"),
        sa.Column("criticality", sa.String(4), nullable=False, server_default="C1"),
        sa.Column("state", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("evidence_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_requirement_traces17_plan_id", "requirement_traces17", ["plan_id"])

    # ── test_cases17 ───────────────────────────────────────────────────────────
    op.create_table(
        "test_cases17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tc_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("criticality", sa.String(4), nullable=False, server_default="C1"),
        sa.Column("evidence_level_required", sa.String(4), nullable=False, server_default="E1"),
        sa.Column("inputs", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("reference_values", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("tolerance", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_golden", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("automated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("req_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_test_cases17_plan_id", "test_cases17", ["plan_id"])

    # ── test_runs17 ────────────────────────────────────────────────────────────
    op.create_table(
        "test_runs17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("test_cases17.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_state", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("environment", sa.String(128), nullable=True),
        sa.Column("commit_hash", sa.String(64), nullable=True),
        sa.Column("dataset_ref", sa.String(256), nullable=True),
        sa.Column("computed_values", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("error_codes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("logs", sa.Text, nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("duration_s", sa.Float, nullable=True),
        sa.Column("evidence_level", sa.String(4), nullable=False, server_default="E1"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("executed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_test_runs17_test_case_id", "test_runs17", ["test_case_id"])

    # ── physical_tests17 ───────────────────────────────────────────────────────
    op.create_table(
        "physical_tests17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("prototype_ref", sa.String(256), nullable=True),
        sa.Column("procedure_ref", sa.String(256), nullable=True),
        sa.Column("lab", sa.String(128), nullable=True),
        sa.Column("instrumentation", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("raw_datasets", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("processed_results", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("uncertainty_budget", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("evidence_level", sa.String(4), nullable=False, server_default="E3"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PLANNED"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_physical_tests17_plan_id", "physical_tests17", ["plan_id"])

    # ── calibration_records17 ──────────────────────────────────────────────────
    op.create_table(
        "calibration_records17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("physical_test_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("physical_tests17.id", ondelete="CASCADE"), nullable=False),
        sa.Column("equipment_id", sa.String(64), nullable=False),
        sa.Column("equipment_name", sa.String(256), nullable=False),
        sa.Column("certificate_ref", sa.String(256), nullable=True),
        sa.Column("calibrated_by", sa.String(128), nullable=True),
        sa.Column("measurement_range", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("uncertainty_k2", sa.Float, nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_calibration_records17_physical_test_id",
                    "calibration_records17", ["physical_test_id"])

    # ── correlation_results17 ──────────────────────────────────────────────────
    op.create_table(
        "correlation_results17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("physical_test_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("physical_tests17.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=False),
        sa.Column("n_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("e_rel_max", sa.Float, nullable=True),
        sa.Column("e_rel_mean", sa.Float, nullable=True),
        sa.Column("rmse", sa.Float, nullable=True),
        sa.Column("bias", sa.Float, nullable=True),
        sa.Column("model_factor", sa.Float, nullable=True),
        sa.Column("uncertainty_u", sa.Float, nullable=True),
        sa.Column("tolerance_target", sa.Float, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("decision", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("evidence_level", sa.String(4), nullable=False, server_default="E3"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_correlation_results17_physical_test_id",
                    "correlation_results17", ["physical_test_id"])

    # ── qualification_domains17 ────────────────────────────────────────────────
    op.create_table(
        "qualification_domains17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("family", sa.String(128), nullable=True),
        sa.Column("geometric_limits", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("material_limits", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("load_limits", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("process_limits", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("extension_rules", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_refs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("validation_level", sa.String(4), nullable=False, server_default="V0"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qualification_domains17_plan_id", "qualification_domains17", ["plan_id"])

    # ── nonconformities17 ─────────────────────────────────────────────────────
    op.create_table(
        "nonconformities17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ncm_id", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("severity", sa.String(4), nullable=False, server_default="S1"),
        sa.Column("affected_module", sa.String(64), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("containment", sa.Text, nullable=True),
        sa.Column("capa", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("blocks_gate", sa.String(8), nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_nonconformities17_plan_id", "nonconformities17", ["plan_id"])

    # ── release_gates17 ───────────────────────────────────────────────────────
    op.create_table(
        "release_gates17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("validation_plans17.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gate_id", sa.String(8), nullable=False),
        sa.Column("gate_state", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("required_evidences", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("provided_evidences", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("approvers", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("decision_by", sa.String(128), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocking_ncms", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_release_gates17_plan_id", "release_gates17", ["plan_id"])

    # ── certificate_evidences17 ────────────────────────────────────────────────
    op.create_table(
        "certificate_evidences17",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("gate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("release_gates17.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_ref", sa.String(256), nullable=False),
        sa.Column("issuer", sa.String(256), nullable=True),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("evidence_level", sa.String(4), nullable=False, server_default="E3"),
        sa.Column("verified_by", sa.String(128), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hash_sha256", sa.String(64), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_certificate_evidences17_gate_id",
                    "certificate_evidences17", ["gate_id"])


def downgrade() -> None:
    op.drop_table("certificate_evidences17")
    op.drop_table("release_gates17")
    op.drop_table("nonconformities17")
    op.drop_table("qualification_domains17")
    op.drop_table("correlation_results17")
    op.drop_table("calibration_records17")
    op.drop_table("physical_tests17")
    op.drop_table("test_runs17")
    op.drop_table("test_cases17")
    op.drop_table("requirement_traces17")
    op.drop_table("validation_plans17")

    op.execute("DROP TYPE IF EXISTS gatestate17")
    op.execute("DROP TYPE IF EXISTS gateid17")
    op.execute("DROP TYPE IF EXISTS ncmseverity17")
    op.execute("DROP TYPE IF EXISTS testrunstate17")
    op.execute("DROP TYPE IF EXISTS criticalitylevel17")
    op.execute("DROP TYPE IF EXISTS validationlevel17")
    op.execute("DROP TYPE IF EXISTS evidencelevel17")
