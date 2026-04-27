# Data Sources

Last updated: 2026-04-27

## Federal Sources

| Source ID | Source | URL | Use | Notes |
| --- | --- | --- | --- | --- |
| `aec_transparency_home` | AEC Transparency Register | https://transparency.aec.gov.au/ | Core federal disclosure portal | Hosts annual, election, referendum, entity, and download pages. |
| `aec_transparency_downloads` | AEC download page | https://transparency.aec.gov.au/Download | Bulk disclosure downloads | Exports are zip files split by annual/election/referendum disclosure returns. |
| `aec_annual_detailed_receipts` | AEC annual detailed receipts | https://transparency.aec.gov.au/AnnualDetailedReceipts | Receipts above disclosure threshold | Includes political parties, significant third parties, and associated entities from 1998-99 onwards. |
| `aec_member_senator_returns` | AEC MP/Senator annual returns | https://transparency.aec.gov.au/MemberOfParliament | MP/Senator financial returns | May require dynamic table/export handling. |
| `aec_disclosure_threshold` | AEC disclosure threshold | https://www.aec.gov.au/Parties_and_Representatives/public_funding/threshold.htm | Legal thresholds by year | Threshold is more than $17,300 for 2025-07-01 to 2026-06-30. |
| `aec_fad_reform` | AEC funding and disclosure reform | https://www.aec.gov.au/news/disclosure-legislative-changes.htm | Reform timeline | Major reforms commence 2026-07-01, including $5,000 threshold and expedited disclosure. |
| `aph_members_interests_48` | House Register of Members' Interests | https://www.aph.gov.au/senators_and_members/members/register | Gifts, interests, travel, holdings | PDFs by member. |
| `aph_senators_interests` | Senate Register of Senators' Interests | https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests/Senators_Interests_Register | Senator interests | Official page loads a React app backed by a public JSON API discovered through `env.js`; archive the page, env asset, query JSON, and detail JSON. |
| `aph_contacts_csv` | Parliament CSV files | https://www.aph.gov.au/Senators_and_Members/Contacting_Senators_and_Members/Address_labels_and_CSV_files | Current MP/Senator roster seed | CSV files by name, state, party, gender. |
| `aec_federal_boundaries_gis` | AEC federal boundary GIS data | https://www.aec.gov.au/Electorates/gis/gis_datadownload.htm | Electorate maps | Current 2025 boundaries and superseded shapefiles. |
| `they_vote_for_you_api` | They Vote For You API | https://theyvoteforyou.org.au/help/data | Division and vote data | Requires API key. Civic source, not official source of record. |
| `open_australia_api` | OpenAustralia API | https://www.openaustralia.org.au/api/ | Hansard and member data context | Legacy civic source. |
| `australian_lobbyists_register` | Australian Government Register of Lobbyists | https://www.ag.gov.au/integrity/australian-government-register-lobbyists | Lobbyists and clients | Important for money plus access analysis. |
| `centre_public_integrity_lobbyists` | Centre for Public Integrity Lobbyist Register | https://publicintegrity.org.au/lobbyist-register/about-2/ | Searchable lobbying context | Civic enhancement of official lobbyist data. |
| `asic_companies_dataset` | ASIC company dataset | https://www.data.gov.au/data/dataset/asic-companies | Company identifiers and names | Weekly company register extract. |
| `abn_lookup` | ABN Lookup | https://abr.business.gov.au/home | ABN public lookup | Public ABR view; ANZSIC is not public in standard ABN Lookup. |
| `abs_anzsic` | ABS ANZSIC classification | https://www.abs.gov.au/statistics/classifications/australian-and-new-zealand-standard-industrial-classification-anzsic | Industry taxonomy | Official industry code hierarchy. |
| `nacc_corrupt_conduct` | NACC corrupt conduct guidance | https://www.nacc.gov.au/reporting-and-investigating-corruption/what-corrupt-conduct | Integrity language and legal caution | Helps keep public claims precise. |

## State and Territory Sources To Expand

| Jurisdiction | Source | URL | Notes |
| --- | --- | --- | --- |
| NSW | NSW Electoral Commission disclosures | https://elections.nsw.gov.au/electoral-funding/disclosures/view-disclosures | Publishes donations and expenditure for at least six years. |
| Queensland | ECQ Electronic Disclosure System | https://www.ecq.qld.gov.au/donations-and-expenditure-disclosure/disclosure-of-political-donations-and-electoral-expenditure/published-disclosure-returns | Search/export by name, party, donor, electorate, date, and gift value. |
| Victoria | VEC annual returns | https://www.vec.vic.gov.au/candidates-and-parties/annual-returns | Legal/publication status needs current monitoring. |
| Western Australia | WAEC returns and reports | https://www.elections.wa.gov.au/returns-and-reports | Online Disclosure System and annual Political Finance Report. |
| South Australia | ECSA funding and disclosure | https://ecsa.sa.gov.au/parties-and-candidates/funding-and-disclosure-all-participants | Major reforms and donation ban from 2025-07-01. |
| Tasmania | TEC disclosure and funding | https://www.tec.tas.gov.au/disclosure-and-funding/registers-and-reports/returns/election-campaign-returns-report.html | Newer disclosure regime from 2025-07-01. |
| ACT | Elections ACT financial disclosure | https://www.elections.act.gov.au/ | Annual returns for parties, MLAs, and associated entities. |
| Northern Territory | NTEC financial disclosure | https://ntec.nt.gov.au/financial-disclosure/financial-disclosure-returns | Annual and election returns, including donor threshold obligations. |

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
- State regimes differ materially and change over time.
