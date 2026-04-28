# Frontend Product Direction

## First User Experience

The first screen should be the national explorer, not a marketing landing page.

Core layout:

- Australia map with House electorates.
- Global search for representatives, electorates, states/territories, parties,
  source entities, sectors, policy topics, and postcodes once a source-backed
  postcode crosswalk is loaded.
- Senate state/territory selector.
- Filters for party, chamber, state, year, industry, source type, and evidence
  confidence.
- Side panel showing selected electorate, MP, Senator, donor, or industry.
- Timeline below or beside the map for money/gifts/votes.

## User Questions To Answer

- Who has this MP/Senator received money, gifts, travel, or hospitality from?
- Which industries are most visible around this party/electorate/person?
- Which donors fund multiple parties or entities?
- Which entities appear as donors, lobbyist clients, gift-givers, or associated
  entities?
- How does this person's voting record line up with sectors that appear in their
  money/interests record?
- Which disclosed source entities appear before, during, or after a linked vote
  topic, and what evidence supports the sector-topic link?
- What is known, what is inferred, and what cannot be known from public data?

## Visual Standards

- The map is the primary visual anchor.
- Every chart supports drill-down to source records.
- Industry colors should be distinct and accessible.
- Party colors should follow Australian political conventions, with care for
  independents and crossbench.
- Confidence and evidence class should be visible but not visually noisy.
- Avoid sensational labels in the data UI. Let the records carry the force.

## MVP Views

- National map.
- Global search.
- MP/Senator profile.
- Donor/entity profile.
- Party profile.
- Industry explorer.
- Gifts and hospitality explorer.
- Vote-topic explorer.
- Source document viewer.
- Methodology and limitations page.
