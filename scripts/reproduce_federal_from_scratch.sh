#!/usr/bin/env bash
#
# Reproduce the entire federal data layer from scratch, against live
# AEC/APH/AIMS public sources. Designed to be the single command a public
# reader runs to verify any number on the site.
#
# Usage:
#   bash scripts/reproduce_federal_from_scratch.sh [--smoke]
#
# Options:
#   --smoke    Run the federal foundation pipeline in smoke mode (small
#              House interests subset). Useful for CI / a quick local check.
#              Without --smoke the script runs the full federal pipeline
#              with --refresh-existing-sources so cached but
#              update-sensitive sources are re-fetched.
#
# What this does:
#   1. Sanity-checks Python / Node / docker-compose / disk space.
#   2. Brings up the local Postgres/PostGIS container and waits for it.
#   3. Bootstraps the backend venv and installs locked dependencies.
#   4. Runs the federal foundation pipeline (or smoke pipeline).
#   5. Applies the schema migrations.
#   6. Loads the processed artifacts into Postgres.
#   7. Runs the post-load QA gate (qa-serving-database).
#   8. Runs the full backend pytest suite with Postgres integration enabled.
#   9. Runs the backend ruff sweep and the frontend production build.
#  10. Prints a summary with the manifest path so the run is traceable.
#
# Every step writes to stdout/stderr and to data/audit/logs/. If any step
# fails the script exits non-zero and the partial logs are left in place
# so failures can be inspected.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
LOG_DIR="${PROJECT_ROOT}/data/audit/logs"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
DOCKER_COMPOSE="${DOCKER_COMPOSE:-/opt/homebrew/bin/docker-compose}"

mkdir -p "${LOG_DIR}"

SMOKE=false
for arg in "$@"; do
  case "$arg" in
    --smoke) SMOKE=true ;;
    *) echo "Unknown argument: $arg"; exit 2 ;;
  esac
done

log() {
  printf '\n==> %s\n' "$*"
}

# 1. Sanity checks ---------------------------------------------------------
log "Sanity-checking required tools"
command -v python3 >/dev/null
command -v node >/dev/null
command -v npm >/dev/null
command -v "${DOCKER_COMPOSE}" >/dev/null
df -h "${PROJECT_ROOT}" | tail -1

# 2. Bring Postgres up -----------------------------------------------------
log "Bringing the Postgres/PostGIS container up"
( cd "${BACKEND_DIR}" && "${DOCKER_COMPOSE}" -f docker-compose.yml up -d )

log "Waiting for Postgres to become ready"
ATTEMPTS=20
for i in $(seq 1 "${ATTEMPTS}"); do
  if ( cd "${BACKEND_DIR}" && \
       "${DOCKER_COMPOSE}" -f docker-compose.yml exec -T postgres \
       pg_isready -U au_politics -d au_politics ) 2>/dev/null; then
    break
  fi
  sleep 2
  if [[ "$i" == "${ATTEMPTS}" ]]; then
    echo "Postgres did not become ready after ${ATTEMPTS} attempts." >&2
    exit 1
  fi
done

# 3. Bootstrap venv --------------------------------------------------------
if [[ ! -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
  log "Creating backend venv and installing locked dependencies"
  ( cd "${BACKEND_DIR}" && python3 -m venv .venv )
  ( cd "${BACKEND_DIR}" && \
    .venv/bin/python -m pip install -c requirements.lock -e '.[dev]' )
fi

# 4. Run the federal foundation pipeline -----------------------------------
PIPELINE_FLAGS=(--refresh-existing-sources)
if [[ "${SMOKE}" == "true" ]]; then
  PIPELINE_FLAGS=(--smoke)
fi

log "Running the federal foundation pipeline (${PIPELINE_FLAGS[*]})"
( cd "${BACKEND_DIR}" && \
  .venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money run-federal-foundation-pipeline "${PIPELINE_FLAGS[@]}" \
  > "${LOG_DIR}/reproduce_federal_pipeline_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/reproduce_federal_pipeline_${TIMESTAMP}.stderr.log" )

# 5. Apply migrations ------------------------------------------------------
log "Applying Postgres schema migrations"
( cd "${BACKEND_DIR}" && \
  .venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money migrate-postgres \
  > "${LOG_DIR}/reproduce_federal_migrate_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/reproduce_federal_migrate_${TIMESTAMP}.stderr.log" )

# 6. Load processed artifacts into Postgres --------------------------------
log "Loading processed artifacts into Postgres (federal-only flags)"
( cd "${BACKEND_DIR}" && \
  .venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money load-postgres \
    --skip-qld-ecq \
    --skip-nsw-aggregates \
    --skip-act-gift-returns \
    --skip-act-annual-returns \
    --skip-nt-ntec-annual-returns \
    --skip-nt-ntec-annual-gifts \
    --skip-sa-ecsa-return-summaries \
    --skip-tas-tec-donations \
    --skip-vic-vec-funding-register \
    --skip-waec-political-contributions \
  > "${LOG_DIR}/reproduce_federal_load_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/reproduce_federal_load_${TIMESTAMP}.stderr.log" )

# 7. Run the post-load QA gate ---------------------------------------------
log "Running the qa-serving-database gate"
( cd "${BACKEND_DIR}" && \
  .venv/bin/dotenv -f .env run -- \
  .venv/bin/au-politics-money qa-serving-database \
  > "${LOG_DIR}/reproduce_federal_qa_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/reproduce_federal_qa_${TIMESTAMP}.stderr.log" )

# 8. Run the full backend pytest suite -------------------------------------
log "Running the backend pytest suite (Postgres integration enabled)"
( cd "${PROJECT_ROOT}" && \
  AUPOL_RUN_POSTGRES_INTEGRATION=1 \
  DATABASE_URL_TEST=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \
  "${BACKEND_DIR}/.venv/bin/pytest" "${BACKEND_DIR}/tests/" -q \
  > "${LOG_DIR}/reproduce_federal_pytest_${TIMESTAMP}.stdout.log" \
  2> "${LOG_DIR}/reproduce_federal_pytest_${TIMESTAMP}.stderr.log" )

# 9. Lint + frontend build -------------------------------------------------
log "Running backend ruff"
( cd "${BACKEND_DIR}" && .venv/bin/ruff check . \
  > "${LOG_DIR}/reproduce_federal_ruff_${TIMESTAMP}.stdout.log" 2>&1 )

log "Building the frontend production bundle"
( cd "${FRONTEND_DIR}" && npm run build \
  > "${LOG_DIR}/reproduce_federal_frontend_build_${TIMESTAMP}.stdout.log" 2>&1 )

# 10. Final summary --------------------------------------------------------
log "Reproduce-federal complete"
LATEST_MANIFEST="$(find "${PROJECT_ROOT}/data/audit/pipeline_runs" \
  -type f -name '*.json' -newer "${LOG_DIR}/reproduce_federal_pipeline_${TIMESTAMP}.stdout.log" 2>/dev/null \
  | sort | tail -1 || true)"
echo "Pipeline manifest: ${LATEST_MANIFEST:-<not found>}"
echo "Logs:              ${LOG_DIR}/reproduce_federal_*_${TIMESTAMP}.{stdout,stderr}.log"
