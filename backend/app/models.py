from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base

try:
    from pgvector.sqlalchemy import Vector as PgVector
except Exception:  # pragma: no cover - pgvector is optional for SQLite tests.
    PgVector = None


class PortableVector(TypeDecorator):
    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = 1536) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PgVector is not None:
            return dialect.type_descriptor(PgVector(self.dimensions))
        return dialect.type_descriptor(JSON())


class DocumentUpload(Base):
    __tablename__ = "document_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    document_kind: Mapped[str] = mapped_column(String(80), default="report", nullable=False)
    intake_source: Mapped[str] = mapped_column(String(40), default="portal", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    blob_path: Mapped[str] = mapped_column(String(700), nullable=False)
    text_blob_path: Mapped[Optional[str]] = mapped_column(String(700), nullable=True)
    source_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    email_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    report_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    report_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    match_status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    processing_status: Mapped[str] = mapped_column(
        String(40),
        default="pending",
        nullable=False,
        index=True,
    )
    processing_error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    processing_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    security_level: Mapped[str] = mapped_column(
        String(40),
        default="standard",
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    uploader_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    uploader_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    contract: Mapped[Optional["Contract"]] = relationship(back_populates="documents")


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_number: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agency_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    office_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    vendor_uei: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    naics_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    psc_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    contract_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    competition_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False, index=True)
    security_level: Mapped[str] = mapped_column(
        String(40),
        default="standard",
        nullable=False,
        index=True,
    )
    record_blob_path: Mapped[Optional[str]] = mapped_column(String(700), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    documents: Mapped[List[DocumentUpload]] = relationship(back_populates="contract")


class ContractAccessGrant(Base):
    __tablename__ = "contract_access_grants"
    __table_args__ = (
        UniqueConstraint("contract_id", "principal_id", "role", name="uq_contract_access_grant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    principal_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(String(40), default="user", nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    security_level: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    granted_by_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class EmailIntakeMessage(Base):
    __tablename__ = "email_intake_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    mailbox: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True, index=True)
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="received", nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentMatchDecision(Base):
    __tablename__ = "document_match_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched_contract_number: Mapped[Optional[str]] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )
    decision_status: Mapped[str] = mapped_column(
        String(40),
        default="pending",
        nullable=False,
        index=True,
    )
    decision_source: Mapped[str] = mapped_column(String(40), default="system", nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentClassificationDecision(Base):
    __tablename__ = "document_classification_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    modification_kind: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    classifier_name: Mapped[str] = mapped_column(String(120), default="deterministic_v1", nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(
        String(80),
        default="document_analysis",
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_type: Mapped[str] = mapped_column(String(80), default="document_analysis", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="running", nullable=False, index=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    raw_model_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    result_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class ProcessingRunStep(Base):
    __tablename__ = "processing_run_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    processing_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    step_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_upload_id", "page_number", name="uq_document_page_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(40), default="extracted", nullable=False, index=True)
    source_start_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_end_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extraction_warning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_upload_id", "chunk_index", name="uq_document_chunk_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section_title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_blob_path: Mapped[Optional[str]] = mapped_column(String(700), nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentReportFact(Base):
    __tablename__ = "document_report_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fact_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    value_text: Mapped[str] = mapped_column(Text, nullable=False)
    value_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "embedding_model", name="uq_chunk_embedding_model"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    embedding_dimension: Mapped[int] = mapped_column(Integer, default=1536, nullable=False)
    embedding: Mapped[List[float]] = mapped_column(PortableVector(1536), nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PerformanceSignal(Base):
    __tablename__ = "performance_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ContractTopic(Base):
    __tablename__ = "contract_topics"
    __table_args__ = (
        UniqueConstraint("contract_id", "topic_key", name="uq_contract_topic_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TopicEvidence(Base):
    __tablename__ = "topic_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contract_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    performance_signal_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("performance_signals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(
        String(80),
        default="supporting",
        nullable=False,
        index=True,
    )
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TopicLink(Base):
    __tablename__ = "topic_links"
    __table_args__ = (
        UniqueConstraint("source_topic_id", "target_topic_id", "link_type", name="uq_topic_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contract_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contract_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ContractTopicRevision(Base):
    __tablename__ = "contract_topic_revisions"
    __table_args__ = (
        UniqueConstraint("topic_id", "revision_number", name="uq_contract_topic_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contract_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class PrimitiveExtractionRun(Base):
    __tablename__ = "primitive_extraction_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    doc_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    period_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    model: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False, index=True)


class ContractPrimitiveDeliverable(Base):
    __tablename__ = "contract_primitives_deliverable"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("primitive_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_doc_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    deliverable_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cdrl_item: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    planned_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    acceptance_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    days_late: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class ContractPrimitiveFinancial(Base):
    __tablename__ = "contract_primitives_financial"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("primitive_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_doc_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    period_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    planned_value: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    earned_value: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    actual_cost: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    budget_at_completion: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    estimate_at_completion: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    estimate_to_complete: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    cost_variance: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    schedule_variance: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    cpi: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    spi: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    percent_complete: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    cumulative_obligations: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)


class ContractPrimitiveDecision(Base):
    __tablename__ = "contract_primitives_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("primitive_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_doc_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    decision_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    mod_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    mod_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_change: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    pop_change_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    scope_change_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    deciding_party: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class ContractPrimitiveIssue(Base):
    __tablename__ = "contract_primitives_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("primitive_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_doc_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    issue_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    responsible_party: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    date_opened: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_resolved: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    recurrence_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ContractPrimitivePersonnel(Base):
    __tablename__ = "contract_primitives_personnel"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    extraction_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("primitive_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_doc_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    labor_category: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    fte_planned: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    fte_actual: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    staffing_gap_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CparsRating(Base):
    __tablename__ = "cpars_ratings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    doc_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evaluation_period: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    evaluation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    quality_rating: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    schedule_rating: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    cost_control_rating: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    management_rating: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    small_business_rating: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    regulatory_compliance_rating: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    overall_rating: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ContractBaseline(Base):
    __tablename__ = "contract_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    source_document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    current_revision_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class BaselineObligation(Base):
    __tablename__ = "baseline_obligations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    baseline_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contract_baselines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    obligation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class BaselineRevision(Base):
    __tablename__ = "baseline_revisions"
    __table_args__ = (
        UniqueConstraint("baseline_id", "revision_number", name="uq_baseline_revision_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    baseline_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contract_baselines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class RegressionFinding(Base):
    __tablename__ = "regression_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    baseline_obligation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("baseline_obligations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    finding_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="medium", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ContractHypothesis(Base):
    __tablename__ = "contract_hypotheses"
    __table_args__ = (
        UniqueConstraint("contract_id", "hypothesis_key", name="uq_contract_hypothesis_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hypothesis_key: Mapped[str] = mapped_column(String(140), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="proposed", nullable=False, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class HypothesisEvidence(Base):
    __tablename__ = "hypothesis_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hypothesis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contract_hypotheses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    regression_finding_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("regression_findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("processing_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_source_ref_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("external_source_refs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(40), default="supporting", nullable=False, index=True)
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class InvestigationRun(Base):
    __tablename__ = "investigation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hypothesis_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contract_hypotheses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False, index=True)
    sources_checked: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ExternalSourceRef(Base):
    __tablename__ = "external_source_refs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    investigation_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("investigation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    hypothesis_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contract_hypotheses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(80), default="official", nullable=False, index=True)
    citation_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ContractSimilarityLink(Base):
    __tablename__ = "contract_similarity_links"
    __table_args__ = (
        UniqueConstraint("source_contract_id", "target_contract_id", "link_type", name="uq_contract_similarity_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentSemanticLink(Base):
    __tablename__ = "document_semantic_links"
    __table_args__ = (
        UniqueConstraint(
            "source_document_upload_id",
            "target_document_upload_id",
            "link_type",
            name="uq_document_semantic_link",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_document_upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class KnowledgeIngestionRun(Base):
    __tablename__ = "knowledge_ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", nullable=False, index=True)
    sources_requested: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    contract_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    vendor_ueis: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class KnowledgeSourceRecord(Base):
    __tablename__ = "knowledge_source_records"
    __table_args__ = (
        UniqueConstraint("source_name", "source_key", name="uq_knowledge_source_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ingestion_run_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("knowledge_ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(80), default="official", nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="available", nullable=False, index=True)
    unavailable_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    source_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vendor_uei: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        UniqueConstraint("node_type", "slug", name="uq_knowledge_node_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    contract_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vendor_uei: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    security_level: Mapped[str] = mapped_column(String(40), default="standard", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False, index=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("knowledge_source_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "edge_type", name="uq_knowledge_edge"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class KnowledgeCitation(Base):
    __tablename__ = "knowledge_citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("knowledge_source_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_upload_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("document_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_source_ref_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("external_source_refs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    quote_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ContractorProfile(Base):
    __tablename__ = "contractor_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vendor_uei: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, unique=True, index=True)
    vendor_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_labels: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    award_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_obligated: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unresolved_issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
