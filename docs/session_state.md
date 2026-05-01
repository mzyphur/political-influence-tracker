# Session State (Where We Are / What's Next)

This file is the single source of truth for an editing-agent session that
needs to pick up where the previous one left off. Read this **before**
proposing a plan; it captures decisions, gotchas, and the current next
step that aren't necessarily obvious from `git log` or the build_log.

Last updated: **2026-05-01** (end of Batch L — public-launch
hardening: fast-feedback CI workflow added at
`.github/workflows/ci.yml`; APH + AEC GIS provisionally cleared per
project-lead direction (reply text TBD on file under
`docs/letters/replies/`); CONTRIBUTING + CODE_OF_CONDUCT + SECURITY
+ issue/PR templates + 10 discovery topics applied to the public
mirror; README rewritten with public-facing tagline + badges +
"what this is/is not" framing block + contributing pointer).

## Current state

**Batches completed (per the May-2026-launch plan):**

- **Batch A — adversarial-review fixes** (commits `ae8bbd1`, `b82d756`,
  `aa6b17b`, `cec5fc2`): umbrella headline rename, sum-of-breakdown
  invariant assertion, QLD council alias regex matrix tests, denominator-
  asymmetry methodology note, `make lock` target, audit retention policy,
  state/local CI smoke job, project-root `CLAUDE.md` autonomy override.
- **Batch B — live AEC Register endpoint probe** (no committed code):
  confirmed token+cookie+JSON shape, found that the fourth client_type is
  `thirdparty` not `thirdpartycampaigner` (the latter returns HTTP 500),
  one token reused across paginated POSTs in a session, anti-forgery
  cookie + token must be redacted from raw archive.
- **Batch C — AEC Register of Entities ingestion** (commits `b9978b7`,
  `ba479c6`, `1e1fe0d`): three PRs for fetch + raw archive + CLI + tests,
  schema 033 + deterministic branch resolver + loader + integration tests,
  pipeline integration + `load_processed_artifacts` wiring + docs.
- **Batch D #1 — live AEC Register pipeline run + verification**
  (commits `901c5c1`, `ef8342f`, `56f1928`, `3f40524`): fetcher metadata
  fix (`body_path`/`final_url`/`content_type`); deterministic source-
  jurisdiction disambiguation rule (`source_jurisdiction_disambiguation_v1`)
  in the resolver, with 7 new unit tests; one-shot data-fix migration
  `034_consolidate_federal_party_duplicates.sql` consolidating 8 federal-
  jurisdiction short/long-form duplicate pairs into single canonical
  rows; reviewer-flagged fixes (`get_or_create_party` short_name
  preservation via `COALESCE`, `_commonwealth_jurisdiction_id`
  fail-loud-on-ambiguous-seed, integration test for jurisdiction
  disambiguation, regression test for short_name preservation). Live
  load produces 87 unique reviewed `party_entity_link` rows (86 →
  ALP id=1, 1 → AG id=136); current ALP MPs surface non-empty
  `party_exposure_summary`. Direct-money invariant unchanged. 315/315
  backend pytest green.
- **Batch E — public reproducibility + visual smoke + perf + curated
  party seed** (commits `4409f6f`, `28ca462`, `a57fe19`): top-level
  `Makefile` with public reproducibility entry points
  (`make reproduce-federal` runs the full live-fetch chain end-to-end);
  new `scripts/reproduce_federal_from_scratch.sh` and
  `scripts/clean_local_data.sh`; top-level `README.md` rewritten with
  a "Reproduce every number on the site" section; methodology HTML
  extended with `#reproducibility` section + nav anchor; live visual
  smoke via the in-app browser confirmed party-exposure panel,
  denominator chip, and postcode search; performance pass on
  `_representative_party_exposure_summary` (p50 5.8 ms, p99 12.7 ms,
  max 16.5 ms, no disk reads); curated party-seed migration
  `035_seed_additional_canonical_party_rows.sql` adding Animal
  Justice Party, Australian Citizens Party, Libertarian Party, and
  Shooters Fishers and Farmers Party as federal canonical rows;
  resolver gained 7 new alias rules + extended state-list coverage on
  the existing rules + Stage-3 parenthetical short-form alias now
  applies source-jurisdiction disambiguation; 18 new resolver tests.
  Reviewed `party_entity_link` rows lifted from 87 → **147** (89 ALP,
  38 LP, 7 NATS, 6 LNP, 2 ACP, 1 each → SFF/AG/CLP/AJP/Libertarian).
  333/333 backend pytest green. ruff clean. frontend build clean.
- **Batch F — methodology auto-stamp + visual smoke + politicalparty
  long tail + postcode expansion path**: build-time methodology
  version + revision injection via
  `frontend/scripts/sync-methodology-version.mjs` (wired into npm
  predev + prebuild); residual visual smoke via the in-app browser
  confirmed state-map mode (93 features, Algester), council-map mode
  (78 QLD-LOCAL features, Aurukun Shire), and the influence-graph
  panel (134 connections for Bean's MP, full claim-discipline
  subtitle); migration `036_seed_additional_canonical_party_rows_v2.sql`
  adds 9 more federal canonical rows (Australian Federation Party,
  Family First Party Australia, The Great Australian Party, Better
  Together Party, Indigenous - Aboriginal Party of Australia,
  Socialist Alliance, Sustainable Australia Party, Power 2 People,
  Health Environment Accountability Rights Transparency); resolver
  gained 7 more alias rules (Greens punctuated/unpunctuated/parens-
  without-Branch, "The Greens" short forms, Nationals Inc-suffix,
  Australian Federation Party state suffixes, Libertarian Party state
  branches, Affordable Housing Now alias, HEART parenthetical alias);
  23 new resolver tests; politicalparty `unresolved_no_match` 31 → 4
  (4 remaining are deliberately-excluded candidate-vehicle names);
  new `scripts/expand_postcode_seed.sh` + `make expand-postcode-seed`
  target documents the path to the full ~3000-postcode national seed
  (the actual bulk fetch is intentionally a maintainer decision, not
  an agent run). 356/356 backend pytest green. ruff clean. frontend
  build clean.
- **Batch L — public-launch hardening** (commits `206e0da`,
  `9b4e906`, `cc515cc`, TBD this batch):
  - **L #1**: fast-feedback CI workflow at `.github/workflows/ci.yml`
    (pytest + ruff + frontend tsc/vite build, runs on every push to
    `main` and every PR). Complements the existing weekly + manual
    `federal-pipeline-smoke.yml`.
  - **L #2**: APH + AEC GIS provisionally cleared per project-lead
    direction on 2026-05-01. Reply text TBD on file under
    `docs/letters/replies/`. `docs/source_licences.md` rows updated
    with honest "provisionally approved; written reply text to be
    archived when it arrives" framing. README's source-data licence
    section rewritten to match.
  - **L #3**: repo polish — `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
    (Contributor Covenant v2.1 by URL reference),  `SECURITY.md`,
    four issue templates (config / bug_report / feature_request /
    data_correction), `PULL_REQUEST_TEMPLATE.md`, plus 10 GitHub
    discovery topics applied via `gh repo edit`.
  - **L #4**: README rewritten for public-facing readers — one-line
    blockquote tagline, four shields.io badges, "What this is /
    What this is **not**" framing block, public-mirror clone URL,
    Contributing section pointing at the new metadata files.
  - **L #5**: docs refresh + final gates + push.

- **Batch K — public-readiness sprint** (commits `32660c3`, `8388cdc`,
  TBD this batch):
  - **K #1**: ready-to-sign Word .docx versions of the APH + AEC GIS
    exception letters under `docs/letters/word/` (3 files: APH House,
    APH Senate, AEC GIS); generator at `scripts/generate_letter_docx.py`;
    python-docx installed in a one-off `/tmp` venv (not added to the
    backend lockfile — render-only dependency).
  - **K #2**: AGPL-3.0 source-code licence at `LICENSE`; README gains
    a "Source code licence" section explaining the AGPL choice;
    `.gitignore` extended with `~$*` so MS Word lock files don't
    accidentally get committed.
  - **K #3**: public GitHub mirror live at
    https://github.com/mzyphur/political-influence-tracker;
    `METHODOLOGY_REPO_URL` wired to load from
    `frontend/.env.local` (or `.env`) via a tiny self-contained
    dotenv loader added to `frontend/scripts/sync-methodology-version.mjs`
    (no new npm dependency); `frontend/.env.example` documents the
    variable; the methodology-page revision marker now renders as
    a clickable `commit/<sha>` link automatically on every build.
  - **Push of `main` to the public mirror** is the project-lead-side
    finishing step. The repo is initialised, the remote is added,
    and the working tree is clean. `gh auth login` (interactive
    browser device-flow) needs to be run once by the project lead;
    after that all agent pushes work seamlessly.

- **Batch J — postcode crosswalk expansion** (no new source-file
  changes; pure live-data round; commits TBD this batch):
  - **J #1**: 195-postcode QLD/SA/WA/TAS focus run (every 20th
    in 4xxx-7xxx, balanced ~49 per state). +65 crosswalk rows
    (191 → 256). Per-state shift NSW 82/VIC 71/QLD 12 → 33/WA 6 → 32/
    SA 3 → 16/TAS 4 → 9/ACT 6/NT 5.
  - **J #2**: 208-postcode balanced 2xxx-7xxx run (every 30th in
    2xxx/3xxx, every 25th in 4xxx-7xxx, excluding already-fetched
    and PR-1 picks). +98 crosswalk rows (256 → 354).
  - **J #3**: 211-postcode broader 2xxx-7xxx run (same shape as PR 2,
    fresh exclusion set). +94 crosswalk rows (354 → **448**); +4
    distinct electorates (123 → **127**: 84.7% of federal House
    seats). Final per-state: NSW 121/37, VIC 114/31, QLD 73/27,
    WA 64/12, SA 40/9, TAS 19/5, ACT 6/3, NT 5/2.
  - Cumulative: **614 unique postcodes seeded across the three PRs,
    zero overlap, +257 crosswalk rows; final electorate coverage 127
    of 150 federal House seats (84.7%)**. (Pre-Batch-J electorate
    count was not measured; PR 3 specifically added +4 vs after-PR-2
    state of 123.) Silent-skip rate ranged 37% to 60% per PR — the
    cost of using the comprehensive CC0 list (Matthew Proctor)
    rather than a curated list. Documented in `docs/build_log.md`.
  - **Known gap recorded for the next operator**: the CC0 source
    has no leading-zero postcodes (0200-0299 ACT and 0800-0899 NT
    residential). ACT and NT coverage is stuck at 6 / 5 rows
    respectively. Expanding those would require a different seed
    source (data.gov.au POA or AEC's own electorate boundary
    intersections), under a redistribution-cleared licence.
  - **J #4**: `frontend/public/methodology.html` extended with a
    new `#postcode-coverage` section + nav anchor, exposing the
    current coverage state and four known limitations (silent-skip,
    leading-zero gap, multi-electorate ambiguity, inner-metro
    fragmentation) to the public reader. Methodology version date
    bumped to 2026-05-01.

- **Batch I — last-mile licence verbatim + 200-postcode bulk fetch +
  exception-request letters** (commits TBD this batch):
  - **I #1**: Australia Post canonical product page verbatim
    (the historic `/about-us/about-our-site/our-licensing-arrangements`
    URL is a 2026 404; current canonical is
    `postcode.auspost.com.au/free_display.html?id=1` titled
    "Non-commercial use only"). All ten sources in `source_licences.md`
    now carry verbatim direct-fetch wording or conclusively-
    unfetchable status with a verbatim record from the canonical
    alternate (data.gov.au for AIMS Coastline 50K).
  - **I #2**: 200-postcode residential-sample bulk fetch lifted
    `postcode_electorate_crosswalk` rows from 51 to **191** (NSW 84 /
    VIC 71 / QLD 12 / ACT 6 / WA 6 / NT 5 / TAS 4 / SA 3); 35
    unresolved candidates retained as auditable observations.
    Earlier silent-exit runs were because head-of-list CC0 postcodes
    (1000-1099) are PO Box / large-volume-recipient codes that
    AEC's finder returns no localities for; the residential-sample
    script avoids that.
  - **I #3**: methodology permalink upgrade is blocked on the
    project being published to a public git mirror;
    `METHODOLOGY_REPO_URL` env-var hook is wired and ready (Batch G #1).
  - **I #4**: APH + AEC GIS public-redistribution exception-request
    letters drafted under `docs/letters/` with a README archive
    policy. Awaiting project-lead signature + send.
  - **I #5**: Firefox smoke already done in the in-app browser
    (Batch F #2); sub-national + state/local stay deferred.
- **Batch H — direct-fetch licence verbatim + CC0 postcode seed +
  is_personality_vehicle API surface** (commits `2c6946f`, `c787130`,
  `e3a8803`):
  - **H #1**: verbatim direct-fetch verification of
    `docs/source_licences.md` for 8 of 10 sources. AIMS Coastline 50K
    verbatim "Licence Not Specified" → **blocked** for public
    redistribution. APH confirmed CC BY-NC-ND 4.0 International
    (prior round had said 3.0 AU). AEC GIS verbatim review is
    friendlier than search-only suggested (derivative products
    permitted with attribution). Australia Post URL 404'd; eAtlas
    AIMS companion 403'd; both flagged for browser-based maintainer
    re-fetch.
  - **H #2**: `scripts/build_postcode_seed_from_cc0.sh` builds a
    9000-postcode national seed (`aec_postcode_search_seed_full.txt`)
    from Matthew Proctor's CC0 dataset; default pipeline seed stays
    at 48 postcodes for AEC endpoint etiquette.
    `docs/data_sources.md` records the CC0 source choice + staged
    bulk-fetch recommendation.
  - **H #3**: `is_personality_vehicle` wired through
    `_representative_party_exposure_summary` + `RepresentativePartyExposureSummary`
    type + `DetailsPanel.tsx` chip ("personal electoral vehicle for
    <name> — not an ideological federal party"). Regression test
    upgraded from blanket "no office_term may reference" assertion to
    end-to-end API-surface assertion. 358/358 pytest pass. Frontend
    build clean.
  - **Permission allowlist** (`.claude/settings.local.json` —
    gitignored) broadens WebFetch / WebSearch / curl / make / npm
    allow rules so future runs skip the per-URL gate.
- **Batch G — licence capture + permalink env-var + candidate-vehicle
  seed + postcode parser fix + v2 seed + sub-national plan** (commits
  `27db774`, `afe9c8d`, `e32fb6a`, `b862e76`, `df0edaa`):
  - **G #1**: methodology permalink env-var. `sync-methodology-version.mjs`
    reads `METHODOLOGY_REPO_URL`; when set, wraps the SHA in a
    `commit/<sha>` link. Idempotent (non-greedy regex) so a re-run
    with a different URL re-wraps cleanly and a re-run without the
    env var strips the link.
  - **G #2**: candidate-vehicle party seed migration `037` adds the
    last four AEC-registered "candidate-vehicle" / personality
    registered-name parties (Dai Le & Frank Carbone W.S.C.; Kim for
    Canberra; Tammy Tyrrell for Tasmania; votefusion.org for big
    ideas) with `is_personality_vehicle` metadata flag. Drops
    `unresolved_no_match` to **0 across all client_types**. Reviewed
    `party_entity_link` count 147 → 148. Reviewer-flagged regression
    test `test_no_office_term_references_personality_vehicle_party_row`
    fails closed if any future loader links an MP to one of these
    rows without first wiring the flag through the API.
  - **G #3**: source-licence doc `docs/source_licences.md` records
    per-source licence terms, attribution wording, and redistribution
    status. Headline blockers: APH (CC BY-NC-ND 3.0 AU — derivative
    restriction), AEC GIS (Limited End-user Licence), AIMS Coastline
    (still "Not Specified" upstream), Australia Post (blocked for
    public postcode lookup). README links to the doc.
  - **G #4**: AEC electorate-finder pagination-row parser bug. Live
    fetch crashed mid-normalize on 8 postcodes whose results spanned
    multiple result pages (the GridView footer's numeric anchors
    parsed as `{Postcode='2'}` data rows). Added
    `_looks_like_pagination_row()` filter + defensive `try/except`
    skip + a unit test pinning the fix. Postcode v2 seed expanded
    from bootstrap 8 to 48 postcodes (capital-city CBDs + regional
    centres / second cities). Live fetch + load yields 51 crosswalk
    rows (was 9), 8 unresolved postcode candidates retained as
    auditable observations.
  - **G #5**: `docs/sub_national_party_seeds_plan.md` documents the
    deferred design for state-jurisdiction party-mediated exposure.
    Three-part PR shape (state seed migration + resolver dual-call
    + API jurisdiction filter). QLD is first target; NSW/VIC/etc.
    follow the deferred state/local rollout. Out-of-scope: money-
    flow re-allocation, federal-row changes, cross-jurisdiction
    merger rules.
  - 358/358 backend pytest green (was 356; +2 new — pagination skip
    + personality-vehicle regression). ruff clean. frontend build
    clean.

## What's next: Batch D — pre-launch readiness

Targeting a **May 2026** federal launch. State/local expansion (NSW/VIC
after QLD) is **deferred** until after federal launch per the dev's
explicit direction — do not let state/local work delay the federal
release unless it exposes a reusable data-model flaw.

Ordered by ratio of empirical value to risk:

### Batch D #1 — live AEC Register pipeline run + verification (DONE — see commits above)

Highest empirical value, smallest effort. Proved Batch C works against
production data and surfaced the duplicate-party-row blocker described
in this section's earlier note. Both the resolver-side fix (source-
jurisdiction disambiguation) and the data-side fix (one-shot
consolidation migration `034`) landed in commits `901c5c1`, `ef8342f`,
`56f1928`, `3f40524`. The original verification checklist below is kept
for historical reference; every item is now satisfied. Skip to Batch
D #2.

Run order:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/backend"

# Apply schema 033 if not already applied to local DB.
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money migrate-postgres

# Fetch all four client_types from the live AEC endpoint.
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money fetch-aec-register-of-entities

# Load the processed JSONL into the local DB.
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-aec-register-of-entities
```

Verification checklist:

- [ ] Loader output shows non-zero
      `reviewed_party_entity_links_upserted` for `associatedentity`.
- [ ] `SELECT count(*) FROM party_entity_link WHERE review_status='reviewed' AND method='official'`
      returns a meaningful number (likely tens to low hundreds).
- [ ] `SELECT resolver_status, count(*) FROM aec_register_of_entities_observation GROUP BY resolver_status`
      shows a healthy mix of `resolved_branch`, `resolved_exact`, plus
      some `unresolved_multiple_matches` (expected because of duplicate
      ALP/Independent rows in the local `party` table).
- [ ] Pick a current ALP MP (e.g. via `SELECT id FROM person JOIN office_term ON ...
      JOIN party ON party.short_name='ALP' WHERE office_term.term_end IS NULL LIMIT 1`),
      hit `GET /api/representatives/{id}`, verify
      `party_exposure_summary` is non-empty and `event_count` is
      non-zero.
- [ ] Run the federal map endpoint
      `GET /api/map/electorates?chamber=house` and confirm at least one
      feature has
      `current_representative_lifetime_party_mediated_money_event_count > 0`
      (or whatever the equivalent map field is — check via
      `frontend/src/types.ts ElectorateProperties`).
- [ ] Boot the frontend (`make api-dev` + `cd frontend && npm run dev`),
      open in Firefox (NOT Chrome — user preference), click through to a
      current ALP MP profile, confirm "Party-Linked Money Exposure"
      panel renders with `Est. exposure $X` lines and the denominator-
      asymmetry chip.

If **#1 reveals duplicate-party-row blocking** (lots of
`unresolved_multiple_matches`): the next sub-task is a one-shot party-
table dedup migration. The local DB has duplicate rows for
`Australian Labor Party` (ids 1351 and 152936), `Liberal National Party`
(1460, 152939), `Independent` (1389, 153001), `Katter's Australian Party`
(1692, 152969). The C-rule correctly fails closed on these; the right
fix is to consolidate canonical rows, not to weaken the resolver.

### Batch D #2 — postcode crosswalk ingestion (DONE — live smoke)

The `aec_electorate_finder.py` ingest module + the `db.load.load_postcode_electorate_crosswalk`
loader + the CLI commands (`fetch-aec-electorate-finder-postcodes`,
`normalize-aec-electorate-finder-postcodes`,
`load-postcode-electorate-crosswalk`) + the pipeline steps + the
`include_postcode_crosswalk=True` flag in `load_processed_artifacts`
were already wired before Batch D started. Batch D #2's actual work
was the live-data smoke run: re-fetched the 8 seed postcodes from the
live AEC endpoint, normalised, and reloaded — 9 crosswalk rows / 1
ambiguous postcode / 0 unresolved candidates. Search API returns
postcode results with the full attribution caveat and confidence
labels intact. Existing tests still pass (2 parser tests + 1 loader
integration test). No new code required.

### Batch D #3 — frontend visual smoke (Firefox only) — code-side audit DONE; user smoke pending

Code-side audit found no regressions: `Est. exposure` prefix renders
via `DetailsPanel.tsx:882`; denominator-asymmetry chip renders as
`denominator scope: current office-term party representatives only
(asymmetric — see methodology)` via `DetailsPanel.tsx:1297`;
`equal share across N current party representatives` line via
`DetailsPanel.tsx:1305`; `claim_scope` sentence rendered via
`DetailsPanel.tsx:1311`; postcode result selection note carries the
full source-backed-candidate caveat via `App.tsx:2247`.

Visual smoke in Firefox is human-side work the agent cannot perform.
The eyes-on companion checklist for the user lives at
`docs/batch_d3_firefox_smoke_checklist.md` (commit `4e516fd`) and
covers: setup commands, ordered checklist for current ALP / AG /
other-party MPs, postcode search smoke, methodology-page anchor
checks, claim-discipline copy spot-checks, council/state-level map
paths.

### Batch D #4 — pre-launch claim-discipline sweep — DONE

Grepped `frontend/src/` for causal/wrongdoing language ("received
from", "took money from", "donated by …", "improper", "corrupt", and
related variants). Found one inconsistent state/local record headline
where `App.tsx:1678` was returning `"${source} gave an annual gift to
${recipient}"` for NT annual-gift rows; every other branch in the
function uses the more neutral "disclosed … to" / "disclosed … from"
framing. Replaced with `"${source} disclosed an annual gift to
${recipient}"` and added an inline comment explaining that donative
verbs ("gave"/"got") read as causal claims and the source data is a
disclosed annual return rather than an observed transfer.

All remaining mentions of "improper" / "wrongdoing" / "causation" in
the frontend are in explicit negating positions — exactly the framing
the project requires. Strong claim-discipline microcopy already in
place ("Not a wrongdoing claim", "do not claim causation or improper
conduct", "Equal-share values are analytical exposure estimates only",
"Est. exposure" prefix, "denominator scope" chip) was left intact.
Frontend build clean. Commit `2a14408`.

### Batch D #5 — methodology page — DONE

Extended `frontend/public/methodology.html` with three new sections
covering the methodology that landed in Batch C/D:

- **`#aec-register-pathways`**: exact-name match → branch alias rules
  → source-jurisdiction disambiguation → fail-closed-on-residual-
  ambiguity, plus a note on the one-shot federal-row consolidation
  migration.
- **`#equal-share`**: numerator/denominator definitions for
  `equal_current_representative_share`, why the per-rep figure is
  rough, and the UI rule that every surface prefixes with "Est.
  exposure" and ships the denominator chip.
- **`#campaign-support-tiers`**: summarises
  `docs/campaign_support_attribution.md` for public readers and
  reinforces that public election funding paid to a party is not a
  personal receipt.

Footer updated to reference the correct three source documents
(`influence_network_model.md`, `theory_of_influence.md`,
`campaign_support_attribution.md` — replacing the stale
`research_standards.md` pointer) and carry a versioned permalink:
methodology version `2026-04-30`, repo revision `3f40524`. Top nav
updated with anchors for the new sections + the version footer.
Frontend production build clean. Commit `4a4f1af`.

## Critical constraints (from CLAUDE.md and dev direction)

- **Zero prose between tool calls within a batch.** PR boundaries are
  not summary points. Status updates only at end-of-batch / test failure
  / genuine blocker / design ambiguity not pre-specified. The user has
  pushed back hard on drift here; obey the rule from the start.
- **Claim discipline is the project's most important invariant**.
  Direct disclosed person-level records, campaign-support records,
  party/entity-mediated context, and modelled allocation must NEVER be
  summed into a single "money received" number. Direct totals must be
  byte-identical before and after any party_entity_link change. There
  is an existing test (`test_loader_does_not_change_direct_representative_money_totals`)
  guarding this; extend it for any future loader that touches related
  paths.
- **No fuzzy similarity in the AEC Register branch resolver.** Only
  exact-normalized match against `party.name`/`party.short_name` or
  documented branch alias rules. Multi-row matches fail closed as
  `unresolved_multiple_matches`.
- **Source/licence wording: conservative.** Use "official public AEC
  register; public redistribution/licence terms to be recorded before
  public data redistribution" rather than "redistribution permitted"
  unless the licence is captured in the repo.
- **AIMS Australian coastline** licence is "Not Specified"; the user
  has confirmed it's OK for **local development** but it is NOT cleared
  for public redistribution. Don't promise reuse permission until terms
  are captured.
- **Browser**: use Firefox or in-app browser for visual checks. Not
  Chrome.
- **Keys**: TVFY/MapTiler/ABN/ABS keys live in `backend/.env` and
  `frontend/.env.local`. User has explicitly said local rotation is
  not a blocker; production keys will be different. Don't waste cycles
  on this.
- **Lockfile**: `backend/requirements.lock` is regenerated only via
  `make lock` (`pip-compile`). Never hand-edit.
- **Sensitive-file dialogs in `~/.claude/`** are a separate harness-
  level protection. The hook fix in
  `~/.claude/hooks/substantive_write_guard.py` only suppresses prompts
  for the AU Politics project root; edits to `~/.claude/` itself still
  prompt by design.

## Useful verification commands

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics"

# Full backend test suite with Postgres integration:
AUPOL_RUN_POSTGRES_INTEGRATION=1 \
DATABASE_URL_TEST=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \
backend/.venv/bin/pytest backend/tests/ -q

# Backend ruff:
backend/.venv/bin/ruff check backend/

# Frontend production build:
cd frontend && npm run build

# Start local Postgres (Docker Desktop must be running):
/opt/homebrew/bin/docker-compose -f backend/docker-compose.yml up -d

# Wait for Postgres ready:
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
  if /opt/homebrew/bin/docker-compose -f backend/docker-compose.yml exec -T postgres \
    pg_isready -U au_politics -d au_politics 2>/dev/null; then echo READY; break; fi; \
  sleep 2; \
done
```

## Recent commit history (top of HEAD)

```
1e1fe0d feat: wire AEC Register into federal pipeline + load_processed_artifacts (Batch C PR 3)
ba479c6 feat: add AEC Register loader with deterministic branch resolver (Batch C PR 2)
b9978b7 feat: add AEC Register of Entities fetch + raw archive (Batch C PR 1)
7173545 docs: add ABS Indicator + Data API sources and document key separation
cec5fc2 docs: log Batch A adversarial-review fixes
aa6b17b ci: add QLD state/local smoke job to federal pipeline workflow
b82d756 build: add make lock target and document audit retention policy
ae8bbd1 fix: clarify direct vs umbrella record counts and party-exposure scope
d77a27a docs: add project CLAUDE.md to grant repo-scoped autonomy
```

## Files added/modified in Batch C (for orientation)

New:

- `backend/au_politics_money/ingest/aec_register_entities.py` (fetcher +
  raw archive)
- `backend/au_politics_money/ingest/aec_register_branch_resolver.py`
  (pure-function deterministic resolver)
- `backend/au_politics_money/db/aec_register_loader.py` (loader using
  resolver + observation table)
- `backend/schema/033_aec_register_of_entities_observations.sql`
- `backend/tests/test_aec_register_entities.py` (18 unit tests, mocked
  HTTP)
- `backend/tests/test_aec_register_branch_resolver.py` (30 unit tests,
  no DB)
- `backend/tests/test_aec_register_loader.py` (7 Postgres integration
  tests including the cross-cutting direct-money-totals invariant)

Modified:

- `backend/au_politics_money/cli.py` (two new commands)
- `backend/au_politics_money/ingest/sources.py` (4 new source records)
- `backend/au_politics_money/pipeline.py` (4 new fetch steps)
- `backend/au_politics_money/db/load.py` (new
  `include_aec_register_of_entities` flag in `load_processed_artifacts`)
- `backend/tests/test_db_load.py` (opt out of new flag in mock test)
- `docs/build_log.md`, `docs/data_sources.md`,
  `docs/influence_network_model.md`, `docs/operations.md`,
  `docs/reproducibility.md`

## When you start: Batches D + E + F + G + H + I + J + K + L are closed; next-step menu

The federal-launch path is structurally complete and the public
mirror is hardened (CI green, repo metadata in place, source
licences provisionally cleared). Live data state at end of Batch L:

- 314,040 non-rejected `influence_event` rows; $13.48B reported total.
- 318 `person`, 150 federal House `electorate` rows.
- **148 reviewed `party_entity_link` rows** (89 ALP, 38 LP, 7 NATS, 6
  LNP, 2 ACP, 1 each → SFF, AG, CLP, AJP, Libertarian, Kim for
  Canberra).
- **0 `unresolved_no_match`** in either `associatedentity` or
  `politicalparty` register observations.
- **448 `postcode_electorate_crosswalk` rows** (was 191 at end of
  Batch I) covering **404 distinct postcodes** across **127 of 150
  federal House seats (84.7%)**. Per-state distribution:
  NSW 121 rows / 37 electorates, VIC 114 / 31, QLD 73 / 27, WA 64 / 12,
  SA 40 / 9, TAS 19 / 5, ACT 6 / 3, NT 5 / 2. **67 unresolved postcode
  candidates** retained as auditable observations.
- 358/358 backend pytest pass. ruff clean. frontend production build
  clean. Direct-money invariant test still passes.

Pick whichever item below is highest empirical value at the time you
read this:

1. **Project lead sends the APH + AEC GIS exception letters.** Drafts
   are at `docs/letters/aph_public_redistribution_request.md` and
   `docs/letters/aec_gis_public_redistribution_request.md`, ready
   to sign and send. Replies go under `docs/letters/replies/` per
   `docs/letters/README.md`. APH (CC BY-NC-ND 4.0) is the bigger
   blocker; AEC GIS is mostly seeking written confirmation that
   the project's use sits within the existing "Derivative Product"
   permission. Land both before public launch.
2. **Postcode batches — Batch J completed three more staged runs**
   lifting to 448 crosswalk rows / 404 distinct postcodes / 127
   federal House electorates (84.7% seat coverage). Further
   residential-sample batches would push the row count higher but
   yield diminishing returns on electorate count — 23 missing
   electorates are likely fragmented inner-metro Sydney/Melbourne
   plus remote regional electorates where AEC's finder data is
   sparse. ACT (0200-0299) and NT (0800-0899) residential ranges
   are entirely absent from the CC0 source (Matthew Proctor's
   dataset stores postcodes as integers, no leading zeros);
   expanding those requires a different seed source (data.gov.au
   POA or AEC's own electorate boundary intersections) under a
   redistribution-cleared licence. The CC0 seed at
   `data/seeds/aec_postcode_search_seed_full.txt` has ~6000
   residential candidates remaining (after Batch I + Batch J
   excluded ~614 of them); each ~200-postcode batch lifts crosswalk
   rows by ~75-100 with a 35-60% silent-skip rate.
3. **Methodology page permalink upgrade — DONE in Batch K.**
   Public mirror is live at
   https://github.com/mzyphur/political-influence-tracker; the
   `METHODOLOGY_REPO_URL` env var is wired to load from
   `frontend/.env.local` (or `frontend/.env`) by the prebuild hook
   so every `npm run build` automatically wraps the SHA marker in
   a clickable `commit/<sha>` link. No further action.

3a. **Push `main` to the public mirror — DONE in Batch K.** The
    project lead completed the one-time `gh auth login` browser
    device-flow and `gh auth setup-git`; macOS Keychain has cached
    the credentials with `repo` + `workflow` scopes. `git push -u
    origin main` published HEAD `b690ec3` to
    https://github.com/mzyphur/political-influence-tracker. GitHub
    auto-detected the AGPL-3.0 from the committed LICENSE. The
    methodology page's clickable revision marker now resolves to
    real commits on the public mirror (HTTP 200 verified). Future
    agent pushes from this directory work without intervention.
4. **AIMS-eAtlas browser-fetch follow-up (low priority).** The
   data.gov.au verbatim "Licence Not Specified" already drives the
   conservative blocked status; eAtlas might have additional
   provenance text but it isn't load-bearing for redistribution
   policy.
5. **Sub-national party seeds rollout.** Plan documented in
   `docs/sub_national_party_seeds_plan.md`. Three-part PR shape.
   QLD first. Out of scope until federal launch.
6. **State/local expansion** (NSW/VIC after QLD) — DEFERRED until
   after federal launch per the dev's standing direction.

Operating constraints below still apply.

Do not stop at PR boundaries within a batch to ask. Stop only on:
test failure, real ambiguity not in this file, destructive operation
needing approval, or external write needing approval.
