from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_response_action_worker_service_is_simulation_safe():
    service = (REPO_ROOT / "deploy/systemd/soar-response-action-worker.service").read_text()

    assert "Description=SOAR Response Action Queue Worker" in service
    assert "Type=oneshot" in service
    assert "Environment=SOAR_EXECUTION_MODE=simulation" in service
    assert "Environment=SOAR_RUNNER_BATCH_SIZE=10" in service
    assert "Environment=SOAR_RECOVER_STALE_RUNNING=true" in service
    assert "scripts/run_response_action_worker_service.sh --json" in service
    assert "soar_playbook_worker_daemon.py" not in service
    assert "SOAR_REAL_FIREWALL_ENABLED=false" in service


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
