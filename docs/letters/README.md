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

### Ready-to-sign Word versions

The same letters are also rendered as Microsoft Word `.docx` files
under [`word/`](word/), with only the letter content (sender block,
date, recipient, subject, salutation, body, sign-off) — none of the
markdown drafts' meta-content (status, project context, action items)
is carried into the Word output. The Word versions are the format
the project lead prints, signs, and sends.

| File | Recipient | Notes |
|---|---|---|
| [`word/aph_public_redistribution_request_house.docx`](word/aph_public_redistribution_request_house.docx) | The Clerk of the House of Representatives | One letter per chamber; the bracketed alternatives in the markdown draft (`[House / Senate]`, `Members' / Senators'`) are resolved to the House variant. |
| [`word/aph_public_redistribution_request_senate.docx`](word/aph_public_redistribution_request_senate.docx) | The Clerk of the Senate | Senate variant of the same letter, addressed to the Department of the Senate. |
| [`word/aec_gis_public_redistribution_request.docx`](word/aec_gis_public_redistribution_request.docx) | AEC GIS Section, Australian Electoral Commission | Single-letter ask for written confirmation that the project's vector-tiled treatment is within the existing "Derivative Product" permission. |

The Word files use Calibri 11pt, 2.5cm margins, right-aligned sender
block + date, left-aligned recipient block, bold subject line, and
a numbered-list body for the Department's questions. Placeholders the
project lead fills in before signing: `[Project Lead Name]`, the
sender address block, `[Date]`, and the signature line.

If the markdown drafts are edited, regenerate the Word versions
with the project's reproducible converter at
[`scripts/generate_letter_docx.py`](../../scripts/generate_letter_docx.py):

```bash
# python-docx is a one-off dependency; install it in a temp venv so it
# never touches the backend lockfile.
python3 -m venv /tmp/docx_venv
/tmp/docx_venv/bin/pip install python-docx
/tmp/docx_venv/bin/python scripts/generate_letter_docx.py
```

The script is deterministic: re-running with the same source content
produces equivalent `.docx` output. If the markdown drafts change,
edit the corresponding constants in the script (e.g. `APH_HOUSE_BODY`,
`AEC_GIS_BODY`) and re-run. Do NOT hand-edit the `.docx` files
directly — they're generated artifacts.

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
