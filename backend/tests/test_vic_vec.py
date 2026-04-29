import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from au_politics_money.ingest.vic_vec import normalize_vic_vec_funding_registers


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def make_docx(path: Path, *, paragraphs: list[str], rows: list[list[str]]) -> None:
    def paragraph_xml(text: str) -> str:
        return f"<w:p><w:r><w:t>{xml_escape(text)}</w:t></w:r></w:p>"

    def cell_xml(text: str) -> str:
        return f"<w:tc><w:p><w:r><w:t>{xml_escape(text)}</w:t></w:r></w:p></w:tc>"

    table_xml = "<w:tbl>" + "".join(
        "<w:tr>" + "".join(cell_xml(cell) for cell in row) + "</w:tr>"
        for row in rows
    ) + "</w:tbl>"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraph_xml(paragraph) for paragraph in paragraphs)
        + table_xml
        + "</w:body></w:document>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


def test_normalize_vic_vec_funding_registers_extracts_public_payment(tmp_path: Path) -> None:
    docx_path = tmp_path / "public-funding.docx"
    make_docx(
        docx_path,
        paragraphs=[
            "Public funding entitlements and payments for the Werribee District by-election 2025",
            "Election day was 8 February 2025",
            "Last updated: 9 September 2025",
        ],
        rows=[
            [
                "Recipient type",
                "Recipient name",
                "Maximum entitlement",
                "Audited statement of expenditure",
                "Actual entitlement",
                "Amount paid",
                "Comment",
            ],
            ["IC", "Paul Hopper", "$44,655.52", "$44,655.52", "$44,655.52", "$44,655.52", ""],
            ["", "Total", "$44,655.52", "$44,655.52", "$44,655.52", "$44,655.52", ""],
        ],
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps({"body_path": str(docx_path), "sha256": sha256_path(docx_path)}) + "\n",
        encoding="utf-8",
    )
    document_summary_path = tmp_path / "documents.summary.json"
    document_summary_path.write_text(
        json.dumps(
            {
                "source_dataset": "vic_vec_funding_register",
                "documents": [
                    {
                        "title": "VEC funding register post-State election 2022 public funding - Werribee District by-election",
                        "url": "https://www.vec.vic.gov.au/-/media/fixture.docx",
                        "source_id": "vic_vec_funding_register__fixture",
                        "metadata_path": str(metadata_path),
                        "metadata_sha256": sha256_path(metadata_path),
                        "body_path": str(docx_path),
                        "body_sha256": sha256_path(docx_path),
                        "source_sha256": sha256_path(docx_path),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary_path = normalize_vic_vec_funding_registers(
        document_summary_path=document_summary_path,
        processed_dir=tmp_path,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["source_dataset"] == "vic_vec_funding_register"
    assert summary["total_count"] == 1
    assert summary["flow_kind_counts"] == {"vic_public_funding_payment": 1}

    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["source_raw_name"] == "Victorian Electoral Commission"
    assert records[0]["recipient_raw_name"] == "Paul Hopper"
    assert records[0]["amount_aud"] == "44655.52"
    assert records[0]["date"] == "2025-02-08"
    assert records[0]["doc_last_updated"] == "2025-09-09"
    assert records[0]["financial_year"] == "Werribee District by-election 2025"
    assert "Election day" not in records[0]["financial_year"]
    assert records[0]["source_row_number"].endswith(":t1:r2:amount_paid")
    assert "not private donations" in records[0]["caveat"]
