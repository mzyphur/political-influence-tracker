from __future__ import annotations

import hashlib
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
from au_politics_money.config import AUDIT_DIR, PROJECT_ROOT
from au_politics_money.ingest.aec_boundaries import (
    extract_current_aec_boundaries,
    fetch_current_aec_boundary_zip,
)
from au_politics_money.ingest.aec_electorate_finder import (
    fetch_aec_electorate_finder_postcodes,
    normalize_aec_electorate_finder_postcodes,
)
from au_politics_money.ingest.act_elections import (
    ANNUAL_RETURNS_SOURCE_ID as ACT_ANNUAL_RETURNS_SOURCE_ID,
    GIFT_RETURNS_SOURCE_ID as ACT_GIFT_RETURNS_SOURCE_ID,
    STATE_SOURCE_DATASET as ACT_STATE_SOURCE_DATASET,
    normalize_act_annual_return_receipts,
    normalize_act_gift_returns,
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
    fetch_official_identifier_bulk_resources,
    fetch_lobbyist_register_snapshot,
)
from au_politics_money.ingest.nsw_electoral import (
    HEATMAP_SOURCE_ID as NSW_HEATMAP_SOURCE_ID,
    normalize_nsw_pre_election_donor_location_heatmap,
    resolve_nsw_heatmap_url_from_pre_election_page,
)
from au_politics_money.ingest.nt_ntec import (
    ANNUAL_GIFTS_SOURCE_ID as NT_NTEC_ANNUAL_GIFTS_SOURCE_ID,
    ANNUAL_RETURNS_SOURCE_ID as NT_NTEC_ANNUAL_RETURNS_SOURCE_ID,
    normalize_nt_ntec_annual_gifts,
    normalize_nt_ntec_annual_returns,
)
from au_politics_money.ingest.pdf_text import extract_pdf_text_batch
from au_politics_money.ingest.qld_ecq_eds import (
    QLD_ECQ_EDS_CONTEXT_LOOKUPS,
    QLD_ECQ_EDS_EXPORTS,
    QLD_ECQ_EDS_PARTICIPANT_LOOKUPS,
    fetch_qld_ecq_eds_exports,
    normalize_qld_ecq_eds_contexts,
    normalize_qld_ecq_eds_money_flows,
    normalize_qld_ecq_eds_participants,
)
from au_politics_money.ingest.qld_boundaries import (
    extract_qld_state_electorate_boundaries,
    fetch_qld_state_electorate_boundaries,
)
from au_politics_money.ingest.qld_parliament_members import (
    extract_qld_current_members,
    fetch_qld_current_members,
)
from au_politics_money.ingest.sa_ecsa import (
    SOURCE_DATASET as SA_ECSA_SOURCE_DATASET,
    fetch_sa_ecsa_return_index_pages,
    normalize_sa_ecsa_return_index,
)
from au_politics_money.ingest.senate_interests import (
    extract_senate_interest_records,
    fetch_senate_interest_statements,
)
from au_politics_money.ingest.sources import get_source
from au_politics_money.ingest.tas_tec import (
    SOURCE_DATASET as TAS_TEC_SOURCE_DATASET,
    fetch_tas_tec_declaration_documents,
    fetch_tas_tec_donation_tables,
    normalize_tas_tec_donations,
)
from au_politics_money.ingest.they_vote_for_you import (
    extract_they_vote_for_you_divisions,
    fetch_they_vote_for_you_divisions,
)
from au_politics_money.ingest.vic_vec import (
    FUNDING_REGISTER_SOURCE_ID as VIC_VEC_FUNDING_REGISTER_SOURCE_ID,
    fetch_vic_vec_funding_register_documents,
    normalize_vic_vec_funding_registers,
)
from au_politics_money.ingest.waec import (
    SOURCE_DATASET as WAEC_SOURCE_DATASET,
    fetch_waec_political_contribution_pages,
    normalize_waec_political_contributions,
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
POSTCODE_SEED_PATH = PROJECT_ROOT / "data" / "seeds" / "aec_postcode_search_seed.txt"


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
    output_sha256: str = ""
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
        output_sha256 = _file_sha256(output) if isinstance(output, Path) else ""
        status = "succeeded"
        error = ""
    except Exception as exc:  # noqa: BLE001 - pipeline manifest must record failures.
        output = None
        output_sha256 = ""
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
        output_sha256=output_sha256,
        error=error,
    )
    if status == "failed":
        raise PipelineStepError(result)
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _seed_postcodes() -> list[str]:
    postcodes: list[str] = []
    if not POSTCODE_SEED_PATH.exists():
        raise FileNotFoundError(f"Postcode seed file not found: {POSTCODE_SEED_PATH}")
    for line in POSTCODE_SEED_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.split("#", maxsplit=1)[0].strip()
        if cleaned:
            postcodes.append(cleaned)
    return postcodes


def _postcode_seed_metadata(postcodes: list[str]) -> dict[str, Any]:
    payload = "\n".join(sorted(postcodes)) + "\n"
    return {
        "postcode_seed_path": str(POSTCODE_SEED_PATH.relative_to(PROJECT_ROOT)),
        "postcode_seed_count": len(postcodes),
        "postcode_seed_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
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


def _qld_ecq_source_ids() -> tuple[str, ...]:
    source_ids = [
        spec.page_source_id for spec in QLD_ECQ_EDS_EXPORTS
    ] + [
        spec.source_id for spec in QLD_ECQ_EDS_PARTICIPANT_LOOKUPS
    ] + [
        spec.source_id for spec in QLD_ECQ_EDS_CONTEXT_LOOKUPS
    ]
    return tuple(dict.fromkeys(source_ids))


def _qld_export_metadata_paths_from_summary(summary_path: Path) -> dict[str, Path]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    outputs = summary.get("outputs")
    if not isinstance(outputs, list):
        raise RuntimeError(f"Malformed QLD ECQ export summary: {summary_path}")
    metadata_paths: dict[str, Path] = {}
    for output in outputs:
        if not isinstance(output, dict):
            continue
        source_id = str(output.get("source_id") or "")
        metadata_path = output.get("metadata_path")
        if source_id and metadata_path:
            metadata_paths[source_id] = Path(str(metadata_path))
    expected_source_ids = {spec.export_source_id for spec in QLD_ECQ_EDS_EXPORTS}
    missing = expected_source_ids - set(metadata_paths)
    if missing:
        raise RuntimeError(
            f"QLD ECQ export summary missing metadata path(s): {', '.join(sorted(missing))}"
        )
    return metadata_paths


def run_federal_foundation_pipeline(
    *,
    smoke: bool = False,
    refresh_existing_sources: bool = False,
    skip_house_pdfs: bool = False,
    skip_pdf_text: bool = False,
    include_votes: bool = False,
    include_official_identifier_bulk: bool = False,
    votes_start_date: str | None = None,
    votes_end_date: str | None = None,
) -> Path:
    started = utc_now()
    postcode_seed = _seed_postcodes()
    manifest = PipelineManifest(
        pipeline_name="federal_foundation",
        run_id=f"federal_foundation_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "smoke": smoke,
            "refresh_existing_sources": refresh_existing_sources,
            "skip_house_pdfs": skip_house_pdfs,
            "skip_pdf_text": skip_pdf_text,
            "include_votes": include_votes,
            "include_official_identifier_bulk": include_official_identifier_bulk,
            "votes_start_date": votes_start_date,
            "votes_end_date": votes_end_date,
            **_postcode_seed_metadata(postcode_seed),
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
        (
            "fetch_aec_electorate_finder_postcodes",
            lambda: fetch_aec_electorate_finder_postcodes(
                postcode_seed,
                refetch=refresh_existing_sources,
            ),
        ),
        (
            "normalize_aec_electorate_finder_postcodes",
            lambda: normalize_aec_electorate_finder_postcodes(postcode_seed),
        ),
        (
            "fetch_current_aec_boundaries_zip",
            lambda: fetch_current_aec_boundary_zip(refetch=refresh_existing_sources),
        ),
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
                only_missing=not refresh_existing_sources,
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
    if include_official_identifier_bulk:
        steps.append(
            (
                "fetch_official_identifier_bulk_resources",
                lambda: fetch_official_identifier_bulk_resources(
                    extract_limit_per_source=25 if smoke else None,
                ),
            )
        )
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


def run_state_local_pipeline(*, jurisdiction: str = "qld", smoke: bool = False) -> Path:
    normalized_jurisdiction = jurisdiction.strip().lower()
    if normalized_jurisdiction not in {
        "act",
        "australian capital territory",
        "qld",
        "queensland",
        "nsw",
        "new south wales",
        "nt",
        "northern territory",
        "sa",
        "south australia",
        "tas",
        "tasmania",
        "vic",
        "victoria",
        "wa",
        "western australia",
    }:
        raise ValueError(
            "Unsupported state/local jurisdiction. Currently supported: "
            "act, qld, nsw, nt, sa, tas, vic, wa."
        )
    if normalized_jurisdiction in {"act", "australian capital territory"}:
        return _run_act_state_local_pipeline(smoke=smoke)
    if normalized_jurisdiction in {"nsw", "new south wales"}:
        return _run_nsw_state_local_pipeline(smoke=smoke)
    if normalized_jurisdiction in {"nt", "northern territory"}:
        return _run_nt_state_local_pipeline(smoke=smoke)
    if normalized_jurisdiction in {"sa", "south australia"}:
        return _run_sa_state_local_pipeline(smoke=smoke)
    if normalized_jurisdiction in {"tas", "tasmania"}:
        return _run_tas_state_local_pipeline(smoke=smoke)
    if normalized_jurisdiction in {"vic", "victoria"}:
        return _run_vic_state_local_pipeline(smoke=smoke)
    if normalized_jurisdiction in {"wa", "western australia"}:
        return _run_wa_state_local_pipeline(smoke=smoke)

    started = utc_now()
    page_source_ids = {spec.page_source_id for spec in QLD_ECQ_EDS_EXPORTS}
    lookup_source_ids = {
        spec.source_id
        for spec in (*QLD_ECQ_EDS_PARTICIPANT_LOOKUPS, *QLD_ECQ_EDS_CONTEXT_LOOKUPS)
    }
    qld_artifacts: dict[str, dict[str, Path]] = {
        "page_metadata_paths": {},
        "lookup_metadata_paths": {},
        "export_metadata_paths": {},
        "boundary_metadata_paths": {},
        "member_metadata_paths": {},
    }

    def fetch_qld_form_and_lookup_sources() -> dict[str, Any]:
        metadata_paths: dict[str, str] = {}
        for source_id in _qld_ecq_source_ids():
            metadata_path = fetch_source(get_source(source_id))
            metadata_paths[source_id] = str(metadata_path)
            if source_id in page_source_ids:
                qld_artifacts["page_metadata_paths"][source_id] = Path(metadata_path)
            if source_id in lookup_source_ids:
                qld_artifacts["lookup_metadata_paths"][source_id] = Path(metadata_path)
        return {
            "source_count": len(metadata_paths),
            "metadata_paths": metadata_paths,
        }

    def fetch_qld_exports() -> Path:
        summary_path = fetch_qld_ecq_eds_exports(
            page_metadata_paths=qld_artifacts["page_metadata_paths"],
        )
        qld_artifacts["export_metadata_paths"] = _qld_export_metadata_paths_from_summary(
            summary_path
        )
        return summary_path

    def fetch_qld_state_boundaries() -> Path:
        metadata_path = fetch_qld_state_electorate_boundaries(refetch=True)
        qld_artifacts["boundary_metadata_paths"]["state_boundaries"] = Path(metadata_path)
        return metadata_path

    def fetch_qld_members() -> Path:
        metadata_path = fetch_qld_current_members(refetch=True)
        qld_artifacts["member_metadata_paths"]["current_members"] = Path(metadata_path)
        return metadata_path

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_qld_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "qld",
            "source_family": "qld_ecq_eds",
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize Queensland ECQ disclosure rows, participants, "
                "and disclosure contexts. Loading, review, and public claims remain "
                "separate downstream steps."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        (
            "fetch_qld_ecq_form_and_lookup_sources",
            fetch_qld_form_and_lookup_sources,
        ),
        ("fetch_qld_ecq_eds_exports", fetch_qld_exports),
        (
            "normalize_qld_ecq_eds_money_flows",
            lambda: normalize_qld_ecq_eds_money_flows(
                export_metadata_paths=qld_artifacts["export_metadata_paths"],
            ),
        ),
        (
            "normalize_qld_ecq_eds_participants",
            lambda: normalize_qld_ecq_eds_participants(
                lookup_metadata_paths=qld_artifacts["lookup_metadata_paths"],
            ),
        ),
        (
            "normalize_qld_ecq_eds_contexts",
            lambda: normalize_qld_ecq_eds_contexts(
                lookup_metadata_paths=qld_artifacts["lookup_metadata_paths"],
            ),
        ),
        ("fetch_qld_state_boundaries", fetch_qld_state_boundaries),
        (
            "normalize_qld_state_boundaries",
            lambda: extract_qld_state_electorate_boundaries(
                metadata_path=qld_artifacts["boundary_metadata_paths"]["state_boundaries"],
            ),
        ),
        ("fetch_qld_current_members", fetch_qld_members),
        (
            "normalize_qld_current_members",
            lambda: extract_qld_current_members(
                metadata_path=qld_artifacts["member_metadata_paths"]["current_members"],
            ),
        ),
    ]

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


def _run_act_state_local_pipeline(*, smoke: bool = False) -> Path:
    started = utc_now()
    act_artifacts: dict[str, Path] = {}

    def fetch_act_sources() -> dict[str, Any]:
        gift_metadata_path = fetch_source(get_source(ACT_GIFT_RETURNS_SOURCE_ID))
        annual_metadata_path = fetch_source(get_source(ACT_ANNUAL_RETURNS_SOURCE_ID))
        act_artifacts["gift_returns_metadata_path"] = Path(gift_metadata_path)
        act_artifacts["annual_returns_metadata_path"] = Path(annual_metadata_path)
        return {
            "source_count": 2,
            "metadata_paths": {
                ACT_GIFT_RETURNS_SOURCE_ID: str(gift_metadata_path),
                ACT_ANNUAL_RETURNS_SOURCE_ID: str(annual_metadata_path),
            },
        }

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_act_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "act",
            "source_family": ACT_STATE_SOURCE_DATASET,
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize ACT Elections current gift-return rows and "
                "latest annual-return receipt detail rows. Rows are source-backed "
                "party, MLA, non-party MLA, candidate/grouping, or associated-entity "
                "disclosure observations. Gift-in-kind and free-facility values are "
                "non-cash reported values; none of these rows alone imply wrongdoing, "
                "personal income, or policy causation."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("fetch_act_elections_sources", fetch_act_sources),
        (
            "normalize_act_gift_returns",
            lambda: normalize_act_gift_returns(
                metadata_path=act_artifacts["gift_returns_metadata_path"],
            ),
        ),
        (
            "normalize_act_annual_return_receipts",
            lambda: normalize_act_annual_return_receipts(
                metadata_path=act_artifacts["annual_returns_metadata_path"],
            ),
        ),
    ]

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


def _run_nsw_state_local_pipeline(*, smoke: bool = False) -> Path:
    started = utc_now()
    nsw_artifacts: dict[str, Path] = {}
    nsw_context: dict[str, dict[str, str]] = {}

    def fetch_nsw_sources() -> dict[str, Any]:
        pre_election_source_id = "nsw_2023_state_election_pre_election_donations"
        pre_election_metadata_path = fetch_source(get_source(pre_election_source_id))
        metadata_paths: dict[str, str] = {
            pre_election_source_id: str(pre_election_metadata_path),
        }
        link_context = resolve_nsw_heatmap_url_from_pre_election_page(
            pre_election_metadata_path
        )
        registered_heatmap_url = get_source(NSW_HEATMAP_SOURCE_ID).url
        if link_context["heatmap_url"].casefold() != registered_heatmap_url.casefold():
            raise ValueError(
                "NSW heatmap URL on the pre-election page does not match the "
                "registered heatmap source URL: "
                f"page={link_context['heatmap_url']} registry={registered_heatmap_url}"
            )
        heatmap_metadata_path = fetch_source(get_source(NSW_HEATMAP_SOURCE_ID))
        metadata_paths[NSW_HEATMAP_SOURCE_ID] = str(heatmap_metadata_path)
        nsw_artifacts["heatmap_metadata_path"] = Path(heatmap_metadata_path)
        nsw_context["heatmap_link_context"] = link_context
        return {
            "source_count": len(metadata_paths),
            "metadata_paths": metadata_paths,
            "heatmap_link_context": link_context,
        }

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_nsw_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "nsw",
            "source_family": "nsw_electoral_disclosures",
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize NSW Electoral Commission 2023 State Election "
                "pre-election-period donation heatmap aggregates. Rows are "
                "donor-location aggregate context, not donor-recipient money flows "
                "or representative-level receipt."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("fetch_nsw_electoral_disclosure_sources", fetch_nsw_sources),
        (
            "normalize_nsw_pre_election_donor_location_heatmap",
            lambda: normalize_nsw_pre_election_donor_location_heatmap(
                metadata_path=nsw_artifacts["heatmap_metadata_path"],
                source_page_link_context=nsw_context.get("heatmap_link_context"),
            ),
        ),
    ]

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


def _run_vic_state_local_pipeline(*, smoke: bool = False) -> Path:
    started = utc_now()
    vic_artifacts: dict[str, Path] = {}

    def fetch_vic_sources() -> dict[str, Any]:
        page_metadata_path = fetch_source(get_source(VIC_VEC_FUNDING_REGISTER_SOURCE_ID))
        document_summary_path = fetch_vic_vec_funding_register_documents(
            page_metadata_path=Path(page_metadata_path),
        )
        vic_artifacts["document_summary_path"] = Path(document_summary_path)
        return {
            "source_count": 1,
            "metadata_paths": {VIC_VEC_FUNDING_REGISTER_SOURCE_ID: str(page_metadata_path)},
            "document_summary_path": str(document_summary_path),
        }

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_vic_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "vic",
            "source_family": "vic_vec_funding_register",
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize VEC funding-register DOCX records. Rows are "
                "Victorian public funding, administrative expenditure funding, and "
                "policy development funding context; they are not private donations, "
                "personal income, or evidence of improper conduct. VEC says affected "
                "funding/disclosure material is under review after Hopper & Anor v "
                "State of Victoria [2026] HCA 11."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("fetch_vic_vec_funding_register_sources", fetch_vic_sources),
        (
            "normalize_vic_vec_funding_registers",
            lambda: normalize_vic_vec_funding_registers(
                document_summary_path=vic_artifacts["document_summary_path"],
            ),
        ),
    ]

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


def _run_tas_state_local_pipeline(*, smoke: bool = False) -> Path:
    started = utc_now()
    tas_artifacts: dict[str, Path] = {}
    tas_declaration_documents: dict[str, Path] = {}

    def fetch_tas_sources() -> dict[str, Any]:
        metadata_paths = fetch_tas_tec_donation_tables()
        tas_artifacts.update({source_id: Path(path) for source_id, path in metadata_paths.items()})
        return {
            "source_count": len(metadata_paths),
            "metadata_paths": {
                source_id: str(path)
                for source_id, path in sorted(metadata_paths.items())
            },
        }

    def fetch_tas_declaration_documents() -> dict[str, Any]:
        metadata_paths = fetch_tas_tec_declaration_documents(
            metadata_paths=tas_artifacts,
            limit=10 if smoke else None,
        )
        tas_declaration_documents.update(
            {url: Path(path) for url, path in metadata_paths.items()}
        )
        return {
            "source_count": len(metadata_paths),
            "limited_by_smoke": smoke,
            "metadata_paths": {
                url: str(path)
                for url, path in sorted(metadata_paths.items())
            },
        }

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_tas_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "tas",
            "source_family": TAS_TEC_SOURCE_DATASET,
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize Tasmanian Electoral Commission reportable "
                "political donation tables. Rows are source-backed donation or "
                "reportable-loan observations under the disclosure scheme that "
                "commenced on 1 July 2025; they are not claims of wrongdoing, "
                "causation, quid pro quo, or improper influence."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("fetch_tas_tec_donation_table_sources", fetch_tas_sources),
        ("fetch_tas_tec_declaration_documents", fetch_tas_declaration_documents),
        (
            "normalize_tas_tec_donations",
            lambda: normalize_tas_tec_donations(
                metadata_paths=tas_artifacts,
                declaration_metadata_paths=tas_declaration_documents,
            ),
        ),
    ]

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


def _run_nt_state_local_pipeline(*, smoke: bool = False) -> Path:
    started = utc_now()
    nt_artifacts: dict[str, Path] = {}

    def fetch_nt_sources() -> dict[str, Any]:
        annual_returns_metadata_path = fetch_source(
            get_source(NT_NTEC_ANNUAL_RETURNS_SOURCE_ID)
        )
        annual_gifts_metadata_path = fetch_source(get_source(NT_NTEC_ANNUAL_GIFTS_SOURCE_ID))
        nt_artifacts["annual_returns_metadata_path"] = Path(annual_returns_metadata_path)
        nt_artifacts["annual_gifts_metadata_path"] = Path(annual_gifts_metadata_path)
        return {
            "source_count": 2,
            "metadata_paths": {
                NT_NTEC_ANNUAL_RETURNS_SOURCE_ID: str(annual_returns_metadata_path),
                NT_NTEC_ANNUAL_GIFTS_SOURCE_ID: str(annual_gifts_metadata_path),
            },
        }

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_nt_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "nt",
            "source_family": "nt_ntec_annual_returns",
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize NTEC 2024-2025 annual return and annual "
                "gift-return rows. Rows are source-backed state disclosure "
                "observations; they are not claims of wrongdoing, causation, quid "
                "pro quo, or improper influence. NT annual return rows are not "
                "consolidated reported amount totals until cross-source "
                "deduplication exists."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("fetch_nt_ntec_annual_return_sources", fetch_nt_sources),
        (
            "normalize_nt_ntec_annual_returns",
            lambda: normalize_nt_ntec_annual_returns(
                metadata_path=nt_artifacts["annual_returns_metadata_path"],
            ),
        ),
        (
            "normalize_nt_ntec_annual_gifts",
            lambda: normalize_nt_ntec_annual_gifts(
                metadata_path=nt_artifacts["annual_gifts_metadata_path"],
            ),
        ),
    ]

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


def _run_sa_state_local_pipeline(*, smoke: bool = False) -> Path:
    started = utc_now()
    sa_artifacts: dict[str, Path] = {}

    def fetch_sa_sources() -> dict[str, Any]:
        metadata_path = fetch_sa_ecsa_return_index_pages(max_pages=1 if smoke else None)
        sa_artifacts["return_index_metadata_path"] = Path(metadata_path)
        return {
            "source_count": 1,
            "metadata_paths": {
                "sa_ecsa_funding2024_return_records": str(metadata_path),
            },
            "smoke_max_pages": 1 if smoke else None,
        }

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_sa_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "sa",
            "source_family": SA_ECSA_SOURCE_DATASET,
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize Electoral Commission SA current funding "
                "portal return-index rows. Rows are return-level source-backed "
                "summary records and official report links, not individual "
                "donor-to-recipient transactions, not personal receipt by a "
                "representative, and not causal claims."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("fetch_sa_ecsa_return_index_pages", fetch_sa_sources),
        (
            "normalize_sa_ecsa_return_index",
            lambda: normalize_sa_ecsa_return_index(
                metadata_path=sa_artifacts["return_index_metadata_path"],
            ),
        ),
    ]

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


def _run_wa_state_local_pipeline(*, smoke: bool = False) -> Path:
    started = utc_now()
    wa_artifacts: dict[str, Path] = {}

    def fetch_wa_sources() -> dict[str, Any]:
        metadata_path = fetch_waec_political_contribution_pages(
            max_pages=1 if smoke else None,
        )
        wa_artifacts["political_contribution_metadata_path"] = Path(metadata_path)
        return {
            "source_count": 1,
            "metadata_paths": {
                "waec_ods_political_contributions": str(metadata_path),
            },
            "smoke_max_pages": 1 if smoke else None,
        }

    manifest = PipelineManifest(
        pipeline_name="state_local",
        run_id=f"state_local_wa_{timestamp(started)}",
        status="running",
        started_at=started.isoformat(),
        git_commit=_git_commit(),
        dependency_versions=_dependency_versions(),
        parameters={
            "jurisdiction": "wa",
            "source_family": WAEC_SOURCE_DATASET,
            "smoke": smoke,
            "loads_database": False,
            "claim_boundary": (
                "Fetch and normalize Western Australian Electoral Commission "
                "Online Disclosure System published political contribution rows. "
                "Rows are source-backed donor-to-political-entity contribution "
                "records at WAEC's disclosure level; they are not personal receipt "
                "by a representative, evidence of wrongdoing, or causal claims."
            ),
        },
    )

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("fetch_waec_political_contribution_pages", fetch_wa_sources),
        (
            "normalize_waec_political_contributions",
            lambda: normalize_waec_political_contributions(
                metadata_path=wa_artifacts["political_contribution_metadata_path"],
            ),
        ),
    ]

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
