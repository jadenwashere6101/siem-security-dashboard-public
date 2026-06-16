#!/usr/bin/env bash
# Operator-controlled install/update/rollback for soar-playbook-worker.service.
# Does not run automatically from deploy_backend_vm.sh or repo checkout.
# See docs/playbook_worker_systemd_service.md

set -euo pipefail

readonly SERVICE_NAME="soar-playbook-worker.service"
readonly UNIT_SOURCE="deploy/systemd/soar-playbook-worker.service"
readonly UNIT_DEST="/etc/systemd/system/${SERVICE_NAME}"
readonly EXPECTED_USER="jaden"
readonly EXPECTED_HOME="/home/${EXPECTED_USER}/siem-security-dashboard"

DRY_RUN=0
DO_ENABLE=0
DO_START=0
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
Usage: scripts/install_soar_playbook_worker_service.sh [OPTIONS]

Install, update, or roll back soar-playbook-worker.service on the VM.
Run from the repository root as the jaden user. Privileged steps use sudo.

By default, install copies the unit and runs systemctl daemon-reload only.
The service is not enabled or started unless you pass explicit flags.

Options:
  --dry-run       Print commands without executing them.
  --enable        Enable the service after install (requires install path).
  --start         Start the service after install (implies --enable).
  --rollback      Stop, disable, remove the unit, and daemon-reload.
  -h, --help      Show this help.

Examples:
  scripts/install_soar_playbook_worker_service.sh --dry-run
  scripts/install_soar_playbook_worker_service.sh
  scripts/install_soar_playbook_worker_service.sh --enable --start
  scripts/install_soar_playbook_worker_service.sh --rollback --dry-run

This script does not modify SOAR worker logic, backend APIs, schema, or
deploy_backend_vm.sh behavior.
EOF
}

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
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
  [[ -f scripts/soar_playbook_worker_daemon.py ]] || die "missing daemon entrypoint"
  [[ -x venv/bin/python3 ]] || die "missing executable venv/bin/python3"
}

install_unit() {
  preflight
  log "Installing ${SERVICE_NAME} from ${UNIT_SOURCE}"
  run_sudo cp "$UNIT_SOURCE" "$UNIT_DEST"
  run_sudo systemctl daemon-reload
  log "Unit installed. Service is not started unless --start was passed."
}

enable_service() {
  run_sudo systemctl enable "$SERVICE_NAME"
}

start_service() {
  run_sudo systemctl start "$SERVICE_NAME"
  run_sudo systemctl status "$SERVICE_NAME" --no-pager || true
}

rollback_service() {
  preflight
  log "Rolling back ${SERVICE_NAME}"
  run_sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  run_sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  run_sudo rm -f "$UNIT_DEST"
  run_sudo systemctl daemon-reload
  run_sudo systemctl reset-failed "$SERVICE_NAME" 2>/dev/null || true
  if [[ "$DRY_RUN" -eq 0 ]]; then
    systemctl is-enabled "$SERVICE_NAME" 2>/dev/null || log "service not enabled (expected after rollback)"
    systemctl is-active "$SERVICE_NAME" 2>/dev/null || log "service not active (expected after rollback)"
  fi
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
fi
