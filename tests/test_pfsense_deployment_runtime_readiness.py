from pathlib import Path

import scripts.pfsense_deployment_readiness_check as readiness


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "pfsense_deployment_runtime_readiness.md"
SCRIPT = REPO_ROOT / "scripts" / "pfsense_deployment_readiness_check.py"


def test_runbook_documents_scope_boundaries():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "Mac repo is the source of truth" in text
    assert "VM repo is deployment/runtime only" in text
    assert "No Azure NSG rule is created by this runbook" in text
    assert "No VM firewall rule is created by this runbook" in text
    assert "No live pfSense production traffic is used for validation" in text
    assert "does not implement or redesign the parser" in text


def test_runbook_documents_deployment_order_and_clean_git_gates():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "git status --short" in text
    assert "Never merge on a dirty VM" in text
    assert "backend first, then workers, then listener" in text
    assert "deploy_backend_vm.sh --dry-run-migrations" in text
    assert "deploy_backend_vm.sh --skip-restart" in text
    assert "ss -lunp | grep ':5514'" in text


def test_runbook_documents_required_listener_environment_variables():
    text = RUNBOOK.read_text(encoding="utf-8")

    for name in readiness.REQUIRED_ENV_VARS:
        assert name in text


def test_runbook_documents_runtime_validation_and_failure_paths():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "Runtime Validation" in text
    assert "synthetic/local packets only" in text
    assert "source=pfsense" in text
    assert "source_type=firewall" in text
    assert "malformed packet" in text
    assert "oversized packet" in text
    assert "unauthorized source IP" in text
    assert "rate-limited traffic" in text
    assert "backend 4xx" in text
    assert "backend 5xx" in text


def test_runbook_documents_readiness_signoff_rollback_and_handoff_gates():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "Production Readiness" in text
    assert "Rollback Plan" in text
    assert "Deployment Sign-off" in text
    assert "No uncle/pfSense handoff communication may be sent before this sign-off exists." in text
    assert "Status -> System Logs -> Settings" in text
    assert "<Azure VM public IP>:<confirmed listener UDP port>" in text


def test_readiness_helper_is_non_mutating_by_default():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "systemctl restart" not in text
    assert "az network nsg rule create" not in text
    assert "ufw allow" not in text
    assert "iptables -A" not in text
    assert "--require-clean-git" in text
    assert "non-mutating" in text


def test_readiness_helper_passes_artifact_checks_without_requiring_clean_git():
    results = readiness.collect_checks(require_clean_git=False)

    assert results
    assert all(result.ok for result in results), [result for result in results if not result.ok]


def test_readiness_helper_requires_operator_controlled_install_helpers():
    results = {
        result.name: result
        for result in readiness.collect_checks(require_clean_git=False)
    }

    assert results["listener install helper"].ok
    assert results["playbook worker install helper"].ok
    assert results["response worker install helper"].ok


def test_listener_install_helper_does_not_autostart_by_default():
    helper = (REPO_ROOT / "scripts" / "install_pfsense_syslog_listener_service.sh").read_text(
        encoding="utf-8"
    )

    assert "The service is not enabled or started unless you pass explicit flags." in helper
    assert "--enable" in helper
    assert "--start" in helper
    assert "--rollback" in helper


def test_listener_systemd_unit_documents_readiness_environment():
    unit = (REPO_ROOT / "deploy" / "systemd" / "pfsense-syslog-listener.service").read_text(
        encoding="utf-8"
    )

    for name in readiness.REQUIRED_ENV_VARS:
        assert name in unit
