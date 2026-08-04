"""
Fase 5 - Acero: Diseño, Verificación y Fabricación
Salvi Studio · Columns

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enums
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TYPE steel_grade AS ENUM ('S235', 'S275', 'S355', 'S420', 'S460')
    """)
    op.execute("""
        CREATE TYPE steel_subgrade AS ENUM ('JR', 'J0', 'J2', 'K2', 'M', 'N')
    """)
    op.execute("""
        CREATE TYPE steel_product_form AS ENUM
        ('SHEET', 'COIL', 'HOT_TUBE', 'COLD_TUBE', 'PROFILE', 'BAR', 'BOLT', 'MACHINED')
    """)
    op.execute("""
        CREATE TYPE normative_route AS ENUM ('EN40', 'EN40_EXTENDED', 'SPECIAL')
    """)
    op.execute("""
        CREATE TYPE route_decision_status AS ENUM ('PASS', 'BLOCKED', 'WARNING')
    """)
    op.execute("""
        CREATE TYPE section_property_set AS ENUM
        ('GROSS', 'NET', 'COMPOSITE', 'EFFECTIVE', 'FABRICATION')
    """)
    op.execute("""
        CREATE TYPE steel_check_status AS ENUM ('PASS', 'FAIL', 'BLOCKED', 'WARNING')
    """)
    op.execute("""
        CREATE TYPE weld_type AS ENUM
        ('W_LONG', 'W_CIRC', 'W_BASE', 'W_ARM', 'W_REINF', 'W_STIFF', 'W_SLEEVE')
    """)
    op.execute("""
        CREATE TYPE weld_process AS ENUM ('SMAW', 'GMAW', 'GTAW', 'SAW', 'FCAW')
    """)
    op.execute("""
        CREATE TYPE weld_quality_class AS ENUM ('B', 'C', 'D', 'E')
    """)
    op.execute("""
        CREATE TYPE fatigue_method AS ENUM
        ('SIMPLIFIED_EN40', 'DAMAGE_ACCUMULATION', 'STRUCTURAL_STRESS')
    """)
    op.execute("""
        CREATE TYPE corrosivity_category AS ENUM
        ('C1', 'C2', 'C3', 'C4', 'C5', 'CX', 'IM1', 'IM2', 'IM3')
    """)
    op.execute("""
        CREATE TYPE protection_system AS ENUM
        ('HOT_DIP_GALVANIZING', 'PAINT', 'DUPLEX', 'THERMAL_SPRAY', 'REINFORCED')
    """)
    op.execute("""
        CREATE TYPE steel_joint_type AS ENUM
        ('TELESCOPIC', 'FLANGED', 'SHOP_WELDED', 'BOLTED', 'SLEEVE')
    """)
    op.execute("""
        CREATE TYPE steel_run_status AS ENUM
        ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED')
    """)
    op.execute("""
        CREATE TYPE optimization_objective AS ENUM
        ('MIN_COST', 'MIN_WEIGHT', 'MIN_CO2', 'BALANCED')
    """)
    op.execute("""
        CREATE TYPE maturity_level AS ENUM ('M1', 'M2', 'M3', 'M4')
    """)
    op.execute("""
        CREATE TYPE validation_evidence_type AS ENUM
        ('CALCULATION', 'TEST_EN40_3_2', 'LOCAL_FEM', 'HISTORICAL', 'PRODUCTION_INSPECTION')
    """)

    # ------------------------------------------------------------------
    # steel_product_properties
    # ------------------------------------------------------------------
    op.create_table(
        "steel_product_properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("product_norm", sa.String(64), nullable=False),
        sa.Column("steel_grade", postgresql.ENUM(name="steel_grade", create_type=False), nullable=False),
        sa.Column("subgrade", postgresql.ENUM(name="steel_subgrade", create_type=False), nullable=False),
        sa.Column("product_form", postgresql.ENUM(name="steel_product_form", create_type=False), nullable=False),
        sa.Column("supply_condition", sa.String(32), nullable=False, server_default="AR"),
        sa.Column("thickness_min_mm", sa.Numeric(6, 2), nullable=False),
        sa.Column("thickness_max_mm", sa.Numeric(6, 2), nullable=False),
        sa.Column("temperature_min_c", sa.Numeric(6, 1), nullable=True),
        sa.Column("fy_mpa", sa.Numeric(8, 2), nullable=False),
        sa.Column("fu_mpa", sa.Numeric(8, 2), nullable=False),
        sa.Column("E_gpa", sa.Numeric(8, 3), nullable=False, server_default="210.0"),
        sa.Column("G_gpa", sa.Numeric(8, 3), nullable=False, server_default="80.769"),
        sa.Column("nu", sa.Numeric(6, 4), nullable=False, server_default="0.3"),
        sa.Column("rho_kg_m3", sa.Numeric(8, 2), nullable=False, server_default="7850.0"),
        sa.Column("alpha_t_per_k", sa.Numeric(12, 10), nullable=False, server_default="0.000012"),
        sa.Column("charpy_energy_j", sa.Numeric(8, 2), nullable=True),
        sa.Column("charpy_temp_c", sa.Numeric(6, 1), nullable=True),
        sa.Column("cev_max", sa.Numeric(6, 4), nullable=True),
        sa.Column("weldability_note", sa.Text, nullable=True),
        sa.Column("coating_compatibility", postgresql.JSONB, nullable=True),
        sa.Column("thickness_tolerance_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("certificate_type", sa.String(32), nullable=True),
        sa.Column("carbon_factor_kg_co2_per_kg", sa.Numeric(8, 4), nullable=True),
        sa.Column("carbon_factor_source", sa.String(128), nullable=True),
        sa.Column("carbon_factor_year", sa.Integer, nullable=True),
        sa.Column("carbon_factor_region", sa.String(64), nullable=True),
        sa.Column("library_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "product_norm", "steel_grade", "subgrade", "product_form",
            "supply_condition", "thickness_min_mm", "thickness_max_mm",
            "temperature_min_c", "library_version",
            name="uq_steel_product_property_canonical",
        ),
    )
    op.create_index("ix_steel_props_grade", "steel_product_properties", ["steel_grade"])
    op.create_index("ix_steel_props_deprecated", "steel_product_properties", ["deprecated"])

    # ------------------------------------------------------------------
    # steel_normative_routes
    # ------------------------------------------------------------------
    op.create_table(
        "steel_normative_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("structural_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id"), nullable=True),
        sa.Column("route", postgresql.ENUM(name="normative_route", create_type=False), nullable=False),
        sa.Column("route_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("step_1_status", postgresql.ENUM(name="route_decision_status", create_type=False), nullable=False),
        sa.Column("step_2_status", postgresql.ENUM(name="route_decision_status", create_type=False), nullable=False),
        sa.Column("step_3_status", postgresql.ENUM(name="route_decision_status", create_type=False), nullable=False),
        sa.Column("step_4_status", postgresql.ENUM(name="route_decision_status", create_type=False), nullable=False),
        sa.Column("step_5_status", postgresql.ENUM(name="route_decision_status", create_type=False), nullable=False),
        sa.Column("step_6_status", postgresql.ENUM(name="route_decision_status", create_type=False), nullable=False),
        sa.Column("step_7_status", postgresql.ENUM(name="route_decision_status", create_type=False), nullable=False),
        sa.Column("decision_trace", postgresql.JSONB, nullable=False),
        sa.Column("active_rules", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("discarded_rules", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("exclusions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("max_declaration_allowed", sa.String(128), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_steel_routes_project", "steel_normative_routes", ["project_id"])

    # ------------------------------------------------------------------
    # steel_section_check_runs
    # ------------------------------------------------------------------
    op.create_table(
        "steel_section_check_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("structural_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_analysis_runs.id"), nullable=False),
        sa.Column("normative_route_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_normative_routes.id"), nullable=False),
        sa.Column("status", postgresql.ENUM(name="steel_run_status", create_type=False), nullable=False),
        sa.Column("maturity_level", postgresql.ENUM(name="maturity_level", create_type=False), nullable=False),
        sa.Column("geometry_hash", sa.String(64), nullable=False),
        sa.Column("material_hash", sa.String(64), nullable=False),
        sa.Column("rules_hash", sa.String(64), nullable=False),
        sa.Column("stress_hash", sa.String(64), nullable=False),
        sa.Column("run_hash", sa.String(64), nullable=True),
        sa.Column("utilization_limit", sa.Numeric(6, 4), nullable=False, server_default="1.0"),
        sa.Column("include_fatigue", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("include_local_buckling", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("max_utilization", sa.Numeric(8, 6), nullable=True),
        sa.Column("governing_station_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("governing_combination", sa.String(128), nullable=True),
        sa.Column("governing_check_type", sa.String(64), nullable=True),
        sa.Column("all_checks_passed", sa.Boolean, nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True, unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_steel_check_runs_project", "steel_section_check_runs", ["project_id"])
    op.create_index("ix_steel_check_runs_status", "steel_section_check_runs", ["status"])

    # ------------------------------------------------------------------
    # steel_section_checks
    # ------------------------------------------------------------------
    op.create_table(
        "steel_section_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_section_check_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_nodes.id"), nullable=True),
        sa.Column("element_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_elements.id"), nullable=True),
        sa.Column("combination_id", sa.String(128), nullable=False),
        sa.Column("wind_direction_deg", sa.Numeric(6, 2), nullable=True),
        sa.Column("check_type", sa.String(64), nullable=False),
        sa.Column("norm", sa.String(32), nullable=False),
        sa.Column("norm_edition", sa.String(16), nullable=True),
        sa.Column("norm_clause", sa.String(32), nullable=True),
        sa.Column("property_set", postgresql.ENUM(name="section_property_set", create_type=False), nullable=False),
        sa.Column("route", postgresql.ENUM(name="normative_route", create_type=False), nullable=False),
        sa.Column("N_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Vy_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Vz_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("T_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("My_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("Mz_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("N_rd_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Vy_rd_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Vz_rd_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("T_rd_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("My_rd_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("Mz_rd_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("utilization", sa.Numeric(8, 6), nullable=False),
        sa.Column("margin", sa.Numeric(8, 6), nullable=True),
        sa.Column("status", postgresql.ENUM(name="steel_check_status", create_type=False), nullable=False),
        sa.Column("intermediate_values", postgresql.JSONB, nullable=True),
        sa.Column("domain_ok", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("domain_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_steel_checks_run", "steel_section_checks", ["run_id"])
    op.create_index("ix_steel_checks_type", "steel_section_checks", ["check_type"])
    op.create_index("ix_steel_checks_status", "steel_section_checks", ["status"])

    # ------------------------------------------------------------------
    # effective_section_runs
    # ------------------------------------------------------------------
    op.create_table(
        "effective_section_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("check_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_section_check_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("element_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("structural_elements.id"), nullable=True),
        sa.Column("station_z_m", sa.Numeric(10, 4), nullable=True),
        sa.Column("panels", postgresql.JSONB, nullable=False),
        sa.Column("section_class", sa.Integer, nullable=True),
        sa.Column("A_eff_m2", sa.Numeric(14, 10), nullable=True),
        sa.Column("Iy_eff_m4", sa.Numeric(20, 16), nullable=True),
        sa.Column("Iz_eff_m4", sa.Numeric(20, 16), nullable=True),
        sa.Column("centroid_y_shift_m", sa.Numeric(12, 9), nullable=True),
        sa.Column("centroid_z_shift_m", sa.Numeric(12, 9), nullable=True),
        sa.Column("iterations", sa.Integer, nullable=True),
        sa.Column("converged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("convergence_tolerance", sa.Numeric(10, 8), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_eff_section_run", "effective_section_runs", ["check_run_id"])

    # ------------------------------------------------------------------
    # door_section_models
    # ------------------------------------------------------------------
    op.create_table(
        "door_section_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_section_check_runs.id"), nullable=True),
        sa.Column("door_height_mm", sa.Numeric(8, 2), nullable=False),
        sa.Column("door_width_mm", sa.Numeric(8, 2), nullable=False),
        sa.Column("corner_radius_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("bottom_elevation_m", sa.Numeric(8, 4), nullable=False),
        sa.Column("top_elevation_m", sa.Numeric(8, 4), nullable=False),
        sa.Column("orientation_deg", sa.Numeric(6, 2), nullable=False, server_default="0.0"),
        sa.Column("reinforcement_type", sa.String(64), nullable=True),
        sa.Column("reinforcement_geometry", postgresql.JSONB, nullable=True),
        sa.Column("A_net_m2", sa.Numeric(14, 10), nullable=True),
        sa.Column("Iy_net_m4", sa.Numeric(20, 16), nullable=True),
        sa.Column("Iz_net_m4", sa.Numeric(20, 16), nullable=True),
        sa.Column("Iyz_net_m4", sa.Numeric(20, 16), nullable=True),
        sa.Column("J_net_m4", sa.Numeric(20, 16), nullable=True),
        sa.Column("centroid_y_m", sa.Numeric(12, 9), nullable=True),
        sa.Column("centroid_z_m", sa.Numeric(12, 9), nullable=True),
        sa.Column("principal_angle_deg", sa.Numeric(8, 4), nullable=True),
        sa.Column("method_level", sa.String(32), nullable=False, server_default="GLOBAL_EN40"),
        sa.Column("method_in_domain", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("requires_local_method", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("geometry_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_door_models_project", "door_section_models", ["project_id"])

    # ------------------------------------------------------------------
    # weld_groups
    # ------------------------------------------------------------------
    op.create_table(
        "weld_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_section_check_runs.id"), nullable=True),
        sa.Column("weld_type", postgresql.ENUM(name="weld_type", create_type=False), nullable=False),
        sa.Column("weld_process", postgresql.ENUM(name="weld_process", create_type=False), nullable=True),
        sa.Column("quality_class", postgresql.ENUM(name="weld_quality_class", create_type=False), nullable=True),
        sa.Column("weld_group_geometry", postgresql.JSONB, nullable=False),
        sa.Column("effective_throat_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("effective_length_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("ineffective_length_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("base_material_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_product_properties.id"), nullable=True),
        sa.Column("filler_material", sa.String(64), nullable=True),
        sa.Column("fu_w_mpa", sa.Numeric(8, 2), nullable=True),
        sa.Column("wps_reference", sa.String(64), nullable=True),
        sa.Column("position", sa.String(16), nullable=True),
        sa.Column("accessible_for_inspection", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("fabricable", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("Fx_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Fy_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Fz_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Mx_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("My_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("Mz_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("sigma_eq_mpa", sa.Numeric(10, 4), nullable=True),
        sa.Column("sigma_rd_mpa", sa.Numeric(10, 4), nullable=True),
        sa.Column("static_utilization", sa.Numeric(8, 6), nullable=True),
        sa.Column("static_status", postgresql.ENUM(name="steel_check_status", create_type=False), nullable=True),
        sa.Column("delta_sigma_mpa", sa.Numeric(10, 4), nullable=True),
        sa.Column("fatigue_category", sa.String(16), nullable=True),
        sa.Column("fatigue_cycles", sa.Numeric(14, 2), nullable=True),
        sa.Column("fatigue_damage", sa.Numeric(10, 8), nullable=True),
        sa.Column("fatigue_utilization", sa.Numeric(8, 6), nullable=True),
        sa.Column("fatigue_status", postgresql.ENUM(name="steel_check_status", create_type=False), nullable=True),
        sa.Column("inspection_method", sa.String(32), nullable=True),
        sa.Column("inspection_extent_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("inspection_criterion", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_weld_groups_project", "weld_groups", ["project_id"])
    op.create_index("ix_weld_groups_type", "weld_groups", ["weld_type"])

    # ------------------------------------------------------------------
    # fatigue_details
    # ------------------------------------------------------------------
    op.create_table(
        "fatigue_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("detail_id", sa.String(32), nullable=False),
        sa.Column("description", sa.String(256), nullable=False),
        sa.Column("eligible_geometry", postgresql.JSONB, nullable=False),
        sa.Column("stress_orientation", sa.String(32), nullable=False),
        sa.Column("fatigue_category_mpa", sa.Numeric(8, 2), nullable=False),
        sa.Column("sn_curve_id", sa.String(32), nullable=False),
        sa.Column("thickness_limit_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("norm", sa.String(32), nullable=False),
        sa.Column("norm_edition", sa.String(16), nullable=True),
        sa.Column("norm_clause", sa.String(32), nullable=True),
        sa.Column("quality_required", postgresql.ENUM(name="weld_quality_class", create_type=False), nullable=True),
        sa.Column("domain_min_thickness_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("domain_max_thickness_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("domain_notes", sa.Text, nullable=True),
        sa.Column("validation_cases", postgresql.JSONB, nullable=True),
        sa.Column("reference_images", postgresql.JSONB, nullable=True),
        sa.Column("library_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deprecated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_fatigue_details_detail_id", "fatigue_details", ["detail_id"])

    # ------------------------------------------------------------------
    # durability_systems
    # ------------------------------------------------------------------
    op.create_table(
        "durability_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component", sa.String(64), nullable=True, server_default="FULL_COLUMN"),
        sa.Column("corrosivity_category", postgresql.ENUM(name="corrosivity_category", create_type=False), nullable=False),
        sa.Column("design_life_years", sa.Integer, nullable=False),
        sa.Column("exposure_type", sa.String(64), nullable=True),
        sa.Column("protection_system", postgresql.ENUM(name="protection_system", create_type=False), nullable=False),
        sa.Column("layers", postgresql.JSONB, nullable=False),
        sa.Column("surface_preparation", sa.String(32), nullable=True),
        sa.Column("maintenance_interval_years", sa.Integer, nullable=True),
        sa.Column("maintenance_notes", sa.Text, nullable=True),
        sa.Column("galvanizing_vent_holes_ok", sa.Boolean, nullable=True),
        sa.Column("galvanizing_drain_holes_ok", sa.Boolean, nullable=True),
        sa.Column("closed_cavities_detected", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("compatible", sa.Boolean, nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("cost_per_m2", sa.Numeric(10, 4), nullable=True),
        sa.Column("co2_kg_per_m2", sa.Numeric(10, 4), nullable=True),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_durability_project", "durability_systems", ["project_id"])

    # ------------------------------------------------------------------
    # manufacturing_calibrations
    # ------------------------------------------------------------------
    op.create_table(
        "manufacturing_calibrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("material", sa.String(32), nullable=False),
        sa.Column("thickness_min_mm", sa.Numeric(6, 2), nullable=False),
        sa.Column("thickness_max_mm", sa.Numeric(6, 2), nullable=False),
        sa.Column("machine", sa.String(64), nullable=True),
        sa.Column("tool", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("bend_allowance_mm", sa.Numeric(8, 4), nullable=True),
        sa.Column("springback_deg", sa.Numeric(6, 3), nullable=True),
        sa.Column("min_inner_radius_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("k_factor", sa.Numeric(6, 4), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # manufacturing_routes
    # ------------------------------------------------------------------
    op.create_table(
        "manufacturing_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", postgresql.ENUM(name="steel_run_status", create_type=False), nullable=False),
        sa.Column("bom", postgresql.JSONB, nullable=True),
        sa.Column("total_mass_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("total_surface_m2", sa.Numeric(10, 4), nullable=True),
        sa.Column("material_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("process_cost", postgresql.JSONB, nullable=True),
        sa.Column("total_industrial_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("margin_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("margin_type", sa.String(16), nullable=True),
        sa.Column("sale_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="EUR"),
        sa.Column("co2_steel_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("co2_process_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("co2_coating_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("co2_transport_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("co2_total_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("blocking_rules", postgresql.JSONB, nullable=True),
        sa.Column("all_fabricable", sa.Boolean, nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("blank_geometry", postgresql.JSONB, nullable=True),
        sa.Column("bend_lines", postgresql.JSONB, nullable=True),
        sa.Column("nesting", postgresql.JSONB, nullable=True),
        sa.Column("tolerances", postgresql.JSONB, nullable=True),
        sa.Column("calibration_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("manufacturing_calibrations.id"), nullable=True),
        sa.Column("is_preliminary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_mfg_routes_project", "manufacturing_routes", ["project_id"])

    # ------------------------------------------------------------------
    # steel_joints
    # ------------------------------------------------------------------
    op.create_table(
        "steel_joints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_section_check_runs.id"), nullable=True),
        sa.Column("joint_type", postgresql.ENUM(name="steel_joint_type", create_type=False), nullable=False),
        sa.Column("position_z_m", sa.Numeric(8, 4), nullable=False),
        sa.Column("nominal_overlap_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("min_overlap_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("taper_compatibility", sa.Boolean, nullable=True),
        sa.Column("rotational_stiffness_nm_per_rad", sa.Numeric(14, 2), nullable=True),
        sa.Column("axial_stiffness_n_per_m", sa.Numeric(14, 2), nullable=True),
        sa.Column("stiffness_validated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("N_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Vy_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("Vz_kn", sa.Numeric(14, 4), nullable=True),
        sa.Column("T_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("My_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("Mz_knm", sa.Numeric(14, 6), nullable=True),
        sa.Column("static_status", postgresql.ENUM(name="steel_check_status", create_type=False), nullable=True),
        sa.Column("fatigue_status", postgresql.ENUM(name="steel_check_status", create_type=False), nullable=True),
        sa.Column("slip_status", postgresql.ENUM(name="steel_check_status", create_type=False), nullable=True),
        sa.Column("within_validated_domain", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("design_sequence", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_steel_joints_project", "steel_joints", ["project_id"])

    # ------------------------------------------------------------------
    # steel_optimization_runs
    # ------------------------------------------------------------------
    op.create_table(
        "steel_optimization_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", postgresql.ENUM(name="steel_run_status", create_type=False), nullable=False),
        sa.Column("utilization_limit", sa.Numeric(6, 4), nullable=False, server_default="1.0"),
        sa.Column("max_piece_length_m", sa.Numeric(6, 2), nullable=False, server_default="12.0"),
        sa.Column("min_diameter_mm", sa.Numeric(6, 2), nullable=False, server_default="60.0"),
        sa.Column("available_grades", postgresql.JSONB, nullable=True),
        sa.Column("available_thicknesses_mm", postgresql.JSONB, nullable=True),
        sa.Column("allowed_tapers", postgresql.JSONB, nullable=True),
        sa.Column("pareto_front", postgresql.JSONB, nullable=True),
        sa.Column("n_candidates_generated", sa.Integer, nullable=True),
        sa.Column("n_candidates_filtered", sa.Integer, nullable=True),
        sa.Column("n_candidates_calculated", sa.Integer, nullable=True),
        sa.Column("n_pareto_solutions", sa.Integer, nullable=True),
        sa.Column("min_cost_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("min_weight_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("min_co2_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("balanced_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_opt_runs_project", "steel_optimization_runs", ["project_id"])

    # ------------------------------------------------------------------
    # steel_optimization_candidates
    # ------------------------------------------------------------------
    op.create_table(
        "steel_optimization_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("optimization_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_optimization_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("steel_grade", postgresql.ENUM(name="steel_grade", create_type=False), nullable=False),
        sa.Column("subgrade", postgresql.ENUM(name="steel_subgrade", create_type=False), nullable=True),
        sa.Column("thickness_profile", postgresql.JSONB, nullable=False),
        sa.Column("diameter_base_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("diameter_top_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("taper_per_mille", sa.Numeric(6, 3), nullable=True),
        sa.Column("n_faces", sa.Integer, nullable=True),
        sa.Column("segments", postgresql.JSONB, nullable=True),
        sa.Column("total_mass_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("total_industrial_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("co2_total_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("max_utilization", sa.Numeric(8, 6), nullable=True),
        sa.Column("governing_check", sa.String(64), nullable=True),
        sa.Column("all_checks_passed", sa.Boolean, nullable=True),
        sa.Column("fabricable", sa.Boolean, nullable=True),
        sa.Column("transportable", sa.Boolean, nullable=True),
        sa.Column("pareto_dominated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("objective", postgresql.ENUM(name="optimization_objective", create_type=False), nullable=True),
        sa.Column("selected", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("check_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_section_check_runs.id"), nullable=True),
        sa.Column("manufacturing_route_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("manufacturing_routes.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_opt_candidates_run", "steel_optimization_candidates", ["optimization_run_id"])

    # ------------------------------------------------------------------
    # product_families
    # ------------------------------------------------------------------
    op.create_table(
        "product_families",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("domain", postgresql.JSONB, nullable=False),
        sa.Column("domain_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # validation_evidences
    # ------------------------------------------------------------------
    op.create_table(
        "validation_evidences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("product_families.id"), nullable=True),
        sa.Column("evidence_type", postgresql.ENUM(name="validation_evidence_type", create_type=False), nullable=False),
        sa.Column("reference", sa.String(256), nullable=False),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("tolerance", sa.Numeric(8, 4), nullable=True),
        sa.Column("result_summary", sa.Text, nullable=True),
        sa.Column("conservative_side", sa.Boolean, nullable=True),
        sa.Column("laboratory", sa.String(128), nullable=True),
        sa.Column("test_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_description", sa.Text, nullable=True),
        sa.Column("loads_applied", postgresql.JSONB, nullable=True),
        sa.Column("failure_mode", sa.String(128), nullable=True),
        sa.Column("solver_version", sa.String(32), nullable=True),
        sa.Column("norm_used", sa.String(64), nullable=True),
        sa.Column("inputs_hash", sa.String(64), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_val_evidences_family", "validation_evidences", ["family_id"])

    # ------------------------------------------------------------------
    # steel_report_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "steel_report_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("steel_section_check_runs.id"), nullable=True),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("maturity_level", postgresql.ENUM(name="maturity_level", create_type=False), nullable=False),
        sa.Column("language", sa.String(8), nullable=False, server_default="es"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("input_hashes", postgresql.JSONB, nullable=False),
        sa.Column("all_evidences_present", sa.Boolean, nullable=True),
        sa.Column("all_approvals_present", sa.Boolean, nullable=True),
        sa.Column("storage_path", sa.String(512), nullable=True),
        sa.Column("format", sa.String(16), nullable=False, server_default="PDF"),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_steel_reports_project", "steel_report_snapshots", ["project_id"])
    op.create_index("ix_steel_reports_type", "steel_report_snapshots", ["report_type"])


def downgrade() -> None:
    # Tablas en orden inverso de FK
    op.drop_table("steel_report_snapshots")
    op.drop_table("validation_evidences")
    op.drop_table("product_families")
    op.drop_table("steel_optimization_candidates")
    op.drop_table("steel_optimization_runs")
    op.drop_table("steel_joints")
    op.drop_table("manufacturing_routes")
    op.drop_table("manufacturing_calibrations")
    op.drop_table("durability_systems")
    op.drop_table("fatigue_details")
    op.drop_table("weld_groups")
    op.drop_table("door_section_models")
    op.drop_table("effective_section_runs")
    op.drop_table("steel_section_checks")
    op.drop_table("steel_section_check_runs")
    op.drop_table("steel_normative_routes")
    op.drop_table("steel_product_properties")

    # Enums
    for enum_name in [
        "validation_evidence_type", "maturity_level", "optimization_objective",
        "steel_run_status", "steel_joint_type", "protection_system", "corrosivity_category",
        "fatigue_method", "weld_quality_class", "weld_process", "weld_type",
        "steel_check_status", "section_property_set", "route_decision_status",
        "normative_route", "steel_product_form", "steel_subgrade", "steel_grade",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
