"""create l3_config table

Revision ID: 20260625_0009
Revises: 20260625_0008
Create Date: 2026-06-25

"""
from alembic import op
import sqlalchemy as sa

revision = '20260625_0009'
down_revision = '20260625_0008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'l3_config',
        sa.Column('id', sa.Integer(), nullable=False, default=1),
        sa.Column('params_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_by', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute("INSERT INTO l3_config (id, params_json) VALUES (1, '{}')")


def downgrade():
    op.drop_table('l3_config')
