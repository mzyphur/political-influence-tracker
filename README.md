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

## Current Structure

- `docs/` - planning, research standards, source inventory, and methodology.
- `backend/` - Python ingestion, normalization, and database code.
- `backend/schema/` - PostgreSQL/PostGIS schema drafts.
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

For a local PostgreSQL/PostGIS database:

```bash
cd backend
cp .env.example .env
docker compose up -d
```

The initial schema is in `backend/schema/001_initial.sql`.

Load the latest reproducible artifacts into PostgreSQL:

```bash
cd backend
export DATABASE_URL=postgresql://au_politics:change-me-local-only@localhost:54329/au_politics
.venv/bin/python -m au_politics_money.cli load-postgres --apply-schema
```

Current local federal baseline loaded into PostgreSQL:

- 192,201 AEC annual money-flow rows.
- 5,853 House interest records from PDF text/OCR extraction.
- 1,752 Senate interest records from the official APH-backed Senate interests API.
- 226 people/office terms, including one documented House-register-derived fallback for Sussan Ley/Farrer because the APH contact CSV omitted that House seat.
- 35,874 generated entity-sector classifications from `public_interest_sector_rules_v1`; these are inferred rule-based labels pending official identifier/manual-review enrichment.

## Reproducible Pipeline

The main federal workflow is now a single auditable command:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline
```

It writes a run manifest under `data/audit/pipeline_runs/`.

The pipeline currently archives and normalizes:

- APH current MP/Senator roster CSVs.
- AEC annual disclosure bulk data.
- Senate register JSON records from the official APH-backed Senate interests API.
- House register PDF text/OCR, numbered sections, and structured interest records.
- Rule-based entity and public-interest-sector classifications.

For CI/development:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline --smoke
```

See `docs/reproducibility.md` and `docs/operations.md`.

## Standards

Every public claim should eventually link to:

1. The source document or official page.
2. The parser/extractor version.
3. The normalized database record.
4. The confidence level for entity matching and industry classification.
5. A human-readable caveat where the evidence is incomplete or ambiguous.
