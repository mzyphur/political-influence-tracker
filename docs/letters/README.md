# Project correspondence

This directory holds drafts of formal correspondence the project lead
needs to send before the public launch, plus archived replies once
they come back. It is intentionally part of the repo so the
project's licensing posture is auditable from the outside.

## Pending drafts

| File | Recipient | Purpose | Status |
|---|---|---|---|
| [`aph_public_redistribution_request.md`](aph_public_redistribution_request.md) | Clerks of the House and Senate | Clarify whether structured-record transformation of the registers of interests, MP/Senator contacts CSV, House Votes & Proceedings, and Senate Journals is a derivative work for CC BY-NC-ND 4.0 purposes; request an exception or scope clarification. | Draft, ready to sign |
| [`aec_gis_public_redistribution_request.md`](aec_gis_public_redistribution_request.md) | AEC GIS Section | Confirm that the project's re-projected, vector-tiled, publicly-served treatment of federal electorate boundary geometry sits within the AEC GIS End-user Licence's "Derivative Product" permission, with the verbatim attribution string. | Draft, ready to sign |

## Archive policy for replies

When a reply comes back:

1. Save the raw reply (PDF, screenshot of email, text export) under
   `docs/letters/replies/<recipient>_<YYYYMMDD>.{pdf,txt,html}`.
2. Add a short summary block to the bottom of the corresponding draft
   file recording the reply's load-bearing terms.
3. Update `docs/source_licences.md` with the new licence-status row
   (`ready` / `needs-follow-up` / `blocked`) and re-link the verified
   statement.

The standing rule is: if a reply hasn't arrived yet, the project keeps
the conservative blocked / needs-follow-up status documented in
`docs/source_licences.md`. Replies don't change project posture until
they're applied to that file.
