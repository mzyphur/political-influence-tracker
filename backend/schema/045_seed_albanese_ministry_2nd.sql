-- 045_seed_albanese_ministry_2nd.sql
--
-- Initial seed for the Albanese Government 2nd Ministry (post-
-- 2025 election). Hand-curated from publicly-available APH
-- ministry list + AAO. Covers MAJOR portfolios + their flagship
-- agencies for the political-influence-correlation use case.
--
-- This seed is INTENTIONALLY NOT EXHAUSTIVE — it covers the
-- portfolios most likely to surface in cross-correlation queries
-- (Defence, Health, Treasury, Infrastructure, Resources, Home
-- Affairs, Communications, etc.). A follow-up batch will add
-- assistant ministers + parliamentary secretaries + the Outer
-- Ministry once the AAO scraper lands.
--
-- Source: https://www.pm.gov.au/government/ministries (current
-- ministry list) + AAO PDFs at
-- https://www.pmc.gov.au/honours-and-symbols/commonwealth-coat-arms/administrative-arrangements-orders.
--
-- Idempotent via WHERE NOT EXISTS — safe to re-apply.

INSERT INTO cabinet_ministry (
    label, short_label, parliamentary_term, governing_party_short_name,
    effective_from, is_current, metadata
)
SELECT
    'Albanese Ministry — 2nd Cabinet (48th Parliament, post-2025 election)',
    'Albanese 2',
    '48',
    'ALP',
    DATE '2025-05-13',
    TRUE,
    jsonb_build_object(
        'source_url', 'https://www.pm.gov.au/government/ministries',
        'aao_url', 'https://www.pmc.gov.au/honours-and-symbols/commonwealth-coat-arms/administrative-arrangements-orders',
        'seed_note', 'Hand-curated initial seed covering major portfolios; extends in subsequent batches.'
    )
WHERE NOT EXISTS (
    SELECT 1 FROM cabinet_ministry
    WHERE label = 'Albanese Ministry — 2nd Cabinet (48th Parliament, post-2025 election)'
);

-- Major portfolio agencies. Aliases include common AusTender
-- spellings (with / without "Department of", abbreviations, etc.).
INSERT INTO portfolio_agency (
    cabinet_ministry_id, portfolio_label, agency_canonical_name, agency_aliases, metadata
)
SELECT
    cm.id, p.portfolio_label, p.agency_canonical_name, p.agency_aliases::TEXT[],
    jsonb_build_object('seed_source', '045_seed_albanese_ministry_2nd.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    -- Defence
    ('Defence', 'Department of Defence', ARRAY['Defence', 'Defence Materiel Organisation', 'DoD', 'Defence Australia']),
    ('Defence', 'Australian Signals Directorate', ARRAY['ASD']),
    ('Defence', 'Defence Housing Australia', ARRAY['DHA']),
    ('Defence', 'Australian Submarine Agency', ARRAY['ASA', 'Submarine Agency']),

    -- Treasury / Finance
    ('Treasury', 'Department of the Treasury', ARRAY['Treasury', 'The Treasury']),
    ('Treasury', 'Australian Taxation Office', ARRAY['ATO', 'Tax Office']),
    ('Treasury', 'Australian Bureau of Statistics', ARRAY['ABS']),
    ('Treasury', 'Australian Securities and Investments Commission', ARRAY['ASIC']),
    ('Treasury', 'Australian Prudential Regulation Authority', ARRAY['APRA']),
    ('Treasury', 'Australian Competition and Consumer Commission', ARRAY['ACCC']),
    ('Finance', 'Department of Finance', ARRAY['Finance', 'DOFA']),
    ('Finance', 'Australian Electoral Commission', ARRAY['AEC']),

    -- Health
    ('Health and Aged Care', 'Department of Health and Aged Care',
     ARRAY['Department of Health', 'Health Department', 'DoHAC', 'Health']),
    ('Health and Aged Care', 'Therapeutic Goods Administration', ARRAY['TGA']),
    ('Health and Aged Care', 'National Blood Authority', ARRAY['NBA']),
    ('Health and Aged Care', 'Aged Care Quality and Safety Commission', ARRAY['ACQSC']),
    ('Health and Aged Care', 'Australian Institute of Health and Welfare', ARRAY['AIHW']),

    -- Infrastructure / Transport
    ('Infrastructure, Transport, Regional Development, Communications and the Arts',
     'Department of Infrastructure, Transport, Regional Development, Communications and the Arts',
     ARRAY['Infrastructure Department', 'DITRDCA']),
    ('Infrastructure, Transport, Regional Development, Communications and the Arts',
     'Infrastructure Australia', ARRAY['IA']),
    ('Infrastructure, Transport, Regional Development, Communications and the Arts',
     'Civil Aviation Safety Authority', ARRAY['CASA']),
    ('Infrastructure, Transport, Regional Development, Communications and the Arts',
     'Australian Communications and Media Authority', ARRAY['ACMA']),
    ('Infrastructure, Transport, Regional Development, Communications and the Arts',
     'NBN Co Limited', ARRAY['NBN', 'NBN Co']),

    -- Industry / Resources
    ('Industry, Science and Resources',
     'Department of Industry, Science and Resources',
     ARRAY['DISR', 'Industry Department']),
    ('Industry, Science and Resources',
     'CSIRO', ARRAY['Commonwealth Scientific and Industrial Research Organisation']),
    ('Industry, Science and Resources', 'Geoscience Australia', ARRAY['GA']),
    ('Industry, Science and Resources', 'IP Australia', ARRAY[]::TEXT[]),

    -- Climate / Energy
    ('Climate Change, Energy, the Environment and Water',
     'Department of Climate Change, Energy, the Environment and Water',
     ARRAY['DCCEEW', 'Climate Department', 'Environment Department']),
    ('Climate Change, Energy, the Environment and Water',
     'Clean Energy Regulator', ARRAY['CER']),
    ('Climate Change, Energy, the Environment and Water',
     'Australian Renewable Energy Agency', ARRAY['ARENA']),
    ('Climate Change, Energy, the Environment and Water',
     'Bureau of Meteorology', ARRAY['BoM', 'BOM']),

    -- Home Affairs / Immigration
    ('Home Affairs', 'Department of Home Affairs',
     ARRAY['Home Affairs', 'DHA Home Affairs']),
    ('Home Affairs', 'Australian Border Force', ARRAY['ABF']),
    ('Home Affairs', 'Australian Federal Police', ARRAY['AFP']),
    ('Home Affairs', 'Australian Security Intelligence Organisation', ARRAY['ASIO']),

    -- Foreign Affairs
    ('Foreign Affairs', 'Department of Foreign Affairs and Trade',
     ARRAY['DFAT', 'Foreign Affairs']),
    ('Foreign Affairs', 'Australian Trade and Investment Commission', ARRAY['Austrade']),

    -- Attorney-General
    ('Attorney-General', 'Attorney-General''s Department',
     ARRAY['AGD', 'AG''s Department']),
    ('Attorney-General', 'Federal Court of Australia', ARRAY['FCA', 'Federal Court']),
    ('Attorney-General', 'Australian Government Solicitor', ARRAY['AGS']),

    -- Veterans
    ('Veterans'' Affairs', 'Department of Veterans'' Affairs',
     ARRAY['DVA', 'Veterans Affairs']),

    -- Education
    ('Education', 'Department of Education', ARRAY['Education Department']),

    -- Employment
    ('Employment and Workplace Relations',
     'Department of Employment and Workplace Relations',
     ARRAY['DEWR']),
    ('Employment and Workplace Relations', 'Fair Work Ombudsman', ARRAY['FWO']),
    ('Employment and Workplace Relations', 'Fair Work Commission', ARRAY['FWC']),

    -- Social Services / NDIS
    ('Social Services', 'Department of Social Services', ARRAY['DSS']),
    ('Social Services', 'Services Australia', ARRAY['Centrelink', 'Medicare', 'Department of Human Services', 'DHS']),
    ('NDIS', 'National Disability Insurance Agency', ARRAY['NDIA']),

    -- Agriculture
    ('Agriculture, Fisheries and Forestry',
     'Department of Agriculture, Fisheries and Forestry',
     ARRAY['DAFF', 'Agriculture Department']),

    -- PM&C
    ('Prime Minister and Cabinet',
     'Department of the Prime Minister and Cabinet',
     ARRAY['PM&C', 'PMC']),
    ('Prime Minister and Cabinet', 'National Indigenous Australians Agency', ARRAY['NIAA']),

    -- Housing
    ('Housing', 'Housing Australia', ARRAY['NHFIC', 'National Housing Finance and Investment Corporation'])
) AS p(portfolio_label, agency_canonical_name, agency_aliases)
WHERE cm.label = 'Albanese Ministry — 2nd Cabinet (48th Parliament, post-2025 election)'
  AND NOT EXISTS (
    SELECT 1 FROM portfolio_agency pa
    WHERE pa.cabinet_ministry_id = cm.id
      AND pa.portfolio_label = p.portfolio_label
      AND pa.agency_canonical_name = p.agency_canonical_name
  );


-- Senior Cabinet ministers (publicly known as of seed date). The
-- person_id column is left NULL — to be populated by a follow-up
-- script that resolves person_raw_name → person.id via the
-- existing person table. effective_from = sworn-in date for the
-- 2nd Albanese Ministry.
INSERT INTO minister_role (
    cabinet_ministry_id, person_raw_name, role_title, portfolio_label,
    role_type, effective_from, is_current, metadata
)
SELECT
    cm.id, m.person_raw_name, m.role_title, m.portfolio_label,
    'cabinet_minister', DATE '2025-05-13', TRUE,
    jsonb_build_object('seed_source', '045_seed_albanese_ministry_2nd.sql')
FROM cabinet_ministry cm,
LATERAL (VALUES
    ('Anthony Albanese', 'Prime Minister', 'Prime Minister and Cabinet'),
    ('Richard Marles', 'Deputy Prime Minister and Minister for Defence', 'Defence'),
    ('Penny Wong', 'Minister for Foreign Affairs', 'Foreign Affairs'),
    ('Jim Chalmers', 'Treasurer', 'Treasury'),
    ('Katy Gallagher', 'Minister for Finance and Minister for the Public Service', 'Finance'),
    ('Tony Burke', 'Minister for Home Affairs', 'Home Affairs'),
    ('Mark Dreyfus', 'Attorney-General', 'Attorney-General'),
    ('Mark Butler', 'Minister for Health and Aged Care', 'Health and Aged Care'),
    ('Catherine King', 'Minister for Infrastructure, Transport, Regional Development and Local Government', 'Infrastructure, Transport, Regional Development, Communications and the Arts'),
    ('Ed Husic', 'Minister for Industry and Science', 'Industry, Science and Resources'),
    ('Madeleine King', 'Minister for Resources and Minister for Northern Australia', 'Industry, Science and Resources'),
    ('Chris Bowen', 'Minister for Climate Change and Energy', 'Climate Change, Energy, the Environment and Water'),
    ('Tanya Plibersek', 'Minister for Environment and Water', 'Climate Change, Energy, the Environment and Water'),
    ('Murray Watt', 'Minister for Employment and Workplace Relations', 'Employment and Workplace Relations'),
    ('Amanda Rishworth', 'Minister for Social Services', 'Social Services'),
    ('Bill Shorten', 'Minister for the National Disability Insurance Scheme and Minister for Government Services', 'NDIS'),
    ('Matt Keogh', 'Minister for Veterans'' Affairs and Minister for Defence Personnel', 'Veterans'' Affairs'),
    ('Jason Clare', 'Minister for Education', 'Education'),
    ('Julie Collins', 'Minister for Agriculture, Fisheries and Forestry', 'Agriculture, Fisheries and Forestry'),
    ('Clare O''Neil', 'Minister for Housing and Minister for Homelessness', 'Housing')
) AS m(person_raw_name, role_title, portfolio_label)
WHERE cm.label = 'Albanese Ministry — 2nd Cabinet (48th Parliament, post-2025 election)'
  AND NOT EXISTS (
    SELECT 1 FROM minister_role mr
    WHERE mr.cabinet_ministry_id = cm.id
      AND mr.person_raw_name = m.person_raw_name
      AND mr.role_title = m.role_title
  );


-- Resolve person_raw_name → person_id where a match exists in the
-- person table. UPDATE to attach person_id when first_name +
-- last_name match. Idempotent.
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
