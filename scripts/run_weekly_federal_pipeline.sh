#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
LOG_DIR="${PROJECT_ROOT}/data/audit/logs"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"

mkdir -p "${LOG_DIR}"

cd "${BACKEND_DIR}"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -e '.[dev]'
fi

.venv/bin/python -m au_politics_money.cli run-federal-foundation-pipeline \
  > "${LOG_DIR}/weekly_federal_pipeline_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_federal_pipeline_${TIMESTAMP}.stderr.log"

.venv/bin/python -m pytest \
  > "${LOG_DIR}/weekly_federal_pipeline_tests_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_federal_pipeline_tests_${TIMESTAMP}.stderr.log"

