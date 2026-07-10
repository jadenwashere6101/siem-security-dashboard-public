#!/usr/bin/env bash
# Run one bounded response-action queue worker batch using the environment loaded by systemd.
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

export SOAR_EXECUTION_MODE="${SOAR_EXECUTION_MODE:-simulation}"
export SOAR_RUNNER_BATCH_SIZE="${SOAR_RUNNER_BATCH_SIZE:-10}"
export SOAR_RECOVER_STALE_RUNNING="${SOAR_RECOVER_STALE_RUNNING:-true}"
export SOAR_STALE_RUNNING_AFTER_SECONDS="${SOAR_STALE_RUNNING_AFTER_SECONDS:-900}"
export SOAR_STALE_RECOVERY_LIMIT="${SOAR_STALE_RECOVERY_LIMIT:-50}"

exec venv/bin/python scripts/soar_worker_run.py "$@"
