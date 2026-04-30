# Influence Network and Allocation Model

This project treats political influence as a source-backed, typed network. The
goal is to show how disclosed money, gifts, interests, campaign support,
party-channelled support, lobbying/client relationships, and policy behaviour
connect without collapsing different evidence tiers into one misleading total.
The broader theoretical rationale is maintained in
`docs/theory_of_influence.md`.

## Core Principle

Money or benefits disclosed at a party, branch, campaign committee, associated
entity, or third-party level must not be described as money or gifts personally
received by an MP or Senator. The app may show those records as connected
context, and may calculate labelled allocation estimates, but the public record
scope must remain visible.

## Evidence Tiers

1. `direct_disclosed`
   - Source record names the MP, Senator, candidate, Senate group, or direct
     person-level recipient.
   - Public display may say "direct disclosed record" or "direct person-linked
     record".

2. `source_backed_campaign_context`
   - Source record names a candidate, Senate group, electorate, campaign
     committee, campaign expenditure, media-ad activity, public funding payment,
     or party-handled candidate campaign context.
   - Public display may say "campaign support connected to this contest" but
     must not say personal receipt.

3. `party_entity_context`
   - Source record names a party, state branch, associated entity, party
     foundation, affiliated organisation, or reviewed party/entity link.
   - Public display may show the party/entity profile and network path to
     current representatives, but not person-level receipt.

4. `modelled_allocation`
   - An analytical allocation from aggregate party/entity/campaign records to
     electorates, candidates, MPs, or Senators using an explicit model.
   - Public display must label this as "estimated allocation" or "modelled
     indirect exposure" and show the method, assumptions, uncertainty, and
     sensitivity range.

5. `policy_behaviour_context`
   - Vote, division, speech, committee, portfolio, bill, policy-topic, or
     ministerial-action context.
   - Public display may show timing, topic overlap, and association. It must not
     claim causation, quid pro quo, improper influence, or corruption without
     independent evidence.

## Graph Node Types

- `person`: MP, Senator, candidate, minister, former representative.
- `party`: parliamentary party or registered political party.
- `party_branch`: state/territory/federal branch where distinguishable.
- `associated_entity`: associated entity, foundation, trust, fundraising body.
- `source_entity`: donor, company, union, association, lobbyist client,
  individual donor, third party, campaigner, media/ad provider.
- `campaign_context`: candidate, Senate group, electorate contest, campaign
  committee, campaign expenditure context.
- `public_funding_source`: AEC or equivalent public funding payer.
- `policy_topic`: bill/topic/sector-linked policy area.
- `division_or_action`: vote, division, parliamentary decision, speech,
  committee action, ministerial decision where supported.

## Graph Edge Types

- `disclosed_money_flow`: source-backed money or receipt/debt/expenditure row.
- `disclosed_benefit_flow`: gifts, hospitality, travel, tickets, meals,
  flights, memberships, or other declared benefits.
- `campaign_support_flow`: candidate/Senate group expenditure, public funding,
  media ad activity, party-handled candidate campaign records, or third-party
  campaign expenditure.
- `party_entity_link`: reviewed association between party and branch/entity.
- `office_or_party_membership`: person currently or historically represents a
  party, chamber, electorate, or state/territory.
- `lobbying_registration_context`: official registration and client
  relationship, not proof of a meeting or access.
- `sector_classification`: official, reviewed, or inferred industry/sector
  classification with method/confidence.
- `policy_topic_link`: reviewed sector/material-interest link to a policy
  topic.
- `modelled_allocation_edge`: estimated allocation from aggregate record to a
  lower level, with method and uncertainty.

## Indirect Path Examples

The graph may display paths such as:

`Commonwealth Bank -> ALP entity/branch -> ALP MPs/Senators`

This path means:

- Commonwealth Bank appears in a source-backed disclosed flow involving an ALP
  party/entity record.
- The party/entity is reviewed as connected to ALP or is a directly named ALP
  party record.
- A representative is an ALP MP/Senator through office-term data.

It does not mean:

- Commonwealth Bank paid that MP/Senator personally.
- The MP/Senator changed behaviour because of the money.
- The payment was improper.

The graph may support calculations such as "indirect disclosed party/entity
exposure by sector for current ALP representatives", but the result must stay in
an indirect/modelled panel separate from direct disclosed records.

## Allocation Methods

Allocation methods should be versioned, reproducible, and sensitivity-tested.
Initial methods can include:

1. `no_allocation`
   - Show aggregate party/entity records only at the party/entity level.
   - Default for publication unless a lower-level source supports attribution.

2. `equal_current_representative_share`
   - Divide party/entity aggregate by the number of current representatives.
   - Useful only as a rough exposure index; weak for causal or spending claims.

3. `electorate_candidate_return_link`
   - Allocate only records that name a candidate, electorate, Senate group, or
     campaign context.
   - Source-backed campaign context, not personal receipt.

4. `vote_share_or_public_funding_generated`
   - Allocate public funding or campaign context by votes generated in a contest
     when source and electoral data support it.
   - Display as public funding generated by votes and paid to party/candidate.

5. `party_campaign_spend_model`
   - Estimate support using candidate-level expenditure returns, ad-library
     evidence, state/branch campaign records, and party return descriptions.
   - Must carry uncertainty intervals and source-completeness caveats.

6. `network_diffusion_weighted`
   - Propagate entity money through reviewed party/entity and office-term edges
     using documented weights.
   - Display as modelled indirect exposure, never as disclosed receipt.

## Required Metadata for Modelled Edges

Every `modelled_allocation_edge` must include:

- `model_name`
- `model_version`
- `input_source_document_ids`
- `input_event_ids`
- `allocation_basis`
- `allocation_denominator`
- `allocation_weight`
- `event_period_scope`
- `representative_scope`
- `party_context_label`
- `amount_estimate`
- `amount_lower_bound`
- `amount_upper_bound`
- `currency`
- `uncertainty_label`
- `display_caveat`
- `generated_at`

Current API graph scaffold:

- `modelled_party_money_exposure`
  - Uses reviewed party/entity links and current office-term party membership.
  - Reports `party_context_reported_amount_total` as loaded-period reviewed
    party/entity receipts. The current implementation does not claim this is
    term-bounded to an individual representative's service period.
  - Reports `modelled_amount_total` as a labelled equal-share exposure index
    when `allocation_method = equal_current_representative_share`.
  - Keeps `reported_amount_total` unset on the party-to-person edge so the
    value cannot be mistaken for a disclosed personal receipt.
  - Includes `claim_scope = analytical equal-share exposure ... not a disclosed
    personal receipt` for frontend display.

## AEC Register of Entities as the Source-Backed Origin of `party_entity_link`

Reviewed `party_entity_link` rows are the structural input to the
party-mediated exposure surface, the influence graph's reviewed-party path,
and the party profile money-flow surfaces. Until the AEC Register of
Entities ingestion, the local DB had **zero** reviewed links and these
surfaces rendered empty in production despite their plumbing being
complete.

The AEC Register of Entities is the official public registry of registered
political parties, associated entities, significant third parties, and
third parties. Each `associatedentity` row carries an explicit
`AssociatedParties` text field listing the parent party (often by state
branch). This is the source-backed origin from which we can produce
deterministic reviewed `party_entity_link` rows without human review per
row, while still respecting the C-rule: only resolve segments that map
unambiguously to one canonical `party.id`.

The deterministic resolver:

1. Exact normalized match against `party.name` / `party.short_name`.
2. Documented branch-alias rules (ALP/Liberal/Greens/Nationals state
   branches → canonical parent).
3. Parenthetical short-form alias (`Australian Labor Party (ALP)` →
   match by `ALP` short_name).

Multi-row matches (e.g. duplicate ALP rows in the local party table) fail
closed as `unresolved_multiple_matches`. Individual-name segments fail
closed as `unresolved_individual_segment`. No fuzzy similarity is used.

Auto-created links carry `method='official'`,
`confidence='exact_identifier'`, `reviewer='system:aec_register_of_entities'`,
and an evidence_note that records the AEC `ClientIdentifier`, raw
`AssociatedParties` segment, the resolver rule that fired, and the
attribution caveat: *"Official AEC branch/party relationship resolved to
canonical app party for display/network context; not proof of personal
receipt or candidate-specific support."*

The resolver is implemented in
`backend/au_politics_money/ingest/aec_register_branch_resolver.py` and the
loader in `backend/au_politics_money/db/aec_register_loader.py`, with
integration tests in `backend/tests/test_aec_register_loader.py` that
explicitly assert direct-representative money totals do not change after a
load.

## Denominator Asymmetry in `equal_current_representative_share`

The first allocation method shipped on the API,
`equal_current_representative_share`, is deliberately a rough exposure index. It
has a known asymmetry between its numerator and denominator that consumers must
keep in mind. The asymmetry is surfaced as both `event_period_scope` (numerator)
and `representative_scope` (denominator) chips in the response and in the UI
detail line for each row.

- Numerator (`event_period_scope = all_loaded_reviewed_party_entity_receipts`):
  every reviewed party/entity money receipt currently loaded into the database,
  with no time window. If the project loads several decades of AEC annual returns,
  the numerator includes all of them.
- Denominator (`representative_scope = current_office_term_party_membership`):
  the count of distinct people whose `office_term.term_end IS NULL` for that
  party. Only the current head-count.

Because the numerator is a long historical record while the denominator is a
single cross-section, the resulting per-representative figure is **not** a
"how much money each MP saw during their service" estimate. A wave-election
party that recently doubled its head-count will show a smaller per-rep figure
than a same-receipts party with stable membership; a party that recently lost
seats will show a larger one. The figure is useful only as a rough exposure
index and is labelled "Est. exposure" on every UI surface that exposes it.

The intentionally simpler current behaviour is acceptable because:

- The numerator and denominator are both faithfully labelled.
- The frontend never sums this estimate with direct or campaign-support
  records.
- The party-context reported amount total (the numerator) is exposed alongside
  the equal-share figure so a careful consumer can reproduce the calculation.

A future enhancement would compute the denominator over the union of office
terms active during the receipt window (`representative_scope =
union_of_office_terms_during_receipts`). That option preserves the historical
numerator and matches it with the historical denominator. It is more honest but
costs an extra join per request and an additional `denominator_period_scope`
sensitivity column that exposes the min/max of plausible denominators. The
field name is reserved for this enhancement when it lands; until then the
current asymmetry is the documented method.

## UI Rules

- Direct disclosed records appear first and keep source links visible.
- Campaign support appears in a separate campaign/context section.
- Party/entity-level money appears in party/entity and network panels.
- Modelled allocation appears only after the user can see the method and caveat.
- Representative profiles may show a compact `party_exposure_summary` derived
  from the same reviewed party/entity links and equal-share model, but it must
  remain visually separate from direct money and campaign support, must retain
  the "not a disclosed personal receipt" caveat, and must label loaded-period
  estimates as exposure indexes rather than money received.
- Direct, campaign, party/entity, and modelled totals are not summed into a
  single "money received" number.
- Network paths can show indirect relationships, but each edge must expose its
  type, evidence tier, source, review status, and caveat.

## Immediate Implementation Plan

1. Keep `campaign_support` records separate from direct money and benefits.
2. Add party/entity and candidate-review visual separation in the frontend.
3. Add graph/API support for typed indirect paths:
   `source_entity -> reviewed party/entity -> party -> current representatives`.
4. Add a non-public experimental allocation table or materialized view for
   `modelled_allocation_edge` records.
5. Expose allocation methods only after tests assert that direct totals exclude
   all modelled values.
6. Add documentation and UI text for every allocation method before enabling it
   in public views.
