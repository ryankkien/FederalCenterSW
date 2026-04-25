"""create document uploads

Revision ID: 20260425_0001
Revises:
Create Date: 2026-04-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260425_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_uploads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("blob_path", sa.String(length=700), nullable=False),
        sa.Column("uploader_id", sa.String(length=120), nullable=False),
        sa.Column("uploader_role", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_uploads_uploader_id", "document_uploads", ["uploader_id"])


def downgrade() -> None:
    op.drop_index("ix_document_uploads_uploader_id", table_name="document_uploads")
    op.drop_table("document_uploads")
