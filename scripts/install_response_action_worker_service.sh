#!/usr/bin/env bash
# Operator-controlled install/update/rollback for response-action queue worker units.

set -euo pipefail

readonly SERVICE_NAME="soar-response-action-worker.service"
readonly TIMER_NAME="soar-response-action-worker.timer"
readonly SERVICE_SOURCE="deploy/systemd/${SERVICE_NAME}"
readonly TIMER_SOURCE="deploy/systemd/${TIMER_NAME}"
readonly SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}"
readonly TIMER_DEST="/etc/systemd/system/${TIMER_NAME}"
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
Usage: scripts/install_response_action_worker_service.sh [OPTIONS]

Install, update, or roll back the SOAR response-action queue worker service/timer.
Run from the repository root as the jaden user on the VM. Privileged steps use sudo.

By default, install copies the service and timer and runs systemctl daemon-reload.
The timer is not enabled or started unless you pass explicit flags.

Options:
  --dry-run       Print commands without executing them.
  --enable        Enable the timer after install.
  --start         Start the timer after install (implies --enable).
  --rollback      Stop, disable, remove units, and daemon-reload.
  -h, --help      Show this help.

Examples:
  scripts/install_response_action_worker_service.sh --dry-run
  scripts/install_response_action_worker_service.sh
  scripts/install_response_action_worker_service.sh --enable --start
  scripts/install_response_action_worker_service.sh --rollback --dry-run

The timer runs bounded simulation-safe batches. It does not enable real firewall
enforcement and does not process playbook_executions.
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
  [[ -f "$SERVICE_SOURCE" ]] || die "missing service source: ${SERVICE_SOURCE}"
  [[ -f "$TIMER_SOURCE" ]] || die "missing timer source: ${TIMER_SOURCE}"
  [[ -f scripts/soar_worker_run.py ]] || die "missing response-action worker runner"
  [[ -f scripts/run_response_action_worker_service.sh ]] || die "missing service wrapper"
  [[ -x venv/bin/python ]] || die "missing executable venv/bin/python"
}

install_units() {
  preflight
  log "Installing ${SERVICE_NAME} and ${TIMER_NAME}"
  run_sudo cp "$SERVICE_SOURCE" "$SERVICE_DEST"
  run_sudo cp "$TIMER_SOURCE" "$TIMER_DEST"
  run_sudo systemctl daemon-reload
  log "Units installed. Timer is not enabled or started unless --start was passed."
}

enable_timer() {
  run_sudo systemctl enable "$TIMER_NAME"
}

start_timer() {
  run_sudo systemctl start "$TIMER_NAME"
  run_sudo systemctl status "$TIMER_NAME" --no-pager || true
}

rollback_units() {
  preflight
  log "Rolling back ${SERVICE_NAME} and ${TIMER_NAME}"
  run_sudo systemctl stop "$TIMER_NAME" 2>/dev/null || true
  run_sudo systemctl disable "$TIMER_NAME" 2>/dev/null || true
  run_sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  run_sudo rm -f "$SERVICE_DEST" "$TIMER_DEST"
  run_sudo systemctl daemon-reload
  run_sudo systemctl reset-failed "$SERVICE_NAME" "$TIMER_NAME" 2>/dev/null || true
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
  rollback_units
  exit 0
fi

install_units

if [[ "$DO_ENABLE" -eq 1 ]]; then
  enable_timer
fi

if [[ "$DO_START" -eq 1 ]]; then
  start_timer
fi
