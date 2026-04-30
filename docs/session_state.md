# Session State (Where We Are / What's Next)

This file is the single source of truth for an editing-agent session that
needs to pick up where the previous one left off. Read this **before**
proposing a plan; it captures decisions, gotchas, and the current next
step that aren't necessarily obvious from `git log` or the build_log.

Last updated: **2026-04-30** (end of Batch D #1 — live AEC Register
pipeline run + verification landed in three commits).

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
  load now produces 87 unique reviewed `party_entity_link` rows (86 →
  ALP id=1, 1 → AG id=136), and `party_exposure_summary` surfaces non-
  empty for current ALP MPs (event_count 4,291, party-context total
  $310M, equal-share modelled per current rep ~$2.53M, denominator
  123). Direct-money invariant unchanged (314,040 events / $13.48B).
  315/315 backend pytest green. ruff clean. frontend build clean.

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

### Batch D #3 — frontend visual smoke (Firefox only)

Click through map → details panel → party profile → influence graph for
a few representative MPs. Confirm new party-exposure data renders
correctly post-Batch-C; confirm "Est. exposure" prefix is visible;
confirm denominator-asymmetry chip shows up; confirm council/state map
paths still work.

### Batch D #4 — pre-launch claim-discipline sweep

Grep frontend for UI text that could be misread as causal/wrongdoing
("received from", "took money from", "donated by … to", "improper",
"corrupt"). Replace with neutral evidence-tier language.

### Batch D #5 — methodology page

Render `docs/influence_network_model.md` +
`docs/campaign_support_attribution.md` + `docs/theory_of_influence.md`
as a public-facing methodology section with versioned permalinks.
Journalists/academics will look for this first.

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

## When you start: pick up at Batch D #1

The next thing to do is the live AEC Register pipeline run + verification
above. If the verification checklist passes cleanly, move to Batch D #2
(postcode crosswalk). If it surfaces a duplicate-party-row blocker,
spike a one-shot party-table dedup migration before continuing.

Do not stop at PR boundaries within Batch D to ask. Stop only on:
test failure, real ambiguity not in this file, destructive operation
needing approval, or external write needing approval.
