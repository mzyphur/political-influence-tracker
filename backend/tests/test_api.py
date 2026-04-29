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
        geometry_role="display",
    ):
        assert chamber == "house"
        assert state == "VIC"
        assert boundary_set == "aec_federal_2025_current"
        assert include_geometry is False
        assert simplify_tolerance == 0.05
        assert geometry_role == "display"
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


def test_coverage_endpoint_delegates_to_query_layer(monkeypatch) -> None:
    monkeypatch.setattr(
        queries,
        "get_data_coverage",
        lambda: {
            "status": "ok",
            "active_country": "AU",
            "active_levels": ["federal"],
            "planned_levels": ["state", "council"],
            "coverage_layers": [],
            "influence_events_by_family": [],
            "influence_event_totals": {"event_count": 0},
            "caveat": "fixture",
        },
    )
    client = TestClient(app)

    response = client.get("/api/coverage")

    assert response.status_code == 200
    assert response.json()["active_country"] == "AU"


def test_state_local_summary_endpoint_delegates_to_query_layer(monkeypatch) -> None:
    captured = {}

    def fake_summary(level=None, limit=8):
        captured["level"] = level
        captured["limit"] = limit
        return {
            "status": "ok",
            "source_family": "qld_ecq_eds",
            "requested_level": level,
            "db_level": "local",
            "totals_by_level": [],
            "top_gift_donors": [],
            "top_gift_recipients": [],
            "top_expenditure_actors": [],
            "top_events": [],
            "top_local_electorates": [],
            "caveat": "fixture",
        }

    monkeypatch.setattr(queries, "get_state_local_summary", fake_summary)
    client = TestClient(app)

    response = client.get("/api/state-local/summary", params={"level": "council", "limit": 5})

    assert response.status_code == 200
    assert response.json()["source_family"] == "qld_ecq_eds"
    assert captured == {"level": "council", "limit": 5}


def test_influence_graph_endpoint_delegates_to_query_layer(monkeypatch) -> None:
    def fake_get_influence_graph(
        *,
        person_id=None,
        party_id=None,
        entity_id=None,
        include_candidates=False,
        limit=100,
    ):
        assert person_id == 123
        assert party_id is None
        assert entity_id is None
        assert include_candidates is True
        assert limit == 25
        return {
            "root_id": "person:123",
            "nodes": [{"id": "person:123", "type": "person", "label": "Jane Citizen"}],
            "edges": [],
            "node_count": 1,
            "edge_count": 0,
            "filters": {},
            "caveat": queries.GRAPH_CAVEAT,
        }

    monkeypatch.setattr(queries, "get_influence_graph", fake_get_influence_graph)
    client = TestClient(app)

    response = client.get(
        "/api/graph/influence",
        params={"person_id": "123", "include_candidates": "true", "limit": "25"},
    )

    assert response.status_code == 200
    assert response.json()["root_id"] == "person:123"


def test_influence_graph_requires_one_root() -> None:
    client = TestClient(app)

    response = client.get("/api/graph/influence")

    assert response.status_code == 400


def test_representative_profile_404(monkeypatch) -> None:
    monkeypatch.setattr(queries, "get_representative_profile", lambda person_id: {})
    client = TestClient(app)

    response = client.get("/api/representatives/999999")

    assert response.status_code == 404


def test_party_profile_404(monkeypatch) -> None:
    monkeypatch.setattr(queries, "get_party_profile", lambda party_id: {})
    client = TestClient(app)

    response = client.get("/api/parties/999999")

    assert response.status_code == 404


def test_representative_contact_payload_does_not_expose_local_source_paths() -> None:
    contact = queries._representative_contact_from_metadata(
        {
            "email": "Example.Member.MP@aph.gov.au",
            "email_source_metadata_path": "/local/raw/contact-list/metadata.json",
            "electorate_phone": "(02) 0000 0000",
            "electorate_office_address": "1 Example Street, Canberra ACT 2600",
        },
        source_url="https://www.aph.gov.au/example.csv",
    )

    assert contact["email"] == "Example.Member.MP@aph.gov.au"
    assert contact["email_source_metadata_path"] is None
    assert contact["source_url"] == "https://www.aph.gov.au/example.csv"


def test_search_database_short_query_returns_caveat_without_db() -> None:
    response = queries.search_database("x")

    assert response["results"] == []
    assert response["caveat"] == queries.SEARCH_CAVEAT


def test_party_search_terms_include_common_public_aliases() -> None:
    _, labor_short_names = queries._party_search_terms("labor")
    _, liberal_short_names = queries._party_search_terms("liberal")
    _, liberal_national_short_names = queries._party_search_terms("liberal national")
    _, greens_short_names = queries._party_search_terms("greens")

    assert "ALP" in labor_short_names
    assert {"LP", "LNP", "CLP"} <= liberal_short_names
    assert "ALP" not in liberal_short_names
    assert liberal_national_short_names == {"LNP"}
    assert "AG" in greens_short_names


def test_search_result_sort_prioritizes_active_party_records() -> None:
    rows = [
        {
            "type": "party",
            "rank": 30,
            "label": "Australian Labor Party",
            "metadata": {"current_representative_count": 0},
        },
        {
            "type": "party",
            "rank": 30,
            "label": "ALP",
            "metadata": {"current_representative_count": 123},
        },
    ]

    sorted_rows = sorted(rows, key=queries._search_result_sort_key)

    assert sorted_rows[0]["label"] == "ALP"


def test_search_result_sort_prioritizes_postcode_coverage() -> None:
    rows = [
        {
            "type": "postcode",
            "rank": 5,
            "label": "2600 -> Bean",
            "metadata": {"confidence": 0.5, "locality_count": 1},
        },
        {
            "type": "postcode",
            "rank": 5,
            "label": "2600 -> Canberra",
            "metadata": {"confidence": 0.5, "locality_count": 4},
        },
    ]

    sorted_rows = sorted(rows, key=queries._search_result_sort_key)

    assert sorted_rows[0]["label"] == "2600 -> Canberra"


def test_party_public_label_expands_roster_abbreviations() -> None:
    assert queries._party_public_label("ALP", "ALP") == "Australian Labor Party (ALP)"
    assert queries._party_public_label("Australian Labor Party", "Australian Labor Party") == (
        "Australian Labor Party"
    )
