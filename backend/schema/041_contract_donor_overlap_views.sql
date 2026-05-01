-- 041_contract_donor_overlap_views.sql
--
-- Cross-source correlation views: identify entities that BOTH
-- (a) received Australian Government contracts (LLM-tagged in
--     `austender_contract_topic_tag`)
-- AND (b) appear as donors / gift-givers / hosts in
--     `influence_event` (deterministic disclosure data).
--
-- This is the project's headline analytical surface: "supplier X
-- received $Y in contracts AND gave $Z in donations to MP/party W
-- whose portfolio oversees agency A". The views are STRICTLY
-- analytical — they expose the correlation without summing across
-- the project's distinct evidence tiers.
--
-- Claim discipline:
--   * The contract data is LLM-tagged (evidence tier 2 — labelled
--     `extraction_method LIKE 'llm_austender_topic_tag_%'`).
--   * The donation/gift data is deterministic-source-backed
--     (evidence tier 1).
--   * NEVER sum contract-receipts + donations into a single number.
--     The views surface them side-by-side as separate aggregates.
--   * Every public surface MUST carry the tier label.
--
-- Name-matching strategy:
--   * Suppliers from austender_contract_topic_tag.metadata->>'supplier_name'
--     are normalised by `normalize_supplier_name()` (mirrors the
--     project's existing `normalize_name()` utility).
--   * Match against `entity.normalized_name` exact equality.
--   * No fuzzy matching — false-positive overlaps would undermine
--     the project's "no causation claim" framing.
--   * Suppliers without a matching entity row are NOT flagged as
--     overlap (yet) — the Stage 1 LLM classification run is
--     populating the entity table over time.

CREATE OR REPLACE FUNCTION normalize_supplier_name(value TEXT)
RETURNS TEXT
LANGUAGE SQL IMMUTABLE
AS $$
    SELECT trim(both ' ' from regexp_replace(
        regexp_replace(
            lower(value),
            '[^a-z0-9]+',
            ' ',
            'g'
        ),
        '\s+',
        ' ',
        'g'
    ))
$$;


-- View 1: Per-supplier contract aggregate, with optional entity link.
-- One row per (supplier_name, prompt_version) pair. Suppliers are
-- aggregated across all contract notices the LLM has tagged.
CREATE OR REPLACE VIEW v_contract_supplier_aggregates AS
SELECT
    metadata->>'supplier_name' AS supplier_name,
    normalize_supplier_name(metadata->>'supplier_name') AS supplier_normalized,
    prompt_version,
    COUNT(*) AS contract_count,
    COUNT(DISTINCT contract_id) AS distinct_contract_ids,
    SUM(
        COALESCE(NULLIF(metadata->>'contract_value_aud', '')::numeric, 0)
    ) AS total_contract_value_aud,
    array_agg(DISTINCT sector) AS sectors,
    array_agg(DISTINCT policy_topic ORDER BY policy_topic) FILTER (
        WHERE policy_topic IS NOT NULL
    ) AS policy_topics_distinct,
    array_agg(DISTINCT metadata->>'agency_name') AS agencies,
    MIN(created_at) AS first_tagged_at,
    MAX(created_at) AS last_tagged_at
FROM austender_contract_topic_tag t
LEFT JOIN LATERAL unnest(t.policy_topics) AS policy_topic ON true
GROUP BY metadata->>'supplier_name', prompt_version;


-- View 2: Per-entity influence_event aggregate (donations + gifts +
-- private interests + benefits, etc.). One row per entity_id.
-- Used by the overlap view below.
CREATE OR REPLACE VIEW v_donor_entity_aggregates AS
SELECT
    e.id AS entity_id,
    e.canonical_name,
    e.normalized_name,
    e.entity_type,
    COUNT(ie.id) AS event_count,
    COUNT(DISTINCT ie.event_family) AS distinct_event_families,
    COUNT(*) FILTER (WHERE ie.event_family = 'money') AS money_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'campaign_support') AS campaign_support_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'private_interest') AS private_interest_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'benefit') AS benefit_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'access') AS access_event_count,
    COUNT(*) FILTER (WHERE ie.event_family = 'organisational_role') AS organisational_role_event_count,
    SUM(COALESCE(ie.amount, 0)) FILTER (WHERE ie.event_family = 'money') AS total_money_aud,
    SUM(COALESCE(ie.amount, 0)) FILTER (WHERE ie.event_family = 'campaign_support') AS total_campaign_support_aud,
    array_agg(DISTINCT ie.event_family) AS event_families,
    MIN(ie.event_date) AS earliest_event_date,
    MAX(ie.event_date) AS latest_event_date
FROM entity e
JOIN influence_event ie ON ie.source_entity_id = e.id
WHERE ie.review_status != 'rejected'
GROUP BY e.id, e.canonical_name, e.normalized_name, e.entity_type;


-- View 3: THE HEADLINE. Contract suppliers that ALSO appear as
-- donors / gift-givers / hosts in influence_event. One row per
-- (supplier_normalized, prompt_version) pair where the entity
-- match resolved.
--
-- Public-facing readers see this as: "Supplier X received $Y in
-- contracts during 2020-2025 AND made $Z in donations to political
-- parties / Australian MPs over the same period".
--
-- The view DOES NOT sum these — they live in separate columns
-- with separate evidence-tier labels. Aggregating them into a
-- "total influence" number would conflate evidence tiers and
-- breach the project's claim-discipline rule.
CREATE OR REPLACE VIEW v_contract_donor_overlap AS
SELECT
    csa.supplier_name,
    csa.supplier_normalized,
    csa.prompt_version AS contract_prompt_version,
    csa.contract_count,
    csa.distinct_contract_ids,
    csa.total_contract_value_aud,
    csa.sectors AS contract_sectors,
    csa.policy_topics_distinct AS contract_policy_topics,
    csa.agencies AS contract_agencies,
    -- Entity match
    dea.entity_id AS matched_entity_id,
    dea.canonical_name AS matched_entity_canonical_name,
    dea.entity_type AS matched_entity_type,
    -- Donor / gift / private-interest aggregates
    dea.event_count AS donor_event_count,
    dea.distinct_event_families AS donor_distinct_event_families,
    dea.money_event_count,
    dea.campaign_support_event_count,
    dea.private_interest_event_count,
    dea.benefit_event_count,
    dea.access_event_count,
    dea.organisational_role_event_count,
    dea.total_money_aud AS donor_total_money_aud,
    dea.total_campaign_support_aud AS donor_total_campaign_support_aud,
    dea.event_families AS donor_event_families,
    dea.earliest_event_date AS donor_earliest_event_date,
    dea.latest_event_date AS donor_latest_event_date,
    -- Provenance
    csa.first_tagged_at,
    csa.last_tagged_at,
    -- Claim-discipline labels for downstream surfaces
    'llm_austender_topic_tag' AS contract_evidence_tier,
    'rule_based_disclosure' AS donor_evidence_tier,
    'no causation implied; cross-source temporal correlation only' AS claim_discipline_note
FROM v_contract_supplier_aggregates csa
JOIN v_donor_entity_aggregates dea ON dea.normalized_name = csa.supplier_normalized
WHERE csa.supplier_normalized IS NOT NULL AND csa.supplier_normalized != '';


COMMENT ON VIEW v_contract_donor_overlap IS
'Cross-source correlation: AusTender contract suppliers that ALSO appear as donors / gift-givers / hosts in influence_event. Strictly analytical surface — preserves separate evidence tiers; never sums across them. Powers the public app''s "supplier-X-got-$N-contracts-AND-donated-$M-to-MP-Y" feature.';
