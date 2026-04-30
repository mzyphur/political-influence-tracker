-- 036_seed_additional_canonical_party_rows_v2.sql
--
-- Second-wave seed migration. After 035 the AEC Register's
-- `associatedentity` rows resolved cleanly (60 -> 1 unresolved_no_match).
-- This migration tackles the residual 31 `politicalparty` rows that the
-- live AEC Register currently lists as registered federal parties but
-- that the local DB has no canonical row for. The set is taken
-- directly from the live federal register.
--
-- Same C-rule as before: the AEC Register loader still refuses to
-- auto-create canonical `party` rows from register-row observations.
-- These additions are explicitly hand-curated seeds with public AEC
-- registrations; metadata records the seed source / date / rationale /
-- attribution caveat for every row.
--
-- Scope: federal-jurisdiction canonical rows for AEC-registered parties
-- whose name maps cleanly to a single real-world party (i.e.
-- "Australian Federation Party" maps to all the state-suffixed
-- "Australian Federation Party <state>" rows via the resolver's
-- branch-alias step — see the matching extensions in
-- `aec_register_branch_resolver.py`).
--
-- DELIBERATELY excluded for now (candidate-vehicle / personality
-- registered-name rows — adding them as canonical party rows is a
-- separate scope decision, not blocked by this migration):
--   * "Dai Le & Frank Carbone W.S.C."
--   * "Kim for Canberra"
--   * "Tammy Tyrrell for Tasmania"
--   * "votefusion.org for big ideas"
--
-- Idempotent: rows are only inserted when their (name, jurisdiction_id)
-- slot is not already taken.
DO $$
DECLARE
    cwlth_id BIGINT;
    seed RECORD;
BEGIN
    SELECT id INTO cwlth_id
        FROM jurisdiction
        WHERE level = 'federal'
          AND (code = 'CWLTH' OR LOWER(name) = 'commonwealth')
        ORDER BY id
        LIMIT 1;

    IF cwlth_id IS NULL THEN
        RAISE NOTICE 'Commonwealth jurisdiction not present; skipping party seed v2.';
        RETURN;
    END IF;

    FOR seed IN
        SELECT * FROM (VALUES
            (
                'Australian Federation Party',
                'AFP',
                'AEC-registered federal party with state branches in ACT/NSW/NT/QLD/SA/TAS/VIC/WA. Seeded so the resolver''s branch-alias step can fold the state-suffixed forms into the federal canonical row.'
            ),
            (
                'Family First Party Australia',
                'FFP',
                'AEC-registered federal party. Seeded for the AEC Register resolver.'
            ),
            (
                'The Great Australian Party',
                'TGAP',
                'AEC-registered federal party. Seeded for the AEC Register resolver.'
            ),
            (
                'Better Together Party',
                'BTP',
                'AEC-registered federal party. Seeded for the AEC Register resolver.'
            ),
            (
                'Indigenous - Aboriginal Party of Australia',
                'IAPA',
                'AEC-registered federal party (preserves AEC registered name with hyphen). Seeded for the AEC Register resolver.'
            ),
            (
                'Socialist Alliance',
                'SA',
                'AEC-registered federal party. Seeded for the AEC Register resolver.'
            ),
            (
                'Sustainable Australia Party',
                'SUSAUS',
                'AEC-registered federal party (also publishes under the registered name "Affordable Housing Now - Sustainable Australia Party"). Seeded for the AEC Register resolver; the affordable-housing variant is mapped via a documented alias rule.'
            ),
            (
                'Power 2 People',
                'P2P',
                'AEC-registered federal party. Seeded for the AEC Register resolver.'
            ),
            (
                'Health Environment Accountability Rights Transparency',
                'HEART',
                'AEC-registered federal party. Seeded for the AEC Register resolver.'
            )
        ) AS s(party_name, party_short_name, rationale)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM party
            WHERE name = seed.party_name AND jurisdiction_id = cwlth_id
        ) THEN
            INSERT INTO party (name, short_name, jurisdiction_id, metadata)
            VALUES (
                seed.party_name,
                seed.party_short_name,
                cwlth_id,
                jsonb_build_object(
                    'seed_source', 'schema/036_seed_additional_canonical_party_rows_v2.sql',
                    'seed_date', '2026-04-30',
                    'seed_rationale', seed.rationale,
                    'attribution_caveat',
                    'Seeded canonical party row for AEC Register resolver context. '
                    || 'Not a wrongdoing claim; not a personal-receipt claim about any '
                    || 'individual MP, senator, or candidate.'
                )
            );
        END IF;
    END LOOP;
END $$;
