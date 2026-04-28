from datetime import date, datetime, timezone
from decimal import Decimal

from au_politics_money.db.review import (
    ENTITY_CLASSIFICATIONS_SQL,
    OFFICIAL_MATCH_CANDIDATES_SQL,
    PARTY_ENTITY_LINKS_SQL,
    REVIEW_QUEUES,
    SECTOR_POLICY_LINKS_SQL,
    ReviewImportError,
    decision_key_for,
    decision_from_db_row,
    decision_payload_sha256,
    json_safe,
    load_review_decision_file,
    normalize_review_decision,
    review_queue_names,
    row_to_dict,
)


def test_review_queue_names_are_stable() -> None:
    assert review_queue_names() == [
        "benefit-events",
        "entity-classifications",
        "official-match-candidates",
        "party-entity-links",
        "sector-policy-links",
    ]
    assert REVIEW_QUEUES["benefit-events"].subject_type == "influence_event"
    assert REVIEW_QUEUES["sector-policy-links"].subject_type == "sector_policy_topic_link"
    assert REVIEW_QUEUES["party-entity-links"].subject_type == "party_entity_link"


def test_review_queue_fingerprints_avoid_surrogate_entity_ids() -> None:
    assert "emc.entity_id::text" not in OFFICIAL_MATCH_CANDIDATES_SQL
    assert "entity_industry_classification.entity_id::text" not in ENTITY_CLASSIFICATIONS_SQL
    assert "entity.entity_type || ':' || observation.stable_key" in OFFICIAL_MATCH_CANDIDATES_SQL
    assert "entity.entity_type || ':' ||" in ENTITY_CLASSIFICATIONS_SQL
    assert "sector_policy_topic_link:' || link.public_sector" in SECTOR_POLICY_LINKS_SQL
    assert "to_char(link.confidence, 'FM0.000')" in SECTOR_POLICY_LINKS_SQL
    assert "link.party_id::text" not in PARTY_ENTITY_LINKS_SQL
    assert "link.entity_id::text" not in PARTY_ENTITY_LINKS_SQL
    assert "party_entity_link:' ||" in PARTY_ENTITY_LINKS_SQL
    assert "entity.normalized_name" in PARTY_ENTITY_LINKS_SQL
    assert "aec_money_flow_context" in PARTY_ENTITY_LINKS_SQL


def test_json_safe_preserves_publishable_values() -> None:
    assert json_safe(Decimal("12.30")) == "12.30"
    assert json_safe(date(2026, 4, 27)) == "2026-04-27"
    assert json_safe(datetime(2026, 4, 27, tzinfo=timezone.utc)) == "2026-04-27T00:00:00+00:00"
    assert json_safe({"already": "json"}) == {"already": "json"}


def test_row_to_dict_uses_column_names() -> None:
    assert row_to_dict(["review_subject_id", "amount"], (123, Decimal("4.50"))) == {
        "review_subject_id": 123,
        "amount": "4.50",
    }


def test_normalize_review_decision_accepts_exported_subject_fields() -> None:
    decision = normalize_review_decision(
        {
            "review_subject_type": "entity_match_candidate",
            "review_subject_id": 42,
            "subject_external_key": (
                "entity_match_candidate:beach energy:company:"
                "lobbyist_client:exact_normalized_name"
            ),
            "review_subject_fingerprint": "abc123",
            "decision": "accept",
            "reviewer": "m.zyphur@uq.edu.au",
            "evidence_note": "Official client row and donor entity refer to the same legal entity.",
            "proposed_changes": {"entity_type": "company"},
        },
        line_number=1,
    )

    assert decision["subject_type"] == "entity_match_candidate"
    assert decision["subject_id"] == 42
    assert decision["expected_subject_fingerprint"] == "abc123"
    assert decision["decision_key"].startswith("review:")
    assert decision["payload_sha256"] == decision_payload_sha256(decision)


def test_normalize_sector_policy_link_decision_requires_stable_key() -> None:
    decision = normalize_review_decision(
        {
            "subject_type": "sector_policy_topic_link",
            "subject_external_key": (
                "sector_policy_topic_link:fossil_fuels:"
                "they_vote_for_you_policy_99:direct_material_interest:manual"
            ),
            "decision": "accept",
            "reviewer": "m.zyphur@uq.edu.au",
            "evidence_note": (
                "Policy topic concerns fossil-fuel regulation and the sector has a direct "
                "material interest in the policy outcome."
            ),
            "proposed_changes": {
                "public_sector": "fossil_fuels",
                "topic_slug": "they_vote_for_you_policy_99",
                "relationship": "direct_material_interest",
                "method": "manual",
                "confidence": "0.900",
            },
            "supporting_sources": [
                {
                    "evidence_role": "topic_scope",
                    "url": "https://theyvoteforyou.org.au/policies/99",
                },
                {
                    "evidence_role": "sector_material_interest",
                    "url": "https://example.org/fossil-fuel-policy-material-interest",
                },
            ],
        },
        line_number=1,
    )

    assert decision["subject_type"] == "sector_policy_topic_link"
    assert decision["subject_id"] is None
    assert decision["subject_external_key"].startswith("sector_policy_topic_link:fossil_fuels:")
    assert decision["payload_sha256"] == decision_payload_sha256(decision)


def test_normalize_party_entity_link_decision_requires_stable_key() -> None:
    decision = normalize_review_decision(
        {
            "subject_type": "party_entity_link",
            "subject_external_key": (
                "party_entity_link:CWLTH:example party:"
                "example party federal campaign:political_party:party_branch"
            ),
            "decision": "reject",
            "reviewer": "m.zyphur@uq.edu.au",
            "evidence_note": (
                "The name is similar but the source does not support a current party/entity "
                "relationship."
            ),
        },
        line_number=1,
    )

    assert decision["subject_type"] == "party_entity_link"
    assert decision["subject_id"] is None
    assert decision["subject_external_key"].startswith("party_entity_link:CWLTH:")
    assert decision["payload_sha256"] == decision_payload_sha256(decision)


def test_decision_key_changes_when_reviewed_fingerprint_changes() -> None:
    base = {
        "subject_type": "sector_policy_topic_link",
        "subject_external_key": (
            "sector_policy_topic_link:fossil_fuels:"
            "they_vote_for_you_policy_99:direct_material_interest:manual"
        ),
        "decision": "accept",
        "reviewer": "m.zyphur@uq.edu.au",
        "evidence_note": "Reviewed sector-policy linkage.",
        "proposed_changes": {
            "public_sector": "fossil_fuels",
            "topic_slug": "they_vote_for_you_policy_99",
            "relationship": "direct_material_interest",
            "method": "manual",
            "confidence": "0.900",
        },
        "supporting_sources": [
            {"evidence_role": "topic_scope", "url": "https://theyvoteforyou.org.au/policies/99"},
            {
                "evidence_role": "sector_material_interest",
                "url": "https://example.org/fossil-fuel-policy-material-interest",
            },
        ],
    }
    first = normalize_review_decision(
        {**base, "review_subject_fingerprint": "fingerprint-v1"},
        line_number=1,
    )
    second = normalize_review_decision(
        {**base, "review_subject_fingerprint": "fingerprint-v2"},
        line_number=1,
    )

    assert first["decision_key"] != second["decision_key"]


def test_decision_from_db_row_rejects_generated_subject_without_external_key() -> None:
    reviewed_at = datetime(2026, 4, 27, tzinfo=timezone.utc)
    try:
        decision_from_db_row(
            (
                10,
                "review:legacy",
                "influence_event",
                123,
                None,
                "accept",
                "reviewer@example.org",
                reviewed_at,
                "Legacy ID-only decisions cannot be replayed safely.",
                {},
                [],
                {},
            )
        )
    except ReviewImportError as exc:
        assert "missing subject_external_key" in str(exc)
    else:  # pragma: no cover - assertion helper.
        raise AssertionError("Expected ReviewImportError")


def test_generated_review_decisions_require_external_key() -> None:
    try:
        normalize_review_decision(
            {
                "review_subject_type": "influence_event",
                "review_subject_id": 42,
                "decision": "accept",
                "reviewer": "m.zyphur@uq.edu.au",
                "evidence_note": "Missing external key should fail.",
            },
            line_number=1,
        )
    except ReviewImportError as exc:
        assert "require subject_external_key" in str(exc)
    else:  # pragma: no cover - assertion helper.
        raise AssertionError("Expected ReviewImportError")


def test_decision_key_is_stable_without_review_timestamp() -> None:
    first = normalize_review_decision(
        {
            "subject_type": "influence_event",
            "subject_external_key": "gift_interest:abc",
            "decision": "accept",
            "reviewer": "reviewer@example.org",
            "evidence_note": "Source text is clear enough for publication as a disclosed benefit.",
        },
        line_number=1,
    )
    second = {**first, "reviewed_at": first["reviewed_at"].replace(year=first["reviewed_at"].year)}

    assert decision_key_for(first) == decision_key_for(second)


def test_decision_key_ignores_numeric_id_when_external_key_exists() -> None:
    base = {
        "subject_type": "influence_event",
        "subject_external_key": "gift_interest:abc",
        "decision": "accept",
        "reviewer": "reviewer@example.org",
        "evidence_note": "Source text is clear enough for publication as a disclosed benefit.",
        "proposed_changes": {},
        "supporting_sources": [],
    }

    assert decision_key_for({**base, "subject_id": 1}) == decision_key_for(
        {**base, "subject_id": 999}
    )


def test_load_review_decision_file_rejects_missing_evidence_note(tmp_path) -> None:
    path = tmp_path / "decisions.jsonl"
    path.write_text(
        '{"subject_type":"influence_event","subject_external_key":"gift_interest:abc",'
        '"decision":"accept","reviewer":"reviewer@example.org"}\n',
        encoding="utf-8",
    )

    try:
        load_review_decision_file(path)
    except ReviewImportError as exc:
        assert "evidence_note is required" in str(exc)
    else:  # pragma: no cover - assertion helper.
        raise AssertionError("Expected ReviewImportError")


def test_decision_from_db_row_round_trips_import_payload() -> None:
    reviewed_at = datetime(2026, 4, 27, tzinfo=timezone.utc)
    loaded = decision_from_db_row(
        (
            9,
            "review:abc",
            "influence_event",
            None,
            "gift_interest:abc",
            "accept",
            "reviewer@example.org",
            reviewed_at,
            "Accepted as a disclosed benefit based on source text.",
            {"amount_status": "not_disclosed"},
            [{"url": "https://example.org/source"}],
            {"expected_subject_fingerprint": "fingerprint-1"},
        )
    )

    decision = loaded["decision"]
    assert loaded["decision_id"] == 9
    assert decision["decision_key"] == "review:abc"
    assert decision["subject_external_key"] == "gift_interest:abc"
    assert decision["expected_subject_fingerprint"] == "fingerprint-1"
    assert decision["payload_sha256"] == decision_payload_sha256(decision)
