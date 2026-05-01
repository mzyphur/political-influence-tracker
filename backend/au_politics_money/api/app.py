from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from au_politics_money import __version__
from au_politics_money.api import queries
from au_politics_money.config import API_CORS_ALLOW_ORIGINS, API_RATE_LIMIT_PER_MINUTE


app = FastAPI(
    title="Australian Political Influence Transparency API",
    version=__version__,
    description=(
        "Search and context API for source-backed Australian political "
        "money, gifts, interests, lobbying, and voting records.\n\n"
        "**Claim discipline.** Every record returned by this API "
        "carries an evidence tier (`direct`, `campaign_support`, "
        "`party_mediated`, or `modelled`) and an attribution caveat. "
        "Direct disclosed person-level records, source-backed "
        "campaign-support records, party/entity-mediated context, "
        "and modelled allocations are kept as separate evidence "
        "families and are NEVER summed into a single \"money "
        "received\" headline by the project's own surfaces. "
        "Consumers of this API are expected to preserve the same "
        "separation.\n\n"
        "**Source documents.** Every record is reproducible from "
        "public AEC, APH, AIMS, ABS, and (optional) civic sources. "
        "The reproducibility chain is documented at "
        "[`docs/reproducibility.md`](https://github.com/mzyphur/political-influence-tracker/blob/main/docs/reproducibility.md). "
        "The per-source licence audit is at "
        "[`docs/source_licences.md`](https://github.com/mzyphur/political-influence-tracker/blob/main/docs/source_licences.md).\n\n"
        "**Rate limits.** This API enforces a per-IP, per-minute "
        "rate limit (configurable; defaults to 60/min). Responses "
        "that exceed the limit return 429 with `Retry-After`. The "
        "API is read-only — only `GET` is permitted.\n\n"
        "**License.** The project's source code is licensed under "
        "AGPL-3.0. Source data carries the upstream publishers' "
        "separate licences as documented in `docs/source_licences.md`."
    ),
    contact={
        "name": "Project lead",
        "email": "mzyphur@instats.org",
        "url": "https://github.com/mzyphur/political-influence-tracker",
    },
    license_info={
        "name": "AGPL-3.0",
        "url": "https://www.gnu.org/licenses/agpl-3.0.txt",
    },
    openapi_tags=[
        {
            "name": "Health",
            "description": "Liveness + database-readiness probes.",
        },
        {
            "name": "Search",
            "description": (
                "Free-text search across representatives, electorates, "
                "parties, entities, public-policy sectors, public-policy "
                "topics, and postcodes."
            ),
        },
        {
            "name": "Map",
            "description": "Geographic data for the federal House map.",
        },
        {
            "name": "Coverage",
            "description": (
                "Project-wide data coverage statistics: row counts, "
                "evidence-tier breakdowns, source-document counts, and "
                "postcode-crosswalk completeness."
            ),
        },
        {
            "name": "State / Local",
            "description": (
                "State-level and council-level disclosure summaries "
                "and records. Federal scope is the project's primary "
                "focus through May 2026; state/local coverage expands "
                "after the federal launch."
            ),
        },
        {
            "name": "Representatives",
            "description": (
                "Per-MP / per-Senator profile and evidence-event "
                "endpoints."
            ),
        },
        {
            "name": "Entities",
            "description": (
                "Per-entity (donor, lobbyist client, associated "
                "entity, or third-party campaigner) profile."
            ),
        },
        {
            "name": "Parties",
            "description": "Per-party profile.",
        },
        {
            "name": "Electorates",
            "description": "Per-electorate profile (federal House).",
        },
        {
            "name": "Influence",
            "description": (
                "Cross-cutting influence-context and graph endpoints. "
                "These return labelled connections between "
                "representatives, parties, entities, sectors, and "
                "topics — they do NOT assert wrongdoing or causation."
            ),
        },
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(API_CORS_ALLOW_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)

_RATE_WINDOW_SECONDS = 60.0
_rate_limit_hits: defaultdict[str, deque[float]] = defaultdict(deque)


# Per-path cache hints (max-age in seconds) for the read-heavy
# coverage / stats endpoints. The values change infrequently (loaders
# refresh on the hour-or-less cadence) so a short public cache is
# correct and reduces load. Path matching is exact or via the leading-
# segment match below.
_CACHE_MAX_AGE_BY_PATH: dict[str, int] = {
    "/api/stats": 60,
    "/api/coverage": 60,
}


@app.middleware("http")
async def rate_limit_api_requests(request: Request, call_next):
    if API_RATE_LIMIT_PER_MINUTE > 0 and request.url.path.startswith("/api/"):
        client_host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = _rate_limit_hits[client_host]
        while hits and now - hits[0] > _RATE_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= API_RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(int(_RATE_WINDOW_SECONDS))},
            )
        hits.append(now)
    response = await call_next(request)
    cache_max_age = _CACHE_MAX_AGE_BY_PATH.get(request.url.path)
    if cache_max_age is not None and 200 <= response.status_code < 300:
        # The reader-facing snapshot endpoints can safely live behind a
        # short public cache. The value is 60s because loader refreshes
        # are no more frequent than that; longer would risk serving
        # noticeably stale numbers.
        response.headers["Cache-Control"] = (
            f"public, max-age={cache_max_age}, "
            f"stale-while-revalidate={cache_max_age * 5}"
        )
    return response


@app.get(
    "/health",
    tags=["Health"],
    summary="Process liveness probe",
    description="Returns 200 with the package version. Does not check the database.",
)
def root_health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get(
    "/api/health",
    tags=["Health"],
    summary="Database-backed health check",
    description=(
        "Returns 200 with a database-readiness summary plus the package "
        "version. Returns 503 if the database is unavailable or not "
        "migrated."
    ),
    responses={
        200: {"description": "Service healthy"},
        503: {"description": "Database unavailable or not migrated"},
    },
)
def api_health() -> dict:
    try:
        return {**queries.healthcheck(), "version": __version__}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/api/search",
    tags=["Search"],
    summary="Search across the project's records",
    description=(
        "Free-text search across representatives, electorates, parties, "
        "entities, public-policy sectors, public-policy topics, and "
        "postcodes. The search index is deterministic — no fuzzy "
        "matching is applied across the seven result types. Pass `types` "
        "one or more times to restrict the result set."
    ),
)
def search(
    q: Annotated[str, Query(min_length=1, description="Search text, name, party, sector, or postcode.")],
    types: Annotated[
        list[str] | None,
        Query(description="Optional repeated filter: representative, electorate, party, entity, sector, policy_topic, postcode."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    return queries.search_database(q, result_types=set(types) if types else None, limit=limit)


@app.get(
    "/api/map/electorates",
    tags=["Map"],
    summary="GeoJSON-style features for the federal map",
    description=(
        "Returns the federal House (or, optionally, Senate / state / "
        "council) electorate features used by the public app's map. "
        "Geometry is re-projected to EPSG:4326 and (optionally) "
        "simplified for interactive responsiveness; the AEC's official "
        "boundary geometry is unchanged in storage. Use "
        "`include_geometry=false` to skip the polygons (lighter "
        "payload for tabular consumers)."
    ),
    responses={
        200: {"description": "Electorate features"},
        400: {"description": "Invalid query parameter"},
    },
)
def electorate_map(
    chamber: Annotated[str, Query(pattern="^(house|senate|state|council)$")] = "house",
    state: Annotated[str | None, Query(min_length=2, max_length=3)] = None,
    boundary_set: Annotated[
        str | None,
        Query(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$"),
    ] = None,
    include_geometry: bool = True,
    simplify_tolerance: Annotated[float, Query(ge=0.0, le=0.25)] = 0.0005,
    geometry_role: Annotated[str, Query(pattern="^(display|source)$")] = "display",
) -> dict:
    try:
        return queries.get_electorate_map(
            chamber=chamber,
            state=state,
            boundary_set=boundary_set,
            include_geometry=include_geometry,
            simplify_tolerance=simplify_tolerance,
            geometry_role=geometry_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/coverage",
    tags=["Coverage"],
    summary="Project data-coverage summary",
    description=(
        "Returns row counts, evidence-tier breakdowns, source-document "
        "counts, and postcode-crosswalk completeness as of the "
        "currently-loaded database state. Use this endpoint to gauge "
        "what fraction of the federal-launch surface is covered. "
        "This is the engineering / audit view; for a smaller, "
        "reader-facing summary suitable for embedding in dashboards "
        "and public pages, use `/api/stats` instead."
    ),
)
def coverage() -> dict:
    return queries.get_data_coverage()


@app.get(
    "/api/stats",
    tags=["Coverage"],
    summary="Reader-facing project stats snapshot",
    description=(
        "Returns a small, stable-shape JSON snapshot of the project's "
        "headline numbers — total non-rejected `influence_event` rows, "
        "reported-value sum, person count, federal-House electorate "
        "count, reviewed `party_entity_link` count, postcode-crosswalk "
        "size, federal-House-seat coverage percent, source-document "
        "count, and the most-recent fetch timestamp. The payload "
        "includes a `caveat` string reminding consumers that the four "
        "evidence families are NEVER summed across families on any "
        "user-facing surface — the single influence_event row count is "
        "a loaded-row metric for transparency, not a 'money received' "
        "headline.\n\n"
        "Designed to be embedded directly in HTML / JSON dashboards / "
        "RSS / static-site generators that want a stable schema and a "
        "small payload."
    ),
)
def project_stats() -> dict:
    return queries.get_project_stats()


@app.get(
    "/api/state-local/summary",
    tags=["State / Local"],
    summary="State / council disclosure summary",
    description=(
        "Returns top-N state-level or council-level disclosure summaries "
        "ordered by value. State / local coverage expands after the "
        "May 2026 federal launch."
    ),
    responses={
        200: {"description": "Summary"},
        400: {"description": "Invalid query parameter"},
    },
)
def state_local_summary(
    level: Annotated[str | None, Query(pattern="^(state|council|local)$")] = None,
    jurisdiction_code: Annotated[
        str | None,
        Query(pattern="^(ACT|NSW|NT|QLD|SA|TAS|VIC|WA|act|nsw|nt|qld|sa|tas|vic|wa)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 8,
) -> dict:
    try:
        return queries.get_state_local_summary(
            level=level,
            jurisdiction_code=jurisdiction_code,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/state-local/records",
    tags=["State / Local"],
    summary="State / council disclosure records",
    description=(
        "Returns paginated state-level or council-level disclosure "
        "records. Each record carries its own attribution caveat. Use "
        "`flow_kind` to filter to a specific record family (e.g. "
        "`qld_gift`, `vic_public_funding_payment`, `nt_annual_gift`)."
    ),
    responses={
        200: {"description": "Records page"},
        400: {"description": "Invalid query parameter"},
    },
)
def state_local_records(
    level: Annotated[str | None, Query(pattern="^(state|council|local)$")] = None,
    jurisdiction_code: Annotated[
        str | None,
        Query(pattern="^(ACT|NSW|NT|QLD|SA|TAS|VIC|WA|act|nsw|nt|qld|sa|tas|vic|wa)$"),
    ] = None,
    flow_kind: Annotated[
        str | None,
        Query(
            pattern=(
                "^(act_annual_free_facilities_use|act_annual_gift_in_kind|"
                "act_annual_gift_of_money|act_annual_receipt|act_gift_in_kind|"
                "act_gift_of_money|nt_annual_debt|nt_annual_gift|"
                "nt_annual_receipt|nt_donor_return_donation|qld_gift|"
                "qld_electoral_expenditure|vic_administrative_funding_entitlement|"
                "vic_policy_development_funding_payment|vic_public_funding_payment|"
                "sa_annual_political_expenditure_return_summary|"
                "sa_associated_entity_return_summary|"
                "sa_candidate_campaign_donations_return_summary|"
                "sa_capped_expenditure_return_summary|sa_donor_return_summary|"
                "sa_political_party_return_summary|"
                "sa_prescribed_expenditure_return_summary|"
                "sa_special_large_gift_return_summary|"
                "sa_third_party_capped_expenditure_return_summary|"
                "sa_third_party_return_summary|tas_reportable_donation|"
                "tas_reportable_loan|wa_political_contribution)$"
            )
        ),
    ] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=600)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    try:
        return queries.get_state_local_records(
            level=level,
            jurisdiction_code=jurisdiction_code,
            flow_kind=flow_kind,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/representatives/{person_id}",
    tags=["Representatives"],
    summary="Per-MP / per-Senator profile",
    description=(
        "Returns a representative's office terms, party affiliation, "
        "evidence-tier exposure summary (direct, campaign-support, "
        "party-mediated, modelled), recent disclosed records, and "
        "linked sectors / topics. The exposure summary is asymmetric "
        "with respect to the equal-share denominator — see the "
        "methodology page's #equal-share section for details."
    ),
    responses={
        200: {"description": "Representative profile"},
        404: {"description": "Representative not found"},
    },
)
def representative_profile(person_id: int) -> dict:
    profile = queries.get_representative_profile(person_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Representative not found")
    return profile


@app.get(
    "/api/representatives/{person_id}/evidence",
    tags=["Representatives"],
    summary="Paginated evidence events for a representative",
    description=(
        "Returns paginated evidence events for a representative, scoped "
        "to one of two evidence groups: `direct` (disclosed person-level "
        "records) or `campaign_support` (source-backed campaign-support "
        "records). The two groups are NEVER summed at any project surface. "
        "Cursor-based pagination."
    ),
    responses={
        200: {"description": "Evidence events page"},
        400: {"description": "Invalid query parameter"},
        404: {"description": "Representative not found"},
    },
)
def representative_evidence(
    person_id: int,
    group: Annotated[str, Query(pattern="^(direct|campaign_support)$")] = "direct",
    event_family: Annotated[
        str | None,
        Query(min_length=1, max_length=80, pattern=r"^[a-z0-9_:-]+$"),
    ] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=600)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    try:
        page = queries.get_representative_evidence_events(
            person_id,
            group=group,
            event_family=event_family,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not page:
        raise HTTPException(status_code=404, detail="Representative not found")
    return page


@app.get(
    "/api/entities/{entity_id}",
    tags=["Entities"],
    summary="Per-entity profile (donor / lobbyist client / associated entity / third-party campaigner)",
    description=(
        "Returns an entity's profile, including its public-policy "
        "sectors, AEC Register pathway (if any), and the records linking "
        "it to representatives. The entity's records are presented with "
        "explicit evidence-tier labels."
    ),
    responses={
        200: {"description": "Entity profile"},
        404: {"description": "Entity not found"},
    },
)
def entity_profile(entity_id: int) -> dict:
    profile = queries.get_entity_profile(entity_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Entity not found")
    return profile


@app.get(
    "/api/parties/{party_id}",
    tags=["Parties"],
    summary="Per-party profile",
    description=(
        "Returns a party's profile including its current MPs, "
        "associated entities, public-policy sectors, and disclosed "
        "campaign-support exposure. Federal short-form party rows "
        "(ALP, IND, AG, NATS, LP, LNP, ON, KAP) were consolidated with "
        "their long-form pairs in migration 034; state-jurisdiction "
        "rows are intentionally untouched."
    ),
    responses={
        200: {"description": "Party profile"},
        404: {"description": "Party not found"},
    },
)
def party_profile(party_id: int) -> dict:
    profile = queries.get_party_profile(party_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Party not found")
    return profile


@app.get(
    "/api/electorates/{electorate_id}",
    tags=["Electorates"],
    summary="Per-electorate profile (federal House)",
    description=(
        "Returns an electorate's profile including its current "
        "representative, party-mediated exposure summary, and a list "
        "of postcodes mapped to the electorate (via the AEC's "
        "Electorate Finder)."
    ),
    responses={
        200: {"description": "Electorate profile"},
        404: {"description": "Electorate not found"},
    },
)
def electorate_profile(electorate_id: int) -> dict:
    profile = queries.get_electorate_profile(electorate_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Electorate not found")
    return profile


@app.get(
    "/api/influence-context",
    tags=["Influence"],
    summary="Cross-cutting influence-context lookup",
    description=(
        "Returns labelled connections relevant to a representative, a "
        "policy topic, or a public-policy sector. The connections are "
        "described as recorded patterns; this endpoint does NOT assert "
        "wrongdoing or causation."
    ),
)
def influence_context(
    person_id: int | None = None,
    topic_id: int | None = None,
    public_sector: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    return queries.get_influence_context(
        person_id=person_id,
        topic_id=topic_id,
        public_sector=public_sector,
        limit=limit,
    )


@app.get(
    "/api/graph/influence",
    tags=["Influence"],
    summary="Influence-graph nodes and edges",
    description=(
        "Returns a small, focused graph of nodes (representatives, "
        "parties, entities) and edges (disclosed records, party links, "
        "AEC Register pathways) anchored at the requested seed. Each "
        "edge carries its evidence tier so a graph consumer can render "
        "direct vs party-mediated vs modelled connections "
        "differently. Returns 404 if the seed entity / party / "
        "representative does not exist."
    ),
    responses={
        200: {"description": "Graph"},
        400: {"description": "Invalid query parameter"},
        404: {"description": "Graph root not found"},
    },
)
def influence_graph(
    person_id: int | None = None,
    party_id: int | None = None,
    entity_id: int | None = None,
    include_candidates: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    try:
        graph = queries.get_influence_graph(
            person_id=person_id,
            party_id=party_id,
            entity_id=entity_id,
            include_candidates=include_candidates,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not graph:
        raise HTTPException(status_code=404, detail="Graph root not found")
    return graph


@app.get(
    "/api/industry-aggregate",
    tags=["Influence"],
    summary="Per-sector industry-level influence aggregate",
    description=(
        "Returns rows from `v_industry_influence_aggregate`: one "
        "row per sector with side-by-side donor-side aggregates "
        "(money / campaign-support / private-interest / benefit / "
        "access / organisational-role event counts and totals — "
        "deterministic tier 1) and contract-side aggregates "
        "(LLM-tagged AusTender contract count + total value — "
        "tier 2). NEVER sums across tier boundaries. Powers "
        "questions like 'how much did the gas industry donate AND "
        "how much did it receive in contracts'."
    ),
    responses={200: {"description": "Sector-by-sector aggregate"}},
)
def industry_aggregate(
    min_donor_money_aud: Annotated[float, Query(ge=0)] = 0,
    min_contract_value_aud: Annotated[float, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    return queries.get_industry_aggregate(
        min_donor_money_aud=min_donor_money_aud,
        min_contract_value_aud=min_contract_value_aud,
        limit=limit,
    )


@app.get(
    "/api/industry-anatomy",
    tags=["Influence"],
    summary="THE influence-anatomy view: all evidence streams per sector",
    description=(
        "Returns rows from `v_industry_anatomy`: per-sector "
        "side-by-side aggregation of donations, gifts, sponsored "
        "travel, memberships, investments, AND contracts. Every "
        "evidence stream the project has on a sector lives in its "
        "own column with explicit tier label. NEVER sums across "
        "tiers. Powers the public app's 'Industry Detail' page "
        "surface — the load-bearing pro-democracy transparency "
        "page."
    ),
    responses={200: {"description": "Per-sector anatomy rows"}},
)
def industry_anatomy(
    sector: str | None = None,
    min_money_aud: Annotated[float, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> dict:
    return queries.get_industry_anatomy(
        sector=sector,
        min_money_aud=min_money_aud,
        limit=limit,
    )


@app.get(
    "/api/roi-items",
    tags=["Influence"],
    summary="LLM-extracted disclosure items from House Register",
    description=(
        "Returns rows from `llm_register_of_interests_observation` "
        "(Stage 2 LLM extraction; ~3,547 items in DB at end of "
        "Stage 2 full corpus). Each row is one MP-disclosed item: "
        "gift, sponsored travel, membership, directorship, "
        "investment, liability, etc. Filters: item_type, "
        "counterparty_name (LIKE-match), member_name (LIKE-match), "
        "min_value_aud. Powers per-MP ROI drill-downs and per-"
        "counterparty 'who got gifts from Qantas' queries."
    ),
    responses={200: {"description": "Per-item ROI rows"}},
)
def roi_items(
    item_type: str | None = None,
    counterparty_name_query: str | None = None,
    member_name_query: str | None = None,
    min_value_aud: Annotated[float, Query(ge=0)] | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    return queries.get_roi_items(
        item_type=item_type,
        counterparty_name_query=counterparty_name_query,
        member_name_query=member_name_query,
        min_value_aud=min_value_aud,
        limit=limit,
    )


@app.get(
    "/api/roi-providers",
    tags=["Influence"],
    summary="Top counterparties (gift-givers / travel-sponsors / etc.)",
    description=(
        "Returns per-counterparty aggregate of MP ROI items: who "
        "gave the most gifts / sponsored the most travel / hosted "
        "the most MPs at events. Powers the 'top gift providers' "
        "surface (Qantas Chairman's Lounge pattern)."
    ),
    responses={200: {"description": "Per-counterparty aggregates"}},
)
def roi_providers(
    item_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    return queries.get_roi_providers(item_type=item_type, limit=limit)


@app.get(
    "/api/donor-recipient-voting-alignment",
    tags=["Influence"],
    summary="Per (donor → recipient MP → policy topic) voting record",
    description=(
        "Returns rows from `v_donor_recipient_voting_alignment`: "
        "for every donor → MP pair where both sides carry "
        "evidence (donor donations + MP votes on tagged "
        "divisions), surfaces the MP's voting pattern alongside "
        "the donor's industry classification + total "
        "contributions. RAW COUNTS ONLY — does NOT auto-label "
        "any vote as 'aligned' or 'opposed' to the donor's "
        "industry. That would be a causation claim the project "
        "does not make. Consumers (researchers, journalists, "
        "the public) interpret. Joins three evidence streams: "
        "donor donations (tier 1), entity industry classification "
        "(LLM tier 2), MP voting record (tier 1 + They Vote For "
        "You topic linkage CC-BY)."
    ),
    responses={200: {"description": "Per donor-recipient-topic rows"}},
)
def donor_recipient_voting_alignment(
    donor_entity_id: int | None = None,
    recipient_person_id: int | None = None,
    donor_sector: str | None = None,
    topic_slug: str | None = None,
    min_donor_money_aud: Annotated[float, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    return queries.get_donor_recipient_voting_alignment(
        donor_entity_id=donor_entity_id,
        recipient_person_id=recipient_person_id,
        donor_sector=donor_sector,
        topic_slug=topic_slug,
        min_donor_money_aud=min_donor_money_aud,
        limit=limit,
    )


@app.get(
    "/api/minister-voting-pattern",
    tags=["Influence"],
    summary="Per-minister voting record summarised by policy topic",
    description=(
        "Returns rows from `v_minister_voting_pattern`: each row "
        "is a (minister, policy_topic) summary with division_count, "
        "aye_count, no_count, rebellion_count. Powers questions like "
        "'how did Mark Dreyfus vote on unconventional gas mining "
        "divisions?' or 'which ministers rebelled most on climate "
        "policy?'. Topics are imported from They Vote For You "
        "(CC-BY) — `division_topic.method='third_party_civic'`. "
        "Voting + portfolio data are both tier-1 (deterministic, "
        "source-attributed). The view does NOT pre-judge alignment "
        "— consumers interpret the raw votes."
    ),
    responses={200: {"description": "Per-minister voting summaries"}},
)
def minister_voting_pattern(
    minister_name: str | None = None,
    portfolio: str | None = None,
    topic_slug: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    return queries.get_minister_voting_pattern(
        minister_name=minister_name,
        portfolio=portfolio,
        topic_slug=topic_slug,
        limit=limit,
    )


@app.get(
    "/api/contract-minister-responsibility",
    tags=["Influence"],
    summary="Contracts joined to the responsible minister via portfolio mapping",
    description=(
        "Returns rows from `v_contract_minister_responsibility`: "
        "every LLM-tagged AusTender contract joined to the minister "
        "+ portfolio that oversees the awarding agency, via the "
        "deterministic `portfolio_agency` + `minister_role` "
        "tables (Stage 4a, schema 044/045). Closes the structural "
        "influence-narrative loop: a query that combines this with "
        "`/api/contract-donor-overlap` surfaces 'supplier-X donated "
        "to MP-Z whose portfolio oversees the agency that paid X'. "
        "The contract → minister join uses lower-cased exact match "
        "on `agency_canonical_name` OR any of the per-agency "
        "`agency_aliases`. Coverage on the BB pilot data: ~98% of "
        "tagged contracts joined to a minister + portfolio."
    ),
    responses={200: {"description": "Per-contract minister responsibility"}},
)
def contract_minister_responsibility(
    agency: str | None = None,
    minister_name: str | None = None,
    portfolio: str | None = None,
    sector: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    return queries.get_contract_minister_responsibility(
        agency=agency,
        minister_name=minister_name,
        portfolio=portfolio,
        sector=sector,
        limit=limit,
    )


@app.get(
    "/api/contract-donor-overlap",
    tags=["Influence"],
    summary="Contract suppliers that ALSO appear as donors",
    description=(
        "Returns rows from `v_contract_donor_overlap`: entities "
        "that received Australian Government contracts (LLM-tagged) "
        "AND appear as donors / gift-givers / hosts in "
        "`influence_event` (deterministic). Tier-1 donor amounts "
        "and tier-2 contract amounts are surfaced as separate "
        "columns; the API does NOT sum them. Powers the public "
        "app's headline 'supplier-X-got-$N-contracts-AND-donated-"
        "$M-to-MP-Y' surface."
    ),
    responses={200: {"description": "Per-supplier overlap rows"}},
)
def contract_donor_overlap(
    min_contract_value_aud: Annotated[float, Query(ge=0)] = 0,
    min_donor_money_aud: Annotated[float, Query(ge=0)] = 0,
    sector: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    return queries.get_contract_donor_overlap(
        min_contract_value_aud=min_contract_value_aud,
        min_donor_money_aud=min_donor_money_aud,
        sector=sector,
        limit=limit,
    )


def main() -> None:
    import uvicorn

    uvicorn.run("au_politics_money.api.app:app", host="127.0.0.1", port=8008, reload=True)
