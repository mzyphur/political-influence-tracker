# State and Council Expansion Plan

Last updated: 2026-04-29

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
- indexed thresholds and caps.

Notes:

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

### South Australia

Official source:
https://www.ecsa.sa.gov.au/parties-and-candidates/funding-and-disclosure-all-participants/funding-and-disclosure-political-parties?catid=13%3Aparties-and-candidates&id=1116%3Areporting-obligations-political-parties&view=article

Priority data families:

- party, candidate, associated entity, and third-party returns;
- amounts received, amounts paid, debts, and donation details above thresholds;
- election and periodic return schedules.

Notes:

- Build the adapter around the published forms/downloads and then normalize into
  the same `influence_event` families.

### Western Australia

Official source:
https://www.elections.wa.gov.au/returns-and-reports

Priority data families:

- annual returns and election returns;
- gifts, income, expenditure, and electoral reimbursements;
- Online Disclosure System entries where accessible;
- local-government disclosure duties where records are obtainable.

Notes:

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
4. Add ACT and WA next because their party/candidate expenditure records are
   theoretically valuable for party-channelled campaign support.
5. Add South Australia, Tasmania, and Northern Territory with careful regime-date
   caveats and source-specific parsers.
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

Next adapter task: inspect the EFA disclosure portal for stable request
parameters or export endpoints, then normalize state/local donation and
expenditure rows into `influence_event` with jurisdiction-specific thresholds,
redaction status, and record-retention caveats.

### Victoria Discovery Targets

The Victoria discovery manifest retained 26 links. The strongest parser targets
are:

- `disclosures.vec.vic.gov.au` donation disclosure and public-donation portals;
- VEC funding pages for registered parties, independent members/candidates,
  state campaign accounts, and funding registers;
- annual-return pages for registered parties, associated entities, nominated
  entities, independents/groups, and third-party campaigners;
- glossary anchors for gifts, electoral expenditure, and political expenditure.

Next adapter task: inspect the VEC disclosure portal for export/API behaviour
and implement a state-level parser first. Victorian council donations require a
separate local-government adapter because the VEC page points council donation
returns away from the state disclosure surface.

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
- The current normalized artifact contains 49,839 rows: 22,726 gift/donation
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
