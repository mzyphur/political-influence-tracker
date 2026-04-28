-- Unified influence-event evidence surface.
-- This migration is intentionally duplicated in the current 001 baseline so
-- fresh databases get the full schema, while older local databases can be
-- upgraded in place.

CREATE TABLE IF NOT EXISTS influence_event (
    id BIGSERIAL PRIMARY KEY,
    external_key TEXT UNIQUE,
    event_family TEXT NOT NULL CHECK (
        event_family IN (
            'money',
            'benefit',
            'private_interest',
            'organisational_role',
            'access',
            'policy_behavior',
            'procurement',
            'grant',
            'appointment',
            'other'
        )
    ),
    event_type TEXT NOT NULL,
    event_subtype TEXT,
    source_entity_id BIGINT REFERENCES entity(id),
    source_raw_name TEXT,
    recipient_entity_id BIGINT REFERENCES entity(id),
    recipient_person_id BIGINT REFERENCES person(id),
    recipient_party_id BIGINT REFERENCES party(id),
    recipient_raw_name TEXT,
    jurisdiction_id BIGINT REFERENCES jurisdiction(id),
    money_flow_id BIGINT REFERENCES money_flow(id),
    gift_interest_id BIGINT REFERENCES gift_interest(id),
    amount NUMERIC(14, 2),
    currency TEXT NOT NULL DEFAULT 'AUD',
    amount_status TEXT NOT NULL CHECK (
        amount_status IN (
            'reported',
            'estimated',
            'not_disclosed',
            'not_applicable',
            'unknown'
        )
    ),
    event_date DATE,
    reporting_period TEXT,
    date_reported DATE,
    chamber TEXT,
    disclosure_system TEXT NOT NULL,
    disclosure_threshold TEXT,
    evidence_status TEXT NOT NULL CHECK (
        evidence_status IN (
            'official_record',
            'official_record_parsed',
            'third_party_civic',
            'journalistic',
            'academic',
            'inferred',
            'manual_reviewed'
        )
    ),
    extraction_method TEXT,
    review_status TEXT NOT NULL CHECK (
        review_status IN ('not_required', 'needs_review', 'reviewed', 'rejected')
    ),
    description TEXT NOT NULL,
    source_document_id BIGINT NOT NULL REFERENCES source_document(id),
    source_ref TEXT,
    original_text TEXT,
    missing_data_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS influence_event_family_type_idx
    ON influence_event (event_family, event_type);
CREATE INDEX IF NOT EXISTS influence_event_source_entity_idx
    ON influence_event (source_entity_id);
CREATE INDEX IF NOT EXISTS influence_event_recipient_entity_idx
    ON influence_event (recipient_entity_id);
CREATE INDEX IF NOT EXISTS influence_event_recipient_person_idx
    ON influence_event (recipient_person_id);
CREATE INDEX IF NOT EXISTS influence_event_recipient_party_idx
    ON influence_event (recipient_party_id);
CREATE INDEX IF NOT EXISTS influence_event_date_idx
    ON influence_event (event_date);
CREATE INDEX IF NOT EXISTS influence_event_amount_idx
    ON influence_event (amount);
CREATE INDEX IF NOT EXISTS influence_event_review_status_idx
    ON influence_event (review_status);

ALTER TABLE claim_evidence
    ADD COLUMN IF NOT EXISTS influence_event_id BIGINT REFERENCES influence_event(id);
