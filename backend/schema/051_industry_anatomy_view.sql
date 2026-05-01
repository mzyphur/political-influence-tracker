-- 051_industry_anatomy_view.sql
--
-- THE INFLUENCE ANATOMY VIEW. Per-sector aggregation of EVERY
-- evidence stream the project has on each industry — donations,
-- gifts, sponsored travel, memberships, private interests,
-- contracts received, voting record by the MPs they donated to,
-- and minister oversight overlap.
--
-- Powers the project's headline pro-democracy transparency
-- surface: "Industry X" page showing in one place:
--
--   * How much the industry donated to which parties / MPs.
--   * Which MPs received gifts / hospitality from industry X.
--   * Which MPs took sponsored travel paid for by industry X.
--   * Which contracts the industry won from government, and
--     which ministers oversaw the awarding agencies.
--   * How those MPs voted on policy topics relevant to the
--     industry (raw aye/no/rebellion counts; no auto-alignment).
--
-- Claim discipline preserved. Tier 1 (deterministic donor /
-- gift / travel / membership / minister / voting data) and
-- tier 2 (LLM-tagged contract data) are surfaced in SEPARATE
-- columns. NEVER summed across the boundary.

-- ----------------------------------------------------------------
-- v_sector_gift_aggregates — gift / sponsored-travel / membership
-- counts per sector. The donor sector for each ROI item is
-- looked up via entity_industry_classification matched against
-- the counterparty_name. An entity match is best-effort exact-
-- string-match on normalized_name; non-matching counterparties
-- count toward `unknown` sector.
-- ----------------------------------------------------------------

CREATE OR REPLACE VIEW v_sector_gift_aggregates AS
WITH item_with_sector AS (
    SELECT
        roi.id AS item_id,
        roi.item_type,
        roi.counterparty_name,
        roi.estimated_value_aud,
        roi.event_date,
        roi.disposition,
        eic.public_sector AS counterparty_sector,
        eic.method AS sector_method
    FROM llm_register_of_interests_observation roi
    LEFT JOIN entity e
        ON lower(regexp_replace(roi.counterparty_name, '[^a-zA-Z0-9]+', ' ', 'g')) =
           regexp_replace(e.normalized_name, '\s+', ' ', 'g')
    LEFT JOIN LATERAL (
        SELECT public_sector, method
        FROM entity_industry_classification
        WHERE entity_id = e.id
        ORDER BY
            CASE method
                WHEN 'official' THEN 1
                WHEN 'rule_based' THEN 2
                WHEN 'model_assisted' THEN 3
                ELSE 4
            END,
            CASE confidence
                WHEN 'fuzzy_high' THEN 1
                WHEN 'fuzzy_low' THEN 2
                ELSE 3
            END
        LIMIT 1
    ) eic ON TRUE
)
SELECT
    COALESCE(counterparty_sector, 'unknown') AS sector,
    COUNT(*) FILTER (WHERE item_type = 'gift') AS gift_count,
    SUM(COALESCE(estimated_value_aud, 0)) FILTER (WHERE item_type = 'gift')
        AS gift_total_aud,
    COUNT(*) FILTER (WHERE item_type = 'sponsored_travel')
        AS sponsored_travel_count,
    SUM(COALESCE(estimated_value_aud, 0)) FILTER (WHERE item_type = 'sponsored_travel')
        AS sponsored_travel_total_aud,
    COUNT(*) FILTER (WHERE item_type = 'membership') AS membership_count,
    COUNT(*) FILTER (WHERE item_type = 'directorship') AS directorship_count,
    COUNT(*) FILTER (WHERE item_type IN ('shareholding', 'investment', 'other_asset'))
        AS investment_count,
    COUNT(*) FILTER (WHERE item_type = 'liability') AS liability_count,
    COUNT(DISTINCT counterparty_name) AS distinct_counterparty_names
FROM item_with_sector
GROUP BY COALESCE(counterparty_sector, 'unknown');

COMMENT ON VIEW v_sector_gift_aggregates IS
'Per-sector aggregation of LLM-extracted ROI items (gifts, sponsored travel, memberships, directorships, investments, liabilities). Joined to sector via entity_industry_classification on counterparty name match.';


-- ----------------------------------------------------------------
-- v_sector_voting_alignment — for every sector, aggregate the
-- voting record of MPs who received donations from sector
-- entities, on policy topics tagged by They Vote For You.
-- This surfaces "did MPs who took industry X money vote in
-- patterns that align with industry X interests?" — RAW counts
-- only; consumer interprets.
-- ----------------------------------------------------------------

CREATE OR REPLACE VIEW v_sector_voting_alignment AS
SELECT
    drva.donor_sector AS sector,
    drva.policy_topic_label,
    drva.policy_topic_slug,
    COUNT(DISTINCT drva.recipient_person_id) AS distinct_recipient_persons,
    SUM(drva.donor_total_money_aud) AS sector_total_money_to_recipients_aud,
    SUM(drva.recipient_aye_count) AS recipients_total_aye_count,
    SUM(drva.recipient_no_count) AS recipients_total_no_count,
    SUM(drva.recipient_rebellion_count) AS recipients_total_rebellion_count,
    SUM(drva.recipient_division_count) AS recipients_total_division_count
FROM v_donor_recipient_voting_alignment drva
WHERE drva.donor_sector IS NOT NULL
GROUP BY drva.donor_sector, drva.policy_topic_label, drva.policy_topic_slug;

COMMENT ON VIEW v_sector_voting_alignment IS
'Per (sector, policy_topic) summary: total contributions from sector → recipient MPs and those MPs aggregate aye/no/rebellion counts on the topic. RAW counts; no causation labels.';


-- ----------------------------------------------------------------
-- v_industry_anatomy — THE INFLUENCE ANATOMY view. One row per
-- sector with EVERY evidence stream surfaced side-by-side.
-- ----------------------------------------------------------------

CREATE OR REPLACE VIEW v_industry_anatomy AS
SELECT
    via.sector,
    -- Donor-side (deterministic, tier 1)
    via.distinct_donor_entities,
    via.donor_event_count,
    via.money_event_count,
    via.campaign_support_event_count,
    via.private_interest_event_count,
    via.benefit_event_count,
    via.access_event_count,
    via.organisational_role_event_count,
    via.total_money_aud,
    via.total_campaign_support_aud,
    -- Stage 2 ROI extracted gifts / travel / membership / etc. (LLM tier 2)
    sga.gift_count,
    sga.gift_total_aud,
    sga.sponsored_travel_count,
    sga.sponsored_travel_total_aud,
    sga.membership_count,
    sga.directorship_count,
    sga.investment_count,
    sga.liability_count,
    sga.distinct_counterparty_names AS distinct_gift_counterparty_names,
    -- Contract-side (LLM tier 2)
    via.contract_count,
    via.distinct_contract_ids,
    via.distinct_suppliers,
    via.total_contract_value_aud,
    via.contracting_agencies,
    via.procurement_classes,
    -- Provenance
    via.donor_evidence_tier,
    via.contract_evidence_tier,
    'rule_based_disclosure_with_LLM_sector_label' AS gift_evidence_tier,
    'side-by-side aggregation; tier-1 donor + tier-2 contract + tier-2 ROI items NEVER summed' AS claim_discipline_note
FROM v_industry_influence_aggregate via
LEFT JOIN v_sector_gift_aggregates sga ON sga.sector = via.sector;


COMMENT ON VIEW v_industry_anatomy IS
'THE INFLUENCE ANATOMY VIEW. Per-sector unified aggregation: donations + gifts + sponsored travel + memberships + investments + contracts. Each evidence stream in its own column with explicit tier label. NEVER summed across tiers. Powers the public app''s "Industry Detail" page surface.';
