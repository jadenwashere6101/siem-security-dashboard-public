#!/usr/bin/env bash
# Operator-controlled install/update/reload/rollback for siem-backend.service.

set -euo pipefail

readonly SERVICE_NAME="siem-backend.service"
readonly UNIT_SOURCE="deploy/systemd/${SERVICE_NAME}"
readonly UNIT_DEST="/etc/systemd/system/${SERVICE_NAME}"
readonly EXPECTED_USER="jaden"
readonly EXPECTED_HOME="/home/${EXPECTED_USER}/siem-security-dashboard"

DRY_RUN=0
DO_ENABLE=0
DO_START=0
DO_RELOAD=0
DO_ROLLBACK=0

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: scripts/install_siem_backend_service.sh [OPTIONS]

Install, update, reload, or roll back siem-backend.service on the VM.
Run from the repository root as the jaden user. Privileged steps use sudo.

Install copies the repo-owned Gunicorn systemd unit and reloads systemd. --start
restarts the service and verifies the effective unit contains Gunicorn.

Options:
  --dry-run       Print commands without executing them.
  --enable        Enable the service after install.
  --start         Restart the service after install (implies --enable).
  --reload        Gracefully reload the already-installed service after install.
  --rollback      Stop, disable, remove the unit, daemon-reload, and reset failures.
  -h, --help      Show this help.

Examples:
  scripts/install_siem_backend_service.sh --dry-run
  scripts/install_siem_backend_service.sh
  scripts/install_siem_backend_service.sh --enable --start
  scripts/install_siem_backend_service.sh --reload
  scripts/install_siem_backend_service.sh --rollback --dry-run

This helper never edits .env, runs migrations, builds frontend assets, changes nginx,
touches provider configuration, or deploys code to the VM.
EOF
}

run_sudo() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] sudo %s\n' "$*"
    return 0
  fi
  sudo "$@"
}

preflight() {
  [[ "$(id -un)" == "$EXPECTED_USER" ]] || die "run as ${EXPECTED_USER} on the VM"
  [[ -d "$EXPECTED_HOME" ]] || die "expected repo at ${EXPECTED_HOME}"
  [[ -f "$UNIT_SOURCE" ]] || die "missing unit source: ${UNIT_SOURCE}"
  [[ -f scripts/validate_backend_runtime_env.sh ]] || die "missing runtime validator"
  [[ -f siem_backend.py ]] || die "missing siem_backend.py"
  [[ -x venv/bin/gunicorn ]] || die "missing executable venv/bin/gunicorn"
}

install_unit() {
  preflight
  log "Installing ${SERVICE_NAME} from ${UNIT_SOURCE}"
  run_sudo cp "$UNIT_SOURCE" "$UNIT_DEST"
  run_sudo systemctl daemon-reload
  log "Unit installed. Service is not restarted unless --start or --reload was passed."
}

enable_service() {
  run_sudo systemctl enable "$SERVICE_NAME"
}

verify_effective_unit() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] sudo systemctl cat %s --no-pager\n' "$SERVICE_NAME"
    return 0
  fi
  effective="$(sudo systemctl cat "$SERVICE_NAME" --no-pager)"
  printf '%s\n' "$effective"
  grep -q 'venv/bin/gunicorn' <<<"$effective" || die "effective unit does not run Gunicorn"
  grep -q 'siem_backend:app' <<<"$effective" || die "effective unit does not target siem_backend:app"
  if grep -Eq 'python[0-9. ]+siem_backend\.py|flask run|app\.run' <<<"$effective"; then
    die "effective unit contains Flask development-server startup"
  fi
}

start_service() {
  run_sudo systemctl restart "$SERVICE_NAME"
  run_sudo systemctl status "$SERVICE_NAME" --no-pager
  verify_effective_unit
}

reload_service() {
  run_sudo systemctl reload "$SERVICE_NAME"
  run_sudo systemctl status "$SERVICE_NAME" --no-pager
  verify_effective_unit
}

rollback_service() {
  preflight
  log "Rolling back ${SERVICE_NAME}"
  run_sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  run_sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  run_sudo rm -f "$UNIT_DEST"
  run_sudo systemctl daemon-reload
  run_sudo systemctl reset-failed "$SERVICE_NAME" 2>/dev/null || true
  log "Rollback complete."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --enable)
      DO_ENABLE=1
      shift
      ;;
    --start)
      DO_ENABLE=1
      DO_START=1
      shift
      ;;
    --reload)
      DO_RELOAD=1
      shift
      ;;
    --rollback)
      DO_ROLLBACK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1 (use --help)"
      ;;
  esac
done

if [[ "$DO_ROLLBACK" -eq 1 ]]; then
  rollback_service
  exit 0
fi

install_unit

if [[ "$DO_ENABLE" -eq 1 ]]; then
  enable_service
fi

if [[ "$DO_START" -eq 1 ]]; then
  start_service
elif [[ "$DO_RELOAD" -eq 1 ]]; then
  reload_service
fi
