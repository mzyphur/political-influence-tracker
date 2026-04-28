from __future__ import annotations

from au_politics_money.db.sector_policy_suggestions import suggest_links_for_topic


def test_suggest_links_for_fossil_fuel_policy_topic() -> None:
    topic = {
        "id": 1,
        "slug": "they_vote_for_you_policy_250",
        "label": "ending government investment in fossil fuels",
        "description": "the federal government should stop all investment in fossil fuels",
        "metadata": {
            "source": "they_vote_for_you",
            "source_evidence_class": "third_party_civic",
            "they_vote_for_you_policy_id": 250,
        },
    }

    suggestions = suggest_links_for_topic(topic)

    fossil = [item for item in suggestions if item["public_sector"] == "fossil_fuels"]
    assert fossil
    assert fossil[0]["subject_external_key"] == (
        "sector_policy_topic_link:fossil_fuels:"
        "they_vote_for_you_policy_250:direct_material_interest:model_assisted"
    )
    assert fossil[0]["topic_url"] == "https://theyvoteforyou.org.au/policies/250"
    assert fossil[0]["draft_review_decision"]["decision"] == "needs_more_evidence"
    assert fossil[0]["draft_review_decision"]["supporting_sources"][1]["url"] == ""


def test_suggest_links_returns_empty_for_unmatched_topic() -> None:
    topic = {
        "id": 2,
        "slug": "they_vote_for_you_policy_112",
        "label": "speeding things along in Parliament",
        "description": "procedural motion to put the question",
        "metadata": {"source": "they_vote_for_you"},
    }

    assert suggest_links_for_topic(topic) == []


def test_suggest_links_does_not_match_gas_inside_unrelated_words() -> None:
    topic = {
        "id": 3,
        "slug": "they_vote_for_you_policy_113",
        "label": "gastric health services",
        "description": "procedures for hospital services and clinical care",
        "metadata": {"source": "they_vote_for_you"},
    }

    assert suggest_links_for_topic(topic) == []
