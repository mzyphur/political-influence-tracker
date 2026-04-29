from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from au_politics_money.config import AUDIT_DIR
from au_politics_money.db.load import (
    DEFAULT_COASTLINE_REPAIR_BUFFER_METERS,
    MAX_COASTLINE_REPAIR_BUFFER_METERS,
    apply_migrations,
    connect,
    load_electorate_boundary_display_geometries,
    load_influence_events,
    load_processed_artifacts,
    load_postcode_electorate_crosswalk,
    load_qld_ecq_eds_contexts,
    load_qld_ecq_eds_money_flows,
    load_qld_ecq_eds_participants,
)
from au_politics_money.db.review import (
    REVIEW_SUBJECT_TYPES,
    export_review_queue,
    import_review_decisions,
    reapply_review_decisions,
    review_queue_names,
)
from au_politics_money.db.party_entity_suggestions import materialize_party_entity_link_candidates
from au_politics_money.db.quality import (
    ServingDatabaseQualityConfig,
    run_serving_database_quality_checks,
)
from au_politics_money.db.sector_policy_suggestions import export_sector_policy_link_suggestions
from au_politics_money.ingest.discovered_sources import (
    child_source_id,
    source_from_discovered_link,
)
from au_politics_money.ingest.aec_boundaries import (
    extract_current_aec_boundaries,
    fetch_current_aec_boundary_zip,
)
from au_politics_money.ingest.aec_electorate_finder import (
    fetch_aec_electorate_finder_postcodes,
    normalize_aec_electorate_finder_postcodes,
)
from au_politics_money.ingest.entity_classification import classify_entity_names
from au_politics_money.ingest.discovery import (
    discover_links_from_body,
    latest_body_path,
    latest_discovered_links_path,
    read_discovered_links,
    write_discovered_links,
)
from au_politics_money.ingest.aec_annual import (
    normalize_aec_annual_money_flows,
    summarize_aec_annual_zip,
)
from au_politics_money.ingest.aec_election import (
    normalize_aec_election_money_flows,
    summarize_aec_election_zip,
)
from au_politics_money.ingest.aec_public_funding import normalize_aec_public_funding
from au_politics_money.ingest.aph_decision_records import (
    DECISION_RECORD_SOURCE_IDS,
    extract_aph_decision_record_index,
    fetch_aph_decision_record_documents,
)
from au_politics_money.ingest.aph_official_divisions import extract_official_aph_divisions
from au_politics_money.ingest.aph_roster import build_current_parliament_roster
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.house_interests import extract_house_interest_sections
from au_politics_money.ingest.house_interest_records import extract_house_interest_records
from au_politics_money.ingest.land_mask import (
    extract_aims_australian_coastline_land_mask,
    extract_natural_earth_country_land_mask,
    extract_natural_earth_physical_land_mask,
    fetch_aims_australian_coastline_zip,
    fetch_natural_earth_admin0_zip,
    fetch_natural_earth_physical_land_zip,
)
from au_politics_money.ingest.official_identifiers import (
    AbnLookupWebServiceError,
    MissingAbnLookupGuid,
    discover_official_identifier_sources,
    extract_official_identifiers_from_file,
    fetch_abn_lookup_web_record,
    fetch_lobbyist_register_snapshot,
)
from au_politics_money.ingest.pdf_text import extract_pdf_text_batch
from au_politics_money.ingest.qld_ecq_eds import (
    QLD_ECQ_EDS_EXPORTS,
    fetch_qld_ecq_eds_exports,
    normalize_qld_ecq_eds_contexts,
    normalize_qld_ecq_eds_money_flows,
    normalize_qld_ecq_eds_participants,
)
from au_politics_money.ingest.senate_interests import (
    extract_senate_interest_records,
    fetch_senate_interest_statements,
)
from au_politics_money.ingest.sources import all_sources, get_source
from au_politics_money.ingest.they_vote_for_you import (
    MissingTheyVoteForYouApiKey,
    extract_they_vote_for_you_divisions,
    fetch_they_vote_for_you_divisions,
    fetch_they_vote_for_you_people,
)
from au_politics_money.models import DiscoveredLink, SourceRecord
from au_politics_money.pipeline import run_federal_foundation_pipeline


def list_sources() -> int:
    for source in all_sources():
        print(
            f"{source.source_id}\t{source.priority}\t{source.jurisdiction}\t"
            f"{source.source_type}\t{source.name}"
        )
    return 0


def coastline_repair_buffer_arg(value: str) -> int:
    try:
        buffer_meters = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer number of metres") from exc
    if buffer_meters < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    if buffer_meters > MAX_COASTLINE_REPAIR_BUFFER_METERS:
        raise argparse.ArgumentTypeError(
            f"must be no greater than {MAX_COASTLINE_REPAIR_BUFFER_METERS} metres"
        )
    return buffer_meters


def show_source(source_id: str) -> int:
    source = get_source(source_id)
    print(json.dumps(source.to_dict(), indent=2, sort_keys=True))
    return 0


def fetch_source_command(source_id: str) -> int:
    source = get_source(source_id)
    metadata_path = fetch_source(source)
    print(str(Path(metadata_path).resolve()))
    return 0


def discover_links_command(source_id: str) -> int:
    source = get_source(source_id)
    body_path = latest_body_path(source.source_id)
    if body_path is None:
        fetch_source(source)
        body_path = latest_body_path(source.source_id)
    if body_path is None:
        raise FileNotFoundError(f"No raw body found for source {source.source_id}")

    links = discover_links_from_body(source, body_path)
    output_path = write_discovered_links(source, links)
    print(f"{len(links)} links")
    print(str(Path(output_path).resolve()))
    return 0


def _child_source_id(parent_source_id: str, link: DiscoveredLink) -> str:
    return child_source_id(parent_source_id, link)


def _source_from_discovered_link(parent: SourceRecord, link: DiscoveredLink) -> SourceRecord:
    return source_from_discovered_link(parent, link)


def fetch_discovered_command(source_id: str, link_type: str | None, limit: int | None) -> int:
    parent = get_source(source_id)
    links_path = latest_discovered_links_path(parent.source_id)
    if links_path is None:
        discover_links_command(parent.source_id)
        links_path = latest_discovered_links_path(parent.source_id)
    if links_path is None:
        raise FileNotFoundError(f"No discovered links found for source {parent.source_id}")

    links = read_discovered_links(links_path)
    if link_type:
        links = [link for link in links if link.link_type == link_type]
    if limit is not None:
        links = links[:limit]

    for link in links:
        child_source = _source_from_discovered_link(parent, link)
        metadata_path = fetch_source(child_source)
        print(str(Path(metadata_path).resolve()))

    print(f"fetched {len(links)} links")
    return 0


def build_roster_command() -> int:
    roster_path = build_current_parliament_roster()
    print(str(Path(roster_path).resolve()))
    return 0


def extract_pdf_text_command(prefix: str, limit: int | None) -> int:
    summary_path = extract_pdf_text_batch(prefix=prefix, limit=limit)
    print(str(Path(summary_path).resolve()))
    return 0


def summarize_aec_annual_command(sample_size: int) -> int:
    summary_path = summarize_aec_annual_zip(sample_size=sample_size)
    print(str(Path(summary_path).resolve()))
    return 0


def normalize_aec_annual_command() -> int:
    summary_path = normalize_aec_annual_money_flows()
    print(str(Path(summary_path).resolve()))
    return 0


def summarize_aec_election_command(sample_size: int) -> int:
    summary_path = summarize_aec_election_zip(sample_size=sample_size)
    print(str(Path(summary_path).resolve()))
    return 0


def normalize_aec_election_command() -> int:
    summary_path = normalize_aec_election_money_flows()
    print(str(Path(summary_path).resolve()))
    return 0


def normalize_aec_public_funding_command() -> int:
    summary_path = normalize_aec_public_funding()
    print(str(Path(summary_path).resolve()))
    return 0


def _postcode_inputs(postcodes: list[str] | None, postcodes_file: str | None) -> list[str]:
    values = list(postcodes or [])
    if postcodes_file:
        for line in Path(postcodes_file).read_text(encoding="utf-8").splitlines():
            cleaned = line.split("#", maxsplit=1)[0].strip()
            if cleaned:
                values.append(cleaned)
    return values


def fetch_aec_electorate_finder_postcodes_command(
    postcodes: list[str],
    postcodes_file: str | None,
    refetch: bool,
) -> int:
    summary_path = fetch_aec_electorate_finder_postcodes(
        _postcode_inputs(postcodes, postcodes_file),
        refetch=refetch,
    )
    print(str(Path(summary_path).resolve()))
    return 0


def normalize_aec_electorate_finder_postcodes_command(
    postcodes: list[str] | None,
    postcodes_file: str | None,
) -> int:
    requested_postcodes = _postcode_inputs(postcodes, postcodes_file)
    summary_path = normalize_aec_electorate_finder_postcodes(requested_postcodes or None)
    print(str(Path(summary_path).resolve()))
    return 0


def fetch_qld_ecq_eds_exports_command(export_names: list[str] | None) -> int:
    summary_path = fetch_qld_ecq_eds_exports(export_names=export_names)
    print(str(Path(summary_path).resolve()))
    return 0


def normalize_qld_ecq_eds_money_flows_command() -> int:
    summary_path = normalize_qld_ecq_eds_money_flows()
    print(str(Path(summary_path).resolve()))
    return 0


def normalize_qld_ecq_eds_participants_command() -> int:
    summary_path = normalize_qld_ecq_eds_participants()
    print(str(Path(summary_path).resolve()))
    return 0


def normalize_qld_ecq_eds_contexts_command() -> int:
    summary_path = normalize_qld_ecq_eds_contexts()
    print(str(Path(summary_path).resolve()))
    return 0


def extract_house_interest_sections_command() -> int:
    summary_path = extract_house_interest_sections()
    print(str(Path(summary_path).resolve()))
    return 0


def extract_house_interest_records_command() -> int:
    summary_path = extract_house_interest_records()
    print(str(Path(summary_path).resolve()))
    return 0


def fetch_senate_interests_api_command(limit: int | None) -> int:
    summary_path = fetch_senate_interest_statements(limit=limit)
    print(str(Path(summary_path).resolve()))
    return 0


def extract_senate_interest_records_command() -> int:
    summary_path = extract_senate_interest_records()
    print(str(Path(summary_path).resolve()))
    return 0


def fetch_they_vote_for_you_people_command() -> int:
    try:
        summary_path = fetch_they_vote_for_you_people()
    except MissingTheyVoteForYouApiKey as exc:
        print(str(exc))
        return 2
    print(str(Path(summary_path).resolve()))
    return 0


def fetch_they_vote_for_you_divisions_command(
    start_date: str | None,
    end_date: str | None,
    house: str | None,
    limit: int | None,
    allow_truncated: bool,
) -> int:
    try:
        summary_path = fetch_they_vote_for_you_divisions(
            start_date=start_date,
            end_date=end_date,
            house=house,
            limit=limit,
            allow_truncated=allow_truncated,
        )
    except MissingTheyVoteForYouApiKey as exc:
        print(str(exc))
        return 2
    print(str(Path(summary_path).resolve()))
    return 0


def extract_they_vote_for_you_divisions_command(fetch_summary_path: str | None) -> int:
    summary_path = extract_they_vote_for_you_divisions(
        Path(fetch_summary_path) if fetch_summary_path else None
    )
    print(str(Path(summary_path).resolve()))
    return 0


def classify_entities_command() -> int:
    summary_path = classify_entity_names()
    print(str(Path(summary_path).resolve()))
    return 0


def fetch_current_aec_boundaries_command(refetch: bool) -> int:
    metadata_path = fetch_current_aec_boundary_zip(refetch=refetch)
    print(str(Path(metadata_path).resolve()))
    return 0


def extract_aec_boundaries_command(metadata_path: str | None) -> int:
    summary_path = extract_current_aec_boundaries(
        metadata_path=Path(metadata_path) if metadata_path else None,
    )
    print(str(Path(summary_path).resolve()))
    return 0


def fetch_natural_earth_land_mask_command(refetch: bool) -> int:
    for metadata_path in (
        fetch_natural_earth_admin0_zip(refetch=refetch),
        fetch_natural_earth_physical_land_zip(refetch=refetch),
    ):
        print(str(Path(metadata_path).resolve()))
    return 0


def extract_natural_earth_land_mask_command(country_name: str) -> int:
    for summary_path in (
        extract_natural_earth_country_land_mask(country_name=country_name),
        extract_natural_earth_physical_land_mask(country_name=country_name),
    ):
        print(str(Path(summary_path).resolve()))
    return 0


def fetch_aims_coastline_land_mask_command(refetch: bool) -> int:
    print(str(fetch_aims_australian_coastline_zip(refetch=refetch).resolve()))
    return 0


def extract_aims_coastline_land_mask_command(country_name: str) -> int:
    summary_path = extract_aims_australian_coastline_land_mask(country_name=country_name)
    print(str(Path(summary_path).resolve()))
    return 0


def load_display_geometries_command(
    boundary_set: str | None,
    country_name: str,
    coastline_repair_buffer_meters: int,
) -> int:
    with connect() as conn:
        summary = load_electorate_boundary_display_geometries(
            conn,
            boundary_set=boundary_set or "aec_federal_2025_current",
            country_name=country_name,
            coastline_repair_buffer_meters=coastline_repair_buffer_meters,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def extract_aph_decision_record_index_command(source_id: str | None, all_sources: bool) -> int:
    source_ids = DECISION_RECORD_SOURCE_IDS if all_sources or source_id is None else (source_id,)
    for selected_source_id in source_ids:
        summary_path = extract_aph_decision_record_index(selected_source_id)
        print(str(Path(summary_path).resolve()))
    return 0


def fetch_aph_decision_record_documents_command(
    *,
    include_html: bool,
    include_pdf: bool,
    only_missing: bool,
    limit: int | None,
) -> int:
    summary_path = fetch_aph_decision_record_documents(
        include_html=include_html,
        include_pdf=include_pdf,
        only_missing=only_missing,
        limit=limit,
    )
    print(str(Path(summary_path).resolve()))
    return 0


def extract_official_aph_divisions_command() -> int:
    summary_path = extract_official_aph_divisions()
    print(str(Path(summary_path).resolve()))
    return 0


def discover_official_identifier_sources_command() -> int:
    summary_path = discover_official_identifier_sources()
    print(str(Path(summary_path).resolve()))
    return 0


def fetch_lobbyist_register_command(limit: int | None) -> int:
    summary_path = fetch_lobbyist_register_snapshot(limit=limit)
    print(str(Path(summary_path).resolve()))
    return 0


def extract_official_identifiers_command(
    source_id: str,
    input_path: str,
    limit: int | None,
) -> int:
    jsonl_path = extract_official_identifiers_from_file(
        source_id,
        Path(input_path),
        limit=limit,
    )
    print(str(Path(jsonl_path).resolve()))
    return 0


def fetch_abn_lookup_web_command(
    lookup_type: str,
    lookup_value: str,
    include_historical_details: bool,
) -> int:
    try:
        summary_path = fetch_abn_lookup_web_record(
            lookup_type,
            lookup_value,
            include_historical_details=include_historical_details,
        )
    except MissingAbnLookupGuid as exc:
        print(str(exc))
        return 2
    except AbnLookupWebServiceError as exc:
        print(str(exc))
        return 2
    print(str(Path(summary_path).resolve()))
    return 0


def run_pipeline_command(
    smoke: bool,
    refresh_existing_sources: bool,
    skip_house_pdfs: bool,
    skip_pdf_text: bool,
    include_votes: bool,
    votes_start_date: str | None,
    votes_end_date: str | None,
) -> int:
    manifest_path = run_federal_foundation_pipeline(
        smoke=smoke,
        refresh_existing_sources=refresh_existing_sources,
        skip_house_pdfs=skip_house_pdfs,
        skip_pdf_text=skip_pdf_text,
        include_votes=include_votes,
        votes_start_date=votes_start_date,
        votes_end_date=votes_end_date,
    )
    print(str(Path(manifest_path).resolve()))
    return 0


def load_postgres_command(
    apply_schema_first: bool,
    skip_roster: bool,
    skip_money_flows: bool,
    skip_qld_ecq: bool,
    skip_house_interests: bool,
    skip_senate_interests: bool,
    skip_electorate_boundaries: bool,
    skip_influence_events: bool,
    skip_entity_classifications: bool,
    skip_official_identifiers: bool,
    skip_official_decision_records: bool,
    skip_official_decision_record_documents: bool,
    skip_official_aph_divisions: bool,
    include_vote_divisions: bool,
    skip_postcode_crosswalk: bool,
    skip_party_entity_links: bool,
    skip_review_reapply: bool,
) -> int:
    summary = load_processed_artifacts(
        apply_schema_first=apply_schema_first,
        include_roster=not skip_roster,
        include_money_flows=not skip_money_flows,
        include_qld_ecq=not skip_qld_ecq,
        include_house_interests=not skip_house_interests,
        include_senate_interests=not skip_senate_interests,
        include_electorate_boundaries=not skip_electorate_boundaries,
        include_influence_events=not skip_influence_events,
        include_entity_classifications=not skip_entity_classifications,
        include_official_identifiers=not skip_official_identifiers,
        include_official_decision_records=not skip_official_decision_records,
        include_official_decision_record_documents=not skip_official_decision_record_documents,
        include_official_aph_divisions=not skip_official_aph_divisions,
        include_vote_divisions=include_vote_divisions,
        include_postcode_crosswalk=not skip_postcode_crosswalk,
        include_party_entity_links=not skip_party_entity_links,
        reapply_reviews=not skip_review_reapply,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def migrate_postgres_command() -> int:
    with connect() as conn:
        summary = apply_migrations(conn)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def load_qld_ecq_eds_money_flows_command(skip_influence_events: bool) -> int:
    with connect() as conn:
        summary: dict[str, object] = {
            "qld_ecq_eds_money_flows": load_qld_ecq_eds_money_flows(conn),
            "qld_ecq_eds_participants": load_qld_ecq_eds_participants(conn),
            "qld_ecq_eds_contexts": load_qld_ecq_eds_contexts(conn),
        }
        if not skip_influence_events:
            summary["influence_events"] = load_influence_events(conn)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def load_qld_ecq_eds_participants_command() -> int:
    with connect() as conn:
        summary = load_qld_ecq_eds_participants(conn)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def load_qld_ecq_eds_contexts_command(skip_influence_events: bool) -> int:
    with connect() as conn:
        summary: dict[str, object] = {
            "qld_ecq_eds_contexts": load_qld_ecq_eds_contexts(conn),
        }
        if not skip_influence_events:
            summary["influence_events"] = load_influence_events(conn)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def load_postcode_electorate_crosswalk_command() -> int:
    with connect() as conn:
        summary = load_postcode_electorate_crosswalk(conn)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def export_review_queue_command(queue_name: str, limit: int | None) -> int:
    with connect() as conn:
        summary_path = export_review_queue(conn, queue_name, limit=limit)
    print(str(Path(summary_path).resolve()))
    return 0


def suggest_sector_policy_links_command(limit: int | None) -> int:
    summary_path = export_sector_policy_link_suggestions(limit=limit)
    print(str(Path(summary_path).resolve()))
    return 0


def materialize_party_entity_links_command(limit_per_party: int | None) -> int:
    with connect() as conn:
        summary = materialize_party_entity_link_candidates(conn, limit_per_party=limit_per_party)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def prepare_review_bundle_command(limit: int | None, limit_per_party: int | None) -> int:
    if limit is not None and limit < 1:
        raise ValueError("--limit must be positive when supplied.")
    if limit_per_party is not None and limit_per_party < 1:
        raise ValueError("--limit-per-party must be positive when supplied.")

    with connect() as conn:
        party_entity_materialize_summary = materialize_party_entity_link_candidates(
            conn,
            limit_per_party=limit_per_party,
        )
        official_match_queue_summary_path = export_review_queue(
            conn,
            "official-match-candidates",
            limit=limit,
        )
        benefit_event_queue_summary_path = export_review_queue(
            conn,
            "benefit-events",
            limit=limit,
        )
        entity_classification_queue_summary_path = export_review_queue(
            conn,
            "entity-classifications",
            limit=limit,
        )
        party_entity_queue_summary_path = export_review_queue(
            conn,
            "party-entity-links",
            limit=limit,
        )
        sector_policy_queue_summary_path = export_review_queue(
            conn,
            "sector-policy-links",
            limit=limit,
        )
    sector_policy_suggestions_summary_path = export_sector_policy_link_suggestions(limit=limit)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target_dir = AUDIT_DIR / "review_bundles"
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / f"federal_review_bundle_{timestamp}.summary.json"
    manifest = {
        "generated_at": timestamp,
        "schema_version": "review_bundle_manifest_v1",
        "description": (
            "Reproducible federal review bundle for official identifier matches, "
            "disclosed benefit events, entity-sector classifications, indirect "
            "party/entity paths, and sector-policy topic links. These files are "
            "review inputs only; public claims require accepted review decisions "
            "with supporting sources where required."
        ),
        "limit": limit,
        "limit_per_party": limit_per_party,
        "party_entity_materialize_summary": party_entity_materialize_summary,
        "official_match_queue_summary_path": str(official_match_queue_summary_path),
        "benefit_event_queue_summary_path": str(benefit_event_queue_summary_path),
        "entity_classification_queue_summary_path": str(entity_classification_queue_summary_path),
        "party_entity_queue_summary_path": str(party_entity_queue_summary_path),
        "sector_policy_queue_summary_path": str(sector_policy_queue_summary_path),
        "sector_policy_suggestions_summary_path": str(sector_policy_suggestions_summary_path),
        "review_rules": [
            "official_match_candidate accept/revise decisions attach official identifiers only through the allowlisted importer.",
            "benefit-events review confirms source text, missing provider/date/value labels, and whether extraction should be accepted, revised, rejected, or deferred.",
            "entity-classifications review creates manual classification rows rather than overwriting generated classifications.",
            "party_entity_link accept/revise decisions require supporting_sources with evidence_role='party_entity_relationship'.",
            "sector_policy_topic_link accept/revise decisions require supporting_sources with topic_scope and sector_material_interest evidence roles.",
            "Generated candidates do not mutate reviewed public graph claims until accepted decisions are imported.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(manifest_path.resolve()))
    return 0


def import_review_decisions_command(input_path: str, apply: bool) -> int:
    with connect() as conn:
        summary = import_review_decisions(conn, Path(input_path), apply=apply)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def reapply_review_decisions_command(
    apply: bool,
    subject_type: str | None,
    continue_on_error: bool,
) -> int:
    with connect() as conn:
        summary = reapply_review_decisions(
            conn,
            apply=apply,
            subject_type=subject_type,
            continue_on_error=continue_on_error,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def qa_serving_database_command(
    boundary_set: str,
    expected_house_boundary_count: int,
    max_official_unmatched_votes: int,
    min_current_influence_events: int,
    min_person_linked_influence_events: int,
    min_current_money_flows: int,
    min_current_gift_interests: int,
    min_current_house_office_terms: int,
    min_current_senate_office_terms: int,
) -> int:
    config = ServingDatabaseQualityConfig(
        boundary_set=boundary_set,
        expected_house_boundary_count=expected_house_boundary_count,
        max_official_unmatched_votes=max_official_unmatched_votes,
        min_current_influence_events=min_current_influence_events,
        min_person_linked_influence_events=min_person_linked_influence_events,
        min_current_money_flows=min_current_money_flows,
        min_current_gift_interests=min_current_gift_interests,
        min_current_house_office_terms=min_current_house_office_terms,
        min_current_senate_office_terms=min_current_senate_office_terms,
    )
    with connect() as conn:
        summary = run_serving_database_quality_checks(conn, config)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "pass" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="au-politics-money")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-sources")

    show_parser = subparsers.add_parser("show-source")
    show_parser.add_argument("source_id")

    fetch_parser = subparsers.add_parser("fetch-source")
    fetch_parser.add_argument("source_id")

    discover_parser = subparsers.add_parser("discover-links")
    discover_parser.add_argument("source_id")

    fetch_discovered_parser = subparsers.add_parser("fetch-discovered")
    fetch_discovered_parser.add_argument("source_id")
    fetch_discovered_parser.add_argument("--link-type")
    fetch_discovered_parser.add_argument("--limit", type=int)

    subparsers.add_parser("build-roster")

    pdf_text_parser = subparsers.add_parser("extract-pdf-text")
    pdf_text_parser.add_argument("--prefix", default="aph_members_interests_48__")
    pdf_text_parser.add_argument("--limit", type=int)

    aec_annual_parser = subparsers.add_parser("summarize-aec-annual")
    aec_annual_parser.add_argument("--sample-size", type=int, default=3)

    subparsers.add_parser("normalize-aec-annual-money-flows")

    aec_election_parser = subparsers.add_parser("summarize-aec-election")
    aec_election_parser.add_argument("--sample-size", type=int, default=3)

    subparsers.add_parser("normalize-aec-election-money-flows")

    subparsers.add_parser("normalize-aec-public-funding")

    aec_postcode_fetch_parser = subparsers.add_parser("fetch-aec-electorate-finder-postcodes")
    aec_postcode_fetch_parser.add_argument(
        "--postcode",
        action="append",
        help="Four-digit postcode to fetch from the AEC electorate finder. Repeat for many.",
    )
    aec_postcode_fetch_parser.add_argument(
        "--postcodes-file",
        help="Text file of postcodes, one per line. Lines may include # comments.",
    )
    aec_postcode_fetch_parser.add_argument("--refetch", action="store_true")

    aec_postcode_normalize_parser = subparsers.add_parser(
        "normalize-aec-electorate-finder-postcodes"
    )
    aec_postcode_normalize_parser.add_argument(
        "--postcode",
        action="append",
        help="Four-digit postcode to normalize. Repeat for many; omit to normalize all fetched postcodes.",
    )
    aec_postcode_normalize_parser.add_argument(
        "--postcodes-file",
        help="Text file of postcodes to normalize, one per line. Lines may include # comments.",
    )

    qld_eds_exports_parser = subparsers.add_parser("fetch-qld-ecq-eds-exports")
    qld_eds_exports_parser.add_argument(
        "--export",
        action="append",
        choices=[spec.export_name for spec in QLD_ECQ_EDS_EXPORTS],
        help="Fetch one QLD ECQ EDS CSV export. Repeat for multiple exports; omit for all.",
    )
    subparsers.add_parser("normalize-qld-ecq-eds-money-flows")

    subparsers.add_parser("normalize-qld-ecq-eds-participants")

    subparsers.add_parser("normalize-qld-ecq-eds-contexts")

    subparsers.add_parser("extract-house-interest-sections")

    subparsers.add_parser("extract-house-interest-records")

    senate_fetch_parser = subparsers.add_parser("fetch-senate-interests-api")
    senate_fetch_parser.add_argument("--limit", type=int)

    subparsers.add_parser("extract-senate-interest-records")

    subparsers.add_parser("fetch-they-vote-for-you-people")

    tvfy_fetch_parser = subparsers.add_parser("fetch-they-vote-for-you-divisions")
    tvfy_fetch_parser.add_argument("--start-date")
    tvfy_fetch_parser.add_argument("--end-date")
    tvfy_fetch_parser.add_argument("--house", choices=("representatives", "senate"))
    tvfy_fetch_parser.add_argument("--limit", type=int)
    tvfy_fetch_parser.add_argument("--allow-truncated", action="store_true")

    tvfy_extract_parser = subparsers.add_parser("extract-they-vote-for-you-divisions")
    tvfy_extract_parser.add_argument("--fetch-summary-path")

    subparsers.add_parser("classify-entities")

    boundary_fetch_parser = subparsers.add_parser("fetch-current-aec-boundaries")
    boundary_fetch_parser.add_argument(
        "--refetch",
        action="store_true",
        help="Fetch even if a current national ESRI ZIP is already present in raw storage.",
    )

    boundary_extract_parser = subparsers.add_parser("extract-aec-boundaries")
    boundary_extract_parser.add_argument("--metadata-path")

    land_mask_fetch_parser = subparsers.add_parser("fetch-natural-earth-land-mask")
    land_mask_fetch_parser.add_argument("--refetch", action="store_true")

    land_mask_extract_parser = subparsers.add_parser("extract-natural-earth-land-mask")
    land_mask_extract_parser.add_argument("--country-name", default="Australia")

    display_geometry_parser = subparsers.add_parser("load-display-geometries")
    display_geometry_parser.add_argument("--boundary-set")
    display_geometry_parser.add_argument("--country-name", default="Australia")
    display_geometry_parser.add_argument(
        "--coastline-repair-buffer-meters",
        type=coastline_repair_buffer_arg,
        default=DEFAULT_COASTLINE_REPAIR_BUFFER_METERS,
    )

    aims_land_mask_fetch_parser = subparsers.add_parser("fetch-aims-coastline-land-mask")
    aims_land_mask_fetch_parser.add_argument("--refetch", action="store_true")

    aims_land_mask_extract_parser = subparsers.add_parser("extract-aims-coastline-land-mask")
    aims_land_mask_extract_parser.add_argument("--country-name", default="Australia")

    aph_decision_parser = subparsers.add_parser("extract-aph-decision-record-index")
    aph_decision_parser.add_argument("source_id", choices=DECISION_RECORD_SOURCE_IDS, nargs="?")
    aph_decision_parser.add_argument(
        "--all",
        action="store_true",
        help="Extract all registered APH decision-record index sources.",
    )

    aph_document_parser = subparsers.add_parser("fetch-aph-decision-record-documents")
    aph_document_parser.add_argument("--skip-html", action="store_true")
    aph_document_parser.add_argument("--skip-pdf", action="store_true")
    aph_document_parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Skip linked record representations that already have a successful raw fetch.",
    )
    aph_document_parser.add_argument("--limit", type=int)

    subparsers.add_parser("extract-official-aph-divisions")

    subparsers.add_parser("discover-official-identifier-sources")

    lobbyist_parser = subparsers.add_parser("fetch-lobbyist-register")
    lobbyist_parser.add_argument("--limit", type=int)

    official_parser = subparsers.add_parser("extract-official-identifiers")
    official_parser.add_argument(
        "source_id",
        choices=("asic_companies_dataset", "acnc_register", "abn_lookup"),
    )
    official_parser.add_argument("input_path")
    official_parser.add_argument("--limit", type=int)

    abn_lookup_parser = subparsers.add_parser("fetch-abn-lookup-web")
    abn_lookup_parser.add_argument("lookup_type", choices=("abn", "acn"))
    abn_lookup_parser.add_argument("lookup_value")
    abn_lookup_parser.add_argument(
        "--current-only",
        action="store_true",
        help="Request current ABR details only instead of current plus historical details.",
    )

    subparsers.add_parser("migrate-postgres")

    load_qld_parser = subparsers.add_parser("load-qld-ecq-eds-money-flows")
    load_qld_parser.add_argument(
        "--skip-influence-events",
        action="store_true",
        help="Load QLD ECQ EDS money_flow rows without rebuilding influence_event.",
    )
    subparsers.add_parser("load-qld-ecq-eds-participants")

    load_qld_contexts_parser = subparsers.add_parser("load-qld-ecq-eds-contexts")
    load_qld_contexts_parser.add_argument(
        "--skip-influence-events",
        action="store_true",
        help="Load QLD ECQ event/local-electorate context without rebuilding influence_event.",
    )

    subparsers.add_parser("load-postcode-electorate-crosswalk")

    review_parser = subparsers.add_parser("export-review-queue")
    review_parser.add_argument("queue_name", choices=review_queue_names())
    review_parser.add_argument("--limit", type=int)

    suggestions_parser = subparsers.add_parser("suggest-sector-policy-links")
    suggestions_parser.add_argument("--limit", type=int)

    party_entity_parser = subparsers.add_parser("materialize-party-entity-links")
    party_entity_parser.add_argument("--limit-per-party", type=int)

    review_bundle_parser = subparsers.add_parser("prepare-review-bundle")
    review_bundle_parser.add_argument("--limit", type=int)
    review_bundle_parser.add_argument("--limit-per-party", type=int)

    import_review_parser = subparsers.add_parser("import-review-decisions")
    import_review_parser.add_argument("input_path")
    import_review_parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate the database. Without this flag the command validates and writes a dry-run summary.",
    )

    reapply_review_parser = subparsers.add_parser("reapply-review-decisions")
    reapply_review_parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate the database. Without this flag the command validates replay only.",
    )
    reapply_review_parser.add_argument(
        "--subject-type",
        choices=sorted(REVIEW_SUBJECT_TYPES),
    )
    reapply_review_parser.add_argument("--continue-on-error", action="store_true")

    qa_parser = subparsers.add_parser("qa-serving-database")
    qa_parser.add_argument("--boundary-set", default="aec_federal_2025_current")
    qa_parser.add_argument("--expected-house-boundary-count", type=int, default=150)
    qa_parser.add_argument("--max-official-unmatched-votes", type=int, default=25)
    qa_parser.add_argument("--min-current-influence-events", type=int, default=0)
    qa_parser.add_argument("--min-person-linked-influence-events", type=int, default=0)
    qa_parser.add_argument("--min-current-money-flows", type=int, default=0)
    qa_parser.add_argument("--min-current-gift-interests", type=int, default=0)
    qa_parser.add_argument("--min-current-house-office-terms", type=int, default=0)
    qa_parser.add_argument("--min-current-senate-office-terms", type=int, default=0)

    pipeline_parser = subparsers.add_parser("run-federal-foundation-pipeline")
    pipeline_parser.add_argument("--smoke", action="store_true")
    pipeline_parser.add_argument(
        "--refresh-existing-sources",
        action="store_true",
        help=(
            "Refetch sources that usually reuse a valid raw snapshot. Scheduled "
            "update runs should enable this so changed official records produce "
            "new hashes and downstream current/withdrawn flags."
        ),
    )
    pipeline_parser.add_argument("--skip-house-pdfs", action="store_true")
    pipeline_parser.add_argument("--skip-pdf-text", action="store_true")
    pipeline_parser.add_argument("--include-votes", action="store_true")
    pipeline_parser.add_argument("--votes-start-date")
    pipeline_parser.add_argument("--votes-end-date")

    load_parser = subparsers.add_parser("load-postgres")
    load_parser.add_argument("--apply-schema", action="store_true")
    load_parser.add_argument("--skip-roster", action="store_true")
    load_parser.add_argument("--skip-money-flows", action="store_true")
    load_parser.add_argument(
        "--skip-qld-ecq",
        action="store_true",
        help=(
            "Skip Queensland ECQ state/local artifacts during this load. Federal-only "
            "scheduled runs should use this unless the QLD fetch/normalize steps ran."
        ),
    )
    load_parser.add_argument("--skip-house-interests", action="store_true")
    load_parser.add_argument("--skip-senate-interests", action="store_true")
    load_parser.add_argument("--skip-electorate-boundaries", action="store_true")
    load_parser.add_argument("--skip-influence-events", action="store_true")
    load_parser.add_argument("--skip-entity-classifications", action="store_true")
    load_parser.add_argument("--skip-official-identifiers", action="store_true")
    load_parser.add_argument("--skip-official-decision-records", action="store_true")
    load_parser.add_argument("--skip-official-decision-record-documents", action="store_true")
    load_parser.add_argument("--skip-official-aph-divisions", action="store_true")
    load_parser.add_argument(
        "--include-vote-divisions",
        action="store_true",
        help="Load processed They Vote For You division/vote artifacts if present.",
    )
    load_parser.add_argument("--skip-postcode-crosswalk", action="store_true")
    load_parser.add_argument("--skip-party-entity-links", action="store_true")
    load_parser.add_argument("--skip-review-reapply", action="store_true")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "list-sources":
        return list_sources()
    if args.command == "show-source":
        return show_source(args.source_id)
    if args.command == "fetch-source":
        return fetch_source_command(args.source_id)
    if args.command == "discover-links":
        return discover_links_command(args.source_id)
    if args.command == "fetch-discovered":
        return fetch_discovered_command(args.source_id, args.link_type, args.limit)
    if args.command == "build-roster":
        return build_roster_command()
    if args.command == "extract-pdf-text":
        return extract_pdf_text_command(args.prefix, args.limit)
    if args.command == "summarize-aec-annual":
        return summarize_aec_annual_command(args.sample_size)
    if args.command == "normalize-aec-annual-money-flows":
        return normalize_aec_annual_command()
    if args.command == "summarize-aec-election":
        return summarize_aec_election_command(args.sample_size)
    if args.command == "normalize-aec-election-money-flows":
        return normalize_aec_election_command()
    if args.command == "normalize-aec-public-funding":
        return normalize_aec_public_funding_command()
    if args.command == "fetch-aec-electorate-finder-postcodes":
        return fetch_aec_electorate_finder_postcodes_command(
            args.postcode,
            args.postcodes_file,
            args.refetch,
        )
    if args.command == "normalize-aec-electorate-finder-postcodes":
        return normalize_aec_electorate_finder_postcodes_command(
            args.postcode,
            args.postcodes_file,
        )
    if args.command == "fetch-qld-ecq-eds-exports":
        return fetch_qld_ecq_eds_exports_command(args.export)
    if args.command == "normalize-qld-ecq-eds-money-flows":
        return normalize_qld_ecq_eds_money_flows_command()
    if args.command == "normalize-qld-ecq-eds-participants":
        return normalize_qld_ecq_eds_participants_command()
    if args.command == "normalize-qld-ecq-eds-contexts":
        return normalize_qld_ecq_eds_contexts_command()
    if args.command == "extract-house-interest-sections":
        return extract_house_interest_sections_command()
    if args.command == "extract-house-interest-records":
        return extract_house_interest_records_command()
    if args.command == "fetch-senate-interests-api":
        return fetch_senate_interests_api_command(args.limit)
    if args.command == "extract-senate-interest-records":
        return extract_senate_interest_records_command()
    if args.command == "fetch-they-vote-for-you-people":
        return fetch_they_vote_for_you_people_command()
    if args.command == "fetch-they-vote-for-you-divisions":
        return fetch_they_vote_for_you_divisions_command(
            args.start_date,
            args.end_date,
            args.house,
            args.limit,
            args.allow_truncated,
        )
    if args.command == "extract-they-vote-for-you-divisions":
        return extract_they_vote_for_you_divisions_command(args.fetch_summary_path)
    if args.command == "classify-entities":
        return classify_entities_command()
    if args.command == "fetch-current-aec-boundaries":
        return fetch_current_aec_boundaries_command(args.refetch)
    if args.command == "extract-aec-boundaries":
        return extract_aec_boundaries_command(args.metadata_path)
    if args.command == "fetch-natural-earth-land-mask":
        return fetch_natural_earth_land_mask_command(args.refetch)
    if args.command == "extract-natural-earth-land-mask":
        return extract_natural_earth_land_mask_command(args.country_name)
    if args.command == "load-display-geometries":
        return load_display_geometries_command(
            args.boundary_set,
            args.country_name,
            args.coastline_repair_buffer_meters,
        )
    if args.command == "fetch-aims-coastline-land-mask":
        return fetch_aims_coastline_land_mask_command(args.refetch)
    if args.command == "extract-aims-coastline-land-mask":
        return extract_aims_coastline_land_mask_command(args.country_name)
    if args.command == "extract-aph-decision-record-index":
        return extract_aph_decision_record_index_command(args.source_id, args.all)
    if args.command == "fetch-aph-decision-record-documents":
        return fetch_aph_decision_record_documents_command(
            include_html=not args.skip_html,
            include_pdf=not args.skip_pdf,
            only_missing=args.only_missing,
            limit=args.limit,
        )
    if args.command == "extract-official-aph-divisions":
        return extract_official_aph_divisions_command()
    if args.command == "discover-official-identifier-sources":
        return discover_official_identifier_sources_command()
    if args.command == "fetch-lobbyist-register":
        return fetch_lobbyist_register_command(args.limit)
    if args.command == "extract-official-identifiers":
        return extract_official_identifiers_command(args.source_id, args.input_path, args.limit)
    if args.command == "fetch-abn-lookup-web":
        return fetch_abn_lookup_web_command(
            args.lookup_type,
            args.lookup_value,
            include_historical_details=not args.current_only,
        )
    if args.command == "migrate-postgres":
        return migrate_postgres_command()
    if args.command == "load-qld-ecq-eds-money-flows":
        return load_qld_ecq_eds_money_flows_command(args.skip_influence_events)
    if args.command == "load-qld-ecq-eds-participants":
        return load_qld_ecq_eds_participants_command()
    if args.command == "load-qld-ecq-eds-contexts":
        return load_qld_ecq_eds_contexts_command(args.skip_influence_events)
    if args.command == "load-postcode-electorate-crosswalk":
        return load_postcode_electorate_crosswalk_command()
    if args.command == "export-review-queue":
        return export_review_queue_command(args.queue_name, args.limit)
    if args.command == "suggest-sector-policy-links":
        return suggest_sector_policy_links_command(args.limit)
    if args.command == "materialize-party-entity-links":
        return materialize_party_entity_links_command(args.limit_per_party)
    if args.command == "prepare-review-bundle":
        return prepare_review_bundle_command(args.limit, args.limit_per_party)
    if args.command == "import-review-decisions":
        return import_review_decisions_command(args.input_path, args.apply)
    if args.command == "reapply-review-decisions":
        return reapply_review_decisions_command(
            args.apply,
            args.subject_type,
            args.continue_on_error,
        )
    if args.command == "qa-serving-database":
        return qa_serving_database_command(
            args.boundary_set,
            args.expected_house_boundary_count,
            args.max_official_unmatched_votes,
            args.min_current_influence_events,
            args.min_person_linked_influence_events,
            args.min_current_money_flows,
            args.min_current_gift_interests,
            args.min_current_house_office_terms,
            args.min_current_senate_office_terms,
        )
    if args.command == "run-federal-foundation-pipeline":
        return run_pipeline_command(
            args.smoke,
            args.refresh_existing_sources,
            args.skip_house_pdfs,
            args.skip_pdf_text,
            args.include_votes,
            args.votes_start_date,
            args.votes_end_date,
        )
    if args.command == "load-postgres":
        return load_postgres_command(
            args.apply_schema,
            args.skip_roster,
            args.skip_money_flows,
            args.skip_qld_ecq,
            args.skip_house_interests,
            args.skip_senate_interests,
            args.skip_electorate_boundaries,
            args.skip_influence_events,
            args.skip_entity_classifications,
            args.skip_official_identifiers,
            args.skip_official_decision_records,
            args.skip_official_decision_record_documents,
            args.skip_official_aph_divisions,
            args.include_vote_divisions,
            args.skip_postcode_crosswalk,
            args.skip_party_entity_links,
            args.skip_review_reapply,
        )
    raise ValueError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
