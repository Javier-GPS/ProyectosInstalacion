"""Fase 9: Uniones y Columnas Segmentadas

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-14
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enumeraciones ─────────────────────────────────────────────────────────
    joint_type_enum = postgresql.ENUM(
        "J9_TEL", "J9_BRI", "J9_SOL", "J9_MAN", "J9_HIB", "J9_HOR", "J9_ACC",
        name="jointtype", create_type=True,
    )
    joint_type_enum.create(op.get_bind(), checkfirst=True)

    segment_plan_status_enum = postgresql.ENUM(
        "DRAFT", "CANDIDATE", "OPTIMIZING", "VERIFIED", "RELEASED", "BLOCKED",
        name="segmentplanstatus", create_type=True,
    )
    segment_plan_status_enum.create(op.get_bind(), checkfirst=True)

    joint_stiffness_enum = postgresql.ENUM(
        "RIGID_IDEAL", "DECOUPLED_SPRINGS", "MATRIX_6X6",
        "NONLINEAR_CONTACT", "FEM_CONDENSED", "TEST_DERIVED",
        name="jointstiffnessmodel", create_type=True,
    )
    joint_stiffness_enum.create(op.get_bind(), checkfirst=True)

    telescopic_state_enum = postgresql.ENUM(
        "PRE_ASSEMBLY", "INSERTION", "SEATED", "SERVICE", "CYCLIC", "DECOMMISSION",
        name="telescopicstate", create_type=True,
    )
    telescopic_state_enum.create(op.get_bind(), checkfirst=True)

    flange_contact_enum = postgresql.ENUM(
        "FULLY_CLOSED", "PARTIALLY_OPEN", "FULLY_OPEN", "NOT_APPLICABLE",
        name="flangecontactstate", create_type=True,
    )
    flange_contact_enum.create(op.get_bind(), checkfirst=True)

    weld_process_enum = postgresql.ENUM(
        "SMAW", "GMAW", "GTAW", "SAW", "FSW",
        name="weldprocess9", create_type=True,
    )
    weld_process_enum.create(op.get_bind(), checkfirst=True)

    sleeve_type_enum = postgresql.ENUM(
        "INTERIOR", "EXTERIOR", "REPAIR", "TRANSITION",
        name="sleevetype", create_type=True,
    )
    sleeve_type_enum.create(op.get_bind(), checkfirst=True)

    hybrid_material_enum = postgresql.ENUM(
        "STEEL_ALUMINIUM", "STEEL_CONCRETE", "ALUMINIUM_CONCRETE",
        name="hybridmaterial", create_type=True,
    )
    hybrid_material_enum.create(op.get_bind(), checkfirst=True)

    assembly_stage_enum = postgresql.ENUM(
        "FACTORY_LOAD", "TRANSPORT", "UNLOAD", "PRE_ASSEMBLY",
        "ASSEMBLY", "LIFT", "INSTALLATION", "ACCEPTANCE",
        name="assemblystage", create_type=True,
    )
    assembly_stage_enum.create(op.get_bind(), checkfirst=True)

    maturity_enum = postgresql.ENUM(
        "V0", "V1", "V2", "V3", "V4", "V5",
        name="jointmaturitylevel", create_type=True,
    )
    maturity_enum.create(op.get_bind(), checkfirst=True)

    joint_check_status_enum = postgresql.ENUM(
        "PASS", "FAIL", "WARNING", "BLOCKED", "FEM_REQUIRED", "NOT_APPLICABLE",
        name="jointcheckstatus", create_type=True,
    )
    joint_check_status_enum.create(op.get_bind(), checkfirst=True)

    joint_release_enum = postgresql.ENUM(
        "M0", "M1", "M2", "M3", "M4",
        name="jointreleaselevel", create_type=True,
    )
    joint_release_enum.create(op.get_bind(), checkfirst=True)

    # ── segment_plan ──────────────────────────────────────────────────────────
    op.create_table(
        "segment_plan",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_route", sa.String(16), nullable=False),
        sa.Column("total_height_m", sa.Float, nullable=False),
        sa.Column("piece_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("max_piece_length_m", sa.Float, nullable=False, server_default="12.0"),
        sa.Column("objective", sa.String(32), nullable=False, server_default="min_cost"),
        sa.Column("constraints_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", postgresql.ENUM("DRAFT", "CANDIDATE", "OPTIMIZING", "VERIFIED",
                                    "RELEASED", "BLOCKED", name="segmentplanstatus", create_type=False),
                   nullable=False, server_default="DRAFT"),
        sa.Column("plan_hash", sa.String(64), nullable=True),
        sa.Column("rejected_reasons_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_segment_plan_design", "segment_plan", ["design_id"])
    op.create_index("ix_segment_plan_status", "segment_plan", ["status"])

    # ── segment ───────────────────────────────────────────────────────────────
    op.create_table(
        "segment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("segment_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("z_start_m", sa.Float, nullable=False),
        sa.Column("z_end_m", sa.Float, nullable=False),
        sa.Column("length_m", sa.Float, nullable=False),
        sa.Column("envelope_length_m", sa.Float, nullable=False),
        sa.Column("mass_kg", sa.Float, nullable=True),
        sa.Column("cg_z_m", sa.Float, nullable=True),
        sa.Column("section_start_json", postgresql.JSONB, nullable=True),
        sa.Column("section_end_json", postgresql.JSONB, nullable=True),
        sa.Column("seam_azimuth_deg", sa.Float, nullable=True, server_default="0.0"),
        sa.Column("handling_points_json", postgresql.JSONB, nullable=True),
        sa.Column("galvanizing_ok", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("transport_ok", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("weight_ok", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("error_codes_json", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_segment_plan_index", "segment", ["plan_id", "index"], unique=True)

    # ── joint ─────────────────────────────────────────────────────────────────
    op.create_table(
        "joint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("segment_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joint_type", postgresql.ENUM("J9_TEL", "J9_BRI", "J9_SOL", "J9_MAN",
                                         "J9_HIB", "J9_HOR", "J9_ACC", name="jointtype", create_type=False),
                   nullable=False),
        sa.Column("z_station_m", sa.Float, nullable=False),
        sa.Column("orientation_deg", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("stiffness_model", postgresql.ENUM("RIGID_IDEAL", "DECOUPLED_SPRINGS", "MATRIX_6X6",
                                              "NONLINEAR_CONTACT", "FEM_CONDENSED", "TEST_DERIVED",
                                              name="jointstiffnessmodel", create_type=False),
                   nullable=False, server_default="DECOUPLED_SPRINGS"),
        sa.Column("stiffness_matrix_json", postgresql.JSONB, nullable=True),
        sa.Column("design_actions_json", postgresql.JSONB, nullable=True),
        sa.Column("governing_combination", sa.String(64), nullable=True),
        sa.Column("verification_state", postgresql.ENUM("PASS", "FAIL", "WARNING", "BLOCKED",
                                                  "FEM_REQUIRED", "NOT_APPLICABLE",
                                                  name="jointcheckstatus", create_type=False),
                   nullable=False, server_default="NOT_APPLICABLE"),
        sa.Column("maturity_level", postgresql.ENUM("V0", "V1", "V2", "V3", "V4", "V5",
                                             name="jointmaturitylevel", create_type=False),
                   nullable=False, server_default="V0"),
        sa.Column("in_forbidden_zone", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("error_codes_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_joint_plan", "joint", ["plan_id"])
    op.create_index("ix_joint_type", "joint", ["joint_type"])

    # ── telescopic_joint ──────────────────────────────────────────────────────
    op.create_table(
        "telescopic_joint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("joint_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("joint.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overlap_nominal_mm", sa.Float, nullable=False),
        sa.Column("overlap_min_mm", sa.Float, nullable=False),
        sa.Column("overlap_max_mm", sa.Float, nullable=False),
        sa.Column("taper_male", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("taper_female", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("clearance_mm", sa.Float, nullable=True),
        sa.Column("interference_mm", sa.Float, nullable=True),
        sa.Column("ovalization_mm", sa.Float, nullable=True),
        sa.Column("friction_coeff_min", sa.Float, nullable=False, server_default="0.15"),
        sa.Column("friction_coeff_max", sa.Float, nullable=False, server_default="0.35"),
        sa.Column("friction_source", sa.String(128), nullable=True),
        sa.Column("insertion_force_target_kn", sa.Float, nullable=True),
        sa.Column("contact_bands_json", postgresql.JSONB, nullable=True),
        sa.Column("anti_rotation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("drain_ok", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("seal_type", sa.String(32), nullable=True),
        sa.Column("state", postgresql.ENUM("PRE_ASSEMBLY", "INSERTION", "SEATED", "SERVICE",
                                    "CYCLIC", "DECOMMISSION", name="telescopicstate", create_type=False),
                   nullable=False, server_default="SERVICE"),
        sa.Column("overlap_achieved_ok", sa.Boolean, nullable=True),
        sa.Column("sliding_uls_mm", sa.Float, nullable=True),
        sa.Column("sliding_sls_mm", sa.Float, nullable=True),
        sa.Column("fretting_fatigue_ok", sa.Boolean, nullable=True),
        sa.Column("robust_scenario_json", postgresql.JSONB, nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
    )

    # ── flanged_joint ─────────────────────────────────────────────────────────
    op.create_table(
        "flanged_joint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("joint_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("joint.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("flange_outer_d_mm", sa.Float, nullable=False),
        sa.Column("flange_inner_d_mm", sa.Float, nullable=False),
        sa.Column("flange_thickness_mm", sa.Float, nullable=False),
        sa.Column("bolt_count", sa.Integer, nullable=False),
        sa.Column("bolt_pcd_mm", sa.Float, nullable=False),
        sa.Column("bolt_class", sa.String(8), nullable=False, server_default="8.8"),
        sa.Column("bolt_diameter_mm", sa.Float, nullable=False),
        sa.Column("bolt_grip_length_mm", sa.Float, nullable=True),
        sa.Column("pretensioned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("target_pretension_kn", sa.Float, nullable=True),
        sa.Column("tightening_method", sa.String(32), nullable=True),
        sa.Column("tightening_torque_nm", sa.Float, nullable=True),
        sa.Column("stiffener_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("contact_state", postgresql.ENUM("FULLY_CLOSED", "PARTIALLY_OPEN",
                                            "FULLY_OPEN", "NOT_APPLICABLE",
                                            name="flangecontactstate", create_type=False),
                   nullable=False, server_default="NOT_APPLICABLE"),
        sa.Column("prying_amplification", sa.Float, nullable=True),
        sa.Column("bolt_max_tension_kn", sa.Float, nullable=True),
        sa.Column("bolt_utilization_max", sa.Float, nullable=True),
        sa.Column("flange_utilization_max", sa.Float, nullable=True),
        sa.Column("sliding_ok", sa.Boolean, nullable=True),
        sa.Column("moment_rotation_json", postgresql.JSONB, nullable=True),
        sa.Column("fatigue_ok", sa.Boolean, nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
    )

    # ── welded_joint ──────────────────────────────────────────────────────────
    op.create_table(
        "welded_joint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("joint_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("joint.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("weld_process", postgresql.ENUM("SMAW", "GMAW", "GTAW", "SAW", "FSW",
                                           name="weldprocess9", create_type=False), nullable=False, server_default="GMAW"),
        sa.Column("joint_configuration", sa.String(32), nullable=False,
                   server_default="butt_full_penetration"),
        sa.Column("edge_prep", sa.String(64), nullable=True),
        sa.Column("throat_mm", sa.Float, nullable=True),
        sa.Column("weld_category", sa.String(4), nullable=True),
        sa.Column("field_weld", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("field_weld_approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("wps_reference", sa.String(64), nullable=True),
        sa.Column("ndt_method", sa.String(32), nullable=True),
        sa.Column("misalignment_mm", sa.Float, nullable=True),
        sa.Column("distortion_tolerance_mm", sa.Float, nullable=True),
        sa.Column("static_utilization", sa.Float, nullable=True),
        sa.Column("fatigue_utilization", sa.Float, nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
    )

    # ── sleeve_joint ──────────────────────────────────────────────────────────
    op.create_table(
        "sleeve_joint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("joint_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("joint.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("sleeve_type", postgresql.ENUM("INTERIOR", "EXTERIOR", "REPAIR", "TRANSITION",
                                          name="sleevetype", create_type=False), nullable=False),
        sa.Column("length_mm", sa.Float, nullable=False),
        sa.Column("outer_d_mm", sa.Float, nullable=False),
        sa.Column("inner_d_mm", sa.Float, nullable=False),
        sa.Column("attachment_method", sa.String(32), nullable=False),
        sa.Column("stop_provided", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("anti_rotation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("drain_ok", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("transfer_length_ok", sa.Boolean, nullable=True),
        sa.Column("torsion_ok", sa.Boolean, nullable=True),
        sa.Column("fatigue_edge_ok", sa.Boolean, nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
    )

    # ── hybrid_interface ──────────────────────────────────────────────────────
    op.create_table(
        "hybrid_interface",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("joint_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("joint.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("hybrid_type", postgresql.ENUM("STEEL_ALUMINIUM", "STEEL_CONCRETE",
                                          "ALUMINIUM_CONCRETE", name="hybridmaterial", create_type=False),
                   nullable=False),
        sa.Column("isolator_type", sa.String(64), nullable=True),
        sa.Column("isolator_thickness_mm", sa.Float, nullable=True),
        sa.Column("galvanic_area_ratio", sa.Float, nullable=True),
        sa.Column("thermal_delta_k", sa.Float, nullable=True),
        sa.Column("thermal_stress_mpa", sa.Float, nullable=True),
        sa.Column("isolator_continuous", sa.Boolean, nullable=True),
        sa.Column("drain_ok", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("galvanic_ok", sa.Boolean, nullable=True),
        sa.Column("thermal_ok", sa.Boolean, nullable=True),
        sa.Column("concrete_bearing_stress_mpa", sa.Float, nullable=True),
        sa.Column("concrete_bearing_ok", sa.Boolean, nullable=True),
        sa.Column("grout_hardened", sa.Boolean, nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
    )

    # ── assembly_operation ────────────────────────────────────────────────────
    op.create_table(
        "assembly_operation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("joint_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("joint.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", postgresql.ENUM("FACTORY_LOAD", "TRANSPORT", "UNLOAD", "PRE_ASSEMBLY",
                                    "ASSEMBLY", "LIFT", "INSTALLATION", "ACCEPTANCE",
                                    name="assemblystage", create_type=False), nullable=False),
        sa.Column("sequence_index", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("tools_json", postgresql.JSONB, nullable=True),
        sa.Column("force_target_kn", sa.Float, nullable=True),
        sa.Column("torque_target_nm", sa.Float, nullable=True),
        sa.Column("tolerance_json", postgresql.JSONB, nullable=True),
        sa.Column("hold_point", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("evidence_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accessible", sa.Boolean, nullable=True),
        sa.Column("operadores_count", sa.Integer, nullable=True, server_default="1"),
        sa.Column("error_codes_json", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_assembly_joint_seq", "assembly_operation", ["joint_id", "sequence_index"])

    # ── inspection_point ──────────────────────────────────────────────────────
    op.create_table(
        "inspection_point",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("joint_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("joint.id", ondelete="CASCADE"), nullable=False),
        sa.Column("characteristic", sa.String(128), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("sample_description", sa.Text, nullable=True),
        sa.Column("acceptance_criteria", sa.Text, nullable=False),
        sa.Column("criticality", sa.String(8), nullable=False, server_default="B"),
        sa.Column("evidence_path", sa.Text, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=True),
    )

    # ── joint_optimization_run ────────────────────────────────────────────────
    op.create_table(
        "joint_optimization_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("segment_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidates_count", sa.Integer, nullable=True),
        sa.Column("pareto_count", sa.Integer, nullable=True),
        sa.Column("weights_json", postgresql.JSONB, nullable=True),
        sa.Column("min_cost_candidate_json", postgresql.JSONB, nullable=True),
        sa.Column("min_weight_candidate_json", postgresql.JSONB, nullable=True),
        sa.Column("min_co2_candidate_json", postgresql.JSONB, nullable=True),
        sa.Column("balanced_candidate_json", postgresql.JSONB, nullable=True),
        sa.Column("discarded_reasons_json", postgresql.JSONB, nullable=True),
        sa.Column("run_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_joint_opt_plan", "joint_optimization_run", ["plan_id"])


def downgrade() -> None:
    op.drop_table("joint_optimization_run")
    op.drop_table("inspection_point")
    op.drop_table("assembly_operation")
    op.drop_table("hybrid_interface")
    op.drop_table("sleeve_joint")
    op.drop_table("welded_joint")
    op.drop_table("flanged_joint")
    op.drop_table("telescopic_joint")
    op.drop_table("joint")
    op.drop_table("segment")
    op.drop_table("segment_plan")

    for name in ["jointtype", "segmentplanstatus", "jointstiffnessmodel", "telescopicstate",
                  "flangecontactstate", "weldprocess9", "sleevetype", "hybridmaterial",
                  "assemblystage", "jointmaturitylevel", "jointcheckstatus", "jointreleaselevel"]:
        op.execute(f"DROP TYPE IF EXISTS {name}")
