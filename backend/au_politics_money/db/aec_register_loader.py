"""Loader for AEC Register of Entities observations + auto-reviewed links.

Implements Batch C PR 2 of the AEC Register ingestion. Reads the JSONL +
summary written by `ingest.aec_register_entities.fetch_register_of_entities`
and:

1. Upserts every register row into `aec_register_of_entities_observation`,
   preserving distinct observations per (client_type, observation_fingerprint).
2. Upserts an `entity` row for each unique (client_type, ClientIdentifier)
   plus an `entity_identifier` row of scheme
   `aec_register_of_entities_client_id`.
3. For `associatedentity` rows only, runs the deterministic branch resolver
   over each `AssociatedParties` segment. Segments that resolve to exactly
   one canonical `party.id` produce reviewed `party_entity_link` rows with
   `method='official'`, `confidence='exact_identifier'`,
   `review_status='reviewed'`, `reviewer='system:aec_register_of_entities'`,
   and an evidence_note recording the AEC client_id, raw segment, and
   resolver rule. Unresolved/ambiguous/individual segments are NOT linked
   and remain visible only via the observation table for review.
4. For `politicalparty` rows, upserts the entity + identifier, attempts an
   exact-match resolution against the local `party` table (recorded in the
   observation), and DOES NOT create `party_entity_link` rows from this
   client_type alone (per dev C-rule).
5. For `significantthirdparty` and `thirdparty` rows, ingests as
   entity + identifier only. No `party_entity_link` is created regardless
   of `AssociatedParties` content.

Direct representative money totals must be invariant across this load:
the loader does not touch `influence_event` or any direct-representative
surface. An integration test guards this.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from au_politics_money.config import PROCESSED_DIR
from au_politics_money.ingest.aec_register_branch_resolver import (
    PartyDirectory,
    SegmentResolution,
    resolve_segments,
)
from au_politics_money.ingest.aec_register_entities import (
    SOURCE_ID_BY_CLIENT_TYPE,
)


LOADER_NAME = "aec_register_of_entities_loader_v1"
LOADER_VERSION = "1"
SYSTEM_REVIEWER = "system:aec_register_of_entities"
ENTITY_IDENTIFIER_SCHEME = "aec_register_of_entities_client_id"
RESOLVED_STATUSES = frozenset(
    {"resolved_exact", "resolved_branch", "resolved_alias"}
)


def latest_jsonl(client_type: str, *, processed_dir: Path = PROCESSED_DIR) -> Path | None:
    target_dir = processed_dir / "aec_register_of_entities" / client_type
    if not target_dir.exists():
        return None
    candidates = sorted(target_dir.glob("*.jsonl"), reverse=True)
    return candidates[0] if candidates else None


def latest_summary(client_type: str, *, processed_dir: Path = PROCESSED_DIR) -> Path | None:
    target_dir = processed_dir / "aec_register_of_entities" / client_type
    if not target_dir.exists():
        return None
    candidates = sorted(target_dir.glob("*.summary.json"), reverse=True)
    return candidates[0] if candidates else None


def _ensure_party_directory(conn) -> PartyDirectory:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, short_name, jurisdiction_id FROM party")
        rows = cur.fetchall()
    return PartyDirectory.from_rows(rows)


def _commonwealth_jurisdiction_id(conn) -> int | None:
    """Return the local id of the Commonwealth (federal) jurisdiction.

    The AEC Register is by definition a federal source, so when its
    `AssociatedParties` segments resolve to multiple `party` rows that only
    differ by jurisdiction (e.g. ALP federal-row + ALP QLD-row), the
    resolver should prefer the row whose `jurisdiction_id` matches this
    federal id. Returns `None` if the jurisdiction is not present, in
    which case the resolver simply skips its source-jurisdiction
    disambiguation step (and continues to fail closed on multi-match).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM jurisdiction
            WHERE level = 'federal'
              AND (code = 'CWLTH' OR LOWER(name) = 'commonwealth')
            ORDER BY id
            LIMIT 1
            """
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_source_document_for_observation(
    conn,
    observation_metadata_path: Path,
    *,
    client_type: str,
) -> int:
    """Use the existing upsert_source_document helper from db.load."""
    from au_politics_money.db.load import upsert_source_document

    return upsert_source_document(conn, observation_metadata_path)


def _upsert_entity(
    conn,
    *,
    client_identifier: str,
    client_name: str,
    client_type: str,
    source_document_id: int,
) -> int:
    from au_politics_money.db.load import normalize_name

    canonical_name = client_name.strip()
    normalized_name = normalize_name(canonical_name)
    entity_type = (
        "political_party"
        if client_type == "politicalparty"
        else "associated_entity"
        if client_type == "associatedentity"
        else "significant_third_party"
        if client_type == "significantthirdparty"
        else "third_party"
    )
    metadata = {
        "aec_register_client_type": client_type,
        "aec_register_client_identifier": client_identifier,
        "aec_register_observation_loader": LOADER_NAME,
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity (
                canonical_name, normalized_name, entity_type, country,
                source_document_id, metadata
            )
            VALUES (%s, %s, %s, 'AU', %s, %s)
            ON CONFLICT (normalized_name, entity_type) DO UPDATE SET
                canonical_name = COALESCE(NULLIF(entity.canonical_name, ''), EXCLUDED.canonical_name),
                source_document_id = COALESCE(entity.source_document_id, EXCLUDED.source_document_id),
                metadata = entity.metadata || EXCLUDED.metadata
            RETURNING id
            """,
            (
                canonical_name,
                normalized_name,
                entity_type,
                source_document_id,
                Jsonb(metadata),
            ),
        )
        entity_id = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO entity_identifier (
                entity_id, identifier_type, identifier_value,
                source_document_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (identifier_type, identifier_value) DO UPDATE SET
                entity_id = EXCLUDED.entity_id,
                source_document_id = COALESCE(
                    entity_identifier.source_document_id,
                    EXCLUDED.source_document_id
                ),
                metadata = entity_identifier.metadata || EXCLUDED.metadata
            """,
            (
                entity_id,
                ENTITY_IDENTIFIER_SCHEME,
                client_identifier,
                source_document_id,
                Jsonb(
                    {
                        "aec_register_client_type": client_type,
                        "loader": LOADER_NAME,
                    }
                ),
            ),
        )
    return entity_id


def _upsert_observation(
    conn,
    record: dict[str, Any],
    *,
    source_document_id: int,
    fetched_at: datetime,
    resolutions: list[SegmentResolution],
    canonical_party_id_for_observation: int | None,
    overall_resolver_status: str,
) -> int:
    resolver_notes = {
        "loader_name": LOADER_NAME,
        "loader_version": LOADER_VERSION,
        "segment_resolutions": [
            {
                "segment": resolution.segment,
                "normalized_segment": resolution.normalized_segment,
                "resolver_status": resolution.resolver_status,
                "canonical_party_id": resolution.canonical_party_id,
                "canonical_party_name": resolution.canonical_party_name,
                "matched_via_rule_id": resolution.matched_via_rule_id,
                "candidate_party_ids": list(resolution.candidate_party_ids),
                "notes": resolution.notes,
            }
            for resolution in resolutions
        ],
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO aec_register_of_entities_observation (
                source_document_id, observation_fingerprint, client_type,
                client_identifier, client_name, view_name, return_id,
                financial_year, return_type, return_status, ammendment_number,
                is_non_registered_branch, associated_parties_raw,
                associated_party_segments, show_in_political_party_register,
                show_in_associated_entity_register,
                show_in_significant_third_party_register,
                show_in_third_party_register, registered_as_associated_entity,
                registered_as_significant_third_party,
                register_of_political_parties_label,
                link_to_register_of_political_parties,
                resolved_canonical_party_id, resolver_status, resolver_notes,
                fetched_at, parser_name, parser_version, raw_row, metadata
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s,
                %s,
                %s, %s,
                %s,
                %s,
                %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (client_type, observation_fingerprint) DO UPDATE SET
                source_document_id = EXCLUDED.source_document_id,
                client_identifier = EXCLUDED.client_identifier,
                client_name = EXCLUDED.client_name,
                view_name = EXCLUDED.view_name,
                return_id = EXCLUDED.return_id,
                financial_year = EXCLUDED.financial_year,
                return_type = EXCLUDED.return_type,
                return_status = EXCLUDED.return_status,
                ammendment_number = EXCLUDED.ammendment_number,
                is_non_registered_branch = EXCLUDED.is_non_registered_branch,
                associated_parties_raw = EXCLUDED.associated_parties_raw,
                associated_party_segments = EXCLUDED.associated_party_segments,
                show_in_political_party_register = EXCLUDED.show_in_political_party_register,
                show_in_associated_entity_register = EXCLUDED.show_in_associated_entity_register,
                show_in_significant_third_party_register = EXCLUDED.show_in_significant_third_party_register,
                show_in_third_party_register = EXCLUDED.show_in_third_party_register,
                registered_as_associated_entity = EXCLUDED.registered_as_associated_entity,
                registered_as_significant_third_party = EXCLUDED.registered_as_significant_third_party,
                register_of_political_parties_label = EXCLUDED.register_of_political_parties_label,
                link_to_register_of_political_parties = EXCLUDED.link_to_register_of_political_parties,
                resolved_canonical_party_id = EXCLUDED.resolved_canonical_party_id,
                resolver_status = EXCLUDED.resolver_status,
                resolver_notes = EXCLUDED.resolver_notes,
                fetched_at = EXCLUDED.fetched_at,
                parser_name = EXCLUDED.parser_name,
                parser_version = EXCLUDED.parser_version,
                raw_row = EXCLUDED.raw_row,
                metadata = aec_register_of_entities_observation.metadata || EXCLUDED.metadata
            RETURNING id
            """,
            (
                source_document_id,
                record["observation_fingerprint"],
                record["client_type"],
                record["client_identifier"],
                record.get("client_name") or "",
                record.get("view_name"),
                record.get("return_id"),
                record.get("financial_year"),
                record.get("return_type"),
                record.get("return_status"),
                record.get("ammendment_number"),
                record.get("is_non_registered_branch"),
                record.get("associated_parties_raw"),
                Jsonb(record.get("associated_party_segments") or []),
                record.get("show_in_political_party_register"),
                record.get("show_in_associated_entity_register"),
                record.get("show_in_significant_third_party_register"),
                record.get("show_in_third_party_register"),
                record.get("registered_as_associated_entity"),
                record.get("registered_as_significant_third_party"),
                record.get("register_of_political_parties_label"),
                record.get("link_to_register_of_political_parties"),
                canonical_party_id_for_observation,
                overall_resolver_status,
                Jsonb(resolver_notes),
                fetched_at,
                record["parser_name"],
                record["parser_version"],
                Jsonb(record.get("raw_row") or {}),
                Jsonb({"loader_name": LOADER_NAME, "loader_version": LOADER_VERSION}),
            ),
        )
        return int(cur.fetchone()[0])


def _create_reviewed_party_entity_link(
    conn,
    *,
    party_id: int,
    entity_id: int,
    resolution: SegmentResolution,
    client_identifier: str,
    source_document_id: int,
    reviewed_at: datetime,
) -> bool:
    """Insert a reviewed associated_entity link. Returns True if inserted, False if a stronger row exists."""
    evidence_note = (
        f"AEC Register of Entities row {client_identifier} explicitly names "
        f"{resolution.segment!r}; resolved to canonical party "
        f"{resolution.canonical_party_name!r} via "
        f"{resolution.notes.get('stage')!s}"
        + (
            f" using rule {resolution.matched_via_rule_id}"
            if resolution.matched_via_rule_id
            else ""
        )
        + ". Official AEC branch/party relationship resolved to canonical app "
        + "party for display/network context; not proof of personal receipt or "
        + "candidate-specific support."
    )
    metadata = {
        "loader_name": LOADER_NAME,
        "loader_version": LOADER_VERSION,
        "raw_aec_segment": resolution.segment,
        "normalized_segment": resolution.normalized_segment,
        "resolver_status": resolution.resolver_status,
        "matched_via_rule_id": resolution.matched_via_rule_id,
        "aec_register_client_identifier": client_identifier,
        "resolver_notes": resolution.notes,
        "attribution_limit": (
            "Official AEC branch/party relationship resolved to canonical app "
            "party for display/network context; not proof of personal receipt or "
            "candidate-specific support."
        ),
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO party_entity_link (
                party_id, entity_id, link_type, method, confidence,
                review_status, evidence_note, reviewer, reviewed_at,
                source_document_id, metadata
            )
            VALUES (
                %s, %s, 'associated_entity', 'official', 'exact_identifier',
                'reviewed', %s, %s, %s, %s, %s
            )
            ON CONFLICT (party_id, entity_id, link_type)
            DO UPDATE SET
                method = 'official',
                confidence = 'exact_identifier',
                review_status = 'reviewed',
                evidence_note = EXCLUDED.evidence_note,
                reviewer = EXCLUDED.reviewer,
                reviewed_at = EXCLUDED.reviewed_at,
                source_document_id = EXCLUDED.source_document_id,
                metadata = party_entity_link.metadata || EXCLUDED.metadata
            WHERE party_entity_link.review_status <> 'rejected'
            RETURNING id
            """,
            (
                party_id,
                entity_id,
                evidence_note,
                SYSTEM_REVIEWER,
                reviewed_at,
                source_document_id,
                Jsonb(metadata),
            ),
        )
        row = cur.fetchone()
        return row is not None


def _select_observation_resolver_status(resolutions: list[SegmentResolution]) -> str:
    """Pick a representative resolver_status for the observation row.

    If at least one segment resolved, mark the observation 'resolved_exact'
    when the highest-confidence stage was Stage 1, else 'resolved_branch' or
    'resolved_alias' as appropriate. If no segments resolved, return the
    most informative unresolved reason.
    """
    statuses = [resolution.resolver_status for resolution in resolutions]
    if not statuses:
        return "not_applicable"
    if "resolved_exact" in statuses:
        return "resolved_exact"
    if "resolved_branch" in statuses:
        return "resolved_branch"
    if "resolved_alias" in statuses:
        return "resolved_alias"
    if "unresolved_multiple_matches" in statuses:
        return "unresolved_multiple_matches"
    if "unresolved_individual_segment" in statuses and all(
        status == "unresolved_individual_segment" for status in statuses
    ):
        return "unresolved_individual_segment"
    return "unresolved_no_match"


def _representative_canonical_party_id(
    resolutions: list[SegmentResolution],
) -> int | None:
    """Pick one canonical_party_id to record on the observation row.

    For multi-segment associatedentity rows, the observation table only
    stores a single resolved_canonical_party_id (the per-link records are
    in `party_entity_link` and `resolver_notes`). We pick the first
    resolved match, which by convention corresponds to the first segment.
    """
    for resolution in resolutions:
        if resolution.resolver_status in RESOLVED_STATUSES:
            return resolution.canonical_party_id
    return None


def load_aec_register_of_entities(
    conn,
    *,
    client_type: str,
    jsonl_path: Path | None = None,
    summary_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
    party_directory_factory: Callable[[Any], PartyDirectory] = _ensure_party_directory,
    now_factory: Callable[[], datetime] = _now,
) -> dict[str, Any]:
    """Load one client_type's processed JSONL into the database.

    Returns counts of observations upserted, entities upserted, links
    auto-created, and per-resolver-status tallies.
    """
    if client_type not in SOURCE_ID_BY_CLIENT_TYPE:
        raise ValueError(
            f"Unsupported AEC Register client_type: {client_type!r}"
        )
    if jsonl_path is None:
        jsonl_path = latest_jsonl(client_type, processed_dir=processed_dir)
    if summary_path is None:
        summary_path = latest_summary(client_type, processed_dir=processed_dir)
    if jsonl_path is None or summary_path is None:
        raise FileNotFoundError(
            f"No processed AEC Register artefacts found for client_type "
            f"{client_type!r} under {processed_dir / 'aec_register_of_entities' / client_type}; "
            "run fetch-aec-register-of-entities first."
        )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    fetched_at = datetime.strptime(
        summary["generated_at"], "%Y%m%dT%H%M%SZ"
    ).replace(tzinfo=timezone.utc)

    party_directory = party_directory_factory(conn)
    source_jurisdiction_id = _commonwealth_jurisdiction_id(conn)
    reviewed_at = now_factory()
    resolver_status_counts: dict[str, int] = {}
    observations_upserted = 0
    entities_upserted = 0
    links_created = 0
    individual_segments_skipped = 0
    multi_match_segments_skipped = 0
    no_match_segments_skipped = 0

    with jsonl_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)

            source_metadata_path = Path(record["source_metadata_path"])
            source_document_id = _upsert_source_document_for_observation(
                conn,
                source_metadata_path,
                client_type=record["client_type"],
            )

            entity_id = _upsert_entity(
                conn,
                client_identifier=record["client_identifier"],
                client_name=record.get("client_name") or "",
                client_type=record["client_type"],
                source_document_id=source_document_id,
            )
            entities_upserted += 1

            segments = list(record.get("associated_party_segments") or [])
            resolutions: list[SegmentResolution] = []
            if record["client_type"] == "associatedentity" and segments:
                resolutions = resolve_segments(
                    segments,
                    party_directory,
                    source_jurisdiction_id=source_jurisdiction_id,
                )
            elif record["client_type"] == "politicalparty":
                # Resolve the entity's own ClientName against the party
                # directory just to record the match, but do NOT auto-link
                # via party_entity_link.
                resolutions = resolve_segments(
                    [record.get("client_name") or ""],
                    party_directory,
                    source_jurisdiction_id=source_jurisdiction_id,
                )

            canonical_party_id_for_observation = _representative_canonical_party_id(
                resolutions
            )
            overall_resolver_status = (
                _select_observation_resolver_status(resolutions)
                if resolutions
                else "not_applicable"
            )

            _upsert_observation(
                conn,
                record,
                source_document_id=source_document_id,
                fetched_at=fetched_at,
                resolutions=resolutions,
                canonical_party_id_for_observation=canonical_party_id_for_observation,
                overall_resolver_status=overall_resolver_status,
            )
            observations_upserted += 1
            resolver_status_counts[overall_resolver_status] = (
                resolver_status_counts.get(overall_resolver_status, 0) + 1
            )

            if record["client_type"] != "associatedentity":
                # politicalparty / significantthirdparty / thirdparty: no
                # auto party_entity_link creation per the C-rule.
                continue

            for resolution in resolutions:
                if resolution.resolver_status in RESOLVED_STATUSES:
                    if resolution.canonical_party_id is None:
                        continue
                    if _create_reviewed_party_entity_link(
                        conn,
                        party_id=resolution.canonical_party_id,
                        entity_id=entity_id,
                        resolution=resolution,
                        client_identifier=record["client_identifier"],
                        source_document_id=source_document_id,
                        reviewed_at=reviewed_at,
                    ):
                        links_created += 1
                elif resolution.resolver_status == "unresolved_individual_segment":
                    individual_segments_skipped += 1
                elif resolution.resolver_status == "unresolved_multiple_matches":
                    multi_match_segments_skipped += 1
                else:
                    no_match_segments_skipped += 1

    conn.commit()

    return {
        "client_type": client_type,
        "jsonl_path": str(jsonl_path.resolve()),
        "summary_path": str(summary_path.resolve()),
        "observations_upserted": observations_upserted,
        "entities_upserted": entities_upserted,
        "reviewed_party_entity_links_upserted": links_created,
        "individual_segments_skipped": individual_segments_skipped,
        "multi_match_segments_skipped": multi_match_segments_skipped,
        "no_match_segments_skipped": no_match_segments_skipped,
        "resolver_status_counts": resolver_status_counts,
        "loader_name": LOADER_NAME,
        "loader_version": LOADER_VERSION,
        "reviewer": SYSTEM_REVIEWER,
    }
