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
    op.execute('ALTER TABLE audit_events ALTER COLUMN detail TYPE VARCHAR(500)')


def downgrade():
    op.execute('ALTER TABLE audit_events ALTER COLUMN detail TYPE VARCHAR(64)')
