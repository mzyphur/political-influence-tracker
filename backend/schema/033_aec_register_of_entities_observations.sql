-- AEC Register of Entities — official registration observation table.
--
-- Each row of the AEC Register at transparency.aec.gov.au/RegisterOfEntities
-- is preserved here as one observation, distinct from our app's canonical
-- `party` table. The dev's resolver C-rule explicitly says the AEC register
-- is not equivalent to our `party` table; this table is the auditable middle
-- layer that backs deterministic branch-to-canonical-party resolution.
--
-- Per dev direction (Batch C feedback): preserve every distinct observation
-- where FinancialYear / ReturnId / ReturnType / ViewName / AmmendmentNumber /
-- ReturnStatus differ. We need the provenance even if the serving model
-- selects a current/canonical observation.

CREATE TABLE IF NOT EXISTS aec_register_of_entities_observation (
    id BIGSERIAL PRIMARY KEY,
    source_document_id BIGINT NOT NULL REFERENCES source_document(id),
    observation_fingerprint TEXT NOT NULL,
    client_type TEXT NOT NULL CHECK (
        client_type IN (
            'politicalparty',
            'associatedentity',
            'significantthirdparty',
            'thirdparty'
        )
    ),
    client_identifier TEXT NOT NULL,
    client_name TEXT NOT NULL,
    view_name TEXT,
    return_id TEXT,
    financial_year TEXT,
    return_type TEXT,
    return_status TEXT,
    ammendment_number TEXT, -- AEC's spelling preserved verbatim
    is_non_registered_branch TEXT,
    associated_parties_raw TEXT,
    associated_party_segments JSONB NOT NULL DEFAULT '[]'::jsonb,
    show_in_political_party_register TEXT,
    show_in_associated_entity_register TEXT,
    show_in_significant_third_party_register TEXT,
    show_in_third_party_register TEXT,
    registered_as_associated_entity TEXT,
    registered_as_significant_third_party TEXT,
    register_of_political_parties_label TEXT,
    link_to_register_of_political_parties TEXT,
    -- Resolver outputs populated by the loader; null until resolution attempt.
    resolved_canonical_party_id BIGINT REFERENCES party(id),
    resolver_status TEXT NOT NULL DEFAULT 'unresolved' CHECK (
        resolver_status IN (
            'unresolved',
            'resolved_exact',
            'resolved_branch',
            'resolved_alias',
            'unresolved_no_match',
            'unresolved_multiple_matches',
            'unresolved_individual_segment',
            'not_applicable'
        )
    ),
    resolver_notes JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at TIMESTAMPTZ NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    raw_row JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (client_type, observation_fingerprint)
);

CREATE INDEX IF NOT EXISTS aec_register_of_entities_observation_client_type_idx
    ON aec_register_of_entities_observation (client_type);
CREATE INDEX IF NOT EXISTS aec_register_of_entities_observation_client_identifier_idx
    ON aec_register_of_entities_observation (client_type, client_identifier);
CREATE INDEX IF NOT EXISTS aec_register_of_entities_observation_resolver_status_idx
    ON aec_register_of_entities_observation (resolver_status);
CREATE INDEX IF NOT EXISTS aec_register_of_entities_observation_canonical_party_idx
    ON aec_register_of_entities_observation (resolved_canonical_party_id);
