ALTER TABLE postcode_electorate_crosswalk
    ADD COLUMN IF NOT EXISTS aec_division_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS source_boundary_context TEXT NOT NULL DEFAULT 'next_federal_election_electorates',
    ADD COLUMN IF NOT EXISTS current_member_context TEXT NOT NULL DEFAULT 'previous_election_or_subsequent_by_election_member';
