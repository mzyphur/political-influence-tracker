CREATE TABLE IF NOT EXISTS postcode_electorate_crosswalk (
    id BIGSERIAL PRIMARY KEY,
    postcode TEXT NOT NULL CHECK (postcode ~ '^[0-9]{4}$'),
    electorate_id BIGINT NOT NULL REFERENCES electorate(id),
    state_or_territory TEXT,
    match_method TEXT NOT NULL,
    confidence NUMERIC(6, 4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    locality_count INTEGER NOT NULL DEFAULT 0,
    localities JSONB NOT NULL DEFAULT '[]'::jsonb,
    redistributed_electorates JSONB NOT NULL DEFAULT '[]'::jsonb,
    other_localities JSONB NOT NULL DEFAULT '[]'::jsonb,
    aec_division_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_document_id BIGINT REFERENCES source_document(id),
    source_updated_text TEXT,
    source_boundary_context TEXT NOT NULL DEFAULT 'next_federal_election_electorates',
    current_member_context TEXT NOT NULL DEFAULT 'previous_election_or_subsequent_by_election_member',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (postcode, electorate_id, match_method)
);

CREATE INDEX IF NOT EXISTS postcode_electorate_crosswalk_postcode_idx
    ON postcode_electorate_crosswalk (postcode);

CREATE INDEX IF NOT EXISTS postcode_electorate_crosswalk_electorate_idx
    ON postcode_electorate_crosswalk (electorate_id);

CREATE INDEX IF NOT EXISTS postcode_electorate_crosswalk_source_document_idx
    ON postcode_electorate_crosswalk (source_document_id);
