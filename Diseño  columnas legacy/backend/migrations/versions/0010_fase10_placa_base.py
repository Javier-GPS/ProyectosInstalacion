"""
Fase 10 · Placa Base, Pernos y Anclajes
Alembic migration: enums + tables

Revision ID: 0010
Down revision: 0009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Enums
    # -----------------------------------------------------------------------
    assemblystatus10 = postgresql.ENUM(
        "DRAFT", "PRELIMINARY", "VERIFIED", "APPROVED", "SUPERSEDED",
        name="assemblystatus10", create_type=True
    )
    bplatematurity = postgresql.ENUM(
        "V0", "V1", "V2", "V3", "V4",
        name="bplatematurity", create_type=True
    )
    anchorfamily10 = postgresql.ENUM(
        "EMBEDDED", "POST_INSTALLED",
        name="anchorfamily10", create_type=True
    )
    platepatterntype = postgresql.ENUM(
        "200x200", "250x250", "300x300",
        "CIRCULAR_4", "CIRCULAR_6", "CIRCULAR_8",
        "RECTANGULAR", "SPECIAL",
        name="platepatterntype", create_type=True
    )
    platedesignmethod = postgresql.ENUM(
        "P0_RIGID", "P1_CANTILEVER", "P2_YIELD_LINE", "P3_FEM_SHELL", "P4_FEM_SOLID",
        name="platedesignmethod", create_type=True
    )
    contactstate10 = postgresql.ENUM(
        "FULL", "PARTIAL", "BIAXIAL_SECTORS", "LOCAL_OPENING",
        name="contactstate10", create_type=True
    )
    shearmechanism10 = postgresql.ENUM(
        "FRICTION", "BOLT_BEARING", "PLATE_BEARING", "SHEAR_KEY", "COMBINED",
        name="shearmechanism10", create_type=True
    )
    anchorrodtype10 = postgresql.ENUM(
        "L", "J", "STRAIGHT",
        name="anchorrodtype10", create_type=True
    )
    postinstalledtype10 = postgresql.ENUM(
        "MECHANICAL_EXPANSION", "UNDERCUT", "CHEMICAL_THREADED",
        "CHEMICAL_SPECIAL", "HYBRID_SLEEVE",
        name="postinstalledtype10", create_type=True
    )
    concretecondition10 = postgresql.ENUM(
        "CRACKED", "UNCRACKED",
        name="concretecondition10", create_type=True
    )
    grouttype10 = postgresql.ENUM(
        "CONTINUOUS_MORTAR", "LEVELING_NUTS_THEN_GROUT",
        "PERMANENT_PACKERS", "DRY_PACK", "SPECIAL_NO_GROUT",
        name="grouttype10", create_type=True
    )
    concretefailuremode10 = postgresql.ENUM(
        "CONCRETE_CONE", "PULL_OUT", "SPLITTING", "BLOW_OUT",
        "PRY_OUT", "EDGE_SHEAR", "BOND", "LOCAL_CRUSHING",
        name="concretefailuremode10", create_type=True
    )
    mkthomostat10 = postgresql.ENUM(
        "HOMOLOGATED", "PENDING", "EXPIRED", "REJECTED",
        name="mkthomostat10", create_type=True
    )
    # Market reference uses separate enum instances to avoid collision
    anchorfamily10_mkt = postgresql.ENUM(
        "EMBEDDED", "POST_INSTALLED",
        name="anchorfamily10_mkt", create_type=True
    )
    postinstalledtype10_mkt = postgresql.ENUM(
        "MECHANICAL_EXPANSION", "UNDERCUT", "CHEMICAL_THREADED",
        "CHEMICAL_SPECIAL", "HYBRID_SLEEVE",
        name="postinstalledtype10_mkt", create_type=True
    )
    concretecondition10_mkt = postgresql.ENUM(
        "CRACKED", "UNCRACKED",
        name="concretecondition10_mkt", create_type=True
    )

    for e in [
        assemblystatus10, bplatematurity, anchorfamily10, platepatterntype,
        platedesignmethod, contactstate10, shearmechanism10, anchorrodtype10,
        postinstalledtype10, concretecondition10, grouttype10, concretefailuremode10,
        mkthomostat10, anchorfamily10_mkt, postinstalledtype10_mkt, concretecondition10_mkt,
    ]:
        e.create(op.get_bind(), checkfirst=True)

    # -----------------------------------------------------------------------
    # Tables
    # -----------------------------------------------------------------------

    # 1. base_assembly
    op.create_table(
        "base_assembly",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", postgresql.ENUM(name="assemblystatus10", create_type=False), nullable=False),
        sa.Column("maturity_level", postgresql.ENUM(name="bplatematurity", create_type=False), nullable=False),
        sa.Column("anchor_family", postgresql.ENUM(name="anchorfamily10", create_type=False), nullable=False),
        sa.Column("pattern_type", postgresql.ENUM(name="platepatterntype", create_type=False), nullable=False),
        sa.Column("N_kn", sa.Float, nullable=False, server_default="0"),
        sa.Column("Vy_kn", sa.Float, nullable=False, server_default="0"),
        sa.Column("Vz_kn", sa.Float, nullable=False, server_default="0"),
        sa.Column("T_knm", sa.Float, nullable=False, server_default="0"),
        sa.Column("My_knm", sa.Float, nullable=False, server_default="0"),
        sa.Column("Mz_knm", sa.Float, nullable=False, server_default="0"),
        sa.Column("governing_combination", sa.String(64), nullable=True),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("calc_hash", sa.String(64), nullable=True),
        sa.Column("solver_version", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("project_id", "code", name="uq_baseassembly_project_code"),
    )
    op.create_index("ix_baseassembly_project_id", "base_assembly", ["project_id"])

    # 2. base_plate
    op.create_table(
        "base_plate",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shape", sa.String(32), nullable=False, server_default="RECTANGULAR"),
        sa.Column("width_mm", sa.Float, nullable=False),
        sa.Column("length_mm", sa.Float, nullable=False),
        sa.Column("thickness_mm", sa.Float, nullable=False),
        sa.Column("material_grade", sa.String(16), nullable=False, server_default="S355"),
        sa.Column("fy_mpa", sa.Float, nullable=False, server_default="355"),
        sa.Column("fu_mpa", sa.Float, nullable=False, server_default="470"),
        sa.Column("design_method", postgresql.ENUM(name="platedesignmethod", create_type=False), nullable=False),
        sa.Column("overhang_x_mm", sa.Float, nullable=True),
        sa.Column("overhang_y_mm", sa.Float, nullable=True),
        sa.Column("hole_diameter_mm", sa.Float, nullable=True),
        sa.Column("hole_count", sa.Integer, nullable=True),
        sa.Column("planarity_tolerance_mm", sa.Float, nullable=True),
        sa.Column("mass_kg", sa.Float, nullable=True),
        sa.Column("is_recommended", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("util_plate", sa.Float, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_baseplate_assembly_id", "base_plate", ["assembly_id"])

    # 3. stiffener
    op.create_table(
        "stiffener",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_plate.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(32), nullable=True),
        sa.Column("height_mm", sa.Float, nullable=False),
        sa.Column("thickness_mm", sa.Float, nullable=False),
        sa.Column("length_mm", sa.Float, nullable=False),
        sa.Column("position_angle_deg", sa.Float, nullable=True),
        sa.Column("material_grade", sa.String(16), nullable=False, server_default="S355"),
        sa.Column("weld_throat_mm", sa.Float, nullable=True),
        sa.Column("util_stiffener", sa.Float, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_stiffener_plate_id", "stiffener", ["plate_id"])

    # 4. anchor_pattern
    op.create_table(
        "anchor_pattern",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("pattern_label", sa.String(32), nullable=False),
        sa.Column("bolt_count", sa.Integer, nullable=False),
        sa.Column("bolt_pcd_mm", sa.Float, nullable=True),
        sa.Column("bolt_x_mm", postgresql.JSONB, nullable=True),
        sa.Column("bolt_y_mm", postgresql.JSONB, nullable=True),
        sa.Column("orientation_deg", sa.Float, nullable=False, server_default="0"),
        sa.Column("position_tolerance_mm", sa.Float, nullable=True),
        sa.Column("cage_drawing_ref", sa.String(128), nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )

    # 5. anchor_rod
    op.create_table(
        "anchor_rod",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pattern_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("anchor_pattern.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rod_index", sa.Integer, nullable=False),
        sa.Column("rod_type", postgresql.ENUM(name="anchorrodtype10", create_type=False), nullable=False),
        sa.Column("material_grade", sa.String(16), nullable=False),
        sa.Column("nominal_diameter_mm", sa.Float, nullable=False),
        sa.Column("thread_pitch_mm", sa.Float, nullable=True),
        sa.Column("effective_thread_area_mm2", sa.Float, nullable=True),
        sa.Column("total_length_mm", sa.Float, nullable=False),
        sa.Column("embedment_depth_mm", sa.Float, nullable=False),
        sa.Column("hook_length_mm", sa.Float, nullable=True),
        sa.Column("hook_radius_mm", sa.Float, nullable=True),
        sa.Column("end_plate_diameter_mm", sa.Float, nullable=True),
        sa.Column("free_length_mm", sa.Float, nullable=True),
        sa.Column("fy_mpa", sa.Float, nullable=False),
        sa.Column("fu_mpa", sa.Float, nullable=False),
        sa.Column("coating", sa.String(64), nullable=True),
        sa.Column("util_tension", sa.Float, nullable=True),
        sa.Column("util_shear", sa.Float, nullable=True),
        sa.Column("util_interaction", sa.Float, nullable=True),
        sa.Column("axial_stiffness_kn_mm", sa.Float, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_anchorrod_pattern_id", "anchor_rod", ["pattern_id"])

    # 6. post_installed_anchor
    op.create_table(
        "post_installed_anchor",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anchor_index", sa.Integer, nullable=False),
        sa.Column("post_type", postgresql.ENUM(name="postinstalledtype10", create_type=False), nullable=False),
        sa.Column("manufacturer", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(128), nullable=False),
        sa.Column("eta_document", sa.String(128), nullable=False),
        sa.Column("eta_edition", sa.String(32), nullable=True),
        sa.Column("nominal_diameter_mm", sa.Float, nullable=False),
        sa.Column("drill_diameter_mm", sa.Float, nullable=False),
        sa.Column("embedment_depth_mm", sa.Float, nullable=False),
        sa.Column("concrete_condition", postgresql.ENUM(name="concretecondition10", create_type=False), nullable=False),
        sa.Column("fck_mpa", sa.Float, nullable=False),
        sa.Column("temperature_max_c", sa.Float, nullable=True),
        sa.Column("installation_torque_nm", sa.Float, nullable=True),
        sa.Column("cure_time_hours", sa.Float, nullable=True),
        sa.Column("NRd_c_kn", sa.Float, nullable=True),
        sa.Column("NRd_p_kn", sa.Float, nullable=True),
        sa.Column("VRd_c_kn", sa.Float, nullable=True),
        sa.Column("util_tension", sa.Float, nullable=True),
        sa.Column("util_shear", sa.Float, nullable=True),
        sa.Column("util_interaction", sa.Float, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_postinstalled_assembly_id", "post_installed_anchor", ["assembly_id"])

    # 7. nut_washer_set
    op.create_table(
        "nut_washer_set",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rod_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("anchor_rod.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("nut_grade", sa.String(16), nullable=False),
        sa.Column("washer_od_mm", sa.Float, nullable=True),
        sa.Column("washer_thickness_mm", sa.Float, nullable=True),
        sa.Column("lock_nut", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("coating", sa.String(64), nullable=True),
        sa.Column("torque_target_nm", sa.Float, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )

    # 8. grout_layer
    op.create_table(
        "grout_layer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("grout_type", postgresql.ENUM(name="grouttype10", create_type=False), nullable=False),
        sa.Column("product_name", sa.String(128), nullable=True),
        sa.Column("thickness_mm", sa.Float, nullable=False),
        sa.Column("fck_mortar_mpa", sa.Float, nullable=False),
        sa.Column("elastic_modulus_mpa", sa.Float, nullable=True),
        sa.Column("effective_area_mm2", sa.Float, nullable=True),
        sa.Column("sigma_Ed_mpa", sa.Float, nullable=True),
        sa.Column("sigma_Rd_mpa", sa.Float, nullable=True),
        sa.Column("util_bearing", sa.Float, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )

    # 9. shear_key
    op.create_table(
        "shear_key",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("shape", sa.String(32), nullable=False),
        sa.Column("width_mm", sa.Float, nullable=False),
        sa.Column("height_mm", sa.Float, nullable=False),
        sa.Column("depth_mm", sa.Float, nullable=False),
        sa.Column("eccentricity_mm", sa.Float, nullable=False),
        sa.Column("material_grade", sa.String(16), nullable=False),
        sa.Column("fy_mpa", sa.Float, nullable=False),
        sa.Column("weld_throat_mm", sa.Float, nullable=True),
        sa.Column("Vx_design_kn", sa.Float, nullable=True),
        sa.Column("Vy_design_kn", sa.Float, nullable=True),
        sa.Column("util_shear", sa.Float, nullable=True),
        sa.Column("util_bending", sa.Float, nullable=True),
        sa.Column("util_concrete", sa.Float, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )

    # 10. contact_solution
    op.create_table(
        "contact_solution",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False),
        sa.Column("combination_id", sa.String(64), nullable=False),
        sa.Column("contact_state", postgresql.ENUM(name="contactstate10", create_type=False), nullable=False),
        sa.Column("contact_area_mm2", sa.Float, nullable=True),
        sa.Column("sigma_max_mpa", sa.Float, nullable=True),
        sa.Column("sigma_avg_mpa", sa.Float, nullable=True),
        sa.Column("neutral_axis_dist_mm", sa.Float, nullable=True),
        sa.Column("max_bolt_tension_kn", sa.Float, nullable=True),
        sa.Column("max_bolt_shear_kn", sa.Float, nullable=True),
        sa.Column("iterations", sa.Integer, nullable=True),
        sa.Column("converged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("equilibrium_error", sa.Float, nullable=True),
        sa.Column("rotation_rad", sa.Float, nullable=True),
        sa.Column("horizontal_slip_mm", sa.Float, nullable=True),
        sa.Column("shear_mechanism", postgresql.ENUM(name="shearmechanism10", create_type=False), nullable=True),
        sa.Column("force_per_bolt", postgresql.JSONB, nullable=True),
        sa.Column("solver_version", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_contactsol_assembly_combination",
                    "contact_solution", ["assembly_id", "combination_id"])

    # 11. anchor_group_result
    op.create_table(
        "anchor_group_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False),
        sa.Column("combination_id", sa.String(64), nullable=False),
        sa.Column("bolt_index", sa.Integer, nullable=False),
        sa.Column("N_Ed_kn", sa.Float, nullable=False),
        sa.Column("V_Ed_kn", sa.Float, nullable=False),
        sa.Column("util_steel_tension", sa.Float, nullable=True),
        sa.Column("util_steel_shear", sa.Float, nullable=True),
        sa.Column("util_interaction", sa.Float, nullable=True),
        sa.Column("util_bending", sa.Float, nullable=True),
        sa.Column("util_governing", sa.Float, nullable=True),
        sa.Column("governing_mode", sa.String(64), nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_anchorgroupres_assembly", "anchor_group_result", ["assembly_id"])

    # 12. concrete_failure_result
    op.create_table(
        "concrete_failure_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False),
        sa.Column("combination_id", sa.String(64), nullable=False),
        sa.Column("failure_mode", postgresql.ENUM(name="concretefailuremode10", create_type=False), nullable=False),
        sa.Column("NEd_kn", sa.Float, nullable=True),
        sa.Column("VEd_kn", sa.Float, nullable=True),
        sa.Column("NRd_kn", sa.Float, nullable=True),
        sa.Column("VRd_kn", sa.Float, nullable=True),
        sa.Column("util", sa.Float, nullable=True),
        sa.Column("governing", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("edge_distances_mm", postgresql.JSONB, nullable=True),
        sa.Column("cone_geometry", postgresql.JSONB, nullable=True),
        sa.Column("factors", postgresql.JSONB, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_concretefail_assembly", "concrete_failure_result", ["assembly_id"])

    # 13. market_reference10
    op.create_table(
        "market_reference10",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manufacturer", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(128), nullable=False),
        sa.Column("product_code", sa.String(64), nullable=False, unique=True),
        sa.Column("anchor_family", postgresql.ENUM(name="anchorfamily10_mkt", create_type=False), nullable=False),
        sa.Column("post_type", postgresql.ENUM(name="postinstalledtype10_mkt", create_type=False), nullable=True),
        sa.Column("nominal_diameter_mm", sa.Float, nullable=False),
        sa.Column("embedment_range_mm", postgresql.JSONB, nullable=True),
        sa.Column("fck_range_mpa", postgresql.JSONB, nullable=True),
        sa.Column("concrete_condition", postgresql.ENUM(name="concretecondition10_mkt", create_type=False), nullable=True),
        sa.Column("eta_document", sa.String(128), nullable=True),
        sa.Column("eta_edition", sa.String(32), nullable=True),
        sa.Column("homologation_status", postgresql.ENUM(name="mkthomostat10", create_type=False), nullable=False),
        sa.Column("unit_price_eur", sa.Float, nullable=True),
        sa.Column("mass_kg", sa.Float, nullable=True),
        sa.Column("co2_kg_per_unit", sa.Float, nullable=True),
        sa.Column("country_of_origin", sa.String(8), nullable=True),
        sa.Column("lead_time_days", sa.Integer, nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_mktref10_anchor_family", "market_reference10", ["anchor_family"])

    # 14. foundation_interface
    op.create_table(
        "foundation_interface",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("base_assembly.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("N_max_kn", sa.Float, nullable=True),
        sa.Column("N_min_kn", sa.Float, nullable=True),
        sa.Column("Vx_max_kn", sa.Float, nullable=True),
        sa.Column("Vy_max_kn", sa.Float, nullable=True),
        sa.Column("T_max_knm", sa.Float, nullable=True),
        sa.Column("Mx_max_knm", sa.Float, nullable=True),
        sa.Column("My_max_knm", sa.Float, nullable=True),
        sa.Column("min_concrete_thickness_mm", sa.Float, nullable=True),
        sa.Column("min_edge_distance_x_mm", sa.Float, nullable=True),
        sa.Column("min_edge_distance_y_mm", sa.Float, nullable=True),
        sa.Column("min_fck_mpa", sa.Float, nullable=True),
        sa.Column("rebar_requirement", sa.String(256), nullable=True),
        sa.Column("cone_geometry_envelope", postgresql.JSONB, nullable=True),
        sa.Column("stiffness_matrix_6x6", postgresql.JSONB, nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=True),
        sa.Column("frozen_at", sa.DateTime, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("foundation_interface")
    op.drop_table("market_reference10")
    op.drop_table("concrete_failure_result")
    op.drop_table("anchor_group_result")
    op.drop_table("contact_solution")
    op.drop_table("shear_key")
    op.drop_table("grout_layer")
    op.drop_table("nut_washer_set")
    op.drop_table("post_installed_anchor")
    op.drop_table("anchor_rod")
    op.drop_table("anchor_pattern")
    op.drop_table("stiffener")
    op.drop_table("base_plate")
    op.drop_table("base_assembly")

    for enum_name in [
        "assemblystatus10", "bplatematurity", "anchorfamily10", "platepatterntype",
        "platedesignmethod", "contactstate10", "shearmechanism10", "anchorrodtype10",
        "postinstalledtype10", "concretecondition10", "grouttype10", "concretefailuremode10",
        "mkthomostat10", "anchorfamily10_mkt", "postinstalledtype10_mkt",
        "concretecondition10_mkt",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
