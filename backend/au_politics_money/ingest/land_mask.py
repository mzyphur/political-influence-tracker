from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import shapefile
from pyproj import CRS, Transformer

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.sources import get_source

SOURCE_ID = "natural_earth_admin0_countries_10m"
PHYSICAL_LAND_SOURCE_ID = "natural_earth_physical_land_10m"
AIMS_COASTLINE_SOURCE_ID = "aims_australian_coastline_50k_2024_simp"
PARSER_NAME = "natural_earth_admin0_country_land_mask_pyshp_v1"
PARSER_VERSION = "1"
AIMS_COASTLINE_PARSER_NAME = "aims_australian_coastline_50k_land_mask_pyshp_v1"
AIMS_COASTLINE_PARSER_VERSION = "1"
OUTPUT_CRS = "EPSG:4326"
AIMS_COASTLINE_LIMITATIONS = (
    "Catalogue licence is currently listed as Not Specified; do not redistribute "
    "raw or processed coastline files publicly until reuse terms are confirmed. "
    "Known source limitations include possible false land from turbid water, "
    "breaking waves, shallow water, jetties, oil rigs, and bridges, plus some "
    "version 1-1 ocean-connected rivers and water bodies being filled or bridged."
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_metadata_path(source_id: str = SOURCE_ID, raw_dir: Path = RAW_DIR) -> Path | None:
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


def fetch_natural_earth_admin0_zip(*, refetch: bool = False) -> Path:
    if not refetch:
        latest = _latest_metadata_path()
        if latest is not None:
            return latest
    return fetch_source(get_source(SOURCE_ID), timeout=120)


def fetch_natural_earth_physical_land_zip(*, refetch: bool = False) -> Path:
    if not refetch:
        latest = _latest_metadata_path(PHYSICAL_LAND_SOURCE_ID)
        if latest is not None:
            return latest
    return fetch_source(get_source(PHYSICAL_LAND_SOURCE_ID), timeout=120)


def fetch_aims_australian_coastline_zip(*, refetch: bool = False) -> Path:
    if not refetch:
        latest = _latest_metadata_path(AIMS_COASTLINE_SOURCE_ID)
        if latest is not None:
            return latest
    return fetch_source(get_source(AIMS_COASTLINE_SOURCE_ID), timeout=180)


def _find_single_shapefile(extract_dir: Path) -> Path:
    shapefiles = sorted(extract_dir.glob("**/*.shp"))
    if len(shapefiles) != 1:
        raise RuntimeError(f"Expected exactly one shapefile in ZIP; found {len(shapefiles)}.")
    return shapefiles[0]


def _read_prj(shp_path: Path) -> str:
    prj_path = shp_path.with_suffix(".prj")
    if not prj_path.exists():
        raise FileNotFoundError(f"Missing projection file for shapefile: {prj_path}")
    return prj_path.read_text(encoding="utf-8")


def _stable_shapefile_component_hash(shp_path: Path) -> str:
    digest = hashlib.sha256()
    for suffix in (".cpg", ".dbf", ".prj", ".shp", ".shx"):
        component_path = shp_path.with_suffix(suffix)
        if not component_path.exists():
            continue
        digest.update(component_path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(component_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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


def _matches_country(raw: dict[str, Any], country_name: str) -> bool:
    expected = country_name.casefold()
    return any(
        str(raw.get(field) or "").casefold() == expected
        for field in ("ADMIN", "NAME", "NAME_LONG", "SOVEREIGNT")
    )


def _bbox_intersects(
    shape_record: shapefile.ShapeRecord,
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> bool:
    shape_min_x, shape_min_y, shape_max_x, shape_max_y = shape_record.shape.bbox
    return not (
        shape_max_x < min_x
        or shape_min_x > max_x
        or shape_max_y < min_y
        or shape_min_y > max_y
    )


def extract_natural_earth_country_land_mask(
    *,
    country_name: str = "Australia",
    metadata_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = metadata_path or fetch_natural_earth_admin0_zip(refetch=False)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    zip_path = Path(metadata["body_path"])

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
            raw = _record_dict(field_names, shape_record)
            if not _matches_country(raw, country_name):
                continue
            geometry = shape_record.shape.__geo_interface__
            if geometry["type"] not in {"Polygon", "MultiPolygon"}:
                raise RuntimeError(f"Unexpected Natural Earth geometry type: {geometry['type']}")
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "country_name": country_name,
                        "source_id": SOURCE_ID,
                        "source_metadata_path": str(metadata_path.resolve()),
                        "source_crs": source_crs.to_string(),
                        "output_crs": OUTPUT_CRS,
                        "parser_name": PARSER_NAME,
                        "parser_version": PARSER_VERSION,
                        "source_row": raw,
                    },
                    "geometry": {
                        "type": geometry["type"],
                        "coordinates": _transform_coordinates(geometry["coordinates"], transformer),
                    },
                }
            )

    if not features:
        raise RuntimeError(f"No Natural Earth country features found for {country_name!r}.")

    timestamp = _timestamp()
    output_dir = processed_dir / "natural_earth_land_mask"
    output_dir.mkdir(parents=True, exist_ok=True)
    geojson_path = output_dir / f"{timestamp}.{country_name.lower().replace(' ', '_')}.geojson"
    feature_collection = {
        "type": "FeatureCollection",
        "name": f"natural_earth_admin0_{country_name.lower().replace(' ', '_')}",
        "crs": {"type": "name", "properties": {"name": OUTPUT_CRS}},
        "features": features,
    }
    geojson_path.write_text(
        json.dumps(feature_collection, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = {
        "country_name": country_name,
        "feature_count": len(features),
        "generated_at": timestamp,
        "geojson_path": str(geojson_path.resolve()),
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "raw_metadata_path": str(metadata_path.resolve()),
        "raw_sha256": metadata.get("sha256"),
        "source_id": SOURCE_ID,
        "source_url": metadata["source"]["url"],
    }
    summary_path = output_dir / f"{timestamp}.{country_name.lower().replace(' ', '_')}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def extract_natural_earth_physical_land_mask(
    *,
    country_name: str = "Australia",
    metadata_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = metadata_path or fetch_natural_earth_physical_land_zip(refetch=False)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    zip_path = Path(metadata["body_path"])
    bbox = {
        "min_x": 110.0,
        "min_y": -45.0,
        "max_x": 155.0,
        "max_y": -8.0,
    }

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
        features = []
        for shape_record in reader.iterShapeRecords():
            if not _bbox_intersects(shape_record, **bbox):
                continue
            geometry = shape_record.shape.__geo_interface__
            if geometry["type"] not in {"Polygon", "MultiPolygon"}:
                raise RuntimeError(f"Unexpected Natural Earth geometry type: {geometry['type']}")
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "country_name": country_name,
                        "source_id": PHYSICAL_LAND_SOURCE_ID,
                        "source_metadata_path": str(metadata_path.resolve()),
                        "source_crs": source_crs.to_string(),
                        "output_crs": OUTPUT_CRS,
                        "parser_name": PARSER_NAME,
                        "parser_version": PARSER_VERSION,
                        "clip_bbox": bbox,
                    },
                    "geometry": {
                        "type": geometry["type"],
                        "coordinates": _transform_coordinates(geometry["coordinates"], transformer),
                    },
                }
            )

    if not features:
        raise RuntimeError("No Natural Earth physical land features intersected Australia bbox.")

    timestamp = _timestamp()
    output_dir = processed_dir / "natural_earth_physical_land_mask"
    output_dir.mkdir(parents=True, exist_ok=True)
    country_slug = country_name.lower().replace(" ", "_")
    geojson_path = output_dir / f"{timestamp}.{country_slug}.geojson"
    feature_collection = {
        "type": "FeatureCollection",
        "name": f"natural_earth_physical_land_{country_slug}",
        "crs": {"type": "name", "properties": {"name": OUTPUT_CRS}},
        "features": features,
    }
    geojson_path.write_text(
        json.dumps(feature_collection, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = {
        "country_name": country_name,
        "feature_count": len(features),
        "generated_at": timestamp,
        "geojson_path": str(geojson_path.resolve()),
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "raw_metadata_path": str(metadata_path.resolve()),
        "raw_sha256": metadata.get("sha256"),
        "source_id": PHYSICAL_LAND_SOURCE_ID,
        "source_url": metadata["source"]["url"],
        "clip_bbox": bbox,
    }
    summary_path = output_dir / f"{timestamp}.{country_slug}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def extract_aims_australian_coastline_land_mask(
    *,
    country_name: str = "Australia",
    metadata_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if country_name.casefold() != "australia":
        raise ValueError("AIMS Australian coastline land mask only supports country_name='Australia'.")
    country_name = "Australia"
    metadata_path = metadata_path or fetch_aims_australian_coastline_zip(refetch=False)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    zip_path = Path(metadata["body_path"])

    with tempfile.TemporaryDirectory() as tmp_dir:
        extract_dir = Path(tmp_dir)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
        shp_path = _find_single_shapefile(extract_dir)
        stable_component_sha256 = _stable_shapefile_component_hash(shp_path)
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
                raise RuntimeError(f"Unexpected AIMS coastline geometry type: {geometry['type']}")
            raw = _record_dict(field_names, shape_record)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "country_name": country_name,
                        "source_id": AIMS_COASTLINE_SOURCE_ID,
                        "source_metadata_path": str(metadata_path.resolve()),
                        "source_crs": source_crs.to_string(),
                        "output_crs": OUTPUT_CRS,
                        "parser_name": AIMS_COASTLINE_PARSER_NAME,
                        "parser_version": AIMS_COASTLINE_PARSER_VERSION,
                        "source_limitations": AIMS_COASTLINE_LIMITATIONS,
                        "source_row": raw,
                    },
                    "geometry": {
                        "type": geometry["type"],
                        "coordinates": _transform_coordinates(geometry["coordinates"], transformer),
                    },
                }
            )

    if not features:
        raise RuntimeError("No AIMS Australian coastline features found.")

    timestamp = _timestamp()
    output_dir = processed_dir / "aims_australian_coastline_land_mask"
    output_dir.mkdir(parents=True, exist_ok=True)
    country_slug = country_name.lower().replace(" ", "_")
    geojson_path = output_dir / f"{timestamp}.{country_slug}.geojson"
    feature_collection = {
        "type": "FeatureCollection",
        "name": f"aims_australian_coastline_50k_{country_slug}",
        "crs": {"type": "name", "properties": {"name": OUTPUT_CRS}},
        "features": features,
    }
    geojson_path.write_text(
        json.dumps(feature_collection, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = {
        "country_name": country_name,
        "feature_count": len(features),
        "generated_at": timestamp,
        "geojson_path": str(geojson_path.resolve()),
        "parser_name": AIMS_COASTLINE_PARSER_NAME,
        "parser_version": AIMS_COASTLINE_PARSER_VERSION,
        "raw_metadata_path": str(metadata_path.resolve()),
        "raw_sha256": metadata.get("sha256"),
        "extracted_component_sha256": stable_component_sha256,
        "source_id": AIMS_COASTLINE_SOURCE_ID,
        "source_url": metadata["source"]["url"],
        "source_limitations": AIMS_COASTLINE_LIMITATIONS,
    }
    summary_path = output_dir / f"{timestamp}.{country_slug}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def latest_country_land_mask_geojson(
    *,
    country_name: str = "Australia",
    processed_dir: Path = PROCESSED_DIR,
) -> Path | None:
    mask_dir = processed_dir / "natural_earth_land_mask"
    if not mask_dir.exists():
        return None
    country_slug = country_name.lower().replace(" ", "_")
    candidates = sorted(mask_dir.glob(f"*.{country_slug}.geojson"), reverse=True)
    return candidates[0] if candidates else None


def latest_physical_land_mask_geojson(
    *,
    country_name: str = "Australia",
    processed_dir: Path = PROCESSED_DIR,
) -> Path | None:
    mask_dir = processed_dir / "natural_earth_physical_land_mask"
    if not mask_dir.exists():
        return None
    country_slug = country_name.lower().replace(" ", "_")
    candidates = sorted(mask_dir.glob(f"*.{country_slug}.geojson"), reverse=True)
    return candidates[0] if candidates else None


def latest_aims_australian_coastline_land_mask_geojson(
    *,
    country_name: str = "Australia",
    processed_dir: Path = PROCESSED_DIR,
) -> Path | None:
    mask_dir = processed_dir / "aims_australian_coastline_land_mask"
    if not mask_dir.exists():
        return None
    country_slug = country_name.lower().replace(" ", "_")
    candidates = sorted(mask_dir.glob(f"*.{country_slug}.geojson"), reverse=True)
    return candidates[0] if candidates else None
