from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.ingest import qld_council_boundaries


def _write_metadata(
    tmp_path: Path,
    *,
    feature_count: int = 78,
    geometry_type: str = "Polygon",
) -> Path:
    features = []
    for index in range(feature_count):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "lga": "AURUKUN SHIRE" if index == 0 else f"Fixture Council {index}",
                    "abbrev_name": "AURUKUN" if index == 0 else f"FIXTURE {index}",
                    "lga_code": str(250 + index),
                    "objectid": index + 1,
                    "ca_area_sqkm": 100.5 + index,
                },
                "geometry": {
                    "type": geometry_type,
                    "coordinates": [
                        [
                            [142.0 + index * 0.001, -12.0],
                            [142.001 + index * 0.001, -12.0],
                            [142.001 + index * 0.001, -12.001],
                            [142.0 + index * 0.001, -12.001],
                            [142.0 + index * 0.001, -12.0],
                        ]
                    ],
                },
            }
        )
    body_path = tmp_path / "body.json"
    body_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "sha256": hashlib.sha256(body_path.read_bytes()).hexdigest(),
                "source": {
                    "source_id": qld_council_boundaries.SOURCE_ID,
                    "url": "https://example.test/qld-council-boundaries",
                },
            }
        ),
        encoding="utf-8",
    )
    return metadata_path


def test_extract_qld_council_boundaries_normalizes_geojson(tmp_path: Path) -> None:
    metadata_path = _write_metadata(tmp_path)

    summary_path = qld_council_boundaries.extract_qld_council_boundaries(
        metadata_path=metadata_path,
        processed_dir=tmp_path / "processed",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["feature_count"] == 78
    assert summary["boundary_set"] == "qld_local_government_current"
    assert summary["source_id"] == qld_council_boundaries.SOURCE_ID
    assert summary["raw_metadata_sha256"] == hashlib.sha256(metadata_path.read_bytes()).hexdigest()

    geojson_path = Path(summary["geojson_path"])
    assert summary["geojson_sha256"] == hashlib.sha256(geojson_path.read_bytes()).hexdigest()
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    first = geojson["features"][0]
    assert first["properties"]["chamber"] == "council"
    assert first["properties"]["division_name"] == "Aurukun Shire"
    assert first["properties"]["official_name"] == "AURUKUN SHIRE"
    assert first["properties"]["lga_code"] == "250"
    assert first["properties"]["state_or_territory"] == "QLD"
    assert first["properties"]["source_metadata_path"] == str(metadata_path.resolve())


def test_extract_qld_council_boundaries_fails_on_incomplete_feature_count(
    tmp_path: Path,
) -> None:
    metadata_path = _write_metadata(tmp_path, feature_count=77)

    with pytest.raises(RuntimeError, match="Expected 78 QLD local-government"):
        qld_council_boundaries.extract_qld_council_boundaries(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )


def test_extract_qld_council_boundaries_fails_on_unexpected_geometry_type(
    tmp_path: Path,
) -> None:
    metadata_path = _write_metadata(tmp_path, geometry_type="Point")

    with pytest.raises(RuntimeError, match="Unexpected QLD council boundary geometry type"):
        qld_council_boundaries.extract_qld_council_boundaries(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )
