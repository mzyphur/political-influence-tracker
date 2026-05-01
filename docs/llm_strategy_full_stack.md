# LLM Extraction Strategy — Full Document-Type Stack

**Last updated:** 2026-05-01
**Project budget:** $3,000 AUD baseline (~$1,950 USD) — **expandable for step-change features per project-lead direction**.
**Status:** Stage 1 (entity industry classification) running; Stages 2–11 scoped below; Stages 12–15 added for the step-change tier.

This document is the project's **complete** answer to:
*"Across every document type we ingest, where does LLM extraction
deliver materially better transparency than deterministic parsing,
and what's the cost?"*

The decision rule, applied per document type:

* **Deterministic parsing wins** if the source publishes
  structured data (CSV, JSON, well-formed HTML tables, SDMX,
  shapefiles). LLMs add nothing here and would only introduce
  cost + hallucination risk.
* **LLM extraction wins** if the source publishes prose,
  multi-page PDFs with handwritten amendments, scanned images,
  freeform descriptions, or narrative reports. The deterministic
  parser has a known coverage / accuracy gap that LLMs close.
* **Hybrid wins** when the source has a structured backbone but
  freeform fields (e.g. AusTender's CSV is structured but the
  `Description` column is prose; the LLM tags the description).

The full reproducibility chain (versioned prompts, hash-cached
responses, schema validation, no money-flow extraction) is
documented in [`llm_extraction_pipeline.md`](llm_extraction_pipeline.md).

## Document type × LLM-suitability matrix

| # | Document type | Source ID(s) | Format | Current parser | LLM verdict | Stage |
|---|---|---|---|---|---|---|
| 1 | AEC bulk disclosures | `aec_annual_*`, `aec_election_*` | CSV (structured) | Deterministic — high coverage | **No LLM** — already structured | — |
| 2 | AEC Register of Entities | `aec_register_of_entities_*` | JSON via XHR | Deterministic — high coverage | **No LLM** — already structured | — |
| 3 | AEC GIS shapefile | `aec_federal_boundaries_gis` | ESRI shapefile | Deterministic via pyshp + pyproj | **No LLM** | — |
| 4 | **House Register of Members' Interests PDFs** | `aph_members_interests_48` | Multi-page PDF + handwritten amendments | Deterministic — captures ~5,800 rows; estimated 10–20% miss rate | **LLM strongly recommended** (Stage 2) | **2** |
| 5 | **Senate Register of Senators' Interests** | `aph_senators_interests` | JSON API (current) + PDF amendments (legacy) | JSON: structured. PDFs: deterministic — 1,752 rows captured | **LLM for legacy PDFs only** (Stage 2) | **2** |
| 6 | APH MP/Senator contacts CSV | `aph_contacts_csv` | CSV | Deterministic — complete | **No LLM** | — |
| 7 | **House Votes & Proceedings PDFs (division blocks)** | `aph_house_votes_and_proceedings` | Semi-structured PDF | Deterministic — divisions captured | **No LLM** for divisions | — |
| 7b | **House Votes & Proceedings (Hansard speech text)** | `aph_house_votes_and_proceedings` | Long-form prose | **NOT parsed today** | **LLM strongly recommended** (Stage 4) | **4** |
| 8 | **Senate Journals PDFs** | `aph_senate_journals` | Semi-structured PDF | Deterministic — divisions captured | **LLM** for speech text only (Stage 4) | **4** |
| 9 | **APH Hansard full-text via ParlInfo** | `aph_hansard_full_text_proquest` | HTML / PDF | **NOT parsed today** | **LLM very strongly recommended** (Stage 4) | **4** |
| 10 | **APH Bills Search + Bills Digest** | `aph_bills_search` | HTML + PDF | **NOT parsed today** | **LLM strongly recommended** (Stage 5) | **5** |
| 11 | **APH Committee inquiries (submissions + transcripts)** | `aph_committee_inquiries` | PDF (submissions) + HTML (transcripts) | **NOT parsed today** | **LLM strongly recommended** (Stage 6) | **6** |
| 12 | AusTender contracts CSV | `austender_contract_notices_*` | CSV (structured) | Deterministic CSV→JSONL parser landed in Batch X | **Hybrid** — LLM tags Description column to policy topic (Stage 3) | **3** |
| 13 | GrantConnect grants | `grantconnect_grants` | CSV (structured) | Loader pending | **Hybrid** — LLM tags Description column (Stage 3) | **3** |
| 14 | **FITS register** | `fits_register` | HTML search results | Loader pending | **Hybrid** — LLM extracts activity-type from freeform "activity description" (Stage 9) | **9** |
| 15 | Senate Order on Departmental Contracts | `senate_order_contracts` | Per-portfolio HTML tables | Loader pending | **Mostly deterministic**; LLM useful only for the per-row "subject matter" prose | **(low priority)** |
| 16 | **ANAO performance audit reports** | `anao_performance_audits` | PDF | Loader pending | **LLM strongly recommended** for findings + recommendations + portfolio extraction (Stage 7) | **7** |
| 17 | NACC report releases | `nacc_corrupt_conduct` (placeholder) | HTML/PDF as published | **NOT parsed today** | **LLM strongly recommended** for findings extraction (Stage 8) | **8** |
| 18 | Federal Register of Legislation | `federal_register_of_legislation` | XML/HTML | Loader pending | **Mostly deterministic** — XML is structured; LLM useful for explanatory-memorandum summarization | **(low priority)** |
| 19 | **Modern Slavery Statements** | `modern_slavery_register` | PDF | Loader pending | **LLM strongly recommended** for supply-chain entity extraction (Stage 10) | **10** |
| 20 | They Vote For You API | `they_vote_for_you_api` | JSON (structured) | Deterministic | **No LLM** | — |
| 21 | ABS data APIs | `abs_indicator_api`, `abs_data_api` | SDMX | Deterministic | **No LLM** | — |
| 22 | ABN Lookup | `abn_lookup` | XML web service | Deterministic | **No LLM** | — |
| 23 | NSWEC disclosures | `nsw_electoral_disclosures` | HTML/CSV | Loader partial | **Mostly deterministic**; LLM only if narrative fields surface | — |
| 24 | VEC funding register DOCX | `vic_vec_funding_register` | DOCX | Existing DOCX adapter | **No LLM** unless DOCX edge cases break | — |
| 25 | QLD ECQ EDS | `qld_ecq_eds_*` | CSV + JSON | Deterministic | **No LLM** | — |
| 26 | SA ECSA | `sa_ecsa_*` | HTML index | Deterministic | **No LLM** | — |
| 27 | WAEC ODS | `waec_ods_*` | JSON dashboard | Deterministic | **No LLM** | — |
| 28 | TAS TEC | `tas_tec_*` | HTML tables | Deterministic | **No LLM** | — |
| 29 | NT NTEC | `nt_ntec_*` | HTML tables | Deterministic | **No LLM** | — |
| 30 | Elections ACT | `act_*` | HTML tables | Deterministic | **No LLM** | — |
| 31 | **State Hansard** (NSW + VIC + QLD + WA + SA + TAS + NT + ACT) | `nsw_parliament_hansard`, `vic_parliament_hansard`, `qld_parliament_hansard`, others to register | HTML + PDF | **NOT parsed today** | **LLM strongly recommended** (Stage 11) | **11** |
| 32 | Australian Government Lobbyist Register | `australian_lobbyists_register` | JSON | Deterministic | **No LLM** | — |
| 33 | State lobbyist registers (NSW + VIC + QLD + WA + SA + TAS + ACT + NT) | `*_register_of_lobbyists` | HTML tables | Loader pending | **Mostly deterministic**; LLM useful for free-text "activity description" if published | — |
| 34 | Centre for Public Integrity Lobbyist Register | `centre_public_integrity_lobbyists` | HTML | Loader pending | **No LLM** if structure is tabular | — |
| 35 | **Entity industry classification** | (cross-cutting) | Entity name + context strings | Rule-based classifier covers ~half the tail | **LLM strongly recommended** — Stage 1 ✅ DONE | **1** |

## Stage-by-stage plan within $3,000 AUD ($1,950 USD)

### ✅ Stage 1 — Entity industry classification (DONE)

* **Cost:** ~$100 USD = ~$155 AUD.
* **Status:** Pilot complete (200 entities, $0.71 USD); full run executing now (28,300 entities; ETA 30-90 min).
* **Model:** `claude-sonnet-4-6`.
* **Prompt:** [`prompts/entity_industry_classification/v1.md`](../prompts/entity_industry_classification/v1.md).
* **Loader:** `scripts/load_llm_entity_classifications.py`.
* **Outcome:** ~28k previously-unknown entities tagged with one of 32 industry sectors + entity_type promotion for high-confidence cases.

### Stage 2 — House + Senate Register of Interests PDF deeper extraction

* **Cost estimate:** $50–150 USD = $80–230 AUD (one-time + annual refreshes).
* **Why:** The current deterministic parser captures ~5,800 House rows + 1,752 Senate rows. Anecdotally, MPs declare 15–40 items each × 318 reps = 5,000–13,000 items. The gap is from format variations: handwritten amendments, scanned-then-OCR'd updates, free-form clause text, item numbering quirks. LLMs handle these gracefully.
* **Approach:** Run Sonnet 4.6 against the original PDF (multimodal input) with a strict JSON schema for each declared item: `{kind, description, organisation, position, relationship, declared_at}`. Validate against the existing `house_interest_record` / `senate_interest_record` schemas; reject hallucinations.
* **Method tag:** `extraction_method='llm_register_of_interests_pdf_v1'`.
* **Cost basis:** ~318 PDFs × 8k input tokens × $3/M = $7.6; output ~3k tokens × $15/M = $14.3 per run. Total ~$22 per refresh; with prompt caching on the system instruction, ~$15.
* **Reproducibility:** PDF SHA-256 + prompt SHA-256 + response SHA-256 → cached envelope.

### Stage 3 — AusTender + GrantConnect description topic-tagging

* **Cost estimate:** $200–400 USD = $310–620 AUD (full historical, one-time).
* **Why:** AusTender publishes ~75k contracts/year × 25 years = ~1.9M contracts. Each has a freeform Description field but no policy-topic tag. LLMs map descriptions to the project's existing 32-sector taxonomy + a parallel policy-topic taxonomy (health, defence, infrastructure, IT, etc.). Same for GrantConnect grants (~150k recent). Surfaces "this MP's electorate received $X in Commonwealth grants for industry Y over the same period industry Y donated $Z to their party" as labelled context.
* **Approach:** Haiku 4.5 (cheaper) for high-volume tagging since each row is short input (~200 tokens) → short output (~50 tokens).
* **Method tag:** `extraction_method='llm_austender_topic_tag_v1'` / `llm_grantconnect_topic_tag_v1`.
* **Cost basis:** Recent 5-year window first (~375k contracts × $0.0003/contract ≈ $112 USD); full 25-year history later if budget allows (~$300 USD).

### Stage 4 — Hansard speech extraction (federal)

* **Cost estimate:** $400–800 USD = $620–1,240 AUD (full historical Hansard).
* **Why:** The biggest analytical gap. Currently the project ingests divisions (who voted how) but NOT the actual speeches. Hansard text is the public record of what every MP said in chamber. Pairing speech text with division votes lets the app answer "what did MP X say about Bill Y BEFORE voting Z on it?" — a substantial transparency surface.
* **Approach:** ParlInfo Search exposes per-speech permalinks. For each Bill: enumerate the second-reading + amendment debate speeches; LLM extracts speaker → topic → speech-summary tuples + bill linkage.
* **Method tag:** `extraction_method='llm_hansard_speech_v1'`.
* **Cost basis:** Federal Hansard at ~50k speeches/year × 1k input tokens (with prompt caching the system instruction is shared) × $3/M = ~$150/year. Full 25-year history at ~$3,750 USD is too expensive — focus on the **current parliamentary term** (~$300 USD) plus selective extraction for landmark Bills.
* **Compromise:** Stage 4a — current term only, $200-400 USD. Stage 4b — historical speeches for the top-50 Bills by public interest, $100-200 USD.

### Stage 5 — APH Bills Search + Bills Digest summarization

* **Cost estimate:** $50–100 USD = $80–155 AUD.
* **Why:** Each Bill has an Explanatory Memorandum and a Parliamentary Library "Bills Digest" — both narrative documents that summarise what the Bill does, who it affects, and what concerns have been raised. Pairing these with TVFY voting records lets the app surface "the Bill said X; MP Y voted FOR; the Bills Digest flagged concerns Z" linkages.
* **Approach:** Sonnet 4.6 reads each Bill's PDF + Bills Digest, returns: `{bill_id, summary, affected_industries, key_provisions, concerns_flagged_by_library, sponsoring_minister}`.
* **Method tag:** `extraction_method='llm_bills_digest_v1'`.
* **Cost basis:** ~500 Bills/term × 5k input tokens × $3/M = $7.5 per term. Two terms covered = $15. Add output: ~$30. Total: ~$50.

### Stage 6 — APH Committee inquiry submission extraction

* **Cost estimate:** $300–600 USD = $470–940 AUD.
* **Why:** Parliamentary committees publish thousands of submissions per year. Each submission is a PDF document by a corporate, professional, or civic entity arguing for/against a policy. This is **lobbying-by-public-record** at scale — every submission is timestamped, named, and addressable. LLM extraction surfaces who-submitted-what-on-which-bill-with-what-position.
* **Approach:** Per submission → `{submitter_entity, submitter_type, key_claims, position_for_against_neutral, policy_areas, recommended_amendments}`.
* **Method tag:** `extraction_method='llm_committee_submission_v1'`.
* **Cost basis:** ~5k submissions/year × 8k input tokens × $3/M = $120/year. Add output: ~$60. Total: $180/year. Two-year backfill: $360.

### Stage 7 — ANAO performance audit findings extraction

* **Cost estimate:** $50–150 USD = $80–230 AUD.
* **Why:** ANAO publishes ~50 performance audit reports per year. Each is a 50-200 page narrative PDF with structured findings + recommendations + agency responses. LLM extracts these into `{audit_id, portfolio, agency, audit_topic, findings: [], recommendations: [], agency_response_summary}`.
* **Approach:** Sonnet 4.6 multimodal PDF input with strict schema. Findings + recommendations are the high-value structured output.
* **Method tag:** `extraction_method='llm_anao_audit_v1'`.
* **Cost basis:** 50 reports × 30k input tokens × $3/M = $4.5/year. Output: ~$50/year. Total: ~$55. Five-year backfill: $275.

### Stage 8 — NACC + integrity-commission report extraction

* **Cost estimate:** $30–100 USD = $50–155 AUD.
* **Why:** The NACC (federal) and state integrity commissions (NSW ICAC, VIC IBAC, QLD CCC, WA CCC, SA ICAC, TAS Integrity Commission) publish formal corruption findings + investigation reports. Currently low volume (NACC: <10 reports/year) but high transparency value when they do publish.
* **Approach:** Sonnet 4.6. Schema: `{commission, report_id, subject_individuals_or_entities, findings: [], recommendations: [], status}`. Strong claim-discipline guardrails — only extract what the report SAYS, never characterise.
* **Method tag:** `extraction_method='llm_integrity_commission_v1'`.
* **Cost basis:** ~30 reports/year × 30k input tokens × $3/M = $2.7. Output: ~$15. Total: ~$20/year.

### Stage 9 — FITS activity-description extraction

* **Cost estimate:** $20–50 USD = $30–80 AUD.
* **Why:** FITS register publishes ~500 active registrants. Each has a "general description of activity" freeform field that says what the registrant does for the foreign principal. LLM extracts: `{activity_type, parliamentary_lobbying_yes_no, communications_activity_yes_no, disbursement_yes_no, target_government_areas: []}`.
* **Approach:** Haiku 4.5; small dataset, structured output.
* **Cost basis:** 500 entries × 1k tokens = ~$2/refresh. Trivial.

### Stage 10 — Modern Slavery Statement entity extraction

* **Cost estimate:** $100–250 USD = $155–390 AUD.
* **Why:** ~3,000 entities file annual modern-slavery statements. Each statement names the reporting entity's tier-1 / tier-2 supply chain partners — a public-record map of which large Australian companies do business with which suppliers. Cross-references usefully with the project's donor entity table (suppliers that also appear as political donors).
* **Approach:** Sonnet 4.6 multimodal PDF input. Schema: `{reporting_entity, reporting_period, supply_chain_entities: [{name, country, tier}], policy_areas, due_diligence_summary}`.
* **Cost basis:** 3,000 statements × 15k input tokens × $3/M = $135. Output: ~$50. Total: ~$185 one-time + $185/year for refreshes.

### Stage 11 — State Hansard extraction (after federal Hansard lands)

* **Cost estimate:** $300–800 USD = $470–1,240 AUD across all 8 states/territories.
* **Why:** State Hansard fills the gap left by the federal Hansard ingestion. Each state parliament publishes a separate Hansard with its own URL surface. State-level political-influence analysis (e.g. NSW Liberal Party connections to NSW property sector via state contracts AND state speeches AND state disclosures) becomes possible.
* **Cost basis:** Each state's parliamentary record is ~10-30k speeches/year. ~$50–150 USD per state per year of historical coverage. Stagger by state to manage cost.

## Step-change tier (Stages 12–15)

Per project-lead direction (2026-05-01): the budget can expand
beyond $3,000 AUD where a stage delivers a genuine step-change in
information / features — not just incremental coverage but a
new public surface that fundamentally changes what the project
can answer.

The four stages below are step-change-grade. Each transforms a
narrative document corpus that currently has zero project surface
into a structured queryable surface. Together they take the
project from "shows disclosed money" to "shows disclosed money +
what was said about it + how it was scrutinised + what was
delivered for it."

### Stage 12 — Senate Estimates Q&A transcript extraction

* **Cost estimate:** $400–800 USD = $620–1,240 AUD per term.
* **Why step-change:** Senate Estimates runs twice yearly across every
  portfolio. Officials answer detailed questions about programs,
  contracts, recipients, and timelines. The transcripts are
  publicly published but unparsed. LLM extraction maps each Q&A
  exchange to: `{senator, minister_or_official, portfolio,
  topic, question_summary, answer_summary, taken_on_notice,
  follow_up_required}`.
* **Surface unlocked:** "When questioned about Program X in
  Estimates, Minister Y said Z" linked to the Bill, the program's
  funding records (GrantConnect), and the contracted suppliers
  (AusTender). Closes the loop between disclosed money and
  ministerial accountability.
* **Method tag:** `extraction_method='llm_senate_estimates_qa_v1'`.

### Stage 13 — APH Question Time + Hansard daily extraction

* **Cost estimate:** $300–600 USD = $470–940 AUD per term.
* **Why step-change:** Question Time is the daily public surface
  of executive accountability. LLM extraction surfaces every
  question + answer pair with topic, minister, party, and the
  Bill or program at issue. Pairs with TVFY divisions to surface
  "the Member asked about Bill X today; the Member voted on Bill
  X next week as Y."
* **Surface unlocked:** A queryable map of every question asked
  in the chamber and the answer given. Critical context for any
  political-influence narrative.
* **Method tag:** `extraction_method='llm_question_time_v1'`.

### Stage 14 — Treasury / Finance / Health FOI disclosure logs

* **Cost estimate:** $50–150 USD = $80–230 AUD.
* **Why step-change:** FOI disclosure logs are public records
  showing what FOI requests an agency has answered. The logs
  themselves don't contain the answers, but they reveal which
  topics have been the subject of journalist / public-interest
  scrutiny. Cross-references with donor entities + voting records
  show "X journalist FOI'd Treasury about [donor entity Y] right
  before [legislation that benefited entity Y] passed."
* **Surface unlocked:** A meta-layer of public-interest scrutiny.

### Stage 15 — Royal Commission archive ingestion

* **Cost estimate:** Highly variable depending on scope.
  Major royal commissions (Banking, Aged Care, Disability,
  Robodebt) publish ~10,000+ pages of evidence + thousands of
  transcripts + hundreds of submissions. $1,000–3,000 USD per
  commission for full extraction.
* **Why step-change:** Royal Commission archives are the deepest
  public-interest evidence base in Australian governance. They
  contain primary-source testimony from corporate witnesses,
  regulators, and government officials. Currently the project
  has zero surface for this evidence. LLM extraction surfaces
  per-commission: `{witness_entity, witness_role, key_testimony,
  document_exhibits, findings_recommendations}`.
* **Surface unlocked:** A reader can pivot from "company X is a
  donor" to "company X gave testimony to royal commission Y on
  date Z saying [quote]" — the deepest cross-evidence linkage
  the project can produce.

## Step-change tier total

| Stage | Cost (USD) | Cost (AUD) |
|---|---:|---:|
| 12 — Senate Estimates Q&A (current term) | $400 | $620 |
| 12b — Estimates historical (5 years) | $800 | $1,240 |
| 13 — Question Time (current term) | $300 | $470 |
| 13b — Question Time historical (5 years) | $600 | $940 |
| 14 — Treasury / Finance / Health FOI logs | $100 | $155 |
| 15 — Royal Commissions (top 3 — Banking, Aged Care, Robodebt) | $3,000 | $4,650 |
| **Step-change subtotal** | **$5,200** | **$8,075** |
| Buffer for prompt iteration + re-runs | $500 | $775 |
| **Step-change tier total** | **$5,700** | **$8,850** |

Combined with the must-have Stages 1–10 ($1,602 USD = $2,490 AUD):

**Full-vision project cost: $7,302 USD = $11,340 AUD**

This is the ceiling number. The project can stage execution by
priority — Stages 1–10 first to land the standard transparency
surface; Stages 11–15 added incrementally as each delivers
verified step-change value before the next is funded.

## Total budget allocation within $3,000 AUD

| Stage | Cost (USD) | Cost (AUD) | Status |
|---|---:|---:|---|
| 1 — Entity classification (~28k) | $100 | $155 | ✅ executing |
| 2 — Register of Interests PDFs | $50–150 | $80–230 | scoped |
| 3 — AusTender + GrantConnect topics (5yr) | $112 | $175 | scoped |
| 3b — AusTender historical extension (15-25yr) | $200 | $310 | optional |
| 4a — Hansard current term | $300 | $470 | scoped |
| 4b — Hansard top-50 historical Bills | $150 | $230 | optional |
| 5 — Bills Digest summarization | $50 | $80 | scoped |
| 6 — Committee submission extraction (2yr) | $360 | $560 | scoped |
| 7 — ANAO audits (5yr) | $275 | $430 | scoped |
| 8 — NACC + integrity commissions | $50 | $80 | scoped |
| 9 — FITS activity descriptions | $20 | $30 | scoped |
| 10 — Modern Slavery Statements | $185 | $290 | scoped |
| 11 — State Hansard (NSW + VIC pilot) | $300 | $470 | optional |
| **Subtotal (must-haves: Stages 1–10)** | **$1,402** | **$2,180** | |
| **Buffer for prompt iteration + re-runs** | $200 | $310 | |
| **Total committed Stages 1–10** | **$1,602** | **$2,490** | |
| **Headroom for Stage 11 + new sources** | $348 | $510 | |

This fits comfortably inside the $3,000 AUD ceiling with a meaningful buffer for prompt iteration (every prompt revision = some re-spend on cache invalidation), genuine re-runs after schema fixes, and Stage 11 + future-source experimentation.

## Reproducibility commitment for ALL stages

Every stage adheres to the four invariants in
[`llm_extraction_pipeline.md`](llm_extraction_pipeline.md):

1. **Pinned model versions.** Every cache key includes the model id. Swapping models invalidates the cache by design.
2. **Versioned prompts.** Every prompt is committed to `prompts/<task>/v<N>.md` in the public repo. Prompt revisions ship as new versions; old versions stay valid for their existing extractions.
3. **Strict schema validation.** Every LLM response is validated against a JSON schema. Hallucinations → rejection, not auto-correction.
4. **Hash-cached responses.** Every API call's input + output is persisted at `data/raw/llm_extractions/<task>/<sha256>.{input,output}.json`. A researcher can verify any extraction without an API key by checking the cached envelope.
5. **No money-flow extraction.** LLMs never produce rows that feed direct-money totals. The byte-identical-totals invariant remains the project's top rule.

## Operational discipline (across all stages)

* **Pilot first, scale after.** Every stage runs on 10–200 records first to verify quality + cost before scaling.
* **Cost ceiling per stage** declared up front; the maintainer approves before running.
* **Prompts are public.** Anyone can audit `prompts/<task>/v<N>.md` and propose v2 via PR.
* **Validation gates.** Schema validation rejects malformed responses; the project does not auto-correct hallucinations.
* **Concurrent execution.** Default 8–12 parallel workers; respects Anthropic rate limits.
* **Method tagging.** Every LLM-extracted row carries `extraction_method='llm_<task>_v<n>'` so consumers can filter by method.
* **Public surface labels.** The methodology page documents which surfaces use LLM extraction so a reader sees "this row was classified by claude-sonnet-4-6 on 2026-05-01" rather than presuming deterministic provenance.

## What this stack does NOT use LLMs for

For complete transparency about the boundary:

* **Money flows.** Direct disclosed money / receipts / donations are extracted by deterministic parsers exclusively. The byte-identical-totals invariant requires it.
* **Person, party, electorate name resolution.** The project's resolver is exact-match by design. Adding LLM fuzzy-matching here would violate the project's anti-fuzzy-similarity rule.
* **Anything with a structured CSV / JSON / SDMX source.** AEC bulk data, AusTender CSV (the rows themselves), TVFY API, ABS APIs, ABN Lookup all stay deterministic.
* **Geographic data.** Shapefiles + boundary geometry are deterministic.
* **Anything that affects the AEC Register branch resolver.** The deterministic 5-stage resolver is foundational to the federal-vs-state party-row separation.

## How to add a new LLM-extraction stage

1. **Survey the source.** Confirm it's a document type that LLM extraction adds value to (per the matrix above).
2. **Estimate cost.** Per-record token count × volume × pricing → per-stage budget.
3. **Get maintainer approval** before any run > $50 USD.
4. **Write `prompts/<task>/v1.md`** with: system instruction (load-bearing), user-message template, response schema, claim-discipline framing.
5. **Build `scripts/llm_<task>.py`** that reads source records, calls `LLMClient`, validates, writes JSONL.
6. **Build `scripts/load_llm_<task>.py`** that lifts JSONL into the appropriate DB table with `extraction_method='llm_<task>_v1'`.
7. **Pilot on 10–200 records.** Review output for hallucination + sector accuracy.
8. **Scale to full volume.** Document the cost outcome.
9. **Update [`llm_extraction_pipeline.md`](llm_extraction_pipeline.md) + this doc** with the new stage's status.
