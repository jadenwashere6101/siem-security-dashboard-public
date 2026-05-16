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
    restart_idx = main_body.index("restart_backend_service")
    assert dry_idx < apply_idx < restart_idx
