# Federal Rollout Checklist

This checklist defines the minimum conditions for treating the Commonwealth
layer as release-ready. It is a product, engineering, and research-validity
gate: the app can be useful before every item is complete, but public launch
should not present the federal layer as settled until these checks pass.

## Data Gates

- Federal House map has 150 current House boundaries for the active AEC
  boundary set.
- Senate map has all eight state/territory Senate regions and current senator
  lists.
- Current office terms are loaded for serving House members and senators, with
  stale fallback rows closed or removed from public surfaces.
- Money-flow rows use current-source semantics. Rows absent from the latest
  source-family artifact remain auditable but do not contribute to public
  non-rejected totals.
- House/Senate interest and benefit rows use current-source semantics and do
  not republish withdrawn or obvious form/OCR artifact rows.
- Official APH vote/division rows are current-only in public summaries and
  linked to current decision-record document snapshots.
- QLD state/local rows may be shown as partial non-federal coverage, but the
  federal launch must label them as summary-only until state/council maps and
  representative joins are ready.

## Evidence And Claim Gates

- Direct person-linked money, gifts, travel, hospitality, memberships, interests,
  and roles are shown separately from campaign-support records.
- Campaign-support, public-funding, advertising, party-channelled, and
  expenditure records are never summed into "money personally received" unless
  the source explicitly supports that narrower claim.
- Party/entity money paths use reviewed `party_entity_link` rows only.
  Generated candidates remain review inputs.
- Sector-policy and source-to-policy overlap uses reviewed
  `sector_policy_topic_link` rows only.
- Modelled exposure edges are labelled as modelled allocation, not disclosed
  receipt, causation, or improper conduct.
- The methodology page and API caveats remain visible enough that journalists
  and public users can distinguish source-backed records, reviewed links,
  modelled paths, missing data, and non-claims.

## Review Gates

- Run `prepare-review-bundle` and archive the manifest for the release commit.
- Review at least the top party/entity link candidates by reported amount and
  event count before enabling party-mediated graph claims beyond beta examples.
- Review sector-policy link suggestions before showing source-policy overlap as
  anything stronger than "pending review".
- Import accepted/revised decisions through `import-review-decisions --apply`;
  do not manually mutate reviewed rows outside the append-only decision trail.
- Re-run `reapply-review-decisions --apply` after a full reload to prove the
  review trail survives regenerated source artifacts.

## Operational Gates

- Weekly runner completes with `--refresh-existing-sources`.
- `qa-serving-database` passes with configured minimum serving-count thresholds.
- Full backend tests pass.
- Real Postgres integration tests pass.
- Frontend production build passes.
- API CORS origins and rate limits match the deployment environment.
- MapTiler browser key is restricted to approved launch origins before public
  deployment.
- Secrets remain gitignored, and public artifacts do not expose `.env`, local
  storage paths, cookies, or provider request tokens.

## UI Gates

- Map selections do not recenter or zoom without explicit user action.
- Selected-region outlines remain readable at national and local zoom levels.
- Panels can collapse on laptop-sized screens so the map remains inspectable.
- Representative detail pages can load more direct and campaign-support records
  without mixing their claim categories.
- State/Council modes clearly say "partial" or "planned" until maps and joins
  are available.
- Source links, missing-value labels, review status, evidence status, and
  extraction method are visible in expanded records.

## Federal To State/Council Transition

The next jurisdiction should be promoted only after it has the same basic
structure as the federal layer:

- official source registry entries;
- reproducible fetch and normalize commands;
- source-current semantics;
- jurisdiction-specific identifier enrichment;
- summary API surface;
- map boundary source and geometry policy;
- claim taxonomy for direct, campaign-support, party/entity, and modelled paths;
- QA thresholds appropriate to that jurisdiction;
- review queues for ambiguous identities and indirect links.
