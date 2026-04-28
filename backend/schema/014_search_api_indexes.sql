-- Search/API hardening indexes for public read endpoints.

CREATE INDEX IF NOT EXISTS person_display_name_trgm_idx
    ON person USING gin (display_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS electorate_name_trgm_idx
    ON electorate USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS policy_topic_label_trgm_idx
    ON policy_topic USING gin (label gin_trgm_ops);

CREATE INDEX IF NOT EXISTS policy_topic_slug_trgm_idx
    ON policy_topic USING gin (slug gin_trgm_ops);

CREATE INDEX IF NOT EXISTS entity_industry_public_sector_trgm_idx
    ON entity_industry_classification USING gin (public_sector gin_trgm_ops);
