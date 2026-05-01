# Influence Correlation Gaps — Strategic Stocktake (2026-05-01)

**Purpose:** before public launch, audit what data we have, what's
missing for the influence-narrative analysis, and the plan to close
the gaps. This is a load-bearing strategic doc — every gap below
has a plan, an estimated cost, and a launch-blocker / nice-to-have
flag.

## The influence narrative we're building

> A specific donor X (or a beneficial owner above X) gives money
> or gifts to MP Z. MP Z is a member of the governing party AND
> holds a portfolio that oversees agency A. Agency A subsequently
> awards a contract worth $N to X. MP Z votes for / advocates for
> bills favourable to X's industry. X's senior staff include
> ex-public servants who previously worked at Agency A.

Each underline above is a separate evidence stream. Every link
in the chain must be source-backed and labelled with its
evidence tier. The cross-correlation views surface the links
WITHOUT summing across tiers, in line with the project's
claim-discipline rule.

## What we have (data complete)

| Domain | Source | Tier | Status |
|---|---|---|---|
| Federal donations (annual + election) | AEC | 1 | LIVE — 225,800 money events |
| Federal campaign support (public funding etc.) | AEC | 1 | LIVE — 77,176 events |
| Federal MP private interests | APH House register PDF + Senate API | 1 | LIVE — 4,667 events |
| Federal MP gifts / hospitality | APH register | 1 | LIVE — 1,364 benefit events |
| Federal MP access disclosures | APH register | 1 | LIVE — 3,212 access events |
| Federal MP organisational roles | APH register | 1 | LIVE — 1,382 events |
| State donations (NSW + ACT + NT + QLD + VIC + SA + WA + TAS) | State EC | 1 | LIVE |
| Postcode → electorate crosswalk | AEC electorate finder | 1 | LIVE — 448 rows / 127/150 House seats |
| AEC Register of Entities (party-entity links) | AEC | 1 | LIVE — 148 reviewed links |
| Federal candidate-vehicle party seeds | AEC | 1 | LIVE — 4 personality vehicles |
| State-jurisdiction party seeds | State EC | 1 | LIVE — 31 sub-national rows |
| AusTender contract notices (parsed JSONL) | data.gov.au CC-BY 3.0 AU | 1 | LIVE — 73,458 contract notices |
| **Entity industry classification** | LLM Sonnet 4.6 | 2 | **IN PROGRESS — ~14k/28k done** |
| **Register of Interests deep extraction** | LLM Sonnet 4.6 | 2 | LIVE pilot — 109 items from 100 sections |
| **AusTender contract topic tagging** | LLM Sonnet 4.6 v2 | 2 | LIVE pilot — 200 contracts, 99% high-conf |
| **Cross-source contract × donor overlap view** | SQL view over above | composite | LIVE — 6 overlaps from 200 pilot contracts |

## What's MISSING for the full influence narrative

### Critical gaps (must land before public launch)

#### Stage 4a — Portfolio → Agency → Minister mapping

**Why critical:** without this, the cross-correlation surfaces
"supplier X got contracts AND donated to MPs" but cannot show
"those donations went to MPs whose portfolio oversees the agency
paying X". This is the structural anchor of the influence story.

**Source:** APH Administrative Arrangements Order (AAO) — the
public document defining which department reports to which
minister. The AAO is updated at each election + ministry
reshuffle. Public domain, machine-readable PDF.

**Method:** deterministic. Parse AAO + Cabinet composition; load
into new tables `cabinet_ministry`, `portfolio_responsibility`,
`minister_portfolio_term` with effective-date ranges. Join from
`influence_event.recipient_person_id` → office_term.party →
minister status + portfolio coverage at the contract date.

**Cost:** $0 (deterministic).

**Status:** LAUNCH-BLOCKER. To be implemented in Batch BB
(this session).

#### Stage 4b — Lobbyist Register

**Why critical:** lobbyists are the legitimate mediating actor
between donors and government. Closing this gap surfaces:

* Lobbyist firm L represents Client X.
* Lobbyist firm L (or its principals) donate to MPs Z, W, V.
* Client X subsequently receives contracts from agencies
  overseen by Z / W / V.

This three-way correlation (lobbyist + donor + contract) is
journalistically devastating when present.

**Source:** Federal Lobbyist Register at
https://lobbyists.ag.gov.au/register, plus state equivalents
(NSW, VIC, QLD, SA, WA, TAS).

**Method:** deterministic. Fetch HTML / structured data; parse
into `lobbyist_organisation`, `lobbyist_principal`,
`lobbyist_client_engagement` tables.

**Cost:** $0 (deterministic).

**Status:** LAUNCH-BLOCKER for the federal launch.

#### Stage 4c — APH division voting records

**Why critical:** how an MP voted on a bill is the most direct
signal of whether their disclosed interests / donations align
with their public actions.

**Source:** `aph_official_divisions` raw data already exists in
the repo at `data/raw/aph_official_divisions/`. Just needs a
loader.

**Method:** deterministic. Parse division vote XML / JSON; load
into `division`, `division_vote` tables; join `division_vote.
person_id` to `office_term` for context.

**Cost:** $0 (deterministic).

**Status:** LAUNCH-BLOCKER for the federal launch.

#### Stage 4d — Beneficial ownership / corporate structure

**Why critical:** donations are often made by a corporate
vehicle that obscures the ultimate controlling person. Without
beneficial-ownership data, cross-source correlation undercount
real influence (donor X and donor Y donate separately but are
both controlled by person Z).

**Source:** ASIC company register (paid bulk data; ~AUD$45/year
for the bulk-organisation feed) + ACNC charity register (free
bulk download).

**Method:** deterministic-first (parse ASIC + ACNC officeholder
records); LLM-aided for ambiguous-name matching to existing
entity rows.

**Cost:** ASIC bulk feed AUD$45/year + ~$50 USD LLM matching
budget = ~$95 AUD year-1.

**Status:** HIGH-VALUE, NOT BLOCKING for launch (can ship as
Batch CC after launch). The cross-correlation view works
without it — it just under-counts shared-ownership cases.

#### Stage 4e — Electorate demographics + SEIFA

**Why critical:** the user explicitly asked about correlating
political behavior with "democratic and social conditions".
ABS Census + SEIFA (Socio-Economic Index For Areas) gives
electorate-level demographics: median income, education
attainment, employment, age structure, remoteness category.

**Source:** ABS Census 2021 + SEIFA 2021 by electorate (CC-BY
4.0 from data.gov.au).

**Method:** deterministic. Fetch CSV; load to `electorate_seifa`
+ `electorate_census_2021` tables.

**Cost:** $0 (deterministic; data already CC-BY).

**Status:** LAUNCH-WORTHY for public app to surface "Industries
that donate to MPs in low-SEIFA electorates" type queries.

### High-value gaps (can ship post-launch)

#### Stage 5 — Hansard speech / Question Time

**Why high-value:** what MPs publicly advocate for / criticise
is the second-best vote signal after divisions. Combined with
contracts + donations, surfaces "MP advocated for industry X
funding while receiving X donations".

**Source:** APH Hansard.
**Method:** LLM-aided (Sonnet 4.6 over speech text).
**Cost:** ~$300-500 USD per parliamentary term.
**Status:** Stage 5 in the existing strategic plan.

#### Stage 6 — Committee submissions

**Why valuable:** who submits formal submissions to which inquiry
+ what positions they take. Surfaces lobbying-by-formal-submission.

**Source:** APH committees website.
**Method:** LLM-aided.
**Cost:** ~$360 USD per 2-year window.
**Status:** Stage 6 in plan.

#### Stage 7 — Public service revolving door

**Why valuable:** the most insidious influence channel. Ex-
public servants who oversaw a sector then move to a company
in that sector + lobby their former colleagues.

**Source:** APS Gazette + LinkedIn-style data + news mentions.
**Method:** LLM-aided + deterministic.
**Cost:** ~$200 USD initial + ~$50/year refresh.
**Status:** New stage; not in current plan but should be added.

#### Stage 8 — News mention extraction (Trove + news APIs)

**Why valuable:** captures scandals, allegations, denials,
policy positions not formally recorded elsewhere.

**Source:** Trove (free, NLA), commercial news APIs.
**Method:** LLM-aided.
**Cost:** ~$1,000 USD initial corpus + ~$100/year.
**Status:** Stage 8 candidate.

### Lower-priority gaps (out-of-scope for v1 launch)

* Modern Slavery Statements (Stage 10) — supply-chain risk
  disclosures; useful for trade-related correlations.
* Royal Commission archives (Stage 15) — historical
  reconstruction; per-commission ~$1,000+.
* International FITS activity descriptions (Stage 9) — foreign
  influence; small but high-signal corpus.
* NACC / Integrity Commission reports (Stage 8) — corruption
  findings; small corpus.

## Prompt-strategy lessons learned (Stages 1-3 retro)

What we'd do differently next time:

1. **System-instruction length pre-flight check.** Stage 3 v1's
   system instruction was 1,099 tokens — right at Anthropic's
   1,024-token cache floor. v1 caching never fired. v2's
   expansion pushed it to ~3,666 tokens; caching fires reliably.
   New rule: **every prompt's system instruction must be at
   least 1,500 tokens to ensure caching**, even if it means
   adding worked examples that aren't strictly necessary for
   correctness.

2. **Concurrency vs rate-limit reality check.** Set the default
   concurrency to 8-10 (synchronous mode) regardless of how
   fast we want to go. Anthropic's 450k input-TPM org rate
   limit (Haiku) and equivalent (Sonnet) caps real throughput
   at ~10 req/sec on the size of prompts we use. Higher
   concurrency just queues threads, doesn't speed things up.
   For full-corpus runs, use the Anthropic Batches API (50%
   off, async, separate rate limits, supports tool-use +
   caching).

3. **Schema enforcement defence-in-depth.** Even with strict
   tool-use input_schema enums, the model occasionally returns
   a value outside the enum (Stage 3 v1 returned "furniture" as
   a sector). The driver's belt-and-braces post-validation
   catches it. Always do BOTH server-side schema (via tool-use)
   AND client-side enum check.

4. **Reviewer-agent timeouts.** The general-purpose reviewer
   agent timed out at 600s without a verdict — the audit
   workload (load 200 records + 5,000 source records + audit
   30 cases) was too large in one agent call. Future audits
   should split into smaller chunks or just be done by the
   maintainer manually for small samples.

5. **Prompt versioning is non-negotiable.** Stage 3 v1's pilot
   results stayed in the cache and the DB even after v2
   shipped. New `(contract_id, prompt_version)` rows for v2.
   This means consumers can A/B compare prompt revisions, and
   the v1 cache stays as historical record without contaminating
   v2 outputs.

6. **Deterministic methods are still preferred where they
   work.** All five Stage 4 critical gaps above are
   deterministic. LLMs are for genuinely freeform text where
   a regex / parser would lose information. Don't reach for an
   LLM when an HTML scraper or PDF text extractor + regex would
   do.

## Cost ceiling (recompute)

| Stage | Estimated cost | Status |
|---|---:|---|
| Stage 1 (entity classification, 28k) | $100 USD | running, ~14k done |
| Stage 2 (ROI deep extraction, 100 pilot) | $0.38 USD | done |
| Stage 2 full (3,180 sections) | ~$15 USD | not yet run |
| Stage 3 v2 pilot (200) | $1.09 USD | done |
| Stage 3 v2 full 5-year (73k) | ~$200 USD regular / ~$100 Batches | not yet run |
| Stage 3 v2 full 25-year (1.9M) | ~$5,200 / ~$2,600 Batches | future |
| Stage 4a-e (deterministic) | $0 | next |
| Stage 4d (ASIC bulk) | AUD$45/year | post-launch |
| Stage 5 Hansard | $300-500 USD/term | post-launch |
| **Cumulative pre-launch** | **~$320 USD** | within budget |

The project's stated budget envelope ($1,000 AUD original,
expandable to $3,000 AUD for step-change) is comfortably
respected.

## Decision: PROCEED with Stage 4 (deterministic)

The user (project lead) and the agent agree (2026-05-01):
*close Stage 4a + 4b + 4c + 4e BEFORE public launch*. These
are deterministic, cheap, and structural — they upgrade the
analysis surface from "interesting correlations" to "the
influence narrative".

Stage 4d (beneficial ownership) is high-value but not blocking;
ships as Batch CC post-launch.

LLM Stages 5+ are post-launch refinements.
