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
    """Synthetic directory that simulates two ALP rows with the same
    canonical name in the SAME jurisdiction. The resolver must fail
    closed on this rather than auto-pick one — even with source-
    jurisdiction disambiguation, ambiguity within a single jurisdiction
    is unresolvable.

    Note: the previous version of this fixture mirrored the live local
    DB's pre-`034_consolidate_federal_party_duplicates` state (id=1351
    federal long-form + id=152936 QLD short-form). After migration 034
    consolidated short/long-form federal pairs and the resolver gained
    the source-jurisdiction disambiguation rule, this fixture is now a
    deliberately-constructed adversarial case rather than a live mirror.
    The `federal_vs_state_duplicate_alp_directory` fixture below covers
    the live federal-vs-state case that disambiguation can break.
    """
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


# --- Extended alias rules (Batch E) -----------------------------------------


@pytest.fixture
def post_seed_directory() -> PartyDirectory:
    """Mirrors the local DB AFTER migrations 034 + 035 have been applied:
    federal short-form rows are the canonical home for the major parties,
    plus the seeded Animal Justice / Australian Citizens / Libertarian /
    Shooters Fishers & Farmers rows. State-jurisdiction rows are kept
    where they exist live (jurisdiction_id=41 for QLD)."""
    return PartyDirectory.from_rows(
        [
            (1, "Australian Labor Party", "ALP", 1),
            (3, "Liberal Party", "LP", 1),
            (6, "Liberal National Party", "LNP", 1),
            (10, "National Party", "NATS", 1),
            (11, "Independent", "IND", 1),
            (66, "Katter's Australian Party", "KAP", 1),
            (136, "Australian Greens", "AG", 1),
            (8192, "Country Liberal Party", "CLP", 1),
            (200001, "Animal Justice Party", "AJP", 1),
            (200002, "Australian Citizens Party", "CITZN", 1),
            (200003, "Libertarian Party", "LIB-DEM", 1),
            (200004, "Shooters, Fishers and Farmers Party", "SFF", 1),
            (152936, "Australian Labor Party", "ALP", 41),
        ]
    )


@pytest.mark.parametrize(
    "segment,expected_party_id,expected_rule_id",
    [
        # Bare federal long forms map to the canonical short-name row.
        (
            "Liberal Party of Australia",
            3,
            "liberal_party_of_australia_long_form_v1",
        ),
        (
            "National Party of Australia",
            10,
            "national_party_of_australia_long_form_v1",
        ),
        (
            "Liberal National Party of Queensland",
            6,
            "liberal_national_party_of_queensland_long_form_v1",
        ),
        # Comma- and hyphen-delimited Liberal state divisions.
        (
            "Liberal Party of Australia, NSW Division",
            3,
            "liberal_party_state_division_punctuated_v1",
        ),
        (
            "Liberal Party of Australia - ACT Division",
            3,
            "liberal_party_state_division_punctuated_v1",
        ),
        (
            "Liberal Party of Australia - Tasmanian Division",
            3,
            "liberal_party_state_division_punctuated_v1",
        ),
        # Parens with dot-abbreviated state codes that the v1 regex did not
        # cover and parens with full state names.
        (
            "Liberal Party of Australia (S.A. Division)",
            3,
            "liberal_party_state_division_to_liberal_parent_v1",
        ),
        (
            "Liberal Party of Australia (Victorian Division)",
            3,
            "liberal_party_state_division_to_liberal_parent_v1",
        ),
        # WA Liberals registered name carries an "Inc"/"Inc." suffix.
        (
            "Liberal Party (W.A. Division) Inc",
            3,
            "liberal_party_wa_division_inc_v1",
        ),
        (
            "Liberal Party (W.A. Division) Inc.",
            3,
            "liberal_party_wa_division_inc_v1",
        ),
        # Hyphen-delimited Nationals state branches.
        (
            "National Party of Australia - N.S.W.",
            10,
            "nationals_state_branch_punctuated_v1",
        ),
        (
            "National Party of Australia - Victoria",
            10,
            "nationals_state_branch_punctuated_v1",
        ),
        # CLP with explicit (NT) suffix.
        (
            "Country Liberal Party (NT)",
            8192,
            "country_liberal_party_nt_short_form_v1",
        ),
    ],
)
def test_extended_alias_rules_resolve_to_canonical_party(
    segment: str,
    expected_party_id: int,
    expected_rule_id: str,
    post_seed_directory: PartyDirectory,
) -> None:
    res = resolve_segment(segment, post_seed_directory, source_jurisdiction_id=1)
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == expected_party_id
    assert res.matched_via_rule_id == expected_rule_id


@pytest.mark.parametrize(
    "segment,expected_party_id",
    [
        ("Animal Justice Party", 200001),
        ("Australian Citizens Party", 200002),
        ("Libertarian Party", 200003),
        ("Shooters, Fishers and Farmers Party", 200004),
    ],
)
def test_seeded_canonical_parties_resolve_via_exact_match(
    segment: str,
    expected_party_id: int,
    post_seed_directory: PartyDirectory,
) -> None:
    res = resolve_segment(segment, post_seed_directory, source_jurisdiction_id=1)
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == expected_party_id


def test_parenthetical_short_form_picks_federal_when_disambiguated(
    post_seed_directory: PartyDirectory,
) -> None:
    """`Australian Labor Party (ALP)` previously fell through to
    unresolved_no_match because two short_name='ALP' rows existed
    (federal id=1 + QLD id=152936). With source-jurisdiction
    disambiguation the parenthetical resolver now picks the federal row.
    """
    res = resolve_segment(
        "Australian Labor Party (ALP)",
        post_seed_directory,
        source_jurisdiction_id=1,
    )
    assert res.resolver_status == "resolved_alias"
    assert res.canonical_party_id == 1
    assert res.matched_via_rule_id == "parenthetical_short_name_alias_v1"
    assert "source_jurisdiction_disambiguation" in res.notes


# --- Batch F second-wave alias rules + politicalparty long-tail seeds ----


@pytest.fixture
def post_v2_seed_directory() -> PartyDirectory:
    """Mirrors the local DB after migrations 034 + 035 + 036 + the
    `_v1` resolver rules. Adds Australian Federation Party, Family First
    Party Australia, The Great Australian Party, Better Together Party,
    Indigenous - Aboriginal Party of Australia, Socialist Alliance,
    Sustainable Australia Party, Power 2 People, and Health Environment
    Accountability Rights Transparency on top of `post_seed_directory`'s
    parties.
    """
    return PartyDirectory.from_rows(
        [
            (1, "Australian Labor Party", "ALP", 1),
            (3, "Liberal Party", "LP", 1),
            (6, "Liberal National Party", "LNP", 1),
            (10, "National Party", "NATS", 1),
            (11, "Independent", "IND", 1),
            (66, "Katter's Australian Party", "KAP", 1),
            (136, "Australian Greens", "AG", 1),
            (8192, "Country Liberal Party", "CLP", 1),
            (200001, "Animal Justice Party", "AJP", 1),
            (200002, "Australian Citizens Party", "CITZN", 1),
            (200003, "Libertarian Party", "LIB-DEM", 1),
            (200004, "Shooters, Fishers and Farmers Party", "SFF", 1),
            (200005, "Australian Federation Party", "AFP", 1),
            (200006, "Family First Party Australia", "FFP", 1),
            (200007, "The Great Australian Party", "TGAP", 1),
            (200008, "Better Together Party", "BTP", 1),
            (200009, "Indigenous - Aboriginal Party of Australia", "IAPA", 1),
            (200010, "Socialist Alliance", "SA", 1),
            (200011, "Sustainable Australia Party", "SUSAUS", 1),
            (200012, "Power 2 People", "P2P", 1),
            (
                200013,
                "Health Environment Accountability Rights Transparency",
                "HEART",
                1,
            ),
            (152936, "Australian Labor Party", "ALP", 41),
        ]
    )


@pytest.mark.parametrize(
    "segment,expected_party_id,expected_rule_id",
    [
        # Greens variants the v1 rule did not catch.
        (
            "Australian Greens (South Australia)",
            136,
            "greens_state_branch_to_australian_greens_parent_v1",
        ),
        (
            "Australian Greens, Australian Capital Territory Branch",
            136,
            "greens_state_branch_punctuated_v1",
        ),
        (
            "Australian Greens, Northern Territory Branch",
            136,
            "greens_state_branch_punctuated_v1",
        ),
        (
            "Australian Greens, Tasmanian Branch",
            136,
            "greens_state_branch_punctuated_v1",
        ),
        (
            "Australian Greens Victoria",
            136,
            "greens_state_branch_unpunctuated_v1",
        ),
        (
            "The Greens NSW",
            136,
            "the_greens_short_form_to_australian_greens_v1",
        ),
        (
            "The Greens (WA) Inc",
            136,
            "the_greens_short_form_to_australian_greens_v1",
        ),
        # Nationals state divisions with Inc suffix.
        (
            "National Party of Australia (S.A.) Inc.",
            10,
            "nationals_state_branch_inc_suffix_v1",
        ),
        (
            "National Party of Australia (WA) Inc",
            10,
            "nationals_state_branch_inc_suffix_v1",
        ),
        # Australian Federation Party state suffixes.
        (
            "Australian Federation Party Australian Capital Territory",
            200005,
            "australian_federation_party_state_branch_v1",
        ),
        (
            "Australian Federation Party Western Australia",
            200005,
            "australian_federation_party_state_branch_v1",
        ),
        # Libertarian Party state branches.
        (
            "Libertarian Party of Queensland",
            200003,
            "libertarian_party_state_branch_v1",
        ),
        # Sustainable Australia Party "Affordable Housing Now" alias.
        (
            "Affordable Housing Now - Sustainable Australia Party",
            200011,
            "affordable_housing_now_to_sustainable_australia_v1",
        ),
        # HEART parenthetical short-form name.
        (
            "Health Environment Accountability Rights Transparency (HEART)",
            200013,
            "health_environment_accountability_rights_transparency_paren_v1",
        ),
    ],
)
def test_second_wave_alias_rules_resolve_to_canonical_party(
    segment: str,
    expected_party_id: int,
    expected_rule_id: str,
    post_v2_seed_directory: PartyDirectory,
) -> None:
    res = resolve_segment(
        segment, post_v2_seed_directory, source_jurisdiction_id=1
    )
    assert res.resolver_status == "resolved_branch"
    assert res.canonical_party_id == expected_party_id
    assert res.matched_via_rule_id == expected_rule_id


@pytest.mark.parametrize(
    "segment,expected_party_id",
    [
        ("Australian Federation Party", 200005),
        ("Family First Party Australia", 200006),
        ("The Great Australian Party", 200007),
        ("Better Together Party", 200008),
        ("Indigenous - Aboriginal Party of Australia", 200009),
        ("Socialist Alliance", 200010),
        ("Sustainable Australia Party", 200011),
        ("Power 2 People", 200012),
        ("Health Environment Accountability Rights Transparency", 200013),
    ],
)
def test_v2_seeded_canonical_parties_resolve_via_exact_match(
    segment: str,
    expected_party_id: int,
    post_v2_seed_directory: PartyDirectory,
) -> None:
    res = resolve_segment(
        segment, post_v2_seed_directory, source_jurisdiction_id=1
    )
    assert res.resolver_status == "resolved_exact"
    assert res.canonical_party_id == expected_party_id


# --- State-branch detection (sub-national rollout, Batch R) ---------------


@pytest.mark.parametrize(
    "segment,expected_state_code",
    [
        # Queensland — paren forms.
        ("Australian Labor Party (Queensland)", "QLD"),
        ("Liberal National Party (Queensland Division)", "QLD"),
        ("Australian Labor Party (State of Queensland)", "QLD"),
        ("Australian Greens (QLD Branch)", "QLD"),
        # NSW — paren forms.
        ("Australian Greens (NSW Branch)", "NSW"),
        ("Liberal Party (New South Wales Division)", "NSW"),
        ("Australian Greens (N.S.W.)", "NSW"),
        # Victorian — paren forms.
        ("Liberal Party of Australia (Victorian Division)", "VIC"),
        ("Australian Greens (Victoria Branch)", "VIC"),
        ("Australian Labor Party (VIC)", "VIC"),
        # SA / WA / TAS / NT / ACT paren forms.
        ("National Party of Australia (S.A.)", "SA"),
        ("Australian Greens (Western Australia)", "WA"),
        ("Australian Labor Party (Tasmania Branch)", "TAS"),
        ("Country Liberal Party (Northern Territory)", "NT"),
        ("Australian Labor Party (ACT Branch)", "ACT"),
        # Comma-form trailing — AEC published in liberal_party_state_division_punctuated_v1.
        ("Liberal Party of Australia, NSW Division", "NSW"),
        ("Liberal Party of Australia, ACT Division", "ACT"),
        ("Liberal Party of Australia, Tasmanian Division", "TAS"),
        ("Liberal Party of Australia, Victorian Division", "VIC"),
        ("Liberal Party of Australia, South Australian Division", "SA"),
        ("Liberal Party of Australia, Western Australian Division", "WA"),
        # Dash-form trailing.
        ("Liberal Party of Australia - ACT Division", "ACT"),
        ("Liberal Party of Australia - Tasmanian Division", "TAS"),
        ("Liberal Party of Australia – Victorian Division", "VIC"),  # en-dash
        ("Liberal Party of Australia — Tasmanian Division", "TAS"),  # em-dash
        # "Division of <state>" trailing form.
        ("Liberal Party of Australia Division of New South Wales", "NSW"),
        ("Liberal Party of Australia Division of Queensland", "QLD"),
    ],
)
def test_detect_state_branch_recognises_known_wordings(
    segment: str, expected_state_code: str
) -> None:
    from au_politics_money.ingest.aec_register_branch_resolver import (
        detect_state_branch,
    )

    assert detect_state_branch(segment) == expected_state_code


@pytest.mark.parametrize(
    "segment",
    [
        # Bare federal canonical names: NO state suffix.
        "Australian Labor Party",
        "Liberal National Party",
        "Australian Greens",
        # Entity name with an incidental state mention — must NOT match.
        # The detector is restricted to TRAILING parenthetical state
        # wordings, so an entity whose name happens to contain a state
        # name (without the parenthetical form) is left alone.
        "Queensland Property Holdings Pty Ltd",
        "New South Wales Trades & Labour Council",
        "Bank of Western Australia",
    ],
)
def test_detect_state_branch_does_not_match_incidental_mentions(
    segment: str,
) -> None:
    from au_politics_money.ingest.aec_register_branch_resolver import (
        detect_state_branch,
    )

    assert detect_state_branch(segment) is None


def test_resolve_segment_with_state_branch_returns_federal_only_when_no_state(
    deduped_directory: PartyDirectory,
) -> None:
    """A bare federal canonical name with no state suffix should
    produce a CompositeResolution whose `state` is None.
    """
    from au_politics_money.ingest.aec_register_branch_resolver import (
        resolve_segment_with_state_branch,
    )

    composite = resolve_segment_with_state_branch(
        "Australian Labor Party",
        deduped_directory,
        source_jurisdiction_id=1,
        state_jurisdiction_id_by_code={"QLD": 41},
    )
    assert composite.federal.canonical_party_id == 1
    assert composite.federal.resolver_status == "resolved_exact"
    assert composite.state is None
    assert composite.state_jurisdiction_id is None
    assert composite.state_code is None


def test_resolve_segment_with_state_branch_emits_state_resolution_for_qld() -> None:
    """A QLD-branch segment that resolves via the existing branch alias
    rules should produce two resolutions: federal (canonical Australian
    Labor Party) and state (QLD-jurisdiction Australian Labor Party).

    Uses 'Australian Labor Party (State of Queensland)' which is
    explicitly handled by the existing
    `alp_state_of_queensland_to_alp_parent_v1` branch alias rule (the
    rewrite folds it to bare 'Australian Labor Party' which then
    matches via the source-jurisdiction-disambiguation rule).
    """
    from au_politics_money.ingest.aec_register_branch_resolver import (
        resolve_segment_with_state_branch,
    )

    # Directory mirrors the live state where federal ALP id=1 and QLD
    # state ALP id=152936 (per migration 034 + the existing QLD ECQ
    # ingest-side row).
    directory = PartyDirectory.from_rows(
        [
            (1, "Australian Labor Party", "ALP", 1),  # federal
            (152936, "Australian Labor Party", "ALP", 41),  # QLD state
        ]
    )

    composite = resolve_segment_with_state_branch(
        "Australian Labor Party (State of Queensland)",
        directory,
        source_jurisdiction_id=1,
        state_jurisdiction_id_by_code={"QLD": 41},
    )
    # Federal call: source_jurisdiction_id=1 should disambiguate to
    # federal canonical row (party_id=1) via the alp_state_of_queensland
    # alias rule + source-jurisdiction disambiguation.
    assert composite.federal.canonical_party_id == 1
    # State call: source_jurisdiction_id=41 should disambiguate to the
    # QLD-jurisdiction row (party_id=152936).
    assert composite.state is not None
    assert composite.state.canonical_party_id == 152936
    assert composite.state_jurisdiction_id == 41
    assert composite.state_code == "QLD"


def test_resolve_segment_with_state_branch_skips_state_when_no_mapping() -> None:
    """If the loader doesn't pass a state-jurisdiction mapping (or the
    detected state isn't in the mapping), the second pass is skipped.
    """
    from au_politics_money.ingest.aec_register_branch_resolver import (
        resolve_segment_with_state_branch,
    )

    directory = PartyDirectory.from_rows(
        [(1, "Australian Labor Party", "ALP", 1)]
    )

    # Case A: no mapping at all.
    composite_a = resolve_segment_with_state_branch(
        "Australian Labor Party (State of Queensland)",
        directory,
        source_jurisdiction_id=1,
        state_jurisdiction_id_by_code=None,
    )
    assert composite_a.state is None
    assert composite_a.state_code == "QLD"  # detected, but no mapping

    # Case B: mapping does not include QLD.
    composite_b = resolve_segment_with_state_branch(
        "Australian Labor Party (State of Queensland)",
        directory,
        source_jurisdiction_id=1,
        state_jurisdiction_id_by_code={"NSW": 43},
    )
    assert composite_b.state is None
    assert composite_b.state_code == "QLD"


def test_resolve_segment_with_state_branch_skips_when_state_equals_source() -> None:
    """If the detected state happens to equal the source jurisdiction,
    a second pass would add nothing — skip it.
    """
    from au_politics_money.ingest.aec_register_branch_resolver import (
        resolve_segment_with_state_branch,
    )

    directory = PartyDirectory.from_rows(
        [(152936, "Australian Labor Party", "ALP", 41)]
    )

    composite = resolve_segment_with_state_branch(
        "Australian Labor Party (State of Queensland)",
        directory,
        source_jurisdiction_id=41,  # source IS QLD
        state_jurisdiction_id_by_code={"QLD": 41},
    )
    # Detection still flags QLD, but no second pass.
    assert composite.state is None
    assert composite.state_code == "QLD"
    assert composite.state_jurisdiction_id == 41
