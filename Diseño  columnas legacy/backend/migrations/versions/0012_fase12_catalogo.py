"""Fase 12 · Catálogo y Selección Estándar

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Enums ----
    op.execute("""
        CREATE TYPE productstatus12 AS ENUM
        ('DRAFT', 'CANDIDATE', 'HOMOLOGATED', 'RESTRICTED', 'SUSPENDED', 'OBSOLETE', 'RETIRED')
    """)
    # Duplicate for product_revision table
    op.execute("""
        CREATE TYPE productstatus12_rev AS ENUM
        ('DRAFT', 'CANDIDATE', 'HOMOLOGATED', 'RESTRICTED', 'SUSPENDED', 'OBSOLETE', 'RETIRED')
    """)
    op.execute("""
        CREATE TYPE applicabilitystatus12 AS ENUM
        ('COVERED', 'RECALCULATE', 'CONDITIONAL', 'OUT_OF_SCOPE', 'UNKNOWN')
    """)
    op.execute("""
        CREATE TYPE applicabilitystatus12_ev AS ENUM
        ('COVERED', 'RECALCULATE', 'CONDITIONAL', 'OUT_OF_SCOPE', 'UNKNOWN')
    """)
    op.execute("""
        CREATE TYPE verificationroute12 AS ENUM ('ROUTE_A', 'ROUTE_B', 'ROUTE_C')
    """)
    op.execute("""
        CREATE TYPE evidencetype12 AS ENUM
        ('TEST', 'CALCULATION', 'CERTIFICATE', 'INSPECTION', 'FEM', 'DECLARATION', 'APPROVAL')
    """)
    op.execute("""
        CREATE TYPE evidencequalitystatus12 AS ENUM
        ('PENDING', 'REVIEWED', 'APPROVED', 'EXPIRED', 'REJECTED')
    """)
    op.execute("""
        CREATE TYPE substitutiontype12 AS ENUM
        ('EXACT', 'TECHNICAL', 'COMMERCIAL', 'SUPERIOR', 'CONDITIONAL', 'NOT_EQUIVALENT')
    """)
    op.execute("""
        CREATE TYPE thirdpartystatus12 AS ENUM
        ('DISCOVERED', 'UNDER_REVIEW', 'APPROVED', 'CONDITIONED', 'SUSPENDED', 'WITHDRAWN')
    """)
    op.execute("""
        CREATE TYPE datasourcetype12 AS ENUM
        ('CONFIRMED', 'IMPORTED', 'CALCULATED', 'ESTIMATED', 'CONSERVATIVE', 'PENDING', 'CONFLICT')
    """)
    op.execute("""
        CREATE TYPE rankingprofile12 AS ENUM
        ('COMMERCIAL', 'ENGINEERING', 'ESG', 'URGENT', 'MAINTENANCE')
    """)
    op.execute("""
        CREATE TYPE importjobstatus12 AS ENUM
        ('PENDING', 'RUNNING', 'STAGED', 'REVIEWING', 'PUBLISHED', 'FAILED', 'ROLLED_BACK')
    """)
    op.execute("""
        CREATE TYPE optiontype12 AS ENUM
        ('COSMETIC', 'MINOR_GEOMETRIC', 'STRUCTURAL', 'MATERIAL_PROCESS', 'MARKET', 'ACCESSORY')
    """)
    op.execute("""
        CREATE TYPE optiontype12_opt AS ENUM
        ('COSMETIC', 'MINOR_GEOMETRIC', 'STRUCTURAL', 'MATERIAL_PROCESS', 'MARKET', 'ACCESSORY')
    """)
    op.execute("""
        CREATE TYPE compatibilityruleop12 AS ENUM
        ('REQUIRE', 'EXCLUDE', 'IMPLIES', 'RANGE', 'ONE_OF', 'ALL_OF')
    """)
    op.execute("""
        CREATE TYPE selectionrunstatus12 AS ENUM
        ('RUNNING', 'COMPLETED', 'FAILED', 'NEEDS_CUSTOM')
    """)

    # ---- Tables ----

    # product_family
    op.create_table(
        "product_family",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("material", sa.String(32), nullable=False),
        sa.Column("geometry_type", sa.String(64), nullable=True),
        sa.Column("base_type", sa.String(32), nullable=True),
        sa.Column("has_hierarchy", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("hierarchy_description", sa.Text(), nullable=True),
        sa.Column("extension_rules_version", sa.String(32), nullable=True),
        sa.Column("is_third_party", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("third_party_status", postgresql.ENUM("DISCOVERED", "UNDER_REVIEW", "APPROVED",
                                                "CONDITIONED", "SUSPENDED", "WITHDRAWN",
                                                name="thirdpartystatus12", create_type=False), nullable=True),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_productfamily_code", "product_family", ["code"])

    # standard_product
    op.create_table(
        "standard_product",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("product_family.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("status", postgresql.ENUM("DRAFT", "CANDIDATE", "HOMOLOGATED", "RESTRICTED",
                                    "SUSPENDED", "OBSOLETE", "RETIRED",
                                    name="productstatus12", create_type=False), nullable=False,
                  server_default="DRAFT"),
        sa.Column("current_revision", sa.String(32), nullable=True),
        sa.Column("nominal_height_m", sa.Float(), nullable=True),
        sa.Column("total_height_m", sa.Float(), nullable=True),
        sa.Column("base_type", sa.String(32), nullable=True),
        sa.Column("geometry_definition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("material_grade", sa.String(64), nullable=True),
        sa.Column("material_data_source", postgresql.ENUM("CONFIRMED", "IMPORTED", "CALCULATED",
                                                  "ESTIMATED", "CONSERVATIVE", "PENDING",
                                                  "CONFLICT", name="datasourcetype12", create_type=False),
                  nullable=False, server_default="PENDING"),
        sa.Column("piece_length_m", sa.Float(), nullable=True),
        sa.Column("piece_mass_kg", sa.Float(), nullable=True),
        sa.Column("is_segmented", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("segment_count", sa.Integer(), nullable=True),
        sa.Column("total_co2_kg", sa.Float(), nullable=True),
        sa.Column("sales_regions", postgresql.JSONB(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("minimum_order", sa.Integer(), nullable=True),
        sa.Column("quality_index", sa.Float(), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("family_id", "code", name="uq_standard_product_family_code"),
    )
    op.create_index("ix_standardproduct_code", "standard_product", ["code"])
    op.create_index("ix_standardproduct_status", "standard_product", ["status"])
    op.create_index("ix_standardproduct_family_id", "standard_product", ["family_id"])

    # product_revision (immutable)
    op.create_table(
        "product_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("standard_product.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.String(32), nullable=False),
        sa.Column("status_at_revision", postgresql.ENUM("DRAFT", "CANDIDATE", "HOMOLOGATED",
                                                "RESTRICTED", "SUSPENDED", "OBSOLETE",
                                                "RETIRED", name="productstatus12_rev", create_type=False),
                  nullable=False),
        sa.Column("geometry_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("material_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("performance_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("options_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("superseded_by_revision", sa.String(32), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("published_by", sa.String(128), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", postgresql.JSONB(), nullable=True),
        sa.Column("data_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("product_id", "revision_number", name="uq_revision_product_rev"),
    )
    op.create_index("ix_productrevision_product_id", "product_revision", ["product_id"])

    # product_variant
    op.create_table(
        "product_variant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("standard_product.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("option_type", postgresql.ENUM("COSMETIC", "MINOR_GEOMETRIC", "STRUCTURAL",
                                         "MATERIAL_PROCESS", "MARKET", "ACCESSORY",
                                         name="optiontype12", create_type=False), nullable=False),
        sa.Column("requires_recalculation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("alters_mass", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("alters_wind_area", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("alters_fatigue", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("parameter_deltas", postgresql.JSONB(), nullable=True),
        sa.Column("cost_delta_eur", sa.Float(), nullable=True),
        sa.Column("co2_delta_kg", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_productvariant_product_id", "product_variant", ["product_id"])

    # product_option
    op.create_table(
        "product_option",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("product_family.id", ondelete="CASCADE"), nullable=False),
        sa.Column("option_group", sa.String(64), nullable=False),
        sa.Column("option_key", sa.String(64), nullable=False),
        sa.Column("option_label", sa.String(256), nullable=True),
        sa.Column("option_type", postgresql.ENUM("COSMETIC", "MINOR_GEOMETRIC", "STRUCTURAL",
                                         "MATERIAL_PROCESS", "MARKET", "ACCESSORY",
                                         name="optiontype12_opt", create_type=False), nullable=False),
        sa.Column("affects_calculation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("affects_bom", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("requires_recalculation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("default_value", sa.String(128), nullable=True),
        sa.Column("allowed_values", postgresql.JSONB(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_productoption_family_id", "product_option", ["family_id"])

    # compatibility_rule
    op.create_table(
        "compatibility_rule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("product_family.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("rule_op", postgresql.ENUM("REQUIRE", "EXCLUDE", "IMPLIES", "RANGE",
                                     "ONE_OF", "ALL_OF", name="compatibilityruleop12", create_type=False),
                  nullable=False),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("consequence", postgresql.JSONB(), nullable=False),
        sa.Column("rule_dsl", sa.Text(), nullable=True),
        sa.Column("version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_compatibilityrule_family_id", "compatibility_rule", ["family_id"])

    # performance_envelope
    op.create_table(
        "performance_envelope",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("standard_product.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applicability_status", postgresql.ENUM("COVERED", "RECALCULATE", "CONDITIONAL",
                                                  "OUT_OF_SCOPE", "UNKNOWN",
                                                  name="applicabilitystatus12", create_type=False),
                  nullable=False, server_default="UNKNOWN"),
        sa.Column("max_moment_knm", sa.Float(), nullable=True),
        sa.Column("max_shear_kn", sa.Float(), nullable=True),
        sa.Column("max_axial_kn", sa.Float(), nullable=True),
        sa.Column("max_height_m", sa.Float(), nullable=True),
        sa.Column("min_height_m", sa.Float(), nullable=True),
        sa.Column("max_wind_area_m2", sa.Float(), nullable=True),
        sa.Column("max_luminaire_mass_kg", sa.Float(), nullable=True),
        sa.Column("max_utilization", sa.Float(), nullable=True),
        sa.Column("domain_envelope", postgresql.JSONB(), nullable=True),
        sa.Column("domain_type", sa.String(32), nullable=True),
        sa.Column("governing_check", sa.String(128), nullable=True),
        sa.Column("norm_edition", sa.String(64), nullable=True),
        sa.Column("country_scope", postgresql.JSONB(), nullable=True),
        sa.Column("calc_hash", sa.String(64), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_performanceenvelope_product_id", "performance_envelope", ["product_id"])

    # evidence_record (immutable when approved)
    op.create_table(
        "evidence_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("standard_product.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_type", postgresql.ENUM("TEST", "CALCULATION", "CERTIFICATE",
                                           "INSPECTION", "FEM", "DECLARATION", "APPROVAL",
                                           name="evidencetype12", create_type=False), nullable=False),
        sa.Column("quality_status", postgresql.ENUM("PENDING", "REVIEWED", "APPROVED",
                                            "EXPIRED", "REJECTED",
                                            name="evidencequalitystatus12", create_type=False),
                  nullable=False, server_default="PENDING"),
        sa.Column("source", sa.String(256), nullable=True),
        sa.Column("reference_code", sa.String(128), nullable=True),
        sa.Column("tested_object", sa.Text(), nullable=True),
        sa.Column("conditions", postgresql.JSONB(), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("applicability", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_date", sa.DateTime(), nullable=True),
        sa.Column("expiry_date", sa.DateTime(), nullable=True),
        sa.Column("has_domain", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("file_ref", sa.String(512), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_evidencerecord_product_id", "evidence_record", ["product_id"])

    # extension_rule
    op.create_table(
        "extension_rule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("product_family.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("allowed_variables", postgresql.JSONB(), nullable=True),
        sa.Column("allowed_ranges", postgresql.JSONB(), nullable=True),
        sa.Column("conservative_factor", sa.Float(), nullable=True),
        sa.Column("covers_product_ids", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_extensionrule_family_id", "extension_rule", ["family_id"])
    op.create_index("ix_extensionrule_evidence_id", "extension_rule", ["evidence_id"])

    # hierarchy_definition
    op.create_table(
        "hierarchy_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("product_family.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hierarchy_code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ordinal_map", postgresql.JSONB(), nullable=True),
        sa.Column("comparison_basis", sa.Text(), nullable=True),
        sa.Column("upgrade_rule", sa.Text(), nullable=True),
        sa.Column("cross_family_allowed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fallback", sa.String(64), nullable=True),
        sa.Column("version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_hierarchydefinition_family_id", "hierarchy_definition", ["family_id"])

    # substitution_relation
    op.create_table(
        "substitution_relation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("standard_product.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("to_product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("standard_product.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("substitution_type", postgresql.ENUM("EXACT", "TECHNICAL", "COMMERCIAL",
                                               "SUPERIOR", "CONDITIONAL", "NOT_EQUIVALENT",
                                               name="substitutiontype12", create_type=False), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), nullable=True),
        sa.Column("adaptations_required", postgresql.JSONB(), nullable=True),
        sa.Column("requires_recalculation", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("interface_changes", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("from_product_id", "to_product_id",
                            name="uq_substitution_from_to"),
    )
    op.create_index("ix_substitution_from", "substitution_relation", ["from_product_id"])

    # market_availability
    op.create_table(
        "market_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("standard_product.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_code", sa.String(4), nullable=False),
        sa.Column("norm_edition", sa.String(64), nullable=True),
        sa.Column("manufacturing_site", sa.String(128), nullable=True),
        sa.Column("stock_status", sa.String(32), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("lead_time_range_days", sa.Integer(), nullable=True),
        sa.Column("minimum_order", sa.Integer(), nullable=True),
        sa.Column("supply_risk", sa.String(16), nullable=True),
        sa.Column("supply_risk_reason", sa.String(256), nullable=True),
        sa.Column("price_eur", sa.Float(), nullable=True),
        sa.Column("price_date", sa.DateTime(), nullable=True),
        sa.Column("currency", sa.String(4), nullable=True, server_default="EUR"),
        sa.Column("is_offerable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_technically_valid", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("product_id", "country_code", "manufacturing_site",
                            name="uq_market_product_country_site"),
    )
    op.create_index("ix_marketavailability_product_id", "market_availability", ["product_id"])

    # selection_run (immutable)
    op.create_table(
        "selection_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("selection_code", sa.String(64), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_revision", sa.String(64), nullable=True),
        sa.Column("catalog_snapshot_id", sa.String(64), nullable=True),
        sa.Column("requirements_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("ranking_profile", postgresql.ENUM("COMMERCIAL", "ENGINEERING", "ESG",
                                             "URGENT", "MAINTENANCE",
                                             name="rankingprofile12", create_type=False),
                  nullable=False, server_default="COMMERCIAL"),
        sa.Column("utilization_limit", sa.Float(), nullable=True, server_default="0.9"),
        sa.Column("status", postgresql.ENUM("RUNNING", "COMPLETED", "FAILED", "NEEDS_CUSTOM",
                                    name="selectionrunstatus12", create_type=False),
                  nullable=False, server_default="RUNNING"),
        sa.Column("recommended_product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recommended_revision", sa.String(32), nullable=True),
        sa.Column("recommended_configuration_hash", sa.String(64), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("governing_check", sa.String(128), nullable=True),
        sa.Column("max_utilization", sa.Float(), nullable=True),
        sa.Column("next_action", sa.String(64), nullable=True),
        sa.Column("selection_trace_hash", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("run_by", sa.String(128), nullable=True),
        sa.Column("run_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_selectionrun_project_id", "selection_run", ["project_id"])

    # candidate_evaluation
    op.create_table(
        "candidate_evaluation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("selection_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_code", sa.String(128), nullable=True),
        sa.Column("passed_hard_filters", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("discard_reasons", postgresql.JSONB(), nullable=True),
        sa.Column("applicability_status", postgresql.ENUM("COVERED", "RECALCULATE", "CONDITIONAL",
                                                  "OUT_OF_SCOPE", "UNKNOWN",
                                                  name="applicabilitystatus12_ev", create_type=False), nullable=True),
        sa.Column("verification_route", postgresql.ENUM("ROUTE_A", "ROUTE_B", "ROUTE_C",
                                                name="verificationroute12", create_type=False), nullable=True),
        sa.Column("max_utilization", sa.Float(), nullable=True),
        sa.Column("governing_check", sa.String(128), nullable=True),
        sa.Column("compliant", sa.Boolean(), nullable=True),
        sa.Column("hierarchy_ordinal", sa.Integer(), nullable=True),
        sa.Column("is_immediately_superior", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_inferior_candidate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("score_total", sa.Float(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("label", sa.String(32), nullable=True),
        sa.Column("configuration_applied", postgresql.JSONB(), nullable=True),
        sa.Column("configuration_delta", postgresql.JSONB(), nullable=True),
        sa.Column("verification_detail", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_candidateevaluation_run_id", "candidate_evaluation", ["run_id"])
    op.create_index("ix_candidateevaluation_product_id", "candidate_evaluation", ["product_id"])

    # catalog_import_job
    op.create_table(
        "catalog_import_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_code", sa.String(64), nullable=True),
        sa.Column("status", postgresql.ENUM("PENDING", "RUNNING", "STAGED", "REVIEWING",
                                    "PUBLISHED", "FAILED", "ROLLED_BACK",
                                    name="importjobstatus12", create_type=False), nullable=False,
                  server_default="PENDING"),
        sa.Column("source_file_name", sa.String(512), nullable=True),
        sa.Column("source_file_hash", sa.String(64), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("mapping_template_id", sa.String(64), nullable=True),
        sa.Column("mapping_template_version", sa.String(16), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("imported_ok", sa.Integer(), nullable=True),
        sa.Column("errors", sa.Integer(), nullable=True),
        sa.Column("warnings", sa.Integer(), nullable=True),
        sa.Column("staged_product_ids", postgresql.JSONB(), nullable=True),
        sa.Column("error_report", postgresql.JSONB(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("published_by", sa.String(128), nullable=True),
        sa.Column("reviewed_by", postgresql.JSONB(), nullable=True),
        sa.Column("rollback_available", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("rollback_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True, unique=True),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_candidateevaluation_product_id", "candidate_evaluation")
    op.drop_index("ix_candidateevaluation_run_id", "candidate_evaluation")
    op.drop_index("ix_selectionrun_project_id", "selection_run")
    op.drop_index("ix_marketavailability_product_id", "market_availability")
    op.drop_index("ix_substitution_from", "substitution_relation")
    op.drop_index("ix_hierarchydefinition_family_id", "hierarchy_definition")
    op.drop_index("ix_extensionrule_evidence_id", "extension_rule")
    op.drop_index("ix_extensionrule_family_id", "extension_rule")
    op.drop_index("ix_evidencerecord_product_id", "evidence_record")
    op.drop_index("ix_performanceenvelope_product_id", "performance_envelope")
    op.drop_index("ix_compatibilityrule_family_id", "compatibility_rule")
    op.drop_index("ix_productoption_family_id", "product_option")
    op.drop_index("ix_productvariant_product_id", "product_variant")
    op.drop_index("ix_productrevision_product_id", "product_revision")
    op.drop_index("ix_standardproduct_family_id", "standard_product")
    op.drop_index("ix_standardproduct_status", "standard_product")
    op.drop_index("ix_standardproduct_code", "standard_product")
    op.drop_index("ix_productfamily_code", "product_family")

    op.drop_table("catalog_import_job")
    op.drop_table("candidate_evaluation")
    op.drop_table("selection_run")
    op.drop_table("market_availability")
    op.drop_table("substitution_relation")
    op.drop_table("hierarchy_definition")
    op.drop_table("extension_rule")
    op.drop_table("evidence_record")
    op.drop_table("performance_envelope")
    op.drop_table("compatibility_rule")
    op.drop_table("product_option")
    op.drop_table("product_variant")
    op.drop_table("product_revision")
    op.drop_table("standard_product")
    op.drop_table("product_family")

    for t in ["selectionrunstatus12", "compatibilityruleop12",
              "optiontype12_opt", "optiontype12", "importjobstatus12",
              "rankingprofile12", "datasourcetype12", "thirdpartystatus12",
              "substitutiontype12", "evidencequalitystatus12", "evidencetype12",
              "verificationroute12", "applicabilitystatus12_ev",
              "applicabilitystatus12", "productstatus12_rev", "productstatus12"]:
        op.execute(f"DROP TYPE IF EXISTS {t}")
