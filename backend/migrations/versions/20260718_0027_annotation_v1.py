"""annotation v1 core schema and task persistence

Revision ID: 20260718_0027
Revises: 20260717_0026
Create Date: 2026-07-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260718_0027'
down_revision = '20260717_0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sub_goal_schemas',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('task_type_id', sa.String(length=64), nullable=False),
        sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='draft'),
        sa.Column('schema_payload', sa.JSON(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('published_by', sa.String(length=64), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('retired_by', sa.String(length=64), nullable=True),
        sa.Column('retired_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('retirement_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_type_id', 'version_no', name='uq_sub_goal_schemas_task_type_version'),
    )
    op.create_index(op.f('ix_sub_goal_schemas_task_type_id'), 'sub_goal_schemas', ['task_type_id'], unique=False)
    op.create_index(op.f('ix_sub_goal_schemas_status'), 'sub_goal_schemas', ['status'], unique=False)
    op.create_index(
        'ix_sub_goal_schemas_task_type_status',
        'sub_goal_schemas',
        ['task_type_id', 'status'],
        unique=False,
    )
    op.create_index(
        'uq_sub_goal_schemas_one_published',
        'sub_goal_schemas',
        ['task_type_id'],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
        sqlite_where=sa.text("status = 'published'"),
    )

    with op.batch_alter_table('task_types') as batch_op:
        batch_op.add_column(sa.Column('default_published_sub_goal_schema_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            'fk_task_types_default_published_sub_goal_schema',
            'sub_goal_schemas',
            ['default_published_sub_goal_schema_id'],
            ['id'],
        )

    op.create_table(
        'sub_goal_definitions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('sub_goal_schema_id', sa.String(length=64), nullable=False),
        sa.Column('sequence_no', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=128), nullable=False),
        sa.Column('name_en', sa.String(length=255), nullable=False),
        sa.Column('name_zh', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('action_verb', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_conditional', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('max_occurrences', sa.Integer(), nullable=True),
        sa.Column('object_role_hints', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['sub_goal_schema_id'], ['sub_goal_schemas.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sub_goal_schema_id', 'code', name='uq_sub_goal_definitions_schema_code'),
        sa.UniqueConstraint('sub_goal_schema_id', 'sequence_no', name='uq_sub_goal_definitions_schema_sequence'),
    )
    op.create_index('ix_sub_goal_definitions_schema_id', 'sub_goal_definitions', ['sub_goal_schema_id'], unique=False)

    op.create_table(
        'annotation_tasks',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('episode_id', sa.String(length=64), nullable=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('task_type_id', sa.String(length=64), nullable=False),
        sa.Column('sub_goal_schema_id', sa.String(length=64), nullable=False),
        sa.Column('sub_goal_schema_version', sa.Integer(), nullable=False),
        sa.Column('sub_goal_schema_content_hash', sa.String(length=64), nullable=False),
        sa.Column('work_status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('status_before_invalidation', sa.String(length=16), nullable=True),
        sa.Column('invalidated_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('invalidation_reason', sa.Text(), nullable=True),
        sa.Column('assigned_to', sa.String(length=64), nullable=True),
        sa.Column('assigned_by', sa.String(length=64), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('assignment_note', sa.Text(), nullable=False, server_default=''),
        sa.Column('public_claim_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('public_claim_enabled_by', sa.String(length=64), nullable=True),
        sa.Column('public_claim_enabled_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('lock_owner', sa.String(length=64), nullable=True),
        sa.Column('lock_acquired_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('lock_expires_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('completed_by', sa.String(length=64), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('current_revision_no', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('initial_source', sa.String(length=16), nullable=False, server_default='manual'),
        sa.Column('manual_from_scratch_reason', sa.String(length=64), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['episode_id'], ['episodes.id']),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id']),
        sa.ForeignKeyConstraint(['sub_goal_schema_id'], ['sub_goal_schemas.id']),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id']),
        sa.ForeignKeyConstraint(['lock_owner'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('episode_id', name='uq_annotation_tasks_episode_id'),
    )
    op.create_index(op.f('ix_annotation_tasks_batch_id'), 'annotation_tasks', ['batch_id'], unique=False)
    op.create_index(op.f('ix_annotation_tasks_task_type_id'), 'annotation_tasks', ['task_type_id'], unique=False)
    op.create_index(op.f('ix_annotation_tasks_work_status'), 'annotation_tasks', ['work_status'], unique=False)
    op.create_index(op.f('ix_annotation_tasks_assigned_to'), 'annotation_tasks', ['assigned_to'], unique=False)
    op.create_index('ix_annotation_tasks_assignment', 'annotation_tasks', ['work_status', 'assigned_to'], unique=False)

    op.create_table(
        'episode_annotations',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('annotation_task_id', sa.String(length=64), nullable=False),
        sa.Column('canonical_instruction_en', sa.Text(), nullable=False, server_default=''),
        sa.Column('canonical_instruction_zh', sa.Text(), nullable=True),
        sa.Column('instruction_variants_en', sa.JSON(), nullable=False),
        sa.Column('episode_summary', sa.Text(), nullable=True),
        sa.Column('objects', sa.JSON(), nullable=False),
        sa.Column('task_outcome', sa.String(length=32), nullable=True),
        sa.Column('failure_sub_goal_instance_id', sa.Integer(), nullable=True),
        sa.Column('last_successful_sub_goal_instance_id', sa.Integer(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('annotation_notes', sa.Text(), nullable=True),
        sa.Column('human_modified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('annotation_schema_version', sa.String(length=16), nullable=False, server_default='1.0'),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['annotation_task_id'], ['annotation_tasks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('annotation_task_id', name='uq_episode_annotations_task_id'),
    )

    op.create_table(
        'episode_sub_goal_instances',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('episode_annotation_id', sa.String(length=64), nullable=False),
        sa.Column('sub_goal_definition_id', sa.String(length=64), nullable=False),
        sa.Column('occurrence_no', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='observed'),
        sa.Column('start_step', sa.Integer(), nullable=True),
        sa.Column('end_step_exclusive', sa.Integer(), nullable=True),
        sa.Column('representative_step', sa.Integer(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=24), nullable=False, server_default='human'),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['episode_annotation_id'], ['episode_annotations.id']),
        sa.ForeignKeyConstraint(['sub_goal_definition_id'], ['sub_goal_definitions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'episode_annotation_id', 'sub_goal_definition_id', 'occurrence_no',
            name='uq_episode_sub_goal_instances_occurrence',
        ),
    )
    op.create_index(
        'ix_episode_sub_goal_instances_annotation_id',
        'episode_sub_goal_instances',
        ['episode_annotation_id'],
        unique=False,
    )

    op.create_table(
        'annotation_revisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('annotation_task_id', sa.String(length=64), nullable=False),
        sa.Column('episode_annotation_id', sa.String(length=64), nullable=False),
        sa.Column('revision_no', sa.Integer(), nullable=False),
        sa.Column('annotation_payload', sa.JSON(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['annotation_task_id'], ['annotation_tasks.id']),
        sa.ForeignKeyConstraint(['episode_annotation_id'], ['episode_annotations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('annotation_task_id', 'revision_no', name='uq_annotation_revisions_task_revision'),
    )
    op.create_index(
        'ix_annotation_revisions_episode_annotation_id',
        'annotation_revisions',
        ['episode_annotation_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_annotation_revisions_episode_annotation_id', table_name='annotation_revisions')
    op.drop_table('annotation_revisions')
    op.drop_index('ix_episode_sub_goal_instances_annotation_id', table_name='episode_sub_goal_instances')
    op.drop_table('episode_sub_goal_instances')
    op.drop_table('episode_annotations')
    op.drop_index('ix_annotation_tasks_assignment', table_name='annotation_tasks')
    op.drop_index(op.f('ix_annotation_tasks_assigned_to'), table_name='annotation_tasks')
    op.drop_index(op.f('ix_annotation_tasks_work_status'), table_name='annotation_tasks')
    op.drop_index(op.f('ix_annotation_tasks_task_type_id'), table_name='annotation_tasks')
    op.drop_index(op.f('ix_annotation_tasks_batch_id'), table_name='annotation_tasks')
    op.drop_table('annotation_tasks')
    op.drop_index('ix_sub_goal_definitions_schema_id', table_name='sub_goal_definitions')
    op.drop_table('sub_goal_definitions')
    with op.batch_alter_table('task_types') as batch_op:
        batch_op.drop_constraint('fk_task_types_default_published_sub_goal_schema', type_='foreignkey')
        batch_op.drop_column('default_published_sub_goal_schema_id')
    op.drop_index('uq_sub_goal_schemas_one_published', table_name='sub_goal_schemas')
    op.drop_index('ix_sub_goal_schemas_task_type_status', table_name='sub_goal_schemas')
    op.drop_index(op.f('ix_sub_goal_schemas_status'), table_name='sub_goal_schemas')
    op.drop_index(op.f('ix_sub_goal_schemas_task_type_id'), table_name='sub_goal_schemas')
    op.drop_table('sub_goal_schemas')
