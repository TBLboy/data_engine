"""expand audit_events.detail from VARCHAR(64) to VARCHAR(500) — matches model definition

Revision ID: 20260710_0020
Revises: 20260710_0019
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260710_0020'
down_revision = '20260710_0019'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE audit_events ALTER COLUMN detail TYPE VARCHAR(500)')


def downgrade():
    op.execute('ALTER TABLE audit_events ALTER COLUMN detail TYPE VARCHAR(64)')
