# Operations

Last updated: 2026-04-29

## Local Setup

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
make install
make test
make lint
```

The default test command skips the PostgreSQL integration test unless
`DATABASE_URL_TEST` is set. With the local Docker database running, use:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
AUPOL_RUN_POSTGRES_INTEGRATION=1 \
  DATABASE_URL_TEST=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \
  .venv/bin/python -m pytest tests/test_postgres_integration.py -q
```

The integration test creates and drops an isolated temporary schema. It applies
the current baseline plus all incremental migrations, then exercises real
FastAPI SQL query paths against seeded fixture data.

## Run the Federal Pipeline

Production-style full run:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline \
    --refresh-existing-sources --include-votes
```

Development smoke run:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline --smoke
```

## Subnational Source Smoke Fetch

Before writing state or council parsers, archive the official source landing
pages through the same raw-source workflow used by the federal pipeline:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics"
./scripts/fetch_state_council_seed_sources.sh
```

The script fetches the seed source IDs registered in
`backend/au_politics_money/ingest/sources.py` for NSW, Victoria, Queensland,
South Australia, Western Australia, Tasmania, Northern Territory, and the ACT.
It writes raw source bodies and metadata under `data/raw/` and command logs
under `data/audit/logs/`. Parsing remains a separate step so acquisition,
normalization, and interpretation stay reproducible and auditable.

## Queensland ECQ EDS State/Local Exports

Queensland is the first active state/local electoral-finance adapter. Refresh
the official ECQ EDS source pages, fetch the current CSV exports from the
archived page form fields, and normalize them into money-flow artifacts with a
single manifest-producing command:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
MANIFEST=$(.venv/bin/python -m au_politics_money.cli run-state-local-pipeline --jurisdiction qld)
.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli load-state-local-pipeline-manifest "$MANIFEST"
```

The state/local pipeline writes a reproducibility manifest under
`data/audit/pipeline_runs/`. It fetches the ECQ form pages and lookup API
snapshots, fetches both current ECQ CSV exports, and normalizes money-flow,
participant, and event/local-electorate context artifacts. The loader is kept
separate so database mutation remains an explicit step after source acquisition
and normalization have succeeded. Within the runner, later steps receive the
exact metadata paths produced by earlier steps rather than re-reading an
ambient "latest" snapshot; this keeps a manifest tied to the artifacts it
actually normalized. `load-state-local-pipeline-manifest` then reads that same
manifest, opens the normalizer summaries it references, and loads those exact
processed JSONL files.

The fetcher archives raw CSV bodies and metadata under
`data/raw/qld_ecq_eds_map_export_csv/` and
`data/raw/qld_ecq_eds_expenditure_export_csv/`. The normalized JSONL artifact
is written under `data/processed/qld_ecq_eds_money_flows/`. Participant lookup
normalization reads the archived ECQ APIs for political electors/candidates,
political parties, associated entities, and local groups, then writes
`data/processed/qld_ecq_eds_participants/`. Context normalization reads archived
ECQ political-event and local-electorate lookup APIs, then writes
`data/processed/qld_ecq_eds_contexts/`. The participant and context normalizers
can fetch a missing lookup snapshot, but reproducible runs should fetch the
lookup source IDs explicitly first so raw acquisition remains visible in the
audit log.
`load-qld-ecq-eds-money-flows` refreshes just this source family and rebuilds
the derived `influence_event` surface. It also applies the latest participant
identifier and event/local-electorate context artifacts when present. To refresh
identifiers or contexts only after reviewing a new lookup snapshot, run:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli load-qld-ecq-eds-participants
.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli load-qld-ecq-eds-contexts
```

For exact replay from a reviewed artifact bundle, the QLD loader commands also
accept explicit processed JSONL paths: `--money-flows-path`,
`--participants-path`, `--contexts-path`, and `--jsonl-path` on the individual
participant/context loaders. Omit those flags only when loading the most recent
processed artifacts is intentional. Prefer `load-state-local-pipeline-manifest`
for normal scheduled QLD refreshes because it performs that exact-artifact
selection from the pipeline manifest.

Use `--skip-influence-events` only for a fast money-flow-table inspection where
the public API does not need to be current yet. The full `load-postgres` command
also loads QLD ECQ EDS rows and participant identifiers by default, but
federal-only scheduled runs use `load-postgres --skip-qld-ecq` so stale QLD
artifacts are not promoted when the QLD fetch/normalize steps did not run.
Public QLD API summaries read only `money_flow.is_current = true` rows.

ECQ gift/donation rows are money records. ECQ expenditure rows are
campaign-support records with event type `state_local_electoral_expenditure`;
they are campaign activity, not personal receipt by a representative.
ECQ lookup identifiers are evidence-backed for participants exposed by those
public lookup APIs. Political party, associated-entity, and local-group
identifiers are auto-attached only for exact unique lookup-to-disclosure-actor
matches. Candidate/elector lookup matches stay in the manual-review layer unless
future event/electorate/role evidence strengthens the match. Donor names remain
free-text unless the donor also matches an accepted ECQ participant lookup
record; this is a source limitation, not a manual redaction. Political-event
and local-electorate lookup matches are stored as disclosure context only:
event dates describe the election event, not the transaction date, and local
electorate names must not be treated as candidate/councillor identity or map
geometry without further source evidence.

## Frontend Development

Start the backend API:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
.venv/bin/dotenv -f .env run -- .venv/bin/uvicorn au_politics_money.api.app:app --reload --host 127.0.0.1 --port 8008
```

Start the frontend:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/frontend"
npm run dev
```

The frontend reads `VITE_API_BASE_URL` and `VITE_MAPTILER_API_KEY`. The Vite
dev server proxies `/api` and `/health` to the backend so browser requests stay
same-origin during local development.

## Weekly Server Command

The repo includes:

```text
scripts/run_weekly_federal_pipeline.sh
```

Run it from cron, systemd, launchd, or a CI runner.
The script loads `backend/.env` and includes optional vote ingestion only when
`THEY_VOTE_FOR_YOU_API_KEY` or `TVFY_API_KEY` is present. When neither key is
set, the weekly run writes a `weekly_federal_votes_<timestamp>.skipped.log`
file and still refreshes the rest of the federal database. The federal pipeline
runs with `--refresh-existing-sources`, so update-sensitive cached sources such
as AEC postcode lookups, current AEC boundaries, and official APH
decision-record documents are fetched again instead of being silently reused.
The weekly federal load also uses `--skip-qld-ecq`; QLD state/local rows should
be refreshed by the QLD-specific commands above.
After loading, the script runs `qa-serving-database`. That QA gate fails the
weekly run before the database is treated as releasable if core serving
invariants break, including missing House boundaries, active events pointing at
non-current source rows, obvious House form/OCR boilerplate in public events,
official APH vote-count mismatches, or unexpected unmatched official APH votes.
The weekly runner also passes conservative minimum serving-count thresholds for
current influence events, person-linked events, current money-flow rows, current
interest rows, and current House/Senate office terms so a sharp source-refresh
drop fails loudly instead of publishing an empty-looking interface.
Official APH vote QA reads only current `vote_division` rows; withdrawn or
corrected official rows remain auditable but do not fail serving checks. The
default unmatched-vote tolerance is 25 rows, currently above the 11 known
unmatched official APH roster-vote rows in the local baseline.

New backend virtual environments created by the weekly runner and CI install
with `backend/requirements.lock` as a constraints file. Update that file
intentionally when dependency upgrades are part of the work.

Example cron entry for a server using UTC, running Sundays at 18:00 UTC
which is Monday morning in eastern Australia depending on daylight saving:

```cron
0 18 * * 0 /path/to/AU\ Politics/scripts/run_weekly_federal_pipeline.sh
```

## Database

Docker Desktop is the local container runtime. On Apple Silicon, the current
`postgis/postgis:16-3.4` image runs as `linux/amd64`, which is explicit in
`backend/docker-compose.yml`.

Start local PostgreSQL/PostGIS:

```bash
cd backend
cp .env.example .env
docker compose up -d
```

Initial schema:

```bash
psql "$DATABASE_URL" -f schema/001_initial.sql
```

Load the latest processed roster, AEC annual money-flow artifacts, AEC federal
boundaries, House interest records, Senate interest records, and the derived
unified influence event surface. By default this also loads the latest official
APH House Votes and Proceedings / Senate Journals index artifacts when present:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli load-postgres --apply-schema
```

The loader is idempotent for the current schema: source documents, people,
office terms, parties, electorates, boundaries, entities, AEC annual money-flow
rows, House interest records, Senate interest records, and official APH
decision-record index rows use stable keys or uniqueness constraints.

To skip a layer during development:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli load-postgres --skip-senate-interests
```

Regenerate only the derived unified influence events after `money_flow` and
`gift_interest` already exist:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-postgres \
  --skip-roster --skip-money-flows --skip-house-interests \
  --skip-senate-interests --skip-entity-classifications \
  --skip-official-identifiers --skip-official-decision-records \
  --skip-official-decision-record-documents
```

Regenerate only the House PDF-derived layers after PDF text has already been
extracted:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli extract-house-interest-sections
.venv/bin/python -m au_politics_money.cli extract-house-interest-records
```

Regenerate entity/industry classifications from the latest processed money-flow
and interest artifacts:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli classify-entities
```

Regenerate only AEC current federal House boundaries:

```bash
cd backend
.venv/bin/au-politics-money fetch-current-aec-boundaries
.venv/bin/au-politics-money extract-aec-boundaries
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-postgres \
  --skip-roster --skip-money-flows --skip-house-interests \
  --skip-senate-interests --skip-influence-events \
  --skip-entity-classifications --skip-official-identifiers \
  --skip-official-decision-records --skip-official-decision-record-documents
```

The canonical boundary layer uses the full AEC national ESRI shapefile. The
processed GeoJSON and PostGIS rows are SRID 4326; the raw AEC shapefile source
CRS and DBF attributes remain in metadata. The serving API defaults to a
separate `land_clipped_display` derivative produced from AIMS/eAtlas/AODN
Australian Coastline 50K land-area polygons, plus a small local coastline
repair buffer inside each official AEC boundary. The buffer is applied in
EPSG:3577 Australian Albers metres, documented in metadata, and handles minor
mask/basemap alignment differences while avoiding the broad sea fill caused by
coarser global masks. Natural Earth land masks remain available as fallback
inputs for non-Australian/generalised display work. The official AEC geometry
remains preserved for audit.
The AIMS/eAtlas/AODN catalogue currently lists the licence as "Not Specified",
so raw and processed coastline files must not be redistributed in public
releases until reuse terms are confirmed. The source page also documents known
failure modes, including occasional false land from turbid water, shallow water,
breaking waves, jetties, oil rigs, bridges, and some filled ocean-connected
rivers/water bodies. Treat this geometry as a display aid only, never as a legal
or electoral boundary.

```bash
cd backend
.venv/bin/au-politics-money fetch-aims-coastline-land-mask
.venv/bin/au-politics-money extract-aims-coastline-land-mask
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-display-geometries \
  --coastline-repair-buffer-meters 100
```

They Vote For You division/vote ingestion:

```bash
cd backend
# Add THEY_VOTE_FOR_YOU_API_KEY=... to .env first. Do not commit the value.
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money \
  fetch-they-vote-for-you-divisions \
  --start-date 2026-01-01 --end-date 2026-04-28
.venv/bin/au-politics-money extract-they-vote-for-you-divisions
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-postgres \
  --skip-roster --skip-money-flows --skip-house-interests \
  --skip-senate-interests --skip-electorate-boundaries \
  --skip-influence-events --skip-entity-classifications \
  --skip-official-identifiers --skip-official-decision-records \
  --skip-official-decision-record-documents --include-vote-divisions
```

They Vote For You returns at most 100 divisions per list request. The fetcher
automatically splits capped date windows and records both the split probes and
accepted child windows in the processed summary. It still fails closed if a
single-day request returns 100 records, unless `--allow-truncated` is passed
after confirming the expected loss. This source is labelled
`third_party_civic`, not official parliamentary record.

Official APH decision-record indexes:

```bash
cd backend
.venv/bin/au-politics-money extract-aph-decision-record-index --all
.venv/bin/au-politics-money fetch-aph-decision-record-documents --only-missing
.venv/bin/au-politics-money extract-official-aph-divisions
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-postgres \
  --skip-roster --skip-money-flows --skip-house-interests \
  --skip-senate-interests --skip-electorate-boundaries \
  --skip-influence-events --skip-entity-classifications \
  --skip-official-identifiers --skip-review-reapply
```

Current index extraction is deliberately date-record scoped: House consolidated
PDFs and other related links are not loaded as separate sitting-day records.
Senate rows merge the PDF and HTML ParlInfo representations for the same
journal into one canonical index record. These rows have evidence status
`official_record_index`. `fetch-aph-decision-record-documents` archives the
linked ParlInfo HTML/PDF bodies as raw source snapshots and records the request
headers used for reproducible public access. `extract-official-aph-divisions`
currently parses Senate Journals PDF division blocks into official
division/person-vote rows; House vote-content parsing remains a later source
format task.

Official identifier enrichment:

```bash
cd backend
.venv/bin/au-politics-money fetch-lobbyist-register
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money migrate-postgres
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-postgres \
  --skip-roster --skip-money-flows --skip-house-interests \
  --skip-senate-interests --skip-entity-classifications \
  --skip-official-decision-records --skip-official-decision-record-documents
```

Official identifier bulk enrichment and targeted ABN Lookup web-service
enrichment for a reviewed ABN or ACN:

```bash
cd backend
.venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money discover-official-identifier-sources
.venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money fetch-official-identifier-bulk \
    --source-id asic_companies_dataset \
    --source-id acnc_register \
    --extract-limit-per-source 5000
.venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money fetch-abn-lookup-web abn "51 824 753 556"
.venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money fetch-abn-lookup-web acn "123 456 780"
```

`fetch-official-identifier-bulk` reads the data.gov CKAN discovery artifact,
selects supported ASIC, ACNC, and ABN Bulk resources using source-specific
hints, archives each selected body plus metadata under `data/raw/`, and emits
one `official_identifier_record_v1` snapshot JSONL per source under
`data/processed/official_identifiers/`. ABN Bulk resources can be multi-part;
the fetcher groups selected ABN parts into one source snapshot so the loader
does not accidentally treat only the newest part as current. Omit
`--extract-limit-per-source` for a full refresh. Use
`run-federal-foundation-pipeline --include-official-identifier-bulk` when a
scheduled run should refresh these large bulk files; smoke runs cap extraction
per source.

This uses the current ABN Lookup document-style methods
`SearchByABNv202001` and `SearchByASICv201408`, archives the returned XML,
writes redacted metadata under `data/raw/abn_lookup/`, and emits
`official_identifier_record_v1` JSONL under `data/processed/official_identifiers/`.
These targeted web-service JSONL files are treated as incremental artifacts in
raw/processed storage. The loader selects all incremental ABN/ACN lookup files
but upserts repeated refreshes of the same ABN/ACN to one current database
observation keyed by the official identifier.
`ABN_LOOKUP_GUID` is read from the environment only and is redacted if the
service echoes it. The web-service path is for targeted, cached enrichment of
reviewed identifiers; do not run high-volume sweeps until ABN Lookup terms,
permitted use, and rate limits are documented. Trading names from ABN Lookup
must be treated as historical-only evidence because the ABR stopped collecting
or updating them in May 2012 and gives them no legal status.
ABN web-service responses containing ABR exception payloads, including
`No records found`, fail closed and write a failure summary rather than a
loadable official-identifier artifact.

The loader stores official identifier observations and match candidates first.
It does not attach ABNs/ACNs/register IDs to existing money-flow entities on
name alone. Exact-name-only matches remain `needs_review` until an identifier
or manual decision supports the mapping.

Review queues for ambiguous or incomplete evidence:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money export-review-queue official-match-candidates
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money export-review-queue benefit-events
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money export-review-queue entity-classifications
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money export-review-queue sector-policy-links
```

Add `--limit 5000` or similar for a working slice. Exports write JSONL plus a
summary file under `data/audit/review_queues/`; the database also has
`manual_review_decision` for later reviewer decisions without overwriting the
machine-produced record.

Sector-policy link suggestions:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money suggest-sector-policy-links
```

This writes review prompts under `data/audit/sector_policy_link_suggestions/`.
Suggestions do not mutate the database and do not create
`sector_policy_topic_link` rows. Draft review decisions are intentionally set to
`needs_more_evidence` and include a blank `sector_material_interest` source so a
reviewer must add independent sector-interest evidence before importing an
accepted/revised decision.

Federal release review bundle:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money prepare-review-bundle
```

This materializes current `party_entity_link` candidates, exports the
`official-match-candidates`, `benefit-events`, `entity-classifications`,
`party-entity-links`, and `sector-policy-links` queues, runs sector-policy
suggestions, and writes a manifest under `data/audit/review_bundles/`. Use
`--limit` for smaller working files and `--limit-per-party` to restrict
party/entity candidate generation. The bundle is review input only: public
benefit, identifier, classification, and network claims still require imported
accepted/revised decisions with the supporting-source roles enforced by the
importer where those roles are required.

Reviewed decision import:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money import-review-decisions reviewed_decisions.jsonl
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money import-review-decisions reviewed_decisions.jsonl --apply
```

The first command is the default dry run. It validates the JSONL, computes the
input checksum, computes per-row decision hashes, and writes a summary under
`data/audit/review_imports/` without mutating PostgreSQL. `--apply` inserts
append-only `manual_review_decision` rows and applies only allowlisted side
effects:

- accepted official match candidates become `manual_accepted`, and identifiers,
  aliases, and official classifications are attached only when no identifier
  conflict exists;
- rejected official match candidates become `rejected`;
- accepted/revised entity classifications create a separate `method = 'manual'`
  classification row rather than overwriting the generated rule-based row;
- benefit/influence events only have review status/metadata updated. Raw source
  text, source documents, source references, and machine-derived fields are not
  overwritten;
- accepted/revised sector-policy link decisions upsert a reviewed
  `sector_policy_topic_link` row with confidence, evidence note, reviewer, and
  timestamp. These links gate the vote/influence context view and do not mutate
  vote records or influence events.
  Automatic `load-postgres` review replay defers sector-policy link decisions
  unless `--include-vote-divisions` is used, because those decisions depend on
  loaded `policy_topic` rows.

Manual sector-policy link decisions can be authored after policy topics exist:

```json
{
  "subject_type": "sector_policy_topic_link",
  "subject_external_key": "sector_policy_topic_link:fossil_fuels:they_vote_for_you_policy_99:direct_material_interest:manual",
  "decision": "accept",
  "reviewer": "m.zyphur@uq.edu.au",
  "evidence_note": "The policy topic concerns fossil-fuel regulation; fossil-fuel producers have a direct material interest in the policy outcome.",
  "proposed_changes": {
    "public_sector": "fossil_fuels",
    "topic_slug": "they_vote_for_you_policy_99",
    "relationship": "direct_material_interest",
    "method": "manual",
    "confidence": "0.900"
  },
  "supporting_sources": [
    {
      "evidence_role": "topic_scope",
      "url": "https://theyvoteforyou.org.au/policies/99",
      "note": "Specific policy/topic or division source; use the actual topic/division URL from the reviewed export."
    },
    {
      "evidence_role": "sector_material_interest",
      "url": "https://www.aph.gov.au/Parliamentary_Business/Chamber_documents/HoR/Votes_and_Proceedings",
      "note": "Replace with the specific official, academic, regulator, company, or industry source supporting the sector's material interest."
    }
  ]
}
```

Accepted or revised sector-policy link decisions require role-specific
`supporting_sources` for both `topic_scope` and `sector_material_interest`; a
generic API documentation URL is not enough for public display.

Review exports include stable `subject_external_key` values and
`review_subject_fingerprint` values. Numeric row IDs are treated as hints, not
the durable identity of a reviewed subject; entity-based keys and fingerprints
use normalized names, entity type, and source stable keys rather than database
surrogate IDs.
If a fingerprint changes between export and import, the importer fails so the
row can be re-exported and reviewed against the current evidence.

After a normal data reload, replay stored decisions so regenerated machine rows
receive the current manual overlays again:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money reapply-review-decisions
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money reapply-review-decisions --apply
```

Use `--subject-type entity_match_candidate`, `--subject-type influence_event`,
or `--subject-type entity_industry_classification` to replay a narrower slice.
The first command is a dry run; `--apply` mutates PostgreSQL. The command is
idempotent and uses the same conflict checks as the importer. Review queues also
suppress rows with existing accepted/rejected/revised decisions by stable
`subject_external_key` only while the reviewed fingerprint still matches, so
changed evidence is re-queued instead of hidden.

`load-postgres` runs this replay step in apply mode by default after the
selected load layers.
Use `--skip-review-reapply` only when debugging loader behavior before manual
overlays are applied.

If Docker is unavailable on a development machine, still run the unit tests and
smoke pipeline; the database loader should then be verified on the first machine
with PostgreSQL/PostGIS available.

Quick database count check:

```bash
cd backend
docker compose exec -T postgres psql -U au_politics -d au_politics \
  -c "select count(*) from money_flow;"
```

Current local baseline after the 2026-04-29 federal/state-local load:

- `person`: 226, including one House-register-derived fallback person for Sussan Ley/Farrer because the APH contact CSV omitted that seat.
- `office_term`: 226.
- `money_flow`: 294,707 rows: AEC annual/election/public-funding records plus
  active QLD ECQ state/local disclosure rows.
- `gift_interest`: 7,639 total rows: 5,838 current House rows, 49
  non-current House rows retained for audit, and 1,752 current Senate rows.
  Non-current source rows are excluded from active public `influence_event`
  totals.
- `gift_interest` current gift/travel subset: House gifts 531, House sponsored
  travel/hospitality 309, Senate gifts 227, Senate sponsored
  travel/hospitality 263.
- `electorate_boundary`: 150 current federal House boundaries in `aec_federal_2025_current`; all canonical source geometries are SRID 4326, valid, and non-empty.
- `electorate_boundary_display_geometry`: 150 `land_clipped_display` rows for web-map use.
- `influence_event`: 302,297 non-rejected derived rows: 217,531 money events, 77,176 campaign-support events, 1,406 benefit events, 4,700 private-interest events, 1,384 organisational-role events, and 100 other declared interests.
- `influence_event` benefit subtypes include 386 membership/lounge access rows, 288 event ticket/pass rows, 69 private-aircraft/flight rows, 42 meal/reception rows, 24 accommodation rows, and 83 subscription/service rows; most benefit records do not disclose value.
- `entity_industry_classification`: 35,874 generated rows from `public_interest_sector_rules_v1`.
- `official_identifier_observation`: 3,591 unique official observations: 3,590 current lobbyist-register observations from 3,602 parsed rows plus one ABN Lookup web-service smoke record for BHP Group Limited.
- `entity_match_candidate`: 2,092 match candidates across official identifiers and QLD ECQ participant lookups; no official identifiers are attached by name alone.
- `official_parliamentary_decision_record`: 72 APH current decision-record
  index rows: 53 House Votes and Proceedings records and 19 Senate Journal
  records, all dated, with Senate PDF/HTML ParlInfo alternatives retained as
  representations on one canonical row per sitting day.
- `official_parliamentary_decision_record_document`: 91 linked ParlInfo raw
  snapshots: 72 HTML representations and 19 Senate PDF representations, linked
  to all 72 APH current decision-record rows through `source_document`.
- `vote_division`: 335 official APH Senate divisions parsed from Senate
  Journals PDFs across 19 sitting dates from 2026-01-19 to 2026-04-01.
- `person_vote`: 18,715 official APH senator-vote rows, all matched to current
  senator records.
- They Vote For You civic-source load after adding
  `THEY_VOTE_FOR_YOU_API_KEY`: 399 divisions for 2026-01-01 through
  2026-04-28, including 55 House divisions, 24 TVFY-only Senate divisions, and
  TVFY enrichment attached to 320 official APH Senate divisions. Person-vote
  context from TVFY is attached to 17,263 official APH senator-vote rows, with
  8,084 TVFY-only person-vote rows retained mainly for House divisions pending
  official House person-vote parsing.
- Current review queue exports should include the official identifier match
  candidates, QLD ECQ participant match candidates, benefit events with
  extraction or missing-data review flags, and inferred entity classifications
  recommended for review. QLD ECQ lookup hits are still review candidates unless
  an importer has explicitly accepted the match.
- Current classifier sector totals include 14,833 `individual_uncoded`, 1,482 `unions`, 1,017 `finance`, 904 `political_entity`, 582 `property_development`, 278 `mining`, and 205 `fossil_fuels`.
- They Vote For You list requests are recursively split when the API returns
  its 100-record cap; a one-day capped response still fails closed unless
  `--allow-truncated` is explicitly supplied.
- `person_policy_vote_summary`, `person_influence_sector_summary`, and
  `person_policy_influence_context` are analytical views for the future app.
  The context view only emits rows after a reviewed `sector_policy_topic_link`
  record exists, so money/gift/interest sectors are not linked to policy topics
  by implication alone. Context rows also bucket influence events as before,
  during, after, or unknown relative to the linked topic-vote span.

## Operational Checks

After each scheduled run, check:

- Latest manifest in `data/audit/pipeline_runs/`.
- Pipeline `status == succeeded`.
- No step-level errors.
- Source fetch HTTP status codes are 2xx/3xx.
- Counts are within expected ranges.
- New PDFs or CSV columns are reviewed.
- OCR-needed PDFs are queued.
- Any APH contact CSV and House interests register member-count mismatch is reviewed.
- House structured extraction summaries are checked for explanatory-note/header leakage and duplicate external keys.
- Entity classification summaries are checked for broad-rule false positives before database load.
- Any sector used for public-facing claims is marked as inferred unless backed by official identifiers or manual review.
- Any sector-to-policy linkage used to place influence evidence beside vote
  behaviour is stored in `sector_policy_topic_link` with method, confidence,
  evidence note, review status, and reviewer fields.
- Review-queue exports are generated and archived for any public snapshot.
- Boundary load checks show 150 geometries, 150 distinct electorates, SRID 4326,
  and no current House electorate missing a boundary.
- Official APH decision-record index checks show non-zero House and Senate
  counts, zero missing `record_date`, and no duplicate Senate rows for PDF/HTML
  alternatives.
- Official APH decision-record document checks show zero failed fetches and a
  document link count matching current index representations: 72 HTML and 19
  PDF in the current local baseline. Validation should show 72 `html_signature`
  rows and 19 `pdf_signature` rows.
- Official APH division checks show zero count-mismatch divisions and zero
  unmatched senator votes before database loading.

## Known Current Limitations

- House PDF records are structured into declaration lines, but table interpretation remains heuristic and should be sampled before public analytical claims.
- OCR fallback is implemented for low-text House PDF pages, but OCR-derived names/electorates still need QA sampling.
- Senate interests API ingestion is implemented; House interests rely on PDF text/OCR extraction.
- Entity/industry classification is currently rule-based unless a row is explicitly `method = 'official'`. The first official lobbyist-register observations are loaded, but exact-name-only matches remain in a manual-review queue.
- Local data.gov.au CKAN access for ASIC, ACNC, and ABN Bulk Extract returned HTTP 403 in this environment on 2026-04-27. Discovery now fails closed after writing the failure artifact so weekly runs do not silently proceed without those sources.
- AEC boundary ingestion preserves the full-resolution canonical boundary layer
  and now also derives a `land_clipped_display` map geometry. Future vector-tile
  work should use the display role by default and expose source geometry only
  through explicit QA/research controls.
- They Vote For You is a civic data source, not the official parliamentary
  source of record. The importer preserves that caveat and should later be
  cross-checked against official Hansard, Votes and Proceedings, and Senate
  Journals data.
- Current APH official vote parsing covers Senate Journals PDF division blocks.
  House Votes and Proceedings parsing is not yet person-vote complete, and
  voice votes/party-room decisions remain outside division-level data.
- Current APH decision-record discovery covers the present House/Senate index
  pages. Historical House parliament pages and Senate year pages still need
  date-range-aware discovery before older vote backfills can be fully checked
  against official records.
