-- Ensure ON CONFLICT (decision_key) works on databases upgraded before 005
-- added a table-level unique constraint.

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
