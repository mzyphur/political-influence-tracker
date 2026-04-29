# Build Log

## 2026-04-29

Completed:

- Added a reproducible AEC Electorate Finder postcode crosswalk pipeline:
  archived AEC postcode search pages, normalized source-backed postcode to
  electorate-candidate rows with ambiguity/confidence/locality metadata, added
  `postcode_electorate_crosswalk`, and connected `/api/search` to return loaded
  postcode candidates rather than guessing a single electorate. Review
  hardening added AEC division ids, next-election boundary context, deterministic
  seed hashes, stale-row replacement on reload, and removal of local filesystem
  paths from public API metadata.
- Added `postcode_electorate_crosswalk_unresolved` so AEC postcode candidates
  that cannot yet be resolved to the loaded House boundary table remain
  auditable and surface as explicit search limitations rather than disappearing.
  The frontend now renders search limitations and marks postcode map-opening as
  pending until the target feature is actually loaded.
- Compact laptop map layout pass: narrowed the left controls and right details
  overlays, reduced panel spacing, made both overlays independently scrollable,
  and collapsed the long coverage caveat behind a disclosure control so map
  geography remains visible on smaller screens.
- Added collapsible map controls and selection-details panels. Collapsed panels
  leave compact "Controls" and "Details" reopen buttons; focus is explicitly
  restored between collapse/reopen controls for keyboard users, and the map
  zoom controls plus influence graph reclaim right-side space when details are
  collapsed.
- Improved party search semantics. Public searches such as "Labor", "Liberal",
  and "Greens" now map to active parliamentary party abbreviations like `ALP`,
  `LP`/`LNP`, and `AG`, sort active parliamentary parties above zero-seat
  disclosure-name rows, and display public-friendly labels such as
  "Australian Labor Party (ALP)".
- Made party breakdowns actionable from selected map regions. Clicking a party
  in the selection details opens that party/entity money profile directly,
  helping users move from representative-level context to aggregate
  party-channelled money without manual search.
- Addressed first follow-up review items: frontend search now includes
  postcode as an available type, AEC public-funding normalization fails loudly
  if the page yields zero rows or unparseable non-empty amount cells, and
  specific party aliases such as "liberal national" no longer broaden to all
  Liberal-family parties.
- Reduced duplicate representative-money counts by turning the second money
  panel into a campaign/party-channelled support expander only, and visually
  separated party/entity review candidates from reviewed links in the party
  profile panel.
- Added `docs/influence_network_model.md`, which defines direct, campaign,
  party/entity, and modelled allocation evidence tiers for indirect network
  paths such as `Commonwealth Bank -> ALP entity/branch -> ALP MPs/Senators`.
- Added the first representative-level indirect graph implementation. Person
  influence graphs now include current party context, reviewed party/entity
  links, source-backed money into reviewed party entities, and a separately
  labelled `modelled_party_money_exposure` edge using
  `equal_current_representative_share` only as modelled exposure, not personal
  receipt.
- Hardened indirect graph totals after review: modelled party exposure now uses
  an unbounded distinct-event aggregate across all reviewed party/entity links,
  not the graph display limit, and duplicate reviewed link types for the same
  party entity do not double-count the same money event.
- Improved granular benefit extraction for individual gifts, hospitality,
  tickets, memberships, and travel. The House/Senate interests parsers now
  catch provider phrases such as "at invitation of", values expressed as
  "worth $X" or "estimated at $X", branded providers for Qantas/Virgin airline
  lounge memberships and similar named benefits, and richer subtypes for
  private jets/flights and sporting or cultural tickets.
- Added a further benefit-extraction hardening pass for source text that names
  the provider before the verb, such as "Commonwealth Bank hosted..." or
  "Example Foundation provided..."; date parsing now handles day-range starts
  and month-first dates. A follow-up review gate rejects passive fragments such
  as "tickets were provided" as provider names and marks Senate subject-provider
  captures as heuristic review items. Regenerated the House/Senate interest
  artifacts and narrowly refreshed local `gift_interest` plus `influence_event`
  records without rebuilding map geometry.
- Hardened House PDF interest parsing against form/OCR artifacts such as
  "HOUSE OF REPRESENTATIVES", "PARLIAMENT OF AUSTRALIA", signature/date rows,
  and replacement-character OCR fragments. The local active serving surface now
  has 5,838 current House interest rows and 1,406 non-rejected benefit events;
  the obvious form artifacts are retained only as non-current base evidence.
- Added source-snapshot current flags for `money_flow` and `gift_interest`.
  Reloads now mark rows absent from the latest source-family artifact as
  `is_current = false`, rebuild the public `influence_event` surface from
  current rows only, and suppress retained claim-linked withdrawn events as
  rejected rather than keeping them in public totals.
- Made the weekly federal runner key-aware for They Vote For You. Scheduled
  runs now skip optional TVFY fetch/load steps when neither
  `THEY_VOTE_FOR_YOU_API_KEY` nor `TVFY_API_KEY` is configured, instead of
  aborting the whole federal refresh.
- Added `qa-serving-database` and wired it into the weekly runner after the
  database load. The QA gate checks federal House boundary coverage, public
  events pointing at non-current base rows, known House form/OCR boilerplate,
  official APH vote-count mismatches, and unmatched official APH roster votes
  above a configurable tolerance.
- Improved the representative panel's public evidence surface. The left map
  metrics now use a 2-by-2 grid so labels such as "Electorates" do not collide,
  and representative profiles now expose compact sector, vote-topic, and
  reviewed source-policy overlap signals with an explicit non-causation caveat.
- Added scheduled-source refresh hardening. `run-federal-foundation-pipeline`
  now supports `--refresh-existing-sources`, the weekly runner enables it, and
  cached AEC postcode, AEC boundary, and official APH decision-record document
  sources are refetched on scheduled runs rather than silently reused.
- Added backend dependency constraints with `backend/requirements.lock` and
  made CI/new weekly virtualenv installs use it as the reproducible install
  baseline.
- Hardened QLD state/local public summaries so they only read current
  `money_flow` rows, and made the federal weekly load use `--skip-qld-ecq` so
  stale QLD processed artifacts are not promoted unless the QLD refresh steps
  ran.
- Bound House PDF text extraction to the latest APH House interests
  discovered-link manifest. Cached PDFs absent from the current APH index are
  ignored during extraction, allowing prior House register rows to remain
  non-current instead of being republished.
- Added current/withdrawn semantics for official APH parliamentary decision
  indexes, linked decision-record documents, official `vote_division` rows, and
  `person_vote` rows. Refresh loads now mark prior official rows for the
  refreshed source/chamber as non-current before reactivating rows present in
  the latest artifact, and public vote summaries, coverage counts, and QA checks
  read only current official vote rows.
- Hardened the APH current-row implementation after review: linked decision
  documents are also withdrawn when their parent index row is withdrawn, document
  reloads require a current parent record, official division reloads require a
  current linked decision-document snapshot, and reactivated rows clear stale
  withdrawal metadata before becoming current again.
- Softened public network language in the app from "influence graph" toward
  "evidence network", renamed "Non-rejected records" to "Published records",
  added visible non-causation caveats, and expanded the methodology page with
  a plain-English "what this can show / cannot prove / how to read arrows"
  summary.
- Added `docs/theory_of_influence.md` as the standing theory/methodology layer
  connecting engineering decisions to mechanisms of influence, democratic
  transparency, operating hypotheses, allowed claims, non-claims, and the
  documentation rule for future data families and UI surfaces.
- Added `frontend/public/methodology.html` and an app-header "Method" link so
  the public web app can host a companion methodology page with diagrams of the
  operating theory, evidence tiers, network paths, and claim discipline.
- Added `display_land_masks` to `/api/coverage` and the frontend coverage panel
  so public users can see which display-only land-mask source is backing clipped
  interactive map geometry.
- Added `docs/state_council_expansion_plan.md`, grounded in current official
  state/territory disclosure pages, to define the first subnational source
  surfaces, sequencing, theory rationale, and claim limits before implementation.
- Added state/territory seed source records to the backend source registry for
  NSW, Victoria, Queensland, South Australia, Western Australia, Tasmania,
  Northern Territory, and the ACT so subnational fetching can start from named
  reproducible source IDs rather than prose-only targets.
- Added `scripts/fetch_state_council_seed_sources.sh` as a reproducible
  acquisition smoke script for those official subnational source records. The
  script archives raw source bodies and metadata under `data/raw/` and logs
  command output under `data/audit/logs/`.
- Ran the subnational source smoke fetch once successfully at
  `20260429T002623Z`. Metadata was archived for NSW, Victoria, Queensland, South
  Australia, Western Australia, Tasmania, Northern Territory, and the ACT under
  ignored `data/raw/<source_id>/<timestamp>/metadata.json` directories; stderr
  logs were empty.
- Extended reproducible link discovery to the first subnational targets. Running
  `discover-links` on the archived seed pages produced parser-target inventories
  for NSW (23 official disclosure/register links), Victoria (26 VEC disclosure,
  funding, annual-return, and portal links), and Queensland (22 ECQ state/local
  disclosure, EDS, register, and participant links). The generated manifests are
  under ignored `data/processed/discovered_links/<source_id>/20260429T003319Z.json`.
- Added the first active state/local disclosure adapter for Queensland ECQ EDS.
  The source registry now includes the EDS public map, expenditure, report, CSV
  export, and public lookup API surfaces discovered from official ECQ pages.
  `fetch-qld-ecq-eds-exports` archives current gift and expenditure CSV exports
  by POSTing source-backed form fields from the archived ECQ pages, and
  `normalize-qld-ecq-eds-money-flows` converts those exports into normalized
  state/local influence-event input records.
- Loaded the current Queensland ECQ EDS exports into the local PostgreSQL
  database. The normalized artifact contains 49,839 source-backed rows:
  22,726 gift/donation rows from the public map export and 27,113 electoral
  expenditure rows from the expenditure export. Expenditure rows are loaded as
  `campaign_support` / `state_local_electoral_expenditure`, not as personal
  receipt by a representative.
- Updated `/api/coverage` and the frontend coverage panel so State and Council
  now show partial active coverage when QLD ECQ EDS rows are loaded. The map
  remains federal-only for now and tells users that state/local map drilldown is
  still being built rather than implying there are no state/local records.
- Added `load-qld-ecq-eds-money-flows` as a targeted incremental DB refresh
  command for the new QLD source family. It avoids re-upserting every federal
  money-flow artifact while still rebuilding the derived `influence_event`
  surface by default.
- Added QLD ECQ participant identifier enrichment from the archived lookup APIs
  for political electors/candidates, political parties, associated entities,
  and local groups. The first local enrichment pass normalized 6,360 lookup
  records and, after review hardening, auto-accepted 48 exact unique
  party/associated-entity/local-group matches against existing QLD money-flow
  entities. A further 1,618 candidate/elector name-only matches are retained for
  manual review rather than published as ECQ-ID-backed identities.
- Added `GET /api/state-local/summary` and the first State/Council frontend
  summary panel. State and Council modes now show QLD ECQ disclosure totals,
  gift/donation rows, electoral-expenditure rows, ECQ-ID coverage, top gift
  donors/recipients, and top campaign-spend actors while maps and
  representative joins for those levels are still being built.
- Tightened the state/local summary after review: top-actor rankings no longer
  duplicate rows when an entity carries multiple ECQ identifiers, and the
  frontend labels identifier coverage as row-side coverage rather than distinct
  ID counts.
- Tightened QLD ECQ participant enrichment after review: candidate/elector
  name-only matches now remain `needs_review` unless future event,
  electorate, or role context supports the identity, while exact unique
  party/associated-entity/local-group matches can still be auto-accepted.
- Added QLD ECQ political-event and local-electorate context normalization from
  archived lookup APIs. QLD money-flow rows now carry exact unique
  event/local-electorate context matches where available, `/api/state-local/summary`
  exposes top events/local electorates, and the frontend splits gift/donation
  totals from electoral campaign-spend totals so users do not read campaign
  expenditure as personal receipt.
- Made QLD State/Council summary actor rows actionable. Rows with a resolved
  disclosure entity now open the existing entity profile and influence graph
  surfaces from State or Council mode, while source-only free-text rows remain
  displayed as unresolved source names.
- Increased the representative-profile evidence payloads exposed by the API.
  The UI remains compact by default, but selected representatives can now reveal
  more direct person-linked records and more campaign/party-channelled support
  rows without implying that campaign-support rows are personal receipts.
- Added cursor-paginated representative evidence pages at
  `/api/representatives/{person_id}/evidence`. Direct records and
  campaign-support records are separate API groups, pagination uses the same
  date/id ordering as the profile feed, and the frontend now loads further rows
  on demand without collapsing campaign support into personal receipt.
- Added concrete QLD State/Council recent-record rows to
  `/api/state-local/summary` and the summary panel. Users can now inspect
  source/recipient names, reported amounts, ECQ event/local-electorate context,
  row references, and source links even before state/local map drilldown exists.
- Added `prepare-review-bundle`, a reproducible CLI wrapper that materializes
  party/entity link candidates, exports party/entity and sector-policy review
  queues, runs sector-policy suggestions, and writes a manifest for reviewers
  without turning candidates into public claims.

Verification:

- Frontend production build passed after each UI change.
- Focused API and AEC public-funding tests passed:
  `backend/tests/test_api.py` and `backend/tests/test_aec_public_funding.py`.
- Focused `ruff check` passed for the party-search and public-funding parser
  changes.
- Postgres integration tests passed for the indirect graph path, including
  direct totals excluding campaign/modelled values, low graph limits not
  changing modelled totals, duplicate reviewed party/entity link types not
  double-counting money, and modelled edges carrying caveats/metadata instead
  of `reported_amount_total`.
- Frontend graph build passed after adding explicit modelled-exposure labels,
  de-emphasized context-edge weighting, and keyboard-focusable graph edges.
- Focused House/Senate interests and influence-event classifier tests passed
  for branded lounge access, private-jet travel, sporting tickets, provider
  extraction, and value extraction.
- Live local API smoke checks confirmed `labor` and `liberal` search results now
  prioritize active parliamentary party records.
- Focused source-registry/discovery tests passed after adding NSW/Victoria/Queensland
  subnational link-retention coverage.
- Focused QLD ECQ EDS parser and source-registry tests passed, along with the
  existing DB loader tests. A local DB reload confirmed the new QLD rows extend
  the unified `influence_event` surface while preserving the direct-money versus
  campaign-support separation.
- Postgres integration coverage now asserts that QLD ECQ EDS rows surface as
  `partial_levels` for state and council while `active_levels` remains federal.
- Focused QLD participant, API, DB-loader, and frontend production-build checks
  passed. A live local DB query confirmed QLD state totals of 34,002 rows and
  QLD local/council totals of 15,837 rows through the new state/local summary
  API.

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
- Added AEC election-disclosure ingestion for seven detail tables: donor
  donations made/received, Senate group/candidate donations and discretionary
  benefits, third-party donations made/received, and media advertisement
  details. The normalizer emits disclosure observations, preserves original
  rows, excludes aggregate-only return summary tables, and annotates canonical
  transaction keys so cross-table duplicate observations are retained as
  evidence without inflating reported-total sums.
- Added display-safe map geometry. Official AEC boundary polygons remain
  preserved in `electorate_boundary.geom`; the API now defaults to
  `geometry_role=display`, backed by `land_clipped_display` geometry derived
  from AIMS/eAtlas/AODN Australian Coastline 50K land-area polygons. Source
  geometry remains requestable for audit via `geometry_role=source`.
- Added the `campaign_support` influence-event family for source-backed
  campaign support and party-channelled support. The AEC election normalizer now
  covers candidate/Senate group expenses, candidate/Senate group return
  summaries, and third-party campaign expenditure, while preserving direct money
  and benefit records as separate families. The frontend exposes this as “Money
  Connected To This Representative,” with campaign support labelled separately
  from direct disclosed money/gifts/interests.
- Added migration coverage and integration tests to keep campaign support out of
  direct-money totals, source-effect context amount totals, person/entity graph
  direct-disclosure edges, and entity direct-money summaries. Campaign-support
  amounts remain visible in campaign-support-specific fields and panels.
- Added reproducible AEC public-funding ingestion for the finalised 2025 federal
  election funding page. The pipeline fetches the official AEC HTML page,
  normalises party and independent-candidate payment tables, and loads them as
  `campaign_support` / `election_public_funding_paid` rows rather than donations
  or personal receipts.

Notable data observations:

- APH current contact CSV returned 149 House members and 76 Senators, while the official House interests register included Sussan Ley for Farrer. The loader now creates `Sussan Ley (Farrer)` from the House register with metadata source `derived_from_house_interest_register` so records are not dropped; this should be monitored in future APH CSV refreshes.
- AEC annual disclosure ZIP contains 13 CSV tables and is small enough for routine weekly ingestion.
- The annual money-flow normalizer covers Detailed Receipts, Donations Made,
  Donor Donations Received, and Third Party Donations Received. It does not yet
  normalize annual debts, discretionary benefits, capital contributions, or
  return summary tables.
- An earlier AEC election normalizer pass produced 19,994 detail observations from the
  current election bulk ZIP. It identified 17,972 canonical transaction keys,
  965 duplicate transaction groups, and 971 duplicate observations. Duplicate
  observations and campaign-expenditure rows remain available as records but
  use `amount_status=not_applicable` in the unified event layer so donation-like
  reported totals are not overstated.
- The expanded AEC election normalizer version 2 produced 52,581 observations
  from the current election bulk ZIP: 34,308 candidate/Senate group campaign
  support flows, 15,119 media-advertising rows, 204 third-party campaign
  expenditure rows, and the original donor/candidate/third-party donation and
  benefit detail rows. Candidate/electorate/state context is attached only when
  the candidate-context key is unambiguous; nine ambiguous context keys are
  withheld for review rather than linked.
- The AEC 2025 public-funding normalizer produced 86 rows: 26 party aggregate
  payments and 60 independent-candidate payments. Loaded public funding totals
  match the AEC finalised total of $93,850,428.95 and remain separated from
  direct disclosed money/gift totals.
- House interests text extraction needed OCR fallback for scanned/low-text pages, including `Gosling_48P.pdf` and `Katter_48P.pdf`; OCR artifacts are handled in the metadata extractor and record filters.
- The Senate register currently exposes structured JSON through a public API used by the official APH React app; this is preferable to PDF scraping for current Senate interests, but the API should be monitored for schema changes.
- `public_interest_sector_rules_v1` is useful for exploratory filtering but remains inferred. Any public claim about an entity's sector should retain the classifier/method/confidence caveat until ABN/ASIC/ANZSIC or manual-review evidence is added.
- Most benefit events do not disclose a value or a parsed provider. The new `missing_data_flags` field makes those limitations queryable instead of hiding them.
- The AEC national boundary file does not include a state/territory column, so state remains sourced from the APH roster/electorate table rather than the shapefile.
- AEC source boundary polygons include legitimate offshore/maritime extents
  that are unsuitable as filled web-map polygons. Display geometry is now a
  derived land-clipped layer; never overwrite the official source geometry with
  display geometry.
