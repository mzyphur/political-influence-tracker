-- 035_seed_additional_canonical_party_rows.sql
--
-- Seed migration: add a small, hand-curated set of additional federal-
-- jurisdiction canonical `party` rows so the deterministic AEC Register
-- resolver can connect their associated-entity rows to a real party
-- without breaking the C-rule against silent auto-creation.
--
-- Why a seed migration rather than an auto-create rule?
-- ---------------------------------------------------------
-- The AEC Register loader's C-rule deliberately refuses to auto-create
-- canonical `party` rows from register-row observations: that would
-- silently expand the public influence model without review. The
-- alternative is to seed canonical rows here, in code, with a
-- documented rationale. Each row this migration adds has a public AEC
-- registration that names it explicitly; nothing here is inferred from
-- a non-source-backed dataset.
--
-- Scope: federal-jurisdiction canonical rows only. Per the existing
-- pattern, `name` carries the long-form display name and `short_name`
-- carries the conventional code/abbreviation. State-level "branch" rows
-- continue to be created by their own ingestion paths and are not
-- merged into these federal canonicals.
--
-- The metadata blob records the seed source so the row's history is
-- auditable.
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
        RAISE NOTICE 'Commonwealth jurisdiction not present; skipping party seed.';
        RETURN;
    END IF;

    FOR seed IN
        SELECT * FROM (VALUES
            (
                'Animal Justice Party',
                'AJP',
                'AEC-registered federal party. Seeded so AEC Register associated-entity rows naming this party as a parent resolve to a single canonical id.'
            ),
            (
                'Australian Citizens Party',
                'CITZN',
                'AEC-registered federal party (formerly Citizens Electoral Council). Seeded for the AEC Register resolver.'
            ),
            (
                'Libertarian Party',
                'LIB-DEM',
                'AEC-registered federal party (rebranded from Liberal Democrats). Seeded for the AEC Register resolver.'
            ),
            (
                'Shooters, Fishers and Farmers Party',
                'SFF',
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
                    'seed_source', 'schema/035_seed_additional_canonical_party_rows.sql',
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
