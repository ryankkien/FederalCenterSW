"""add ai contract knowledge base schema

Revision ID: 20260425_0002
Revises: 20260425_0001
Create Date: 2026-04-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260425_0002"
down_revision: Union[str, None] = "20260425_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


class VectorType(sa.types.UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dimensions})"


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _embedding_type() -> sa.types.TypeEngine:
    if _dialect_name() == "postgresql":
        return VectorType(1536)
    return sa.JSON()


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
    if _dialect_name() == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "contracts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_number", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("agency_name", sa.String(length=200), nullable=True),
        sa.Column("office_name", sa.String(length=200), nullable=True),
        sa.Column("vendor_name", sa.String(length=200), nullable=True),
        sa.Column("vendor_uei", sa.String(length=32), nullable=True),
        sa.Column("naics_code", sa.String(length=20), nullable=True),
        sa.Column("psc_code", sa.String(length=20), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("security_level", sa.String(length=40), server_default="standard", nullable=False),
        sa.Column("record_blob_path", sa.String(length=700), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_number", name="uq_contracts_contract_number"),
    )
    op.create_index("ix_contracts_agency_name", "contracts", ["agency_name"])
    op.create_index("ix_contracts_contract_number", "contracts", ["contract_number"])
    op.create_index("ix_contracts_naics_code", "contracts", ["naics_code"])
    op.create_index("ix_contracts_psc_code", "contracts", ["psc_code"])
    op.create_index("ix_contracts_security_level", "contracts", ["security_level"])
    op.create_index("ix_contracts_status", "contracts", ["status"])
    op.create_index("ix_contracts_vendor_name", "contracts", ["vendor_name"])
    op.create_index("ix_contracts_vendor_uei", "contracts", ["vendor_uei"])

    op.create_table(
        "contract_access_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("principal_id", sa.String(length=120), nullable=False),
        sa.Column("principal_type", sa.String(length=40), server_default="user", nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("security_level", sa.String(length=40), server_default="standard", nullable=False),
        sa.Column("granted_by_id", sa.String(length=120), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "principal_id", "role", name="uq_contract_access_grant"),
    )
    op.create_index("ix_contract_access_grants_contract_id", "contract_access_grants", ["contract_id"])
    op.create_index("ix_contract_access_grants_principal_id", "contract_access_grants", ["principal_id"])
    op.create_index("ix_contract_access_grants_role", "contract_access_grants", ["role"])

    op.create_table(
        "email_intake_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("mailbox", sa.String(length=255), nullable=True),
        sa.Column("sender_email", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="received", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_email_intake_messages_message_id"),
    )
    op.create_index("ix_email_intake_messages_message_id", "email_intake_messages", ["message_id"])
    op.create_index("ix_email_intake_messages_received_at", "email_intake_messages", ["received_at"])
    op.create_index("ix_email_intake_messages_sender_email", "email_intake_messages", ["sender_email"])
    op.create_index("ix_email_intake_messages_status", "email_intake_messages", ["status"])

    with op.batch_alter_table("document_uploads") as batch_op:
        batch_op.add_column(sa.Column("contract_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("document_kind", sa.String(length=80), server_default="report", nullable=False)
        )
        batch_op.add_column(
            sa.Column("intake_source", sa.String(length=40), server_default="portal", nullable=False)
        )
        batch_op.add_column(sa.Column("text_blob_path", sa.String(length=700), nullable=True))
        batch_op.add_column(sa.Column("source_sha256", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("email_message_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("report_period_start", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("report_period_end", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("match_status", sa.String(length=40), server_default="pending", nullable=False)
        )
        batch_op.add_column(
            sa.Column("processing_status", sa.String(length=40), server_default="pending", nullable=False)
        )
        batch_op.add_column(sa.Column("processing_error_code", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("processing_error_message", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("security_level", sa.String(length=40), server_default="standard", nullable=False)
        )
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))
        batch_op.add_column(_updated_at_column())
        batch_op.create_foreign_key(
            "fk_document_uploads_contract_id_contracts",
            "contracts",
            ["contract_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_document_uploads_contract_id", "document_uploads", ["contract_id"])
    op.create_index("ix_document_uploads_email_message_id", "document_uploads", ["email_message_id"])
    op.create_index("ix_document_uploads_match_status", "document_uploads", ["match_status"])
    op.create_index("ix_document_uploads_processing_status", "document_uploads", ["processing_status"])
    op.create_index("ix_document_uploads_security_level", "document_uploads", ["security_level"])
    op.create_index("ix_document_uploads_source_sha256", "document_uploads", ["source_sha256"])

    op.create_table(
        "document_match_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("matched_contract_number", sa.String(length=120), nullable=True),
        sa.Column("decision_status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("decision_source", sa.String(length=40), server_default="system", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.String(length=120), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_match_decisions_contract_id", "document_match_decisions", ["contract_id"])
    op.create_index(
        "ix_document_match_decisions_decision_status",
        "document_match_decisions",
        ["decision_status"],
    )
    op.create_index(
        "ix_document_match_decisions_document_upload_id",
        "document_match_decisions",
        ["document_upload_id"],
    )
    op.create_index(
        "ix_document_match_decisions_matched_contract_number",
        "document_match_decisions",
        ["matched_contract_number"],
    )

    op.create_table(
        "document_processing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=80), server_default="document_analysis", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_processing_jobs_document_upload_id",
        "document_processing_jobs",
        ["document_upload_id"],
    )
    op.create_index("ix_document_processing_jobs_job_type", "document_processing_jobs", ["job_type"])
    op.create_index("ix_document_processing_jobs_status", "document_processing_jobs", ["status"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(length=300), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_blob_path", sa.String(length=700), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_upload_id", "chunk_index", name="uq_document_chunk_position"),
    )
    op.create_index("ix_document_chunks_contract_id", "document_chunks", ["contract_id"])
    op.create_index("ix_document_chunks_document_upload_id", "document_chunks", ["document_upload_id"])

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), server_default="1536", nullable=False),
        sa.Column("embedding", _embedding_type(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "embedding_model", name="uq_chunk_embedding_model"),
    )
    op.create_index("ix_chunk_embeddings_chunk_id", "chunk_embeddings", ["chunk_id"])
    op.create_index("ix_chunk_embeddings_embedding_model", "chunk_embeddings", ["embedding_model"])
    if _dialect_name() == "postgresql":
        op.execute(
            "CREATE INDEX ix_chunk_embeddings_embedding_hnsw "
            "ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)"
        )

    op.create_table(
        "performance_signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("signal_type", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_performance_signals_chunk_id", "performance_signals", ["chunk_id"])
    op.create_index("ix_performance_signals_contract_id", "performance_signals", ["contract_id"])
    op.create_index(
        "ix_performance_signals_document_upload_id",
        "performance_signals",
        ["document_upload_id"],
    )
    op.create_index("ix_performance_signals_severity", "performance_signals", ["severity"])
    op.create_index("ix_performance_signals_signal_type", "performance_signals", ["signal_type"])

    op.create_table(
        "contract_topics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("topic_key", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "topic_key", name="uq_contract_topic_key"),
    )
    op.create_index("ix_contract_topics_contract_id", "contract_topics", ["contract_id"])
    op.create_index("ix_contract_topics_status", "contract_topics", ["status"])

    op.create_table(
        "topic_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("performance_signal_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_type", sa.String(length=80), server_default="supporting", nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["performance_signal_id"],
            ["performance_signals.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["topic_id"], ["contract_topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topic_evidence_chunk_id", "topic_evidence", ["chunk_id"])
    op.create_index("ix_topic_evidence_document_upload_id", "topic_evidence", ["document_upload_id"])
    op.create_index("ix_topic_evidence_evidence_type", "topic_evidence", ["evidence_type"])
    op.create_index(
        "ix_topic_evidence_performance_signal_id",
        "topic_evidence",
        ["performance_signal_id"],
    )
    op.create_index("ix_topic_evidence_topic_id", "topic_evidence", ["topic_id"])

    op.create_table(
        "topic_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_topic_id", sa.String(length=36), nullable=False),
        sa.Column("target_topic_id", sa.String(length=36), nullable=False),
        sa.Column("link_type", sa.String(length=80), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["source_topic_id"], ["contract_topics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_topic_id"], ["contract_topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_topic_id", "target_topic_id", "link_type", name="uq_topic_link"),
    )
    op.create_index("ix_topic_links_link_type", "topic_links", ["link_type"])
    op.create_index("ix_topic_links_source_topic_id", "topic_links", ["source_topic_id"])
    op.create_index("ix_topic_links_target_topic_id", "topic_links", ["target_topic_id"])

    op.create_table(
        "contract_topic_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("changed_by_id", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        _created_at_column(),
        sa.ForeignKeyConstraint(["topic_id"], ["contract_topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "revision_number", name="uq_contract_topic_revision"),
    )
    op.create_index(
        "ix_contract_topic_revisions_changed_by_id",
        "contract_topic_revisions",
        ["changed_by_id"],
    )
    op.create_index("ix_contract_topic_revisions_topic_id", "contract_topic_revisions", ["topic_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=True),
        sa.Column("actor_role", sa.String(length=40), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("document_upload_id", sa.String(length=36), nullable=True),
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_upload_id"], ["document_uploads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_contract_id", "audit_events", ["contract_id"])
    op.create_index("ix_audit_events_document_upload_id", "audit_events", ["document_upload_id"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
    op.create_index("ix_audit_events_event_time", "audit_events", ["event_time"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_event_time", table_name="audit_events")
    op.drop_index("ix_audit_events_entity_type", table_name="audit_events")
    op.drop_index("ix_audit_events_entity_id", table_name="audit_events")
    op.drop_index("ix_audit_events_document_upload_id", table_name="audit_events")
    op.drop_index("ix_audit_events_contract_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_contract_topic_revisions_topic_id", table_name="contract_topic_revisions")
    op.drop_index("ix_contract_topic_revisions_changed_by_id", table_name="contract_topic_revisions")
    op.drop_table("contract_topic_revisions")

    op.drop_index("ix_topic_links_target_topic_id", table_name="topic_links")
    op.drop_index("ix_topic_links_source_topic_id", table_name="topic_links")
    op.drop_index("ix_topic_links_link_type", table_name="topic_links")
    op.drop_table("topic_links")

    op.drop_index("ix_topic_evidence_topic_id", table_name="topic_evidence")
    op.drop_index("ix_topic_evidence_performance_signal_id", table_name="topic_evidence")
    op.drop_index("ix_topic_evidence_evidence_type", table_name="topic_evidence")
    op.drop_index("ix_topic_evidence_document_upload_id", table_name="topic_evidence")
    op.drop_index("ix_topic_evidence_chunk_id", table_name="topic_evidence")
    op.drop_table("topic_evidence")

    op.drop_index("ix_contract_topics_status", table_name="contract_topics")
    op.drop_index("ix_contract_topics_contract_id", table_name="contract_topics")
    op.drop_table("contract_topics")

    op.drop_index("ix_performance_signals_signal_type", table_name="performance_signals")
    op.drop_index("ix_performance_signals_severity", table_name="performance_signals")
    op.drop_index("ix_performance_signals_document_upload_id", table_name="performance_signals")
    op.drop_index("ix_performance_signals_contract_id", table_name="performance_signals")
    op.drop_index("ix_performance_signals_chunk_id", table_name="performance_signals")
    op.drop_table("performance_signals")

    if _dialect_name() == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_chunk_embeddings_embedding_hnsw")
    op.drop_index("ix_chunk_embeddings_embedding_model", table_name="chunk_embeddings")
    op.drop_index("ix_chunk_embeddings_chunk_id", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")

    op.drop_index("ix_document_chunks_document_upload_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_contract_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_document_processing_jobs_status", table_name="document_processing_jobs")
    op.drop_index("ix_document_processing_jobs_job_type", table_name="document_processing_jobs")
    op.drop_index(
        "ix_document_processing_jobs_document_upload_id",
        table_name="document_processing_jobs",
    )
    op.drop_table("document_processing_jobs")

    op.drop_index(
        "ix_document_match_decisions_matched_contract_number",
        table_name="document_match_decisions",
    )
    op.drop_index(
        "ix_document_match_decisions_document_upload_id",
        table_name="document_match_decisions",
    )
    op.drop_index(
        "ix_document_match_decisions_decision_status",
        table_name="document_match_decisions",
    )
    op.drop_index("ix_document_match_decisions_contract_id", table_name="document_match_decisions")
    op.drop_table("document_match_decisions")

    op.drop_index("ix_document_uploads_source_sha256", table_name="document_uploads")
    op.drop_index("ix_document_uploads_security_level", table_name="document_uploads")
    op.drop_index("ix_document_uploads_processing_status", table_name="document_uploads")
    op.drop_index("ix_document_uploads_match_status", table_name="document_uploads")
    op.drop_index("ix_document_uploads_email_message_id", table_name="document_uploads")
    op.drop_index("ix_document_uploads_contract_id", table_name="document_uploads")
    with op.batch_alter_table("document_uploads") as batch_op:
        batch_op.drop_constraint("fk_document_uploads_contract_id_contracts", type_="foreignkey")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("security_level")
        batch_op.drop_column("processing_error_message")
        batch_op.drop_column("processing_error_code")
        batch_op.drop_column("processing_status")
        batch_op.drop_column("match_status")
        batch_op.drop_column("report_period_end")
        batch_op.drop_column("report_period_start")
        batch_op.drop_column("email_message_id")
        batch_op.drop_column("source_sha256")
        batch_op.drop_column("text_blob_path")
        batch_op.drop_column("intake_source")
        batch_op.drop_column("document_kind")
        batch_op.drop_column("contract_id")

    op.drop_index("ix_email_intake_messages_status", table_name="email_intake_messages")
    op.drop_index("ix_email_intake_messages_sender_email", table_name="email_intake_messages")
    op.drop_index("ix_email_intake_messages_received_at", table_name="email_intake_messages")
    op.drop_index("ix_email_intake_messages_message_id", table_name="email_intake_messages")
    op.drop_table("email_intake_messages")

    op.drop_index("ix_contract_access_grants_role", table_name="contract_access_grants")
    op.drop_index("ix_contract_access_grants_principal_id", table_name="contract_access_grants")
    op.drop_index("ix_contract_access_grants_contract_id", table_name="contract_access_grants")
    op.drop_table("contract_access_grants")

    op.drop_index("ix_contracts_vendor_uei", table_name="contracts")
    op.drop_index("ix_contracts_vendor_name", table_name="contracts")
    op.drop_index("ix_contracts_status", table_name="contracts")
    op.drop_index("ix_contracts_security_level", table_name="contracts")
    op.drop_index("ix_contracts_psc_code", table_name="contracts")
    op.drop_index("ix_contracts_naics_code", table_name="contracts")
    op.drop_index("ix_contracts_contract_number", table_name="contracts")
    op.drop_index("ix_contracts_agency_name", table_name="contracts")
    op.drop_table("contracts")
