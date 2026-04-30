# Sub-National Party Seeds Rollout Plan

Last updated: **2026-04-30**

This document records the deferred design for surfacing
state-jurisdiction party exposure on the public app. It is not part of
the federal launch; it is the next layer once federal launch is
public.

## Why this is deliberately deferred

After Batches D / E / F / G, the resolver folds every AEC Register
state-branch wording (e.g. "Australian Greens (NSW Branch)",
"Liberal Party of Australia (Victorian Division)", "National Party of
Australia (S.A.) Inc.") into the corresponding federal canonical
party row. That gives the federal map a clean surface but loses
state-level distinction.

The right time to seed state-jurisdiction party rows is when the
project is ready to:

1. Display state-level disclosure context on a state MP's profile,
2. With a UI affordance that distinguishes state-jurisdiction party
   exposure from federal party exposure,
3. Backed by a state-level disclosure dataset (QLD ECQ already loaded;
   NSW / VIC / others on the deferred state/local rollout).

Doing it earlier would invite the same conflation risk the C-rule was
written to prevent: a state-level reviewed `party_entity_link` row
silently rendering on a federal MP's profile because nothing in the
schema forces the API to filter by jurisdiction.

## What changes when state seeds land

Three coordinated changes need to ship together for any single
jurisdiction (call this the "state-rollout PR shape"):

1. **Seed migration** (`schema/0NN_seed_<state>_canonical_party_rows.sql`)
   that adds the state-branch rows under the matching state
   `jurisdiction_id` (NSW=…, VIC=…, etc.). Each row carries
   `seed_source`, `seed_date`, `seed_rationale`, and
   `state_branch_of` keys in metadata. The federal canonical row
   stays exactly as-is — the state-jurisdiction row is a peer, not a
   replacement.

2. **Resolver enhancement.** `aec_register_branch_resolver.py` is
   currently anchored to a single `source_jurisdiction_id` (federal
   for the AEC Register). The state rollout introduces:
   - A second resolver invocation per source: when a register-row
     observation names "Australian Greens (NSW Branch)", the resolver
     can produce TWO links — one to the federal canonical Australian
     Greens row (the existing behaviour) AND one to the new NSW state
     Greens canonical row.
   - The deterministic disambiguation rule still applies per call
     (federal call narrows to federal-jurisdiction matches; NSW state
     call narrows to NSW-jurisdiction matches).

3. **API + frontend surfaces.** `_representative_party_exposure_summary`
   already groups by `office_term.party_id`. To surface state-level
   exposure separately:
   - The query needs a jurisdiction filter.
   - The response shape gets a `jurisdiction` chip on each row.
   - The frontend renders state and federal exposure in distinct
     panels (e.g. "Federal party-mediated exposure" + "NSW state
     party-mediated exposure"), with the existing claim-discipline
     copy preserved on each.

## Scope per jurisdiction

The first state rollout target is **QLD** because the QLD ECQ EDS
data is already loaded (49,838 disclosure rows; see
`docs/reproducibility.md`). The state branches the AEC Register
references for QLD that need state-jurisdiction canonical rows:

- Australian Labor Party (State of Queensland) → existing federal
  canonical, plus a new QLD-jurisdiction row id 152936 (which is
  already present from QLD ECQ ingestion).
- Liberal National Party of Queensland → already has federal
  canonical id 6 + QLD-jurisdiction id 152939.
- Australian Greens (Queensland) → currently folds federal; needs a
  QLD-jurisdiction row.
- Katter's Australian Party → already has federal id 66 +
  QLD-jurisdiction id 152969.
- Independent → federal id 11 + QLD-jurisdiction id 153001.

Most of the QLD state-jurisdiction rows already exist; the work is
mostly resolver-side (emit the additional state link) plus API
surface.

For NSW, VIC, SA, TAS, WA, ACT, NT — same shape, but the
state-jurisdiction party rows mostly do NOT exist yet. Each state
gets its own seed migration following the QLD pattern.

## Test coverage required

For every state rollout PR:

- A resolver unit test that exercises the dual-resolution path
  (federal + state) and asserts BOTH canonical rows are returned
  with the right rule_id metadata.
- A loader integration test that confirms the AEC Register loader
  emits the right `party_entity_link` rows pointing at the
  state-jurisdiction party id.
- A regression test on `_representative_party_exposure_summary` that
  asserts a federal MP's panel does NOT include state-jurisdiction
  links and vice versa.
- The existing
  `test_loader_does_not_change_direct_representative_money_totals`
  invariant must continue to pass.

## Out of scope

- Re-allocating direct money flows by jurisdiction. That stays as-is
  (the recipient's stated jurisdiction at disclosure time wins).
- Changing the federal canonical rows. State seeds are peers, never
  replacements.
- Cross-jurisdiction "merger" rules. ALP-Federal and ALP-QLD are
  legitimately separate organisations even though they share a
  brand.

## When to revisit

After:

1. Federal launch is public.
2. State/local expansion item #6 in `docs/session_state.md` is
   re-prioritised.
3. The QLD-jurisdiction display surface in the frontend has been
   built and copy-reviewed.
