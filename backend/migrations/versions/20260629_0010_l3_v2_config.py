"""l3_v2_config

Revision ID: 20260629_0010
Revises: 20260625_0009
Create Date: 2026-06-29 01:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260629_0010'
down_revision = '20260625_0009'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'l3_v2_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('params_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('updated_by', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('l3_v2_config')
