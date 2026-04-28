from __future__ import annotations

import json
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import shapefile
from pyproj import CRS, Transformer

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.discovered_sources import (
    child_source_id,
    source_from_discovered_link,
)
from au_politics_money.ingest.discovery import (
    latest_discovered_links_path,
    read_discovered_links,
)
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.sources import get_source
from au_politics_money.models import DiscoveredLink


PARSER_NAME = "aec_federal_boundaries_pyshp_v1"
PARSER_VERSION = "1"
BOUNDARY_SET = "aec_federal_2025_current"
BOUNDARY_SOURCE_ID = "aec_federal_boundaries_gis"
OUTPUT_CRS = "EPSG:4326"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def select_current_national_esri_link(links: list[DiscoveredLink]) -> DiscoveredLink:
    """Select the current national AEC ESRI shapefile link from discovered GIS links.

    AEC's GIS page lists the current national download first, then state-specific
    and superseded downloads. The URL naming convention for the national current
    file is `AUS-<month>-<year>-esri.zip`; keep this selector conservative so a
    changed page shape fails visibly rather than fetching a state or superseded
    file by accident.
    """

    candidates: list[DiscoveredLink] = []
    for link in links:
        url_lower = link.url.lower()
        title_lower = link.title.lower()
        file_name = Path(link.url).name.lower()
        if not file_name.endswith(".zip"):
            continue
        if "esri" not in url_lower and "esri" not in title_lower and ".shp" not in title_lower:
            continue
        if re.match(r"aus-[a-z]+-\d{4}-esri\.zip$", file_name):
            candidates.append(link)

    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one current national AEC ESRI boundary ZIP link; "
            f"found {len(candidates)}."
        )
    return candidates[0]


def fetch_current_aec_boundary_zip(*, refetch: bool = False) -> Path:
    parent = get_source(BOUNDARY_SOURCE_ID)
    links_path = latest_discovered_links_path(parent.source_id)
    if links_path is None:
        raise FileNotFoundError(
            "No discovered AEC GIS links found. Run `au-politics-money discover-links "
            "aec_federal_boundaries_gis` first."
        )

    link = select_current_national_esri_link(read_discovered_links(links_path))
    child_source = source_from_discovered_link(parent, link)
    if not refetch:
        latest = _latest_metadata_path(child_source.source_id)
        if latest is not None:
            return latest
    return fetch_source(child_source, timeout=120)


def _find_single_shapefile(extract_dir: Path) -> Path:
    shapefiles = sorted(extract_dir.glob("*.shp"))
    if len(shapefiles) != 1:
        raise RuntimeError(f"Expected exactly one shapefile in AEC boundary ZIP; found {len(shapefiles)}.")
    return shapefiles[0]


def _read_prj(shp_path: Path) -> str:
    prj_path = shp_path.with_suffix(".prj")
    if not prj_path.exists():
        raise FileNotFoundError(f"Missing projection file for shapefile: {prj_path}")
    return prj_path.read_text(encoding="utf-8")


def _transform_position(position: tuple[float, ...], transformer: Transformer | None) -> list[float]:
    x, y = float(position[0]), float(position[1])
    if transformer is not None:
        x, y = transformer.transform(x, y)
    return [round(x, 8), round(y, 8)]


def _transform_coordinates(value: Any, transformer: Transformer | None) -> Any:
    if isinstance(value, tuple):
        return _transform_position(value, transformer)
    if isinstance(value, list) and value and isinstance(value[0], (int, float)):
        return _transform_position(tuple(value), transformer)
    return [_transform_coordinates(child, transformer) for child in value]


def _field_names(reader: shapefile.Reader) -> list[str]:
    return [str(field[0]) for field in reader.fields[1:]]


def _record_dict(field_names: list[str], record: shapefile.ShapeRecord) -> dict[str, Any]:
    return dict(zip(field_names, record.record, strict=False))


def _feature_properties(raw: dict[str, Any], *, metadata_path: Path, source_crs: str) -> dict[str, Any]:
    division_name = str(raw.get("Elect_div") or raw.get("Sortname") or "").strip()
    if not division_name:
        raise RuntimeError(f"AEC boundary row is missing Elect_div/Sortname: {raw}")
    return {
        "boundary_set": BOUNDARY_SET,
        "chamber": "house",
        "division_name": division_name,
        "division_number": raw.get("E_div_numb"),
        "sort_name": raw.get("Sortname") or division_name,
        "num_ccds": raw.get("Numccds"),
        "actual_enrolment": raw.get("Actual"),
        "projected_enrolment": raw.get("Projected"),
        "total_population": raw.get("Total_Popu"),
        "australian_citizens": raw.get("Australian"),
        "area_sqkm": raw.get("Area_SqKm"),
        "source_crs": source_crs,
        "output_crs": OUTPUT_CRS,
        "source_metadata_path": str(metadata_path.resolve()),
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "source_row": raw,
    }


def extract_aec_boundaries_from_zip(
    zip_path: Path,
    *,
    metadata_path: Path,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        extract_dir = Path(tmp_dir)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
        shp_path = _find_single_shapefile(extract_dir)
        source_crs = CRS.from_wkt(_read_prj(shp_path))
        output_crs = CRS.from_user_input(OUTPUT_CRS)
        transformer = None
        if source_crs != output_crs:
            transformer = Transformer.from_crs(source_crs, output_crs, always_xy=True)

        reader = shapefile.Reader(str(shp_path))
        field_names = _field_names(reader)
        features = []
        for shape_record in reader.iterShapeRecords():
            geometry = shape_record.shape.__geo_interface__
            if geometry["type"] not in {"Polygon", "MultiPolygon"}:
                raise RuntimeError(f"Unexpected AEC boundary geometry type: {geometry['type']}")
            properties = _feature_properties(
                _record_dict(field_names, shape_record),
                metadata_path=metadata_path,
                source_crs=source_crs.to_string(),
            )
            features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": geometry["type"],
                        "coordinates": _transform_coordinates(geometry["coordinates"], transformer),
                    },
                }
            )

    return {
        "type": "FeatureCollection",
        "name": BOUNDARY_SET,
        "crs": {"type": "name", "properties": {"name": OUTPUT_CRS}},
        "features": features,
    }


def extract_current_aec_boundaries(
    *,
    metadata_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = metadata_path or fetch_current_aec_boundary_zip(refetch=False)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    zip_path = Path(metadata["body_path"])
    feature_collection = extract_aec_boundaries_from_zip(zip_path, metadata_path=metadata_path)
    timestamp = _timestamp()
    output_dir = processed_dir / "aec_federal_boundaries"
    output_dir.mkdir(parents=True, exist_ok=True)

    geojson_path = output_dir / f"{timestamp}.geojson"
    geojson_path.write_text(
        json.dumps(feature_collection, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    division_names = sorted(
        feature["properties"]["division_name"] for feature in feature_collection["features"]
    )
    summary = {
        "boundary_set": BOUNDARY_SET,
        "feature_count": len(feature_collection["features"]),
        "generated_at": timestamp,
        "geojson_path": str(geojson_path.resolve()),
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "raw_metadata_path": str(metadata_path.resolve()),
        "raw_sha256": metadata.get("sha256"),
        "source_id": metadata["source"]["source_id"],
        "source_url": metadata["source"]["url"],
        "division_names": division_names,
        "missing_expected_count_flag": len(feature_collection["features"]) != 150,
    }
    summary_path = output_dir / f"{timestamp}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def latest_aec_boundaries_geojson(processed_dir: Path = PROCESSED_DIR) -> Path | None:
    boundary_dir = processed_dir / "aec_federal_boundaries"
    if not boundary_dir.exists():
        return None
    candidates = sorted(boundary_dir.glob("*.geojson"), reverse=True)
    return candidates[0] if candidates else None


def boundary_source_id_from_link(link: DiscoveredLink) -> str:
    return child_source_id(BOUNDARY_SOURCE_ID, link)
