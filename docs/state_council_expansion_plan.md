# State and Council Expansion Plan

Last updated: 2026-04-30

This document defines the first expansion path after the federal/Commonwealth
pilot. The goal is not merely to add more rows. The goal is to preserve the same
theory of influence across levels of government while respecting each
jurisdiction's disclosure law, source structure, and missing-data patterns.

## Operating Principle

State, territory, and council influence records must use the same normalized
surfaces as the federal build:

- actors: representatives, candidates, parties, donors, entities, lobbyists, and
  office holders;
- offices: chamber, council, ward, district, electorate, office term, and party;
- geography: source-backed boundaries and valid dates;
- money: donations, gifts, loans, debts, public funding, campaign expenditure,
  and third-party activity;
- benefits: gifts, hospitality, travel, memberships, event access, and other
  non-cash benefits where registers disclose them;
- interests: assets, liabilities, roles, memberships, conflicts, and related
  registers;
- access: lobbying registers, ministerial diaries, meeting logs, and clients
  where available;
- behaviour: votes, proceedings, agendas, minutes, motions, committee roles,
  procurement/grants decisions, and policy topics where available.

The attribution rule remains unchanged: store each record at the strongest level
the source supports, and never force a party, council, district, or donor record
onto one person without explicit evidence or a labelled model.

## Why Subnational Coverage Matters

Subnational politics are central to the project's influence theory because many
high-value policy domains are state or local responsibilities: planning, zoning,
transport, mining approvals, gambling regulation, policing, procurement,
housing, infrastructure, land releases, environmental approvals, and council
development decisions.

This makes state/council expansion theoretically important in three ways:

1. It adds policy domains where donor or lobbyist interests may be more directly
   connected to government decisions.
2. It exposes variation in disclosure regimes, which is itself a democratic
   transparency variable.
3. It lets the graph model show cross-level influence paths, such as a developer
   donor or industry association appearing in council, state, and federal
   records.

## Jurisdiction Source Priorities

### NSW

Official source:
https://elections.nsw.gov.au/electoral-funding/disclosures/view-disclosures

Priority data families:

- state and local donations and electoral expenditure;
- parties, elected members, candidates, groups, political donors, third-party
  campaigners, and associated entities;
- district-level donation views for state elections;
- local government candidate disclosures where available through the NSWEC
  disclosure system.

Notes:

- NSW publishes disclosed donations and expenditure for at least six years.
- NSW explicitly notes redactions in disclosure forms; redaction status must be
  preserved rather than treated as missing extraction.

### Victoria

Official source:
https://www.vec.vic.gov.au/disclosures/

Priority data families:

- VEC Disclosures donations made and received;
- state candidates, elected members, parties, associated entities, nominated
  entities, and third-party campaigners;
- annual returns covering donations, expenditure, and debts;
- VEC funding-register DOCX files covering public funding, administrative
  expenditure funding, and policy development funding;
- indexed thresholds and caps.

Notes:

- The first active Victoria adapter is the VEC funding-register adapter. It
  gives useful party/participant public-funding context, but it is not a
  substitute for the unavailable donations portal and must never be displayed as
  private donations, gifts, personal income, or improper conduct.
- On 2026-04-29, the VEC public-donations pages redirected to the VEC
  maintenance page. The VEC funding pages state that material may be affected by
  Hopper & Anor v State of Victoria [2026] HCA 11 and may not be accurate while
  the VEC reviews affected information.
- The VEC states that local council election donations are administered through
  a separate local-government process rather than the state VEC disclosure
  surface. Council-level Victoria therefore needs a separate adapter strategy.

### Queensland

Official source:
https://www.ecq.qld.gov.au/donations-and-expenditure-disclosure/disclosure-of-political-donations-and-electoral-expenditure

Priority data families:

- Electronic Disclosure System records;
- state and local government donations, loans, and electoral expenditure;
- candidates, groups of candidates, parties, associated entities, and third-party
  campaigners;
- real-time disclosure requirements and election summary returns.

Notes:

- Queensland is a strong first council-level target because ECQ documentation
  explicitly covers state and local disclosure through the Electronic Disclosure
  System.
- The first implemented subnational adapter is the ECQ Electronic Disclosure
  System export path. It archives the public EDS map and expenditure pages,
  reuses their current hidden form fields, POSTs to the official CSV export
  endpoints, and normalizes gifts/donations and electoral expenditure into the
  same influence-event evidence surface used by the federal build.
- Queensland is also the first state map layer. The `qld_state_electoral_boundaries_arcgis`
  source archives the Queensland government ArcGIS/QSpatial state-electorate
  boundary layer, normalizes 93 current electorates, and stores land-clipped
  display geometries separately from the official source geometry. These
  boundaries support State-mode map drilldown only. ECQ disclosure rows remain
  state/local source records until a public source or reviewed model supports a
  narrower link to a state electorate, candidate, party branch, or current MP.

### South Australia

Official source:
https://www.ecsa.sa.gov.au/parties-and-candidates/disclosure-returns

Priority data families:

- party, candidate, associated entity, and third-party returns;
- amounts received, amounts paid, debts, and donation details above thresholds;
- election and periodic return schedules.

Notes:

- First implemented adapter:
  `run-state-local-pipeline --jurisdiction sa` archives the ECSA disclosure
  landing page and the current `funding2024` return-record portal, then
  normalizes 696 portal index rows into
  `data/processed/sa_ecsa_return_summary_money_flows/`. The source-row reported
  return-summary value is $472,688,444.90.
- The ECSA portal index is return-level, not transaction-level. The implemented
  row families include candidate campaign donations returns, political party
  returns, associated-entity returns, third-party returns, donor returns,
  special large-gift returns, capped-expenditure returns, prescribed
  expenditure returns, and annual political expenditure returns. These are
  useful public disclosure context, but they must not be displayed as detailed
  donor-recipient transactions or personal receipt by a candidate or MP.
- The fetcher partitions by official `For` filter values because unfiltered
  pagination can repeat or omit rows. Future SA work should parse linked return
  reports/PDFs where legally/publicly available, add ECSA-backed actor
  identifiers where the portal supports them, and deduplicate return-level
  summaries against detailed transactions before any consolidated amount totals
  are published.

### Western Australia

Official source:
https://www.elections.wa.gov.au/returns-and-reports

Current adapter status: `run-state-local-pipeline --jurisdiction wa` archives
the WAEC Online Disclosure System public dashboard and fetches the published
political contribution entity-grid JSON. It normalizes
donor-to-political-entity contribution rows into
`data/processed/waec_political_contribution_money_flows/`.

Priority data families:

- annual returns and election returns;
- gifts, income, expenditure, and electoral reimbursements;
- Online Disclosure System entries where accessible (political contributions
  are implemented first);
- local-government disclosure duties where records are obtainable.

Notes:

- WAEC political contribution rows expose donor, political entity, contribution
  type, amount, financial year, public donor postcode, status, version, and
  disclosure-received date. The disclosure-received date is not necessarily the
  contribution transaction date.
- Original-version rows are counted as source-row observations. Amendment or
  other versioned rows are preserved but excluded from reported totals until
  amendment lineage and deduplication rules are validated.
- WAEC states that local-government candidates and donors have disclosure duties,
  but also directs queries to local government CEOs. That means council coverage
  may require a hybrid adapter: state-level index plus council-by-council record
  requests or pages.

### Tasmania

Official source:
https://www.tec.tas.gov.au/disclosure-and-funding/

Priority data families:

- new disclosure and funding scheme from 1 July 2025;
- reportable political donations, electoral expenditure, public funding,
  registers of electoral participants, and official agents.

Notes:

- Tasmania is important because it is a new disclosure regime. The adapter should
  preserve regime-start dates so gaps before 1 July 2025 are not misread as zero
  influence.
- Current adapter status: `run-state-local-pipeline --jurisdiction tas` archives
  the official TEC monthly reportable donation table and the 2025 House of
  Assembly / 2026 Legislative Council seven-day disclosure table fragments, then
  normalizes them into `money_flow` rows.
- The TAS rows are source-backed donor-to-recipient reportable political donation
  or reportable-loan observations. Loan rows are displayed as loans, not gifts.
  Rows should not be described as personal receipt unless the source recipient is
  independently an individual candidate/member.
- The next Tasmania step is to add electoral expenditure, public funding,
  participant/agent registers, and return documents when TEC publishes stable
  machine-readable or safely parseable pages.

### Northern Territory

Official source:
https://ntec.nt.gov.au/about-us/media-and-publications/media-releases/2025/20242025-annual-returns

Priority data families:

- annual gift returns;
- registered party and associated entity annual returns;
- candidate and donor returns;
- election expenditure returns.

Notes:

- NTEC records include published annual returns and gift returns. The adapter
  should preserve the distinction between annual gifts, annual financial returns,
  and election-period expenditure.
- First implemented adapter:
  `run-state-local-pipeline --jurisdiction nt` archives the official NTEC
  2024-2025 annual-return page and annual gift-return page. Current coverage is
  96 annual-return financial rows: 49 recipient-side receipts over $1,500, 2
  associated-entity debt rows over $1,500, and 45 donor-side donation-return
  rows, with $821,044.16 in source-row reported value. The paired gift-return
  artifact adds 78 recipient-side annual gift rows with $1,066,817.76 in
  reported value. These rows are source-backed disclosure observations, but the
  annual-return, gift-return, donor-side, and Commonwealth tables can observe
  overlapping underlying transactions. NT rows therefore remain visible in
  state/local source-family views while consolidated influence totals exclude
  them until cross-source deduplication exists. The annual gift source table
  does not publish per-row gift transaction dates, so normalized gift records
  retain the return received date as `date_reported` where available and carry
  an explicit date caveat. Both normalizers check row sums against
  source-published table totals.
- The next NT task is to add candidate returns and election expenditure returns,
  then link annual-return parties, associated entities, candidates, and donors
  to reviewed identifiers without double-counting the same gift from recipient,
  donor, and Commonwealth disclosure tables.

### ACT

Official source:
https://www.elections.act.gov.au/funding-disclosures-and-registers/funding-and-disclosure-obligations

Priority data families:

- annual financial disclosure returns for parties, MLAs, and associated entities;
- regular gift returns;
- election returns for parties, candidates, associated entities, third-party
  campaigners, broadcasters, and publishers;
- public funding, expenditure caps, receipts, gifts, payments, and debts.

Notes:

- ACT documentation explicitly states that party-endorsed candidate expenditure
  can be included in the party grouping return. This matches the federal
  campaign-support rule: show party-channelled candidate support separately from
  personal receipt.
- First implemented adapter:
  `run-state-local-pipeline --jurisdiction act` archives the official
  Elections ACT 2025-2026 gift-return page and 2024/2025 annual-return page. It
  normalizes current gift-return rows into
  `data/processed/act_gift_return_money_flows/` and annual-return receipt
  detail rows into `data/processed/act_annual_return_receipt_money_flows/`.
  Current coverage is 225 gift-return rows plus 350 annual-return receipt rows.
  Annual-return coverage includes 173 gifts of money, 26 gifts-in-kind, 7
  free-facilities-use rows, and 144 other receipts across parties, MLAs,
  non-party MLAs, and associated entities.
- ACT gift-return rows are source-backed party/non-party-candidate grouping
  disclosure records. ACT annual-return receipt rows add MLA and associated
  entity context, but the online table does not publish per-row receipt dates.
  Gift-in-kind and free-facility rows are non-cash reported values. All should
  be displayed as disclosure context until separate candidate/electorate/
  office-holder evidence supports a more specific attribution.

## First Implementation Sequence

1. Build a state/council source registry with one source record per official
   disclosure surface, including URL, jurisdiction, level, source family,
   expected formats, update cadence, and redistribution caveats.
2. Implement a discovery-only fetcher for each high-priority source surface. The
   fetcher should archive raw HTML/PDF/CSV/XLSX files and metadata before any
   parser is written.
3. Start with NSW, Victoria, and Queensland because they provide the clearest
   immediate coverage across state-level donations, expenditure, and searchable
   disclosure systems.
4. Continue ACT/NT coverage beyond the first gift adapters, and add WA next
   because its party/candidate expenditure and reimbursement records are
   theoretically valuable for party-channelled campaign support.
5. Add South Australia, Tasmania, and Northern Territory with careful
   return-level/regime-date caveats and source-specific parsers.
6. Begin council-level coverage where the state electoral commission provides a
   common disclosure system first, then add council-by-council adapters for
   registers of interests, gifts, meeting minutes, and procurement where needed.
7. Extend `/api/coverage` so users can see active, partial, planned, and blocked
   source families for each jurisdiction and level.
8. Extend the frontend level selector so State and Council switch from "planned"
   to "active" only after each adapter has source-backed records and caveats.

## First Discovery Results

The first reproducible source-discovery run was generated on 2026-04-29 from
archived raw seed pages using:

```bash
au-politics-money discover-links nsw_electoral_disclosures
au-politics-money discover-links vic_vec_disclosures
au-politics-money discover-links qld_ecq_disclosures
```

Generated manifests are archived under ignored
`data/processed/discovered_links/<source_id>/20260429T003319Z.json`.

### NSW Discovery Targets

The NSW discovery manifest retained 23 official links. The strongest parser
targets are:

- `efadisclosures.elections.nsw.gov.au`, the public disclosure search portal;
- disclosure explanation and lodgement pages covering pre-election, half-yearly,
  annual expenditure, and major political donor disclosures;
- public registers for candidates, groups, third-party campaigners, parties,
  senior office holders, associated entities, lobbyists, non-prohibited donors,
  and public notifications;
- a district-level state-election donation page for the 2023 NSW State election.

Implemented first safe adapter: `run-state-local-pipeline --jurisdiction nsw`
archives the official 2023 pre-election donation page and static heatmap, then
normalizes 94 donor-location aggregate rows covering 5,077 disclosed donations
and $6.48m in reported amounts for the 1 Oct 2022 to 25 Mar 2023 window. These
rows load into `aggregate_context_observation`, not `money_flow`, because the
heatmap identifies donor-location districts rather than donor-recipient
transactions or representative-level receipt.

Next NSW adapter task: inspect the EFA disclosure portal for stable request
parameters or export endpoints and confirm automated access terms. Only after
that should we normalize granular state/local donation and expenditure rows
with jurisdiction-specific thresholds, redaction status, and record-retention
caveats.

2026-04-29 review update: the EFA portal is technically scrapeable but is a
Salesforce Visualforce/Ajax4JSF session application rather than a stable public
bulk export. A production adapter should be a separate opt-in
`nsw_efadisclosures` module, not an expansion of the current heatmap adapter,
and should wait for a reproducible session client, PDF/download evidence
capture, and legal/robots review. If implemented, rows parsed from the portal
without original lodged PDFs must be labelled `official_portal_parsed_pdf_not_checked`
or equivalent and displayed as verification-pending source context.

### Victoria Discovery Targets

The Victoria discovery manifest retained 26 links. The strongest parser targets
are:

- `disclosures.vec.vic.gov.au` donation disclosure and public-donation portals;
- VEC funding pages for registered parties, independent members/candidates,
  state campaign accounts, and funding registers;
- annual-return pages for registered parties, associated entities, nominated
  entities, independents/groups, and third-party campaigners;
- glossary anchors for gifts, electoral expenditure, and political expenditure.

Current adapter status: `run-state-local-pipeline --jurisdiction vic` archives
the VEC funding-register landing page, fetches the linked DOCX files, validates
document/source hashes, and normalizes public-funding/admin/policy rows into
state-level public-funding context. Next Victoria adapter task: re-check the VEC
public-donation portal once it is no longer redirecting to maintenance, inspect
its export/API behaviour, and implement private donation/annual-return parsing
with the same claim boundaries. Victorian council donations require a separate
local-government adapter because the VEC page points council donation returns
away from the state disclosure surface.

### Queensland Discovery Targets

The Queensland discovery manifest retained 22 links. The strongest parser
targets are:

- `disclosures.ecq.qld.gov.au`, the Electronic Disclosure System;
- published disclosure returns for political donations and electoral
  expenditure;
- caps/funding-rate, compliance, register, and notice pages;
- local-government participant pages for candidates, groups, parties, third
  parties/donors, broadcasters, and publishers;
- state-government participant pages and official EDS help material.

Next adapter task: inspect the EDS portal and published-disclosure-return pages
for stable query/export behaviour. Queensland should be the first council-level
implementation candidate because the ECQ disclosure system explicitly covers
both state and local government electoral finance disclosures.

Current implementation status:

- Active reproducible exports:
  - `qld_ecq_eds_map_export_csv` for current gift/donation map rows;
  - `qld_ecq_eds_expenditure_export_csv` for electoral expenditure rows.
- The current normalized artifact contains 49,838 rows: 22,725 gift/donation
  rows and 27,113 electoral expenditure rows.
- The gift/donation export is loaded as source-backed state/local money records
  at the actor level supported by the ECQ export fields.
- The expenditure export is loaded as `campaign_support` with event type
  `state_local_electoral_expenditure`, because electoral expenditure is campaign
  activity, not personal receipt by a representative.
- Public lookup API snapshots for electors, parties, associated entities,
  events, local groups, and local electorates have been archived. Elector,
  party, associated-entity, and local-group snapshots are now normalized into a
  participant identifier artifact and applied to existing QLD money-flow
  entities only when the lookup name is unique, the QLD disclosure actor match
  is exact, and the participant type is political party, associated entity, or
  local group. Candidate/elector name-only matches are retained for manual
  review until event/electorate/role evidence supports the identity.
- The first enrichment pass normalized 6,360 ECQ participant lookup records and
  auto-accepted 48 exact unique party/entity/group matches. Ambiguous
  duplicate-name matches and 1,618 candidate/elector name-only matches remain
  in the official-identifier observation/review layer rather than being forced
  onto a donor, recipient, party, or candidate.
- `/api/state-local/summary` and the frontend State/Council summary panel now
  expose QLD ECQ disclosure totals, identifier-backed counts, top gift
  donors/recipients, and top electoral-expenditure actors before state/council
  boundary maps are ready.
- The QLD adapter also normalizes archived ECQ political-event and
  local-electorate lookup APIs. These exact unique name matches are displayed as
  disclosure context only. They improve event/local summaries but do not by
  themselves attribute money to a candidate, councillor, or current
  representative.
- The QLD adapter is now orchestrated by
  `run-state-local-pipeline --jurisdiction qld`, which fetches source pages and
  lookup APIs, fetches current ECQ CSV exports, normalizes money-flow rows,
  participants, and disclosure contexts, and writes a pipeline manifest without
  mutating the serving database. This is the adapter template for the next state
  and council jurisdictions: acquisition, normalization, loading, and public
  attribution remain separate auditable stages. The QLD runner passes exact
  fetched metadata paths into later export and normalization steps, which is the
  reproducibility standard future adapters should follow rather than relying on
  ambient latest-file lookup during a run. The paired
  `load-state-local-pipeline-manifest` command loads the exact JSONL artifacts
  named by the manifest, closing the acquisition-to-load reproducibility loop.
- The historical disclosure-return archive currently returned HTTP 401 during
  reproducible fetch. Treat it as a blocked/pending source until an official
  public access path is confirmed.

Next adapter task: map candidate/group/electorate records into state and local
electoral districts without reclassifying campaign expenditure as personal
receipt, then build QLD state/local map layers and representative/candidate
drilldowns.

## Data Model Requirements

The current schema should be extended conservatively rather than forked:

- keep `jurisdiction.level` as the level dimension;
- add state/council offices through `office_term`;
- add districts, wards, or local government areas through `electorate` or a
  generalized future `district` alias only if the existing table becomes too
  semantically strained;
- load all money/benefit/interests/access records into `influence_event`;
- use `event_family=campaign_support` for candidate, group, party-channelled,
  public-funding, and advertising records that should not be called personal
  receipt;
- add source-family coverage rows and caveats before showing maps publicly.

## Claim Limits

Allowed claims:

- "This source records a donation/gift/expenditure/return involving these actors."
- "This record is linked to this state district, council, party, candidate, or
  elected member at this evidence tier."
- "This source family is missing, blocked, redacted, or not yet available."
- "This entity appears across multiple levels of government."

Disallowed claims without additional evidence:

- that a disclosed gift or donation caused a state/council decision;
- that a party-level state return was personally received by a candidate;
- that missing local-government records mean no influence exists;
- that redacted source details can be inferred from context alone.
