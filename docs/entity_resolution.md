# Entity Resolution and Industry Coding

## Purpose

The project needs to answer "who is this donor/source?" without collapsing
distinct individuals, companies, trusts, unions, or party entities into the same
record too aggressively.

## Entity Types

Initial entity types:

- `individual`
- `company`
- `union`
- `association`
- `trust`
- `political_party`
- `party_branch`
- `associated_entity`
- `third_party_campaigner`
- `significant_third_party`
- `government`
- `foreign_government`
- `lobbyist`
- `unknown`

## Matching Order

1. Exact official identifier: AEC entity ID, ABN, ACN, ARBN, ASIC number.
2. Exact normalized name within same source context.
3. Exact name plus address/location context.
4. Known alias table.
5. Fuzzy name match plus supporting public evidence.
6. Human review.

## Normalization Rules

Name normalization should be conservative:

- Lowercase.
- Strip punctuation and repeated whitespace.
- Normalize `pty ltd`, `proprietary limited`, `limited`, `inc`, and similar
  suffixes into a comparable form while preserving the original name.
- Preserve trust names, fund names, and branch names.
- Do not merge state branches of political parties unless explicitly doing a
  grouped-party analysis.
- Do not merge related corporations unless the relationship is separately stored.

## Industry Taxonomy

Use two parallel classifications:

1. Official ANZSIC where available.
2. Public-interest sector for analysis and visualization.

Implemented first public-interest sectors:

- fossil_fuels
- mining
- renewable_energy
- property_development
- construction
- gambling
- alcohol
- tobacco
- finance
- superannuation
- insurance
- banking
- technology
- telecoms
- defence
- consulting
- law
- accounting
- healthcare
- pharmaceuticals
- education
- media
- sport_entertainment
- transport
- aviation
- agriculture
- unions
- business_associations
- charities_nonprofits
- foreign_government
- government_owned
- political_entity
- individual_uncoded
- unknown

## Current Automated Classifier

The first classifier is `public_interest_sector_rules_v1`.

It is intentionally conservative and reproducible:

- Input: latest processed AEC annual money-flow JSONL plus latest House and
  Senate interest-record JSONL.
- Output: `data/processed/entity_classifications/<timestamp>.jsonl` and a
  matching summary JSON.
- Method: rule-based name patterns only.
- Confidence: clear sector/name patterns are `fuzzy_high`; company/trust suffix
  and individual-name-shape detections are `fuzzy_low`; non-matches are
  `unresolved`.
- Database load: generated rows are replaceable. Reloading deletes and rewrites
  rows whose metadata has `classifier_name = public_interest_sector_rules_v1`.

This classifier does not yet use official ANZSIC, ABN, ACN, ASIC, ACNC, or
manual review evidence. Public-facing analysis should label these values as
inferred classifications until reviewed or supported by official identifiers.

## Official Identifier Enrichment

Implemented first stage:

- ASIC, ACNC, ABN Bulk Extract, and lobbyist-register parsers produce
  `official_identifier_record_v1` JSONL records.
- The Australian Government Register of Lobbyists API is snapshotted by
  organisation profile, including registered lobbying organisations, clients,
  ABNs where present, and public lobbyist-person observations.
- `official_identifier_observation` stores official observations separately
  from canonical `entity` rows.
- `entity_match_candidate` stores exact-name candidates for review.
- Existing entities are not assigned ABNs, ACNs, lobbyist-register IDs, or
  official classifications from name-only matches. Auto-acceptance requires an
  existing identifier match or a later manual-review workflow.
- Manual review subjects use stable external keys. Numeric database IDs may be
  exported for operator context, but accepted/rejected/revised decisions replay
  and suppress queues by stable source/entity keys, entity type, and matching
  fingerprints.

Current 2026-04-28 official identifier load:

- 3,602 parsed records: 378 lobbying organisations, 2,498 clients, and 726
  lobbyist-person observations.
- 1 targeted ABN Lookup web-service record for BHP Group Limited.
- 3,591 unique database observations after stable-key de-duplication.
- 393 exact-name match candidates requiring review.
- 0 identifiers auto-attached from name-only matches.

Current 2026-04-27 artifact:

- 35,874 normalized entity names.
- 23,648 names with a non-unknown public-interest sector.
- 12,226 unknown/uncoded names.
- 27,059 names recommended for review because they are `fuzzy_low` or
  `unresolved`.

High-volume sectors in the current artifact include:

- `individual_uncoded`: 14,833
- `unions`: 1,482
- `finance`: 1,017
- `political_entity`: 904
- `property_development`: 582
- `business_associations`: 470
- `mining`: 278
- `fossil_fuels`: 205

## Human Review Queue

Every uncertain match should generate a review item with:

- Source record ID.
- Raw donor/source string.
- Candidate entity IDs.
- Match features.
- Suggested classification.
- Confidence.
- Reviewer decision.
- Reviewer note.
- Decision timestamp.
