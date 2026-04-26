"""add knowledge wiki index

Revision ID: 20260426_0005
Revises: 20260426_0004
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260426_0005"
down_revision: Union[str, None] = "20260426_0004"
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
        "knowledge_ingestion_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="running", nullable=False),
        sa.Column("sources_requested", sa.JSON(), nullable=True),
        sa.Column("contract_ids", sa.JSON(), nullable=True),
        sa.Column("vendor_ueis", sa.JSON(), nullable=True),
        sa.Column("limit", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_ingestion_runs_scope", "knowledge_ingestion_runs", ["scope"])
    op.create_index("ix_knowledge_ingestion_runs_status", "knowledge_ingestion_runs", ["status"])

    op.create_table(
        "knowledge_source_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=80), server_default="official", nullable=False),
        sa.Column("source_key", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="available", nullable=False),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("vendor_uei", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["knowledge_ingestion_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name", "source_key", name="uq_knowledge_source_key"),
    )
    op.create_index("ix_knowledge_source_records_content_hash", "knowledge_source_records", ["content_hash"])
    op.create_index("ix_knowledge_source_records_contract_id", "knowledge_source_records", ["contract_id"])
    op.create_index("ix_knowledge_source_records_ingestion_run_id", "knowledge_source_records", ["ingestion_run_id"])
    op.create_index("ix_knowledge_source_records_source_name", "knowledge_source_records", ["source_name"])
    op.create_index("ix_knowledge_source_records_source_type", "knowledge_source_records", ["source_type"])
    op.create_index("ix_knowledge_source_records_status", "knowledge_source_records", ["status"])
    op.create_index("ix_knowledge_source_records_vendor_uei", "knowledge_source_records", ["vendor_uei"])

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_type", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("vendor_uei", sa.String(length=32), nullable=True),
        sa.Column("security_level", sa.String(length=40), server_default="standard", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("source_record_id", sa.String(length=36), nullable=True),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_record_id"], ["knowledge_source_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_type", "slug", name="uq_knowledge_node_slug"),
    )
    op.create_index("ix_knowledge_nodes_contract_id", "knowledge_nodes", ["contract_id"])
    op.create_index("ix_knowledge_nodes_node_type", "knowledge_nodes", ["node_type"])
    op.create_index("ix_knowledge_nodes_security_level", "knowledge_nodes", ["security_level"])
    op.create_index("ix_knowledge_nodes_slug", "knowledge_nodes", ["slug"])
    op.create_index("ix_knowledge_nodes_source_record_id", "knowledge_nodes", ["source_record_id"])
    op.create_index("ix_knowledge_nodes_status", "knowledge_nodes", ["status"])
    op.create_index("ix_knowledge_nodes_vendor_uei", "knowledge_nodes", ["vendor_uei"])

    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_node_id", sa.String(length=36), nullable=False),
        sa.Column("target_node_id", sa.String(length=36), nullable=False),
        sa.Column("edge_type", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["source_node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_node_id", "target_node_id", "edge_type", name="uq_knowledge_edge"),
    )
    op.create_index("ix_knowledge_edges_edge_type", "knowledge_edges", ["edge_type"])
    op.create_index("ix_knowledge_edges_source_node_id", "knowledge_edges", ["source_node_id"])
    op.create_index("ix_knowledge_edges_target_node_id", "knowledge_edges", ["target_node_id"])

    op.create_table(
        "knowledge_citations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("source_record_id", sa.String(length=36), nullable=True),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("external_source_ref_id", sa.String(length=36), nullable=True),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("source_path", sa.String(length=1000), nullable=True),
        sa.Column("quote_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["external_source_ref_id"], ["external_source_refs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_record_id"], ["knowledge_source_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_citations_document_upload_id", "knowledge_citations", ["document_upload_id"])
    op.create_index("ix_knowledge_citations_external_source_ref_id", "knowledge_citations", ["external_source_ref_id"])
    op.create_index("ix_knowledge_citations_node_id", "knowledge_citations", ["node_id"])
    op.create_index("ix_knowledge_citations_quote_hash", "knowledge_citations", ["quote_hash"])
    op.create_index("ix_knowledge_citations_source_record_id", "knowledge_citations", ["source_record_id"])

    op.create_table(
        "contractor_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vendor_uei", sa.String(length=32), nullable=True),
        sa.Column("vendor_name", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_labels", sa.JSON(), nullable=True),
        sa.Column("award_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_obligated", sa.Float(), nullable=True),
        sa.Column("unresolved_issue_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("contradiction_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor_uei", name="uq_contractor_profiles_vendor_uei"),
    )
    op.create_index("ix_contractor_profiles_vendor_name", "contractor_profiles", ["vendor_name"])
    op.create_index("ix_contractor_profiles_vendor_uei", "contractor_profiles", ["vendor_uei"])


def downgrade() -> None:
    op.drop_index("ix_contractor_profiles_vendor_uei", table_name="contractor_profiles")
    op.drop_index("ix_contractor_profiles_vendor_name", table_name="contractor_profiles")
    op.drop_table("contractor_profiles")

    op.drop_index("ix_knowledge_citations_source_record_id", table_name="knowledge_citations")
    op.drop_index("ix_knowledge_citations_quote_hash", table_name="knowledge_citations")
    op.drop_index("ix_knowledge_citations_node_id", table_name="knowledge_citations")
    op.drop_index("ix_knowledge_citations_external_source_ref_id", table_name="knowledge_citations")
    op.drop_index("ix_knowledge_citations_document_upload_id", table_name="knowledge_citations")
    op.drop_table("knowledge_citations")

    op.drop_index("ix_knowledge_edges_target_node_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_source_node_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_edge_type", table_name="knowledge_edges")
    op.drop_table("knowledge_edges")

    op.drop_index("ix_knowledge_nodes_vendor_uei", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_status", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_source_record_id", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_slug", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_security_level", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_node_type", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_contract_id", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")

    op.drop_index("ix_knowledge_source_records_vendor_uei", table_name="knowledge_source_records")
    op.drop_index("ix_knowledge_source_records_status", table_name="knowledge_source_records")
    op.drop_index("ix_knowledge_source_records_source_type", table_name="knowledge_source_records")
    op.drop_index("ix_knowledge_source_records_source_name", table_name="knowledge_source_records")
    op.drop_index("ix_knowledge_source_records_ingestion_run_id", table_name="knowledge_source_records")
    op.drop_index("ix_knowledge_source_records_contract_id", table_name="knowledge_source_records")
    op.drop_index("ix_knowledge_source_records_content_hash", table_name="knowledge_source_records")
    op.drop_table("knowledge_source_records")

    op.drop_index("ix_knowledge_ingestion_runs_status", table_name="knowledge_ingestion_runs")
    op.drop_index("ix_knowledge_ingestion_runs_scope", table_name="knowledge_ingestion_runs")
    op.drop_table("knowledge_ingestion_runs")
