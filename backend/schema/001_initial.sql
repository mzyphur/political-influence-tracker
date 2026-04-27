-- Initial PostgreSQL/PostGIS schema for AU Politics Money Tracker.
-- This is a draft intended to stabilize ingestion and evidence tracking.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE source_document (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    url TEXT NOT NULL,
    final_url TEXT,
    fetched_at TIMESTAMPTZ NOT NULL,
    http_status INTEGER,
    content_type TEXT,
    sha256 TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    parser_name TEXT,
    parser_version TEXT,
    parsed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_id, sha256)
);

CREATE INDEX source_document_source_idx ON source_document (source_id);
CREATE INDEX source_document_fetched_idx ON source_document (fetched_at);

CREATE TABLE ingestion_run (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'partial')),
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE jurisdiction (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    level TEXT NOT NULL CHECK (level IN ('federal', 'state', 'territory', 'local', 'national')),
    code TEXT UNIQUE
);

CREATE TABLE party (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT,
    party_group TEXT,
    jurisdiction_id BIGINT REFERENCES jurisdiction(id),
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (name, jurisdiction_id)
);

CREATE TABLE person (
    id BIGSERIAL PRIMARY KEY,
    external_key TEXT UNIQUE,
    display_name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    honorific TEXT,
    gender TEXT,
    birth_date DATE,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX person_canonical_name_trgm_idx ON person USING gin (canonical_name gin_trgm_ops);

CREATE TABLE electorate (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    jurisdiction_id BIGINT NOT NULL REFERENCES jurisdiction(id),
    chamber TEXT NOT NULL CHECK (chamber IN ('house', 'senate', 'legislative_assembly', 'legislative_council', 'council', 'other')),
    state_or_territory TEXT,
    valid_from DATE,
    valid_to DATE,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX electorate_name_idx ON electorate (name);
CREATE UNIQUE INDEX electorate_unique_current_idx ON electorate (name, jurisdiction_id, chamber);

CREATE TABLE electorate_boundary (
    id BIGSERIAL PRIMARY KEY,
    electorate_id BIGINT NOT NULL REFERENCES electorate(id),
    boundary_set TEXT NOT NULL,
    valid_from DATE,
    valid_to DATE,
    geom GEOMETRY(MultiPolygon, 4326),
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX electorate_boundary_geom_idx ON electorate_boundary USING gist (geom);

CREATE TABLE office_term (
    id BIGSERIAL PRIMARY KEY,
    external_key TEXT UNIQUE,
    person_id BIGINT NOT NULL REFERENCES person(id),
    chamber TEXT NOT NULL CHECK (chamber IN ('house', 'senate', 'state_lower', 'state_upper', 'local', 'other')),
    electorate_id BIGINT REFERENCES electorate(id),
    party_id BIGINT REFERENCES party(id),
    role_title TEXT,
    term_start DATE,
    term_end DATE,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX office_term_person_idx ON office_term (person_id);
CREATE INDEX office_term_party_idx ON office_term (party_id);

CREATE TABLE entity (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    country TEXT,
    state_or_territory TEXT,
    website TEXT,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX entity_canonical_name_trgm_idx ON entity USING gin (canonical_name gin_trgm_ops);
CREATE UNIQUE INDEX entity_normalized_type_idx ON entity (normalized_name, entity_type);
CREATE INDEX entity_type_idx ON entity (entity_type);

CREATE TABLE entity_alias (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entity(id),
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (entity_id, normalized_alias)
);

CREATE INDEX entity_alias_normalized_trgm_idx ON entity_alias USING gin (normalized_alias gin_trgm_ops);

CREATE TABLE entity_identifier (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entity(id),
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (identifier_type, identifier_value)
);

CREATE TABLE industry_code (
    id BIGSERIAL PRIMARY KEY,
    scheme TEXT NOT NULL,
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    parent_code TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (scheme, code)
);

CREATE TABLE entity_industry_classification (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT NOT NULL REFERENCES entity(id),
    industry_code_id BIGINT REFERENCES industry_code(id),
    public_sector TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('official', 'rule_based', 'model_assisted', 'manual', 'unknown')),
    confidence TEXT NOT NULL CHECK (confidence IN ('exact_identifier', 'exact_name_context', 'fuzzy_high', 'fuzzy_low', 'manual_reviewed', 'unresolved')),
    evidence_note TEXT,
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE money_flow (
    id BIGSERIAL PRIMARY KEY,
    external_key TEXT UNIQUE,
    source_entity_id BIGINT REFERENCES entity(id),
    source_raw_name TEXT NOT NULL,
    recipient_entity_id BIGINT REFERENCES entity(id),
    recipient_person_id BIGINT REFERENCES person(id),
    recipient_party_id BIGINT REFERENCES party(id),
    recipient_raw_name TEXT NOT NULL,
    amount NUMERIC(14, 2),
    currency TEXT NOT NULL DEFAULT 'AUD',
    financial_year TEXT,
    date_received DATE,
    date_reported DATE,
    return_type TEXT,
    receipt_type TEXT,
    disclosure_category TEXT,
    jurisdiction_id BIGINT REFERENCES jurisdiction(id),
    source_document_id BIGINT NOT NULL REFERENCES source_document(id),
    source_row_ref TEXT,
    original_text TEXT,
    confidence TEXT NOT NULL DEFAULT 'unresolved',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX money_flow_source_entity_idx ON money_flow (source_entity_id);
CREATE INDEX money_flow_recipient_entity_idx ON money_flow (recipient_entity_id);
CREATE INDEX money_flow_recipient_person_idx ON money_flow (recipient_person_id);
CREATE INDEX money_flow_year_idx ON money_flow (financial_year);
CREATE INDEX money_flow_amount_idx ON money_flow (amount);

CREATE TABLE gift_interest (
    id BIGSERIAL PRIMARY KEY,
    external_key TEXT UNIQUE,
    person_id BIGINT NOT NULL REFERENCES person(id),
    source_entity_id BIGINT REFERENCES entity(id),
    source_raw_name TEXT,
    interest_category TEXT NOT NULL,
    description TEXT NOT NULL,
    estimated_value NUMERIC(14, 2),
    currency TEXT NOT NULL DEFAULT 'AUD',
    date_received DATE,
    date_reported DATE,
    parliament_number TEXT,
    chamber TEXT,
    source_document_id BIGINT NOT NULL REFERENCES source_document(id),
    source_page_ref TEXT,
    original_text TEXT,
    extraction_confidence TEXT NOT NULL DEFAULT 'unresolved',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX gift_interest_person_idx ON gift_interest (person_id);
CREATE INDEX gift_interest_source_entity_idx ON gift_interest (source_entity_id);
CREATE INDEX gift_interest_category_idx ON gift_interest (interest_category);

CREATE TABLE vote_division (
    id BIGSERIAL PRIMARY KEY,
    external_id TEXT,
    chamber TEXT NOT NULL,
    division_date DATE NOT NULL,
    division_number INTEGER,
    title TEXT NOT NULL,
    bill_name TEXT,
    motion_text TEXT,
    aye_count INTEGER,
    no_count INTEGER,
    possible_turnout INTEGER,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (chamber, division_date, division_number)
);

CREATE TABLE person_vote (
    id BIGSERIAL PRIMARY KEY,
    division_id BIGINT NOT NULL REFERENCES vote_division(id),
    person_id BIGINT NOT NULL REFERENCES person(id),
    vote TEXT NOT NULL CHECK (vote IN ('aye', 'no', 'abstain', 'absent', 'paired', 'tell_aye', 'tell_no', 'unknown')),
    party_id BIGINT REFERENCES party(id),
    rebelled_against_party BOOLEAN,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (division_id, person_id)
);

CREATE TABLE policy_topic (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    description TEXT,
    parent_topic_id BIGINT REFERENCES policy_topic(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE division_topic (
    id BIGSERIAL PRIMARY KEY,
    division_id BIGINT NOT NULL REFERENCES vote_division(id),
    topic_id BIGINT NOT NULL REFERENCES policy_topic(id),
    method TEXT NOT NULL CHECK (method IN ('manual', 'rule_based', 'model_assisted')),
    confidence NUMERIC(4, 3) CHECK (confidence >= 0 AND confidence <= 1),
    evidence_note TEXT,
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    UNIQUE (division_id, topic_id)
);

CREATE TABLE evidence_claim (
    id BIGSERIAL PRIMARY KEY,
    claim_text TEXT NOT NULL,
    claim_level INTEGER NOT NULL CHECK (claim_level BETWEEN 1 AND 6),
    evidence_class TEXT NOT NULL,
    subject_person_id BIGINT REFERENCES person(id),
    subject_entity_id BIGINT REFERENCES entity(id),
    subject_party_id BIGINT REFERENCES party(id),
    status TEXT NOT NULL CHECK (status IN ('draft', 'reviewed', 'published', 'retracted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    reviewer TEXT,
    caveat TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE claim_evidence (
    id BIGSERIAL PRIMARY KEY,
    claim_id BIGINT NOT NULL REFERENCES evidence_claim(id),
    source_document_id BIGINT REFERENCES source_document(id),
    money_flow_id BIGINT REFERENCES money_flow(id),
    gift_interest_id BIGINT REFERENCES gift_interest(id),
    division_id BIGINT REFERENCES vote_division(id),
    person_vote_id BIGINT REFERENCES person_vote(id),
    evidence_note TEXT
);
