-- 052_grant_observation.sql
--
-- GrantConnect government-grant observations. The other major
-- money outflow from federal government to private actors,
-- alongside AusTender contract awards. Together they constitute
-- the bulk of "what the government pays the private sector" — and
-- what the project's pro-democracy transparency surface needs to
-- expose.
--
-- Source: GrantConnect public API + bulk data export at
--   https://www.grants.gov.au
--   https://data.gov.au/dataset/grants-data
-- Licence: CC BY 3.0 AU (Commonwealth) — same as AusTender.
--
-- Schema design:
--
-- grant_observation
--   * One row per published grant award. Stable identifier is
--     `grant_id` (e.g., "GA12345").
--   * Includes recipient organisation (legal name + ABN +
--     country/state), grant value, agency that awarded the grant,
--     CFDA / GO / scheme identifier, start + end dates,
--     description (freeform), category, location.
--
-- llm_grant_topic_tag (separate per migration; future Stage 3 v3
--   parallel for grants)
--   * One row per grant tagged with the project's standard 40-
--     sector + 24-policy-topic taxonomy via the LLM.
--   * Mirrors `austender_contract_topic_tag` schema for analytical
--     symmetry — every grant has a sector in the same enum as
--     contracts; the cross-correlation views can then surface
--     "Industry X received $Y in contracts AND $Z in grants"
--     side-by-side per sector.
--
-- Cross-correlation:
--   * v_sector_money_outflow VIEW (added in this migration) joins
--     contract + grant aggregates per sector for the headline
--     "how much money flows from government to industry X" rollup.

CREATE TABLE IF NOT EXISTS grant_observation (
    id BIGSERIAL PRIMARY KEY,

    -- Natural key from GrantConnect (e.g. "GA12345"). Stable
    -- across publication rounds.
    grant_id TEXT NOT NULL,
    parent_grant_id TEXT,
    notice_type TEXT,
    -- 'New' / 'Variation' / etc.

    -- Awarding agency
    agency_name TEXT NOT NULL,
    agency_ref_id TEXT,
    agency_branch TEXT,
    agency_division TEXT,
    agency_office_postcode TEXT,

    -- Recipient
    recipient_name TEXT NOT NULL,
    recipient_abn TEXT,
    recipient_address TEXT,
    recipient_suburb TEXT,
    recipient_postcode TEXT,
    recipient_state TEXT,
    recipient_country TEXT,

    -- Money
    grant_value_aud NUMERIC(20, 2),
    funding_amount_aud NUMERIC(20, 2),

    -- Dates
    publish_date DATE,
    decision_date DATE,
    start_date DATE,
    end_date DATE,

    -- Description + classification
    grant_program TEXT,
    grant_activity TEXT,
    description TEXT,
    purpose TEXT,
    cfda_code TEXT,

    -- Location of grant activity (when different from recipient)
    location_postcode TEXT,
    location_suburb TEXT,
    location_state TEXT,

    -- Provenance
    source_dataset TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_document_id BIGINT REFERENCES source_document(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT grant_observation_grant_id_uniq UNIQUE (grant_id)
);

CREATE INDEX IF NOT EXISTS grant_observation_recipient_idx
    ON grant_observation (recipient_name);
CREATE INDEX IF NOT EXISTS grant_observation_recipient_abn_idx
    ON grant_observation (recipient_abn) WHERE recipient_abn IS NOT NULL;
CREATE INDEX IF NOT EXISTS grant_observation_agency_idx
    ON grant_observation (agency_name);
CREATE INDEX IF NOT EXISTS grant_observation_publish_date_idx
    ON grant_observation (publish_date);
CREATE INDEX IF NOT EXISTS grant_observation_value_idx
    ON grant_observation (grant_value_aud) WHERE grant_value_aud IS NOT NULL;


-- LLM topic tags for grants — same shape as
-- austender_contract_topic_tag. Allows cross-source aggregation
-- (sector X received $contract + $grant amounts).
CREATE TABLE IF NOT EXISTS llm_grant_topic_tag (
    id BIGSERIAL PRIMARY KEY,
    grant_id TEXT NOT NULL,

    sector TEXT NOT NULL,
    policy_topics TEXT[] NOT NULL,
    procurement_class TEXT NOT NULL,
    -- procurement_class for grants is more about classification
    -- ('services' / 'goods' / 'capital' / 'mixed' — adapted from
    -- contract semantics).
    summary TEXT NOT NULL,
    confidence TEXT NOT NULL,

    extraction_method TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    llm_model_id TEXT NOT NULL,
    llm_response_sha256 TEXT NOT NULL,
    llm_input_tokens INTEGER,
    llm_output_tokens INTEGER,
    llm_cache_hit BOOLEAN NOT NULL DEFAULT FALSE,

    review_status TEXT NOT NULL DEFAULT 'reviewed',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT llm_grant_topic_tag_sector_chk
        CHECK (sector IN (
            'coal', 'gas', 'petroleum', 'uranium', 'fossil_fuels_other',
            'iron_ore', 'critical_minerals', 'mining_other',
            'fossil_fuels', 'mining',
            'renewable_energy', 'property_development', 'construction',
            'gambling', 'alcohol', 'tobacco', 'finance',
            'superannuation', 'insurance', 'banking', 'technology',
            'telecoms', 'defence', 'consulting', 'law', 'accounting',
            'healthcare', 'pharmaceuticals', 'education', 'media',
            'sport_entertainment', 'transport', 'aviation',
            'agriculture', 'unions', 'business_associations',
            'charities_nonprofits', 'foreign_government',
            'government_owned', 'political_entity',
            'individual_uncoded', 'unknown'
        )),
    CONSTRAINT llm_grant_topic_tag_procurement_chk
        CHECK (procurement_class IN ('services', 'goods', 'construction', 'capital', 'mixed')),
    CONSTRAINT llm_grant_topic_tag_confidence_chk
        CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT llm_grant_topic_tag_review_chk
        CHECK (review_status IN ('reviewed', 'pending_review', 'rejected'))
);

CREATE UNIQUE INDEX IF NOT EXISTS llm_grant_topic_tag_grant_version_uniq
    ON llm_grant_topic_tag (grant_id, prompt_version);
CREATE INDEX IF NOT EXISTS llm_grant_topic_tag_sector_idx
    ON llm_grant_topic_tag (sector);
CREATE INDEX IF NOT EXISTS llm_grant_topic_tag_policy_topics_idx
    ON llm_grant_topic_tag USING GIN (policy_topics);


-- updated_at triggers
CREATE OR REPLACE FUNCTION grant_observation_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS grant_observation_set_updated_at_trg ON grant_observation;
CREATE TRIGGER grant_observation_set_updated_at_trg
    BEFORE UPDATE ON grant_observation
    FOR EACH ROW EXECUTE FUNCTION grant_observation_set_updated_at();

CREATE OR REPLACE FUNCTION llm_grant_topic_tag_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS llm_grant_topic_tag_set_updated_at_trg ON llm_grant_topic_tag;
CREATE TRIGGER llm_grant_topic_tag_set_updated_at_trg
    BEFORE UPDATE ON llm_grant_topic_tag
    FOR EACH ROW EXECUTE FUNCTION llm_grant_topic_tag_set_updated_at();


-- ----------------------------------------------------------------
-- v_sector_money_outflow — the comprehensive money-outflow view.
-- Joins contract aggregates + grant aggregates per sector. The
-- headline "how much money flows from government to industry X"
-- rollup. Two evidence-tier-2 streams (both LLM-tagged), surfaced
-- side-by-side; never summed because grants and contracts are
-- distinct legal/economic instruments.
-- ----------------------------------------------------------------

CREATE OR REPLACE VIEW v_sector_grant_aggregates AS
SELECT
    sector,
    prompt_version AS grant_prompt_version,
    COUNT(*) AS grant_count,
    COUNT(DISTINCT grant_id) AS distinct_grant_ids,
    COUNT(DISTINCT metadata->>'recipient_name') AS distinct_recipients,
    SUM(
        COALESCE(NULLIF(metadata->>'grant_value_aud', '')::numeric, 0)
    ) AS total_grant_value_aud,
    array_agg(DISTINCT metadata->>'agency_name') AS granting_agencies,
    'llm_grant_topic_tag' AS evidence_tier
FROM llm_grant_topic_tag
GROUP BY sector, prompt_version;


CREATE OR REPLACE VIEW v_sector_money_outflow AS
SELECT
    COALESCE(c.sector, g.sector) AS sector,
    -- Contract side
    c.contract_count,
    c.total_contract_value_aud,
    c.contracting_agencies,
    -- Grant side
    g.grant_count,
    g.total_grant_value_aud,
    g.granting_agencies,
    -- Provenance
    c.evidence_tier AS contract_evidence_tier,
    g.evidence_tier AS grant_evidence_tier,
    'side-by-side; contracts and grants are distinct money-outflow types and are NEVER summed' AS claim_discipline_note
FROM v_sector_contract_side_aggregate c
FULL OUTER JOIN v_sector_grant_aggregates g ON g.sector = c.sector;


COMMENT ON VIEW v_sector_money_outflow IS
'Comprehensive government-money-outflow view per sector. Contract awards (LLM-tagged AusTender) and grant awards (LLM-tagged GrantConnect) surfaced as separate columns; never summed. Powers the "how much does government give industry X" rollup.';
COMMENT ON TABLE grant_observation IS
'Federal grant award observations from GrantConnect (CC BY 3.0 AU). Mirrors the AusTender contract notice schema for analytical symmetry; LLM topic tagging via llm_grant_topic_tag (Stage 3-grants parallel).';
COMMENT ON TABLE llm_grant_topic_tag IS
'LLM-generated topic tags for federal grants. Mirrors austender_contract_topic_tag schema (40-sector + 24-policy-topic taxonomy).';
