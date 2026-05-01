# Contributing

Thanks for considering a contribution to the Australian Political
Influence Transparency project. The repository is public, the code
is AGPL-3.0, and the project's mission is to make already-disclosed
political-influence records easier to read without overclaiming.

## Project mission and operating constraints

This is **not** a political opinion site or a watchdog campaign
platform. It is a reproducible, source-backed transparency tool. A
few constraints shape every contribution:

1. **Claim discipline is the project's most important invariant.**
   Direct disclosed person-level money, source-backed campaign-
   support records, party-mediated context, and modelled allocation
   are kept as separate evidence families and **never** summed into
   a single "money received" headline. Every public claim travels
   with its evidence tier and attribution caveat. If a contribution
   would conflate these, it will be declined or sent back for
   restructuring.
2. **Direct-money totals must be byte-identical** before/after any
   change that touches related paths. The cross-cutting test
   `test_loader_does_not_change_direct_representative_money_totals`
   guards this.
3. **No fuzzy similarity** in the AEC Register branch resolver.
   Match exactly, fail closed otherwise. Multi-row matches that
   deterministic disambiguation cannot break must surface as
   `unresolved_multiple_matches`, not as a guess.
4. **Source/licence wording is conservative.** Use the verbatim
   wording from `docs/source_licences.md`. Don't promise reuse
   permission until the licence is captured there.

## Code of conduct

Participation in this project is governed by the
[Contributor Covenant v2.1](CODE_OF_CONDUCT.md). By participating
you agree to abide by it.

## Reporting security vulnerabilities

Do **not** open a public issue. See [`SECURITY.md`](SECURITY.md) for
the private disclosure channel.

## Reporting data-quality / claim-correction issues

If you spot a misclassified record, a missing source citation, or a
claim that overstates the underlying source: open a
**"Data correction"** issue (template available). Include the
specific MP/Senator + record + your reading of the source document.
This is the most valuable contribution category for the project's
mission.

## Setting up the project locally

The full set-up + reproduction commands live in the top-level
[`README.md`](README.md) under "Reproduce These Numbers Yourself"
and in [`docs/reproducibility.md`](docs/reproducibility.md). The
short version:

```bash
git clone https://github.com/mzyphur/political-influence-tracker.git
cd political-influence-tracker
make reproduce-federal-smoke   # fast CI mode, ~few minutes
# or
make reproduce-federal         # full live fetch (much longer)
```

You'll need: Python 3.11+, Node 22, Docker (for PostGIS), and ~20 GB
of disk for the full federal cache. The smoke mode is much smaller
and is what CI runs on every push.

## Submitting a change

1. **Open an issue first** for anything bigger than a typo or a
   one-line cleanup. The issue is where scope is agreed; the PR is
   where the change is reviewed. If you skip the issue and the PR
   turns out to be out of scope, the work is wasted.
2. **Fork + branch.** Branch naming: `feat/<short-description>`,
   `fix/<short-description>`, `docs/<short-description>`,
   `chore/<short-description>`. Match the prefixes used in
   `git log --oneline`.
3. **Land tests + ruff clean.** Every PR must keep
   `pytest backend/tests/` and `ruff check backend/` green. If you
   change Python code, also keep
   `AUPOL_RUN_POSTGRES_INTEGRATION=1` happy. The `ci.yml` workflow
   runs both on every PR.
4. **Land the frontend build.** If you change `frontend/`, run
   `cd frontend && npm run build` locally and confirm it stays
   clean. CI runs this too.
5. **Match the commit-message style.** One-line subject in the
   imperative mood (`feat: …`, `fix: …`, `docs: …`, `chore: …`,
   `ci: …`), 1–3 sentence body explaining *why*. The recent commit
   log is the canonical reference.
6. **Open the PR against `main`.** Fill in the PR template
   (`.github/PULL_REQUEST_TEMPLATE.md`). The template asks: what
   evidence-tier surfaces are touched, what the test plan is, and
   what the source-licence implications are.
7. **Be ready for revision-rounds.** Reviews focus on claim
   discipline, source-licence posture, the
   direct-money-byte-identical invariant, and methodology
   consistency. Mechanical fixes (tests, formatting) are usually
   waved through.

## What's a good first contribution?

- **Add a state/local jurisdiction.** The plan is documented at
  `docs/sub_national_party_seeds_plan.md` and is gated behind the
  May 2026 federal launch but suggestions / draft PRs are welcome.
- **Improve the methodology page.** The page at
  `frontend/public/methodology.html` is the public face of the
  project's claim discipline. Suggestions for clearer language,
  better diagrams, or new sections are high-value.
- **File a data-correction issue.** Pick an MP / senator, read
  their actual disclosed record, and compare to what the project
  surfaces. If anything's off, file an issue with the source-
  document URL and the discrepancy.
- **Run the reproduction chain on your machine** and report the
  outcome. Reproducibility is load-bearing; if something breaks
  outside the maintainer's environment, that's a real bug.

## Decisions reserved to the maintainer

- Headline framing on the public page (claim discipline)
- Source-licence posture (the
  [`docs/source_licences.md`](docs/source_licences.md) file is
  load-bearing for public redistribution decisions)
- Anything that would conflate direct vs party-mediated vs
  campaign-support vs modelled evidence families
- Anything that would weaken the AEC Register branch resolver into
  fuzzy matching

Thanks for helping make Australian political-influence records
easier to read without overclaiming.
