# Security Notes

Last updated: 2026-04-28

This project is being built privately until a deliberate public release.

Current local safeguards:

- `.env` and `.env.*` are ignored and must not be committed or published.
- The working `backend/.env` is intentionally kept in the Drive-backed project
  folder for backup. Treat Drive access, sharing, and third-party OAuth grants as
  part of the project security boundary.
- Generated source material and derived data are ignored: `data/raw/`, `data/processed/`, and `data/audit/`.
- The local PostgreSQL password in `backend/.env.example` is for local development only and must be replaced before any hosted deployment.
- Docker volumes are local development state. Do not expose the database port outside trusted local or server firewall boundaries.
- Local Docker Compose now binds PostgreSQL to `127.0.0.1:${POSTGRES_PORT:-54329}` only.
- Public-source records are preserved as evidence. We keep the local corpus unpublished during development so the release can include methodology, caveats, checksums, source attribution, and secret checks rather than because public records are being suppressed.
- Lobbyist-person observations from the public register preserve the public API record in processed JSONL.
- They Vote For You API keys must live only in local/server environment
  variables. The fetcher stores public request URLs and request parameters
  without the `key` value, while preserving public response bodies.
- MapTiler browser keys are visible to end users by design. Use the default key
  only for local testing; production should use a separate protected key with
  allowed HTTP origins configured in MapTiler.
- ABN Lookup GUIDs and any future OpenCorporates/OpenSanctions/ABS keys should
  live only in local/server environment variables and must not be written to raw
  fetch metadata, generated docs, or committed examples.
- The ABN Lookup web-service fetcher posts the GUID rather than placing it in a
  URL, writes only redacted request parameters, and redacts the GUID from raw XML
  before archiving because some services can echo request content.
- ABN Lookup Web Services terms require reasonable deletion action if the ABR
  notifies us that specific information has been withdrawn. Before any public
  corpus release, maintain a takedown/withdrawal procedure that can identify and
  delete affected raw XML, processed JSONL, review exports, and database rows by
  ABN/ACN/source metadata.

Before public release:

- Rotate any real credentials used during development.
- Review all `.env`, shell history, notebooks, and generated reports for accidental secrets.
- Publish reproducible code and documentation separately from large generated data unless the release plan explicitly includes the data corpus.
- Attach data-source citations, parser versions, extraction confidence, and caveats to public analytical outputs.
- Rotate development API keys before public deployment or wider repository/data
  sharing, even if the keys were never committed to git.
