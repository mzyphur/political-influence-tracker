# Research Standards

Last updated: 2026-04-27

## Evidence Classes

Use these evidence classes throughout the database and public app.

| Class | Meaning | Public wording |
| --- | --- | --- |
| `official_record` | Directly from an official source such as AEC, APH, state electoral commission, legislation, or court/regulator record. | "Official record" |
| `official_record_parsed` | Extracted from an official document, usually PDF/HTML/CSV, with parser metadata. | "Parsed from official record" |
| `third_party_civic` | Reputable civic dataset such as They Vote For You or Open Politics. | "Civic data source" |
| `journalistic` | Credible journalism used for context, not primary record replacement. | "Reported context" |
| `academic` | Peer-reviewed or scholarly source. | "Academic source" |
| `inferred` | Derived classification or link made by our pipeline or reviewers. | "Inferred classification" |
| `manual_reviewed` | Human-reviewed extraction or match. | "Reviewed" |

## Claim Levels

The public app must separate low-level facts from high-level interpretation.

| Level | Allowed claim | Example |
| --- | --- | --- |
| 1 | Source fact | "The AEC record lists X as giving $Y to Z." |
| 2 | Normalized fact | "X is treated as the same donor as X Pty Ltd based on ABN match." |
| 3 | Classification | "X is classified as fossil fuels because its primary business is oil and gas extraction." |
| 4 | Association | "Before this vote, this MP/party had recorded receipts from donors in this sector." |
| 5 | Pattern | "This sector is concentrated among these recipients over this period." |
| 6 | Causal or corrupt conduct claim | Only use if supported by legal finding, official investigation, admission, or a strong published research design. |

Default public language should stop at levels 1-5.

## Language Rules

Use:

- "received", "declared", "reported", "listed", "disclosed"
- "associated with", "co-occurs with", "before/after", "same sector"
- "potential conflict", where supported by conflict-of-interest standards
- "cannot determine from public data", where applicable

Avoid unless legally established:

- "bribe"
- "quid pro quo"
- "bought"
- "corrupt"
- "illegal"
- "payoff"
- "controlled by"

The site can explain structural corruption and political economy, but individual
records must stay tied to evidence.

## Source Preservation

Every source document should store:

- Source ID.
- Original URL.
- Fetch timestamp in UTC.
- HTTP status and content type.
- SHA-256 checksum.
- Raw file path.
- Parser name and version when parsed.
- Extraction timestamp.
- Page/row/cell reference where applicable.

## Entity Resolution Standard

Entity matching must store confidence.

| Confidence | Meaning |
| --- | --- |
| `exact_identifier` | ABN, ACN, AEC entity ID, or another reliable unique identifier matches. |
| `exact_name_context` | Exact name plus strong contextual match, such as same address or same registered entity category. |
| `fuzzy_high` | Strong fuzzy name match with supporting context. |
| `fuzzy_low` | Possible match that needs review. |
| `manual_reviewed` | Human-approved match with reviewer and date. |
| `unresolved` | No reliable match. |

Never collapse donors with only weak evidence.

## Industry Classification Standard

Store both official and public-facing classifications:

- ANZSIC code and label where available.
- Public-interest sector label for user-facing analysis.
- Classification method: official, rule-based, model-assisted, manual.
- Evidence note.
- Confidence.

When public ABR/ASIC data lacks ANZSIC, classify using public evidence such as
company descriptions, annual reports, websites, lobbyist registers, and known
sector lists. Mark this as inferred unless manually reviewed.

## Defamation and Fairness

Australian defamation law makes precision essential. The project should:

- Use official records as the backbone.
- Preserve exact source wording.
- Avoid imputing criminality without findings.
- Give users source links and caveats.
- Allow correction workflows.
- Maintain a visible methodology page.

## Reproducibility

For any published analysis:

- Pin data snapshot date.
- Pin parser versions.
- Export code used for tables/charts.
- Include limitations and missing-data notes.
- Distinguish federal, state, territory, and local disclosure regimes.

