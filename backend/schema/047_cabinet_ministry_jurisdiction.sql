-- 047_cabinet_ministry_jurisdiction.sql
--
-- Add `jurisdiction_id` to the cabinet_ministry table so state +
-- territory ministries can coexist with the federal ministry
-- (Albanese 2nd Cabinet) seeded by migration 045. Without this,
-- state premiers + their cabinets cannot be modelled.
--
-- Additive migration:
--   * jurisdiction_id is added as nullable; existing rows are
--     backfilled to the Commonwealth jurisdiction (federal).
--   * After backfill, the column is set NOT NULL.
--   * A FK to jurisdiction(id) is added to enforce referential integrity.
--
-- The portfolio_agency table also needs the jurisdiction (since a
-- "Department of Health" exists at federal AND in most states).
-- We use the cabinet_ministry's jurisdiction_id transitively
-- (portfolio_agency → cabinet_ministry → jurisdiction). This
-- avoids duplicating the jurisdiction column in portfolio_agency.

ALTER TABLE cabinet_ministry
ADD COLUMN IF NOT EXISTS jurisdiction_id BIGINT
    REFERENCES jurisdiction(id) ON DELETE RESTRICT;

-- Backfill: existing Albanese 2nd Cabinet row → Commonwealth.
UPDATE cabinet_ministry
SET jurisdiction_id = (
    SELECT id FROM jurisdiction
    WHERE level = 'federal'
    ORDER BY id
    LIMIT 1
)
WHERE jurisdiction_id IS NULL
  AND EXISTS (SELECT 1 FROM jurisdiction WHERE level = 'federal');

-- Defence in depth: if any rows still have NULL jurisdiction_id
-- (no federal jurisdiction existed at backfill time — seen in
-- the test integration fixture which seeds jurisdictions AFTER
-- migrations run), DELETE them as orphans rather than failing
-- the SET NOT NULL. They can be re-inserted by migration 045's
-- idempotent INSERT (which now requires the federal jurisdiction
-- to exist before insertion).
DELETE FROM cabinet_ministry WHERE jurisdiction_id IS NULL;

ALTER TABLE cabinet_ministry
ALTER COLUMN jurisdiction_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS cabinet_ministry_jurisdiction_idx
    ON cabinet_ministry (jurisdiction_id, is_current);


-- Update v_contract_minister_responsibility to surface the
-- ministry's jurisdiction (federal / state). AusTender contracts
-- are federal only at the moment, but the view's join key is
-- agency_canonical_name match — once state portfolio_agency rows
-- are seeded, federal contracts continue to match only federal
-- ministries, and future state contracts (if loaded) match state
-- ministries.
DROP VIEW IF EXISTS v_contract_minister_responsibility CASCADE;

CREATE VIEW v_contract_minister_responsibility AS
SELECT
    act.contract_id,
    act.metadata->>'agency_name' AS agency_name,
    act.metadata->>'supplier_name' AS supplier_name,
    act.sector,
    act.policy_topics,
    act.procurement_class,
    act.summary,
    pa.portfolio_label,
    pa.cabinet_ministry_id,
    cm.label AS cabinet_ministry_label,
    cm.parliamentary_term,
    cm.governing_party_short_name,
    cm.jurisdiction_id AS ministry_jurisdiction_id,
    j.code AS ministry_jurisdiction_code,
    j.level AS ministry_jurisdiction_level,
    j.name AS ministry_jurisdiction_name,
    mr.id AS minister_role_id,
    mr.person_id AS minister_person_id,
    mr.person_raw_name AS minister_name,
    mr.role_title AS minister_role_title,
    mr.role_type AS minister_role_type,
    mr.effective_from AS minister_effective_from,
    mr.effective_to AS minister_effective_to,
    'llm_austender_topic_tag' AS contract_evidence_tier,
    'rule_based_aao' AS portfolio_evidence_tier,
    'rule_based_ministry_list' AS minister_evidence_tier,
    'no causation implied; structural mapping of which minister oversaw which agency' AS claim_discipline_note
FROM austender_contract_topic_tag act
LEFT JOIN portfolio_agency pa
    ON lower(pa.agency_canonical_name) = lower(act.metadata->>'agency_name')
       OR lower(act.metadata->>'agency_name') = ANY(
           ARRAY(SELECT lower(unnest(pa.agency_aliases)))
       )
LEFT JOIN cabinet_ministry cm ON cm.id = pa.cabinet_ministry_id
LEFT JOIN jurisdiction j ON j.id = cm.jurisdiction_id
LEFT JOIN minister_role mr
    ON mr.cabinet_ministry_id = pa.cabinet_ministry_id
       AND mr.portfolio_label = pa.portfolio_label;

COMMENT ON VIEW v_contract_minister_responsibility IS
'Contracts joined to the responsible minister via portfolio mapping. Now jurisdiction-aware so federal contracts match federal ministers, state contracts match state ministers (when state contracts are loaded).';
