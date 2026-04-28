ALTER TABLE sector_policy_topic_link
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'needs_review';

ALTER TABLE sector_policy_topic_link
    ALTER COLUMN confidence SET NOT NULL,
    ALTER COLUMN evidence_note SET NOT NULL;

ALTER TABLE sector_policy_topic_link
    DROP CONSTRAINT IF EXISTS sector_policy_topic_link_public_sector_nonempty,
    ADD CONSTRAINT sector_policy_topic_link_public_sector_nonempty
    CHECK (length(btrim(public_sector)) > 0);

ALTER TABLE sector_policy_topic_link
    DROP CONSTRAINT IF EXISTS sector_policy_topic_link_evidence_note_nonempty,
    ADD CONSTRAINT sector_policy_topic_link_evidence_note_nonempty
    CHECK (length(btrim(evidence_note)) > 0);

ALTER TABLE sector_policy_topic_link
    DROP CONSTRAINT IF EXISTS sector_policy_topic_link_review_status_check,
    ADD CONSTRAINT sector_policy_topic_link_review_status_check
    CHECK (review_status IN ('needs_review', 'reviewed', 'rejected'));

ALTER TABLE sector_policy_topic_link
    DROP CONSTRAINT IF EXISTS sector_policy_topic_link_reviewed_requires_reviewer,
    ADD CONSTRAINT sector_policy_topic_link_reviewed_requires_reviewer
    CHECK (
        review_status <> 'reviewed'
        OR (
            reviewer IS NOT NULL
            AND length(btrim(reviewer)) > 0
            AND reviewed_at IS NOT NULL
        )
    );

DROP VIEW IF EXISTS person_policy_influence_context;
DROP VIEW IF EXISTS person_influence_sector_summary;
DROP VIEW IF EXISTS person_policy_vote_summary;

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
