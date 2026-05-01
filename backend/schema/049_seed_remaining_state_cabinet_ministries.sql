-- 049_seed_remaining_state_cabinet_ministries.sql
--
-- Extends the Batch BB-6 state cabinet seed (NSW, VIC, QLD —
-- migration 048) to cover the remaining 5 states + territories:
-- WA, SA, TAS, ACT, NT. Combined with the federal Albanese 2nd
-- Cabinet (migration 045), this gives portfolio→agency→minister
-- mapping for ALL Australian governments — federal, every state,
-- every territory.
--
-- Source: official government cabinet pages
--   * WA: https://www.wa.gov.au/government/wa-government-ministers
--   * SA: https://www.premier.sa.gov.au/government
--   * TAS: https://www.premier.tas.gov.au/ministers
--   * ACT: https://www.cmtedd.act.gov.au/about-the-department/the-act-government
--   * NT: https://nt.gov.au/page/cabinet-ministers
--
-- Current as of 2026-05-01:
--   * WA: Cook Labor Government (since 2023-06-08, after McGowan)
--   * SA: Malinauskas Labor Government (since 2022-03-21)
--   * TAS: Rockliff Liberal Government (since 2022-04-08, minority since 2024)
--   * ACT: Barr Labor Government (since 2014-12-11, longest-serving Chief Minister)
--   * NT: Finocchiaro CLP Government (since 2024-08-27, after Lawler)
--
-- Idempotent via WHERE NOT EXISTS.

-- ===========================================================
-- WA: Cook Labor Government
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Cook WA Labor Government (post-McGowan 2023)',
    'Cook WA',
    'WA-41',
    'WA Labor',
    j.id,
    DATE '2023-06-08',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.wa.gov.au/government/wa-government-ministers',
        'seed_note', 'Successor to McGowan ministry; major-state #4 (after NSW + VIC + QLD).'
    )
FROM jurisdiction j
WHERE j.code = 'WA' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Cook WA Labor Government (post-McGowan 2023)');

INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Premier', 'Department of the Premier and Cabinet (WA)', ARRAY['WA DPC']),
    ('Treasurer', 'Department of Treasury (WA)', ARRAY['WA Treasury']),
    ('Health', 'WA Health', ARRAY['Department of Health WA']),
    ('Education', 'Department of Education (WA)', ARRAY['WA Education']),
    ('Police', 'Western Australia Police Force', ARRAY['WA Police']),
    ('Transport', 'Department of Transport (WA)', ARRAY['WA Transport']),
    ('Mines and Petroleum', 'Department of Energy, Mines, Industry Regulation and Safety (WA)',
     ARRAY['DEMIRS', 'WA Mines Department']),
    ('Climate Change and the Environment', 'Department of Water and Environmental Regulation (WA)',
     ARRAY['DWER', 'WA DWER'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Cook WA Labor Government (post-McGowan 2023)'
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
    'cabinet_minister', DATE '2023-06-08', TRUE,
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Roger Cook', 'Premier of Western Australia', 'Premier'),
    ('Rita Saffioti', 'Deputy Premier and Treasurer', 'Treasurer'),
    ('Amber-Jade Sanderson', 'Minister for Health', 'Health'),
    ('Tony Buti', 'Minister for Education', 'Education'),
    ('Paul Papalia', 'Minister for Police', 'Police'),
    ('David Michael', 'Minister for Transport', 'Transport'),
    ('David Michael', 'Minister for Ports', 'Mines and Petroleum'),
    ('Reece Whitby', 'Minister for Environment and Climate Action', 'Climate Change and the Environment')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Cook WA Labor Government (post-McGowan 2023)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
      AND mr.role_title = m.role_title
  );

-- ===========================================================
-- SA: Malinauskas Labor Government
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Malinauskas SA Labor Government (post-2022 election)',
    'Malinauskas SA',
    'SA-55',
    'SA Labor',
    j.id,
    DATE '2022-03-21',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.premier.sa.gov.au/government',
        'seed_note', 'Major-state #5 in seed expansion.'
    )
FROM jurisdiction j
WHERE j.code = 'SA' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Malinauskas SA Labor Government (post-2022 election)');

INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Premier', 'Department of the Premier and Cabinet (SA)', ARRAY['SA DPC']),
    ('Treasurer', 'Department of Treasury and Finance (SA)', ARRAY['SA Treasury']),
    ('Health', 'SA Health', ARRAY['Department of Health and Wellbeing (SA)']),
    ('Education', 'Department for Education (SA)', ARRAY['SA Education']),
    ('Police', 'South Australia Police', ARRAY['SAPOL']),
    ('Infrastructure and Transport', 'Department for Infrastructure and Transport (SA)', ARRAY['DIT', 'SA Transport'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Malinauskas SA Labor Government (post-2022 election)'
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
    'cabinet_minister', DATE '2022-03-21', TRUE,
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Peter Malinauskas', 'Premier of South Australia', 'Premier'),
    ('Susan Close', 'Deputy Premier', 'Premier'),
    ('Stephen Mullighan', 'Treasurer', 'Treasurer'),
    ('Chris Picton', 'Minister for Health and Wellbeing', 'Health'),
    ('Blair Boyer', 'Minister for Education, Training and Skills', 'Education'),
    ('Joe Szakacs', 'Minister for Police', 'Police'),
    ('Tom Koutsantonis', 'Minister for Infrastructure and Transport', 'Infrastructure and Transport')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Malinauskas SA Labor Government (post-2022 election)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
  );

-- ===========================================================
-- TAS: Rockliff Liberal Government
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Rockliff TAS Liberal Government (since 2022)',
    'Rockliff TAS',
    'TAS-50',
    'TAS Liberal',
    j.id,
    DATE '2022-04-08',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.premier.tas.gov.au/ministers',
        'seed_note', 'Minority government since 2024 election.'
    )
FROM jurisdiction j
WHERE j.code = 'TAS' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Rockliff TAS Liberal Government (since 2022)');

INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Premier', 'Department of Premier and Cabinet (TAS)', ARRAY['TAS DPC']),
    ('Treasurer', 'Department of Treasury and Finance (TAS)', ARRAY['TAS Treasury']),
    ('Health', 'Department of Health (TAS)', ARRAY['TAS Health']),
    ('Education', 'Department for Education, Children and Young People (TAS)', ARRAY['TAS Education']),
    ('Police', 'Tasmania Police', ARRAY['TasPol']),
    ('Infrastructure', 'Department of State Growth (TAS)', ARRAY['TAS State Growth'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Rockliff TAS Liberal Government (since 2022)'
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
    'cabinet_minister', DATE '2022-04-08', TRUE,
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Jeremy Rockliff', 'Premier of Tasmania', 'Premier'),
    ('Guy Barnett', 'Treasurer', 'Treasurer'),
    ('Jacquie Petrusma', 'Minister for Health', 'Health'),
    ('Roger Jaensch', 'Minister for Education', 'Education'),
    ('Felix Ellis', 'Minister for Police, Fire and Emergency Management', 'Police'),
    ('Eric Abetz', 'Minister for Business, Industry and Resources', 'Infrastructure')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Rockliff TAS Liberal Government (since 2022)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
  );

-- ===========================================================
-- ACT: Barr Labor Government
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Barr ACT Labor Government (since 2014)',
    'Barr ACT',
    'ACT-11',
    'ACT Labor',
    j.id,
    DATE '2014-12-11',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.cmtedd.act.gov.au/about-the-department/the-act-government',
        'seed_note', 'Australia''s longest-serving Chief Minister; ACT is also a federal-electorate territory.'
    )
FROM jurisdiction j
WHERE j.code = 'ACT' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Barr ACT Labor Government (since 2014)');

INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Chief Minister', 'Chief Minister, Treasury and Economic Development Directorate (ACT)', ARRAY['CMTEDD', 'ACT Chief Minister']),
    ('Treasury', 'ACT Treasury', ARRAY['Treasury Directorate ACT']),
    ('Health', 'ACT Health Directorate', ARRAY['ACT Health']),
    ('Education', 'Education Directorate (ACT)', ARRAY['ACT Education']),
    ('Justice and Community Safety', 'Justice and Community Safety Directorate (ACT)', ARRAY['JACS', 'ACT Justice']),
    ('Transport and City Services', 'Transport Canberra and City Services Directorate', ARRAY['TCCS', 'ACT Transport'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Barr ACT Labor Government (since 2014)'
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
    'cabinet_minister', DATE '2014-12-11', TRUE,
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Andrew Barr', 'Chief Minister and Treasurer', 'Chief Minister'),
    ('Yvette Berry', 'Deputy Chief Minister and Minister for Education and Youth Affairs', 'Education'),
    ('Rachel Stephen-Smith', 'Minister for Health', 'Health'),
    ('Shane Rattenbury', 'Attorney-General', 'Justice and Community Safety'),
    ('Chris Steel', 'Minister for Transport and City Services', 'Transport and City Services')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Barr ACT Labor Government (since 2014)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
  );

-- ===========================================================
-- NT: Finocchiaro CLP Government
-- ===========================================================

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    jurisdiction_id, effective_from, is_current, metadata
)
SELECT
    'Finocchiaro NT CLP Government (post-2024 election)',
    'Finocchiaro NT',
    'NT-15',
    'CLP',
    j.id,
    DATE '2024-08-27',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://nt.gov.au/page/cabinet-ministers',
        'seed_note', 'CLP returned to government after Lawler Labor period.'
    )
FROM jurisdiction j
WHERE j.code = 'NT' AND j.level = 'state'
  AND NOT EXISTS (SELECT 1 FROM cabinet_ministry WHERE label = 'Finocchiaro NT CLP Government (post-2024 election)');

INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Chief Minister', 'Department of the Chief Minister and Cabinet (NT)', ARRAY['NT DCMC']),
    ('Treasurer', 'Department of Treasury and Finance (NT)', ARRAY['NT Treasury']),
    ('Health', 'NT Health', ARRAY['Department of Health (NT)']),
    ('Education', 'Department of Education (NT)', ARRAY['NT Education']),
    ('Police, Fire and Emergency Services', 'Northern Territory Police', ARRAY['NT Police', 'NTPOL']),
    ('Mining and Industry', 'Department of Mining and Industry (NT)', ARRAY['DIPL', 'NT Mining'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Finocchiaro NT CLP Government (post-2024 election)'
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
    'cabinet_minister', DATE '2024-08-27', TRUE,
    jsonb_build_object('seed_source', '049_seed_remaining_state_cabinet_ministries.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Lia Finocchiaro', 'Chief Minister of the Northern Territory', 'Chief Minister'),
    ('Bill Yan', 'Treasurer', 'Treasurer'),
    ('Steve Edgington', 'Minister for Health', 'Health'),
    ('Jo Hersey', 'Minister for Education', 'Education'),
    ('Robyn Cahill', 'Minister for Police, Fire and Emergency Services', 'Police, Fire and Emergency Services'),
    ('Gerard Maley', 'Minister for Mining and Industry', 'Mining and Industry')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Finocchiaro NT CLP Government (post-2024 election)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
  );

-- ===========================================================
-- Resolve person_raw_name → person_id where possible. State + NT
-- MPs are NOT typically in the federal `person` table; this UPDATE
-- is mostly a no-op until state member ingestion lands.
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
