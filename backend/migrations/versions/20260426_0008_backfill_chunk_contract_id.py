"""backfill document_chunks.contract_id from document_uploads

Revision ID: 20260426_0008
Revises: 20260426_0007
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260426_0008"
down_revision: Union[str, None] = "20260426_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE document_chunks AS dc
        SET contract_id = du.contract_id
        FROM document_uploads AS du
        WHERE dc.document_upload_id = du.id
          AND dc.contract_id IS NULL
          AND du.contract_id IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
