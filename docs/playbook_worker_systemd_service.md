# SOAR Playbook Worker systemd Service

Operator-controlled install, verification, and rollback for `soar-playbook-worker.service`.

This document defines deployment artifacts and VM commands only. Repository checkout
does not install, enable, or start the worker. `scripts/deploy_backend_vm.sh` does
not manage this service during the initial rollout.

For daemon behavior, simulation guards, and foreground validation, see
[soar_playbook_worker_daemon_runbook.md](soar_playbook_worker_daemon_runbook.md).

## Repo-Owned Unit File

Source unit (do not edit `/etc/systemd/system/` directly; copy from the repo):

```text
deploy/systemd/soar-playbook-worker.service
```

Installed path on the VM:

```text
/etc/systemd/system/soar-playbook-worker.service
```

## Safety Guardrails

The unit pins simulation-safe environment variables that override `.env` drift:

- `INTEGRATION_MODE=simulation`
- `SOAR_EXECUTION_MODE=simulation`
- `SOAR_REAL_SLACK_ENABLED=false`
- `SOAR_REAL_TEAMS_ENABLED=false`
- `SOAR_REAL_EMAIL_ENABLED=false`
- `SOAR_REAL_WEBHOOK_ENABLED=false`
- `SOAR_REAL_FIREWALL_ENABLED=false`

The worker runs as `jaden:jaden`, loads `/home/jaden/siem-security-dashboard/.env`,
and uses the project virtualenv Python. It does not start response-action workers
or enable real remediation adapters.

## Preflight Checks

Run on the VM from `/home/jaden/siem-security-dashboard` before install or start.

Confirm repo sync and unit source exists:

```bash
test -f deploy/systemd/soar-playbook-worker.service
test -f scripts/soar_playbook_worker_daemon.py
test -x venv/bin/python3
```

Confirm `.env` database settings (do not print passwords):

```bash
grep -E '^(SIEM_DB_|DB_)' .env | sed 's/=.*$/=***REDACTED***/'
```

Confirm simulation guards in the active shell (unit pins these at runtime):

```bash
env | grep -E '^(INTEGRATION_MODE|SOAR_EXECUTION_MODE|SOAR_REAL_.*_ENABLED)='
```

Confirm database connectivity:

```bash
export DATABASE_URL="postgresql://${SIEM_DB_USER}:${SIEM_DB_PASSWORD}@${SIEM_DB_HOST}:5432/${SIEM_DB_NAME}"
psql "$DATABASE_URL" -c "SELECT current_database(), current_user;"
```

Check playbook execution queue state:

```bash
psql "$DATABASE_URL" -c "
SELECT status, count(*)
FROM playbook_executions
GROUP BY status
ORDER BY status;"
```

Optional zero-loop smoke test (no DB work):

```bash
venv/bin/python3 scripts/soar_playbook_worker_daemon.py --max-loops 0 --log-level INFO
```

Confirm no conflicting worker process is already running:

```bash
ps -ef | grep 'soar_playbook_worker_daemon.py' | grep -v grep
```

## Install and Update

Manual install (recommended for first rollout):

```bash
cd /home/jaden/siem-security-dashboard
sudo cp deploy/systemd/soar-playbook-worker.service /etc/systemd/system/soar-playbook-worker.service
sudo systemctl daemon-reload
```

Optional helper (prints commands with `--dry-run`; does not start unless `--start`):

```bash
scripts/install_soar_playbook_worker_service.sh --dry-run
scripts/install_soar_playbook_worker_service.sh
```

Enable and start are explicit operator actions after install:

```bash
sudo systemctl enable soar-playbook-worker.service
sudo systemctl start soar-playbook-worker.service
```

Or via helper:

```bash
scripts/install_soar_playbook_worker_service.sh --enable --start
```

Update after a repo sync:

```bash
sudo cp deploy/systemd/soar-playbook-worker.service /etc/systemd/system/soar-playbook-worker.service
sudo systemctl daemon-reload
sudo systemctl restart soar-playbook-worker.service
```

## Status and Journal Verification

```bash
sudo systemctl status soar-playbook-worker.service --no-pager
sudo systemctl is-enabled soar-playbook-worker.service
sudo systemctl is-active soar-playbook-worker.service
sudo systemctl cat soar-playbook-worker.service
```

Recent logs:

```bash
journalctl -u soar-playbook-worker.service -n 100 --no-pager
journalctl -u soar-playbook-worker.service -f
```

Useful filters:

```bash
journalctl -u soar-playbook-worker.service --since "15 minutes ago" --no-pager | grep 'soar_playbook_worker_start'
journalctl -u soar-playbook-worker.service --since "15 minutes ago" --no-pager | grep 'soar_playbook_worker_loop_error'
```

Expected structured markers:

- `soar_playbook_worker_start`
- `soar_playbook_worker_loop`
- `soar_playbook_worker_shutdown`

Stop immediately if logs suggest real adapter calls, secret leakage, or approval-gated
recovery.

## Metrics Verification

When the backend is running, check the metrics endpoint (requires analyst or
super_admin session):

```bash
curl -sS -b cookies.txt http://127.0.0.1:5051/metrics/playbook-worker
```

Expected:

- Aggregate execution counts only.
- `daemon_health.status` may be `unknown` until heartbeat persistence is added.
- No DB URLs, passwords, webhook URLs, tokens, or raw error secrets.

Cross-check Worker Operations in the SOAR Metrics UI against direct database counts.

## Rollback

Stop and disable the service:

```bash
sudo systemctl stop soar-playbook-worker.service
sudo systemctl disable soar-playbook-worker.service
```

Remove the unit and reload systemd:

```bash
sudo rm -f /etc/systemd/system/soar-playbook-worker.service
sudo systemctl daemon-reload
sudo systemctl reset-failed soar-playbook-worker.service 2>/dev/null || true
```

Verify inactive or absent:

```bash
sudo systemctl status soar-playbook-worker.service --no-pager || true
sudo systemctl is-enabled soar-playbook-worker.service 2>/dev/null || echo "not installed"
ps -ef | grep 'soar_playbook_worker_daemon.py' | grep -v grep
```

Optional helper rollback (dry-run first):

```bash
scripts/install_soar_playbook_worker_service.sh --rollback --dry-run
scripts/install_soar_playbook_worker_service.sh --rollback
```

Manual executor fallback (simulation only, operator-controlled window):

```bash
venv/bin/python3 scripts/run_playbook_executor_once.py --limit 10
```

## Backend Deploy Decoupling

`scripts/deploy_backend_vm.sh` applies schema migrations and restarts
`siem-backend.service` only. It does not install, enable, start, stop, restart, or
reload `soar-playbook-worker.service`. A routine backend deploy does not implicitly
start continuous playbook processing.

## Local Verification (Before VM Install)

From the repository root on a dev machine:

```bash
python3 -m py_compile scripts/soar_playbook_worker_daemon.py engines/soar_playbook_worker.py
python3 -m pytest tests/test_soar_playbook_worker.py tests/test_playbook_execution_leases.py -v
```
