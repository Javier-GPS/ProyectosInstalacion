"""Fase 13 · Optimización Multiobjetivo y Diseño Especial

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision    = "0013"
down_revision = "0012"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    variabletype13 = postgresql.ENUM(
        "CONTINUOUS", "DISCRETE", "CATEGORICAL", "BOOLEAN", "DERIVED", "DEPENDENT",
        name="variabletype13", create_type=True,
    )
    variablemode13 = postgresql.ENUM(
        "FIXED", "SELECTABLE", "OPTIMIZABLE", "DERIVED",
        name="variablemode13", create_type=True,
    )
    constraintclass13 = postgresql.ENUM(
        "NORMATIVA", "DOMINIO", "GEOMETRICA", "FABRICACION",
        "TRANSPORTE_MONTAJE", "COMERCIAL", "SOSTENIBILIDAD", "ROBUSTEZ",
        name="constraintclass13", create_type=True,
    )
    constraintseverity13 = postgresql.ENUM(
        "HARD", "SOFT", "WARNING",
        name="constraintseverity13", create_type=True,
    )
    candidatestatus13 = postgresql.ENUM(
        "PENDING", "EVALUATING", "VALID", "REJECTED", "DOMINATED", "SELECTED",
        name="candidatestatus13", create_type=True,
    )
    optimizationrunstatus13 = postgresql.ENUM(
        "DRAFT", "RUNNING", "PAUSED", "COMPLETED", "CANCELLED", "FAILED",
        name="optimizationrunstatus13", create_type=True,
    )
    objectivedirection13 = postgresql.ENUM(
        "MINIMIZE", "MAXIMIZE",
        name="objectivedirection13", create_type=True,
    )
    robustnessmethod13 = postgresql.ENUM(
        "DISCRETE_SCENARIOS", "INTERVALS", "LATIN_HYPERCUBE",
        "MONTE_CARLO", "ROBUST_OPTIMIZATION", "WORST_CASE",
        name="robustnessmethod13", create_type=True,
    )
    interviewstate13 = postgresql.ENUM(
        "NEW", "DISCOVERY", "ELICITATION", "CLARIFICATION",
        "REVIEW", "CONFIRMED", "BLOCKED", "READY",
        name="interviewstate13", create_type=True,
    )
    questionpriority13 = postgresql.ENUM(
        "P0", "P1", "P2", "P3", "DERIVABLE",
        name="questionpriority13", create_type=True,
    )
    fielddatastatus13 = postgresql.ENUM(
        "EXACT", "ESTIMATED", "RANGE", "UNKNOWN", "CONFLICT", "PENDING_CONFIRMATION",
        name="fielddatastatus13", create_type=True,
    )
    interviewrole13 = postgresql.ENUM(
        "USER", "ASSISTANT", "SYSTEM",
        name="interviewrole13", create_type=True,
    )

    for enum in [
        variabletype13, variablemode13, constraintclass13, constraintseverity13,
        candidatestatus13, optimizationrunstatus13, objectivedirection13,
        robustnessmethod13, interviewstate13, questionpriority13,
        fielddatastatus13, interviewrole13,
    ]:
        enum.create(op.get_bind(), checkfirst=True)

    # ── optimization_profile ───────────────────────────────────────────────────
    op.create_table(
        "optimization_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("user_role", sa.String(60), nullable=False),
        sa.Column("defaults", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("limits", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("published_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── optimization_run ───────────────────────────────────────────────────────
    op.create_table(
        "optimization_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_profile.id"), nullable=True),
        sa.Column("objectives", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("algorithm_config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("algorithm_version", sa.String(40), nullable=False, server_default="1.0.0"),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("run_hash", sa.String(64), nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pareto_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_evaluations", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("elapsed_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_optimization_run_status", "optimization_run", ["status"])
    op.create_index("ix_optimization_run_project", "optimization_run", ["project_revision_id"])

    # ── design_variable ────────────────────────────────────────────────────────
    op.create_table(
        "design_variable",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("variable_type", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("domain", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("dependency_expr", sa.Text(), nullable=True),
        sa.Column("source", sa.String(60), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "name", name="uq_design_variable_run_name"),
    )

    # ── constraint_definition ──────────────────────────────────────────────────
    op.create_table(
        "constraint_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("constraint_class", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="HARD"),
        sa.Column("evaluator", sa.String(120), nullable=True),
        sa.Column("limit_value", postgresql.JSONB(), nullable=True),
        sa.Column("normative_reference", sa.String(120), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "code", name="uq_constraint_def_run_code"),
    )

    # ── objective_definition ───────────────────────────────────────────────────
    op.create_table(
        "objective_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("normalization", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("direction", sa.String(20), nullable=False, server_default="MINIMIZE"),
        sa.Column("scope", sa.String(60), nullable=True),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "code", name="uq_objective_def_run_code"),
    )

    # ── candidate_design ───────────────────────────────────────────────────────
    op.create_table(
        "candidate_design",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidate_design.id", ondelete="SET NULL"), nullable=True),
        sa.Column("variables", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("candidate_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("rejection_code", sa.String(60), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_candidate_design_run_status", "candidate_design", ["run_id", "status"])
    op.create_index("ix_candidate_design_hash", "candidate_design", ["candidate_hash"])

    # ── candidate_evaluation ───────────────────────────────────────────────────
    op.create_table(
        "candidate_evaluation_13",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidate_design.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("solver_run_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("utilizations", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("objective_values", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("constraint_results", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("cost_eur", sa.Float(), nullable=True),
        sa.Column("mass_kg", sa.Float(), nullable=True),
        sa.Column("co2_kg", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── pareto_alternative ─────────────────────────────────────────────────────
    op.create_table(
        "pareto_alternative",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidate_design.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("dominance_rank", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("crowding_distance", sa.Float(), nullable=True),
        sa.Column("label", sa.String(60), nullable=True),
        sa.Column("selected_reason", sa.Text(), nullable=True),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pareto_alternative_run", "pareto_alternative", ["run_id"])

    # ── robustness_scenario ────────────────────────────────────────────────────
    op.create_table(
        "robustness_scenario",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidate_design.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uncertain_variables", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("method", sa.String(30), nullable=False, server_default="DISCRETE_SCENARIOS"),
        sa.Column("samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sensitivity", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── cost_snapshot ──────────────────────────────────────────────────────────
    op.create_table(
        "cost_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidate_design.id", ondelete="SET NULL"), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_versions", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("components", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("total_eur", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── carbon_snapshot ────────────────────────────────────────────────────────
    op.create_table(
        "carbon_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidate_design.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scope", sa.String(30), nullable=False, server_default="A1-A3"),
        sa.Column("factors", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("geography", sa.String(10), nullable=True),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("total_kgco2e", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── design_interview ───────────────────────────────────────────────────────
    op.create_table(
        "design_interview",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="es"),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── interview_message ──────────────────────────────────────────────────────
    op.create_table(
        "interview_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("design_interview.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(15), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("extra_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_interview_message_interview", "interview_message", ["interview_id"])

    # ── extracted_field ────────────────────────────────────────────────────────
    op.create_table(
        "extracted_field",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("design_interview.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_path", sa.String(200), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=True),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_CONFIRMATION"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("criticality", sa.String(20), nullable=True),
        sa.Column("source", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("interpretation", sa.Text(), nullable=True),
        sa.Column("uncertainty", postgresql.JSONB(), nullable=True),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parser_version", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("interview_id", "field_path", name="uq_extracted_field_interview_path"),
    )

    # ── question_template ──────────────────────────────────────────────────────
    op.create_table(
        "question_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", sa.String(60), nullable=False, unique=True),
        sa.Column("target_fields", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("preconditions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("skip_condition", sa.Text(), nullable=True),
        sa.Column("criticality", sa.String(10), nullable=False, server_default="P2"),
        sa.Column("allowed_answer_types", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("examples", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("validation_rules", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("clarification_policy", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("completion_rule", sa.Text(), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("question_template")
    op.drop_table("extracted_field")
    op.drop_table("interview_message")
    op.drop_table("design_interview")
    op.drop_table("carbon_snapshot")
    op.drop_table("cost_snapshot")
    op.drop_table("robustness_scenario")
    op.drop_table("pareto_alternative")
    op.drop_table("candidate_evaluation_13")
    op.drop_table("candidate_design")
    op.drop_table("objective_definition")
    op.drop_table("constraint_definition")
    op.drop_table("design_variable")
    op.drop_table("optimization_run")
    op.drop_table("optimization_profile")

    for enum_name in [
        "variabletype13", "variablemode13", "constraintclass13", "constraintseverity13",
        "candidatestatus13", "optimizationrunstatus13", "objectivedirection13",
        "robustnessmethod13", "interviewstate13", "questionpriority13",
        "fielddatastatus13", "interviewrole13",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
