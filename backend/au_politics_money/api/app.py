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
        "Search and context API for source-backed Australian political money, "
        "gifts, interests, lobbying, and voting records."
    ),
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
    return await call_next(request)


@app.get("/health")
def root_health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/health")
def api_health() -> dict:
    try:
        return {**queries.healthcheck(), "version": __version__}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/search")
def search(
    q: Annotated[str, Query(min_length=1, description="Search text, name, party, sector, or postcode.")],
    types: Annotated[
        list[str] | None,
        Query(description="Optional repeated filter: representative, electorate, party, entity, sector, policy_topic, postcode."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    return queries.search_database(q, result_types=set(types) if types else None, limit=limit)


@app.get("/api/map/electorates")
def electorate_map(
    chamber: Annotated[str, Query(pattern="^(house|senate|state)$")] = "house",
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


@app.get("/api/coverage")
def coverage() -> dict:
    return queries.get_data_coverage()


@app.get("/api/state-local/summary")
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


@app.get("/api/state-local/records")
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


@app.get("/api/representatives/{person_id}")
def representative_profile(person_id: int) -> dict:
    profile = queries.get_representative_profile(person_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Representative not found")
    return profile


@app.get("/api/representatives/{person_id}/evidence")
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


@app.get("/api/entities/{entity_id}")
def entity_profile(entity_id: int) -> dict:
    profile = queries.get_entity_profile(entity_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Entity not found")
    return profile


@app.get("/api/parties/{party_id}")
def party_profile(party_id: int) -> dict:
    profile = queries.get_party_profile(party_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Party not found")
    return profile


@app.get("/api/electorates/{electorate_id}")
def electorate_profile(electorate_id: int) -> dict:
    profile = queries.get_electorate_profile(electorate_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Electorate not found")
    return profile


@app.get("/api/influence-context")
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


@app.get("/api/graph/influence")
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


def main() -> None:
    import uvicorn

    uvicorn.run("au_politics_money.api.app:app", host="127.0.0.1", port=8008, reload=True)
