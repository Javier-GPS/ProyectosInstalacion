"""Fase 7: Hormigón Pretensado — tablas de diseño, pérdidas, verificación, optimización.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-13
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE concretecementclass AS ENUM ('R','N','S','SL')")
    op.execute("CREATE TYPE concreteexposureclass AS ENUM ('X0','XC1','XC2','XC3','XC4','XD1','XD2','XD3','XS1','XS2','XS3','XF1','XF2','XF3','XF4','XA1','XA2','XA3')")
    op.execute("CREATE TYPE prestressingsteelclass AS ENUM ('CLASS_1','CLASS_2')")
    op.execute("CREATE TYPE prestressingelementtype AS ENUM ('WIRE','STRAND_3W','STRAND_7W','BAR')")
    op.execute("CREATE TYPE prestresslostype AS ENUM ('ANCHOR_SLIP','ELASTIC_SHORTENING','SHORT_TERM_RELAXATION','THERMAL_GRADIENT','BED_DEFORMATION','SHRINKAGE','CREEP','LONG_TERM_RELAXATION','COMBINED_CSR')")
    op.execute("CREATE TYPE productionstage_code AS ENUM ('S0','S1','S2','S3','S4','S5','S6','S7')")
    op.execute("CREATE TYPE limitstate AS ENUM ('SLS_COMPRESSION','SLS_TENSION','SLS_DECOMPRESSION','SLS_CRACKING','SLS_DEFLECTION','SLS_VIBRATION','ULS_BENDING','ULS_SHEAR','ULS_TORSION','ULS_INTERACTION','ULS_STABILITY','FATIGUE_STRAND','FATIGUE_CONCRETE','FATIGUE_PASSIVE','TRANSFER_SPLITTING','TRANSFER_COMPRESSION')")
    op.execute("CREATE TYPE concreteverificationstatus AS ENUM ('PASS','FAIL','WARNING','BLOCKED','NOT_APPLICABLE')")
    op.execute("CREATE TYPE concretenormativeroute AS ENUM ('EN40','EN40_EC2','SPECIAL','BLOCKED')")
    op.execute("CREATE TYPE concretedesignstatus AS ENUM ('DRAFT','COMPUTING','READY','APPROVED','ARCHIVED','BLOCKED')")
    op.execute("CREATE TYPE optimizationobjective AS ENUM ('MIN_COST','MIN_WEIGHT','MIN_CO2','MAX_ROBUSTNESS','BALANCED')")
    op.execute("CREATE TYPE concretematerialstatus AS ENUM ('DRAFT','VALIDATED','PUBLISHED','DEPRECATED')")
    op.execute("CREATE TYPE concretereporttype AS ENUM ('SUMMARY','FULL','FABRICATION','QUALITY')")
    op.execute("CREATE TYPE inserttype AS ENUM ('LUMINAIRE_ARM','GROUND_LATCH','CABLE_ENTRY','EARTH_BOLT','INSPECTION_DOOR')")
    op.execute("CREATE TYPE spincurvestatus AS ENUM ('PENDING','VALIDATED','APPROVED','DEPRECATED')")

    # ── concrete_mix_version ─────────────────────────────────────────────────
    op.create_table(
        "concrete_mix_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mix_code", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("fck", sa.Float, nullable=False),
        sa.Column("fcm", sa.Float, nullable=False),
        sa.Column("fctm", sa.Float, nullable=False),
        sa.Column("Ecm", sa.Float, nullable=False),
        sa.Column("s_cement", sa.Float, nullable=False),
        sa.Column("cement_class", postgresql.ENUM("R","N","S","SL", name="concretecementclass", create_type=False), nullable=False),
        sa.Column("epsilon_ca_inf", sa.Float, nullable=False, server_default="50.0"),
        sa.Column("epsilon_cd_0", sa.Float),
        sa.Column("phi_ref", sa.Float),
        sa.Column("rho", sa.Float, nullable=False, server_default="2450.0"),
        sa.Column("alpha_T", sa.Float, nullable=False, server_default="0.00001"),
        sa.Column("poisson", sa.Float, nullable=False, server_default="0.2"),
        sa.Column("exposure_classes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("design_life_years", sa.Integer, nullable=False, server_default="50"),
        sa.Column("process_domain", sa.String(64), nullable=False, server_default="CENTRIFUGADO"),
        sa.Column("min_transfer_strength_mpa", sa.Float),
        sa.Column("curing_regime", sa.String(64)),
        sa.Column("status", postgresql.ENUM("DRAFT","VALIDATED","PUBLISHED","DEPRECATED", name="concretematerialstatus", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("mix_code", "version", name="uq_mix_code_version"),
    )

    # ── prestressing_steel_version ───────────────────────────────────────────
    op.create_table(
        "prestressing_steel_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("steel_code", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("element_type", postgresql.ENUM("WIRE","STRAND_3W","STRAND_7W","BAR", name="prestressingelementtype", create_type=False), nullable=False),
        sa.Column("relaxation_class", postgresql.ENUM("CLASS_1","CLASS_2", name="prestressingsteelclass", create_type=False), nullable=False),
        sa.Column("fpk", sa.Float, nullable=False),
        sa.Column("fp01k", sa.Float, nullable=False),
        sa.Column("Ep", sa.Float, nullable=False),
        sa.Column("elongation_pct", sa.Float),
        sa.Column("rho1000_pct", sa.Float, nullable=False),
        sa.Column("phi", sa.Float, nullable=False),
        sa.Column("area", sa.Float, nullable=False),
        sa.Column("mass_per_m", sa.Float, nullable=False),
        sa.Column("alpha1", sa.Float, nullable=False, server_default="1.25"),
        sa.Column("alpha2", sa.Float, nullable=False, server_default="0.25"),
        sa.Column("eta1", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("eta2", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("sigma_max_jack_ratio", sa.Float, nullable=False, server_default="0.80"),
        sa.Column("sigma_max_jack_ratio2", sa.Float, nullable=False, server_default="0.90"),
        sa.Column("sigma_after_transfer_ratio", sa.Float, nullable=False, server_default="0.75"),
        sa.Column("compatible_processes", postgresql.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("steel_code", "version", name="uq_steel_code_version"),
    )

    # ── passive_reinforcement_version ────────────────────────────────────────
    op.create_table(
        "passive_reinforcement_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("steel_code", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("fyk", sa.Float, nullable=False),
        sa.Column("ftk", sa.Float, nullable=False),
        sa.Column("Es", sa.Float, nullable=False, server_default="200000.0"),
        sa.Column("phi", sa.Float, nullable=False),
        sa.Column("ductility_class", sa.String(4)),
        sa.Column("weldable", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("min_bend_dia_ratio", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("steel_code", "version", name="uq_passive_code_version"),
    )

    # ── concrete_pole_design ─────────────────────────────────────────────────
    op.create_table(
        "concrete_pole_design",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("height_m", sa.Float, nullable=False),
        sa.Column("D_base_mm", sa.Float, nullable=False),
        sa.Column("D_top_mm", sa.Float, nullable=False),
        sa.Column("t_base_mm", sa.Float, nullable=False),
        sa.Column("t_top_mm", sa.Float, nullable=False),
        sa.Column("is_segmented", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("mix_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prestress_steel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normative_route", postgresql.ENUM("EN40","EN40_EC2","SPECIAL","BLOCKED", name="concretenormativeroute", create_type=False)),
        sa.Column("geometry_hash", sa.String(64)),
        sa.Column("material_hash", sa.String(64)),
        sa.Column("layout_hash", sa.String(64)),
        sa.Column("rules_hash", sa.String(64)),
        sa.Column("status", postgresql.ENUM("DRAFT","COMPUTING","READY","APPROVED","ARCHIVED","BLOCKED", name="concretedesignstatus", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("max_utilization", sa.Float),
        sa.Column("governing_stage", sa.String(4)),
        sa.Column("governing_limit_state", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["mix_version_id"], ["concrete_mix_version.id"]),
        sa.ForeignKeyConstraint(["prestress_steel_id"], ["prestressing_steel_version.id"]),
    )

    # ── prestress_layout ─────────────────────────────────────────────────────
    op.create_table(
        "prestress_layout",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strand_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("element_index", sa.Integer, nullable=False),
        sa.Column("group_id", sa.Integer, nullable=False, server_default="1"),
        sa.Column("r_polar_mm", sa.Float, nullable=False),
        sa.Column("theta_deg", sa.Float, nullable=False),
        sa.Column("x_mm", sa.Float),
        sa.Column("y_mm", sa.Float),
        sa.Column("initial_force_kn", sa.Float, nullable=False),
        sa.Column("sigma_initial_mpa", sa.Float),
        sa.Column("sigma_after_transfer_mpa", sa.Float),
        sa.Column("sigma_final_mpa", sa.Float),
        sa.Column("jack_sequence", sa.Integer),
        sa.Column("cut_sequence", sa.Integer),
        sa.Column("l_transfer_mm", sa.Float),
        sa.Column("l_anchor_ulu_mm", sa.Float),
        sa.Column("l_active_length_mm", sa.Float),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strand_version_id"], ["prestressing_steel_version.id"]),
        sa.UniqueConstraint("design_id", "element_index", name="uq_layout_element"),
    )

    # ── production_stage ─────────────────────────────────────────────────────
    op.create_table(
        "production_stage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_code", postgresql.ENUM("S0","S1","S2","S3","S4","S5","S6","S7", name="productionstage_code", create_type=False), nullable=False),
        sa.Column("sequence_order", sa.Integer, nullable=False),
        sa.Column("age_days", sa.Float, nullable=False),
        sa.Column("fcm_at_stage", sa.Float),
        sa.Column("Ecm_at_stage", sa.Float),
        sa.Column("fctm_at_stage", sa.Float),
        sa.Column("prestress_effective_kn", sa.Float),
        sa.Column("prestress_eccentricity_mm", sa.Float),
        sa.Column("loss_accumulated_pct", sa.Float),
        sa.Column("applied_loads_json", postgresql.JSONB, server_default="{}"),
        sa.Column("support_positions_json", postgresql.JSONB, server_default="[]"),
        sa.Column("environment_json", postgresql.JSONB, server_default="{}"),
        sa.Column("max_stress_concrete", sa.Float),
        sa.Column("min_stress_concrete", sa.Float),
        sa.Column("max_stress_strand", sa.Float),
        sa.Column("max_deflection", sa.Float),
        sa.Column("camber", sa.Float),
        sa.Column("cracking_occurred", sa.Boolean, server_default="false"),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("design_id", "stage_code", "sequence_order", name="uq_stage_seq"),
    )

    # ── loss_component_result ────────────────────────────────────────────────
    op.create_table(
        "loss_component_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loss_type", postgresql.ENUM("ANCHOR_SLIP","ELASTIC_SHORTENING","SHORT_TERM_RELAXATION","THERMAL_GRADIENT","BED_DEFORMATION","SHRINKAGE","CREEP","LONG_TERM_RELAXATION","COMBINED_CSR", name="prestresslostype", create_type=False), nullable=False),
        sa.Column("delta_P_kn", sa.Float, nullable=False),
        sa.Column("delta_sigma_mpa", sa.Float, nullable=False),
        sa.Column("loss_pct", sa.Float, nullable=False),
        sa.Column("method", sa.String(64)),
        sa.Column("rule_reference", sa.String(64)),
        sa.Column("sensitivity", sa.Float),
        sa.Column("input_values_json", postgresql.JSONB, server_default="{}"),
        sa.Column("equation_trace_json", postgresql.JSONB, server_default="{}"),
        sa.ForeignKeyConstraint(["stage_id"], ["production_stage.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
    )

    # ── concrete_section_station ─────────────────────────────────────────────
    op.create_table(
        "concrete_section_station",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("station_m", sa.Float, nullable=False),
        sa.Column("D_ext_mm", sa.Float, nullable=False),
        sa.Column("D_int_mm", sa.Float, nullable=False),
        sa.Column("t_wall_mm", sa.Float, nullable=False),
        sa.Column("A_gross", sa.Float),
        sa.Column("Iy_gross", sa.Float),
        sa.Column("Iz_gross", sa.Float),
        sa.Column("J_gross", sa.Float),
        sa.Column("Wel_y", sa.Float),
        sa.Column("A_transformed", sa.Float),
        sa.Column("Iy_transformed", sa.Float),
        sa.Column("yG_transformed", sa.Float),
        sa.Column("Iy_cracked", sa.Float),
        sa.Column("neutral_axis_cracked", sa.Float),
        sa.Column("fiber_mesh_hash", sa.String(64)),
        sa.Column("n_fibers", sa.Integer),
        sa.Column("P_prestress_kn", sa.Float),
        sa.Column("e_prestress_mm", sa.Float),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
    )

    # ── concrete_verification_result ─────────────────────────────────────────
    op.create_table(
        "concrete_verification_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True)),
        sa.Column("stage_code", postgresql.ENUM("S0","S1","S2","S3","S4","S5","S6","S7", name="productionstage_code", create_type=False)),
        sa.Column("station_m", sa.Float),
        sa.Column("limit_state", postgresql.ENUM("SLS_COMPRESSION","SLS_TENSION","SLS_DECOMPRESSION","SLS_CRACKING","SLS_DEFLECTION","SLS_VIBRATION","ULS_BENDING","ULS_SHEAR","ULS_TORSION","ULS_INTERACTION","ULS_STABILITY","FATIGUE_STRAND","FATIGUE_CONCRETE","FATIGUE_PASSIVE","TRANSFER_SPLITTING","TRANSFER_COMPRESSION", name="limitstate", create_type=False)),
        sa.Column("N_ed", sa.Float),
        sa.Column("My_ed", sa.Float),
        sa.Column("Mz_ed", sa.Float),
        sa.Column("V_ed", sa.Float),
        sa.Column("T_ed", sa.Float),
        sa.Column("solicitation", sa.Float, nullable=False),
        sa.Column("resistance", sa.Float, nullable=False),
        sa.Column("utilization", sa.Float, nullable=False),
        sa.Column("unit", sa.String(32)),
        sa.Column("status", postgresql.ENUM("PASS","FAIL","WARNING","BLOCKED","NOT_APPLICABLE", name="concreteverificationstatus", create_type=False), nullable=False),
        sa.Column("governing_case", sa.String(64)),
        sa.Column("governing_rule", sa.String(128)),
        sa.Column("equation_trace_json", postgresql.JSONB, server_default="{}"),
        sa.Column("intermediate_values_json", postgresql.JSONB, server_default="{}"),
        sa.Column("run_hash", sa.String(64)),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
    )

    # ── concrete_insert ──────────────────────────────────────────────────────
    op.create_table(
        "concrete_insert",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insert_type", postgresql.ENUM("LUMINAIRE_ARM","GROUND_LATCH","CABLE_ENTRY","EARTH_BOLT","INSPECTION_DOOR", name="inserttype", create_type=False), nullable=False),
        sa.Column("station_m", sa.Float, nullable=False),
        sa.Column("theta_deg", sa.Float, nullable=False),
        sa.Column("material", sa.String(64)),
        sa.Column("embedded_length_mm", sa.Float),
        sa.Column("axial_capacity_kn", sa.Float),
        sa.Column("shear_capacity_kn", sa.Float),
        sa.Column("min_distance_to_strand_mm", sa.Float),
        sa.Column("clearance_ok", sa.Boolean),
        sa.Column("clearance_error_code", sa.String(32)),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
    )

    # ── production_recipe ────────────────────────────────────────────────────
    op.create_table(
        "production_recipe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("mould_id", sa.String(64)),
        sa.Column("spin_curve_json", postgresql.JSONB, server_default="{}"),
        sa.Column("spin_status", postgresql.ENUM("PENDING","VALIDATED","APPROVED","DEPRECATED", name="spincurvestatus", create_type=False)),
        sa.Column("max_spin_rpm", sa.Float),
        sa.Column("curing_regime", sa.String(64)),
        sa.Column("curing_temperature_c", sa.Float),
        sa.Column("min_transfer_strength_mpa", sa.Float),
        sa.Column("cut_sequence_json", postgresql.JSONB, server_default="[]"),
        sa.Column("lifting_points_json", postgresql.JSONB, server_default="[]"),
        sa.Column("transport_supports_json", postgresql.JSONB, server_default="[]"),
        sa.Column("concrete_volume_m3", sa.Float),
        sa.Column("strand_mass_kg", sa.Float),
        sa.Column("passive_mass_kg", sa.Float),
        sa.Column("inserts_mass_kg", sa.Float),
        sa.Column("total_mass_kg", sa.Float),
        sa.Column("material_cost_eur", sa.Float),
        sa.Column("process_cost_eur", sa.Float),
        sa.Column("total_cost_eur", sa.Float),
        sa.Column("total_co2_kg", sa.Float),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
    )

    # ── concrete_optimization_run ────────────────────────────────────────────
    op.create_table(
        "concrete_optimization_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("solver_version", sa.String(32), nullable=False),
        sa.Column("ruleset_hash", sa.String(64), nullable=False),
        sa.Column("seed", sa.Integer, nullable=False, server_default="42"),
        sa.Column("run_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("objectives", postgresql.JSONB, server_default="[]"),
        sa.Column("constraints_json", postgresql.JSONB, server_default="{}"),
        sa.Column("candidates_evaluated", sa.Integer),
        sa.Column("candidates_rejected", sa.Integer),
        sa.Column("pareto_size", sa.Integer),
        sa.Column("convergence_reached", sa.Boolean),
        sa.Column("min_cost_candidate_id", postgresql.UUID(as_uuid=True)),
        sa.Column("min_weight_candidate_id", postgresql.UUID(as_uuid=True)),
        sa.Column("min_co2_candidate_id", postgresql.UUID(as_uuid=True)),
        sa.Column("balanced_candidate_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
    )

    # ── concrete_optimization_candidate ─────────────────────────────────────
    op.create_table(
        "concrete_optimization_candidate",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("n_strands", sa.Integer, nullable=False),
        sa.Column("strand_diameter_mm", sa.Float, nullable=False),
        sa.Column("strand_steel_id", postgresql.UUID(as_uuid=True)),
        sa.Column("crown_radius_mm", sa.Float, nullable=False),
        sa.Column("initial_force_per_strand_kn", sa.Float, nullable=False),
        sa.Column("design_variables_json", postgresql.JSONB, server_default="{}"),
        sa.Column("stage_results_json", postgresql.JSONB, server_default="{}"),
        sa.Column("total_cost_eur", sa.Float),
        sa.Column("total_mass_kg", sa.Float),
        sa.Column("total_co2_kg", sa.Float),
        sa.Column("robustness_score", sa.Float),
        sa.Column("max_utilization", sa.Float),
        sa.Column("governing_constraint", sa.String(64)),
        sa.Column("governing_stage", sa.String(4)),
        sa.Column("feasible", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("transportable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pareto_dominated", sa.Boolean),
        sa.Column("rejection_reason", sa.String(128)),
        sa.ForeignKeyConstraint(["run_id"], ["concrete_optimization_run.id"], ondelete="CASCADE"),
    )

    # ── concrete_report_snapshot ─────────────────────────────────────────────
    op.create_table(
        "concrete_report_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", postgresql.ENUM("SUMMARY","FULL","FABRICATION","QUALITY", name="concretereporttype", create_type=False), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("input_hashes_json", postgresql.JSONB, server_default="{}"),
        sa.Column("all_checks_passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approved_by", sa.String(256)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["design_id"], ["concrete_pole_design.id"], ondelete="CASCADE"),
    )

    # ── índices ──────────────────────────────────────────────────────────────
    op.create_index("ix_concrete_pole_design_project", "concrete_pole_design", ["project_id"])
    op.create_index("ix_concrete_verification_design", "concrete_verification_result", ["design_id"])
    op.create_index("ix_production_stage_design", "production_stage", ["design_id"])


def downgrade() -> None:
    op.drop_table("concrete_report_snapshot")
    op.drop_table("concrete_optimization_candidate")
    op.drop_table("concrete_optimization_run")
    op.drop_table("production_recipe")
    op.drop_table("concrete_insert")
    op.drop_table("concrete_verification_result")
    op.drop_table("concrete_section_station")
    op.drop_table("loss_component_result")
    op.drop_table("production_stage")
    op.drop_table("prestress_layout")
    op.drop_table("concrete_pole_design")
    op.drop_table("passive_reinforcement_version")
    op.drop_table("prestressing_steel_version")
    op.drop_table("concrete_mix_version")
    for enum in ["spincurvestatus","inserttype","concretereporttype","concretematerialstatus",
                 "optimizationobjective","concretedesignstatus","concretenormativeroute",
                 "concreteverificationstatus","limitstate","productionstage_code",
                 "prestresslostype","prestressingelementtype","prestressingsteelclass",
                 "concreteexposureclass","concretecementclass"]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
