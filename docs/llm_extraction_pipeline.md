# LLM-Assisted Extraction Pipeline

**Last updated:** 2026-05-01 (Stages 1-3 + cross-source correlation view shipped)

This document is the load-bearing reference for the project's
hybrid LLM-assisted extraction pipeline. It explains:

* The architectural promise: deterministic-first, LLM-where-it-fills-a-gap.
* Reproducibility chain: pinned models, versioned prompts, hash-cached responses.
* Per-stage scope, cost, and operational discipline.
* How a public researcher reproduces any LLM-extracted record without an API key.

The full strategic rationale for adopting hybrid LLM extraction
(rather than going all-in on LLMs or staying purely deterministic)
is in [`docs/build_log.md`](build_log.md) under the Batch AA entry.

## Architectural promises

The project commits to four invariants for every LLM-extracted row:

1. **Determinism at the project layer.** Every LLM input is hashed
   (SHA-256 of the canonicalised prompt + system instruction +
   schema + content + model id + temperature). Hash → cached
   response. Re-running with the same input returns the cached
   output verbatim, so a researcher who clones the repo + downloads
   the cached responses gets byte-for-byte identical extraction
   results without an API key.

2. **Pinned model versions.** Every call records the exact model id
   (e.g. `claude-sonnet-4-6`). The cache key includes the model id,
   so swapping models invalidates the cache by design — old
   classifications stay on disk for audit but are not re-used by a
   new model.

3. **Strict schema validation.** Every LLM response is validated
   against a JSON schema before it's accepted; malformed responses
   are rejected with a structured error rather than silently
   reshaped. The project's claim-discipline rule prefers a hard
   failure over a hallucinated field.

4. **No money-flow extraction.** The byte-identical-totals
   invariant remains the top rule. LLM-extracted rows are tagged
   with `extraction_method='llm_<task>_v<n>'` and never feed
   direct-money totals. LLMs only extract `private_interest`,
   `benefit`, `organisational_role`, classification metadata, and
   topic tags.

## Where the LLM pipeline lives

| Path | What |
|---|---|
| `prompts/<task>/v<N>.md` | Versioned prompt for each LLM task. Includes system instruction, user-message template, response schema, and task-specific reproducibility commitment. Public-facing — anyone can audit / fork. |
| `backend/au_politics_money/llm/__init__.py` | Module entry point. Exports `LLMClient`, `LLMResponse`, `LLMCache`. |
| `backend/au_politics_money/llm/client.py` | `LLMClient` — Anthropic-backed client wrapping `messages.create` with strict tool-use schema enforcement, retry-on-rate-limit, prompt caching via `cache_control`, and full-envelope persistence. |
| `backend/au_politics_money/llm/cache.py` | `LLMCache` — file-system-backed SHA-256 hash cache. Cache key includes prompt-version + model id, so prompt revisions invalidate cleanly. |
| `scripts/llm_classify_entities.py` | Stage-1 driver: reads unclassified entities from the DB, calls the LLM, writes JSONL + summary JSON. Supports `--concurrency` for parallel API calls. |
| `scripts/load_llm_entity_classifications.py` | Stage-1 loader: reads JSONL artifacts and lifts them into `entity_industry_classification` rows + (optionally) promotes `entity.entity_type` from `unknown`. |
| `data/raw/llm_extractions/<task>/<sha256>.{input,output}.json` | Per-call envelope cache. **Gitignored** (the cache may be large) but reproducible from the prompt + entity data. A researcher can fetch the cache from a public release artefact. |
| `data/processed/llm_<task>/<UTC-stamp>.{jsonl,summary.json}` | Per-run output artefact. JSONL is one row per classified record; summary JSON has aggregate statistics + cost. Gitignored. |

## Reproducibility chain (the published version)

For any LLM-extracted row visible on the public app:

1. **The row's `extraction_method` field tells you the task + version.**
   Example: `llm_entity_industry_classification_v1`.

2. **The row's metadata blob carries the SHA-256 of the cached LLM
   response.** Look up the cache file at
   `data/raw/llm_extractions/<task>/<sha256>.output.json` — the
   output is verbatim what the model returned.

3. **The corresponding `<sha256>.input.json` carries the full
   request envelope** — the system instruction, the user message,
   the response schema, the model id, the temperature. Together
   these reproduce the exact API call.

4. **The prompt file is in the public repo** at
   `prompts/<task>/v<N>.md`. The system instruction within it is
   what the cache hashed.

5. **A researcher with no API key can verify any classification**
   by fetching the prompt file, the input envelope, and the output
   envelope, and checking that the SHA-256 of the canonicalised
   input matches the filename. If it does, they have the same
   classification the project published.

6. **A researcher with an API key can re-run the same call** by
   loading the input envelope + sending it to Anthropic's API.
   With `temperature=0` and the pinned model id, the response
   should match (modulo the model's own non-determinism, which
   Anthropic minimises but does not eliminate).

## Stage 1 — Entity industry classification

**Status:** complete as of 2026-05-01.
**Model:** `claude-sonnet-4-6` (released 2026-02-17).
**Prompt:** [`prompts/entity_industry_classification/v1.md`](../prompts/entity_industry_classification/v1.md).
**Cost:** ~$100 USD for ~28,300 entities at $0.0035 USD/entity (with prompt caching).
**Concurrency:** 12 parallel workers; full run completes in ~30-90 min.

### What it does

Reads entities from the live database where
`entity_type = 'unknown'` AND the entity has appeared in at least
one `influence_event` row, and classifies each into one of:

* The project's 32 fixed industry sectors (`fossil_fuels`,
  `mining`, `renewable_energy`, `property_development`,
  `construction`, `gambling`, `alcohol`, `tobacco`, `finance`,
  `superannuation`, `insurance`, `banking`, `technology`,
  `telecoms`, `defence`, `consulting`, `law`, `accounting`,
  `healthcare`, `pharmaceuticals`, `education`, `media`,
  `sport_entertainment`, `transport`, `aviation`, `agriculture`,
  `unions`, `business_associations`, `charities_nonprofits`,
  `foreign_government`, `government_owned`, `political_entity`)
  plus `individual_uncoded` and `unknown`.

* One of the project's 14 valid `entity_type` values.

* A confidence label (`high`, `medium`, `low`) and a 1-2 sentence
  evidence note.

### Confidence + entity_type mapping

The LLM uses user-friendly labels. The loader maps them to the
DB's stricter CHECK-constrained values:

| LLM `confidence` | DB `confidence` |
|---|---|
| `high` | `fuzzy_high` |
| `medium` | `fuzzy_high` (still confident enough) |
| `low` | `fuzzy_low` |

| LLM `entity_type` | DB `entity_type` |
|---|---|
| `charity` | `association` |
| `education_institution` | `association` |
| All other 12 values | 1:1 mapping |

### Entity_type promotion rule

The loader inserts `entity_industry_classification` rows for ALL
classifications, but only promotes the `entity.entity_type` field
from `'unknown'` to the LLM-classified type when:

* LLM confidence is `high`, AND
* The new type is NOT `'unknown'`.

Medium/low-confidence reclassifications stay in
`entity_industry_classification` (so the surface is available)
but don't override the catch-all `entity_type` until a human
reviewer confirms.

### Conservative on uncertainty

The v1 prompt instructs the model to return `unknown` with
`confidence: low` when the entity name is opaque (e.g. "ABC
Holdings Pty Ltd", "Smith Family Trust", "1234 Investments",
"Pulse"). This honours the project's claim-discipline rule:
**an honest "I don't know" beats a confidently-wrong sector tag**.

In the 200-entity pilot run, ~7% of entities were classified
`unknown` for exactly this reason. The model is being properly
conservative.

### Cost breakdown (200-entity pilot)

* Total cost: $0.71 USD
* Per-entity: $0.0035 USD
* Cache hits: 9 / 200 (4.5%; from prior canary runs)
* Fresh API calls: 191 / 200
* Tokens: 99,611 input / 27,672 output
* Output rate: ~138 tokens/call (small; the schema's
  `evidence_note` field is the main output)
* With Anthropic prompt caching active, ~4050 of the ~520-token
  per-call input is cached read at 10% pricing, saving ~$0.13
  per 200 calls relative to no caching.

Projected full-run cost (28,300 entities at the pilot rate):
**~$99 USD = ~$155 AUD**, well within the project's $1,000 AUD
LLM-extraction budget.

## How to reproduce a Stage-1 classification yourself

Without an API key:

```bash
# 1. Clone the repo + fetch the cached response (the cache is
#    published as a release artefact; specific URL TBD per the
#    project's release pipeline).
git clone https://github.com/mzyphur/political-influence-tracker.git
cd political-influence-tracker

# 2. Find the SHA-256 of the row you want to verify.
backend/.venv/bin/python -c "
import psycopg, json, sys
conn = psycopg.connect('<your local DB url>')
cur = conn.cursor()
cur.execute('''
    SELECT entity_industry_classification.metadata
    FROM entity_industry_classification
    JOIN entity ON entity.id = entity_industry_classification.entity_id
    WHERE entity.canonical_name = %s
      AND entity_industry_classification.method = 'model_assisted'
''', ('THE PHARMACY GUILD OF AUSTRALIA',))
metadata = cur.fetchone()[0]
print(metadata['llm_response_sha256'])
"

# 3. Open the cached envelope.
cat data/raw/llm_extractions/entity_industry_classification/<sha256>.input.json
cat data/raw/llm_extractions/entity_industry_classification/<sha256>.output.json
```

With an API key (re-running to verify):

```bash
# 1. Set your Anthropic key.
export ANTHROPIC_API_KEY=sk-ant-...

# 2. Run the script with --force-refresh to bypass the cache.
DATABASE_URL=postgresql://... \\
    backend/.venv/bin/python scripts/llm_classify_entities.py \\
        --limit 1
```

## Stages currently shipped

### Stage 2 — Register of Interests deep extraction (LIVE)

* Prompt: `prompts/register_of_interests_extraction/v1.md`.
* Model: `claude-sonnet-4-6`, temperature 0.0, max_tokens 2048,
  tool-use enforcement.
* Schema migration: `backend/schema/040_llm_register_of_interests_observation.sql`.
* Driver: `scripts/llm_extract_register_of_interests.py`.
* Loader: `scripts/load_llm_register_of_interests.py`.
* **Pilot results (2026-05-01):** 100 House register sections;
  68 fresh calls, 31 nil-skipped (preamble + structural nil
  returns), 1 failed; 109 disclosure items extracted across the
  68 substantive sections (~1.6 items/section avg). Cost $0.38 USD
  regular (~$0.0056/section).
* Output schema: `{item_type, counterparty_name, counterparty_type,
  description, estimated_value_aud, event_date, disposition,
  confidence, evidence_excerpt}`. Each disclosure item lands as a
  separate row with verbatim source-text excerpt for audit.
* Item-type taxonomy: 12 codes (`shareholding`, `real_estate`,
  `directorship`, `partnership`, `liability`, `investment`,
  `other_asset`, `gift`, `sponsored_travel`, `donation_received`,
  `membership`, `other_interest`).
* Counterparty-type taxonomy: 9 codes (`company`, `individual`,
  `government`, `foreign_government`, `union`, `association`,
  `political_party`, `charity`, `unknown`).

### Stage 3 — AusTender contract topic tagging (LIVE)

* Prompt **v1**: `prompts/austender_contract_topic_tag/v1.md` —
  Claude Haiku 4.5 (initial design, $0.0029/contract). 500-contract
  pilot ran with 1 schema-mismatch hallucination ("furniture" →
  outside the 33-value sector enum). Prompt-cache did NOT fire
  reliably (system instruction was 1,099 tokens, right at the
  1,024-token Haiku cache floor).
* Prompt **v2**: `prompts/austender_contract_topic_tag/v2.md` —
  upgraded to **Claude Sonnet 4.6** (project lead direction,
  2026-05-01) for max accuracy + expanded system instruction
  with worked examples (#A-#E) + explicit "furniture is NOT a
  valid sector" reinforcement. System instruction is now ~3,666
  tokens — caching FIRES reliably (verified: every v2 cache
  envelope reports `cache_read_input_tokens: 3666`).
* Schema migration: `backend/schema/039_austender_contract_topic_tag.sql`.
* Driver: `scripts/llm_tag_austender_contracts.py`.
* Loader: `scripts/load_llm_austender_topic_tags.py`.
* **v2 pilot results (2026-05-01):** 200 contracts, 200 fresh calls,
  0 failures, 0 skipped. Per-call: 584 input + 3666 cached + 125
  output tokens average. True cost $1.09 USD ($0.0055/contract)
  including cached-token charges. Without caching this would have
  been $2.95 USD, so caching saves ~63%.
* **Quality audit (manual, 10 random contracts, 2026-05-01):**
  7/10 correct (clear sector + topics + class + accurate summary),
  2/10 acceptable (judgment-call differences from reviewer view but
  not wrong), 1/10 weak (medium-confidence labelling captured the
  ambiguity correctly). 0/10 wrong. High-confidence subset: 5/5
  correct. Quality is production-grade.
* Sector distribution from v1+v2 pilot (n=499 v1 + 200 v2):
  defence (37%), technology (10%), consulting (10%),
  government_owned (8%), construction (5%), property_development
  (5%), pharmaceuticals (4%). 99% high-confidence overall.
* **Full corpus projection (Sonnet 4.6 + caching):**
  - 5-year (~73k contracts): ~$400 USD regular / ~$200 Batches API
  - 25-year (~1.9M contracts): ~$10,400 / ~$5,200 Batches API
  - These are within the project's $1k–3k AUD budget envelope.

## Cross-source correlation surface (NEW — shipped 2026-05-01)

The headline analytical view: **entities that BOTH (a) received
Australian Government contracts AND (b) appear as donors / gift-
givers / hosts in `influence_event`**.

* Schema migration: `backend/schema/041_contract_donor_overlap_views.sql`.
* Reporting script: `scripts/report_contract_donor_overlap.py`
  (exports JSON + CSV + summary stats).
* Three views:
  - `v_contract_supplier_aggregates` — one row per (supplier_name,
    prompt_version); aggregates contract count, total value,
    sectors, policy topics, agencies.
  - `v_donor_entity_aggregates` — one row per entity; aggregates
    influence_event by family (money / campaign_support / private_
    interest / benefit / access / organisational_role).
  - `v_contract_donor_overlap` — INNER JOIN of the two on
    normalised name; one row per supplier-with-entity-match,
    SEPARATELY surfacing `total_contract_value_aud` and
    `donor_total_money_aud` (NEVER summed; tier labels preserved).

**Pilot findings from just 200 v2-tagged contracts (2026-05-01):**

| Supplier | Contracts (AUD) | Donations (AUD) | Disclosed events |
|---|---:|---:|---:|
| Luerssen Australia | $2,827,548,741 | $19,000 | 4 |
| BAE Systems Australia | $1,257,370,739 | $170,459 | 9 |
| Veolia Environmental Services | $471,802,244 | $136,345 | 22 |
| Raytheon Australia | $417,000,000 | $344,550 | 35 |
| Settlement Services International | $411,922,000 | $1,767,512 | 4 |
| BAE Systems Australia (alias) | $287,787,178 | $131,908 | 3 |

These six suppliers (just 3% of the 200-contract pilot) total
$5.67 BILLION in contract awards AND $2.57 MILLION in disclosed
political donations. The full 73k-contract corpus will surface
hundreds of additional overlaps; the 1.9M-contract 25-year archive
likely thousands.

**Claim discipline:** the view DOES NOT sum contract-receipts and
donations into a single number. They live in separate columns
with separate evidence-tier labels (LLM-tagged tier 2 vs
deterministic tier 1). No causation is implied; the overlap is a
cross-source temporal correlation surface for researchers /
journalists / public scrutiny.

## Stages 4+ (planned)

* **Stage 4 — Portfolio responsibility / minister-agency mapping
  (deterministic, no LLM).** Strategic gap identified 2026-05-01:
  the cross-correlation view shows "supplier X got contracts AND
  donated to MPs" but cannot show "those donations went to MPs
  whose portfolio oversees the agency that paid X". Closing this
  gap requires loading the Administrative Arrangements Order +
  Cabinet ministry composition for current + historical terms.
  Public domain data from APH; no LLM cost.

* **Stage 5 — Hansard speech-level metadata extraction.** Cost
  TBD (~$300 USD for current term per `docs/llm_strategy_full_stack.md`).
  Surfaces what topics each MP advocates / opposes for, enabling
  the "donor-recipient MP voted/spoke for the donor's industry"
  correlation.

* **Stage 6 — Senate Estimates Q&A extraction.** Step-change
  feature; ~$400 USD per term.

* **Stage 7 — Royal Commission archives.** Per-commission ~$1,000+
  USD. Highest-value step-change for historical influence
  reconstruction.

## Operational discipline (lessons from Stages 1-3)

The discipline list below is updated as we learn:

* **Cost ceiling per stage** is declared up front; the
  maintainer approves before running.
* **Pilot first, then scale.** Every stage runs against a small
  sample (10-500 records) before going to full scale. Stage 3 v1
  pilot at concurrency=50 hit Anthropic's 450k-input-tokens-per-
  minute org rate limit on Haiku 4.5 (17/500 contracts errored).
  Concurrency=8-10 is the safe-default for synchronous mode;
  Anthropic Batches API (50% off, async, separate rate limits)
  is the path for full-scale runs.
* **Prompt caching pre-flight check.** A system instruction below
  ~1,500 tokens often falls below Anthropic's caching threshold.
  Check `cache_read_input_tokens` in the first cache file after a
  pilot run; if zero, expand the system instruction with worked
  examples until caching fires reliably. Caching saves ~60-70%
  of input cost.
* **No prompt revision without a version bump.** Editing
  `v1.md` after first publication = breaks reproducibility for
  any consumer relying on the cached responses. Prompt fixes
  ship as `v2.md` (etc.); existing v1-tagged classifications
  stay v1. Stage 3's v1→v2 upgrade (Haiku → Sonnet) was a clean
  version bump; v1 cache rows remain on disk for audit.
* **Validation gates.** Every LLM-extracted row passes a
  deterministic schema check before landing in the DB. The
  schema is strict — if the LLM hallucinates a field or returns
  malformed JSON, the row is rejected, not auto-corrected. v1
  hit one such case ("furniture" not in the 33-sector enum); the
  driver flagged it, the loader skipped it, no contamination.
* **Manual quality audit per pilot.** Spot-check ~10 random
  records by hand against source data. Stage 3 v2 manual audit
  (10 contracts): 7 correct, 2 acceptable judgment calls, 1 weak
  (correctly flagged as `medium` confidence by the model).
* **Public review path.** All prompts are committed to the
  public mirror. A researcher who disagrees with how a sector
  is defined can open a GitHub issue + propose a v2 prompt.

## Operational discipline

* **Cost ceiling per stage** is declared up front; the
  maintainer approves before running.
* **Pilot first, then scale.** Every stage runs against a small
  sample (10-200 records) before going to full scale.
* **No prompt revision without a version bump.** Editing
  `v1.md` after first publication = breaks reproducibility for
  any consumer relying on the cached responses. Prompt fixes
  ship as `v2.md` (etc.); existing v1-tagged classifications
  stay v1.
* **Validation gates.** Every LLM-extracted row passes a
  deterministic schema check before landing in the DB. The
  schema is strict — if the LLM hallucinates a field or returns
  malformed JSON, the row is rejected, not auto-corrected.
* **Public review path.** All prompts are committed to the
  public mirror. A researcher who disagrees with how a sector
  is defined can open a GitHub issue + propose a v2 prompt.
