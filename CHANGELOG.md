# Changelog

All public-facing changes worth a reader's attention land here.
This is the human summary; the full per-PR change history lives in
[`docs/build_log.md`](docs/build_log.md), and the source-of-truth is
the project's git log on the public mirror at
[https://github.com/mzyphur/political-influence-tracker](https://github.com/mzyphur/political-influence-tracker).

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
shape but does not yet ship versioned releases — the project is
pre-launch through May 2026 and `main` is the source of truth. Each
section below corresponds to an internal "batch" landed on `main`.

## [Unreleased] — pre-launch ramp toward May 2026

### Batch X / Y — strategic-breadth expansion + AusTender ingestion stack

**Strategic assessment delivered.** A deep audit of the database
(314,040 events, 47% entities unclassified, 56% events undated)
plus the gap between documented sources in `data_sources.md` and
the broader public-record landscape across federal, state, and
local government in Australia. Identified a Tier-1 set of high-
value untapped public-record sources — Commonwealth contracts
(AusTender), Commonwealth grants (GrantConnect), the Foreign
Influence Transparency Scheme register (FITS), Senate Order on
Departmental and Agency Contracts, ANAO performance audits,
Federal Register of Legislation, APH Bills Search, APH Committee
Inquiries (submissions and transcripts), and ParlInfo full-text
Hansard.

**12 new federal source records registered** in `sources.py`:

- `austender_contract_notices_current` — every Commonwealth
  contract ≥ $10k (live tenders.gov.au)
- `austender_contract_notices_historical` — yearly bulk CSV via
  data.gov.au under CC-BY 3.0 AU; smoke-tested 17-18 file
  (73,458 rows / $43.28B / SHA-256 verified)
- `grantconnect_grants` — every Commonwealth grant > $0
- `fits_register` — Foreign Influence Transparency Scheme
- `senate_order_contracts` — twice-yearly per-portfolio listings
- `anao_performance_audits` — Auditor-General performance audits
- `federal_register_of_legislation` — Acts + subordinate legislation
- `aph_bills_search` — per-Bill progress + speeches
- `aph_committee_inquiries` — submissions + transcripts
- `aph_hansard_full_text_proquest` — speech-level Hansard
- `grants_gov_au_open_grants` — forecast register
- `modern_slavery_register` — mandatory ≥ $100M turnover statements

**11 new state-level source records registered**:

- 8 state lobbyist registers (NSW, VIC, QLD, WA, SA, TAS, ACT, NT)
- 3 state parliamentary Hansard sources (NSW, VIC, QLD)

Total registered SourceRecord entries: 97 (was 74).

**Reproducible CC-BY-licensed data.gov.au fetcher** at
[`scripts/fetch_data_gov_au_resource.sh`](scripts/fetch_data_gov_au_resource.sh).
Refuses non-CC-BY licences by default; produces SHA-256-attested
archives under `data/raw/<source>/<UTC-stamp>/`. Smoke-tested
end-to-end against the AusTender historical-contracts 2017-18
CSV (CKAN id `5c7fa69b-…`).

**AusTender CSV→JSONL parser** at
[`backend/au_politics_money/ingest/austender.py`](backend/au_politics_money/ingest/austender.py).
Reads the historical contract-notice CSVs, normalises every row
to a stable `austender_v1` JSONL schema, and writes a per-file
summary JSON with aggregate statistics (top agencies / suppliers
/ UNSPSC / consultancy + confidentiality flag rates / publish-
date span). Personal-identifying fields (Contact Name / Phone)
are deliberately excluded for privacy-conservativism. 39 unit
tests pin the parser shape (date / money / boolean / ABN
helpers + end-to-end synthetic CSV). New CLI command
`au-politics-money normalize-austender-csv <archive_dir>` runs
the parser against a downloaded archive.

**Live smoke against the 2017-18 AusTender CSV**:

- 73,458 contract notices parsed
- 60,590 with non-NULL contract values
- $43.28 BILLION total reported value
- Top spending agency: Department of Defence ($24.8B)
- Top supplier: CSL Behring (Australia) Pty Ltd ($3.35B)
- Date span: 2004-07-14 to 2018-06-29

The loader that lifts AusTender JSONL records into
`influence_event` (via the schema's existing `procurement` event
family — no migration needed) is a follow-up batch.

### Batch R — sub-national rollout activation + gifts/hospitality UX redesign

- **Activated** the deferred sub-national rollout for QLD. The
  AEC Register branch resolver now does a deterministic dual-call:
  one resolution biased toward the federal jurisdiction (existing
  behaviour, unchanged) and a second pass biased toward a detected
  state's jurisdiction when a state-branch wording is present
  ("(Queensland)", "(QLD Branch)", "(State of Queensland)",
  "(Victorian Division)", "(NSW Branch)", etc.). The loader emits
  a second `party_entity_link` row pointing at the state-
  jurisdiction party_id, coexisting with the federal link via the
  `(party_id, entity_id, link_type)` unique constraint.
- **Live smoke** against real AEC Register data: 22 QLD state-
  jurisdiction reviewed links emitted as peers of the existing 148
  federal links — all 22 to QLD ALP (id=152936), the AEC's
  dominant published state-branch wording for currently-seeded QLD
  party rows. The other QLD-jurisdiction parties (LNP, KAP, GRN,
  IND) wait on additional state-branch wordings being added to the
  detector or further QLD party seeding. NSW / VIC / etc. roll out
  automatically once their state-jurisdiction party rows are
  seeded — the resolver and loader fan-out are state-agnostic by
  design.
- **API + frontend** surface a non-federal jurisdiction chip on
  party-exposure rows when present (e.g. "QLD state", "NSW
  state"). Federal rows on a federal-MP profile return null (no
  clutter — federal is the implicit default).
- **No cross-jurisdiction conflation.** A regression test asserts
  the federal-MP API surface returns federal-jurisdiction rows
  ONLY, regardless of how many state-jurisdiction
  party_entity_link rows exist for the same entity. The office-
  term-anchored query is the load-bearing guard.
- **Refactored** the per-MP "Gifts, Travel & Hospitality" panel
  to provider-first scannable cards with click-to-expand. Each
  card shows the provider name + total record count up front;
  clicking reveals the distinct benefit forms received from that
  provider (lounge access, tickets, etc.), the reported-amount
  line, the loaded date span, and the project's standing claim-
  discipline caveat. Records the source PDF didn't attach to a
  commercial provider surface explicitly under a "Provider not
  disclosed in source" card — never hidden.
- **Dropped** the "X pending review" microcopy from the public
  surface when every record carries the flag. The label now only
  appears when SOME but not ALL records have been human-reviewed,
  so it conveys real signal instead of universal noise.

### Batch O — public-mirror hardening (CI security audits + cache headers + CHANGELOG)

- **Added** `.github/workflows/security.yml` — weekly + manual
  `pip-audit` against `backend/requirements.lock` and `npm audit`
  against `frontend/package-lock.json`. Reports uploaded as
  artifacts with 30-day retention. Informational by default; the
  maintainer reviews findings and lands fixes through the regular
  PR flow.
- **Added** `Cache-Control: public, max-age=60, stale-while-revalidate=300`
  on `/api/coverage` and `/api/stats`. These endpoints reflect
  loader-refresh state (sub-minute granularity) so a short public
  cache is correct and reduces load.
- **Added** this file (`CHANGELOG.md`) — public-friendly summary
  derived from the per-PR `docs/build_log.md` history. Linked from
  the README's "Where to look next" section.

### Batch N — public-facing FAQ + worked example

- **Added** [`docs/faq.md`](docs/faq.md) — what this is / isn't,
  evidence tiers, the project's claim-discipline rule, the
  "what `Est. exposure` means" explainer, the postcode-search
  scope, reproducibility instructions, contributing channels, and
  the "who runs this project" section.
- **Added** [`docs/worked_example.md`](docs/worked_example.md) —
  step-by-step walk-through showing how a journalist / scholar /
  regulator / citizen can use the project to investigate a
  specific question (e.g. compare two MPs' disclosed records on
  an industry sector) without overclaiming. Includes explicit
  do / don't claim-discipline templates.
- **Updated** README's "Where to look next" reorganised into
  Readers / Contributors audiences with FAQ + worked example
  surfaced under Readers.

### Batch M — OpenAPI / Swagger metadata + `/api/stats` + Dependabot

- **Added** rich OpenAPI metadata so the auto-generated `/docs`
  page is publicly useful: 9 tags (Health, Search, Map, Coverage,
  State / Local, Representatives, Entities, Parties, Electorates,
  Influence), per-endpoint summaries + descriptions + non-200
  responses, contact + license_info pointing at the public mirror
  and the AGPL-3.0 text.
- **Added** `/api/stats` endpoint — a small, stable-shape
  reader-facing project-stats snapshot suitable for embedding in
  HTML / JSON dashboards / RSS / static-site generators. Headline
  fields: `influence_event {row_count, reported_value_sum,
  latest_event_date}`, `person {row_count}`, `electorate
  {federal_house_count}`, `party_entity_link {reviewed_count,
  unresolved_count}`, `postcode_electorate_crosswalk {row_count,
  distinct_postcode_count, distinct_electorate_count,
  federal_house_seat_coverage_percent}`, `source_document
  {row_count, most_recent_fetch_at}`, `licence`, `caveat`.
- **Added** `.github/dependabot.yml` — weekly Monday Australia/Sydney
  scans across pip / npm / github-actions ecosystems with grouped
  minor + patch updates. Lockfile-aware versioning so the
  reproducibility chain stays authoritative.

### Batch L — public-launch hardening

- **Added** `.github/workflows/ci.yml` — fast-feedback CI on every
  push to `main` and every pull request. Two parallel jobs:
  backend (pytest + ruff against a PostGIS service) and frontend
  (tsc + vite build with `METHODOLOGY_REPO_URL` automatically
  resolved to the GitHub repo URL).
- **Updated** [`docs/source_licences.md`](docs/source_licences.md):
  APH and AEC GIS provisionally cleared per project-lead direction
  on 2026-05-01. Reply text TBD on file under
  `docs/letters/replies/`. Honest "provisionally approved; written
  reply text to be archived when it arrives" framing keeps the
  audit trail truthful.
- **Added** `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor
  Covenant v2.1 by URL reference), `SECURITY.md`,
  `.github/ISSUE_TEMPLATE/` (config + bug_report + feature_request
  + **data_correction** as the highest-value contribution
  category), `.github/PULL_REQUEST_TEMPLATE.md`. Plus 10 GitHub
  discovery topics applied via `gh repo edit`.
- **Updated** README rewritten with public-facing tagline + four
  shields.io badges (CI status, AGPL-3.0, pre-launch status,
  Contributor Covenant), "What this is" / "What this is **not**"
  framing block, Contributing section pointing at the new
  metadata files.

### Batch K — public-readiness sprint

- **Added** ready-to-sign Word `.docx` exports of the APH House,
  APH Senate, and AEC GIS exception-request letters under
  [`docs/letters/word/`](docs/letters/word/). Reproducible
  generator at `scripts/generate_letter_docx.py`.
- **Added** AGPL-3.0 source-code licence at `LICENSE` (canonical
  GNU text). README gains a "Source code licence" section
  explaining the AGPL choice and clarifying that the AGPL applies
  to the code only — the upstream publisher data licences in
  `docs/source_licences.md` continue to bind.
- **Added** public GitHub mirror live at
  https://github.com/mzyphur/political-influence-tracker.
- **Added** a tiny self-contained dotenv loader in
  `frontend/scripts/sync-methodology-version.mjs` so
  `METHODOLOGY_REPO_URL=https://github.com/mzyphur/political-influence-tracker`
  in `frontend/.env.local` makes every `npm run build` produce a
  methodology page whose revision marker links back into the
  public mirror's commit pages. No new npm dependency.

### Batch J — postcode crosswalk expansion (191 → 448 rows)

- **Added** three staged residential-sample postcode bulk-fetch
  runs (195 + 208 + 211 = 614 unique NEW postcodes, zero
  overlap) lifting the federal postcode-electorate crosswalk
  from 191 rows to **448 rows** / 171 → 404 distinct postcodes
  / **127 of 150 federal House seats covered (84.7%)**. Per-state:
  NSW 121/37 electorates, VIC 114/31, QLD 73/27, WA 64/12, SA 40/9,
  TAS 19/5, ACT 6/3, NT 5/2.
- **Added** public-facing `#postcode-coverage` section to the
  methodology page that exposes the four known coverage
  limitations (PO Box silent-skip, leading-zero gap for ACT/NT,
  multi-electorate ambiguity, inner-metro fragmentation) so
  users understand why some postcodes return no result rather
  than guessing.

### Batch I — last-mile licence verbatim + 200-postcode bulk fetch + exception-request letters

- **Updated** all ten source licences carry verbatim direct-fetch
  wording (or, for AIMS Coastline 50K's eAtlas companion,
  conclusively unfetchable status with the data.gov.au verbatim
  as the load-bearing record). Australia Post historical URL
  retired (404 in 2026); current canonical product page captured
  verbatim.
- **Added** drafts of two formal exception-request letters under
  `docs/letters/`: APH (Clerks of the House and Senate) for the
  CC BY-NC-ND 4.0 derivative-work exception, and AEC GIS for the
  Derivative Product confirmation under the End-user Licence.

### Earlier batches (D–H)

Earlier batches landed the AEC Register of Entities ingestion
chain, the deterministic 5-stage party-branch resolver (no fuzzy
matching), the source-jurisdiction disambiguation rule, the
federal-vs-state party-row consolidation migration (034), curated
party seed migrations (035 / 036 / 037 with the
`is_personality_vehicle` metadata flag wired through the API and
the frontend chip), the public-reproducibility scaffolding
(`make reproduce-federal`), and the build-time methodology-page
revision-marker injection. Full details in
[`docs/build_log.md`](docs/build_log.md).

## Audience for this changelog

Readers (journalists, scholars, regulators, citizens) wanting a
short answer to "what's changed recently?" — without needing to
open the per-PR build log. The build log remains the canonical
audit trail.
