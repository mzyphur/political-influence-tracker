# Build Log

## 2026-04-27

Initial federal backend foundation created.

Completed:

- Created project scaffold under `/Users/mikezyphur/Library/CloudStorage/GoogleDrive-mzyphur@instats.org/My Drive/AU Politics`.
- Added research plan, data-source inventory, research standards, entity-resolution notes, and frontend direction.
- Added Python backend package and source registry.
- Added raw source fetcher with metadata, checksums, content type, and source IDs.
- Added link discovery for AEC download pages, APH contact CSVs, APH House interests PDFs, and AEC GIS ZIPs.
- Downloaded APH current member/senator CSVs.
- Built current APH roster JSON: 149 House members and 76 Senators.
- Downloaded House Register of Members' Interests index and 152 PDFs/reference PDFs.
- Extracted text from 152 House interests PDFs/reference PDFs with PDF text plus Tesseract OCR fallback: 2,170 pages, 11 OCR pages, zero extraction failures.
- Downloaded AEC annual disclosure ZIP.
- Summarized 13 AEC annual CSV table schemas.
- Normalized 192,201 AEC annual money-flow rows into JSONL.
- Split House interests PDFs into 2,852 numbered section records across 150 member documents; 2 reference documents were skipped.
- Added House interest structured-record extraction from numbered sections, including owner context, category mapping, conservative counterparty guessing, duplicate-key suppression, and filters for explanatory notes/form prompts.
- Added PostgreSQL/PostGIS schema draft.
- Added local Docker Compose database scaffold.
- Added reproducible `run-federal-foundation-pipeline` command.
- Added pipeline run manifests under `data/audit/pipeline_runs`.
- Added weekly pipeline shell script and CI smoke workflow.
- Added idempotent PostgreSQL loader for the latest processed roster and AEC annual money-flow artifacts.
- Moved discovered-source ID generation into shared ingestion code so CLI and scheduled pipelines use the same stable source IDs.
- Added reproducible Senate interests API ingestion through the official APH page's `env.js` API configuration.
- Added Senate interest record flattening for gifts, travel/hospitality, liabilities, assets, income, directorships, and alterations.
- Extended the PostgreSQL loader to insert Senate and House interest records into `gift_interest` after matching MPs/Senators to the reproducible APH roster.
- Added a provenance-marked House-register fallback person path for cases where the APH contact CSV omits a valid House member present in the official House interests register.
- Installed Docker Desktop 4.71.0 as `/Applications/Docker.app` and linked Docker CLI tools for the current shell environment.
- Started the local PostGIS stack with Docker Compose and loaded the current reproducible artifacts into PostgreSQL.

Verification:

- `pytest`: 29 passed.
- `ruff check .`: passed.
- Federal smoke pipeline: succeeded (`federal_foundation_20260427T111450Z.json`).
- Senate smoke API fetch: 5 of 76 available senator statements fetched; 104 flattened interest records produced.
- Full Senate API refresh: 76 of 76 available senator statements fetched; 1,752 flattened interest records produced.
- Full House PDF text extraction: 152 PDFs/reference PDFs, 2,170 pages, 11 OCR pages, 0 failed documents.
- Full House section extraction: 2,852 numbered sections from 150 member documents; 277 gift sections.
- Full House structured extraction: 5,853 unique House interest records after excluding explanatory notes, form prompts, and duplicate keys.
- Docker/PostGIS load succeeded: 226 people, 226 office terms, 192,201 AEC money-flow rows, 5,853 House interest records, 1,752 Senate interest records, 7,605 total `gift_interest` rows.

Notable data observations:

- APH current contact CSV returned 149 House members and 76 Senators, while the official House interests register included Sussan Ley for Farrer. The loader now creates `Sussan Ley (Farrer)` from the House register with metadata source `derived_from_house_interest_register` so records are not dropped; this should be monitored in future APH CSV refreshes.
- AEC annual disclosure ZIP contains 13 CSV tables and is small enough for routine weekly ingestion.
- The first money-flow normalizer covers Detailed Receipts, Donations Made, Donor Donations Received, and Third Party Donations Received. It does not yet normalize debts, discretionary benefits, capital contributions, or return summary tables.
- House interests text extraction needed OCR fallback for scanned/low-text pages, including `Gosling_48P.pdf` and `Katter_48P.pdf`; OCR artifacts are handled in the metadata extractor and record filters.
- The Senate register currently exposes structured JSON through a public API used by the official APH React app; this is preferable to PDF scraping for current Senate interests, but the API should be monitored for schema changes.
