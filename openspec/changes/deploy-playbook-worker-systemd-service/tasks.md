## 1. Service Unit Artifact

- [x] 1.1 Add a repo-owned systemd unit file for `soar-playbook-worker.service`.
- [x] 1.2 Configure the unit with `User=jaden`, `Group=jaden`, `WorkingDirectory=/home/jaden/siem-security-dashboard`, and `EnvironmentFile=/home/jaden/siem-security-dashboard/.env`.
- [x] 1.3 Configure `ExecStart` to use `/home/jaden/siem-security-dashboard/venv/bin/python3 scripts/soar_playbook_worker_daemon.py` with bounded daemon arguments.
- [x] 1.4 Pin simulation-safe environment variables in the unit: `INTEGRATION_MODE=simulation`, `SOAR_EXECUTION_MODE=simulation`, and all `SOAR_REAL_*_ENABLED=false` flags required by the spec.
- [x] 1.5 Configure restart, shutdown, and logging directives: `Restart=on-failure`, `RestartSec=15`, `KillSignal=SIGTERM`, `TimeoutStopSec=60`, and journal output.

## 2. Operator Install and Rollback Documentation

- [x] 2.1 Update the SOAR playbook worker daemon runbook with the final repo-owned service file path.
- [x] 2.2 Document install/update commands to copy the unit to `/etc/systemd/system/soar-playbook-worker.service`, run `systemctl daemon-reload`, enable, start, check status, and inspect journal logs.
- [x] 2.3 Document rollback commands to stop, disable, remove the unit file, run `systemctl daemon-reload`, and verify the service is inactive or absent.
- [x] 2.4 Document that service install/start remains an explicit operator action and must not happen during ordinary repository checkout.
- [x] 2.5 Document that `scripts/deploy_backend_vm.sh` remains decoupled from worker service install/start/restart for the initial rollout.

## 3. Optional Helper Script

- [x] 3.1 Decide whether to add an operator helper script for service install/update or keep implementation documentation-only.
- [x] 3.2 If a helper script is added, make install/update explicit and avoid automatic service start unless an explicit start flag is provided.
- [x] 3.3 If a helper script is added, include dry-run or command-print behavior so operators can review privileged actions before running them.

## 4. Safety and Non-Regression Checks

- [x] 4.1 Confirm no SOAR worker logic files are modified.
- [x] 4.2 Confirm no playbook execution semantics, approval gates, protected-target behavior, or integration adapter behavior changes.
- [x] 4.3 Confirm no backend API, schema, mutation endpoint, frontend, or deploy-backend coupling changes are introduced.
- [x] 4.4 Confirm service safety pins preserve simulation mode and do not enable real firewall, Slack, Teams, email, or webhook execution.

## 5. Verification

- [x] 5.1 Run `python3 -m py_compile scripts/soar_playbook_worker_daemon.py engines/soar_playbook_worker.py`.
- [x] 5.2 Run focused worker tests, including `python3 -m pytest tests/test_soar_playbook_worker.py tests/test_playbook_execution_leases.py -v`.
- [x] 5.3 Validate the OpenSpec change with `openspec validate deploy-playbook-worker-systemd-service --strict`.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Document VM post-commit verification commands: `systemctl status`, `systemctl is-enabled`, `systemctl is-active`, `journalctl`, and `/metrics/playbook-worker` when available.
- [x] 5.6 Confirm no service was installed, enabled, started, stopped, or restarted during implementation.
