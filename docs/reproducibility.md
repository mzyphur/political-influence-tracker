# Reproducibility and Auto-Update Standard

Last updated: 2026-04-28

## Core Rule

The project must be reproducible from code plus public sources.

A reviewer should be able to:

1. Clone or copy the project code.
2. Install dependencies.
3. Run the declared pipeline command.
4. Recreate the raw source archive, processed outputs, and audit manifests.
5. Inspect every public claim back to source documents and parser versions.

Manual one-off data downloads are not acceptable as production workflow. Manual
inspection is allowed for parser design and QA, but any data-producing operation
must be captured in code and documented.

## Current Pipeline

The current federal foundation pipeline is:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline
```

For a fast verification run:

```bash
cd backend
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline --smoke
```

The smoke run executes all pipeline stages but limits House interests PDF work to
a small subset. It is for CI/development only, not production data publication.

## Database Rebuild

The database is rebuilt from processed artifacts, not hand-entered data:

```bash
cd backend
export DATABASE_URL=postgresql://au_politics:change-me-local-only@localhost:54329/au_politics
.venv/bin/python -m au_politics_money.cli load-postgres --apply-schema
```

The loader uses stable keys for source documents, people, current office terms,
entities, AEC annual money-flow rows, and Senate interest records so it can be
rerun after each scheduled pipeline run. The database is therefore a
serving/indexing layer over reproducible artifacts rather than the only copy of
the evidence.

## Pipeline Stages

The federal foundation pipeline currently performs:

1. Fetch official index/source files:
   - AEC Transparency Register downloads index.
   - APH contacts CSV index.
   - APH House interests register index.
   - APH Senate interests register app page.
   - AEC federal boundary GIS index.
   - AEC annual disclosure bulk ZIP.
   - APH House Votes and Proceedings current index.
   - APH Senate Journals current index.
2. Discover child links:
   - AEC bulk annual/election/referendum download links.
   - APH MP/Senator CSV links.
   - APH House interests PDF links.
   - APH Senate register `env.js` API configuration asset.
   - AEC GIS ZIP links.
   - APH current decision-record links for House Votes and Proceedings and
     Senate Journals.
3. Fetch APH roster CSV child files.
4. Build current federal Parliament roster JSON.
5. Summarize AEC annual disclosure ZIP schemas.
6. Normalize key AEC annual money-flow tables.
7. Fetch the current national AEC ESRI federal-boundary ZIP.
8. Transform AEC federal boundaries from source CRS to GeoJSON/PostGIS SRID 4326.
9. Extract official APH decision-record indexes for House Votes and
   Proceedings and Senate Journals.
10. Archive linked ParlInfo HTML/PDF decision-record representations as raw
    source snapshots, using source-specific transparent request headers where a
    public source requires browser-compatible access.
    The processed fetch summary stores the APH index-to-document linkage and
    validation result, so existing raw metadata does not need to be rewritten
    when an already-fetched snapshot is reused.
11. Parse current official APH Senate Journals PDF division blocks into
    division and senator-vote JSONL records.
12. Fetch House interests PDFs.
13. Extract House interests PDF text.
14. Split House interests into numbered register sections.
15. Fetch Senate statement-list JSON and per-senator statement-detail JSON from the official APH-backed API.
16. Flatten Senate interest categories, gifts, travel/hospitality, liabilities, and alterations into JSONL records.
17. Optional, when `THEY_VOTE_FOR_YOU_API_KEY` is available: fetch They Vote For
    You division lists/details, archive raw public JSON with API-key-free
    request metadata, and normalize divisions, votes, linked civic policies,
    and bills into JSONL. Date windows that hit the API's 100-record cap are
    split recursively; the fetcher still fails closed if a one-day window is
    capped.

## Audit Manifests

Every pipeline run writes a manifest to:

```text
data/audit/pipeline_runs/
```

Each manifest records:

- Pipeline name and run ID.
- Status.
- Start/end timestamps.
- Runtime.
- Python and package versions.
- Platform.
- Git commit if run inside a git repository.
- Pipeline parameters.
- Step-by-step output paths and errors.

Every raw source fetch writes metadata to:

```text
data/raw/<source_id>/<timestamp>/metadata.json
```

Each raw source metadata file records:

- Source ID/name/type.
- Original and final URL.
- Fetch timestamp.
- HTTP status.
- Content type and size.
- SHA-256 checksum.
- Raw body path.
- Response headers.
- Request headers used by the fetcher. This includes source-specific
  browser-compatible headers for ParlInfo, while retaining the project contact
  string for transparency.

Processed APH decision-record document summaries additionally record the current
APH index row, the linked ParlInfo representation URL, the raw metadata path,
and the HTML/PDF validation result used by the database loader.

## Delete-and-Rebuild Test

Before any public launch, we should regularly verify:

```bash
cd backend
rm -rf ../data/raw ../data/processed ../data/audit
.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline --smoke
.venv/bin/python -m au_politics_money.cli load-postgres --apply-schema
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

Do not run destructive delete commands without an explicit operator decision.

## Publication Policy

Publish:

- Source code.
- Schema.
- Source registry.
- Pipeline commands.
- Parser logic.
- Research standards.
- Data dictionary.
- Validation reports.

Potentially publish separately:

- Processed non-sensitive official-record extracts.
- Aggregate tables.
- Reproducible data snapshots with checksums.

Be cautious with:

- Public records containing addresses, signatures, or fields that are legally
  public but personally sensitive in context.
- Personal donor addresses where official sites publish them but reuse may raise
  privacy concerns.
- Any inferred entity resolution that has not been reviewed.
- Manual review decisions that include reviewer notes should be checked for
  private comments before public release, while preserving the reproducible
  decision logic and public evidence.

## Auto-Update Policy

Production should run weekly at first. A weekly cadence is enough for current
federal annual disclosure data and APH register changes. After 1 July 2026, the
AEC expedited disclosure regime may require daily or sub-daily checks during
election periods.

Recommended initial schedule:

- Weekly full run.
- Daily lightweight source-index check.
- Manual review queue after each run.
- Manual review decisions stored separately from machine-produced records.
- Vote/policy-topic artifacts should be included on the weekly federal run when
  API keys are available, because reviewed sector-policy links depend on loaded
  `policy_topic` rows. Loads without vote artifacts intentionally skip
  sector-policy link replay.
- Alert on source checksum changes, parser failures, large count shifts, or new
  unparsed source formats.
- For official APH decision records, weekly runs should refetch current
  representation URLs with `--only-missing` for routine operation, and full
  refetches should be scheduled periodically to detect changed hashes. The
  database links source-document snapshots by checksum so changed public bodies
  are added as new evidence rather than overwriting prior raw evidence.
