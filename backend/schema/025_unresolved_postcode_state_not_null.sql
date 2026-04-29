UPDATE postcode_electorate_crosswalk_unresolved
SET state_or_territory = ''
WHERE state_or_territory IS NULL;

ALTER TABLE postcode_electorate_crosswalk_unresolved
    ALTER COLUMN state_or_territory SET DEFAULT '',
    ALTER COLUMN state_or_territory SET NOT NULL;
