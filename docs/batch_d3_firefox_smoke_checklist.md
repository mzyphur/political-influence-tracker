# Batch D #3 — Frontend visual smoke (Firefox)

This is the human-side smoke checklist for the Batch D #3 task in
`docs/session_state.md`. The render paths it exercises were
audited code-side as part of Batch D #3 (no changes needed); this
checklist is the actual eyes-on confirmation that nothing regressed
visually after Batches C / D #1 / D #2 / D #4 / D #5 landed.

**Browser**: Use Firefox or the in-app browser. The project's
`CLAUDE.md` explicitly forbids Chrome for this kind of verification.

## Setup

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics"

# Make sure local Postgres is up.
/opt/homebrew/bin/docker-compose -f backend/docker-compose.yml up -d
/opt/homebrew/bin/docker-compose -f backend/docker-compose.yml exec -T postgres \
  pg_isready -U au_politics -d au_politics

# Run the latest migration + load AEC Register data + load postcode crosswalk.
cd backend
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money migrate-postgres
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-aec-register-of-entities
.venv/bin/dotenv -f .env run -- .venv/bin/au-politics-money load-postcode-electorate-crosswalk

# Start the API.
make api-dev   # runs uvicorn on 127.0.0.1:8008

# In a second shell, start the frontend dev server.
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics/frontend"
npm run dev
```

Open `http://127.0.0.1:5173/` (or the port `npm run dev` reports) in
Firefox.

## Checklist — current ALP MP (Batch D #1 surface)

1. **Map loads, electorate count matches.** Status pill bottom-right
   shows `N map features` (federal). No console errors.
2. **Click a current ALP-held electorate** (e.g. Chisholm, Robertson,
   Macarthur). The details panel should open with:
   - "Current Representation" block.
   - "Records Linked To This Representative" with Money / Gifts /
     Campaign Support sub-counts.
   - **"Party-Linked Money Exposure" panel** (Batch C/D #1) — should
     be non-empty for ALP MPs and contain at least one row labelled
     `ALP` (or `Australian Labor Party`).
3. **In the Party-Linked Money Exposure panel, the value column
   should show `Est. exposure $X.XXm`** (NOT a raw amount, NOT a
   personal-receipt label).
4. **The detail line below each `Est. exposure` row should include**:
   - "N reviewed party/entity receipt records"
   - "$X loaded-period party context"
   - "equal share across 123 current party representatives" (or
     however many active ALP MPs the local DB currently has)
   - "numerator scope: all loaded reviewed party/entity receipt records"
   - "denominator scope: current office-term party representatives
     only (asymmetric — see methodology)" — this is the
     **denominator-asymmetry chip**.
   - "N source documents"
   - The full claim-scope sentence ending in "...not a disclosed
     personal receipt or term-bounded total."
5. **The "scope-caption" paragraph above the panel rows reads**: "These
   are loaded-period receipts to reviewed party or associated-entity
   pathways. Equal-share values are analytical exposure estimates only;
   they are not term-bounded totals or disclosed money received by this
   representative."

## Checklist — current AG (Greens) MP

Repeat the same checks for an Australian Greens-held seat (e.g.
Melbourne, Brisbane, Ryan, Griffith). Confirm the Party-Linked Money
Exposure panel renders at least one row labelled `AG` /
`Australian Greens` and that the value shows `Est. exposure …`.

## Checklist — current LP / LNP / IND / NATS / KAP / ON MP

Visit at least one electorate held by each of the other federal
parties. Each should produce **either** a non-empty Party-Linked Money
Exposure panel OR no panel at all. None should display a panel that
references the deleted long-form party rows (id 1351 / 1389 / 1412 /
1444 / 1445 / 1460 / 1517 / 1692). The dedup migration `034` re-points
links to the canonical short-id rows; if you ever see a stale long-form
id surface here, that means the migration is not in the schema chain
or the loader was run against a pre-migration DB.

## Checklist — postcode search (Batch D #2)

1. Type `2600` into the search box. Expect TWO results: `2600 ->
   Canberra` (4 localities) and `2600 -> Bean` (1 locality), each with
   a state chip "ACT".
2. Type `3000`. Expect ONE result: `3000 -> Melbourne` (Melbourne CBD).
3. Type `0800`. Expect ONE result: `0800 -> Solomon`.
4. Click any postcode result. The map should pan to that electorate
   and the details panel should show the
   "source-backed AEC electorate candidate" note (full claim-scope
   message, NOT a definitive "this is your MP" assertion).

## Checklist — methodology page (Batch D #5)

1. Click the "Method" link in the top-right (or navigate to
   `/methodology.html`). The page should open in a new tab.
2. The top nav should now include the new anchors: "AEC Register",
   "Equal-share estimates", "Campaign support tiers", "Version".
3. Click each anchor and confirm the section scrolls into view.
4. The footer should show `Methodology version: 2026-04-30 · Repo
   revision 3f40524 (Batch D #5 - …)` and reference the three docs
   `docs/influence_network_model.md`, `docs/theory_of_influence.md`,
   `docs/campaign_support_attribution.md`.

## Checklist — claim-discipline copy (Batch D #4)

1. Search for `2600` and click a Canberra/Bean result. Confirm the
   selection note explicitly says "is not address-level proof of the
   current local member".
2. Open any electorate's details panel. Confirm somewhere on the page
   the user sees one or more of:
   - "Counts are descriptive and do not imply wrongdoing"
   - "Not a wrongdoing claim"
   - "do not claim causation or improper conduct"
   - "not proof of improper influence"
3. Open the influence graph for an MP. Confirm the bottom-of-graph
   caveat reads "prove causation or improper conduct" (in negation).

## Checklist — council/state map paths still work

1. Switch the data-level toggle from federal to state, and to council.
2. Confirm the map renders council/LGA boundaries.
3. Click a council polygon. Confirm the details panel renders with
   "Council Map Layer" heading and the local disclosure context, NOT
   a representative-style profile.

## Recording results

Record the run in the build log if anything regressed:

```bash
cd "/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics"
$EDITOR docs/build_log.md   # add a "## YYYY-MM-DD (Batch D #3 visual smoke)" section
```

If the smoke is clean, just update the entry in
`docs/session_state.md` to mark Batch D #3 done.
