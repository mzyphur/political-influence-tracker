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
- `GET /api/graph/influence` - source-backed network payload for exactly one
  root (`person_id`, `party_id`, or `entity_id`). Nodes and edges are suitable
  for frontend graph views. Party graph money edges use reviewed
  `party_entity_link` rows only; `include_candidates=true` adds candidate
  party/entity link edges with `evidence_status="candidate_requires_review"`.
- `GET /api/state-local/summary` - first state/local summary surface. It
  returns QLD ECQ, ACT Elections, NT NTEC annual-return/annual-gift, and VEC
  funding-register source-family totals, SA ECSA return-summary totals, and
  WAEC Online Disclosure System political contribution totals,
  identifier-backed counts where available, top gift/gift-in-kind/contribution
  donors and recipients, top campaign-spend actors, top public-funding
  recipients, and top return-summary sources/recipients. It also returns NSW donor-location
  aggregate context from the official 2023 State Election heatmap when loaded.
  State/council maps and representative joins remain under construction.
- `GET /api/state-local/records` - paginated state/local source-row feed for
  the summary panel. It accepts `level=state|council|local`,
  `flow_kind=act_gift_of_money|act_gift_in_kind|nt_annual_gift|nt_annual_receipt|nt_donor_return_donation|nt_annual_debt|qld_gift|qld_electoral_expenditure|wa_political_contribution|vic_public_funding_payment|vic_administrative_funding_entitlement|vic_policy_development_funding_payment|sa_*_return_summary`,
  `limit`, and an opaque `cursor`; cursors are bound to the current level and
  flow-kind filters so rows are not skipped if a UI changes slices. NT rows
  expose annual-return and annual gift-return caveats because the NTEC source
  families include overlapping recipient-side and donor-side disclosure views,
  and the annual gift tables do not publish per-row gift dates. VEC rows expose
  public-funding context and date caveats; they are not private donations,
  gifts, or personal income. SA ECSA rows expose return-level index summaries,
  not detailed transaction rows or personal receipt. WAEC rows expose
  donor-to-political-entity contribution disclosures; the parsed grid date is
  the disclosure-received date, not necessarily the contribution transaction
  date, and non-original version rows are preserved pending deduplication.

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
electorate. The pipeline now supports a reproducible AEC postcode search
crosswalk:

```bash
au-politics-money fetch-aec-electorate-finder-postcodes \
  --postcodes-file data/seeds/aec_postcode_search_seed.txt
au-politics-money normalize-aec-electorate-finder-postcodes \
  --postcodes-file data/seeds/aec_postcode_search_seed.txt
au-politics-money load-postcode-electorate-crosswalk
```

When a postcode is loaded, `/api/search?q=2600&types=postcode` returns every
source-backed electorate candidate with `match_method`, `confidence`,
`localities`, AEC division ids where available, source-document metadata, and
the AEC ambiguity caveat. AEC Electorate Finder results may describe electorates
for the next federal election, so the API also exposes `source_boundary_context`
and `current_member_context`; postcode search must not be displayed as proof of
the current local member after a redistribution. If an AEC candidate cannot yet
be resolved to the loaded House electorate boundary table, the loader stores it
in `postcode_electorate_crosswalk_unresolved` and the API returns a
`postcode_search` limitation naming the unresolved candidate instead of silently
dropping it. When a postcode is not loaded at all, the API returns a
`postcode_search` limitation rather than implying the postcode has no federal
electorate.

Next implementation path:

1. Expand the seed list into a reviewed full postcode refresh set.
2. Add locality/suburb exact search from the same AEC electorate-finder source.
3. Add an ABS Postal Area overlay as a secondary approximation for map search,
   labelled clearly because ABS Postal Areas are not the same as Australia Post
   delivery postcodes.

## Map Features

`/api/map/electorates` returns a GeoJSON-style `FeatureCollection` for the
frontend map. By default it emits House electorates with low-tolerance
`geometry_role=display` geometry from
`electorate_boundary_display_geometry`, current representative and party fields
from `office_term`, and non-rejected disclosed influence-event counts for the
current representative or representatives. The display geometry is a
land-clipped derivative for usability; official AEC source geometry remains
available and unchanged in `electorate_boundary.geom`.

Useful parameters:

- `chamber=house|senate`
- `state=VIC`, `NSW`, etc.
- `boundary_set=aec_federal_2025_current`
- `include_geometry=false` for sidebar/list loading.
- `geometry_role=display|source`; `display` is the default. Use `source` only
  for QA or publication checks that explicitly need the official AEC geometry,
  including offshore electoral extents.
- `simplify_tolerance=0.0005` is the interactive default. It is much finer than
  the earlier development value and avoids large visible cracks while keeping
  payloads usable.
- `simplify_tolerance=0` preserves whichever role is requested without
  simplification. Higher tolerances are allowed for lighter development
  payloads, but they can create visible cracks because adjacent electorates are
  simplified separately.

When `boundary_set` is supplied, only electorates with that boundary set are
returned. When it is omitted, the endpoint selects the latest currently valid
boundary per electorate. The singular `representative_*` and `party_*` fields
are populated only when exactly one current representative is attached; use
`current_representatives` and `party_breakdown` for multi-member chambers.
Influence summary fields are explicitly named
`current_representative_lifetime_*` because they summarize publishable records
for the current representative(s), not the electorate itself.
`current_representative_lifetime_reported_amount_total` excludes
`campaign_support` records so campaign expenditure and party-channelled context
are not collapsed into direct money/gift totals. Campaign rows are exposed
separately via
`current_representative_lifetime_campaign_support_event_count` and
`current_representative_campaign_support_reported_total`.

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
It separates active federal/Commonwealth coverage from partial state/council
coverage and planned layers, and exposes whole-database counts alongside
attribution caveats. This is the endpoint the UI uses to show why the
map-linked record counts are narrower than the total disclosed-money database.
Queensland ECQ EDS rows currently make state and council/local coverage
`partial` via `partial_levels`; `active_levels` remains federal until
state/local boundaries, representatives, and attribution joins are loaded for
public drilldown.

The endpoint also exposes `display_land_masks` when a display-only land mask is
loaded for interactive boundary clipping. These rows identify the source key,
source document, geometry role, method, licence status, and limitations. They do
not replace official electorate boundaries; they explain the public map display
geometry.

The coverage model is intentionally portable: each jurisdiction adapter should
fill the same dimensions where legally/publicly available: actors, offices,
boundaries, money flows, gifts/hospitality/travel, interests/assets/roles,
lobbying access, votes/proceedings, entity identifiers, and industry
classifications.

## State/Local Summary

`/api/state-local/summary` is the first public API surface for non-federal data.
It currently supports Queensland ECQ Electronic Disclosure System money-flow
rows, ACT Elections gift-return rows, Northern Territory NTEC annual-return and
annual gift-return rows, South Australia ECSA return-summary rows, Victoria VEC
funding-register rows, and NSW Electoral Commission aggregate donor-location
context.

Useful parameters:

- `level=state|council|local`; `council` and `local` both select local
  government rows where a loaded adapter has them. ACT, NT, SA ECSA return
  summaries, VEC funding, and NSW aggregate context are state-level only. Omit
  `level` to aggregate all loaded state/local rows.
- `limit=1..25` controls each top-actor list.

The response includes:

- `source_document_count` and `latest_source_fetched_at`: freshness indicators
  for the current source documents backing the loaded state/local money-flow
  rows. These values do not count every lookup API snapshot and they are not
  completeness guarantees.
- `totals_by_level`: money-flow row counts, gift/donation counts,
  gift-in-kind counts, electoral expenditure counts, separate gift/gift-in-kind
  and electoral-expenditure reported amount totals, SA return-summary row counts
  and return-summary values, ECQ event/local-electorate context-backed row
  counts, and source/recipient row counts where that side of the row is backed
  by an accepted identifier. There is intentionally no combined "personal
  receipt" total because cash gifts, non-cash gifts, campaign expenditure, and
  return-level summaries are different evidence families.
- `top_gift_donors` and `top_gift_recipients`: disclosed gift and
  gift-in-kind actors.
- `top_expenditure_actors`: electoral expenditure actors, which are
  campaign-support context rather than personal receipt.
- `top_events` and `top_local_electorates`: exact unique matches from archived
  ECQ political-event and local-electorate lookup APIs. Event dates describe the
  election event, not the gift/donation/expenditure transaction date; local
  electorate labels are context labels, not candidate/councillor attribution.
- `recent_records`: a compact current-row feed with source/recipient names,
  reported amount or value, ECQ event/local-electorate context where matched,
  source-row reference, source-document URL, and row-side identifier signals.
- `aggregate_context_totals` and `top_aggregate_donor_locations`: NSW
  aggregate donor-location rows from the official static 2023 State Election
  heatmap. These rows are not donor-recipient money-flow records and must not
  be attributed to any representative, candidate, councillor, or party without
  separate supporting evidence. Public displays must preserve the NSWEC source
  caveat that the map does not show recipient locations and may exclude donor
  locations that cannot be mapped, plus NSWEC CC BY 4.0 attribution and
  no-endorsement requirements.

`/api/state-local/records` returns the concrete current state/local rows behind
that summary with cursor pagination. Each row includes the normalized source and
recipient names, amount/date fields, identifier-backed flags, event/local
context where matched, source row reference, source URL, source document id,
source fetch timestamp, SHA-256 snapshot hash, and selected row metadata such
as gift-in-kind description, expenditure purpose, or goods/services where the
source provides them. Gift/donation rows are donor-recipient records.
Gift-in-kind rows are reported non-cash values. Electoral expenditure rows are
expenditure incurred by a named actor; they are campaign-support context, not
evidence that another person or office-holder received money.
NT annual gift rows are donor-recipient gift observations from the official
NTEC annual return gifts page. They carry `date_reported` as the return received date
where available because the recipient-side table does not publish per-row gift
transaction dates. They remain visible in state/local source-family totals, but
their `public_amount_counting_role` is
`jurisdictional_cross_disclosure_observation`, so consolidated influence totals
do not add those amounts until cross-source deduplication against Commonwealth
and donor-side returns exists. The state/local record API keeps source row
references and document URLs visible but does not echo address-bearing NTEC
`original_text` by default.
NT annual-return financial rows add recipient-side receipts over $1,500,
associated-entity debts over $1,500, and donor-side donation-return rows from
the broader NTEC annual-return page. These flow kinds are
`nt_annual_receipt`, `nt_annual_debt`, and `nt_donor_return_donation`. They are
displayed as source-row context, not consolidated reported totals, because they
can overlap with the annual gift-return page, donor-side returns, and
Commonwealth disclosure records.
SA ECSA return-summary rows come from the current ECSA return-record portal.
The API exposes them as return-summary context with flow kinds such as
`sa_candidate_campaign_donations_return_summary`,
`sa_political_party_return_summary`, `sa_associated_entity_return_summary`,
`sa_third_party_return_summary`, `sa_donor_return_summary`,
`sa_special_large_gift_return_summary`, and capped/prescribed expenditure
summary kinds. They are not detailed transaction rows and must not be summed
with direct gift/donation rows as if they were personal receipt.

ECQ identifiers are attached only when the archived public lookup APIs provide
an evidence-backed participant ID and the loader can make an exact unique match
to a QLD money-flow entity. Political party, associated-entity, and local-group
matches can be auto-accepted under that rule. Candidate/elector name-only
matches stay in the manual-review layer unless future event, electorate, or
role context supports the identity. The endpoint does not claim that every donor
has an ECQ identifier; many donor names remain free text because the archived
lookup APIs identify political participants, parties, associated entities, and
local groups rather than all donors.

## Representative Profiles

`/api/representatives/{person_id}` returns the representative's current and
historical office terms, reviewed context summaries, and a person-linked
`recent_events` feed. The feed is the first UI surface for "what did this person
receive or disclose?" across money, gifts, hospitality, travel, private
interests, organisational roles, and other traceable disclosed records.
Each recent event includes source-document labels/URLs, source refs, evidence
status, review status, amount status, and missing-data flags so the frontend can
show the evidentiary trail rather than only a summary claim.

`/api/representatives/{person_id}/evidence` pages through the same event shape
for selected representatives. It uses stable cursor pagination over
`event_date`, `date_reported`, and event id so load-more interactions do not
skip or duplicate same-date disclosures. By default `group=direct` excludes
`campaign_support`; `group=campaign_support` must be requested explicitly.
Optional `event_family` filtering is available only for direct records. The
endpoint rejects invalid cursors and returns 404 for unknown people.

Campaign-return and party-channelled records are deliberately separated from
the direct feed. The response includes `campaign_support_summary`,
`campaign_support_recent_events`, and `campaign_support_caveat` for candidate
or Senate-group election returns, campaign expenditure, nil-return context, and
other campaign activity that is source-backed but not personal receipt. AEC
public election funding is also represented as campaign support: party payments
remain party aggregate rows, while independent-candidate payments remain
candidate/campaign-context rows. House candidate rows are linked to
representatives only when the candidate name, electorate, and state form an
exact unique match; Senate rows stay at state/group/party context unless a
source supports senator-specific attribution.

Candidate and Senate-group election contexts are also materialised internally as
`candidate_contest` rows. Current exact House candidate-name/electorate/state
matches are labelled `name_context_only` and keep `office_term_id` empty until
historical office-term dates support a temporal match. This prevents campaign
support from being upgraded into “MP received money” merely because the same
person later or currently holds the seat.

Entity profiles keep the same separation. `reported_amount_total` fields in
entity direct-money summaries exclude `campaign_support`; campaign support is
available in `campaign_support_reported_amount_total` fields and in recent
records with `event_family=campaign_support`.

Lobbyist-register rows are exposed as `event_family=access` only at entity/
raw-name context level. A client-to-lobbying-organisation edge means the
official register listed that client relationship. A lobbying-organisation to
listed-lobbyist edge means the register listed that person for the organisation.
Neither edge is evidence of a meeting with a representative, access granted,
successful lobbying, improper influence, or wrongdoing.

The response also includes a `contact` object for public representative contact
details. Phone and office-address fields come from APH contact CSVs. Email is
populated only when the address is present in an official APH House/Senate
contact-list PDF and the deterministic match is unambiguous; otherwise the API
returns the official APH profile/search URL as the electronic contact path.

These are still person-linked or source-backed campaign-context records only.
Party/entity aggregate money flows remain in the whole database and should be
surfaced through party/entity and attribution-method views rather than forced
onto a person without evidence.

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
- `access` rows where the entity appears in official lobbying-register client
  or lobbyist-person context. These rows have `amount_status=not_applicable`
  and should be displayed as registry context, not as money or gifts.
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
