ALTER TABLE official_parliamentary_decision_record
    ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMPTZ;

ALTER TABLE official_parliamentary_decision_record_document
    ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMPTZ;

ALTER TABLE vote_division
    ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMPTZ;

ALTER TABLE person_vote
    ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS official_decision_record_current_source_idx
    ON official_parliamentary_decision_record (source_id, is_current);

CREATE INDEX IF NOT EXISTS official_decision_record_document_current_record_idx
    ON official_parliamentary_decision_record_document (decision_record_id, is_current);

CREATE INDEX IF NOT EXISTS vote_division_current_chamber_idx
    ON vote_division (chamber, is_current);

CREATE INDEX IF NOT EXISTS person_vote_current_division_idx
    ON person_vote (division_id, is_current);

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
        'Summarizes current recorded divisions linked to policy topics; voice votes, party-room decisions, withdrawn/corrected records, and unlinked divisions are outside this view.'
    ) AS metadata
FROM person_vote pv
JOIN person p ON p.id = pv.person_id
JOIN vote_division vd ON vd.id = pv.division_id
JOIN division_topic dt ON dt.division_id = vd.id
JOIN policy_topic pt ON pt.id = dt.topic_id
WHERE pv.is_current IS TRUE
  AND vd.is_current IS TRUE
GROUP BY pv.person_id, p.display_name, vd.chamber, dt.topic_id, pt.slug, pt.label;
