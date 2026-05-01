# LLM-Assisted Extraction Pipeline

**Last updated:** 2026-05-01 (Stage 1 — entity industry classification)

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

## Stages 2-4 (planned, not yet shipped)

* **Stage 2 — Re-extract House + Senate Register PDFs.**
  ~$30 USD. Pushes the `private_interest` row count higher by
  capturing rows the deterministic PDF parser misses.
* **Stage 3 — Topic-tag AusTender contracts + GrantConnect
  grants.** ~$200/year USD. Maps free-text contract / grant
  descriptions to the project's existing 32-public-policy-sector
  taxonomy, enabling "what industries received the most public
  money for what purposes" surfaces.
* **Stage 4 — Hansard speech-level metadata extraction.** Cost
  TBD. Deferred until Stages 1-3 land cleanly.

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
