# Security Notes

Last updated: 2026-04-27

This project is being built privately until a deliberate public release.

Current local safeguards:

- `.env` and `.env.*` are ignored and must not be committed or published.
- Generated source material and derived data are ignored: `data/raw/`, `data/processed/`, and `data/audit/`.
- The local PostgreSQL password in `backend/.env.example` is for local development only and must be replaced before any hosted deployment.
- Docker volumes are local development state. Do not expose the database port outside trusted local or server firewall boundaries.
- Raw official documents are public records, but we still keep the local corpus private until the workflow, caveats, and attribution are ready for release.

Before public release:

- Rotate any real credentials used during development.
- Review all `.env`, shell history, notebooks, and generated reports for accidental secrets.
- Publish reproducible code and documentation separately from large generated data unless the release plan explicitly includes the data corpus.
- Attach data-source citations, parser versions, extraction confidence, and caveats to public analytical outputs.
