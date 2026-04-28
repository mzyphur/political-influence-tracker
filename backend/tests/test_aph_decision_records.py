from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.ingest.aph_decision_records import (
    decision_record_document_source,
    fetch_aph_decision_record_documents,
    parse_aph_decision_record_index,
)
from au_politics_money.ingest.sources import get_source


def test_parse_house_votes_and_proceedings_index_extracts_official_record_links() -> None:
    source = get_source("aph_house_votes_and_proceedings")
    html = """
    <html>
      <body>
        <h2>48th Parliament</h2>
        <h3>2026</h3>
        <table>
          <tr>
            <th>February</th>
            <td>
              <a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22chamber/votes/test/0000%22">3</a>
              <a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22 chamber/votes/space-test/0000%22">4</a>
            </td>
          </tr>
        </table>
        <a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22chamber/hansardr/test/0000%22">Hansard</a>
        <a href="/-/media/example/consolidated-votes.pdf">PDF 3.1 MB</a>
      </body>
    </html>
    """

    records = parse_aph_decision_record_index(source=source, html=html)

    assert len(records) == 2
    assert records[0]["chamber"] == "house"
    assert records[0]["record_type"] == "votes_and_proceedings"
    assert records[0]["record_kind"] == "parlinfo_html"
    assert records[0]["parliament_label"] == "48th Parliament"
    assert records[0]["year"] == "2026"
    assert records[0]["month"] == "February"
    assert records[0]["day_label"] == "3"
    assert records[0]["record_date"] == "2026-02-03"
    assert records[0]["url"].startswith("https://parlinfo.aph.gov.au/")
    assert records[0]["evidence_status"] == "official_record_index"
    assert records[0]["metadata"]["date_source"] == "heading_month_and_link_text"
    assert "%20chamber/votes/space-test" in records[1]["url"]


def test_parse_senate_journal_index_extracts_pdf_links() -> None:
    source = get_source("aph_senate_journals")
    html = """
    <html>
      <body>
        <h2>48th Parliament</h2>
        <h3>2026</h3>
        <table>
          <tr>
            <td>March</td>
            <td>
              <a href="https://parlinfo.aph.gov.au/parlInfo/download/chamber/journals/test/toc_pdf/sen-jn.pdf;fileType=application%2Fpdf">24</a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    records = parse_aph_decision_record_index(source=source, html=html)

    assert len(records) == 1
    assert records[0]["chamber"] == "senate"
    assert records[0]["record_type"] == "journals_of_the_senate"
    assert records[0]["record_kind"] == "parlinfo_pdf"
    assert records[0]["parliament_label"] == "48th Parliament"
    assert records[0]["year"] == "2026"
    assert records[0]["month"] == "March"
    assert records[0]["day_label"] == "24"
    assert records[0]["record_date"] == "2026-03-24"


def test_parse_index_prefers_aria_label_date() -> None:
    source = get_source("aph_house_votes_and_proceedings")
    html = """
    <html>
      <body>
        <h2>48th Parliament</h2>
        <h3>2026</h3>
        <table>
          <tr>
            <td>Wrong Month</td>
            <td>
              <a aria-label="03-Feb-2026" href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22chamber/votes/test/0000%22">3</a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    records = parse_aph_decision_record_index(source=source, html=html)

    assert records[0]["record_date"] == "2026-02-03"
    assert records[0]["month"] == "February"
    assert records[0]["metadata"]["date_source"] == "aria-label"


def test_parse_senate_journal_index_merges_html_and_pdf_representations() -> None:
    source = get_source("aph_senate_journals")
    html = """
    <html>
      <body>
        <h2>Journals of the Senate</h2>
        <h3>2026</h3>
        <table>
          <tr>
            <td>March</td>
            <td>
              <a aria-label="24-Mar-2026" href="https://parlinfo.aph.gov.au/parlInfo/download/chamber/journals/test/toc_pdf/sen-jn.pdf;fileType=application%2Fpdf">24</a>
              <a aria-label="24-Mar-2026" href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22chamber/journals/test/0000%22">24</a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    records = parse_aph_decision_record_index(source=source, html=html)

    assert len(records) == 1
    assert records[0]["record_kind"] == "parlinfo_multi"
    assert records[0]["url"].startswith("https://parlinfo.aph.gov.au/parlInfo/search/display")
    assert len(records[0]["metadata"]["representations"]) == 2
    assert records[0]["parliament_label"] == ""


def test_parse_index_rejects_dated_record_link_with_invalid_date() -> None:
    source = get_source("aph_house_votes_and_proceedings")
    html = """
    <html>
      <body>
        <h2>48th Parliament</h2>
        <h3>2026</h3>
        <table>
          <tr>
            <td>February</td>
            <td>
              <a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22chamber/votes/test/0000%22">31</a>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    with pytest.raises(ValueError, match="missing parseable date"):
        parse_aph_decision_record_index(source=source, html=html)


def test_parse_decision_record_index_rejects_unsupported_source() -> None:
    with pytest.raises(ValueError, match="Unsupported APH decision-record source"):
        parse_aph_decision_record_index(
            source=get_source("aec_transparency_downloads"),
            html="<html></html>",
        )


def test_decision_record_document_source_is_stable() -> None:
    record = {
        "external_key": "aph_house_votes_and_proceedings:test",
        "source_id": "aph_house_votes_and_proceedings",
        "source_name": "House Votes and Proceedings",
        "chamber": "house",
        "record_date": "2026-02-03",
    }
    representation = {
        "record_kind": "parlinfo_html",
        "url": "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p",
    }

    first = decision_record_document_source(record, representation)
    second = decision_record_document_source(record, representation)

    assert first == second
    assert first.source_id.startswith("aph_house_votes_and_proceedings__decision_record__20260203__html__")
    assert first.source_type == "official_parliamentary_decision_record_document"
    assert first.url == representation["url"]


def test_fetch_aph_decision_record_documents_writes_linkage_in_summary(tmp_path) -> None:
    index_path = tmp_path / "aph_house_votes_and_proceedings" / "index.jsonl"
    index_path.parent.mkdir(parents=True)
    record = {
        "external_key": "aph_house_votes_and_proceedings:test",
        "source_id": "aph_house_votes_and_proceedings",
        "source_name": "House Votes and Proceedings",
        "chamber": "house",
        "record_type": "votes_and_proceedings",
        "record_kind": "parlinfo_html",
        "record_date": "2026-02-03",
        "title": "House Votes and Proceedings 2026-02-03",
        "url": "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p",
        "source_metadata_path": "/tmp/index-metadata.json",
        "metadata": {
            "representations": [
                {
                    "url": "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p",
                    "record_kind": "parlinfo_html",
                    "link_text": "3",
                    "host": "parlinfo.aph.gov.au",
                    "parent_text": "February 3",
                }
            ]
        },
    }
    index_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def fake_fetcher(source, raw_dir, timeout):
        body = b"<html>official record</html>"
        target_dir = raw_dir / source.source_id / "20260427T000000Z"
        target_dir.mkdir(parents=True)
        body_path = target_dir / "body.html"
        body_path.write_bytes(body)
        metadata_path = target_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "source": source.to_dict(),
                    "fetched_at": "20260427T000000Z",
                    "ok": True,
                    "http_status": 200,
                    "final_url": source.url,
                    "content_type": "text/html",
                    "content_length": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "body_path": str(body_path),
                    "headers": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return metadata_path

    summary_path = fetch_aph_decision_record_documents(
        jsonl_paths=[index_path],
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        fetcher=fake_fetcher,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["selected_count"] == 1
    assert summary["fetched_count"] == 1
    document = summary["documents"][0]
    assert document["official_decision_record"]["external_key"] == record["external_key"]
    assert document["official_decision_record_representation"]["record_kind"] == "parlinfo_html"
    assert document["validation"]["validation"] == "html_signature"
    metadata_path = document["metadata_path"]
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    assert "official_decision_record" not in metadata
    assert "official_decision_record_representation" not in metadata
