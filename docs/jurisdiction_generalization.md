# Jurisdiction Generalization Strategy

This project should not be hard-coded to Australian federal data, even though
the Commonwealth build is the pilot. The durable unit is a jurisdiction adapter:
a reproducible source bundle that maps public records into the same normalized
surfaces with explicit coverage and attribution caveats.

## Portable Model

Every country or level should try to fill the same dimensions where public law
and source availability allow:

- Actors: representatives, candidates, parties, associated entities, donors,
  lobbyists, companies, trusts, unions, industry bodies, and relevant office
  holders.
- Offices: chamber, role, term, party, electorate/district/seat, and government
  level.
- Boundaries: source-backed geometry with valid dates, boundary set, CRS, and
  simplification policy.
- Money flows: donations, receipts, loans, debts, public funding, campaign
  spending, and in-kind support.
- Benefits: gifts, hospitality, travel, accommodation, event access, memberships,
  services, and other disclosed non-cash benefits.
- Interests and roles: assets, liabilities, shares, trusts, directorships,
  employments, memberships, sponsored roles, and conflicts registers.
- Access: lobbying register entries, ministerial diaries, meeting logs, visitor
  logs, procurement contacts, and consultancies where legally available.
- Behaviour: divisions/votes, bill sponsorship, committee membership, questions,
  speeches, motions, amendments, grants, procurement decisions, and policy
  announcements.
- Entity enrichment: official identifiers, aliases, ownership/parent links,
  sanction/PEP flags where relevant, industry classifications, and manual review
  decisions.

## Levels

- National/federal: active Australian pilot.
- State/territory/province/devolved: UI and schema are reserved; source adapters
  should be added one jurisdiction at a time.
- Local/council/municipal: UI and schema are reserved; source adapters will need
  stronger locality/address caveats because public records are less standardized.

## Cross-Country Adapters

The same approach should support New Zealand, the United Kingdom, and the United
States after the Australian pilot stabilizes:

- AU: Commonwealth active; state/territory and council planned.
- NZ: Parliament, Electoral Commission, register of pecuniary interests, local
  authority members/interests, procurement, lobbying/access sources if available.
- UK: Electoral Commission, MPs' register of interests, Lords register, APPGs,
  ministerial meetings/gifts/hospitality/travel, Companies House, Parliament
  divisions, devolved parliaments, and councils.
- US: FEC, state campaign-finance systems, congressional personal financial
  disclosures, lobbying disclosure, travel/gifts where available, House/Senate
  votes, state legislatures, OpenSecrets-style enrichment where licensed.

## Attribution Rule

Never force a record onto a person, party, district, or industry if the source
does not support that attribution. Store the record at the strongest supported
level and let the UI expose the attribution level:

- person-linked
- party-linked
- entity-linked
- electorate/district-linked
- return-level only
- inferred candidate match pending review
- unsupported/unassigned

This prevents the map from implying false precision while still making large
party/entity money flows discoverable.

## Geometry Rule

Canonical boundary tables preserve source precision. Interactive maps may use a
low labelled tolerance for usability; strict QA/publication checks can request
exact source geometry with `simplify_tolerance=0`. Independently simplifying
neighbouring polygons can create visible cracks and overlaps, so future
large-scale deployments should use prebuilt vector tiles or a topology-preserving
boundary service rather than per-request high-tolerance simplification.

## Coverage Rule

Every adapter must report coverage through `/api/coverage`: source families,
record counts, last fetched date, active levels, planned levels, attribution
limits, and caveats. The absence of a source family should be visible to users
and reviewers as a coverage gap, not hidden behind empty map counts.
