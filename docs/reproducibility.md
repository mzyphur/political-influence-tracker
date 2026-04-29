# Reproducibility and Auto-Update Standard

Last updated: 2026-04-29

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

## Current Subnational Pipeline

The first active state/local adapter is Queensland ECQ EDS. It is deliberately
separate from the federal foundation command while the state/council framework
is being generalized.

```bash
cd backend
.venv/bin/python -m au_politics_money.cli fetch-source qld_ecq_eds_public_map
.venv/bin/python -m au_politics_money.cli fetch-source qld_ecq_eds_expenditures
.venv/bin/python -m au_politics_money.cli fetch-qld-ecq-eds-exports
.venv/bin/python -m au_politics_money.cli normalize-qld-ecq-eds-money-flows
```

The export fetcher does not depend on a manual browser download. It reads the
latest archived ECQ EDS public map and expenditure pages, extracts their current
HTML form fields, and posts those source-backed fields to the official ECQ CSV
export endpoints. Raw CSV bodies and request/response metadata are archived
under:

```text
data/raw/qld_ecq_eds_map_export_csv/<timestamp>/
data/raw/qld_ecq_eds_expenditure_export_csv/<timestamp>/
```

The normalizer writes:

```text
data/processed/qld_ecq_eds_money_flows/<timestamp>.jsonl
data/processed/qld_ecq_eds_money_flows/<timestamp>.summary.json
```

Current normalized coverage is 49,839 rows: 22,726 gift/donation rows and
27,113 electoral expenditure rows. Gift/donation rows are normalized as
state/local money records at the actor level supported by the ECQ export.
Electoral expenditure rows are normalized as `campaign_support` with event type
`state_local_electoral_expenditure`; they must not be described as money
received personally by a representative.

The serving database loader includes the latest processed QLD ECQ EDS artifact
when money-flow loading is enabled:

```bash
cd backend
export DATABASE_URL=postgresql://au_politics:change-me-local-only@localhost:54329/au_politics
.venv/bin/python -m au_politics_money.cli load-postgres
```

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

When `--apply-schema` is used, the loader applies the baseline schema and then
all additive migrations. Routine weekly runs should use `migrate-postgres`
followed by `load-postgres --include-vote-divisions` so the serving database is
updated from the newest reproducible artifacts.

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
   Direct MP/Senator return rows are person-linked only when the recipient name
   is a unique exact cleaned-name match against the reproducible APH roster.
   Titles and postnominals are stripped, but ambiguous/unmatched rows remain
   unlinked with audit metadata rather than being guessed.
   AEC transaction dates are accepted into the serving date field only when
   they parse and fall inside the row's declared financial year; source dates
   outside that window remain preserved in metadata with a
   `date_validation.status` value instead of being exposed as event dates.
7. Fetch the current national AEC ESRI federal-boundary ZIP.
8. Transform AEC federal boundaries from source CRS to GeoJSON/PostGIS SRID 4326.
9. Fetch/extract the AIMS/eAtlas/AODN Australian Coastline 50K land-area
   polygons, with Natural Earth retained as a fallback/general-country mask,
   then derive `land_clipped_display` geometry for interactive maps. The
   display geometry uses a documented local coastline repair buffer applied in
   EPSG:3577 Australian Albers metres so minor mask/basemap offsets do not cut
   away shoreline land. This is display-only; official AEC boundary geometry
   remains unchanged. Because the AIMS/eAtlas/AODN catalogue currently lists
   the licence as "Not Specified", raw/processed coastline files are not public
   release artifacts until reuse terms are confirmed; source limitations are
   carried in loader metadata.
10. Extract official APH decision-record indexes for House Votes and
   Proceedings and Senate Journals.
11. Archive linked ParlInfo HTML/PDF decision-record representations as raw
    source snapshots, using source-specific transparent request headers where a
    public source requires browser-compatible access.
    The processed fetch summary stores the APH index-to-document linkage and
    validation result, so existing raw metadata does not need to be rewritten
    when an already-fetched snapshot is reused.
    House Votes and Proceedings index rows link to ParlInfo HTML pages; the
    fetcher derives and archives the embedded official PDF representation from
    the HTML so later parsing remains reproducible from public APH/ParlInfo
    evidence.
11. Parse current official APH Senate Journals and House Votes and Proceedings
    PDF division blocks into division and person-vote JSONL records. Official
    division counts are preserved separately from current-roster matching: a
    raw official vote name that is not present in the current roster remains in
    the artifact as an unmatched roster vote instead of being guessed or
    dropped.
12. Fetch House interests PDFs.
13. Extract House interests PDF text.
14. Split House interests into numbered register sections.
15. Fetch Senate statement-list JSON and per-senator statement-detail JSON from the official APH-backed API.
16. Flatten Senate interest categories, gifts, travel/hospitality, liabilities, and alterations into JSONL records.
17. Conservatively extract benefit provider, value, event date, and report date
    fields from House and Senate interest descriptions when the text uses
    explicit phrases such as "provided by", "hosted by", "at invitation of",
    "valued at", "worth", or a parseable date. A narrow branded-benefit pass
    also identifies source providers for recurring named benefits such as
    Qantas Chairman's Lounge, Virgin lounge/club access, airline upgrades, and
    Foxtel subscriptions. Non-disclosed values/dates remain labelled as missing
    rather than inferred.
18. Optional, when `THEY_VOTE_FOR_YOU_API_KEY` is available: fetch They Vote For
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
- Weekly PostgreSQL migration and reload after the full run.
- Daily lightweight source-index check.
- Manual review queue after each run.
- Manual review decisions stored separately from machine-produced records.
- Party/entity link candidates are materialized from party-name family patterns
  and AEC money-flow context before review replay, so accepted/rejected
  decisions can be replayed after a database rebuild without overwriting the
  original candidate evidence.
- QLD ECQ EDS export rows should be refreshed on the same cadence as the state
  source pages. Because the EDS covers state and local disclosures, downstream
  state/council UI surfaces should show source-family coverage and caveats
  before presenting row counts as complete jurisdictional coverage.
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
