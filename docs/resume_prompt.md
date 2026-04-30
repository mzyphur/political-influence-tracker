# Resume Prompt (paste this into a fresh session after `/compact`)

> **Copy everything below the line into the next prompt.** It is intended
> to fully prime a fresh editing-agent session that has just been
> compacted, with no memory of the prior conversation. The session-state
> file in the repo is the canonical record; this prompt is the
> conversational entry point that points the agent at it and tells it to
> start working.

---

You are continuing work on the Australian Political Influence Transparency project at:

```
/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics
```

## Read these files first, in this order

1. `CLAUDE.md` — project operating mode for THIS repository. **It overrides** the global `~/CLAUDE.md`. Critical rule: zero prose between tool calls within a batch. Phase boundaries are not summary points. Status text is friction; the user will push back hard on drift.
2. `docs/session_state.md` — single source of truth for where we are. It contains:
   - Batches A → C completed (last commit `24970e8`).
   - Batch D items #1 to #5 in priority order, with verification checklists and known gotchas.
   - Critical project constraints (claim-discipline, no fuzzy resolver matching, conservative licence wording, AIMS coastline limits, lockfile policy, browser preference).
   - The exact CLI commands for each verification step.
3. `docs/influence_network_model.md` — methodology, especially the new "AEC Register of Entities as the Source-Backed Origin of party_entity_link" section and the "Denominator Asymmetry in equal_current_representative_share" section.
4. `docs/build_log.md` — most recent batch summaries, ordered newest-first.

## Project mission (one line)

Build a reproducible, source-backed Australian political influence transparency app, federal-first, that NEVER conflates direct disclosed person-level money with campaign-support records, party-mediated party/entity context, or modelled allocation. Every public claim must travel with its evidence tier and attribution limit.

## What just landed (Batches C + D — federal launch readiness)

- **Batch C — AEC Register of Entities ingestion** (commits `b9978b7`,
  `ba479c6`, `1e1fe0d`): fetcher with token redaction + cookie-value
  redaction + AEC field-typo preservation; deterministic branch
  resolver (no fuzzy similarity); loader with the dev's C-rule per
  client_type; schema 033; pipeline + `load_processed_artifacts`
  wiring; 55 backend tests covering fetcher / resolver / loader and a
  cross-cutting direct-money invariant.
- **Batch D #1 — live AEC Register run + dedup + disambiguation** (5
  commits `901c5c1` → `68c2e74`): fetcher metadata fix
  (`body_path`/`final_url`/`content_type`); deterministic
  source-jurisdiction disambiguation rule
  (`source_jurisdiction_disambiguation_v1`) added to the resolver
  with `jurisdiction_id` threaded into `PartyDirectory`; one-shot
  data-fix migration `034_consolidate_federal_party_duplicates.sql`
  consolidating eight federal short/long-form duplicate pairs into
  single canonical rows (state-jurisdiction rows untouched);
  reviewer-feedback fixes: `get_or_create_party` now uses
  `COALESCE(party.short_name, EXCLUDED.short_name)` so the curated
  `short_name='ALP'` etc. is not clobbered on next pipeline run;
  `_commonwealth_jurisdiction_id` raises on ambiguous seeds rather
  than silently picking lower id. Live DB: 87 unique reviewed
  `party_entity_link` rows (86 → ALP, 1 → AG); current ALP MPs now
  surface non-empty `party_exposure_summary` with event_count 4,291,
  party-context total $310M, equal-share modelled per current rep
  ~$2.53M, denominator 123. Direct-money invariant unchanged
  (314,040 events / $13.48B).
- **Batch D #2 — postcode crosswalk live verification** (commit
  `2aedaaa`): pipeline already wired; live re-fetch of 8 seed
  postcodes produced 9 crosswalk rows / 1 ambiguous postcode (2600
  ACT → Canberra + Bean) / 0 unresolved. Search API returns postcode
  results with full attribution caveat + boundary/current-member
  context labels + per-result confidence (0.5 ambiguous, 1.0
  unambiguous). No new code needed.
- **Batch D #3 — frontend visual smoke** (commit `4e516fd`):
  code-side audit confirmed no regressions in render paths
  (`Est. exposure` prefix, denominator-asymmetry chip, postcode
  result rendering, claim-discipline microcopy). Eyes-on Firefox
  smoke is human-side work the agent cannot perform; checklist for
  the user lives at `docs/batch_d3_firefox_smoke_checklist.md`.
- **Batch D #4 — claim-discipline sweep** (commit `2a14408`): grepped
  `frontend/src/` for causal/wrongdoing language. Found one outlier
  in `App.tsx:1678` where the NT annual-gift headline used the active
  "gave" verb while every other state/local headline used "disclosed"
  framing; replaced with `"${source} disclosed an annual gift to
  ${recipient}"` and added an inline comment. All remaining mentions
  of "improper" / "wrongdoing" / "causation" are in explicit negating
  positions, which is the framing the project requires.
- **Batch D #5 — methodology page** (commits `4a4f1af`, `d69405d`):
  extended `frontend/public/methodology.html` with three new
  sections — `#aec-register-pathways` (4-stage resolver including
  parenthetical short-form alias and source-jurisdiction
  disambiguation), `#equal-share` (numerator/denominator scope, Est.
  exposure UI rule), `#campaign-support-tiers` (link to
  `docs/campaign_support_attribution.md` per-tier rules); footer
  refreshed with the correct three source docs and a versioned
  internal-revision marker `2026-04-30 / 3f40524`. Reviewer-feedback
  fix: parenthetical-alias step added to the enumeration, and the
  permalink wording re-named to "internal revision marker" to stop
  overstating what the bare git SHA is.

## What's next

The federal-launch path is structurally complete. Suggested next
moves, in priority order:

1. **User runs the Firefox visual smoke** per
   `docs/batch_d3_firefox_smoke_checklist.md`. If anything regresses
   visually, log it and fix.
2. **Expand the postcode seed list.** `data/seeds/aec_postcode_search_seed.txt`
   currently has 8 bootstrap postcodes. Production refresh should
   cover at least every postcode that maps to a federal electorate
   (~3000+ Australian postcodes). The pipeline supports the
   expanded list out of the box; just feed a larger
   `--postcodes-file`.
3. **Methodology page link in the markdown footer.** The static page
   carries a `2026-04-30 / 3f40524` marker. When the project gets a
   public git mirror, wrap the marker in an `<a href="…/commit/3f40524">`
   so it becomes a real permalink.
4. **Source-licence capture.** The repo currently uses "official public
   AEC register; public redistribution/licence terms to be recorded
   before public data redistribution." Land verified terms before any
   public data redistribution.
5. **State/local expansion** (NSW/VIC after QLD). Deferred until after
   federal launch per the dev's standing direction; do NOT let
   state/local work delay the May 2026 federal release unless it
   exposes a reusable data-model flaw.

## Critical operating constraints (will be enforced; user has pushed back hard)

- **Zero prose between tool calls.** Status updates only at end-of-batch / test failure / blocker / design ambiguity not pre-specified.
- **Phase boundaries are not summary points.** Move from PR 1 → PR 2 → PR 3 → next batch without stopping for a nod.
- **Don't ask permission** for read/write/edit/test/lint/commit on this repo. The user has explicitly granted full autonomy. Per-action narration reads as permission-asking even when no question mark is present.
- **Never weaken the resolver into fuzzy matching.** No fuzzy similarity. Multi-row matches must fail closed.
- **Direct-money totals must be byte-identical** before/after any loader change that touches related paths. Existing test (`test_loader_does_not_change_direct_representative_money_totals`) guards this; extend the guard for new loaders.
- **Conservative source/licence wording.** Use "official public AEC register; public redistribution/licence terms to be recorded before public data redistribution." Do not promise reuse permission until terms are captured.
- **AIMS Australian coastline** is OK for local development; **not** cleared for public redistribution.
- **Browser**: Firefox or in-app browser; not Chrome.
- **Lockfile**: regenerate via `make lock` only; never hand-edit `backend/requirements.lock`.
- **Editing `~/.claude/`** still triggers a built-in harness "sensitive file" prompt by design. That is a separate protection layer from `substantive_write_guard.py`. Don't try to bypass it.
- **Inline `python3 -c` scripts are fragile under the hook**: if the script's source mentions `os.makedirs` / `os.remove` / `Path(...).write_text` etc. — even via an import — the hook will flag the bash invocation as a possible mutator. Prefer writing a small temp file and executing it, or skip the verification.

## Test commands (run when needed)

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics"

# Full backend test suite (Postgres integration enabled):
AUPOL_RUN_POSTGRES_INTEGRATION=1 \
DATABASE_URL_TEST=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \
backend/.venv/bin/pytest backend/tests/ -q

# Backend ruff:
backend/.venv/bin/ruff check backend/

# Frontend production build:
cd frontend && npm run build
```

## Now go

Batch D is closed. Pick whichever next-step item from the list above
is highest empirical value at the time you read this. If the user's
prompt directs you to a specific item, do that first. If you are
spinning up cold with no instruction, default to encouraging the user
to run the Firefox visual smoke (item #1) before any other work, since
no agent can do that and a regression there blocks public launch.

Update `docs/session_state.md` and `docs/build_log.md` whenever a
new batch or task closes. If anything in `docs/session_state.md`
contradicts this prompt, **trust `docs/session_state.md`** — it's
the authoritative record.
