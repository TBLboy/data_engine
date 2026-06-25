"""fix contradictory episode qc state (assigned+fail black hole)

Revision ID: 20260625_0007
Revises: 20260625_0006
Create Date: 2026-06-25

Repairs episodes left in a contradictory state by the old dispatch-plan bug:
qc_status was reset to new/assigned/in_review on re-dispatch while a stale
qc_result (fail/pass) lingered, so the task vanished from every reviewer count.
Reset qc_result to 'pending' and reason_code to '-' for any episode whose
qc_status is not 'done' but still carries a non-pending result.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '20260625_0007'
down_revision: Union[str, None] = '20260625_0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE episodes
        SET qc_result = 'pending', reason_code = '-'
        WHERE qc_status <> 'done'
          AND qc_result NOT IN ('pending', '')
        """
    )


def downgrade() -> None:
    # Data repair is not reversible.
    pass
