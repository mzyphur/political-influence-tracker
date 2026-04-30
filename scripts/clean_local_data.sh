#!/usr/bin/env bash
#
# Refusable helper that wipes data/raw, data/processed, and data/audit so
# the next reproduce-federal run starts from a clean slate. The destruction
# is gated behind an explicit y/N confirmation prompt because deleting
# data/audit also throws away pipeline-run manifests and validation
# evidence.
#
# This script never touches the local Postgres database or the project
# code — only the on-disk artifacts under data/. To rebuild the database
# from scratch use `make reproduce-federal` after this completes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cat <<EOF
This will delete:
  ${PROJECT_ROOT}/data/raw
  ${PROJECT_ROOT}/data/processed
  ${PROJECT_ROOT}/data/audit

Pipeline-run manifests and validation evidence in data/audit will be lost.
The Postgres database itself is NOT touched by this script.

Type 'yes' to proceed.
EOF

read -r REPLY
if [[ "${REPLY}" != "yes" ]]; then
  echo "Aborted."
  exit 1
fi

rm -rf \
  "${PROJECT_ROOT}/data/raw" \
  "${PROJECT_ROOT}/data/processed" \
  "${PROJECT_ROOT}/data/audit"

echo "Removed."
echo "Run \`make reproduce-federal\` to regenerate everything from public sources."
