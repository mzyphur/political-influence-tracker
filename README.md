# Australian Political Influence Transparency

> **A reproducible, source-backed transparency tool that publishes a
> verifiable link from disclosed federal political records back to
> the original public source documents.**

[![ci](https://github.com/mzyphur/political-influence-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/mzyphur/political-influence-tracker/actions/workflows/ci.yml)
[![licence: AGPL-3.0](https://img.shields.io/badge/licence-AGPL--3.0-blue.svg)](LICENSE)
[![status: pre-launch 2026-05](https://img.shields.io/badge/status-pre--launch%202026--05-yellow.svg)](docs/build_log.md)
[![code of conduct](https://img.shields.io/badge/code%20of%20conduct-Contributor%20Covenant%202.1-brightgreen.svg)](CODE_OF_CONDUCT.md)

Federal-first; state/local follows. Targets a May 2026 federal launch.
The corresponding theory of influence and the per-mechanism modelling
choices live in [`docs/theory_of_influence.md`](docs/theory_of_influence.md)
and [`docs/influence_network_model.md`](docs/influence_network_model.md).
The hostable, public-facing companion page is at
[`frontend/public/methodology.html`](frontend/public/methodology.html)
(linked from the app as **Method**).

## What this is

A public-interest transparency tool. It ingests Australia's already-
public political-disclosure records — AEC annual + election returns,
the AEC Register of Entities, House and Senate registers of
interests, MP/Senator contacts, House Votes & Proceedings + Senate
Journals, voting records via They Vote For You — parses them into
structured records, and surfaces them on a public app alongside the
original PDFs and CSVs. Every claim the app makes travels with its
evidence tier and a link back to the source document.

## What this is **not**

* **Not a watchdog campaign or opinion site.** The project does not
  characterise individual MPs or senators as corrupt, improper, or
  bribed. Disclosed records are not allegations of wrongdoing;
  surfacing a record is not equivalent to accusing the person who
  disclosed it.
* **Not a single "money received" leaderboard.** Direct disclosed
  person-level records, source-backed campaign-support records,
  party/entity-mediated context, and modelled allocations are kept
  as **separate evidence families** with their own caveats. They
  are NEVER summed.
* **Not a substitute for journalism.** The project surfaces records
  in a navigable form; interpretation, investigation, and reporting
  on what those records mean is the work of journalists, scholars,
  regulators, and citizens.

The central rule that ties all of these together: **show the
evidence, preserve the source, and separate facts from
interpretation.** Every public claim travels with its evidence tier
and attribution limit.

---

## Reproduce every number on the site

Every number the public app shows is reproducible from public sources
plus the code in this repository. There is no manual data entry, no
private spreadsheets, no human-curated row-by-row totals.

### One command, from a clean clone

```bash
git clone https://github.com/mzyphur/political-influence-tracker.git
cd political-influence-tracker
make bootstrap        # backend venv + frontend npm deps
make db-up            # local Postgres/PostGIS via docker-compose
make db-ready         # block until Postgres is ready
make reproduce-federal
```

For a faster local sanity check (CI mode; smaller dataset, no full
live fetch):

```bash
make reproduce-federal-smoke
```

The same chain runs in CI on every push to `main` and every pull
request — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
and the weekly full-pipeline smoke at
[`.github/workflows/federal-pipeline-smoke.yml`](.github/workflows/federal-pipeline-smoke.yml).

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

## Source code licence

The project's source code (Python backend, TypeScript frontend, SQL
schema migrations, build / pipeline scripts, documentation, and
this README) is licensed under the
**[GNU Affero General Public License, version 3.0](LICENSE)** (AGPL-3.0).

The AGPL is a strong copyleft licence with one extension that matters
for civic-transparency code: if you run a modified version of this
project as a public-facing network service, the AGPL requires that
you offer the source of your modifications to your service's users.
This is intentional. The point of a public-interest transparency
project is that anyone running a public-facing fork can be held to
the same source-disclosure standard.

The AGPL applies to the project's **code**. The data the project
ingests is governed by the upstream publishers' separate licences
(documented per-source below); those licences continue to bind
regardless of what the code licence says.

## Source-data licence terms

Source-licence status for every public source ingested by the project
is documented in [`docs/source_licences.md`](docs/source_licences.md),
with verbatim publisher pages cited.

Headline status:

- **APH (Parliament of Australia) — CC BY-NC-ND 4.0 International.**
  The default licence does not permit derivative works (which
  includes parsing the registers of interests into structured
  records). The project sought, and per project-lead direction has
  been provisionally granted, written exceptions from the
  Department of the House of Representatives and the Department of
  the Senate (2026-05-01). Reply text will be archived under
  `docs/letters/replies/` when received and any conditions narrower
  than the project's current behaviour will be applied to
  `docs/source_licences.md`. The CC BY-NC-ND 4.0 upstream
  restrictions remain binding for any republisher who doesn't have
  the same exception.
- **AEC GIS (electorate boundaries) — Limited End-user Licence with
  Derivative Product permission.** The licence already permits
  derivative products with attribution, sub-licensing, and end-user
  distribution. The project's re-projected, vector-tiled,
  publicly-served treatment of federal electorate boundary geometry
  is provisionally confirmed (2026-05-01, project-lead-side) as
  sitting within the existing "Derivative Product" permission.
  Reply text TBD on file; specific attribution-form conditions in
  the reply will be applied here when received. The verbatim
  attribution string and warranty disclaimer are preserved on every
  map surface.
- **AIMS Australian Coastline 50K — Licence Not Specified
  (verbatim, data.gov.au record).** Conservatively read as
  all-rights-reserved. Used only as a display-clip layer;
  substituted with Natural Earth coastline (public domain) before
  any public release.
- **Australia Post postcode CSV — non-commercial reference only.**
  Do NOT seed the project's public postcode crosswalk from this
  source. The project's postcode seed comes from Matthew Proctor's
  Australian-postcodes CC0 dataset instead.

Source-licence wording on internal artefacts continues to be
intentionally conservative: *"official public <agency> snapshot;
public redistribution / licence terms to be recorded before public
data redistribution"*. Local development is fine; public
redistribution depends on the verified licence terms (and the
in-flight written exceptions for APH + AEC GIS) captured in
`docs/source_licences.md`.

---

## Contributing

Bug reports, feature requests, **data corrections** (the highest-
value contribution category — see the dedicated
[issue template](.github/ISSUE_TEMPLATE/data_correction.md)),
and pull requests are all welcome. Start with:

* [`CONTRIBUTING.md`](CONTRIBUTING.md) — project mission, dev setup,
  branch + commit conventions, and the project-specific gates the
  maintainers apply during review (claim discipline, no fuzzy
  matching in the resolver, byte-identical direct-money totals,
  source-licence posture).
* [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant
  v2.1.
* [`SECURITY.md`](SECURITY.md) — private vulnerability-disclosure
  channel. Use this for security issues, source-licence violations,
  or claim-discipline bypasses; do **not** open a public issue for
  these.

## Where to look next

For readers (journalists, scholars, regulators, citizens):
- **Methodology** — open the app and click **Method**, or visit
  [`frontend/public/methodology.html`](frontend/public/methodology.html).
- **FAQ** — [`docs/faq.md`](docs/faq.md). What this is / isn't,
  what an evidence tier means, how the project handles claims, the
  source-licence posture, the postcode-coverage limitations.
- **Worked example** — [`docs/worked_example.md`](docs/worked_example.md).
  How to use the project to investigate a question (e.g. comparing
  two MPs' disclosed records on an industry sector) without
  overclaiming. Includes the do / don't claim-discipline templates.
- **API documentation** — start the local server and open
  [http://127.0.0.1:8008/docs](http://127.0.0.1:8008/docs) for the
  auto-generated Swagger page. Endpoints are grouped by tag (Search /
  Map / Coverage / Representatives / etc.).

For contributors (developers, data correctors):
- **Changelog** — [`CHANGELOG.md`](CHANGELOG.md) (public-friendly
  per-batch summary; the canonical per-PR audit trail is
  [`docs/build_log.md`](docs/build_log.md)).
- **Reproducibility policy** — [`docs/reproducibility.md`](docs/reproducibility.md).
- **Build log** — [`docs/build_log.md`](docs/build_log.md) (newest
  first).
- **Session state for the next contributor** — [`docs/session_state.md`](docs/session_state.md).
- **Contributing guide** — [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Operating mode for AI-assisted contributions** — [`CLAUDE.md`](CLAUDE.md).
- **Project correspondence** (formal letters to APH + AEC GIS) —
  [`docs/letters/`](docs/letters/). Ready-to-sign Word versions are
  under [`docs/letters/word/`](docs/letters/word/).
