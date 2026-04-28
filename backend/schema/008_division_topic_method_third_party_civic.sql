ALTER TABLE division_topic
    DROP CONSTRAINT IF EXISTS division_topic_method_check;

ALTER TABLE division_topic
    ADD CONSTRAINT division_topic_method_check
    CHECK (method IN ('manual', 'rule_based', 'model_assisted', 'third_party_civic'));

CREATE UNIQUE INDEX IF NOT EXISTS vote_division_external_id_idx
    ON vote_division (external_id)
    WHERE external_id IS NOT NULL;
