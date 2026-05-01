# Frequently Asked Questions

A living public-facing FAQ. If your question isn't here, the
[issue tracker](https://github.com/mzyphur/political-influence-tracker/issues)
is the right place to ask it; the project will fold genuinely
common questions back into this file over time.

## What this project is and isn't

### What is the Political Influence Tracker?

A reproducible, source-backed transparency tool that publishes a
verifiable link from disclosed federal political records back to
the original public source documents. It ingests the records that
the AEC, the Parliament of Australia, and several public-interest
civic services already publish, parses them into structured
records, and surfaces them on a public app alongside the original
PDFs and CSVs.

Every claim the app makes travels with its evidence tier and a
link back to the source document.

### Is the project accusing anyone of corruption or wrongdoing?

**No.** The project's most important rule is *show the evidence,
preserve the source, and separate facts from interpretation*.

Disclosed records are not allegations of wrongdoing. Surfacing a
record is not equivalent to accusing the person who disclosed it.
Australia's political-disclosure regime exists precisely so that
ordinary people, journalists, scholars, and regulators can read
what's been disclosed without each having to file FOIs and parse
PDFs by hand. This project just makes that easier.

### Is this a "money received" leaderboard?

**No.** The project keeps four evidence families strictly separate
and never sums across them on any user-facing surface:

1. **Direct disclosed person-level records** — what an MP / Senator
   has personally disclosed (Register of Interests gifts and
   hospitality, declared interests, and similar).
2. **Source-backed campaign-support records** — AEC annual / election
   disclosure returns. These flow to candidates, parties, or
   campaign vehicles; they are not personal income.
3. **Party / entity-mediated context** — the AEC Register of
   Entities records that link a party to its associated entities
   and significant third parties. This is *context*, not money the
   MP received.
4. **Modelled allocation** — equal-share or analytical estimates
   computed by the project (e.g. the per-rep equal-share split of
   a party's exposure across its current caucus). These are
   labelled "Est." in the UI and ship with a denominator-scope
   caveat.

The project's API at `/api/stats` returns one row count for
`influence_event` (a loaded-row metric), but that is for
transparency only — it is **not** a "money received" total.

### What's the legal status of the data?

The project's per-source licence audit is in
[`docs/source_licences.md`](source_licences.md). All ten public
sources have been verbatim-fetched from each publisher's licence
page. The project's posture is conservative: until a licence is
captured in that file, the project does not redistribute the
underlying source content.

The project's source code is licensed under the
[GNU Affero General Public License v3.0](../LICENSE). The data the
project ingests is governed by the upstream publishers' separate
licences (CC-BY 4.0 for AEC website content, ODbL for OpenStreetMap
and TVFY, the AEC GIS End-user Licence for boundaries, CC BY-NC-ND
4.0 for APH register material, etc.) — those licences continue to
bind regardless of what the source-code licence says.

## Reading the data

### What's an "evidence tier"?

A label that tells you *how strong* the claim is. The project uses
four tiers:

- **direct** — a public record explicitly says this person received
  this thing on this date.
- **campaign_support** — a public record explicitly says a campaign
  vehicle (party, candidate, third party, associated entity)
  received this thing on this date. This is **not** a personal
  receipt by the MP / Senator who happens to be associated with
  that vehicle.
- **party_mediated** — public records (e.g. AEC Register of
  Entities) link a party to an associated entity. Looking at this
  on its own does NOT mean any individual MP got anything.
- **modelled** — the project computed a label or estimate (e.g. an
  equal-share allocation across a current caucus). Always labelled
  "Est." in the UI.

If you find a surface that doesn't tell you which tier a claim is
in, that's a bug — please file a
[Data correction issue](https://github.com/mzyphur/political-influence-tracker/issues/new?template=data_correction.md).

### What does "Est. exposure $X" mean?

It is an **analytical estimate**, not a direct receipt. The most
common case: a party has disclosed total exposure of $Y across its
N current MPs, and the per-rep figure is $Y / N. The "denominator
scope" chip on the UI tells you what N is (typically: current
office-term party representatives only).

These numbers are useful for *patterns* — which party-mediated
exposure footprints are largest, which sectors concentrate
disclosed flows — but they are NOT receipts to the named
representative. The label "Est." and the denominator-scope chip
are both load-bearing; do not strip them when quoting.

### What does the postcode search do?

It maps a postcode to one or more federal House electorates via
the AEC's official Electorate Finder endpoint, then displays the
linked MP. It does NOT estimate "your" MP's behaviour from your
postcode — once you've reached the MP's profile page, the records
shown are what the MP has personally disclosed.

The current postcode-to-electorate crosswalk covers 404 distinct
postcodes mapping to 127 of 150 federal House seats (84.7% seat
coverage). The methodology page's
[`#postcode-coverage`](../frontend/public/methodology.html#postcode-coverage)
section enumerates the four known coverage limitations.

## Reproducibility

### Can I rebuild every number on the public site myself?

Yes. The project's reproducibility chain is documented at
[`docs/reproducibility.md`](reproducibility.md), and the README's
"Reproduce every number on the site" section walks through the
exact commands. The short version:

```bash
git clone https://github.com/mzyphur/political-influence-tracker.git
cd political-influence-tracker
make bootstrap
make db-up
make db-ready
make reproduce-federal
```

The CI workflow at `.github/workflows/ci.yml` runs the smoke
version of the same chain on every push to `main` and every pull
request, and the weekly `federal-pipeline-smoke.yml` runs the full
chain. The expected output is a database that matches what the
public app shows.

### How fresh is the data?

Every record carries a `fetched_at` timestamp on its
`source_document` row. The `/api/stats` endpoint returns the
`source_document.most_recent_fetch_at` field as a public proxy
for project freshness. The methodology page's footer carries the
build-time short SHA, linked back into the public repo's commit
history.

## Contributing

### How do I report a record the site gets wrong?

Open a [Data correction issue](https://github.com/mzyphur/political-influence-tracker/issues/new?template=data_correction.md).
The template walks through what the maintainers need: the public
app surface (or API endpoint) where you saw it, the underlying
source document with a verifiable URL, and the affected evidence
family.

Data corrections are the highest-value contribution category for
the project's mission.

### Can I send a security issue privately?

Yes — see [`SECURITY.md`](../SECURITY.md). Email the project lead
at `mzyphur@instats.org`; do **not** open a public issue for
security disclosures, source-licence violations, or
claim-discipline bypasses.

### Can I submit a code change?

Yes — see [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the dev
setup, branch / commit conventions, and the project-specific gates
the maintainers apply during review. The CI workflow runs pytest +
ruff + the frontend build on every PR; matching local commands are
in the README's "Tests, linting, build" section.

## Other questions readers ask

### Why federal-first?

Federal disclosure law is national, the AEC publishes the
underlying records uniformly, and the federal House map is
testable end-to-end. State and council disclosure regimes vary and
are best added one jurisdiction at a time after the federal launch
proves out.

The state / local rollout plan is documented at
[`docs/sub_national_party_seeds_plan.md`](sub_national_party_seeds_plan.md).
QLD canary work is in flight.

### Is there an API?

Yes — the FastAPI app at `backend/au_politics_money/api/` exposes
14 endpoints under `/api/...`. Run `make api-dev` from the project
root to get the local server, then open
http://127.0.0.1:8008/docs for the auto-generated Swagger
documentation. The OpenAPI metadata enumerates the endpoints by
tag (Search / Map / Coverage / State-Local / Representatives /
Entities / Parties / Electorates / Influence) and includes
example responses.

### Who runs this project?

The project's lead is the maintainer commit-attribution on the
public mirror. Public correspondence is at
[`docs/letters/`](letters/) (with ready-to-sign Word versions
under `docs/letters/word/`). Code contributions go through the
public GitHub flow; non-public correspondence goes to the email
in [`SECURITY.md`](../SECURITY.md).

The project is **not** affiliated with the AEC, the Parliament of
Australia, the AIMS, or any political party. It is a public-
interest civic-tech project that ingests their already-public
records.

### Does the project make money?

No. The project is a non-commercial public-interest tool. It does
not run advertising, does not paywall the data, and does not sell
the data. The AGPL-3.0 source-code licence is chosen specifically
to keep public-facing forks transparent: anyone running a modified
version as a public-facing service must offer the source of their
modifications back to that service's users.

---

*Have a question that should be here? Open a
[discussion](https://github.com/mzyphur/political-influence-tracker/discussions)
or a [feature-request issue](https://github.com/mzyphur/political-influence-tracker/issues/new?template=feature_request.md).*
