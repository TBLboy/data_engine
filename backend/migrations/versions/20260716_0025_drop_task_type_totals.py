"""drop cached task type total counters

Revision ID: 20260716_0025
Revises: 20260716_0024
Create Date: 2026-07-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260716_0025'
down_revision = '20260716_0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('task_types', 'total_episodes')
    op.drop_column('task_types', 'total_batches')


def downgrade() -> None:
    op.add_column(
        'task_types',
        sa.Column('total_batches', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'task_types',
        sa.Column('total_episodes', sa.Integer(), nullable=False, server_default='0'),
    )
    with op.batch_alter_table('task_types') as batch_op:
        batch_op.alter_column('total_batches', server_default=None)
        batch_op.alter_column('total_episodes', server_default=None)
