# AU Politics Money Tracker

This project builds a public evidence system for Australian political money, gifts,
interests, lobbying access, and voting behaviour.

The initial scope is Commonwealth/federal politics:

- AEC financial disclosure returns and detailed receipts.
- House and Senate registers of interests, gifts, travel, hospitality, and related interests.
- Current and historical MPs/Senators, parties, electorates, and electoral boundaries.
- Parliamentary voting behaviour, initially through official records and They Vote For You.
- Donor/entity resolution and industry classification.

The project principle is: show the evidence, preserve the source, and separate facts
from interpretation. The app should make influence visible without overstating what
the public record can prove.

The project also maintains an explicit operating theory of influence in
`docs/theory_of_influence.md`. Engineering choices should connect to that theory:
which influence mechanism is being operationalized, which observable indicator is
being used, and which public claims remain out of bounds.

The frontend includes a hostable public companion page at
`frontend/public/methodology.html`, linked from the app as "Method". It translates
the theory and evidence rules into an HTML page with diagrams for public,
journalistic, and academic audiences.

The state/council expansion sequence is tracked in
`docs/state_council_expansion_plan.md`. It identifies the first official
state/territory disclosure surfaces, source-priority order, and attribution
rules for carrying the same influence model below the Commonwealth level.

## Current Structure

- `docs/` - planning, research standards, source inventory, and methodology.
- `backend/` - Python ingestion, normalization, and database code.
- `backend/schema/` - PostgreSQL/PostGIS schema drafts.
- `frontend/` - React/Vite/MapLibre public interface scaffold.
- `data/raw/` - raw downloaded source documents, grouped by source and timestamp.
- `data/processed/` - derived intermediate outputs.
- `data/audit/` - validation reports and extraction QA outputs.
- `notebooks/` - exploratory analysis only.

## First Backend Commands

From `backend/`:

```bash
python3 -m au_politics_money.cli list-sources
python3 -m au_politics_money.cli show-source aec_transparency_downloads
python3 -m au_politics_money.cli fetch-source aec_transparency_downloads
```

The fetch command stores raw bytes plus JSON metadata under `data/raw/`. It does
not parse or transform records yet.

For the local backend environment:

```bash
cd backend
make install
make test
make lint
```

For the local frontend environment:

```bash
cd frontend
npm install
npm run dev
```

The first frontend screen uses `/api/map/electorates` and `/api/search`, with
MapTiler configured through `VITE_MAPTILER_API_KEY` in `frontend/.env.local`.

For a local PostgreSQL/PostGIS database:

```bash
cd backend
cp .env.example .env
docker compose up -d
```

The initial schema is in `backend/schema/001_initial.sql`.
Additive local migrations start at `backend/schema/002_official_identifiers.sql`;
`backend/schema/003_influence_events.sql` adds the unified event surface used by
the future API/frontend.

Load the latest reproducible artifacts into PostgreSQL:

```bash
cd backend
export DATABASE_URL=postgresql://au_politics:change-me-local-only@localhost:54329/au_politics
.venv/bin/python -m au_politics_money.cli load-postgres --apply-schema
```

For an existing local database, apply additive migrations without rerunning the
initial schema:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money migrate-postgres
```

Current local federal baseline loaded into PostgreSQL:

- 192,201 AEC annual money-flow rows.
- 5,853 House interest records from PDF text/OCR extraction.
- 1,752 Senate interest records from the official APH-backed Senate interests API.
- 199,806 unified `influence_event` rows derived from the money-flow and
  interests tables: 192,201 money events, 1,390 benefit events, 4,700 private
  interest events, 1,413 organisational-role events, and 102 other declared
  interests.
- 50 direct AEC House-member return money rows are now person-linked to MP
  profiles through conservative unique cleaned-name matching, totaling
  AUD 1,383,511. Unmatched direct representative rows remain unlinked with audit
  metadata rather than guessed.
- 226 people/office terms, including one documented House-register-derived fallback for Sussan Ley/Farrer because the APH contact CSV omitted that House seat.
- 150 current federal House electorate boundaries from the AEC March 2025
  national ESRI shapefile transformed from GDA94/EPSG:4283 to GeoJSON/PostGIS
  SRID 4326.
- 35,874 generated entity-sector classifications from `public_interest_sector_rules_v1`; these are inferred rule-based labels pending official identifier/manual-review enrichment.
- 3,591 unique official identifier observations: the Australian Government Register of Lobbyists full current snapshot plus one live ABN Lookup web-service smoke record for BHP Group Limited.
- Targeted ABN Lookup web-service enrichment is implemented for reviewed ABN/ACN lookups, with raw XML archiving, secret redaction, and trading-name caveats.
- 393 exact-name official match candidates are queued for manual review. No official identifiers are attached to money-flow entities until an existing identifier or a reviewed mapping supports the match.
- 72 official APH decision-record index rows: 53 current House Votes and
  Proceedings links and 19 current Senate Journals links. These are
  `official_record_index` rows linked to 91 archived raw ParlInfo snapshots:
  72 HTML representations and 19 Senate PDF representations. The official
  documents are snapshotted and format-validated.
- 335 official APH Senate divisions parsed from Senate Journals PDFs, with
  18,715 matched senator-vote rows and zero unmatched current-senator votes.
- 399 They Vote For You civic-source divisions loaded for 2026-01-01 through
  2026-04-28: 55 House divisions, 24 Senate divisions not already represented
  by official APH keys, and TVFY enrichment attached to 320 official APH Senate
  divisions. TVFY person-vote context is attached to 17,263 official APH
  senator-vote rows, with 8,084 TVFY-only person-vote rows retained mainly for
  House divisions pending official House person-vote parsing.
- Review-queue export commands now write auditable JSONL artifacts for official
  match candidates, benefit events, and inferred entity classifications under
  `data/audit/review_queues/`.
- Reviewed decisions can be imported with a dry-run-first command that stores
  append-only decision records and applies only conflict-checked/manual overlay
  updates.
- Sector-policy link suggestions can be exported for human review with
  `suggest-sector-policy-links`; suggestions do not mutate the database and do
  not make source-to-effect claims until reviewed evidence is imported.

## Reproducible Pipeline

The main federal workflow is now a single auditable command:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline
```

It writes a run manifest under `data/audit/pipeline_runs/`.

The pipeline currently archives and normalizes:

- APH current MP/Senator roster CSVs.
- AEC annual and election disclosure bulk data. Election rows are treated as
  source disclosure observations, with cross-table duplicate observations
  retained for audit but excluded from reported-total sums.
- AEC current national federal electorate boundary shapefile and GeoJSON/PostGIS
  source boundary layer, plus AIMS/eAtlas/AODN Coastline 50K-backed land-clipped
  display geometry for the web map.
- Senate register JSON records from the official APH-backed Senate interests API.
- House register PDF text/OCR, numbered sections, and structured interest records.
- Official APH House Votes and Proceedings and Senate Journals current
  decision-record indexes plus linked ParlInfo HTML/PDF snapshots. Current
  Senate Journals PDFs are parsed into official Senate division/person-vote
  records.
- Rule-based entity and public-interest-sector classifications.
- Official identifier source discovery and the Australian Government Register of
  Lobbyists API snapshot. ASIC, ABN Bulk Extract, and ACNC parsers are implemented
  for official extracts; local data.gov.au access currently returned HTTP 403 in
  this environment, so those bulk extracts are staged but not yet loaded here.
- Optional They Vote For You division/vote API ingestion. This is a third-party
  civic source and requires `THEY_VOTE_FOR_YOU_API_KEY`; stored metadata omits
  only the key while preserving the public API response body. The fetcher
  automatically splits capped date windows to avoid silent API truncation.

For CI/development:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline --smoke
```

See `docs/reproducibility.md` and `docs/operations.md`.

## Local API

The first read-only FastAPI layer is available for frontend development:

```bash
cd backend
make api-dev
```

It serves global search and source-to-policy context endpoints at
`http://127.0.0.1:8008`; see `docs/api.md`. The map endpoint defaults to a
low-tolerance interactive geometry and can emit exact source geometry for strict
QA. `/api/coverage` exposes source-family coverage so map-linked representative
counts are not confused with whole-database party/entity/return-level money-flow
counts. Postcode search is exposed with a limitation response until a source-backed
postcode/locality-to-electorate crosswalk is ingested.

## Standards

Every public claim should eventually link to:

1. The source document or official page.
2. The parser/extractor version.
3. The normalized database record.
4. The confidence level for entity matching and industry classification.
5. A human-readable caveat where the evidence is incomplete or ambiguous.
