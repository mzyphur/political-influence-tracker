from __future__ import annotations

from au_politics_money.db.party_entity_suggestions import (
    party_entity_name_patterns,
    party_entity_name_terms,
)


def test_party_entity_name_patterns_skip_non_party_labels() -> None:
    for label in ("IND", "Independent", "PRES", "DPRES"):
        party = {"name": label, "short_name": label}
        assert party_entity_name_patterns(party) == []
        assert party_entity_name_terms(party) == []


def test_party_entity_name_patterns_keep_current_party_families() -> None:
    labor = {"name": "ALP", "short_name": "ALP"}
    liberal = {"name": "LP", "short_name": "LP"}
    greens = {"name": "AG", "short_name": "AG"}

    assert "Australian Labor Party%" in party_entity_name_patterns(labor)
    assert "liberal party" in party_entity_name_terms(liberal)
    assert "australian greens" in party_entity_name_terms(greens)
