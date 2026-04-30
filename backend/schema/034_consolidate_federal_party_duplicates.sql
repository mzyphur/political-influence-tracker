-- 034_consolidate_federal_party_duplicates.sql
--
-- One-shot data-fix migration: consolidate federal-jurisdiction
-- short-form / long-form party duplicate pairs into a single canonical
-- row per real-world party, so that AEC-Register-derived
-- party_entity_link rows (which the resolver targets via the
-- long-form name) surface on the same MPs whose office_term rows refer
-- to the short-form id.
--
-- Background
-- ----------
-- The local `party` table grew from two ingestion paths:
--   * Short-form rows (e.g. id=1 name='ALP', short_name='ALP') created
--     by the federal results / TVFY pipeline. These are what live
--     office_term rows reference, so they're where current MPs sit.
--   * Long-form rows (e.g. id=1351 name='Australian Labor Party',
--     short_name='Australian Labor Party') created by other ingestion
--     paths and what the AEC Register's `AssociatedParties` text
--     resolves to via the deterministic branch resolver.
--
-- They refer to the same real-world federal party, but have no
-- foreign-key bridge between them. Without consolidation,
-- AEC-Register-derived party_entity_link rows attach to the long-form
-- ids, which have zero active office_terms — so no MP ever surfaces a
-- party-mediated exposure event from this source.
--
-- Direct-money invariant
-- ----------------------
-- The long-form rows have ZERO references in `money_flow`,
-- `influence_event`, and `evidence_claim` at the time of writing, so
-- the consolidation cannot change any direct-money totals. The
-- existing `test_loader_does_not_change_direct_representative_money_totals`
-- integration test guards this invariant on every CI run.
--
-- QLD state-jurisdiction "duplicates" (jurisdiction_id=41) are LEFT
-- ALONE — they are intentional separate rows for state-level
-- representatives and must not be folded into federal rows.
--
-- Idempotency
-- -----------
-- The migration is wrapped in a DO block that checks for the
-- existence of both sides of each pair before acting. On a fresh
-- database that never had the long-form rows, every pair is a no-op
-- and the migration completes cleanly.
DO $$
DECLARE
    pair RECORD;
    long_name_value TEXT;
BEGIN
    FOR pair IN
        SELECT * FROM (VALUES
            (1351::BIGINT,    1::BIGINT),  -- Australian Labor Party -> ALP
            (1389::BIGINT,   11::BIGINT),  -- Independent -> IND
            (1412::BIGINT,  136::BIGINT),  -- Australian Greens -> AG
            (1444::BIGINT,   10::BIGINT),  -- National Party -> NATS
            (1445::BIGINT,    3::BIGINT),  -- Liberal Party -> LP
            (1460::BIGINT,    6::BIGINT),  -- Liberal National Party -> LNP
            (1517::BIGINT,   65::BIGINT),  -- One Nation -> ON
            (1692::BIGINT,   66::BIGINT)   -- Katter's Australian Party -> KAP
        ) AS pairs(long_id, short_id)
    LOOP
        -- Only act if BOTH rows exist AND both are in the federal
        -- jurisdiction. (State-jurisdiction rows must not be merged
        -- into federal rows.)
        IF EXISTS (
            SELECT 1 FROM party
            WHERE id = pair.long_id
              AND jurisdiction_id = 1
        )
        AND EXISTS (
            SELECT 1 FROM party
            WHERE id = pair.short_id
              AND jurisdiction_id = 1
        ) THEN
            -- Capture the long-form display name BEFORE deleting it,
            -- so we can promote it onto the canonical short-id row.
            SELECT name INTO long_name_value
                FROM party WHERE id = pair.long_id;

            -- Re-point every FK reference from long-id to short-id.
            UPDATE office_term
                SET party_id = pair.short_id
                WHERE party_id = pair.long_id;
            UPDATE money_flow
                SET recipient_party_id = pair.short_id
                WHERE recipient_party_id = pair.long_id;
            UPDATE person_vote
                SET party_id = pair.short_id
                WHERE party_id = pair.long_id;
            UPDATE evidence_claim
                SET subject_party_id = pair.short_id
                WHERE subject_party_id = pair.long_id;
            UPDATE influence_event
                SET recipient_party_id = pair.short_id
                WHERE recipient_party_id = pair.long_id;
            UPDATE party_entity_link
                SET party_id = pair.short_id
                WHERE party_id = pair.long_id;
            UPDATE aec_register_of_entities_observation
                SET resolved_canonical_party_id = pair.short_id
                WHERE resolved_canonical_party_id = pair.long_id;

            -- Now delete the long-form row to free up the (name,
            -- jurisdiction_id) unique slot.
            DELETE FROM party WHERE id = pair.long_id;

            -- Promote the long-form display name onto the surviving
            -- short-id row. Keep the short_name as the code-form so
            -- existing consumers still recognize the 'ALP'/'LP'/etc.
            -- short identifiers.
            UPDATE party
                SET name = long_name_value
                WHERE id = pair.short_id;
        END IF;
    END LOOP;
END $$;
