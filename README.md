# Australian Political Influence Transparency

A reproducible, source-backed evidence system for Australian political
money, gifts, interests, lobbying access, party-channelled support, and
parliamentary voting behaviour. Federal-first; state/local follows.

The project's central rule: **show the evidence, preserve the source,
and separate facts from interpretation.** Direct disclosed person-level
records, source-backed campaign-support records, party/entity-mediated
context, and modelled allocations are kept as separate evidence
families. They are NEVER summed into a single "money received" headline.
Every public claim travels with its evidence tier and attribution
limit.

The corresponding theory of influence and the per-mechanism modelling
choices are documented in
[`docs/theory_of_influence.md`](docs/theory_of_influence.md) and
[`docs/influence_network_model.md`](docs/influence_network_model.md).
The hostable, public-facing companion page is at
[`frontend/public/methodology.html`](frontend/public/methodology.html)
(linked from the app as **Method**).

---

## Reproduce every number on the site

Every number the public app shows is reproducible from public sources
plus the code in this repository. There is no manual data entry, no
private spreadsheets, no human-curated row-by-row totals.

### One command, from a clean clone

```bash
git clone <repo-url> au-politics
cd au-politics
make bootstrap        # backend venv + frontend npm deps
make db-up            # local Postgres/PostGIS via docker-compose
make db-ready         # block until Postgres is ready
make reproduce-federal
```

`make reproduce-federal` runs
[`scripts/reproduce_federal_from_scratch.sh`](scripts/reproduce_federal_from_scratch.sh).
The script:

1. Sanity-checks Python / Node / docker-compose and reports disk free.
2. Brings up the local Postgres/PostGIS container.
3. Bootstraps the backend venv with `requirements.lock` so dependency
   versions are pinned.
4. Runs the federal foundation pipeline against the **live** AEC, APH,
   AIMS, and (optional) They Vote For You sources, archiving raw
   responses + parsed JSONL under
   [`data/raw/`](data/raw/) and [`data/processed/`](data/processed/).
5. Applies every Postgres schema migration in
   [`backend/schema/`](backend/schema/), including the AEC Register
   ingestion (`033`) and federal-party-row consolidation (`034`).
6. Loads the freshly-fetched processed artifacts into Postgres.
7. Runs the `qa-serving-database` gate (current-MP coverage, dropped
   boundaries, parser boilerplate detection, vote-count parity, etc.).
8. Runs the full backend pytest suite with Postgres integration.
9. Runs `ruff check` and the frontend production build.
10. Prints the audit-manifest path and the per-stage log paths.

### CI / quick-iteration mode

```bash
make reproduce-federal-smoke
```

The same chain in `--smoke` mode (House interests PDF work limited to
a small subset). Used by CI; do not use for public data publication.

### Targeted reproducibility entry points

If you only want to reproduce the most recently-changed surfaces, the
top-level `Makefile` exposes single-step targets that match the
methodology-page sections:

| Step | Target |
|---|---|
| Fetch the AEC Register of Entities live | `make fetch-aec-register` |
| Load the latest fetched AEC Register JSONL into Postgres | `make load-aec-register` |
| Fetch postcodes from the AEC electorate finder using the seed list | `make fetch-postcode-crosswalk` |
| Load the latest postcode crosswalk JSONL | `make load-postcode-crosswalk` |
| Run the post-load QA gate + tests + frontend build | `make verify` |

Run `make help` to see the full list.

### Auditing what just happened

Every run leaves behind:

- `data/raw/<source_id>/<timestamp>/metadata.json` for each fetched
  source (URL, HTTP status, sha256, request/response headers, redaction
  policy, source-licence caveat).
- `data/processed/<dataset>/<timestamp>.jsonl(.summary.json)` for each
  parsed output.
- `data/audit/pipeline_runs/<run-id>.json` recording pipeline name,
  status, timestamps, runtime, Python + package versions, platform,
  git commit, parameters, and per-step output paths/errors.
- `data/audit/logs/reproduce_federal_*_<timestamp>.{stdout,stderr}.log`
  for every stage of the reproduce script.

The detailed reproducibility policy is in
[`docs/reproducibility.md`](docs/reproducibility.md).

---

## Repository layout

| Path | Purpose |
|---|---|
| [`backend/`](backend/) | Python ingestion, normalization, FastAPI surface, and database loaders. |
| [`backend/schema/`](backend/schema/) | PostgreSQL/PostGIS schema migrations (`001` baseline, then additive). |
| [`backend/au_politics_money/`](backend/au_politics_money/) | Pipeline / loader / parser / API code. |
| [`backend/tests/`](backend/tests/) | Pytest suites. Postgres integration tests are gated behind `AUPOL_RUN_POSTGRES_INTEGRATION=1`. |
| [`frontend/`](frontend/) | Vite/React/MapLibre app. |
| [`frontend/public/methodology.html`](frontend/public/methodology.html) | Hostable public methodology companion. |
| [`scripts/`](scripts/) | Pipeline-runner shell scripts (weekly federal, weekly state/local, reproduce-from-scratch). |
| [`data/raw/`](data/raw/) | Raw downloaded source documents, grouped by source and timestamp. |
| [`data/processed/`](data/processed/) | Parsed/normalised JSONL outputs. |
| [`data/audit/`](data/audit/) | Pipeline-run manifests, validation reports, run logs. |
| [`data/seeds/`](data/seeds/) | Hand-curated seed lists (postcodes, etc.) used by reproducible fetchers. |
| [`docs/`](docs/) | Methodology, source inventory, build log, session state, reproducibility policy. |
| [`notebooks/`](notebooks/) | Exploratory analysis only — never the source of truth. |

---

## Local serving baseline

These are the row counts on the local development database after the
last full federal reproduce run. They are NOT goals; they are
auditable facts about the most recent ingestion. Anyone reproducing
the pipeline against the same public sources at the same point in time
should get equivalent numbers (modulo source-side updates).

- **314,040** non-rejected `influence_event` rows.
- **318** `person` rows.
- **150** federal House `electorate` rows.
- **87** reviewed `party_entity_link` rows derived from the AEC
  Register of Entities (86 → ALP, 1 → AG).
- **9** `postcode_electorate_crosswalk` rows from the bootstrap
  postcode seed list.

The `qa-serving-database` gate enforces the structural invariants on
top of the row counts (current House boundary count, current-roster
match coverage, parser-boilerplate detection, etc.).

The federal foundation pipeline currently archives and normalises:

- AEC annual + election disclosure bulk data.
- AEC Register of Entities (political party / associated entity /
  significant third party / third party).
- AEC current federal electorate boundary shapefile + GeoJSON +
  AIMS-clipped display geometry.
- APH House / Senate registers of interests, gifts, travel,
  hospitality.
- APH House Votes & Proceedings + Senate Journals decision-record
  indexes and PDFs.
- APH MP/Senator current contacts CSVs (the federal roster).
- AEC Electorate Finder postcode crosswalk (bootstrap seed list).
- Australian Government Register of Lobbyists snapshot.
- Optional: They Vote For You division/vote API ingestion (with
  `THEY_VOTE_FOR_YOU_API_KEY`).

---

## Frontend / API for local development

```bash
make api-dev          # backend FastAPI on http://127.0.0.1:8008
make frontend-dev     # frontend Vite dev server on http://127.0.0.1:5173
```

The frontend defaults to `VITE_API_BASE_URL=http://127.0.0.1:8008` and
proxies `/api` and `/health` through Vite. MapTiler tiles are
configured via `VITE_MAPTILER_API_KEY` in `frontend/.env.local`.

The browser of choice for visual checks is **Firefox or the in-app
browser**, never Chrome. The reasoning is in
[`CLAUDE.md`](CLAUDE.md). The eyes-on smoke checklist is at
[`docs/batch_d3_firefox_smoke_checklist.md`](docs/batch_d3_firefox_smoke_checklist.md).

---

## Tests, linting, build

```bash
make test       # backend pytest (Postgres integration enabled) + frontend build
make lint       # backend ruff
make verify     # qa-serving-database + tests + lint + frontend build
```

The full backend suite currently passes 315/315; running the suite
locally requires the Postgres container up
(`make db-up && make db-ready`).

---

## Claim discipline (the rule everything else serves)

When in doubt, the project errs toward under-claiming.

We can show:

- Source-backed flows: who disclosed what, from whom, to whom, when,
  and which public source.
- Pathways with explicit evidence tiers (direct-disclosed,
  source-backed-campaign-context, party/entity-mediated,
  modelled-allocation).
- Missingness as a data condition, not as zero.

We must not claim without stronger evidence:

- Bribery, personal receipt, or improper influence — lawful
  disclosure is not automatically improper, and party money is not
  personal income.
- Causation — a donor did not necessarily cause a vote.
- Hidden values — missing dollar amounts are missing data, not
  evidence the value was high.

Per-tier rules for campaign-support attribution are in
[`docs/campaign_support_attribution.md`](docs/campaign_support_attribution.md).

---

## License / source-licence terms

Source-licence status for every public source ingested by the project
is documented in [`docs/source_licences.md`](docs/source_licences.md),
with verbatim publisher pages cited.

Headline implications a maintainer must resolve before any public
data release:

- **APH (Parliament of Australia) — CC BY-NC-ND 3.0 AU.** Parsing the
  registers of interests is a derivative work; needs explicit written
  exception or restriction to verbatim-only public surfaces.
- **AEC GIS (electorate boundaries) — Limited End-user Licence.** Public
  redistribution of the geometry likely falls outside the licence;
  needs written confirmation from AEC.
- **AIMS Australian Coastline 50K — licence not yet confirmed
  upstream.** Used only as a display-clip layer; substitute with
  Natural Earth before any public release until terms are captured.
- **Australia Post postcode CSV — non-commercial reference only.** Do
  NOT seed the project's public postcode crosswalk from this source.

Source-licence wording on internal artefacts continues to be
intentionally conservative: *"official public <agency> snapshot;
public redistribution / licence terms to be recorded before public
data redistribution"*. Local development is fine; public
redistribution requires verified licence terms captured in
`docs/source_licences.md`.

---

## Where to look next

- **Methodology** for non-engineers and journalists — open the app and
  click **Method**, or visit
  [`frontend/public/methodology.html`](frontend/public/methodology.html).
- **Reproducibility policy** — [`docs/reproducibility.md`](docs/reproducibility.md).
- **Build log** — [`docs/build_log.md`](docs/build_log.md) (newest
  first).
- **Session state for the next contributor** — [`docs/session_state.md`](docs/session_state.md).
- **Operating mode for AI-assisted contributions** — [`CLAUDE.md`](CLAUDE.md).
