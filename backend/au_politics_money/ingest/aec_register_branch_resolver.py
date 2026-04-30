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
    jurisdiction_id: int | None = None


@dataclass(frozen=True)
class PartyDirectory:
    rows: tuple[PartyDirectoryRow, ...]

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[
            tuple[int, str, str | None]
            | tuple[int, str, str | None, int | None]
        ],
    ) -> "PartyDirectory":
        """Build a directory from `(id, name, short_name)` or
        `(id, name, short_name, jurisdiction_id)` tuples. Older 3-tuple
        callers continue to work (jurisdiction_id is left as None and the
        source-jurisdiction disambiguation step is a no-op for them)."""
        directory_rows = tuple(
            PartyDirectoryRow(
                party_id=int(row[0]),
                name=str(row[1] or ""),
                short_name=str(row[2]) if row[2] else None,
                normalized_name=_normalize_party_name(row[1]),
                normalized_short_name=_normalize_party_name(row[2]),
                jurisdiction_id=(
                    int(row[3])
                    if len(row) >= 4 and row[3] is not None
                    else None
                ),
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
            r"^Liberal Party of Australia\s*\((?:ACT|N\.S\.W\.|NSW|QLD|S\.A\.|SA|"
            r"TAS|VIC|W\.A\.|WA|Victorian|Tasmanian|"
            r"South Australian|Western Australian)"
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
        rule_id="liberal_party_state_division_punctuated_v1",
        pattern=re.compile(
            # AEC also publishes Liberal state divisions in comma- or hyphen-
            # delimited form, e.g. "Liberal Party of Australia, NSW Division",
            # "Liberal Party of Australia - ACT Division",
            # "Liberal Party of Australia - Tasmanian Division".
            r"^Liberal Party of Australia\s*[,\-]\s*(?:ACT|N\.S\.W\.|NSW|QLD|S\.A\.|SA|"
            r"TAS|VIC|W\.A\.|WA|Victorian|Tasmanian|"
            r"South Australian|Western Australian|New South Wales)"
            r"(?:\s+Division)?\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Liberal Party",
        description=(
            "AEC also publishes Liberal state divisions in comma- or hyphen-"
            "delimited form (e.g. 'Liberal Party of Australia, NSW Division'). "
            "Resolved to canonical Liberal Party."
        ),
    ),
    BranchAliasRule(
        rule_id="liberal_party_wa_division_inc_v1",
        pattern=re.compile(
            # AEC publishes the WA Liberals as "Liberal Party (W.A. Division)"
            # or "Liberal Party (W.A. Division) Inc[.]?". The trailing "Inc"
            # is part of the registered company structure but does not change
            # the canonical party identity.
            r"^Liberal Party\s*\(W\.A\.\s*Division\)\s*Inc\.?\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Liberal Party",
        description=(
            "AEC publishes the WA Liberals with an 'Inc' suffix as the "
            "registered association name; resolved to canonical Liberal Party."
        ),
    ),
    BranchAliasRule(
        rule_id="liberal_party_of_australia_long_form_v1",
        pattern=re.compile(
            # The AEC's federal long-form name is "Liberal Party of
            # Australia"; the local DB stores the canonical row as
            # "Liberal Party". Map the long form to the canonical row.
            r"^Liberal Party of Australia\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Liberal Party",
        description=(
            "AEC's federal long-form name 'Liberal Party of Australia' "
            "resolved to canonical local 'Liberal Party' row."
        ),
    ),
    BranchAliasRule(
        rule_id="liberal_national_party_of_queensland_long_form_v1",
        pattern=re.compile(
            # AEC publishes the LNP as "Liberal National Party of Queensland"
            # at the federal register level (the QLD-state designator is
            # part of the registered name, not a separate state branch). The
            # local canonical row uses the shorter "Liberal National Party".
            r"^Liberal National Party of Queensland\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Liberal National Party",
        description=(
            "AEC's 'Liberal National Party of Queensland' is the registered "
            "federal name; resolved to canonical 'Liberal National Party' row."
        ),
    ),
    BranchAliasRule(
        rule_id="country_liberal_party_nt_short_form_v1",
        pattern=re.compile(
            # AEC sometimes appends a "(NT)" suffix to the Country Liberal
            # Party name even though CLP is by definition NT-based.
            r"^Country Liberal Party\s*\(NT\)\s*$",
            re.IGNORECASE,
        ),
        canonical_name="Country Liberal Party",
        description=(
            "AEC publishes the CLP with an explicit '(NT)' suffix even though "
            "CLP is NT-based by definition. Resolved to canonical Country "
            "Liberal Party row."
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
            r"^National Party of Australia\s*\((?:NSW|QLD|VIC|WA|N\.S\.W\.|"
            r"Victorian|Western Australian|New South Wales)\s*(?:Branch|Division)?\)\s*$",
            re.IGNORECASE,
        ),
        canonical_name="National Party",
        description=(
            "AEC state Nationals branches resolved to canonical National Party. "
            "Distinct from LNP and CLP which have separate canonical rows."
        ),
    ),
    BranchAliasRule(
        rule_id="nationals_state_branch_punctuated_v1",
        pattern=re.compile(
            # AEC also publishes Nationals state branches in comma- or
            # hyphen-delimited form, e.g. "National Party of Australia -
            # N.S.W.", "National Party of Australia - Victoria".
            r"^National Party of Australia\s*[,\-]\s*(?:NSW|QLD|VIC|WA|N\.S\.W\.|"
            r"Victoria|Tasmania|South Australia|Western Australia|"
            r"Victorian|Tasmanian|Queensland|New South Wales)"
            r"(?:\s+Branch|\s+Division)?\s*$",
            re.IGNORECASE,
        ),
        canonical_name="National Party",
        description=(
            "AEC also publishes Nationals state branches in comma- or "
            "hyphen-delimited form. Resolved to canonical National Party."
        ),
    ),
    BranchAliasRule(
        rule_id="national_party_of_australia_long_form_v1",
        pattern=re.compile(
            # AEC's federal long-form name is "National Party of Australia";
            # the local DB stores the canonical row as "National Party".
            r"^National Party of Australia\s*$",
            re.IGNORECASE,
        ),
        canonical_name="National Party",
        description=(
            "AEC's federal long-form name 'National Party of Australia' "
            "resolved to canonical local 'National Party' row."
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
    segment: str,
    directory: PartyDirectory,
    *,
    source_jurisdiction_id: int | None = None,
) -> tuple[PartyDirectoryRow | None, bool]:
    """Try to resolve a `<long name> (<SHORT>)` segment by exact match on
    the parenthetical content against `party.short_name`.

    Returns `(matched_row, used_source_jurisdiction_disambiguation)`. The
    second element is True when more than one candidate matched the
    parenthetical short_name and the source-jurisdiction disambiguation
    rule narrowed the candidate set to exactly one row whose
    `jurisdiction_id` matches the source. The rule consults a stable,
    source-attributed integer attribute - it is not fuzzy similarity.
    """
    cleaned = " ".join(segment.split())
    match = _SHORT_FORM_PARENTHETICAL.match(cleaned)
    if not match:
        return None, False
    short_norm = _normalize_party_name(match.group("short"))
    candidates = [
        row
        for row in directory.rows
        if row.normalized_short_name and row.normalized_short_name == short_norm
    ]
    if len(candidates) == 1:
        return candidates[0], False
    if len(candidates) > 1 and source_jurisdiction_id is not None:
        same_juris = [
            row for row in candidates if row.jurisdiction_id == source_jurisdiction_id
        ]
        if len(same_juris) == 1:
            return same_juris[0], True
    return None, False


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


SOURCE_JURISDICTION_DISAMBIGUATION_RULE_ID = (
    "source_jurisdiction_disambiguation_v1"
)


def _disambiguate_by_source_jurisdiction(
    matches: list[PartyDirectoryRow],
    source_jurisdiction_id: int | None,
) -> tuple[list[PartyDirectoryRow], bool]:
    """Filter `matches` to those whose `jurisdiction_id` equals the source
    document's jurisdiction.

    Returns `(filtered_matches, applied)`. Disambiguation is **applied**
    (`applied=True`) only when:

    - a `source_jurisdiction_id` is provided,
    - more than one candidate exists, AND
    - exactly one candidate's `jurisdiction_id` equals the source jurisdiction.

    The rule is fully deterministic — it consults a stable, source-attributed
    integer attribute (the AEC Register is published by a federal authority,
    so its rows are by definition Commonwealth-jurisdiction). It is NOT
    fuzzy similarity. When applied, the resolver records the rule id in the
    resolution notes so the audit trail is preserved.
    """
    if source_jurisdiction_id is None or len(matches) <= 1:
        return matches, False
    same_juris = [
        row for row in matches if row.jurisdiction_id == source_jurisdiction_id
    ]
    if len(same_juris) == 1:
        return same_juris, True
    return matches, False


def resolve_segment(
    segment: str,
    directory: PartyDirectory,
    *,
    source_jurisdiction_id: int | None = None,
) -> SegmentResolution:
    """Resolve a single AEC AssociatedParties segment to a canonical party.

    Returns a `SegmentResolution` with the deterministic resolver_status
    and any candidate matches captured in metadata.

    `source_jurisdiction_id` (optional) lets the loader bias multi-match
    candidates toward the source's own jurisdiction. The AEC Register is a
    federal source, so loaders pass the local Commonwealth jurisdiction id;
    that lets the resolver pick the federal-jurisdiction `Australian Labor
    Party` row over a coexisting state-jurisdiction row of the same name
    when they only differ by jurisdiction.
    """
    raw = segment
    cleaned = " ".join(segment.split())
    normalized = _normalize_party_name(cleaned)

    # Stage 1: exact-normalized match against party.name / party.short_name.
    exact_matches = directory.find_by_normalized(normalized)
    exact_after, exact_disambiguated = _disambiguate_by_source_jurisdiction(
        exact_matches, source_jurisdiction_id
    )
    if len(exact_after) == 1:
        match = exact_after[0]
        notes: dict[str, Any] = {
            "stage": "exact_normalized_party_name_or_short_name",
            "resolver_name": RESOLVER_NAME,
            "resolver_version": RESOLVER_VERSION,
        }
        if exact_disambiguated:
            notes["source_jurisdiction_disambiguation"] = {
                "rule_id": SOURCE_JURISDICTION_DISAMBIGUATION_RULE_ID,
                "source_jurisdiction_id": source_jurisdiction_id,
                "candidate_party_ids_before": sorted(
                    m.party_id for m in exact_matches
                ),
                "candidate_party_names_before": sorted(
                    {m.name for m in exact_matches}
                ),
            }
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="resolved_exact",
            canonical_party_id=match.party_id,
            canonical_party_name=match.name,
            canonical_party_short_name=match.short_name,
            matched_via_rule_id=(
                SOURCE_JURISDICTION_DISAMBIGUATION_RULE_ID
                if exact_disambiguated
                else None
            ),
            candidate_party_ids=(match.party_id,),
            notes=notes,
        )
    if len(exact_after) > 1:
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="unresolved_multiple_matches",
            canonical_party_id=None,
            canonical_party_name=None,
            canonical_party_short_name=None,
            matched_via_rule_id=None,
            candidate_party_ids=tuple(sorted(m.party_id for m in exact_after)),
            notes={
                "stage": "exact_normalized_party_name_or_short_name",
                "ambiguity": "multiple_party_rows_match_normalized_segment",
                "resolver_name": RESOLVER_NAME,
                "resolver_version": RESOLVER_VERSION,
                "candidate_party_names": sorted(
                    {match.name for match in exact_after}
                ),
                "source_jurisdiction_id_used": source_jurisdiction_id,
            },
        )

    # Stage 2: documented branch alias rules.
    rewritten_name, rule_id = _resolve_via_alias_rules(cleaned)
    if rewritten_name is not None and rule_id is not None:
        rewritten_norm = _normalize_party_name(rewritten_name)
        branch_matches_raw = directory.find_by_normalized(rewritten_norm)
        branch_matches, branch_disambiguated = _disambiguate_by_source_jurisdiction(
            branch_matches_raw, source_jurisdiction_id
        )
        if len(branch_matches) == 1:
            match = branch_matches[0]
            notes = {
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
            }
            if branch_disambiguated:
                notes["source_jurisdiction_disambiguation"] = {
                    "rule_id": SOURCE_JURISDICTION_DISAMBIGUATION_RULE_ID,
                    "source_jurisdiction_id": source_jurisdiction_id,
                    "candidate_party_ids_before": sorted(
                        m.party_id for m in branch_matches_raw
                    ),
                    "candidate_party_names_before": sorted(
                        {m.name for m in branch_matches_raw}
                    ),
                }
            return SegmentResolution(
                segment=raw,
                normalized_segment=normalized,
                resolver_status="resolved_branch",
                canonical_party_id=match.party_id,
                canonical_party_name=match.name,
                canonical_party_short_name=match.short_name,
                matched_via_rule_id=rule_id,
                candidate_party_ids=(match.party_id,),
                notes=notes,
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
                    "source_jurisdiction_id_used": source_jurisdiction_id,
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
    paren_match, paren_disambiguated = _resolve_via_parenthetical_short_name(
        cleaned, directory, source_jurisdiction_id=source_jurisdiction_id
    )
    if paren_match is not None:
        notes = {
            "stage": "parenthetical_short_name_alias",
            "resolver_name": RESOLVER_NAME,
            "resolver_version": RESOLVER_VERSION,
        }
        if paren_disambiguated:
            notes["source_jurisdiction_disambiguation"] = {
                "rule_id": SOURCE_JURISDICTION_DISAMBIGUATION_RULE_ID,
                "source_jurisdiction_id": source_jurisdiction_id,
                "stage": "parenthetical_short_name_alias",
            }
        return SegmentResolution(
            segment=raw,
            normalized_segment=normalized,
            resolver_status="resolved_alias",
            canonical_party_id=paren_match.party_id,
            canonical_party_name=paren_match.name,
            canonical_party_short_name=paren_match.short_name,
            matched_via_rule_id="parenthetical_short_name_alias_v1",
            candidate_party_ids=(paren_match.party_id,),
            notes=notes,
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
    segments: Iterable[str],
    directory: PartyDirectory,
    *,
    source_jurisdiction_id: int | None = None,
) -> list[SegmentResolution]:
    return [
        resolve_segment(
            segment, directory, source_jurisdiction_id=source_jurisdiction_id
        )
        for segment in segments
    ]
