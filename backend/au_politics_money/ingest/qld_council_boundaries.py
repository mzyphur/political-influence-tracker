from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.sources import get_source


PARSER_NAME = "qld_local_government_boundaries_arcgis_geojson_v1"
PARSER_VERSION = "1"
SOURCE_ID = "qld_local_government_boundaries_arcgis"
BOUNDARY_SET = "qld_local_government_current"
EXPECTED_LOCAL_GOVERNMENT_COUNT = 78
OUTPUT_CRS = "EPSG:4326"
SOURCE_CRS = "EPSG:4283"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_metadata_path(source_id: str, raw_dir: Path = RAW_DIR) -> Path | None:
    source_dir = raw_dir / source_id
    if not source_dir.exists():
        return None
    for run_dir in sorted(source_dir.iterdir(), reverse=True):
        metadata_path = run_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if metadata.get("ok") is False:
            continue
        if Path(metadata.get("body_path", "")).exists():
            return metadata_path
    return None


def fetch_qld_council_boundaries(*, refetch: bool = False) -> Path:
    source = get_source(SOURCE_ID)
    if not refetch:
        latest = _latest_metadata_path(source.source_id)
        if latest is not None:
            return latest
    return fetch_source(source, timeout=120)


def _display_council_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return ""
    if not cleaned.isupper():
        return cleaned

    def format_piece(piece: str) -> str:
        if not piece:
            return piece
        if piece.startswith("MC") and len(piece) > 2:
            return "Mc" + piece[2:3].upper() + piece[3:].lower()
        return piece[:1].upper() + piece[1:].lower()

    words = []
    for word in cleaned.split(" "):
        hyphen_parts = [
            "-".join(format_piece(part) for part in segment.split("-"))
            for segment in word.split("/")
        ]
        words.append("/".join(hyphen_parts))
    return " ".join(words)


def _normalize_feature(feature: dict[str, Any], *, metadata_path: Path) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise RuntimeError(f"Unexpected QLD council boundary geometry type: {geometry.get('type')}")

    official_name = str(properties.get("lga") or "").strip()
    display_name = _display_council_name(official_name)
    if not display_name:
        raise RuntimeError(f"QLD council boundary row is missing lga: {properties}")

    return {
        "type": "Feature",
        "properties": {
            "boundary_set": BOUNDARY_SET,
            "chamber": "council",
            "division_name": display_name,
            "official_name": official_name,
            "state_or_territory": "QLD",
            "lga_code": str(properties.get("lga_code") or "").strip(),
            "abbrev_name": str(properties.get("abbrev_name") or "").strip(),
            "objectid": properties.get("objectid"),
            "area_sqkm": properties.get("ca_area_sqkm"),
            "source_crs": SOURCE_CRS,
            "output_crs": OUTPUT_CRS,
            "source_metadata_path": str(metadata_path.resolve()),
            "parser_name": PARSER_NAME,
            "parser_version": PARSER_VERSION,
            "source_row": properties,
        },
        "geometry": geometry,
    }


def extract_qld_council_boundaries(
    *,
    metadata_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = metadata_path or fetch_qld_council_boundaries(refetch=False)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source_id = metadata.get("source", {}).get("source_id")
    if source_id != SOURCE_ID:
        raise RuntimeError(f"Expected source_id {SOURCE_ID}; found {source_id}.")
    body_path = Path(metadata["body_path"])
    source_geojson = json.loads(body_path.read_text(encoding="utf-8"))
    features = [
        _normalize_feature(feature, metadata_path=metadata_path)
        for feature in source_geojson.get("features", [])
    ]
    if len(features) != EXPECTED_LOCAL_GOVERNMENT_COUNT:
        raise RuntimeError(
            "Expected "
            f"{EXPECTED_LOCAL_GOVERNMENT_COUNT} QLD local-government boundary features; "
            f"found {len(features)}."
        )

    timestamp = _timestamp()
    output_dir = processed_dir / "qld_council_boundaries"
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_collection = {
        "type": "FeatureCollection",
        "name": BOUNDARY_SET,
        "crs": {"type": "name", "properties": {"name": OUTPUT_CRS}},
        "features": features,
    }
    geojson_path = output_dir / f"{timestamp}.geojson"
    geojson_path.write_text(
        json.dumps(feature_collection, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    geojson_sha256 = _sha256_path(geojson_path)
    division_names = sorted(feature["properties"]["division_name"] for feature in features)
    summary = {
        "boundary_set": BOUNDARY_SET,
        "feature_count": len(features),
        "generated_at": timestamp,
        "geojson_path": str(geojson_path.resolve()),
        "geojson_sha256": geojson_sha256,
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "raw_metadata_path": str(metadata_path.resolve()),
        "raw_metadata_sha256": _sha256_path(metadata_path),
        "raw_sha256": metadata.get("sha256"),
        "source_id": metadata["source"]["source_id"],
        "source_url": metadata["source"]["url"],
        "division_names": division_names,
        "missing_expected_count_flag": len(features) != EXPECTED_LOCAL_GOVERNMENT_COUNT,
        "claim_boundary": (
            "Official Queensland local-government area geometry only. These "
            "boundaries do not by themselves attribute ECQ disclosure records to "
            "a councillor, candidate, council, state MP, or federal MP."
        ),
    }
    summary_path = output_dir / f"{timestamp}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def latest_qld_council_boundaries_geojson(processed_dir: Path = PROCESSED_DIR) -> Path | None:
    boundary_dir = processed_dir / "qld_council_boundaries"
    if not boundary_dir.exists():
        return None
    candidates = sorted(boundary_dir.glob("*.geojson"), reverse=True)
    return candidates[0] if candidates else None
