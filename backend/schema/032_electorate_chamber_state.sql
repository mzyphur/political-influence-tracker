ALTER TABLE electorate
DROP CONSTRAINT IF EXISTS electorate_chamber_check;

ALTER TABLE electorate
ADD CONSTRAINT electorate_chamber_check
CHECK (
    chamber IN (
        'house',
        'senate',
        'state',
        'legislative_assembly',
        'legislative_council',
        'council',
        'other'
    )
);
