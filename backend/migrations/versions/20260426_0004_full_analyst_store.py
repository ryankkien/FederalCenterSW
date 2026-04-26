"""add full analyst intermediate store

Revision ID: 20260426_0004
Revises: 20260426_0003
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_0004"
down_revision: Union[str, None] = "20260426_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _created_at_column() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("run_type", sa.String(length=80), server_default="document_analysis", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="running", nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("raw_model_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["document_processing_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_runs_contract_id", "processing_runs", ["contract_id"])
    op.create_index("ix_processing_runs_document_upload_id", "processing_runs", ["document_upload_id"])
    op.create_index("ix_processing_runs_job_id", "processing_runs", ["job_id"])
    op.create_index("ix_processing_runs_status", "processing_runs", ["status"])

    op.create_table(
        "processing_run_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("processing_run_id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_run_steps_document_upload_id", "processing_run_steps", ["document_upload_id"])
    op.create_index("ix_processing_run_steps_processing_run_id", "processing_run_steps", ["processing_run_id"])
    op.create_index("ix_processing_run_steps_status", "processing_run_steps", ["status"])
    op.create_index("ix_processing_run_steps_step_name", "processing_run_steps", ["step_name"])

    op.create_table(
        "document_pages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("processing_run_id", sa.String(length=36), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extraction_status", sa.String(length=40), server_default="extracted", nullable=False),
        sa.Column("source_start_offset", sa.Integer(), nullable=True),
        sa.Column("source_end_offset", sa.Integer(), nullable=True),
        sa.Column("extraction_warning", sa.Text(), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_upload_id", "page_number", name="uq_document_page_number"),
    )
    op.create_index("ix_document_pages_document_upload_id", "document_pages", ["document_upload_id"])
    op.create_index("ix_document_pages_extraction_status", "document_pages", ["extraction_status"])
    op.create_index("ix_document_pages_processing_run_id", "document_pages", ["processing_run_id"])

    op.create_table(
        "document_classification_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("processing_run_id", sa.String(length=36), nullable=True),
        sa.Column("document_kind", sa.String(length=80), nullable=False),
        sa.Column("modification_kind", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("classifier_name", sa.String(length=120), server_default="deterministic_v1", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_classification_decisions_document_kind", "document_classification_decisions", ["document_kind"])
    op.create_index("ix_document_classification_decisions_document_upload_id", "document_classification_decisions", ["document_upload_id"])
    op.create_index("ix_document_classification_decisions_modification_kind", "document_classification_decisions", ["modification_kind"])
    op.create_index("ix_document_classification_decisions_processing_run_id", "document_classification_decisions", ["processing_run_id"])

    op.create_table(
        "document_entities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("page_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("processing_run_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.String(length=500), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["document_pages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_entities_chunk_id", "document_entities", ["chunk_id"])
    op.create_index("ix_document_entities_contract_id", "document_entities", ["contract_id"])
    op.create_index("ix_document_entities_document_upload_id", "document_entities", ["document_upload_id"])
    op.create_index("ix_document_entities_entity_type", "document_entities", ["entity_type"])
    op.create_index("ix_document_entities_evidence_hash", "document_entities", ["evidence_hash"])
    op.create_index("ix_document_entities_normalized_value", "document_entities", ["normalized_value"])
    op.create_index("ix_document_entities_page_id", "document_entities", ["page_id"])
    op.create_index("ix_document_entities_processing_run_id", "document_entities", ["processing_run_id"])

    op.create_table(
        "document_report_facts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("page_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("processing_run_id", sa.String(length=36), nullable=True),
        sa.Column("fact_type", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=180), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["document_pages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["processing_run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_report_facts_chunk_id", "document_report_facts", ["chunk_id"])
    op.create_index("ix_document_report_facts_contract_id", "document_report_facts", ["contract_id"])
    op.create_index("ix_document_report_facts_document_upload_id", "document_report_facts", ["document_upload_id"])
    op.create_index("ix_document_report_facts_evidence_hash", "document_report_facts", ["evidence_hash"])
    op.create_index("ix_document_report_facts_fact_type", "document_report_facts", ["fact_type"])
    op.create_index("ix_document_report_facts_page_id", "document_report_facts", ["page_id"])
    op.create_index("ix_document_report_facts_processing_run_id", "document_report_facts", ["processing_run_id"])

    with op.batch_alter_table("baseline_obligations") as batch_op:
        batch_op.add_column(sa.Column("page_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("processing_run_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("evidence_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_baseline_obligations_page_id", "baseline_obligations", ["page_id"])
    op.create_index("ix_baseline_obligations_processing_run_id", "baseline_obligations", ["processing_run_id"])
    op.create_index("ix_baseline_obligations_evidence_hash", "baseline_obligations", ["evidence_hash"])

    with op.batch_alter_table("baseline_revisions") as batch_op:
        batch_op.add_column(sa.Column("processing_run_id", sa.String(length=36), nullable=True))
    op.create_index("ix_baseline_revisions_processing_run_id", "baseline_revisions", ["processing_run_id"])

    with op.batch_alter_table("regression_findings") as batch_op:
        batch_op.add_column(sa.Column("page_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("processing_run_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("evidence_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_regression_findings_page_id", "regression_findings", ["page_id"])
    op.create_index("ix_regression_findings_processing_run_id", "regression_findings", ["processing_run_id"])
    op.create_index("ix_regression_findings_evidence_hash", "regression_findings", ["evidence_hash"])

    with op.batch_alter_table("hypothesis_evidence") as batch_op:
        batch_op.add_column(sa.Column("page_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("processing_run_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("external_source_ref_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("evidence_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_hypothesis_evidence_page_id", "hypothesis_evidence", ["page_id"])
    op.create_index("ix_hypothesis_evidence_processing_run_id", "hypothesis_evidence", ["processing_run_id"])
    op.create_index("ix_hypothesis_evidence_external_source_ref_id", "hypothesis_evidence", ["external_source_ref_id"])
    op.create_index("ix_hypothesis_evidence_evidence_hash", "hypothesis_evidence", ["evidence_hash"])

    with op.batch_alter_table("external_source_refs") as batch_op:
        batch_op.add_column(sa.Column("hypothesis_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("evidence_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_external_source_refs_hypothesis_id", "external_source_refs", ["hypothesis_id"])
    op.create_index("ix_external_source_refs_evidence_hash", "external_source_refs", ["evidence_hash"])


def downgrade() -> None:
    op.drop_index("ix_external_source_refs_evidence_hash", table_name="external_source_refs")
    op.drop_index("ix_external_source_refs_hypothesis_id", table_name="external_source_refs")
    with op.batch_alter_table("external_source_refs") as batch_op:
        batch_op.drop_column("evidence_hash")
        batch_op.drop_column("confidence")
        batch_op.drop_column("hypothesis_id")

    for table_name, indexes in (
        ("hypothesis_evidence", ("evidence_hash", "external_source_ref_id", "processing_run_id", "page_id")),
        ("regression_findings", ("evidence_hash", "processing_run_id", "page_id")),
        ("baseline_revisions", ("processing_run_id",)),
        ("baseline_obligations", ("evidence_hash", "processing_run_id", "page_id")),
    ):
        for column in indexes:
            op.drop_index(f"ix_{table_name}_{column}", table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            for column in indexes:
                batch_op.drop_column(column)

    for table_name in ("document_report_facts", "document_entities"):
        for suffix in (
            "processing_run_id",
            "page_id",
            "evidence_hash",
            "document_upload_id",
            "contract_id",
            "chunk_id",
        ):
            op.drop_index(f"ix_{table_name}_{suffix}", table_name=table_name)
        if table_name == "document_entities":
            op.drop_index("ix_document_entities_normalized_value", table_name=table_name)
            op.drop_index("ix_document_entities_entity_type", table_name=table_name)
        else:
            op.drop_index("ix_document_report_facts_fact_type", table_name=table_name)
        op.drop_table(table_name)

    op.drop_index("ix_document_classification_decisions_processing_run_id", table_name="document_classification_decisions")
    op.drop_index("ix_document_classification_decisions_modification_kind", table_name="document_classification_decisions")
    op.drop_index("ix_document_classification_decisions_document_upload_id", table_name="document_classification_decisions")
    op.drop_index("ix_document_classification_decisions_document_kind", table_name="document_classification_decisions")
    op.drop_table("document_classification_decisions")

    op.drop_index("ix_document_pages_processing_run_id", table_name="document_pages")
    op.drop_index("ix_document_pages_extraction_status", table_name="document_pages")
    op.drop_index("ix_document_pages_document_upload_id", table_name="document_pages")
    op.drop_table("document_pages")

    op.drop_index("ix_processing_run_steps_step_name", table_name="processing_run_steps")
    op.drop_index("ix_processing_run_steps_status", table_name="processing_run_steps")
    op.drop_index("ix_processing_run_steps_processing_run_id", table_name="processing_run_steps")
    op.drop_index("ix_processing_run_steps_document_upload_id", table_name="processing_run_steps")
    op.drop_table("processing_run_steps")

    op.drop_index("ix_processing_runs_status", table_name="processing_runs")
    op.drop_index("ix_processing_runs_job_id", table_name="processing_runs")
    op.drop_index("ix_processing_runs_document_upload_id", table_name="processing_runs")
    op.drop_index("ix_processing_runs_contract_id", table_name="processing_runs")
    op.drop_table("processing_runs")
