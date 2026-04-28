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
- `GET /api/representatives/{person_id}` - current profile with office terms,
  influence-by-sector summaries, vote-topic summaries, and reviewed
  source-to-policy context.
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
