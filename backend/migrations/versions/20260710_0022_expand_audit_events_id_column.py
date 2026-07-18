"""expand audit_events.id from VARCHAR(64) to VARCHAR(128) — rereview audit IDs exceed 64 chars

Revision ID: 20260710_0022
Revises: 20260710_0021
Create Date: 2026-07-10 14:35:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260710_0022'
down_revision = '20260710_0021'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('audit_events') as batch_op:
        batch_op.alter_column('id', type_=sa.String(length=128))


def downgrade():
    with op.batch_alter_table('audit_events') as batch_op:
        batch_op.alter_column('id', type_=sa.String(length=64))
