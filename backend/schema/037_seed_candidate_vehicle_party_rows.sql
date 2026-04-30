-- 037_seed_candidate_vehicle_party_rows.sql
--
-- Third-wave seed migration. The four rows still classified as
-- `unresolved_no_match` after migration 036 are the AEC-registered
-- "candidate-vehicle / personality" parties: parties that exist as a
-- registered electoral vehicle for a specific candidate or duo rather
-- than as an ideological/policy organisation. They were deliberately
-- deferred from 036 because including them as plain canonical rows
-- would conflate "party" with "personal campaign vehicle" in the public
-- network model.
--
-- This migration adds them with an explicit metadata flag
-- (`is_personality_vehicle = true` plus `affiliated_person_hint`) so
-- downstream UI surfaces can render them with a distinct "personal
-- electoral vehicle" label instead of conflating them with ideological
-- federal parties. The data-model treatment is unchanged - they are
-- still rows in `party` with a federal jurisdiction - but the metadata
-- gives the API and the frontend a deterministic way to flag them.
--
-- Parties added (all AEC-registered at the federal level):
--   * Dai Le & Frank Carbone W.S.C.        (electoral vehicle for the
--                                           Dai Le / Frank Carbone
--                                           Western Sydney Community
--                                           grouping; Dai Le is the
--                                           current federal MP for
--                                           Fowler)
--   * Kim for Canberra                     (electoral vehicle for Kim
--                                           Rubenstein's independent
--                                           Senate campaign in the ACT)
--   * Tammy Tyrrell for Tasmania           (electoral vehicle for
--                                           Senator Tammy Tyrrell)
--   * votefusion.org for big ideas         (Fusion: Science, Pirate,
--                                           Secular, Climate Emergency
--                                           party's federally-registered
--                                           name; not a personality
--                                           vehicle in the same sense
--                                           but uses the same registered
--                                           name pattern, so flagged
--                                           with the same metadata key
--                                           for transparency)
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
        RAISE NOTICE 'Commonwealth jurisdiction not present; skipping party seed v3.';
        RETURN;
    END IF;

    FOR seed IN
        SELECT * FROM (VALUES
            (
                'Dai Le & Frank Carbone W.S.C.',
                'WSC',
                'Western Sydney Community electoral vehicle for the Dai Le / Frank Carbone grouping. Dai Le is the current federal MP for Fowler.',
                TRUE,
                'Dai Le; Frank Carbone'
            ),
            (
                'Kim for Canberra',
                'K4C',
                'Electoral vehicle for Kim Rubenstein''s independent Senate campaign in the ACT.',
                TRUE,
                'Kim Rubenstein'
            ),
            (
                'Tammy Tyrrell for Tasmania',
                'TT4T',
                'Electoral vehicle for Senator Tammy Tyrrell (Tasmania).',
                TRUE,
                'Tammy Tyrrell'
            ),
            (
                'votefusion.org for big ideas',
                'FUSION',
                'AEC-registered name for the Fusion (Science, Pirate, Secular, Climate Emergency) party. Not a single-personality vehicle but uses the same registered-name pattern; flagged with the same metadata key so the UI can distinguish registered-name-style parties from ideological ones consistently.',
                FALSE,
                NULL
            )
        ) AS s(party_name, party_short_name, rationale, is_personality_vehicle, affiliated_person_hint)
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
                    'seed_source', 'schema/037_seed_candidate_vehicle_party_rows.sql',
                    'seed_date', '2026-04-30',
                    'seed_rationale', seed.rationale,
                    'is_personality_vehicle', seed.is_personality_vehicle,
                    'affiliated_person_hint', seed.affiliated_person_hint,
                    'attribution_caveat',
                    'Seeded canonical party row for AEC Register resolver context. '
                    || 'Personality-vehicle metadata distinguishes registered electoral '
                    || 'vehicles for specific candidates from ideological parties; '
                    || 'downstream UI may render them with a distinct label. '
                    || 'Not a wrongdoing claim; not a personal-receipt claim about any '
                    || 'individual MP, senator, or candidate.'
                )
            );
        END IF;
    END LOOP;
END $$;
