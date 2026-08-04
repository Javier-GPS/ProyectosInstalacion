"""Fase 4: Motor Estructural Común — tablas y enums

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# ── Enums a crear ─────────────────────────────────────────────────────────────
ENUMS = [
    ("element_type",
     ["BEAM3D_VAR", "BEAM3D_CONST", "RIGID_LINK", "SPRING6", "MASS6", "RELEASE"]),
    ("analysis_order",
     ["FIRST_ORDER", "SECOND_ORDER"]),
    ("mesh_profile",
     ["FAST", "STANDARD", "PRECISE", "VALIDATION"]),
    ("shear_formulation",
     ["EULER_BERNOULLI", "TIMOSHENKO"]),
    ("mass_model",
     ["LUMPED", "CONSISTENT"]),
    ("structural_model_status",
     ["BUILDING", "BUILT", "VALIDATED", "INVALID"]),
    ("structural_property_set",
     ["GROSS", "NET", "CRACKED", "HAZ", "DOOR", "EFFECTIVE"]),
    ("structural_run_status",
     ["QUEUED", "PREPARING", "SOLVING", "POSTPROCESSING",
      "COMPLETED", "FAILED", "CANCELLED"]),
    ("support_type",
     ["IDEAL_FIXED", "ELASTIC", "DISTRIBUTED_SPRINGS", "PINNED", "GUIDED", "TEMPORARY"]),
    ("structural_diagnostic_severity",
     ["INFO", "WARNING", "ERROR", "CRITICAL"]),
    ("envelope_scope",
     ["BY_STATION", "BY_COMPONENT", "BY_CONNECTION", "BY_PROJECT", "BY_DIRECTION"]),
    ("structural_load_type",
     ["NODAL", "DISTRIBUTED", "THERMAL", "INERTIAL", "IMPOSED_DEFORMATION", "PRESTRESS"]),
]


def upgrade() -> None:
    # ── Crear enums ───────────────────────────────────────────────────────────
    for name, values in ENUMS:
        op.execute(
            f"CREATE TYPE {name} AS ENUM ({', '.join(repr(v) for v in values)})"
        )

    # ── structural_models ─────────────────────────────────────────────────────
    op.create_table(
        "structural_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_revision_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("action_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(20), nullable=False, server_default="4.0.0"),
        sa.Column("structural_model_hash", sa.String(64), nullable=True),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("action_run_hash", sa.String(64), nullable=True),
        sa.Column("engine_version", sa.String(20), nullable=False, server_default="4.0.0"),
        sa.Column("status", postgresql.ENUM(name="structural_model_status", create_type=False),
                  nullable=False, server_default="BUILDING"),
        sa.Column("property_set", postgresql.ENUM(name="structural_property_set", create_type=False),
                  nullable=False, server_default="GROSS"),
        sa.Column("mesh_profile", postgresql.ENUM(name="mesh_profile", create_type=False),
                  nullable=False, server_default="STANDARD"),
        sa.Column("shear_formulation", postgresql.ENUM(name="shear_formulation", create_type=False),
                  nullable=False, server_default="TIMOSHENKO"),
        sa.Column("mass_model", postgresql.ENUM(name="mass_model", create_type=False),
                  nullable=False, server_default="CONSISTENT"),
        sa.Column("default_analysis_order", postgresql.ENUM(name="analysis_order", create_type=False),
                  nullable=False, server_default="SECOND_ORDER"),
        sa.Column("modal_modes", sa.Integer, nullable=True),
        sa.Column("node_count", sa.Integer, nullable=True),
        sa.Column("element_count", sa.Integer, nullable=True),
        sa.Column("dof_count", sa.Integer, nullable=True),
        sa.Column("station_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("build_time_s", sa.Float, nullable=True),
        sa.Column("build_log_json", postgresql.JSONB, nullable=True),
    )

    # ── structural_nodes ──────────────────────────────────────────────────────
    op.create_table(
        "structural_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("x_m", sa.Float, nullable=False),
        sa.Column("y_m", sa.Float, nullable=False),
        sa.Column("z_m", sa.Float, nullable=False),
        sa.Column("dof_active_json", postgresql.JSONB, nullable=False,
                  server_default="[true,true,true,true,true,true]"),
        sa.Column("component_type", sa.String(50), nullable=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("local_axes_json", postgresql.JSONB, nullable=True),
        sa.Column("is_master_node", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_mandatory_station", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_structural_nodes_model", "structural_nodes", ["model_id"])

    # ── structural_elements ───────────────────────────────────────────────────
    op.create_table(
        "structural_elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_i_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("node_j_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("element_type", postgresql.ENUM(name="element_type", create_type=False), nullable=False),
        sa.Column("element_order", sa.Integer, nullable=False),
        sa.Column("length_m", sa.Float, nullable=True),
        sa.Column("roll_angle_rad", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("section_stations_json", postgresql.JSONB, nullable=False,
                  server_default="[]"),
        sa.Column("material_json", postgresql.JSONB, nullable=False,
                  server_default='{"E_Pa":null,"G_Pa":null,"rho_kg_m3":null,"alpha_T_1_K":null}'),
        sa.Column("stiffness_matrix_json", postgresql.JSONB, nullable=True),
        sa.Column("releases_i_json", postgresql.JSONB, nullable=True),
        sa.Column("releases_j_json", postgresql.JSONB, nullable=True),
        sa.Column("offset_vector_json", postgresql.JSONB, nullable=True),
        sa.Column("component_type", sa.String(50), nullable=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_structural_elements_model", "structural_elements", ["model_id"])

    # ── support_conditions ────────────────────────────────────────────────────
    op.create_table(
        "support_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("support_type", postgresql.ENUM(name="support_type", create_type=False), nullable=False),
        sa.Column("constrained_dofs_json", postgresql.JSONB, nullable=True),
        sa.Column("stiffness_matrix_json", postgresql.JSONB, nullable=True),
        sa.Column("distributed_springs_json", postgresql.JSONB, nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("source_reference", sa.String(200), nullable=True),
    )

    # ── mass_objects ──────────────────────────────────────────────────────────
    op.create_table(
        "mass_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("mass_kg", sa.Float, nullable=False),
        sa.Column("cg_global_json", postgresql.JSONB, nullable=False,
                  server_default='{"x_m":0.0,"y_m":0.0,"z_m":0.0}'),
        sa.Column("inertia_tensor_json", postgresql.JSONB, nullable=True),
        sa.Column("component_type", sa.String(50), nullable=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("include_in_self_weight", sa.Boolean, nullable=False, server_default="true"),
        sa.CheckConstraint("mass_kg >= 0", name="ck_mass_nonneg"),
    )

    # ── structural_analysis_runs ──────────────────────────────────────────────
    op.create_table(
        "structural_analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_models.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True, unique=True),
        sa.Column("structural_model_hash", sa.String(64), nullable=True),
        sa.Column("analysis_input_hash", sa.String(64), nullable=True),
        sa.Column("solver_hash", sa.String(64), nullable=True),
        sa.Column("engine_version", sa.String(20), nullable=False, server_default="4.0.0"),
        sa.Column("analysis_types_json", postgresql.JSONB, nullable=False,
                  server_default='["LINEAR","SECOND_ORDER"]'),
        sa.Column("analysis_order",
                  postgresql.ENUM(name="analysis_order", create_type=False),
                  nullable=False, server_default="SECOND_ORDER"),
        sa.Column("mesh_profile",
                  postgresql.ENUM(name="mesh_profile", create_type=False),
                  nullable=False, server_default="STANDARD"),
        sa.Column("shear_formulation",
                  postgresql.ENUM(name="shear_formulation", create_type=False),
                  nullable=False, server_default="TIMOSHENKO"),
        sa.Column("mass_model",
                  postgresql.ENUM(name="mass_model", create_type=False),
                  nullable=False, server_default="CONSISTENT"),
        sa.Column("modal_modes", sa.Integer, nullable=True),
        sa.Column("buckling_modes", sa.Integer, nullable=True),
        sa.Column("nl_tol_residual", sa.Float, nullable=False, server_default="1e-6"),
        sa.Column("nl_tol_displacement", sa.Float, nullable=False, server_default="1e-6"),
        sa.Column("nl_max_iterations", sa.Integer, nullable=False, server_default="50"),
        sa.Column("status",
                  postgresql.ENUM(name="structural_run_status", create_type=False),
                  nullable=False, server_default="QUEUED"),
        sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preprocess_time_s", sa.Float, nullable=True),
        sa.Column("assembly_time_s", sa.Float, nullable=True),
        sa.Column("factorization_time_s", sa.Float, nullable=True),
        sa.Column("solve_time_s", sa.Float, nullable=True),
        sa.Column("postprocess_time_s", sa.Float, nullable=True),
        sa.Column("system_size", sa.Integer, nullable=True),
        sa.Column("nonzeros", sa.Integer, nullable=True),
        sa.Column("condition_number", sa.Float, nullable=True),
        sa.Column("nl_iterations", sa.Integer, nullable=True),
        sa.Column("nl_residual_final", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("manifest_json", postgresql.JSONB, nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_struct_run_idempotency"),
    )
    op.create_index("ix_struct_runs_model", "structural_analysis_runs", ["model_id"])
    op.create_index("ix_struct_runs_status", "structural_analysis_runs", ["status"])

    # ── structural_load_vectors ───────────────────────────────────────────────
    op.create_table(
        "structural_load_vectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("load_case_ref", sa.String(100), nullable=True),
        sa.Column("load_type",
                  postgresql.ENUM(name="structural_load_type", create_type=False), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_element_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_vector_json", postgresql.JSONB, nullable=False),
        sa.Column("transform_json", postgresql.JSONB, nullable=True),
        sa.Column("applied_vector_json", postgresql.JSONB, nullable=False),
        sa.Column("station_start_m", sa.Float, nullable=True),
        sa.Column("station_end_m", sa.Float, nullable=True),
        sa.Column("delta_t_uniform_k", sa.Float, nullable=True),
        sa.Column("delta_t_gradient_k_m", sa.Float, nullable=True),
    )

    # ── nodal_results ─────────────────────────────────────────────────────────
    op.create_table(
        "nodal_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_nodes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("load_case_ref", sa.String(100), nullable=False),
        sa.Column("ux_m", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("uy_m", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("uz_m", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("rx_rad", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("ry_rad", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("rz_rad", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("rx_n", sa.Float, nullable=True),
        sa.Column("ry_n", sa.Float, nullable=True),
        sa.Column("rz_n", sa.Float, nullable=True),
        sa.Column("mrx_nm", sa.Float, nullable=True),
        sa.Column("mry_nm", sa.Float, nullable=True),
        sa.Column("mrz_nm", sa.Float, nullable=True),
        sa.Column("u_horizontal_m", sa.Float, nullable=True),
    )
    op.create_index("ix_nodal_results_run", "nodal_results", ["run_id"])
    op.create_index("ix_nodal_results_node_run", "nodal_results", ["node_id", "run_id"])

    # ── section_results ───────────────────────────────────────────────────────
    op.create_table(
        "section_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("element_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_elements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("load_case_ref", sa.String(100), nullable=False),
        sa.Column("xi", sa.Float, nullable=False),
        sa.Column("z_global_m", sa.Float, nullable=True),
        sa.Column("n_n", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("vy_n", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("vz_n", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("t_nm", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("my_nm", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("mz_nm", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("curvature_y", sa.Float, nullable=True),
        sa.Column("curvature_z", sa.Float, nullable=True),
    )
    op.create_index("ix_section_results_run", "section_results", ["run_id"])
    op.create_index("ix_section_results_element_run", "section_results",
                    ["element_id", "run_id"])

    # ── modal_results ─────────────────────────────────────────────────────────
    op.create_table(
        "modal_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode_number", sa.Integer, nullable=False),
        sa.Column("frequency_hz", sa.Float, nullable=False),
        sa.Column("period_s", sa.Float, nullable=False),
        sa.Column("eff_mass_x_kg", sa.Float, nullable=True),
        sa.Column("eff_mass_y_kg", sa.Float, nullable=True),
        sa.Column("eff_mass_z_kg", sa.Float, nullable=True),
        sa.Column("participation_x_pct", sa.Float, nullable=True),
        sa.Column("participation_y_pct", sa.Float, nullable=True),
        sa.Column("participation_z_pct", sa.Float, nullable=True),
        sa.Column("modal_shape_json", postgresql.JSONB, nullable=True),
        sa.Column("mode_description", sa.String(100), nullable=True),
        sa.CheckConstraint("frequency_hz > 0", name="ck_modal_freq_pos"),
        sa.CheckConstraint("mode_number >= 1", name="ck_modal_mode_pos"),
    )
    op.create_index("ix_modal_results_run", "modal_results", ["run_id"])

    # ── buckling_results ──────────────────────────────────────────────────────
    op.create_table(
        "buckling_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("load_case_ref", sa.String(100), nullable=False),
        sa.Column("mode_number", sa.Integer, nullable=False),
        sa.Column("critical_factor", sa.Float, nullable=False),
        sa.Column("buckling_shape_json", postgresql.JSONB, nullable=True),
        sa.Column("critical_element_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("critical_factor > 0", name="ck_buckling_factor_pos"),
        sa.CheckConstraint("mode_number >= 1", name="ck_buckling_mode_pos"),
    )
    op.create_index("ix_buckling_results_run", "buckling_results", ["run_id"])

    # ── result_envelopes ──────────────────────────────────────────────────────
    op.create_table(
        "result_envelopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", postgresql.ENUM(name="envelope_scope", create_type=False), nullable=False),
        sa.Column("quantity", sa.String(30), nullable=False),
        sa.Column("sign", sa.String(4), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("load_case_ref", sa.String(100), nullable=True),
        sa.Column("combination_ref", sa.String(100), nullable=True),
        sa.Column("wind_direction_deg", sa.Float, nullable=True),
        sa.Column("station_xi", sa.Float, nullable=True),
        sa.Column("element_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("governing_context_json", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_result_envelopes_run", "result_envelopes", ["run_id"])
    op.create_index("ix_result_envelopes_quantity", "result_envelopes",
                    ["run_id", "quantity", "sign"])

    # ── structural_diagnostic_events ──────────────────────────────────────────
    op.create_table(
        "structural_diagnostic_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_models.id", ondelete="CASCADE"), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("severity",
                  postgresql.ENUM(name="structural_diagnostic_severity", create_type=False),
                  nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context_json", postgresql.JSONB, nullable=True),
        sa.Column("metric_value", sa.Float, nullable=True),
        sa.Column("metric_unit", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # ── structural_exports ────────────────────────────────────────────────────
    op.create_table(
        "structural_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("structural_model_hash", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    # Tablas en orden inverso de dependencias
    for table in [
        "structural_exports",
        "structural_diagnostic_events",
        "result_envelopes",
        "buckling_results",
        "modal_results",
        "section_results",
        "nodal_results",
        "structural_load_vectors",
        "structural_analysis_runs",
        "mass_objects",
        "support_conditions",
        "structural_elements",
        "structural_nodes",
        "structural_models",
    ]:
        op.drop_table(table)

    for name, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
