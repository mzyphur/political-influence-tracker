-- 040_llm_register_of_interests_observation.sql
--
-- Stage 2 of the LLM extraction pipeline: store per-section
-- LLM-extracted disclosure items from House Register of Members'
-- Interests PDFs. The deterministic parser at
-- `backend/au_politics_money/ingest/house_interests.py` already
-- splits each PDF into 13 numbered sections; this LLM stage
-- structures those freeform sections into discrete records.
--
-- Schema design:
--   * One row per (source_id, section_number, item_index, prompt_version).
--     A single section can produce 0..N items; item_index disambiguates.
--   * `extraction_method = 'llm_register_of_interests_v1'` is the
--     project's standard tier label.
--   * Tied to the existing parser via `source_id` (matches the same
--     id space used by `house_interest_section`).
--
-- Reproducibility chain (matches Stages 1+3):
--   * `llm_response_sha256` is the cache envelope hash under
--     `data/raw/llm_extractions/register_of_interests_extraction/<sha256>.{input,output}.json`.
--   * `prompt_version` lets v2/v3 prompts coexist with v1 rows.
--   * Empty-section observations (where `items=[]`) are NOT
--     stored (zero-row sections are uninformative for analysis;
--     the loader checks `items` length).
--
-- Claim discipline:
--   * These rows are evidence-tier-2 (LLM-extracted) and never
--     contribute to the byte-identical-totals invariant for direct
--     person-level money. They surface alongside (not summed with)
--     deterministic tier-1 records.

CREATE TABLE IF NOT EXISTS llm_register_of_interests_observation (
    id BIGSERIAL PRIMARY KEY,

    -- Tied to the existing parser-side keying. The PDF source id
    -- is stable per-MP-per-parliament; section_number is one of
    -- 1..13 (or alt-numbering 1..13 in newer PDFs).
    source_id TEXT NOT NULL,
    section_number TEXT NOT NULL,
    item_index INTEGER NOT NULL,

    -- Member context, echoed from the parser output for
    -- self-contained analysis (avoids needing to JOIN back to the
    -- source-document tables for every read).
    member_name TEXT,
    family_name TEXT,
    given_names TEXT,
    electorate TEXT,
    state TEXT,
    section_title TEXT,

    -- LLM-emitted item fields (enums match the v1 prompt's schema).
    item_type TEXT NOT NULL,
    counterparty_name TEXT NOT NULL,
    counterparty_type TEXT NOT NULL,
    description TEXT NOT NULL,
    estimated_value_aud NUMERIC(20, 2),
    event_date DATE,
    disposition TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence_excerpt TEXT NOT NULL,

    -- Reproducibility provenance.
    extraction_method TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    llm_model_id TEXT NOT NULL,
    llm_response_sha256 TEXT NOT NULL,
    llm_input_tokens INTEGER,
    llm_output_tokens INTEGER,
    llm_cache_hit BOOLEAN NOT NULL DEFAULT FALSE,

    -- Reviewer surface.
    review_status TEXT NOT NULL DEFAULT 'reviewed',

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT llm_roi_obs_item_type_chk
        CHECK (item_type IN (
            'shareholding', 'real_estate', 'directorship',
            'partnership', 'liability', 'investment',
            'other_asset', 'gift', 'sponsored_travel',
            'donation_received', 'membership', 'other_interest'
        )),

    CONSTRAINT llm_roi_obs_counterparty_type_chk
        CHECK (counterparty_type IN (
            'company', 'individual', 'government',
            'foreign_government', 'union', 'association',
            'political_party', 'charity', 'unknown'
        )),

    CONSTRAINT llm_roi_obs_disposition_chk
        CHECK (disposition IN (
            'retained', 'surrendered_displayed',
            'surrendered_donated', 'unknown', 'not_applicable'
        )),

    CONSTRAINT llm_roi_obs_confidence_chk
        CHECK (confidence IN ('high', 'medium', 'low')),

    CONSTRAINT llm_roi_obs_review_chk
        CHECK (review_status IN ('reviewed', 'pending_review', 'rejected'))
);

-- Idempotency: one canonical row per (source_id, section_number,
-- item_index, prompt_version). Re-loading the same JSONL is a
-- no-op via ON CONFLICT DO UPDATE in the loader.
CREATE UNIQUE INDEX IF NOT EXISTS llm_roi_obs_source_section_item_uniq
    ON llm_register_of_interests_observation
    (source_id, section_number, item_index, prompt_version);

-- Indexes for the public app's expected access patterns.
CREATE INDEX IF NOT EXISTS llm_roi_obs_member_idx
    ON llm_register_of_interests_observation (member_name);
CREATE INDEX IF NOT EXISTS llm_roi_obs_counterparty_idx
    ON llm_register_of_interests_observation (counterparty_name);
CREATE INDEX IF NOT EXISTS llm_roi_obs_item_type_idx
    ON llm_register_of_interests_observation (item_type);
CREATE INDEX IF NOT EXISTS llm_roi_obs_counterparty_type_idx
    ON llm_register_of_interests_observation (counterparty_type);
CREATE INDEX IF NOT EXISTS llm_roi_obs_confidence_idx
    ON llm_register_of_interests_observation (confidence);
CREATE INDEX IF NOT EXISTS llm_roi_obs_event_date_idx
    ON llm_register_of_interests_observation (event_date)
    WHERE event_date IS NOT NULL;

-- updated_at trigger.
CREATE OR REPLACE FUNCTION llm_register_of_interests_obs_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS llm_register_of_interests_obs_set_updated_at_trg
    ON llm_register_of_interests_observation;
CREATE TRIGGER llm_register_of_interests_obs_set_updated_at_trg
    BEFORE UPDATE ON llm_register_of_interests_observation
    FOR EACH ROW
    EXECUTE FUNCTION llm_register_of_interests_obs_set_updated_at();
