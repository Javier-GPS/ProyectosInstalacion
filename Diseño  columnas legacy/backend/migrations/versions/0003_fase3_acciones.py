"""Fase 3: Acciones, Ubicación y Combinaciones — tablas y enums

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    environment_type = postgresql.ENUM(
        "sea", "rural", "suburban", "urban", "urban_dense",
        name="environment_type",
    )
    geo_parameter_type = postgresql.ENUM(
        "wind_basic_velocity", "wind_roughness_category", "wind_orographic_factor",
        "wind_directional_factor", "snow_load", "ice_load", "seismic_acceleration",
        "seismic_zone", "air_density", "altitude", "temperature_min",
        "temperature_max", "other",
        name="geo_parameter_type",
    )
    data_confidence_level = postgresql.ENUM(
        "A", "B", "C", "D", "E",
        name="data_confidence_level",
    )
    confirmation_state = postgresql.ENUM(
        "proposed", "confirmed", "substituted", "estimated", "conservative", "pending",
        name="confirmation_state",
    )
    action_type = postgresql.ENUM(
        "G", "W", "S", "I", "E", "T", "C", "M", "A", "P",
        name="action_type",
    )
    cable_action_state = postgresql.ENUM(
        "active_permanent", "active_conditional", "absent",
        "accidental_break", "temporary_tensioned",
        name="cable_action_state",
    )
    action_run_status = postgresql.ENUM(
        "pending", "running", "succeeded", "failed", "cancelled",
        name="action_run_status",
    )
    diagnostic_severity = postgresql.ENUM(
        "error", "warning", "info", "blocked",
        name="diagnostic_severity",
    )
    limit_state = postgresql.ENUM(
        "ULS_persistent", "ULS_accidental", "ULS_seismic",
        "SLS_characteristic", "SLS_frequent", "SLS_quasi_permanent", "fatigue",
        name="limit_state",
    )
    spatial_load_type = postgresql.ENUM(
        "nodal", "distributed", "surface_pressure", "mass",
        "imposed_displacement", "temperature",
        name="spatial_load_type",
    )
    aero_quality = postgresql.ENUM(
        "A", "B", "C",
        name="aero_quality",
    )

    for e in [
        environment_type, geo_parameter_type, data_confidence_level,
        confirmation_state, action_type, cable_action_state,
        action_run_status, diagnostic_severity, limit_state,
        spatial_load_type, aero_quality,
    ]:
        e.create(op.get_bind(), checkfirst=True)

    # ── locations ──────────────────────────────────────────────────────────────
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_revision_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("country_code", sa.String(3), nullable=False),
        sa.Column("country_name", sa.String(100), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("municipality", sa.String(100), nullable=True),
        sa.Column("altitude_m", sa.Float, nullable=True),
        sa.Column("altitude_source", sa.String(100), nullable=True),
        sa.Column("altitude_resolution_m", sa.Float, nullable=True),
        sa.Column("environment", postgresql.ENUM(name="environment_type", create_type=False), nullable=True),
        sa.Column("project_life_years", sa.Integer, nullable=True),
        sa.Column("reference_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jurisdiction_json", postgresql.JSONB, nullable=True),
        sa.Column("normative_set_json", postgresql.JSONB, nullable=True),
        sa.Column("geocoding_source", sa.String(100), nullable=True),
        sa.Column("geocoding_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_state", postgresql.ENUM(name="confirmation_state", create_type=False), nullable=False, server_default="proposed"),
        sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_location_lat"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_location_lon"),
    )
    op.create_index("ix_locations_revision", "locations", ["project_revision_id"])
    op.create_index("ix_locations_country", "locations", ["country_code"])

    # ── geo_parameters ─────────────────────────────────────────────────────────
    op.create_table(
        "geo_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parameter_type", postgresql.ENUM(name="geo_parameter_type", create_type=False), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("proposed_value", sa.Float, nullable=True),
        sa.Column("proposed_value_json", postgresql.JSONB, nullable=True),
        sa.Column("adopted_value", sa.Float, nullable=True),
        sa.Column("adopted_value_json", postgresql.JSONB, nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("source_id", sa.String(100), nullable=True),
        sa.Column("source_version", sa.String(50), nullable=True),
        sa.Column("retrieval_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(50), nullable=True),
        sa.Column("interpolation_method", sa.String(50), nullable=True),
        sa.Column("confidence", postgresql.ENUM(name="data_confidence_level", create_type=False), nullable=False, server_default="E"),
        sa.Column("confirmation_state", postgresql.ENUM(name="confirmation_state", create_type=False), nullable=False, server_default="proposed"),
        sa.Column("justification", sa.Text, nullable=True),
        sa.Column("spatial_ref_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_geo_parameters_location", "geo_parameters", ["location_id"])
    op.create_index("ix_geo_parameters_type", "geo_parameters", ["parameter_type"])
    op.create_index("ix_geo_parameters_confidence", "geo_parameters", ["confidence"])

    # ── normative_action_rules ─────────────────────────────────────────────────
    op.create_table(
        "normative_action_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("library_version_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("library_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("edition", sa.String(30), nullable=False),
        sa.Column("clause", sa.String(100), nullable=True),
        sa.Column("country_code", sa.String(3), nullable=True),
        sa.Column("action_type", postgresql.ENUM(name="action_type", create_type=False), nullable=True),
        sa.Column("formula_json", postgresql.JSONB, nullable=False),
        sa.Column("validity_json", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_normative_rules_code", "normative_action_rules", ["code"])
    op.create_index("ix_normative_rules_edition", "normative_action_rules", ["edition"])
    op.create_index("ix_normative_rules_country", "normative_action_rules", ["country_code"])

    # ── aerodynamic_properties ─────────────────────────────────────────────────
    op.create_table(
        "aerodynamic_properties",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("component_type", sa.String(50), nullable=False),
        sa.Column("orientation_deg", sa.Float, nullable=True),
        sa.Column("area_m2", sa.Float, nullable=True),
        sa.Column("cd", sa.Float, nullable=True),
        sa.Column("polar_table_json", postgresql.JSONB, nullable=True),
        sa.Column("method", sa.String(50), nullable=False, server_default="geometric_projection"),
        sa.Column("validity_json", postgresql.JSONB, nullable=True),
        sa.Column("quality", postgresql.ENUM(name="aero_quality", create_type=False), nullable=False, server_default="C"),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("cp_local_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_aero_props_component", "aerodynamic_properties", ["component_id"])
    op.create_index("ix_aero_props_type", "aerodynamic_properties", ["component_type"])

    # ── combination_templates ──────────────────────────────────────────────────
    op.create_table(
        "combination_templates",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("library_version_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("library_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("edition", sa.String(30), nullable=False),
        sa.Column("country_code", sa.String(3), nullable=True),
        sa.Column("limit_state", postgresql.ENUM(name="limit_state", create_type=False), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("formula_graph_json", postgresql.JSONB, nullable=False),
        sa.Column("factors_json", postgresql.JSONB, nullable=False),
        sa.Column("exclusions_json", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_combination_templates_code", "combination_templates", ["code"])
    op.create_index("ix_combination_templates_limit_state", "combination_templates", ["limit_state"])

    # ── action_runs ────────────────────────────────────────────────────────────
    op.create_table(
        "action_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_revision_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("outputs_hash", sa.String(64), nullable=True),
        sa.Column("engine_version", sa.String(30), nullable=True),
        sa.Column("library_versions_json", postgresql.JSONB, nullable=True),
        sa.Column("status", postgresql.ENUM(name="action_run_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifest_json", postgresql.JSONB, nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True, unique=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("arq_job_id", sa.String(100), nullable=True),
        sa.Column("sweep_config_json", postgresql.JSONB, nullable=True),
        sa.Column("combination_template_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_action_runs_revision", "action_runs", ["project_revision_id"])
    op.create_index("ix_action_runs_status", "action_runs", ["status"])
    op.create_index("ix_action_runs_input_hash", "action_runs", ["input_hash"])

    # ── action_components ──────────────────────────────────────────────────────
    op.create_table(
        "action_components",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", postgresql.ENUM(name="action_type", create_type=False), nullable=False),
        sa.Column("component_ref", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("component_type", sa.String(50), nullable=True),
        sa.Column("direction_deg", sa.Float, nullable=True),
        sa.Column("characteristic_value", sa.Float, nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("distribution_json", postgresql.JSONB, nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("rule_ref", sa.String(50), nullable=True),
        sa.Column("calculation_trace_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_action_components_run", "action_components", ["action_run_id"])
    op.create_index("ix_action_components_type", "action_components", ["action_type"])

    # ── cable_actions ──────────────────────────────────────────────────────────
    op.create_table(
        "cable_actions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cable_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("cable_load_points.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cable_identifier", sa.String(20), nullable=False),
        sa.Column("anchor_z_m", sa.Float, nullable=False),
        sa.Column("tension_n", sa.Float, nullable=False),
        sa.Column("azimuth_rad", sa.Float, nullable=False),
        sa.Column("elevation_rad", sa.Float, nullable=False, server_default="0"),
        sa.Column("force_vector_json", postgresql.JSONB, nullable=True),
        sa.Column("eccentricity_json", postgresql.JSONB, nullable=True),
        sa.Column("cable_state", postgresql.ENUM(name="cable_action_state", create_type=False), nullable=False, server_default="active_permanent"),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("uncertainty_pct", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tension_n >= 0", name="ck_cable_tension_positive"),
    )
    op.create_index("ix_cable_actions_run", "cable_actions", ["action_run_id"])

    # ── load_cases ─────────────────────────────────────────────────────────────
    op.create_table(
        "load_cases",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("direction_deg", sa.Float, nullable=True),
        sa.Column("action_types_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("active_actions_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("component_states_json", postgresql.JSONB, nullable=True),
        sa.Column("case_hash", sa.String(64), nullable=True),
        sa.Column("is_base_direction", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_refined", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("parent_direction_deg", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_load_cases_run", "load_cases", ["action_run_id"])
    op.create_index("ix_load_cases_direction", "load_cases", ["direction_deg"])
    op.create_index("ix_load_cases_hash", "load_cases", ["case_hash"])

    # ── combination_instances ──────────────────────────────────────────────────
    op.create_table(
        "combination_instances",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("load_case_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("load_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("combination_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("limit_state", postgresql.ENUM(name="limit_state", create_type=False), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("leading_action", postgresql.ENUM(name="action_type", create_type=False), nullable=True),
        sa.Column("normalized_terms_json", postgresql.JSONB, nullable=False),
        sa.Column("instance_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_combination_instances_run", "combination_instances", ["action_run_id"])
    op.create_index("ix_combination_instances_hash", "combination_instances", ["instance_hash"])
    op.create_index("ix_combination_instances_limit_state", "combination_instances", ["limit_state"])

    # ── spatial_loads ──────────────────────────────────────────────────────────
    op.create_table(
        "spatial_loads",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("load_case_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("load_cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("station_start_m", sa.Float, nullable=True),
        sa.Column("station_end_m", sa.Float, nullable=True),
        sa.Column("load_type", postgresql.ENUM(name="spatial_load_type", create_type=False), nullable=False),
        sa.Column("coordinate_system", sa.String(20), nullable=False, server_default="global"),
        sa.Column("vector_json", postgresql.JSONB, nullable=True),
        sa.Column("law_json", postgresql.JSONB, nullable=True),
        sa.Column("action_type", postgresql.ENUM(name="action_type", create_type=False), nullable=True),
        sa.Column("direction_deg", sa.Float, nullable=True),
        sa.Column("provenance_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_spatial_loads_run", "spatial_loads", ["action_run_id"])
    op.create_index("ix_spatial_loads_case", "spatial_loads", ["load_case_id"])
    op.create_index("ix_spatial_loads_target", "spatial_loads", ["target_id"])

    # ── mass_items ─────────────────────────────────────────────────────────────
    op.create_table(
        "mass_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("component_type", sa.String(50), nullable=False),
        sa.Column("mass_kg", sa.Float, nullable=False),
        sa.Column("cg_global_json", postgresql.JSONB, nullable=True),
        sa.Column("inertia_json", postgresql.JSONB, nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="geometry"),
        sa.Column("includes_hardware", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("includes_cables", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("includes_finish", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("additional_margin_pct", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mass_kg >= 0", name="ck_mass_item_positive"),
    )
    op.create_index("ix_mass_items_run", "mass_items", ["action_run_id"])
    op.create_index("ix_mass_items_component", "mass_items", ["component_id"])

    # ── action_diagnostics ─────────────────────────────────────────────────────
    op.create_table(
        "action_diagnostics",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("severity", postgresql.ENUM(name="diagnostic_severity", create_type=False), nullable=False),
        sa.Column("condition", sa.Text, nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("field_path", sa.String(200), nullable=True),
        sa.Column("normative_ref", sa.String(100), nullable=True),
        sa.Column("accepted_by_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acceptance_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_action_diagnostics_run", "action_diagnostics", ["action_run_id"])
    op.create_index("ix_action_diagnostics_code", "action_diagnostics", ["code"])
    op.create_index("ix_action_diagnostics_severity", "action_diagnostics", ["severity"])

    # ── user_overrides ─────────────────────────────────────────────────────────
    op.create_table(
        "user_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("action_run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("action_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parameter_ref", sa.String(100), nullable=False),
        sa.Column("original_value", sa.Float, nullable=True),
        sa.Column("original_value_json", postgresql.JSONB, nullable=True),
        sa.Column("adopted_value", sa.Float, nullable=True),
        sa.Column("adopted_value_json", postgresql.JSONB, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("evidence", sa.Text, nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("requires_ot_approval", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_overrides_run", "user_overrides", ["action_run_id"])


def downgrade() -> None:
    for table in [
        "user_overrides", "action_diagnostics", "mass_items", "spatial_loads",
        "combination_instances", "load_cases", "cable_actions", "action_components",
        "action_runs", "combination_templates", "aerodynamic_properties",
        "normative_action_rules", "geo_parameters", "locations",
    ]:
        op.drop_table(table)

    for enum_name in [
        "aero_quality", "spatial_load_type", "limit_state", "diagnostic_severity",
        "action_run_status", "cable_action_state", "action_type", "confirmation_state",
        "data_confidence_level", "geo_parameter_type", "environment_type",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
