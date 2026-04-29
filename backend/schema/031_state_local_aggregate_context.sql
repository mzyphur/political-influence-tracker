CREATE TABLE IF NOT EXISTS aggregate_context_observation (
    id BIGSERIAL PRIMARY KEY,
    jurisdiction_id BIGINT REFERENCES jurisdiction(id),
    source_document_id BIGINT REFERENCES source_document(id),
    source_dataset TEXT NOT NULL,
    source_id TEXT NOT NULL,
    observation_key TEXT NOT NULL,
    context_family TEXT NOT NULL,
    context_type TEXT NOT NULL,
    geography_type TEXT,
    geography_name TEXT,
    amount NUMERIC(18,2),
    amount_status TEXT NOT NULL DEFAULT 'reported',
    record_count INTEGER,
    reporting_period_start DATE,
    reporting_period_end DATE,
    evidence_status TEXT NOT NULL DEFAULT 'official_record_parsed',
    attribution_scope TEXT NOT NULL DEFAULT 'aggregate_context_not_recipient_attribution',
    caveat TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_dataset, observation_key)
);

CREATE INDEX IF NOT EXISTS aggregate_context_observation_source_dataset_idx
    ON aggregate_context_observation (source_dataset)
    WHERE is_current IS TRUE;

CREATE INDEX IF NOT EXISTS aggregate_context_observation_jurisdiction_idx
    ON aggregate_context_observation (jurisdiction_id)
    WHERE is_current IS TRUE;

CREATE INDEX IF NOT EXISTS aggregate_context_observation_context_type_idx
    ON aggregate_context_observation (context_type)
    WHERE is_current IS TRUE;

CREATE INDEX IF NOT EXISTS aggregate_context_observation_geography_name_trgm_idx
    ON aggregate_context_observation USING gin (geography_name gin_trgm_ops);
