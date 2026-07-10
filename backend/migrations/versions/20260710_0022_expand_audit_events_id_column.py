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
    op.execute('ALTER TABLE audit_events ALTER COLUMN id TYPE VARCHAR(128)')


def downgrade():
    op.execute('ALTER TABLE audit_events ALTER COLUMN id TYPE VARCHAR(64)')
