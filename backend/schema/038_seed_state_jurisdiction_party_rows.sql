-- 038_seed_state_jurisdiction_party_rows.sql
--
-- Sub-national rollout — state-jurisdiction party seed migration.
--
-- Activates the deferred sub-national rollout for NSW, VIC, SA, WA,
-- TAS, NT, and ACT. Each state/territory gets a peer canonical
-- `party` row for the major federal parties' state branches, sitting
-- under the matching state `jurisdiction_id`. The federal canonical
-- row stays unchanged; the state-jurisdiction row is a PEER, not a
-- replacement. (This is the same shape as the QLD-jurisdiction
-- party rows that QLD ECQ ingestion created on-the-fly for QLD —
-- ALP id=152936, LNP id=152939, KAP id=152969, IND id=153001,
-- Australian Greens id=152983.)
--
-- Why this exists. The Batch R sub-national rollout activated the
-- dual-call resolver: when an AEC Register `AssociatedParties`
-- segment names a state branch (e.g. "Australian Labor Party
-- (NSW Branch)"), the loader resolves it to BOTH the federal
-- canonical ALP row AND the corresponding state-jurisdiction ALP
-- row, emitting two `party_entity_link` rows as peers. That
-- behaviour requires the state-jurisdiction rows to exist. QLD
-- already had them; this migration backfills the rest.
--
-- Important non-goals. This migration deliberately:
--   * Does NOT touch federal canonical rows.
--   * Does NOT consolidate, merge, or otherwise change the
--     `(name, jurisdiction_id, chamber)` unique key on existing
--     rows (the federal-vs-state separation is the entire point).
--   * Does NOT seed minor / candidate-vehicle / regional parties
--     (e.g. SA-Best, JLN, CLP, Canberra Liberals). Those land
--     when they're needed; this migration covers the four
--     parties present in every state's federal-party landscape:
--     ALP, Liberal Party, Australian Greens, and the National
--     Party (where it is separate from the Liberal Party).
--   * Does NOT change any direct-money totals. The dual-call
--     resolver only adds party_entity_link rows; the
--     `test_loader_does_not_change_direct_representative_money_totals`
--     invariant continues to hold.
--
-- Once seeded, NSW / VIC / SA / WA / TAS / NT / ACT state-branch
-- segments in the AEC Register start producing state-jurisdiction
-- party_entity_link rows automatically on the next pipeline run —
-- no further code changes needed.

-- Idempotency. Each INSERT block is wrapped in
-- WHERE NOT EXISTS so a re-run is a no-op.

-- ----- New South Wales -----
INSERT INTO party (name, short_name, jurisdiction_id, metadata)
SELECT
    party_name,
    short_name,
    j.id,
    jsonb_build_object(
        'seed_source', 'schema/038_seed_state_jurisdiction_party_rows.sql',
        'seed_date', '2026-05-01',
        'seed_rationale',
        'NSW state-jurisdiction peer of the federal canonical row, ' ||
        'seeded for sub-national rollout. Allows the AEC Register ' ||
        'dual-call resolver to emit a NSW-jurisdiction party_entity_link ' ||
        'when an AEC AssociatedParties segment names a NSW branch ' ||
        '(e.g. "Australian Labor Party (NSW Branch)").',
        'state_branch_of', state_branch_of_name
    )
FROM (
    VALUES
        ('Australian Labor Party', 'ALP', 'Australian Labor Party'),
        ('Liberal Party', 'LP', 'Liberal Party of Australia'),
        ('National Party', 'NATS', 'National Party of Australia'),
        ('Australian Greens', 'AG', 'Australian Greens'),
        ('Independent', 'IND', 'Independent')
) AS s(party_name, short_name, state_branch_of_name)
CROSS JOIN jurisdiction j
WHERE j.level = 'state' AND j.code = 'NSW'
AND NOT EXISTS (
    SELECT 1 FROM party p
    WHERE p.name = s.party_name AND p.jurisdiction_id = j.id
);

-- ----- Victoria -----
INSERT INTO party (name, short_name, jurisdiction_id, metadata)
SELECT
    party_name,
    short_name,
    j.id,
    jsonb_build_object(
        'seed_source', 'schema/038_seed_state_jurisdiction_party_rows.sql',
        'seed_date', '2026-05-01',
        'seed_rationale',
        'VIC state-jurisdiction peer of the federal canonical row, ' ||
        'seeded for sub-national rollout.',
        'state_branch_of', state_branch_of_name
    )
FROM (
    VALUES
        ('Australian Labor Party', 'ALP', 'Australian Labor Party'),
        ('Liberal Party', 'LP', 'Liberal Party of Australia'),
        ('National Party', 'NATS', 'National Party of Australia'),
        ('Australian Greens', 'AG', 'Australian Greens'),
        ('Independent', 'IND', 'Independent')
) AS s(party_name, short_name, state_branch_of_name)
CROSS JOIN jurisdiction j
WHERE j.level = 'state' AND j.code = 'VIC'
AND NOT EXISTS (
    SELECT 1 FROM party p
    WHERE p.name = s.party_name AND p.jurisdiction_id = j.id
);

-- ----- South Australia -----
INSERT INTO party (name, short_name, jurisdiction_id, metadata)
SELECT
    party_name,
    short_name,
    j.id,
    jsonb_build_object(
        'seed_source', 'schema/038_seed_state_jurisdiction_party_rows.sql',
        'seed_date', '2026-05-01',
        'seed_rationale',
        'SA state-jurisdiction peer of the federal canonical row, ' ||
        'seeded for sub-national rollout.',
        'state_branch_of', state_branch_of_name
    )
FROM (
    VALUES
        ('Australian Labor Party', 'ALP', 'Australian Labor Party'),
        ('Liberal Party', 'LP', 'Liberal Party of Australia'),
        ('Australian Greens', 'AG', 'Australian Greens'),
        ('Independent', 'IND', 'Independent')
) AS s(party_name, short_name, state_branch_of_name)
CROSS JOIN jurisdiction j
WHERE j.level = 'state' AND j.code = 'SA'
AND NOT EXISTS (
    SELECT 1 FROM party p
    WHERE p.name = s.party_name AND p.jurisdiction_id = j.id
);

-- ----- Western Australia -----
INSERT INTO party (name, short_name, jurisdiction_id, metadata)
SELECT
    party_name,
    short_name,
    j.id,
    jsonb_build_object(
        'seed_source', 'schema/038_seed_state_jurisdiction_party_rows.sql',
        'seed_date', '2026-05-01',
        'seed_rationale',
        'WA state-jurisdiction peer of the federal canonical row, ' ||
        'seeded for sub-national rollout.',
        'state_branch_of', state_branch_of_name
    )
FROM (
    VALUES
        ('Australian Labor Party', 'ALP', 'Australian Labor Party'),
        ('Liberal Party', 'LP', 'Liberal Party of Australia'),
        ('National Party', 'NATS', 'National Party of Australia'),
        ('Australian Greens', 'AG', 'Australian Greens'),
        ('Independent', 'IND', 'Independent')
) AS s(party_name, short_name, state_branch_of_name)
CROSS JOIN jurisdiction j
WHERE j.level = 'state' AND j.code = 'WA'
AND NOT EXISTS (
    SELECT 1 FROM party p
    WHERE p.name = s.party_name AND p.jurisdiction_id = j.id
);

-- ----- Tasmania -----
INSERT INTO party (name, short_name, jurisdiction_id, metadata)
SELECT
    party_name,
    short_name,
    j.id,
    jsonb_build_object(
        'seed_source', 'schema/038_seed_state_jurisdiction_party_rows.sql',
        'seed_date', '2026-05-01',
        'seed_rationale',
        'TAS state-jurisdiction peer of the federal canonical row, ' ||
        'seeded for sub-national rollout.',
        'state_branch_of', state_branch_of_name
    )
FROM (
    VALUES
        ('Australian Labor Party', 'ALP', 'Australian Labor Party'),
        ('Liberal Party', 'LP', 'Liberal Party of Australia'),
        ('Australian Greens', 'AG', 'Australian Greens'),
        ('Independent', 'IND', 'Independent')
) AS s(party_name, short_name, state_branch_of_name)
CROSS JOIN jurisdiction j
WHERE j.level = 'state' AND j.code = 'TAS'
AND NOT EXISTS (
    SELECT 1 FROM party p
    WHERE p.name = s.party_name AND p.jurisdiction_id = j.id
);

-- ----- Northern Territory -----
INSERT INTO party (name, short_name, jurisdiction_id, metadata)
SELECT
    party_name,
    short_name,
    j.id,
    jsonb_build_object(
        'seed_source', 'schema/038_seed_state_jurisdiction_party_rows.sql',
        'seed_date', '2026-05-01',
        'seed_rationale',
        'NT territory-jurisdiction peer of the federal canonical row, ' ||
        'seeded for sub-national rollout.',
        'state_branch_of', state_branch_of_name
    )
FROM (
    VALUES
        ('Australian Labor Party', 'ALP', 'Australian Labor Party'),
        ('Country Liberal Party', 'CLP', 'Country Liberal Party'),
        ('Australian Greens', 'AG', 'Australian Greens'),
        ('Independent', 'IND', 'Independent')
) AS s(party_name, short_name, state_branch_of_name)
CROSS JOIN jurisdiction j
WHERE j.level = 'state' AND j.code = 'NT'
AND NOT EXISTS (
    SELECT 1 FROM party p
    WHERE p.name = s.party_name AND p.jurisdiction_id = j.id
);

-- ----- Australian Capital Territory -----
INSERT INTO party (name, short_name, jurisdiction_id, metadata)
SELECT
    party_name,
    short_name,
    j.id,
    jsonb_build_object(
        'seed_source', 'schema/038_seed_state_jurisdiction_party_rows.sql',
        'seed_date', '2026-05-01',
        'seed_rationale',
        'ACT territory-jurisdiction peer of the federal canonical row, ' ||
        'seeded for sub-national rollout.',
        'state_branch_of', state_branch_of_name
    )
FROM (
    VALUES
        ('Australian Labor Party', 'ALP', 'Australian Labor Party'),
        ('Liberal Party', 'LP', 'Liberal Party of Australia'),
        ('Australian Greens', 'AG', 'Australian Greens'),
        ('Independent', 'IND', 'Independent')
) AS s(party_name, short_name, state_branch_of_name)
CROSS JOIN jurisdiction j
WHERE j.level = 'state' AND j.code = 'ACT'
AND NOT EXISTS (
    SELECT 1 FROM party p
    WHERE p.name = s.party_name AND p.jurisdiction_id = j.id
);
