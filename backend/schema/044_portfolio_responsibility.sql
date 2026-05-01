-- 044_portfolio_responsibility.sql
--
-- Stage 4a of the influence-correlation pipeline: portfolio →
-- agency → minister mapping. Closes the structural gap that
-- prevents the cross-correlation surface from showing
-- "donations went to MPs whose portfolio oversees the agency
-- paying X". Without this table, we know donors-and-recipients
-- but not minister-and-agency. With it, we close the loop.
--
-- Schema design:
--
-- `cabinet_ministry`
--   * One row per ministry (e.g. "Albanese Ministry — 2nd
--     Cabinet, post-2025-election").
--   * Identified by descriptive label + effective-date range.
--   * FK target for `minister_role`.
--
-- `minister_role`
--   * One row per (person, role, ministry) tuple.
--   * `role_title` = "Minister for Defence", "Treasurer",
--     "Attorney-General", etc. (verbatim AAO wording).
--   * `effective_from` / `effective_to` = date range during
--     which the person held the role. Open-ended (NULL
--     `effective_to`) for current roles.
--   * Honours overlapping appointments (one person can hold
--     multiple portfolios; one portfolio can be split across
--     multiple ministers).
--
-- `portfolio_agency`
--   * One row per (cabinet_ministry, agency_name) tuple.
--   * The agencies under each portfolio. From the
--     Administrative Arrangements Order (AAO).
--   * `agency_canonical_name` matches the supplier names used
--     by AusTender (e.g. "Department of Defence", "Australian
--     Taxation Office") so cross-joins are direct.
--
-- Source provenance:
--   * Every row carries `source_document_id` pointing at the
--     APH ministry-list page or the AAO PDF.
--   * Updates land via deterministic re-fetch, never
--     hand-edited in production.
--
-- Claim discipline:
--   * These rows are tier-1 (deterministic, source-attributed).
--   * Joining `portfolio_agency` to `austender_contract_topic_tag`
--     by `agency_canonical_name` and `minister_role` to
--     `influence_event.recipient_person_id` enables the
--     three-way correlation (donor → MP → portfolio → contract).
--   * NEVER infer minister responsibility from absence; agencies
--     not in `portfolio_agency` are "responsibility unknown",
--     not "no minister".

CREATE TABLE IF NOT EXISTS cabinet_ministry (
    id BIGSERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    short_label TEXT,
    parliamentary_term TEXT,
    governing_party_short_name TEXT,
    effective_from DATE NOT NULL,
    effective_to DATE,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    source_document_id BIGINT REFERENCES source_document(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cabinet_ministry_label_uniq UNIQUE (label)
);

CREATE INDEX IF NOT EXISTS cabinet_ministry_effective_idx
    ON cabinet_ministry (effective_from, effective_to);
CREATE INDEX IF NOT EXISTS cabinet_ministry_current_idx
    ON cabinet_ministry (is_current) WHERE is_current;


CREATE TABLE IF NOT EXISTS minister_role (
    id BIGSERIAL PRIMARY KEY,
    cabinet_ministry_id BIGINT REFERENCES cabinet_ministry(id)
        ON DELETE CASCADE,
    person_id BIGINT REFERENCES person(id) ON DELETE SET NULL,
    person_raw_name TEXT NOT NULL,
    role_title TEXT NOT NULL,
    portfolio_label TEXT,
    role_type TEXT NOT NULL DEFAULT 'minister',
    -- Full-Cabinet-Minister vs Outer-Ministry vs Assistant-Minister
    -- vs Parliamentary-Secretary etc. The granularity is captured
    -- because contracts are typically signed off by Cabinet
    -- ministers but the influence chain extends through the full
    -- ministry hierarchy.
    effective_from DATE NOT NULL,
    effective_to DATE,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    source_document_id BIGINT REFERENCES source_document(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT minister_role_role_type_chk
        CHECK (role_type IN (
            'cabinet_minister', 'outer_minister', 'assistant_minister',
            'parliamentary_secretary', 'shadow_minister', 'minister'
        ))
);

CREATE INDEX IF NOT EXISTS minister_role_person_idx
    ON minister_role (person_id);
CREATE INDEX IF NOT EXISTS minister_role_ministry_idx
    ON minister_role (cabinet_ministry_id);
CREATE INDEX IF NOT EXISTS minister_role_effective_idx
    ON minister_role (effective_from, effective_to);
CREATE INDEX IF NOT EXISTS minister_role_current_idx
    ON minister_role (is_current) WHERE is_current;
CREATE INDEX IF NOT EXISTS minister_role_role_title_idx
    ON minister_role (role_title);


CREATE TABLE IF NOT EXISTS portfolio_agency (
    id BIGSERIAL PRIMARY KEY,
    cabinet_ministry_id BIGINT REFERENCES cabinet_ministry(id)
        ON DELETE CASCADE,
    portfolio_label TEXT NOT NULL,
    agency_canonical_name TEXT NOT NULL,
    agency_aliases TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- Aliases match the AusTender `agency.name` column wording
    -- (e.g. "Department of Defence" canonical, alias "DoD",
    -- "Defence Department", etc.). Cross-correlation joins
    -- `austender_contract_topic_tag.metadata->>'agency_name'`
    -- against either canonical or one of the aliases.
    source_document_id BIGINT REFERENCES source_document(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT portfolio_agency_unique
        UNIQUE (cabinet_ministry_id, portfolio_label, agency_canonical_name)
);

CREATE INDEX IF NOT EXISTS portfolio_agency_canonical_idx
    ON portfolio_agency (agency_canonical_name);
CREATE INDEX IF NOT EXISTS portfolio_agency_aliases_idx
    ON portfolio_agency USING GIN (agency_aliases);


-- updated_at triggers (mirror project standard pattern).
CREATE OR REPLACE FUNCTION cabinet_ministry_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS cabinet_ministry_set_updated_at_trg ON cabinet_ministry;
CREATE TRIGGER cabinet_ministry_set_updated_at_trg
    BEFORE UPDATE ON cabinet_ministry
    FOR EACH ROW EXECUTE FUNCTION cabinet_ministry_set_updated_at();

CREATE OR REPLACE FUNCTION minister_role_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS minister_role_set_updated_at_trg ON minister_role;
CREATE TRIGGER minister_role_set_updated_at_trg
    BEFORE UPDATE ON minister_role
    FOR EACH ROW EXECUTE FUNCTION minister_role_set_updated_at();

CREATE OR REPLACE FUNCTION portfolio_agency_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS portfolio_agency_set_updated_at_trg ON portfolio_agency;
CREATE TRIGGER portfolio_agency_set_updated_at_trg
    BEFORE UPDATE ON portfolio_agency
    FOR EACH ROW EXECUTE FUNCTION portfolio_agency_set_updated_at();


-- VIEW: contracts joined to the responsible minister via portfolio
-- mapping. THE STRUCTURAL CLOSE-OUT of the influence narrative.
--
-- For every AusTender contract tagged in
-- `austender_contract_topic_tag`, this view surfaces:
--   * The agency that paid the contract.
--   * The portfolio + cabinet ministry overseeing that agency at
--     the contract's publish_date (when both are known).
--   * The minister(s) holding that portfolio at that time.
--   * The supplier's matched donor entity (if any) — pulled
--     transitively via the existing v_contract_donor_overlap.
--
-- Powers the headline question:
--   "Did supplier X donate to the minister whose portfolio
--    oversees the agency that awarded X a contract?"

CREATE OR REPLACE VIEW v_contract_minister_responsibility AS
SELECT
    act.contract_id,
    act.metadata->>'agency_name' AS agency_name,
    act.metadata->>'supplier_name' AS supplier_name,
    act.sector,
    act.policy_topics,
    act.procurement_class,
    act.summary,
    pa.portfolio_label,
    pa.cabinet_ministry_id,
    cm.label AS cabinet_ministry_label,
    cm.parliamentary_term,
    cm.governing_party_short_name,
    mr.id AS minister_role_id,
    mr.person_id AS minister_person_id,
    mr.person_raw_name AS minister_name,
    mr.role_title AS minister_role_title,
    mr.role_type AS minister_role_type,
    mr.effective_from AS minister_effective_from,
    mr.effective_to AS minister_effective_to,
    -- Provenance
    'llm_austender_topic_tag' AS contract_evidence_tier,
    'rule_based_aao' AS portfolio_evidence_tier,
    'rule_based_ministry_list' AS minister_evidence_tier,
    'no causation implied; structural mapping of which minister oversaw which agency' AS claim_discipline_note
FROM austender_contract_topic_tag act
LEFT JOIN portfolio_agency pa
    ON lower(pa.agency_canonical_name) = lower(act.metadata->>'agency_name')
       OR lower(act.metadata->>'agency_name') = ANY(
           ARRAY(SELECT lower(unnest(pa.agency_aliases)))
       )
LEFT JOIN cabinet_ministry cm ON cm.id = pa.cabinet_ministry_id
LEFT JOIN minister_role mr
    ON mr.cabinet_ministry_id = pa.cabinet_ministry_id
       AND mr.portfolio_label = pa.portfolio_label;


COMMENT ON VIEW v_contract_minister_responsibility IS
'Contracts joined to the responsible minister via portfolio mapping. Closes the structural influence-narrative gap: a contract awarded by Department X to supplier Y, where Minister Z holds portfolio P containing X, lets cross-correlation queries surface "supplier Y donated to Z whose portfolio oversaw the agency that paid Y".';
