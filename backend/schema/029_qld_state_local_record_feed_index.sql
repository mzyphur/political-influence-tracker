CREATE INDEX IF NOT EXISTS money_flow_qld_ecq_current_record_feed_idx
    ON money_flow (
        (COALESCE(date_received, date_reported, DATE '0001-01-01')) DESC,
        id DESC
    )
    WHERE is_current IS TRUE
      AND metadata->>'source_dataset' = 'qld_ecq_eds';

CREATE INDEX IF NOT EXISTS money_flow_qld_ecq_current_kind_record_feed_idx
    ON money_flow (
        (metadata->>'flow_kind'),
        (COALESCE(date_received, date_reported, DATE '0001-01-01')) DESC,
        id DESC
    )
    WHERE is_current IS TRUE
      AND metadata->>'source_dataset' = 'qld_ecq_eds';
