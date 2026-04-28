CREATE TABLE IF NOT EXISTS sector_policy_topic_link (
    id BIGSERIAL PRIMARY KEY,
    public_sector TEXT NOT NULL,
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
    confidence NUMERIC(4, 3) CHECK (confidence >= 0 AND confidence <= 1),
    evidence_note TEXT,
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (public_sector, topic_id, relationship, method)
);

CREATE INDEX IF NOT EXISTS sector_policy_topic_link_sector_idx
    ON sector_policy_topic_link (public_sector);
CREATE INDEX IF NOT EXISTS sector_policy_topic_link_topic_idx
    ON sector_policy_topic_link (topic_id);

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
    sum(ie.amount) FILTER (WHERE ie.amount_status = 'reported') AS reported_amount_total,
    min(ie.event_date) AS first_event_date,
    max(ie.event_date) AS last_event_date,
    jsonb_build_object(
        'sector_method', min(best_entity_sector.method),
        'view_caveat',
        'Summarizes disclosed influence events by source-entity sector; sector labels may be inferred unless backed by official or manual review evidence.'
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
    sector.influence_event_count,
    sector.money_event_count,
    sector.benefit_event_count,
    sector.private_interest_event_count,
    sector.organisational_role_event_count,
    sector.reported_amount_total,
    sector.first_event_date,
    sector.last_event_date,
    votes.division_vote_count,
    votes.aye_count,
    votes.no_count,
    votes.absent_count,
    votes.other_vote_count,
    votes.rebel_count,
    votes.first_division_date,
    votes.last_division_date,
    jsonb_build_object(
        'view_caveat',
        'Context view only. Rows require an explicit sector_policy_topic_link and do not assert causation, quid pro quo, or improper conduct.'
    ) AS metadata
FROM person_policy_vote_summary votes
JOIN sector_policy_topic_link link ON link.topic_id = votes.topic_id
JOIN person_influence_sector_summary sector
    ON sector.person_id = votes.person_id
   AND sector.public_sector = link.public_sector;
