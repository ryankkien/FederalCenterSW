"""add primitive extraction tables and analysis runs

Revision ID: 20260425_0006
Revises: 20260426_0005
Create Date: 2026-04-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260425_0006"
down_revision: Union[str, None] = "20260426_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New columns on contracts for cohort matching
    op.add_column("contracts", sa.Column("contract_type", sa.String(length=40), nullable=True))
    op.add_column("contracts", sa.Column("competition_type", sa.String(length=40), nullable=True))

    op.create_table(
        "primitive_extraction_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("doc_upload_id", sa.String(length=36), nullable=True),
        sa.Column("period_label", sa.String(length=20), nullable=True),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="success", nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doc_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_primitive_extraction_runs_contract_id", "primitive_extraction_runs", ["contract_id"])
    op.create_index("ix_primitive_extraction_runs_doc_upload_id", "primitive_extraction_runs", ["doc_upload_id"])
    op.create_index("ix_primitive_extraction_runs_status", "primitive_extraction_runs", ["status"])

    op.create_table(
        "contract_primitives_deliverable",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("extraction_run_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("source_doc_ids", sa.JSON(), nullable=True),
        sa.Column("period_label", sa.String(length=20), nullable=True),
        sa.Column("deliverable_name", sa.Text(), nullable=True),
        sa.Column("cdrl_item", sa.String(length=40), nullable=True),
        sa.Column("planned_due_date", sa.Date(), nullable=True),
        sa.Column("actual_delivery_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("acceptance_status", sa.String(length=40), nullable=True),
        sa.Column("days_late", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["primitive_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cpd_contract_id", "contract_primitives_deliverable", ["contract_id"])
    op.create_index("ix_cpd_period_label", "contract_primitives_deliverable", ["period_label"])

    op.create_table(
        "contract_primitives_financial",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("extraction_run_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("source_doc_ids", sa.JSON(), nullable=True),
        sa.Column("period_label", sa.String(length=20), nullable=True),
        sa.Column("period_end_date", sa.Date(), nullable=True),
        sa.Column("planned_value", sa.Numeric(), nullable=True),
        sa.Column("earned_value", sa.Numeric(), nullable=True),
        sa.Column("actual_cost", sa.Numeric(), nullable=True),
        sa.Column("budget_at_completion", sa.Numeric(), nullable=True),
        sa.Column("estimate_at_completion", sa.Numeric(), nullable=True),
        sa.Column("estimate_to_complete", sa.Numeric(), nullable=True),
        sa.Column("cost_variance", sa.Numeric(), nullable=True),
        sa.Column("schedule_variance", sa.Numeric(), nullable=True),
        sa.Column("cpi", sa.Numeric(), nullable=True),
        sa.Column("spi", sa.Numeric(), nullable=True),
        sa.Column("percent_complete", sa.Numeric(), nullable=True),
        sa.Column("cumulative_obligations", sa.Numeric(), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["primitive_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cpf_contract_id", "contract_primitives_financial", ["contract_id"])
    op.create_index("ix_cpf_period_label", "contract_primitives_financial", ["period_label"])

    op.create_table(
        "contract_primitives_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("extraction_run_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("source_doc_ids", sa.JSON(), nullable=True),
        sa.Column("period_label", sa.String(length=20), nullable=True),
        sa.Column("decision_type", sa.String(length=40), nullable=True),
        sa.Column("mod_number", sa.String(length=40), nullable=True),
        sa.Column("mod_reason", sa.Text(), nullable=True),
        sa.Column("value_change", sa.Numeric(), nullable=True),
        sa.Column("pop_change_days", sa.Integer(), nullable=True),
        sa.Column("scope_change_description", sa.Text(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("deciding_party", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["primitive_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cpdec_contract_id", "contract_primitives_decisions", ["contract_id"])
    op.create_index("ix_cpdec_period_label", "contract_primitives_decisions", ["period_label"])

    op.create_table(
        "contract_primitives_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("extraction_run_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("source_doc_ids", sa.JSON(), nullable=True),
        sa.Column("period_label", sa.String(length=20), nullable=True),
        sa.Column("issue_id", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("responsible_party", sa.String(length=40), nullable=True),
        sa.Column("date_opened", sa.Date(), nullable=True),
        sa.Column("date_resolved", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("recurrence_flag", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["primitive_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cpi_contract_id", "contract_primitives_issues", ["contract_id"])
    op.create_index("ix_cpi_category", "contract_primitives_issues", ["category"])
    op.create_index("ix_cpi_period_label", "contract_primitives_issues", ["period_label"])

    op.create_table(
        "contract_primitives_personnel",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("extraction_run_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("source_doc_ids", sa.JSON(), nullable=True),
        sa.Column("period_label", sa.String(length=20), nullable=True),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("labor_category", sa.String(length=200), nullable=True),
        sa.Column("fte_planned", sa.Numeric(), nullable=True),
        sa.Column("fte_actual", sa.Numeric(), nullable=True),
        sa.Column("staffing_gap_flag", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["primitive_extraction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cpp_contract_id", "contract_primitives_personnel", ["contract_id"])
    op.create_index("ix_cpp_period_label", "contract_primitives_personnel", ["period_label"])

    op.create_table(
        "cpars_ratings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("doc_upload_id", sa.String(length=36), nullable=True),
        sa.Column("evaluation_period", sa.String(length=40), nullable=True),
        sa.Column("evaluation_date", sa.Date(), nullable=True),
        sa.Column("quality_rating", sa.String(length=40), nullable=True),
        sa.Column("schedule_rating", sa.String(length=40), nullable=True),
        sa.Column("cost_control_rating", sa.String(length=40), nullable=True),
        sa.Column("management_rating", sa.String(length=40), nullable=True),
        sa.Column("small_business_rating", sa.String(length=40), nullable=True),
        sa.Column("regulatory_compliance_rating", sa.String(length=40), nullable=True),
        sa.Column("overall_rating", sa.String(length=40), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doc_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cpars_ratings_contract_id", "cpars_ratings", ["contract_id"])
    op.create_index("ix_cpars_ratings_evaluation_period", "cpars_ratings", ["evaluation_period"])

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_type", sa.String(length=20), nullable=False),
        sa.Column("target_contract_id", sa.String(length=36), nullable=True),
        sa.Column("cohort_definition", sa.JSON(), nullable=True),
        sa.Column("cohort_contract_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["target_contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_run_type", "analysis_runs", ["run_type"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])
    op.create_index("ix_analysis_runs_target_contract_id", "analysis_runs", ["target_contract_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_target_contract_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_run_type", table_name="analysis_runs")
    op.drop_table("analysis_runs")

    op.drop_index("ix_cpars_ratings_evaluation_period", table_name="cpars_ratings")
    op.drop_index("ix_cpars_ratings_contract_id", table_name="cpars_ratings")
    op.drop_table("cpars_ratings")

    op.drop_index("ix_cpp_period_label", table_name="contract_primitives_personnel")
    op.drop_index("ix_cpp_contract_id", table_name="contract_primitives_personnel")
    op.drop_table("contract_primitives_personnel")

    op.drop_index("ix_cpi_period_label", table_name="contract_primitives_issues")
    op.drop_index("ix_cpi_category", table_name="contract_primitives_issues")
    op.drop_index("ix_cpi_contract_id", table_name="contract_primitives_issues")
    op.drop_table("contract_primitives_issues")

    op.drop_index("ix_cpdec_period_label", table_name="contract_primitives_decisions")
    op.drop_index("ix_cpdec_contract_id", table_name="contract_primitives_decisions")
    op.drop_table("contract_primitives_decisions")

    op.drop_index("ix_cpf_period_label", table_name="contract_primitives_financial")
    op.drop_index("ix_cpf_contract_id", table_name="contract_primitives_financial")
    op.drop_table("contract_primitives_financial")

    op.drop_index("ix_cpd_period_label", table_name="contract_primitives_deliverable")
    op.drop_index("ix_cpd_contract_id", table_name="contract_primitives_deliverable")
    op.drop_table("contract_primitives_deliverable")

    op.drop_index("ix_primitive_extraction_runs_status", table_name="primitive_extraction_runs")
    op.drop_index("ix_primitive_extraction_runs_doc_upload_id", table_name="primitive_extraction_runs")
    op.drop_index("ix_primitive_extraction_runs_contract_id", table_name="primitive_extraction_runs")
    op.drop_table("primitive_extraction_runs")

    op.drop_column("contracts", "competition_type")
    op.drop_column("contracts", "contract_type")
