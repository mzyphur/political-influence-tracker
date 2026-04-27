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

Suggested first public-interest sectors:

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

