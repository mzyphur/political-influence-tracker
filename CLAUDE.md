# AU Politics — Project Operating Mode

This file overrides the global `~/CLAUDE.md` for this repository only.

## Autonomy

The user has explicitly granted full read/write/edit autonomy on this
repository. Within the scope of any agreed plan or approved batch of work,
take the lead and proceed without per-file or per-action approval.

- Do NOT narrate "now editing X" / "next I'll do Y" / "moving to Z" between
  tool calls. Just execute.
- Do NOT acknowledge permission grants ("taking the lead", "approved", etc.).
- Do NOT ask "should I proceed?" or "want me to continue?" mid-batch.
- Do NOT print pre-flight summaries before every edit.
### The hard rule on prose between tool calls

**ZERO prose between tool calls within a batch.** No "X done", no "moving to
Y", no "tests passed", no "committing now", no "continuing to PR N". The user
sees tool calls in real time and gets notified; status text is friction and
the user has explicitly asked it to stop.

Prose is allowed at exactly two points:

1. **End of an agreed batch** (Batch A finished, Batch B finished, etc.) —
   one consolidated summary.
2. **Real blockers** — a test failure I cannot fix without input, a design
   ambiguity not pre-specified, an external write or destructive operation
   that needs approval.

PR boundaries WITHIN a batch are NOT summary points. Test runs that pass
are NOT summary points. Single-finding completions inside a multi-finding
batch are NOT summary points. Commits that are part of a planned sequence
are NOT summary points.

If I find myself about to type "X done" or "Y next" between tool calls, do
not type it. Just make the next tool call.

### Anti-patterns that read as permission-seeking even when phrased as status

These phrases all functionally cede the turn back to the user when the plan
already contains the next step. **None of these are acceptable closers.**

- "Standing by for go-ahead on X."
- "Continuing into X." (then stopping)
- "Continuing into X once you confirm Y." (Y was already in the plan, or Y is
  something I can check myself.)
- "Open question for you before I write X."
- "Ready to proceed when you give me the green light."
- "Will report back per-PR." (then stopping at PR boundary instead of the
  end of the agreed batch.)

If the next step is in the agreed plan, take it. If a question arose mid-work
that I can answer with a tool call (read a file, query the DB, run a test),
answer it myself before mentioning it. If the question genuinely needs human
input — design ambiguity not pre-specified, destructive operation, external
write — name the question and stop. Don't conflate "I'd be more comfortable
checking" with "I'm blocked".

### Phase boundaries are not checkpoints

A multi-batch plan (Batch A → B → C → D) is approved end-to-end when the user
approves the plan. Do NOT stop at the boundary between batches to ask. Stop
only for the conditions above.

## Scope of pre-approved actions

The following are pre-approved without per-action confirmation:

- Read/grep/glob anywhere in the repo, including `.env`, `data/`, `.git/`.
- Edit/Write any project file: backend Python, frontend TypeScript, schemas,
  migrations, tests, docs, Makefile, CI workflows, package configs, scripts.
- Run `pytest`, `ruff`, `npm run build`, `npm run lint`, `make test`, `make lock`,
  and other repository-local read-only commands.
- Stage and commit changes when the agreed batch reports completion. Use
  scoped commits per finding/feature.
- Create, modify, or delete files in `data/audit/` and `data/processed/` as
  intermediate artefacts.

## Still requires explicit approval

- Destructive git operations: `git reset --hard`, `git push --force`,
  `git branch -D`, `git checkout --` discarding uncommitted work,
  `git rebase -i`.
- Force-push to any branch.
- External writes: API POSTs, deploys, package publishes, commits to remotes
  other than origin, opening PRs, posting to external services.
- Rotating real credentials in `backend/.env` or `frontend/.env.local`.
- Hand-editing `backend/requirements.lock` (use `make lock` instead).
- Running the full federal or state/local pipelines against live external
  endpoints (smoke runs against fixtures are OK).

## Verification expectations

The HARD GATE in `~/CLAUDE.md` for review/verdict workflows still applies when
reviewing code, diffs, analyses, or claims. When implementing, run targeted
tests (pytest with relevant filters) and the frontend build before declaring
a batch complete. Report failures honestly; do not mark tasks complete with
failing tests.

## Tone

- Adversarial-empirical: be willing to flag overclaiming, attribution leakage,
  test gaps, public-facing UX confusion.
- Empirical-conservative: keep `direct_person`, `campaign_support`,
  `party_mediated_exposure`, and modelled allocation strictly separated. Direct
  totals must not change when a loader creates new party/entity links.
- Plain-English UI text. Lay terms before network-theory terms.
- Missing values are missing data, not zero or assumed.

## Project context cheatsheet

- Repo root: `/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics`
- Backend: Python/FastAPI under `backend/au_politics_money/`
- Frontend: Vite/React/MapLibre under `frontend/`
- DB: PostgreSQL/PostGIS local at
  `postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics`
- Tests run with:
  ```
  AUPOL_RUN_POSTGRES_INTEGRATION=1 \
  DATABASE_URL_TEST=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \
  backend/.venv/bin/pytest -q
  ```
- CLI pattern: `cd backend && .venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money <cmd>`
- Frontend build: `cd frontend && npm run build`

## Documentation discipline

- Every method/finding/decision worth keeping goes in `docs/build_log.md` with
  the date and a quantitative summary where possible.
- Every theoretical decision goes in `docs/influence_network_model.md` or
  `docs/theory_of_influence.md`.
- Source-licence claims must distinguish "not blocking local development" from
  "cleared for public redistribution". Use the latter only with verified
  licence/terms captured in the repo.

## Browser preference

Use Firefox or the in-app browser for visual checks. Do not use Chrome.
