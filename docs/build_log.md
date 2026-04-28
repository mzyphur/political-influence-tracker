# Build Log

## 2026-04-28

Completed:

- Added APH linked decision-record document archival. The pipeline now fetches
  ParlInfo HTML/PDF representations referenced by the current official House
  Votes and Proceedings and Senate Journals indexes, preserving raw bodies,
  checksums, request headers, and APH index provenance in processed summaries
  and database link rows.
- Added the first federal data-coverage audit focused on why representative
  pages were sparse, with a prioritized plan for direct MP/Senator money,
  party/entity money surfaces, benefit extraction, lobbying/access evidence,
  official House votes, and sector-policy review.
- Added conservative AEC direct-representative money linking. Direct
  representative annual return rows now strip titles/postnominals and link only
  unique exact cleaned-name matches to `person`; unmatched or ambiguous rows are
  preserved with audit metadata instead of guessed. The current local reload
  linked 50 of 57 `Member of HOR Return` rows, totaling AUD 1,383,511, to MP
  profiles.
- Hardened public influence surfaces so rejected `influence_event` rows are
  excluded from sector/context views, entity search counts, and electorate
  profile summaries.
- Hardened roster refreshes so prior APH current-office terms absent from a new
  APH roster snapshot can be closed with audit metadata, avoiding stale
  `term_end IS NULL` public representatives.
- Extended the weekly runner so scheduled runs now execute the pipeline, apply
  migrations, reload PostgreSQL with vote divisions, and then run tests.
- Added `/api/entities/{entity_id}` and the first frontend entity drilldown for
  search results. Source/recipient entity profiles show sector classifications,
  identifiers, source/recipient summaries, top counterparties, recent
  source-backed events, and caveats that party/entity-level records are not
  person-level claims.
- Added `official_parliamentary_decision_record_document` plus a loader that
  links each archived raw ParlInfo snapshot back to its APH index row without
  overwriting original raw evidence.
- Added `fetch-aph-decision-record-documents` with `--only-missing`, HTML/PDF
  filters, and a smoke `--limit` option. The weekly federal pipeline now runs
  this after APH index extraction; smoke runs fetch only 10 representations.
- Hardened the generic fetcher for ParlInfo by using a source-specific
  browser-compatible user agent that still includes the project name/contact,
  and by storing request headers in raw fetch metadata.
- Hardened the APH document layer after reviewer feedback: routine scheduled
  runs now use `--only-missing`, existing raw metadata is not rewritten when
  linking current index rows to existing source snapshots, linked HTML/PDF
  bodies are signature/content-type validated before DB loading, missing parent
  decision records no longer create orphan source-document rows, and pipeline
  manifests now include dependency package versions.

Verification:

- Focused tests: 21 passed for APH decision-record parsing/fetching and DB
  loading.
- Focused `ruff check`: passed.
- Live ParlInfo smoke fetch: 5 of 5 representations fetched after header
  hardening; the previous 403 failure summary is preserved as failed raw fetch
  evidence.
- Full initial ParlInfo fetch: 91 selected, 86 newly fetched, 5 skipped as
  already present, 0 failed; 72 HTML and 19 PDF representations.
- Regenerated non-mutating incremental summary: 91 selected, 0 newly fetched,
  91 skipped as already present, 0 failed; 72 HTML signatures and 19 PDF
  signatures validated.
- Migration `013_official_parliamentary_decision_record_documents.sql` applied.
- PostgreSQL load linked 91 official decision-record document snapshots to all
  72 current APH decision-record index rows.
- Added `aph_official_divisions_v1`, which parses current Senate Journals PDF
  division blocks from archived APH source snapshots, including AYES/NOES
  counts, senator names, teller markers, raw block evidence, and count-mismatch
  validation.
- Parsed and loaded 335 official APH Senate divisions across 19 sitting dates
  from 2026-01-19 to 2026-04-01, with 18,715 senator-vote rows, zero
  count-mismatch divisions, and zero unmatched current-senator votes.

## 2026-04-27

Initial federal backend foundation created.

Completed:

- Created project scaffold under `/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics`.
- Added research plan, data-source inventory, research standards, entity-resolution notes, and frontend direction.
- Added Python backend package and source registry.
- Added raw source fetcher with metadata, checksums, content type, and source IDs.
- Added link discovery for AEC download pages, APH contact CSVs, APH House interests PDFs, and AEC GIS ZIPs.
- Downloaded APH current member/senator CSVs.
- Built current APH roster JSON: 149 House members and 76 Senators.
- Downloaded House Register of Members' Interests index and 152 PDFs/reference PDFs.
- Extracted text from 152 House interests PDFs/reference PDFs with PDF text plus Tesseract OCR fallback: 2,170 pages, 11 OCR pages, zero extraction failures.
- Downloaded AEC annual disclosure ZIP.
- Summarized 13 AEC annual CSV table schemas.
- Normalized 192,201 AEC annual money-flow rows into JSONL.
- Split House interests PDFs into 2,852 numbered section records across 150 member documents; 2 reference documents were skipped.
- Added House interest structured-record extraction from numbered sections, including owner context, category mapping, conservative counterparty guessing, duplicate-key suppression, and filters for explanatory notes/form prompts.
- Added PostgreSQL/PostGIS schema draft.
- Added local Docker Compose database scaffold.
- Added reproducible `run-federal-foundation-pipeline` command.
- Added pipeline run manifests under `data/audit/pipeline_runs`.
- Added weekly pipeline shell script and CI smoke workflow.
- Added idempotent PostgreSQL loader for the latest processed roster and AEC annual money-flow artifacts.
- Moved discovered-source ID generation into shared ingestion code so CLI and scheduled pipelines use the same stable source IDs.
- Added reproducible Senate interests API ingestion through the official APH page's `env.js` API configuration.
- Added Senate interest record flattening for gifts, travel/hospitality, liabilities, assets, income, directorships, and alterations.
- Extended the PostgreSQL loader to insert Senate and House interest records into `gift_interest` after matching MPs/Senators to the reproducible APH roster.
- Added a provenance-marked House-register fallback person path for cases where the APH contact CSV omits a valid House member present in the official House interests register.
- Added reproducible rule-based entity and public-interest-sector classification artifact generation (`public_interest_sector_rules_v1`).
- Extended the PostgreSQL loader to replace/load generated entity-sector classifications and update entity types without creating duplicate entities on future reloads.
- Installed Docker Desktop 4.71.0 as `/Applications/Docker.app` and linked Docker CLI tools for the current shell environment.
- Started the local PostGIS stack with Docker Compose and loaded the current reproducible artifacts into PostgreSQL.

Verification:

- `pytest`: 33 passed.
- `ruff check .`: passed.
- Federal smoke pipeline: succeeded (`federal_foundation_20260427T111450Z.json`).
- Senate smoke API fetch: 5 of 76 available senator statements fetched; 104 flattened interest records produced.
- Full Senate API refresh: 76 of 76 available senator statements fetched; 1,752 flattened interest records produced.
- Full House PDF text extraction: 152 PDFs/reference PDFs, 2,170 pages, 11 OCR pages, 0 failed documents.
- Full House section extraction: 2,852 numbered sections from 150 member documents; 277 gift sections.
- Full House structured extraction: 5,853 unique House interest records after excluding explanatory notes, form prompts, and duplicate keys.
- Docker/PostGIS load succeeded: 226 people, 226 office terms, 192,201 AEC money-flow rows, 5,853 House interest records, 1,752 Senate interest records, 7,605 total `gift_interest` rows.
- Full entity classification artifact: 35,874 normalized entity names, 23,648 non-unknown sector classifications, 12,226 unknown/uncoded names.
- Entity classification database load: 35,874 generated `entity_industry_classification` rows; repeat load verified as idempotent at 35,874 rows.
- Added official identifier enrichment scaffolding for ASIC, ABN Bulk Extract, ACNC, ABS ANZSIC sections, and the Australian Government Register of Lobbyists.
- Snapshotted the current federal lobbyist register via the public official API: 378 lobbying organisations, 2,498 client rows, and 726 lobbyist-person rows flattened into 3,602 official identifier records.
- Loaded 3,590 unique official lobbyist-register observations into PostgreSQL and created 392 exact-name match candidates for manual review. The loader now refuses to attach identifiers from name-only matches.
- Hardened official enrichment based on Codex/Claude review: tab-delimited ASIC parsing, source-discovery fail-closed behavior, stable official-ID observation keys, public lobbyist-person record preservation, a migration ledger, safer Docker loopback binding, and HTTP failure fail-closed fetch behavior.
- Local data.gov.au CKAN/source download access returned HTTP 403 for ASIC, ACNC, and ABN Bulk Extract discovery on 2026-04-27. The failure artifact is preserved under `data/processed/official_identifier_sources/`, and the command now fails instead of silently proceeding.
- Added unified `influence_event` schema and loader so AEC money flows and APH interests/gifts become comparable event records with source links, evidence status, review status, amount status, and missing-data flags.
- Materialized 199,806 local influence events: 192,201 money events, 1,390 benefit events, 4,700 private-interest events, 1,413 organisational-role events, and 102 other declared interests.
- Benefit-event taxonomy now separates flights/upgrades, event tickets/passes, meals/receptions, accommodation, membership/lounge access, subscriptions/services, generic gifts, and sponsored travel/hospitality. Ordinary organisational memberships are kept as organisational-role events unless the text indicates benefit-style lounge/access treatment.
- Added `manual_review_decision` schema and reproducible review-queue exports for `official-match-candidates`, `benefit-events`, and `entity-classifications`.
- Generated current review queues under `data/audit/review_queues/`: 392 official identifier match candidates, 1,390 benefit events, and 27,059 inferred entity classifications recommended for review.
- Added reviewed-decision importer with dry-run default, input checksums, deterministic decision keys, payload hashes, stable subject keys, stale-subject fingerprint checks, identifier-conflict blocking, and append-only decision storage.
- The importer applies only conservative side effects: accepted official matches attach identifiers/aliases/classifications after conflict checks; manual classification decisions create separate `method = 'manual'` rows; influence events only receive review status/metadata updates.
- Added a table-level unique constraint migration for `manual_review_decision.decision_key` so importer `ON CONFLICT` behavior is consistent on upgraded and fresh databases.
- Added queue suppression for accepted/rejected/revised decisions by stable `subject_external_key` and a `reapply-review-decisions` command to replay stored manual decisions after regenerated loader output.
- Hardened review replay after Codex reviewer checks: standalone replay is dry-run by default, `load-postgres` reapplies decisions after refresh by default, replay has per-decision savepoints for `--continue-on-error`, queue suppression is fingerprint-aware so changed evidence is re-queued, entity-based review keys/fingerprints use normalized names plus entity type rather than surrogate database IDs, ambiguous key matches fail closed, and accepted/revised classifications are conflict-checked against existing manual/official rows.
- Added reproducible AEC federal boundary ingestion: selected the current national ESRI ZIP, archived the March 2025 shapefile, transformed 150 House division geometries from GDA94/EPSG:4283 to GeoJSON/PostGIS SRID 4326, and loaded an idempotent `aec_federal_2025_current` boundary set.
- Boundary load QA: 150 valid non-empty geometries, 150 current House electorates matched after normalized-name joins, zero missing House boundaries, and four boundary-only duplicate electorate rows from an initial exact-name pass were removed.
- Added optional They Vote For You vote/division ingestion: API-key-free raw fetch metadata with public response bodies preserved, division detail normalization, person-level vote normalization, civic policy-topic linkage, database loader for `vote_division`, `person_vote`, `policy_topic`, and `division_topic`, and a schema migration allowing `third_party_civic` topic links.
- The local `.env` does not yet include `THEY_VOTE_FOR_YOU_API_KEY`, so no real vote records were fetched or loaded in this pass.
- Added vote-behaviour analytical scaffolding: explicit `sector_policy_topic_link`
  records plus views for person-topic vote summaries, person-sector influence
  summaries, and context-only influence/vote displays that require reviewed or
  otherwise explicit sector-topic links before combining the evidence streams.
- Hardened the vote/influence context scaffold after review: sector-topic links
  now require confidence and evidence notes, reviewed links require reviewer and
  timestamp fields, and the context view exposes temporal buckets plus
  uncertainty counts instead of joining lifetime influence to votes without
  timing labels.
- Added `sector_policy_topic_link` as a manual-review subject type with
  append-only decision import/replay support and a `sector-policy-links` review
  queue. A disposable database smoke test confirmed dry-run validation and apply
  mode can create a reviewed sector-topic link without modifying raw evidence.
- Hardened sector-policy review after reviewer feedback: reviewed links now
  require role-specific supporting sources for both topic scope and sector
  material interest, review keys include the reviewed fingerprint so changed
  evidence can be re-reviewed as a new decision, and APH source registration now
  separates Hansard transcript context from House Votes and Proceedings and
  Senate Journals decision records.
- Added APH official decision-record index extraction and loading for current
  House Votes and Proceedings and Senate Journals. The parser uses APH
  `aria-label` dates where available, fails closed on empty/missing-date parses,
  excludes related consolidated PDFs from sitting-day records, and merges Senate
  PDF/HTML ParlInfo alternatives into one canonical row.
- Loaded 72 `official_parliamentary_decision_record` rows locally: 53 current
  House records and 19 current Senate records, zero missing dates. These are
  `official_record_index` rows that support official cross-checking once the
  linked ParlInfo records are archived and parsed.
- Added live They Vote For You API ingestion after `THEY_VOTE_FOR_YOU_API_KEY`
  was configured. The fetcher now recursively splits date windows that hit the
  API's 100-record cap, archives all raw public JSON with API-key-free metadata,
  and still fails closed if a one-day request is capped.
- Loaded 399 TVFY civic-source divisions for 2026-01-01 through 2026-04-28:
  55 House divisions, 24 TVFY-only Senate divisions, and TVFY enrichment on 320
  official APH Senate divisions. The loader preserves official APH evidence as
  primary on conflicts and attaches TVFY details under enrichment metadata.
- Fixed TVFY person-vote normalization for API responses that provide
  `member.first_name` and `member.last_name` instead of a full name, cached
  roster matching during loads, and added cleanup for stale TVFY fallback
  identities. The corrected local load created zero new fallback people,
  attached TVFY context to 17,263 official APH senator-vote rows, retained
  8,084 TVFY-only person-vote rows, and deleted 225 stale fallback people/office
  terms from the initial failed matching pass.
- Added the first read-only FastAPI backend for frontend development:
  `/api/search`, `/api/representatives/{person_id}`,
  `/api/electorates/{electorate_id}`, and `/api/influence-context`. Search
  spans representatives, electorates, parties, source entities, sectors, and
  policy topics, while postcode queries return an explicit limitation until a
  source-backed postcode/locality crosswalk is ingested.
- Added API documentation, a local `make api-dev` target, and dependency
  wiring for FastAPI/Uvicorn.
- Added reproducible sector-policy link suggestion exports. The command
  `suggest-sector-policy-links` scans loaded policy topics, applies conservative
  transparent keyword rules, writes audit JSONL under
  `data/audit/sector_policy_link_suggestions/`, and deliberately leaves draft
  decisions as `needs_more_evidence` until a reviewer supplies independent
  sector-material-interest support. The first corrected local run reviewed 26
  policy topics and produced 18 suggestions across fossil fuels, mining,
  renewable energy, finance, healthcare, law, and technology.
- Added targeted ABN Lookup web-service enrichment. The new
  `fetch-abn-lookup-web` command uses the current document-style
  `SearchByABNv202001` and `SearchByASICv201408` methods, posts the GUID from
  the environment, redacts secrets from metadata/raw XML, writes archived XML
  under `data/raw/abn_lookup/`, and emits normal
  `official_identifier_record_v1` JSONL for loader/review use. Trading-name
  caveats and high-volume terms/rate-limit warnings are now documented.
  Official-identifier artifact selection now includes every incremental ABN
  web-service JSONL while retaining only the latest full-snapshot artifact for
  snapshot sources; repeated refreshes of the same ABN/ACN upsert one current
  database observation.
- Live ABN Lookup smoke test on 2026-04-28 for BHP Group Limited succeeded:
  one `abn_web_service_entity` record was archived, parsed, and loaded. Local
  official-identifier counts are now 3,591 observations and 393 exact-name
  candidates needing review.
- Hardened ABN Lookup web-service ingestion after reviewer feedback: ABR
  exception XML now fails closed, collision-resistant artifact names include the
  lookup slug, incremental lookup loads no longer delete the whole `abn_lookup`
  source, and historical/trading names are stored as typed metadata rather than
  normal entity aliases.
- Hardened the public API and fetch surface after external review: response
  headers are whitelisted before metadata persistence, FastAPI has an explicit
  CORS allow-list plus process-local rate limit, free-text search defaults to a
  three-character minimum, public-search trgm indexes were added in migration
  `014_search_api_indexes.sql`, weekly federal runs include vote ingestion
  through the local `.env`, sector-policy lexical rules were tightened, TVFY
  provisional topic links receive lower confidence, incremental migrations fail
  clearly on a missing baseline schema, and source-document fetched timestamps
  no longer move backwards on out-of-order replay.
- Committed the federal backend foundation as reproducible repository state
  (`e603a94`) and added the first real PostgreSQL/PostGIS integration test.
  CI now starts a PostGIS service, applies the current baseline plus all
  incremental migrations in an isolated schema, checks migration idempotence,
  seeds a minimal
  representative/entity/influence/vote/topic graph, and exercises the actual
  FastAPI search, electorate, representative, and influence-context SQL paths.
  This test exposed and fixed migration `009` view replay behavior by dropping
  dependent views before recreating them. Local DB-backed test runs require the
  explicit `AUPOL_RUN_POSTGRES_INTEGRATION=1` opt-in.
- Added the first map-facing API slice for the future web app:
  `/api/map/electorates` returns a GeoJSON-style FeatureCollection with
  optional simplified electorate geometry, current representative and party
  properties, and non-rejected disclosed influence-event summary counts. The
  endpoint filters explicit boundary-set requests to matching boundaries, uses
  currently valid boundaries by default, avoids singular representative labels
  for multi-member electorates, and names map counts as current-representative
  lifetime context rather than electorate-level totals. The integration test now
  seeds a PostGIS boundary and verifies this endpoint through the real
  FastAPI/PostgreSQL path.
- Added the first frontend scaffold: a React/Vite/TypeScript app using
  MapLibre with a MapTiler basemap, wired to `/api/map/electorates` and
  `/api/search`. The initial interface is a real national explorer screen with
  a map, compact search/filter controls, current map totals, selectable
  electorates, and an evidence/caveat-aware side panel.
- Extended the frontend/backend map path for Senate and future jurisdiction
  levels. The UI now exposes Federal, State, and Council scopes, with
  Federal/Commonwealth active and State/Council clearly reserved for planned
  ingestion layers. The Senate map now returns state/territory features derived
  from source-backed House boundaries, while senator lists and influence
  summaries come from Senate office terms.
- Tightened map geometry QA after visual inspection showed cracks from aggressive
  per-electorate simplification. The frontend now requests low-tolerance
  geometry (`simplify_tolerance=0.0005`) and disables fill antialias seams; exact
  source geometry remains available for strict QA with `simplify_tolerance=0`.
- Added `/api/coverage` and a frontend coverage panel so sparse-looking
  representative map counts can be compared against whole-database source-family
  counts. The coverage model is written as a portable jurisdiction-adapter layer
  for later AU state/council, NZ, UK, and US builds.
- Fixed Senate/House state normalization after visual inspection exposed a
  missing NSW region. Farrer was carrying `New South Wales` while map filters and
  Senate composites expected `NSW`; map/search APIs now normalize Australian
  state names to codes.
- Added person-linked representative record detail in `/api/representatives`
  and the side panel. Selecting an MP or senator now shows family counts and
  recent source-backed records instead of only aggregate map counts.
- Brightened the frontend political palette and selected-region treatment after
  visual QA. Party short-code colors now cover the parties present in the
  current database, and the selected region uses a white halo plus bright gold
  stroke instead of the earlier muted outline.
- Added public representative contact details to the reproducible roster/API/UI
  path. Weekly runs now fetch explicit APH House and Senate contact-list PDFs,
  the roster preserves APH CSV phone/address fields, email fields are attached
  only when matched from official APH PDF text, ambiguous senator surname email
  matches are left blank, and clicking a representative opens a contact popup in
  the frontend with source/caveat text.
- Added a first evidence browser for representative-linked records. Event rows
  are filterable by family and expandable, exposing source-document names/URLs,
  source refs, evidence status, review status, amount status, and missing-data
  flags. Search now shows empty/error states and flags database results that are
  not yet implemented as map drilldowns.

Notable data observations:

- APH current contact CSV returned 149 House members and 76 Senators, while the official House interests register included Sussan Ley for Farrer. The loader now creates `Sussan Ley (Farrer)` from the House register with metadata source `derived_from_house_interest_register` so records are not dropped; this should be monitored in future APH CSV refreshes.
- AEC annual disclosure ZIP contains 13 CSV tables and is small enough for routine weekly ingestion.
- The first money-flow normalizer covers Detailed Receipts, Donations Made, Donor Donations Received, and Third Party Donations Received. It does not yet normalize debts, discretionary benefits, capital contributions, or return summary tables.
- House interests text extraction needed OCR fallback for scanned/low-text pages, including `Gosling_48P.pdf` and `Katter_48P.pdf`; OCR artifacts are handled in the metadata extractor and record filters.
- The Senate register currently exposes structured JSON through a public API used by the official APH React app; this is preferable to PDF scraping for current Senate interests, but the API should be monitored for schema changes.
- `public_interest_sector_rules_v1` is useful for exploratory filtering but remains inferred. Any public claim about an entity's sector should retain the classifier/method/confidence caveat until ABN/ASIC/ANZSIC or manual-review evidence is added.
- Most benefit events do not disclose a value or a parsed provider. The new `missing_data_flags` field makes those limitations queryable instead of hiding them.
- The AEC national boundary file does not include a state/territory column, so state remains sourced from the APH roster/electorate table rather than the shapefile.
