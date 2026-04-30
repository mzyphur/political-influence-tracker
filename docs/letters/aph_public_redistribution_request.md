# Draft: Public-redistribution exception request — Department of the House of Representatives + Department of the Senate

**Status:** Draft for the project lead to review, sign, and send. Saved
in the repository so the request and any reply are auditable.

**Project context:** The Australian Political Influence Transparency
project (working title; see [README](../../README.md)) is a public-
interest, source-backed transparency tool that surfaces disclosed
money, gifts, hospitality, and registered interests linked to
Australian federal MPs and senators. The system parses public-record
PDFs (e.g. House Members' Interests, Senate Senators' Interests) and
public-record CSVs (e.g. APH MP/Senator contacts) into structured
records that the project's public app and API surface alongside the
original source documents.

The project's per-source licence audit is at
[`docs/source_licences.md`](../source_licences.md). That audit records
that APH website material — including the registers of interests, the
MP/Senator contacts CSV, House Votes & Proceedings, and Senate
Journals — is published under the **Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International** licence
(CC BY-NC-ND 4.0). The "NoDerivatives" clause is the load-bearing
constraint here: the project's parsing and structuring of the
register PDFs into JSON, CSV, and database rows is, on its face, a
derivative work and is not permitted under the standard CC-BY-NC-ND
licence.

The project is not yet publishing this material. Local development
and reproducibility runs are within the existing licence terms (no
public redistribution). Before the project's first public release we
need an explicit written exception from the relevant Department(s)
clarifying:

1. Whether the Department considers the project's structured-record
   transformation of the registers of interests, MP/Senator contacts
   CSV, House Votes & Proceedings, and Senate Journals to be a
   derivative work for the purposes of the CC BY-NC-ND 4.0
   restriction; and
2. If so, whether the Department is willing to grant an exception
   permitting the project to publish those structured records,
   subject to attribution and any other reasonable conditions; or
3. Alternatively, what scope of public-facing surface (e.g.
   verbatim PDFs and CSVs only, with no structured-record JSON)
   would be permissible without an exception.

The project's public-redistribution policy is conservative: until
written terms are captured, parsed register-of-interests records
remain in the local development database only. The transparent
operating constraint and the reproducibility chain are documented at
[`docs/source_licences.md`](../source_licences.md) and
[`docs/reproducibility.md`](../reproducibility.md).

## Suggested addressees

- The Clerk of the House of Representatives —
  Department of the House of Representatives, Parliament House,
  Canberra ACT 2600.
- The Clerk of the Senate —
  Department of the Senate, Parliament House, Canberra ACT 2600.

(One letter per chamber; the registers are owned by the respective
departments.)

## Suggested wording

> Dear Clerk,
>
> I am the lead on the Australian Political Influence Transparency
> project, a public-interest source-backed transparency tool that
> publishes a reproducible link from disclosed federal political
> records back to the original public source documents.
>
> The project's data layer parses material that the Department of
> the [House / Senate] publishes under Creative Commons
> Attribution-NonCommercial-NoDerivatives 4.0 International on the
> Parliament of Australia website. Specifically, we ingest:
>
> - The Register of Members' [or Senators'] Interests PDFs;
> - The MP [or Senator] contacts CSV from
>   `https://www.aph.gov.au/Senators_and_Members/Members/...`;
> - House Votes and Proceedings [or Senate Journals] decision-record
>   indexes and PDFs.
>
> Our public app surfaces these records alongside the original PDFs
> and clearly labels every claim with its evidence tier and
> attribution caveat. We do not paywall the data, do not run
> advertising on it, and are not a commercial entity. We treat
> structured-record transformations of the source PDFs as derivative
> works for the purposes of the CC BY-NC-ND 4.0 licence, and we are
> not yet publishing those transformations.
>
> Could the Department please advise:
>
> 1. Whether the Department considers our structured-record
>    transformation of the [registers of interests / contacts CSV /
>    Votes and Proceedings / Senate Journals] a derivative work for
>    the purposes of the CC BY-NC-ND 4.0 licence;
> 2. If so, whether the Department is willing to grant an exception
>    permitting us to publish those structured records — with
>    attribution and any other reasonable conditions the Department
>    asks for; and
> 3. If an exception is not appropriate, what surface (e.g. verbatim
>    PDFs and CSVs with no JSON / CSV transformation) would be
>    permissible without an exception.
>
> Our reproducibility policy is at
> `docs/reproducibility.md` in the project repository. Every public
> claim travels with its evidence tier, attribution caveat, and a
> link back to the original source document. We would welcome any
> conditions the Department considers appropriate.
>
> Yours faithfully,
>
> [Project lead]

## Action item for the project lead

1. Sign the letter, send to both Clerks.
2. Save the reply (PDF or text) under `docs/letters/replies/` once
   received, with the licence-status update applied to
   `docs/source_licences.md`.
