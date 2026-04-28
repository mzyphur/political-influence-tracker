from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from au_politics_money import __version__
from au_politics_money.config import AUDIT_DIR
from au_politics_money.ingest.aec_boundaries import (
    extract_current_aec_boundaries,
    fetch_current_aec_boundary_zip,
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
    extract_aph_decision_record_index,
    fetch_aph_decision_record_documents,
)
from au_politics_money.ingest.aph_official_divisions import extract_official_aph_divisions
from au_politics_money.ingest.aph_roster import build_current_parliament_roster
from au_politics_money.ingest.discovered_sources import source_from_discovered_link
from au_politics_money.ingest.discovery import (
    discover_links_from_body,
    latest_body_path,
    latest_discovered_links_path,
    read_discovered_links,
    write_discovered_links,
)
from au_politics_money.ingest.entity_classification import classify_entity_names
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
    discover_official_identifier_sources,
    fetch_lobbyist_register_snapshot,
)
from au_politics_money.ingest.pdf_text import extract_pdf_text_batch
from au_politics_money.ingest.senate_interests import (
    extract_senate_interest_records,
    fetch_senate_interest_statements,
)
from au_politics_money.ingest.sources import get_source
from au_politics_money.ingest.they_vote_for_you import (
    extract_they_vote_for_you_divisions,
    fetch_they_vote_for_you_divisions,
)

DEPENDENCY_DISTRIBUTIONS = (
    "beautifulsoup4",
    "httpx",
    "pandas",
    "pdfplumber",
    "psycopg",
    "pydantic",
    "pyproj",
    "pyshp",
    "pytesseract",
    "python-dotenv",
    "rapidfuzz",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class StepResult:
    name: str
    status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    output: Any = None
    error: str = ""


@dataclass
class PipelineManifest:
    pipeline_name: str
    run_id: str
    status: str
    started_at: str
    finished_at: str = ""
    duration_seconds: float = 0.0
    au_politics_money_version: str = __version__
    python_version: str = platform.python_version()
    platform: str = platform.platform()
    git_commit: str = ""
    dependency_versions: dict[str, str] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    steps: list[StepResult] = field(default_factory=list)


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in DEPENDENCY_DISTRIBUTIONS:
        try:
            versions[distribution] = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            versions[distribution] = "not_installed"
    return versions


def _run_step(name: str, func: Callable[[], Any]) -> StepResult:
    started = utc_now()
    try:
        output = func()
        status = "succeeded"
        error = ""
    except Exception as exc:  # noqa: BLE001 - pipeline manifest must record failures.
        output = None
        status = "failed"
        error = repr(exc)
    finished = utc_now()
    result = StepResult(
        name=name,
        status=status,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_seconds=(finished - started).total_seconds(),
        output=str(output) if isinstance(output, Path) else output,
        error=error,
    )
    if status == "failed":
        raise PipelineStepError(result)
    return result


class PipelineStepError(RuntimeError):
    def __init__(self, result: StepResult) -> None:
        super().__init__(f"Pipeline step failed: {result.name}: {result.error}")
        self.result = result


def _discover_source_links(source_id: str) -> Path:
    source = get_source(source_id)
    body_path = latest_body_path(source.source_id)
    if body_path is None:
        fetch_source(source)
        body_path = latest_body_path(source.source_id)
    if body_path is None:
        raise FileNotFoundError(f"No raw body found for source {source.source_id}")
    return write_discovered_links(source, discover_links_from_body(source, body_path))


def _fetch_discovered(source_id: str, link_type: str | None = None, limit: int | None = None) -> dict:
    parent = get_source(source_id)
    links_path = latest_discovered_links_path(parent.source_id)
    if links_path is None:
        _discover_source_links(parent.source_id)
        links_path = latest_discovered_links_path(parent.source_id)
    if links_path is None:
        raise FileNotFoundError(f"No discovered links found for source {parent.source_id}")

    links = read_discovered_links(links_path)
    if link_type:
        links = [link for link in links if link.link_type == link_type]
    if limit is not None:
        links = links[:limit]

    outputs = []
    for link in links:
        outputs.append(str(fetch_source(source_from_discovered_link(parent, link))))

    return {
        "parent_source_id": source_id,
        "link_type": link_type,
        "limit": limit,
        "fetched_count": len(outputs),
        "metadata_paths": outputs,
    }


def _write_manifest(manifest: PipelineManifest) -> Path:
    target_dir = AUDIT_DIR / "pipeline_runs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{manifest.run_id}.json"
    target_path.write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target_path


def run_federal_foundation_pipeline(
    *,
    smoke: bool = False,
    skip_house_pdfs: bool = False,
    skip_pdf_text: bool = False,
    include_votes: bool = False,
    votes_start_date: str | None = None,
    votes_end_date: str | None = None,
) -> Path:
    started = utc_now()
    manifest = PipelineManifest(
        pipeline_name="federal_foundation",
        run_id=f"federal_foundation_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "smoke": smoke,
            "skip_house_pdfs": skip_house_pdfs,
            "skip_pdf_text": skip_pdf_text,
            "include_votes": include_votes,
            "votes_start_date": votes_start_date,
            "votes_end_date": votes_end_date,
        },
    )

    house_pdf_limit = 5 if smoke else None
    pdf_text_limit = 5 if smoke else None
    senate_statement_limit = 5 if smoke else None
    lobbyist_org_limit = 25 if smoke else None
    decision_record_document_limit = 10 if smoke else None

    steps: list[tuple[str, Callable[[], Any]]] = [
        (
            "fetch_core_index_sources",
            lambda: [
                str(fetch_source(get_source(source_id)))
                for source_id in (
                    "aec_transparency_downloads",
                    "aph_contacts_csv",
                    "aph_members_contact_list_pdf",
                    "aph_senators_contact_list_pdf",
                    "aph_members_interests_48",
                    "aph_senators_interests",
                    "aec_federal_boundaries_gis",
                    "aec_download_all_annual_data",
                    "aec_download_all_election_data",
                    "aec_2025_federal_election_funding_finalised",
                    "aims_australian_coastline_50k_2024_simp",
                    "natural_earth_admin0_countries_10m",
                    "natural_earth_physical_land_10m",
                    "aph_house_votes_and_proceedings",
                    "aph_senate_journals",
                )
            ],
        ),
        (
            "discover_core_child_links",
            lambda: [
                str(_discover_source_links(source_id))
                for source_id in (
                    "aec_transparency_downloads",
                    "aph_contacts_csv",
                    "aph_members_interests_48",
                    "aph_senators_interests",
                    "aec_federal_boundaries_gis",
                    "aph_house_votes_and_proceedings",
                    "aph_senate_journals",
                )
            ],
        ),
        ("fetch_aph_contact_csvs", lambda: _fetch_discovered("aph_contacts_csv", "csv")),
        ("build_current_parliament_roster", build_current_parliament_roster),
        ("summarize_aec_annual_zip", summarize_aec_annual_zip),
        ("normalize_aec_annual_money_flows", normalize_aec_annual_money_flows),
        ("summarize_aec_election_zip", summarize_aec_election_zip),
        ("normalize_aec_election_money_flows", normalize_aec_election_money_flows),
        ("normalize_aec_public_funding", normalize_aec_public_funding),
        ("fetch_current_aec_boundaries_zip", fetch_current_aec_boundary_zip),
        ("extract_aec_federal_boundaries", extract_current_aec_boundaries),
        ("fetch_aims_australian_coastline_zip", fetch_aims_australian_coastline_zip),
        (
            "extract_aims_australian_coastline_land_mask",
            extract_aims_australian_coastline_land_mask,
        ),
        ("fetch_natural_earth_admin0_zip", fetch_natural_earth_admin0_zip),
        ("fetch_natural_earth_physical_land_zip", fetch_natural_earth_physical_land_zip),
        ("extract_natural_earth_australia_land_mask", extract_natural_earth_country_land_mask),
        (
            "extract_natural_earth_australia_physical_land_mask",
            extract_natural_earth_physical_land_mask,
        ),
        (
            "extract_house_votes_and_proceedings_index",
            lambda: extract_aph_decision_record_index("aph_house_votes_and_proceedings"),
        ),
        (
            "extract_senate_journals_index",
            lambda: extract_aph_decision_record_index("aph_senate_journals"),
        ),
        (
            "fetch_aph_decision_record_documents",
            lambda: fetch_aph_decision_record_documents(
                only_missing=True,
                limit=decision_record_document_limit,
            ),
        ),
        ("extract_official_aph_divisions", extract_official_aph_divisions),
        (
            "fetch_senate_interests_api",
            lambda: fetch_senate_interest_statements(limit=senate_statement_limit),
        ),
        ("extract_senate_interest_records", extract_senate_interest_records),
    ]

    if not skip_house_pdfs:
        steps.append(
            (
                "fetch_house_interests_pdfs",
                lambda: _fetch_discovered("aph_members_interests_48", "pdf", house_pdf_limit),
            )
        )

    if not skip_pdf_text:
        steps.extend(
            [
                (
                    "extract_house_interests_pdf_text",
                    lambda: extract_pdf_text_batch(
                        prefix="aph_members_interests_48__",
                        limit=pdf_text_limit,
                    ),
                ),
                ("extract_house_interest_sections", extract_house_interest_sections),
                ("extract_house_interest_records", extract_house_interest_records),
            ]
        )

    steps.append(("classify_entities", classify_entity_names))
    steps.append(("discover_official_identifier_sources", discover_official_identifier_sources))
    steps.append(
        (
            "fetch_lobbyist_register_snapshot",
            lambda: fetch_lobbyist_register_snapshot(limit=lobbyist_org_limit),
        )
    )
    if include_votes:
        tvfy_limit = 5 if smoke else None
        steps.extend(
            [
                (
                    "fetch_they_vote_for_you_divisions",
                    lambda: fetch_they_vote_for_you_divisions(
                        start_date=votes_start_date,
                        end_date=votes_end_date,
                        limit=tvfy_limit,
                    ),
                ),
                ("extract_they_vote_for_you_divisions", extract_they_vote_for_you_divisions),
            ]
        )

    try:
        for name, func in steps:
            manifest.steps.append(_run_step(name, func))
        manifest.status = "succeeded"
    except PipelineStepError as exc:
        manifest.steps.append(exc.result)
        manifest.status = "failed"
    finally:
        finished = utc_now()
        manifest.finished_at = finished.isoformat()
        manifest.duration_seconds = (finished - started).total_seconds()

    manifest_path = _write_manifest(manifest)
    if manifest.status == "failed":
        raise RuntimeError(f"Pipeline failed. Manifest: {manifest_path}")
    return manifest_path
