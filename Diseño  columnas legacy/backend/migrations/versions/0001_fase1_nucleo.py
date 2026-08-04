"""Fase 1 — Núcleo: proyectos, revisiones, bibliotecas, usuarios, auditoría

Revision ID: 0001
Revises:
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE role_enum AS ENUM ('commercial','engineer','technical_office','library_admin','system_admin','auditor','service')")
    op.execute("CREATE TYPE maturity_enum AS ENUM ('M0','M1','M2','M3','M4')")
    op.execute("CREATE TYPE revision_maturity_enum AS ENUM ('M0','M1','M2','M3','M4')")
    op.execute("CREATE TYPE project_status_enum AS ENUM ('draft','in_preparation','in_review','observed','validated','released','archived','cancelled','blocked')")
    op.execute("CREATE TYPE confidentiality_enum AS ENUM ('internal','restricted','client')")
    op.execute("CREATE TYPE scenario_status_enum AS ENUM ('active','discarded','comparative','contractual')")
    op.execute("CREATE TYPE revision_type_enum AS ENUM ('draft','technical','client','production','as_built')")
    op.execute("CREATE TYPE alternative_origin_enum AS ENUM ('manual','catalog','optimization')")
    op.execute("CREATE TYPE job_status_enum AS ENUM ('queued','running','succeeded','failed','cancelled')")
    op.execute("CREATE TYPE library_type_enum AS ENUM ('norms','materials','standard_geometries','processes','suppliers','costs','co2_factors','units_formats','templates','corporate_equipment')")
    op.execute("CREATE TYPE library_version_status_enum AS ENUM ('draft','under_review','published','deprecated','withdrawn')")
    op.execute("CREATE TYPE material_family_enum AS ENUM ('steel','aluminum_extruded','aluminum_sheet','concrete','fasteners')")

    # ── Usuarios ─────────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False, unique=True),
        sa.Column('full_name', sa.String(180), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_sso', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('preferred_language', sa.String(5), nullable=False, server_default='es'),
        sa.Column('preferred_unit_system', sa.String(10), nullable=False, server_default='SI'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'user_roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', postgresql.ENUM(name='role_enum', create_type=False), nullable=False),
        sa.Column('granted_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # ── Proyectos ────────────────────────────────────────────────────────────
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_code', sa.String(64), nullable=False, unique=True),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('opportunity_ref', sa.String(120), nullable=True),
        sa.Column('country', sa.String(2), nullable=False),
        sa.Column('region', sa.String(80), nullable=True),
        sa.Column('timezone', sa.String(64), nullable=False, server_default='Europe/Madrid'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
        sa.Column('language', sa.String(5), nullable=False, server_default='es'),
        sa.Column('confidentiality', postgresql.ENUM(name='confidentiality_enum', create_type=False), nullable=False, server_default='internal'),
        sa.Column('status', postgresql.ENUM(name='project_status_enum', create_type=False), nullable=False, server_default='draft'),
        sa.Column('maturity', postgresql.ENUM(name='maturity_enum', create_type=False), nullable=False, server_default='M0'),
        sa.Column('owner_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cloned_from_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_projects_project_code', 'projects', ['project_code'], unique=True)
    op.create_index('ix_projects_customer_id', 'projects', ['customer_id'])

    op.create_table(
        'sites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('altitude_m', sa.Float(), nullable=True),
        sa.Column('geo_params', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'design_scenarios',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sites.id'), nullable=True),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM(name='scenario_status_enum', create_type=False), nullable=False, server_default='active'),
        sa.Column('is_base', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cloned_from_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('design_scenarios.id'), nullable=True),
        sa.Column('hypotheses', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'alternatives',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('scenario_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('design_scenarios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('origin', postgresql.ENUM(name='alternative_origin_enum', create_type=False), nullable=False, server_default='manual'),
        sa.Column('is_preferred', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('discard_reason', sa.Text(), nullable=True),
        sa.Column('selection_criteria', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'revisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revision_code', sa.String(16), nullable=False),
        sa.Column('revision_type', postgresql.ENUM(name='revision_type_enum', create_type=False), nullable=False, server_default='draft'),
        sa.Column('maturity', postgresql.ENUM(name='revision_maturity_enum', create_type=False), nullable=False, server_default='M0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('change_summary', sa.Text(), nullable=True),
        sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('frozen_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validated_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('validation_comment', sa.Text(), nullable=True),
        sa.Column('input_hash', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("frozen_at IS NOT NULL OR is_frozen = false", name='ck_revisions_frozen_consistency'),
    )

    op.create_table(
        'revision_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('revision_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('revisions.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('project_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('normative_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('library_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('geo_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('configuration_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('software_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('input_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('artifact_manifest', postgresql.JSONB(), nullable=False),
        sa.Column('canonical_hash', sa.String(64), nullable=False, unique=True),
    )

    op.create_table(
        'calculation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('revision_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('revisions.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('triggered_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', postgresql.ENUM(name='job_status_enum', create_type=False), nullable=False, server_default='queued'),
        sa.Column('engine_version', sa.String(32), nullable=True),
        sa.Column('input_hash', sa.String(64), nullable=True),
        sa.Column('result_hash', sa.String(64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
    )

    # ── Bibliotecas ──────────────────────────────────────────────────────────
    op.create_table(
        'libraries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(64), nullable=False, unique=True),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('library_type', postgresql.ENUM(name='library_type_enum', create_type=False), nullable=False),
        sa.Column('owner_role', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_libraries_code', 'libraries', ['code'], unique=True)

    op.create_table(
        'library_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('library_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('libraries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_number', sa.String(32), nullable=False),
        sa.Column('status', postgresql.ENUM(name='library_version_status_enum', create_type=False), nullable=False, server_default='draft'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('change_notes', sa.Text(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('superseded_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('library_versions.id'), nullable=True),
        sa.Column('content', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'materials',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('library_version_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('library_versions.id'), nullable=False),
        sa.Column('code', sa.String(64), nullable=False),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('material_family', postgresql.ENUM(name='material_family_enum', create_type=False), nullable=False),
        sa.Column('yield_strength_pa', sa.Float(), nullable=True),
        sa.Column('ultimate_strength_pa', sa.Float(), nullable=True),
        sa.Column('youngs_modulus_pa', sa.Float(), nullable=True),
        sa.Column('poisson_ratio', sa.Float(), nullable=True),
        sa.Column('density_kg_m3', sa.Float(), nullable=True),
        sa.Column('thermal_expansion_1_k', sa.Float(), nullable=True),
        sa.Column('min_thickness_m', sa.Float(), nullable=True),
        sa.Column('max_thickness_m', sa.Float(), nullable=True),
        sa.Column('weldable', sa.Boolean(), nullable=True),
        sa.Column('co2_factor_kg_per_kg', sa.Float(), nullable=True),
        sa.Column('co2_source', sa.String(255), nullable=True),
        sa.Column('corrosion_class', sa.String(16), nullable=True),
        sa.Column('extended_properties', postgresql.JSONB(), nullable=True),
        sa.Column('haz_properties', postgresql.JSONB(), nullable=True),
        sa.Column('applicable_standards', postgresql.JSONB(), nullable=True),
        sa.Column('compatible_finishes', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_materials_code', 'materials', ['code'])

    # ── Auditoría ────────────────────────────────────────────────────────────
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('actor_email', sa.String(254), nullable=True),
        sa.Column('actor_role', sa.String(64), nullable=True),
        sa.Column('entity_type', sa.String(64), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('action_result', sa.String(16), nullable=False, server_default='success'),
        sa.Column('before_state', postgresql.JSONB(), nullable=True),
        sa.Column('after_state', postgresql.JSONB(), nullable=True),
        sa.Column('diff', postgresql.JSONB(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('correlation_id', sa.String(64), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('app_version', sa.String(32), nullable=True),
    )
    op.create_index('ix_audit_logs_project_id', 'audit_logs', ['project_id'])
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_entity', 'audit_logs', ['entity_type', 'entity_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_correlation_id', 'audit_logs', ['correlation_id'])

    op.create_table(
        'async_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('job_type', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='queued'),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('triggered_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('correlation_id', sa.String(64), nullable=False, unique=True),
        sa.Column('arq_job_id', sa.String(128), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('error_code', sa.String(64), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
    )
    op.create_index('ix_async_jobs_correlation_id', 'async_jobs', ['correlation_id'], unique=True)

    op.create_table(
        'artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revision_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('revisions.id'), nullable=True),
        sa.Column('uploaded_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('artifact_type', sa.String(32), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('storage_key', sa.String(512), nullable=False),
        sa.Column('content_type', sa.String(128), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
    )

    op.create_table(
        'decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('decision_type', sa.String(64), nullable=False, server_default='technical'),
        sa.Column('made_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('alternatives_considered', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revision_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('revisions.id'), nullable=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('parent_comment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('comments.id'), nullable=True),
        sa.Column('field_anchor', sa.String(255), nullable=True),
        sa.Column('entity_type', sa.String(64), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Protección extra: auditoría no editable via política RLS (recomendada en producción)
    # ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;


def downgrade() -> None:
    op.drop_table('comments')
    op.drop_table('decisions')
    op.drop_table('artifacts')
    op.drop_table('async_jobs')
    op.drop_table('audit_logs')
    op.drop_table('materials')
    op.drop_table('library_versions')
    op.drop_table('libraries')
    op.drop_table('calculation_runs')
    op.drop_table('revision_snapshots')
    op.drop_table('revisions')
    op.drop_table('alternatives')
    op.drop_table('design_scenarios')
    op.drop_table('sites')
    op.drop_table('projects')
    op.drop_table('user_roles')
    op.drop_table('users')

    for enum in [
        'role_enum', 'maturity_enum', 'revision_maturity_enum', 'project_status_enum',
        'confidentiality_enum', 'scenario_status_enum', 'revision_type_enum',
        'alternative_origin_enum', 'job_status_enum', 'library_type_enum',
        'library_version_status_enum', 'material_family_enum',
    ]:
        op.execute(f'DROP TYPE IF EXISTS {enum}')
