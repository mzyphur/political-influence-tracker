-- Official identifier enrichment evidence tables.
-- This migration is intentionally duplicated in the current 001 baseline so
-- fresh databases get the full schema, while databases created before the
-- identifier-enrichment increment can be upgraded in place.

CREATE TABLE IF NOT EXISTS official_identifier_observation (
    id BIGSERIAL PRIMARY KEY,
    stable_key TEXT NOT NULL UNIQUE,
    source_document_id BIGINT REFERENCES source_document(id),
    source_id TEXT NOT NULL,
    source_record_type TEXT NOT NULL,
    external_id TEXT,
    display_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'unknown',
    public_sector TEXT NOT NULL DEFAULT 'unknown',
    confidence TEXT NOT NULL CHECK (
        confidence IN (
            'exact_identifier',
            'exact_name_context',
            'fuzzy_high',
            'fuzzy_low',
            'manual_reviewed',
            'unresolved'
        )
    ),
    status TEXT,
    source_updated_at TIMESTAMPTZ,
    evidence_note TEXT,
    identifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_record JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS official_identifier_observation_name_idx
    ON official_identifier_observation (normalized_name);
CREATE INDEX IF NOT EXISTS official_identifier_observation_source_idx
    ON official_identifier_observation (source_id, source_record_type);

CREATE TABLE IF NOT EXISTS entity_match_candidate (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entity(id),
    observation_id BIGINT NOT NULL REFERENCES official_identifier_observation(id),
    match_method TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (
        confidence IN (
            'exact_identifier',
            'exact_name_context',
            'fuzzy_high',
            'fuzzy_low',
            'manual_reviewed',
            'unresolved'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN ('auto_accepted', 'needs_review', 'manual_accepted', 'rejected')
    ),
    score NUMERIC(5, 2),
    evidence_note TEXT,
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (entity_id, observation_id, match_method)
);
