CREATE TABLE IF NOT EXISTS party_entity_link (
    id BIGSERIAL PRIMARY KEY,
    party_id BIGINT NOT NULL REFERENCES party(id),
    entity_id BIGINT NOT NULL REFERENCES entity(id),
    link_type TEXT NOT NULL CHECK (
        link_type IN (
            'exact_party_entity',
            'party_branch',
            'associated_entity',
            'party_campaigner',
            'other'
        )
    ),
    method TEXT NOT NULL CHECK (
        method IN ('official', 'manual', 'rule_based', 'model_assisted')
    ),
    confidence TEXT NOT NULL DEFAULT 'unreviewed_candidate',
    review_status TEXT NOT NULL DEFAULT 'needs_review' CHECK (
        review_status IN ('not_required', 'needs_review', 'reviewed', 'rejected')
    ),
    evidence_note TEXT,
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (party_id, entity_id, link_type)
);

CREATE INDEX IF NOT EXISTS party_entity_link_party_idx
    ON party_entity_link (party_id, review_status);

CREATE INDEX IF NOT EXISTS party_entity_link_entity_idx
    ON party_entity_link (entity_id, review_status);
