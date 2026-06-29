"""session_token for concurrent login protection

Revision ID: 20260629_0014
Revises: 20260629_0013
Create Date: 2026-06-29 05:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260629_0014'
down_revision = '20260629_0013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('session_token', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('users', 'session_token')
