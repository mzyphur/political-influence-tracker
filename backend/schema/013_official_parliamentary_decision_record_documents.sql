CREATE TABLE IF NOT EXISTS official_parliamentary_decision_record_document (
    id BIGSERIAL PRIMARY KEY,
    decision_record_id BIGINT NOT NULL REFERENCES official_parliamentary_decision_record(id),
    source_document_id BIGINT NOT NULL REFERENCES source_document(id),
    representation_url TEXT NOT NULL,
    representation_kind TEXT NOT NULL,
    fetched_at TIMESTAMPTZ,
    sha256 TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (decision_record_id, representation_url, source_document_id)
);

CREATE INDEX IF NOT EXISTS official_decision_record_document_record_idx
    ON official_parliamentary_decision_record_document (decision_record_id);
CREATE INDEX IF NOT EXISTS official_decision_record_document_source_idx
    ON official_parliamentary_decision_record_document (source_document_id);
CREATE INDEX IF NOT EXISTS official_decision_record_document_url_idx
    ON official_parliamentary_decision_record_document (representation_url);
