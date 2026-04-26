-- Federal Center SW application schema mirror.
-- Alembic migrations in backend/migrations/versions are authoritative for upgrades.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE contracts (
    id VARCHAR(36) PRIMARY KEY,
    contract_number VARCHAR(120) NOT NULL UNIQUE,
    title VARCHAR(300) NOT NULL,
    description TEXT,
    agency_name VARCHAR(200),
    office_name VARCHAR(200),
    vendor_name VARCHAR(200),
    vendor_uei VARCHAR(32),
    naics_code VARCHAR(20),
    psc_code VARCHAR(20),
    period_start DATE,
    period_end DATE,
    status VARCHAR(40) NOT NULL DEFAULT 'active',
    security_level VARCHAR(40) NOT NULL DEFAULT 'standard',
    record_blob_path VARCHAR(700),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_uploads (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    document_type VARCHAR(80) NOT NULL,
    document_kind VARCHAR(80) NOT NULL DEFAULT 'report',
    intake_source VARCHAR(40) NOT NULL DEFAULT 'portal',
    notes TEXT,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(120) NOT NULL,
    size_bytes INTEGER NOT NULL,
    blob_path VARCHAR(700) NOT NULL,
    text_blob_path VARCHAR(700),
    source_sha256 VARCHAR(64),
    email_message_id VARCHAR(255),
    report_period_start DATE,
    report_period_end DATE,
    match_status VARCHAR(40) NOT NULL DEFAULT 'pending',
    processing_status VARCHAR(40) NOT NULL DEFAULT 'pending',
    processing_error_code VARCHAR(80),
    processing_error_message TEXT,
    security_level VARCHAR(40) NOT NULL DEFAULT 'standard',
    metadata_json JSON,
    uploader_id VARCHAR(120) NOT NULL,
    uploader_role VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contract_access_grants (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    principal_id VARCHAR(120) NOT NULL,
    principal_type VARCHAR(40) NOT NULL DEFAULT 'user',
    role VARCHAR(40) NOT NULL,
    security_level VARCHAR(40) NOT NULL DEFAULT 'standard',
    granted_by_id VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_access_grant UNIQUE (contract_id, principal_id, role)
);

CREATE TABLE email_intake_messages (
    id VARCHAR(36) PRIMARY KEY,
    message_id VARCHAR(255) NOT NULL UNIQUE,
    mailbox VARCHAR(255),
    sender_email VARCHAR(320),
    subject VARCHAR(500),
    received_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    status VARCHAR(40) NOT NULL DEFAULT 'received',
    error_message TEXT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_match_decisions (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    matched_contract_number VARCHAR(120),
    decision_status VARCHAR(40) NOT NULL DEFAULT 'pending',
    decision_source VARCHAR(40) NOT NULL DEFAULT 'system',
    confidence FLOAT,
    rationale TEXT,
    decided_by_id VARCHAR(120),
    decided_at TIMESTAMPTZ,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_processing_jobs (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    job_type VARCHAR(80) NOT NULL DEFAULT 'document_analysis',
    status VARCHAR(40) NOT NULL DEFAULT 'queued',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    worker_id VARCHAR(120),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_code VARCHAR(80),
    error_message TEXT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE processing_runs (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    job_id VARCHAR(36) REFERENCES document_processing_jobs(id) ON DELETE SET NULL,
    run_type VARCHAR(80) NOT NULL DEFAULT 'document_analysis',
    status VARCHAR(40) NOT NULL DEFAULT 'running',
    model_name VARCHAR(160),
    prompt_version VARCHAR(80),
    raw_model_json JSON,
    result_json JSON,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    metadata_json JSON
);

CREATE TABLE processing_run_steps (
    id VARCHAR(36) PRIMARY KEY,
    processing_run_id VARCHAR(36) NOT NULL REFERENCES processing_runs(id) ON DELETE CASCADE,
    document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    step_name VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL,
    message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    metadata_json JSON
);

CREATE TABLE document_pages (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    extraction_status VARCHAR(40) NOT NULL DEFAULT 'extracted',
    source_start_offset INTEGER,
    source_end_offset INTEGER,
    extraction_warning TEXT,
    extraction_error TEXT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_page_number UNIQUE (document_upload_id, page_number)
);

CREATE TABLE document_chunks (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_classification_decisions (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    document_kind VARCHAR(80) NOT NULL,
    modification_kind VARCHAR(80),
    confidence FLOAT,
    rationale TEXT,
    classifier_name VARCHAR(120) NOT NULL DEFAULT 'deterministic_v1',
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_entities (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    page_id VARCHAR(36) REFERENCES document_pages(id) ON DELETE SET NULL,
    chunk_id VARCHAR(36) REFERENCES document_chunks(id) ON DELETE SET NULL,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    entity_type VARCHAR(80) NOT NULL,
    value TEXT NOT NULL,
    normalized_value VARCHAR(500),
    quote TEXT,
    confidence FLOAT,
    evidence_hash VARCHAR(64),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_report_facts (
    id VARCHAR(36) PRIMARY KEY,
    document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    page_id VARCHAR(36) REFERENCES document_pages(id) ON DELETE SET NULL,
    chunk_id VARCHAR(36) REFERENCES document_chunks(id) ON DELETE SET NULL,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    fact_type VARCHAR(80) NOT NULL,
    label VARCHAR(180) NOT NULL,
    value_text TEXT NOT NULL,
    value_json JSON,
    quote TEXT,
    confidence FLOAT,
    evidence_hash VARCHAR(64),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chunk_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    chunk_id VARCHAR(36) NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    embedding_model VARCHAR(120) NOT NULL,
    embedding_dimension INTEGER NOT NULL DEFAULT 1536,
    embedding VECTOR(1536) NOT NULL,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chunk_embedding_model UNIQUE (chunk_id, embedding_model)
);

CREATE TABLE performance_signals (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    chunk_id VARCHAR(36) REFERENCES document_chunks(id) ON DELETE SET NULL,
    signal_type VARCHAR(80) NOT NULL,
    label VARCHAR(160),
    summary TEXT NOT NULL,
    severity VARCHAR(40),
    confidence FLOAT,
    observed_at TIMESTAMPTZ,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contract_topics (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    topic_key VARCHAR(120) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(40) NOT NULL DEFAULT 'active',
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_topic_key UNIQUE (contract_id, topic_key)
);

CREATE TABLE topic_evidence (
    id VARCHAR(36) PRIMARY KEY,
    topic_id VARCHAR(36) NOT NULL REFERENCES contract_topics(id) ON DELETE CASCADE,
    document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    chunk_id VARCHAR(36) REFERENCES document_chunks(id) ON DELETE SET NULL,
    performance_signal_id VARCHAR(36) REFERENCES performance_signals(id) ON DELETE SET NULL,
    evidence_type VARCHAR(80) NOT NULL DEFAULT 'supporting',
    quote TEXT,
    summary TEXT,
    confidence FLOAT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE topic_links (
    id VARCHAR(36) PRIMARY KEY,
    source_topic_id VARCHAR(36) NOT NULL REFERENCES contract_topics(id) ON DELETE CASCADE,
    target_topic_id VARCHAR(36) NOT NULL REFERENCES contract_topics(id) ON DELETE CASCADE,
    link_type VARCHAR(80) NOT NULL,
    weight FLOAT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_topic_link UNIQUE (source_topic_id, target_topic_id, link_type)
);

CREATE TABLE contract_topic_revisions (
    id VARCHAR(36) PRIMARY KEY,
    topic_id VARCHAR(36) NOT NULL REFERENCES contract_topics(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(40) NOT NULL,
    change_summary TEXT,
    changed_by_id VARCHAR(120),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_topic_revision UNIQUE (topic_id, revision_number)
);

CREATE TABLE audit_events (
    id VARCHAR(36) PRIMARY KEY,
    actor_id VARCHAR(120),
    actor_role VARCHAR(40),
    event_type VARCHAR(100) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id VARCHAR(120) NOT NULL,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSON
);

CREATE TABLE contract_baselines (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) NOT NULL UNIQUE REFERENCES contracts(id) ON DELETE CASCADE,
    source_document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    current_revision_number INTEGER NOT NULL DEFAULT 0,
    confidence FLOAT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE baseline_obligations (
    id VARCHAR(36) PRIMARY KEY,
    baseline_id VARCHAR(36) NOT NULL REFERENCES contract_baselines(id) ON DELETE CASCADE,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    source_document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    chunk_id VARCHAR(36) REFERENCES document_chunks(id) ON DELETE SET NULL,
    page_id VARCHAR(36) REFERENCES document_pages(id) ON DELETE SET NULL,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    obligation_type VARCHAR(80) NOT NULL,
    title VARCHAR(220) NOT NULL,
    description TEXT NOT NULL,
    reference_text TEXT,
    confidence FLOAT,
    evidence_hash VARCHAR(64),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE baseline_revisions (
    id VARCHAR(36) PRIMARY KEY,
    baseline_id VARCHAR(36) NOT NULL REFERENCES contract_baselines(id) ON DELETE CASCADE,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    source_document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    revision_number INTEGER NOT NULL,
    change_type VARCHAR(80) NOT NULL,
    summary TEXT NOT NULL,
    created_by_id VARCHAR(120),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_baseline_revision_number UNIQUE (baseline_id, revision_number)
);

CREATE TABLE regression_findings (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    chunk_id VARCHAR(36) REFERENCES document_chunks(id) ON DELETE SET NULL,
    page_id VARCHAR(36) REFERENCES document_pages(id) ON DELETE SET NULL,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    baseline_obligation_id VARCHAR(36) REFERENCES baseline_obligations(id) ON DELETE SET NULL,
    finding_type VARCHAR(80) NOT NULL,
    title VARCHAR(220) NOT NULL,
    summary TEXT NOT NULL,
    severity VARCHAR(40) NOT NULL DEFAULT 'medium',
    status VARCHAR(40) NOT NULL DEFAULT 'open',
    confidence FLOAT,
    quote TEXT,
    evidence_hash VARCHAR(64),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contract_hypotheses (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    hypothesis_key VARCHAR(140) NOT NULL,
    title VARCHAR(240) NOT NULL,
    narrative TEXT NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'proposed',
    confidence FLOAT,
    created_by_id VARCHAR(120),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_hypothesis_key UNIQUE (contract_id, hypothesis_key)
);

CREATE TABLE investigation_runs (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    hypothesis_id VARCHAR(36) REFERENCES contract_hypotheses(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'completed',
    sources_checked JSON,
    result_summary TEXT NOT NULL,
    confidence FLOAT,
    created_by_id VARCHAR(120),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE external_source_refs (
    id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(36) REFERENCES contracts(id) ON DELETE SET NULL,
    investigation_run_id VARCHAR(36) REFERENCES investigation_runs(id) ON DELETE SET NULL,
    hypothesis_id VARCHAR(36) REFERENCES contract_hypotheses(id) ON DELETE SET NULL,
    url VARCHAR(1000) NOT NULL,
    title VARCHAR(300),
    source_domain VARCHAR(255) NOT NULL,
    source_type VARCHAR(80) NOT NULL DEFAULT 'official',
    citation_text TEXT,
    is_official BOOLEAN NOT NULL DEFAULT true,
    confidence FLOAT,
    evidence_hash VARCHAR(64),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE hypothesis_evidence (
    id VARCHAR(36) PRIMARY KEY,
    hypothesis_id VARCHAR(36) NOT NULL REFERENCES contract_hypotheses(id) ON DELETE CASCADE,
    regression_finding_id VARCHAR(36) REFERENCES regression_findings(id) ON DELETE SET NULL,
    document_upload_id VARCHAR(36) REFERENCES document_uploads(id) ON DELETE SET NULL,
    chunk_id VARCHAR(36) REFERENCES document_chunks(id) ON DELETE SET NULL,
    page_id VARCHAR(36) REFERENCES document_pages(id) ON DELETE SET NULL,
    processing_run_id VARCHAR(36) REFERENCES processing_runs(id) ON DELETE SET NULL,
    external_source_ref_id VARCHAR(36) REFERENCES external_source_refs(id) ON DELETE SET NULL,
    evidence_type VARCHAR(40) NOT NULL DEFAULT 'supporting',
    quote TEXT,
    summary TEXT NOT NULL,
    confidence FLOAT,
    evidence_hash VARCHAR(64),
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contract_similarity_links (
    id VARCHAR(36) PRIMARY KEY,
    source_contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    target_contract_id VARCHAR(36) NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    link_type VARCHAR(80) NOT NULL,
    summary TEXT NOT NULL,
    score FLOAT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_contract_similarity_link UNIQUE (source_contract_id, target_contract_id, link_type)
);

CREATE TABLE document_semantic_links (
    id VARCHAR(36) PRIMARY KEY,
    source_document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    target_document_upload_id VARCHAR(36) NOT NULL REFERENCES document_uploads(id) ON DELETE CASCADE,
    link_type VARCHAR(80) NOT NULL,
    summary TEXT NOT NULL,
    score FLOAT,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_semantic_link UNIQUE (
        source_document_upload_id,
        target_document_upload_id,
        link_type
    )
);

CREATE TABLE contractor_profiles (
    id VARCHAR(36) PRIMARY KEY,
    vendor_uei VARCHAR(32),
    vendor_name VARCHAR(300) NOT NULL,
    summary TEXT NOT NULL,
    evidence_labels JSON,
    award_count INTEGER NOT NULL DEFAULT 0,
    total_obligated FLOAT,
    unresolved_issue_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_contractor_profiles_vendor_uei UNIQUE (vendor_uei)
);

CREATE INDEX ix_contracts_agency_name ON contracts (agency_name);
CREATE INDEX ix_contracts_contract_number ON contracts (contract_number);
CREATE INDEX ix_contracts_naics_code ON contracts (naics_code);
CREATE INDEX ix_contracts_psc_code ON contracts (psc_code);
CREATE INDEX ix_contracts_security_level ON contracts (security_level);
CREATE INDEX ix_contracts_status ON contracts (status);
CREATE INDEX ix_contracts_vendor_name ON contracts (vendor_name);
CREATE INDEX ix_contracts_vendor_uei ON contracts (vendor_uei);

CREATE INDEX ix_document_uploads_contract_id ON document_uploads (contract_id);
CREATE INDEX ix_document_uploads_email_message_id ON document_uploads (email_message_id);
CREATE INDEX ix_document_uploads_match_status ON document_uploads (match_status);
CREATE INDEX ix_document_uploads_processing_status ON document_uploads (processing_status);
CREATE INDEX ix_document_uploads_security_level ON document_uploads (security_level);
CREATE INDEX ix_document_uploads_source_sha256 ON document_uploads (source_sha256);
CREATE INDEX ix_document_uploads_uploader_id ON document_uploads (uploader_id);

CREATE INDEX ix_contract_access_grants_contract_id ON contract_access_grants (contract_id);
CREATE INDEX ix_contract_access_grants_principal_id ON contract_access_grants (principal_id);
CREATE INDEX ix_contract_access_grants_role ON contract_access_grants (role);

CREATE INDEX ix_email_intake_messages_message_id ON email_intake_messages (message_id);
CREATE INDEX ix_email_intake_messages_received_at ON email_intake_messages (received_at);
CREATE INDEX ix_email_intake_messages_sender_email ON email_intake_messages (sender_email);
CREATE INDEX ix_email_intake_messages_status ON email_intake_messages (status);

CREATE INDEX ix_document_match_decisions_contract_id ON document_match_decisions (contract_id);
CREATE INDEX ix_document_match_decisions_decision_status ON document_match_decisions (decision_status);
CREATE INDEX ix_document_match_decisions_document_upload_id ON document_match_decisions (document_upload_id);
CREATE INDEX ix_document_match_decisions_matched_contract_number ON document_match_decisions (matched_contract_number);

CREATE INDEX ix_document_processing_jobs_document_upload_id ON document_processing_jobs (document_upload_id);
CREATE INDEX ix_document_processing_jobs_job_type ON document_processing_jobs (job_type);
CREATE INDEX ix_document_processing_jobs_status ON document_processing_jobs (status);

CREATE INDEX ix_processing_runs_contract_id ON processing_runs (contract_id);
CREATE INDEX ix_processing_runs_document_upload_id ON processing_runs (document_upload_id);
CREATE INDEX ix_processing_runs_job_id ON processing_runs (job_id);
CREATE INDEX ix_processing_runs_status ON processing_runs (status);

CREATE INDEX ix_processing_run_steps_document_upload_id ON processing_run_steps (document_upload_id);
CREATE INDEX ix_processing_run_steps_processing_run_id ON processing_run_steps (processing_run_id);
CREATE INDEX ix_processing_run_steps_status ON processing_run_steps (status);
CREATE INDEX ix_processing_run_steps_step_name ON processing_run_steps (step_name);

CREATE INDEX ix_document_pages_document_upload_id ON document_pages (document_upload_id);
CREATE INDEX ix_document_pages_extraction_status ON document_pages (extraction_status);
CREATE INDEX ix_document_pages_processing_run_id ON document_pages (processing_run_id);

CREATE INDEX ix_document_chunks_contract_id ON document_chunks (contract_id);
CREATE INDEX ix_document_chunks_document_upload_id ON document_chunks (document_upload_id);

CREATE INDEX ix_document_classification_decisions_document_kind ON document_classification_decisions (document_kind);
CREATE INDEX ix_document_classification_decisions_document_upload_id ON document_classification_decisions (document_upload_id);
CREATE INDEX ix_document_classification_decisions_modification_kind ON document_classification_decisions (modification_kind);
CREATE INDEX ix_document_classification_decisions_processing_run_id ON document_classification_decisions (processing_run_id);

CREATE INDEX ix_document_entities_chunk_id ON document_entities (chunk_id);
CREATE INDEX ix_document_entities_contract_id ON document_entities (contract_id);
CREATE INDEX ix_document_entities_document_upload_id ON document_entities (document_upload_id);
CREATE INDEX ix_document_entities_entity_type ON document_entities (entity_type);
CREATE INDEX ix_document_entities_evidence_hash ON document_entities (evidence_hash);
CREATE INDEX ix_document_entities_normalized_value ON document_entities (normalized_value);
CREATE INDEX ix_document_entities_page_id ON document_entities (page_id);
CREATE INDEX ix_document_entities_processing_run_id ON document_entities (processing_run_id);

CREATE INDEX ix_document_report_facts_chunk_id ON document_report_facts (chunk_id);
CREATE INDEX ix_document_report_facts_contract_id ON document_report_facts (contract_id);
CREATE INDEX ix_document_report_facts_document_upload_id ON document_report_facts (document_upload_id);
CREATE INDEX ix_document_report_facts_evidence_hash ON document_report_facts (evidence_hash);
CREATE INDEX ix_document_report_facts_fact_type ON document_report_facts (fact_type);
CREATE INDEX ix_document_report_facts_page_id ON document_report_facts (page_id);
CREATE INDEX ix_document_report_facts_processing_run_id ON document_report_facts (processing_run_id);

CREATE INDEX ix_chunk_embeddings_chunk_id ON chunk_embeddings (chunk_id);
CREATE INDEX ix_chunk_embeddings_embedding_model ON chunk_embeddings (embedding_model);
CREATE INDEX ix_chunk_embeddings_embedding_hnsw ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX ix_performance_signals_chunk_id ON performance_signals (chunk_id);
CREATE INDEX ix_performance_signals_contract_id ON performance_signals (contract_id);
CREATE INDEX ix_performance_signals_document_upload_id ON performance_signals (document_upload_id);
CREATE INDEX ix_performance_signals_severity ON performance_signals (severity);
CREATE INDEX ix_performance_signals_signal_type ON performance_signals (signal_type);

CREATE INDEX ix_contract_topics_contract_id ON contract_topics (contract_id);
CREATE INDEX ix_contract_topics_status ON contract_topics (status);

CREATE INDEX ix_topic_evidence_chunk_id ON topic_evidence (chunk_id);
CREATE INDEX ix_topic_evidence_document_upload_id ON topic_evidence (document_upload_id);
CREATE INDEX ix_topic_evidence_evidence_type ON topic_evidence (evidence_type);
CREATE INDEX ix_topic_evidence_performance_signal_id ON topic_evidence (performance_signal_id);
CREATE INDEX ix_topic_evidence_topic_id ON topic_evidence (topic_id);

CREATE INDEX ix_topic_links_link_type ON topic_links (link_type);
CREATE INDEX ix_topic_links_source_topic_id ON topic_links (source_topic_id);
CREATE INDEX ix_topic_links_target_topic_id ON topic_links (target_topic_id);

CREATE INDEX ix_contract_topic_revisions_changed_by_id ON contract_topic_revisions (changed_by_id);
CREATE INDEX ix_contract_topic_revisions_topic_id ON contract_topic_revisions (topic_id);

CREATE INDEX ix_audit_events_actor_id ON audit_events (actor_id);
CREATE INDEX ix_audit_events_contract_id ON audit_events (contract_id);
CREATE INDEX ix_audit_events_document_upload_id ON audit_events (document_upload_id);
CREATE INDEX ix_audit_events_entity_id ON audit_events (entity_id);
CREATE INDEX ix_audit_events_entity_type ON audit_events (entity_type);
CREATE INDEX ix_audit_events_event_time ON audit_events (event_time);
CREATE INDEX ix_audit_events_event_type ON audit_events (event_type);

CREATE INDEX ix_contract_baselines_contract_id ON contract_baselines (contract_id);
CREATE INDEX ix_contract_baselines_source_document_upload_id ON contract_baselines (source_document_upload_id);

CREATE INDEX ix_baseline_obligations_baseline_id ON baseline_obligations (baseline_id);
CREATE INDEX ix_baseline_obligations_chunk_id ON baseline_obligations (chunk_id);
CREATE INDEX ix_baseline_obligations_contract_id ON baseline_obligations (contract_id);
CREATE INDEX ix_baseline_obligations_evidence_hash ON baseline_obligations (evidence_hash);
CREATE INDEX ix_baseline_obligations_obligation_type ON baseline_obligations (obligation_type);
CREATE INDEX ix_baseline_obligations_page_id ON baseline_obligations (page_id);
CREATE INDEX ix_baseline_obligations_processing_run_id ON baseline_obligations (processing_run_id);
CREATE INDEX ix_baseline_obligations_source_document_upload_id ON baseline_obligations (source_document_upload_id);

CREATE INDEX ix_baseline_revisions_baseline_id ON baseline_revisions (baseline_id);
CREATE INDEX ix_baseline_revisions_change_type ON baseline_revisions (change_type);
CREATE INDEX ix_baseline_revisions_contract_id ON baseline_revisions (contract_id);
CREATE INDEX ix_baseline_revisions_processing_run_id ON baseline_revisions (processing_run_id);
CREATE INDEX ix_baseline_revisions_source_document_upload_id ON baseline_revisions (source_document_upload_id);

CREATE INDEX ix_regression_findings_baseline_obligation_id ON regression_findings (baseline_obligation_id);
CREATE INDEX ix_regression_findings_chunk_id ON regression_findings (chunk_id);
CREATE INDEX ix_regression_findings_contract_id ON regression_findings (contract_id);
CREATE INDEX ix_regression_findings_document_upload_id ON regression_findings (document_upload_id);
CREATE INDEX ix_regression_findings_evidence_hash ON regression_findings (evidence_hash);
CREATE INDEX ix_regression_findings_finding_type ON regression_findings (finding_type);
CREATE INDEX ix_regression_findings_page_id ON regression_findings (page_id);
CREATE INDEX ix_regression_findings_processing_run_id ON regression_findings (processing_run_id);
CREATE INDEX ix_regression_findings_severity ON regression_findings (severity);
CREATE INDEX ix_regression_findings_status ON regression_findings (status);

CREATE INDEX ix_contract_hypotheses_contract_id ON contract_hypotheses (contract_id);
CREATE INDEX ix_contract_hypotheses_status ON contract_hypotheses (status);

CREATE INDEX ix_investigation_runs_contract_id ON investigation_runs (contract_id);
CREATE INDEX ix_investigation_runs_hypothesis_id ON investigation_runs (hypothesis_id);
CREATE INDEX ix_investigation_runs_status ON investigation_runs (status);

CREATE INDEX ix_external_source_refs_contract_id ON external_source_refs (contract_id);
CREATE INDEX ix_external_source_refs_evidence_hash ON external_source_refs (evidence_hash);
CREATE INDEX ix_external_source_refs_hypothesis_id ON external_source_refs (hypothesis_id);
CREATE INDEX ix_external_source_refs_investigation_run_id ON external_source_refs (investigation_run_id);
CREATE INDEX ix_external_source_refs_is_official ON external_source_refs (is_official);
CREATE INDEX ix_external_source_refs_source_domain ON external_source_refs (source_domain);
CREATE INDEX ix_external_source_refs_source_type ON external_source_refs (source_type);

CREATE INDEX ix_hypothesis_evidence_chunk_id ON hypothesis_evidence (chunk_id);
CREATE INDEX ix_hypothesis_evidence_document_upload_id ON hypothesis_evidence (document_upload_id);
CREATE INDEX ix_hypothesis_evidence_evidence_hash ON hypothesis_evidence (evidence_hash);
CREATE INDEX ix_hypothesis_evidence_evidence_type ON hypothesis_evidence (evidence_type);
CREATE INDEX ix_hypothesis_evidence_external_source_ref_id ON hypothesis_evidence (external_source_ref_id);
CREATE INDEX ix_hypothesis_evidence_hypothesis_id ON hypothesis_evidence (hypothesis_id);
CREATE INDEX ix_hypothesis_evidence_page_id ON hypothesis_evidence (page_id);
CREATE INDEX ix_hypothesis_evidence_processing_run_id ON hypothesis_evidence (processing_run_id);
CREATE INDEX ix_hypothesis_evidence_regression_finding_id ON hypothesis_evidence (regression_finding_id);

CREATE INDEX ix_contract_similarity_links_link_type ON contract_similarity_links (link_type);
CREATE INDEX ix_contract_similarity_links_source_contract_id ON contract_similarity_links (source_contract_id);
CREATE INDEX ix_contract_similarity_links_target_contract_id ON contract_similarity_links (target_contract_id);

CREATE INDEX ix_document_semantic_links_link_type ON document_semantic_links (link_type);
CREATE INDEX ix_document_semantic_links_source_document_upload_id ON document_semantic_links (source_document_upload_id);
CREATE INDEX ix_document_semantic_links_target_document_upload_id ON document_semantic_links (target_document_upload_id);

CREATE INDEX ix_contractor_profiles_vendor_name ON contractor_profiles (vendor_name);
CREATE INDEX ix_contractor_profiles_vendor_uei ON contractor_profiles (vendor_uei);
