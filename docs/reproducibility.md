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

The active state/local adapters are deliberately separate from the federal
foundation command while the state/council framework is being generalized.
Queensland ECQ EDS, NSW aggregate donor-location context, ACT gift returns,
Northern Territory NTEC annual returns/annual gift returns, South Australia
ECSA return-record summaries, and the Victoria VEC funding register now have
manifest-producing runners:

```bash
cd backend
MANIFEST=$(.venv/bin/python -m au_politics_money.cli run-state-local-pipeline --jurisdiction qld)
.venv/bin/python -m au_politics_money.cli load-state-local-pipeline-manifest "$MANIFEST"

MANIFEST=$(.venv/bin/python -m au_politics_money.cli run-state-local-pipeline --jurisdiction act)
.venv/bin/python -m au_politics_money.cli load-state-local-pipeline-manifest "$MANIFEST"

MANIFEST=$(.venv/bin/python -m au_politics_money.cli run-state-local-pipeline --jurisdiction nt)
.venv/bin/python -m au_politics_money.cli load-state-local-pipeline-manifest "$MANIFEST"

MANIFEST=$(.venv/bin/python -m au_politics_money.cli run-state-local-pipeline --jurisdiction sa)
.venv/bin/python -m au_politics_money.cli load-state-local-pipeline-manifest "$MANIFEST"

MANIFEST=$(.venv/bin/python -m au_politics_money.cli run-state-local-pipeline --jurisdiction vic)
.venv/bin/python -m au_politics_money.cli load-state-local-pipeline-manifest "$MANIFEST"
```

`run-state-local-pipeline` performs acquisition and normalization only. It does
not mutate the serving database. Its manifest records `loads_database: false`
and the claim boundary that ECQ gift/donation rows, electoral expenditure rows,
participants, disclosure contexts, ACT gifts, NT annual-return/annual-gift
rows, and SA return-level summaries are source-backed state/local disclosure
records. SA rows are return-level portal index summaries rather than detailed
transactions or personal receipt. VEC funding rows are public-funding/admin/
policy context, not private donations, gifts, personal income, or automatic
claims about personal receipt by an MP, senator, state MP, or councillor.
Loading remains explicit through
`load-state-local-pipeline-manifest` or a source-specific loader. The runner
passes the exact fetched page, export, lookup, or document metadata paths into
downstream normalizers so the normalized artifacts can be traced to the same
run instead of an unrelated "latest" file.
The manifest loader reads the referenced normalizer summaries, checks that the
manifest still matches the summary files, verifies the JSONL artifact hashes and
expected QLD source scopes, and then loads those exact JSONL artifacts into
Postgres.
Manifests and summaries produced from 2026-04-29 onward include SHA-256 hashes
for the referenced output files. Older QLD manifests remain replayable when the
referenced local artifacts still exist; in that legacy case the loader computes
current file hashes and still validates normalizer names, expected source
scopes, non-zero record counts, JSONL row counts, and source-count totals before
loading.

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
data/processed/qld_ecq_eds_participants/<timestamp>.jsonl
data/processed/qld_ecq_eds_participants/<timestamp>.summary.json
data/processed/qld_ecq_eds_contexts/<timestamp>.jsonl
data/processed/qld_ecq_eds_contexts/<timestamp>.summary.json
```

Current normalized coverage is 49,838 rows: 22,725 gift/donation rows and
27,113 electoral expenditure rows. Gift/donation rows are normalized as
state/local money records at the actor level supported by the ECQ export.
Electoral expenditure rows are normalized as `campaign_support` with event type
`state_local_electoral_expenditure`; they must not be described as money
received personally by a representative.

The participant normalizer uses archived ECQ lookup APIs for
political electors/candidates, political parties, associated entities, and local
groups. The normalizer can fetch a missing lookup snapshot, but reproducible
runs should fetch the lookup source IDs explicitly before normalization. The
loader stores all lookup rows as official identifier observations. It
auto-accepts political-party, associated-entity, and local-group identifiers
onto an existing QLD money-flow entity only when the lookup name is unique and
exactly one existing QLD entity has the same normalized name. Candidate/elector
name-only matches remain `needs_review` until event, electorate, or role context
supports the identity. Duplicate lookup names and ambiguous matches also remain
`needs_review`; the original free-text money-flow evidence is not overwritten.

The first NSW adapter is intentionally narrower. It archives the official NSW
Electoral Commission 2023 State Election pre-election donation page and static
heatmap, then normalizes the embedded district table into
`data/processed/nsw_pre_election_donor_location_aggregates/`. Current normalized
coverage is 94 donor-location aggregate rows, 5,077 disclosed donations, and
$6,477,605.56 in reported amounts for the 1 Oct 2022 to 25 Mar 2023
pre-election period. These rows are stored as `aggregate_context_observation`
records, not `money_flow` records, because the heatmap does not identify the
recipient, donor entity, candidate, party, or MP for each aggregate row. The
public UI and API must label this family as aggregate donor-location context,
not representative receipt or donor-recipient flow. The NSW runner resolves and
checks the heatmap link from the official explanatory page on each run; the
summary and JSONL carry SHA-256 hashes for the source metadata and source body,
and manifest replay refuses to load rows if those hashes no longer match.
The source page caveat about unmapped donor locations and NSWEC Creative
Commons Attribution 4.0 requirements must be preserved in public displays and
derived data documentation.

The ACT adapter archives the official Elections ACT 2025-2026 gift-return page
and normalizes the current HTML tables into
`data/processed/act_gift_return_money_flows/`. Current normalized coverage is
225 rows: 206 gifts of money and 19 gifts-in-kind with $87,394.50 in reported
value. These rows are source-backed ACT state disclosure records. Gift-in-kind
rows are reported non-cash values and are not cash payments. The ACT disclosure
trigger is cumulative: a party grouping or non-party candidate grouping must
report a gift, or cumulative gifts from a single donor, totalling $1,000 or more
during the relevant period. Individual rows may therefore be below $1,000. The
normalizer and manifest loader preserve and verify source metadata, source body,
summary, and JSONL SHA-256 hashes before loading.

The NT adapter archives the official NTEC 2024-2025 annual return page and the
separate annual return gifts page. It normalizes 96 annual-return financial rows
into `data/processed/nt_ntec_annual_return_money_flows/`: 49 recipient-side
receipts over $1,500, 2 associated-entity debt rows over $1,500, and 45
donor-side donation-return rows, with $821,044.16 in source-row reported value.
It also normalizes 78 recipient-side annual gift rows into
`data/processed/nt_ntec_annual_gift_money_flows/`, with $1,066,817.76 in
reported annual gift value. The annual gift source table does not publish
per-row gift transaction dates, so the records store the return received date as
`date_reported` where available and carry an explicit date caveat. Both NT
normalizers check parsed row sums against source-published table totals. NT rows
are marked `jurisdictional_cross_disclosure_observation`: state/local record
views show the annual-return source-row values, state/local gift-family
summaries show annual gift-return values, and consolidated influence totals
exclude them until cross-source deduplication against NTEC gift tables,
donor-side returns, and Commonwealth records is implemented. Raw artifacts
preserve public address text from the official page; the generic state/local
records API does not echo address-bearing `original_text` by default. The loader
verifies manifest summary hashes, JSONL hashes, source metadata hashes, source
body hashes, source ID, source dataset, non-zero counts, and row counts before
inserting rows.

The SA adapter archives the official ECSA disclosure-return landing page and
the current return-record portal, then normalizes the portal index into
`data/processed/sa_ecsa_return_summary_money_flows/`. Current normalized
coverage from the 2026-04-29 implementation run is 696 return-level rows with
$472,688,444.90 in source-row return-summary value. The fetcher first reads the
portal's official `For` filter values and pages each partition separately
(`filter_for_partitioned_pages`) because unfiltered portal pagination can repeat
rows and miss other rows. Replay validates the portal-reported row count,
complete partition coverage, source metadata hashes, summary hashes, JSONL
hashes, source ID, source dataset, non-zero counts, and row counts before
loading. SA return-summary rows are visible in state/local source-family views
as return summaries, but their amounts are not added to consolidated influence
totals until detailed SA transaction parsing and cross-source deduplication are
implemented.

The VEC funding-register adapter archives the official VEC funding-register
page and the linked DOCX files, then normalizes public funding, administrative
expenditure funding, and policy development funding rows. Current normalized
coverage from the 2026-04-29 run is 202 rows with $45,447,717.13 in reported
public-funding/admin/policy amounts. These are not private donations, gifts, or
personal income. Some dates are election-day or calendar-period context dates,
not transaction dates, and the normalized rows carry `date_caveat` values. On
the implementation run the VEC public-donation portal redirected to the VEC
maintenance page, so private-donation parsing for Victoria remains pending.

Donors are ECQ-identifier-backed only when they also appear in an accepted ECQ
participant lookup record.

The context normalizer uses archived ECQ political-event and local-electorate
lookup APIs to annotate disclosure rows with exact unique event/local-electorate
name matches. These are source-backed context labels, not personal attribution:
the ECQ event date is the election event date rather than a transaction date,
and a local-electorate name is not sufficient evidence that a specific candidate,
councillor, or MP received money.

The targeted serving-database loader refreshes just the QLD ECQ EDS
`money_flow` rows, applies the latest participant identifier artifact when
present, and then rebuilds the unified `influence_event` surface. The general
database loader also includes the latest processed QLD ECQ EDS money-flow and
participant artifacts when money-flow loading is enabled:

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
entities, AEC annual money-flow rows, AEC candidate-contest context rows, and
Senate interest records so it can be rerun after each scheduled pipeline run.
Candidate-contest links are source-backed campaign context; exact
candidate/electorate/state matches remain `name_context_only` until a dated
office-term link validates the timing. The database is therefore a
serving/indexing layer over reproducible artifacts rather than the only copy of
the evidence.

Money-flow and register-interest rows are loaded as current source snapshots.
When a later processed artifact no longer contains a previously loaded
`money_flow` or `gift_interest` row from the same source family, the row is
retained with `is_current = false` and withdrawal metadata instead of being
silently destroyed. The derived public `influence_event` surface is rebuilt
only from current base rows; withdrawn derived events are deleted when possible
or marked rejected if another claim-evidence table still references them. This
preserves auditability and manual-review history while preventing corrected or
withdrawn source records from staying in public totals.

House PDF text extraction is also bound to the latest APH House interests
discovered-link manifest. Cached PDF snapshots whose source IDs are absent from
the current APH index are ignored by the text-extraction stage, so they cannot
be re-parsed and reloaded as current House register rows after APH withdraws or
renames a PDF.

Official APH parliamentary decision-record indexes, linked decision-record
documents, official `vote_division` rows, and official `person_vote` rows use
the same snapshot discipline. Each refreshed source/chamber first marks prior
official rows as `is_current = false` with withdrawal metadata, then reactivates
the rows present in the latest parsed artifact. Public vote summaries, coverage
counts, and serving-database quality checks filter to current official vote
rows, while withdrawn/corrected rows remain available for audit.

When `--apply-schema` is used, the loader applies the baseline schema and then
all additive migrations. Routine weekly runs should use `migrate-postgres`
followed by `load-postgres` so the serving database is updated from the newest
reproducible artifacts. `--include-vote-divisions` should be added only when a
They Vote For You API key is configured.

Federal-only scheduled loads use `load-postgres --skip-qld-ecq
--skip-nsw-aggregates --skip-act-gift-returns
--skip-nt-ntec-annual-returns --skip-nt-ntec-annual-gifts
--skip-sa-ecsa-return-summaries --skip-vic-vec-funding-register` unless the
relevant state/local fetch/normalize steps also ran. QLD, ACT, NT, SA, and VIC
state/local public summaries filter to current `money_flow` rows, and NSW
aggregate summaries filter to current `aggregate_context_observation` rows, but
the schedule should still avoid refreshing a state/local source family from
stale processed artifacts.

Routine update jobs should run the serving-database QA gate after loading:

```bash
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/python -m au_politics_money.cli qa-serving-database
```

The QA gate fails if the current federal House boundary count is not 150, any
current House office term lacks a loaded boundary, a non-rejected public
influence event points to a non-current base row, known House form/OCR
boilerplate appears as an active influence event, an official APH division has a
parsed vote-count mismatch, or official APH vote rows cannot be matched to the
current roster beyond the configured tolerance. The current default tolerance is
25 unmatched official APH roster-vote rows, so small known parser/roster name
edge cases are monitored without blocking every refresh.

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
    "valued at", "worth", or a parseable date. A second conservative pattern
    captures subject-provider wording such as "Example Foundation provided..."
    or "Commonwealth Bank hosted..." when the source text names the provider
    before the verb. That subject-provider pattern is treated as a review-gated
    heuristic in Senate API rows, and passive fragments such as "tickets were
    provided" or "I was gifted" are rejected as provider names. Date parsing
    includes numeric dates, day-month dates, day-range starts, and month-first
    dates. A narrow branded-benefit pass also identifies source providers for
    recurring named benefits such as Qantas Chairman's Lounge, Virgin
    lounge/club access, airline upgrades, and Foxtel subscriptions.
    Non-disclosed providers, values, or dates remain labelled as missing rather
    than inferred.
18. Optional, when `THEY_VOTE_FOR_YOU_API_KEY` or `TVFY_API_KEY` is available:
    fetch They Vote For
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
- Use `run-federal-foundation-pipeline --refresh-existing-sources` for scheduled
  federal updates so cached but update-sensitive sources are fetched again and
  checksum changes are captured.
- Use `run-federal-foundation-pipeline --include-official-identifier-bulk` on
  scheduled identifier-refresh runs when ASIC, ACNC, or ABN Bulk register
  snapshots should be refreshed. These large data.gov files are archived as raw
  source snapshots and normalized into one official-identifier JSONL per source;
  ABN multi-part resources are grouped so a current-source load does not drop
  older parts of the same bulk extract.
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
- For official APH decision records, scheduled federal runs refetch current
  representation URLs through `--refresh-existing-sources`; smoke/development
  runs may use cache-friendly `only_missing` behavior. The database links
  source-document snapshots by checksum so changed public bodies are added as
  new evidence rather than overwriting prior raw evidence.
- Backend dependency versions used by CI and new weekly-runner virtual
  environments are constrained by `backend/requirements.lock`. Treat updates to
  that file as intentional reproducibility changes.
