# Security policy

Thanks for helping keep the project and its users safe.

## Supported versions

The project's source-of-truth is the `main` branch of this repository.
There are no separate release branches at this stage. Security
updates land on `main` and are reflected in the methodology page's
revision marker (auto-stamped at build time from
`git rev-parse --short HEAD`).

## Reporting a vulnerability

**Please do not report security issues by opening a public GitHub
issue.** Instead, send a private email to:

> **mzyphur@instats.org**

Use the subject line:

```
[security] political-influence-tracker — <one-line summary>
```

Include in the body:

1. A short description of the issue.
2. The repository commit (or build) you tested against.
3. Reproduction steps, ideally a minimal example.
4. The impact you observed (data exposure, ability to write data
   you should not be able to write, broken claim discipline,
   broken source-licence posture, etc.).
5. Whether you'd like to be credited in the fix's commit message
   (and how).

You should expect an acknowledgement within a few business days.
Time-to-fix depends on severity and on the maintainer's available
time, but the project aims to land a fix within 30 days for
high-impact issues.

## Scope

The repository's security surface includes:

- The Python backend (`backend/`) and its API surface.
- The TypeScript frontend (`frontend/`).
- The data-pipeline ingestion + loading scripts under
  `backend/au_politics_money/` and `scripts/`.
- The CI workflows under `.github/workflows/`.
- The repository's published methodology page
  (`frontend/public/methodology.html`) and the auto-stamping hook
  that injects build-time provenance into it.

In particular, please report:

- Any way to make the public app surface a claim that is **not**
  source-backed (i.e. cannot be traced to a specific public source
  document with a verifiable URL and evidence tier).
- Any way to make the app conflate direct disclosed person-level
  records with party-mediated, campaign-support, or modelled
  evidence families.
- Any path that exposes API keys, source content the project does
  not have a redistribution licence for, or other secret material
  from the local environment.
- Any SQL injection, XSS, CSRF, SSRF, path traversal, deserialization
  vulnerability, or similar standard web-application issue.
- Any way to bypass the claim-discipline rules in
  `docs/source_licences.md`, `docs/influence_network_model.md`, or
  `docs/campaign_support_attribution.md` through the public API.

## Not in scope

- Vulnerabilities in upstream dependencies that have already been
  reported to the upstream project. (Please do tell us about them
  so we can roll out the upgrade — but the disclosure obligation
  belongs to the upstream first.)
- Issues that require a malicious local administrator already on
  the host running the app.
- Findings that are already documented under "Known limitations"
  on the methodology page (e.g. postcode-coverage gaps for
  leading-zero ranges).

## Source-licence reports

If you spot a source-licence inconsistency — for example, the
project surfaces data in a way that conflicts with the licence
captured in `docs/source_licences.md` — that is a high-priority
report. Please use the same private channel above. Public
redistribution decisions are load-bearing for the project's
posture, and getting them wrong is treated as a security issue.

## Disclosure

The project follows responsible disclosure: a private acknowledgement
first, a fix on `main` as soon as practical, and a public
write-up (in the commit message and in `docs/build_log.md`) once
users have had a reasonable window to update.
