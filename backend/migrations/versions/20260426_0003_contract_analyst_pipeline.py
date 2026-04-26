"""add contract analyst pipeline schema

Revision ID: 20260426_0003
Revises: 20260425_0002
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_0003"
down_revision: Union[str, None] = "20260425_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _created_at_column() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def _updated_at_column() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "contract_baselines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("current_revision_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_upload_id"],
            ["document_uploads.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", name="uq_contract_baselines_contract_id"),
    )
    op.create_index("ix_contract_baselines_contract_id", "contract_baselines", ["contract_id"])
    op.create_index(
        "ix_contract_baselines_source_document_upload_id",
        "contract_baselines",
        ["source_document_upload_id"],
    )

    op.create_table(
        "baseline_obligations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("baseline_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("obligation_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["baseline_id"], ["contract_baselines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_upload_id"],
            ["document_uploads.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_baseline_obligations_baseline_id", "baseline_obligations", ["baseline_id"])
    op.create_index("ix_baseline_obligations_chunk_id", "baseline_obligations", ["chunk_id"])
    op.create_index("ix_baseline_obligations_contract_id", "baseline_obligations", ["contract_id"])
    op.create_index(
        "ix_baseline_obligations_obligation_type",
        "baseline_obligations",
        ["obligation_type"],
    )
    op.create_index(
        "ix_baseline_obligations_source_document_upload_id",
        "baseline_obligations",
        ["source_document_upload_id"],
    )

    op.create_table(
        "baseline_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("baseline_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["baseline_id"], ["contract_baselines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_upload_id"],
            ["document_uploads.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("baseline_id", "revision_number", name="uq_baseline_revision_number"),
    )
    op.create_index("ix_baseline_revisions_baseline_id", "baseline_revisions", ["baseline_id"])
    op.create_index("ix_baseline_revisions_change_type", "baseline_revisions", ["change_type"])
    op.create_index("ix_baseline_revisions_contract_id", "baseline_revisions", ["contract_id"])
    op.create_index(
        "ix_baseline_revisions_source_document_upload_id",
        "baseline_revisions",
        ["source_document_upload_id"],
    )

    op.create_table(
        "regression_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("baseline_obligation_id", sa.String(length=36), nullable=True),
        sa.Column("finding_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), server_default="medium", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="open", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["baseline_obligation_id"],
            ["baseline_obligations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_regression_findings_baseline_obligation_id",
        "regression_findings",
        ["baseline_obligation_id"],
    )
    op.create_index("ix_regression_findings_chunk_id", "regression_findings", ["chunk_id"])
    op.create_index("ix_regression_findings_contract_id", "regression_findings", ["contract_id"])
    op.create_index(
        "ix_regression_findings_document_upload_id",
        "regression_findings",
        ["document_upload_id"],
    )
    op.create_index("ix_regression_findings_finding_type", "regression_findings", ["finding_type"])
    op.create_index("ix_regression_findings_severity", "regression_findings", ["severity"])
    op.create_index("ix_regression_findings_status", "regression_findings", ["status"])

    op.create_table(
        "contract_hypotheses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("hypothesis_key", sa.String(length=140), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="proposed", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_by_id", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "hypothesis_key", name="uq_contract_hypothesis_key"),
    )
    op.create_index("ix_contract_hypotheses_contract_id", "contract_hypotheses", ["contract_id"])
    op.create_index("ix_contract_hypotheses_status", "contract_hypotheses", ["status"])

    op.create_table(
        "hypothesis_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hypothesis_id", sa.String(length=36), nullable=False),
        sa.Column("regression_finding_id", sa.String(length=36), nullable=True),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_type", sa.String(length=40), server_default="supporting", nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["contract_hypotheses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["regression_finding_id"],
            ["regression_findings.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hypothesis_evidence_chunk_id", "hypothesis_evidence", ["chunk_id"])
    op.create_index(
        "ix_hypothesis_evidence_document_upload_id",
        "hypothesis_evidence",
        ["document_upload_id"],
    )
    op.create_index("ix_hypothesis_evidence_evidence_type", "hypothesis_evidence", ["evidence_type"])
    op.create_index("ix_hypothesis_evidence_hypothesis_id", "hypothesis_evidence", ["hypothesis_id"])
    op.create_index(
        "ix_hypothesis_evidence_regression_finding_id",
        "hypothesis_evidence",
        ["regression_finding_id"],
    )

    op.create_table(
        "investigation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("hypothesis_id", sa.String(length=36), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="completed", nullable=False),
        sa.Column("sources_checked", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_by_id", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["contract_hypotheses.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_investigation_runs_contract_id", "investigation_runs", ["contract_id"])
    op.create_index("ix_investigation_runs_hypothesis_id", "investigation_runs", ["hypothesis_id"])
    op.create_index("ix_investigation_runs_status", "investigation_runs", ["status"])

    op.create_table(
        "external_source_refs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("investigation_run_id", sa.String(length=36), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("source_domain", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=80), server_default="official", nullable=False),
        sa.Column("citation_text", sa.Text(), nullable=True),
        sa.Column("is_official", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["investigation_run_id"],
            ["investigation_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_source_refs_contract_id", "external_source_refs", ["contract_id"])
    op.create_index(
        "ix_external_source_refs_investigation_run_id",
        "external_source_refs",
        ["investigation_run_id"],
    )
    op.create_index("ix_external_source_refs_is_official", "external_source_refs", ["is_official"])
    op.create_index("ix_external_source_refs_source_domain", "external_source_refs", ["source_domain"])
    op.create_index("ix_external_source_refs_source_type", "external_source_refs", ["source_type"])

    op.create_table(
        "contract_similarity_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_contract_id", sa.String(length=36), nullable=False),
        sa.Column("target_contract_id", sa.String(length=36), nullable=False),
        sa.Column("link_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["source_contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_contract_id",
            "target_contract_id",
            "link_type",
            name="uq_contract_similarity_link",
        ),
    )
    op.create_index(
        "ix_contract_similarity_links_link_type",
        "contract_similarity_links",
        ["link_type"],
    )
    op.create_index(
        "ix_contract_similarity_links_source_contract_id",
        "contract_similarity_links",
        ["source_contract_id"],
    )
    op.create_index(
        "ix_contract_similarity_links_target_contract_id",
        "contract_similarity_links",
        ["target_contract_id"],
    )

    op.create_table(
        "document_semantic_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("target_document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("link_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(
            ["source_document_upload_id"],
            ["document_uploads.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_document_upload_id"],
            ["document_uploads.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_document_upload_id",
            "target_document_upload_id",
            "link_type",
            name="uq_document_semantic_link",
        ),
    )
    op.create_index("ix_document_semantic_links_link_type", "document_semantic_links", ["link_type"])
    op.create_index(
        "ix_document_semantic_links_source_document_upload_id",
        "document_semantic_links",
        ["source_document_upload_id"],
    )
    op.create_index(
        "ix_document_semantic_links_target_document_upload_id",
        "document_semantic_links",
        ["target_document_upload_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_semantic_links_target_document_upload_id", table_name="document_semantic_links")
    op.drop_index("ix_document_semantic_links_source_document_upload_id", table_name="document_semantic_links")
    op.drop_index("ix_document_semantic_links_link_type", table_name="document_semantic_links")
    op.drop_table("document_semantic_links")

    op.drop_index("ix_contract_similarity_links_target_contract_id", table_name="contract_similarity_links")
    op.drop_index("ix_contract_similarity_links_source_contract_id", table_name="contract_similarity_links")
    op.drop_index("ix_contract_similarity_links_link_type", table_name="contract_similarity_links")
    op.drop_table("contract_similarity_links")

    op.drop_index("ix_external_source_refs_source_type", table_name="external_source_refs")
    op.drop_index("ix_external_source_refs_source_domain", table_name="external_source_refs")
    op.drop_index("ix_external_source_refs_is_official", table_name="external_source_refs")
    op.drop_index("ix_external_source_refs_investigation_run_id", table_name="external_source_refs")
    op.drop_index("ix_external_source_refs_contract_id", table_name="external_source_refs")
    op.drop_table("external_source_refs")

    op.drop_index("ix_investigation_runs_status", table_name="investigation_runs")
    op.drop_index("ix_investigation_runs_hypothesis_id", table_name="investigation_runs")
    op.drop_index("ix_investigation_runs_contract_id", table_name="investigation_runs")
    op.drop_table("investigation_runs")

    op.drop_index("ix_hypothesis_evidence_regression_finding_id", table_name="hypothesis_evidence")
    op.drop_index("ix_hypothesis_evidence_hypothesis_id", table_name="hypothesis_evidence")
    op.drop_index("ix_hypothesis_evidence_evidence_type", table_name="hypothesis_evidence")
    op.drop_index("ix_hypothesis_evidence_document_upload_id", table_name="hypothesis_evidence")
    op.drop_index("ix_hypothesis_evidence_chunk_id", table_name="hypothesis_evidence")
    op.drop_table("hypothesis_evidence")

    op.drop_index("ix_contract_hypotheses_status", table_name="contract_hypotheses")
    op.drop_index("ix_contract_hypotheses_contract_id", table_name="contract_hypotheses")
    op.drop_table("contract_hypotheses")

    op.drop_index("ix_regression_findings_status", table_name="regression_findings")
    op.drop_index("ix_regression_findings_severity", table_name="regression_findings")
    op.drop_index("ix_regression_findings_finding_type", table_name="regression_findings")
    op.drop_index("ix_regression_findings_document_upload_id", table_name="regression_findings")
    op.drop_index("ix_regression_findings_contract_id", table_name="regression_findings")
    op.drop_index("ix_regression_findings_chunk_id", table_name="regression_findings")
    op.drop_index("ix_regression_findings_baseline_obligation_id", table_name="regression_findings")
    op.drop_table("regression_findings")

    op.drop_index("ix_baseline_revisions_source_document_upload_id", table_name="baseline_revisions")
    op.drop_index("ix_baseline_revisions_contract_id", table_name="baseline_revisions")
    op.drop_index("ix_baseline_revisions_change_type", table_name="baseline_revisions")
    op.drop_index("ix_baseline_revisions_baseline_id", table_name="baseline_revisions")
    op.drop_table("baseline_revisions")

    op.drop_index("ix_baseline_obligations_source_document_upload_id", table_name="baseline_obligations")
    op.drop_index("ix_baseline_obligations_obligation_type", table_name="baseline_obligations")
    op.drop_index("ix_baseline_obligations_contract_id", table_name="baseline_obligations")
    op.drop_index("ix_baseline_obligations_chunk_id", table_name="baseline_obligations")
    op.drop_index("ix_baseline_obligations_baseline_id", table_name="baseline_obligations")
    op.drop_table("baseline_obligations")

    op.drop_index("ix_contract_baselines_source_document_upload_id", table_name="contract_baselines")
    op.drop_index("ix_contract_baselines_contract_id", table_name="contract_baselines")
    op.drop_table("contract_baselines")
