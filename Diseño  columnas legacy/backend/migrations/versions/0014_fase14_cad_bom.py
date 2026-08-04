"""Fase 14 · CAD paramétrico, BOM y documentación industrial

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# ── Nombres de enum PG (sufijo 14) ────────────────────────────────────────────
_ENUMS = [
    ("snapshotstate14",     ["DRAFT","REVIEW","APPROVED","RELEASED","OBSOLETE"]),
    ("cadlevel14",          ["G0_SCHEMATIC","G1_CALC","G2_ENGINEERING","G3_MANUFACTURING","G4_AS_BUILT"]),
    ("artifacttype14",      [
        "CAD_STEP","CAD_DXF","CAD_GLB","DRAWING_PDF",
        "BOM_EBOM","BOM_MBOM","BOM_PBOM","BOM_SBOM","BOM_ASBUILT","BOM_SERVICE",
        "ROUTING","DOC_PACKAGE","MANIFEST",
    ]),
    ("artifactstate14",     ["PENDING","GENERATING","VALID","ERROR","SUPERSEDED"]),
    ("bomview14",           ["EBOM","MBOM","PBOM","SBOM","ASBUILT","SERVICE"]),
    ("bomlinetype14",       [
        "MANUFACTURED","PURCHASED","RAW_MATERIAL","CONSUMABLE",
        "SUBCONTRACTED","PHANTOM","ALTERNATIVE","WASTE",
    ]),
    ("changeclass14",       ["EDITORIAL","INDUSTRIAL","GEOMETRIC","STRUCTURAL","REGULATORY"]),
    ("changestatus14",      ["DRAFT","UNDER_REVIEW","APPROVED","REJECTED","IMPLEMENTED"]),
    ("validationseverity14",["BLOCKING","ERROR","WARNING","INFO"]),
    ("operationtype14",     [
        "RECEPTION","CUTTING","BEVELING","BENDING","WELDING_LONGITUDINAL",
        "WELDING_CIRCUMFERENTIAL","ASSEMBLY","STRAIGHTENING","GALVANIZING",
        "PAINTING","MACHINING","INSPECTION","RELEASE",
    ]),
    ("releasegate14",       ["PENDING","PASSED","FAILED","WAIVED"]),
    ("documentaudience14",  ["CLIENT","ENGINEERING","PRODUCTION","QUALITY","SUPPLIER","SITE","REGULATORY"]),
]


def upgrade() -> None:
    # ── 1. Crear enums ─────────────────────────────────────────────────────────
    for name, values in _ENUMS:
        e = postgresql.ENUM(*values, name=name, create_type=True)
        e.create(op.get_bind(), checkfirst=True)

    # ── 2. product_snapshots ──────────────────────────────────────────────────
    op.create_table(
        "product_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_code", sa.String(80), nullable=False),
        sa.Column("revision", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("snapshot_hash", sa.String(64), nullable=True),
        sa.Column("material", sa.String(40), nullable=True),
        sa.Column("cad_level", sa.String(30), nullable=False, server_default="G2_ENGINEERING"),
        sa.Column("geometry_params", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("structural_hashes", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("library_versions", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("mass_kg_cad", sa.Float, nullable=True),
        sa.Column("mass_kg_bom", sa.Float, nullable=True),
        sa.Column("mass_kg_shipped", sa.Float, nullable=True),
        sa.Column("cost_eur_industrial", sa.Float, nullable=True),
        sa.Column("co2_kgco2e", sa.Float, nullable=True),
        sa.Column("is_fit_for_release", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("release_blockers", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("product_code", "revision", name="uq_snapshot_product_rev"),
    )
    op.create_index("ix_product_snapshots_state", "product_snapshots", ["state"])
    op.create_index("ix_product_snapshots_code", "product_snapshots", ["product_code"])

    # ── 3. product_assemblies ─────────────────────────────────────────────────
    op.create_table(
        "product_assemblies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assembly_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quantity", sa.Float, nullable=False, server_default="1"),
        sa.Column("cad_level", sa.String(30), nullable=False, server_default="G2_ENGINEERING"),
        sa.Column("assembly_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_passy_snapshot"),
        sa.ForeignKeyConstraint(["parent_id"], ["product_assemblies.id"],
                                ondelete="SET NULL", name="fk_passy_parent"),
    )
    op.create_index("ix_product_assemblies_snapshot", "product_assemblies", ["snapshot_id"])

    # ── 4. part_definitions ───────────────────────────────────────────────────
    op.create_table(
        "part_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assembly_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("part_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("material", sa.String(80), nullable=True),
        sa.Column("thickness_mm", sa.Float, nullable=True),
        sa.Column("geometry_params", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("cad_level", sa.String(30), nullable=False, server_default="G2_ENGINEERING"),
        sa.Column("is_purchased", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("quantity_per_assy", sa.Integer, nullable=False, server_default="1"),
        sa.Column("mass_kg", sa.Float, nullable=True),
        sa.Column("surface_area_m2", sa.Float, nullable=True),
        sa.Column("volume_cm3", sa.Float, nullable=True),
        sa.Column("part_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_partdef_snapshot"),
        sa.ForeignKeyConstraint(["assembly_id"], ["product_assemblies.id"],
                                ondelete="SET NULL", name="fk_partdef_assembly"),
    )
    op.create_index("ix_part_definitions_snapshot", "part_definitions", ["snapshot_id"])

    # ── 5. feature_definitions ────────────────────────────────────────────────
    op.create_table(
        "feature_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_id", sa.String(80), nullable=False),
        sa.Column("feature_type", sa.String(40), nullable=False),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("coordinate_system", postgresql.JSONB, nullable=True),
        sa.Column("dependencies", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("normative_source", sa.String(120), nullable=True),
        sa.Column("suppression_rule", sa.Text, nullable=True),
        sa.Column("is_critical", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("feature_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["part_id"], ["part_definitions.id"],
                                ondelete="CASCADE", name="fk_featdef_part"),
    )

    # ── 6. interface_definitions ──────────────────────────────────────────────
    op.create_table(
        "interface_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interface_code", sa.String(80), nullable=False),
        sa.Column("interface_type", sa.String(60), nullable=False),
        sa.Column("part_a_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("part_b_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("constraints", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("tolerance_group", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_iface_snapshot"),
    )

    # ── 7. cad_artifacts ──────────────────────────────────────────────────────
    op.create_table(
        "cad_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(30), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("cad_level", sa.String(30), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("generator_version", sa.String(40), nullable=True),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("units", sa.String(10), nullable=False, server_default="mm"),
        sa.Column("properties", postgresql.JSONB, nullable=True),
        sa.Column("validation_status", sa.String(20), nullable=True),
        sa.Column("validation_errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_cadart_snapshot"),
        sa.UniqueConstraint("idempotency_key", name="uq_cadart_idempotency"),
    )
    op.create_index("ix_cad_artifacts_snapshot_type", "cad_artifacts", ["snapshot_id","artifact_type"])

    # ── 8. drawing_artifacts ──────────────────────────────────────────────────
    op.create_table(
        "drawing_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("drawing_code", sa.String(80), nullable=False),
        sa.Column("drawing_type", sa.String(60), nullable=False),
        sa.Column("revision", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("format", sa.String(10), nullable=False, server_default="PDF"),
        sa.Column("language", sa.String(5), nullable=False, server_default="es"),
        sa.Column("views", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("validation_status", sa.String(20), nullable=True),
        sa.Column("validation_errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("is_fit_for_manufacture", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_drawart_snapshot"),
    )
    op.create_index("ix_drawing_artifacts_snapshot", "drawing_artifacts", ["snapshot_id"])

    # ── 9. bom_headers ────────────────────────────────────────────────────────
    op.create_table(
        "bom_headers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bom_view", sa.String(20), nullable=False),
        sa.Column("revision", sa.String(20), nullable=False, server_default="A"),
        sa.Column("state", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("bom_hash", sa.String(64), nullable=True),
        sa.Column("total_mass_kg", sa.Float, nullable=True),
        sa.Column("total_cost_eur", sa.Float, nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("mass_reconciliation_ok", sa.Boolean, nullable=True),
        sa.Column("mass_delta_pct", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_bomhdr_snapshot"),
    )
    op.create_index("ix_bom_headers_snapshot_view", "bom_headers", ["snapshot_id","bom_view"])

    # ── 10. bom_lines ─────────────────────────────────────────────────────────
    op.create_table(
        "bom_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("header_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("item_code", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("line_type", sa.String(30), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False, server_default="1"),
        sa.Column("quantity_unit", sa.String(20), nullable=False, server_default="EA"),
        sa.Column("quantity_rule", sa.String(40), nullable=True),
        sa.Column("scrap_factor", sa.Float, nullable=False, server_default="0"),
        sa.Column("min_lot", sa.Float, nullable=True),
        sa.Column("mass_kg_unit", sa.Float, nullable=True),
        sa.Column("cost_eur_unit", sa.Float, nullable=True),
        sa.Column("material", sa.String(80), nullable=True),
        sa.Column("is_critical", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["header_id"], ["bom_headers.id"],
                                ondelete="CASCADE", name="fk_bomline_header"),
        sa.ForeignKeyConstraint(["part_id"], ["part_definitions.id"],
                                ondelete="SET NULL", name="fk_bomline_part"),
    )
    op.create_index("ix_bom_lines_header", "bom_lines", ["header_id"])

    # ── 11. material_requirements ─────────────────────────────────────────────
    op.create_table(
        "material_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("material_code", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("norm", sa.String(120), nullable=True),
        sa.Column("grade", sa.String(40), nullable=True),
        sa.Column("surface_finish", sa.String(80), nullable=True),
        sa.Column("required_certs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_matreq_snapshot"),
    )

    # ── 12. routings ──────────────────────────────────────────────────────────
    op.create_table(
        "routings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("routing_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.String(20), nullable=False, server_default="A"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("plant", sa.String(60), nullable=True),
        sa.Column("routing_hash", sa.String(64), nullable=True),
        sa.Column("total_time_h", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_routing_snapshot"),
    )

    # ── 13. operations ────────────────────────────────────────────────────────
    op.create_table(
        "operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("routing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("operation_type", sa.String(40), nullable=False),
        sa.Column("work_center", sa.String(80), nullable=True),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("setup_time_h", sa.Float, nullable=False, server_default="0"),
        sa.Column("run_time_h", sa.Float, nullable=False, server_default="0"),
        sa.Column("is_stop_point", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_subcontracted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("supplier_code", sa.String(80), nullable=True),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["routing_id"], ["routings.id"],
                                ondelete="CASCADE", name="fk_operation_routing"),
    )
    op.create_index("ix_operations_routing_seq", "operations", ["routing_id","sequence_no"])

    # ── 14. work_instructions ─────────────────────────────────────────────────
    op.create_table(
        "work_instructions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("safety_notes", sa.Text, nullable=True),
        sa.Column("tools_required", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("reference_drawing", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"],
                                ondelete="CASCADE", name="fk_wi_operation"),
    )

    # ── 15. inspection_plans ──────────────────────────────────────────────────
    op.create_table(
        "inspection_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_code", sa.String(80), nullable=False),
        sa.Column("revision", sa.String(20), nullable=False, server_default="A"),
        sa.Column("state", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_insp_snapshot"),
    )

    # ── 16. inspection_characteristics ───────────────────────────────────────
    op.create_table(
        "inspection_characteristics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("characteristic_type", sa.String(40), nullable=False),
        sa.Column("method", sa.String(80), nullable=True),
        sa.Column("nominal", sa.Float, nullable=True),
        sa.Column("tolerance_plus", sa.Float, nullable=True),
        sa.Column("tolerance_minus", sa.Float, nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("frequency", sa.String(60), nullable=True),
        sa.Column("is_critical", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("ctq_level", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["plan_id"], ["inspection_plans.id"],
                                ondelete="CASCADE", name="fk_inspchar_plan"),
    )

    # ── 17. document_packages ─────────────────────────────────────────────────
    op.create_table(
        "document_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audience", sa.String(30), nullable=False),
        sa.Column("language", sa.String(5), nullable=False, server_default="es"),
        sa.Column("state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("package_hash", sa.String(64), nullable=True),
        sa.Column("expiry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_docpkg_snapshot"),
    )

    # ── 18. document_artifacts ────────────────────────────────────────────────
    op.create_table(
        "document_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(60), nullable=False),
        sa.Column("format", sa.String(10), nullable=False, server_default="PDF"),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["package_id"], ["document_packages.id"],
                                ondelete="CASCADE", name="fk_docart_package"),
    )

    # ── 19. release_records ───────────────────────────────────────────────────
    op.create_table(
        "release_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("release_code", sa.String(80), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("gates", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("blockers", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("release_hash", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_to_erp", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("erp_transaction_id", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="RESTRICT", name="fk_relrec_snapshot"),
        sa.UniqueConstraint("release_code", name="uq_release_code"),
    )

    # ── 20. change_requests ───────────────────────────────────────────────────
    op.create_table(
        "change_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("change_class", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("affected_fields", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("requires_recalc", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("requested_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_chgreq_snapshot"),
    )
    op.create_index("ix_change_requests_snapshot", "change_requests", ["snapshot_id"])

    # ── 21. change_orders ─────────────────────────────────────────────────────
    op.create_table(
        "change_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_code", sa.String(80), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["request_id"], ["change_requests.id"],
                                ondelete="CASCADE", name="fk_chgord_request"),
    )

    # ── 22. supplier_manufacturing_capabilities ────────────────────────────────
    op.create_table(
        "supplier_manufacturing_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("capabilities", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("materials", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("max_length_mm", sa.Float, nullable=True),
        sa.Column("max_diameter_mm", sa.Float, nullable=True),
        sa.Column("max_mass_kg", sa.Float, nullable=True),
        sa.Column("lead_time_days", sa.Integer, nullable=True),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("supplier_code", name="uq_supplier_code"),
    )

    # ── 23. asbuilt_measurements ──────────────────────────────────────────────
    op.create_table(
        "asbuilt_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("characteristic_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lot_number", sa.String(80), nullable=True),
        sa.Column("serial_number", sa.String(80), nullable=True),
        sa.Column("measured_value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("nominal", sa.Float, nullable=False),
        sa.Column("tolerance_plus", sa.Float, nullable=False),
        sa.Column("tolerance_minus", sa.Float, nullable=False),
        sa.Column("is_conformant", sa.Boolean, nullable=False),
        sa.Column("deviation", sa.Float, nullable=True),
        sa.Column("instrument", sa.String(80), nullable=True),
        sa.Column("measured_by", sa.String(120), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_abmeas_snapshot"),
    )
    op.create_index("ix_asbuilt_snapshot", "asbuilt_measurements", ["snapshot_id"])

    # ── 24. non_conformances ──────────────────────────────────────────────────
    op.create_table(
        "non_conformances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("nc_code", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disposition", sa.String(60), nullable=True),
        sa.Column("requires_requalification", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_nc_snapshot"),
    )

    # ── 25. validation_results ────────────────────────────────────────────────
    op.create_table(
        "validation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_code", sa.String(60), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_waived", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("waived_by", sa.String(120), nullable=True),
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_valres_snapshot"),
    )
    op.create_index("ix_validation_results_snapshot_sev", "validation_results",
                    ["snapshot_id", "severity"])

    # ── 26. artifact_manifests ────────────────────────────────────────────────
    op.create_table(
        "artifact_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("artifact_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_complete", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("entries", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("cad_level", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["product_snapshots.id"],
                                ondelete="CASCADE", name="fk_artman_snapshot"),
    )


def downgrade() -> None:
    tables = [
        "artifact_manifests","validation_results","non_conformances",
        "asbuilt_measurements","supplier_manufacturing_capabilities",
        "change_orders","change_requests","release_records",
        "document_artifacts","document_packages","inspection_characteristics",
        "inspection_plans","work_instructions","operations","routings",
        "material_requirements","bom_lines","bom_headers","drawing_artifacts",
        "cad_artifacts","interface_definitions","feature_definitions",
        "part_definitions","product_assemblies","product_snapshots",
    ]
    for t in tables:
        op.drop_table(t)
    for name, _ in reversed(_ENUMS):
        e = postgresql.ENUM(name=name)
        e.drop(op.get_bind(), checkfirst=True)
