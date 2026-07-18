"""expand audit_events.detail column from VARCHAR(64) to VARCHAR(500)

Revision ID: 20260710_0021
Revises: 20260710_0020
Create Date: 2026-07-10 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260710_0021'
down_revision = '20260710_0020'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('audit_events') as batch_op:
        batch_op.alter_column('detail', type_=sa.String(length=500))


def downgrade():
    with op.batch_alter_table('audit_events') as batch_op:
        batch_op.alter_column('detail', type_=sa.String(length=64))
