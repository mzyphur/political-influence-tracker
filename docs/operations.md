# Operations

Last updated: 2026-04-27

## Local Setup

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
make install
make test
make lint
```

## Run the Federal Pipeline

Production-style full run:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline
```

Development smoke run:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline --smoke
```

## Weekly Server Command

The repo includes:

```text
scripts/run_weekly_federal_pipeline.sh
```

Run it from cron, systemd, launchd, or a CI runner.

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

Load the latest processed roster, AEC annual money-flow artifacts, House
interest records, and Senate interest records:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli load-postgres --apply-schema
```

The loader is idempotent for the current schema: source documents, people,
office terms, parties, electorates, entities, AEC annual money-flow rows, House
interest records, and Senate interest records use stable keys or uniqueness
constraints.

To skip a layer during development:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli load-postgres --skip-senate-interests
```

Regenerate only the House PDF-derived layers after PDF text has already been
extracted:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli extract-house-interest-sections
.venv/bin/python -m au_politics_money.cli extract-house-interest-records
```

If Docker is unavailable on a development machine, still run the unit tests and
smoke pipeline; the database loader should then be verified on the first machine
with PostgreSQL/PostGIS available.

Quick database count check:

```bash
cd backend
docker compose exec -T postgres psql -U au_politics -d au_politics \
  -c "select count(*) from money_flow;"
```

Current local baseline after the 2026-04-27 federal load:

- `person`: 226, including one House-register-derived fallback person for Sussan Ley/Farrer because the APH contact CSV omitted that seat.
- `office_term`: 226.
- `money_flow`: 192,201 AEC annual rows.
- `gift_interest`: 7,605 total rows: 5,853 House and 1,752 Senate.
- `gift_interest` gift/travel subset: House gifts 538, House sponsored travel/hospitality 317, Senate gifts 227, Senate sponsored travel/hospitality 263.

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

## Known Current Limitations

- House PDF records are structured into declaration lines, but table interpretation remains heuristic and should be sampled before public analytical claims.
- OCR fallback is implemented for low-text House PDF pages, but OCR-derived names/electorates still need QA sampling.
- Senate interests API ingestion is implemented; House interests rely on PDF text/OCR extraction.
- AEC GIS ZIPs are discovered but not yet transformed into GeoJSON/PostGIS.
- They Vote For You API needs an API key before vote ingestion can run.
