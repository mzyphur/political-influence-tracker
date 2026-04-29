# Data Sources

Last updated: 2026-04-29

## Federal Sources

| Source ID | Source | URL | Use | Notes |
| --- | --- | --- | --- | --- |
| `aec_transparency_home` | AEC Transparency Register | https://transparency.aec.gov.au/ | Core federal disclosure portal | Hosts annual, election, referendum, entity, and download pages. |
| `aec_transparency_downloads` | AEC download page | https://transparency.aec.gov.au/Download | Bulk disclosure downloads | Exports are zip files split by annual/election/referendum disclosure returns. |
| `aec_annual_detailed_receipts` | AEC annual detailed receipts | https://transparency.aec.gov.au/AnnualDetailedReceipts | Receipts above disclosure threshold | Includes political parties, significant third parties, and associated entities from 1998-99 onwards. |
| `aec_download_all_election_data` | AEC all election disclosure data ZIP | https://transparency.aec.gov.au/Download/AllElectionsData | Election-period donation, benefit, and advertising rows | Detail rows are normalized as disclosure observations. Cross-table duplicate observations are retained for evidence but excluded from reported-total sums. Aggregate-only return summary tables are intentionally not normalized as transactions. |
| `aec_member_senator_returns` | AEC MP/Senator annual returns | https://transparency.aec.gov.au/MemberOfParliament | MP/Senator financial returns | May require dynamic table/export handling. |
| `aec_disclosure_threshold` | AEC disclosure threshold | https://www.aec.gov.au/Parties_and_Representatives/public_funding/threshold.htm | Legal thresholds by year | Threshold is more than $17,300 for 2025-07-01 to 2026-06-30. |
| `aec_fad_reform` | AEC funding and disclosure reform | https://www.aec.gov.au/news/disclosure-legislative-changes.htm | Reform timeline | Major reforms commence 2026-07-01, including $5,000 threshold and expedited disclosure. |
| `aph_members_interests_48` | House Register of Members' Interests | https://www.aph.gov.au/senators_and_members/members/register | Gifts, interests, travel, holdings | PDFs by member. |
| `aph_senators_interests` | Senate Register of Senators' Interests | https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests/Senators_Interests_Register | Senator interests | Official page loads a React app backed by a public JSON API discovered through `env.js`; archive the page, env asset, query JSON, and detail JSON. |
| `aph_contacts_csv` | Parliament CSV files | https://www.aph.gov.au/Senators_and_Members/Contacting_Senators_and_Members/Address_labels_and_CSV_files | Current MP/Senator roster seed | CSV files by name, state, party, gender. |
| `aec_federal_boundaries_gis` | AEC federal boundary GIS data | https://www.aec.gov.au/Electorates/gis/gis_datadownload.htm | Electorate maps | Current 2025 national ESRI shapefile is archived and transformed to GeoJSON/PostGIS; source CRS is GDA94/EPSG:4283 and loaded geometry SRID is 4326. |
| `aims_australian_coastline_50k_2024_simp` | Australian Coastline 50K 2024 simplified | https://data.gov.au/data/dataset/australian-coastline-50k-2024-nesp-mac-3-17-aims | Preferred display-only land clipping | Australian coastline and surrounding-island land-area polygons from AIMS/eAtlas/AODN, derived from 2022-2024 Sentinel-2 imagery. Used only to derive `land_clipped_display` map geometry; official AEC geometries remain preserved unchanged in `electorate_boundary.geom`. The catalogue currently lists licence as "Not Specified"; do not redistribute raw/processed coastline files publicly until licence is confirmed. |
| `natural_earth_admin0_countries_10m` + `natural_earth_physical_land_10m` | Natural Earth country and physical land layers | https://www.naturalearthdata.com/ | Fallback display-only land clipping | Public-domain display masks retained as fallback/general-country masks. They are no longer preferred for Australian federal electorate display geometry because the coastline is too coarse for shore-level UI inspection. |
| `aec_electorate_finder` | AEC electorate finder | https://electorate.aec.gov.au/ | Address/locality/postcode to federal electorate lookup | Active for reproducible postcode candidate search through archived AEC postcode result pages. Must preserve ambiguity because a postcode or locality may map to more than one federal electorate; results are candidates, not address-level determinations, and may reflect next-election boundaries rather than current-member boundaries after redistributions. |
| `abs_postal_areas` | ABS ASGS Postal Areas | https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files | Postal Area geometry approximation | Planned secondary search/map approximation. Postal Areas are not identical to Australia Post delivery postcodes and must be labelled as approximate. |
| `they_vote_for_you_api` | They Vote For You API | https://theyvoteforyou.org.au/help/data | Division and person-level vote data | Requires API key. Implemented as optional ingestion with API-key-free metadata and public response bodies preserved; civic source, not official source of record. |
| `aph_hansard` | Parliament of Australia Hansard | https://www.aph.gov.au/Hansard | Official transcript/report context | Useful for speech and proceeding context; not the sole formal division record. |
| `aph_house_votes_and_proceedings` | House Votes and Proceedings | https://www.aph.gov.au/Parliamentary_Business/Chamber_documents/HoR/Votes_and_Proceedings | Official House decision record | Formal record for House proceedings, decisions, attendance, and divisions. Current index links and ParlInfo snapshots are archived; person-vote parsing is still pending for House formats. |
| `aph_senate_journals` | Journals of the Senate | https://www.aph.gov.au/About_Parliament/Senate/Powers_practice_n_procedures/~/~/link.aspx?_id=732F8182C02D4B3699E417F33843A933 | Official Senate decision record | Current/historical journal links; records include senators voting in divisions. Current Senate PDF snapshots are parsed into official division/person-vote rows. |
| `open_australia_api` | OpenAustralia API | https://www.openaustralia.org.au/api/ | Hansard and member data context | Legacy civic source. |
| `australian_lobbyists_register` | Australian Government Register of Lobbyists | https://www.ag.gov.au/integrity/australian-government-register-lobbyists | Lobbyists and clients | Important for money plus access analysis. |
| `centre_public_integrity_lobbyists` | Centre for Public Integrity Lobbyist Register | https://publicintegrity.org.au/lobbyist-register/about-2/ | Searchable lobbying context | Civic enhancement of official lobbyist data. |
| `asic_companies_dataset` | ASIC company dataset | https://www.data.gov.au/data/dataset/asic-companies | Company identifiers and names | Weekly company register extract. |
| `acnc_register` | ACNC Registered Charities | https://data.gov.au/data/dataset/acnc-register | Charity ABNs, names, purposes | Weekly charity-register extract; some withheld records are absent. |
| `abn_lookup` | ABN Lookup | https://abr.business.gov.au/home | ABN public lookup | Public ABR view plus targeted document-style web-service lookups using `SearchByABNv202001` and `SearchByASICv201408`; ANZSIC is not public in standard ABN Lookup. Trading names are historical-only after May 2012 and have no legal status. |
| `abs_anzsic` | ABS ANZSIC classification | https://www.abs.gov.au/statistics/classifications/australian-and-new-zealand-standard-industrial-classification-anzsic | Industry taxonomy | Official industry code hierarchy. |
| `nacc_corrupt_conduct` | NACC corrupt conduct guidance | https://www.nacc.gov.au/reporting-and-investigating-corruption/what-corrupt-conduct | Integrity language and legal caution | Helps keep public claims precise. |

## State and Territory Sources To Expand

These seed records are now in `backend/au_politics_money/ingest/sources.py`.
The detailed sequencing and theory rationale are in
`docs/state_council_expansion_plan.md`.
The first three high-priority seed pages also support reproducible
`discover-links` runs, which write filtered official parser-target inventories
under `data/processed/discovered_links/`.

| Source ID | Jurisdiction | Source | URL | Notes |
| --- | --- | --- | --- | --- |
| `nsw_electoral_disclosures` | NSW | NSW Electoral Commission disclosures | https://elections.nsw.gov.au/electoral-funding/disclosures/view-disclosures | State and local donations/expenditure by parties, elected members, candidates, groups, donors, third-party campaigners, and associated entities. Preserve redaction caveats. |
| `nsw_2023_state_election_pre_election_donations` | NSW | 2023 State Election pre-election donations page | https://elections.nsw.gov.au/electoral-funding/disclosures/pre-election-period-donation-disclosure/2023-nsw-state-election-donations | Official explanatory page for the 1 Oct 2022 to 25 Mar 2023 pre-election-period reportable donation window and linked disclosure surfaces. |
| `nsw_2023_state_election_donation_heatmap` | NSW | 2023 State Election donation heatmap | https://elections.nsw.gov.au/getmedia/2ea29d95-d8a4-45ee-b45b-f9f9150a8446/FDC-heat-map.html | Static official aggregate heatmap of reportable donations by donor-location district. Aggregate context only; not donor-recipient money flow or representative attribution. Preserve source caveats that the map does not show recipient locations and may exclude donor locations that cannot be mapped, plus NSWEC CC BY 4.0 attribution/no-endorsement requirements. |
| `vic_vec_disclosures` | Victoria | VEC Disclosures | https://www.vec.vic.gov.au/disclosures/ | State political donations and annual returns for candidates, elected members, parties, associated entities, nominated entities, and third-party campaigners. Council donations need a separate local-government adapter. |
| `vic_vec_funding_register` | Victoria | VEC funding register | https://www.vec.vic.gov.au/candidates-and-parties/funding/funding-register | Active reproducible DOCX adapter for public funding, administrative expenditure funding, and policy development funding. These rows are public-funding context, not private donations, gifts, personal income, or evidence of improper conduct. The VEC states affected funding/disclosure material may be under review after Hopper & Anor v State of Victoria [2026] HCA 11. |
| `qld_ecq_disclosures` | Queensland | ECQ disclosure system | https://www.ecq.qld.gov.au/donations-and-expenditure-disclosure/disclosure-of-political-donations-and-electoral-expenditure | State and local government donations, gifts, loans, and expenditure through ECQ's Electronic Disclosure System. |
| `qld_ecq_eds_public_map` | Queensland | ECQ EDS public map | https://disclosures.ecq.qld.gov.au/Map | Current state/local gift and donation map surface. The adapter archives the page, extracts current form fields, and posts those fields to the official CSV export endpoint. |
| `qld_ecq_eds_expenditures` | Queensland | ECQ EDS expenditure search | https://disclosures.ecq.qld.gov.au/Expenditures | Current state/local electoral expenditure surface. Expenditure rows are normalized as campaign-support activity, not personal receipt. |
| `qld_ecq_eds_map_export_csv` | Queensland | ECQ EDS map CSV export | https://disclosures.ecq.qld.gov.au/Map/ExportCsv | Active reproducible export endpoint for gift/donation rows. Current normalized artifact has 22,725 rows. |
| `qld_ecq_eds_expenditure_export_csv` | Queensland | ECQ EDS expenditure CSV export | https://disclosures.ecq.qld.gov.au/Expenditures/ExportCsv | Active reproducible export endpoint for electoral expenditure rows. Current normalized artifact has 27,113 rows. |
| `qld_ecq_eds_reports` | Queensland | ECQ EDS report page | https://disclosures.ecq.qld.gov.au/Report | Report-download surface. JavaScript and form behaviour are archived; report-specific CSV parsing remains pending. |
| `qld_ecq_eds_api_political_electors` | Queensland | ECQ EDS public electors API | https://disclosures.ecq.qld.gov.au/api/political/electors | Archived lookup API snapshot used for political elector/candidate review candidates. Name-only matches are not auto-attached as ECQ-backed identifiers without stronger event/electorate/role context. |
| `qld_ecq_eds_api_political_parties` | Queensland | ECQ EDS political parties API | https://disclosures.ecq.qld.gov.au/api/political/political-parties | Archived lookup API snapshot used for ECQ-backed party identifiers and aliases. |
| `qld_ecq_eds_api_associated_entities` | Queensland | ECQ EDS associated entities API | https://disclosures.ecq.qld.gov.au/api/political/organisations?DisclosureRole=AssociatedEntity | Archived lookup API snapshot used for ECQ-backed associated-entity identifiers. |
| `qld_ecq_eds_api_political_events` | Queensland | ECQ EDS political events API | https://disclosures.ecq.qld.gov.au/api/political/events | Archived lookup API snapshot for state/local event identifiers. |
| `qld_ecq_eds_api_local_groups` | Queensland | ECQ EDS local groups API | https://disclosures.ecq.qld.gov.au/api/political/local-groups | Archived lookup API snapshot used for ECQ-backed local government group identifiers. |
| `qld_ecq_eds_api_local_electorates` | Queensland | ECQ EDS local electorates API | https://disclosures.ecq.qld.gov.au/api/political/local-electorates | Archived lookup API snapshot for local electorate names and identifiers. |
| `qld_ecq_disclosure_return_archives` | Queensland | ECQ historical disclosure return archives | https://www.ecq.qld.gov.au/disclosurereturnarchives | Historical archive target. The first reproducible fetch returned HTTP 401, so this remains blocked/pending until a public access path is confirmed. |
| `sa_ecsa_funding_disclosure` | South Australia | ECSA funding and disclosure | https://www.ecsa.sa.gov.au/parties-and-candidates/funding-and-disclosure-all-participants/funding-and-disclosure-political-parties?catid=13%3Aparties-and-candidates&id=1116%3Areporting-obligations-political-parties&view=article | Party, candidate, associated-entity, and third-party return obligations. Discover concrete return downloads/forms before parsing. |
| `waec_returns_reports` | Western Australia | WAEC returns and reports | https://www.elections.wa.gov.au/returns-and-reports | Annual and election returns for gifts, income, expenditure, and reimbursements. Council records may require local CEO/council handling. |
| `tas_tec_disclosure_funding` | Tasmania | TEC disclosure and funding | https://www.tec.tas.gov.au/disclosure-and-funding/ | New disclosure and funding regime from 2025-07-01; preserve regime-start date in coverage caveats. |
| `nt_ntec_annual_returns` | Northern Territory | NTEC annual returns | https://ntec.nt.gov.au/about-us/media-and-publications/media-releases/2025/20242025-annual-returns | Annual gift returns, annual returns, candidate returns, donor returns, and election expenditure context. |
| `act_elections_funding_disclosure` | ACT | Elections ACT funding/disclosure obligations | https://www.elections.act.gov.au/funding-disclosures-and-registers/funding-and-disclosure-obligations | Gift returns, annual returns, election returns, expenditure caps, public funding, receipts, gifts, payments, and debts. Party-endorsed candidate expenditure may sit in party grouping returns. |
| `act_gift_returns_2025_2026` | ACT | Elections ACT gift returns 2025-2026 | https://www.elections.act.gov.au/funding-disclosures-and-registers/gift-returns/gift-returns-2025-2026 | Active reproducible HTML-table adapter. Current artifact has 225 rows: 206 gifts of money and 19 gifts-in-kind. The ACT threshold is a gift, or cumulative gifts from one donor, totalling $1,000 or more, so individual rows may be below $1,000. Gift-in-kind values are non-cash reported values, not cash payments. |

## Known Data Risks

- Federal annual disclosure is lagged and thresholded.
- Some receipts are not legally classified as donations.
- Associated entities can obscure original funding sources.
- Register of interests PDFs may be handwritten, scanned, amended, or inconsistent.
- Gift value may be missing or approximate.
- MP/Senator records can include spouse/partner/dependent interests, but some parts
  are confidential or redacted under parliamentary rules.
- Voting records capture divisions, not all voice votes or party-room decisions.
- Industry classification often requires inference because public ABR data does
  not expose all ANZSIC details.
- ABN Lookup web-service enrichment must remain targeted and cached unless the
  ABN Lookup terms, permitted use, and rate limits support broader automation.
- ABN Lookup trading names collected before 28 May 2012 are historical reference
  only and cannot be relied on as current legal identity evidence.
- ABN Lookup may notify web-service users that specific details have been
  withdrawn. Public data-release procedures must support deletion of affected
  raw and derived records if that occurs.
- State regimes differ materially and change over time.
- VEC public-donation disclosure pages were redirecting to the VEC maintenance
  page during the 2026-04-29 build, while the funding register remained
  available. Victoria private-donation rows therefore remain pending and should
  not be inferred from public-funding records.
