#!/usr/bin/env python3
"""Local artifact checks for pfSense deployment/runtime readiness.

This helper is intentionally non-mutating. It validates that the repo contains
the operator-controlled deployment artifacts and documentation required before
future runtime deployment, but it does not restart services, open ports, modify
Azure NSG rules, contact pfSense, or send production traffic.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK_PATH = REPO_ROOT / "docs" / "pfsense_deployment_runtime_readiness.md"
LISTENER_HELPER_PATH = REPO_ROOT / "scripts" / "install_pfsense_syslog_listener_service.sh"
PLAYBOOK_HELPER_PATH = REPO_ROOT / "scripts" / "install_soar_playbook_worker_service.sh"
RESPONSE_HELPER_PATH = REPO_ROOT / "scripts" / "install_response_action_worker_service.sh"
BACKEND_DEPLOY_PATH = REPO_ROOT / "scripts" / "deploy_backend_vm.sh"
LISTENER_UNIT_PATH = REPO_ROOT / "deploy" / "systemd" / "pfsense-syslog-listener.service"

FORBIDDEN_LIVE_ACTION_TOKENS = (
    ("az", "network", "nsg", "rule", "create"),
    ("az", "network", "nsg", "rule", "update"),
    ("ufw", "allow"),
    ("iptables", "-A"),
    ("systemctl", "restart"),
    ("systemctl", "start", "pfsense-syslog-listener.service"),
    ("systemctl", "enable", "pfsense-syslog-listener.service"),
)

REQUIRED_ENV_VARS = (
    "PFSENSE_LISTENER_BIND_HOST",
    "PFSENSE_LISTENER_PORT",
    "PFSENSE_ALLOWED_SOURCE_IPS",
    "PFSENSE_BACKEND_URL",
    "PFSENSE_INGEST_API_KEY",
    "PFSENSE_API_KEY_HEADER",
    "PFSENSE_MAX_PACKET_BYTES",
    "PFSENSE_GLOBAL_RATE_LIMIT",
    "PFSENSE_PER_SOURCE_RATE_LIMIT",
    "PFSENSE_RATE_LIMIT_WINDOW_SECONDS",
    "PFSENSE_BACKEND_TIMEOUT_SECONDS",
    "PFSENSE_RECV_TIMEOUT_SECONDS",
    "PFSENSE_ENVIRONMENT",
    "PFSENSE_SYSLOG_TIMEZONE",
)

RUNBOOK_REQUIRED_PHRASES = (
    "Mac repo is the source of truth",
    "VM repo is deployment/runtime only",
    "No Azure NSG rule is created by this runbook",
    "No VM firewall rule is created by this runbook",
    "No live pfSense production traffic is used for validation",
    "backend first, then workers, then listener",
    "Rollback Plan",
    "Runtime Validation",
    "Production Readiness",
    "pfSense Handoff",
    "Deployment Sign-off",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_file_exists(path: Path, label: str) -> CheckResult:
    return CheckResult(label, path.is_file(), str(path.relative_to(REPO_ROOT)))


def check_helper_is_operator_controlled(path: Path, label: str) -> CheckResult:
    if not path.is_file():
        return CheckResult(label, False, f"missing {path.relative_to(REPO_ROOT)}")
    text = read_text(path)
    required = ("--dry-run", "--enable", "--start", "--rollback", "systemctl daemon-reload")
    missing = [item for item in required if item not in text]
    default_safe = "not enabled or started unless" in text or "not started unless" in text
    if missing or not default_safe:
        detail = "missing " + ", ".join(missing) if missing else "missing default no-start wording"
        return CheckResult(label, False, detail)
    return CheckResult(label, True, f"{path.relative_to(REPO_ROOT)} is explicit-flag controlled")


def check_no_live_actions_in_readiness_script() -> CheckResult:
    text = read_text(Path(__file__))
    found = [" ".join(tokens) for tokens in FORBIDDEN_LIVE_ACTION_TOKENS if " ".join(tokens) in text]
    if found:
        return CheckResult("readiness helper avoids live actions", False, ", ".join(found))
    return CheckResult("readiness helper avoids live actions", True, "non-mutating local checks only")


def check_listener_unit_env_inventory() -> CheckResult:
    if not LISTENER_UNIT_PATH.is_file():
        return CheckResult("listener unit env inventory", False, "missing listener unit")
    text = read_text(LISTENER_UNIT_PATH)
    missing = [name for name in REQUIRED_ENV_VARS if name not in text]
    if missing:
        return CheckResult("listener unit env inventory", False, "missing " + ", ".join(missing))
    return CheckResult("listener unit env inventory", True, "listener env vars documented in unit")


def check_runbook_content() -> CheckResult:
    if not RUNBOOK_PATH.is_file():
        return CheckResult("readiness runbook content", False, "missing runbook")
    text = read_text(RUNBOOK_PATH)
    missing = [phrase for phrase in RUNBOOK_REQUIRED_PHRASES if phrase not in text]
    missing_env = [name for name in REQUIRED_ENV_VARS if name not in text]
    if missing or missing_env:
        detail = []
        if missing:
            detail.append("missing phrases: " + ", ".join(missing))
        if missing_env:
            detail.append("missing env vars: " + ", ".join(missing_env))
        return CheckResult("readiness runbook content", False, "; ".join(detail))
    return CheckResult("readiness runbook content", True, str(RUNBOOK_PATH.relative_to(REPO_ROOT)))


def check_backend_deploy_sequence() -> CheckResult:
    if not BACKEND_DEPLOY_PATH.is_file():
        return CheckResult("backend migration/restart helper", False, "missing deploy_backend_vm.sh")
    text = read_text(BACKEND_DEPLOY_PATH)
    try:
        main_body = text.split("main() {", 1)[1].split("\n}\n\nmain", 1)[0]
        dry_run_idx = main_body.index("run_migration_dry_run")
        apply_idx = main_body.index("run_migration_apply")
        restart_idx = main_body.index("restart_backend_service")
        health_idx = main_body.index("check_health_endpoint")
    except (IndexError, ValueError) as exc:
        return CheckResult("backend migration/restart helper", False, f"unable to verify sequence: {exc}")
    ok = dry_run_idx < apply_idx < restart_idx < health_idx
    detail = "dry-run migrations before apply before restart before health"
    return CheckResult("backend migration/restart helper", ok, detail)


def check_git_clean() -> CheckResult:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return CheckResult("local git clean", False, proc.stderr.strip() or "git status failed")
    output = proc.stdout.strip()
    return CheckResult("local git clean", not output, "clean" if not output else output)


def collect_checks(require_clean_git: bool) -> list[CheckResult]:
    checks = [
        check_file_exists(RUNBOOK_PATH, "readiness runbook exists"),
        check_file_exists(LISTENER_UNIT_PATH, "listener systemd unit exists"),
        check_file_exists(BACKEND_DEPLOY_PATH, "backend deploy helper exists"),
        check_helper_is_operator_controlled(LISTENER_HELPER_PATH, "listener install helper"),
        check_helper_is_operator_controlled(PLAYBOOK_HELPER_PATH, "playbook worker install helper"),
        check_helper_is_operator_controlled(RESPONSE_HELPER_PATH, "response worker install helper"),
        check_listener_unit_env_inventory(),
        check_runbook_content(),
        check_backend_deploy_sequence(),
        check_no_live_actions_in_readiness_script(),
    ]
    if require_clean_git:
        checks.append(check_git_clean())
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate pfSense deployment/runtime readiness artifacts without side effects."
    )
    parser.add_argument(
        "--require-clean-git",
        action="store_true",
        help="Also require the local working tree to be clean. Intended for future deployment use.",
    )
    args = parser.parse_args(argv)

    checks = collect_checks(require_clean_git=args.require_clean_git)
    for check in checks:
        status = "PASS" if check.ok else "FAIL"
        print(f"{status} {check.name}: {check.detail}")

    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
