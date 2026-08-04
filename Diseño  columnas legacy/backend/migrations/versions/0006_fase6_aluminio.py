"""0006 · Fase 6 — Aluminio: Diseño, Verificación y Fabricación

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TYPE aluminium_product_form AS ENUM (
            'SHEET', 'STRIP', 'HOLLOW_EXTRUSION', 'SOLID_EXTRUSION',
            'TUBE', 'FORGING', 'PLATE', 'OTHER_APPROVED'
        )
    """)
    op.execute("""
        CREATE TYPE aluminium_route AS ENUM (
            'EN40', 'EN40_EXTENDED', 'SPECIAL', 'BLOCKED'
        )
    """)
    op.execute("""
        CREATE TYPE haz_type AS ENUM (
            'LONGITUDINAL_SEAM', 'CIRCUMFERENTIAL', 'FILLET_REINFORCEMENT',
            'BASE_PLATE', 'FSW_NUGGET', 'FSW_TMAZ', 'FSW_HAZ', 'REPAIR'
        )
    """)
    op.execute("""
        CREATE TYPE aluminium_weld_process AS ENUM (
            'MIG', 'TIG', 'FSW', 'OTHER_APPROVED'
        )
    """)
    op.execute("""
        CREATE TYPE joint_geometry AS ENUM (
            'BUTT', 'LAP', 'FILLET', 'T_JOINT', 'CORNER'
        )
    """)
    op.execute("""
        CREATE TYPE section_region_type AS ENUM (
            'BASE_METAL', 'HAZ', 'TMAZ', 'FSW_NUGGET',
            'WELD_METAL', 'REINFORCEMENT', 'HOLE', 'VOID'
        )
    """)
    op.execute("""
        CREATE TYPE panel_status AS ENUM (
            'EFFECTIVE', 'REDUCED', 'OUT_OF_DOMAIN', 'BLOCKED'
        )
    """)
    op.execute("""
        CREATE TYPE door_reinforcement_type AS ENUM (
            'PERIMETER_FRAME', 'VERTICAL_PROFILES', 'INNER_PLATE',
            'RING_SLEEVE', 'REINFORCED_EXTRUSION'
        )
    """)
    op.execute("""
        CREATE TYPE aluminium_surface_treatment AS ENUM (
            'NATURAL', 'ANODIZED', 'POWDER_COAT', 'LIQUID_PAINT',
            'COMBINED_SYSTEM', 'GALVANIC_ISOLATION'
        )
    """)
    op.execute("""
        CREATE TYPE aluminium_joint_type AS ENUM (
            'TELESCOPIC', 'FLANGED', 'WELDED', 'SLEEVE', 'HYBRID_AL_STEEL'
        )
    """)
    op.execute("""
        CREATE TYPE aluminium_check_type AS ENUM (
            'AXIAL', 'BENDING_UNIAXIAL', 'BENDING_BIAXIAL', 'SHEAR',
            'TORSION', 'INTERACTION', 'GLOBAL_BUCKLING', 'DEFORMATION',
            'FATIGUE', 'WALL_SLENDERNESS'
        )
    """)
    op.execute("""
        CREATE TYPE aluminium_check_status AS ENUM (
            'PASS', 'FAIL', 'BLOCKED', 'OUT_OF_DOMAIN', 'WARNING', 'PENDING'
        )
    """)
    op.execute("""
        CREATE TYPE material_status AS ENUM (
            'DRAFT', 'REVIEW', 'APPROVED', 'WITHDRAWN', 'SUPERSEDED'
        )
    """)
    op.execute("""
        CREATE TYPE aluminium_report_type AS ENUM (
            'CLIENT_SUMMARY', 'CLIENT_EXTENDED', 'INTERNAL_CALC',
            'PRODUCTION', 'QUALITY', 'CONFORMITY', 'COST_SUSTAINABILITY'
        )
    """)

    # ── Tablas ───────────────────────────────────────────────────────────────

    # aluminium_alloy_versions
    op.create_table(
        "aluminium_alloy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alloy_designation", sa.String(32), nullable=False),
        sa.Column("temper", sa.String(16), nullable=False),
        sa.Column("product_form", postgresql.ENUM(name="aluminium_product_form", create_type=False), nullable=False),
        sa.Column("norm_reference", sa.String(64), nullable=False),
        sa.Column("thickness_min_mm", sa.Float, nullable=False),
        sa.Column("thickness_max_mm", sa.Float, nullable=False),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("temperature_c", sa.Float, nullable=False, server_default="20.0"),
        sa.Column("f0_mpa", sa.Float, nullable=False),
        sa.Column("fu_mpa", sa.Float, nullable=False),
        sa.Column("E_mpa", sa.Float, nullable=False, server_default="70000.0"),
        sa.Column("G_mpa", sa.Float, nullable=False, server_default="26900.0"),
        sa.Column("nu", sa.Float, nullable=False, server_default="0.33"),
        sa.Column("rho_kg_m3", sa.Float, nullable=False, server_default="2700.0"),
        sa.Column("alpha_T_per_k", sa.Float, nullable=False, server_default="0.0000236"),
        sa.Column("haz_rho_yield", sa.Float, nullable=True),
        sa.Column("haz_rho_ultimate", sa.Float, nullable=True),
        sa.Column("haz_rho_buckling", sa.Float, nullable=True),
        sa.Column("haz_rho_fatigue", sa.Float, nullable=True),
        sa.Column("haz_width_mm", sa.Float, nullable=True),
        sa.Column("bend_limit_r_over_t_L", sa.Float, nullable=True),
        sa.Column("bend_limit_r_over_t_LT", sa.Float, nullable=True),
        sa.Column("status", postgresql.ENUM(name="material_status", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("epd_factor_kg_co2_per_kg", sa.Float, nullable=True),
        sa.Column("price_per_kg_eur", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "alloy_designation", "temper", "product_form", "norm_reference",
            "thickness_min_mm", "thickness_max_mm", "direction", "temperature_c",
            name="uq_al_alloy_canonical_key",
        ),
    )

    # haz_rule_versions
    op.create_table(
        "haz_rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alloy_designation", sa.String(32), nullable=False),
        sa.Column("temper", sa.String(16), nullable=False),
        sa.Column("product_form", postgresql.ENUM(name="aluminium_product_form", create_type=False), nullable=False),
        sa.Column("process", postgresql.ENUM(name="aluminium_weld_process", create_type=False), nullable=False),
        sa.Column("haz_type", postgresql.ENUM(name="haz_type", create_type=False), nullable=False),
        sa.Column("thickness_min_mm", sa.Float, nullable=False),
        sa.Column("thickness_max_mm", sa.Float, nullable=False),
        sa.Column("haz_width_mm", sa.Float, nullable=False),
        sa.Column("rho_yield", sa.Float, nullable=False),
        sa.Column("rho_ultimate", sa.Float, nullable=False),
        sa.Column("rho_buckling", sa.Float, nullable=True),
        sa.Column("rho_fatigue", sa.Float, nullable=True),
        sa.Column("norm_reference", sa.String(64), nullable=False),
        sa.Column("clause", sa.String(32), nullable=True),
        sa.Column("status", postgresql.ENUM(name="material_status", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_fsw_procedures (antes de weld_joints porque weld_joints lo referencia)
    op.create_table(
        "aluminium_fsw_procedures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("procedure_code", sa.String(32), nullable=False, unique=True),
        sa.Column("machine_model", sa.String(64), nullable=True),
        sa.Column("max_force_kn", sa.Float, nullable=True),
        sa.Column("backing_type", sa.String(32), nullable=True),
        sa.Column("tool_material", sa.String(32), nullable=True),
        sa.Column("shoulder_diameter_mm", sa.Float, nullable=True),
        sa.Column("pin_geometry", sa.String(32), nullable=True),
        sa.Column("alloy_designation", sa.String(32), nullable=False),
        sa.Column("temper", sa.String(16), nullable=False),
        sa.Column("thickness_min_mm", sa.Float, nullable=False),
        sa.Column("thickness_max_mm", sa.Float, nullable=False),
        sa.Column("rotation_speed_min_rpm", sa.Float, nullable=True),
        sa.Column("rotation_speed_max_rpm", sa.Float, nullable=True),
        sa.Column("travel_speed_min_mm_per_min", sa.Float, nullable=True),
        sa.Column("travel_speed_max_mm_per_min", sa.Float, nullable=True),
        sa.Column("axial_force_min_kn", sa.Float, nullable=True),
        sa.Column("axial_force_max_kn", sa.Float, nullable=True),
        sa.Column("nugget_properties", postgresql.JSONB, nullable=True),
        sa.Column("tmaz_properties", postgresql.JSONB, nullable=True),
        sa.Column("haz_width_mm", sa.Float, nullable=True),
        sa.Column("haz_rho_yield", sa.Float, nullable=True),
        sa.Column("haz_rho_ultimate", sa.Float, nullable=True),
        sa.Column("defect_criteria", postgresql.JSONB, nullable=True),
        sa.Column("inspection_methods", postgresql.JSONB, nullable=False,
                  server_default="[]"),
        sa.Column("status", postgresql.ENUM(name="material_status", create_type=False), nullable=False, server_default="DRAFT"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_normative_routes
    op.create_table(
        "aluminium_normative_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("route", postgresql.ENUM(name="aluminium_route", create_type=False), nullable=False),
        sa.Column("route_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("step_1_norm_active", sa.Boolean, nullable=False),
        sa.Column("step_2_height_typology", sa.Boolean, nullable=False),
        sa.Column("step_3_alloy_in_library", sa.Boolean, nullable=False),
        sa.Column("step_4_domain_ok", sa.Boolean, nullable=False),
        sa.Column("step_5_checks_defined", sa.Boolean, nullable=False),
        sa.Column("step_6_rules_available", sa.Boolean, nullable=False),
        sa.Column("step_7_evidence_ok", sa.Boolean, nullable=False),
        sa.Column("decision_trace", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("active_rules", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("discarded_rules", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("exclusions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("max_declaration_allowed", sa.String(64), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("height_nominal_m", sa.Float, nullable=False),
        sa.Column("has_catenary_cables", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_haz_maps
    op.create_table(
        "aluminium_haz_maps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("alloy_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_alloy_versions.id"), nullable=True),
        sa.Column("section_station_m", sa.Float, nullable=False),
        sa.Column("regions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("has_overlapping_zones", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("overlap_treatment", sa.String(64), nullable=True),
        sa.Column("geometry_hash", sa.String(64), nullable=False),
        sa.Column("material_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_verification_runs
    op.create_table(
        "aluminium_verification_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("normative_route_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_normative_routes.id"), nullable=True),
        sa.Column("structural_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id"), nullable=True),
        sa.Column("geometry_hash", sa.String(64), nullable=False),
        sa.Column("material_hash", sa.String(64), nullable=False),
        sa.Column("haz_hash", sa.String(64), nullable=False),
        sa.Column("rules_hash", sa.String(64), nullable=False),
        sa.Column("stress_hash", sa.String(64), nullable=False),
        sa.Column("run_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True, unique=True),
        sa.Column("engine_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("gamma_M0", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("gamma_M1", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("gamma_M2", sa.Float, nullable=False, server_default="1.25"),
        sa.Column("utilization_limit", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("overall_status", postgresql.ENUM(name="aluminium_check_status", create_type=False),
                  nullable=False, server_default="PENDING"),
        sa.Column("max_utilization", sa.Float, nullable=True),
        sa.Column("governing_station_m", sa.Float, nullable=True),
        sa.Column("governing_combination", sa.String(64), nullable=True),
        sa.Column("governing_check_type", postgresql.ENUM(name="aluminium_check_type", create_type=False), nullable=True),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )

    # aluminium_section_regions
    op.create_table(
        "aluminium_section_regions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("haz_map_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_haz_maps.id"), nullable=False),
        sa.Column("region_type", postgresql.ENUM(name="section_region_type", create_type=False), nullable=False),
        sa.Column("area_m2", sa.Float, nullable=False),
        sa.Column("centroid_y_m", sa.Float, nullable=False),
        sa.Column("centroid_z_m", sa.Float, nullable=False),
        sa.Column("Iy_m4", sa.Float, nullable=True),
        sa.Column("Iz_m4", sa.Float, nullable=True),
        sa.Column("f0_d_mpa", sa.Float, nullable=False),
        sa.Column("fu_d_mpa", sa.Float, nullable=False),
        sa.Column("E_mpa", sa.Float, nullable=False),
        sa.Column("rho_yield_applied", sa.Float, nullable=True),
        sa.Column("rho_ultimate_applied", sa.Float, nullable=True),
        sa.Column("gamma_M", sa.Float, nullable=False, server_default="1.1"),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # aluminium_section_checks
    op.create_table(
        "aluminium_section_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_verification_runs.id"), nullable=False),
        sa.Column("station_m", sa.Float, nullable=False),
        sa.Column("combination_id", sa.String(64), nullable=False),
        sa.Column("check_type", postgresql.ENUM(name="aluminium_check_type", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="aluminium_check_status", create_type=False), nullable=False),
        sa.Column("N_kn", sa.Float, nullable=True),
        sa.Column("Vy_kn", sa.Float, nullable=True),
        sa.Column("Vz_kn", sa.Float, nullable=True),
        sa.Column("My_knm", sa.Float, nullable=True),
        sa.Column("Mz_knm", sa.Float, nullable=True),
        sa.Column("T_knm", sa.Float, nullable=True),
        sa.Column("N_Rd_kn", sa.Float, nullable=True),
        sa.Column("Vpl_Rd_kn", sa.Float, nullable=True),
        sa.Column("Mc_Rd_knm", sa.Float, nullable=True),
        sa.Column("T_Rd_knm", sa.Float, nullable=True),
        sa.Column("utilization", sa.Float, nullable=True),
        sa.Column("governing_rule", sa.String(64), nullable=True),
        sa.Column("equation_trace", postgresql.JSONB, nullable=True),
        sa.Column("intermediate_values", postgresql.JSONB, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
    )

    # aluminium_local_buckling_panels
    op.create_table(
        "aluminium_local_buckling_panels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("verification_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_verification_runs.id"), nullable=False),
        sa.Column("panel_index", sa.Integer, nullable=False),
        sa.Column("panel_description", sa.String(64), nullable=True),
        sa.Column("width_gross_mm", sa.Float, nullable=False),
        sa.Column("thickness_eff_mm", sa.Float, nullable=False),
        sa.Column("curvature_radius_mm", sa.Float, nullable=True),
        sa.Column("support_condition", sa.String(32), nullable=False, server_default="SS"),
        sa.Column("stress_distribution", sa.String(16), nullable=False, server_default="UNIFORM"),
        sa.Column("sigma_max_mpa", sa.Float, nullable=False),
        sa.Column("sigma_min_mpa", sa.Float, nullable=True),
        sa.Column("psi", sa.Float, nullable=True),
        sa.Column("slenderness", sa.Float, nullable=True),
        sa.Column("reduction_factor", sa.Float, nullable=True),
        sa.Column("width_effective_mm", sa.Float, nullable=True),
        sa.Column("n_iterations", sa.Integer, nullable=True),
        sa.Column("converged", sa.Boolean, nullable=True),
        sa.Column("iteration_history", postgresql.JSONB, nullable=True),
        sa.Column("status", postgresql.ENUM(name="panel_status", create_type=False), nullable=False, server_default="EFFECTIVE"),
        sa.Column("governing_rule", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # aluminium_weld_joints
    op.create_table(
        "aluminium_weld_joints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("joint_id_code", sa.String(32), nullable=False),
        sa.Column("process", postgresql.ENUM(name="aluminium_weld_process", create_type=False), nullable=False),
        sa.Column("geometry", postgresql.ENUM(name="joint_geometry", create_type=False), nullable=False),
        sa.Column("alloy_1_designation", sa.String(32), nullable=False),
        sa.Column("temper_1", sa.String(16), nullable=False),
        sa.Column("alloy_2_designation", sa.String(32), nullable=True),
        sa.Column("temper_2", sa.String(16), nullable=True),
        sa.Column("thickness_mm", sa.Float, nullable=False),
        sa.Column("orientation_deg", sa.Float, nullable=True),
        sa.Column("wps_pqr_reference", sa.String(64), nullable=True),
        sa.Column("fsw_procedure_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_fsw_procedures.id"), nullable=True),
        sa.Column("haz_rule_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("haz_rule_versions.id"), nullable=True),
        sa.Column("throat_mm", sa.Float, nullable=True),
        sa.Column("effective_length_mm", sa.Float, nullable=True),
        sa.Column("fatigue_detail_category", sa.Float, nullable=True),
        sa.Column("fatigue_detail_id", sa.String(32), nullable=True),
        sa.Column("end_condition", sa.String(32), nullable=True),
        sa.Column("inspection_methods", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("inspection_percentage", sa.Float, nullable=False, server_default="100.0"),
        sa.Column("static_utilization", sa.Float, nullable=True),
        sa.Column("fatigue_damage", sa.Float, nullable=True),
        sa.Column("is_compliant", sa.Boolean, nullable=True),
        sa.Column("governing_case", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "joint_id_code", name="uq_al_weld_joint"),
    )

    # aluminium_door_reinforcements
    op.create_table(
        "aluminium_door_reinforcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("reinforcement_type", postgresql.ENUM(name="door_reinforcement_type", create_type=False), nullable=False),
        sa.Column("door_height_m", sa.Float, nullable=False),
        sa.Column("door_width_m", sa.Float, nullable=False),
        sa.Column("door_station_bottom_m", sa.Float, nullable=False),
        sa.Column("door_station_top_m", sa.Float, nullable=False),
        sa.Column("door_azimuth_deg", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("reinforcement_geometry", postgresql.JSONB, nullable=False),
        sa.Column("alloy_designation", sa.String(32), nullable=False),
        sa.Column("temper", sa.String(16), nullable=False),
        sa.Column("net_A_m2", sa.Float, nullable=True),
        sa.Column("net_Iy_m4", sa.Float, nullable=True),
        sa.Column("net_J_m4", sa.Float, nullable=True),
        sa.Column("max_utilization", sa.Float, nullable=True),
        sa.Column("fatigue_damage", sa.Float, nullable=True),
        sa.Column("is_fabricable", sa.Boolean, nullable=True),
        sa.Column("is_compliant", sa.Boolean, nullable=True),
        sa.Column("extra_mass_kg", sa.Float, nullable=True),
        sa.Column("extra_cost_eur", sa.Float, nullable=True),
        sa.Column("extra_co2_kg", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_surface_systems
    op.create_table(
        "aluminium_surface_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("treatment", postgresql.ENUM(name="aluminium_surface_treatment", create_type=False), nullable=False),
        sa.Column("corrosivity_category", sa.String(4), nullable=False),
        sa.Column("design_life_years", sa.Float, nullable=False),
        sa.Column("anodizing_thickness_um", sa.Float, nullable=True),
        sa.Column("sealing_type", sa.String(32), nullable=True),
        sa.Column("paint_system_layers", postgresql.JSONB, nullable=True),
        sa.Column("total_dft_um", sa.Float, nullable=True),
        sa.Column("life_adequate", sa.Boolean, nullable=True),
        sa.Column("life_range_min_years", sa.Float, nullable=True),
        sa.Column("life_range_max_years", sa.Float, nullable=True),
        sa.Column("galvanic_pairs", postgresql.JSONB, nullable=True),
        sa.Column("galvanic_isolation_required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("isolation_method", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_joints
    op.create_table(
        "aluminium_joints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("joint_type", postgresql.ENUM(name="aluminium_joint_type", create_type=False), nullable=False),
        sa.Column("station_m", sa.Float, nullable=False),
        sa.Column("overlap_length_mm", sa.Float, nullable=True),
        sa.Column("flange_plate_thickness_mm", sa.Float, nullable=True),
        sa.Column("bolt_pattern", postgresql.JSONB, nullable=True),
        sa.Column("is_aluminium_steel_interface", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("galvanic_isolation_detail", postgresql.JSONB, nullable=True),
        sa.Column("moment_transfer_verified", sa.Boolean, nullable=True),
        sa.Column("shear_transfer_verified", sa.Boolean, nullable=True),
        sa.Column("torsion_transfer_verified", sa.Boolean, nullable=True),
        sa.Column("rotational_stiffness_knm_per_rad", sa.Float, nullable=True),
        sa.Column("fretting_risk", sa.Boolean, nullable=True),
        sa.Column("max_utilization", sa.Float, nullable=True),
        sa.Column("fatigue_damage", sa.Float, nullable=True),
        sa.Column("is_compliant", sa.Boolean, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_manufacturing_routes
    op.create_table(
        "aluminium_manufacturing_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("alloy_designation", sa.String(32), nullable=False),
        sa.Column("temper", sa.String(16), nullable=False),
        sa.Column("product_form", postgresql.ENUM(name="aluminium_product_form", create_type=False), nullable=False),
        sa.Column("blank_geometry", postgresql.JSONB, nullable=True),
        sa.Column("folding_sequence", postgresql.JSONB, nullable=True),
        sa.Column("seam_azimuth_deg", sa.Float, nullable=True),
        sa.Column("seam_not_in_door", sa.Boolean, nullable=True),
        sa.Column("extrusion_die_id", sa.String(32), nullable=True),
        sa.Column("extrusion_die_cost_eur", sa.Float, nullable=True),
        sa.Column("is_existing_die", sa.Boolean, nullable=True),
        sa.Column("bom", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("total_mass_kg", sa.Float, nullable=True),
        sa.Column("nesting_efficiency", sa.Float, nullable=True),
        sa.Column("scrap_rate", sa.Float, nullable=True),
        sa.Column("process_operations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("material_cost_eur", sa.Float, nullable=True),
        sa.Column("process_cost_eur", sa.Float, nullable=True),
        sa.Column("weld_cost_eur", sa.Float, nullable=True),
        sa.Column("surface_cost_eur", sa.Float, nullable=True),
        sa.Column("inspection_cost_eur", sa.Float, nullable=True),
        sa.Column("transport_cost_eur", sa.Float, nullable=True),
        sa.Column("total_cost_eur", sa.Float, nullable=True),
        sa.Column("total_co2_kg", sa.Float, nullable=True),
        sa.Column("max_piece_length_m", sa.Float, nullable=False, server_default="12.0"),
        sa.Column("min_diameter_mm", sa.Float, nullable=False, server_default="60.0"),
        sa.Column("is_fabricable", sa.Boolean, nullable=True),
        sa.Column("fabricability_issues", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("is_preliminary", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_optimization_runs
    op.create_table(
        "aluminium_optimization_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("normative_route_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_normative_routes.id"), nullable=True),
        sa.Column("utilization_limit", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("max_piece_length_m", sa.Float, nullable=False, server_default="12.0"),
        sa.Column("min_diameter_mm", sa.Float, nullable=False, server_default="60.0"),
        sa.Column("candidate_min_cost_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_min_weight_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_min_co2_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_balanced_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("n_candidates_total", sa.Integer, nullable=True),
        sa.Column("n_pareto_front", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # aluminium_optimization_candidates
    op.create_table(
        "aluminium_optimization_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_optimization_runs.id"), nullable=False),
        sa.Column("alloy_designation", sa.String(32), nullable=False),
        sa.Column("temper", sa.String(16), nullable=False),
        sa.Column("product_form", postgresql.ENUM(name="aluminium_product_form", create_type=False), nullable=False),
        sa.Column("weld_process", postgresql.ENUM(name="aluminium_weld_process", create_type=False), nullable=False),
        sa.Column("thickness_mm", sa.Float, nullable=False),
        sa.Column("diameter_base_mm", sa.Float, nullable=False),
        sa.Column("taper_ratio", sa.Float, nullable=False, server_default="11.0"),
        sa.Column("n_segments", sa.Integer, nullable=False, server_default="1"),
        sa.Column("total_cost_eur", sa.Float, nullable=False),
        sa.Column("total_mass_kg", sa.Float, nullable=False),
        sa.Column("total_co2_kg", sa.Float, nullable=False),
        sa.Column("max_utilization", sa.Float, nullable=False),
        sa.Column("is_fabricable", sa.Boolean, nullable=False),
        sa.Column("is_transportable", sa.Boolean, nullable=False),
        sa.Column("is_pareto_dominated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("objectives", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # aluminium_report_snapshots
    op.create_table(
        "aluminium_report_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("verification_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("aluminium_verification_runs.id"), nullable=True),
        sa.Column("report_type", postgresql.ENUM(name="aluminium_report_type", create_type=False), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("input_hashes", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("language", sa.String(8), nullable=False, server_default="es"),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("includes_cost_data", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("all_evidences_present", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("all_approvals_present", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("content_url", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # ── Índices ───────────────────────────────────────────────────────────────
    op.create_index("ix_al_alloy_designation", "aluminium_alloy_versions", ["alloy_designation"])
    op.create_index("ix_al_routes_project", "aluminium_normative_routes", ["project_id"])
    op.create_index("ix_al_haz_maps_project", "aluminium_haz_maps", ["project_id"])
    op.create_index("ix_al_ver_runs_project", "aluminium_verification_runs", ["project_id"])
    op.create_index("ix_al_ver_runs_status", "aluminium_verification_runs", ["overall_status"])
    op.create_index("ix_al_sec_checks_run", "aluminium_section_checks", ["run_id"])
    op.create_index("ix_al_sec_checks_type", "aluminium_section_checks", ["check_type"])
    op.create_index("ix_al_panels_run", "aluminium_local_buckling_panels", ["verification_run_id"])
    op.create_index("ix_al_weld_joints_project", "aluminium_weld_joints", ["project_id"])
    op.create_index("ix_al_door_reinf_project", "aluminium_door_reinforcements", ["project_id"])
    op.create_index("ix_al_surface_project", "aluminium_surface_systems", ["project_id"])
    op.create_index("ix_al_joints_project", "aluminium_joints", ["project_id"])
    op.create_index("ix_al_mfg_routes_project", "aluminium_manufacturing_routes", ["project_id"])
    op.create_index("ix_al_opt_runs_project", "aluminium_optimization_runs", ["project_id"])
    op.create_index("ix_al_opt_cands_run", "aluminium_optimization_candidates", ["run_id"])
    op.create_index("ix_al_reports_project", "aluminium_report_snapshots", ["project_id"])
    op.create_index("ix_al_reports_type", "aluminium_report_snapshots", ["report_type"])


def downgrade() -> None:
    # Índices
    for idx in [
        "ix_al_reports_type", "ix_al_reports_project", "ix_al_opt_cands_run",
        "ix_al_opt_runs_project", "ix_al_mfg_routes_project", "ix_al_joints_project",
        "ix_al_surface_project", "ix_al_door_reinf_project", "ix_al_weld_joints_project",
        "ix_al_panels_run", "ix_al_sec_checks_type", "ix_al_sec_checks_run",
        "ix_al_ver_runs_status", "ix_al_ver_runs_project", "ix_al_haz_maps_project",
        "ix_al_routes_project", "ix_al_alloy_designation",
    ]:
        op.drop_index(idx)

    # Tablas (orden inverso de dependencias)
    for tbl in [
        "aluminium_report_snapshots",
        "aluminium_optimization_candidates",
        "aluminium_optimization_runs",
        "aluminium_manufacturing_routes",
        "aluminium_joints",
        "aluminium_surface_systems",
        "aluminium_door_reinforcements",
        "aluminium_weld_joints",
        "aluminium_local_buckling_panels",
        "aluminium_section_checks",
        "aluminium_section_regions",
        "aluminium_verification_runs",
        "aluminium_haz_maps",
        "aluminium_normative_routes",
        "aluminium_fsw_procedures",
        "haz_rule_versions",
        "aluminium_alloy_versions",
    ]:
        op.drop_table(tbl)

    # Enums
    for enum in [
        "aluminium_report_type", "aluminium_check_status", "aluminium_check_type",
        "aluminium_joint_type", "aluminium_surface_treatment", "door_reinforcement_type",
        "panel_status", "section_region_type", "joint_geometry", "aluminium_weld_process",
        "haz_type", "aluminium_route", "aluminium_product_form", "material_status",
    ]:
        op.execute(f"DROP TYPE {enum}")
