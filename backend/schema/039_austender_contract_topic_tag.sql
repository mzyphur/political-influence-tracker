-- 039_austender_contract_topic_tag.sql
--
-- Stage 3 of the LLM extraction pipeline: store per-contract topic tags
-- emitted by the LLM tagger driven by
-- `prompts/austender_contract_topic_tag/v1.md` (Haiku 4.5).
--
-- Each AusTender contract notice is tagged exactly once per (contract_id,
-- prompt_version) pair with:
--   * one industry sector (33-value taxonomy, matches Stage 1)
--   * one or more policy topics (24-value taxonomy)
--   * a procurement_class (services / goods / construction / mixed)
--   * a 1-sentence plain-English summary (<= 250 chars)
--   * a confidence label
--
-- The table is independent of the (still-pending) `austender_contract`
-- table — Stage 3 lands BEFORE the AusTender DB loader does, so we use
-- the natural `contract_id` (CN12345678 / CN12345678-A1) as the join key
-- without a foreign key. Once the contract loader ships, a follow-up
-- migration will add the FK with `ON UPDATE CASCADE / ON DELETE CASCADE`.
--
-- Reproducibility chain (matches Stage 1 design):
--   * `input_sha256` is the hash of the cache envelope under
--     `data/raw/llm_extractions/austender_contract_topic_tag/<sha256>.{input,output}.json`.
--     Anyone with the cache files can verify the row without an API key.
--   * `prompt_version` lets v2 / v3 prompts coexist with v1 rows;
--     `(contract_id, prompt_version)` is the unique key.
--   * `extraction_method` carries the project's standard tier label so
--     the row never gets confused with deterministic / rule-based output.

CREATE TABLE IF NOT EXISTS austender_contract_topic_tag (
    id BIGSERIAL PRIMARY KEY,

    -- Natural key from the AusTender contract notice CSV. Stable
    -- across publication rounds (CN<digits>; amendments suffix
    -- "-A<n>"). Never a surrogate id.
    contract_id TEXT NOT NULL,

    -- LLM-emitted classification fields. Enums kept in sync with the
    -- entity_industry_classification.public_sector check constraint
    -- (Stage 1) plus the 24-value policy-topic taxonomy.
    sector TEXT NOT NULL,
    policy_topics TEXT[] NOT NULL,
    procurement_class TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence TEXT NOT NULL,

    -- Reproducibility provenance.
    extraction_method TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    llm_model_id TEXT NOT NULL,
    llm_response_sha256 TEXT NOT NULL,
    llm_input_tokens INTEGER,
    llm_output_tokens INTEGER,
    llm_cache_hit BOOLEAN NOT NULL DEFAULT FALSE,

    -- Reviewer surface — same shape as other observation tables.
    review_status TEXT NOT NULL DEFAULT 'reviewed',

    -- Free-form metadata (UNSPSC echoed back, agency at tag time, etc.).
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT austender_contract_topic_tag_sector_chk
        CHECK (sector IN (
            'fossil_fuels', 'mining', 'renewable_energy',
            'property_development', 'construction', 'gambling',
            'alcohol', 'tobacco', 'finance', 'superannuation',
            'insurance', 'banking', 'technology', 'telecoms',
            'defence', 'consulting', 'law', 'accounting',
            'healthcare', 'pharmaceuticals', 'education',
            'media', 'sport_entertainment', 'transport',
            'aviation', 'agriculture', 'unions',
            'business_associations', 'charities_nonprofits',
            'foreign_government', 'government_owned',
            'political_entity', 'individual_uncoded', 'unknown'
        )),

    CONSTRAINT austender_contract_topic_tag_procurement_chk
        CHECK (procurement_class IN ('services', 'goods', 'construction', 'mixed')),

    CONSTRAINT austender_contract_topic_tag_confidence_chk
        CHECK (confidence IN ('high', 'medium', 'low')),

    CONSTRAINT austender_contract_topic_tag_review_chk
        CHECK (review_status IN ('reviewed', 'pending_review', 'rejected'))
);

-- One canonical tag row per (contract_id, prompt_version). v2/v3 prompts
-- coexist with v1 rows; the API surface picks whichever is freshest.
CREATE UNIQUE INDEX IF NOT EXISTS austender_contract_topic_tag_contract_version_uniq
    ON austender_contract_topic_tag (contract_id, prompt_version);

-- Lookups by sector / policy topic — the public app's main filtering
-- surfaces (e.g. "Show me defence-procurement contracts to consulting
-- firms").
CREATE INDEX IF NOT EXISTS austender_contract_topic_tag_sector_idx
    ON austender_contract_topic_tag (sector);
CREATE INDEX IF NOT EXISTS austender_contract_topic_tag_policy_topics_idx
    ON austender_contract_topic_tag USING GIN (policy_topics);
CREATE INDEX IF NOT EXISTS austender_contract_topic_tag_procurement_idx
    ON austender_contract_topic_tag (procurement_class);
CREATE INDEX IF NOT EXISTS austender_contract_topic_tag_confidence_idx
    ON austender_contract_topic_tag (confidence);

-- updated_at trigger — same pattern as other tables in the schema.
CREATE OR REPLACE FUNCTION austender_contract_topic_tag_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS austender_contract_topic_tag_set_updated_at_trg
    ON austender_contract_topic_tag;
CREATE TRIGGER austender_contract_topic_tag_set_updated_at_trg
    BEFORE UPDATE ON austender_contract_topic_tag
    FOR EACH ROW
    EXECUTE FUNCTION austender_contract_topic_tag_set_updated_at();
