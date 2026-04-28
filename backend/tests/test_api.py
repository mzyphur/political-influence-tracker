from __future__ import annotations

from fastapi.testclient import TestClient

from au_politics_money.api import queries
from au_politics_money.api.app import app


def test_root_health_does_not_require_database() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_allows_local_frontend_origin() -> None:
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_search_endpoint_delegates_to_query_layer(monkeypatch) -> None:
    def fake_search_database(query, *, result_types=None, limit=10, database_url=None):
        assert query == "climate"
        assert result_types == {"representative", "policy_topic"}
        assert limit == 7
        assert database_url is None
        return {
            "query": query,
            "normalized_query": query,
            "results": [{"type": "policy_topic", "id": 1, "label": "Climate"}],
            "result_count": 1,
            "limitations": [],
            "caveat": queries.SEARCH_CAVEAT,
        }

    monkeypatch.setattr(queries, "search_database", fake_search_database)
    client = TestClient(app)

    response = client.get(
        "/api/search",
        params=[
            ("q", "climate"),
            ("types", "representative"),
            ("types", "policy_topic"),
            ("limit", "7"),
        ],
    )

    assert response.status_code == 200
    assert response.json()["result_count"] == 1


def test_electorate_map_endpoint_delegates_to_query_layer(monkeypatch) -> None:
    def fake_get_electorate_map(
        *,
        chamber="house",
        state=None,
        boundary_set=None,
        include_geometry=True,
        simplify_tolerance=0.01,
    ):
        assert chamber == "house"
        assert state == "VIC"
        assert boundary_set == "aec_federal_2025_current"
        assert include_geometry is False
        assert simplify_tolerance == 0.05
        return {
            "type": "FeatureCollection",
            "features": [],
            "feature_count": 0,
            "filters": {},
            "caveat": queries.MAP_CAVEAT,
        }

    monkeypatch.setattr(queries, "get_electorate_map", fake_get_electorate_map)
    client = TestClient(app)

    response = client.get(
        "/api/map/electorates",
        params={
            "chamber": "house",
            "state": "VIC",
            "boundary_set": "aec_federal_2025_current",
            "include_geometry": "false",
            "simplify_tolerance": "0.05",
        },
    )

    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"


def test_representative_profile_404(monkeypatch) -> None:
    monkeypatch.setattr(queries, "get_representative_profile", lambda person_id: {})
    client = TestClient(app)

    response = client.get("/api/representatives/999999")

    assert response.status_code == 404


def test_search_database_short_query_returns_caveat_without_db() -> None:
    response = queries.search_database("x")

    assert response["results"] == []
    assert response["caveat"] == queries.SEARCH_CAVEAT
