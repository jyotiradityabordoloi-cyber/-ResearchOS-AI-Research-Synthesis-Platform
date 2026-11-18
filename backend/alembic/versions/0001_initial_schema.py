"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-18 02:14:35.062482
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('research_projects',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('objectives', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('target_segments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('synthesis_status', sa.String(length=32), nullable=False),
    sa.Column('active_run_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_research_projects_owner_id'), 'research_projects', ['owner_id'], unique=False)
    op.create_index('ix_research_projects_status', 'research_projects', ['status'], unique=False)
    op.create_table('human_reviews',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('entity_type', sa.String(length=32), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(length=48), nullable=False),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['research_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_human_reviews_entity', 'human_reviews', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_human_reviews_project_created', 'human_reviews', ['project_id', 'created_at'], unique=False)
    op.create_table('interviews',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('participant_id', sa.String(length=100), nullable=False),
    sa.Column('participant_role', sa.String(length=200), nullable=False),
    sa.Column('company_size', sa.String(length=100), nullable=False),
    sa.Column('plan_tier', sa.String(length=100), nullable=False),
    sa.Column('pain', sa.Text(), nullable=False),
    sa.Column('behavior', sa.Text(), nullable=False),
    sa.Column('verbatim_quote', sa.Text(), nullable=False),
    sa.Column('raw_content', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('source_filename', sa.String(length=300), nullable=True),
    sa.Column('validation_status', sa.String(length=16), nullable=False),
    sa.Column('validation_errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['research_projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_interviews_project_id', 'interviews', ['project_id'], unique=False)
    op.create_index('ix_interviews_project_participant', 'interviews', ['project_id', 'participant_id'], unique=False)
    op.create_index('ix_interviews_validation_status', 'interviews', ['validation_status'], unique=False)
    op.create_table('synthesis_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('stage', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('embedding_provider', sa.String(length=32), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('triggered_by_id', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['research_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['triggered_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_synthesis_runs_project_id'), 'synthesis_runs', ['project_id'], unique=False)
    op.create_table('pain_points',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('interview_id', sa.Uuid(), nullable=False),
    sa.Column('participant_id', sa.String(length=100), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('quote', sa.Text(), nullable=True),
    sa.Column('quote_verified', sa.Boolean(), nullable=False),
    sa.Column('severity', sa.Integer(), nullable=True),
    sa.Column('sensitive_tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['research_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['synthesis_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pain_points_embedding_hnsw', 'pain_points', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_pain_points_interview_id', 'pain_points', ['interview_id'], unique=False)
    op.create_index('ix_pain_points_project_run', 'pain_points', ['project_id', 'run_id'], unique=False)
    op.create_table('research_reports',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('content_markdown', sa.Text(), nullable=False),
    sa.Column('content_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('excluded_sensitive_count', sa.Integer(), nullable=False),
    sa.Column('generated_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['generated_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['research_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['synthesis_runs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_research_reports_project_id'), 'research_reports', ['project_id'], unique=False)
    op.create_table('themes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=True),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('implication', sa.Text(), nullable=False),
    sa.Column('participant_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('participant_count', sa.Integer(), nullable=False),
    sa.Column('total_participants', sa.Integer(), nullable=False),
    sa.Column('frequency', sa.Float(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('evidence_status', sa.String(length=16), nullable=False),
    sa.Column('is_outlier', sa.Boolean(), nullable=False),
    sa.Column('is_low_confidence', sa.Boolean(), nullable=False),
    sa.Column('has_contradictions', sa.Boolean(), nullable=False),
    sa.Column('sensitive_tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('requires_approval', sa.Boolean(), nullable=False),
    sa.Column('strategic_flag', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('human_edited', sa.Boolean(), nullable=False),
    sa.Column('merged_into_id', sa.Uuid(), nullable=True),
    sa.Column('split_from_id', sa.Uuid(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['merged_into_id'], ['themes.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['research_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['synthesis_runs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['split_from_id'], ['themes.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_themes_embedding_hnsw', 'themes', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_themes_project_run', 'themes', ['project_id', 'run_id'], unique=False)
    op.create_index('ix_themes_status', 'themes', ['status'], unique=False)
    op.create_table('insights',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=True),
    sa.Column('theme_id', sa.Uuid(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('implication', sa.Text(), nullable=False),
    sa.Column('frequency', sa.Float(), nullable=False),
    sa.Column('severity', sa.Integer(), nullable=False),
    sa.Column('strategic_relevance', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('priority_score', sa.Float(), nullable=False),
    sa.Column('priority_override', sa.String(length=16), nullable=True),
    sa.Column('override_reason', sa.Text(), nullable=True),
    sa.Column('pm_comment', sa.Text(), nullable=True),
    sa.Column('is_outlier', sa.Boolean(), nullable=False),
    sa.Column('sensitive_tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('requires_approval', sa.Boolean(), nullable=False),
    sa.Column('strategic_flag', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['research_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['synthesis_runs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_insights_embedding_hnsw', 'insights', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_insights_project_run', 'insights', ['project_id', 'run_id'], unique=False)
    op.create_index('ix_insights_status', 'insights', ['status'], unique=False)
    op.create_index('ix_insights_theme_id', 'insights', ['theme_id'], unique=False)
    op.create_table('theme_evidence',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('theme_id', sa.Uuid(), nullable=False),
    sa.Column('interview_id', sa.Uuid(), nullable=False),
    sa.Column('pain_point_id', sa.Uuid(), nullable=True),
    sa.Column('participant_id', sa.String(length=100), nullable=False),
    sa.Column('quote', sa.Text(), nullable=False),
    sa.Column('quote_verified', sa.Boolean(), nullable=False),
    sa.Column('stance', sa.String(length=16), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['pain_point_id'], ['pain_points.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_theme_evidence_interview_id', 'theme_evidence', ['interview_id'], unique=False)
    op.create_index('ix_theme_evidence_theme_id', 'theme_evidence', ['theme_id'], unique=False)
    # research_projects <-> synthesis_runs is circular; add this FK last.
    op.create_foreign_key('fk_research_projects_active_run_id', 'research_projects', 'synthesis_runs',
                          ['active_run_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_research_projects_active_run_id', 'research_projects', type_='foreignkey')
    op.drop_index('ix_theme_evidence_theme_id', table_name='theme_evidence')
    op.drop_index('ix_theme_evidence_interview_id', table_name='theme_evidence')
    op.drop_table('theme_evidence')
    op.drop_index('ix_insights_theme_id', table_name='insights')
    op.drop_index('ix_insights_status', table_name='insights')
    op.drop_index('ix_insights_project_run', table_name='insights')
    op.drop_index('ix_insights_embedding_hnsw', table_name='insights', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('insights')
    op.drop_index('ix_themes_status', table_name='themes')
    op.drop_index('ix_themes_project_run', table_name='themes')
    op.drop_index('ix_themes_embedding_hnsw', table_name='themes', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('themes')
    op.drop_index(op.f('ix_research_reports_project_id'), table_name='research_reports')
    op.drop_table('research_reports')
    op.drop_index('ix_pain_points_project_run', table_name='pain_points')
    op.drop_index('ix_pain_points_interview_id', table_name='pain_points')
    op.drop_index('ix_pain_points_embedding_hnsw', table_name='pain_points', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('pain_points')
    op.drop_index(op.f('ix_synthesis_runs_project_id'), table_name='synthesis_runs')
    op.drop_table('synthesis_runs')
    op.drop_index('ix_interviews_validation_status', table_name='interviews')
    op.drop_index('ix_interviews_project_participant', table_name='interviews')
    op.drop_index('ix_interviews_project_id', table_name='interviews')
    op.drop_table('interviews')
    op.drop_index('ix_human_reviews_project_created', table_name='human_reviews')
    op.drop_index('ix_human_reviews_entity', table_name='human_reviews')
    op.drop_table('human_reviews')
    op.drop_index('ix_research_projects_status', table_name='research_projects')
    op.drop_index(op.f('ix_research_projects_owner_id'), table_name='research_projects')
    op.drop_table('research_projects')
    op.drop_table('users')
