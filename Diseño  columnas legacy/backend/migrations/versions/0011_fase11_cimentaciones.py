"""Fase 11 · Cimentaciones y Geotecnia

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Enums ----
    op.execute("""
        CREATE TYPE geotechnicallevel11 AS ENUM
        ('G0', 'G1', 'G2', 'G3', 'G4')
    """)
    op.execute("""
        CREATE TYPE foundationfamily11 AS ENUM
        ('F11-A', 'F11-B', 'F11-C', 'F11-D', 'F11-E', 'F11-F', 'F11-G', 'F11-H')
    """)
    op.execute("""
        CREATE TYPE soilclass11 AS ENUM
        ('ROCK', 'DENSE_GRAVEL', 'DENSE_SAND', 'MEDIUM_SAND', 'LOOSE_SAND',
         'STIFF_CLAY', 'FIRM_CLAY', 'SOFT_CLAY', 'CONTROLLED_FILL',
         'UNKNOWN_FILL', 'EXPANSIVE', 'COLLAPSIBLE')
    """)
    op.execute("""
        CREATE TYPE drainagecondition11 AS ENUM ('DRAINED', 'UNDRAINED', 'BOTH')
    """)
    op.execute("""
        CREATE TYPE waterscenario11 AS ENUM
        ('NONE', 'PERMANENT', 'SEASONAL', 'ACCIDENTAL', 'UNKNOWN')
    """)
    op.execute("""
        CREATE TYPE foundationcandidatestatus11 AS ENUM
        ('DRAFT', 'PREDIMENSIONED', 'CALCULATED', 'VERIFIED', 'OPTIMIZED', 'REJECTED', 'RELEASED')
    """)
    op.execute("""
        CREATE TYPE foundationmaturity11 AS ENUM ('M0', 'M1', 'M2', 'M3', 'M4')
    """)
    op.execute("""
        CREATE TYPE foundationcheckmode11 AS ENUM
        ('BEARING_CAPACITY', 'OVERTURNING', 'SLIDING', 'UPLIFT', 'FLOTATION',
         'PUNCHING', 'SHEAR_1D', 'BENDING_PLATE', 'LOCAL_COMPRESSION', 'DEFORMATION_SLS')
    """)
    op.execute("""
        CREATE TYPE stiffnessmodel11 AS ENUM
        ('RIGID', 'ELASTIC_LINEAR', 'ELASTIC_FULL', 'NONLINEAR', 'EXTERNAL_FEM')
    """)
    op.execute("""
        CREATE TYPE embedmentfill11 AS ENUM
        ('CONCRETE', 'GROUT', 'GRANULAR_CONTROLLED', 'GRANULAR_UNKNOWN')
    """)
    op.execute("""
        CREATE TYPE evidencetype11 AS ENUM
        ('MANUAL_CALC', 'SOFTWARE', 'TEST', 'APPROVAL', 'AS_BUILT')
    """)
    # Duplicate type for evidence table (different name to avoid collision)
    op.execute("""
        CREATE TYPE geotechnicallevel11_ev AS ENUM
        ('G0', 'G1', 'G2', 'G3', 'G4')
    """)

    # ---- Tables ----

    # geotechnical_site_model
    op.create_table(
        "geotechnical_site_model",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("geo_level", postgresql.ENUM("G0", "G1", "G2", "G3", "G4",
                                        name="geotechnicallevel11", create_type=False), nullable=False,
                  server_default="G0"),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("country_code", sa.String(4), nullable=True),
        sa.Column("municipality", sa.String(128), nullable=True),
        sa.Column("altitude_m", sa.Float(), nullable=True),
        sa.Column("frost_depth_m", sa.Float(), nullable=True),
        sa.Column("seismic_zone", sa.String(32), nullable=True),
        sa.Column("environmental_class", sa.String(32), nullable=True),
        sa.Column("water_scenario", postgresql.ENUM("NONE", "PERMANENT", "SEASONAL",
                                            "ACCIDENTAL", "UNKNOWN",
                                            name="waterscenario11", create_type=False), nullable=False,
                  server_default="UNKNOWN"),
        sa.Column("water_table_depth_m", sa.Float(), nullable=True),
        sa.Column("water_table_seasonal_high_m", sa.Float(), nullable=True),
        sa.Column("surface_type", sa.String(64), nullable=True),
        sa.Column("slope_near_m", sa.Float(), nullable=True),
        sa.Column("buried_services", sa.Boolean(), nullable=True),
        sa.Column("proximity_slope", sa.Boolean(), nullable=True),
        sa.Column("data_source", postgresql.JSONB(), nullable=True),
        sa.Column("confirmed_fields", postgresql.JSONB(), nullable=True),
        sa.Column("proposed_fields", postgresql.JSONB(), nullable=True),
        sa.Column("blockers", postgresql.JSONB(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(), nullable=True),
        sa.Column("calc_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_geosite_project_id", "geotechnical_site_model", ["project_id"])

    # soil_layer
    op.create_table(
        "soil_layer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geotechnical_site_model.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("layer_index", sa.Integer(), nullable=False),
        sa.Column("depth_top_m", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("depth_bottom_m", sa.Float(), nullable=False),
        sa.Column("soil_class", postgresql.ENUM(
            "ROCK", "DENSE_GRAVEL", "DENSE_SAND", "MEDIUM_SAND", "LOOSE_SAND",
            "STIFF_CLAY", "FIRM_CLAY", "SOFT_CLAY", "CONTROLLED_FILL",
            "UNKNOWN_FILL", "EXPANSIVE", "COLLAPSIBLE",
            name="soilclass11", create_type=False), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("gamma_kn_m3", sa.Float(), nullable=True),
        sa.Column("gamma_sat_kn_m3", sa.Float(), nullable=True),
        sa.Column("gamma_sub_kn_m3", sa.Float(), nullable=True),
        sa.Column("phi_deg", sa.Float(), nullable=True),
        sa.Column("c_kpa", sa.Float(), nullable=True),
        sa.Column("cu_kpa", sa.Float(), nullable=True),
        sa.Column("E_mpa", sa.Float(), nullable=True),
        sa.Column("nu", sa.Float(), nullable=True),
        sa.Column("ks_kn_m3", sa.Float(), nullable=True),
        sa.Column("drainage_condition", postgresql.ENUM("DRAINED", "UNDRAINED", "BOTH",
                                                name="drainagecondition11", create_type=False),
                  nullable=False, server_default="DRAINED"),
        sa.Column("source", sa.String(256), nullable=True),
        sa.Column("is_conservative_estimate", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_soillayer_site_id", "soil_layer", ["site_id"])

    # foundation_candidate
    op.create_table(
        "foundation_candidate",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("site_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geotechnical_site_model.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("family", postgresql.ENUM("F11-A", "F11-B", "F11-C", "F11-D", "F11-E",
                                    "F11-F", "F11-G", "F11-H",
                                    name="foundationfamily11", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM("DRAFT", "PREDIMENSIONED", "CALCULATED", "VERIFIED",
                                    "OPTIMIZED", "REJECTED", "RELEASED",
                                    name="foundationcandidatestatus11", create_type=False),
                  nullable=False, server_default="DRAFT"),
        sa.Column("maturity_level", postgresql.ENUM("M0", "M1", "M2", "M3", "M4",
                                            name="foundationmaturity11", create_type=False),
                  nullable=False, server_default="M0"),
        sa.Column("width_m", sa.Float(), nullable=True),
        sa.Column("length_m", sa.Float(), nullable=True),
        sa.Column("depth_m", sa.Float(), nullable=True),
        sa.Column("diameter_m", sa.Float(), nullable=True),
        sa.Column("pedestal_width_m", sa.Float(), nullable=True),
        sa.Column("pedestal_height_m", sa.Float(), nullable=True),
        sa.Column("fck_mpa", sa.Float(), nullable=True, server_default="25.0"),
        sa.Column("N_kn", sa.Float(), nullable=True),
        sa.Column("My_knm", sa.Float(), nullable=True),
        sa.Column("Mz_knm", sa.Float(), nullable=True),
        sa.Column("Vy_kn", sa.Float(), nullable=True),
        sa.Column("Vz_kn", sa.Float(), nullable=True),
        sa.Column("T_knm", sa.Float(), nullable=True),
        sa.Column("governing_combination", sa.String(64), nullable=True),
        sa.Column("util_bearing", sa.Float(), nullable=True),
        sa.Column("util_overturning", sa.Float(), nullable=True),
        sa.Column("util_sliding", sa.Float(), nullable=True),
        sa.Column("util_uplift", sa.Float(), nullable=True),
        sa.Column("util_governing", sa.Float(), nullable=True),
        sa.Column("governing_mode", sa.String(64), nullable=True),
        sa.Column("total_cost_eur", sa.Float(), nullable=True),
        sa.Column("concrete_volume_m3", sa.Float(), nullable=True),
        sa.Column("excavation_volume_m3", sa.Float(), nullable=True),
        sa.Column("total_co2_kg", sa.Float(), nullable=True),
        sa.Column("total_mass_kg", sa.Float(), nullable=True),
        sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("label", sa.String(32), nullable=True),
        sa.Column("calc_hash", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_foundationcandidate_site_id", "foundation_candidate", ["site_id"])

    # foundation_check
    op.create_table(
        "foundation_check",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("foundation_candidate.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("combination_id", sa.String(64), nullable=False),
        sa.Column("check_mode", postgresql.ENUM(
            "BEARING_CAPACITY", "OVERTURNING", "SLIDING", "UPLIFT", "FLOTATION",
            "PUNCHING", "SHEAR_1D", "BENDING_PLATE", "LOCAL_COMPRESSION",
            "DEFORMATION_SLS", name="foundationcheckmode11", create_type=False), nullable=False),
        sa.Column("demand", sa.Float(), nullable=True),
        sa.Column("resistance", sa.Float(), nullable=True),
        sa.Column("utilization", sa.Float(), nullable=True),
        sa.Column("governing", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("norm_clause", sa.String(128), nullable=True),
        sa.Column("factors", postgresql.JSONB(), nullable=True),
        sa.Column("error_codes", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_foundationcheck_candidate_id", "foundation_check", ["candidate_id"])

    # foundation_stiffness
    op.create_table(
        "foundation_stiffness",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("foundation_candidate.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("stiffness_model", postgresql.ENUM("RIGID", "ELASTIC_LINEAR", "ELASTIC_FULL",
                                             "NONLINEAR", "EXTERNAL_FEM",
                                             name="stiffnessmodel11", create_type=False),
                  nullable=False, server_default="ELASTIC_LINEAR"),
        sa.Column("kz_kn_m", sa.Float(), nullable=True),
        sa.Column("kx_kn_m", sa.Float(), nullable=True),
        sa.Column("ky_kn_m", sa.Float(), nullable=True),
        sa.Column("kthx_knm_rad", sa.Float(), nullable=True),
        sa.Column("kthy_knm_rad", sa.Float(), nullable=True),
        sa.Column("kthz_knm_rad", sa.Float(), nullable=True),
        sa.Column("matrix_6x6", postgresql.JSONB(), nullable=True),
        sa.Column("domain_conditions", postgresql.JSONB(), nullable=True),
        sa.Column("converged", sa.Boolean(), nullable=True),
        sa.Column("iterations", sa.Integer(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
    )

    # embedded_pole_model
    op.create_table(
        "embedded_pole_model",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("foundation_candidate.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("pole_diameter_mm", sa.Float(), nullable=False),
        sa.Column("block_diameter_m", sa.Float(), nullable=True),
        sa.Column("embedment_length_m", sa.Float(), nullable=False),
        sa.Column("fill_type", postgresql.ENUM("CONCRETE", "GROUT", "GRANULAR_CONTROLLED",
                                       "GRANULAR_UNKNOWN", name="embedmentfill11", create_type=False),
                  nullable=False, server_default="CONCRETE"),
        sa.Column("passive_pressure_kpa", sa.Float(), nullable=True),
        sa.Column("reaction_top_kn", sa.Float(), nullable=True),
        sa.Column("reaction_bottom_kn", sa.Float(), nullable=True),
        sa.Column("moment_at_surface_knm", sa.Float(), nullable=True),
        sa.Column("shear_at_surface_kn", sa.Float(), nullable=True),
        sa.Column("util_lateral", sa.Float(), nullable=True),
        sa.Column("util_toe", sa.Float(), nullable=True),
        sa.Column("has_bottom_drain", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("corrosion_protection", sa.String(128), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
    )

    # construction_scenario
    op.create_table(
        "construction_scenario",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("foundation_candidate.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("stage_name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("N_kn", sa.Float(), nullable=True),
        sa.Column("Vy_kn", sa.Float(), nullable=True),
        sa.Column("Vz_kn", sa.Float(), nullable=True),
        sa.Column("My_knm", sa.Float(), nullable=True),
        sa.Column("Mz_knm", sa.Float(), nullable=True),
        sa.Column("water_table_m", sa.Float(), nullable=True),
        sa.Column("concrete_strength_fraction", sa.Float(), nullable=True,
                  server_default="1.0"),
        sa.Column("util_governing", sa.Float(), nullable=True),
        sa.Column("compliant", sa.Boolean(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
    )

    # foundation_cost_model
    op.create_table(
        "foundation_cost_model",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("foundation_candidate.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("concrete_eur_m3", sa.Float(), nullable=True),
        sa.Column("excavation_eur_m3", sa.Float(), nullable=True),
        sa.Column("backfill_eur_m3", sa.Float(), nullable=True),
        sa.Column("grout_eur_m3", sa.Float(), nullable=True),
        sa.Column("labour_eur", sa.Float(), nullable=True),
        sa.Column("transport_eur", sa.Float(), nullable=True),
        sa.Column("prefab_eur", sa.Float(), nullable=True),
        sa.Column("concrete_volume_m3", sa.Float(), nullable=True),
        sa.Column("excavation_volume_m3", sa.Float(), nullable=True),
        sa.Column("backfill_volume_m3", sa.Float(), nullable=True),
        sa.Column("total_cost_eur", sa.Float(), nullable=True),
        sa.Column("cost_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("currency", sa.String(4), nullable=True, server_default="EUR"),
        sa.Column("price_date", sa.DateTime(), nullable=True),
        sa.Column("country_code", sa.String(4), nullable=True),
    )

    # foundation_carbon_model
    op.create_table(
        "foundation_carbon_model",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("foundation_candidate.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("concrete_co2_kg_m3", sa.Float(), nullable=True),
        sa.Column("steel_co2_kg_kg", sa.Float(), nullable=True),
        sa.Column("excavation_co2_kg_m3", sa.Float(), nullable=True),
        sa.Column("transport_co2_kg", sa.Float(), nullable=True),
        sa.Column("total_co2_kg", sa.Float(), nullable=True),
        sa.Column("co2_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("epd_references", postgresql.JSONB(), nullable=True),
    )

    # foundation_evidence
    op.create_table(
        "foundation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("foundation_candidate.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("evidence_type", postgresql.ENUM("MANUAL_CALC", "SOFTWARE", "TEST",
                                           "APPROVAL", "AS_BUILT",
                                           name="evidencetype11", create_type=False), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(256), nullable=True),
        sa.Column("file_ref", sa.String(512), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("geo_level_at_approval", postgresql.ENUM("G0", "G1", "G2", "G3", "G4",
                                                    name="geotechnicallevel11_ev", create_type=False),
                  nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_foundationevidence_candidate_id", "foundation_evidence",
                    ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_foundationevidence_candidate_id", "foundation_evidence")
    op.drop_index("ix_foundationcheck_candidate_id", "foundation_check")
    op.drop_index("ix_foundationcandidate_site_id", "foundation_candidate")
    op.drop_index("ix_soillayer_site_id", "soil_layer")
    op.drop_index("ix_geosite_project_id", "geotechnical_site_model")

    op.drop_table("foundation_evidence")
    op.drop_table("foundation_carbon_model")
    op.drop_table("foundation_cost_model")
    op.drop_table("construction_scenario")
    op.drop_table("embedded_pole_model")
    op.drop_table("foundation_stiffness")
    op.drop_table("foundation_check")
    op.drop_table("foundation_candidate")
    op.drop_table("soil_layer")
    op.drop_table("geotechnical_site_model")

    op.execute("DROP TYPE IF EXISTS geotechnicallevel11_ev")
    op.execute("DROP TYPE IF EXISTS evidencetype11")
    op.execute("DROP TYPE IF EXISTS embedmentfill11")
    op.execute("DROP TYPE IF EXISTS stiffnessmodel11")
    op.execute("DROP TYPE IF EXISTS foundationcheckmode11")
    op.execute("DROP TYPE IF EXISTS foundationmaturity11")
    op.execute("DROP TYPE IF EXISTS foundationcandidatestatus11")
    op.execute("DROP TYPE IF EXISTS waterscenario11")
    op.execute("DROP TYPE IF EXISTS drainagecondition11")
    op.execute("DROP TYPE IF EXISTS soilclass11")
    op.execute("DROP TYPE IF EXISTS foundationfamily11")
    op.execute("DROP TYPE IF EXISTS geotechnicallevel11")
