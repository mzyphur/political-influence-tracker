# Worked example: how to use the project to investigate a question

This is a walk-through showing how a journalist, scholar, regulator,
or citizen can use the project to investigate a specific question
about Australian political-influence records — without overclaiming,
and with every step traceable back to a public source document.

The example is **how to compare two MPs' disclosed records**. The
same shape applies to any of the project's other surfaces (compare
two parties, an industry sector across multiple MPs, a postcode's
representative across years).

## The question

> *"Two MPs from neighbouring electorates are about to vote on a
> bill affecting industry X. What has each personally disclosed
> about their dealings with industry X, and what party-mediated
> context surrounds each?"*

## Step 1 — Find the two MPs

Start at the project's public app and use the search box.
Equivalently, use the API:

```bash
# Search the project's records by name.
curl 'http://127.0.0.1:8008/api/search?q=<name>&types=representative&limit=5' \
  | jq '.results'
```

The search is deterministic — exact-match on the name, then a list
of source-backed candidates if multiple representatives share the
name. The maintainer never auto-disambiguates; if there's
ambiguity the API surfaces the candidates.

Note the `person_id` in each result. You'll use that ID to fetch
profiles below.

## Step 2 — Read each MP's disclosed direct records

For each `person_id`:

```bash
curl 'http://127.0.0.1:8008/api/representatives/<person_id>'
```

The response includes:

- **`office_term`** — current and historical terms in office
- **`party_exposure_summary`** — party-mediated exposure
  (estimated, with a denominator-scope caveat — read the methodology
  page's [#equal-share](../frontend/public/methodology.html#equal-share)
  section before quoting these)
- **`recent_records`** — a sample of disclosed direct records

The `recent_records` block is what the MP has *personally
disclosed*. Each record carries:

- `event_family` — what kind of record (gift, hospitality, share,
  loan, contract, etc.)
- `evidence_tier` — `direct` for these
- `source_url` — link back to the original source document (PDF,
  CSV row, etc.)
- `source_document_id` — internal ID for cross-referencing
- A short text summary

## Step 3 — Filter to industry X

The project's records are tagged with public-policy sectors and
public-policy topics. To find records relevant to industry X, use
the `/api/representatives/{id}/evidence` endpoint with the
`event_family` filter, OR cross-reference against
`/api/influence-context`:

```bash
curl 'http://127.0.0.1:8008/api/influence-context?person_id=<id>&public_sector=<sector>&limit=50' \
  | jq '.rows[] | {sector, topic, evidence_tier, source_url, summary}'
```

This endpoint returns *labelled connections*, not assertions of
wrongdoing. Each row carries its evidence tier so you can read
direct vs party-mediated vs modelled separately.

## Step 4 — Read each MP's party-mediated context

If the MP belongs to a party, the AEC Register of Entities records
which entities are formally associated with that party. This is
the "party_mediated" evidence family — it does NOT mean the MP
personally received anything from the listed entities.

```bash
curl 'http://127.0.0.1:8008/api/parties/<party_id>'
```

The response includes the party's `associated_entities` list,
sourced verbatim from the AEC Register and labelled `evidence_tier:
party_mediated`.

When you write up findings, **you must keep this separate from any
direct claim about the MP**. The project keeps these in different
data families on purpose. Don't merge them in a public write-up
unless you can name a source document that explicitly links the
specific entity to the specific MP — at which point you've found
a record that belongs in the `direct` family, not `party_mediated`.

## Step 5 — Read each MP's voting record on industry X

The project's They Vote For You integration surfaces parliamentary
voting records by topic. This is independent of money / gifts /
interests — voting is its own evidence family.

Look at the methodology page's
[#campaign-support-tiers](../frontend/public/methodology.html#campaign-support-tiers)
section and the project's `docs/campaign_support_attribution.md`
file before quoting voting records alongside money records. The
project's claim-discipline rule is specifically that disclosed
flows do not "buy" votes — voting records and disclosed flows are
co-occurring patterns, not causation.

## Step 6 — Write up findings without overclaiming

The project's claim-discipline microcopy on the public app is the
template a careful write-up should follow:

- ✅ "MP X has personally disclosed receiving the following records,
  according to public source documents (linked)."
- ✅ "MP X's party has separately disclosed the following
  associated-entity links in the AEC Register of Entities."
- ✅ "MP X's party-mediated exposure is *estimated* at $Y under the
  equal-share model across N current caucus members. This is a
  modelled allocation, not a personal receipt."
- ✅ "MP X voted [for|against|abstained] on the following bills
  related to industry X."
- ❌ "MP X received $Z from industry X." (Wrong unless every $Z
  was a direct disclosed person-level record. Otherwise this
  conflates evidence families.)
- ❌ "MP X is corrupt." (Disclosed records are not allegations of
  wrongdoing; the project does not characterise individuals.)
- ❌ "MP X took $Z from industry X to vote for the bill."
  (Causation requires evidence the project's records do not, by
  themselves, supply.)

If your write-up cites a project surface, link to the specific
permalink — every page on the public app and every API endpoint
returns content that's reproducible from the public source
documents listed in the response.

## Step 7 — Save a snapshot for citation

The project provides a stable-shape snapshot at `/api/stats` that
is suitable for citation:

```bash
curl http://127.0.0.1:8008/api/stats | jq
```

The fields you might cite (with their interpretation):

- `influence_event.row_count` — *total disclosed records loaded*,
  across **all four evidence families**. This is for transparency
  only; do NOT quote this as "money received" or "money flowing".
- `postcode_electorate_crosswalk.federal_house_seat_coverage_percent`
  — fraction of federal House seats covered by the postcode-
  search surface.
- `source_document.most_recent_fetch_at` — when the project last
  refreshed against the upstream sources.
- The methodology page's footer carries the short SHA of the build
  that produced the snapshot, linked into the public mirror's
  commit history.

When citing the project in a publication, include both the build
SHA (for reproducibility) and the `most_recent_fetch_at` (for data
freshness).

## Step 8 — File a data-correction issue if you find a record the
project gets wrong

The project's
[Data correction issue template](../.github/ISSUE_TEMPLATE/data_correction.md)
is the right channel. Include:

- The exact public-app surface (or API endpoint) showing the issue
- The underlying source-document URL
- Your quote of the source vs the project's quote
- The affected evidence family (direct / campaign-support /
  party-mediated / modelled)
- Your confidence level (have you read the source document yourself?)

## Why the discipline?

This is a public-interest project. The temptation in any influence-
tracking tool is to combine separate disclosure regimes into a
single "money received" headline; that temptation is what the
project's claim-discipline rule is designed to resist.

Direct disclosed money to an MP, campaign-support money to a
party, party-mediated context, and modelled allocations describe
*different things* in the public record. Mixing them up isn't
just a methodology mistake — it can become an unfounded allegation
about a named individual, and that's not what the project is for.

Every public surface in the project — the app, the API, the
methodology page, the per-MP detail panel — preserves the
separation. A careful write-up does the same.

---

*If this walk-through helped you investigate something, the project
would be glad to hear about it. Discussions go in the public
[GitHub Discussions](https://github.com/mzyphur/political-influence-tracker/discussions);
data corrections go in the
[issue tracker](https://github.com/mzyphur/political-influence-tracker/issues).*
