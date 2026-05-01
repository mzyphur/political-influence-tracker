---
name: Feature request
about: Suggest a new capability, data source, or analysis surface
title: "[feature] <short summary>"
labels: ["enhancement", "needs-triage"]
---

## The problem you're trying to solve

What can't you do today, or what's harder than it should be? State
the user-facing problem before any solution. The project is more
likely to land on a fix that helps you if the problem is clearly
described.

## What you'd like to be able to do

A description of the new capability, data source, or analysis
surface. Concrete examples: "search MPs by total exposure," "filter
the map by year," "ingest a new state-level disclosure register."

## Why this fits the project's mission

The project's mission is **public transparency without
overclaiming**, and every public claim must travel with its
evidence tier and attribution caveat. Briefly explain how your
proposal fits that mission. In particular:

- Does it preserve the separation between direct, party-mediated,
  campaign-support, and modelled evidence families? (The project
  never sums these into a single "money received" headline.)
- Does it require a new public data source? If yes, what's the
  source's licence, and does the project already have a written
  redistribution permission for it (per `docs/source_licences.md`)?
- Does it require a fuzzy-matching step? (The AEC Register branch
  resolver does NOT do fuzzy matching; multi-row matches that
  deterministic disambiguation cannot break must fail closed.)

## Alternatives you've considered

Other ways to solve the same problem, including the option of
keeping the status quo.

## Additional context

Mockups, links to existing reports / dashboards that do something
similar, or anything else that helps the maintainers see what you
see.

---

By filing this issue you agree to abide by the project's
[Code of Conduct](../../CODE_OF_CONDUCT.md).
