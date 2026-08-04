"""Fase 2: Geometría Paramétrica — tablas y enums

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    geometry_quality_state = postgresql.ENUM(
        "draft", "geometrically_valid", "manufacturable",
        "calculation_ready", "cad_ready", "obsolete",
        name="geometry_quality_state",
    )
    geometry_lod = postgresql.ENUM(
        "G0", "G1", "G2", "G3", "G4",
        name="geometry_lod",
    )
    section_law_type = postgresql.ENUM(
        "constant", "linear", "stepped", "table", "imported",
        name="section_law_type",
    )
    section_profile_type = postgresql.ENUM(
        "circular", "polygonal_regular", "folded", "extruded", "concrete_hollow",
        name="section_profile_type",
    )
    joint_type = postgresql.ENUM(
        "telescopic", "flanged", "welded", "sleeve",
        name="joint_type",
    )
    arm_type = postgresql.ENUM(
        "straight", "curved", "davit", "cruciform",
        "radial_crown", "post_top", "adapter",
        name="arm_type",
    )
    attachment_type = postgresql.ENUM(
        "luminaire", "solar_panel", "battery_cabinet", "sign_banner",
        "camera_sensor", "antenna", "traffic_light", "generic",
        name="attachment_type",
    )
    cable_load_state = postgresql.ENUM(
        "confirmed", "estimated", "pending",
        name="cable_load_state",
    )
    base_interface_type = postgresql.ENUM(
        "plate", "embedded",
        name="base_interface_type",
    )
    geometry_artifact_format = postgresql.ENUM(
        "step", "dxf", "gltf", "svg", "json", "glb", "pdf",
        name="geometry_artifact_format",
    )
    geometry_artifact_status = postgresql.ENUM(
        "generating", "ready", "obsolete", "failed",
        name="geometry_artifact_status",
    )
    validation_result = postgresql.ENUM(
        "pass", "fail", "warning", "blocked",
        name="validation_result",
    )
    validation_severity = postgresql.ENUM(
        "error", "warning", "info", "exception_required",
        name="validation_severity",
    )
    manufacturing_process = postgresql.ENUM(
        "tube", "folded_longitudinal_weld", "extrusion",
        "centrifuged_concrete", "machined", "welded_assembly", "bolted", "other",
        name="manufacturing_process",
    )

    for e in [
        geometry_quality_state, geometry_lod, section_law_type,
        section_profile_type, joint_type, arm_type, attachment_type,
        cable_load_state, base_interface_type, geometry_artifact_format,
        geometry_artifact_status, validation_result, validation_severity,
        manufacturing_process,
    ]:
        e.create(op.get_bind(), checkfirst=True)

    # ── section_profiles ───────────────────────────────────────────────────────
    op.create_table(
        "section_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("library_version_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("library_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("profile_type", postgresql.ENUM(name="section_profile_type", create_type=False), nullable=False),
        sa.Column("geometry_json", postgresql.JSONB, nullable=False),
        sa.Column("canonical_dimension_m", sa.Float, nullable=False),
        sa.Column("orientation_rad", sa.Float, nullable=False, server_default="0"),
        sa.Column("schema_version", sa.String(20), nullable=False, server_default="2.0"),
        sa.Column("properties_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_section_profiles_code", "section_profiles", ["code"])
    op.create_index("ix_section_profiles_type", "section_profiles", ["profile_type"])

    # ── section_laws ───────────────────────────────────────────────────────────
    op.create_table(
        "section_laws",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("law_type", postgresql.ENUM(name="section_law_type", create_type=False), nullable=False),
        sa.Column("interpolation", sa.String(30), nullable=False, server_default="linear"),
        sa.Column("continuity", sa.String(10), nullable=False, server_default="C0"),
        sa.Column("parameter_json", postgresql.JSONB, nullable=False),
        sa.Column("profile_ref", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("section_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("domain", sa.String(50), nullable=False, server_default="mast_segment"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_section_laws_type", "section_laws", ["law_type"])

    # ── manufacturing_constraint_sets ──────────────────────────────────────────
    op.create_table(
        "manufacturing_constraint_sets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("rules_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mfg_constraints_code", "manufacturing_constraint_sets", ["code"])
    op.create_index("ix_mfg_constraints_active", "manufacturing_constraint_sets", ["is_active"])

    # ── geometry_models ────────────────────────────────────────────────────────
    op.create_table(
        "geometry_models",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("project_revision_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False, server_default="2.0"),
        sa.Column("lod", postgresql.ENUM(name="geometry_lod", create_type=False), nullable=False, server_default="G1"),
        sa.Column("quality_state", postgresql.ENUM(name="geometry_quality_state", create_type=False), nullable=False, server_default="draft"),
        sa.Column("coordinate_convention", sa.String(50), nullable=False, server_default="Z_up_X_azimuth0"),
        sa.Column("canonical_units", sa.String(20), nullable=False, server_default="SI"),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("engine_version", sa.String(30), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_geometry_models_revision", "geometry_models", ["project_revision_id"])
    op.create_index("ix_geometry_models_hash", "geometry_models", ["geometry_hash"])
    op.create_index("ix_geometry_models_quality", "geometry_models", ["quality_state"])

    # ── masts ──────────────────────────────────────────────────────────────────
    op.create_table(
        "masts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("geometry_model_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("geometry_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nominal_height_m", sa.Float, nullable=False),
        sa.Column("base_type", postgresql.ENUM(name="base_interface_type", create_type=False), nullable=False, server_default="plate"),
        sa.Column("material_ref", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("materials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("manufacturing_process", postgresql.ENUM(name="manufacturing_process", create_type=False), nullable=True),
        sa.Column("constraint_set_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("manufacturing_constraint_sets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_height_m", sa.Float, nullable=True),
        sa.Column("total_mass_kg", sa.Float, nullable=True),
        sa.Column("cg_z_m", sa.Float, nullable=True),
        sa.Column("is_segmented", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("nominal_height_m > 0 AND nominal_height_m <= 30", name="ck_mast_height"),
    )
    op.create_index("ix_masts_geometry_model", "masts", ["geometry_model_id"])

    # ── mast_segments ──────────────────────────────────────────────────────────
    op.create_table(
        "mast_segments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("mast_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("masts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_order", sa.Integer, nullable=False),
        sa.Column("piece_id", sa.String(20), nullable=False),
        sa.Column("z_start_m", sa.Float, nullable=False),
        sa.Column("z_end_m", sa.Float, nullable=False),
        sa.Column("section_law_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("section_laws.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("physical_length_m", sa.Float, nullable=False),
        sa.Column("visible_length_m", sa.Float, nullable=True),
        sa.Column("transport_orientation", sa.String(20), nullable=True),
        sa.Column("manufacturing_process", postgresql.ENUM(name="manufacturing_process", create_type=False), nullable=True),
        sa.Column("material_ref", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("materials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mass_kg", sa.Float, nullable=True),
        sa.Column("cg_z_m", sa.Float, nullable=True),
        sa.Column("features_json", postgresql.JSONB, nullable=True),
        sa.Column("manufacturing_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("z_end_m > z_start_m", name="ck_segment_z_order"),
        sa.CheckConstraint("physical_length_m > 0", name="ck_segment_length_positive"),
    )
    op.create_index("ix_mast_segments_mast", "mast_segments", ["mast_id"])
    op.create_index("ix_mast_segments_order", "mast_segments", ["mast_id", "segment_order"])

    # ── joints ──────────────────────────────────────────────────────────────────
    op.create_table(
        "joints",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("mast_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("masts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lower_segment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("mast_segments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upper_segment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("mast_segments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joint_type", postgresql.ENUM(name="joint_type", create_type=False), nullable=False),
        sa.Column("overlap_m", sa.Float, nullable=True),
        sa.Column("z_joint_m", sa.Float, nullable=False),
        sa.Column("geometry_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_joints_mast", "joints", ["mast_id"])

    # ── arms ────────────────────────────────────────────────────────────────────
    op.create_table(
        "arms",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("mast_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("masts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_segment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("mast_segments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("arm_type", postgresql.ENUM(name="arm_type", create_type=False), nullable=False),
        sa.Column("code", sa.String(30), nullable=True),
        sa.Column("library_item_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("library_version", sa.String(20), nullable=True),
        sa.Column("anchor_json", postgresql.JSONB, nullable=False),
        sa.Column("axis_curve_json", postgresql.JSONB, nullable=False),
        sa.Column("section_law_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("section_laws.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transform_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("roll_angle_rad", sa.Float, nullable=False, server_default="0"),
        sa.Column("luminaire_interface_json", postgresql.JSONB, nullable=True),
        sa.Column("fabrication_mode", postgresql.ENUM(name="manufacturing_process", create_type=False), nullable=True),
        sa.Column("symmetry_group", sa.String(30), nullable=True),
        sa.Column("material_ref", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("materials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mass_kg", sa.Float, nullable=True),
        sa.Column("cg_local_json", postgresql.JSONB, nullable=True),
        sa.Column("projected_areas_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_arms_mast", "arms", ["mast_id"])

    # ── attachments ────────────────────────────────────────────────────────────
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("mast_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("masts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_arm_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("arms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attachment_type", postgresql.ENUM(name="attachment_type", create_type=False), nullable=False),
        sa.Column("code", sa.String(30), nullable=True),
        sa.Column("library_item_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("library_version", sa.String(20), nullable=True),
        sa.Column("library_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("lod", postgresql.ENUM(name="geometry_lod", create_type=False), nullable=False, server_default="G1"),
        sa.Column("transform_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("mass_kg", sa.Float, nullable=True),
        sa.Column("cg_local_json", postgresql.JSONB, nullable=True),
        sa.Column("projected_areas_json", postgresql.JSONB, nullable=True),
        sa.Column("aero_json", postgresql.JSONB, nullable=True),
        sa.Column("properties_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attachments_mast", "attachments", ["mast_id"])
    op.create_index("ix_attachments_type", "attachments", ["attachment_type"])

    # ── cable_load_points ──────────────────────────────────────────────────────
    op.create_table(
        "cable_load_points",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("mast_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("masts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cable_identifier", sa.String(20), nullable=False),
        sa.Column("anchor_z_m", sa.Float, nullable=False),
        sa.Column("position_local_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("azimuth_rad", sa.Float, nullable=False),
        sa.Column("elevation_rad", sa.Float, nullable=False, server_default="0"),
        sa.Column("tension_n", sa.Float, nullable=True),
        sa.Column("cable_state", postgresql.ENUM(name="cable_load_state", create_type=False), nullable=False, server_default="pending"),
        sa.Column("interface_type", sa.String(50), nullable=True),
        sa.Column("interface_envelope_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cable_load_points_mast", "cable_load_points", ["mast_id"])

    # ── door_assemblies ────────────────────────────────────────────────────────
    op.create_table(
        "door_assemblies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("mast_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("masts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("mast_segments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opening_json", postgresql.JSONB, nullable=False),
        sa.Column("reinforcement_json", postgresql.JSONB, nullable=True),
        sa.Column("reinforcement_ref", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("door_envelope_json", postgresql.JSONB, nullable=True),
        sa.Column("interior_support_json", postgresql.JSONB, nullable=True),
        sa.Column("cable_path_json", postgresql.JSONB, nullable=True),
        sa.Column("earth_connection_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_door_assemblies_mast", "door_assemblies", ["mast_id"])

    # ── base_interfaces ────────────────────────────────────────────────────────
    op.create_table(
        "base_interfaces",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("mast_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("masts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("interface_type", postgresql.ENUM(name="base_interface_type", create_type=False), nullable=False),
        sa.Column("geometry_json", postgresql.JSONB, nullable=False),
        sa.Column("bolt_pattern_json", postgresql.JSONB, nullable=True),
        sa.Column("bolt_details_json", postgresql.JSONB, nullable=True),
        sa.Column("embedment_length_m", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_base_interfaces_mast", "base_interfaces", ["mast_id"])

    # ── geometry_validations ───────────────────────────────────────────────────
    op.create_table(
        "geometry_validations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("geometry_model_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("geometry_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("rule_code", sa.String(20), nullable=False),
        sa.Column("severity", postgresql.ENUM(name="validation_severity", create_type=False), nullable=False),
        sa.Column("result", postgresql.ENUM(name="validation_result", create_type=False), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("evidence_json", postgresql.JSONB, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("exception_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_geometry_validations_model", "geometry_validations", ["geometry_model_id"])
    op.create_index("ix_geometry_validations_rule", "geometry_validations", ["rule_code"])
    op.create_index("ix_geometry_validations_hash", "geometry_validations", ["geometry_hash"])
    op.create_index("ix_geometry_validations_result", "geometry_validations", ["result"])

    # ── geometry_artifacts ──────────────────────────────────────────────────────
    op.create_table(
        "geometry_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("geometry_model_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("geometry_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geometry_hash", sa.String(64), nullable=False),
        sa.Column("artifact_format", postgresql.ENUM(name="geometry_artifact_format", create_type=False), nullable=False),
        sa.Column("lod", postgresql.ENUM(name="geometry_lod", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="geometry_artifact_status", create_type=False), nullable=False, server_default="generating"),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("generator_version", sa.String(30), nullable=True),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_geometry_artifacts_model", "geometry_artifacts", ["geometry_model_id"])
    op.create_index("ix_geometry_artifacts_hash", "geometry_artifacts", ["geometry_hash"])
    op.create_index("ix_geometry_artifacts_status", "geometry_artifacts", ["status"])


def downgrade() -> None:
    for table in [
        "geometry_artifacts", "geometry_validations", "base_interfaces",
        "door_assemblies", "cable_load_points", "attachments", "arms",
        "joints", "mast_segments", "masts", "geometry_models",
        "manufacturing_constraint_sets", "section_laws", "section_profiles",
    ]:
        op.drop_table(table)

    for enum_name in [
        "geometry_artifact_status", "geometry_artifact_format", "validation_result",
        "validation_severity", "cable_load_state", "attachment_type", "arm_type",
        "joint_type", "section_profile_type", "section_law_type", "geometry_lod",
        "geometry_quality_state", "base_interface_type", "manufacturing_process",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
