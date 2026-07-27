#!/usr/bin/env bash
# Run one bounded scheduled SOC briefing worker batch using systemd-provided environment.
# EnvironmentFile values are data; this wrapper must never source or evaluate .env as shell code.

set -euo pipefail

pick() {
  local primary="$1"
  local fallback="$2"
  local value="${!primary:-}"
  if [[ -n "$value" ]]; then
    printf '%s' "$value"
    return 0
  fi
  printf '%s' "${!fallback:-}"
}

db_name="$(pick SIEM_DB_NAME DB_NAME)"
db_user="$(pick SIEM_DB_USER DB_USER)"
db_host="$(pick SIEM_DB_HOST DB_HOST)"
db_password="$(pick SIEM_DB_PASSWORD DB_PASSWORD)"
db_port="${SIEM_DB_PORT:-${DB_PORT:-5432}}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ -z "$db_name" || -z "$db_user" || -z "$db_host" || -z "$db_password" ]]; then
    printf 'ERROR: database settings missing; set DATABASE_URL or SIEM_DB_*/DB_* values in .env\n' >&2
    exit 1
  fi
  export DATABASE_URL="postgresql://${db_user}:${db_password}@${db_host}:${db_port}/${db_name}"
fi

export SOC_BRIEFING_BATCH_SIZE="${SOC_BRIEFING_BATCH_SIZE:-5}"
export SOC_BRIEFING_MATERIALIZE_LIMIT="${SOC_BRIEFING_MATERIALIZE_LIMIT:-25}"
export SOC_BRIEFING_STALE_RECOVERY_LIMIT="${SOC_BRIEFING_STALE_RECOVERY_LIMIT:-50}"
export SOC_BRIEFING_MAX_RUNTIME_SECONDS="${SOC_BRIEFING_MAX_RUNTIME_SECONDS:-55}"

exec venv/bin/python scripts/soc_briefing_worker.py "$@"
