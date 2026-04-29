import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.ingest.tas_tec import (
    SOURCE_IDS,
    _source_link_url,
    fetch_tas_tec_declaration_documents,
    normalize_tas_tec_donations,
)


HEADERS = """
<tr>
  <th>Date of donation</th>
  <th>Dollar value of donation</th>
  <th>Name of recipient</th>
  <th>Type of recipient</th>
  <th>Name of donor</th>
  <th>ABN or ACN of donor</th>
  <th>Donor declaration lodged</th>
  <th>Recipient declaration lodged</th>
</tr>
"""


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _table_html(*, amount: str, donor: str, recipient: str) -> str:
    return f"""
    <table>
      <caption>As at: 10:03 AM Tuesday 28 April 2026</caption>
      <tbody>
        {HEADERS}
        <tr>
          <td data-hidden-sort="20260428">28/04/2026</td>
          <td>{amount}</td>
          <td>{recipient}</td>
          <td>Registered party</td>
          <td>{donor}</td>
          <td data-hidden-sort="00632816383">006 328 163 83</td>
          <td><a href="data/downloads/edf-donation-ha25-0001-d.pdf">Download</a></td>
          <td>Failed to lodge</td>
        </tr>
      </tbody>
    </table>
    """


def _write_metadata(tmp_path: Path, source_id: str, body: str) -> Path:
    body_path = tmp_path / f"{source_id}.html"
    body_path.write_text(body, encoding="utf-8")
    metadata_path = tmp_path / f"{source_id}.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": {
                    "source_id": source_id,
                    "url": (
                        "https://www.tec.tas.gov.au/disclosure-and-funding/"
                        "registers-and-reports/donations/data/table-fixture.html"
                    ),
                },
                "final_url": (
                    "https://www.tec.tas.gov.au/disclosure-and-funding/"
                    "registers-and-reports/donations/data/table-fixture.html"
                ),
                "body_path": str(body_path),
                "sha256": _sha256_path(body_path),
                "fetched_at": "20260428T000000Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def _write_declaration_metadata(tmp_path: Path, url: str) -> Path:
    body_path = tmp_path / "declaration.pdf"
    body_path.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
    metadata_path = tmp_path / "declaration.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": {
                    "source_id": "tas_tec_declaration_document_fixture",
                    "url": url,
                },
                "final_url": url,
                "body_path": str(body_path),
                "sha256": _sha256_path(body_path),
                "content_type": "application/pdf",
                "content_length": body_path.stat().st_size,
                "fetched_at": "20260428T010000Z",
                "ok": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def test_normalize_tas_tec_donations_extracts_donations_and_loans(tmp_path) -> None:
    metadata_paths = {
        "tas_tec_donations_monthly_table": _write_metadata(
            tmp_path,
            "tas_tec_donations_monthly_table",
            _table_html(
                amount="$1,200.00",
                donor="Example Donor Pty Ltd",
                recipient="Example Party Tasmania",
            ),
        ),
        "tas_tec_donations_seven_day_ha25_table": _write_metadata(
            tmp_path,
            "tas_tec_donations_seven_day_ha25_table",
            _table_html(
                amount="$500,000.00*",
                donor="Loan Provider Pty Ltd",
                recipient="Example Candidate",
            ),
        ),
        "tas_tec_donations_seven_day_lc26_table": _write_metadata(
            tmp_path,
            "tas_tec_donations_seven_day_lc26_table",
            _table_html(
                amount="$250.00",
                donor="Small Donor Pty Ltd",
                recipient="Example Legislative Council Candidate",
            ),
        ),
    }

    summary_path = normalize_tas_tec_donations(
        metadata_paths=metadata_paths,
        processed_dir=tmp_path / "processed",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert summary["source_dataset"] == "tas_tec_donations"
    assert summary["source_ids"] == list(SOURCE_IDS)
    assert summary["total_count"] == 3
    assert summary["reported_amount_total"] == "501450.00"
    assert summary["flow_kind_counts"] == {
        "tas_reportable_donation": 2,
        "tas_reportable_loan": 1,
    }
    assert rows[0]["date"] == "2026-04-28"
    assert rows[0]["flow_kind"] == "tas_reportable_donation"
    assert rows[0]["donor_abn_or_acn"]["digits"] == "00632816383"
    assert rows[0]["donor_declaration_status"] == "download_available"
    assert rows[0]["recipient_declaration_status"] == "failed_to_lodge"
    assert rows[0]["supporting_documents"][0]["role"] == "donor_declaration"
    assert rows[0]["supporting_documents"][0]["archived"] is False
    assert rows[1]["flow_kind"] == "tas_reportable_loan"
    assert rows[1]["transaction_kind"] == "loan"
    assert "not claims of wrongdoing" in rows[1]["claim_boundary"]


def test_normalize_tas_tec_donations_attaches_archived_declaration_metadata(tmp_path) -> None:
    metadata_paths = {
        source_id: _write_metadata(
            tmp_path,
            source_id,
            _table_html(
                amount="$1,200.00",
                donor="Example Donor Pty Ltd",
                recipient="Example Party Tasmania",
            ),
        )
        for source_id in SOURCE_IDS
    }
    declaration_url = (
        "https://www.tec.tas.gov.au/disclosure-and-funding/"
        "registers-and-reports/donations/data/downloads/edf-donation-ha25-0001-d.pdf"
    )
    declaration_metadata = _write_declaration_metadata(tmp_path, declaration_url)

    summary_path = normalize_tas_tec_donations(
        metadata_paths=metadata_paths,
        declaration_metadata_paths={declaration_url: declaration_metadata},
        processed_dir=tmp_path / "processed",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]

    donor_document = rows[0]["supporting_documents"][0]
    assert donor_document["role"] == "donor_declaration"
    assert donor_document["url"] == declaration_url
    assert donor_document["archived"] is True
    assert donor_document["archive_body_sha256"] == _sha256_path(tmp_path / "declaration.pdf")
    assert summary["supporting_document_url_count"] == 1
    assert summary["supporting_document_archived_count"] == 1
    assert summary["supporting_document_failed_count"] == 0
    assert declaration_url in summary["supporting_document_hashes"]


def test_fetch_tas_tec_declaration_documents_archives_unique_links(tmp_path, monkeypatch) -> None:
    metadata_paths = {
        source_id: _write_metadata(
            tmp_path,
            source_id,
            _table_html(
                amount="$1,200.00",
                donor="Example Donor Pty Ltd",
                recipient="Example Party Tasmania",
            ),
        )
        for source_id in SOURCE_IDS
    }
    fetched: list[str] = []

    def fake_fetch_source(source, raw_dir):
        fetched.append(source.url)
        path = tmp_path / f"{source.source_id}.metadata.json"
        path.write_text(
            json.dumps(
                {
                    "source": source.to_dict(),
                    "body_path": str(tmp_path / f"{source.source_id}.pdf"),
                    "sha256": "fixture",
                    "ok": True,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr("au_politics_money.ingest.tas_tec.fetch_source", fake_fetch_source)

    archived = fetch_tas_tec_declaration_documents(
        metadata_paths=metadata_paths,
        raw_dir=tmp_path / "raw",
    )

    assert len(archived) == 1
    assert fetched == list(archived)


def test_fetch_tas_tec_declaration_documents_keeps_failed_fetch_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    metadata_paths = {
        source_id: _write_metadata(
            tmp_path,
            source_id,
            _table_html(
                amount="$1,200.00",
                donor="Example Donor Pty Ltd",
                recipient="Example Party Tasmania",
            ),
        )
        for source_id in SOURCE_IDS
    }

    def fake_fetch_source(source, raw_dir):
        target_dir = raw_dir / source.source_id / "20260428T020000Z"
        target_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = target_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "source": source.to_dict(),
                    "body_path": str(target_dir / "body.html"),
                    "sha256": "error-body",
                    "ok": False,
                    "http_status": 404,
                    "fetched_at": "20260428T020000Z",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raise RuntimeError("404")

    monkeypatch.setattr("au_politics_money.ingest.tas_tec.fetch_source", fake_fetch_source)

    archived = fetch_tas_tec_declaration_documents(
        metadata_paths=metadata_paths,
        raw_dir=tmp_path / "raw",
    )

    assert len(archived) == 1
    failed_metadata = json.loads(next(iter(archived.values())).read_text(encoding="utf-8"))
    assert failed_metadata["ok"] is False
    assert failed_metadata["http_status"] == 404


def test_tas_tec_relative_links_do_not_duplicate_data_directory() -> None:
    assert _source_link_url(
        "https://www.tec.tas.gov.au/disclosure-and-funding/registers-and-reports/donations/data/table.html",
        "data/downloads/edf-donation-ha25-0001-d.pdf",
    ) == (
        "https://www.tec.tas.gov.au/disclosure-and-funding/"
        "registers-and-reports/donations/data/downloads/edf-donation-ha25-0001-d.pdf"
    )


def test_tas_tec_normalizer_rejects_unexpected_headers(tmp_path) -> None:
    metadata_paths = {
        source_id: _write_metadata(
            tmp_path,
            source_id,
            """
            <table>
              <tbody>
                <tr><th>Unexpected</th></tr>
                <tr><td>value</td></tr>
              </tbody>
            </table>
            """,
        )
        for source_id in SOURCE_IDS
    }

    with pytest.raises(ValueError, match="Unexpected TAS TEC donation headers"):
        normalize_tas_tec_donations(
            metadata_paths=metadata_paths,
            processed_dir=tmp_path / "processed",
        )
