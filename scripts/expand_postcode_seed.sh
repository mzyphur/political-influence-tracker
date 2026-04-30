#!/usr/bin/env bash
#
# Reproducible wrapper for expanding `data/seeds/aec_postcode_search_seed.txt`
# into the full federal-postcode crosswalk.
#
# Usage:
#   bash scripts/expand_postcode_seed.sh [<custom-seed-file>] [--max-postcodes N]
#
# What this does:
#   1. Reads the seed file (default `data/seeds/aec_postcode_search_seed.txt`).
#   2. Fetches each postcode from the live AEC Electorate Finder endpoint
#      via the existing `fetch-aec-electorate-finder-postcodes` CLI, with
#      `--refetch` so cached snapshots are re-archived.
#   3. Normalises every fetched response into JSONL.
#   4. Loads the JSONL into the local Postgres `postcode_electorate_crosswalk`
#      and `postcode_electorate_crosswalk_unresolved` tables.
#   5. Reports the resulting row counts.
#
# Operational etiquette (read before running with a large seed file):
#   * The AEC's electorate-finder endpoint is a public website. Do NOT run
#     this script with thousands of postcodes back-to-back. The federal
#     pipeline already builds in per-source delays via the shared
#     fetch helpers; respect those.
#   * For the first production refresh, the recommended approach is to
#     run this against the bootstrap 8-postcode seed (see
#     `data/seeds/aec_postcode_search_seed.txt`), confirm the chain is
#     healthy, then iterate up to a curated ~200-postcode "regional
#     coverage" seed, then a full ~3000-postcode national seed.
#   * Use `--max-postcodes N` to cap the run; the script reports the
#     postcodes it actually fetched so the next run can resume.
#
# Where to source a comprehensive postcode list:
#   * data.gov.au — community-curated Australia Post locality / postcode
#     CSVs.
#   * ABS POA (Postal Areas) shapefile — official, free.
#   * Australia Post's free "Postcode Locality" CSV (subject to Australia
#     Post's licence).
#   The actual list is a deliberate maintainer choice; this script just
#   feeds whichever list is selected. Document the source choice in
#   `docs/data_sources.md` before running with a non-bootstrap list.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
DEFAULT_SEED="${PROJECT_ROOT}/data/seeds/aec_postcode_search_seed.txt"

SEED_FILE="${DEFAULT_SEED}"
MAX_POSTCODES=""
for arg in "$@"; do
  case "$arg" in
    --max-postcodes=*)
      MAX_POSTCODES="${arg#--max-postcodes=}"
      ;;
    --max-postcodes)
      shift || true
      ;;
    --*)
      echo "Unknown flag: $arg" >&2
      exit 2
      ;;
    *)
      SEED_FILE="$arg"
      ;;
  esac
done

if [[ ! -f "${SEED_FILE}" ]]; then
  echo "Seed file not found: ${SEED_FILE}" >&2
  exit 1
fi

EFFECTIVE_SEED="${SEED_FILE}"
if [[ -n "${MAX_POSTCODES}" ]]; then
  TMP_SEED="$(mktemp -t expand_postcode_seed.XXXXXX)"
  grep -E '^\s*[0-9]{4}' "${SEED_FILE}" | head -n "${MAX_POSTCODES}" > "${TMP_SEED}"
  EFFECTIVE_SEED="${TMP_SEED}"
fi

cd "${BACKEND_DIR}"

echo "==> Fetching ${EFFECTIVE_SEED} from the live AEC Electorate Finder"
.venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money fetch-aec-electorate-finder-postcodes \
  --postcodes-file "${EFFECTIVE_SEED}" --refetch

echo "==> Normalising the fetched postcode responses to JSONL"
.venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money normalize-aec-electorate-finder-postcodes \
  --postcodes-file "${EFFECTIVE_SEED}"

echo "==> Loading the latest postcode crosswalk JSONL into Postgres"
.venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money load-postcode-electorate-crosswalk

if [[ -n "${MAX_POSTCODES}" ]]; then
  echo "(Used a capped seed of ${MAX_POSTCODES} postcodes; remove --max-postcodes for a full run.)"
fi
