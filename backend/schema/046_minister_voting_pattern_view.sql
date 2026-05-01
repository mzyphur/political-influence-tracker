-- 046_minister_voting_pattern_view.sql
--
-- Stage 4c of the influence-correlation pipeline: views that
-- join voting records (vote_division + person_vote +
-- division_topic + policy_topic, all already loaded — 506
-- divisions / 37,886 votes from They Vote For You) to the
-- minister-responsibility tables introduced by migration 044.
--
-- Powers the headline question: "Did minister Z, who oversees
-- agency A and received donations from supplier X, vote in
-- favour of bills affecting X's industry?" — the canonical
-- influence-pattern question.
--
-- Three views land in this migration:
--
-- v_person_voting_summary
--   * Per (person, policy_topic) summary: total aye / no / count
--     of divisions where this MP voted on a topic-tagged division.
--   * Source data: person_vote.vote ('aye' / 'no') joined to
--     division_topic via division_id.
--   * Used by every other voting query as the building block.
--
-- v_minister_voting_pattern
--   * Per (minister, policy_topic) summary: a minister's voting
--     pattern on policy topics (e.g. "Mark Butler voted aye 5x
--     and no 0x on health-aged-care-related divisions").
--   * Joins v_person_voting_summary to the minister_role table
--     (filtered to currently-serving cabinet ministers).
--
-- v_donor_recipient_voting_alignment
--   * Per (donor entity → recipient MP → policy topic) summary:
--     how aligned was the recipient MP's voting pattern with the
--     donor's likely interests?
--   * Joins influence_event (donor → MP) to v_person_voting_summary.
--     The "interest alignment" is necessarily a SOFT signal —
--     we surface the raw votes + topic and let the consumer (UI
--     / researcher) interpret. We do NOT auto-label "alignment"
--     vs "rebellion" because that would imply causation.
--
-- Claim discipline:
--   * Voting records are tier-1 (public APH divisions; ingested
--     from They Vote For You with the policy-topic linkage they
--     publish under CC-BY).
--   * Donor-recipient links are tier-1 (AEC disclosure data).
--   * Joining them does NOT imply causation. The view structure
--     surfaces correlation + temporal coincidence; the consumer
--     decides.
--   * Topics are CC-BY from They Vote For You; the policy_topic
--     table's `method='third_party_civic'` rows in
--     division_topic carry that provenance.

CREATE OR REPLACE VIEW v_person_voting_summary AS
SELECT
    pv.person_id,
    p.canonical_name AS person_canonical_name,
    p.display_name AS person_display_name,
    dt.topic_id,
    pt.label AS policy_topic_label,
    pt.slug AS policy_topic_slug,
    COUNT(*) AS division_count,
    COUNT(*) FILTER (WHERE pv.vote = 'aye') AS aye_count,
    COUNT(*) FILTER (WHERE pv.vote = 'no') AS no_count,
    COUNT(*) FILTER (WHERE pv.rebelled_against_party) AS rebellion_count,
    MIN(vd.division_date) AS earliest_vote_date,
    MAX(vd.division_date) AS latest_vote_date,
    -- Provenance
    'rule_based_disclosure_with_third_party_topic_linkage' AS evidence_tier
FROM person_vote pv
JOIN vote_division vd ON vd.id = pv.division_id
JOIN division_topic dt ON dt.division_id = vd.id
JOIN policy_topic pt ON pt.id = dt.topic_id
JOIN person p ON p.id = pv.person_id
WHERE pv.withdrawn_at IS NULL
  AND pv.vote IN ('aye', 'no')
GROUP BY pv.person_id, p.canonical_name, p.display_name,
         dt.topic_id, pt.label, pt.slug;


CREATE OR REPLACE VIEW v_minister_voting_pattern AS
SELECT
    mr.id AS minister_role_id,
    mr.cabinet_ministry_id,
    cm.label AS cabinet_ministry_label,
    mr.person_id AS minister_person_id,
    mr.person_raw_name AS minister_name,
    mr.role_title AS minister_role_title,
    mr.portfolio_label,
    mr.role_type AS minister_role_type,
    mr.effective_from AS minister_effective_from,
    mr.effective_to AS minister_effective_to,
    pvs.topic_id,
    pvs.policy_topic_label,
    pvs.policy_topic_slug,
    pvs.division_count,
    pvs.aye_count,
    pvs.no_count,
    pvs.rebellion_count,
    pvs.earliest_vote_date,
    pvs.latest_vote_date,
    'rule_based_disclosure_with_third_party_topic_linkage' AS voting_evidence_tier,
    'rule_based_aao' AS portfolio_evidence_tier,
    'no causation implied; voting record alongside portfolio responsibility' AS claim_discipline_note
FROM minister_role mr
JOIN cabinet_ministry cm ON cm.id = mr.cabinet_ministry_id
JOIN v_person_voting_summary pvs ON pvs.person_id = mr.person_id
WHERE mr.person_id IS NOT NULL;


-- Donor → MP voting-alignment surface. For every donor-recipient
-- pair (where donor is an entity classified to a sector + the
-- recipient is an MP), surface the recipient's voting pattern on
-- topic tags relevant to the donor's industry.
--
-- This view is intentionally LIBERAL with what it surfaces — it
-- does NOT pre-filter to "topics aligned with donor industry".
-- That mapping (sector → relevant policy topics) is made by the
-- consumer or by a follow-up view. Pre-judgement here would
-- breach claim discipline.
CREATE OR REPLACE VIEW v_donor_recipient_voting_alignment AS
SELECT
    ie.source_entity_id AS donor_entity_id,
    e_donor.canonical_name AS donor_canonical_name,
    eic.public_sector AS donor_sector,
    ie.recipient_person_id AS recipient_person_id,
    p.canonical_name AS recipient_person_canonical_name,
    p.display_name AS recipient_person_display_name,
    SUM(COALESCE(ie.amount, 0)) FILTER (WHERE ie.event_family = 'money')
        AS donor_total_money_aud,
    COUNT(*) FILTER (WHERE ie.event_family = 'money')
        AS donor_money_event_count,
    pvs.topic_id,
    pvs.policy_topic_label,
    pvs.policy_topic_slug,
    SUM(pvs.division_count) AS recipient_division_count,
    SUM(pvs.aye_count) AS recipient_aye_count,
    SUM(pvs.no_count) AS recipient_no_count,
    SUM(pvs.rebellion_count) AS recipient_rebellion_count,
    'rule_based_disclosure' AS donor_evidence_tier,
    'rule_based_disclosure_with_third_party_topic_linkage' AS recipient_voting_evidence_tier,
    'no causation implied; correlation + temporal coincidence only' AS claim_discipline_note
FROM influence_event ie
JOIN entity e_donor ON e_donor.id = ie.source_entity_id
LEFT JOIN entity_industry_classification eic
    ON eic.entity_id = ie.source_entity_id
       AND eic.method IN ('official', 'rule_based', 'model_assisted')
JOIN person p ON p.id = ie.recipient_person_id
JOIN v_person_voting_summary pvs ON pvs.person_id = ie.recipient_person_id
WHERE ie.review_status != 'rejected'
  AND ie.recipient_person_id IS NOT NULL
  AND ie.source_entity_id IS NOT NULL
GROUP BY
    ie.source_entity_id, e_donor.canonical_name,
    eic.public_sector, ie.recipient_person_id,
    p.canonical_name, p.display_name,
    pvs.topic_id, pvs.policy_topic_label, pvs.policy_topic_slug;


COMMENT ON VIEW v_person_voting_summary IS
'Per-(person, policy_topic) summary of voting record. Powers all minister-voting and donor-recipient-voting analyses.';

COMMENT ON VIEW v_minister_voting_pattern IS
'Per-(minister, policy_topic) summary of voting record. Surfaces "minister Z voted aye 5x and no 0x on health-aged-care divisions".';

COMMENT ON VIEW v_donor_recipient_voting_alignment IS
'Per (donor entity, recipient MP, policy topic) tuple: surfaces the recipient MP''s voting pattern on the topic alongside the donor''s industry classification + total contributions. No causation implied; the view exposes correlation only.';
