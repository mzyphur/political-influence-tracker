ALTER TABLE manual_review_decision
    DROP CONSTRAINT IF EXISTS manual_review_decision_subject_type_check;

ALTER TABLE manual_review_decision
    ADD CONSTRAINT manual_review_decision_subject_type_check
    CHECK (
        subject_type IN (
            'entity_match_candidate',
            'influence_event',
            'entity_industry_classification',
            'sector_policy_topic_link',
            'party_entity_link',
            'source_document',
            'other'
        )
    );

ALTER TABLE party_entity_link
    DROP CONSTRAINT IF EXISTS party_entity_link_review_requires_reviewer_check;

ALTER TABLE party_entity_link
    ADD CONSTRAINT party_entity_link_review_requires_reviewer_check
    CHECK (
        review_status NOT IN ('reviewed', 'rejected')
        OR (reviewer IS NOT NULL AND reviewed_at IS NOT NULL)
    ) NOT VALID;
