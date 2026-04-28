# Federal Data Coverage Audit

Last updated: 2026-04-28

This audit tracks whether the federal build can show useful, source-backed
information about money, gifts, hospitality, travel, interests, lobbying/access,
and parliamentary behaviour for Australian MPs and Senators.

## Current Federal Coverage

Loaded source families:

- AEC annual financial disclosure bulk data from the AEC Transparency Register
  download surface: 192,201 normalized money-flow rows. Official source:
  <https://transparency.aec.gov.au/> and
  <https://transparency.aec.gov.au/Download>.
- AEC Member of the House of Representatives and Senator returns are present in
  the annual disclosure data and individual return pages. Official source:
  <https://transparency.aec.gov.au/MemberOfParliament>.
- House Register of Members' Interests: 5,853 structured records from current
  House PDFs. Official source:
  <https://www.aph.gov.au/Senators_and_Members/Members/Register>.
- Senate interests: 1,752 structured records from 76 official Senate statements.
  Official source:
  <https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests/Senators_Interests_Register>.
- Lobbyist-register observations: 3,591 official identifier observations,
  including lobbying organisations, clients, lobbyist people, and former
  representatives. Official source:
  <https://www.ag.gov.au/integrity/australian-government-register-lobbyists>.
- Voting: 482 official APH divisions parsed from Senate Journals and House
  Votes and Proceedings PDF records, comprising 335 Senate divisions and 147
  House divisions, plus 399 They Vote For You divisions/enrichments. The latest
  official APH parser artifact has zero division count mismatches and preserves
  11 `Ms Ley` House vote names as unmatched current-roster names rather than
  guessing. Official APH sources:
  <https://www.aph.gov.au/Parliamentary_Business/Chamber_documents/HoR/Votes_and_Proceedings>
  and
  <https://www.aph.gov.au/About_Parliament/Senate/Powers_practice_n_procedures/~/~/link.aspx?_id=732F8182C02D4B3699E417F33843A933>.

Current local `influence_event` coverage after the 2026-04-28 reload:

- Money: 192,201 events; 50 now person-linked; AUD 12,433,325,687 reported
  across all loaded AEC money events.
- Benefit/gift/travel/hospitality: 1,390 person-linked events.
- Private interests: 4,700 person-linked events.
- Organisational roles: 1,413 person-linked events.
- Other declared interests: 102 person-linked events.

AEC date QA now prevents source typos from becoming misleading timeline
signals. In the current local reload, 165 money-flow rows have a source date
outside the row's declared financial year; their raw dates remain in metadata
with `date_validation.status = outside_financial_year`, while their served
`event_date` is left empty.

The first direct AEC representative-money bridge is active. It considers only
direct representative return rows and links only unique exact cleaned-name
matches. In the current local data this links 50 of 57 `Member of HOR Return`
rows, totaling AUD 1,383,511, to MP profiles. Seven rows remain unmatched and
must not be guessed.

## Main Gaps

### 1. Party and entity money is much larger than person-linked money

Most AEC financial-disclosure rows are party, associated-entity, significant
third-party, donor, or campaigner returns. They are source-backed and important,
but many cannot honestly be assigned to one MP or Senator without extra evidence
about campaign committees, office-holder links, or explicit recipient fields.

Immediate implication for the web app: profiles should show direct person-linked
money, but the map should also expose party/entity flows and explain why many
large records are party-level rather than representative-level.

### 2. Benefits are person-linked but still incomplete analytically

Gift, travel, hospitality, flight, ticket, meal, lounge, and service records are
loaded from public interests registers. The extractor now captures explicit
provider phrases, reported values, event dates, and Senate reported dates where
the source text supports it. Many records still lack structured provider,
amount, and event date because the register does not disclose those details or
because the wording needs manual review.

Immediate implication: the UI should surface these records as disclosed benefits
with missing-data labels, and the review queue should prioritize provider/date
extraction where the text supports it.

### 3. Lobbying is registry context, not meeting/access evidence

The official lobbyist register tells us which third-party lobbyists and clients
are registered. It does not prove that a specific meeting occurred with a
specific MP/Senator. Meeting diaries, ministerial diaries, FOI releases, and
published calendars need separate source adapters and separate evidence labels.

Immediate implication: use lobbyist/client status as entity context and network
context, not as a claim of direct access.

### 4. Source-to-effect context is intentionally conservative

The project has vote/policy context scaffolding, but public context rows appear
only after reviewed sector-policy links exist. This prevents causal overreach.
The current database has no reviewed sector-policy links, so the source-to-effect
panel will stay sparse until review decisions are imported.

Immediate implication: prioritize review/import of sector-policy suggestions,
with independent evidence for both the policy topic and the material-interest
link.

### 5. Historical roster coverage is needed for older or changed office holders

Official House and Senate division/person-vote parsing is active for the
current APH decision-record corpus. It uses the current APH roster for person
matching, so official vote names that are no longer present in that current
roster remain explicit unmatched roster names in the artifact.

Immediate implication: add historical roster snapshots or APH member-history
adapters before claiming complete person matching across old parliaments or
changed memberships.

### 6. Entity resolution is the main quality multiplier

Sector labels are currently dominated by transparent rule-based classifications.
Official identifiers and manual review are the path to higher-confidence donor,
company, charity, union, lobbyist-client, fossil-fuel, mining, tech, finance,
property, healthcare, gambling, tobacco, and other sector labels.

Immediate implication: review exact-name official-match candidates, then expand
ABN/ASIC/ACNC enrichment once source access is stable.

## Current Caveats

- AEC annual returns are thresholded, lagged, and can include receipts that are
  not donations. The AEC published that the 2024-25 disclosure threshold was
  AUD 16,900. Current obligations apply to the 2025-26 financial year; the AEC
  has also announced reform timing changes for the newer regime.
- Public interests registers can include spouse/partner/dependent interests,
  and not every declared interest is a received benefit.
- House and Senate register rules differ. House explanatory material includes
  thresholds for gifts and sponsored travel/hospitality; Senate explanatory
  notes state that actual value or number of some assets/gifts/travel/hospitality
  need not be declared.
- Lobbyist registration is evidence of registration and client relationships,
  not evidence of a meeting or successful influence.
- Vote-money/gift relationships are empirical context, not causation, corrupt
  conduct, quid pro quo, or legal wrongdoing without independent findings.

## High-Leverage Next Steps

1. Review and import party/entity links so the party profile API can move
   transparent name-family candidates into evidence-backed reviewed links.
2. Add a review queue for unmatched/ambiguous direct representative AEC return
   rows and for donor-to-person campaign-committee name patterns.
3. Add historical roster snapshots or member-history ingestion for official
   votes whose raw APH names are absent from the current roster.
4. Import reviewed sector-policy link decisions to activate the conservative
   source-to-policy context panels.
5. Improve benefit provider/date/value extraction and review UI for the 1,390
   current benefit rows.
6. Expand official identifier enrichment beyond the current lobbyist snapshot
   and targeted ABN lookups.
7. Add data-quality alerts for implausible AEC dates, large count shifts,
   parser failure rates, and newly unmatched current representatives.
