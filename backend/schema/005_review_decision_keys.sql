-- Idempotency key for imported manual review decisions.
-- Existing local databases may have applied 004 before decision_key existed.

ALTER TABLE manual_review_decision
    ADD COLUMN IF NOT EXISTS decision_key TEXT;

UPDATE manual_review_decision
SET decision_key = 'legacy:' || id::text
WHERE decision_key IS NULL;

ALTER TABLE manual_review_decision
    ALTER COLUMN decision_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS manual_review_decision_decision_key_idx
    ON manual_review_decision (decision_key)
    WHERE decision_key IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        JOIN pg_attribute attribute_row
          ON attribute_row.attrelid = constraint_row.conrelid
         AND attribute_row.attnum = constraint_row.conkey[1]
        WHERE constraint_row.conrelid = 'manual_review_decision'::regclass
          AND constraint_row.contype = 'u'
          AND array_length(constraint_row.conkey, 1) = 1
          AND attribute_row.attname = 'decision_key'
    ) THEN
        ALTER TABLE manual_review_decision
            ADD CONSTRAINT manual_review_decision_decision_key_unique UNIQUE (decision_key);
    END IF;
END $$;
