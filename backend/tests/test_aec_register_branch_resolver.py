"""Tests for the AEC Register branch resolver (Batch C PR 2).

Resolver MUST:
- Resolve `Australian Labor Party (ACT Branch)` to canonical ALP via the
  documented branch alias rule, NOT via fuzzy similarity.
- Resolve `Australian Labor Party` exactly when the party directory has a
  single ALP row.
- Treat individual names like `Allegra Spender`, `Dr Monique Ryan` as
  `unresolved_individual_segment`, never auto-linking to a party.
- Fail closed on ambiguous matches (multiple party rows with the same
  normalized name) — `unresolved_multiple_matches`, not auto-pick.
- Fail closed when no rule resolves — `unresolved_no_match`.
- Pass through the matched rule id + candidate ids in metadata so PR 2's
  loader can produce auditable evidence_notes and review-queue entries.

Pure-function tests against a synthetic `PartyDirectory`; no DB required.
"""
from __future__ import annotations

import pytest

from au_politics_money.ingest.aec_register_branch_resolver import (
    PartyDirectory,
    resolve_segment,
    resolve_segments,
)


@pytest.fixture
def deduped_directory() -> PartyDirectory:
    """A 'clean' directory with exactly one row per canonical party.

    Used to exercise the happy paths where exact and branch resolution both
    yield unique matches.
    """
    return PartyDirectory.from_rows(
        [
            (1, "Australian Labor Party", "ALP"),
            (2, "Liberal Party", "LP"),
            (3, "Liberal National Party", "LNP"),
            (4, "Country Liberal Party", "CLP"),
            (5, "Australian Greens", "Australian Greens"),
            (6, "AG", "AG"),  # short-only canonical row
            (7, "National Party", "NATS"),
            (8, "Independent", "IND"),
            (9, "Pauline Hanson's One Nation Party", "ON"),
            (10, "Katter's Australian Party", "KAP"),
        ]
    )


@pytest.fixture
def duplicate_alp_directory() -> PartyDirectory:
    """Mirrors the live local DB which has multiple ALP rows; the resolver
    must fail closed on this rather than auto-pick one."""
    return PartyDirectory.from_rows(
        [
            (1, "ALP", "ALP"),
            (1351, "Australian Labor Party", "Australian Labor Party"),
            (152936, "Australian Labor Party", "ALP"),
            (1412, "Australian Greens", "Australian Greens"),
        ]
    )


# --- Stage 1: exact-normalized matches -------------------------------------


def test_exact_match_resolves_unambiguous_party(deduped_directory: PartyDirectory) -> None:
    res = resolve_segment("Australian Labor Party", deduped_directory)
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == 1
    assert res.canonical_party_name == "Australian Labor Party"
    assert res.notes["stage"] == "exact_normalized_party_name_or_short_name"


def test_exact_short_name_match_resolves(deduped_directory: PartyDirectory) -> None:
    res = resolve_segment("ALP", deduped_directory)
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == 1


def test_exact_match_normalizes_punctuation(deduped_directory: PartyDirectory) -> None:
    res = resolve_segment("  Australian   Labor   Party.  ", deduped_directory)
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == 1


def test_duplicate_party_rows_fail_closed(duplicate_alp_directory: PartyDirectory) -> None:
    res = resolve_segment("Australian Labor Party", duplicate_alp_directory)
    assert res.resolver_status == "unresolved_multiple_matches"
    assert res.canonical_party_id is None
    assert sorted(res.candidate_party_ids) == [1351, 152936]
    assert res.notes["ambiguity"] == "multiple_party_rows_match_normalized_segment"


# --- Stage 2: branch alias rules ------------------------------------------


@pytest.mark.parametrize(
    "segment,expected_rule_id",
    [
        ("Australian Labor Party (ACT Branch)", "alp_state_or_territory_branch_to_alp_parent_v1"),
        ("Australian Labor Party (NSW Branch)", "alp_state_or_territory_branch_to_alp_parent_v1"),
        ("Australian Labor Party (N.S.W. Branch)", "alp_state_or_territory_branch_to_alp_parent_v1"),
        ("Australian Labor Party (South Australian Branch)", "alp_state_or_territory_branch_to_alp_parent_v1"),
        # AEC's QLD branch wording omits the trailing 'Branch' suffix; the
        # resolver has a dedicated rule for it.
        ("Australian Labor Party (State of Queensland)", "alp_state_of_queensland_to_alp_parent_v1"),
        ("Australian Labor Party (Tasmanian Branch)", "alp_state_or_territory_branch_to_alp_parent_v1"),
        ("Australian Labor Party (Victorian Branch)", "alp_state_or_territory_branch_to_alp_parent_v1"),
        ("Australian Labor Party (Western Australian Branch)", "alp_state_or_territory_branch_to_alp_parent_v1"),
    ],
)
def test_alp_state_branch_resolves_to_canonical_alp(
    segment: str, expected_rule_id: str, deduped_directory: PartyDirectory
) -> None:
    res = resolve_segment(segment, deduped_directory)
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == 1
    assert res.matched_via_rule_id == expected_rule_id
    assert "attribution_limit" in res.notes


def test_alp_trailing_branch_qualifier_resolves(deduped_directory: PartyDirectory) -> None:
    res = resolve_segment(
        "Australian Labor Party (Northern Territory) Branch",
        deduped_directory,
    )
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == 1
    assert res.matched_via_rule_id == "alp_nt_or_qld_trailing_branch_v1"


def test_liberal_state_division_resolves_to_liberal_party(
    deduped_directory: PartyDirectory,
) -> None:
    res = resolve_segment("Liberal Party of Australia (NSW Division)", deduped_directory)
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == 2


def test_greens_state_branch_resolves(deduped_directory: PartyDirectory) -> None:
    res = resolve_segment("Australian Greens (Victorian Branch)", deduped_directory)
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == 5


def test_nationals_state_branch_resolves(deduped_directory: PartyDirectory) -> None:
    res = resolve_segment(
        "National Party of Australia (NSW Branch)", deduped_directory
    )
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == 7


def test_alp_branch_with_duplicate_directory_still_fails_closed(
    duplicate_alp_directory: PartyDirectory,
) -> None:
    res = resolve_segment(
        "Australian Labor Party (ACT Branch)", duplicate_alp_directory
    )
    assert res.resolver_status == "unresolved_multiple_matches"
    assert res.matched_via_rule_id == "alp_state_or_territory_branch_to_alp_parent_v1"
    assert sorted(res.candidate_party_ids) == [1351, 152936]


def test_alias_target_missing_from_directory_returns_no_match() -> None:
    # Directory has no ALP row at all; alias rule fires but rewrite resolves
    # to nothing.
    directory = PartyDirectory.from_rows([(99, "Australian Greens", "Australian Greens")])
    res = resolve_segment("Australian Labor Party (NSW Branch)", directory)
    assert res.resolver_status == "unresolved_no_match"
    assert res.matched_via_rule_id == "alp_state_or_territory_branch_to_alp_parent_v1"
    assert (
        res.notes["ambiguity"] == "alias_rewrite_target_missing_from_party_directory"
    )


# --- Stage 3: parenthetical short-form aliases ----------------------------


def test_parenthetical_short_name_alias_resolves(
    deduped_directory: PartyDirectory,
) -> None:
    res = resolve_segment("Australian Labor Party (ALP)", deduped_directory)
    # The short-form match is via Stage 3, but the segment also matches Stage 2
    # for ALP branch (no — it doesn't, the rule requires a branch keyword).
    # Stage 1 fails because the full string is not exactly "Australian Labor Party".
    # So Stage 3 should fire on the trailing (ALP).
    assert res.resolver_status == "resolved_alias"
    assert res.canonical_party_id == 1
    assert res.matched_via_rule_id == "parenthetical_short_name_alias_v1"


# --- Individual segments (Allegra Spender etc.) ---------------------------


@pytest.mark.parametrize(
    "individual",
    [
        "Allegra Spender",
        "Dr Monique Ryan",
        "Benjamin John Smith",
        "Francine Wiig",
        "Keryn Jones",
        "Anita Kuss",
    ],
)
def test_individual_segments_never_auto_link(
    individual: str, deduped_directory: PartyDirectory
) -> None:
    res = resolve_segment(individual, deduped_directory)
    assert res.resolver_status == "unresolved_individual_segment"
    assert res.canonical_party_id is None
    assert res.matched_via_rule_id is None
    assert "individual" in res.notes["rationale"].lower()


# --- Adversarial guards: do not auto-link via fuzzy similarity ------------


def test_unrelated_segment_returns_no_match(deduped_directory: PartyDirectory) -> None:
    res = resolve_segment("Animal Justice Party", deduped_directory)
    assert res.resolver_status == "unresolved_no_match"
    assert res.canonical_party_id is None


def test_misspelled_party_does_not_fuzzy_match(
    deduped_directory: PartyDirectory,
) -> None:
    res = resolve_segment("Austraian Labor Pary", deduped_directory)  # missing letters
    assert res.resolver_status == "unresolved_no_match"
    assert res.canonical_party_id is None


def test_branch_segment_with_unknown_state_does_not_match() -> None:
    # The pattern allowlist only includes Australian state/territory abbrevs;
    # an unknown qualifier (e.g. fictional Z Branch) must not resolve.
    directory = PartyDirectory.from_rows([(1, "Australian Labor Party", "ALP")])
    res = resolve_segment(
        "Australian Labor Party (Z Branch)", directory
    )
    assert res.resolver_status == "unresolved_no_match"


# --- Multi-segment helper -------------------------------------------------


def test_resolve_segments_handles_mixed_input(deduped_directory: PartyDirectory) -> None:
    segments = [
        "Australian Labor Party (ACT Branch)",
        "Allegra Spender",
        "Australian Greens",
        "Animal Justice Party",
    ]
    results = resolve_segments(segments, deduped_directory)
    assert [r.resolver_status for r in results] == [
        "resolved_branch",
        "unresolved_individual_segment",
        "resolved_exact",
        "unresolved_no_match",
    ]
    # Only the resolved ones produce canonical_party_id values, and they
    # produce them deterministically without fuzzy matching.
    canonical_ids = [r.canonical_party_id for r in results]
    assert canonical_ids == [1, None, 5, None]


def test_party_directory_normalization_collapses_whitespace_and_punctuation() -> None:
    directory = PartyDirectory.from_rows([(42, "Pauline Hanson's One Nation Party", "ON")])
    res = resolve_segment(
        "Pauline   Hanson's One   Nation Party!!!", directory
    )
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == 42


# --- Source-jurisdiction disambiguation -----------------------------------
#
# The local DB legitimately stores both a federal-jurisdiction `Australian
# Labor Party` row (id=1351, jurisdiction_id=1) AND a QLD-jurisdiction
# `Australian Labor Party` row (id=152936, jurisdiction_id=41). They are
# NOT duplicates — they belong to different jurisdiction scopes. When the
# AEC Register (a federal source) yields an `Australian Labor Party`
# segment, the resolver must deterministically prefer the federal-
# jurisdiction row, NOT fail closed and NOT pick fuzzily.


@pytest.fixture
def federal_vs_state_duplicate_alp_directory() -> PartyDirectory:
    """ALP federal row + ALP QLD-state row, plus an unrelated party."""
    return PartyDirectory.from_rows(
        [
            (1351, "Australian Labor Party", "Australian Labor Party", 1),
            (152936, "Australian Labor Party", "ALP", 41),
            (1412, "Australian Greens", "Australian Greens", 1),
        ]
    )


def test_source_jurisdiction_breaks_exact_federal_state_tie(
    federal_vs_state_duplicate_alp_directory: PartyDirectory,
) -> None:
    res = resolve_segment(
        "Australian Labor Party",
        federal_vs_state_duplicate_alp_directory,
        source_jurisdiction_id=1,
    )
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == 1351
    assert res.matched_via_rule_id == "source_jurisdiction_disambiguation_v1"
    juris_notes = res.notes["source_jurisdiction_disambiguation"]
    assert juris_notes["source_jurisdiction_id"] == 1
    assert juris_notes["candidate_party_ids_before"] == [1351, 152936]


def test_source_jurisdiction_breaks_branch_alias_federal_state_tie(
    federal_vs_state_duplicate_alp_directory: PartyDirectory,
) -> None:
    res = resolve_segment(
        "Australian Labor Party (ACT Branch)",
        federal_vs_state_duplicate_alp_directory,
        source_jurisdiction_id=1,
    )
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == 1351
    assert (
        res.matched_via_rule_id
        == "alp_state_or_territory_branch_to_alp_parent_v1"
    )
    juris_notes = res.notes["source_jurisdiction_disambiguation"]
    assert juris_notes["source_jurisdiction_id"] == 1
    assert juris_notes["candidate_party_ids_before"] == [1351, 152936]


def test_source_jurisdiction_unknown_keeps_old_fail_closed_behaviour(
    federal_vs_state_duplicate_alp_directory: PartyDirectory,
) -> None:
    res = resolve_segment(
        "Australian Labor Party",
        federal_vs_state_duplicate_alp_directory,
    )
    assert res.resolver_status == "unresolved_multiple_matches"
    assert res.canonical_party_id is None


def test_source_jurisdiction_with_no_matching_candidate_still_fails_closed(
    federal_vs_state_duplicate_alp_directory: PartyDirectory,
) -> None:
    # Pretend the AEC Register lived in jurisdiction 999, which no party
    # row matches. Disambiguation must NOT pick anything and must fail
    # closed.
    res = resolve_segment(
        "Australian Labor Party",
        federal_vs_state_duplicate_alp_directory,
        source_jurisdiction_id=999,
    )
    assert res.resolver_status == "unresolved_multiple_matches"
    assert res.canonical_party_id is None


def test_source_jurisdiction_with_two_matching_candidates_still_fails_closed() -> None:
    # Two rows in the SAME jurisdiction with the same name — disambiguation
    # cannot break this, and the resolver must remain fail-closed.
    directory = PartyDirectory.from_rows(
        [
            (10, "Independent", "IND", 1),
            (11, "Independent", "Independent", 1),
        ]
    )
    res = resolve_segment(
        "Independent",
        directory,
        source_jurisdiction_id=1,
    )
    assert res.resolver_status == "unresolved_multiple_matches"
    assert res.canonical_party_id is None


def test_source_jurisdiction_does_not_change_unique_match() -> None:
    # When there is already exactly one candidate, disambiguation must be a
    # no-op and must NOT decorate the resolution with a rule id.
    directory = PartyDirectory.from_rows(
        [
            (1, "Australian Labor Party", "ALP", 1),
            (2, "Australian Greens", "Australian Greens", 1),
        ]
    )
    res = resolve_segment(
        "Australian Labor Party", directory, source_jurisdiction_id=1
    )
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == 1
    assert res.matched_via_rule_id is None
    assert "source_jurisdiction_disambiguation" not in res.notes


def test_three_tuple_directory_is_still_supported() -> None:
    # Backwards compatibility: existing fixtures and callers that pass
    # 3-tuples (id, name, short_name) without jurisdiction continue to
    # work, and disambiguation is silently a no-op.
    directory = PartyDirectory.from_rows(
        [
            (1, "Australian Labor Party", "ALP"),
            (2, "Australian Greens", "Australian Greens"),
        ]
    )
    res = resolve_segment(
        "Australian Labor Party", directory, source_jurisdiction_id=1
    )
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == 1
