#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
LOG_DIR="${PROJECT_ROOT}/data/audit/logs"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"

SOURCE_IDS=(
  nsw_electoral_disclosures
  vic_vec_disclosures
  qld_ecq_disclosures
  sa_ecsa_funding_disclosure
  sa_ecsa_funding2024_return_records
  waec_returns_reports
  waec_ods_public_dashboard
  waec_ods_political_contributions
  tas_tec_disclosure_funding
  tas_tec_donations_monthly_table
  tas_tec_donations_seven_day_ha25_table
  tas_tec_donations_seven_day_lc26_table
  nt_ntec_annual_returns
  act_elections_funding_disclosure
)

mkdir -p "${LOG_DIR}"

cd "${BACKEND_DIR}"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -e '.[dev]'
fi

for source_id in "${SOURCE_IDS[@]}"; do
  .venv/bin/python -m au_politics_money.cli show-source "${source_id}" \
    > "${LOG_DIR}/state_council_show_${source_id}_${TIMESTAMP}.json"

  .venv/bin/python -m au_politics_money.cli fetch-source "${source_id}" \
    > "${LOG_DIR}/state_council_fetch_${source_id}_${TIMESTAMP}.stdout.log" \
    2> "${LOG_DIR}/state_council_fetch_${source_id}_${TIMESTAMP}.stderr.log"
done
