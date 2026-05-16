#!/usr/bin/env bash
# VM backend deploy: schema migrations (scripts/migrate.py) then siem-backend.service restart.
# See docs/schema_migration_workflow.md and openspec/changes/harden-migration-deployment-workflow/
# Frontend deploy remains deploy.sh (artifact helper only).

set -euo pipefail

readonly SERVICE_NAME="siem-backend.service"
readonly MIGRATE_SCRIPT="scripts/migrate.py"
readonly ENV_FILE=".env"

DRY_RUN_MIGRATIONS=0
SKIP_RESTART=0
SKIP_HEALTH_CHECK=0

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: scripts/deploy_backend_vm.sh [OPTIONS]

Run from the repository root on the VM after syncing code.
Applies pending schema migrations, then restarts the backend service.

Options:
  --dry-run-migrations   Run migration dry-run only; do not apply, restart, or health-check.
  --skip-restart         Apply migrations but do not restart siem-backend.service.
  --skip-health-check    Skip HTTP health probe after restart.
  -h, --help             Show this help.

This script does not build the frontend, run playbooks, or send notifications.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run-migrations)
        DRY_RUN_MIGRATIONS=1
        ;;
      --skip-restart)
        SKIP_RESTART=1
        ;;
      --skip-health-check)
        SKIP_HEALTH_CHECK=1
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        die "Unknown option: $1 (use --help)"
        ;;
    esac
    shift
  done

  if [[ "$DRY_RUN_MIGRATIONS" -eq 1 ]]; then
    SKIP_RESTART=1
    SKIP_HEALTH_CHECK=1
  fi
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "${script_dir}/.." && pwd)"
  cd "$REPO_ROOT"
}

verify_repo_root() {
  [[ -f "$MIGRATE_SCRIPT" ]] || die "Missing ${MIGRATE_SCRIPT}. Run from repository root."
  [[ -d migrations ]] || die "Missing migrations/ directory."
  [[ -x venv/bin/python ]] || die "Missing venv/bin/python. Create the project virtualenv on the VM."
}

# Load .env without echoing values (read-only; does not modify the file).
load_env_file() {
  local env_path="$1"
  [[ -f "$env_path" ]] || die "Missing ${env_path}. Create it on the VM before deploy."

  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]]; then
      line="${line#export }"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    key="${key#"${key%%[![:space:]]*}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "${key}=${value}"
  done < "$env_path"
}

build_database_url() {
  DATABASE_URL="$(
    venv/bin/python - <<'PY'
import os
import sys
from urllib.parse import quote_plus

def pick(*keys, default=""):
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return default

existing = os.getenv("DATABASE_URL", "").strip()
if existing:
    print(existing)
    sys.exit(0)

host = pick("SIEM_DB_HOST", "DB_HOST")
port = pick("SIEM_DB_PORT", "DB_PORT", default="5432")
dbname = pick("SIEM_DB_NAME", "DB_NAME")
user = pick("SIEM_DB_USER", "DB_USER")
password = pick("SIEM_DB_PASSWORD", "DB_PASSWORD")

missing = [
    name
    for name, value in (
        ("SIEM_DB_HOST or DB_HOST", host),
        ("SIEM_DB_NAME or DB_NAME", dbname),
        ("SIEM_DB_USER or DB_USER", user),
        ("SIEM_DB_PASSWORD or DB_PASSWORD", password),
    )
    if not value
]
if missing:
    print("Missing database settings: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)

print(
    "postgresql://"
    f"{quote_plus(user)}:{quote_plus(password)}"
    f"@{host}:{port}/{quote_plus(dbname)}"
)
PY
  )" || die "Unable to build DATABASE_URL from .env (see stderr; secrets are not printed)."
  export DATABASE_URL
}

verify_db_settings_present() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    return 0
  fi
  local host db user
  host="${SIEM_DB_HOST:-${DB_HOST:-}}"
  db="${SIEM_DB_NAME:-${DB_NAME:-}}"
  user="${SIEM_DB_USER:-${DB_USER:-}}"
  [[ -n "$host" && -n "$db" && -n "$user" && -n "${SIEM_DB_PASSWORD:-${DB_PASSWORD:-}}" ]] \
    || die "Database settings missing. Set DATABASE_URL or SIEM_DB_* / DB_* in ${ENV_FILE}."
}

print_preflight() {
  local git_rev migration_count db_host db_name db_user health_port
  git_rev="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  migration_count="$(find migrations -maxdepth 1 -name '*.sql' | wc -l | tr -d ' ')"
  db_host="${SIEM_DB_HOST:-${DB_HOST:-}}"
  db_name="${SIEM_DB_NAME:-${DB_NAME:-}}"
  db_user="${SIEM_DB_USER:-${DB_USER:-}}"
  health_port="${SIEM_PORT:-5051}"

  log "=== Backend VM deploy preflight ==="
  log "Repo root:      ${REPO_ROOT}"
  log "Git revision:   ${git_rev}"
  log "Hostname:       $(hostname)"
  log "Migration files: ${migration_count}"
  log "DB host:        ${db_host:-<unset>}"
  log "DB name:        ${db_name:-<unset>}"
  log "DB user:        ${db_user:-<unset>}"
  log "DB password:    <redacted>"
  log "Service:        ${SERVICE_NAME}"
  log "INTEGRATION_MODE: ${INTEGRATION_MODE:-<unset>}"
  log "SOAR_REAL_SLACK_ENABLED: ${SOAR_REAL_SLACK_ENABLED:-<unset>}"
  log "Dry-run only:   $([[ "$DRY_RUN_MIGRATIONS" -eq 1 ]] && echo yes || echo no)"
  log "Skip restart:   $([[ "$SKIP_RESTART" -eq 1 ]] && echo yes || echo no)"
  log "Skip health:    $([[ "$SKIP_HEALTH_CHECK" -eq 1 ]] && echo yes || echo no)"
  log "Health probe:   http://127.0.0.1:${health_port}/health"
  log "==================================="
}

run_migration_dry_run() {
  log "Running migration dry-run (no DDL, no ledger writes)..."
  log "Command: venv/bin/python ${MIGRATE_SCRIPT} --db-url [REDACTED] --dry-run"
  venv/bin/python "$MIGRATE_SCRIPT" --db-url "$DATABASE_URL" --dry-run
}

run_migration_apply() {
  log "Applying pending schema migrations..."
  log "Command: venv/bin/python ${MIGRATE_SCRIPT} --db-url [REDACTED]"
  if ! venv/bin/python "$MIGRATE_SCRIPT" --db-url "$DATABASE_URL"; then
    die "Migration apply failed. Backend was not restarted. Inspect schema_migrations and migration logs."
  fi
}

restart_backend_service() {
  log "Restarting ${SERVICE_NAME}..."
  sudo systemctl restart "$SERVICE_NAME"
}

check_backend_service_status() {
  log "Checking ${SERVICE_NAME} status..."
  sudo systemctl status "$SERVICE_NAME" --no-pager || die "${SERVICE_NAME} is not healthy after restart."
}

check_health_endpoint() {
  local health_port health_url
  health_port="${SIEM_PORT:-5051}"
  health_url="http://127.0.0.1:${health_port}/health"
  if ! command -v curl >/dev/null 2>&1; then
    log "curl not available; skipping health check for ${health_url}"
    return 0
  fi
  log "Probing ${health_url} ..."
  if curl -fsS --max-time 10 "$health_url" >/dev/null; then
    log "Health check passed."
  else
    die "Health check failed for ${health_url}"
  fi
}

main() {
  parse_args "$@"
  resolve_repo_root
  verify_repo_root
  load_env_file "$ENV_FILE"
  verify_db_settings_present
  build_database_url
  print_preflight

  run_migration_dry_run

  if [[ "$DRY_RUN_MIGRATIONS" -eq 1 ]]; then
    log "Dry-run migrations complete. Skipping apply, restart, and health check."
    exit 0
  fi

  run_migration_apply

  if [[ "$SKIP_RESTART" -eq 1 ]]; then
    log "Skipping backend restart (--skip-restart)."
    exit 0
  fi

  restart_backend_service
  check_backend_service_status

  if [[ "$SKIP_HEALTH_CHECK" -eq 1 ]]; then
    log "Skipping health check (--skip-health-check)."
    exit 0
  fi

  check_health_endpoint
  log "Backend VM deploy complete."
}

main "$@"
