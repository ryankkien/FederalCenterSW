"""add analyzed_doc_ids to analysis_runs

Revision ID: 20260426_0007
Revises: 20260425_0006
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_0007"
down_revision: Union[str, None] = "20260425_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("analyzed_doc_ids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_runs", "analyzed_doc_ids")
