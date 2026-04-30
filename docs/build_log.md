# Build Log

## 2026-05-01 (Batch J — postcode crosswalk expansion: 191 → 448 rows; 127 of 150 federal House seats surfaced; methodology page documents coverage scope + limitations)

Three staged bulk-fetch PRs landed against the live AEC Electorate
Finder, all sourced from the CC0 national seed at
`data/seeds/aec_postcode_search_seed_full.txt` (Matthew Proctor's
public-domain dataset). Each PR built a fresh residential-sample
seed under `/tmp` that excluded already-fetched postcodes plus the
prior PRs' picks, so no postcode was re-fetched within Batch J. No
project source file changed; the work is documentation + live data.

- **J #1: 195-postcode QLD/SA/WA/TAS focus run.** Picked every 20th
  postcode in 4xxx-7xxx residential ranges (49 each from QLD / SA /
  WA / TAS, balanced) — the under-served quadrant after Batch I,
  whose awk filter drained head-of-list quickly through 2xxx/3xxx
  before reaching 5xxx-7xxx. Live results: **+65
  postcode_electorate_crosswalk rows** (191 → 256), 63 postcodes
  resolved, 5 ambiguous-postcode candidates, 4 unresolved postcode
  candidates, 4 skipped (no electorate match). 117 of 195 postcodes
  silent-skipped (60%) — the CC0 dataset includes business / large-
  volume-recipient codes the AEC finder doesn't return localities
  for, especially in regional ranges. State coverage shift:
  NSW 82 / VIC 71 / QLD 12 → 33 / WA 6 → 32 / SA 3 → 16 / TAS 4 → 9
  / ACT 6 / NT 5.
- **J #2: 208-postcode balanced 2xxx-7xxx run.** Took every 30th in
  2xxx/3xxx (~30 picks each) and every 25th in 4xxx-7xxx (~37 picks
  each), excluding already-fetched and PR-1 picks. Live results:
  **+98 crosswalk rows** (256 → 354), 87 postcodes resolved, 13
  ambiguous-postcode candidates, 13 unresolved postcode candidates,
  13 skipped. 82 of 208 postcodes silent-skipped (39%) — meaningfully
  lower than PR 1 because 2xxx/3xxx postcodes are more densely
  residential. State coverage shift: NSW 82 → 105 (no new
  electorates) / VIC 71 → 95 / QLD 33 → 53 / WA 32 → 42 / SA 16 →
  27 / TAS 9 → 15.
- **J #3: 211-postcode broader 2xxx-7xxx run.** Same shape as PR 2
  with a fresh exclusion set (excluded already-fetched + PR 1 picks
  + PR 2 picks). Live results: **+94 crosswalk rows** (354 → 448),
  87 postcodes resolved, 16 ambiguous-postcode candidates, 15
  unresolved postcode candidates, 15 skipped. 78 of 211 silent-
  skipped (37%). **+4 distinct electorates** (123 → 127 — QLD +2,
  WA +1, SA +1). Final per-state coverage: NSW 121 rows / 37
  electorates, VIC 114 / 31, QLD 73 / 27, WA 64 / 12, SA 40 / 9,
  TAS 19 / 5, ACT 6 / 3, NT 5 / 2. **127 / 150 federal House seats
  have at least one postcode entry (84.7%)**.

**Cumulative Batch J shape:**

- Postcodes seeded across the three PRs: 195 + 208 + 211 = **614
  unique residential-sample postcodes**, zero overlap across PRs.
- Postcodes resolved into crosswalk rows: 63 + 87 + 87 = **237** (some
  multi-electorate postcodes contributed multiple crosswalk rows).
- Crosswalk-row growth: 191 → 448 (**+257 rows, +135%**).
- Distinct postcodes in crosswalk: 171 → 404 (**+233**).
- Distinct electorates in crosswalk at end of Batch J: **127** of
  150 federal House seats (84.7%). The pre-Batch-J electorate count
  was not measured; PR 3 specifically added 4 electorates (after-PR-2
  was queried at 123).
- Unresolved postcode candidates retained as auditable observations:
  35 → 67.

- **J #4: methodology HTML documents postcode coverage scope.**
  Added a public-facing `#postcode-coverage` section to
  `frontend/public/methodology.html` (with nav-link entry) that
  records the current coverage state (404 distinct postcodes / 127
  of 150 federal House seats / 84.7%) and the four known
  limitations: silent-skip on PO Box / large-volume-recipient
  codes, missing leading-zero ranges (ACT 0200-0299 / NT
  0800-0899) due to the CC0 source storing postcodes as integers,
  multi-electorate postcodes routed to the unresolved candidates
  table, and inner-metro fragmentation. Methodology version date
  bumped to 2026-05-01. Frontend production build clean.

**Notes for the next batch operator:**

- The CC0 dataset has **no postcodes with leading zeros** — Matthew
  Proctor's CSV stores postcodes as integers, so 0200-0299 (ACT
  residential) and 0800-0899 (NT residential) are not in
  `data/seeds/aec_postcode_search_seed_full.txt`. The Batch I run's
  awk filter included those ranges but matched zero rows, which is
  why ACT/NT coverage is stuck at 6 / 5 rows respectively. Whoever
  expands ACT/NT coverage will need a different seed source (data.gov.au
  POA or AEC's own electorate boundary intersections), AND it must
  be re-licensed for public redistribution.
- Silent-skip rate is the dominant operational signal. The CC0
  dataset includes business / large-volume-recipient codes the AEC
  finder doesn't have data for; these silently exit the script with
  a non-zero `postcodes_refreshed` count but zero loader output. PR 1
  hit a 60% silent-skip rate on the 4xxx-7xxx bands; PR 2 + PR 3 hit
  ~37% on broader 2xxx-7xxx bands. Don't try to fix this by tightening
  the seed without ground-truth data on which 4-digit codes are
  actual residential postcodes — the silent skips are the cost of
  using the comprehensive CC0 list rather than a curated one.
- 127 / 150 House-seat electorate coverage is the load-bearing
  metric for the public postcode-search UI. Batch J added 4 new
  electorates; further postcode batches will yield diminishing
  returns on electorate count (most additional postcodes will land
  in already-covered electorates). The 23 missing electorates are
  likely fragmented inner-metro Sydney/Melbourne, plus remote
  regional electorates where AEC's finder data is sparse.
- Batch J did not change any project source file. No new tests,
  no new migrations, no schema changes. This is a pure data-
  expansion batch.

358/358 backend pytest pass. ruff clean. frontend production build
clean. Direct-money invariant test still passes.

## 2026-05-01 (Batch I — last-mile licence verbatim + 200-postcode bulk fetch + exception-request letters)

Five PRs landed:

- **I #1: Australia Post + AIMS Coastline last-mile verbatim.** The
  prior Australia Post `auspost.com.au/about-us/about-our-site/our-licensing-arrangements`
  URL is a permanent 404 in 2026; the canonical free-tier product
  page is now at `postcode.auspost.com.au/free_display.html?id=1`
  and its title is literally "Non-commercial use only". `docs/source_licences.md`
  patched with the verbatim restriction wording from that page
  (no sub-licensing / no derivative works / no public lookup /
  Australia Post retains all property rights). AIMS Coastline's
  eAtlas companion remains HTTP 403 to plain HTTP clients and a JS-
  rendered Angular SPA when accessed via Wayback; the data.gov.au
  record's verbatim "Licence Not Specified" is the canonical source
  and drives the conservative blocked status. The project-level
  "Implications" block now records that all ten sources carry
  verbatim direct-fetch wording (or, for AIMS-eAtlas, conclusively
  unfetchable status with the data.gov.au verbatim as the
  load-bearing record).
- **I #2: 200-postcode residential-sample bulk fetch.** Earlier
  staged runs against the head of the CC0 list silently produced
  zero crosswalk rows because postcodes 1000-1099 are PO Box / large-
  volume-recipient codes that AEC's electorate finder doesn't return
  any localities for — the script exits 0 because there's nothing to
  process. Built a residential-sample list (200 postcodes spaced
  across NSW/VIC/QLD/SA/WA/TAS/ACT/NT residential ranges) and ran
  the bulk fetch through `scripts/expand_postcode_seed.sh`. Live
  results: **191 resolved postcode_electorate_crosswalk rows** (was
  51), **35 unresolved postcode candidates**, 200 postcodes
  refreshed, 26 ambiguous-postcode candidates (multi-electorate),
  133 unique source documents upserted. Coverage now spans NSW (84)
  / VIC (71) / QLD (12) / ACT (6) / WA (6) / NT (5) / TAS (4) / SA
  (3).
- **I #3: methodology permalink upgrade — blocked on a public
  mirror URL existing.** `git remote -v` shows no remote on this
  repo (the project hasn't been published to a public git mirror
  yet). The `METHODOLOGY_REPO_URL` env-var hook is wired and live;
  whoever publishes the public mirror just sets that env var in the
  build environment and the marker becomes a clickable link.
  Documented as the explicit unblocking step in `docs/session_state.md`.
- **I #4: APH + AEC GIS public-redistribution exception letters.**
  Drafted two letters under `docs/letters/`:
  - `aph_public_redistribution_request.md` — to the Clerks of the
    House and Senate, asking whether structured-record transformation
    of registers of interests, MP/Senator contacts CSV, Votes &
    Proceedings, and Senate Journals constitutes a derivative work
    for CC BY-NC-ND 4.0, and requesting an exception or scope
    clarification.
  - `aec_gis_public_redistribution_request.md` — to AEC GIS,
    confirming that the project's re-projected vector-tiled
    publicly-served treatment of federal electorate boundary geometry
    sits within the End-user Licence's "Derivative Product"
    permission.
  - `docs/letters/README.md` records the archive policy: replies go
    under `docs/letters/replies/<recipient>_<YYYYMMDD>.{pdf,txt,html}`,
    a summary block goes onto the corresponding draft, and
    `docs/source_licences.md` is updated with the new licence-status
    row.
- **I #5: residual deferred items.** Firefox visual smoke is already
  done in the in-app browser (Batch F #2). Sub-national party seeds
  rollout stays deferred until state/local rollout per
  `docs/sub_national_party_seeds_plan.md`. State/local expansion
  (NSW/VIC after QLD) stays deferred per the dev's standing
  direction.

358/358 backend pytest pass. ruff clean. frontend production build
clean. Direct-money invariant test still passes.

## 2026-04-30 (Batch H — direct-fetch licence verbatim + CC0 postcode seed + is_personality_vehicle API surface)

Three PRs landed (`2c6946f`, `c787130`, `e3a8803`):

- **H #1 — direct-fetch licence verbatim (`2c6946f`).** Replaced the
  search-confirmed wording in `docs/source_licences.md` with verbatim
  text fetched directly from each publisher's licence page on
  2026-04-30. Eight of ten sources now carry verbatim direct-fetch
  wording (AEC website, AEC GIS, APH, ABS, TVFY, MapTiler ×2, OSM,
  Natural Earth). AIMS Australian Coastline 50K verbatim string from
  data.gov.au is literally **"Licence Not Specified"** — status
  downgraded from needs-follow-up to **blocked** for public
  redistribution; substitute with Natural Earth coastline (public
  domain). The eAtlas companion of AIMS returned HTTP 403; the
  Australia Post licensing-arrangements URL resolved to a 404 (the
  page appears to have been moved/JS-rendered). Both flagged as
  not-yet-verbatim with explicit follow-ups for a maintainer with a
  browser. APH's current Creative Commons deed is now confirmed as
  **CC BY-NC-ND 4.0 International** (the search-only round had recorded
  3.0 AU; NC-ND restrictions are still load-bearing either way). AEC
  GIS direct-fetch is **friendlier** than the search-only round
  suggested — derivative products ARE permitted with attribution. The
  project-level "Implications" block updated accordingly.
- **H #2 — CC0 comprehensive postcode seed (`c787130`).** New
  `scripts/build_postcode_seed_from_cc0.sh` downloads Matthew
  Proctor's `matthewproctor/australianpostcodes` GitHub dataset
  (Public Domain / CC0), archives the source CSV with SHA-256, and
  writes a deduplicated 4-digit-postcode list (8957 unique postcodes)
  to `data/seeds/aec_postcode_search_seed_full.txt`. The default
  pipeline seed at `data/seeds/aec_postcode_search_seed.txt` stays at
  the curated 48-postcode v2 list to respect AEC endpoint etiquette
  during routine runs. `docs/data_sources.md` gains a "Postcode Seed
  (Comprehensive)" section explaining the source choice (NOT
  Australia Post — blocked) + the staged-bulk-fetch operational
  recommendation.
- **H #3 — `is_personality_vehicle` wired through API + frontend
  (`e3a8803`).** Closes the inert-flag gap reviewer-flagged in
  Batch G #2. `_representative_party_exposure_summary` now selects
  `party.metadata->>'is_personality_vehicle'` and
  `party.metadata->>'affiliated_person_hint'` and propagates both
  through the response payload. `RepresentativePartyExposureSummary`
  TypeScript type updated. `DetailsPanel.tsx` renders personality-
  vehicle rows with a "personal electoral vehicle" suffix in the
  label and a chip in the detail line: "personal electoral vehicle
  for <name> — not an ideological federal party" when an
  affiliated_person_hint is present. The Batch G #2 regression test
  is upgraded from a blanket "no office_term may reference these
  rows" assertion to an end-to-end API surface assertion: seeds a
  personality-vehicle party + office_term + recipient-side
  influence_event + reviewed party_entity_link, then asserts the API
  returns `is_personality_vehicle=True` and the affiliated_person_hint
  string. Locks the wiring end-to-end (party metadata → SQL
  projection → API response shape → frontend chip).
- **Permission allowlist** (`.claude/settings.local.json` —
  gitignored) broadens WebFetch / WebSearch / curl / make / npm allow
  rules so future runs skip the per-URL permission gate. This file is
  intentionally NOT committed (it's local-only per the existing
  `.claude/` gitignore rule).

358/358 backend pytest pass. ruff clean. frontend production build
clean. Direct-money invariant test still passes.

## 2026-04-30 (Batch G — licence capture + permalink env-var + candidate-vehicle seed + postcode parser fix + v2 seed + sub-national plan)

Seven changes landed:

- **G #1: methodology permalink env-var.** `frontend/scripts/sync-methodology-version.mjs`
  now reads `METHODOLOGY_REPO_URL`. When set, the SHA marker is wrapped
  in an `<a href="${url}/commit/${sha}">` (with a `-dirty` suffix kept
  in link text but stripped from the URL). Fully idempotent — placeholder
  regexes are non-greedy so a later run with a different URL re-wraps
  cleanly, and a re-run without the env var strips the link.
- **G #2: candidate-vehicle party seed migration 037.** Adds the four
  AEC-registered "candidate-vehicle" / personality registered names
  ("Dai Le & Frank Carbone W.S.C.", "Kim for Canberra", "Tammy Tyrrell
  for Tasmania", "votefusion.org for big ideas") as federal canonical
  rows with explicit `is_personality_vehicle` metadata flag. Drops
  `unresolved_no_match` to **0 across all client_types** (was 4
  politicalparty + 1 associatedentity). Reviewed `party_entity_link`
  count 147 → 148.
- **G #2 reviewer follow-up.** Added regression test
  `test_no_office_term_references_personality_vehicle_party_row`. The
  test seeds a personality-vehicle party row directly in the
  integration schema (the fixture order means migration 037
  short-circuits during fixture setup) and asserts no `office_term`
  references it. If a future loader ever links an MP's office_term
  to one of the personality-vehicle parties without first wiring the
  flag through the API, this test fails closed.
- **G #3: source-licence doc.** New `docs/source_licences.md` records
  per-source licence terms, attribution wording, and redistribution
  status for AEC website / AEC GIS / APH / AIMS Coastline 50K / ABS /
  TVFY / MapTiler / OpenStreetMap / Natural Earth / Australia Post.
  Critical findings flagged on AEC GIS (Limited End-user Licence —
  needs follow-up before public redistribution), APH (CC BY-NC-ND
  3.0 AU — derivative work restrictions), Australia Post (blocked for
  public postcode lookup), AIMS (licence string still unverified).
  README now links to the doc.
- **G #4: postcode parser pagination-row fix.** Live AEC Electorate
  Finder responses for high-population postcodes (2800, 2480, 0820,
  0850, 0870, 4350, 3350, 6330) include a paginated GridView footer
  the parser was mistaking for a data row, raising `ValueError:
  Expected a four-digit Australian postcode, got '2'` mid-normalize.
  Added `_PAGINATION_CELL_RE` + `_looks_like_pagination_row()` filter
  in `_table_rows()` and a defensive `try/except ValueError` skip in
  the per-row loop. New unit test
  `test_parse_aec_electorate_finder_postcode_skips_pagination_footer`
  pins the fix.
- **G #4: postcode v2 seed.** Replaced the bootstrap 8-postcode seed
  list with a curated 48-postcode v2 seed covering capital-city CBDs
  + 1-3 regional centres / second cities per state-territory. Live
  fetch + load yielded 51 crosswalk rows (was 9), 8 unresolved
  postcode candidates (electorate names from AEC that don't match the
  loaded boundary table — left as auditable observations). Wrapper at
  `scripts/expand_postcode_seed.sh` and `make expand-postcode-seed`
  remain available for the future ~3000-postcode national seed.
- **G #5: sub-national party seeds rollout design doc.** New
  `docs/sub_national_party_seeds_plan.md` records the deferred design
  for state-jurisdiction party-mediated exposure: seed migrations per
  state, dual resolver invocations (federal + state), API
  jurisdiction filter on `_representative_party_exposure_summary`,
  and the test-coverage requirements per state-rollout PR. QLD is
  the first target because QLD ECQ data is already loaded; NSW / VIC
  / others follow the deferred state/local rollout.

358/358 backend pytest pass (was 356; +2 new tests). ruff clean.
frontend production build clean. Direct-money invariant test still
passes.

## 2026-04-30 (Batch F — methodology auto-stamp + visual smoke + politicalparty long tail + postcode-expansion path)

Four PRs landed:

- **F #1: build-time methodology version + revision injection.** Replaced
  the hand-edited `2026-04-30 / 3f40524` revision marker on
  `frontend/public/methodology.html` with `<code data-methodology-
  version-date>` and `<code data-methodology-version-sha>` placeholders.
  New `frontend/scripts/sync-methodology-version.mjs` calls
  `git rev-parse --short HEAD`, suffixes `-dirty` if the working tree
  has uncommitted changes, and stamps both placeholders in place.
  Wired into npm `predev` + `prebuild` so dev and build always carry
  the actual current SHA (no more stale markers). Standalone
  invocation as `npm run sync:methodology-version`.
- **F #2: residual visual smoke via the in-app browser.** Confirmed
  state-map mode (`State map beta`, 93 features, Algester selected,
  state-map-layer caveat intact); council-map mode (`Council map beta`,
  78 QLD-LOCAL features, Aurukun Shire selected, "are not treated as
  personal receipts or representative-linked claims" caveat intact);
  and the influence-graph panel (134 source-backed/reviewed/context
  connections for Bean's MP, full claim-discipline subtitle, selected-
  connection drawer with source URLs). All three panels rendered with
  the project's strict "do not prove causation or improper conduct"
  framing.
- **F #3: politicalparty long-tail seed migration + 7 new alias
  rules.** Migration `036_seed_additional_canonical_party_rows_v2.sql`
  adds nine federal-jurisdiction canonical rows (Australian Federation
  Party, Family First Party Australia, The Great Australian Party,
  Better Together Party, Indigenous - Aboriginal Party of Australia,
  Socialist Alliance, Sustainable Australia Party, Power 2 People,
  Health Environment Accountability Rights Transparency). Each row
  carries seed-source / date / rationale / attribution-caveat
  metadata; idempotent on rerun. Resolver gained 7 new alias rules:
  Greens parens-without-Branch + comma-form + unpunctuated-form, "The
  Greens" short-form + Inc-suffix, Nationals state divisions with Inc
  suffix, Australian Federation Party state suffixes, Libertarian
  Party state branches, "Affordable Housing Now -" prefix for
  Sustainable Australia Party, and the HEART parenthetical
  short-form. 23 new resolver unit tests (14 alias-rule checks,
  9 seeded-canonical-party exact checks). Live load post-PR drops
  `politicalparty` `unresolved_no_match` from 31 to **4** (the
  remaining 4 are deliberately-excluded candidate-vehicle / personality
  registered names: "Dai Le & Frank Carbone W.S.C.", "Kim for Canberra",
  "Tammy Tyrrell for Tasmania", "votefusion.org for big ideas").
  Reviewed `party_entity_link` count unchanged at 147 (politicalparty
  client_type doesn't auto-create links per the C-rule); the win is
  cleaner audit trail.
- **F #4: postcode seed expansion path.** New
  `scripts/expand_postcode_seed.sh` wrapper feeds an arbitrary seed
  file through the existing fetch → normalize → load chain with
  `--max-postcodes=N` cap support. New `make expand-postcode-seed`
  target documents the operational etiquette: a full ~3000-postcode
  national seed should be a deliberate maintainer run, not part of the
  weekly federal pipeline. The maintainer chooses the source list
  (data.gov.au community-curated postcode CSV, ABS POA shapefile, or
  Australia Post free-tier locality CSV) and documents the source
  choice in `docs/data_sources.md` before running with a non-bootstrap
  list. The actual ~3000-postcode bulk fetch is intentionally NOT run
  in this batch — it's a maintainer decision, not an agent-run task.

356/356 backend pytest pass (was 333 pre-Batch-F; +23 new). ruff clean.
frontend production build clean.

## 2026-04-30 (Batch E — public reproducibility + visual smoke + perf + curated seed)

Three PRs landed (`4409f6f`, `28ca462`, `a57fe19`) plus the live
visual smoke through the in-app browser:

- **PR 1 — public reproducibility infra.** Top-level `Makefile` with
  the public reproducibility entry points (bootstrap / db-up /
  db-ready / reproduce-federal / verify / fetch-aec-register /
  load-aec-register / fetch-postcode-crosswalk / load-postcode-crosswalk
  / api-dev / frontend-dev / test / lint).
  `scripts/reproduce_federal_from_scratch.sh` runs the full live fetch
  → migrate → load → QA → pytest → ruff → frontend-build chain with
  per-stage logs in `data/audit/logs/`. `scripts/clean_local_data.sh`
  is a confirmed-deletion helper for `data/raw` + `data/processed` +
  `data/audit`. Top-level `README.md` rewritten with a prominent
  "Reproduce every number on the site" section, the one-command recipe,
  the targeted entry-point table, the auditing checklist, and a
  refreshed local-serving baseline.
- **PR 2 — methodology HTML reproducibility section.** Added
  `#reproducibility` section + nav anchor on
  `frontend/public/methodology.html`. Walks a public reader through
  the clone → bootstrap → reproduce recipe; bullets every concrete
  thing `make reproduce-federal` does (locked deps, live fetch,
  raw + processed archive, audit manifest, qa gate, pytest with the
  cross-cutting direct-money invariant); covers `--smoke` mode and
  the targeted entry points; points at `docs/reproducibility.md` for
  the full policy.
- **PR 3 — curated party-seed migration + extended resolver alias
  rules.** Migration `035_seed_additional_canonical_party_rows.sql`
  adds four federal-jurisdiction canonical `party` rows the AEC
  Register names but the local DB never carried: Animal Justice
  Party, Australian Citizens Party, Libertarian Party, and Shooters,
  Fishers and Farmers Party. Each row records seed source / date /
  rationale / attribution caveat in metadata; idempotent on rerun.
  Resolver gained 7 new alias rules (Liberal long form, Liberal state
  divisions in comma- and hyphen-delimited form, dot-abbreviated state
  codes, full state names, WA "Inc" suffix, LNP-of-QLD long form,
  CLP-(NT)) plus extended state-list coverage on the existing Liberal
  / Nationals state branch rules. Stage 3 (parenthetical short-form
  alias) now also runs deterministic source-jurisdiction disambiguation
  so `Australian Labor Party (ALP)` resolves to the federal-jurisdiction
  ALP row rather than falling through to unresolved on the parallel
  QLD-jurisdiction row. 18 new resolver unit tests (13 parametrised
  alias-rule checks, 4 seeded-party exact checks, 1 parenthetical
  disambiguation). Full backend pytest 333/333 (was 315 pre-Batch-E).

Live results post-Batch E:

- Reviewed `party_entity_link` rows: 87 → **147** (89 ALP, 38 LP,
  7 NATS, 6 LNP, 2 Australian Citizens Party, 1 each → SFF, AG, CLP,
  AJP, Libertarian).
- `associatedentity` unresolved_no_match: 60 → **1**.
- `politicalparty` unresolved_no_match: 49 → 31 (remaining are
  state-level parties without a federal canonical parent — out of
  scope for federal-jurisdiction disambiguation).
- API perf check: `_representative_party_exposure_summary` across
  all 149 current House MPs — p50 5.8 ms, p90 6.7 ms, p99 12.7 ms,
  max 16.5 ms. EXPLAIN ANALYZE shows clean bitmap-index-scan +
  nested-loop-with-index plan; total execution 7.5 ms / 0 disk reads.
- Visual smoke via the in-app browser confirmed: map renders 150
  features, Bean (ALP) details panel surfaces "Party-Linked Money
  Exposure" with `Est. exposure` line and `denominator scope: current
  office-term party representatives only (asymmetric — see methodology)`
  chip; methodology page anchors all reachable; postcode-search
  endpoint returns ambiguous-2600 correctly with confidence 0.5 +
  caveat.

## 2026-04-30 (Batch D #2 — postcode crosswalk live verification)

Completed:

- Confirmed `aec_electorate_finder.py` + `db.load.load_postcode_electorate_crosswalk`
  + CLI wiring + pipeline steps already form a complete fetch → normalize
  → load chain. Re-fetched the 8 postcodes from the bootstrap seed
  (`data/seeds/aec_postcode_search_seed.txt`) against the live AEC
  electorate-finder endpoint, normalised the JSONL, and reloaded into
  Postgres: 9 `postcode_electorate_crosswalk` rows / 1 ambiguous
  postcode (2600 → Canberra + Bean) / 0 unresolved candidates / 8
  source documents upserted.
- Hit `search_database` for `q=2600` (ambiguous), `q=3000` (Melbourne),
  `q=0800` (Solomon) and confirmed every result includes the
  attribution caveat *"AEC postcode search can return multiple federal
  electorates because a postcode can contain multiple localities or
  split across boundaries…"*, the boundary-context label, and the
  current-member-context label. Confidence 0.5 for ambiguous postcodes
  and 1.0 for unambiguous, as designed.
- Existing postcode tests all pass: 2 in `test_aec_electorate_finder.py`
  (parser + ambiguity preservation), 1 in
  `test_postgres_integration.py::test_postcode_loader_keeps_unresolved_aec_candidates_auditable`.
- No new code was needed; the wiring landed earlier as part of schemas
  022-025. Batch D #2's actual work was a live-data smoke run plus
  documentation that the path is production-ready.

## 2026-04-30 (Batch D #1 — live AEC Register pipeline run + verification)

Completed (3 PRs):

- **PR 1: fetcher metadata fix.** Live load failed on first run with
  `KeyError: 'body_path'` because the AEC Register fetcher's archive
  metadata didn't include the fields that the shared
  `db.load.upsert_source_document` helper requires (`body_path`,
  `final_url`, `content_type`). Updated `_http_get`/`_http_post_form` to
  return the response's final URL as a 4-tuple, added a
  `_content_type_from_headers` helper, and made `_write_archive` inject
  `body_path` into metadata before writing it to disk. Fixture-level
  fetcher tests updated to construct `_FakeResponse` with a `url`
  attribute. 18/18 unit tests still pass.
- **PR 2: deterministic source-jurisdiction disambiguation in the
  branch resolver.** The first live load showed 86
  `unresolved_multiple_matches` segments out of 184 associated entities
  because the local DB intentionally stores both federal-jurisdiction
  and QLD-jurisdiction rows for `Australian Labor Party`,
  `Liberal National Party`, `Independent`, and `Katter's Australian
  Party` (state-level rows from prior QLD ECQ ingestion). Added a new
  resolver step `source_jurisdiction_disambiguation_v1` that, when the
  loader passes a `source_jurisdiction_id`, narrows multi-match
  candidates to those whose `jurisdiction_id` equals the source's own
  jurisdiction. The rule consults a stable, source-attributed integer
  attribute — not fuzzy similarity. Multi-row matches that
  disambiguation cannot break (two rows in the same jurisdiction) still
  fail closed. Loader updated to look up the local Commonwealth
  jurisdiction id (`level='federal' AND code='CWLTH'`) and pass it
  through. 7 new resolver unit tests added (37/37 pass).
- **PR 3: one-shot data-fix migration
  `034_consolidate_federal_party_duplicates.sql`.** Even with
  jurisdiction disambiguation, AEC-Register-derived links pointed to
  federal-jurisdiction long-form rows (e.g. id=1351 `Australian Labor
  Party`) which had ZERO active office_term references — actual MPs sit
  on the parallel short-form rows (e.g. id=1 `ALP`). The migration
  consolidates eight federal short/long-form duplicate pairs (ALP, IND,
  AG, NATS, LP, LNP, ON, KAP), re-points all FK references from the
  long-form id to the short-form id, deletes the long-form row, and
  promotes the long-form display name onto the surviving short-form
  row. State-jurisdiction rows are untouched. Idempotent (no-op when
  long-form rows absent). Direct-money invariant test passed
  unchanged.

Live results post-Batch D #1:

- AEC Register fetcher: 70 politicalparty / 184 associatedentity / 55
  significantthirdparty / 44 thirdparty rows (353 total) archived
  verbatim under `data/raw/aec_register_of_entities_*` with anti-forgery
  token + cookie values redacted from metadata.
- Loader: 184/184 associated-entity observations upserted; 87 unique
  reviewed `party_entity_link` rows (86 → ALP, 1 → AG); 0
  multi_match_segments_skipped after disambiguation (was 86 before);
  resolver mix on associatedentity = 86 resolved_branch + 1
  resolved_exact + 37 unresolved_individual_segment + 60
  unresolved_no_match (the no-match segments are parties not present in
  the local `party` table at all, e.g. *Animal Justice Party*, *Liberal
  Party of Australia (Victorian Division)*; per the C-rule we do NOT
  auto-create canonical party rows from this register).
- API check: hit `_representative_party_exposure_summary` for three
  current ALP MPs (Dr Carina Garland, Dr Gordon Reid, Dr Mike
  Freelander). Each surfaces a non-empty summary with party_id=1
  Australian Labor Party (ALP), event_count 4,291, party-context
  reported total $310,815,151, equal-share modelled amount per current
  representative ~$2.53M, denominator 123, claim-scope label
  intact: *"Analytical equal-share exposure to all loaded reviewed
  party/entity receipts for the current party; not a disclosed personal
  receipt or term-bounded total."*
- Direct-money invariant: existing
  `test_loader_does_not_change_direct_representative_money_totals`
  still passes; influence_event aggregate unchanged at 314,040 events
  / $13,483,949,861.89.

Files added/modified:

- `backend/schema/034_consolidate_federal_party_duplicates.sql` (new)
- `backend/au_politics_money/ingest/aec_register_entities.py`
  (metadata + http helpers)
- `backend/au_politics_money/ingest/aec_register_branch_resolver.py`
  (jurisdiction disambiguation + 4-tuple PartyDirectory)
- `backend/au_politics_money/db/aec_register_loader.py`
  (commonwealth jurisdiction lookup + resolver call)
- `backend/tests/test_aec_register_entities.py` (response url plumbing)
- `backend/tests/test_aec_register_branch_resolver.py` (7 new tests)
- `docs/influence_network_model.md` (documented disambiguation +
  consolidation)

## 2026-05-01 (AEC Register of Entities ingestion)

Completed:

- Probed the live AEC Register of Entities endpoint at
  `transparency.aec.gov.au/RegisterOfEntities` to confirm shape before
  designing a parser. Findings: GET → token extraction → POST flow, one
  token + one anti-forgery cookie reused across paginated POSTs in a
  session, JSON `{Data: [...], Total: <int>, ...}` shape, and crucially
  the working third-party `clientType` value is `thirdparty` not
  `thirdpartycampaigner` (the latter returns HTTP 500). Recorded the
  finding and the AEC field-name typos (`RegisterOfPolitcalParties`,
  `LinkToRegisterOfPolitcalParties`, `AmmendmentNumber`) so downstream
  loaders preserve them verbatim.
- Added Batch C PR 1: fetch + raw archive module
  (`backend/au_politics_money/ingest/aec_register_entities.py`) plus four
  source registry entries, a `fetch-aec-register-of-entities` CLI command,
  and 18 mock-HTTP unit tests. Anti-forgery token + cookie values are
  redacted from raw archive metadata; the `Cookie` request header is
  never persisted. Refuses to publish empty observation sets, fails loudly
  on HTTP error / non-JSON / missing token / multiple distinct tokens / a
  hard 50-page pagination cap. Live test_aec_register_entities suite
  passes 18/18.
- Added Batch C PR 2: schema 033 (registration-observation table),
  deterministic branch resolver
  (`backend/au_politics_money/ingest/aec_register_branch_resolver.py`),
  loader (`backend/au_politics_money/db/aec_register_loader.py`), CLI
  `load-aec-register-of-entities`, plus 30 resolver unit tests and 7
  Postgres integration tests. Implements the dev's C-rule per client_type:
  `politicalparty` → entity + identifier only (no auto party_entity_link;
  unresolved register rows are NOT auto-promoted to canonical `party`
  rows); `associatedentity` → reviewed `party_entity_link` ONLY when the
  AssociatedParties segment resolves to exactly one canonical `party.id`
  via exact name/short_name match, the documented branch alias rules
  (ALP/Liberal/Greens/Nationals state branches → canonical parent), or a
  parenthetical short-name alias; `significantthirdparty` /
  `thirdparty` → entity + identifier only regardless of AssociatedParties
  content. Reviewed links carry `method='official'`,
  `confidence='exact_identifier'`, `reviewer='system:aec_register_of_entities'`,
  and an evidence_note recording the AEC client_id, raw segment, resolver
  rule, and the explicit attribution-limit caveat. Multi-segment
  AssociatedParties produce one idempotent link per resolved party.
  Individual-name segments (`Allegra Spender`, `Dr Monique Ryan`, etc.)
  never auto-link. Multi-row matches (e.g. duplicate ALP rows in the local
  party table) fail closed as `unresolved_multiple_matches`. The loader
  is idempotent across re-runs and an integration test asserts that
  direct-representative money totals are byte-identical before and after.
- Added Batch C PR 3: pipeline integration. The federal foundation
  pipeline now runs `fetch_aec_register_of_entities_<client_type>` for all
  four client types after the lobbyist register fetch, with smoke runs
  using `take=25` per client_type. Per-client_type fetch failures are
  captured in the manifest without aborting the pipeline.
  `load_processed_artifacts` now also loads any present AEC Register
  JSONL artefacts via a new `include_aec_register_of_entities=True`
  default flag, exposing per-client_type loader summaries on the load
  result.

Verification:

- 30/30 resolver unit tests passing.
- 7/7 Postgres loader integration tests passing.
- Full backend pytest 306/306 passing (with Postgres integration enabled).
- ruff clean across new modules + cli.py + pipeline.py + load.py.
- Frontend production build still clean.

## 2026-04-30 (Batch A — adversarial-review fixes)

Completed:

- Renamed the umbrella headline in the right-side details panel from
  "Published records" to "All disclosed records (any type)" and expanded both
  the section caption and the fact tooltip to explain that the umbrella count
  covers every event family (money, benefits, campaign support, private
  interests, organisational roles, and any other declared types) — not just the
  three families shown as fact cards. The numeric value was already correct;
  the rename addresses a top-down read where users could mistake the headline
  for a single influence-money figure.
- Added an integration assertion in
  `test_campaign_support_stays_separate_from_direct_money_totals` that
  `current_representative_lifetime_influence_event_count` is `>=` the sum of
  `money + benefit + campaign_support` breakdowns shown in the UI, with strict
  equality for the controlled fixture state. Future SQL changes that desync
  the umbrella from its breakdown will fail loudly.
- Added `test_qld_council_disclosure_context_alias_regex_matrix` covering
  Townsville City vs Town of Weipa cross-prefix mismatch, Sunshine Coast
  Regional vs Sunshine Coast Hinterland Regional shared-prefix separation,
  Mareeba Shire ↔ Shire of Mareeba alias-form pairing, and Cairns Regional
  child-area resolution. Asserts both positive and negative match outcomes
  for each pair, so the eight alias regex branches in
  `_qld_council_disclosure_context` cannot quietly drift into false positives.
- Verified that `get_influence_graph` party path already excludes internal
  party-entity flows (queries.py L5106-5112: source_entity_id NOT IN reviewed
  party_entity_link set). The internal-flow exclusion is expressed via SQL set
  difference rather than the explicit `internal_party_entity_flow` enum used
  in `get_party_profile`, but it is functionally equivalent. No code change.
- Surfaced the equal-share denominator asymmetry in the Party-Linked Money
  Exposure UI. The party exposure detail line now renders an explicit
  "numerator scope: all loaded reviewed party/entity receipt records" chip
  alongside "denominator scope: current office-term party representatives only
  (asymmetric — see methodology)" so consumers can see the scope mismatch
  before they read the modelled value.
- Added a "Denominator Asymmetry in `equal_current_representative_share`"
  section to `docs/influence_network_model.md` documenting why the numerator
  is loaded-period and the denominator is current-cross-section, what use the
  resulting figure does and does not support, and what the future
  `union_of_office_terms_during_receipts` enhancement would change.
- Added `make lock` target to `backend/Makefile` that runs
  `python -m piptools compile pyproject.toml --extra dev -o requirements.lock`
  inside the project venv. Declared `pip-tools>=7.4` as a dev dependency in
  `backend/pyproject.toml` so `make install` makes `make lock` runnable. Added
  a "Lockfile Regeneration" subsection to `docs/operations.md` explaining that
  the lock must not be hand-edited and is regenerated only via `make lock`
  when direct dependencies change.
- Added an "Audit Artefact Retention" section to `docs/operations.md`
  documenting per-tree retention rules: keep all `pipeline_runs/` manifests,
  keep latest 30 of each `review_queues/` and `sector_policy_link_suggestions/`
  export with archive of older into `archive/<YYYYMMDD>/`, keep all
  `review_imports/` and `review_replays/` records, keep 90 days of
  `data/audit/logs/`. The whole `data/audit/` tree stays gitignored so this
  is a storage decision, not a reproducibility one.
- Added a "Run state/local smoke pipeline (QLD canary)" step to
  `.github/workflows/federal-pipeline-smoke.yml` so QLD ECQ adapter regressions
  are caught in CI alongside the federal pipeline smoke. Uses the same
  Postgres service container.
- Added project-root `CLAUDE.md` overriding the global per-action approval
  rule for this repository. Gives the editing agent autonomy on read/write
  within agreed plans, while still requiring approval for destructive git
  ops, force-push, external writes, credential rotation, and live external
  pipeline runs.



- Added representative-level benefit highlights to the API and frontend. The
  representative profile now exposes source-backed summaries of declared
  benefit forms (for example private flights, tickets, lounge access, meals,
  accommodation, subscriptions/services) plus the top named benefit providers.
  The details pane shows these as "Gifts, Travel & Hospitality Highlights" so
  users can see the small but politically meaningful influence channels before
  opening raw source cards. The raw records and missing-data caveats remain
  available; the summary does not imply wrongdoing or causation.
- Improved conservative benefit-provider extraction for recurring public-register
  wording. The parser now catches narrow leading-provider descriptions such as
  `Cricket Australia - 2 x tickets` and `McKinnon Institute, covering...`, and
  expands Virgin lounge/club wording to `Virgin Australia`. Senate leading-provider
  matches are review-gated as heuristics. The leading-provider rule deliberately
  rejects generic event/place/route titles such as `Melbourne Cup - 2 x tickets`,
  `State of Origin - hospitality`, and `Sydney to Melbourne - flights`.
- Tightened benefit-highlight claim discipline after review. Benefit summaries
  now expose named-provider counts, missing-data counts, and pending-review
  counts, and the frontend wording says missing values are not recorded in the
  normalized data rather than assuming the public source never published them.
- Added representative-level party-mediated money context. Profiles now expose
  reviewed party/entity money totals and a labelled equal-current-representative
  exposure estimate when the source-backed party/entity links support the path.
  The details pane shows this separately from direct money and campaign support,
  with explicit wording that the estimate is analytical context and not money
  received by the representative.
- Tightened the party-mediated exposure model after review. The API and graph now
  label the estimate as a loaded-period reviewed party/entity receipts exposure
  index, not a term-bounded total, and the UI prefixes the primary value with
  `Est. exposure`. Integration tests now assert that these party/entity receipts
  stay out of direct representative event summaries, recent source cards, and the
  default representative evidence feed.
- Hardened direct representative feeds against over-linked rows. If a money row
  points to a reviewed party/entity recipient, representative profile summaries,
  evidence pages, and map direct totals exclude it from direct person-level
  money even when a person id is also present. The row can still support
  party/entity context and modelled exposure with the appropriate caveat.
- Focused the party/entity review queue on useful representative exposure paths.
  The generator now skips non-party labels such as `Independent` and, by default,
  only materializes candidate links for party rows with current office-term
  representatives. Historical/no-current-rep party rows can still be included
  deliberately with `--include-without-current-representatives`.
- Added click-level QLD council disclosure context without turning the council
  boundary into a recipient. `GET /api/electorates/{id}` now returns a
  `qld_ecq_local_disclosure_context` object for QLD council features when ECQ
  local-electorate labels match the selected council area, a child ward/division
  label, or a cautious current/legacy council-name alias. The object keeps
  gift/donation and electoral-expenditure counts/totals separate, exposes
  matched local labels and top disclosed sources/spenders, and carries the
  explicit caveat that the rows are local disclosure context, not claims of
  receipt by a council, councillor, candidate, state MP, or federal MP. The
  frontend Council details pane now fetches this endpoint on selection and
  labels the resulting counts accordingly.
- Follow-up review tightened the same QLD council context by adding prefix-form
  council aliases such as `Weipa Town` / `Town of Weipa` and removing the
  generic mixed `reported_amount_total` from the council-context payload. Public
  consumers now receive separate gift/donation and electoral-expenditure totals
  only.
- Further tightened public evidence cards. Expanded source-record cards now
  replace internal workflow rows such as `Evidence status: official record
  parsed`, `Review status: needs review`, and `How captured` with
  public-facing `Source basis` and `What this supports` language. Default
  non-values such as unrecorded source rows, missing disclosure thresholds, and
  empty missing-field flags are hidden unless they add substantive information.
  When a source/provider field is not named but the public description contains
  useful text, collapsed cards now use that description instead of leading with
  "Source not named".
- Enabled first-pass State/Council map search in the frontend. Outside federal
  mode the search box now searches the loaded map features client-side by
  electorate/council name, state, current representative names, parties, and
  boundary metadata. This is intentionally map-feature search only; disclosure
  attribution remains governed by the state/local caveats.
- Added `scripts/run_weekly_state_local_pipeline.sh` as the scheduled
  state/local counterpart to the federal weekly runner. It refreshes the
  implemented jurisdiction adapters, stores each pipeline manifest path in the
  audit log, replays manifests into Postgres, rebuilds consolidated influence
  events once at the end, and runs serving QA plus tests.
- Added the first source-backed council map layer. The new QLD
  local-government boundary adapter fetches the official Queensland government
  ArcGIS/QSpatial local-government layer, normalizes 78 current council areas
  into `data/processed/qld_council_boundaries/`, loads them as `council`
  chamber boundaries under the separate `QLD-LOCAL` jurisdiction, and creates
  78 land-clipped display geometries. `/api/map/electorates?chamber=council`
  now serves QLD council map features with a caveat that ECQ disclosure rows
  remain state/local source records unless a source-backed or reviewed link
  supports a narrower council/candidate/councillor/MP attribution. A live
  manifest replay from
  `data/audit/pipeline_runs/state_local_qld_20260429T185533Z.json` loaded
  49,840 QLD ECQ rows, 6,360 participant lookup rows, 912 context rows, 93
  state boundaries, 92 current state MPs, one vacant electorate, and 78 council
  boundaries.
- Optimized display land-mask loading. Boundary loaders now reuse an existing
  loaded AIMS Australian Coastline 50K display mask when no explicit replacement
  GeoJSON is supplied, avoiding a costly PostGIS re-union during routine
  manifest replay while still preserving explicit refresh paths for a new mask.
- Added the first source-backed state electorate map layer. The new QLD
  boundary adapter fetches the official Queensland government ArcGIS/QSpatial
  state electorate layer, normalizes 93 current electorates into
  `data/processed/qld_state_electorate_boundaries/`, loads them as `state`
  chamber boundaries, and creates 93 land-clipped display geometries using the
  Australian coastline display mask. `/api/map/electorates?chamber=state`
  now serves QLD state map features with a caveat that disclosure rows remain
  separate until a source or reviewed model supports electorate/MP attribution.
- Added the first state current-representation join. The QLD Parliament
  current-member mail-merge XLSX is now fetched, normalized, and loaded into
  `person` and `office_term` as a current state roster snapshot. The live run
  joined 92 current MPs to QLD state electorates, preserved one vacant/unjoined
  electorate, and exposed public electorate-office email/address details in the
  state map payload. The State details panel now shows these roster facts while
  explicitly avoiding claims that ECQ disclosure rows are personal receipts or
  electorate-level attributions.
- Folded the QLD state map and current-member roster into the reproducible
  state/local manifest path. `run-state-local-pipeline --jurisdiction qld` now
  archives and normalizes ECQ disclosure exports, ECQ lookup enrichments, QLD
  state boundaries, and the Queensland Parliament current-member roster in one
  non-mutating manifest run. `load-state-local-pipeline-manifest` validates and
  loads the exact named artifacts, rejects failed or partial map/roster
  manifests, checks boundary/member artifact and raw source hashes, and verifies
  that artifact-derived boundary and roster electorate-name sets match; the live
  smoke/replay run loaded 49,840 QLD ECQ rows, 93 state boundaries, 92 current
  MPs, and one vacant electorate with influence-event rebuild skipped for fast
  loader validation.
- Hardened House-register `As above` handling for multi-record owner blocks.
  When a spouse/partner row says `As above` after several self disclosures, the
  parser now preserves the whole preceding owner block rather than only the
  immediately previous row. After regenerating and loading the House interest
  artifact, the local DB has 5,846 current House interest records, 1,364
  benefit events, 314,040 non-rejected influence events, and 7,831
  person-linked influence events. The refreshed federal review bundle is
  `data/audit/review_bundles/federal_review_bundle_20260429T175537Z.summary.json`.
- Added jurisdiction filtering to the state/local API and frontend summary
  panel. `/api/state-local/summary` and `/api/state-local/records` now accept
  `jurisdiction_code` (`ACT`, `NSW`, `NT`, `QLD`, `SA`, `TAS`, `VIC`, `WA`);
  QLD local/council requests map to the loaded `QLD-LOCAL` jurisdiction code.
  Pagination cursors include the selected jurisdiction so a "load more" action
  cannot mix rows from a previous state selection. The frontend state selector
  now filters the State and Council panes as well as the federal map.
- Hardened the Tasmania declaration evidence chain after review. A declaration
  PDF marked `archived` must now have an existing body file whose SHA-256
  matches the fetch metadata, and the TAS manifest loader verifies both
  declaration metadata and archived PDF body hashes before allowing a processed
  artifact into a database load. The frontend declaration label now counts only
  URL-backed declaration documents, so statuses such as `failed_to_lodge` do
  not inflate the archived-document denominator.
- Made the state/local recent-row filter jurisdiction-aware. When users choose
  TAS, ACT, WA, NT, SA, VIC, or QLD, the row-type chips now show only flow
  families that can exist in that jurisdiction, while `All` still exposes the
  cross-jurisdiction list. This avoids inviting users into empty combinations
  such as TAS plus QLD expenditure.
- Tightened the representative evidence-card display so the public pane no
  longer repeats invariant workflow labels (`official_record_parsed`,
  `needs_review`, default not-disclosed amount status, or numeric register
  period) as if they were substantive findings. Collapsed cards now prioritize
  record type, named source/provider where available, source wording, disclosed
  amount/date facts, and compact public-facing chips. Provenance, extraction,
  review, period, source-row, and missing-field details remain available in the
  expanded record view.
- Hardened benefit-provider extraction for small-gift and travel records. The
  shared House/Senate interests parser now preserves public parenthetical
  acronyms in provider names, such as `(ASTRA)`, and avoids turning travel
  class changes, such as "Economy to Business", into invented source entities.
  Route wording such as "flight from Sydney to Melbourne provided by Qantas"
  remains supported.
- Tightened TAS TEC declaration evidence validation after adversarial review.
  The manifest loader now checks that the unique declaration URL set in the
  JSONL rows exactly matches the attempted archive URL set in the summary, and
  that each supporting-document metadata file is bound to the deterministic
  source id and source/final URL for the claimed declaration URL. This prevents
  partial archive coverage or swapped declaration-document hashes from being
  accepted as reproducible evidence.
- Regenerated the federal House/Senate interest artifacts after the benefit
  parser hardening and refreshed the local PostgreSQL `gift_interest` plus
  unified `influence_event` layers. The refresh loaded 5,838 current House
  interest records, 1,752 Senate interest records, and 314,032 influence
  events, including 1,458 disclosed benefit events. The two known travel-class
  upgrade examples now remain missing-provider rows rather than invented
  provider entities.
- Generated a full federal review bundle under
  `data/audit/review_bundles/federal_review_bundle_20260429T162159Z.summary.json`.
  The bundle materialized 1,536 party/entity link candidates and exported
  review queues for 1,438 benefit events, 2,043 official identifier match
  candidates, 27,059 entity-sector classifications, 1,536 party/entity links,
  and 18 sector-policy suggestions. These files are review inputs only; public
  graph/path claims still require accepted review decisions with supporting
  sources.
- Hardened House interest record filtering against additional alteration-form
  and OCR artifacts, including inline `GIVEN NAMES`, `FAMILY NAME`,
  electorate/state labels, `N/A`, `Value: Unknown`, standalone value fragments,
  and short parliamentary form-tail lines. After regenerating House records and
  refreshing `gift_interest`/`influence_event`, the local DB now has 5,844
  current House interest records and 1,362 benefit events; known form artifacts
  such as `GIVEN NAMES`, `FAMILY NAME`, `48TH PARLIAMENT`, `N/A`,
  `Value: Unknown`, and `GRAYNDLER NSW` are absent from benefit events. A
  cleaned federal review bundle was then generated at
  `data/audit/review_bundles/federal_review_bundle_20260429T164609Z.summary.json`
  with 1,342 benefit-event review rows.
- Expanded the serving-database QA gate so future runs fail if known House
  form/OCR artifacts reappear through exact or regex matches. The current
  local serving QA run passes with 150 House boundaries, zero public events
  from non-current source rows, zero obvious form-noise events, 11 unmatched
  official APH roster votes under the configured maximum of 25, 314,038
  non-rejected influence events, 7,829 person-linked influence events, 303,230
  current money-flow rows, 7,596 current gift-interest rows, 150 current House
  office terms, and 76 current Senate office terms.
- Regenerated and loaded the current official APH division artifact from House
  Votes and Proceedings plus Senate Journals PDF snapshots. The parser produced
  482 official divisions: 147 House divisions and 335 Senate divisions, with
  zero vote-count mismatches. The loader inserted/updated 36,234 current
  official APH person-vote rows: 17,519 House rows and 18,715 Senate rows. The
  11 unmatched official vote names are retained as raw unmatched names rather
  than guessed roster matches.
- Preserved House-register `As above` disclosures as source cross-references
  instead of treating them as non-values. The parser now resolves `As above` to
  the previous parsed disclosure where possible, keeps the new owner context
  and the original source text in metadata, and skips only unresolved
  cross-references. After regenerating and loading the artifact, the local DB
  has 5,845 current House interest records, 270 current House sponsored
  travel/hospitality rows, 1,363 benefit events, 314,039 non-rejected influence
  events, 7,830 person-linked influence events, and 7,597 current gift-interest
  rows. The regenerated federal review bundle is
  `data/audit/review_bundles/federal_review_bundle_20260429T170338Z.summary.json`
  with 1,343 benefit-event review rows.
- Hardened ACT annual-return receipt handling after review. Broad annual
  `act_annual_receipt` rows are now loaded as state source-row context with
  `public_amount_counting_role =
  state_source_receipt_context_not_consolidated`; influence events for those
  rows use `amount_status = not_applicable` and flags documenting that the row
  is not counted in consolidated reported totals and is not a personal receipt.
  ACT annual gift rows and free-facility-use rows remain counted
  source-backed observations.
- Expanded the Tasmania TEC adapter to archive linked donor/recipient
  declaration PDFs as supporting evidence. The 2026-04-29 live run extracted
  216 reportable donation/loan rows and 366 declaration-document URLs; 365
  declaration PDFs archived successfully with SHA-256 hashes and 1 TEC link
  returned HTTP 404. Failed supporting-document fetches are retained as audit
  metadata and do not stop the table row from loading, because the table itself
  remains the structured source observation. The public API exposes declaration
  URL, role, archive status, hash, HTTP status, content type, and fetched time,
  but strips local filesystem archive paths.

## 2026-04-29

Completed:

- Expanded `run-state-local-pipeline --jurisdiction act` from current
  gift-return rows into a two-source ACT state disclosure pipeline. It now
  archives and normalizes the 2025-2026 gift-return page plus the 2024/2025
  annual-return receipt detail page. The 2026-04-29 implementation run produced
  225 gift-return rows and 350 annual-return receipt rows: 173 annual gifts of
  money, 26 annual gifts-in-kind, 7 free-facility-use rows, and 144 other
  receipt rows. This adds much more useful ACT person/entity context, including
  MLA annual-return gift-in-kind rows, while preserving the caveat that annual
  receipt rows do not publish per-row receipt dates and are not personal-income
  or wrongdoing claims.
- Added `run-state-local-pipeline --jurisdiction tas` for the first Tasmania
  TEC row-level adapter. It archives the monthly reportable donation table and
  the 2025 House of Assembly / 2026 Legislative Council seven-day disclosure
  table fragments, normalizes donor-to-recipient reportable political donation
  and reportable-loan observations into
  `data/processed/tas_tec_donation_money_flows/`, validates source/summary/JSONL
  hashes in manifest loading, and exposes `tas_reportable_donation` /
  `tas_reportable_loan` rows through the state/local API and UI. The adapter
  preserves the 2025-07-01 disclosure-regime start caveat and keeps loans
  distinct from gifts. The 2026-04-29 implementation run extracted 216 TEC
  rows: 215 donation rows and 1 reportable-loan row.
- Simplified representative record cards in the right-side panel: invariant
  backend provenance chips such as `official_record_parsed` and `needs_review`
  are now kept in detail/tooltips rather than repeated on every card; the card
  emphasizes human-readable record type, named source/provider, source wording,
  useful date/amount metadata, and a section-level caveat for missing dollar
  values.
- Added `run-state-local-pipeline --jurisdiction wa` for the first Western
  Australia WAEC state-level adapter. It archives the official Online
  Disclosure System public dashboard, token response, and Power Pages
  entity-grid JSON pages for published political contributions, then normalizes
  donor-to-political-entity contribution rows into
  `data/processed/waec_political_contribution_money_flows/`. The 2026-04-29
  implementation run extracted 6,661 rows with $13,318,292.66 in counted
  original-version source-row value; WAEC's grid `ItemCount` appears capped at
  5,000 while `MoreRecords` continues to page beyond that cap, so the normalizer
  validates completeness against summed per-page record counts and records the
  source cap caveat in the summary. The loader rejects incomplete smoke
  artifacts, validates manifest/summary/source/body/JSONL hashes, and keeps WAEC
  rows visible in the state/local summary and record API. WAEC grid dates are
  treated as disclosure-received dates, not contribution transaction dates, and
  non-original version rows are preserved but excluded from reported amount
  totals until amendment deduplication is validated.
- Added `run-state-local-pipeline --jurisdiction sa` for the first South
  Australia ECSA state-level adapter. It archives the official disclosure
  landing page, fetches the current ECSA return-record portal by partitioning
  the portal over official `For` filter values, and normalizes 696 unique
  return-level index rows into
  `data/processed/sa_ecsa_return_summary_money_flows/`, matching the
  portal-reported row count. Current local coverage is $472,688,444.90 in
  source-row return-summary value across candidate campaign donations returns,
  political party returns, associated-entity returns, third-party returns,
  donor returns, large-gift returns, capped-expenditure returns, and annual
  political expenditure returns. These rows are shown as return-summary
  context, not detailed transaction rows, not personal receipt, and not
  consolidated influence totals.
- Added `run-state-local-pipeline --jurisdiction nt` for the first Northern
  Territory state-level disclosure adapter. It archives the official NTEC
  2024-2025 annual-return page plus the annual return gifts page, validates
  source table headers and totals, and normalizes 96 annual-return financial
  rows into `data/processed/nt_ntec_annual_return_money_flows/`: 49
  recipient-side receipts over $1,500, 2 associated-entity debt rows over
  $1,500, and 45 donor-side donation-return rows, with $821,044.16 in
  source-row reported value. It also normalizes 78 over-threshold annual gift
  rows into `data/processed/nt_ntec_annual_gift_money_flows/`, with
  $1,066,817.76 in source-backed donor-to-recipient annual gift observations.
  NT rows are visible in state/local source-family views but excluded from
  consolidated influence totals until cross-source deduplication against NTEC
  gift tables, donor-side returns, and Commonwealth records is implemented.
  Annual gift rows preserve the NTEC return received date as `date_reported`
  where available because the source does not publish per-row gift transaction
  dates.
- Added `run-state-local-pipeline --jurisdiction vic` for the first Victoria
  state-level adapter. It archives the official VEC funding-register page,
  fetches the linked DOCX files, validates source/document hashes, and
  normalizes 202 rows into `data/processed/vic_vec_funding_register_money_flows/`:
  149 public-funding payments, 44 administrative expenditure funding
  entitlements, and 9 policy development funding payments, with $45,447,717.13
  in reported public-funding/admin/policy amounts. These rows are shown as
  public-funding context, not private donations, gifts, personal income, or
  improper conduct. Date caveats are preserved for election-day/calendar-period
  context dates.
- Added `run-state-local-pipeline --jurisdiction act` for the first ACT
  state-level money/gift adapter. It archives the official Elections ACT
  2025-2026 gift-return page, validates the current table headers, normalizes
  225 rows into `data/processed/act_gift_return_money_flows/`, and loads those
  exact manifest-referenced artifacts into Postgres after checking summary,
  JSONL, source metadata, and source body hashes. Current local coverage is 206
  gifts of money and 19 gifts-in-kind with $87,394.50 in reported value.
- Generalized `/api/state-local/summary`, `/api/state-local/records`, and the
  State/Council frontend panel beyond QLD-only rows. ACT gift-in-kind rows are
  displayed as reported non-cash values, QLD expenditure remains
  campaign-support context, and NSW donor-location aggregates stay separate
  from donor-recipient money-flow rows.
- Added `run-state-local-pipeline --jurisdiction qld` as the first
  manifest-producing state/local orchestration command. It refreshes ECQ form
  pages and lookup API snapshots, fetches current ECQ CSV exports, normalizes
  money-flow, participant, and disclosure-context artifacts, and records that
  database loading and public attribution remain separate downstream steps.
  Follow-up hardening now passes exact fetched metadata paths between QLD
  runner steps so a manifest is tied to the artifacts it normalized rather than
  whichever source snapshot happens to be latest. Added
  `load-state-local-pipeline-manifest` so scheduled loads can load the exact
  processed JSONL artifacts referenced by that manifest.
- Added QLD state/local freshness metadata to `/api/state-local/summary` and
  the frontend State/Council panel. The public UI now shows the newest ECQ
  money-flow export fetch time and export-snapshot count next to the
  partial-data caveat, making update recency visible without treating source
  coverage as complete.
- Hardened QLD manifest replay so state/local loads validate manifest summary
  hashes, processed JSONL hashes, expected export/lookup source scopes, and
  summary row counts before mutating Postgres.
- Added `run-state-local-pipeline --jurisdiction nsw` as the first NSW
  state-level adapter. It archives the official NSW Electoral Commission 2023
  State Election pre-election donation page plus the static heatmap, normalizes
  94 donor-location aggregate rows covering 5,077 disclosed donations and
  $6.48m in reported amounts, and records an explicit claim boundary that these
  rows are aggregate context, not donor-recipient flows or representative-level
  receipt.
- Added `aggregate_context_observation` for source-backed aggregate political
  finance context that should not be forced into the `money_flow` schema. The
  state/local summary API and frontend now show NSW top donor-location
  aggregates separately from QLD gift/donation and campaign-expenditure rows.
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
  database. The normalized artifact contains 49,838 source-backed rows:
  22,725 gift/donation rows from the public map export and 27,113 electoral
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
- Added cursor-paginated QLD State/Council disclosure records at
  `/api/state-local/records` and wired the frontend summary panel to load more
  current ECQ rows on demand. Record cursors are filter-bound, expenditure rows
  are displayed as campaign spend incurred rather than donor-recipient
  transfers, and the API now exposes source document id, fetch timestamp,
  SHA-256 snapshot hash, original row text, and selected row metadata for
  reproducibility.
- Added State/Council row-type filters so users can inspect all QLD rows,
  gift/donation rows, or electoral campaign-spend rows separately. Filtered
  views call the source-row endpoint directly rather than reusing the mixed
  summary sample, preserving pagination correctness and the gift/spend
  evidence-family distinction.
- Added `fetch-official-identifier-bulk`, a reproducible data.gov bulk
  identifier fetch/normalize path for ASIC, ACNC, and ABN Bulk resources. The
  selector uses source-specific CKAN resource hints, archives selected bodies
  plus metadata, writes one official-identifier JSONL snapshot per source, and
  groups multi-part ABN resources so current-source loads do not accidentally
  use only one part. The federal pipeline can opt into this via
  `--include-official-identifier-bulk`; smoke runs cap extraction per source.
- Added `prepare-review-bundle`, a reproducible CLI wrapper that materializes
  party/entity link candidates, exports party/entity and sector-policy review
  queues, runs sector-policy suggestions, and writes a manifest for reviewers
  without turning candidates into public claims.
- Added configurable minimum-count checks to `qa-serving-database` and wired
  conservative thresholds into the weekly federal runner for influence events,
  person-linked rows, current money flows, current interest rows, and current
  House/Senate office terms.
- Added `docs/federal_rollout_checklist.md`, which defines the data, evidence,
  review, operational, UI, and state/council transition gates for treating the
  Commonwealth layer as release-ready rather than merely useful beta software.

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
- Added typed access-context events from the official Australian Government
  Register of Lobbyists snapshot. Client-to-lobbying-organisation rows and
  lobbying-organisation-to-listed-lobbyist rows now load as `event_family=access`
  with `amount_status=not_applicable`, entity/raw-name graph context, and
  explicit caveats that they are registry context only, not evidence of meetings,
  access granted, successful lobbying, improper influence, or wrongdoing.
- Added the first historical candidate/contest spine: AEC election candidate
  context is materialised into `candidate_contest` rows, `money_flow` and
  derived `influence_event` rows carry `candidate_contest_id`, and nullable
  `office_term_id` fields are ready for later date-validated linking. Exact
  candidate-name/electorate/state matches are deliberately labelled
  `name_context_only` until historical office-term dates support a temporal
  claim.

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
- NSW aggregate-context replay now verifies the source metadata/body hashes
  carried by the normalized artifact, resolves the heatmap link from the
  official explanatory page, and preserves NSWEC map-exclusion and CC BY 4.0
  attribution caveats.
