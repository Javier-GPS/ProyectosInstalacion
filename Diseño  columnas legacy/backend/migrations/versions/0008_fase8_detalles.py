"""Fase 8: Puertas, Soportes y Detalles Locales.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-14
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE openingtype AS ENUM ('RECTANGULAR','RECTANGULAR_ROUNDED','OVAL','CABLE_SLOT','VENTILATION','DRAIN','CUSTOM')")
    op.execute("CREATE TYPE openinggeometriclevel AS ENUM ('G0','G1','G2','G3','G4')")
    op.execute("CREATE TYPE detailroute AS ENUM ('R8_A','R8_B','R8_C','R8_D','R8_E')")
    op.execute("CREATE TYPE reinforcementfamily AS ENUM ('FRAME','TWO_VERTICALS','VERTICALS_CROSSBARS','WRAPPING_PLATE','RING','EXTRUSION','HYBRID')")
    op.execute("CREATE TYPE detailcheckstatus AS ENUM ('PASS','FAIL','WARNING','BLOCKED','FEM_REQUIRED','NOT_APPLICABLE')")
    op.execute("CREATE TYPE weldprocess AS ENUM ('SMAW','GMAW','GTAW','SAW','FSW')")
    op.execute("CREATE TYPE weldinspection AS ENUM ('VT','PT','MT','UT','RT')")
    op.execute("CREATE TYPE equipmentcategory AS ENUM ('DRIVER','BATTERY','SMARTEC_NODE','TERMINAL_BLOCK','PROTECTION','AUXILIARY')")
    op.execute("CREATE TYPE feastatus AS ENUM ('PENDING','RUNNING','CONVERGED','FAILED','NOT_REQUIRED')")
    op.execute("CREATE TYPE detailreleaselevel AS ENUM ('M0','M1','M2','M3','M4')")
    op.execute("CREATE TYPE openingstatus AS ENUM ('DRAFT','VALIDATED','OPTIMIZED','RELEASED','BLOCKED')")

    # ── opening_definition ───────────────────────────────────────────────────
    op.create_table(
        "opening_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opening_type", postgresql.ENUM("RECTANGULAR","RECTANGULAR_ROUNDED","OVAL","CABLE_SLOT","VENTILATION","DRAIN","CUSTOM", name="openingtype", create_type=False), nullable=False),
        sa.Column("geometric_level", postgresql.ENUM("G0","G1","G2","G3","G4", name="openinggeometriclevel", create_type=False), nullable=False, server_default="G1"),
        sa.Column("route", postgresql.ENUM("R8_A","R8_B","R8_C","R8_D","R8_E", name="detailroute", create_type=False)),
        sa.Column("status", postgresql.ENUM("DRAFT","VALIDATED","OPTIMIZED","RELEASED","BLOCKED", name="openingstatus", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("station_bottom_m", sa.Float, nullable=False),
        sa.Column("station_top_m", sa.Float, nullable=False),
        sa.Column("width_mm", sa.Float, nullable=False),
        sa.Column("height_mm", sa.Float, nullable=False),
        sa.Column("corner_radius_mm", sa.Float, server_default="0.0"),
        sa.Column("orientation_deg", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("tol_width_mm", sa.Float, server_default="1.0"),
        sa.Column("tol_height_mm", sa.Float, server_default="1.0"),
        sa.Column("tol_position_mm", sa.Float, server_default="2.0"),
        sa.Column("tol_corner_radius_mm", sa.Float, server_default="0.5"),
        sa.Column("D_ext_mm", sa.Float),
        sa.Column("t_wall_mm", sa.Float),
        sa.Column("geometric_hash", sa.String(64)),
        sa.Column("rules_hash", sa.String(64)),
        sa.Column("extra_json", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_opening_design", "opening_definition", ["design_id"])

    # ── reinforcement_definition ─────────────────────────────────────────────
    op.create_table(
        "reinforcement_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family", postgresql.ENUM("FRAME","TWO_VERTICALS","VERTICALS_CROSSBARS","WRAPPING_PLATE","RING","EXTRUSION","HYBRID", name="reinforcementfamily", create_type=False), nullable=False),
        sa.Column("material_code", sa.String(64), nullable=False),
        sa.Column("thickness_mm", sa.Float, nullable=False),
        sa.Column("width_mm", sa.Float),
        sa.Column("depth_mm", sa.Float),
        sa.Column("extension_top_mm", sa.Float, server_default="0.0"),
        sa.Column("extension_bottom_mm", sa.Float, server_default="0.0"),
        sa.Column("offset_mm", sa.Float, server_default="0.0"),
        sa.Column("geometry_json", postgresql.JSONB, server_default="{}"),
        sa.Column("weld_process", postgresql.ENUM("SMAW","GMAW","GTAW","SAW","FSW", name="weldprocess", create_type=False)),
        sa.Column("cost_eur", sa.Float),
        sa.Column("mass_kg", sa.Float),
        sa.Column("co2_kg", sa.Float),
        sa.Column("feasible", sa.Boolean, server_default="true"),
        sa.Column("pareto_dominated", sa.Boolean),
        sa.Column("rejection_reason", sa.String(256)),
        sa.Column("design_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opening_id"], ["opening_definition.id"], ondelete="CASCADE"),
    )

    # ── local_section_result ─────────────────────────────────────────────────
    op.create_table(
        "local_section_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.String(64), nullable=False),
        sa.Column("include_reinforcement", sa.Boolean, server_default="false"),
        sa.Column("A_gross_m2", sa.Float),
        sa.Column("Iy_gross_m4", sa.Float),
        sa.Column("Iz_gross_m4", sa.Float),
        sa.Column("A_net_m2", sa.Float),
        sa.Column("centroid_x_m", sa.Float),
        sa.Column("centroid_y_m", sa.Float),
        sa.Column("Iy_net_m4", sa.Float),
        sa.Column("Iz_net_m4", sa.Float),
        sa.Column("Iyz_net_m4", sa.Float),
        sa.Column("J_net_m4", sa.Float),
        sa.Column("Cw_m6", sa.Float),
        sa.Column("alpha_principal_deg", sa.Float),
        sa.Column("I1_m4", sa.Float),
        sa.Column("I2_m4", sa.Float),
        sa.Column("Wel_y_m3", sa.Float),
        sa.Column("Wel_z_m3", sa.Float),
        sa.Column("contrast_delta_pct", sa.Float),
        sa.Column("contrast_passed", sa.Boolean),
        sa.Column("status", postgresql.ENUM("PASS","FAIL","WARNING","BLOCKED","FEM_REQUIRED","NOT_APPLICABLE", name="detailcheckstatus", create_type=False), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.Column("run_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opening_id"], ["opening_definition.id"], ondelete="CASCADE"),
    )

    # ── local_check_result ───────────────────────────────────────────────────
    op.create_table(
        "local_check_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(32)),
        sa.Column("check_type", sa.String(64), nullable=False),
        sa.Column("demand", sa.Float, nullable=False),
        sa.Column("resistance", sa.Float, nullable=False),
        sa.Column("utilization", sa.Float, nullable=False),
        sa.Column("unit", sa.String(32)),
        sa.Column("status", postgresql.ENUM("PASS","FAIL","WARNING","BLOCKED","FEM_REQUIRED","NOT_APPLICABLE", name="detailcheckstatus", create_type=False), nullable=False),
        sa.Column("governing_rule", sa.String(256)),
        sa.Column("intermediate_values_json", postgresql.JSONB, server_default="{}"),
        sa.Column("equation_trace_json", postgresql.JSONB, server_default="{}"),
        sa.Column("error_code", sa.String(32)),
        sa.Column("run_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opening_id"], ["opening_definition.id"], ondelete="CASCADE"),
    )

    # ── weld_group ───────────────────────────────────────────────────────────
    op.create_table(
        "weld_group",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reinforcement_id", postgresql.UUID(as_uuid=True)),
        sa.Column("group_label", sa.String(64)),
        sa.Column("segment_count", sa.Integer),
        sa.Column("total_length_mm", sa.Float, nullable=False),
        sa.Column("throat_mm", sa.Float, nullable=False),
        sa.Column("weld_process", postgresql.ENUM("SMAW","GMAW","GTAW","SAW","FSW", name="weldprocess", create_type=False), nullable=False),
        sa.Column("fatigue_category", sa.String(16)),
        sa.Column("inspection_level", postgresql.ENUM("VT","PT","MT","UT","RT", name="weldinspection", create_type=False)),
        sa.Column("centroid_json", postgresql.JSONB, server_default="{}"),
        sa.Column("Ip_polar_mm4", sa.Float),
        sa.Column("force_direct_n_mm", sa.Float),
        sa.Column("force_torsion_n_mm", sa.Float),
        sa.Column("f_res_max_n_mm", sa.Float),
        sa.Column("capacity_n_mm", sa.Float),
        sa.Column("utilization", sa.Float),
        sa.Column("status", postgresql.ENUM("PASS","FAIL","WARNING","BLOCKED","FEM_REQUIRED","NOT_APPLICABLE", name="detailcheckstatus", create_type=False)),
        sa.Column("governing_rule", sa.String(128)),
        sa.Column("run_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opening_id"], ["opening_definition.id"], ondelete="CASCADE"),
    )

    # ── equipment_item ───────────────────────────────────────────────────────
    op.create_table(
        "equipment_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_type", postgresql.ENUM("DRIVER","BATTERY","SMARTEC_NODE","TERMINAL_BLOCK","PROTECTION","AUXILIARY", name="equipmentcategory", create_type=False), nullable=False),
        sa.Column("reference", sa.String(128)),
        sa.Column("description", sa.Text),
        sa.Column("length_mm", sa.Float, nullable=False),
        sa.Column("width_mm", sa.Float, nullable=False),
        sa.Column("height_mm", sa.Float, nullable=False),
        sa.Column("mass_kg", sa.Float, nullable=False),
        sa.Column("cg_json", postgresql.JSONB, server_default="{}"),
        sa.Column("interfaces_json", postgresql.JSONB, server_default="{}"),
        sa.Column("service_volume_json", postgresql.JSONB, server_default="{}"),
        sa.Column("extraction_volume_json", postgresql.JSONB, server_default="{}"),
        sa.Column("ip_rating", sa.String(8)),
        sa.Column("ik_rating", sa.String(8)),
        sa.Column("max_temperature_c", sa.Float),
        sa.Column("min_temperature_c", sa.Float),
        sa.Column("max_load_kn", sa.Float),
        sa.Column("vibration_class", sa.String(16)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── support_layout ───────────────────────────────────────────────────────
    op.create_table(
        "support_layout",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_ids_json", postgresql.JSONB, server_default="[]"),
        sa.Column("plate_type", sa.String(64)),
        sa.Column("rail_type", sa.String(64)),
        sa.Column("fastener_pattern_json", postgresql.JSONB, server_default="{}"),
        sa.Column("loads_json", postgresql.JSONB, server_default="{}"),
        sa.Column("accessible", sa.Boolean),
        sa.Column("tool_clearance_ok", sa.Boolean),
        sa.Column("cable_radius_ok", sa.Boolean),
        sa.Column("extraction_sequence_json", postgresql.JSONB, server_default="[]"),
        sa.Column("status", postgresql.ENUM("PASS","FAIL","WARNING","BLOCKED","FEM_REQUIRED","NOT_APPLICABLE", name="detailcheckstatus", create_type=False)),
        sa.Column("error_code", sa.String(32)),
        sa.Column("run_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opening_id"], ["opening_definition.id"], ondelete="CASCADE"),
    )

    # ── fea_local_model ──────────────────────────────────────────────────────
    op.create_table(
        "fea_local_model",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("mesh_hash", sa.String(64)),
        sa.Column("bc_json", postgresql.JSONB, server_default="{}"),
        sa.Column("material_model", sa.String(32)),
        sa.Column("activation_reason", sa.String(256)),
        sa.Column("convergence_ratio", sa.Float),
        sa.Column("equilibrium_residual_pct", sa.Float),
        sa.Column("max_stress_mpa", sa.Float),
        sa.Column("max_hotspot_stress_mpa", sa.Float),
        sa.Column("max_deformation_mm", sa.Float),
        sa.Column("buckling_factor", sa.Float),
        sa.Column("analytic_ref_stress_mpa", sa.Float),
        sa.Column("comparison_delta_pct", sa.Float),
        sa.Column("status", postgresql.ENUM("PENDING","RUNNING","CONVERGED","FAILED","NOT_REQUIRED", name="feastatus", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("error_code", sa.String(32)),
        sa.Column("run_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opening_id"], ["opening_definition.id"], ondelete="CASCADE"),
    )

    # ── detail_family ────────────────────────────────────────────────────────
    op.create_table(
        "detail_family",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("family_code", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("opening_type", postgresql.ENUM("RECTANGULAR","RECTANGULAR_ROUNDED","OVAL","CABLE_SLOT","VENTILATION","DRAIN","CUSTOM", name="openingtype", create_type=False)),
        sa.Column("reinforcement_family", postgresql.ENUM("FRAME","TWO_VERTICALS","VERTICALS_CROSSBARS","WRAPPING_PLATE","RING","EXTRUSION","HYBRID", name="reinforcementfamily", create_type=False)),
        sa.Column("domain_json", postgresql.JSONB, server_default="{}"),
        sa.Column("test_references_json", postgresql.JSONB, server_default="[]"),
        sa.Column("modifications_allowed_json", postgresql.JSONB, server_default="[]"),
        sa.Column("status", sa.String(32), server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── detail_release ───────────────────────────────────────────────────────
    op.create_table(
        "detail_release",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opening_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("release_level", postgresql.ENUM("M0","M1","M2","M3","M4", name="detailreleaselevel", create_type=False), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("input_hashes_json", postgresql.JSONB, server_default="{}"),
        sa.Column("all_checks_passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approved_by", sa.String(256)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("documents_json", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opening_id"], ["opening_definition.id"], ondelete="CASCADE"),
    )

    # ── índices ──────────────────────────────────────────────────────────────
    op.create_index("ix_local_check_opening", "local_check_result", ["opening_id"])
    op.create_index("ix_weld_group_opening", "weld_group", ["opening_id"])


def downgrade() -> None:
    op.drop_table("detail_release")
    op.drop_table("detail_family")
    op.drop_table("fea_local_model")
    op.drop_table("support_layout")
    op.drop_table("equipment_item")
    op.drop_table("weld_group")
    op.drop_table("local_check_result")
    op.drop_table("local_section_result")
    op.drop_table("reinforcement_definition")
    op.drop_table("opening_definition")
    for enum in ["openingstatus","detailreleaselevel","feastatus","equipmentcategory",
                 "weldinspection","weldprocess","detailcheckstatus","reinforcementfamily",
                 "detailroute","openinggeometriclevel","openingtype"]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
