"""general_config

Revision ID: 20260629_0011
Revises: 20260629_0010
Create Date: 2026-06-29 02:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260629_0011'
down_revision = '20260629_0010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'general_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('params_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('updated_by', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('general_config')
