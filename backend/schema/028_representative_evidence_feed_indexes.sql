CREATE INDEX IF NOT EXISTS influence_event_person_direct_feed_idx
    ON influence_event (
        recipient_person_id,
        (COALESCE(event_date, DATE '0001-01-01')) DESC,
        (COALESCE(date_reported, DATE '0001-01-01')) DESC,
        id DESC
    )
    WHERE review_status <> 'rejected'
      AND event_family <> 'campaign_support';

CREATE INDEX IF NOT EXISTS influence_event_person_campaign_feed_idx
    ON influence_event (
        recipient_person_id,
        (COALESCE(event_date, DATE '0001-01-01')) DESC,
        (COALESCE(date_reported, DATE '0001-01-01')) DESC,
        id DESC
    )
    WHERE review_status <> 'rejected'
      AND event_family = 'campaign_support';
