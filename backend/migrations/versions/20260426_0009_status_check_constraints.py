"""add CHECK constraints for status enum columns

Revision ID: 20260426_0009
Revises: 20260426_0008
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_0009"
down_revision: Union[str, None] = "20260426_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONSTRAINTS = (
    (
        "contract_hypotheses",
        "ck_contract_hypotheses_status",
        "status IN ('proposed','investigating','supported','contradicted','closed')",
    ),
    (
        "hypothesis_evidence",
        "ck_hypothesis_evidence_evidence_type",
        "evidence_type IN ('supporting','contradicting')",
    ),
    (
        "analysis_runs",
        "ck_analysis_runs_status",
        "status IN ('pending','queued','running','complete','failed')",
    ),
    (
        "primitive_extraction_runs",
        "ck_primitive_extraction_runs_status",
        "status IN ('pending','success','partial','failed','no_rows')",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    for table, name, expression in _CONSTRAINTS:
        if is_postgres:
            # NOT VALID lets prod skip a full table scan; existing offenders
            # surface in pg_constraint and can be cleaned up before VALIDATE.
            op.execute(
                sa.text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID"
                )
            )
        else:
            op.create_check_constraint(name, table, expression)


def downgrade() -> None:
    for table, name, _ in _CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
