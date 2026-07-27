from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_soc_briefing_worker_service_is_oneshot_and_read_only_foundation():
    service = (REPO_ROOT / "deploy/systemd/soc-briefing-worker.service").read_text()

    assert "Description=Scheduled SOC Briefing Runtime Worker" in service
    assert "Type=oneshot" in service
    assert "EnvironmentFile=/home/jaden/siem-security-dashboard/.env" in service
    assert "Environment=SOC_BRIEFING_BATCH_SIZE=5" in service
    assert "scripts/run_soc_briefing_worker_service.sh --json" in service
    assert "gunicorn" not in service
    assert "flask run" not in service
    assert "SLACK_WEBHOOK_URL" not in service
    assert "send_message" not in service


def test_soc_briefing_worker_timer_is_persistent_and_bounded():
    timer = (REPO_ROOT / "deploy/systemd/soc-briefing-worker.timer").read_text()

    assert "Unit=soc-briefing-worker.service" in timer
    assert "OnBootSec=2min" in timer
    assert "OnUnitActiveSec=5min" in timer
    assert "RandomizedDelaySec=30s" in timer
    assert "Persistent=true" in timer


def test_soc_briefing_worker_wrapper_hides_database_url_and_uses_runner():
    wrapper = (REPO_ROOT / "scripts/run_soc_briefing_worker_service.sh").read_text()

    assert "export DATABASE_URL=" in wrapper
    assert "SOC_BRIEFING_BATCH_SIZE" in wrapper
    assert "exec venv/bin/python scripts/soc_briefing_worker.py" in wrapper
    assert ". ./.env" not in wrapper
    assert "printf \"$DATABASE_URL\"" not in wrapper
    assert "echo \"$DATABASE_URL\"" not in wrapper


def test_soc_briefing_install_helper_rolls_back_timer_and_service():
    helper = (REPO_ROOT / "scripts/install_soc_briefing_worker_service.sh").read_text()

    assert "soc-briefing-worker.service" in helper
    assert "soc-briefing-worker.timer" in helper
    assert "systemctl stop \"$TIMER_NAME\"" in helper
    assert "systemctl disable \"$TIMER_NAME\"" in helper
    assert "systemctl stop \"$SERVICE_NAME\"" in helper
    assert "deploy/systemd/${SERVICE_NAME}" in helper
    assert 'systemctl restart "$TIMER_NAME"' in helper
    assert 'systemctl cat "$SERVICE_NAME" "$TIMER_NAME"' in helper


def test_backend_deploy_installs_soc_briefing_worker_units():
    deploy = (REPO_ROOT / "scripts/deploy_backend_vm.sh").read_text()

    assert "install_soc_briefing_worker_service.sh --enable --start" in deploy
