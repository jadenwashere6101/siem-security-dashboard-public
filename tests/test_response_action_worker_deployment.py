from pathlib import Path
import os
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_response_action_worker_service_is_environment_governed():
    service = (REPO_ROOT / "deploy/systemd/soar-response-action-worker.service").read_text()

    assert "Description=SOAR Response Action Queue Worker" in service
    assert "Type=oneshot" in service
    assert "EnvironmentFile=/home/jaden/siem-security-dashboard/.env" in service
    assert "Environment=SOAR_RUNNER_BATCH_SIZE=10" in service
    assert "Environment=SOAR_RECOVER_STALE_RUNNING=true" in service
    assert "scripts/run_response_action_worker_service.sh --json" in service
    assert "soar_playbook_worker_daemon.py" not in service
    assert "Environment=SOAR_REAL_FIREWALL_ENABLED=false" not in service


def test_response_action_worker_timer_is_bounded_and_distinct():
    timer = (REPO_ROOT / "deploy/systemd/soar-response-action-worker.timer").read_text()

    assert "Unit=soar-response-action-worker.service" in timer
    assert "OnUnitActiveSec=5min" in timer
    assert "RandomizedDelaySec=30s" in timer
    assert "soar-playbook-worker" not in timer


def test_response_action_worker_wrapper_hides_database_url_and_uses_runner():
    wrapper = (REPO_ROOT / "scripts/run_response_action_worker_service.sh").read_text()

    assert "export DATABASE_URL=" in wrapper
    assert "SOAR_RECOVER_STALE_RUNNING" in wrapper
    assert "SOAR_STALE_RUNNING_AFTER_SECONDS" in wrapper
    assert "exec venv/bin/python scripts/soar_worker_run.py" in wrapper
    assert ". ./.env" not in wrapper
    assert "printf \"$DATABASE_URL\"" not in wrapper
    assert "echo \"$DATABASE_URL\"" not in wrapper


def test_response_action_worker_install_helper_rolls_back_timer_and_service():
    helper = (REPO_ROOT / "scripts/install_response_action_worker_service.sh").read_text()

    assert "soar-response-action-worker.service" in helper
    assert "soar-response-action-worker.timer" in helper
    assert "systemctl stop \"$TIMER_NAME\"" in helper
    assert "systemctl disable \"$TIMER_NAME\"" in helper
    assert "systemctl stop \"$SERVICE_NAME\"" in helper
    assert "deploy/systemd/${SERVICE_NAME}" in helper
    assert 'systemctl restart "$TIMER_NAME"' in helper
    assert 'systemctl cat "$SERVICE_NAME" "$TIMER_NAME"' in helper


def test_backend_deploy_installs_reloads_restarts_and_verifies_workers():
    deploy = (REPO_ROOT / "scripts/deploy_backend_vm.sh").read_text()
    assert "install_and_restart_worker_units" in deploy
    assert "install_soar_playbook_worker_service.sh --enable --start" in deploy
    assert "install_response_action_worker_service.sh --enable --start" in deploy
    assert "systemctl cat" in (REPO_ROOT / "scripts/install_soar_playbook_worker_service.sh").read_text()


def test_response_worker_wrapper_treats_secret_values_as_data(tmp_path):
    wrapper = REPO_ROOT / "scripts/run_response_action_worker_service.sh"
    work = tmp_path / "worker"
    (work / "scripts").mkdir(parents=True)
    (work / "venv" / "bin").mkdir(parents=True)
    (work / "scripts" / "soar_worker_run.py").write_text("# placeholder\n")
    fake_python = work / "venv" / "bin" / "python"
    fake_python.write_text("#!/bin/sh\nprintf '%s' \"$SMTP_PASSWORD\"\n")
    fake_python.chmod(0o755)
    secret = "quote' space $dollar #hash ; touch SHOULD_NOT_EXIST"
    env = os.environ.copy()
    env.update({"DATABASE_URL": "postgresql://local/test", "SMTP_PASSWORD": secret})

    result = subprocess.run(
        [str(wrapper), "--json"], cwd=work, env=env, text=True, capture_output=True, check=True
    )

    assert result.stdout == secret
    assert not (work / "SHOULD_NOT_EXIST").exists()
