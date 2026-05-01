<!--
Thanks for proposing a change. Please fill the sections below.
The maintainers focus on claim discipline, source-licence posture,
the direct-money-byte-identical invariant, and methodology
consistency — the more you address those up front, the smoother the
review.
-->

## Summary

A 1-2 sentence description of what this PR changes and why.

## Linked issue

Closes #<issue-number> (or "n/a — drive-by fix").

## What this touches

- [ ] Backend Python (`backend/`) — pipeline, parser, loader, API, schema
- [ ] Frontend TypeScript / React (`frontend/`)
- [ ] SQL schema migrations (`backend/schema/`)
- [ ] Pipeline / ingestion scripts (`scripts/`)
- [ ] Methodology HTML (`frontend/public/methodology.html`)
- [ ] Project docs under `docs/`
- [ ] CI workflows (`.github/workflows/`)
- [ ] Source-licence audit (`docs/source_licences.md`)
- [ ] Other (please describe)

## Claim-discipline review

The project's most important invariant: direct disclosed person-level
records, source-backed campaign-support records, party-mediated
context, and modelled allocation are kept as separate evidence
families and **never** summed into a single "money received" headline.

- [ ] This change does not conflate evidence families.
- [ ] If this change adds a new public surface, every claim on it
      travels with its evidence tier and attribution caveat.
- [ ] If this change adds a new modelled / estimated value, the UI
      explicitly labels it as "Est." (or equivalent) and ships a
      denominator-scope disclosure where applicable.
- [ ] N/A — this PR does not touch claim-bearing surfaces.

## Resolver / data-loader changes

The AEC Register branch resolver and any new loader must NOT do
fuzzy matching. Multi-row matches that deterministic disambiguation
cannot break must surface as `unresolved_multiple_matches`, not as
a guess.

- [ ] No fuzzy matching introduced.
- [ ] Direct-money totals are byte-identical before/after this
      change. (The cross-cutting test
      `test_loader_does_not_change_direct_representative_money_totals`
      still passes.)
- [ ] N/A — this PR does not touch resolvers or loaders.

## Source-licence posture

If this PR ingests a new public source, surfaces an existing source
in a new way, or changes the project's redistribution posture:

- [ ] `docs/source_licences.md` updated with verbatim publisher
      wording + redistribution status.
- [ ] README's "Source-data licence terms" section reflects the
      change.
- [ ] If the source is not yet cleared for public redistribution,
      the new surface is gated to local-development only.
- [ ] N/A — this PR does not touch source-licence posture.

## Tests

- [ ] `pytest backend/tests/ -q` passes locally.
- [ ] `AUPOL_RUN_POSTGRES_INTEGRATION=1 pytest` passes locally
      (if any backend code path was touched).
- [ ] `ruff check backend/` passes locally.
- [ ] `cd frontend && npm run build` passes locally
      (if any frontend code path was touched).
- [ ] New tests cover the new behaviour.

## Test plan / how to verify manually

A short list of commands / URLs / record IDs the reviewer can use
to verify the change behaves as described.

## Anything else

Screenshots, related issues, follow-up items, or explicit
out-of-scope items the reviewer should not block on.

---

By submitting this PR you confirm you have read and agree to the
project's [Code of Conduct](../CODE_OF_CONDUCT.md) and that your
contribution is licensed under the project's AGPL-3.0 source-code
licence (per [LICENSE](../LICENSE)).
