from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import pytesseract

from au_politics_money.config import PROCESSED_DIR, RAW_DIR


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def latest_metadata_by_source_prefix(prefix: str, raw_dir: Path = RAW_DIR) -> list[Path]:
    latest: dict[str, Path] = {}
    for metadata_path in raw_dir.glob(f"{prefix}*/**/metadata.json"):
        source_dir = metadata_path.parent.parent.name
        previous = latest.get(source_dir)
        if previous is None or metadata_path.parent.name > previous.parent.name:
            latest[source_dir] = metadata_path
    return [latest[key] for key in sorted(latest)]


def _ocr_page(page: pdfplumber.page.Page, resolution: int = 150) -> str:
    if shutil.which("tesseract") is None:
        raise RuntimeError("Tesseract OCR is required for image-only PDF text extraction.")
    image = page.to_image(resolution=resolution).original
    return pytesseract.image_to_string(image)


def _extract_pdf_record(metadata_path: Path, ocr_min_chars: int = 20) -> dict[str, object]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    body_path = Path(metadata["body_path"])
    record: dict[str, object] = {
        "source_metadata_path": str(metadata_path),
        "source_id": metadata["source"]["source_id"],
        "source_name": metadata["source"]["name"],
        "url": metadata["source"]["url"],
        "body_path": str(body_path),
        "sha256": metadata["sha256"],
        "ok": True,
        "error": "",
        "page_count": 0,
        "ocr_page_count": 0,
        "pages": [],
    }

    try:
        with pdfplumber.open(body_path) as pdf:
            pages = []
            ocr_page_count = 0
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                extraction_method = "pdf_text"
                if len(text.strip()) < ocr_min_chars:
                    ocr_text = _ocr_page(page)
                    if len(ocr_text.strip()) > len(text.strip()):
                        text = ocr_text
                        extraction_method = "ocr_tesseract"
                        ocr_page_count += 1
                pages.append(
                    {
                        "page_number": index,
                        "text": text,
                        "extraction_method": extraction_method,
                    }
                )
            record["page_count"] = len(pages)
            record["ocr_page_count"] = ocr_page_count
            record["pages"] = pages
    except Exception as exc:  # noqa: BLE001 - extraction should record failures and continue.
        record["ok"] = False
        record["error"] = repr(exc)

    return record


def extract_pdf_text_batch(
    prefix: str = "aph_members_interests_48__",
    limit: int | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_paths = latest_metadata_by_source_prefix(prefix, raw_dir=raw_dir)
    if limit is not None:
        metadata_paths = metadata_paths[:limit]

    timestamp = _timestamp()
    target_dir = processed_dir / "pdf_text" / prefix.rstrip("_")
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    ok_count = 0
    failed_count = 0
    page_count = 0
    ocr_page_count = 0
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for metadata_path in metadata_paths:
            record = _extract_pdf_record(metadata_path)
            if record["ok"]:
                ok_count += 1
            else:
                failed_count += 1
            page_count += int(record["page_count"])
            ocr_page_count += int(record["ocr_page_count"])
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "prefix": prefix,
        "document_count": len(metadata_paths),
        "ok_count": ok_count,
        "failed_count": failed_count,
        "page_count": page_count,
        "ocr_page_count": ocr_page_count,
        "jsonl_path": str(jsonl_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
