-- 042_industry_influence_aggregate_view.sql
--
-- Industry-level influence aggregation: roll up donations + gifts +
-- contracts BY SECTOR (not just by entity / supplier). Surfaces
-- the question "which industry-as-a-whole exerts how much
-- influence?" alongside the per-entity surface.
--
-- This is the project's headline industry-level analytical surface.
-- Works at scale once Stage 1 (entity industry classification) +
-- Stage 3 (AusTender topic tagging) are fully populated. Pre-launch
-- pilot data already shows the shape.
--
-- The 33-sector taxonomy includes the politically-salient
-- industries the user expected: `fossil_fuels`, `mining`,
-- `renewable_energy`, `gambling`, `alcohol`, `tobacco`,
-- `pharmaceuticals`, `defence`, `consulting`, `banking`,
-- `superannuation`, `media`, etc. The aggregation respects the
-- project's claim-discipline rule: tier-1 (deterministic) and
-- tier-2 (LLM-tagged) values are NEVER summed across the boundary.
--
-- Two source-side surfaces are joined in this view:
--   (A) entity-sector-via-Stage-1-classification
--   (B) contract-sector-via-Stage-3-topic-tagging
-- These are SEPARATE evidence streams; both are surfaced as
-- distinct columns. A user can see "fossil_fuels donors gave $X
-- to political parties (tier 1)" SIDE-BY-SIDE with "fossil_fuels-
-- sector contracts totalled $Y (tier 2)".

-- View 1: per-sector donor-side aggregate (donations + gifts +
-- private interests + benefits + access + organisational roles
-- received by MPs/parties from entities classified as that
-- sector). Sector classification comes from
-- entity_industry_classification.public_sector — uses the
-- HIGHEST-confidence row per entity if multiple classifications
-- exist.
CREATE OR REPLACE VIEW v_sector_donor_side_aggregate AS
WITH best_entity_sector AS (
    SELECT DISTINCT ON (eic.entity_id)
        eic.entity_id,
        eic.public_sector,
        eic.confidence,
        eic.method
    FROM entity_industry_classification eic
    ORDER BY
        eic.entity_id,
        -- Prefer official classifications over rule-based, prefer
        -- rule-based over model-assisted, prefer fuzzy_high over
        -- fuzzy_low.
        CASE eic.method
            WHEN 'official' THEN 1
            WHEN 'rule_based' THEN 2
            WHEN 'model_assisted' THEN 3
            ELSE 4
        END,
        CASE eic.confidence
            WHEN 'fuzzy_high' THEN 1
            WHEN 'fuzzy_low' THEN 2
            WHEN 'unresolved' THEN 3
            ELSE 4
        END
)
SELECT
    bes.public_sector AS sector,
    bes.method AS sector_method,
    COUNT(DISTINCT bes.entity_id) AS distinct_donor_entities,
    COUNT(ie.id) AS event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'money') AS money_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'campaign_support') AS campaign_support_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'private_interest') AS private_interest_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'benefit') AS benefit_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'access') AS access_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'organisational_role') AS organisational_role_event_count,
    SUM(COALESCE(ie.amount, 0)) FILTER (WHERE ie.event_family = 'money') AS total_money_aud,
    SUM(COALESCE(ie.amount, 0)) FILTER (WHERE ie.event_family = 'campaign_support') AS total_campaign_support_aud,
    MIN(ie.event_date) AS earliest_event_date,
    MAX(ie.event_date) AS latest_event_date,
    'rule_based_disclosure_with_LLM_sector_label' AS evidence_tier
FROM best_entity_sector bes
LEFT JOIN influence_event ie ON ie.source_entity_id = bes.entity_id
WHERE ie.review_status != 'rejected' OR ie.id IS NULL
GROUP BY bes.public_sector, bes.method;


-- View 2: per-sector contract-side aggregate (AusTender contract
-- count + total value tagged to that sector).
CREATE OR REPLACE VIEW v_sector_contract_side_aggregate AS
SELECT
    sector,
    prompt_version AS contract_prompt_version,
    COUNT(*) AS contract_count,
    COUNT(DISTINCT contract_id) AS distinct_contract_ids,
    COUNT(DISTINCT metadata->>'supplier_name') AS distinct_suppliers,
    SUM(
        COALESCE(NULLIF(metadata->>'contract_value_aud', '')::numeric, 0)
    ) AS total_contract_value_aud,
    array_agg(DISTINCT metadata->>'agency_name') AS contracting_agencies,
    array_agg(DISTINCT procurement_class) AS procurement_classes,
    'llm_austender_topic_tag' AS evidence_tier
FROM austender_contract_topic_tag
GROUP BY sector, prompt_version;


-- View 3: THE INDUSTRY-LEVEL HEADLINE. FULL OUTER JOIN of donor-
-- side and contract-side aggregates by sector. Surfaces the
-- side-by-side picture: "Industry X donated $Y AND received $Z
-- in contracts" with separate evidence-tier labels.
--
-- Sectors with donor activity but no tagged contracts (or vice
-- versa) still appear (FULL OUTER JOIN with COALESCE).
CREATE OR REPLACE VIEW v_industry_influence_aggregate AS
SELECT
    COALESCE(donor.sector, contract.sector) AS sector,
    -- Donor-side
    donor.distinct_donor_entities,
    donor.event_count AS donor_event_count,
    donor.money_event_count,
    donor.campaign_support_event_count,
    donor.private_interest_event_count,
    donor.benefit_event_count,
    donor.access_event_count,
    donor.organisational_role_event_count,
    donor.total_money_aud,
    donor.total_campaign_support_aud,
    donor.earliest_event_date AS donor_earliest_event_date,
    donor.latest_event_date AS donor_latest_event_date,
    donor.evidence_tier AS donor_evidence_tier,
    donor.sector_method AS donor_sector_method,
    -- Contract-side
    contract.contract_prompt_version,
    contract.contract_count,
    contract.distinct_contract_ids,
    contract.distinct_suppliers,
    contract.total_contract_value_aud,
    contract.contracting_agencies,
    contract.procurement_classes,
    contract.evidence_tier AS contract_evidence_tier,
    -- Claim-discipline note baked into every row.
    'side-by-side aggregation; tier-1 donor amounts and tier-2 contract amounts are NOT summed' AS claim_discipline_note
FROM v_sector_donor_side_aggregate donor
FULL OUTER JOIN v_sector_contract_side_aggregate contract
    ON donor.sector = contract.sector;


COMMENT ON VIEW v_industry_influence_aggregate IS
'Industry-level influence aggregation: side-by-side donor totals (tier 1) and contract totals (tier 2) per sector. Powers "the gas industry / lobby gave $X in donations AND received $Y in contracts" type analysis.';
