"""Fase 16: Catenarias y Alumbrado Suspendido (10 tablas, sufijo 16).

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Tipos enumerados ────────────────────────────────────────────────────
    op.execute("""
        CREATE TYPE cablesystemstate16 AS ENUM (
            'DRAFT', 'VALIDATED', 'ANALYZED', 'OPTIMIZED', 'RELEASED'
        )
    """)
    op.execute("""
        CREATE TYPE cabledatatype16 AS ENUM (
            'CONFIRMED', 'IMPORTED', 'CALCULATED', 'ESTIMATED',
            'CONSERVATIVE', 'PENDING', 'CONFLICT', 'MEASURED_AS_BUILT'
        )
    """)
    op.execute("""
        CREATE TYPE cabletypology16 AS ENUM (
            'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8'
        )
    """)
    op.execute("""
        CREATE TYPE tensioningmethod16 AS ENUM (
            'FORCE', 'SAG', 'CUT_LENGTH', 'MIN_CLEARANCE',
            'TENSOR_DISPLACEMENT', 'AS_BUILT'
        )
    """)
    op.execute("""
        CREATE TYPE cableanalysisstate16 AS ENUM (
            'PENDING', 'RUNNING', 'CONVERGED', 'FAILED', 'CANCELLED'
        )
    """)
    op.execute("""
        CREATE TYPE couplingstrategy16 AS ENUM (
            'MONOLITHIC', 'PARTITIONED', 'STIFFNESS_EQUIV', 'FIXED_SUPPORT'
        )
    """)
    op.execute("""
        CREATE TYPE anchortype16 AS ENUM (
            'COLUMN', 'FACADE', 'INDEPENDENT', 'EXTERNAL'
        )
    """)

    # ── cable_systems16 ─────────────────────────────────────────────────────
    op.create_table(
        "cable_systems16",
        sa.Column("id",            postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id",    postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name",          sa.String(200), nullable=False),
        sa.Column("description",   sa.Text),
        sa.Column("typology",      sa.String(4), nullable=False),
        sa.Column("state",         sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("max_cables",    sa.Integer, nullable=False, server_default="6"),
        sa.Column("location_data", postgresql.JSONB),
        sa.Column("geometry_hash", sa.String(64)),
        sa.Column("input_hash",    sa.String(64)),
        sa.Column("meta",          postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at",    sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by",    postgresql.UUID(as_uuid=True)),
    )

    # ── cable_lines16 ───────────────────────────────────────────────────────
    op.create_table(
        "cable_lines16",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("system_id",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_systems16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("code",         sa.String(50), nullable=False),
        sa.Column("material_id",  postgresql.UUID(as_uuid=True)),
        sa.Column("diameter_mm",  sa.Float, nullable=False),
        sa.Column("area_mm2",     sa.Float),
        sa.Column("e_mpa",        sa.Float, nullable=False),
        sa.Column("alpha_k",      sa.Float, nullable=False, server_default="0.000012"),
        sa.Column("mass_kg_m",    sa.Float, nullable=False),
        sa.Column("mbl_kn",       sa.Float, nullable=False),
        sa.Column("data_quality", sa.String(20), nullable=False, server_default="ESTIMATED"),
        sa.Column("meta",         postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── cable_anchors16 ─────────────────────────────────────────────────────
    op.create_table(
        "cable_anchors16",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("system_id",       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_systems16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("anchor_type",     sa.String(15), nullable=False),
        sa.Column("structure_id",    postgresql.UUID(as_uuid=True)),
        sa.Column("x_m",             sa.Float, nullable=False),
        sa.Column("y_m",             sa.Float, nullable=False),
        sa.Column("z_m",             sa.Float, nullable=False),
        sa.Column("stiffness_kn_m",  sa.Float),
        sa.Column("cables_attached", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reaction_fx_kn",  sa.Float),
        sa.Column("reaction_fy_kn",  sa.Float),
        sa.Column("reaction_fz_kn",  sa.Float),
        sa.Column("moment_mx_knm",   sa.Float),
        sa.Column("moment_my_knm",   sa.Float),
        sa.Column("moment_mz_knm",   sa.Float),
        sa.Column("data_quality",    sa.String(20), nullable=False, server_default="ESTIMATED"),
        sa.Column("meta",            postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── cable_spans16 ───────────────────────────────────────────────────────
    op.create_table(
        "cable_spans16",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("line_id",              postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_lines16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("span_index",           sa.Integer, nullable=False),
        sa.Column("anchor_a_id",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_anchors16.id"), nullable=False),
        sa.Column("anchor_b_id",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_anchors16.id"), nullable=False),
        sa.Column("length_m",             sa.Float, nullable=False),
        sa.Column("height_diff_m",        sa.Float, nullable=False, server_default="0"),
        sa.Column("distributed_load_n_m", sa.Float, nullable=False),
        sa.Column("point_loads",          postgresql.JSONB, server_default="[]"),
        sa.Column("sag_m",                sa.Float),
        sa.Column("tension_h_kn",         sa.Float),
        sa.Column("clearance_min_m",      sa.Float),
        sa.Column("data_quality",         sa.String(20), nullable=False, server_default="ESTIMATED"),
        sa.Column("meta",                 postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",           sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── suspended_items16 ───────────────────────────────────────────────────
    op.create_table(
        "suspended_items16",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("span_id",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_spans16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("label",        sa.String(100), nullable=False),
        sa.Column("item_type",    sa.String(30), nullable=False, server_default="LUMINAIRE"),
        sa.Column("position_m",   sa.Float, nullable=False),
        sa.Column("mass_kg",      sa.Float, nullable=False),
        sa.Column("wind_area_m2", sa.Float, nullable=False, server_default="0"),
        sa.Column("cd",           sa.Float, nullable=False, server_default="1.2"),
        sa.Column("luminaire_id", postgresql.UUID(as_uuid=True)),
        sa.Column("data_quality", sa.String(20), nullable=False, server_default="ESTIMATED"),
        sa.Column("meta",         postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── tensioning_plans16 ──────────────────────────────────────────────────
    op.create_table(
        "tensioning_plans16",
        sa.Column("id",                postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("system_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_systems16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("method",            sa.String(25), nullable=False),
        sa.Column("target_value",      sa.Float, nullable=False),
        sa.Column("target_unit",       sa.String(5), nullable=False, server_default="kN"),
        sa.Column("tolerance_pct",     sa.Float, nullable=False, server_default="2"),
        sa.Column("t_install_c",       sa.Float, nullable=False, server_default="15"),
        sa.Column("tensor_stroke_mm",  sa.Float),
        sa.Column("sequence",          postgresql.JSONB, server_default="[]"),
        sa.Column("cut_length_m",      sa.Float),
        sa.Column("approved",          sa.Boolean, nullable=False, server_default="false"),
        sa.Column("meta",              postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── cable_states16 ──────────────────────────────────────────────────────
    op.create_table(
        "cable_states16",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("system_id",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_systems16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("label",            sa.String(100), nullable=False),
        sa.Column("combination_type", sa.String(10), nullable=False, server_default="ELS"),
        sa.Column("temperature_c",    sa.Float, nullable=False),
        sa.Column("wind_speed_ms",    sa.Float, nullable=False, server_default="0"),
        sa.Column("wind_angle_deg",   sa.Float, nullable=False, server_default="0"),
        sa.Column("ice_load_n_m",     sa.Float, nullable=False, server_default="0"),
        sa.Column("snow_load_kpa",    sa.Float, nullable=False, server_default="0"),
        sa.Column("accidental_code",  sa.String(5)),
        sa.Column("accidental_data",  postgresql.JSONB, server_default="{}"),
        sa.Column("is_governing",     sa.Boolean, nullable=False, server_default="false"),
        sa.Column("meta",             postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",       sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── cable_analysis_runs16 ───────────────────────────────────────────────
    op.create_table(
        "cable_analysis_runs16",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("system_id",           postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_systems16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("state_id",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_states16.id"), index=True),
        sa.Column("solver_version",      sa.String(30), nullable=False,
                  server_default="newton_raphson_v1"),
        sa.Column("coupling_strategy",   sa.String(20), nullable=False,
                  server_default="PARTITIONED"),
        sa.Column("max_iterations",      sa.Integer, nullable=False, server_default="200"),
        sa.Column("tol_residual",        sa.Float, nullable=False, server_default="1e-6"),
        sa.Column("tol_displacement",    sa.Float, nullable=False, server_default="1e-7"),
        sa.Column("tol_reaction",        sa.Float, nullable=False, server_default="1e-5"),
        sa.Column("iterations_used",     sa.Integer),
        sa.Column("residual_final",      sa.Float),
        sa.Column("displacement_final",  sa.Float),
        sa.Column("converged",           sa.Boolean),
        sa.Column("run_state",           sa.String(15), nullable=False, server_default="PENDING"),
        sa.Column("error_code",          sa.String(20)),
        sa.Column("error_detail",        sa.Text),
        sa.Column("input_hash",          sa.String(64)),
        sa.Column("output_hash",         sa.String(64)),
        sa.Column("duration_s",          sa.Float),
        sa.Column("meta",                postgresql.JSONB, server_default="{}"),
        sa.Column("started_at",          sa.DateTime(timezone=True)),
        sa.Column("finished_at",         sa.DateTime(timezone=True)),
        sa.Column("created_at",          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── cable_results16 ─────────────────────────────────────────────────────
    op.create_table(
        "cable_results16",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id",               postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_analysis_runs16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("span_id",              postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_spans16.id"), index=True),
        sa.Column("anchor_id",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_anchors16.id"), index=True),
        sa.Column("tension_h_kn",         sa.Float),
        sa.Column("tension_max_kn",       sa.Float),
        sa.Column("sag_m",                sa.Float),
        sa.Column("clearance_min_m",      sa.Float),
        sa.Column("cable_length_m",       sa.Float),
        sa.Column("reaction_fx_kn",       sa.Float),
        sa.Column("reaction_fy_kn",       sa.Float),
        sa.Column("reaction_fz_kn",       sa.Float),
        sa.Column("moment_mx_knm",        sa.Float),
        sa.Column("moment_my_knm",        sa.Float),
        sa.Column("moment_mz_knm",        sa.Float),
        sa.Column("utilization_strength", sa.Float),
        sa.Column("utilization_clearance", sa.Float),
        sa.Column("checks_passed",        sa.Boolean),
        sa.Column("error_codes",          postgresql.JSONB, server_default="[]"),
        sa.Column("detail",               postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",           sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── cable_as_builts16 ───────────────────────────────────────────────────
    op.create_table(
        "cable_as_builts16",
        sa.Column("id",                      postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("system_id",               postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_systems16.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("span_id",                 postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cable_spans16.id"), index=True),
        sa.Column("measured_at",             sa.DateTime(timezone=True), nullable=False),
        sa.Column("technician",              sa.String(100), nullable=False),
        sa.Column("t_measure_c",             sa.Float, nullable=False),
        sa.Column("method",                  sa.String(30), nullable=False),
        sa.Column("sag_measured_m",          sa.Float),
        sa.Column("tension_measured_kn",     sa.Float),
        sa.Column("clearance_measured_m",    sa.Float),
        sa.Column("uncertainty_m",           sa.Float),
        sa.Column("deviation_from_plan_pct", sa.Float),
        sa.Column("accepted",                sa.Boolean),
        sa.Column("comments",                sa.Text),
        sa.Column("evidence",                postgresql.JSONB, server_default="{}"),
        sa.Column("created_at",              sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cable_as_builts16")
    op.drop_table("cable_results16")
    op.drop_table("cable_analysis_runs16")
    op.drop_table("cable_states16")
    op.drop_table("tensioning_plans16")
    op.drop_table("suspended_items16")
    op.drop_table("cable_spans16")
    op.drop_table("cable_anchors16")
    op.drop_table("cable_lines16")
    op.drop_table("cable_systems16")

    for t in [
        "anchortype16", "couplingstrategy16", "cableanalysisstate16",
        "tensioningmethod16", "cabletypology16", "cabledatatype16",
        "cablesystemstate16",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {t}")
