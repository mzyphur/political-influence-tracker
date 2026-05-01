#!/usr/bin/env bash
# fetch_federal_lobbyist_register.sh — download the federal
# Lobbyist Register from lobbyists.ag.gov.au and archive the raw
# HTML / JSON to data/raw/federal_lobbyist_register/<UTC-stamp>/.
#
# Stage 4b of the influence-correlation pipeline. Combined with
# the schema at backend/schema/050_lobbyist_register_observations.sql
# and the loader (TBD next batch), this populates the
# lobbyist_organisation_record + lobbyist_principal +
# lobbyist_client_engagement tables.
#
# Source: https://lobbyists.ag.gov.au/register
#
# Usage:  ./scripts/fetch_federal_lobbyist_register.sh
#
# Scaffold-only — the federal register is a JavaScript SPA so a
# naive curl won't capture the firm list. Next batch implements
# either a Playwright-based capture or a backend-API direct fetch.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
RAW_DIR="${PROJECT_ROOT}/data/raw/federal_lobbyist_register/${TIMESTAMP}"
mkdir -p "${RAW_DIR}"

REGISTER_URL="https://lobbyists.ag.gov.au/register"

cat > "${RAW_DIR}/SCAFFOLD_NOTE.md" <<EOF
# Federal Lobbyist Register Fetch — Scaffold

**Created:** ${TIMESTAMP}
**Source:** ${REGISTER_URL}

This directory is a scaffold from the
\`fetch_federal_lobbyist_register.sh\` script.

## Implementation plan

The federal Lobbyist Register at
https://lobbyists.ag.gov.au/register is a JavaScript-rendered SPA.
Three options for next-batch implementation:

1. **Playwright-based capture** — use playwright-python to
   navigate the SPA, click through each firm, capture rendered
   HTML + structured data per firm. Estimated: 1 day.

2. **Backend-API discovery** — the SPA calls internal JSON
   endpoints; inspecting network tab during a manual browse
   should reveal them. If stable, use directly. Estimated:
   half-day.

3. **Manual CSV download** — interim option if a CSV export
   exists.

## Schema destination

\`backend/schema/050_lobbyist_register_observations.sql\`:
- lobbyist_organisation_record (firm, jurisdiction)
- lobbyist_principal (firm, person)
- lobbyist_client_engagement (firm, client)

## Cross-source correlation

When loaded, \`v_lobbyist_client_influence_overlap\` joins the
lobbyist client engagements to influence_event donations to
surface "Lobbyist L represents Client X. Client X donated to
MPs Z" — the canonical three-way influence pattern.

## Cost

Zero — deterministic data ingestion of a public register.
EOF

echo "Scaffold note written: ${RAW_DIR}/SCAFFOLD_NOTE.md"
echo ""
echo "Next-batch work: implement Playwright or direct-API fetcher;"
echo "loader in backend/au_politics_money/db/lobbyist_loader.py;"
echo "wire to Makefile + reproduce-federal flow."
