import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
UNIT_PATH = REPO_ROOT / "deploy" / "systemd" / "siem-backend.service"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_backend_runtime_env.sh"
INSTALLER_PATH = REPO_ROOT / "scripts" / "install_siem_backend_service.sh"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_backend_systemd_unit_runs_gunicorn_wsgi_on_loopback():
    unit = read(UNIT_PATH)

    assert "Description=SIEM Backend API (Gunicorn WSGI)" in unit
    assert "EnvironmentFile=/home/jaden/siem-security-dashboard/.env" in unit
    assert "Environment=SIEM_BIND_HOST=127.0.0.1" in unit
    assert "Environment=SIEM_DEBUG=false" in unit
    assert "ExecStartPre=/home/jaden/siem-security-dashboard/scripts/validate_backend_runtime_env.sh" in unit
    assert "/home/jaden/siem-security-dashboard/venv/bin/gunicorn" in unit
    assert "--worker-class sync" in unit
    assert '--workers "${SIEM_GUNICORN_WORKERS:-2}"' in unit
    assert '--bind "${SIEM_BIND_HOST:-127.0.0.1}:${SIEM_PORT:-5051}"' in unit
    assert '--timeout "${SIEM_GUNICORN_TIMEOUT:-120}"' in unit
    assert '--graceful-timeout "${SIEM_GUNICORN_GRACEFUL_TIMEOUT:-30}"' in unit
    assert "--access-logfile -" in unit
    assert "--error-logfile -" in unit
    assert "--capture-output" in unit
    assert "siem_backend:app" in unit
    assert "ExecReload=/bin/kill -HUP $MAINPID" in unit
    assert "Restart=on-failure" in unit
    assert "KillSignal=SIGTERM" in unit
    assert "StandardOutput=journal" in unit
    assert "StandardError=journal" in unit


def test_backend_systemd_unit_does_not_start_flask_development_server():
    unit = read(UNIT_PATH)

    assert "python3 /home/jaden/siem-security-dashboard/siem_backend.py" not in unit
    assert "python /home/jaden/siem-security-dashboard/siem_backend.py" not in unit
    assert "flask run" not in unit
    assert "app.run" not in unit


def validator_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    fake_root = tmp_path / "repo"
    gunicorn = fake_root / "venv" / "bin" / "gunicorn"
    gunicorn.parent.mkdir(parents=True)
    gunicorn.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gunicorn.chmod(0o755)
    env = {
        **os.environ,
        "SIEM_BACKEND_ROOT": str(fake_root),
        "SIEM_DEBUG": "false",
        "SIEM_BIND_HOST": "127.0.0.1",
        "SIEM_PORT": "5051",
        "SIEM_SECRET_KEY": "present",
        "SIEM_ADMIN_USERNAME": "admin",
        "SIEM_ADMIN_PASSWORD": "present",
        "SIEM_DB_HOST": "127.0.0.1",
        "SIEM_DB_NAME": "siem",
        "SIEM_DB_USER": "siem",
        "SIEM_DB_PASSWORD": "present",
    }
    env.update(overrides)
    return env


def run_validator(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(VALIDATOR_PATH)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_runtime_validator_accepts_safe_production_environment(tmp_path):
    result = run_validator(validator_env(tmp_path))

    assert result.returncode == 0
    assert "debug=false" in result.stdout
    assert "bind=127.0.0.1" in result.stdout
    assert "present" not in result.stdout


def test_runtime_validator_rejects_debug_true(tmp_path):
    result = run_validator(validator_env(tmp_path, SIEM_DEBUG="true"))

    assert result.returncode != 0
    assert "SIEM_DEBUG=false" in result.stderr
    assert "present" not in result.stderr


def test_runtime_validator_rejects_public_bind(tmp_path):
    result = run_validator(validator_env(tmp_path, SIEM_BIND_HOST="0.0.0.0"))

    assert result.returncode != 0
    assert "SIEM_BIND_HOST=127.0.0.1" in result.stderr


def test_runtime_validator_requires_secret_admin_and_database_without_leaking_values(tmp_path):
    env = validator_env(tmp_path)
    env.pop("SIEM_SECRET_KEY")
    env.pop("SECRET_KEY", None)
    env.pop("SIEM_DB_PASSWORD")
    result = run_validator(env)

    assert result.returncode != 0
    assert "Missing SIEM_SECRET_KEY or SECRET_KEY" in result.stderr
    assert "present" not in result.stderr


def test_install_helper_supports_dry_run_start_reload_and_rollback():
    installer = read(INSTALLER_PATH)

    assert "--dry-run" in installer
    assert "--enable" in installer
    assert "--start" in installer
    assert "--reload" in installer
    assert "--rollback" in installer
    assert "sudo cp \"$UNIT_SOURCE\" \"$UNIT_DEST\"" in installer
    assert "sudo systemctl daemon-reload" in installer
    assert "sudo systemctl restart \"$SERVICE_NAME\"" in installer
    assert "sudo systemctl reload \"$SERVICE_NAME\"" in installer
    assert "sudo rm -f \"$UNIT_DEST\"" in installer
    assert "sudo systemctl cat \"$SERVICE_NAME\" --no-pager" in installer
    assert "venv/bin/gunicorn" in installer
    assert "siem_backend:app" in installer
    assert "python[0-9. ]+siem_backend\\.py|flask run|app\\.run" in installer


def test_install_helper_does_not_modify_runtime_inputs_or_deploy():
    installer = read(INSTALLER_PATH)

    assert "This helper never edits .env" in installer
    assert "git fetch" not in installer
    assert "git reset" not in installer
    assert "npm run build" not in installer
    assert "rsync" not in installer
    assert "systemctl restart nginx" not in installer
    assert "systemctl reload nginx" not in installer
