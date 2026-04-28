from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from au_politics_money.config import AUDIT_DIR
from au_politics_money.db.load import connect


PARSER_NAME = "sector_policy_link_suggestions_v1"
PARSER_VERSION = "1"
OUTPUT_DIR = AUDIT_DIR / "sector_policy_link_suggestions"


@dataclass(frozen=True)
class SectorPolicyRule:
    rule_id: str
    public_sector: str
    relationship: str
    confidence: str
    include_terms: tuple[str, ...]
    exclude_terms: tuple[str, ...] = ()
    evidence_note_template: str = ""


RULES: tuple[SectorPolicyRule, ...] = (
    SectorPolicyRule(
        rule_id="fossil_fuels_direct_policy_terms_v1",
        public_sector="fossil_fuels",
        relationship="direct_material_interest",
        confidence="0.850",
        include_terms=(
            "fossil fuel",
            "fossil fuels",
            "coal",
            "natural gas",
            "gas-fired",
            "gas industry",
            "emissions",
            "net zero",
            "climate change",
        ),
        evidence_note_template=(
            "Candidate link: the policy topic text directly concerns fossil fuels, coal, gas, "
            "or emissions policy. Human review must add an independent source showing the "
            "sector's material interest before accepting."
        ),
    ),
    SectorPolicyRule(
        rule_id="mining_direct_policy_terms_v1",
        public_sector="mining",
        relationship="direct_material_interest",
        confidence="0.800",
        include_terms=("mining", "coal industry", "coal seam", "shale gas", "mineral resources"),
        evidence_note_template=(
            "Candidate link: the policy topic text directly concerns mining/resources. Human "
            "review must add an independent source showing the sector's material interest "
            "before accepting."
        ),
    ),
    SectorPolicyRule(
        rule_id="renewable_energy_climate_transition_terms_v1",
        public_sector="renewable_energy",
        relationship="indirect_material_interest",
        confidence="0.650",
        include_terms=("net zero", "emissions", "climate change", "investment in fossil fuels"),
        evidence_note_template=(
            "Candidate link: the policy topic concerns climate or energy-transition settings "
            "that may materially affect renewable energy interests. Human review must add a "
            "sector-material-interest source before accepting."
        ),
    ),
    SectorPolicyRule(
        rule_id="finance_tax_concession_terms_v1",
        public_sector="finance",
        relationship="indirect_material_interest",
        confidence="0.600",
        include_terms=("tax concessions", "high earners"),
        evidence_note_template=(
            "Candidate link: the policy topic concerns tax or investment settings that may "
            "affect finance/investment interests. Human review must confirm scope and add "
            "sector-material-interest evidence before accepting."
        ),
    ),
    SectorPolicyRule(
        rule_id="healthcare_service_access_terms_v1",
        public_sector="healthcare",
        relationship="general_interest",
        confidence="0.550",
        include_terms=("healthcare", "healthy lives"),
        evidence_note_template=(
            "Candidate link: the policy topic text references healthcare/service access. Human "
            "review must confirm the sector relationship and add sector-material-interest "
            "evidence before accepting."
        ),
    ),
    SectorPolicyRule(
        rule_id="law_justice_legal_system_terms_v1",
        public_sector="law",
        relationship="general_interest",
        confidence="0.500",
        include_terms=(
            "legal protections",
            "criminal justice",
            "procedural fairness",
            "mandatory minimum",
            "character test",
        ),
        evidence_note_template=(
            "Candidate link: the policy topic concerns legal procedure, criminal justice, or "
            "legal rights. Human review must confirm whether this is materially relevant to "
            "legal-sector interests before accepting."
        ),
    ),
    SectorPolicyRule(
        rule_id="technology_online_speech_terms_v1",
        public_sector="technology",
        relationship="general_interest",
        confidence="0.500",
        include_terms=("hate speech", "political communication", "online platform"),
        evidence_note_template=(
            "Candidate link: the policy topic may affect online/platform communication. Human "
            "review must confirm scope and add sector-material-interest evidence before "
            "accepting."
        ),
    ),
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _term_matches(text: str, term: str) -> bool:
    escaped = re.escape(_normalize_text(term))
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _policy_url(topic: dict[str, Any]) -> str:
    tvfy_id = (topic.get("metadata") or {}).get("they_vote_for_you_policy_id")
    if tvfy_id in ("", None):
        return ""
    return f"https://theyvoteforyou.org.au/policies/{tvfy_id}"


def _subject_external_key(
    *,
    public_sector: str,
    topic_slug: str,
    relationship: str,
    method: str,
) -> str:
    return f"sector_policy_topic_link:{public_sector}:{topic_slug}:{relationship}:{method}"


def _suggestion_fingerprint(payload: dict[str, Any]) -> str:
    parts = [
        str(payload["public_sector"]),
        str(payload["relationship"]),
        str(payload["confidence"]),
        str(payload["topic_slug"]),
        str(payload["topic_label"]),
        str(payload.get("topic_description") or ""),
        str(payload["rule_id"]),
        ",".join(payload["matched_terms"]),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def suggest_links_for_topic(topic: dict[str, Any]) -> list[dict[str, Any]]:
    text = _normalize_text(f"{topic.get('label') or ''} {topic.get('description') or ''}")
    suggestions = []
    for rule in RULES:
        if any(_term_matches(text, term) for term in rule.exclude_terms):
            continue
        matched_terms = [term for term in rule.include_terms if _term_matches(text, term)]
        if not matched_terms:
            continue
        method = "model_assisted"
        topic_slug = str(topic["slug"])
        public_sector = rule.public_sector
        relationship = rule.relationship
        subject_external_key = _subject_external_key(
            public_sector=public_sector,
            topic_slug=topic_slug,
            relationship=relationship,
            method=method,
        )
        evidence_note = rule.evidence_note_template
        payload = {
            "schema_version": "sector_policy_link_suggestion_v1",
            "parser_name": PARSER_NAME,
            "parser_version": PARSER_VERSION,
            "review_subject_type": "sector_policy_topic_link",
            "subject_external_key": subject_external_key,
            "public_sector": public_sector,
            "relationship": relationship,
            "method": method,
            "confidence": rule.confidence,
            "rule_id": rule.rule_id,
            "matched_terms": matched_terms,
            "topic_id": topic["id"],
            "topic_slug": topic_slug,
            "topic_label": topic["label"],
            "topic_description": topic.get("description") or "",
            "topic_source": (topic.get("metadata") or {}).get("source"),
            "topic_source_evidence_class": (topic.get("metadata") or {}).get(
                "source_evidence_class"
            ),
            "topic_url": _policy_url(topic),
            "evidence_note": evidence_note,
            "review_status": "suggested_needs_human_evidence_review",
            "missing_review_requirements": [
                "Reviewer must verify topic scope against the topic/division source.",
                (
                    "Reviewer must add an independent source showing the sector's material "
                    "interest before importing as accept/revise."
                ),
            ],
            "draft_review_decision": {
                "subject_type": "sector_policy_topic_link",
                "subject_external_key": subject_external_key,
                "decision": "needs_more_evidence",
                "reviewer": "",
                "evidence_note": evidence_note,
                "proposed_changes": {
                    "public_sector": public_sector,
                    "topic_slug": topic_slug,
                    "relationship": relationship,
                    "method": method,
                    "confidence": rule.confidence,
                    "evidence_note": evidence_note,
                },
                "supporting_sources": [
                    {
                        "evidence_role": "topic_scope",
                        "url": _policy_url(topic),
                        "note": "Review the topic and linked divisions before accepting.",
                    },
                    {
                        "evidence_role": "sector_material_interest",
                        "url": "",
                        "note": (
                            "Reviewer must add a specific official, academic, regulator, "
                            "company, or industry source before accepting."
                        ),
                    },
                ],
            },
        }
        payload["suggestion_fingerprint"] = _suggestion_fingerprint(payload)
        suggestions.append(payload)
    return suggestions


def _policy_topics(conn, limit: int | None = None) -> list[dict[str, Any]]:
    limit_clause = "LIMIT %s" if limit is not None else ""
    params: tuple[Any, ...] = (limit,) if limit is not None else ()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT id, slug, label, description, metadata
            FROM policy_topic
            ORDER BY slug
            {limit_clause}
            """,
            params,
        )
        return [dict(row) for row in cur.fetchall()]


def export_sector_policy_link_suggestions(
    *,
    database_url: str | None = None,
    limit: int | None = None,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    generated_at = _timestamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{generated_at}.jsonl"
    summary_path = output_dir / f"{generated_at}.summary.json"

    with connect(database_url) as conn:
        topics = _policy_topics(conn, limit=limit)
    suggestions = [
        suggestion
        for topic in topics
        for suggestion in suggest_links_for_topic(topic)
    ]
    suggestions.sort(
        key=lambda item: (
            item["public_sector"],
            item["topic_slug"],
            item["relationship"],
            item["rule_id"],
        )
    )

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for suggestion in suggestions:
            handle.write(json.dumps(suggestion, sort_keys=True) + "\n")

    sector_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    for suggestion in suggestions:
        sector_counts[suggestion["public_sector"]] = sector_counts.get(
            suggestion["public_sector"], 0
        ) + 1
        topic_counts[suggestion["topic_slug"]] = topic_counts.get(suggestion["topic_slug"], 0) + 1

    summary = {
        "schema_version": "sector_policy_link_suggestions_summary_v1",
        "generated_at": generated_at,
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "jsonl_path": str(jsonl_path),
        "policy_topic_count": len(topics),
        "suggestion_count": len(suggestions),
        "sector_counts": dict(sorted(sector_counts.items())),
        "topic_counts": dict(sorted(topic_counts.items())),
        "rule_count": len(RULES),
        "rules": [asdict(rule) for rule in RULES],
        "caveat": (
            "Suggestions are review prompts only. They do not create "
            "sector_policy_topic_link rows and do not assert causation, quid pro quo, "
            "or improper conduct."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
