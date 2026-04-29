from __future__ import annotations

import re
from collections import Counter
from typing import Any

from psycopg.types.json import Jsonb


PARSER_NAME = "party_entity_link_candidates_v1"
PARSER_VERSION = "3"
NON_PARTY_LABELS = {
    "deputy president",
    "dpres",
    "ind",
    "independent",
    "independents",
    "pres",
    "president",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _is_non_party_label(value: str) -> bool:
    return _normalize_text(value) in NON_PARTY_LABELS


def party_entity_name_patterns(party: dict[str, Any]) -> list[str]:
    name = str(party.get("name") or "")
    short_name = str(party.get("short_name") or "")
    if _is_non_party_label(name) or _is_non_party_label(short_name):
        return []
    normalized = f"{name} {short_name}".lower()
    is_lnp = "liberal national" in normalized or "lnp" in normalized
    is_clp = "country liberal" in normalized or "clp" in normalized
    patterns: list[str] = []
    if "alp" in normalized or "labor" in normalized:
        patterns.extend(["Australian Labor Party%", "% Labor Party%", "% ALP%"])
    if is_lnp:
        patterns.append("Liberal National Party%")
    elif is_clp:
        patterns.extend(["Country Liberal Party%", "CLP"])
    elif re.search(r"\blp\b", normalized) or "liberal party" in normalized:
        patterns.extend(["Liberal Party%", "Liberal Party of Australia%"])
    if not is_lnp and not is_clp and ("national party" in normalized or "nats" in normalized):
        patterns.extend(["National Party%", "The Nationals%"])
    if "greens" in normalized or re.search(r"\bag\b", normalized):
        patterns.extend(["Australian Greens%", "% Greens%", "Greens", "Greens %", "Greens -%"])
    if "one nation" in normalized or re.search(r"\bon\b", normalized):
        patterns.extend(["%One Nation%"])
    if "united australia" in normalized or "uap" in normalized:
        patterns.extend(["United Australia Party%"])
    if "katter" in normalized or "kap" in normalized:
        patterns.extend(["Katter%"])
    if "jacqui lambie" in normalized or "jln" in normalized:
        patterns.extend(["Jacqui Lambie Network%"])
    for value in (name, short_name):
        cleaned = " ".join(str(value or "").split())
        if len(cleaned) >= 4 and not _is_non_party_label(cleaned):
            patterns.append(f"{cleaned}%")
    deduped: list[str] = []
    for pattern in patterns:
        if pattern not in deduped:
            deduped.append(pattern)
    return deduped


def party_entity_name_terms(party: dict[str, Any]) -> list[str]:
    name = str(party.get("name") or "")
    short_name = str(party.get("short_name") or "")
    if _is_non_party_label(name) or _is_non_party_label(short_name):
        return []
    normalized = f"{name} {short_name}".lower()
    is_lnp = "liberal national" in normalized or "lnp" in normalized
    is_clp = "country liberal" in normalized or "clp" in normalized
    terms: list[str] = []
    if "alp" in normalized or "labor" in normalized:
        terms.extend(["australian labor party", "labor party", "alp"])
    if is_lnp:
        terms.extend(["liberal national party", "lnp"])
    elif is_clp:
        terms.extend(["country liberal party", "clp"])
    elif re.search(r"\blp\b", normalized) or "liberal party" in normalized:
        terms.extend(["liberal party", "liberal party of australia"])
    if not is_lnp and not is_clp and ("national party" in normalized or "nats" in normalized):
        terms.extend(["national party", "the nationals"])
    if "greens" in normalized or re.search(r"\bag\b", normalized):
        terms.extend(["australian greens", "greens"])
    if "one nation" in normalized or re.search(r"\bon\b", normalized):
        terms.extend(["one nation", "pauline hanson"])
    if "united australia" in normalized or "uap" in normalized:
        terms.extend(["united australia party", "uap"])
    if "katter" in normalized or "kap" in normalized:
        terms.extend(["katter", "kap"])
    if "jacqui lambie" in normalized or "jln" in normalized:
        terms.extend(["jacqui lambie network", "jln"])
    for value in (name, short_name):
        cleaned = _normalize_text(str(value or ""))
        if len(cleaned) >= 4 and not _is_non_party_label(cleaned):
            terms.append(cleaned)
    deduped: list[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return deduped


def _term_matches(text: str, term: str) -> bool:
    escaped = re.escape(_normalize_text(term))
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _party_candidate_matches_entity(party: dict[str, Any], entity_name: str) -> bool:
    text = _normalize_text(entity_name)
    return any(_term_matches(text, term) for term in party_entity_name_terms(party))


def _parties(conn, *, include_without_current_representatives: bool = False) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                party.id,
                party.name,
                party.short_name,
                jurisdiction.code AS jurisdiction_code,
                jurisdiction.level AS jurisdiction_level,
                count(DISTINCT office_term.person_id) FILTER (
                    WHERE office_term.term_end IS NULL
                ) AS current_representative_count
            FROM party
            LEFT JOIN jurisdiction ON jurisdiction.id = party.jurisdiction_id
            LEFT JOIN office_term ON office_term.party_id = party.id
            WHERE COALESCE(party.name, '') <> ''
            GROUP BY party.id, party.name, party.short_name, jurisdiction.code, jurisdiction.level
            ORDER BY
                count(DISTINCT office_term.person_id) FILTER (
                    WHERE office_term.term_end IS NULL
                ) DESC,
                jurisdiction.code NULLS LAST,
                party.name,
                party.short_name
            """
        )
        parties = []
        for row in cur.fetchall():
            current_representative_count = int(row[5] or 0)
            if current_representative_count <= 0 and not include_without_current_representatives:
                continue
            party = {
                "id": row[0],
                "name": row[1],
                "short_name": row[2],
                "jurisdiction_code": row[3],
                "jurisdiction_level": row[4],
                "current_representative_count": current_representative_count,
            }
            if not party_entity_name_patterns(party):
                continue
            parties.append(party)
        return parties


def _candidate_rows_for_party(
    conn,
    party: dict[str, Any],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    patterns = party_entity_name_patterns(party)
    if not patterns:
        return []
    pattern_clause = " OR ".join(["entity.canonical_name ILIKE %s" for _ in patterns])
    limit_clause = "LIMIT %s" if limit is not None else ""
    params: list[Any] = [*patterns, party["id"]]
    if limit is not None:
        params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                entity.id AS entity_id,
                entity.canonical_name,
                entity.normalized_name,
                entity.entity_type,
                evidence.source_document_id,
                evidence.external_key AS evidence_event_external_key,
                evidence.source_ref AS evidence_source_ref,
                evidence.return_type AS evidence_return_type,
                evidence.event_date AS evidence_event_date,
                evidence.reporting_period AS evidence_reporting_period,
                evidence.amount AS evidence_amount,
                evidence.amount_status AS evidence_amount_status,
                count(DISTINCT influence_event.id) AS influence_event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                ) AS reported_amount_total,
                bool_or(
                    influence_event.metadata->>'return_type' = 'Associated Entity Return'
                ) AS has_associated_entity_return,
                bool_or(
                    influence_event.metadata->>'return_type' IN (
                        'Associated Entity Return',
                        'Political Party Return'
                    )
                ) AS has_party_or_associated_return,
                array_remove(
                    array_agg(DISTINCT influence_event.metadata->>'return_type'),
                    NULL
                ) AS return_types
            FROM entity
            JOIN influence_event
              ON (
                    influence_event.source_entity_id = entity.id
                    OR influence_event.recipient_entity_id = entity.id
                 )
             AND influence_event.event_family = 'money'
             AND influence_event.review_status <> 'rejected'
            JOIN LATERAL (
                SELECT
                    evidence_event.source_document_id,
                    evidence_event.external_key,
                    evidence_event.source_ref,
                    evidence_event.metadata->>'return_type' AS return_type,
                    evidence_event.event_date,
                    evidence_event.reporting_period,
                    evidence_event.amount,
                    evidence_event.amount_status
                FROM influence_event evidence_event
                WHERE evidence_event.event_family = 'money'
                  AND evidence_event.review_status <> 'rejected'
                  AND (
                        evidence_event.source_entity_id = entity.id
                        OR evidence_event.recipient_entity_id = entity.id
                  )
                ORDER BY
                    CASE
                        WHEN evidence_event.metadata->>'return_type' = 'Associated Entity Return'
                        THEN 0
                        WHEN evidence_event.metadata->>'return_type' = 'Political Party Return'
                        THEN 1
                        ELSE 2
                    END,
                    CASE WHEN evidence_event.amount_status = 'reported' THEN 0 ELSE 1 END,
                    evidence_event.amount DESC NULLS LAST,
                    evidence_event.event_date DESC NULLS LAST,
                    evidence_event.reporting_period DESC NULLS LAST,
                    evidence_event.external_key,
                    evidence_event.id
                LIMIT 1
            ) evidence ON true
            WHERE ({pattern_clause})
              AND NOT EXISTS (
                  SELECT 1
                  FROM party_entity_link existing
                  WHERE existing.party_id = %s
                    AND existing.entity_id = entity.id
              )
            GROUP BY
                entity.id,
                entity.canonical_name,
                entity.normalized_name,
                entity.entity_type,
                evidence.source_document_id,
                evidence.external_key,
                evidence.source_ref,
                evidence.return_type,
                evidence.event_date,
                evidence.reporting_period,
                evidence.amount,
                evidence.amount_status
            ORDER BY
                reported_amount_total DESC NULLS LAST,
                influence_event_count DESC,
                entity.canonical_name
            {limit_clause}
            """,
            tuple(params),
        )
        rows = cur.fetchall()
    candidates: list[dict[str, Any]] = []
    party_name = _normalize_text(str(party.get("name") or ""))
    for row in rows:
        (
            entity_id,
            canonical_name,
            normalized_name,
            entity_type,
            source_document_id,
            evidence_event_external_key,
            evidence_source_ref,
            evidence_return_type,
            evidence_event_date,
            evidence_reporting_period,
            evidence_amount,
            evidence_amount_status,
            influence_event_count,
            reported_amount_total,
            has_associated_entity_return,
            has_party_or_associated_return,
            return_types,
        ) = row
        if not _party_candidate_matches_entity(party, str(canonical_name or normalized_name or "")):
            continue
        if not has_party_or_associated_return and entity_type != "political_party":
            continue
        normalized_entity = _normalize_text(str(normalized_name or canonical_name or ""))
        if has_associated_entity_return:
            link_type = "associated_entity"
        elif entity_type == "political_party" or (
            party_name and normalized_entity.startswith(party_name)
        ):
            link_type = "party_branch"
        else:
            link_type = "party_campaigner"
        candidates.append(
            {
                "entity_id": int(entity_id),
                "canonical_name": canonical_name,
                "normalized_name": normalized_name,
                "entity_type": entity_type,
                "source_document_id": source_document_id,
                "influence_event_count": int(influence_event_count or 0),
                "reported_amount_total": (
                    str(reported_amount_total) if reported_amount_total is not None else None
                ),
                "has_associated_entity_return": bool(has_associated_entity_return),
                "return_types": sorted(str(item) for item in (return_types or []) if item),
                "candidate_evidence_event": {
                    "external_key": evidence_event_external_key,
                    "source_ref": evidence_source_ref,
                    "return_type": evidence_return_type,
                    "event_date": evidence_event_date.isoformat()
                    if evidence_event_date is not None
                    else None,
                    "reporting_period": evidence_reporting_period,
                    "amount": str(evidence_amount) if evidence_amount is not None else None,
                    "amount_status": evidence_amount_status,
                },
                "link_type": link_type,
                "matched_patterns": patterns,
            }
        )
    return candidates


def _delete_refreshable_generated_candidates(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM party_entity_link
            WHERE review_status = 'needs_review'
              AND metadata->>'candidate_generator' = %s
              AND NOT (metadata ? 'last_manual_review_decision_id')
            """,
            (PARSER_NAME,),
        )
        return cur.rowcount


def materialize_party_entity_link_candidates(
    conn,
    *,
    limit_per_party: int | None = None,
    include_without_current_representatives: bool = False,
) -> dict[str, Any]:
    parties = _parties(
        conn,
        include_without_current_representatives=include_without_current_representatives,
    )
    candidates_seen = 0
    inserted_or_refreshed = 0
    skipped_existing = 0
    stale_candidates_deleted = _delete_refreshable_generated_candidates(conn)
    link_type_counts: Counter[str] = Counter()
    party_counts: Counter[str] = Counter()
    evidence_note = (
        "Candidate generated from party-name family patterns and AEC money-flow context; "
        "human review must verify the party/entity relationship before publication as a "
        "reviewed link."
    )

    for party in parties:
        for candidate in _candidate_rows_for_party(conn, party, limit=limit_per_party):
            candidates_seen += 1
            link_type_counts[candidate["link_type"]] += 1
            party_label = str(party.get("short_name") or party.get("name") or party["id"])
            party_counts[party_label] += 1
            metadata = {
                "candidate_generator": PARSER_NAME,
                "parser_version": PARSER_VERSION,
                "party_snapshot": {
                    "id": party["id"],
                    "name": party["name"],
                    "short_name": party["short_name"],
                    "jurisdiction_code": party["jurisdiction_code"],
                    "jurisdiction_level": party["jurisdiction_level"],
                    "current_representative_count": party["current_representative_count"],
                },
                "entity_snapshot": {
                    "id": candidate["entity_id"],
                    "canonical_name": candidate["canonical_name"],
                    "normalized_name": candidate["normalized_name"],
                    "entity_type": candidate["entity_type"],
                },
                "matched_patterns": candidate["matched_patterns"],
                "influence_event_count": candidate["influence_event_count"],
                "reported_amount_total": candidate["reported_amount_total"],
                "return_types": candidate["return_types"],
                "candidate_evidence_event": candidate["candidate_evidence_event"],
                "candidate_caveat": (
                    "This is a review candidate only. It is not accepted evidence of a "
                    "party/entity relationship until review_status is reviewed."
                ),
            }
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO party_entity_link (
                        party_id, entity_id, link_type, method, confidence,
                        review_status, evidence_note, source_document_id, metadata
                    )
                    VALUES (
                        %s, %s, %s, 'rule_based', 'unreviewed_candidate',
                        'needs_review', %s, %s, %s
                    )
                    ON CONFLICT (party_id, entity_id, link_type)
                    DO UPDATE SET
                        method = EXCLUDED.method,
                        confidence = EXCLUDED.confidence,
                        evidence_note = COALESCE(
                            party_entity_link.evidence_note,
                            EXCLUDED.evidence_note
                        ),
                        source_document_id = COALESCE(
                            party_entity_link.source_document_id,
                            EXCLUDED.source_document_id
                        ),
                        metadata = party_entity_link.metadata || EXCLUDED.metadata
                    WHERE party_entity_link.review_status = 'needs_review'
                    """,
                    (
                        party["id"],
                        candidate["entity_id"],
                        candidate["link_type"],
                        evidence_note,
                        candidate["source_document_id"],
                        Jsonb(metadata),
                    ),
                )
                if cur.rowcount == 1:
                    inserted_or_refreshed += 1
                else:
                    skipped_existing += 1
    conn.commit()
    return {
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "parties_seen": len(parties),
        "include_without_current_representatives": include_without_current_representatives,
        "candidates_seen": candidates_seen,
        "candidates_inserted_or_refreshed": inserted_or_refreshed,
        "candidates_skipped_existing_review_state": skipped_existing,
        "stale_generated_candidates_deleted": stale_candidates_deleted,
        "link_type_counts": dict(sorted(link_type_counts.items())),
        "party_counts": dict(sorted(party_counts.items())),
        "caveat": (
            "Rows materialized by this step are review candidates only. Accepted public "
            "claims require a reviewed party_entity_link decision with supporting sources."
        ),
    }
