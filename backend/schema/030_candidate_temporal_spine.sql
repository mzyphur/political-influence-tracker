CREATE TABLE IF NOT EXISTS candidate_contest (
    id BIGSERIAL PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    source_document_id BIGINT NOT NULL REFERENCES source_document(id),
    jurisdiction_id BIGINT REFERENCES jurisdiction(id),
    election_name TEXT,
    election_date DATE,
    election_year INTEGER,
    chamber TEXT,
    contest_type TEXT NOT NULL,
    candidate_name TEXT NOT NULL,
    normalized_candidate_name TEXT NOT NULL,
    electorate_name TEXT,
    normalized_electorate_name TEXT,
    state_or_territory TEXT,
    party_name TEXT,
    normalized_party_name TEXT,
    return_type TEXT,
    person_id BIGINT REFERENCES person(id),
    office_term_id BIGINT REFERENCES office_term(id),
    match_status TEXT NOT NULL CHECK (
        match_status IN (
            'linked_temporal',
            'name_context_only',
            'unmatched_or_ambiguous'
        )
    ),
    match_method TEXT NOT NULL,
    confidence TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE money_flow
ADD COLUMN IF NOT EXISTS candidate_contest_id BIGINT REFERENCES candidate_contest(id);

ALTER TABLE money_flow
ADD COLUMN IF NOT EXISTS office_term_id BIGINT REFERENCES office_term(id);

ALTER TABLE influence_event
ADD COLUMN IF NOT EXISTS candidate_contest_id BIGINT REFERENCES candidate_contest(id);

ALTER TABLE influence_event
ADD COLUMN IF NOT EXISTS office_term_id BIGINT REFERENCES office_term(id);

ALTER TABLE person_vote
ADD COLUMN IF NOT EXISTS office_term_id BIGINT REFERENCES office_term(id);

CREATE INDEX IF NOT EXISTS candidate_contest_name_electorate_idx
    ON candidate_contest (
        normalized_candidate_name,
        normalized_electorate_name,
        state_or_territory
    );
CREATE INDEX IF NOT EXISTS candidate_contest_person_idx
    ON candidate_contest (person_id, match_status);
CREATE INDEX IF NOT EXISTS candidate_contest_office_term_idx
    ON candidate_contest (office_term_id);
CREATE INDEX IF NOT EXISTS candidate_contest_source_document_idx
    ON candidate_contest (source_document_id);
CREATE INDEX IF NOT EXISTS money_flow_candidate_contest_idx
    ON money_flow (candidate_contest_id);
CREATE INDEX IF NOT EXISTS money_flow_office_term_idx
    ON money_flow (office_term_id);
CREATE INDEX IF NOT EXISTS influence_event_candidate_contest_idx
    ON influence_event (candidate_contest_id);
CREATE INDEX IF NOT EXISTS influence_event_office_term_idx
    ON influence_event (office_term_id);
CREATE INDEX IF NOT EXISTS person_vote_office_term_idx
    ON person_vote (office_term_id);
