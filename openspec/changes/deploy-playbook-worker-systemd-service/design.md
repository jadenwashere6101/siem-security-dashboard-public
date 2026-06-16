## Context

The SOAR playbook worker daemon implementation already exists in `scripts/soar_playbook_worker_daemon.py` and `engines/soar_playbook_worker.py`. The VM currently has only `siem-backend.service` installed and running; there is no `soar-playbook-worker.service` unit in `/etc/systemd/system`, no enabled unit, and no active daemon process.

The existing runbook documents a future systemd unit design, but the repo does not yet own an installable service file or operator checklist. This change creates the deployment contract only. It must not change execution semantics, approval gates, schema, APIs, integration adapter behavior, or backend deploy behavior.

## Goals / Non-Goals

**Goals:**
- Add a repo-owned systemd unit for `soar-playbook-worker.service`.
- Define an explicit operator-controlled install/update workflow.
- Define rollback and verification steps.
- Ensure the service pins simulation-safe environment variables even if `.env` changes.
- Use the VM project runtime: user `jaden`, group `jaden`, `/home/jaden/siem-security-dashboard`, `.env`, project virtualenv Python, and the existing daemon entrypoint.
- Keep backend deploy and worker service management separate initially.

**Non-Goals:**
- No changes to `scripts/soar_playbook_worker_daemon.py` or `engines/soar_playbook_worker.py`.
- No changes to playbook execution, stale recovery, approval, queue, or SOAR lifecycle semantics.
- No real firewall, Slack, Teams, email, webhook, PagerDuty, or other real adapter enablement.
- No schema changes.
- No backend API changes.
- No automatic worker restart/start from `scripts/deploy_backend_vm.sh`.
- No service installation, enablement, or start as part of this spec-only phase.

## Decisions

### Service identity

Use `soar-playbook-worker.service`.

Rationale: the name is short, matches the daemon role, and matches the existing runbook commands. Alternative names such as `siem-soar-playbook-worker.service` are more verbose and do not add operational clarity.

### Runtime contract

The unit should run as:
- `User=jaden`
- `Group=jaden`
- `WorkingDirectory=/home/jaden/siem-security-dashboard`
- `EnvironmentFile=/home/jaden/siem-security-dashboard/.env`
- `ExecStart=/home/jaden/siem-security-dashboard/venv/bin/python3 scripts/soar_playbook_worker_daemon.py ...`

Rationale: this mirrors the installed backend VM path and avoids depending on a system Python package environment. The command should reference the script relative to `WorkingDirectory` so repo layout stays readable.

### Safety pins

The unit must explicitly set:
- `INTEGRATION_MODE=simulation`
- `SOAR_EXECUTION_MODE=simulation`
- `SOAR_REAL_SLACK_ENABLED=false`
- `SOAR_REAL_TEAMS_ENABLED=false`
- `SOAR_REAL_EMAIL_ENABLED=false`
- `SOAR_REAL_WEBHOOK_ENABLED=false`
- `SOAR_REAL_FIREWALL_ENABLED=false`

Rationale: `.env` is shared operational configuration and may evolve. The worker service must remain simulation-safe unless a separate approved change intentionally changes real-adapter policy. Unit-level pins override accidental `.env` drift for this daemon.

### Restart and shutdown

Use:
- `Restart=on-failure`
- `RestartSec=15`
- `KillSignal=SIGTERM`
- `TimeoutStopSec=60`
- `StandardOutput=journal`
- `StandardError=journal`

Rationale: the daemon already handles SIGTERM/SIGINT and logs structured lifecycle markers. `Restart=on-failure` recovers process crashes without hiding operator-controlled stop/disable actions.

### Install workflow remains operator-controlled

Initial deployment should require explicit VM commands or a dedicated helper script. It must not be folded into `scripts/deploy_backend_vm.sh`.

Rationale: backend deploys currently apply migrations and restart the Flask API. Coupling them to daemon start/restart would make a routine API deploy also trigger continuous playbook processing. Deferring coupling keeps rollout safer and easier to reason about.

### Helper script optional

Implementation may add either documentation-only install commands or a small helper script that copies the unit and runs `systemctl daemon-reload`. If a helper is added, it must not automatically start the worker unless the operator passes an explicit start flag.

## Risks / Trade-offs

- Continuous worker starts processing eligible playbook executions unexpectedly -> require explicit install/start commands and pin simulation mode.
- `.env` contains real integration flags -> service unit safety pins override the real-adapter flags for this worker.
- Unit gets out of sync with repo paths -> verification includes `systemctl cat`, `status`, `is-enabled`, and `journalctl`.
- Crash loop hides failures -> `Restart=on-failure` plus journal verification and metrics checks expose loop errors.
- Backend deploy drift -> intentionally leave `deploy_backend_vm.sh` unchanged during the first service rollout.

## Migration Plan

1. Add repo-owned systemd unit template/file.
2. Update the runbook with install/update, status, journal, and rollback commands.
3. Optionally add a helper script for operator-controlled install/update, without automatic start.
4. Validate Python syntax and worker tests locally.
5. After commit and VM sync, operator copies or installs the service file into `/etc/systemd/system/`.
6. Operator runs `systemctl daemon-reload`, `enable`, `start`, `status`, and journal checks.
7. Rollback by stopping, disabling, removing the unit file, and reloading systemd.

## Open Questions

- Should the implementation be documentation-only plus a unit file, or include a helper script for safer repeatable install/update?
- Should service start remain fully manual, or should a helper support an explicit `--start` flag?
- Should future work add heartbeat persistence so `/metrics/playbook-worker` can report live daemon health instead of DB-derived execution state only?
