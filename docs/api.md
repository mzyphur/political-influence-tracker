# Backend API

The first API layer is a FastAPI app intended for the frontend and public JSON
access. It reads from the local PostgreSQL database and does not mutate data.
The app uses an explicit CORS allow-list from
`AUPOL_API_CORS_ALLOW_ORIGINS` and a simple per-client process-local rate limit
from `AUPOL_API_RATE_LIMIT_PER_MINUTE`. Production should still sit behind a
reverse proxy with request logging, caching, and rate limiting.

Run locally:

```bash
cd backend
make api-dev
```

Local URL:

```text
http://127.0.0.1:8008
```

Interactive docs:

```text
http://127.0.0.1:8008/docs
```

## Endpoints

- `GET /health` - process health, no database required.
- `GET /api/health` - database-backed health check.
- `GET /api/search?q=...` - global search across representatives,
  electorates, parties, entities/donors, sectors, policy topics, and postcode
  lookups where a postcode crosswalk has been loaded.
- `GET /api/map/electorates` - GeoJSON-style FeatureCollection for the national
  map, filterable by `chamber`, `state`, and `boundary_set`, with optional
  simplified boundary geometry and current representative/party/influence-event
  summary properties.
- `GET /api/representatives/{person_id}` - current profile with office terms,
  influence-by-sector summaries, vote-topic summaries, and reviewed
  source-to-policy context.
- `GET /api/entities/{entity_id}` - source/recipient entity profile with
  sector classifications, identifiers, summary counts, top counterparties, and
  recent source-backed event rows.
- `GET /api/parties/{party_id}` - party profile with current representatives,
  reviewed or candidate linked money-flow entities, associated-entity return
  context, source/recipient summaries, and recent source-backed party/entity
  money rows.
- `GET /api/electorates/{electorate_id}` - electorate profile, current
  representatives, boundary availability, and current representative influence
  summary.
- `GET /api/influence-context` - source-to-policy context rows from
  `person_policy_influence_context`, filterable by `person_id`, `topic_id`, and
  `public_sector`.

## Search Behaviour

Search results are discovery aids. They return the record type, database ID,
label, subtitle, rank, and compact metadata. Results are deliberately caveated:
they do not assert wrongdoing, causation, quid pro quo, or improper influence.
Free-text search requires at least three characters by default
(`AUPOL_API_MIN_FREE_TEXT_QUERY_LENGTH=3`) to reduce accidental broad scans on
public deployments; exact four-digit postcode queries are handled separately.

Supported search targets:

- Representative names.
- Electorate names and states/territories.
- Political parties.
- Source entities/donors/gift providers/lobbyist clients.
- Public-interest sectors.
- Policy topics.
- Postcodes, once a source-backed crosswalk is loaded.

## Postcodes

Postcodes are not equivalent to electorates. The AEC's public electorate finder
notes that a locality/suburb or postcode can be in more than one federal
electorate. The API therefore returns a `postcode_search` limitation instead of
guessing until we ingest a reproducible crosswalk.

Preferred implementation path:

1. Ingest official AEC electorate-finder files where available for locality,
   street, and postcode-to-division evidence.
2. Add an ABS Postal Area overlay as a secondary approximation for map search,
   labelled clearly as an approximation because ABS Postal Areas are not the
   same as Australia Post delivery postcodes.
3. Store ambiguous postcode results as multiple electorate candidates with
   method, confidence, source document, and caveat metadata.

## Map Features

`/api/map/electorates` returns a GeoJSON-style `FeatureCollection` for the
frontend map. By default it emits House electorates with low-tolerance geometry
from `electorate_boundary`, current representative and party fields from
`office_term`, and non-rejected disclosed influence-event counts for the current
representative or representatives.

Useful parameters:

- `chamber=house|senate`
- `state=VIC`, `NSW`, etc.
- `boundary_set=aec_federal_2025_current`
- `include_geometry=false` for sidebar/list loading.
- `simplify_tolerance=0.0005` is the interactive default. It is much finer than
  the earlier development value and avoids large visible cracks while keeping
  payloads usable.
- `simplify_tolerance=0` preserves source geometry for strict QA/publication
  checks. Higher tolerances are allowed for lighter development payloads, but
  they can create visible cracks because adjacent electorates are simplified
  separately.

When `boundary_set` is supplied, only electorates with that boundary set are
returned. When it is omitted, the endpoint selects the latest currently valid
boundary per electorate. The singular `representative_*` and `party_*` fields
are populated only when exactly one current representative is attached; use
`current_representatives` and `party_breakdown` for multi-member chambers.
Influence summary fields are explicitly named
`current_representative_lifetime_*` because they summarize publishable records
for the current representative(s), not the electorate itself.

For `chamber=senate`, the endpoint returns one current Senate delegation feature
per state or territory. Senate geometries are composite state/territory features
derived from source-backed federal House electorate boundaries for the same
state or territory, while senator lists and influence counts come from Senate
office terms. Features expose `map_geometry_scope` so the frontend can label
that geometry provenance.

Map counts are discovery context only. They are not claims about misconduct,
causation, or whether any money/gift/interest affected a vote or policy action.
The current map summary counts are representative-linked counts only. Whole
database counts are broader because many financial disclosures are honestly
attributable only to a party, entity, return, or donor-recipient pair rather
than a single MP/electorate.

## Coverage

`/api/coverage` reports source-family coverage for the frontend and public QA.
It separates active federal/Commonwealth coverage from planned state and council
layers, and exposes whole-database counts alongside attribution caveats. This is
the endpoint the UI uses to show why the map-linked record counts are narrower
than the total disclosed-money database.

The coverage model is intentionally portable: each jurisdiction adapter should
fill the same dimensions where legally/publicly available: actors, offices,
boundaries, money flows, gifts/hospitality/travel, interests/assets/roles,
lobbying access, votes/proceedings, entity identifiers, and industry
classifications.

## Representative Profiles

`/api/representatives/{person_id}` returns the representative's current and
historical office terms, reviewed context summaries, and a person-linked
`recent_events` feed. The feed is the first UI surface for "what did this person
receive or disclose?" across money, gifts, hospitality, travel, private
interests, organisational roles, and other traceable disclosed records.
Each recent event includes source-document labels/URLs, source refs, evidence
status, review status, amount status, and missing-data flags so the frontend can
show the evidentiary trail rather than only a summary claim.

The response also includes a `contact` object for public representative contact
details. Phone and office-address fields come from APH contact CSVs. Email is
populated only when the address is present in an official APH House/Senate
contact-list PDF and the deterministic match is unambiguous; otherwise the API
returns the official APH profile/search URL as the electronic contact path.

These are still person-linked records only. Party/entity/candidate-return money
flows remain in the whole database and should be surfaced through party/entity
and attribution-method views rather than forced onto a person without evidence.

## Entity Profiles

`/api/entities/{entity_id}` returns a read-only profile for parsed source or
recipient entities: donors, companies, people-as-donors, parties-as-entities,
associated entities, unions, lobbyist clients, and other named organisations.
It is the first API surface for records that are too broad to attach honestly to
one MP or electorate.

The response includes:

- `classifications` and `identifiers`, when official/manual/rule-based evidence
  exists.
- `as_source_summary`, counting non-rejected events where the entity is the
  parsed source.
- `as_recipient_summary`, counting non-rejected events where the entity is the
  parsed recipient.
- `top_recipients` and `top_sources`, so entity pages can show who money or
  benefits flowed to or from.
- `recent_events`, with source-document labels/URLs, source refs, amount status,
  review status, and missing-data flags.

Entity profiles are discovery context. They do not imply wrongdoing, and
party/entity-level returns must not be assigned to a representative unless a
separate source-backed person-linking method supports that assignment.

## Party Profiles

`/api/parties/{party_id}` is the first surface for AEC party and
associated-entity money that is too broad to assign to one MP or Senator. It
uses reviewed `party_entity_link` rows for party money totals and exposes
transparent name-family candidate entities separately as `candidate_entities`.
Candidate rows are review/discovery context only and must not be added to party
totals until reviewed.

Party/entity candidates are now materialized during database loading with
`materialize-party-entity-links`, then reviewed through the standard audit
workflow:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money materialize-party-entity-links
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money export-review-queue party-entity-links
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money import-review-decisions decisions.jsonl
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money import-review-decisions decisions.jsonl --apply
```

Rejected party/entity links suppress future name-family candidates for that
party/entity pair. The exported draft support source is labelled
`evidence_role="aec_money_flow_context"` because AEC money-flow context alone is
not enough to accept the relationship. Accepted/revised links require a
reviewer-added supporting source with
`evidence_role="party_entity_relationship"` and retain the original candidate
evidence in `party_entity_link.evidence_note`; reviewer rationale is stored in
`manual_review_decision` and link metadata.

Party profiles include:

- Current office holders for the party.
- Money summaries where reviewed linked party entities appear as recipients or
  sources.
- Candidate entities requiring review, with candidate event counts/amounts kept
  separate from reviewed totals.
- Associated-entity return entities detected in AEC metadata.
- Top sources and recipients for party/entity money flows.
- Recent source-backed event rows with review and amount-status fields.

These rows are party/entity context. They are not electorate-level or
representative-level claims unless a separate source-backed attribution method
supports that narrower claim.

## Source-To-Effect Context

The API exposes `person_policy_influence_context`, which only emits rows when a
sector-policy-topic link exists. This is an evidentiary guardrail: the app can
show that a representative had disclosed money/gifts/interests from a sector
and later voted on a linked topic, but the row itself is contextual rather than
causal.

Candidate sector-policy links can be exported with:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money suggest-sector-policy-links
```

These suggestions are review prompts only. They are written to
`data/audit/sector_policy_link_suggestions/`, do not mutate PostgreSQL, and are
not displayed by `/api/influence-context` until a reviewer imports an accepted
or revised decision with the required topic-scope and sector-material-interest
supporting sources.
Reviewed sector-policy links depend on loaded `policy_topic` rows. If the
database is loaded without vote/policy-topic artifacts, review replay skips
sector-policy link decisions and `/api/influence-context` will return no
context rows.

Public wording should use terms like:

- "Disclosed source context before/around/after this vote topic."
- "Sector-policy link reviewed or explicitly documented."
- "No causal claim is made by this row."
