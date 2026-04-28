from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from au_politics_money.config import AUDIT_DIR
from au_politics_money.ingest.entity_classification import PUBLIC_INTEREST_SECTORS


REVIEW_DECISIONS = {"accept", "reject", "revise", "needs_more_evidence", "defer"}
REVIEW_SUBJECT_TYPES = {
    "entity_match_candidate",
    "influence_event",
    "entity_industry_classification",
    "sector_policy_topic_link",
    "source_document",
    "other",
}
GENERATED_REVIEW_SUBJECT_TYPES = {
    "entity_match_candidate",
    "entity_industry_classification",
    "influence_event",
    "sector_policy_topic_link",
}
PUBLIC_INTEREST_SECTOR_CODES = {sector["code"] for sector in PUBLIC_INTEREST_SECTORS}
SECTOR_POLICY_RELATIONSHIPS = {
    "direct_material_interest",
    "indirect_material_interest",
    "general_interest",
    "uncertain",
}
SECTOR_POLICY_LINK_METHODS = {"manual", "rule_based", "model_assisted", "third_party_civic"}


class ReviewImportError(ValueError):
    pass


@dataclass(frozen=True)
class ReviewQueue:
    name: str
    description: str
    sql: str
    subject_type: str


OFFICIAL_MATCH_CANDIDATES_SQL = """
SELECT
    'entity_match_candidate' AS review_subject_type,
    emc.id AS review_subject_id,
    (
        'entity_match_candidate:' || entity.normalized_name || ':' ||
        entity.entity_type || ':' || observation.stable_key || ':' || emc.match_method
    ) AS subject_external_key,
    md5(
        concat_ws(
            '|',
            entity.normalized_name,
            entity.entity_type,
            observation.stable_key,
            emc.match_method,
            observation.display_name,
            observation.identifiers::text,
            observation.aliases::text,
            observation.public_sector
        )
    ) AS review_subject_fingerprint,
    emc.status AS review_status,
    emc.match_method,
    emc.confidence,
    emc.score,
    emc.evidence_note AS candidate_evidence_note,
    entity.id AS entity_id,
    entity.canonical_name AS entity_name,
    entity.entity_type,
    entity.normalized_name AS entity_normalized_name,
    observation.id AS observation_id,
    observation.source_id,
    observation.source_record_type,
    observation.display_name AS official_display_name,
    observation.external_id AS official_external_id,
    observation.entity_type AS official_entity_type,
    observation.public_sector AS official_public_sector,
    observation.identifiers AS official_identifiers,
    observation.aliases AS official_aliases,
    observation.evidence_note AS official_evidence_note,
    source_document.url AS source_url,
    source_document.final_url,
    source_document.storage_path AS source_storage_path
FROM entity_match_candidate emc
JOIN entity ON entity.id = emc.entity_id
JOIN official_identifier_observation observation
  ON observation.id = emc.observation_id
LEFT JOIN source_document ON source_document.id = observation.source_document_id
WHERE emc.status = 'needs_review'
  AND NOT EXISTS (
      SELECT 1
      FROM manual_review_decision decision
      WHERE decision.subject_type = 'entity_match_candidate'
        AND decision.subject_external_key = (
            'entity_match_candidate:' || entity.normalized_name || ':' ||
            entity.entity_type || ':' || observation.stable_key || ':' || emc.match_method
        )
        AND decision.decision IN ('accept', 'reject', 'revise')
        AND (
            decision.metadata->>'expected_subject_fingerprint' IS NULL
            OR decision.metadata->>'expected_subject_fingerprint' = md5(
                concat_ws(
                    '|',
                    entity.normalized_name,
                    entity.entity_type,
                    observation.stable_key,
                    emc.match_method,
                    observation.display_name,
                    observation.identifiers::text,
                    observation.aliases::text,
                    observation.public_sector
                )
            )
        )
  )
ORDER BY emc.id
"""


BENEFIT_EVENTS_SQL = """
SELECT
    'influence_event' AS review_subject_type,
    influence_event.id AS review_subject_id,
    influence_event.external_key AS subject_external_key,
    md5(
        concat_ws(
            '|',
            influence_event.external_key,
            influence_event.event_type,
            COALESCE(influence_event.event_subtype, ''),
            influence_event.description,
            COALESCE(influence_event.source_raw_name, ''),
            COALESCE(influence_event.amount::text, ''),
            influence_event.amount_status,
            influence_event.missing_data_flags::text
        )
    ) AS review_subject_fingerprint,
    influence_event.review_status,
    influence_event.event_type,
    influence_event.event_subtype,
    influence_event.description,
    influence_event.source_raw_name,
    source_entity.canonical_name AS source_entity_name,
    recipient_person.display_name AS recipient_person_name,
    influence_event.amount,
    influence_event.currency,
    influence_event.amount_status,
    influence_event.event_date,
    influence_event.date_reported,
    influence_event.chamber,
    influence_event.disclosure_system,
    influence_event.evidence_status,
    influence_event.extraction_method,
    influence_event.missing_data_flags,
    influence_event.source_ref,
    source_document.url AS source_url,
    source_document.final_url,
    source_document.storage_path AS source_storage_path
FROM influence_event
LEFT JOIN entity source_entity ON source_entity.id = influence_event.source_entity_id
LEFT JOIN person recipient_person ON recipient_person.id = influence_event.recipient_person_id
JOIN source_document ON source_document.id = influence_event.source_document_id
WHERE influence_event.event_family = 'benefit'
  AND COALESCE(influence_event.metadata->>'manual_review_status', '') NOT IN (
      'accepted',
      'rejected',
      'revised'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM manual_review_decision decision
      WHERE decision.subject_type = 'influence_event'
        AND decision.subject_external_key = influence_event.external_key
        AND decision.decision IN ('accept', 'reject', 'revise')
        AND (
            decision.metadata->>'expected_subject_fingerprint' IS NULL
            OR decision.metadata->>'expected_subject_fingerprint' = md5(
                concat_ws(
                    '|',
                    influence_event.external_key,
                    influence_event.event_type,
                    COALESCE(influence_event.event_subtype, ''),
                    influence_event.description,
                    COALESCE(influence_event.source_raw_name, ''),
                    COALESCE(influence_event.amount::text, ''),
                    influence_event.amount_status,
                    influence_event.missing_data_flags::text
                )
            )
        )
  )
  AND (
      influence_event.review_status = 'needs_review'
      OR influence_event.missing_data_flags <> '[]'::jsonb
  )
ORDER BY
    CASE WHEN influence_event.review_status = 'needs_review' THEN 0 ELSE 1 END,
    jsonb_array_length(influence_event.missing_data_flags) DESC,
    influence_event.id
"""


ENTITY_CLASSIFICATIONS_SQL = """
SELECT
    'entity_industry_classification' AS review_subject_type,
    entity_industry_classification.id AS review_subject_id,
    (
        'entity_industry_classification:' ||
        entity.normalized_name || ':' ||
        entity.entity_type || ':' ||
        COALESCE(entity_industry_classification.metadata->>'classifier_name',
                 entity_industry_classification.method) || ':' ||
        entity_industry_classification.method || ':' ||
        entity_industry_classification.public_sector || ':' ||
        COALESCE(industry_code.scheme, '') || ':' ||
        COALESCE(industry_code.code, '')
    ) AS subject_external_key,
    md5(
        concat_ws(
            '|',
            entity.normalized_name,
            entity.entity_type,
            COALESCE(entity_industry_classification.metadata->>'classifier_name',
                     entity_industry_classification.method),
            entity_industry_classification.method,
            entity_industry_classification.public_sector,
            COALESCE(industry_code.scheme, ''),
            COALESCE(industry_code.code, ''),
            entity_industry_classification.confidence,
            COALESCE(entity_industry_classification.evidence_note, '')
        )
    ) AS review_subject_fingerprint,
    entity.id AS entity_id,
    entity.canonical_name AS entity_name,
    entity.entity_type,
    industry_code.scheme AS industry_scheme,
    industry_code.code AS industry_code,
    industry_code.label AS industry_label,
    entity_industry_classification.public_sector,
    entity_industry_classification.method,
    entity_industry_classification.confidence,
    entity_industry_classification.evidence_note,
    entity_industry_classification.metadata,
    source_document.url AS source_url,
    source_document.final_url,
    source_document.storage_path AS source_storage_path
FROM entity_industry_classification
JOIN entity ON entity.id = entity_industry_classification.entity_id
LEFT JOIN industry_code ON industry_code.id = entity_industry_classification.industry_code_id
LEFT JOIN source_document ON source_document.id = entity_industry_classification.source_document_id
WHERE entity_industry_classification.method IN ('rule_based', 'model_assisted')
  AND COALESCE(
      entity_industry_classification.metadata->>'manual_review_status',
      ''
  ) NOT IN ('accepted', 'revised', 'rejected')
  AND NOT EXISTS (
      SELECT 1
      FROM manual_review_decision decision
      WHERE decision.subject_type = 'entity_industry_classification'
        AND decision.subject_external_key = (
            'entity_industry_classification:' ||
            entity.normalized_name || ':' ||
            entity.entity_type || ':' ||
            COALESCE(entity_industry_classification.metadata->>'classifier_name',
                     entity_industry_classification.method) || ':' ||
            entity_industry_classification.method || ':' ||
            entity_industry_classification.public_sector || ':' ||
            COALESCE(industry_code.scheme, '') || ':' ||
            COALESCE(industry_code.code, '')
        )
        AND decision.decision IN ('accept', 'reject', 'revise')
        AND (
            decision.metadata->>'expected_subject_fingerprint' IS NULL
            OR decision.metadata->>'expected_subject_fingerprint' = md5(
                concat_ws(
                    '|',
                    entity.normalized_name,
                    entity.entity_type,
                    COALESCE(entity_industry_classification.metadata->>'classifier_name',
                             entity_industry_classification.method),
                    entity_industry_classification.method,
                    entity_industry_classification.public_sector,
                    COALESCE(industry_code.scheme, ''),
                    COALESCE(industry_code.code, ''),
                    entity_industry_classification.confidence,
                    COALESCE(entity_industry_classification.evidence_note, '')
                )
            )
        )
  )
  AND (
      entity_industry_classification.confidence IN ('fuzzy_low', 'unresolved')
      OR entity_industry_classification.metadata->>'review_recommended' = 'true'
  )
ORDER BY
    CASE entity_industry_classification.confidence
        WHEN 'unresolved' THEN 0
        WHEN 'fuzzy_low' THEN 1
        ELSE 2
    END,
    entity.canonical_name,
    entity_industry_classification.id
"""


SECTOR_POLICY_LINKS_SQL = """
SELECT
    'sector_policy_topic_link' AS review_subject_type,
    link.id AS review_subject_id,
    (
        'sector_policy_topic_link:' || link.public_sector || ':' ||
        policy_topic.slug || ':' || link.relationship || ':' || link.method
    ) AS subject_external_key,
    md5(
        concat_ws(
            '|',
            link.public_sector,
            policy_topic.slug,
            policy_topic.label,
            COALESCE(policy_topic.description, ''),
            COALESCE(policy_topic.metadata->>'source', ''),
            COALESCE(policy_topic.metadata->>'source_evidence_class', ''),
            COALESCE(policy_topic.metadata->>'they_vote_for_you_policy_id', ''),
            COALESCE(policy_topic.metadata->>'provisional', ''),
            COALESCE(policy_topic.metadata->>'last_edited_at', ''),
            link.relationship,
            link.method,
            to_char(link.confidence, 'FM0.000'),
            link.evidence_note
        )
    ) AS review_subject_fingerprint,
    link.review_status,
    link.public_sector,
    policy_topic.id AS topic_id,
    policy_topic.slug AS topic_slug,
    policy_topic.label AS topic_label,
    policy_topic.description AS topic_description,
    policy_topic.metadata->>'source' AS topic_source,
    policy_topic.metadata->>'source_evidence_class' AS topic_source_evidence_class,
    policy_topic.metadata->>'they_vote_for_you_policy_id' AS topic_external_id,
    policy_topic.metadata->>'provisional' AS topic_provisional,
    policy_topic.metadata->>'last_edited_at' AS topic_last_edited_at,
    link.relationship,
    link.method,
    link.confidence,
    link.evidence_note,
    link.reviewer,
    link.reviewed_at,
    link.metadata
FROM sector_policy_topic_link link
JOIN policy_topic ON policy_topic.id = link.topic_id
WHERE link.review_status = 'needs_review'
  AND NOT EXISTS (
      SELECT 1
      FROM manual_review_decision decision
      WHERE decision.subject_type = 'sector_policy_topic_link'
        AND decision.subject_external_key = (
            'sector_policy_topic_link:' || link.public_sector || ':' ||
            policy_topic.slug || ':' || link.relationship || ':' || link.method
        )
        AND decision.decision IN ('accept', 'reject', 'revise')
        AND (
            decision.metadata->>'expected_subject_fingerprint' IS NULL
            OR decision.metadata->>'expected_subject_fingerprint' = md5(
                concat_ws(
                    '|',
                    link.public_sector,
                    policy_topic.slug,
                    policy_topic.label,
                    COALESCE(policy_topic.description, ''),
                    COALESCE(policy_topic.metadata->>'source', ''),
                    COALESCE(policy_topic.metadata->>'source_evidence_class', ''),
                    COALESCE(policy_topic.metadata->>'they_vote_for_you_policy_id', ''),
                    COALESCE(policy_topic.metadata->>'provisional', ''),
                    COALESCE(policy_topic.metadata->>'last_edited_at', ''),
                    link.relationship,
                    link.method,
                    to_char(link.confidence, 'FM0.000'),
                    link.evidence_note
                )
            )
        )
  )
ORDER BY link.public_sector, policy_topic.slug, link.relationship, link.method
"""


REVIEW_QUEUES = {
    "official-match-candidates": ReviewQueue(
        name="official-match-candidates",
        description="Name-only official identifier match candidates requiring review.",
        sql=OFFICIAL_MATCH_CANDIDATES_SQL,
        subject_type="entity_match_candidate",
    ),
    "benefit-events": ReviewQueue(
        name="benefit-events",
        description="Disclosed benefit events with extraction or missing-data review flags.",
        sql=BENEFIT_EVENTS_SQL,
        subject_type="influence_event",
    ),
    "entity-classifications": ReviewQueue(
        name="entity-classifications",
        description="Inferred entity-sector classifications recommended for review.",
        sql=ENTITY_CLASSIFICATIONS_SQL,
        subject_type="entity_industry_classification",
    ),
    "sector-policy-links": ReviewQueue(
        name="sector-policy-links",
        description="Sector-to-policy topic links requiring review before vote/influence context display.",
        sql=SECTOR_POLICY_LINKS_SQL,
        subject_type="sector_policy_topic_link",
    ),
}


def review_queue_names() -> list[str]:
    return sorted(REVIEW_QUEUES)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def row_to_dict(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    return {column: json_safe(value) for column, value in zip(columns, row, strict=True)}


def as_jsonb(value: Any):
    try:
        from psycopg.types.json import Jsonb
    except ImportError as exc:  # pragma: no cover - exercised only in incomplete envs.
        raise RuntimeError("Install database dependencies with `pip install -e '.[dev]'`.") from exc
    return Jsonb(value)


def parse_reviewed_at(value: Any) -> datetime:
    if value in ("", None):
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    cleaned = str(value).strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewImportError(f"Invalid reviewed_at value: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=json_safe)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    canonical_subject_id = None if decision.get("subject_external_key") else decision.get("subject_id")
    return {
        "subject_type": decision["subject_type"],
        "subject_id": canonical_subject_id,
        "subject_external_key": decision.get("subject_external_key"),
        "decision": decision["decision"],
        "reviewer": decision["reviewer"],
        "evidence_note": decision["evidence_note"],
        "proposed_changes": decision.get("proposed_changes") or {},
        "supporting_sources": decision.get("supporting_sources") or [],
        "expected_subject_fingerprint": decision.get("expected_subject_fingerprint"),
    }


def decision_payload_sha256(decision: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(decision_payload(decision)).encode("utf-8")).hexdigest()


def decision_key_for(record: dict[str, Any]) -> str:
    if record.get("decision_key"):
        return str(record["decision_key"]).strip()
    canonical_subject_id = None if record.get("subject_external_key") else record.get("subject_id")
    key_material = {
        "subject_type": record["subject_type"],
        "subject_id": canonical_subject_id,
        "subject_external_key": record.get("subject_external_key"),
        "expected_subject_fingerprint": record.get("expected_subject_fingerprint"),
        "decision": record["decision"],
        "reviewer": record["reviewer"],
        "evidence_note": record["evidence_note"],
        "proposed_changes": record.get("proposed_changes") or {},
        "supporting_sources": record.get("supporting_sources") or [],
    }
    digest = hashlib.sha256(_canonical_json(key_material).encode("utf-8")).hexdigest()
    return f"review:{digest}"


def _coerce_subject_id(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ReviewImportError(f"subject_id must be an integer when supplied: {value!r}") from exc


def normalize_review_decision(record: dict[str, Any], *, line_number: int) -> dict[str, Any]:
    subject_type = record.get("subject_type") or record.get("review_subject_type")
    if subject_type not in REVIEW_SUBJECT_TYPES:
        raise ReviewImportError(
            f"Line {line_number}: invalid subject_type {subject_type!r}; "
            f"expected one of {sorted(REVIEW_SUBJECT_TYPES)}"
        )

    subject_id = _coerce_subject_id(record.get("subject_id") or record.get("review_subject_id"))
    subject_external_key = record.get("subject_external_key") or record.get("external_key")
    if subject_external_key is not None:
        subject_external_key = str(subject_external_key).strip() or None
    if subject_type in GENERATED_REVIEW_SUBJECT_TYPES and subject_external_key is None:
        raise ReviewImportError(
            f"Line {line_number}: {subject_type} decisions require subject_external_key "
            "because numeric row IDs can change after reloads."
        )
    if subject_id is None and subject_external_key is None:
        raise ReviewImportError(
            f"Line {line_number}: subject_id or subject_external_key is required."
        )

    decision = str(record.get("decision") or "").strip().lower()
    if decision not in REVIEW_DECISIONS:
        raise ReviewImportError(
            f"Line {line_number}: invalid decision {decision!r}; "
            f"expected one of {sorted(REVIEW_DECISIONS)}"
        )

    reviewer = str(record.get("reviewer") or "").strip()
    if not reviewer:
        raise ReviewImportError(f"Line {line_number}: reviewer is required.")

    evidence_note = str(record.get("evidence_note") or record.get("review_note") or "").strip()
    if not evidence_note:
        raise ReviewImportError(f"Line {line_number}: evidence_note is required.")

    proposed_changes = record.get("proposed_changes") or {}
    if not isinstance(proposed_changes, dict):
        raise ReviewImportError(f"Line {line_number}: proposed_changes must be an object.")

    supporting_sources = record.get("supporting_sources") or []
    if not isinstance(supporting_sources, list):
        raise ReviewImportError(f"Line {line_number}: supporting_sources must be a list.")

    review_subject_snapshot = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "decision",
            "decision_key",
            "evidence_note",
            "proposed_changes",
            "review_note",
            "reviewer",
            "reviewed_at",
            "supporting_sources",
        }
    }
    normalized = {
        "decision_key": str(record.get("decision_key") or "").strip(),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "subject_external_key": subject_external_key,
        "expected_subject_fingerprint": record.get("review_subject_fingerprint"),
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": parse_reviewed_at(record.get("reviewed_at")),
        "evidence_note": evidence_note,
        "proposed_changes": proposed_changes,
        "supporting_sources": supporting_sources,
        "metadata": {
            "line_number": line_number,
            "review_queue": record.get("review_queue"),
            "review_subject_type": record.get("review_subject_type"),
            "review_subject_id": record.get("review_subject_id"),
            "expected_subject_fingerprint": record.get("review_subject_fingerprint"),
            "review_subject_snapshot": review_subject_snapshot,
            "source_review_record_keys": sorted(record.keys()),
        },
    }
    normalized["decision_key"] = decision_key_for(normalized)
    normalized["payload_sha256"] = decision_payload_sha256(normalized)
    return normalized


def load_review_decision_file(path: Path) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReviewImportError(f"Line {line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ReviewImportError(f"Line {line_number}: each record must be a JSON object.")
            decisions.append(normalize_review_decision(record, line_number=line_number))
    return decisions


def _public_sector_code_ids(conn) -> dict[str, int]:
    code_ids: dict[str, int] = {}
    with conn.cursor() as cur:
        for sector in PUBLIC_INTEREST_SECTORS:
            cur.execute(
                """
                INSERT INTO industry_code (scheme, code, label)
                VALUES (%s, %s, %s)
                ON CONFLICT (scheme, code) DO UPDATE SET label = EXCLUDED.label
                RETURNING id
                """,
                ("public_interest_sector", sector["code"], sector["label"]),
            )
            code_ids[sector["code"]] = int(cur.fetchone()[0])
    return code_ids


def _insert_manual_review_decision(conn, decision: dict[str, Any], source_path: Path) -> tuple[int, bool]:
    metadata = {
        **decision["metadata"],
        "import_file": str(source_path),
        "canonical_payload_sha256": decision["payload_sha256"],
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO manual_review_decision (
                decision_key, subject_type, subject_id, subject_external_key,
                decision, reviewer, reviewed_at, evidence_note, proposed_changes,
                supporting_sources, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (decision_key) DO NOTHING
            RETURNING id
            """,
            (
                decision["decision_key"],
                decision["subject_type"],
                decision["subject_id"],
                decision["subject_external_key"],
                decision["decision"],
                decision["reviewer"],
                decision["reviewed_at"],
                decision["evidence_note"],
                as_jsonb(decision["proposed_changes"]),
                as_jsonb(decision["supporting_sources"]),
                as_jsonb(metadata),
            ),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row[0]), True
        cur.execute(
            "SELECT id, metadata->>'canonical_payload_sha256' FROM manual_review_decision WHERE decision_key = %s",
            (decision["decision_key"],),
        )
        existing_id, existing_payload_sha256 = cur.fetchone()
        if existing_payload_sha256 and existing_payload_sha256 != decision["payload_sha256"]:
            raise ReviewImportError(
                f"Decision key {decision['decision_key']} already exists with a different payload."
            )
        return int(existing_id), False


def _review_metadata(decision_id: int, decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "manual_review_status": {
            "accept": "accepted",
            "reject": "rejected",
            "revise": "revised",
            "needs_more_evidence": "needs_more_evidence",
            "defer": "deferred",
        }[decision["decision"]],
        "last_manual_review_decision_id": decision_id,
        "last_manual_review_decision_key": decision["decision_key"],
        "last_manual_review_decision": decision["decision"],
        "last_manual_review_reviewer": decision["reviewer"],
        "last_manual_reviewed_at": decision["reviewed_at"].isoformat(),
    }


def _validate_subject_fingerprint(
    *,
    decision: dict[str, Any],
    current_fingerprint: str | None,
) -> None:
    expected = decision.get("expected_subject_fingerprint")
    if not expected:
        return
    if expected != current_fingerprint:
        raise ReviewImportError(
            f"Decision {decision['decision_key']}: subject fingerprint changed "
            f"from {expected!r} to {current_fingerprint!r}; re-export and review the row."
        )


def _format_sector_link_confidence(value: Any) -> str:
    try:
        confidence = Decimal(str(value))
    except Exception as exc:
        raise ReviewImportError(f"sector_policy_topic_link confidence is invalid: {value!r}") from exc
    if confidence < Decimal("0") or confidence > Decimal("1"):
        raise ReviewImportError(
            f"sector_policy_topic_link confidence must be between 0 and 1: {value!r}"
        )
    return f"{confidence.quantize(Decimal('0.001')):.3f}"


def _sector_policy_link_external_key(
    *,
    public_sector: str,
    topic_slug: str,
    relationship: str,
    method: str,
) -> str:
    return f"sector_policy_topic_link:{public_sector}:{topic_slug}:{relationship}:{method}"


def _sector_policy_link_fingerprint(link: dict[str, Any]) -> str:
    parts = [
        str(link["public_sector"]),
        str(link["topic_slug"]),
        str(link["topic_label"]),
        str(link.get("topic_description") or ""),
        str(link.get("topic_source") or ""),
        str(link.get("topic_source_evidence_class") or ""),
        str(link.get("topic_external_id") or ""),
        str(link.get("topic_provisional") or ""),
        str(link.get("topic_last_edited_at") or ""),
        str(link["relationship"]),
        str(link["method"]),
        _format_sector_link_confidence(link["confidence"]),
        str(link["evidence_note"]),
    ]
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def _existing_sector_policy_link(conn, decision: dict[str, Any], *, for_update: bool = False):
    if decision["subject_external_key"]:
        where_clause = """
            (
                'sector_policy_topic_link:' || link.public_sector || ':' ||
                policy_topic.slug || ':' || link.relationship || ':' || link.method
            ) = %s
        """
        where_value = decision["subject_external_key"]
    elif decision["subject_id"] is not None:
        where_clause = "link.id = %s"
        where_value = decision["subject_id"]
    else:
        raise ReviewImportError("sector_policy_topic_link decisions require a subject key.")
    lock_clause = "FOR UPDATE OF link" if for_update else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                link.id, link.public_sector, link.topic_id,
                policy_topic.slug, policy_topic.label, policy_topic.description,
                policy_topic.metadata->>'source',
                policy_topic.metadata->>'source_evidence_class',
                policy_topic.metadata->>'they_vote_for_you_policy_id',
                policy_topic.metadata->>'provisional',
                policy_topic.metadata->>'last_edited_at',
                link.relationship, link.method, link.confidence, link.evidence_note,
                link.review_status, link.reviewer, link.reviewed_at, link.metadata
            FROM sector_policy_topic_link link
            JOIN policy_topic ON policy_topic.id = link.topic_id
            WHERE {where_clause}
            {lock_clause}
            """,
            (where_value,),
        )
        rows = cur.fetchall()
    if len(rows) > 1:
        raise ReviewImportError(
            f"Review subject key {where_value!r} matched {len(rows)} current "
            "sector_policy_topic_link rows; review identity is ambiguous."
        )
    if not rows:
        return None
    (
        link_id,
        public_sector,
        topic_id,
        topic_slug,
        topic_label,
        topic_description,
        topic_source,
        topic_source_evidence_class,
        topic_external_id,
        topic_provisional,
        topic_last_edited_at,
        relationship,
        method,
        confidence,
        evidence_note,
        review_status,
        reviewer,
        reviewed_at,
        metadata,
    ) = rows[0]
    return {
        "id": link_id,
        "public_sector": public_sector,
        "topic_id": topic_id,
        "topic_slug": topic_slug,
        "topic_label": topic_label,
        "topic_description": topic_description,
        "topic_source": topic_source,
        "topic_source_evidence_class": topic_source_evidence_class,
        "topic_external_id": topic_external_id,
        "topic_provisional": topic_provisional,
        "topic_last_edited_at": topic_last_edited_at,
        "relationship": relationship,
        "method": method,
        "confidence": confidence,
        "evidence_note": evidence_note,
        "review_status": review_status,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "metadata": metadata or {},
    }


def _policy_topic_for_sector_link(conn, proposed_changes: dict[str, Any], existing: dict[str, Any] | None):
    topic_id = proposed_changes.get("topic_id") or (existing or {}).get("topic_id")
    topic_slug = proposed_changes.get("topic_slug") or proposed_changes.get("policy_topic_slug")
    topic_slug = topic_slug or (existing or {}).get("topic_slug")
    if topic_id:
        where_clause = "id = %s"
        where_value = int(topic_id)
    elif topic_slug:
        where_clause = "slug = %s"
        where_value = str(topic_slug).strip()
    else:
        raise ReviewImportError(
            "sector_policy_topic_link decisions require proposed_changes.topic_slug or topic_id."
        )
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                id, slug, label, description,
                metadata->>'source',
                metadata->>'source_evidence_class',
                metadata->>'they_vote_for_you_policy_id',
                metadata->>'provisional',
                metadata->>'last_edited_at'
            FROM policy_topic
            WHERE {where_clause}
            """,
            (where_value,),
        )
        rows = cur.fetchall()
    if not rows:
        raise ReviewImportError(f"No current policy_topic for {where_value!r}.")
    if len(rows) > 1:
        raise ReviewImportError(f"Policy topic reference {where_value!r} is ambiguous.")
    return {
        "topic_id": rows[0][0],
        "topic_slug": rows[0][1],
        "topic_label": rows[0][2],
        "topic_description": rows[0][3],
        "topic_source": rows[0][4],
        "topic_source_evidence_class": rows[0][5],
        "topic_external_id": rows[0][6],
        "topic_provisional": rows[0][7],
        "topic_last_edited_at": rows[0][8],
    }


def _sector_policy_link_from_decision(
    conn,
    *,
    decision: dict[str, Any],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    proposed = decision["proposed_changes"]
    topic = _policy_topic_for_sector_link(conn, proposed, existing)
    public_sector = str(proposed.get("public_sector") or (existing or {}).get("public_sector") or "")
    public_sector = public_sector.strip()
    if public_sector not in PUBLIC_INTEREST_SECTOR_CODES:
        raise ReviewImportError(f"Unknown public_sector for sector-policy link: {public_sector!r}")
    if public_sector in {"unknown", "individual_uncoded"}:
        raise ReviewImportError(
            f"sector-policy links require a substantive sector, not {public_sector!r}."
        )

    relationship = str(
        proposed.get("relationship") or (existing or {}).get("relationship") or ""
    ).strip()
    if relationship not in SECTOR_POLICY_RELATIONSHIPS:
        raise ReviewImportError(
            f"Invalid sector-policy relationship {relationship!r}; expected "
            f"one of {sorted(SECTOR_POLICY_RELATIONSHIPS)}."
        )

    method = str(proposed.get("method") or (existing or {}).get("method") or "manual").strip()
    if method not in SECTOR_POLICY_LINK_METHODS:
        raise ReviewImportError(
            f"Invalid sector-policy link method {method!r}; expected "
            f"one of {sorted(SECTOR_POLICY_LINK_METHODS)}."
        )

    raw_confidence = proposed.get("confidence", (existing or {}).get("confidence"))
    if raw_confidence in ("", None):
        raise ReviewImportError("sector_policy_topic_link decisions require confidence.")
    confidence = Decimal(_format_sector_link_confidence(raw_confidence))
    evidence_note = str(
        proposed.get("link_evidence_note")
        or proposed.get("evidence_note")
        or (existing or {}).get("evidence_note")
        or decision["evidence_note"]
    ).strip()
    if not evidence_note:
        raise ReviewImportError("sector_policy_topic_link decisions require evidence_note.")

    link = {
        **topic,
        "public_sector": public_sector,
        "relationship": relationship,
        "method": method,
        "confidence": confidence,
        "evidence_note": evidence_note,
    }
    expected_key = _sector_policy_link_external_key(
        public_sector=public_sector,
        topic_slug=link["topic_slug"],
        relationship=relationship,
        method=method,
    )
    if decision["subject_external_key"] and decision["subject_external_key"] != expected_key:
        raise ReviewImportError(
            f"Decision {decision['decision_key']}: subject_external_key "
            f"{decision['subject_external_key']!r} does not match proposed link {expected_key!r}."
        )
    return link


def _validate_sector_policy_link_supporting_sources(decision: dict[str, Any]) -> None:
    if decision["decision"] not in {"accept", "revise"}:
        return
    sources = decision["supporting_sources"]
    roles: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ReviewImportError(
                "sector_policy_topic_link supporting_sources entries must be objects."
            )
        role = str(source.get("evidence_role") or source.get("role") or "").strip()
        if role:
            roles.add(role)
        locator = source.get("url") or source.get("source_url") or source.get("storage_path")
        if role in {"topic_scope", "sector_material_interest"} and not str(locator or "").strip():
            raise ReviewImportError(
                f"sector_policy_topic_link supporting source for role {role!r} "
                "requires url, source_url, or storage_path."
            )
    required = {"topic_scope", "sector_material_interest"}
    missing = sorted(required - roles)
    if missing:
        raise ReviewImportError(
            "Accepted/revised sector_policy_topic_link decisions require supporting_sources "
            f"with evidence_role values for {missing}."
        )


def validate_review_decision_subject(conn, decision: dict[str, Any]) -> None:
    if decision["subject_type"] == "entity_match_candidate":
        if decision["subject_external_key"]:
            where_clause = """
                (
                    'entity_match_candidate:' || entity.normalized_name || ':' ||
                    entity.entity_type || ':' || observation.stable_key || ':' || emc.match_method
                ) = %s
            """
            where_value: Any = decision["subject_external_key"]
        elif decision["subject_id"] is not None:
            where_clause = "emc.id = %s"
            where_value = decision["subject_id"]
        else:
            raise ReviewImportError("entity_match_candidate decisions require a subject key.")
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT md5(
                    concat_ws(
                        '|',
                        entity.normalized_name,
                        entity.entity_type,
                        observation.stable_key,
                        emc.match_method,
                        observation.display_name,
                        observation.identifiers::text,
                        observation.aliases::text,
                        observation.public_sector
                    )
                )
                FROM entity_match_candidate emc
                JOIN official_identifier_observation observation
                  ON observation.id = emc.observation_id
                JOIN entity ON entity.id = emc.entity_id
                WHERE {where_clause}
                """,
                (where_value,),
            )
            rows = cur.fetchall()
        if not rows:
            raise ReviewImportError(f"No current entity_match_candidate for {where_value!r}.")
        if len(rows) > 1:
            raise ReviewImportError(
                f"Review subject key {where_value!r} matched {len(rows)} "
                "current entity_match_candidate rows; review identity is ambiguous."
            )
        _validate_subject_fingerprint(decision=decision, current_fingerprint=rows[0][0])
        return

    if decision["subject_type"] == "entity_industry_classification":
        if decision["subject_external_key"]:
            where_clause = """
                (
                    'entity_industry_classification:' ||
                    entity.normalized_name || ':' ||
                    entity.entity_type || ':' ||
                    COALESCE(eic.metadata->>'classifier_name', eic.method) || ':' ||
                    eic.method || ':' ||
                    eic.public_sector || ':' ||
                    COALESCE(industry_code.scheme, '') || ':' ||
                    COALESCE(industry_code.code, '')
                ) = %s
            """
            where_value = decision["subject_external_key"]
        elif decision["subject_id"] is not None:
            where_clause = "eic.id = %s"
            where_value = decision["subject_id"]
        else:
            raise ReviewImportError(
                "entity_industry_classification decisions require a subject key."
            )
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT md5(
                    concat_ws(
                        '|',
                        entity.normalized_name,
                        entity.entity_type,
                        COALESCE(eic.metadata->>'classifier_name', eic.method),
                        eic.method,
                        eic.public_sector,
                        COALESCE(industry_code.scheme, ''),
                        COALESCE(industry_code.code, ''),
                        eic.confidence,
                        COALESCE(eic.evidence_note, '')
                    )
                )
                FROM entity_industry_classification eic
                JOIN entity ON entity.id = eic.entity_id
                LEFT JOIN industry_code ON industry_code.id = eic.industry_code_id
                WHERE {where_clause}
                """,
                (where_value,),
            )
            rows = cur.fetchall()
        if not rows:
            raise ReviewImportError(
                f"No current entity_industry_classification for {where_value!r}."
            )
        if len(rows) > 1:
            raise ReviewImportError(
                f"Review subject key {where_value!r} matched {len(rows)} current "
                "entity_industry_classification rows; review identity is ambiguous."
            )
        _validate_subject_fingerprint(decision=decision, current_fingerprint=rows[0][0])
        return

    if decision["subject_type"] == "influence_event":
        if decision["subject_external_key"]:
            where_clause = "external_key = %s"
            where_value = decision["subject_external_key"]
        elif decision["subject_id"] is not None:
            where_clause = "id = %s"
            where_value = decision["subject_id"]
        else:
            raise ReviewImportError("influence_event decisions require a subject key.")
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT md5(
                    concat_ws(
                        '|',
                        external_key,
                        event_type,
                        COALESCE(event_subtype, ''),
                        description,
                        COALESCE(source_raw_name, ''),
                        COALESCE(amount::text, ''),
                        amount_status,
                        missing_data_flags::text
                    )
                )
                FROM influence_event
                WHERE {where_clause}
                """,
                (where_value,),
            )
            rows = cur.fetchall()
        if not rows:
            raise ReviewImportError(f"No current influence_event for {where_value!r}.")
        if len(rows) > 1:
            raise ReviewImportError(
                f"Review subject key {where_value!r} matched {len(rows)} current "
                "influence_event rows; review identity is ambiguous."
            )
        _validate_subject_fingerprint(decision=decision, current_fingerprint=rows[0][0])
        return

    if decision["subject_type"] == "sector_policy_topic_link":
        if decision["subject_external_key"] is None:
            raise ReviewImportError(
                "sector_policy_topic_link decisions require subject_external_key."
            )
        _validate_sector_policy_link_supporting_sources(decision)
        existing = _existing_sector_policy_link(conn, decision)
        if existing is not None:
            current_fingerprint = _sector_policy_link_fingerprint(existing)
        else:
            proposed = _sector_policy_link_from_decision(
                conn,
                decision=decision,
                existing=None,
            )
            current_fingerprint = _sector_policy_link_fingerprint(proposed)
        _validate_subject_fingerprint(
            decision=decision,
            current_fingerprint=current_fingerprint,
        )
        return

    if decision["subject_type"] == "source_document":
        if decision["subject_id"] is None:
            raise ReviewImportError("source_document decisions require subject_id.")
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM source_document WHERE id = %s", (decision["subject_id"],))
            if cur.fetchone() is None:
                raise ReviewImportError(f"No current source_document for {decision['subject_id']}.")


def _merge_metadata_sql(table_name: str, id_column: str = "id") -> str:
    return f"""
        UPDATE {table_name}
        SET metadata = metadata || %s
        WHERE {id_column} = %s
    """


def _update_entity_type_from_review(conn, entity_id: int, entity_type: str) -> bool:
    if entity_type in {"", "unknown", "individual"}:
        return False
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE entity
            SET entity_type = %s
            WHERE id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM entity duplicate
                  WHERE duplicate.normalized_name = entity.normalized_name
                    AND duplicate.entity_type = %s
                    AND duplicate.id <> entity.id
              )
            """,
            (entity_type, entity_id, entity_type),
        )
        return cur.rowcount == 1


def _attach_reviewed_identifiers(
    conn,
    *,
    entity_id: int,
    identifiers: list[dict[str, Any]],
    observation: dict[str, Any],
    decision_id: int,
    decision: dict[str, Any],
) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for identifier in identifiers:
            identifier_type = str(identifier.get("identifier_type") or "").strip()
            identifier_value = str(identifier.get("identifier_value") or "").strip()
            if not identifier_type or not identifier_value:
                raise ReviewImportError(
                    f"Decision {decision['decision_key']}: identifier rows require "
                    "identifier_type and identifier_value."
                )
            cur.execute(
                """
                SELECT entity_id
                FROM entity_identifier
                WHERE identifier_type = %s
                  AND identifier_value = %s
                FOR UPDATE
                """,
                (identifier_type, identifier_value),
            )
            existing = cur.fetchone()
            if existing is not None:
                existing_entity_id = int(existing[0])
                if existing_entity_id != entity_id:
                    raise ReviewImportError(
                        f"Decision {decision['decision_key']}: identifier "
                        f"{identifier_type}:{identifier_value} is already attached "
                        f"to entity {existing_entity_id}, not entity {entity_id}."
                    )
                continue
            cur.execute(
                """
                INSERT INTO entity_identifier (
                    entity_id, identifier_type, identifier_value,
                    source_document_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    entity_id,
                    identifier_type,
                    identifier_value,
                    observation["source_document_id"],
                    as_jsonb(
                        {
                            "source_id": observation["source_id"],
                            "source_record_type": observation["source_record_type"],
                            "stable_key": observation["stable_key"],
                            "review_decision_id": decision_id,
                            "review_decision_key": decision["decision_key"],
                            "method": "manual_reviewed_official_observation",
                        }
                    ),
                ),
            )
            inserted += 1
    return inserted


def _attach_reviewed_aliases(
    conn,
    *,
    entity_id: int,
    aliases: list[Any],
    observation: dict[str, Any],
    decision_id: int,
    decision: dict[str, Any],
) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for alias in aliases:
            alias_value = str(alias or "").strip()
            if not alias_value:
                continue
            normalized_alias = " ".join(
                "".join(char.lower() if char.isalnum() else " " for char in alias_value).split()
            )
            if not normalized_alias:
                continue
            cur.execute(
                """
                INSERT INTO entity_alias (
                    entity_id, alias, normalized_alias, source_document_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (entity_id, normalized_alias) DO NOTHING
                """,
                (
                    entity_id,
                    alias_value,
                    normalized_alias,
                    observation["source_document_id"],
                    as_jsonb(
                        {
                            "source_id": observation["source_id"],
                            "source_record_type": observation["source_record_type"],
                            "stable_key": observation["stable_key"],
                            "review_decision_id": decision_id,
                            "review_decision_key": decision["decision_key"],
                            "method": "manual_reviewed_official_observation",
                        }
                    ),
                ),
            )
            if cur.rowcount == 1:
                inserted += 1
    return inserted


def _insert_reviewed_official_classification(
    conn,
    *,
    entity_id: int,
    observation: dict[str, Any],
    decision_id: int,
    decision: dict[str, Any],
    public_sector_code_ids: dict[str, int],
) -> bool:
    public_sector = observation["public_sector"]
    if public_sector in {"", "unknown"}:
        return False
    industry_code_id = public_sector_code_ids.get(public_sector)
    _assert_no_classification_conflict(
        conn,
        entity_id=entity_id,
        public_sector=public_sector,
        industry_code_id=industry_code_id,
        decision=decision,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_industry_classification (
                entity_id, industry_code_id, public_sector, method, confidence,
                evidence_note, reviewer, reviewed_at, source_document_id, metadata
            )
            SELECT %s, %s, %s, 'official', 'manual_reviewed', %s, %s, %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1
                FROM entity_industry_classification existing
                WHERE existing.entity_id = %s
                  AND existing.method = 'official'
                  AND existing.metadata->>'stable_key' = %s
            )
            """,
            (
                entity_id,
                industry_code_id,
                public_sector,
                decision["evidence_note"],
                decision["reviewer"],
                decision["reviewed_at"],
                observation["source_document_id"],
                as_jsonb(
                    {
                        "source_id": observation["source_id"],
                        "source_record_type": observation["source_record_type"],
                        "stable_key": observation["stable_key"],
                        "review_decision_id": decision_id,
                        "review_decision_key": decision["decision_key"],
                        "method": "manual_reviewed_official_observation",
                    }
                ),
                entity_id,
                observation["stable_key"],
            ),
        )
        return cur.rowcount == 1


def _assert_no_classification_conflict(
    conn,
    *,
    entity_id: int,
    public_sector: str,
    industry_code_id: int | None,
    decision: dict[str, Any],
) -> None:
    if decision["proposed_changes"].get("allow_additional_classification") is True:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT existing.id, existing.public_sector, industry_code.scheme, industry_code.code
            FROM entity_industry_classification existing
            LEFT JOIN industry_code ON industry_code.id = existing.industry_code_id
            WHERE existing.entity_id = %s
              AND existing.method IN ('official', 'manual')
              AND COALESCE(existing.metadata->>'review_decision_key', '') <> %s
              AND (
                  existing.public_sector <> %s
                  OR existing.industry_code_id IS DISTINCT FROM %s
              )
            LIMIT 1
            """,
            (entity_id, decision["decision_key"], public_sector, industry_code_id),
        )
        conflict = cur.fetchone()
    if conflict is None:
        return
    conflict_id, conflict_sector, conflict_scheme, conflict_code = conflict
    raise ReviewImportError(
        f"Decision {decision['decision_key']}: entity {entity_id} already has "
        f"manual/official classification {conflict_id} "
        f"({conflict_sector}, {conflict_scheme or ''}:{conflict_code or ''}). "
        "Set proposed_changes.allow_additional_classification=true if this is intentional."
    )


def _apply_entity_match_candidate(
    conn,
    *,
    decision_id: int,
    decision: dict[str, Any],
    public_sector_code_ids: dict[str, int],
) -> dict[str, int]:
    if decision["subject_id"] is None and decision["subject_external_key"] is None:
        raise ReviewImportError(
            "entity_match_candidate decisions require subject_id or subject_external_key."
        )
    if decision["subject_external_key"]:
        where_clause = """
            (
                'entity_match_candidate:' || entity.normalized_name || ':' ||
                entity.entity_type || ':' || observation.stable_key || ':' || emc.match_method
            ) = %s
        """
        where_value: Any = decision["subject_external_key"]
    else:
        where_clause = "emc.id = %s"
        where_value = decision["subject_id"]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                emc.id, emc.entity_id, emc.observation_id,
                observation.stable_key, observation.source_document_id,
                observation.source_id, observation.source_record_type,
                observation.entity_type, observation.public_sector,
                observation.identifiers, observation.aliases,
                md5(
                    concat_ws(
                        '|',
                        entity.normalized_name,
                        entity.entity_type,
                        observation.stable_key,
                        emc.match_method,
                        observation.display_name,
                        observation.identifiers::text,
                        observation.aliases::text,
                        observation.public_sector
                    )
                ) AS review_subject_fingerprint
            FROM entity_match_candidate emc
            JOIN official_identifier_observation observation
              ON observation.id = emc.observation_id
            JOIN entity ON entity.id = emc.entity_id
            WHERE {where_clause}
            FOR UPDATE OF emc
            """,
            (where_value,),
        )
        rows = cur.fetchall()
    if not rows:
        raise ReviewImportError(
            f"entity_match_candidate {decision['subject_id']} does not exist."
        )
    if len(rows) > 1:
        raise ReviewImportError(
            f"Review subject key {where_value!r} matched {len(rows)} current "
            "entity_match_candidate rows; review identity is ambiguous."
        )
    row = rows[0]

    (
        candidate_id,
        entity_id,
        _observation_id,
        stable_key,
        source_document_id,
        source_id,
        source_record_type,
        entity_type,
        public_sector,
        identifiers,
        aliases,
        current_fingerprint,
    ) = row
    _validate_subject_fingerprint(
        decision=decision,
        current_fingerprint=current_fingerprint,
    )
    observation = {
        "stable_key": stable_key,
        "source_document_id": source_document_id,
        "source_id": source_id,
        "source_record_type": source_record_type,
        "entity_type": entity_type or "unknown",
        "public_sector": public_sector or "unknown",
    }
    identifiers = identifiers or []
    aliases = aliases or []

    inserted_identifiers = 0
    inserted_aliases = 0
    inserted_classifications = 0
    updated_entity_type = 0
    status = {
        "accept": "manual_accepted",
        "revise": "manual_accepted",
        "reject": "rejected",
        "needs_more_evidence": "needs_review",
        "defer": "needs_review",
    }[decision["decision"]]
    review_metadata = _review_metadata(decision_id, decision)

    if decision["decision"] in {"accept", "revise"}:
        inserted_identifiers = _attach_reviewed_identifiers(
            conn,
            entity_id=entity_id,
            identifiers=identifiers,
            observation=observation,
            decision_id=decision_id,
            decision=decision,
        )
        inserted_aliases = _attach_reviewed_aliases(
            conn,
            entity_id=entity_id,
            aliases=aliases,
            observation=observation,
            decision_id=decision_id,
            decision=decision,
        )
        if _insert_reviewed_official_classification(
            conn,
            entity_id=entity_id,
            observation=observation,
            decision_id=decision_id,
            decision=decision,
            public_sector_code_ids=public_sector_code_ids,
        ):
            inserted_classifications = 1
        proposed_entity_type = decision["proposed_changes"].get("entity_type")
        if _update_entity_type_from_review(
            conn,
            entity_id,
            proposed_entity_type or observation["entity_type"],
        ):
            updated_entity_type = 1

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE entity_match_candidate
            SET status = %s,
                confidence = CASE
                    WHEN %s IN ('manual_accepted', 'rejected') THEN 'manual_reviewed'
                    ELSE confidence
                END,
                reviewer = %s,
                reviewed_at = %s,
                metadata = metadata || %s
            WHERE id = %s
            """,
            (
                status,
                status,
                decision["reviewer"],
                decision["reviewed_at"],
                as_jsonb(review_metadata),
                candidate_id,
            ),
        )

    return {
        "entity_match_candidates_updated": 1,
        "entity_identifiers_inserted": inserted_identifiers,
        "entity_aliases_inserted": inserted_aliases,
        "official_classifications_inserted": inserted_classifications,
        "entity_types_updated": updated_entity_type,
    }


def _industry_code_for_manual_classification(
    conn,
    *,
    proposed_changes: dict[str, Any],
    current_row: dict[str, Any],
    public_sector_code_ids: dict[str, int],
) -> tuple[int | None, str]:
    public_sector = str(
        proposed_changes.get("public_sector") or current_row["public_sector"] or "unknown"
    )
    scheme = proposed_changes.get("industry_scheme") or current_row.get("industry_scheme")
    code = proposed_changes.get("industry_code") or current_row.get("industry_code")
    label = proposed_changes.get("industry_label") or current_row.get("industry_label") or code
    if scheme and code:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO industry_code (scheme, code, label)
                VALUES (%s, %s, %s)
                ON CONFLICT (scheme, code) DO UPDATE SET label = EXCLUDED.label
                RETURNING id
                """,
                (scheme, code, label),
            )
            return int(cur.fetchone()[0]), public_sector
    return public_sector_code_ids.get(public_sector), public_sector


def _apply_entity_industry_classification(
    conn,
    *,
    decision_id: int,
    decision: dict[str, Any],
    public_sector_code_ids: dict[str, int],
) -> dict[str, int]:
    if decision["subject_id"] is None and decision["subject_external_key"] is None:
        raise ReviewImportError(
            "entity_industry_classification decisions require subject_id or subject_external_key."
        )
    if decision["subject_external_key"]:
        where_clause = """
            (
                'entity_industry_classification:' ||
                entity.normalized_name || ':' ||
                entity.entity_type || ':' ||
                COALESCE(eic.metadata->>'classifier_name', eic.method) || ':' ||
                eic.method || ':' ||
                eic.public_sector || ':' ||
                COALESCE(industry_code.scheme, '') || ':' ||
                COALESCE(industry_code.code, '')
            ) = %s
        """
        where_value: Any = decision["subject_external_key"]
    else:
        where_clause = "eic.id = %s"
        where_value = decision["subject_id"]

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                eic.id, eic.entity_id, eic.industry_code_id, eic.public_sector,
                eic.method, eic.confidence, eic.evidence_note,
                eic.source_document_id, eic.metadata,
                industry_code.scheme, industry_code.code, industry_code.label,
                md5(
                    concat_ws(
                        '|',
                        entity.normalized_name,
                        entity.entity_type,
                        COALESCE(eic.metadata->>'classifier_name', eic.method),
                        eic.method,
                        eic.public_sector,
                        COALESCE(industry_code.scheme, ''),
                        COALESCE(industry_code.code, ''),
                        eic.confidence,
                        COALESCE(eic.evidence_note, '')
                    )
                ) AS review_subject_fingerprint
            FROM entity_industry_classification eic
            JOIN entity ON entity.id = eic.entity_id
            LEFT JOIN industry_code ON industry_code.id = eic.industry_code_id
            WHERE {where_clause}
            FOR UPDATE OF eic
            """,
            (where_value,),
        )
        rows = cur.fetchall()
    if not rows:
        raise ReviewImportError(
            f"entity_industry_classification {decision['subject_id']} does not exist."
        )
    if len(rows) > 1:
        raise ReviewImportError(
            f"Review subject key {where_value!r} matched {len(rows)} current "
            "entity_industry_classification rows; review identity is ambiguous."
        )
    row = rows[0]

    (
        classification_id,
        entity_id,
        _industry_code_id,
        public_sector,
        method,
        confidence,
        evidence_note,
        source_document_id,
        metadata,
        industry_scheme,
        industry_code,
        industry_label,
        current_fingerprint,
    ) = row
    _validate_subject_fingerprint(
        decision=decision,
        current_fingerprint=current_fingerprint,
    )
    current_row = {
        "public_sector": public_sector,
        "method": method,
        "confidence": confidence,
        "evidence_note": evidence_note,
        "metadata": metadata or {},
        "industry_scheme": industry_scheme,
        "industry_code": industry_code,
        "industry_label": industry_label,
    }
    status = _review_metadata(decision_id, decision)
    inserted_manual_classifications = 0

    if decision["decision"] in {"accept", "revise"}:
        manual_industry_code_id, manual_public_sector = _industry_code_for_manual_classification(
            conn,
            proposed_changes=decision["proposed_changes"],
            current_row=current_row,
            public_sector_code_ids=public_sector_code_ids,
        )
        _assert_no_classification_conflict(
            conn,
            entity_id=entity_id,
            public_sector=manual_public_sector,
            industry_code_id=manual_industry_code_id,
            decision=decision,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entity_industry_classification (
                    entity_id, industry_code_id, public_sector, method, confidence,
                    evidence_note, reviewer, reviewed_at, source_document_id, metadata
                )
                SELECT %s, %s, %s, 'manual', 'manual_reviewed', %s, %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM entity_industry_classification existing
                    WHERE existing.method = 'manual'
                      AND existing.metadata->>'review_decision_id' = %s
                )
                """,
                (
                    entity_id,
                    manual_industry_code_id,
                    manual_public_sector,
                    decision["evidence_note"],
                    decision["reviewer"],
                    decision["reviewed_at"],
                    source_document_id,
                    as_jsonb(
                        {
                            "review_decision_id": decision_id,
                            "review_decision_key": decision["decision_key"],
                            "derived_from_classification_id": classification_id,
                            "proposed_changes": decision["proposed_changes"],
                            "original_method": method,
                            "original_confidence": confidence,
                            "original_evidence_note": evidence_note,
                            "original_metadata": metadata or {},
                        }
                    ),
                    str(decision_id),
                ),
            )
            if cur.rowcount == 1:
                inserted_manual_classifications = 1

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE entity_industry_classification
            SET reviewer = %s,
                reviewed_at = %s,
                metadata = metadata || %s
            WHERE id = %s
            """,
            (
                decision["reviewer"],
                decision["reviewed_at"],
                as_jsonb(status),
                classification_id,
            ),
        )

    return {
        "entity_classifications_review_marked": 1,
        "manual_classifications_inserted": inserted_manual_classifications,
    }


def _apply_influence_event(conn, *, decision_id: int, decision: dict[str, Any]) -> dict[str, int]:
    status = {
        "accept": "reviewed",
        "revise": "reviewed",
        "reject": "rejected",
        "needs_more_evidence": "needs_review",
        "defer": "needs_review",
    }[decision["decision"]]

    if decision["subject_external_key"]:
        where_clause = "external_key = %s"
        where_value = decision["subject_external_key"]
    else:
        where_clause = "id = %s"
        where_value = decision["subject_id"]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                id,
                md5(
                    concat_ws(
                        '|',
                        external_key,
                        event_type,
                        COALESCE(event_subtype, ''),
                        description,
                        COALESCE(source_raw_name, ''),
                        COALESCE(amount::text, ''),
                        amount_status,
                        missing_data_flags::text
                    )
                ) AS review_subject_fingerprint
            FROM influence_event
            WHERE {where_clause}
            FOR UPDATE
            """,
            (where_value,),
        )
        row = cur.fetchone()
        if row is None:
            raise ReviewImportError(
                "influence_event decision did not match a record: "
                f"{decision['subject_id'] or decision['subject_external_key']!r}"
            )
        event_id, current_fingerprint = row
        _validate_subject_fingerprint(
            decision=decision,
            current_fingerprint=current_fingerprint,
        )
        cur.execute(
            """
            UPDATE influence_event
            SET review_status = %s,
                metadata = metadata || %s
            WHERE id = %s
            """,
            (status, as_jsonb(_review_metadata(decision_id, decision)), event_id),
        )
        if cur.rowcount != 1:
            raise ReviewImportError(
                "influence_event decision did not update exactly one record: "
                f"{decision['subject_id'] or decision['subject_external_key']!r}"
            )
    return {"influence_events_updated": 1}


def _apply_sector_policy_topic_link(
    conn,
    *,
    decision_id: int,
    decision: dict[str, Any],
) -> dict[str, int]:
    _validate_sector_policy_link_supporting_sources(decision)
    existing = _existing_sector_policy_link(conn, decision, for_update=True)
    link = _sector_policy_link_from_decision(
        conn,
        decision=decision,
        existing=existing,
    )
    current_fingerprint = _sector_policy_link_fingerprint(existing or link)
    _validate_subject_fingerprint(
        decision=decision,
        current_fingerprint=current_fingerprint,
    )
    review_status = {
        "accept": "reviewed",
        "revise": "reviewed",
        "reject": "rejected",
        "needs_more_evidence": "needs_review",
        "defer": "needs_review",
    }[decision["decision"]]
    metadata = {
        **_review_metadata(decision_id, decision),
        "proposed_changes": decision["proposed_changes"],
        "supporting_sources": decision["supporting_sources"],
        "subject_external_key": _sector_policy_link_external_key(
            public_sector=link["public_sector"],
            topic_slug=link["topic_slug"],
            relationship=link["relationship"],
            method=link["method"],
        ),
    }
    if existing is not None:
        metadata["previous_link"] = {
            "public_sector": existing["public_sector"],
            "topic_slug": existing["topic_slug"],
            "relationship": existing["relationship"],
            "method": existing["method"],
            "confidence": str(existing["confidence"]),
            "evidence_note": existing["evidence_note"],
            "review_status": existing["review_status"],
        }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sector_policy_topic_link (
                public_sector, topic_id, relationship, method, confidence,
                evidence_note, review_status, reviewer, reviewed_at, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (public_sector, topic_id, relationship, method)
            DO UPDATE SET
                confidence = EXCLUDED.confidence,
                evidence_note = EXCLUDED.evidence_note,
                review_status = EXCLUDED.review_status,
                reviewer = EXCLUDED.reviewer,
                reviewed_at = EXCLUDED.reviewed_at,
                metadata = sector_policy_topic_link.metadata || EXCLUDED.metadata
            RETURNING id
            """,
            (
                link["public_sector"],
                link["topic_id"],
                link["relationship"],
                link["method"],
                link["confidence"],
                link["evidence_note"],
                review_status,
                decision["reviewer"],
                decision["reviewed_at"],
                as_jsonb(metadata),
            ),
        )
        cur.fetchone()
    return {
        "sector_policy_topic_links_upserted": 1,
        f"sector_policy_topic_links_{review_status}": 1,
    }


def _apply_source_document_or_other(
    conn,
    *,
    decision_id: int,
    decision: dict[str, Any],
) -> dict[str, int]:
    if decision["subject_type"] != "source_document":
        return {"other_review_decisions_recorded": 1}
    if decision["subject_id"] is None:
        raise ReviewImportError("source_document decisions require subject_id.")
    with conn.cursor() as cur:
        cur.execute(
            _merge_metadata_sql("source_document"),
            (as_jsonb(_review_metadata(decision_id, decision)), decision["subject_id"]),
        )
        if cur.rowcount != 1:
            raise ReviewImportError(f"source_document {decision['subject_id']} does not exist.")
    return {"source_documents_review_marked": 1}


def _add_counts(target: dict[str, int], updates: dict[str, int]) -> None:
    for key, value in updates.items():
        target[key] = target.get(key, 0) + value


def decision_from_db_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        decision_id,
        decision_key,
        subject_type,
        subject_id,
        subject_external_key,
        decision,
        reviewer,
        reviewed_at,
        evidence_note,
        proposed_changes,
        supporting_sources,
        metadata,
    ) = row
    metadata = metadata or {}
    if subject_type in GENERATED_REVIEW_SUBJECT_TYPES and subject_external_key is None:
        raise ReviewImportError(
            f"Stored decision {decision_key} for {subject_type} is missing "
            "subject_external_key and cannot be replayed safely after reloads."
        )
    normalized = {
        "decision_key": decision_key,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "subject_external_key": subject_external_key,
        "expected_subject_fingerprint": metadata.get("expected_subject_fingerprint"),
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": parse_reviewed_at(reviewed_at),
        "evidence_note": evidence_note,
        "proposed_changes": proposed_changes or {},
        "supporting_sources": supporting_sources or [],
        "metadata": {
            **metadata,
            "reapplied_from_manual_review_decision_id": decision_id,
        },
    }
    normalized["payload_sha256"] = decision_payload_sha256(normalized)
    return {"decision_id": int(decision_id), "decision": normalized}


def _manual_review_decision_rows(
    conn,
    subject_type: str | None = None,
    exclude_subject_types: set[str] | None = None,
) -> list[tuple[Any, ...]]:
    params: tuple[Any, ...] = ()
    where_clause = ""
    if subject_type:
        if subject_type not in REVIEW_SUBJECT_TYPES:
            raise ReviewImportError(
                f"Invalid subject_type {subject_type!r}; expected one of {sorted(REVIEW_SUBJECT_TYPES)}"
            )
        where_clause = "WHERE subject_type = %s"
        params = (subject_type,)
    elif exclude_subject_types:
        invalid = sorted(exclude_subject_types - REVIEW_SUBJECT_TYPES)
        if invalid:
            raise ReviewImportError(
                f"Invalid excluded subject_type values {invalid}; expected "
                f"values from {sorted(REVIEW_SUBJECT_TYPES)}"
            )
        where_clause = "WHERE NOT (subject_type = ANY(%s))"
        params = (sorted(exclude_subject_types),)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                id, decision_key, subject_type, subject_id, subject_external_key,
                decision, reviewer, reviewed_at, evidence_note, proposed_changes,
                supporting_sources, metadata
            FROM manual_review_decision
            {where_clause}
            ORDER BY reviewed_at, id
            """,
            params,
        )
        return cur.fetchall()


def apply_review_decision(
    conn,
    *,
    decision_id: int,
    decision: dict[str, Any],
    public_sector_code_ids: dict[str, int],
) -> dict[str, int]:
    if decision["subject_type"] == "entity_match_candidate":
        return _apply_entity_match_candidate(
            conn,
            decision_id=decision_id,
            decision=decision,
            public_sector_code_ids=public_sector_code_ids,
        )
    if decision["subject_type"] == "entity_industry_classification":
        return _apply_entity_industry_classification(
            conn,
            decision_id=decision_id,
            decision=decision,
            public_sector_code_ids=public_sector_code_ids,
        )
    if decision["subject_type"] == "influence_event":
        return _apply_influence_event(conn, decision_id=decision_id, decision=decision)
    if decision["subject_type"] == "sector_policy_topic_link":
        return _apply_sector_policy_topic_link(
            conn,
            decision_id=decision_id,
            decision=decision,
        )
    return _apply_source_document_or_other(conn, decision_id=decision_id, decision=decision)


def _reapply_error(
    *,
    row: tuple[Any, ...],
    exc: Exception,
    loaded: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if loaded is not None:
        decision = loaded["decision"]
        return {
            "decision_id": loaded["decision_id"],
            "decision_key": decision["decision_key"],
            "subject_type": decision["subject_type"],
            "subject_external_key": decision["subject_external_key"],
            "error": repr(exc),
        }
    return {
        "decision_id": row[0],
        "decision_key": row[1],
        "subject_type": row[2],
        "subject_external_key": row[4],
        "error": repr(exc),
    }


def reapply_review_decisions(
    conn,
    *,
    apply: bool = False,
    subject_type: str | None = None,
    exclude_subject_types: set[str] | None = None,
    continue_on_error: bool = False,
    output_dir: Path = AUDIT_DIR,
) -> dict[str, Any]:
    rows = _manual_review_decision_rows(
        conn,
        subject_type=subject_type,
        exclude_subject_types=exclude_subject_types,
    )
    generated_at = _timestamp()
    summary: dict[str, Any] = {
        "apply": apply,
        "generated_at": generated_at,
        "subject_type": subject_type,
        "excluded_subject_types": sorted(exclude_subject_types or []),
        "records_seen": len(rows),
        "records_would_reapply": 0,
        "records_reapplied": 0,
        "errors": [],
        "applied_updates": {},
    }
    if not apply:
        for row in rows:
            loaded = None
            try:
                loaded = decision_from_db_row(row)
                decision = loaded["decision"]
                validate_review_decision_subject(conn, decision)
                summary["records_would_reapply"] += 1
            except Exception as exc:
                summary["errors"].append(_reapply_error(row=row, exc=exc, loaded=loaded))
                if not continue_on_error:
                    _write_review_reapply_summary(summary, output_dir=output_dir)
                    raise
        _write_review_reapply_summary(summary, output_dir=output_dir)
        return summary

    public_sector_code_ids = _public_sector_code_ids(conn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("au_politics_review_import",))
        for row in rows:
            loaded = None
            savepoint_started = False
            try:
                loaded = decision_from_db_row(row)
                decision_id = loaded["decision_id"]
                decision = loaded["decision"]
                if continue_on_error:
                    with conn.cursor() as cur:
                        cur.execute("SAVEPOINT review_reapply_decision")
                    savepoint_started = True
                updates = apply_review_decision(
                    conn,
                    decision_id=decision_id,
                    decision=decision,
                    public_sector_code_ids=public_sector_code_ids,
                )
                if continue_on_error:
                    with conn.cursor() as cur:
                        cur.execute("RELEASE SAVEPOINT review_reapply_decision")
                summary["records_reapplied"] += 1
                _add_counts(summary["applied_updates"], updates)
            except Exception as exc:
                if continue_on_error and savepoint_started:
                    with conn.cursor() as cur:
                        cur.execute("ROLLBACK TO SAVEPOINT review_reapply_decision")
                        cur.execute("RELEASE SAVEPOINT review_reapply_decision")
                summary["errors"].append(_reapply_error(row=row, exc=exc, loaded=loaded))
                if not continue_on_error:
                    raise
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    _write_review_reapply_summary(summary, output_dir=output_dir)
    return summary


def _write_review_reapply_summary(summary: dict[str, Any], *, output_dir: Path = AUDIT_DIR) -> Path:
    target_dir = output_dir / "review_replays"
    target_dir.mkdir(parents=True, exist_ok=True)
    mode = "apply" if summary["apply"] else "dry_run"
    summary_path = target_dir / f"review_reapply_{mode}_{summary['generated_at']}.summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def import_review_decisions(
    conn,
    decisions_path: Path,
    *,
    apply: bool = False,
    output_dir: Path = AUDIT_DIR,
) -> dict[str, Any]:
    decisions = load_review_decision_file(decisions_path)
    imported_at = _timestamp()
    summary: dict[str, Any] = {
        "decisions_path": str(decisions_path),
        "decisions_sha256": sha256_file(decisions_path),
        "generated_at": imported_at,
        "dry_run": not apply,
        "records_seen": len(decisions),
        "decisions_inserted": 0,
        "duplicate_decisions": 0,
        "applied_updates": {},
    }
    if not apply:
        for decision in decisions:
            validate_review_decision_subject(conn, decision)
        _write_review_import_summary(summary, output_dir=output_dir)
        return summary

    public_sector_code_ids = _public_sector_code_ids(conn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("au_politics_review_import",))
        for decision in decisions:
            decision_id, inserted = _insert_manual_review_decision(conn, decision, decisions_path)
            if inserted:
                summary["decisions_inserted"] += 1
            else:
                summary["duplicate_decisions"] += 1
            updates = apply_review_decision(
                conn,
                decision_id=decision_id,
                decision=decision,
                public_sector_code_ids=public_sector_code_ids,
            )
            _add_counts(summary["applied_updates"], updates)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    _write_review_import_summary(summary, output_dir=output_dir)
    return summary


def _write_review_import_summary(summary: dict[str, Any], *, output_dir: Path = AUDIT_DIR) -> Path:
    target_dir = output_dir / "review_imports"
    target_dir.mkdir(parents=True, exist_ok=True)
    mode = "apply" if not summary["dry_run"] else "dry_run"
    summary_path = target_dir / f"review_import_{mode}_{summary['generated_at']}.summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def export_review_queue(
    conn,
    queue_name: str,
    *,
    limit: int | None = None,
    output_dir: Path = AUDIT_DIR,
) -> Path:
    if queue_name not in REVIEW_QUEUES:
        valid = ", ".join(review_queue_names())
        raise ValueError(f"Unknown review queue {queue_name!r}. Valid queues: {valid}")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive when supplied.")

    queue = REVIEW_QUEUES[queue_name]
    target_dir = output_dir / "review_queues"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    jsonl_path = target_dir / f"{queue.name}_{timestamp}.jsonl"
    summary_path = target_dir / f"{queue.name}_{timestamp}.summary.json"

    sql = queue.sql
    params: tuple[int, ...] = ()
    if limit is not None:
        sql = f"{sql}\nLIMIT %s"
        params = (limit,)

    count = 0
    with conn.cursor() as cur, jsonl_path.open("w", encoding="utf-8") as handle:
        cur.execute(sql, params)
        columns = [column.name for column in cur.description]
        for row in cur.fetchall():
            count += 1
            record = row_to_dict(columns, row)
            record["review_queue"] = queue.name
            record["review_queue_description"] = queue.description
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "queue_name": queue.name,
        "description": queue.description,
        "subject_type": queue.subject_type,
        "limit": limit,
        "record_count": count,
        "jsonl_path": str(jsonl_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
