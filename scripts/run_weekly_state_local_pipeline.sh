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

if [[ -n "${AUPOL_STATE_LOCAL_JURISDICTIONS:-}" ]]; then
  read -r -a JURISDICTIONS <<< "${AUPOL_STATE_LOCAL_JURISDICTIONS}"
else
  JURISDICTIONS=(qld nsw act nt sa tas vic wa)
fi

if [[ "${#JURISDICTIONS[@]}" -eq 0 ]]; then
  printf '%s\n' "No state/local jurisdictions selected." >&2
  exit 1
fi

.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli migrate-postgres \
  > "${LOG_DIR}/weekly_state_local_migrate_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_state_local_migrate_${TIMESTAMP}.stderr.log"

last_index=$((${#JURISDICTIONS[@]} - 1))
for index in "${!JURISDICTIONS[@]}"; do
  jurisdiction="${JURISDICTIONS[$index]}"
  manifest_log="${LOG_DIR}/weekly_state_local_${jurisdiction}_${TIMESTAMP}.manifest.log"
  stderr_log="${LOG_DIR}/weekly_state_local_${jurisdiction}_${TIMESTAMP}.pipeline.stderr.log"
  load_stdout_log="${LOG_DIR}/weekly_state_local_${jurisdiction}_${TIMESTAMP}.load.stdout.log"
  load_stderr_log="${LOG_DIR}/weekly_state_local_${jurisdiction}_${TIMESTAMP}.load.stderr.log"

  .venv/bin/dotenv -f .env run -- \
    .venv/bin/python -m au_politics_money.cli run-state-local-pipeline \
      --jurisdiction "${jurisdiction}" \
    > "${manifest_log}" \
    2> "${stderr_log}"

  manifest_path="$(tail -n 1 "${manifest_log}")"
  if [[ ! -f "${manifest_path}" ]]; then
    printf 'Manifest path from %s was not a file: %s\n' "${manifest_log}" "${manifest_path}" >&2
    exit 1
  fi

  load_args=(load-state-local-pipeline-manifest "${manifest_path}")
  if [[ "${index}" -lt "${last_index}" ]]; then
    load_args+=(--skip-influence-events)
  fi

  .venv/bin/dotenv -f .env run -- \
    .venv/bin/python -m au_politics_money.cli "${load_args[@]}" \
    > "${load_stdout_log}" \
    2> "${load_stderr_log}"
done

.venv/bin/dotenv -f .env run -- \
  .venv/bin/python -m au_politics_money.cli qa-serving-database \
    --min-current-influence-events "${AUPOL_QA_MIN_CURRENT_INFLUENCE_EVENTS:-100000}" \
    --min-person-linked-influence-events "${AUPOL_QA_MIN_PERSON_LINKED_INFLUENCE_EVENTS:-5000}" \
    --min-current-money-flows "${AUPOL_QA_MIN_CURRENT_MONEY_FLOWS:-100000}" \
    --min-current-gift-interests "${AUPOL_QA_MIN_CURRENT_GIFT_INTERESTS:-4000}" \
    --min-current-house-office-terms "${AUPOL_QA_MIN_CURRENT_HOUSE_OFFICE_TERMS:-140}" \
    --min-current-senate-office-terms "${AUPOL_QA_MIN_CURRENT_SENATE_OFFICE_TERMS:-70}" \
  > "${LOG_DIR}/weekly_state_local_qa_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/weekly_state_local_qa_${TIMESTAMP}.stderr.log"

if [[ "${AUPOL_SKIP_WEEKLY_TESTS:-0}" != "1" ]]; then
  .venv/bin/python -m pytest \
    > "${LOG_DIR}/weekly_state_local_tests_${TIMESTAMP}.stdout.log" \
    2> "${LOG_DIR}/weekly_state_local_tests_${TIMESTAMP}.stderr.log"
fi
