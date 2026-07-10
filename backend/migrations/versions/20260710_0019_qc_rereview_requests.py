"""add qc rereview requests

Revision ID: 20260710_0019
Revises: 20260708_0018
Create Date: 2026-07-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0019"
down_revision: Union[str, None] = "20260708_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'qc_rereview_requests',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('episode_id', sa.String(256), sa.ForeignKey('episodes.id'), nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('batch_id', sa.String(64), nullable=False),
        sa.Column('requester_user_id', sa.String(64), nullable=False),
        sa.Column('requester_name', sa.String(64), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('approver_user_id', sa.String(64), nullable=True),
        sa.Column('approver_name', sa.String(64), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('decided_at', sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index('ix_qc_rereview_requests_episode_id', 'qc_rereview_requests', ['episode_id'])
    op.create_index('ix_qc_rereview_requests_task_id', 'qc_rereview_requests', ['task_id'])
    op.create_index('ix_qc_rereview_requests_batch_id', 'qc_rereview_requests', ['batch_id'])
    op.create_index('ix_qc_rereview_requests_requester_user_id', 'qc_rereview_requests', ['requester_user_id'])
    op.create_index('ix_qc_rereview_requests_status', 'qc_rereview_requests', ['status'])


def downgrade() -> None:
    op.drop_index('ix_qc_rereview_requests_status', table_name='qc_rereview_requests')
    op.drop_index('ix_qc_rereview_requests_requester_user_id', table_name='qc_rereview_requests')
    op.drop_index('ix_qc_rereview_requests_batch_id', table_name='qc_rereview_requests')
    op.drop_index('ix_qc_rereview_requests_task_id', table_name='qc_rereview_requests')
    op.drop_index('ix_qc_rereview_requests_episode_id', table_name='qc_rereview_requests')
    op.drop_table('qc_rereview_requests')
