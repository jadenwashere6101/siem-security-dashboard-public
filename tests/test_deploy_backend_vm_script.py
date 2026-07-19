from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "deploy_backend_vm.sh"


def read_deploy_script():
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT_PATH.is_file()


def test_strict_mode_enabled():
    text = read_deploy_script()
    assert "set -euo pipefail" in text


def test_uses_venv_python_for_migrations():
    text = read_deploy_script()
    assert "venv/bin/python" in text
    assert 'venv/bin/python "$MIGRATE_SCRIPT"' in text or "venv/bin/python \"$MIGRATE_SCRIPT\"" in text


def test_migration_apply_before_backend_restart():
    text = read_deploy_script()
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    assert main_body.index("run_migration_apply") < main_body.index("restart_backend_service")


def test_dry_run_migrations_skips_apply_and_restart():
    text = read_deploy_script()
    assert "--dry-run-migrations" in text
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    dry_run_exit = main_body.split("if [[ \"$DRY_RUN_MIGRATIONS\" -eq 1 ]]; then", 1)[1].split("fi", 1)[0]
    assert "Skipping apply, restart, and health check" in dry_run_exit
    assert "run_migration_apply" not in dry_run_exit
    assert "restart_backend_service" not in dry_run_exit
    assert "DRY_RUN_MIGRATIONS=1" in text
    assert "SKIP_RESTART=1" in text
    assert "SKIP_HEALTH_CHECK=1" in text


def test_does_not_echo_password_variables():
    text = read_deploy_script()
    lowered = text.lower()
    assert "echo" not in lowered or "echo \"$" not in text
    assert "printf '%s\\n' \"$password\"" not in lowered
    assert "echo \"$siem_db_password\"" not in lowered
    assert "echo \"$db_password\"" not in lowered
    assert "echo \"$database_url\"" not in lowered
    assert "<redacted>" in text
    assert "[REDACTED]" in text


def test_supports_expected_flags():
    text = read_deploy_script()
    for flag in (
        "--dry-run-migrations",
        "--skip-restart",
        "--skip-health-check",
        "-h",
        "--help",
    ):
        assert flag in text


def test_verifies_repo_root_and_migrate_script():
    text = read_deploy_script()
    assert "verify_repo_root" in text
    assert "scripts/migrate.py" in text
    assert "Missing venv/bin/python" in text


def test_loads_env_without_mutating_file():
    text = read_deploy_script()
    assert "load_env_file" in text
    assert 'done < "$env_path"' in text
    assert "> \"$env_path\"" not in text


def test_builds_database_url_from_db_env_vars():
    text = read_deploy_script()
    assert "build_database_url" in text
    assert "SIEM_DB_HOST" in text
    assert "DB_HOST" in text
    assert "quote_plus" in text


def test_migration_failure_blocks_restart():
    text = read_deploy_script()
    assert "Migration apply failed. Backend was not restarted." in text
    apply_fn = text.split("run_migration_apply() {", 1)[1].split("\n}\n\nrestart_backend_service", 1)[0]
    assert "restart_backend_service" not in apply_fn
    assert "die \"Migration apply failed" in apply_fn


def test_default_flow_includes_dry_run_then_apply():
    text = read_deploy_script()
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    dry_idx = main_body.index("run_migration_dry_run")
    apply_idx = main_body.index("run_migration_apply")
    install_idx = main_body.index("install_backend_unit")
    restart_idx = main_body.index("restart_backend_service")
    status_idx = main_body.index("check_backend_service_status")
    health_idx = main_body.index("check_health_endpoint")
    security_idx = main_body.index("check_runtime_security_gates")
    worker_idx = main_body.index("install_and_restart_worker_units")
    assert dry_idx < apply_idx < install_idx < restart_idx < status_idx < health_idx < security_idx < worker_idx
    assert main_body.index("check_rate_limit_storage") < main_body.index("print_preflight")


def test_health_retry_loop_is_bounded_with_backoff():
    text = read_deploy_script()
    assert "HEALTH_MAX_ATTEMPTS=10" in text
    assert "HEALTH_RETRY_SECONDS=2" in text
    health_fn = text.split("check_health_endpoint() {", 1)[1].split("\n}\n\nmain", 1)[0]
    assert 'for attempt in $(seq 1 "$HEALTH_MAX_ATTEMPTS")' in health_fn
    assert 'sleep "$HEALTH_RETRY_SECONDS"' in health_fn
    assert '[[ "$attempt" -lt "$HEALTH_MAX_ATTEMPTS" ]]' in health_fn
    assert "after ${HEALTH_MAX_ATTEMPTS} attempts" in health_fn


def test_health_retry_passes_on_http_200():
    text = read_deploy_script()
    health_fn = text.split("check_health_endpoint() {", 1)[1].split("\n}\n\nmain", 1)[0]
    assert 'http_code="$(' in health_fn
    assert '--max-time 5 "$health_url"' in health_fn
    assert 'if [[ "$http_code" == "200" ]]; then' in health_fn
    assert 'Health check passed on attempt ${attempt}/${HEALTH_MAX_ATTEMPTS}.' in health_fn
    assert "return 0" in health_fn


def test_health_retry_prints_safe_attempt_progress():
    text = read_deploy_script()
    health_fn = text.split("check_health_endpoint() {", 1)[1].split("\n}\n\nmain", 1)[0]
    assert "Health check attempt ${attempt}/${HEALTH_MAX_ATTEMPTS}" in health_fn
    assert "$DATABASE_URL" not in health_fn
    assert "SIEM_DB_PASSWORD" not in health_fn
    assert "DB_PASSWORD" not in health_fn


def test_skip_health_check_still_skips_health_logic():
    text = read_deploy_script()
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    skip_block = main_body.split('if [[ "$SKIP_HEALTH_CHECK" -eq 1 ]]; then', 1)[1].split("fi", 1)[0]
    assert "Skipping health check (--skip-health-check)." in skip_block
    assert "exit 0" in skip_block
    assert "check_health_endpoint" not in skip_block
    assert "check_runtime_security_gates" not in skip_block
    assert "install_and_restart_worker_units" not in skip_block


def test_restart_still_happens_before_health_check():
    text = read_deploy_script()
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    assert main_body.index("restart_backend_service") < main_body.index("check_health_endpoint")
    assert main_body.index("check_backend_service_status") < main_body.index("check_health_endpoint")


def test_installs_backend_unit_before_restart():
    text = read_deploy_script()
    assert 'readonly BACKEND_UNIT_SOURCE="deploy/systemd/siem-backend.service"' in text
    assert 'readonly RUNTIME_VALIDATOR="scripts/validate_backend_runtime_env.sh"' in text
    assert "install_backend_unit()" in text
    assert "scripts/install_siem_backend_service.sh" in text
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    assert main_body.index("install_backend_unit") < main_body.index("restart_backend_service")


def test_verifies_gunicorn_effective_unit_and_blocks_flask_dev_server():
    text = read_deploy_script()
    assert "check_backend_effective_unit()" in text
    assert "venv/bin/gunicorn" in text
    assert "siem_backend:app" in text
    assert "python[0-9. ]+siem_backend\\.py|flask run|app\\.run" in text
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    assert main_body.index("check_runtime_security_gates") < main_body.index("install_and_restart_worker_units")


def test_runtime_security_gates_cover_loopback_debugger_and_secure_cookies():
    text = read_deploy_script()
    assert "check_loopback_bind()" in text
    assert "127\\\\.0\\\\.0\\\\.1" in text
    assert "publicly bound" in text
    assert "check_debugger_absent()" in text
    assert "?__debugger__=yes" in text
    assert "werkzeug|debugger|console locked|interactive traceback" in text
    assert "check_secure_cookie_config()" in text
    assert "SESSION_COOKIE_SECURE" in text
    assert "SESSION_COOKIE_HTTPONLY" in text
    assert "SESSION_COOKIE_SAMESITE" in text
    assert "check_rate_limit_storage()" in text
    assert "Validating shared rate-limit Redis storage" in text


def test_preflight_prints_sanitized_gunicorn_runtime_settings():
    text = read_deploy_script()
    assert "Runtime:        Gunicorn WSGI siem_backend:app" in text
    assert "SIEM_DEBUG:" in text
    assert "SIEM_BIND_HOST:" in text
    assert "Gunicorn workers:" in text
    assert "Gunicorn timeout:" in text
    assert "DB password:    <redacted>" in text
    assert "Rate-limit storage:" in text
    assert "Rate-limit storage connectivity: checked" in text
    assert "validate_rate_limit_storage_runtime(os.environ, production=True, ping=False)" in text
    assert "$SIEM_SECRET_KEY" not in text
    assert "$SECRET_KEY" not in text
    assert "$SIEM_RATE_LIMIT_STORAGE_URI" not in text


def test_rate_limit_storage_validation_blocks_worker_restart():
    text = read_deploy_script()
    main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
    security_fn = text.split("check_runtime_security_gates() {", 1)[1].split("\n}\n\nmain", 1)[0]

    assert "check_rate_limit_storage" in security_fn
    assert main_body.index("check_runtime_security_gates") < main_body.index("install_and_restart_worker_units")
    assert "apt install redis" not in text
    assert "yum install redis" not in text
    assert "systemctl restart redis" not in text
    assert "systemctl reload nginx" not in text
