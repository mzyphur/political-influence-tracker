import csv
import json
from pathlib import Path

import pytest

from au_politics_money.ingest import official_identifiers as official_identifier_module
from au_politics_money.ingest.official_identifiers import (
    AbnLookupWebServiceError,
    MissingAbnLookupGuid,
    extract_official_identifiers_from_file,
    fetch_abn_lookup_web_record,
    fetch_official_identifier_bulk_resources,
    format_abn,
    format_acn,
    is_valid_abn,
    is_valid_acn,
    iter_abn_bulk_records,
    iter_abn_lookup_web_records,
    iter_acnc_charity_records,
    iter_asic_company_records,
    latest_official_identifier_jsonl_paths,
    select_official_identifier_bulk_resources,
    write_lobbyist_identifier_records,
)


def test_abn_and_acn_checksums_are_enforced() -> None:
    assert is_valid_abn("51 824 753 556")
    assert format_abn("51824753556") == "51 824 753 556"
    assert not is_valid_abn("51 824 753 557")

    assert is_valid_acn("123 456 780")
    assert format_acn("123456780") == "123 456 780"
    assert not is_valid_acn("123 456 781")


def test_iter_asic_company_records_normalises_identifiers(tmp_path: Path) -> None:
    source_metadata = tmp_path / "metadata.json"
    source_metadata.write_text("{}", encoding="utf-8")
    csv_path = tmp_path / "asic.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Company Name", "ACN", "ABN", "Status"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow(
            {
                "Company Name": "Example Energy Pty Ltd",
                "ACN": "123456780",
                "ABN": "51 824 753 556",
                "Status": "REGD",
            }
        )

    records = list(iter_asic_company_records(csv_path, source_metadata))

    assert len(records) == 1
    assert records[0]["display_name"] == "Example Energy Pty Ltd"
    assert records[0]["entity_type"] == "company"
    assert records[0]["identifiers"] == [
        {"identifier_type": "acn", "identifier_value": "123 456 780"},
        {"identifier_type": "abn", "identifier_value": "51 824 753 556"},
    ]
    assert records[0]["confidence"] == "exact_name_context"


def test_asic_stable_key_uses_official_id_before_name(tmp_path: Path) -> None:
    source_metadata = tmp_path / "metadata.json"
    source_metadata.write_text("{}", encoding="utf-8")
    csv_path = tmp_path / "asic.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Company Name", "ACN"], delimiter="\t")
        writer.writeheader()
        writer.writerow({"Company Name": "Old Example Name Pty Ltd", "ACN": "123456780"})
        writer.writerow({"Company Name": "New Example Name Pty Ltd", "ACN": "123456780"})

    records = list(iter_asic_company_records(csv_path, source_metadata))

    assert records[0]["stable_key"] == records[1]["stable_key"]


def test_iter_acnc_records_marks_registered_charities(tmp_path: Path) -> None:
    source_metadata = tmp_path / "metadata.json"
    source_metadata.write_text("{}", encoding="utf-8")
    csv_path = tmp_path / "acnc.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ABN",
                "Charity_Legal_Name",
                "Other_Organisation_Names",
                "Charity_Size",
                "PBI",
                "Advancing_Education",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ABN": "51 824 753 556",
                "Charity_Legal_Name": "Example Research Foundation",
                "Other_Organisation_Names": "ERF; Example Foundation",
                "Charity_Size": "Large",
                "PBI": "Y",
                "Advancing_Education": "Y",
            }
        )

    records = list(iter_acnc_charity_records(csv_path, source_metadata))

    assert records[0]["public_sector"] == "charities_nonprofits"
    assert records[0]["official_classification"] == "ACNC registered charity"
    assert records[0]["aliases"] == ["ERF", "Example Foundation"]
    assert records[0]["metadata"]["purpose_flags"] == ["advancing_education"]


def test_iter_abn_bulk_records_parses_xml_shape(tmp_path: Path) -> None:
    source_metadata = tmp_path / "metadata.json"
    source_metadata.write_text("{}", encoding="utf-8")
    xml_path = tmp_path / "abn.xml"
    xml_path.write_text(
        """
        <ABRPayloadSearchResults>
          <ABR>
            <ABN status="Active">51824753556</ABN>
            <EntityType EntityTypeText="Australian Private Company" />
            <ASICNumber>123456780</ASICNumber>
            <MainEntity>
              <NonIndividualName>
                <NonIndividualNameText>Example Energy Pty Ltd</NonIndividualNameText>
              </NonIndividualName>
            </MainEntity>
            <MainBusinessPhysicalAddress>
              <StateCode>VIC</StateCode>
              <Postcode>3000</Postcode>
            </MainBusinessPhysicalAddress>
          </ABR>
        </ABRPayloadSearchResults>
        """,
        encoding="utf-8",
    )

    records = list(iter_abn_bulk_records(xml_path, source_metadata))

    assert records[0]["display_name"] == "Example Energy Pty Ltd"
    assert records[0]["entity_type"] == "company"
    assert records[0]["metadata"]["state"] == "VIC"
    assert records[0]["identifiers"] == [
        {"identifier_type": "abn", "identifier_value": "51 824 753 556"},
        {"identifier_type": "acn", "identifier_value": "123 456 780"},
    ]


def test_iter_abn_lookup_web_records_parses_current_method_shape(tmp_path: Path) -> None:
    source_metadata = tmp_path / "metadata.json"
    source_metadata.write_text("{}", encoding="utf-8")
    xml_path = tmp_path / "abn_web.xml"
    xml_path.write_text(
        """
        <ABRPayloadSearchResults xmlns="http://abr.business.gov.au/ABRXMLSearch/">
          <response>
            <usageStatement>Public ABN Lookup response</usageStatement>
            <dateRegisterLastUpdated>2026-04-27</dateRegisterLastUpdated>
            <dateTimeRetrieved>2026-04-28T00:00:00</dateTimeRetrieved>
            <businessEntity202001>
              <ABN>
                <identifierValue>51824753556</identifierValue>
                <isCurrentIndicator>Y</isCurrentIndicator>
              </ABN>
              <entityStatus>
                <entityStatusCode>Active</entityStatusCode>
              </entityStatus>
              <ASICNumber>
                <identifierValue>123456780</identifierValue>
              </ASICNumber>
              <entityType>
                <entityDescription>Australian Private Company</entityDescription>
              </entityType>
              <mainName>
                <organisationName>Example Energy Pty Ltd</organisationName>
              </mainName>
              <businessName>
                <organisationName>Example Energy Retail</organisationName>
              </businessName>
              <mainTradingName>
                <organisationName>Legacy Example Trading</organisationName>
              </mainTradingName>
              <mainBusinessPhysicalAddress>
                <stateCode>VIC</stateCode>
                <postcode>3000</postcode>
              </mainBusinessPhysicalAddress>
            </businessEntity202001>
          </response>
        </ABRPayloadSearchResults>
        """,
        encoding="utf-8",
    )

    records = list(
        iter_abn_lookup_web_records(
            xml_path,
            source_metadata,
            lookup_method="SearchByABNv202001",
            include_historical_details=True,
        )
    )

    assert records[0]["source_record_type"] == "abn_web_service_entity"
    assert records[0]["display_name"] == "Example Energy Pty Ltd"
    assert records[0]["aliases"] == ["Example Energy Retail"]
    assert records[0]["status"] == "Active"
    assert records[0]["metadata"]["date_register_last_updated"] == "2026-04-27"
    assert "historical reference only" in records[0]["metadata"]["trading_name_caveat"]
    trading_observations = [
        item
        for item in records[0]["metadata"]["name_observations"]
        if item["name"] == "Legacy Example Trading"
    ]
    assert trading_observations[0]["is_trading_name"] is True
    assert trading_observations[0]["legal_status_caveat"]


def test_fetch_abn_lookup_web_record_redacts_guid_and_writes_identifiers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABN_LOOKUP_GUID", "SECRET-GUID")

    def fake_open_bytes_with_retries(request, *, timeout=60, tries=4):
        assert request.full_url.endswith("/SearchByABNv202001")
        assert b"authenticationGuid=SECRET-GUID" in request.data
        body = b"""
        <ABRPayloadSearchResults xmlns="http://abr.business.gov.au/ABRXMLSearch/">
          <request>SECRET-GUID</request>
          <response>
            <businessEntity202001>
              <ABN><identifierValue>51824753556</identifierValue></ABN>
              <entityStatus><entityStatusCode>Active</entityStatusCode></entityStatus>
              <mainName><organisationName>Example Energy Pty Ltd</organisationName></mainName>
            </businessEntity202001>
          </response>
        </ABRPayloadSearchResults>
        """
        return body, 200, {"Content-Type": "text/xml"}

    monkeypatch.setattr(
        official_identifier_module,
        "_open_bytes_with_retries",
        fake_open_bytes_with_retries,
    )

    summary_path = fetch_abn_lookup_web_record(
        "abn",
        "51 824 753 556",
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metadata = json.loads(Path(summary["source_metadata_path"]).read_text(encoding="utf-8"))
    body_text = Path(metadata["body_path"]).read_text(encoding="utf-8")
    records = [
        json.loads(line)
        for line in Path(summary["official_identifiers_jsonl"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert metadata["request_params"]["authenticationGuid"] == "redacted"
    assert "SECRET-GUID" not in json.dumps(metadata)
    assert "SECRET-GUID" not in body_text
    assert records[0]["display_name"] == "Example Energy Pty Ltd"
    assert records[0]["identifiers"] == [
        {"identifier_type": "abn", "identifier_value": "51 824 753 556"}
    ]
    assert Path(summary["official_identifiers_jsonl"]).name.endswith(
        "_abn_51824753556.jsonl"
    )


def test_fetch_abn_lookup_web_record_requires_guid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ABN_LOOKUP_GUID", raising=False)

    with pytest.raises(MissingAbnLookupGuid):
        fetch_abn_lookup_web_record(
            "abn",
            "51 824 753 556",
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
        )


def test_fetch_abn_lookup_web_record_fails_on_service_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABN_LOOKUP_GUID", "SECRET-GUID")

    def fake_open_bytes_with_retries(request, *, timeout=60, tries=4):
        body = b"""
        <ABRPayloadSearchResults xmlns="http://abr.business.gov.au/ABRXMLSearch/">
          <response>
            <exception>
              <exceptionCode>Search String</exceptionCode>
              <exceptionDescription>No records found</exceptionDescription>
            </exception>
          </response>
        </ABRPayloadSearchResults>
        """
        return body, 200, {"Content-Type": "text/xml"}

    monkeypatch.setattr(
        official_identifier_module,
        "_open_bytes_with_retries",
        fake_open_bytes_with_retries,
    )

    with pytest.raises(AbnLookupWebServiceError):
        fetch_abn_lookup_web_record(
            "abn",
            "51 824 753 556",
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
        )

    summaries = list((tmp_path / "processed" / "abn_lookup_web").glob("*.summary.json"))
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["ok"] is False
    assert summary["records_written"] == 0
    assert summary["response_context"]["exceptions"] == [
        {"code": "Search String", "description": "No records found"}
    ]


def test_fetch_abn_lookup_web_record_uses_current_acn_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABN_LOOKUP_GUID", "SECRET-GUID")

    def fake_open_bytes_with_retries(request, *, timeout=60, tries=4):
        assert request.full_url.endswith("/SearchByASICv201408")
        assert b"searchString=123456780" in request.data
        body = b"""
        <ABRPayloadSearchResults xmlns="http://abr.business.gov.au/ABRXMLSearch/">
          <response>
            <businessEntity201408>
              <ABN><identifierValue>51824753556</identifierValue></ABN>
              <ASICNumber><identifierValue>123456780</identifierValue></ASICNumber>
              <mainName><organisationName>Example Energy Pty Ltd</organisationName></mainName>
            </businessEntity201408>
          </response>
        </ABRPayloadSearchResults>
        """
        return body, 200, {"Content-Type": "text/xml"}

    monkeypatch.setattr(
        official_identifier_module,
        "_open_bytes_with_retries",
        fake_open_bytes_with_retries,
    )

    summary_path = fetch_abn_lookup_web_record(
        "acn",
        "123456780",
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["lookup_method"] == "SearchByASICv201408"
    assert Path(summary["official_identifiers_jsonl"]).name.endswith(
        "_acn_123456780.jsonl"
    )


def test_select_official_identifier_bulk_resources_prefers_supported_hints() -> None:
    discovery_payload = {
        "packages": [
            {
                "source_id": "asic_companies_dataset",
                "package_id": "asic-companies",
                "canonical_package_id": "asic-canonical",
                "resources": [
                    {
                        "id": "old",
                        "name": "Company Dataset - Historical",
                        "format": "CSV",
                        "url": "https://example.test/old.csv",
                    },
                    {
                        "id": "current",
                        "name": "Company Dataset - Current",
                        "format": "CSV",
                        "url": "https://example.test/current.csv",
                    },
                ],
            },
            {
                "source_id": "abn_lookup",
                "package_id": "abn-bulk-extract",
                "canonical_package_id": "abn-canonical",
                "resources": [
                    {
                        "id": "resource-list",
                        "name": "ABN Bulk Extract Resource List",
                        "format": "CSV",
                        "url": "https://example.test/resource-list.csv",
                    },
                    {
                        "id": "part-1",
                        "name": "ABN Bulk Extract Part 1",
                        "format": "ZIP",
                        "url": "https://example.test/part-1.zip",
                    },
                    {
                        "id": "part-2",
                        "name": "ABN Bulk Extract Part 2",
                        "format": "ZIP",
                        "url": "https://example.test/part-2.zip",
                    },
                ],
            },
        ]
    }

    selected = select_official_identifier_bulk_resources(discovery_payload)

    selected_by_source = {}
    for item in selected:
        selected_by_source.setdefault(item["source_id"], []).append(item["resource"]["id"])
    assert selected_by_source["asic_companies_dataset"] == ["current"]
    assert selected_by_source["abn_lookup"] == ["part-1", "part-2"]
    assert "resource-list" not in selected_by_source["abn_lookup"]


def test_fetch_official_identifier_bulk_resources_groups_multi_part_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery_path = tmp_path / "discovery.json"
    discovery_path.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "source_id": "asic_companies_dataset",
                        "package_id": "asic-companies",
                        "canonical_package_id": "asic-canonical",
                        "resources": [
                            {
                                "id": "asic-current",
                                "name": "Company Dataset - Current",
                                "format": "CSV",
                                "url": "https://example.test/asic.csv",
                            }
                        ],
                    },
                    {
                        "source_id": "abn_lookup",
                        "package_id": "abn-bulk-extract",
                        "canonical_package_id": "abn-canonical",
                        "resources": [
                            {
                                "id": "abn-part-1",
                                "name": "ABN Bulk Extract Part 1",
                                "format": "XML",
                                "url": "https://example.test/abn-part-1.xml",
                            },
                            {
                                "id": "abn-part-2",
                                "name": "ABN Bulk Extract Part 2",
                                "format": "XML",
                                "url": "https://example.test/abn-part-2.xml",
                            },
                        ],
                    },
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_open_bytes_with_retries(request, *, timeout=60, tries=4):
        if request.full_url.endswith("asic.csv"):
            return (
                b"Company Name,ACN,ABN\nExample Energy Pty Ltd,123456780,51824753556\n",
                200,
                {"Content-Type": "text/csv"},
            )
        if request.full_url.endswith("abn-part-1.xml"):
            return (
                b"""
                <ABRPayloadSearchResults>
                  <ABR>
                    <ABN status="Active">51824753556</ABN>
                    <MainEntity>
                      <NonIndividualName>
                        <NonIndividualNameText>Example Energy Pty Ltd</NonIndividualNameText>
                      </NonIndividualName>
                    </MainEntity>
                  </ABR>
                </ABRPayloadSearchResults>
                """,
                200,
                {"Content-Type": "text/xml"},
            )
        if request.full_url.endswith("abn-part-2.xml"):
            return (
                b"""
                <ABRPayloadSearchResults>
                  <ABR>
                    <ABN status="Active">51824753556</ABN>
                    <MainEntity>
                      <NonIndividualName>
                        <NonIndividualNameText>Second Example Pty Ltd</NonIndividualNameText>
                      </NonIndividualName>
                    </MainEntity>
                  </ABR>
                </ABRPayloadSearchResults>
                """,
                200,
                {"Content-Type": "text/xml"},
            )
        raise AssertionError(request.full_url)

    monkeypatch.setattr(
        official_identifier_module,
        "_open_bytes_with_retries",
        fake_open_bytes_with_retries,
    )

    summary_path = fetch_official_identifier_bulk_resources(
        source_ids=["asic_companies_dataset", "abn_lookup"],
        discovery_path=discovery_path,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["source_ids"] == ["abn_lookup", "asic_companies_dataset"]
    assert len(summary["downloaded_resources"]) == 3
    jsonl_paths = [Path(path) for path in summary["official_identifiers_jsonl_paths"]]
    assert len(jsonl_paths) == 2
    abn_jsonl = next(path for path in jsonl_paths if "abn_lookup_bulk" in path.name)
    abn_records = [
        json.loads(line) for line in abn_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["display_name"] for record in abn_records] == [
        "Example Energy Pty Ltd",
        "Second Example Pty Ltd",
    ]
    assert summary["source_summaries"]["abn_lookup"]["record_count"] == 2
    for download in summary["downloaded_resources"]:
        metadata = json.loads(Path(download["source_metadata_path"]).read_text(encoding="utf-8"))
        assert metadata["metadata_kind"] == "data_gov_official_identifier_resource"
        assert Path(metadata["body_path"]).exists()


def test_latest_official_identifier_paths_keep_all_incremental_abn_web_lookups(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "official_identifiers"
    source_dir.mkdir()

    def write_record(path: Path, source_id: str, source_record_type: str) -> None:
        path.write_text(
            json.dumps(
                {
                    "source_id": source_id,
                    "source_record_type": source_record_type,
                    "normalized_name": path.stem,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    abn_first = source_dir / "20260101T000000Z.jsonl"
    abn_second = source_dir / "20260102T000000Z.jsonl"
    lobbyist_old = source_dir / "20260103T000000Z.jsonl"
    lobbyist_new = source_dir / "20260104T000000Z.jsonl"
    write_record(abn_first, "abn_lookup", "abn_web_service_entity")
    write_record(abn_second, "abn_lookup", "abn_web_service_entity")
    write_record(lobbyist_old, "australian_lobbyists_register", "lobbyist_organisation")
    write_record(lobbyist_new, "australian_lobbyists_register", "lobbyist_organisation")

    selected = latest_official_identifier_jsonl_paths(processed_dir=tmp_path)

    assert set(selected) == {abn_first, abn_second, lobbyist_new}
    assert lobbyist_old not in selected


def test_extract_official_identifiers_from_file_writes_jsonl(tmp_path: Path) -> None:
    csv_path = tmp_path / "asic.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Company Name", "ACN"])
        writer.writeheader()
        writer.writerow({"Company Name": "Example Energy Pty Ltd", "ACN": "123456780"})

    processed_dir = tmp_path / "processed"
    raw_dir = tmp_path / "raw"
    output_path = extract_official_identifiers_from_file(
        "asic_companies_dataset",
        csv_path,
        processed_dir=processed_dir,
        raw_dir=raw_dir,
    )
    records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

    assert output_path.parent == processed_dir / "official_identifiers"
    assert records[0]["source_id"] == "asic_companies_dataset"
    assert records[0]["source_metadata_path"].startswith(str(raw_dir))
    metadata_path = Path(records[0]["source_metadata_path"])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert Path(metadata["body_path"]).parent == metadata_path.parent
    assert Path(metadata["body_path"]).exists()
    assert metadata["original_input_path"] == str(csv_path.resolve())


def test_lobbyist_person_records_preserve_public_api_payload(tmp_path: Path) -> None:
    profiles_path = tmp_path / "profiles.jsonl"
    public_lobbyist_record = {
        "additionalNotes": "Public note",
        "cessationDate": "2025-01-31T00:00:00Z",
        "dateDeregistered": None,
        "datePublished": "2025-02-01T00:00:00Z",
        "dateWitnessed": None,
        "displayName": "Alex Public",
        "id": None,
        "isFormerRepresentative": True,
        "modifiedOn": "2025-03-01T00:00:00Z",
        "position": "Director",
        "previousPosition": None,
        "previousPositionLevel": None,
        "previousPositionOther": "Former ministerial adviser",
    }
    profiles_path.write_text(
        json.dumps(
            {
                "summary": {
                    "abn": "51 824 753 556",
                    "displayName": "Example Lobbying Pty Ltd",
                    "id": "org-1",
                    "isDeregistered": False,
                    "modifiedOn": "2025-03-01T00:00:00Z",
                    "tradingName": "Example Lobbying",
                },
                "clients": [],
                "lobbyists": [public_lobbyist_record],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_metadata_path = tmp_path / "metadata.json"
    source_metadata_path.write_text("{}", encoding="utf-8")

    output_path = write_lobbyist_identifier_records(
        profiles_path,
        source_metadata_path,
        processed_dir=tmp_path / "processed",
    )
    records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    person_record = next(
        record for record in records if record["source_record_type"] == "lobbyist_person"
    )

    assert person_record["raw_record"] == public_lobbyist_record
    assert person_record["metadata"]["is_former_representative"] is True
