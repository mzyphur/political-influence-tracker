from __future__ import annotations

import json
from pathlib import Path

import pytest

from au_politics_money.ingest import qld_boundaries


def _write_metadata(tmp_path: Path, feature_count: int = 93) -> Path:
    features = []
    for index in range(feature_count):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "adminareaname": "MCDOWALL" if index == 0 else f"TEST DISTRICT {index}",
                    "id": str(index + 1),
                    "date_effective": 1509235200000,
                    "objectid": index + 1,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [152.0 + index * 0.001, -27.0],
                            [152.001 + index * 0.001, -27.0],
                            [152.001 + index * 0.001, -27.001],
                            [152.0 + index * 0.001, -27.001],
                            [152.0 + index * 0.001, -27.0],
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
                "sha256": "fixture-sha",
                "source": {
                    "source_id": qld_boundaries.SOURCE_ID,
                    "url": "https://example.test/qld-boundaries",
                },
            }
        ),
        encoding="utf-8",
    )
    return metadata_path


def test_extract_qld_state_electorate_boundaries_normalizes_geojson(tmp_path: Path) -> None:
    metadata_path = _write_metadata(tmp_path)

    summary_path = qld_boundaries.extract_qld_state_electorate_boundaries(
        metadata_path=metadata_path,
        processed_dir=tmp_path / "processed",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["feature_count"] == 93
    assert summary["boundary_set"] == "qld_state_2017_current"

    geojson = json.loads(Path(summary["geojson_path"]).read_text(encoding="utf-8"))
    first = geojson["features"][0]
    assert first["properties"]["division_name"] == "McDowall"
    assert first["properties"]["official_name"] == "MCDOWALL"
    assert first["properties"]["date_effective"] == "2017-10-29"
    assert first["properties"]["state_or_territory"] == "QLD"
    assert first["properties"]["source_metadata_path"] == str(metadata_path.resolve())


def test_extract_qld_state_electorate_boundaries_fails_on_incomplete_feature_count(
    tmp_path: Path,
) -> None:
    metadata_path = _write_metadata(tmp_path, feature_count=92)

    with pytest.raises(RuntimeError, match="Expected 93 QLD state electorate"):
        qld_boundaries.extract_qld_state_electorate_boundaries(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )
