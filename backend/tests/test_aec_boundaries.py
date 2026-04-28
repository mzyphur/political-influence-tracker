from __future__ import annotations

import json
import zipfile
from pathlib import Path

import shapefile

from au_politics_money.ingest.aec_boundaries import (
    BOUNDARY_SET,
    extract_aec_boundaries_from_zip,
    select_current_national_esri_link,
)
from au_politics_money.models import DiscoveredLink


def test_select_current_national_esri_link_is_conservative() -> None:
    links = [
        DiscoveredLink(
            parent_source_id="aec_federal_boundaries_gis",
            title="ESRI (.shp) [ZIP 3.14MB]",
            url="https://www.aec.gov.au/Electorates/gis/files/Vic-october-2024-esri.zip",
            link_type="zip_or_download",
        ),
        DiscoveredLink(
            parent_source_id="aec_federal_boundaries_gis",
            title="ESRI (.shp) [ZIP 22.2MB]",
            url="https://www.aec.gov.au/Electorates/files/2025/AUS-March-2025-esri.zip",
            link_type="zip_or_download",
        ),
    ]

    selected = select_current_national_esri_link(links)

    assert selected.url.endswith("AUS-March-2025-esri.zip")


def _write_test_shapefile_zip(tmp_path: Path) -> Path:
    base_path = tmp_path / "AUS_ELB_region"
    writer = shapefile.Writer(str(base_path), shapeType=shapefile.POLYGON)
    writer.field("E_div_numb", "N", size=11, decimal=0)
    writer.field("Elect_div", "C", size=30)
    writer.field("Numccds", "N", size=11, decimal=0)
    writer.field("Actual", "N", size=11, decimal=0)
    writer.field("Projected", "N", size=11, decimal=0)
    writer.field("Total_Popu", "N", size=11, decimal=0)
    writer.field("Australian", "N", size=11, decimal=0)
    writer.field("Area_SqKm", "N", size=31, decimal=15)
    writer.field("Sortname", "C", size=30)
    writer.poly(
        [
            [
                [149.0, -35.0],
                [149.1, -35.0],
                [149.1, -35.1],
                [149.0, -35.1],
                [149.0, -35.0],
            ]
        ]
    )
    writer.record(1, "Bean", 420, 0, 0, 0, 0, 1913.71, "Bean")
    writer.close()
    (tmp_path / "AUS_ELB_region.prj").write_text(
        'GEOGCS["WGS 84",DATUM["WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],'
        'AUTHORITY["EPSG","4326"]]',
        encoding="utf-8",
    )

    zip_path = tmp_path / "boundaries.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for suffix in (".shp", ".shx", ".dbf", ".prj"):
            archive.write(tmp_path / f"AUS_ELB_region{suffix}", f"AUS_ELB_region{suffix}")
    return zip_path


def test_extract_aec_boundaries_from_zip_outputs_geojson(tmp_path: Path) -> None:
    zip_path = _write_test_shapefile_zip(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"body_path": str(zip_path)}), encoding="utf-8")

    geojson = extract_aec_boundaries_from_zip(zip_path, metadata_path=metadata_path)

    assert geojson["type"] == "FeatureCollection"
    assert geojson["features"][0]["properties"]["boundary_set"] == BOUNDARY_SET
    assert geojson["features"][0]["properties"]["division_name"] == "Bean"
    assert geojson["features"][0]["geometry"]["type"] == "Polygon"
    assert geojson["features"][0]["geometry"]["coordinates"][0][0] == [149.0, -35.0]
