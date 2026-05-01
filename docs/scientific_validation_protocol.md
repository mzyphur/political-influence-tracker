# Scientific Validation Protocol

**Last updated:** 2026-05-01

**Scope:** every public claim, statistic, classification, or
correlation surfaced by this project — across both the deterministic
extraction layer (tier 1 evidence) and the LLM-assisted extraction
layer (tier 2 evidence).

**Purpose:** specify the procedures, statistical thresholds,
reliability checks, and bias acknowledgments under which a claim
becomes admissible to the public surface. The project commits to
reproducible, source-attributed, falsifiable evidence — not
journalistic narrative wrapped around correlations.

This document is structured as a research-methods section. A
serious researcher (sociologist, computational social scientist,
data journalist) reading the project's outputs should find here
every protocol they need to:

1. Understand what was measured.
2. Reproduce any statistic byte-for-byte.
3. Identify and apply the appropriate uncertainty bounds.
4. Adapt the methodology for related research.

## 1. Evidence tiers (claim discipline)

The project's foundational rule, never relaxed:

| Tier | Source | Examples | Where surfaced |
|---|---|---|---|
| **1 — Deterministic + source-attributed** | Direct parse of public registers | AEC donations CSV, APH register Senate JSON, AusTender contract CSV | Any "MP X disclosed receiving $Y from donor Z on date D" claim |
| **2 — LLM-assisted classification of tier-1 inputs** | Sonnet 4.6 + versioned prompt | entity_industry_classification, austender_contract_topic_tag, llm_register_of_interests_observation | Any "donor Z is in industry W" or "contract C touches policy area P" claim |
| **3 — Modelled / inferred** | SQL views aggregating tiers 1+2 | postcode→electorate share allocations, party-mediated exposure estimates | Any per-share / per-allocation claim with "Est. exposure" prefix |

**Hard rule:** values from different tiers are NEVER summed into a
single number. They appear side-by-side with explicit tier labels
on every UI surface, every API response, every data export. A user
seeing "Industry X received $Y in donations AND $Z in contracts"
sees TWO numbers, not their sum.

**Test guards:**
* `test_loader_does_not_change_direct_representative_money_totals`
  — guards byte-identical totals across loader changes.
* `austender_contract_topic_tag` schema CHECK constraints reject
  out-of-enum LLM hallucinations.
* SQL views (`v_contract_donor_overlap`,
  `v_industry_influence_aggregate`) define separate columns for
  tier-1 and tier-2 aggregates.

## 2. Reproducibility chain

Every public-facing claim must travel with a reproduction recipe.
The project commits to four reproducibility surfaces:

### 2.1 Source provenance

Every datum in the database carries a `source_document_id` →
`source_document` row → `source` row identifying the source URL,
licence, and fetch timestamp. The full document body is archived
(or its byte-identical regeneration is reproducible from the
fetch URL via `make reproduce-federal`). Source licence terms are
captured verbatim in `docs/source_licences.md`.

### 2.2 Code provenance

Every transformation is in version control. The repo is mirrored
publicly at https://github.com/mzyphur/political-influence-tracker
under AGPL-3.0. Every release tag pins the commit SHA used to
build it. The methodology page wraps the SHA in a clickable
`commit/<sha>` link automatically (via
`frontend/scripts/sync-methodology-version.mjs`).

### 2.3 Model + prompt provenance (LLM stages)

Every LLM-extracted record carries:
* `extraction_method` — e.g. `'llm_austender_topic_tag_v2'`.
* `prompt_version` — the exact `prompts/<task>/v<N>.md` file used.
* `llm_model_id` — pinned model snapshot (e.g. `claude-sonnet-4-6`).
* `llm_response_sha256` — the SHA-256 envelope hash; the input +
  output of the API call is archived at
  `data/raw/llm_extractions/<task>/<sha256>.{input,output}.json`.

A researcher who clones the repo + downloads the cache directory
can reproduce any LLM extraction byte-for-byte without an API key.

### 2.4 Statistical provenance

Every statistic on the public app cites:
* The SQL view or query that produced it (linked to
  `docs/methodology.md`).
* The DB snapshot date.
* The evidence tier (1, 2, or 3).
* Any uncertainty bound, where applicable.

## 3. Inter-rater reliability (LLM tier 2)

LLM classifications are subject to model-specific biases.
The project's mitigation is **structured cross-validation**:
every LLM stage runs through one or more reliability checks
before its outputs are admitted to the public surface.

### 3.1 Methodology

When two raters (e.g. two model versions, or model vs human)
classify the same items, agreement is quantified with
**Cohen's kappa (κ)** for nominal categories and
**Jaccard similarity** for multi-label sets:

\[
\kappa = \frac{p_o - p_e}{1 - p_e}
\]

where \(p_o\) is observed agreement and \(p_e\) is expected
agreement under marginal independence.

**Landis-Koch (1977) interpretation thresholds:**

| κ | Interpretation |
|---:|---|
| ≥ 0.81 | almost perfect |
| 0.61–0.80 | substantial |
| 0.41–0.60 | moderate |
| 0.21–0.40 | fair |
| ≤ 0.20 | slight (or worse-than-chance) |

The project's **acceptance threshold for production use is κ ≥
0.60** (substantial). Lower κ requires either prompt revision
(version bump), model upgrade, or restriction of the surface to
high-confidence rows only.

For multi-label attributes (e.g. `policy_topics`):
* Mean Jaccard across pairs.
* Per-label one-vs-rest κ.
* Macro-averaged κ (mean across labels).
* Macro-F1 + micro-F1.

### 3.2 Reliability tooling

Computation: `scripts/compute_llm_inter_rater_reliability.py`.
Output: `data/audit/llm_inter_rater_reliability/<task>/<ts>.{json,md}`.

The script supports three task types:
* `austender_contract_topic_tag` — joins on `contract_id`.
* `register_of_interests_extraction` — joins on
  `(source_id, section_number)`; computes item-count match rate
  + item-set Jaccard.
* `entity_industry_classification` — joins on `entity_id`.

### 3.3 Recorded baselines

| Stage | Comparison | Sector κ | Procurement κ | Topics J | Date |
|---|---|---:|---:|---:|---|
| 3 (AusTender) | Haiku 4.5 v1 vs Sonnet 4.6 v2 (n=200) | **0.76** (substantial) | **0.71** (substantial) | **0.81** mean Jaccard | 2026-05-01 |

**Interpretation:** Sonnet 4.6 v2 and Haiku 4.5 v1 substantially
agree on sector + procurement_class + policy_topics. Confidence
labels (which both models almost-uniformly emit as `high`) have
near-zero discriminative κ — the confidence label is uninformative
and should not be relied on for downstream weighting. Treat all
v2 outputs as roughly homogeneous in quality; rely on the
classification, not the self-reported confidence.

### 3.4 What we will additionally do at scale

When the full Stage 3 corpus (~73,458 contracts) is tagged:
* Re-run IRR Sonnet vs Sonnet (test-retest, force-refresh) to
  verify stability under temperature=0 — should show κ ≈ 1.0
  via the cache invariant.
* Sample 200 contracts for a manual reviewer audit; compute
  human-vs-LLM κ.
* Bootstrap 95% CIs at n>5,000 (currently the n=200 sample is
  too small for stable per-class CIs).

## 4. Sample audit protocol (manual)

For every LLM stage pilot, the project runs a manual audit by
the maintainer:

1. Random 10 records (deterministic seed=42 for reproducibility).
2. For each: read source data, compare with LLM output.
3. Classify each as `correct` / `acceptable` / `wrong` /
   `summary_issue`.
4. Aggregate into `data/audit/<stage>/<ts>.manual_audit.md`.
5. If wrong rate > 10%, escalate: prompt revision, model upgrade,
   or scope reduction.

**Stage 3 v2 audit (n=10, 2026-05-01):** 7 correct, 2 acceptable
judgment calls, 1 weak (medium-confidence flagged correctly), 0
wrong. Wrong rate: 0%. Verdict: production-grade.

## 5. Bias acknowledgments

The project commits to publicly documenting known biases:

### 5.1 LLM training-data bias

Claude Sonnet 4.6 + Haiku 4.5 are trained on text that includes
public Australian political reporting. They may have:
* Familiarity with major parties / well-known MPs / well-known
  donors that exceeds familiarity with smaller / regional / less-
  reported entities.
* Implicit framing assumptions about which industries are
  "controversial" (e.g. fossil_fuels, gambling, defence, tobacco)
  vs "neutral" (e.g. agriculture, education).

**Mitigation:** the prompt's sector taxonomy is enumerated
explicitly with the same definitional weight per sector. The
model is instructed to choose `unknown` when uncertain rather
than guess. The IRR check between two model versions provides
some bias-vs-bias triangulation.

### 5.2 Source-coverage bias

Federal-level coverage is comprehensive. State-level coverage
varies (NSW, VIC, QLD, SA, WA, TAS, ACT, NT have differing
disclosure regimes and digitisation completeness). Local-
council coverage is presently QLD-only.

**Mitigation:** the public surface labels every claim with its
jurisdiction; users see "federal" coverage as ⓕ vs "state-only"
as ⓢ. State-level coverage gaps are documented in
`docs/source_licences.md` and `docs/influence_correlation_gaps.md`.

### 5.3 Disclosure-threshold bias

Donations / gifts below the disclosure threshold are not
captured. Thresholds vary by jurisdiction + year:
* Federal donations: $14,500 (2023-24); subject to indexation.
* Federal MP gifts: $750.
* State thresholds: documented per-jurisdiction in
  `docs/influence_network_model.md`.

**Mitigation:** the public surface always quotes the relevant
threshold + cautions that "below threshold" influence may exist
but is not measurable from public data.

### 5.4 Beneficial-ownership bias

Donations made via corporate vehicles or trusts that obscure
the ultimate beneficial owner are recorded against the named
entity, not the controlling person. This systematically
under-counts influence by sophisticated actors who use such
vehicles.

**Mitigation:** Stage 4d (ASIC + ACNC beneficial-ownership data)
is planned post-launch. Meanwhile, the public surface flags this
as a known limitation.

### 5.5 Contract-only-since bias

AusTender CSV bulk export covers public-published contracts only.
Highly classified procurement (e.g. some defence work) may not
appear in the public dataset.

**Mitigation:** documented; the public surface notes the
"public-disclosed contracts only" caveat.

## 6. Claim-discipline microcopy (UI standard)

Every public-app surface uses these standard phrases:

* "Est. exposure $X" (NEVER just "$X" for tier-3 modelled values).
* "denominator scope: current office-term party representatives
  only (asymmetric — see methodology)" (next to per-share figures).
* "Equal-share values are analytical exposure estimates only."
* "Not a wrongdoing claim."
* "Do not claim causation or improper conduct."
* "Source-backed candidate" (postcode lookup with confidence
  qualifier).
* "Provisionally approved" (when source-licence reply is pending).

These are coded into the frontend at `DetailsPanel.tsx` +
`App.tsx` and grep-checked in the claim-discipline sweep
(Batch D #4, 2026-04-30).

## 7. Falsifiability

Every public claim should be falsifiable in finite work by an
independent researcher. To demonstrate falsifiability:

* **Tier 1 claim** (e.g. "MP X received $Y from donor Z"):
  reproducible by re-running `make reproduce-federal` against
  the same source URLs. If the AEC dataset disagrees, the claim
  is wrong.

* **Tier 2 claim** (e.g. "Donor Z is in pharmaceuticals sector"):
  reproducible by re-running `scripts/llm_classify_entities.py`
  with the cached LLM response (no API key needed). If the cache
  envelope disagrees with the live API at the same prompt
  version, the claim is wrong (cache drift).

* **Tier 3 claim** (e.g. "Donor Z's donations gave each ALP
  representative ~$N exposure"): reproducible by recomputing the
  per-share allocation using the documented denominator scope.

## 8. Updates to this document

This protocol is itself version-controlled. Substantive changes
require a commit to the public mirror. The `Last updated` date
at the top is bumped on every revision.
