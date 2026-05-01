-- 050_lobbyist_register_observations.sql
--
-- Stage 4b of the influence-correlation pipeline: lobbyist
-- register observations. Adds the structural surface that lets
-- the cross-correlation views reveal "Lobbyist firm L represents
-- Client X. Lobbyist L's principals donate to MPs Z, W, V.
-- Client X receives contracts from agencies overseen by Z / W
-- / V" — the canonical three-way influence pattern.
--
-- Source datasets (all public domain or CC-BY):
--   * Federal Lobbyist Register
--     https://lobbyists.ag.gov.au/register
--   * NSW Lobbyist Register
--     https://nswlrs.com.au
--   * VIC Lobbyist Register
--     https://parliament.vic.gov.au (Department of Premier and Cabinet)
--   * QLD Lobbyist Register
--     https://www.lobbyists.qld.gov.au
--   * SA Lobbyist Register
--     https://www.dpc.sa.gov.au/responsibilities/state-records-of-south-australia/sa-lobbyists-register
--   * WA Lobbyist Register
--     https://www.lobbyists.wa.gov.au
--   * TAS Lobbyist Register
--     https://www.dpac.tas.gov.au (Department of Premier and Cabinet)
--
-- Schema design (three tables):
--
-- lobbyist_organisation_record
--   * One row per lobbyist firm registered with a specific
--     jurisdiction's lobbyist register, with effective dates.
--   * Linked to the existing `entity` table via entity_id (the
--     firm itself; usually entity_type='lobbyist_organisation').
--   * The firm can appear in multiple jurisdictions' registers.
--
-- lobbyist_principal
--   * One row per (lobbyist_organisation, person) tuple — the
--     principals / directors / employees of each firm.
--   * Person-level link via person_id when a match exists in
--     the `person` table (rare for non-MPs); otherwise raw_name
--     is the only identifier.
--   * Effective dates capture when the principal joined / left.
--
-- lobbyist_client_engagement
--   * One row per (lobbyist_organisation, client_entity, jurisdiction)
--     tuple. The client is the entity the lobbyist firm represents.
--   * Captures effective dates + the policy areas the lobbyist
--     firm advocates on for that client.
--   * Critically, this is the JOIN that closes the influence
--     loop: a client received a contract from agency A while
--     their lobbyist firm L's principals donated to MP Z who
--     oversees A.
--
-- Claim discipline:
--   * All three tables are tier-1 evidence (public registers,
--     directly attributed).
--   * Joining lobbyist_client_engagement to influence_event
--     (donations) and austender_contract_topic_tag (contracts)
--     does NOT imply the lobbyist caused either event. The
--     view structure surfaces correlation; consumers interpret.

CREATE TABLE IF NOT EXISTS lobbyist_organisation_record (
    id BIGSERIAL PRIMARY KEY,
    entity_id BIGINT REFERENCES entity(id) ON DELETE SET NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    jurisdiction_id BIGINT NOT NULL REFERENCES jurisdiction(id) ON DELETE RESTRICT,
    register_url TEXT,
    abn TEXT,
    address TEXT,
    business_address_state_or_territory TEXT,
    is_currently_registered BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from DATE,
    effective_to DATE,
    source_document_id BIGINT REFERENCES source_document(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT lobbyist_organisation_record_canonical_jurisdiction_uniq
        UNIQUE (canonical_name, jurisdiction_id)
);

CREATE INDEX IF NOT EXISTS lobbyist_organisation_record_entity_idx
    ON lobbyist_organisation_record (entity_id);
CREATE INDEX IF NOT EXISTS lobbyist_organisation_record_jurisdiction_idx
    ON lobbyist_organisation_record (jurisdiction_id, is_currently_registered);
CREATE INDEX IF NOT EXISTS lobbyist_organisation_record_normalized_idx
    ON lobbyist_organisation_record (normalized_name);


CREATE TABLE IF NOT EXISTS lobbyist_principal (
    id BIGSERIAL PRIMARY KEY,
    lobbyist_organisation_id BIGINT NOT NULL
        REFERENCES lobbyist_organisation_record(id) ON DELETE CASCADE,
    person_id BIGINT REFERENCES person(id) ON DELETE SET NULL,
    person_raw_name TEXT NOT NULL,
    role_title TEXT,
    is_currently_registered BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from DATE,
    effective_to DATE,
    source_document_id BIGINT REFERENCES source_document(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT lobbyist_principal_org_person_uniq
        UNIQUE (lobbyist_organisation_id, person_raw_name, role_title)
);

CREATE INDEX IF NOT EXISTS lobbyist_principal_org_idx
    ON lobbyist_principal (lobbyist_organisation_id, is_currently_registered);
CREATE INDEX IF NOT EXISTS lobbyist_principal_person_idx
    ON lobbyist_principal (person_id);


CREATE TABLE IF NOT EXISTS lobbyist_client_engagement (
    id BIGSERIAL PRIMARY KEY,
    lobbyist_organisation_id BIGINT NOT NULL
        REFERENCES lobbyist_organisation_record(id) ON DELETE CASCADE,
    client_entity_id BIGINT REFERENCES entity(id) ON DELETE SET NULL,
    client_canonical_name TEXT NOT NULL,
    client_normalized_name TEXT NOT NULL,
    policy_topics TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- The 24-value policy-topic taxonomy from
    -- `prompts/austender_contract_topic_tag/v3.md` schema. NULL
    -- when the register entry doesn't specify topics.
    is_currently_engaged BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from DATE,
    effective_to DATE,
    source_document_id BIGINT REFERENCES source_document(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT lobbyist_client_engagement_org_client_uniq
        UNIQUE (lobbyist_organisation_id, client_canonical_name)
);

CREATE INDEX IF NOT EXISTS lobbyist_client_engagement_org_idx
    ON lobbyist_client_engagement (lobbyist_organisation_id);
CREATE INDEX IF NOT EXISTS lobbyist_client_engagement_entity_idx
    ON lobbyist_client_engagement (client_entity_id);
CREATE INDEX IF NOT EXISTS lobbyist_client_engagement_normalized_idx
    ON lobbyist_client_engagement (client_normalized_name);
CREATE INDEX IF NOT EXISTS lobbyist_client_engagement_topics_idx
    ON lobbyist_client_engagement USING GIN (policy_topics);


-- updated_at triggers (mirror project standard pattern).
CREATE OR REPLACE FUNCTION lobbyist_organisation_record_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS lobbyist_organisation_record_set_updated_at_trg
    ON lobbyist_organisation_record;
CREATE TRIGGER lobbyist_organisation_record_set_updated_at_trg
    BEFORE UPDATE ON lobbyist_organisation_record
    FOR EACH ROW EXECUTE FUNCTION lobbyist_organisation_record_set_updated_at();

CREATE OR REPLACE FUNCTION lobbyist_principal_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS lobbyist_principal_set_updated_at_trg ON lobbyist_principal;
CREATE TRIGGER lobbyist_principal_set_updated_at_trg
    BEFORE UPDATE ON lobbyist_principal
    FOR EACH ROW EXECUTE FUNCTION lobbyist_principal_set_updated_at();

CREATE OR REPLACE FUNCTION lobbyist_client_engagement_set_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS lobbyist_client_engagement_set_updated_at_trg
    ON lobbyist_client_engagement;
CREATE TRIGGER lobbyist_client_engagement_set_updated_at_trg
    BEFORE UPDATE ON lobbyist_client_engagement
    FOR EACH ROW EXECUTE FUNCTION lobbyist_client_engagement_set_updated_at();


-- VIEW: closes the lobbyist → donor → minister influence loop.
--
-- For every lobbyist client engagement, surfaces:
--   * The lobbyist organisation and its principals.
--   * The client entity being represented.
--   * The donations the client made to MPs (joined via
--     influence_event.source_entity_id → client_entity_id).
--   * The contracts awarded to the client (joined via
--     austender_contract_topic_tag.metadata->>'supplier_name'
--     → client_canonical_name).
--   * The ministers responsible for those contracts (joined via
--     v_contract_minister_responsibility).
--
-- The query enables the headline three-way correlation:
--   "Lobbyist L represents Client X.
--    Client X received $N in contracts from agencies overseen
--    by Minister Z.
--    Client X (or Lobbyist L's principals) donated $M to MPs."
--
-- Tier separation preserved: client donations (tier 1), lobbyist
-- registrations (tier 1), contracts (LLM tier 2), minister
-- responsibility (tier 1). NEVER summed across tiers.

CREATE OR REPLACE VIEW v_lobbyist_client_influence_overlap AS
SELECT
    lor.id AS lobbyist_organisation_id,
    lor.canonical_name AS lobbyist_canonical_name,
    lor.entity_id AS lobbyist_entity_id,
    j.code AS lobbyist_jurisdiction_code,
    lce.id AS engagement_id,
    lce.client_canonical_name,
    lce.client_normalized_name,
    lce.client_entity_id,
    lce.policy_topics AS engagement_policy_topics,
    -- Donations the client made (joined by entity_id when matched)
    COUNT(ie.id) FILTER (WHERE ie.event_family = 'money')
        AS client_money_event_count,
    SUM(COALESCE(ie.amount, 0)) FILTER (WHERE ie.event_family = 'money')
        AS client_total_money_aud,
    COUNT(DISTINCT ie.recipient_person_id) FILTER (WHERE ie.event_family = 'money')
        AS client_distinct_recipient_persons,
    -- Provenance
    'rule_based_lobbyist_register' AS lobbyist_evidence_tier,
    'rule_based_disclosure' AS donor_evidence_tier,
    'no causation implied; three-way correlation surface only' AS claim_discipline_note
FROM lobbyist_organisation_record lor
JOIN jurisdiction j ON j.id = lor.jurisdiction_id
JOIN lobbyist_client_engagement lce
    ON lce.lobbyist_organisation_id = lor.id
LEFT JOIN influence_event ie
    ON ie.source_entity_id = lce.client_entity_id
       AND ie.review_status != 'rejected'
WHERE lor.is_currently_registered = TRUE
  AND lce.is_currently_engaged = TRUE
GROUP BY
    lor.id, lor.canonical_name, lor.entity_id,
    j.code, lce.id, lce.client_canonical_name,
    lce.client_normalized_name, lce.client_entity_id,
    lce.policy_topics;


COMMENT ON VIEW v_lobbyist_client_influence_overlap IS
'Three-way influence correlation: lobbyist firm + client + client donations. Powers "Lobbyist L represents Client X who donated $M to recipient MPs Z" surface. Loader (Phase C-1) populates the underlying tables; this view becomes meaningful when the federal lobbyist register is loaded.';
