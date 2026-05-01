---
name: Data correction
about: Report a record the project surfaces wrongly, a missing source link, or a claim that overstates the underlying source
title: "[data] <MP/Senator/electorate/postcode> — <short summary>"
labels: ["data-correction", "needs-triage"]
---

> Data corrections are the most valuable contribution category for
> the project's mission. If you've read the underlying source
> document and the project's surface gets it wrong, the project wants
> to know.

## What the project currently shows

Which page / API field / map feature shows the issue. Quote the
exact text or value the project surfaces today.

If you can, paste the URL of the public app page (or the API
endpoint + params), and the short SHA of the build the issue is
visible on (the methodology page's footer carries the build SHA).

## What the underlying source actually says

The project's standing rule is that every public claim must travel
with its evidence tier and a link back to the original public source
document. So please:

1. Quote the relevant section of the source document (PDF page
   number, JSON field, CSV row — whatever applies).
2. Paste the URL of the public source document.
3. If your reading differs from the project's, say specifically how.

Without these three the maintainers can't act on the report.

## Which evidence family is affected

The project keeps four evidence families strictly separate. Tick
the one your correction sits in:

- [ ] **Direct disclosed person-level records** (e.g. an MP's
      register of interests)
- [ ] **Source-backed campaign-support records** (e.g. AEC annual
      / election disclosure returns)
- [ ] **Party-mediated context** (e.g. AEC Register of Entities
      links between a party and an associated entity)
- [ ] **Modelled allocation** (e.g. equal-share exposure
      estimates across a current office-term party caucus)
- [ ] **Source-licence posture** (e.g. the project surfaces data
      in a way that conflicts with the licence captured in
      `docs/source_licences.md`)

Knowing the family helps the maintainers preserve the
"never sum across families" invariant when designing the fix.

## What you think the right answer should be

What should the project's surface say instead? Specific text /
specific value, plus a one-line explanation grounded in the source
document.

## Confidence

- [ ] I have read the underlying source document myself.
- [ ] I have only read the project's summary surface (no source
      document review yet).
- [ ] I am reporting a possible inconsistency I noticed in passing,
      not a confirmed issue.

The first option carries the most weight; the second and third are
still welcome but the maintainers will need to do the source-document
review before acting.

## Anything else

If the issue is sensitive (involves a named individual, a serving
MP, a court matter, or content the project may be asked to redact),
note that here. Sensitive corrections are still handled in the
public issue tracker — the public-record nature of the underlying
source is what makes the project a transparency tool — but the
maintainers will be more careful about microcopy in the fix.

---

Thanks for helping make Australian political-influence records
easier to read without overclaiming. Filing this issue means you
agree to abide by the project's
[Code of Conduct](../../CODE_OF_CONDUCT.md).
