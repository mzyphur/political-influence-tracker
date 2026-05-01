# Design Decisions Log

**Last updated:** 2026-05-01

**Purpose:** chronological record of every substantive design
choice the project has made, with rationale, alternatives
considered, and the trade-offs accepted. A reader who wants to
verify the project's methodological soundness — or who wants to
fork the project for a different jurisdiction — should be able to
read this document and understand exactly *why* each piece of the
architecture is the way it is.

This is the project's research-methods companion to:

* `docs/scientific_validation_protocol.md` — the formal methods
  document (statistical thresholds, IRR procedure, claim discipline).
* `docs/influence_correlation_gaps.md` — the strategic stocktake
  of what's done vs what's missing.
* `docs/sector_taxonomy_evolution.md` — the v1→v2 sector-split
  decision in particular.
* `docs/build_log.md` — the chronological commit narrative.

## Table of contents

1. [Foundational architecture decisions](#1-foundational)
2. [Evidence-tier separation](#2-evidence-tiers)
3. [Hybrid LLM-assisted extraction](#3-hybrid-llm)
4. [Sector + policy-topic taxonomy choices](#4-taxonomy)
5. [Reliability + audit infrastructure](#5-reliability)
6. [Cross-source correlation views](#6-correlation)
7. [Portfolio + ministerial responsibility mapping](#7-portfolio)
8. [Voting record integration](#8-voting)
9. [Reproducibility commitments](#9-reproducibility)
10. [Public-launch readiness criteria](#10-launch)
11. [Things we explicitly chose NOT to do](#11-not-doing)

---

## 1. Foundational architecture <a name="1-foundational"></a>

### 1.1 Federal-first launch (May 2026 target)

**Decision:** prioritise federal coverage to a launch-ready state
before expanding deeper into state and local. State donations
data is loaded for 8 jurisdictions (NSW, VIC, QLD, SA, WA, TAS,
ACT, NT); council-level data is QLD-only.

**Rationale:** federal data is denser, more comprehensive, and
more politically salient. State + council expansion benefits from
the federal pipeline's testing.

**Trade-off:** state + council launches will land later than they
would under a parallel-development strategy.

**Alternatives considered:**
- Federation-of-state launches (one state at a time): rejected
  because most journalism + research focuses federal-first.
- Federal-only forever: rejected because state + council corruption
  patterns are at least as significant.

### 1.2 PostGIS + FastAPI + React stack

**Decision:** Postgres 16 + PostGIS for the data layer; FastAPI
(Python 3.11+) for the API; Vite + React + MapLibre for the
frontend. Docker-Compose for local dev.

**Rationale:** all open-source, mature, well-documented, and the
operations docs lean on standard observability (psql,
docker-compose logs, etc.). PostGIS is critical for the geo joins
(electorate boundaries × postcode crosswalk × demographic data).

**Trade-off:** non-trivial setup for casual contributors. Mitigated
by `make reproduce-federal` end-to-end script.

### 1.3 AGPL-3.0 source code licence

**Decision:** the source code is licensed under AGPL-3.0 (strong
copyleft). Source data carries upstream publishers' separate
licences as documented in `docs/source_licences.md`.

**Rationale:** maximises public-good outcomes — anyone who runs
this software for the public AND deploys modifications must share
those modifications. Eliminates the "private fork" risk where a
political actor takes the code, changes the methodology, and
ships an opaque variant.

**Trade-off:** AGPL is incompatible with proprietary integrations.
Forks adopting MIT/Apache for commercial purposes are blocked.

**Alternatives considered:**
- MIT: rejected (private-fork risk).
- GPL-3.0 (without "Affero"): rejected (network-use loophole).
- CC-BY-SA: rejected (not a software licence per Creative Commons
  guidance).

---

## 2. Evidence-tier separation <a name="2-evidence-tiers"></a>

### 2.1 Three tiers, never summed

**Decision:** every claim carries an evidence tier:
* **Tier 1** — direct deterministic parse of public records.
* **Tier 2** — LLM-assisted classification of tier-1 inputs.
* **Tier 3** — modelled / inferred (per-share allocations,
  party-mediated exposure estimates).

Tier-1, tier-2, and tier-3 amounts are NEVER summed into a single
"money received" headline. They appear side-by-side with explicit
tier labels.

**Rationale:** the project's most important invariant. Conflating
tiers misleads readers and exposes the project to legitimate
methodological criticism. Each tier has different uncertainty
characteristics; summing them hides that.

**Implementation guards:**
* `test_loader_does_not_change_direct_representative_money_totals`
  — pytest gate.
* SQL views (`v_contract_donor_overlap`,
  `v_industry_influence_aggregate`,
  `v_contract_minister_responsibility`,
  `v_donor_recipient_voting_alignment`) define separate columns
  per tier; never `SUM(tier1) + SUM(tier2)`.
* Schema CHECK constraints reject out-of-enum LLM outputs.

### 2.2 Direct-money invariant

**Decision:** any change to loaders that touch
`influence_event.amount` for direct (not party-mediated) records
must produce byte-identical totals before and after the change.
Test guard: `test_loader_does_not_change_direct_representative_money_totals`.

**Rationale:** the project surfaces direct-disclosed person-level
amounts as the most authoritative figure on every MP profile. If
that number drifts due to a refactor, the public claim becomes
unreliable.

---

## 3. Hybrid LLM-assisted extraction <a name="3-hybrid-llm"></a>

### 3.1 Deterministic-first, LLM-where-deterministic-fails

**Decision:** every data domain is extracted deterministically
first. LLMs are added only where deterministic methods have known
coverage gaps (e.g. classifying 28k entities into 33 sectors is
infeasible to hand-curate; tagging 73k contract descriptions to
policy topics same).

**Rationale:** deterministic methods are byte-identical
reproducible, lower-cost, and don't carry the model-bias risks of
LLMs. Reaching for an LLM when a regex would do is a smell.

**Boundaries:**
* Money flows: NEVER LLM-extracted (would breach the byte-identical
  invariant).
* Industry classification of entities: LLM-extracted (Stage 1).
* Contract topic tagging: LLM-extracted (Stage 3).
* Register of Interests deep extraction: LLM-extracted (Stage 2).

### 3.2 Anthropic Claude over Google Gemini

**Decision:** use Anthropic Claude (Sonnet 4.6) as the LLM
provider rather than Google Gemini.

**Rationale:** Claude shows higher tool-use schema-adherence rates
in our pilot tests + lower hallucination on enum constraints +
better PDF understanding for the ROI extraction. The agent
performing this work has acknowledged its bias (it IS Claude) and
strongly recommended Claude on technical grounds, with the
project lead concurring.

**Mitigation against single-provider risk:** the `LLMClient`
abstraction at `backend/au_politics_money/llm/client.py` is
provider-specific (Anthropic-only as of 2026-05-01); switching
providers is a focused refactor of one file. The cache layer is
provider-agnostic.

**Trade-off:** project budget cycles through Anthropic (~$13 USD
spent so far against the $1k AUD envelope; full corpus runs
estimated at ~$420 USD). Acceptable.

### 3.3 Sonnet 4.6 over Haiku 4.5 (Stage 3 v1→v2 upgrade)

**Decision:** initial Stage 3 v1 used Haiku 4.5 ($0.0029/contract,
fast); pilot revealed one schema-mismatch hallucination in 500
contracts ("furniture" not in the 33-sector enum). Project lead
direction: upgrade to Sonnet 4.6 (~3× cost; better enum adherence)
for Stage 3 v2.

**Rationale:** the project's claim-discipline rule prefers a hard
schema failure to a hallucinated value, but Sonnet's cleaner
adherence reduces noise. The cost increase is trivial against
budget.

**Inter-rater reliability check (post-upgrade):** Haiku v1 vs
Sonnet v2 on the same 200 contracts:
* Sector κ = 0.76 (substantial — Landis-Koch).
* Procurement-class κ = 0.71 (substantial).
* Policy-topics mean Jaccard = 0.81; micro-F1 = 0.84.

Conclusion: the upgrade preserved classification quality (the
two models substantially agreed) while eliminating the
schema-mismatch failure mode.

### 3.4 Prompt caching pre-flight check

**Decision:** every system instruction must be at least ~1,500
tokens (well above Anthropic's 1,024-token cache floor) to ensure
prompt caching fires reliably.

**Rationale:** Stage 3 v1's system instruction was 1,099 tokens
— right at the Haiku cache floor. Caching never fired
(`cache_read_input_tokens=0` across all v1 cache files). v2's
expansion to ~3,666 tokens triggers caching reliably (every v2
cache file shows `cache_read_input_tokens=3666`), saving ~63%
of input cost.

**Operational rule:** worked examples + sector-rubric tables +
worked-example #E-style "this is NOT a valid sector" reinforcement
all push system instructions above the threshold and improve
classification quality.

### 3.5 Concurrency 8-10 (sync) for synchronous mode

**Decision:** the synchronous-mode default `--concurrency` is
8-10 (varies by stage); higher concurrency just queues threads
rather than increasing throughput due to Anthropic's input-tokens-
per-minute (TPM) rate limits.

**Rationale:** Stage 3 v1 pilot at concurrency=50 hit the org's
450k input-TPM limit on Haiku; 17 of 500 contracts errored with
rate_limit_error. Recovery at concurrency=8 succeeded cleanly.
For full-corpus runs (>10k records), use the Anthropic Batches
API (50% off, async, separate rate limits, supports tool-use +
caching).

### 3.6 Hash-cache reproducibility chain

**Decision:** every LLM call's input + output is archived at
`data/raw/llm_extractions/<task>/<sha256>.{input,output}.json`.
The SHA-256 includes model_id + prompt_version + temperature +
max_tokens + system_instruction + user_message + response_schema.

**Rationale:** a researcher who clones the repo + downloads the
cache (say from a public release artefact) can reproduce any
LLM-extracted record byte-for-byte WITHOUT an API key. The cache
is the project's reproducibility surface.

**Cost:** one full cache directory at full Stage 3 corpus (~73k
contracts × 2 files × ~5KB) = ~700 MB. Manageable.

### 3.7 Schema-strict tool-use over free-text JSON

**Decision:** every LLM extraction uses Anthropic's tool-use API
with `tool_choice = {"type": "tool", "name": "record_extraction"}`
forcing the model to emit a structured JSON payload validated
against the response schema.

**Rationale:** more reliable than "respond with JSON in the
following format" (free-text). The Anthropic API server-side-
validates `enum` constraints (mostly — see Stage 3 v1's
"furniture" exception). Belt-and-braces client-side enum
re-checking catches the residual cases.

---

## 4. Sector + policy-topic taxonomy <a name="4-taxonomy"></a>

### 4.1 v1: 33-sector + 24-policy-topic taxonomies

**Decision:** the project's sector taxonomy v1 has 33 codes;
policy-topic taxonomy has 24 codes. Both are exhaustive (no
"other" catch-all beyond `unknown` / `general_administration`).

**Rationale:** Australia's political-influence story is dominated
by ~30 industries; finer granularity isn't worth the analytical
overhead at v1.

### 4.2 v2: 40-sector taxonomy (energy + mining splits)

**Decision (2026-05-01):** the v1 `fossil_fuels` and `mining`
buckets are too coarse for Australia. v2 splits them:

* `fossil_fuels` → coal / gas / petroleum / uranium / fossil_fuels_other (5)
* `mining` → iron_ore / critical_minerals / mining_other (3)
* 30 other sectors unchanged.

**Total v2 sectors: 40.**

**Rationale:** Australia is a coal export superpower (≈$60B/year)
AND an LNG export superpower (≈$80B/year). Coal donors and gas
donors pursue different policy agendas (climate + export, vs
domestic-gas + LNG-export). Conflating them into `fossil_fuels`
loses the analytical resolution the cross-correlation views need.

**Migration path:** schema 043 extends the CHECK constraints
additively — every v1 code remains valid, the 8 new codes are
appended. v1-tagged rows stay v1; v2 is a new prompt version with
its own cached responses + DB rows.

**Cost:** ~$100 USD to re-run Stage 1 v2 over the 28k entity
corpus.

**Trade-off:** during the v1→v2 transition, cross-correlation
views see a mix of v1 + v2 sector codes (e.g. some entities
tagged `fossil_fuels` v1 + others tagged `coal` v2). The
methodology page documents this transparently.

### 4.3 Policy-topic taxonomy: They Vote For You alignment

**Decision:** policy-topic linkages on divisions
(`division_topic.method='third_party_civic'`) are imported from
They Vote For You's CC-BY data. We do NOT replicate the topic
labels — we use TVFY's labels verbatim.

**Rationale:** TVFY has spent years curating policy-topic
linkages with public-domain methodology. Replicating that work
would be redundant and increase divergence from a trusted civic
data source.

---

## 5. Reliability + audit infrastructure <a name="5-reliability"></a>

### 5.1 Cohen's kappa as the production-use threshold

**Decision:** every LLM stage must show **Cohen's kappa ≥ 0.60
(substantial — Landis-Koch 1977)** against either a different
model version, a manual reviewer, or a deterministic
cross-validator before its outputs are admitted to public surfaces.

**Rationale:** kappa adjusts observed agreement for chance
agreement. The 0.60 threshold is the conventional substantial-
agreement threshold from the most-cited interpretive paper.

**Recorded baselines:**
* Stage 3 (Haiku v1 vs Sonnet v2 on n=200 same contracts):
  sector κ = 0.76, procurement κ = 0.71, topics Jaccard 0.81,
  topics micro-F1 0.84. ALL above threshold; v2 cleared for
  production.

### 5.2 Manual audit at every pilot

**Decision:** for every LLM stage pilot, the project lead
manually audits ~10 random records against source data and
classifies each as correct / acceptable / wrong / summary_issue.
If wrong-rate > 10%, the prompt or model is revised.

**Stage 3 v2 audit (2026-05-01):** 7 correct / 2 acceptable / 1
weak / 0 wrong. Wrong-rate 0%. v2 cleared for production.

### 5.3 Confidence-label NOT relied on for downstream weighting

**Decision (2026-05-01):** the LLM's `confidence: high|medium|low`
label is reported to consumers but NOT used to weight extractions
in cross-correlation views. Both Sonnet 4.6 and Haiku 4.5 emit
"high" for ~99% of records (confidence κ = 0.06 between models =
slight agreement; the label is essentially uniform).

**Rationale:** the label has near-zero discriminative information.
Treating "medium"/"low" rows as second-class would arbitrarily
exclude well-classified rows. The project relies on the
classification itself + the IRR-quantified model agreement.

---

## 6. Cross-source correlation <a name="6-correlation"></a>

### 6.1 Strict tier separation in views

**Decision:** every cross-source correlation view (e.g.
`v_contract_donor_overlap`,
`v_industry_influence_aggregate`,
`v_contract_minister_responsibility`,
`v_donor_recipient_voting_alignment`) surfaces tier-1 deterministic
amounts and tier-2 LLM-tagged amounts as **separate columns**.
The view never `SUM(donor_money_aud + contract_value_aud)`.

**Rationale:** preserves the evidence-tier invariant (decision 2.1).
A consumer who needs "total exposure" can compute it themselves
with explicit tier labels visible.

### 6.2 Exact-match name-normalisation only

**Decision:** the supplier→entity match in `v_contract_donor_overlap`
uses exact lower-cased equality on
`normalize_supplier_name(metadata->>'supplier_name') =
entity.normalized_name`. NO fuzzy matching.

**Rationale:** false-positive overlaps would create real harm —
"supplier X donated $Y" claims that aren't true. The same
discipline as the AEC Register branch resolver (no fuzzy similarity).

**Trade-off:** under-counts overlaps where one party uses
"PwC Australia" and the other uses "PricewaterhouseCoopers
Australia". Mitigation: the `entity` table normalises common
aliases at load time.

### 6.3 No causation labels, ever

**Decision:** every cross-source view carries a
`claim_discipline_note` column with text like "no causation
implied; cross-source temporal correlation only" baked into
every row.

**Rationale:** the project surfaces correlation; consumers
interpret. Anything stronger would require a degree of evidence
the project doesn't claim to have.

---

## 7. Portfolio + ministerial responsibility <a name="7-portfolio"></a>

### 7.1 Three-table model: cabinet_ministry + minister_role + portfolio_agency

**Decision:** schema 044 introduces three tables to model the
portfolio→agency→minister mapping:
* `cabinet_ministry` — one row per ministry composition (with
  effective dates).
* `minister_role` — one row per (person, role, ministry).
* `portfolio_agency` — one row per (ministry, portfolio, agency).

**Rationale:** this models reality: portfolios change at each
ministry reshuffle; multiple ministers can hold the same
portfolio (full + assistant); multiple agencies sit under one
portfolio. A flat "person ↔ agency" table would lose all temporal
information.

### 7.2 Hand-curated initial seed (Albanese 2nd Cabinet)

**Decision:** schema 045 hand-curates the Albanese 2nd Cabinet
(post-2025 election) with 1 ministry + 51 portfolio-agency
mappings + 20 cabinet ministers (19 resolved to person_id).

**Rationale:** AAO scraping is a future automation; for the
launch-readiness surface, hand-curation is faster and
verifiable.

**Trade-off:** assistant ministers + parliamentary secretaries
+ historical ministries are not yet covered. Documented as
future work in `docs/influence_correlation_gaps.md`.

**Coverage achieved:** 489 of 499 distinct contracts (98%) in
the Stage 3 pilot data successfully joined to a minister +
portfolio. The 10 unjoined are agencies not in the seed
(addressable by extending the seed).

---

## 8. Voting record integration <a name="8-voting"></a>

### 8.1 They Vote For You data via division_topic

**Decision:** policy-topic linkages on parliamentary divisions
are imported from They Vote For You (CC-BY licensed) under
`division_topic.method='third_party_civic'` with `confidence=0.7`
(reflecting the third-party-civic provenance).

**Rationale:** TVFY has years of curated topic linkages.
Re-deriving them would be redundant.

### 8.2 No automatic "alignment" labels in v_donor_recipient_voting_alignment

**Decision:** the view that joins donors to recipient MPs to
voting topics surfaces RAW counts (aye / no / division_count /
rebellion_count). It does NOT auto-label "donor-aligned"
vs "donor-opposed" votes.

**Rationale:** "alignment" implies the donor *intended* the vote
outcome — that's a causation claim. Raw counts let consumers
draw their own conclusions with the raw evidence visible.

---

## 9. Reproducibility commitments <a name="9-reproducibility"></a>

### 9.1 Source provenance on every datum

**Decision:** every database row that landed via a source-
attributed loader carries `source_document_id` → `source_document`
→ `source` (URL, licence, fetch timestamp). The full document
body is archived locally + reproducible via `make reproduce-federal`.

**Rationale:** allows independent replication. Source-licence
terms are captured verbatim in `docs/source_licences.md`.

### 9.2 Code provenance via git + public mirror

**Decision:** the public mirror at
https://github.com/mzyphur/political-influence-tracker is the
canonical source. Every release tag pins a commit SHA. The
methodology page wraps the SHA in a `commit/<sha>` link via the
`METHODOLOGY_REPO_URL` env var.

### 9.3 Model + prompt provenance for LLM rows

**Decision:** every LLM-extracted record carries
`extraction_method` + `prompt_version` + `llm_model_id` +
`llm_response_sha256`. The cache file is reproducible from
prompt + entity input.

### 9.4 Statistical provenance for aggregates

**Decision:** every aggregate on the public app cites the SQL
view, the DB snapshot date, and the evidence tier.

### 9.5 CITATION.cff for academic citation

**Decision:** the public mirror includes `CITATION.cff` (Citation
File Format). References include Landis & Koch (1977) for the
kappa interpretation thresholds.

---

## 10. Public-launch readiness <a name="10-launch"></a>

### 10.1 May 2026 federal launch criteria

**Decision:** federal launch requires:

* **Source-licence verified for every data source.** 10/10 done.
* **AGPL-3.0 licence applied + public mirror live.** Done.
* **Cross-source correlation surfaces working.** Done — multiple
  views shipped in Batch BB.
* **Portfolio→agency→minister mapping for current ministry.**
  Done — 98% pilot coverage.
* **Inter-rater reliability ≥ 0.60 substantial on every LLM stage.**
  Done — Stage 3 v2 sector κ = 0.76.
* **Manual audit ≤ 10% wrong-rate on every LLM stage.** Done —
  Stage 3 v2 wrong-rate = 0%.
* **Reviewable methodology page.** Done — version-stamped, links
  to commit SHA, links to all reference docs.

### 10.2 Things that ship LATER (not blocking launch)

* Stage 1 v2 (40-sector taxonomy re-run): post-launch.
* Stage 4b lobbyist register: post-launch.
* Stage 4d ASIC beneficial ownership: post-launch.
* Stage 5+ (Hansard, committee submissions, FOI, Royal Commissions):
  post-launch refinements.
* State + council portfolio mapping: post-launch.

---

## 11. Things we explicitly chose NOT to do <a name="11-not-doing"></a>

### 11.1 No fuzzy matching in resolvers

**Decision:** the AEC Register branch resolver, the supplier→entity
matcher, and the agency-name→portfolio matcher all use exact-
match (with documented alias rules) only.

**Why not:** false-positive matches would manufacture false
"influence" claims. The project's harm-floor is zero false
positives; we accept under-coverage as the trade-off.

### 11.2 No "total influence" aggregate metric

**Decision:** the project does NOT compute a per-MP / per-entity
"total influence score" that combines multiple evidence tiers
into one number.

**Why not:** any such metric requires evidence-tier weighting
choices that are inherently subjective. Surfacing the underlying
tier-1 + tier-2 + tier-3 rows separately respects the consumer's
analytical autonomy.

### 11.3 No predictive modelling

**Decision:** the project does NOT predict future donor behaviour,
contract awards, or vote outcomes.

**Why not:** prediction implies causation; the project surfaces
correlation only. Predictive models would also require
maintaining model accuracy commitments, which is out of scope.

### 11.4 No sentiment analysis on disclosures

**Decision:** the project does NOT classify disclosures as
"corrupt" / "questionable" / "clean" or any similar normative
label.

**Why not:** legal exposure + scope creep + fundamental
disagreement among researchers about what constitutes corruption
in different contexts. The project surfaces facts; consumers
adjudicate.

---

## How to amend this document

This is a living document. Substantive changes require:

1. A commit to the public mirror with a clear rationale in the
   commit message.
2. The `Last updated` date at the top bumped.
3. New decisions appended as new sub-sections (don't rewrite
   history; build on it).

Decisions made BEFORE this document was written (Batches A
through Z) are documented retroactively in `docs/build_log.md`
+ the repository's git log. Decisions from Batch AA onwards are
documented here in real time.
