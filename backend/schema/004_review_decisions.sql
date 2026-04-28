-- Manual review audit trail.
-- This table records human decisions about ambiguous matches, extractions, and
-- classifications without overwriting the original machine-produced record.

CREATE TABLE IF NOT EXISTS manual_review_decision (
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

CREATE INDEX IF NOT EXISTS manual_review_decision_subject_idx
    ON manual_review_decision (subject_type, subject_id);
CREATE INDEX IF NOT EXISTS manual_review_decision_external_key_idx
    ON manual_review_decision (subject_external_key);
CREATE INDEX IF NOT EXISTS manual_review_decision_reviewed_at_idx
    ON manual_review_decision (reviewed_at);
