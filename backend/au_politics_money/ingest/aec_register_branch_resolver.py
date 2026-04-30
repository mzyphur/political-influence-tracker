"""Deterministic AEC-segment-to-canonical-party resolver (Batch C PR 2).

The AEC `associatedentity.AssociatedParties` field is a semicolon-separated
list of named parties or branches. To create a reviewed `party_entity_link`
under the dev's C-rule, every segment must resolve to **exactly one**
canonical `party.id` via deterministic, documented rules. No fuzzy
similarity is allowed.

Resolution stages, in order:

1. **Stage 1 — exact-normalized match** against `party.name` and
   `party.short_name`. If exactly one party row matches the normalized
   segment, return it with `resolver_status='resolved_exact'`.

2. **Stage 2 — branch alias rules**. A small, curated set of regular
   expressions identifies obvious official branch wording such as
   `Australian Labor Party (* Branch)` and rewrites the segment to its
   canonical parent name (e.g. `Australian Labor Party`). The rewrite is
   then re-matched against `party.name`/`party.short_name` exactly. If a
   unique row matches, return it with `resolver_status='resolved_branch'`
   and metadata recording which alias rule applied. Aliases are
   conservative: only documented Australian state/territory branch
   wordings are stripped, and no fuzzy similarity is used.

3. **Stage 3 — short-form parenthetical aliases**. A handful of segments
   embed an explicit short_name in parentheses, e.g.
   `Australian Labor Party (ALP)`. If the parenthetical content matches a
   `party.short_name` exactly, return that party with
   `resolver_status='resolved_alias'`.

If no stage yields a unique match, the resolver returns
`unresolved_no_match` (zero matches), `unresolved_multiple_matches`
(ambiguous between rows), or `unresolved_individual_segment` (segment
appears to be a person's name rather than a party).

The resolver is implemented as a pure function over an injected
`PartyDirectory` (a list of `(party_id, name, short_name)` tuples) so it
can be tested without a live database. The loader builds the directory
once per call and reuses it across all observations.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


RESOLVER_NAME = "aec_register_branch_resolver_v1"
RESOLVER_VERSION = "1"


# --- normalization --------------------------------------------------------


def _normalize_party_name(value: str | None) -> str:
    """Lowercase, strip non-alphanumerics, collapse whitespace.

    Mirrors `db.load.normalize_name` so resolved matches behave consistently
    with downstream party joins.
    """
    if not value:
        return ""
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


# --- party directory ------------------------------------------------------


@dataclass(frozen=True)
class PartyDirectoryRow:
    party_id: int
    name: str
    short_name: str | None
    normalized_name: str
    normalized_short_name: str


@dataclass(frozen=True)
class PartyDirectory:
    rows: tuple[PartyDirectoryRow, ...]

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[int, str, str | None]]) -> "PartyDirectory":
        directory_rows = tuple(
            PartyDirectoryRow(
                party_id=int(row[0]),
                name=str(row[1] or ""),
                short_name=str(row[2]) if row[2] else None,
                normalized_name=_normalize_party_name(row[1]),
                normalized_short_name=_normalize_party_name(row[2]),
            )
            for row in rows
        )
        return cls(rows=directory_rows)

    def find_by_normalized(self, normalized_segment: str) -> list[PartyDirectoryRow]:
        if not normalized_segment:
            return []
        return [
            row
            for row in self.rows
            if normalized_segment == row.normalized_name
            or (row.normalized_short_name and normalized_segment == row.normalized_short_name)
        ]


# --- branch alias rules ---------------------------------------------------


@dataclass(frozen=True)
class BranchAliasRule:
    rule_id: str
    pattern: re.Pattern[str]
    canonical_name: str
    description: str


# Rules are intentionally conservative. Each pattern matches only well-known
# Australian state/territory branch wordings and rewrites to a documented
# canonical parent party name. The rewritten name is then re-matched
# against the party directory exactly.
_BRANCH_ALIAS_RULES: tuple[BranchAliasRule, ...] = (
    BranchAliasRule(
        rule_id="alp_state_or_territory_branch_to_alp_parent_v1",
        pattern=re.compile(
            # Branch qualifier inside parentheses, with the literal "Branch"
            # suffix. Matches: "(ACT Branch)", "(N.S.W. Branch)", "(South
            # Australian Branch)", "(Tasmanian Branch)", "(Victorian Branch)",
            # "(Western Australian Branch)", "(NSW Branch)", "(QLD Branch)",
            # etc.
            r"^Australian Labor Party\s*\((?:ACT|N\.S\.W\.|NSW|QLD|SA|"
            r"South Australian|Tasmanian|Victorian|"
            r"Western Australian|WA|VIC)\s*Branch\)\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Australian Labor Party",
        description=(
            "AEC publishes ALP state/territory branches as separate associated-entity-"
            "linked parties; resolved to canonical Australian Labor Party for "
            "display/network context. Not a personal-receipt claim about any MP."
        ),
    ),
    BranchAliasRule(
        rule_id="alp_state_of_queensland_to_alp_parent_v1",
        pattern=re.compile(
            # AEC publishes the QLD branch as 'Australian Labor Party (State
            # of Queensland)' with NO 'Branch' suffix — distinct from the
            # other ALP state branch variants. Resolved to canonical ALP.
            r"^Australian Labor Party\s*\(State of Queensland\)\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Australian Labor Party",
        description=(
            "AEC's QLD ALP branch is named 'Australian Labor Party (State of "
            "Queensland)' without the 'Branch' suffix. Resolved to canonical "
            "Australian Labor Party. Same attribution caveat as other ALP "
            "branch resolutions."
        ),
    ),
    BranchAliasRule(
        rule_id="alp_nt_or_qld_trailing_branch_v1",
        pattern=re.compile(
            r"^Australian Labor Party\s*\((?:Northern Territory|State of Queensland)\)"
            r"\s*Branch\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Australian Labor Party",
        description=(
            "AEC publishes some ALP branches with the qualifier outside the "
            "parenthetical, e.g. 'Australian Labor Party (Northern Territory) "
            "Branch'. Resolved to canonical Australian Labor Party."
        ),
    ),
    BranchAliasRule(
        rule_id="liberal_party_state_division_to_liberal_parent_v1",
        pattern=re.compile(
            r"^Liberal Party of Australia\s*\((?:ACT|NSW|QLD|SA|TAS|VIC|WA)"
            r"(?:\s+Division)?\)\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Liberal Party",
        description=(
            "AEC publishes Liberal state divisions as separate parties. Resolved "
            "to canonical Liberal Party. Not a claim about LNP-affiliated members."
        ),
    ),
    BranchAliasRule(
        rule_id="greens_state_branch_to_australian_greens_parent_v1",
        pattern=re.compile(
            r"^Australian Greens\s*\((?:ACT|NSW|QLD|SA|TAS|VIC|WA|"
            r"Victorian|Tasmanian|Western Australian|South Australian|"
            r"Queensland)\s*Branch\)\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Australian Greens",
        description="AEC state Greens branches resolved to canonical Australian Greens.",
    ),
    BranchAliasRule(
        rule_id="nationals_state_branch_to_nationals_parent_v1",
        pattern=re.compile(
            r"^National Party of Australia\s*\((?:NSW|QLD|VIC|WA|"
            r"Victorian|Western Australian)\s*(?:Branch|Division)?\)\s*$",
            re.IGNORECASE,
        ),
        canonical_name="National Party",
        description=(
            "AEC state Nationals branches resolved to canonical National Party. "
            "Distinct from LNP and CLP which have separate canonical rows."
        ),
    ),
)


def _resolve_via_alias_rules(segment: str) -> tuple[str | None, str | None]:
    cleaned = " ".join(segment.split())
    for rule in _BRANCH_ALIAS_RULES:
        if rule.pattern.match(cleaned):
            return rule.canonical_name, rule.rule_id
    return None, None


# --- short-form parenthetical aliases -------------------------------------


_SHORT_FORM_PARENTHETICAL = re.compile(r"^(?P<base>.+?)\s*\((?P<short>[A-Z]{2,5})\)\s*$")


def _resolve_via_parenthetical_short_name(
    segment: str, directory: PartyDirectory
) -> PartyDirectoryRow | None:
    cleaned = " ".join(segment.split())
    match = _SHORT_FORM_PARENTHETICAL.match(cleaned)
    if not match:
        return None
    short_norm = _normalize_party_name(match.group("short"))
    candidates = [
        row
        for row in directory.rows
        if row.normalized_short_name and row.normalized_short_name == short_norm
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


# --- individual-name detection --------------------------------------------


# AEC AssociatedParties sometimes contains individual names (e.g.
# "Allegra Spender;", "Dr Monique Ryan;"). These must NOT auto-link as
# parties. The detector is conservative: a segment that is two-or-more
# title-cased word tokens and does not contain "Party"/"Branch"/"Division"/
# common party words counts as an individual.

_PARTY_KEYWORDS = re.compile(
    r"\b(Party|Branch|Division|Network|Alliance|Greens|Liberals?|Nationals?|"
    r"Labor|Labour|Coalition|Independents?|Federation|Group)\b",
    re.IGNORECASE,
)


def _looks_like_individual(segment: str) -> bool:
    cleaned = " ".join(segment.split())
    if not cleaned:
        return False
    if _PARTY_KEYWORDS.search(cleaned):
        return False
    tokens = cleaned.split()
    if len(tokens) < 2 or len(tokens) > 6:
        return False
    # All tokens are title-case-ish words (allow internal dots, hyphens, apostrophes)
    word_pattern = re.compile(r"^[A-Z][A-Za-z'\-\.]*$")
    return all(word_pattern.match(token) for token in tokens)


# --- public resolver ------------------------------------------------------


@dataclass(frozen=True)
class SegmentResolution:
    segment: str
    normalized_segment: str
    resolver_status: str
    canonical_party_id: int | None
    canonical_party_name: str | None
    canonical_party_short_name: str | None
    matched_via_rule_id: str | None
    candidate_party_ids: tuple[int, ...]
    notes: dict[str, Any]


def resolve_segment(segment: str, directory: PartyDirectory) -> SegmentResolution:
    """Resolve a single AEC AssociatedParties segment to a canonical party.

    Returns a `SegmentResolution` with the deterministic resolver_status
    and any candidate matches captured in metadata.
    """
    raw = segment
    cleaned = " ".join(segment.split())
    normalized = _normalize_party_name(cleaned)

    # Stage 1: exact-normalized match against party.name / party.short_name.
    exact_matches = directory.find_by_normalized(normalized)
    if len(exact_matches) == 1:
        match = exact_matches[0]
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="resolved_exact",
            canonical_party_id=match.party_id,
            canonical_party_name=match.name,
            canonical_party_short_name=match.short_name,
            matched_via_rule_id=None,
            candidate_party_ids=(match.party_id,),
            notes={
                "stage": "exact_normalized_party_name_or_short_name",
                "resolver_name": RESOLVER_NAME,
                "resolver_version": RESOLVER_VERSION,
            },
        )
    if len(exact_matches) > 1:
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="unresolved_multiple_matches",
            canonical_party_id=None,
            canonical_party_name=None,
            canonical_party_short_name=None,
            matched_via_rule_id=None,
            candidate_party_ids=tuple(sorted(m.party_id for m in exact_matches)),
            notes={
                "stage": "exact_normalized_party_name_or_short_name",
                "ambiguity": "multiple_party_rows_match_normalized_segment",
                "resolver_name": RESOLVER_NAME,
                "resolver_version": RESOLVER_VERSION,
                "candidate_party_names": sorted(
                    {match.name for match in exact_matches}
                ),
            },
        )

    # Stage 2: documented branch alias rules.
    rewritten_name, rule_id = _resolve_via_alias_rules(cleaned)
    if rewritten_name is not None and rule_id is not None:
        rewritten_norm = _normalize_party_name(rewritten_name)
        branch_matches = directory.find_by_normalized(rewritten_norm)
        if len(branch_matches) == 1:
            match = branch_matches[0]
            return SegmentResolution(
                segment=raw,
                normalized_segment=normalized,
                resolver_status="resolved_branch",
                canonical_party_id=match.party_id,
                canonical_party_name=match.name,
                canonical_party_short_name=match.short_name,
                matched_via_rule_id=rule_id,
                candidate_party_ids=(match.party_id,),
                notes={
                    "stage": "branch_alias_rewrite",
                    "resolver_name": RESOLVER_NAME,
                    "resolver_version": RESOLVER_VERSION,
                    "alias_rule_id": rule_id,
                    "rewritten_to_canonical_name": rewritten_name,
                    "attribution_limit": (
                        "Official AEC branch/party relationship resolved to canonical "
                        "app party for display/network context; not proof of personal "
                        "receipt or candidate-specific support."
                    ),
                },
            )
        if len(branch_matches) > 1:
            return SegmentResolution(
                segment=raw,
                normalized_segment=normalized,
                resolver_status="unresolved_multiple_matches",
                canonical_party_id=None,
                canonical_party_name=None,
                canonical_party_short_name=None,
                matched_via_rule_id=rule_id,
                candidate_party_ids=tuple(
                    sorted(m.party_id for m in branch_matches)
                ),
                notes={
                    "stage": "branch_alias_rewrite",
                    "ambiguity": "multiple_party_rows_match_alias_rewrite",
                    "resolver_name": RESOLVER_NAME,
                    "resolver_version": RESOLVER_VERSION,
                    "alias_rule_id": rule_id,
                    "rewritten_to_canonical_name": rewritten_name,
                    "candidate_party_names": sorted(
                        {match.name for match in branch_matches}
                    ),
                },
            )
        # Alias rule matched but the rewritten name does not exist in the party
        # directory. Treat as unresolved-no-match so PR 3 reviewers can decide.
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="unresolved_no_match",
            canonical_party_id=None,
            canonical_party_name=None,
            canonical_party_short_name=None,
            matched_via_rule_id=rule_id,
            candidate_party_ids=(),
            notes={
                "stage": "branch_alias_rewrite",
                "resolver_name": RESOLVER_NAME,
                "resolver_version": RESOLVER_VERSION,
                "alias_rule_id": rule_id,
                "rewritten_to_canonical_name": rewritten_name,
                "ambiguity": "alias_rewrite_target_missing_from_party_directory",
            },
        )

    # Stage 3: parenthetical short-form alias.
    paren_match = _resolve_via_parenthetical_short_name(cleaned, directory)
    if paren_match is not None:
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="resolved_alias",
            canonical_party_id=paren_match.party_id,
            canonical_party_name=paren_match.name,
            canonical_party_short_name=paren_match.short_name,
            matched_via_rule_id="parenthetical_short_name_alias_v1",
            candidate_party_ids=(paren_match.party_id,),
            notes={
                "stage": "parenthetical_short_name_alias",
                "resolver_name": RESOLVER_NAME,
                "resolver_version": RESOLVER_VERSION,
            },
        )

    # Individual-name detection (no party link, by design).
    if _looks_like_individual(cleaned):
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="unresolved_individual_segment",
            canonical_party_id=None,
            canonical_party_name=None,
            canonical_party_short_name=None,
            matched_via_rule_id=None,
            candidate_party_ids=(),
            notes={
                "stage": "individual_name_detector",
                "resolver_name": RESOLVER_NAME,
                "resolver_version": RESOLVER_VERSION,
                "rationale": (
                    "Segment looks like a person's name (e.g. an independent "
                    "candidate). AEC AssociatedParties may include individuals, "
                    "but this resolver only auto-links parties."
                ),
            },
        )

    # Default: no resolution.
    return SegmentResolution(
        segment=raw,
        normalized_segment=normalized,
        resolver_status="unresolved_no_match",
        canonical_party_id=None,
        canonical_party_name=None,
        canonical_party_short_name=None,
        matched_via_rule_id=None,
        candidate_party_ids=(),
        notes={
            "stage": "default_no_match",
            "resolver_name": RESOLVER_NAME,
            "resolver_version": RESOLVER_VERSION,
        },
    )


def resolve_segments(
    segments: Iterable[str], directory: PartyDirectory
) -> list[SegmentResolution]:
    return [resolve_segment(segment, directory) for segment in segments]
