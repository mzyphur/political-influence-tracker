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
            'source_document',
            'other'
        )
    );
