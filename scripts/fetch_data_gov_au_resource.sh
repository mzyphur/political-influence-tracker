#!/usr/bin/env bash
#
# Reproducible CC-BY-licensed resource fetcher for data.gov.au.
#
# Many of the project's federal source-of-truth datasets (AusTender
# historical contracts, AEC bulk downloads, ASIC company dataset, ACNC
# charity register, Australian Bureau of Statistics ASGS shapefiles,
# etc.) are mirrored on data.gov.au under CC-BY 3.0/4.0 Australia.
# This script provides a polite, reproducible, hash-archived fetch
# path for any such resource.
#
# Usage:
#
#   bash scripts/fetch_data_gov_au_resource.sh \
#       <ckan_dataset_id_or_slug> \
#       <ckan_resource_id> \
#       [<archive_subdir_name>]
#
# Example:
#
#   # AusTender 2017-18 historical contracts (CC-BY 3.0).
#   bash scripts/fetch_data_gov_au_resource.sh \
#       5c7fa69b-b0e9-4553-b8df-2a022dd2e982 \
#       bc2097b7-8116-4e9d-9953-98813635892a \
#       austender_contract_notices_historical
#
# What this does:
#
#   1. Calls the CKAN package_show API to discover the resource URL
#      and its publisher-recorded licence string.
#   2. Refuses to proceed if the licence is not CC-BY-shaped (the
#      project's standing rule for public-redistribution sources).
#      Override only by exporting `ALLOW_NON_CC_BY=1`.
#   3. Downloads the resource over HTTPS with a polite User-Agent
#      that names the project and links to the public mirror.
#   4. Computes SHA-256 of the bytes and writes a metadata.json
#      alongside the resource.
#   5. Output goes under `data/raw/<archive_subdir_name>/<UTC-stamp>/`
#      so re-fetches are append-only and the project's archive layer
#      stays auditable.
#
# Why a shell script and not a Python adapter:
#
#   The project's full per-source ingest adapters (act_elections.py,
#   qld_ecq_eds.py, etc.) are substantial Python modules that include
#   parsers + loaders. This one-off script is for the discovery /
#   first-fetch step that proves a CC-BY URL is reachable and the
#   licence is what data.gov.au says it is. A full adapter for any
#   given source can land later in its own batch and consume the
#   archived resource as input.
#
# Operational etiquette:
#
#   * Keep `Crawl-delay`-equivalent intervals between calls. data.gov.au
#     is generous with rate limits but the public-interest project
#     shouldn't be the source of someone else's outage.
#   * Always pass the dataset id and resource id (they're stable). Do
#     not depend on the data.gov.au search ordering.
#   * If the resource size is large (> 100 MB), warn before the
#     download starts.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <ckan_dataset_id_or_slug> <ckan_resource_id> [<archive_subdir>]" >&2
  exit 2
fi

DATASET_ID="$1"
RESOURCE_ID="$2"
ARCHIVE_SUBDIR="${3:-data_gov_au_${DATASET_ID}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RAW_DIR="${PROJECT_ROOT}/data/raw/${ARCHIVE_SUBDIR}"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
TARGET_DIR="${RAW_DIR}/${TIMESTAMP}"
USER_AGENT="PoliticalInfluenceTracker/0.1 (+https://github.com/mzyphur/political-influence-tracker)"

mkdir -p "${TARGET_DIR}"

echo "==> Discovering dataset metadata for ${DATASET_ID}"
META_PATH="${TARGET_DIR}/dataset_metadata.json"
curl -sSL -A "${USER_AGENT}" \
  "https://data.gov.au/data/api/3/action/package_show?id=${DATASET_ID}" \
  -o "${META_PATH}"

LICENCE_ID="$(python3 -c "
import json
with open('${META_PATH}') as f:
    d = json.load(f)
print((d.get('result', {}).get('license_id') or '').lower())
")"
LICENCE_TITLE="$(python3 -c "
import json
with open('${META_PATH}') as f:
    d = json.load(f)
print(d.get('result', {}).get('license_title') or '')
")"

echo "    licence: ${LICENCE_ID} (${LICENCE_TITLE})"

case "${LICENCE_ID}" in
  cc-by | cc-by-* | cc-by-au | cc-by-au-* | cc0 | cc0-* | other-pd | other-public)
    echo "    licence accepted (CC-BY family or public domain)"
    ;;
  *)
    if [[ "${ALLOW_NON_CC_BY:-0}" != "1" ]]; then
      echo "    licence ${LICENCE_ID} is not CC-BY family / CC0 / public domain." >&2
      echo "    Refusing to fetch by default. Set ALLOW_NON_CC_BY=1 to override," >&2
      echo "    AND record the licence verbatim in docs/source_licences.md before" >&2
      echo "    redistributing the data publicly." >&2
      exit 3
    fi
    echo "    WARNING: licence ${LICENCE_ID} is non-CC-BY; proceeding under" \
      "ALLOW_NON_CC_BY=1 — record the licence verbatim before public release." >&2
    ;;
esac

RESOURCE_URL="$(python3 -c "
import json
with open('${META_PATH}') as f:
    d = json.load(f)
for r in d.get('result', {}).get('resources', []):
    if r.get('id') == '${RESOURCE_ID}':
        print(r.get('url') or '')
        break
")"
RESOURCE_NAME="$(python3 -c "
import json
with open('${META_PATH}') as f:
    d = json.load(f)
for r in d.get('result', {}).get('resources', []):
    if r.get('id') == '${RESOURCE_ID}':
        print(r.get('name') or '')
        break
")"
RESOURCE_FORMAT="$(python3 -c "
import json
with open('${META_PATH}') as f:
    d = json.load(f)
for r in d.get('result', {}).get('resources', []):
    if r.get('id') == '${RESOURCE_ID}':
        print((r.get('format') or '').lower())
        break
")"

if [[ -z "${RESOURCE_URL}" ]]; then
  echo "    resource ${RESOURCE_ID} not found on dataset ${DATASET_ID}" >&2
  exit 4
fi

# Pick a sensible filename extension based on the format. data.gov.au
# is inconsistent about extensions on storage URLs, so we infer from
# the format field.
case "${RESOURCE_FORMAT}" in
  csv) EXT="csv" ;;
  xlsx | "excel (.xlsx)") EXT="xlsx" ;;
  xls) EXT="xls" ;;
  json) EXT="json" ;;
  zip) EXT="zip" ;;
  pdf) EXT="pdf" ;;
  *) EXT="bin" ;;
esac

RESOURCE_PATH="${TARGET_DIR}/resource.${EXT}"

echo "==> Fetching ${RESOURCE_URL}"
echo "    name: ${RESOURCE_NAME}"
echo "    -> ${RESOURCE_PATH}"
curl -sSL -A "${USER_AGENT}" "${RESOURCE_URL}" -o "${RESOURCE_PATH}" \
  -w "    HTTP %{http_code} size=%{size_download} time=%{time_total}s\n"

SHA256="$(shasum -a 256 "${RESOURCE_PATH}" | awk '{print $1}')"
SIZE_BYTES="$(wc -c < "${RESOURCE_PATH}" | tr -d ' ')"

cat > "${TARGET_DIR}/metadata.json" <<META_EOF
{
  "source": "data.gov.au CKAN package_show",
  "fetched_at": "${TIMESTAMP}",
  "dataset_id": "${DATASET_ID}",
  "resource_id": "${RESOURCE_ID}",
  "resource_name": $(python3 -c "import json; print(json.dumps('${RESOURCE_NAME}'))"),
  "resource_format": "${RESOURCE_FORMAT}",
  "resource_url": $(python3 -c "import json; print(json.dumps('${RESOURCE_URL}'))"),
  "resource_path": "resource.${EXT}",
  "size_bytes": ${SIZE_BYTES},
  "sha256": "${SHA256}",
  "licence_id": "${LICENCE_ID}",
  "licence_title": $(python3 -c "import json; print(json.dumps('${LICENCE_TITLE}'))"),
  "user_agent": "${USER_AGENT}",
  "project_url": "https://github.com/mzyphur/political-influence-tracker"
}
META_EOF

echo "==> Done."
echo "    Archive: ${TARGET_DIR}"
echo "    SHA-256: ${SHA256}"
