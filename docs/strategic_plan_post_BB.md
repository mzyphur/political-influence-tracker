# Strategic Plan — Post-Batch-BB Roadmap

**Last updated:** 2026-05-02

This document is the project's full forward roadmap from the
end of Batch BB (2026-05-01) through public launch (target May
2026) and the post-launch refinement window. It complements
the strategic-stocktake doc at `docs/influence_correlation_gaps.md`
(what's missing) by mapping each gap to a concrete batch +
estimated cost + dependencies.

The plan is structured in seven phases. Phases A–C ship before
public launch; D–G are post-launch refinements. Every phase
preserves the project's claim-discipline rules and reproducibility
chain.

## Executive summary

| Phase | Scope | Cost (USD) | Dep. | Status |
|---|---|---:|---|---|
| A | Stage 1 v2 + IRR + 40-sector consolidation | $100 | — | IN FLIGHT |
| B | Stage 2 + Stage 3 full corpus runs | $250-450 | A | next batch |
| C | Stage 4b lobbyist + 4d ASIC + 4e ABS Census | $50 | — | next batch |
| D | Frontend voting / overlap / industry pages | $0 | B | post-launch |
| E | Council-level expansion (NSW + VIC councils) | $0 | C | post-launch |
| F | LLM Stages 5-15 (Hansard, FOI, committees, RC) | $2-7k | D | post-launch refinements |
| G | Launch polish + perf + press kit | $0 | A-D | pre-launch |

**Total pre-launch additional spend: ~$350-550 USD.**
**Total post-launch refinement budget headroom: $7,000+ USD
within the $10,000 AUD project envelope.**

## Phase A — Stage 1 v2 + IRR + 40-sector consolidation (IN FLIGHT)

**Status:** Stage 1 v2 28k entity corpus run executing in
background at the time of writing this plan (PID 79579).

**What lands:**
* Full 28,218 entities re-classified under the v2 prompt (40
  sectors, energy + mining splits).
* Loader runs; entity_industry_classification grows by ~28k v2
  rows (separate from v1 rows via `extraction_method` +
  `prompt_version` distinction).
* IRR script runs v1 vs v2 on the 28k overlap. Expected
  public-sector κ ≥ 0.85 (the 200-entity pilot showed κ=0.907).
* Sub-classification rate on v1's 60 `fossil_fuels` entities →
  v2 commodity-specific codes (coal/gas/petroleum/uranium).
  Expect >60% of v1 fossil_fuels entities resolve to a specific
  commodity under v2.
* Sub-classification rate on v1's 102 `mining` entities → v2
  iron_ore / critical_minerals / mining_other.
* Industry-aggregate view automatically updates — surfaces
  side-by-side activity per commodity instead of bucketed
  fossil_fuels.

**Decisions to make once data lands:**
* If v2 sub-classification rate is high (>70%): cross-
  correlation views switch to using v2 sectors as canonical;
  v1 stays for audit.
* If sub-classification is mixed (<50% of fossil_fuels go to a
  specific commodity): re-tune v2 prompt to encourage
  commodity-specific assignment, ship as v2.1, re-run only the
  fossil_fuels + mining subset.

**Cost:** $100 USD (in flight at time of writing).

**Dependencies:** None.

## Phase B — Stage 2 + Stage 3 full corpus runs

### Phase B-1 — Stage 2 ROI deep extraction full corpus

* **What:** run `scripts/llm_extract_register_of_interests.py`
  against all 2,852 House register sections (2,810 from
  20260427T105347Z.jsonl + the smaller follow-up files). Skip
  preamble + nil sections in the driver layer (~25% saved).
* **Cost:** ~$30 USD (Sonnet 4.6 with caching; per-section
  ~$0.0095 USD).
* **Wall-clock:** ~30 min at concurrency=8.
* **Output:** ~3,000 disclosure items extracted into
  `llm_register_of_interests_observation`.
* **Quality gate:** sample 30 random sections audit; pass
  threshold ≥ 90% correct (Stage 2 pilot was 109 items / 100
  sections; quality already production-grade in pilot).
* **Run timing:** kick off in background while Stage 1 v2
  completes.

### Phase B-2 — Stage 3 v3 full 5-year corpus

* **What:** run `scripts/llm_tag_austender_contracts.py` (with
  `--prompt-version v3` flag wired) against the 73,458-contract
  5-year corpus.
* **Cost:** $400 USD regular API / $200 USD via Anthropic
  Batches API (50% off).
* **Wall-clock:** ~6h regular / ≤24h Batches.
* **Output:** ~73k contract topic tags at 40-sector granularity.
* **Quality gate:** v3 vs v2 IRR on 200-contract subset; sample
  audit 30 random.
* **Decision: regular vs Batches.** Recommend Batches API for
  cost savings + the 24h SLA is acceptable for offline tagging.
* **Run timing:** AFTER Stage 1 v2 completes (so the entity
  classifications match the contract sectors).

### Phase B-3 — 25-year archive (deferred)

* Full historical 1.9M-contract archive: ~$5,200 via Batches API.
* Justified post-launch when historical pattern analysis
  becomes the next research priority.

## Phase C — Stage 4 deterministic data fills

### Phase C-1 — Stage 4b: Lobbyist Register

* **Source:** Federal Lobbyist Register at
  https://lobbyists.ag.gov.au/register (HTML scrape) + state
  registers (NSW, VIC, QLD, SA, WA, TAS).
* **What:** new tables
  `lobbyist_organisation_record`,
  `lobbyist_principal`,
  `lobbyist_client_engagement` with effective-date ranges.
* **Method:** deterministic HTML scrape; the `entity` table
  already has `entity_type='lobbyist_organisation'` so cross-
  joining is straightforward.
* **Closes the gap:** "Lobbyist firm L represents Client X.
  Lobbyist firm L's principals donate to MPs Z, W, V. Client X
  receives contracts from agencies overseen by Z / W / V."
* **Cost:** $0 (HTML scrape).
* **Status:** schema-design pending; loader is a half-day of
  work.

### Phase C-2 — Stage 4d: ASIC + ACNC beneficial ownership

* **Source:** ASIC bulk company-register (paid; ~AUD$45/year);
  ACNC charity register (free CSV).
* **What:** new table
  `entity_beneficial_ownership_observation` linking the
  controlling person/company → controlled entity with %
  + role + effective dates.
* **Closes the gap:** "Donor X is owned by Person/Entity Y. Y
  also controls Donor Z which received contracts. Combined
  influence calculations no longer under-count corporate
  vehicles."
* **Method:** deterministic-first (ASIC + ACNC officeholder
  parsers); LLM-aided for ambiguous-name matching to existing
  entity rows.
* **Cost:** AUD$45/year + ~$50 USD LLM matching budget.
* **Status:** post-launch (Batch CC).

### Phase C-3 — Stage 4e: ABS Census + SEIFA

* **Source:** ABS Census 2021 + SEIFA 2021 by Federal
  Electorate (CC-BY 4.0 from data.gov.au).
* **What:** new tables `electorate_seifa`,
  `electorate_census_2021` keyed by `electorate_id`.
* **Closes the gap:** "Industries that donate to MPs in
  low-SEIFA electorates" / "high-income electorates contribute
  more to Liberal" / etc. — the social-conditions correlation
  surface.
* **Cost:** $0.
* **Status:** before public launch (high reader value, low cost).

## Phase D — Frontend / UX expansion

### Phase D-1 — Component build-out

Components to ship:
* `MinisterVotingPanel.tsx` — embedded in DetailsPanel for MP
  profiles; renders the rows from
  `/api/minister-voting-pattern?minister_name=<name>`. Shows
  per-policy-topic aye/no/rebellion counts with sparkline.
* `ContractDonorOverlapPanel.tsx` — embedded in
  EntityProfilePanel for matched entities; renders rows from
  `/api/contract-donor-overlap?sector=<...>`. Side-by-side
  contract vs donation columns with tier-1 / tier-2 pills.
* `IndustryDetailPage.tsx` — full-page deep-dive on a sector.
  Reachable via URL `/industry/<sector_slug>`. Includes:
  - Per-sector donor list (top 50 by donation amount)
  - Per-sector contract list (top 50 by contract value)
  - Per-sector minister-overlap (which ministers oversaw most
    sector-X contracts)
  - Sector voting-pattern (how do MPs vote on policies
    affecting this sector?)
* `MinisterDetailPage.tsx` — full-page minister deep-dive.
  Reachable via URL `/minister/<id>`. Includes:
  - Portfolio + agencies under their watch.
  - Top contracts awarded by their portfolio.
  - Donations they received.
  - Voting record on portfolio-related topics.
  - Cross-overlap: did contracted suppliers ALSO donate?

### Phase D-2 — Search expansion

`/api/search` already covers types: representative / electorate /
party / entity / sector / policy_topic / postcode. Add:
* `minister` (joins to minister_role + person)
* `portfolio` (joins to portfolio_agency)
* `industry` (joins to entity_industry_classification.public_sector)

### Phase D-3 — Map integration

Add map pop-up on each electorate showing:
* Top industries donating to current rep (last 5 years).
* Whether current rep is a Cabinet minister; if so, list
  agencies they oversee.

### Phase D-4 — Methodology page

Update `frontend/public/methodology.html` with sections for:
* Stage 4a portfolio mapping
* Stage 4c voting integration
* Inter-rater reliability methodology + recorded baselines
* Sector taxonomy v2 (40 codes vs v1 33)
* Cross-source correlation surfaces

### Phase D-5 — Cost: $0 (all frontend code, no API spend).

## Phase E — Council-level expansion

The project currently has council-level data for QLD only
(Batch R sub-national rollout). Expanding to other states is
the next horizontal data-coverage move.

### Priority order

1. NSW (largest local-government finance disclosure regime).
2. VIC.
3. WA + SA.
4. TAS + ACT + NT (smaller populations + simpler structures).

### Per-state work

* Find each state's local-government disclosure register URL.
* Verify licence (most are CC-BY or equivalent).
* Build deterministic parser per state's data format.
* Load into `influence_event` with `chamber='council'` + the
  state-jurisdiction party_id as `recipient_party_id`.
* Add council to map mode toggle in App.tsx.

### Cost: $0 (deterministic data load).

### Status: post-launch.

## Phase F — LLM Stages 5-15 (post-launch refinements)

Per `docs/llm_strategy_full_stack.md`, Stages 5+ shipped as
post-launch refinements for the analytical surface. Priority
order:

1. **Stage 5: Hansard speech-level metadata** — ~$300/term.
   Surfaces "MP X advocated for / opposed industry Y" as a
   correlation alongside donations + voting. Highest analytical
   ROI.
2. **Stage 6: Committee submissions** — ~$360/2yr. Lobbying-
   by-formal-submission visibility.
3. **Stage 7: ANAO audit findings** — ~$275/5yr. Identifies
   contracts already flagged by the audit office.
4. **Stage 8: NACC + integrity commission reports** — ~$50/yr.
   Direct-corruption-finding linkage.
5. **Stage 9: FITS (foreign influence) descriptions** — ~$20.
   Foreign-influence visibility.
6. **Stage 10: Modern Slavery Statements** — ~$185/yr.
   Supply-chain risk linkage.
7. **Stage 11: State Hansard (NSW + VIC pilot)** — ~$300/year.
8. **Stage 12: Senate Estimates Q&A** — $400/term. Step-change
   feature (most direct accountability surface).
9. **Stage 13: Question Time daily Hansard** — $300/term.
10. **Stage 14: Treasury / Finance / Health FOI logs** — $100.
11. **Stage 15: Royal Commission archives** — $1000+ per
    commission. Historical reconstruction surface.

### Total post-launch LLM budget: ~$3,500-7,000 USD over 12-24 months.

## Phase G — Public-launch polish

### Phase G-1 — Performance + caching

* Materialised views for the cross-correlation surfaces (refresh
  nightly via `make verify` cron).
* CDN edge caching for `/api/coverage`, `/api/stats`,
  `/api/industry-aggregate`.
* Postgres performance pass: `EXPLAIN ANALYZE` on every public
  endpoint; aim for p99 ≤ 100 ms.

### Phase G-2 — Press kit + FAQ

* `docs/press_kit.md` — one-pager for journalists with the
  headline findings (BAE $1.4B contracts + $170k donations,
  property_dev $296M+$1.16B, etc.).
* `docs/faq.md` extension — add FAQ for the new endpoints +
  cross-correlation surfaces.
* `docs/worked_example.md` extension — add a "compare two
  ministers" walkthrough.

### Phase G-3 — Letter follow-ups

* APH + AEC GIS exception-letter status. The provisional
  approvals (Batch L) carry through; written replies archive
  under `docs/letters/replies/` when received.

### Phase G-4 — Final reproducibility verify

* `make reproduce-federal` end-to-end runs against a fresh DB.
* Public mirror's CI workflows green for 30+ days.
* CITATION.cff verified by Zenodo / similar academic-citation
  registry (optional but adds credibility).

### Cost: $0 (all polish; no API spend).

## What I'm executing RIGHT NOW (2026-05-02)

1. ✅ Strategic plan landed (this document).
2. **Stage 2 ROI full corpus run** in background (~$30 USD, ~30 min).
3. **Stage 4b lobbyist scaffolding** — schema + scaffolding for
   Federal Lobbyist Register loader.
4. **Frontend MinisterVotingPanel** — drill-down embedded in
   DetailsPanel.
5. **Frontend ContractDonorOverlapPanel** — drill-down embedded
   in EntityProfilePanel.
6. **Stage 1 v2 completes in background** — loader + IRR + final
   commit when it does.

## How to amend this plan

Same governance as `docs/design_decisions.md`: substantive
changes require a commit to the public mirror with a clear
rationale. The `Last updated` date at the top is bumped on
every revision. New phases append; don't rewrite history.
