---
name: Bug report
about: Something in the app, the API, the data pipeline, or the docs is wrong or broken
title: "[bug] <short summary>"
labels: ["bug", "needs-triage"]
---

## What's broken

A clear, factual description of what's not working. Not what you
think the cause is — what you actually observe.

## Where you saw it

- [ ] Public app (which page / which MP or postcode / what URL)
- [ ] Backend API (which endpoint / which params)
- [ ] Data pipeline (`make reproduce-federal` / `make reproduce-federal-smoke` / a specific `au-politics-money` CLI command)
- [ ] Documentation (which file)
- [ ] Frontend build (`npm run build` / `npm run dev`)
- [ ] CI workflow (which workflow / which job)
- [ ] Other (please describe)

## How to reproduce

1. Step one
2. Step two
3. ...

If reproduction requires a particular DB state, list the migrations
applied and the source documents loaded (or a `pg_dump --schema-only`
attached as a gist).

## What you expected

What the project's methodology / docs / current behaviour led you to
expect.

## What actually happened

The actual observed output, with relevant log lines, error
messages, or screenshots.

## Environment

- Repo commit: `<short SHA from `git rev-parse --short HEAD`>`
- OS + version:
- Python version (for backend issues): `python --version`
- Node version (for frontend issues): `node --version`
- Postgres version (for DB issues): `psql --version`

## Anything else

Anything that might help — related issues, recent changes, partial
workarounds you've tried.

---

By filing this issue you agree to abide by the project's
[Code of Conduct](../../CODE_OF_CONDUCT.md). For security issues
or for code-of-conduct concerns, do **not** use a public issue —
see [SECURITY.md](../../SECURITY.md) and
[CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md) for the private
channels.
