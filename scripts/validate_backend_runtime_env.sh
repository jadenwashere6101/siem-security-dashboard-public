#!/usr/bin/env bash
# Validate production-only SIEM backend runtime settings before Gunicorn starts.

set -euo pipefail

EXPECTED_ROOT="${SIEM_BACKEND_ROOT:-/home/jaden/siem-security-dashboard}"
GUNICORN_BIN="${EXPECTED_ROOT}/venv/bin/gunicorn"
PYTHON_BIN="${EXPECTED_ROOT}/venv/bin/python"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

present() {
  [[ -n "${!1:-}" ]]
}

bool_false() {
  case "${1:-}" in
    false|False|FALSE|0|no|No|NO)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

bool_true() {
  case "${1:-}" in
    true|True|TRUE|1|yes|Yes|YES|on|On|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

[[ -x "$GUNICORN_BIN" ]] || die "Missing executable Gunicorn at ${GUNICORN_BIN}."
[[ -x "$PYTHON_BIN" ]] || die "Missing executable Python at ${PYTHON_BIN}."

bool_false "${SIEM_DEBUG:-}" || die "Production requires SIEM_DEBUG=false."

bind_host="${SIEM_BIND_HOST:-}"
[[ "$bind_host" == "127.0.0.1" ]] || die "Production requires SIEM_BIND_HOST=127.0.0.1."

port="${SIEM_PORT:-5051}"
[[ "$port" =~ ^[0-9]+$ ]] || die "SIEM_PORT must be numeric."

if ! present SIEM_SECRET_KEY && ! present SECRET_KEY; then
  die "Missing SIEM_SECRET_KEY or SECRET_KEY."
fi

present SIEM_ADMIN_USERNAME || present ADMIN_USERNAME || die "Missing SIEM_ADMIN_USERNAME or ADMIN_USERNAME."
present SIEM_ADMIN_PASSWORD || present ADMIN_PASSWORD || die "Missing SIEM_ADMIN_PASSWORD or ADMIN_PASSWORD."

if ! present DATABASE_URL; then
  host="${SIEM_DB_HOST:-${DB_HOST:-}}"
  name="${SIEM_DB_NAME:-${DB_NAME:-}}"
  user="${SIEM_DB_USER:-${DB_USER:-}}"
  password="${SIEM_DB_PASSWORD:-${DB_PASSWORD:-}}"
  [[ -n "$host" && -n "$name" && -n "$user" && -n "$password" ]] \
    || die "Missing DATABASE_URL or complete SIEM_DB_* / DB_* settings."
fi

workers="${SIEM_GUNICORN_WORKERS:-2}"
timeout="${SIEM_GUNICORN_TIMEOUT:-120}"
graceful_timeout="${SIEM_GUNICORN_GRACEFUL_TIMEOUT:-30}"
keepalive="${SIEM_GUNICORN_KEEPALIVE:-5}"
for value_name in workers timeout graceful_timeout keepalive; do
  value="${!value_name}"
  [[ "$value" =~ ^[0-9]+$ ]] || die "${value_name} must be numeric."
done

anthropic_status="disabled"
case "${AI_ANTHROPIC_ENABLED:-false}" in
  true|True|TRUE|1|yes|Yes|YES|on|On|ON|false|False|FALSE|0|no|No|NO|off|Off|OFF)
    ;;
  *)
    die "AI_ANTHROPIC_ENABLED must be a recognized boolean value."
    ;;
esac
if bool_true "${AI_ANTHROPIC_ENABLED:-false}"; then
  present ANTHROPIC_API_KEY || die "Anthropic is enabled but ANTHROPIC_API_KEY is missing."
  present AI_ANTHROPIC_MODEL || die "Anthropic is enabled but AI_ANTHROPIC_MODEL is missing."
  [[ "${AI_ANTHROPIC_MODEL}" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$ ]] \
    || die "AI_ANTHROPIC_MODEL must be a valid provider model identifier."
  anthropic_timeout="${AI_ANTHROPIC_TIMEOUT_SECONDS:-20}"
  [[ "$anthropic_timeout" =~ ^[0-9]+([.][0-9]+)?$ && ! "$anthropic_timeout" =~ ^0+([.]0+)?$ ]] \
    || die "AI_ANTHROPIC_TIMEOUT_SECONDS must be a positive number when Anthropic is enabled."
  anthropic_api_version="${ANTHROPIC_API_VERSION:-2023-06-01}"
  [[ "$anthropic_api_version" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
    || die "ANTHROPIC_API_VERSION must use YYYY-MM-DD format when Anthropic is enabled."
  anthropic_status="configured-unassigned"
fi

rate_limit_storage_summary="$(
  "$PYTHON_BIN" - <<'PY'
import os
import sys

from core.rate_limit_config import RateLimitStorageConfigError, validate_rate_limit_storage_runtime

try:
    config = validate_rate_limit_storage_runtime(os.environ, production=True, ping=True)
except RateLimitStorageConfigError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)

print(config.sanitized_summary)
PY
)" || die "Rate-limit storage validation failed."

printf 'SIEM backend runtime validation passed: debug=false bind=%s port=%s workers=%s timeout=%s graceful_timeout=%s keepalive=%s anthropic=%s rate_limit_storage=\"%s\"\n' \
  "$bind_host" "$port" "$workers" "$timeout" "$graceful_timeout" "$keepalive" "$anthropic_status" "$rate_limit_storage_summary"
