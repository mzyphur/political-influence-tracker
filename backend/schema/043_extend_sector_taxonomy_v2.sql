-- 043_extend_sector_taxonomy_v2.sql
--
-- Extend the project's sector taxonomy CHECK constraints from
-- the v1 33-value list to the v2 40-value list. The v2 changes
-- are ADDITIVE — every v1 sector code remains valid; the new
-- codes split fossil_fuels (1 → 5) and mining (1 → 3).
--
-- Two tables carry sector CHECK constraints:
--   * entity_industry_classification.public_sector
--   * austender_contract_topic_tag.sector
--
-- Approach:
--   1. Drop the v1 CHECK constraint.
--   2. Add a v2 CHECK constraint listing all 40 codes (the v1
--      codes including fossil_fuels and mining stay listed, so
--      v1-tagged rows remain valid).
--   3. v2 prompts (entity_industry_classification/v2.md +
--      austender_contract_topic_tag/v3.md) emit the new sub-
--      codes; v1-tagged rows keep their old codes.
--
-- Rationale for keeping v1 codes valid:
--   * v1 cached responses + DB rows are auditable history.
--   * Cross-version IRR scripts need both v1 + v2 sectors to
--     coexist in the same DB.
--   * The methodology page documents the split clearly to
--     researchers; the row-level prompt_version makes the
--     taxonomy version unambiguous.

-- entity_industry_classification.public_sector
ALTER TABLE entity_industry_classification
DROP CONSTRAINT IF EXISTS entity_industry_classification_public_sector_check;

ALTER TABLE entity_industry_classification
ADD CONSTRAINT entity_industry_classification_public_sector_check
CHECK (public_sector IN (
    -- v2 expanded energy / mining codes (NEW in v2)
    'coal', 'gas', 'petroleum', 'uranium', 'fossil_fuels_other',
    'iron_ore', 'critical_minerals', 'mining_other',
    -- v1 legacy codes (kept valid for v1-tagged rows)
    'fossil_fuels', 'mining',
    -- Unchanged sectors (both v1 and v2 use these)
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
));

-- austender_contract_topic_tag.sector
ALTER TABLE austender_contract_topic_tag
DROP CONSTRAINT IF EXISTS austender_contract_topic_tag_sector_chk;

ALTER TABLE austender_contract_topic_tag
ADD CONSTRAINT austender_contract_topic_tag_sector_chk
CHECK (sector IN (
    -- v2 expanded energy / mining codes (NEW in v2 / v3)
    'coal', 'gas', 'petroleum', 'uranium', 'fossil_fuels_other',
    'iron_ore', 'critical_minerals', 'mining_other',
    -- v1 / v2 legacy codes (kept valid for legacy-tagged rows)
    'fossil_fuels', 'mining',
    -- Unchanged sectors
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
));
