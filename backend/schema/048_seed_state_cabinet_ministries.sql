-- 048_seed_state_cabinet_ministries.sql
--
-- Initial seed for current state cabinet ministries (NSW, VIC,
-- QLD — the three most populous states; covers ~75% of Australians).
-- WA, SA, TAS, ACT, NT to follow in subsequent batches.
--
-- Each seeded ministry includes:
--   * Cabinet ministry row (cabinet_ministry).
--   * Portfolio-agency mappings (portfolio_agency) for the
--     state's major departments.
--   * Premier + key cabinet ministers (minister_role).
--
-- Rationale: state-level portfolio mapping enables the
-- cross-correlation views to handle state political-influence
-- patterns once state contract data is loaded (currently
-- federal-only). State donor → state minister → state agency
-- → state contract chain mirrors the federal one.
--
-- Source: official state government cabinet pages
--   * NSW: https://www.nsw.gov.au/our-government/ministers
--   * VIC: https://www.premier.vic.gov.au/ministers-and-cabinet
--   * QLD: https://www.qld.gov.au/about/how-government-works/government-leadership
--
-- All three current as of 2026-05-01:
--   * NSW: Minns Labor Government (since 2023-03-28)
--   * VIC: Allan Labor Government (since 2023-09-27, after Andrews)
--   * QLD: Crisafulli LNP Government (since 2024-10-26, after Miles)
--
-- The portfolio + agency lists are intentionally non-exhaustive
-- — focused on the agencies most likely to surface in future
-- state-contract analysis (Health, Treasury, Police, Education,
-- Transport, Infrastructure, Planning, Environment).
--
-- Idempotent via WHERE NOT EXISTS.

-- ===========================================================
-- NSW: Minns Labor Government (48th NSW Parliament)
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Minns NSW Labor Government (post-2023 election)',
    'Minns NSW',
    'NSW-58',
    'NSW Labor',
    j.id,
    DATE '2023-03-28',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.nsw.gov.au/our-government/ministers',
        'seed_note', 'NSW first major-state cabinet seed; extends with assistant ministers + parl. secretaries in follow-up.'
    )
FROM jurisdiction j
WHERE j.code = 'NSW' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Minns NSW Labor Government (post-2023 election)');

-- NSW portfolio agencies
INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '048_seed_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Premier', 'Department of the Premier and Cabinet (NSW)', ARRAY['NSW DPC', 'Premier and Cabinet NSW']),
    ('Treasury', 'NSW Treasury', ARRAY['Treasury NSW', 'Department of Treasury NSW']),
    ('Health', 'NSW Health', ARRAY['Department of Health NSW', 'NSW Department of Health', 'Ministry of Health NSW']),
    ('Education', 'NSW Department of Education', ARRAY['Education NSW', 'Department of Education NSW']),
    ('Police', 'NSW Police Force', ARRAY['NSW Police', 'New South Wales Police Force']),
    ('Transport', 'Transport for NSW', ARRAY['NSW Transport', 'TfNSW']),
    ('Planning and Public Spaces', 'Department of Planning, Housing and Infrastructure (NSW)', ARRAY['NSW Planning', 'DPHI']),
    ('Climate Change, Energy, the Environment and Heritage', 'Department of Climate Change, Energy, the Environment and Water (NSW)', ARRAY['NSW DCCEEW', 'NSW Environment Department'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Minns NSW Labor Government (post-2023 election)'
  AND NOT EXISTS (
    SELECT 1 FROM portfolio_agency pa
    WHERE pa.cabinet_ministry_id = cm.id
      AND pa.portfolio_label = p.portfolio_label
      AND pa.agency_canonical_name = p.agency_canonical_name
  );

-- NSW cabinet ministers (current as of 2026-05-01)
INSERT INTO minister_role (
    cabinet_ministry_id, person_raw_name, role_title, portfolio_label,
    role_type, effective_from, is_current, metadata
)
SELECT
    cm.id, m.person_raw_name, m.role_title, m.portfolio_label,
    'cabinet_minister', DATE '2023-03-28', TRUE,
    jsonb_build_object('seed_source', '048_seed_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Chris Minns', 'Premier of NSW', 'Premier'),
    ('Prue Car', 'Deputy Premier and Minister for Education and Early Learning', 'Education'),
    ('Daniel Mookhey', 'Treasurer', 'Treasury'),
    ('Ryan Park', 'Minister for Health', 'Health'),
    ('Yasmin Catley', 'Minister for Police and Counter-terrorism', 'Police'),
    ('Jo Haylen', 'Minister for Transport', 'Transport'),
    ('Paul Scully', 'Minister for Planning and Public Spaces', 'Planning and Public Spaces'),
    ('Penny Sharpe', 'Minister for Climate Change, Energy, the Environment and Heritage', 'Climate Change, Energy, the Environment and Heritage')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Minns NSW Labor Government (post-2023 election)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
  );


-- ===========================================================
-- VIC: Allan Labor Government (60th Victorian Parliament)
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Allan VIC Labor Government (post-Andrews 2023)',
    'Allan VIC',
    'VIC-60',
    'VIC Labor',
    j.id,
    DATE '2023-09-27',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.premier.vic.gov.au/ministers-and-cabinet',
        'seed_note', 'Successor to Andrews ministry; extends in follow-up.'
    )
FROM jurisdiction j
WHERE j.code = 'VIC' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Allan VIC Labor Government (post-Andrews 2023)');

INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '048_seed_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Premier', 'Department of Premier and Cabinet (VIC)', ARRAY['VIC DPC', 'Victorian DPC']),
    ('Treasurer', 'Department of Treasury and Finance (VIC)', ARRAY['VIC Treasury', 'DTF Victoria']),
    ('Health', 'Department of Health (VIC)', ARRAY['VIC Health', 'Victorian Health Department']),
    ('Education', 'Department of Education (VIC)', ARRAY['VIC Education', 'Victorian Education Department']),
    ('Police', 'Victoria Police', ARRAY['VicPol', 'Vic Police']),
    ('Transport and Infrastructure', 'Department of Transport and Planning (VIC)', ARRAY['VIC Transport', 'DTP Victoria']),
    ('Energy and Resources', 'Department of Energy, Environment and Climate Action (VIC)', ARRAY['VIC DEECA', 'Victorian Energy Department'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Allan VIC Labor Government (post-Andrews 2023)'
  AND NOT EXISTS (
    SELECT 1 FROM portfolio_agency pa
    WHERE pa.cabinet_ministry_id = cm.id
      AND pa.portfolio_label = p.portfolio_label
      AND pa.agency_canonical_name = p.agency_canonical_name
  );

INSERT INTO minister_role (
    cabinet_ministry_id, person_raw_name, role_title, portfolio_label,
    role_type, effective_from, is_current, metadata
)
SELECT
    cm.id, m.person_raw_name, m.role_title, m.portfolio_label,
    'cabinet_minister', DATE '2023-09-27', TRUE,
    jsonb_build_object('seed_source', '048_seed_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Jacinta Allan', 'Premier of Victoria', 'Premier'),
    ('Ben Carroll', 'Deputy Premier and Minister for Education', 'Education'),
    ('Tim Pallas', 'Treasurer', 'Treasurer'),
    ('Mary-Anne Thomas', 'Minister for Health', 'Health'),
    ('Anthony Carbines', 'Minister for Police', 'Police'),
    ('Gabrielle Williams', 'Minister for Public and Active Transport', 'Transport and Infrastructure'),
    ('Lily D''Ambrosio', 'Minister for Climate Action, Energy and Resources', 'Energy and Resources')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Allan VIC Labor Government (post-Andrews 2023)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
  );


-- ===========================================================
-- QLD: Crisafulli LNP Government (58th Queensland Parliament)
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Crisafulli QLD LNP Government (post-2024 election)',
    'Crisafulli QLD',
    'QLD-58',
    'LNP',
    j.id,
    DATE '2024-10-26',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.qld.gov.au/about/how-government-works/government-leadership',
        'seed_note', 'First non-Labor QLD cabinet seed since 2015; extends in follow-up.'
    )
FROM jurisdiction j
WHERE j.code = 'QLD' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Crisafulli QLD LNP Government (post-2024 election)');

INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '048_seed_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Premier', 'Department of the Premier and Cabinet (QLD)', ARRAY['QLD DPC', 'Queensland DPC']),
    ('Treasurer', 'Queensland Treasury', ARRAY['QLD Treasury', 'Treasury Queensland']),
    ('Health and Ambulance Services', 'Queensland Health', ARRAY['QLD Health', 'Department of Health Queensland']),
    ('Education and the Arts', 'Department of Education (QLD)', ARRAY['QLD Education']),
    ('Police and Community Safety', 'Queensland Police Service', ARRAY['QPS', 'QLD Police']),
    ('Transport and Main Roads', 'Department of Transport and Main Roads (QLD)', ARRAY['QLD TMR', 'Transport Main Roads']),
    ('Resources and Critical Minerals', 'Department of Resources (QLD)', ARRAY['QLD Resources']),
    ('Environment and Tourism', 'Department of the Environment, Tourism, Science and Innovation (QLD)', ARRAY['QLD DETSI', 'QLD Environment'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Crisafulli QLD LNP Government (post-2024 election)'
  AND NOT EXISTS (
    SELECT 1 FROM portfolio_agency pa
    WHERE pa.cabinet_ministry_id = cm.id
      AND pa.portfolio_label = p.portfolio_label
      AND pa.agency_canonical_name = p.agency_canonical_name
  );

INSERT INTO minister_role (
    cabinet_ministry_id, person_raw_name, role_title, portfolio_label,
    role_type, effective_from, is_current, metadata
)
SELECT
    cm.id, m.person_raw_name, m.role_title, m.portfolio_label,
    'cabinet_minister', DATE '2024-10-26', TRUE,
    jsonb_build_object('seed_source', '048_seed_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('David Crisafulli', 'Premier of Queensland', 'Premier'),
    ('Jarrod Bleijie', 'Deputy Premier and Minister for State Development, Infrastructure and Planning', 'Premier'),
    ('David Janetzki', 'Treasurer and Minister for Energy and Home Ownership', 'Treasurer'),
    ('Tim Nicholls', 'Minister for Health and Ambulance Services', 'Health and Ambulance Services'),
    ('John-Paul Langbroek', 'Minister for Education and the Arts', 'Education and the Arts'),
    ('Dan Purdie', 'Minister for Police and Emergency Services', 'Police and Community Safety'),
    ('Brent Mickelberg', 'Minister for Transport and Main Roads', 'Transport and Main Roads'),
    ('Dale Last', 'Minister for Natural Resources and Mines, Manufacturing and Regional and Rural Development', 'Resources and Critical Minerals'),
    ('Andrew Powell', 'Minister for the Environment and Tourism, and Minister for Science and Innovation', 'Environment and Tourism')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Crisafulli QLD LNP Government (post-2024 election)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
  );


-- ===========================================================
-- Resolve person_raw_name → person_id where possible. State MPs
-- are NOT in the federal `person` table by default; this UPDATE
-- is mostly a no-op until state MPs are loaded. Future batch
-- (state Hansard / member ingestion) will populate matches.
-- ===========================================================

UPDATE minister_role mr
SET person_id = p.id
FROM person p
WHERE mr.person_id IS NULL
  AND mr.person_raw_name IS NOT NULL
  AND (
    lower(p.canonical_name) = lower(mr.person_raw_name)
    OR lower(p.display_name) = lower(mr.person_raw_name)
    OR lower(p.first_name || ' ' || p.last_name) = lower(mr.person_raw_name)
  );
