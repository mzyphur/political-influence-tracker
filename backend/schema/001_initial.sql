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

CREATE TABLE schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
CREATE INDEX person_display_name_trgm_idx ON person USING gin (display_name gin_trgm_ops);

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
CREATE INDEX electorate_name_trgm_idx ON electorate USING gin (name gin_trgm_ops);
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
CREATE UNIQUE INDEX electorate_boundary_unique_idx
    ON electorate_boundary (electorate_id, boundary_set);

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

CREATE TABLE official_identifier_observation (
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

CREATE INDEX official_identifier_observation_name_idx
    ON official_identifier_observation (normalized_name);
CREATE INDEX official_identifier_observation_source_idx
    ON official_identifier_observation (source_id, source_record_type);

CREATE TABLE entity_match_candidate (
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

CREATE INDEX entity_industry_public_sector_trgm_idx
    ON entity_industry_classification USING gin (public_sector gin_trgm_ops);

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

CREATE TABLE influence_event (
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

CREATE INDEX influence_event_family_type_idx ON influence_event (event_family, event_type);
CREATE INDEX influence_event_source_entity_idx ON influence_event (source_entity_id);
CREATE INDEX influence_event_recipient_person_idx ON influence_event (recipient_person_id);
CREATE INDEX influence_event_recipient_party_idx ON influence_event (recipient_party_id);
CREATE INDEX influence_event_date_idx ON influence_event (event_date);
CREATE INDEX influence_event_amount_idx ON influence_event (amount);
CREATE INDEX influence_event_review_status_idx ON influence_event (review_status);

CREATE TABLE manual_review_decision (
    id BIGSERIAL PRIMARY KEY,
    decision_key TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (
        subject_type IN (
            'entity_match_candidate',
            'influence_event',
            'entity_industry_classification',
            'sector_policy_topic_link',
            'source_document',
            'other'
        )
    ),
    subject_id BIGINT,
    subject_external_key TEXT,
    decision TEXT NOT NULL CHECK (
        decision IN (
            'accept',
            'reject',
            'revise',
            'needs_more_evidence',
            'defer'
        )
    ),
    reviewer TEXT NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence_note TEXT NOT NULL,
    proposed_changes JSONB NOT NULL DEFAULT '{}'::jsonb,
    supporting_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (subject_id IS NOT NULL OR subject_external_key IS NOT NULL)
);

CREATE INDEX manual_review_decision_subject_idx
    ON manual_review_decision (subject_type, subject_id);
CREATE INDEX manual_review_decision_external_key_idx
    ON manual_review_decision (subject_external_key);
CREATE INDEX manual_review_decision_reviewed_at_idx
    ON manual_review_decision (reviewed_at);

CREATE TABLE official_parliamentary_decision_record (
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

CREATE INDEX official_decision_record_source_date_idx
    ON official_parliamentary_decision_record (source_id, record_date);
CREATE INDEX official_decision_record_chamber_date_idx
    ON official_parliamentary_decision_record (chamber, record_date);
CREATE INDEX official_decision_record_url_idx
    ON official_parliamentary_decision_record (url);

CREATE TABLE official_parliamentary_decision_record_document (
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

CREATE INDEX official_decision_record_document_record_idx
    ON official_parliamentary_decision_record_document (decision_record_id);
CREATE INDEX official_decision_record_document_source_idx
    ON official_parliamentary_decision_record_document (source_document_id);
CREATE INDEX official_decision_record_document_url_idx
    ON official_parliamentary_decision_record_document (representation_url);

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

CREATE UNIQUE INDEX vote_division_external_id_idx
    ON vote_division (external_id)
    WHERE external_id IS NOT NULL;

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

CREATE INDEX policy_topic_label_trgm_idx ON policy_topic USING gin (label gin_trgm_ops);
CREATE INDEX policy_topic_slug_trgm_idx ON policy_topic USING gin (slug gin_trgm_ops);

CREATE TABLE division_topic (
    id BIGSERIAL PRIMARY KEY,
    division_id BIGINT NOT NULL REFERENCES vote_division(id),
    topic_id BIGINT NOT NULL REFERENCES policy_topic(id),
    method TEXT NOT NULL CHECK (method IN ('manual', 'rule_based', 'model_assisted', 'third_party_civic')),
    confidence NUMERIC(4, 3) CHECK (confidence >= 0 AND confidence <= 1),
    evidence_note TEXT,
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    UNIQUE (division_id, topic_id)
);

CREATE TABLE sector_policy_topic_link (
    id BIGSERIAL PRIMARY KEY,
    public_sector TEXT NOT NULL CHECK (length(btrim(public_sector)) > 0),
    topic_id BIGINT NOT NULL REFERENCES policy_topic(id),
    relationship TEXT NOT NULL CHECK (
        relationship IN (
            'direct_material_interest',
            'indirect_material_interest',
            'general_interest',
            'uncertain'
        )
    ),
    method TEXT NOT NULL CHECK (method IN ('manual', 'rule_based', 'model_assisted', 'third_party_civic')),
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_note TEXT NOT NULL CHECK (length(btrim(evidence_note)) > 0),
    review_status TEXT NOT NULL DEFAULT 'needs_review' CHECK (
        review_status IN ('needs_review', 'reviewed', 'rejected')
    ),
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (
        review_status <> 'reviewed'
        OR (
            reviewer IS NOT NULL
            AND length(btrim(reviewer)) > 0
            AND reviewed_at IS NOT NULL
        )
    ),
    UNIQUE (public_sector, topic_id, relationship, method)
);

CREATE INDEX sector_policy_topic_link_sector_idx
    ON sector_policy_topic_link (public_sector);
CREATE INDEX sector_policy_topic_link_topic_idx
    ON sector_policy_topic_link (topic_id);

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
    influence_event_id BIGINT REFERENCES influence_event(id),
    division_id BIGINT REFERENCES vote_division(id),
    person_vote_id BIGINT REFERENCES person_vote(id),
    evidence_note TEXT
);

CREATE OR REPLACE VIEW person_policy_vote_summary AS
SELECT
    pv.person_id,
    p.display_name AS person_name,
    vd.chamber,
    dt.topic_id,
    pt.slug AS topic_slug,
    pt.label AS topic_label,
    count(*) AS division_vote_count,
    count(*) FILTER (WHERE pv.vote IN ('aye', 'tell_aye')) AS aye_count,
    count(*) FILTER (WHERE pv.vote IN ('no', 'tell_no')) AS no_count,
    count(*) FILTER (WHERE pv.vote = 'absent') AS absent_count,
    count(*) FILTER (WHERE pv.vote NOT IN ('aye', 'tell_aye', 'no', 'tell_no', 'absent')) AS other_vote_count,
    count(*) FILTER (WHERE pv.rebelled_against_party IS TRUE) AS rebel_count,
    min(vd.division_date) AS first_division_date,
    max(vd.division_date) AS last_division_date,
    'recorded_divisions_linked_to_topics'::TEXT AS summary_scope,
    jsonb_build_object(
        'view_caveat',
        'Summarizes recorded divisions linked to policy topics; voice votes, party-room decisions, and unlinked divisions are outside this view.'
    ) AS metadata
FROM person_vote pv
JOIN person p ON p.id = pv.person_id
JOIN vote_division vd ON vd.id = pv.division_id
JOIN division_topic dt ON dt.division_id = vd.id
JOIN policy_topic pt ON pt.id = dt.topic_id
GROUP BY pv.person_id, p.display_name, vd.chamber, dt.topic_id, pt.slug, pt.label;

CREATE OR REPLACE VIEW person_influence_sector_summary AS
WITH best_entity_sector AS (
    SELECT DISTINCT ON (eic.entity_id)
        eic.entity_id,
        eic.public_sector,
        eic.method,
        eic.confidence
    FROM entity_industry_classification eic
    ORDER BY
        eic.entity_id,
        CASE eic.method
            WHEN 'official' THEN 1
            WHEN 'manual' THEN 2
            WHEN 'rule_based' THEN 3
            WHEN 'model_assisted' THEN 4
            ELSE 5
        END,
        CASE eic.confidence
            WHEN 'exact_identifier' THEN 1
            WHEN 'manual_reviewed' THEN 2
            WHEN 'exact_name_context' THEN 3
            WHEN 'fuzzy_high' THEN 4
            WHEN 'fuzzy_low' THEN 5
            ELSE 6
        END
)
SELECT
    ie.recipient_person_id AS person_id,
    p.display_name AS person_name,
    COALESCE(best_entity_sector.public_sector, 'unknown') AS public_sector,
    count(*) AS influence_event_count,
    count(*) FILTER (WHERE ie.event_family = 'money') AS money_event_count,
    count(*) FILTER (WHERE ie.event_family = 'benefit') AS benefit_event_count,
    count(*) FILTER (WHERE ie.event_family = 'private_interest') AS private_interest_event_count,
    count(*) FILTER (WHERE ie.event_family = 'organisational_role') AS organisational_role_event_count,
    count(*) FILTER (WHERE ie.amount_status = 'reported') AS reported_amount_event_count,
    count(*) FILTER (WHERE ie.amount_status = 'not_disclosed') AS not_disclosed_amount_event_count,
    count(*) FILTER (WHERE ie.review_status = 'needs_review') AS needs_review_event_count,
    count(*) FILTER (WHERE jsonb_array_length(ie.missing_data_flags) > 0) AS missing_data_event_count,
    count(DISTINCT ie.source_document_id) AS source_document_count,
    count(*) FILTER (WHERE ie.evidence_status IN ('official_record', 'official_record_parsed')) AS official_record_event_count,
    count(*) FILTER (WHERE ie.evidence_status = 'third_party_civic') AS third_party_civic_event_count,
    count(*) FILTER (WHERE best_entity_sector.method = 'official') AS official_sector_event_count,
    count(*) FILTER (WHERE best_entity_sector.method = 'manual') AS manual_sector_event_count,
    count(*) FILTER (
        WHERE best_entity_sector.method IS NULL
           OR best_entity_sector.method NOT IN ('official', 'manual')
    ) AS inferred_or_unknown_sector_event_count,
    sum(ie.amount) FILTER (WHERE ie.amount_status = 'reported') AS reported_amount_total,
    min(ie.event_date) AS first_event_date,
    max(ie.event_date) AS last_event_date,
    'lifetime_disclosed_influence_events'::TEXT AS summary_scope,
    jsonb_build_object(
        'sector_method_counts',
        jsonb_build_object(
            'official', count(*) FILTER (WHERE best_entity_sector.method = 'official'),
            'manual', count(*) FILTER (WHERE best_entity_sector.method = 'manual'),
            'inferred_or_unknown', count(*) FILTER (
                WHERE best_entity_sector.method IS NULL
                   OR best_entity_sector.method NOT IN ('official', 'manual')
            )
        ),
        'view_caveat',
        'Lifetime summary of disclosed influence events by source-entity sector; sector labels may be inferred unless backed by official or manual review evidence.'
    ) AS metadata
FROM influence_event ie
JOIN person p ON p.id = ie.recipient_person_id
LEFT JOIN best_entity_sector ON best_entity_sector.entity_id = ie.source_entity_id
WHERE ie.recipient_person_id IS NOT NULL
  AND ie.review_status <> 'rejected'
GROUP BY ie.recipient_person_id, p.display_name, COALESCE(best_entity_sector.public_sector, 'unknown');

CREATE OR REPLACE VIEW person_policy_influence_context AS
SELECT
    votes.person_id,
    votes.person_name,
    votes.chamber,
    votes.topic_id,
    votes.topic_slug,
    votes.topic_label,
    sector.public_sector,
    link.relationship,
    link.method AS sector_topic_link_method,
    link.confidence AS sector_topic_link_confidence,
    link.review_status AS sector_topic_link_review_status,
    link.reviewer AS sector_topic_link_reviewer,
    link.reviewed_at AS sector_topic_link_reviewed_at,
    link.evidence_note AS sector_topic_link_evidence_note,
    votes.division_vote_count,
    votes.aye_count,
    votes.no_count,
    votes.absent_count,
    votes.other_vote_count,
    votes.rebel_count,
    votes.first_division_date,
    votes.last_division_date,
    count(ie.id) AS lifetime_influence_event_count,
    count(ie.id) FILTER (WHERE ie.event_date < votes.first_division_date) AS influence_events_before_first_vote,
    count(ie.id) FILTER (
        WHERE ie.event_date >= votes.first_division_date
          AND ie.event_date <= votes.last_division_date
    ) AS influence_events_during_vote_span,
    count(ie.id) FILTER (WHERE ie.event_date > votes.last_division_date) AS influence_events_after_last_vote,
    count(ie.id) FILTER (WHERE ie.event_date IS NULL) AS influence_events_unknown_timing,
    count(ie.id) FILTER (WHERE ie.event_family = 'money') AS lifetime_money_event_count,
    count(ie.id) FILTER (WHERE ie.event_family = 'benefit') AS lifetime_benefit_event_count,
    count(ie.id) FILTER (WHERE ie.event_family = 'private_interest') AS lifetime_private_interest_event_count,
    count(ie.id) FILTER (WHERE ie.event_family = 'organisational_role') AS lifetime_organisational_role_event_count,
    sum(ie.amount) FILTER (WHERE ie.amount_status = 'reported') AS lifetime_reported_amount_total,
    sum(ie.amount) FILTER (
        WHERE ie.amount_status = 'reported'
          AND ie.event_date < votes.first_division_date
    ) AS reported_amount_before_first_vote,
    sum(ie.amount) FILTER (
        WHERE ie.amount_status = 'reported'
          AND ie.event_date >= votes.first_division_date
          AND ie.event_date <= votes.last_division_date
    ) AS reported_amount_during_vote_span,
    sum(ie.amount) FILTER (
        WHERE ie.amount_status = 'reported'
          AND ie.event_date > votes.last_division_date
    ) AS reported_amount_after_last_vote,
    count(ie.id) FILTER (WHERE ie.amount_status = 'reported') AS reported_amount_event_count,
    count(ie.id) FILTER (WHERE ie.amount_status = 'not_disclosed') AS not_disclosed_amount_event_count,
    count(ie.id) FILTER (WHERE ie.review_status = 'needs_review') AS needs_review_event_count,
    count(ie.id) FILTER (WHERE jsonb_array_length(ie.missing_data_flags) > 0) AS missing_data_event_count,
    count(DISTINCT ie.source_document_id) AS source_document_count,
    count(ie.id) FILTER (WHERE ie.evidence_status IN ('official_record', 'official_record_parsed')) AS official_record_event_count,
    count(ie.id) FILTER (WHERE ie.evidence_status = 'third_party_civic') AS third_party_civic_event_count,
    min(ie.event_date) AS first_influence_event_date,
    max(ie.event_date) AS last_influence_event_date,
    'reviewed_sector_topic_context_with_temporal_buckets'::TEXT AS context_scope,
    jsonb_build_object(
        'view_caveat',
        'Context view only. Rows require a reviewed sector_policy_topic_link and do not assert causation, quid pro quo, or improper conduct. Influence timing is bucketed relative to the linked topic vote span.'
    ) AS metadata
FROM person_policy_vote_summary votes
JOIN sector_policy_topic_link link ON link.topic_id = votes.topic_id
JOIN person_influence_sector_summary sector
  ON sector.person_id = votes.person_id
 AND sector.public_sector = link.public_sector
JOIN influence_event ie
  ON ie.recipient_person_id = votes.person_id
LEFT JOIN (
    SELECT DISTINCT ON (eic.entity_id)
        eic.entity_id,
        eic.public_sector,
        eic.method,
        eic.confidence
    FROM entity_industry_classification eic
    ORDER BY
        eic.entity_id,
        CASE eic.method
            WHEN 'official' THEN 1
            WHEN 'manual' THEN 2
            WHEN 'rule_based' THEN 3
            WHEN 'model_assisted' THEN 4
            ELSE 5
        END,
        CASE eic.confidence
            WHEN 'exact_identifier' THEN 1
            WHEN 'manual_reviewed' THEN 2
            WHEN 'exact_name_context' THEN 3
            WHEN 'fuzzy_high' THEN 4
            WHEN 'fuzzy_low' THEN 5
            ELSE 6
        END
) best_entity_sector
  ON best_entity_sector.entity_id = ie.source_entity_id
WHERE link.review_status = 'reviewed'
  AND ie.review_status <> 'rejected'
  AND COALESCE(best_entity_sector.public_sector, 'unknown') = link.public_sector
GROUP BY
    votes.person_id,
    votes.person_name,
    votes.chamber,
    votes.topic_id,
    votes.topic_slug,
    votes.topic_label,
    sector.public_sector,
    link.relationship,
    link.method,
    link.confidence,
    link.review_status,
    link.reviewer,
    link.reviewed_at,
    link.evidence_note,
    votes.division_vote_count,
    votes.aye_count,
    votes.no_count,
    votes.absent_count,
    votes.other_vote_count,
    votes.rebel_count,
    votes.first_division_date,
    votes.last_division_date;
