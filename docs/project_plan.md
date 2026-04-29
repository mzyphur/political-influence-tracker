# Project Plan

Last updated: 2026-04-29

## Mission

Build a rigorous, public-facing web app that helps Australians inspect flows of
political money, gifts, interests, lobbying access, and voting behaviour across
federal, state, territory, and later council governments.

The app should be beautiful and accessible, but its core value is evidentiary:
users must be able to drill from a visualization down to the source record.

## Guiding Principles

1. Preserve raw sources before parsing.
2. Prefer official sources, then reputable civic datasets, then journalistic or
   academic secondary sources.
3. Keep facts, inferred classifications, and interpretations separate.
4. Never imply illegal corruption unless there is a legal or official finding.
5. Make uncertainty visible instead of hiding it.
6. Build repeatable weekly ingestion from the start.
7. Treat country and government level as adapter dimensions, not as one-off
   assumptions; see `docs/jurisdiction_generalization.md`.
8. Treat direct, campaign, party/entity, and modelled allocation as separate
   evidence tiers; see `docs/influence_network_model.md`.
9. Document the operating theory behind substantial engineering and product
   choices; see `docs/theory_of_influence.md`.

## Phase 1: Federal Foundation

Goal: create a reliable Commonwealth data backbone.

Work items:

- Build source registry and raw source downloader.
- Create PostgreSQL/PostGIS schema for people, offices, entities, money flows,
  gifts/interests, votes, source documents, and evidence claims.
- Ingest current MP/Senator rosters from Parliament CSVs.
- Ingest AEC federal electoral boundary GIS data. Current federal 2025 national
  boundaries are now transformed to GeoJSON/PostGIS; later frontend work should
  create simplified/vector-tile derivatives from the canonical full-resolution
  boundary table.
- Ingest AEC Transparency Register downloads and detailed receipts.
- Scrape House and Senate interests register landing pages and PDFs.
- Store all source artifacts with timestamps, checksums, and parser versions.
- Maintain a unified `influence_event` surface so large money flows and small
  disclosed benefits can be queried with the same provenance and uncertainty
  fields.
- Maintain a typed influence graph model so party/entity-level and
  campaign-context records can be connected to representatives without
  mislabelling them as direct personal receipt.
- Maintain methodology notes that connect each new data family to an influence
  mechanism, observable indicator, allowed public claim, and limitation.

Deliverable:

- A local database containing current federal people, electorates, source docs,
  and first normalized disclosure records.

## Phase 2: Money Flow Normalization

Goal: turn AEC records into searchable, comparable flows.

Work items:

- Normalize annual returns, election returns, detailed receipts, donor returns,
  MP/Senator returns, associated entities, significant third parties, and third
  parties.
- Standardize recipient types: party, branch, candidate, MP/Senator, associated
  entity, third party, referendum entity.
- Standardize source types: individual, company, union, association, trust,
  government, foreign government-linked, party entity, unknown.
- Preserve legal return category and source wording exactly.
- Detect duplicates and amended returns.

Deliverable:

- A queryable federal money-flow table with source-document evidence.

## Phase 3: Gifts, Interests, Travel, Hospitality

Goal: extract structured records from APH registers.

Work items:

- Scrape House and Senate register index pages.
- Download PDFs and metadata for each MP/Senator.
- Extract text and tables with `pdfplumber`.
- Use OCR fallback for scanned or handwritten documents.
- Classify entries by register category: gifts, travel, hospitality, sponsored
  travel, memberships, shares, trusts, liabilities, real property, income,
  directorships, other assets, and other interests.
- Build a human review queue for low-confidence extraction.

Deliverable:

- Structured gift/interest records linked to PDF page references.
- Benefit events for disclosed gifts, hospitality, sponsored travel, flights,
  tickets, meals, memberships/lounges, subscriptions, and other traceable
  non-cash items, with disclosure-gap flags when value, provider, or date is
  missing.

## Phase 4: Entity Resolution and Industry Classification

Goal: identify who donors/sources are and what sector they represent.

Work items:

- Build canonical entity table with aliases.
- Match names against AEC entity registers, ASIC company dataset, ABN Lookup,
  ACNC, lobbyist register, and curated manual mappings.
- Assign ANZSIC where available or infer with evidence.
- Add public-interest sector taxonomy: fossil fuels, mining, property,
  gambling, finance, tech, defence, healthcare, pharmaceuticals, education,
  media, unions, agribusiness, consulting, law, foreign government, and other.
- Store classification confidence and reviewer.
- Export review queues and store manual-review decisions separately from raw
  and machine-produced records.

Deliverable:

- Donor/source profiles with identifiers, aliases, industry labels, and caveats.

## Phase 5: Voting Behaviour and Policy Linkage

Goal: compare money/interests with parliamentary behaviour.

Work items:

- Ingest divisions and person-level votes.
- Link divisions to bills, topics, and policy areas.
- Track party-line votes and rebellions.
- Build cautious association measures: time-windowed exposure before votes,
  sector-level funding concentration, and vote-topic alignment.
- Build typed indirect network paths and modelled allocation methods that keep
  source-backed party/campaign records separate from direct person-level
  records.
- Avoid causal language unless backed by a design strong enough for that claim.

Deliverable:

- MP/Senator profile pages showing money, gifts, interests, and votes by topic.

## Phase 6: Public API

Goal: expose clean data for frontend and researchers.

Work items:

- Build FastAPI endpoints for people, parties, electorates, donors, industries,
  influence events, money flows, gifts/interests, votes, and source documents.
- Add API-level filtering by date, party, state, chamber, source type, industry,
  and evidence confidence.
- Add CSV/JSON exports with citation fields.
- Add source-backed postcode/locality search using AEC electorate-finder files
  and/or caveated ABS Postal Area overlays; do not infer a single electorate
  from postcode alone where the source indicates ambiguity.

Deliverable:

- Versioned API suitable for the frontend and public downloads.

## Phase 7: Frontend MVP

Goal: build the first public visual experience.

Core views:

- National map with electorates and Senate state panels.
- MP/Senator profile pages.
- Donor/source profile pages.
- Party money map and timelines.
- Industry influence explorer.
- Gift/travel/hospitality explorer.
- Vote-topic explorer with source-backed caveats.

Design requirements:

- Every chart supports drill-down to records.
- Every record has a source drawer.
- Labels distinguish "official record", "parsed", "matched", "inferred", and
  "reviewed".
- The interface avoids unsupported claims while still making patterns visible.

## Phase 8: State and Territory Expansion

Goal: add jurisdictions one at a time after federal stability.

Likely order:

1. NSW
2. Queensland
3. Victoria
4. Western Australia
5. South Australia
6. Tasmania
7. ACT
8. Northern Territory

The order may change based on data access, current legal/publication changes,
and source stability.

## Phase 9: Council Expansion

Goal: extend to local government.

This is a separate major effort. Council data is likely fragmented by state,
election commission, and council-level disclosure practices. Start only after
state ingestion patterns are stable.
