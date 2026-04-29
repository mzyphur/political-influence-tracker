# Research Standards

Last updated: 2026-04-28

These standards implement the operating theory in
`docs/theory_of_influence.md`: influence is treated as a set of observable,
source-backed mechanisms whose evidentiary limits must remain visible.

## Evidence Classes

Use these evidence classes throughout the database and public app.

| Class | Meaning | Public wording |
| --- | --- | --- |
| `official_record` | Directly from an official source such as AEC, APH, state electoral commission, legislation, or court/regulator record. | "Official record" |
| `official_record_index` | An official index/listing that points to source-of-record documents. It supports discovery and provenance but is not the same as parsed document content. | "Official index" |
| `official_record_snapshot` | Raw archived HTML/PDF/CSV bytes from an official source, with checksum and fetch metadata, before content-specific parsing. | "Archived official record" |
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

## Influence Event Standard

The public app should query a normalized `influence_event` surface instead of
forcing users to understand every source-specific table. Source-specific tables
such as `money_flow` and `gift_interest` remain the evidentiary backing.

Current event families:

- `money`: AEC financial-disclosure money flows, including donations/gifts,
  receipts, loans, and debts as source coverage expands.
- `benefit`: disclosed gifts, sponsored travel/hospitality, airline lounge
  access, tickets, meals, accommodation, flights/upgrades, subscriptions, and
  comparable non-cash benefits.
- `private_interest`: shareholdings, trusts, property, liabilities, assets,
  income, directorships, partnerships, and investments.
- `organisational_role`: memberships, offices, and donations declared as
  organisational relationships rather than as a benefit from the organisation.
- `access`: official registry context for lobbying/client/person relationships.
  These rows are not meeting records and must not be described as proof of
  access granted, successful lobbying, improper influence, or wrongdoing.
- `policy_behavior`, `procurement`, `grant`, and `appointment`: reserved
  families for votes/speeches, contracts, grants, and public appointments as
  those sources are added.
- They Vote For You division/vote records are `third_party_civic` evidence. They
  can support exploratory vote-behaviour analysis, but official parliamentary
  records should be used or cited where a public claim needs the source of
  record.

Every event should store:

- source and recipient identities where known;
- source raw names where identity resolution is unresolved;
- source document and page/row reference;
- amount/value and `amount_status`;
- `missing_data_flags` such as `value_not_disclosed`,
  `provider_not_disclosed_or_not_extracted`, and `event_date_not_disclosed`;
- evidence status, extraction method, and review status.

Vote-behaviour displays must keep association and causation separate. The
`person_policy_influence_context` view is only a context surface: it requires an
explicit reviewed `sector_policy_topic_link` before placing influence evidence
beside votes, buckets influence events by timing relative to the topic-vote span,
and must not be described as proof of quid pro quo or improper conduct without
additional reviewed evidence.

The app may say a small benefit is "tracked" only when it is disclosed,
discoverable in a source document, or otherwise supported by documented evidence.
For below-threshold or private-capacity items that leave no public trace, the
correct label is a disclosure gap, not a hidden fact.

## Manual Review Standard

Ambiguous evidence should be exported to review queues before it is used for
public-facing claims above low-level source facts. Review decisions must never
overwrite the raw or machine-produced record. They should be stored separately
with reviewer, timestamp, decision, evidence note, proposed changes, and any
supporting sources.

Current review-queue types:

- `official-match-candidates`: exact-name official identifier matches that need
  approval before identifiers are attached to canonical entities.
- `benefit-events`: small or non-cash benefits where provider, value, date, or
  extraction quality may need review.
- `entity-classifications`: inferred sector classifications that need official
  identifier support or manual confirmation before stronger public use.

Decision imports are audit-first:

- dry-run is the default;
- every input file is checksummed;
- every decision has a deterministic `decision_key` and payload hash;
- every reviewed subject should use a durable `subject_external_key`;
- every imported decision is stored append-only in `manual_review_decision`;
- side effects are allowlisted by subject type;
- generated/source evidence is never overwritten by a review import.

If a reviewed subject changed since export, the importer must fail or defer the
row rather than silently applying a decision to stale evidence.

After machine-generated rows are refreshed, stored decisions should be replayed
with the same conflict and fingerprint checks. Review queues should suppress
accepted, rejected, and revised subjects by stable subject key so review labor
does not disappear or duplicate after routine ingestion.

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
