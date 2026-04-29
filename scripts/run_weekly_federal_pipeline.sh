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
  .venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
fi

PIPELINE_ARGS=(run-federal-foundation-pipeline --refresh-existing-sources)
LOAD_ARGS=(load-postgres --skip-qld-ecq --skip-nsw-aggregates)
if .venv/bin/dotenv -f .env run -- \
  bash -c 'test -n "${THEY_VOTE_FOR_YOU_API_KEY:-${TVFY_API_KEY:-}}"'; then
  PIPELINE_ARGS+=(--include-votes)
  LOAD_ARGS+=(--include-vote-divisions)
else
  printf '%s\n' \
    "Skipping optional They Vote For You ingestion: no THEY_VOTE_FOR_YOU_API_KEY/TVFY_API_KEY set." \
    > "${LOG_DIR}/weekly_federal_votes_${TIMESTAMP}.skipped.log"
fi

.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli "${PIPELINE_ARGS[@]}" \
  > "${LOG_DIR}/weekly_federal_pipeline_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_federal_pipeline_${TIMESTAMP}.stderr.log"

.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli migrate-postgres \
  > "${LOG_DIR}/weekly_federal_migrate_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_federal_migrate_${TIMESTAMP}.stderr.log"

.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli "${LOAD_ARGS[@]}" \
  > "${LOG_DIR}/weekly_federal_load_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_federal_load_${TIMESTAMP}.stderr.log"

.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli qa-serving-database \
    --min-current-influence-events 100000 \
    --min-person-linked-influence-events 5000 \
    --min-current-money-flows 100000 \
    --min-current-gift-interests 4000 \
    --min-current-house-office-terms 140 \
    --min-current-senate-office-terms 70 \
  > "${LOG_DIR}/weekly_federal_qa_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_federal_qa_${TIMESTAMP}.stderr.log"

.venv/bin/python -m pytest \
  > "${LOG_DIR}/weekly_federal_pipeline_tests_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_federal_pipeline_tests_${TIMESTAMP}.stderr.log"
