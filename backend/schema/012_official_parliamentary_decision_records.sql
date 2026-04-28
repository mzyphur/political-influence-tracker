CREATE TABLE IF NOT EXISTS official_parliamentary_decision_record (
    id BIGSERIAL PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    source_document_id BIGINT REFERENCES source_document(id),
    source_id TEXT NOT NULL,
    chamber TEXT NOT NULL CHECK (chamber IN ('house', 'senate')),
    record_type TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    parliament_label TEXT,
    year_label TEXT,
    month_label TEXT,
    day_label TEXT,
    record_date DATE,
    title TEXT NOT NULL,
    link_text TEXT,
    url TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS official_decision_record_source_date_idx
    ON official_parliamentary_decision_record (source_id, record_date);
CREATE INDEX IF NOT EXISTS official_decision_record_chamber_date_idx
    ON official_parliamentary_decision_record (chamber, record_date);
CREATE INDEX IF NOT EXISTS official_decision_record_url_idx
    ON official_parliamentary_decision_record (url);
