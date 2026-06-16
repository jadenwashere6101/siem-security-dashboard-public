# SOAR Playbook Worker Daemon Runbook

Operational guidance for deploying and operating the daemonized SOAR playbook
worker in simulation mode.

This runbook documents safe commands and service design only. It does not install
or enable systemd, does not modify schema or code, and does not enable real
Slack, Teams, firewall, webhook, email, or other remediation integrations.

## Safety Boundaries

- Run in simulation mode unless a separate real-integration hardening change has
  been approved.
- Do not set real adapter enablement flags for this worker rollout.
- Do not run broad response-action workers as part of this playbook-worker
  rollout.
- Do not modify ingest, detection, or correlation services while validating the
  daemon.
- Start with one worker. Add a second worker only during an explicit
  concurrency-validation window.
- Stop immediately if queue counts, dead letters, or logs show unexpected real
  adapter calls.

Required simulation guards:

```bash
export INTEGRATION_MODE=simulation
export SOAR_EXECUTION_MODE=simulation
export SOAR_REAL_SLACK_ENABLED=false
export SOAR_REAL_TEAMS_ENABLED=false
export SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED=false
```

## Environment

The daemon uses `core/db.py`, which reads the PostgreSQL connection from
`SIEM_DB_*` or the legacy `DB_*` names.

Required:

```bash
export SIEM_DB_HOST=127.0.0.1
export SIEM_DB_NAME=siem_security
export SIEM_DB_USER=siem_user
export SIEM_DB_PASSWORD='REPLACE_WITH_VM_SECRET'
```

Optional worker tuning:

```bash
export SOAR_PLAYBOOK_LEASE_SECONDS=60
```

For operator `psql` checks, build `DATABASE_URL` from the same values instead of
assuming it already exists:

```bash
export DATABASE_URL="postgresql://${SIEM_DB_USER}:${SIEM_DB_PASSWORD}@${SIEM_DB_HOST}:5432/${SIEM_DB_NAME}"
```

Do not print or paste `DATABASE_URL` into tickets, chat, or logs.

## Manual Smoke and Test-Mode Commands

From the repo root:

```bash
cd ~/siem-security-dashboard
```

Zero-loop smoke test. This validates the Python entrypoint and config parsing
without connecting to the database or claiming work:

```bash
python3 scripts/soar_playbook_worker_daemon.py \
  --max-loops 0 \
  --log-level INFO
```

One-loop simulation validation. This may claim and process eligible pending
playbook executions, so run it only after confirming simulation guards and queue
contents:

```bash
python3 scripts/soar_playbook_worker_daemon.py \
  --max-loops 1 \
  --batch-size 1 \
  --poll-interval 0 \
  --idle-backoff 0 \
  --jitter 0 \
  --dry-run-recovery \
  --log-level INFO
```

Normal foreground daemon command for an operator-controlled validation window:

```bash
python3 scripts/soar_playbook_worker_daemon.py \
  --batch-size 10 \
  --poll-interval 5 \
  --idle-backoff 30 \
  --jitter 2 \
  --error-backoff 10 \
  --stale-recovery-interval 60 \
  --stale-limit 50 \
  --log-level INFO
```

Expected structured log markers:

- `soar_playbook_worker_start`
- `soar_playbook_worker_loop`
- `soar_playbook_worker_loop_error`
- `soar_playbook_worker_shutdown`

Logs must include counts and `worker_id`; they must not include DB passwords,
webhook URLs, tokens, or adapter credentials.

## Pre-Start Checks

Confirm simulation guards:

```bash
env | grep -E '^(INTEGRATION_MODE|SOAR_EXECUTION_MODE|SOAR_REAL_SLACK_ENABLED|SOAR_REAL_TEAMS_ENABLED|SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED)='
```

Confirm database connectivity:

```bash
psql "$DATABASE_URL" -c "SELECT current_database(), current_user;"
```

Check queue and stale state:

```bash
psql "$DATABASE_URL" -c "
SELECT status, count(*)
FROM playbook_executions
GROUP BY status
ORDER BY status;"
```

```bash
psql "$DATABASE_URL" -c "
SELECT count(*) AS stale_running
FROM playbook_executions
WHERE status = 'running'
  AND lease_expires_at IS NOT NULL
  AND lease_expires_at < NOW();"
```

Check recent dead letters:

```bash
psql "$DATABASE_URL" -c "
SELECT status, source_type, count(*)
FROM soar_dead_letters
GROUP BY status, source_type
ORDER BY status, source_type;"
```

## Systemd Unit

The repo owns an installable unit at `deploy/systemd/soar-playbook-worker.service`.
Install, enable, start, status, journal, metrics, and rollback steps are documented
in [playbook_worker_systemd_service.md](playbook_worker_systemd_service.md).

Do not install or start the service during ordinary repository checkout. Service
management remains an explicit operator action. `scripts/deploy_backend_vm.sh` does
not manage the worker service during the initial rollout.

Design notes:

- `SIGTERM` triggers graceful shutdown.
- `Restart=on-failure` avoids silent process loss but still exposes crash loops
  through journald and service status.
- The unit pins simulation guards even when `.env` contains other values.
- The unit does not start response-action workers.

## Start, Stop, Restart, and Status

Foreground validation:

```bash
python3 scripts/soar_playbook_worker_daemon.py --batch-size 10 --log-level INFO
```

Stop foreground validation with `Ctrl-C`. The worker should log
`soar_playbook_worker_shutdown`.

After operator install (see [playbook_worker_systemd_service.md](playbook_worker_systemd_service.md)):

```bash
sudo systemctl start soar-playbook-worker.service
sudo systemctl status soar-playbook-worker.service --no-pager
sudo systemctl restart soar-playbook-worker.service
sudo systemctl stop soar-playbook-worker.service
```

Do not run these systemd commands until the service file has been installed by an
explicit operator step.

## Log Inspection

Foreground validation logs appear in the terminal.

Systemd log commands (after install):

```bash
journalctl -u soar-playbook-worker.service -n 100 --no-pager
journalctl -u soar-playbook-worker.service -f
```

Useful filters:

```bash
journalctl -u soar-playbook-worker.service --since "15 minutes ago" --no-pager | grep 'soar_playbook_worker_loop'
journalctl -u soar-playbook-worker.service --since "15 minutes ago" --no-pager | grep 'soar_playbook_worker_loop_error'
```

Stop and investigate if logs contain adapter tokens, webhook URLs, DB passwords,
or real remediation output.

## SOAR Metrics Dashboard Verification

In the UI, open **SOAR Metrics** as `analyst` or `super_admin`.

Verify the **Worker Operations** section:

- Heartbeat is labeled `unknown` until heartbeat persistence is added.
- Pending, running, awaiting approval, stale running, and missing lease counts
  match the database checks.
- Recent failed execution and active dead-letter counts are visible.
- Recovery metrics change only after stale recovery processes eligible rows.
- The section says metrics are operational visibility only and does not indicate
  real remediation is active.

Viewer users must not see Worker Operations.

API check:

```bash
curl -sS -b cookies.txt http://127.0.0.1:5051/metrics/playbook-worker
```

Expected:

- Aggregate counts only.
- `daemon_health.status` may be `unknown`.
- No DB URL, password, webhook URL, token, payload, or raw error secret fields.

## Stale Recovery Validation

Use controlled simulation data only.

1. Capture stale counts before starting the worker:

   ```bash
   psql "$DATABASE_URL" -c "
   SELECT count(*) AS stale_running
   FROM playbook_executions
   WHERE status = 'running'
     AND lease_expires_at IS NOT NULL
     AND lease_expires_at < NOW();"
   ```

2. Run one loop with dry-run recovery:

   ```bash
   python3 scripts/soar_playbook_worker_daemon.py \
     --max-loops 1 \
     --batch-size 1 \
     --dry-run-recovery \
     --stale-recovery-interval 0 \
     --log-level INFO
   ```

3. Confirm dry-run recovery did not persist status changes.

4. During an approved validation window, run without `--dry-run-recovery` and
   confirm stale rows move through the existing recovery semantics.

Stop if `awaiting_approval` rows are recovered as stale. That state must remain
approval-gated.

## Concurrency Validation

Start with one worker. For multi-worker simulation validation, use two terminals
with the same simulation guards and small batch sizes:

```bash
python3 scripts/soar_playbook_worker_daemon.py --batch-size 1 --poll-interval 2 --idle-backoff 5 --log-level INFO
```

Expected:

- Each execution is claimed by one worker only.
- Second workers skip locked or already-owned rows cleanly.
- Terminal updates are guarded by lease owner.
- No duplicate pending retry execution is created.
- Dead-letter capture remains single-active for repeated failure of the same
  execution.

Database spot check:

```bash
psql "$DATABASE_URL" -c "
SELECT id, status, lease_owner, lease_acquired_at, lease_heartbeat_at, lease_expires_at
FROM playbook_executions
ORDER BY id DESC
LIMIT 20;"
```

## Rollback and Emergency Stop

Foreground worker:

- Press `Ctrl-C`.
- Confirm `soar_playbook_worker_shutdown` appears.
- Re-run queue and stale metrics checks.

Systemd worker rollback (see [playbook_worker_systemd_service.md](playbook_worker_systemd_service.md)):

```bash
sudo systemctl stop soar-playbook-worker.service
sudo systemctl disable soar-playbook-worker.service
sudo systemctl status soar-playbook-worker.service --no-pager
```

Manual executor fallback remains available:

```bash
python3 scripts/run_playbook_executor_once.py --limit 10
```

Use the manual path only in simulation mode and during an operator-controlled
window.

Emergency stop conditions:

- Any log suggests real Slack, Teams, webhook, email, firewall, or remediation
  execution.
- Dead-letter count rises unexpectedly.
- Queue failures repeat for the same execution after retry exhaustion.
- Stale recovery touches approval-gated executions.
- DB errors repeat across multiple loops.
- Dashboard metrics diverge from direct DB checks.
- Worker logs expose secrets.

Emergency response:

1. Stop all foreground worker terminals with `Ctrl-C`.
2. Stop the future systemd service if installed.
3. Confirm no worker process remains:

   ```bash
   ps -ef | grep 'soar_playbook_worker_daemon.py' | grep -v grep
   ```

4. Preserve logs and inspect dead letters before restarting anything.

## Firewall Real-Mode Safety Boundary

`SPEC-INTEG-005` intentionally keeps firewall behavior simulation/dry-run only. The
playbook-facing `FirewallSimulationAdapter` never performs live firewall calls, subprocess
execution, cloud security-group mutation, or `blocked_ips` writes. The lower-level
`LinuxFirewallDryRunAdapter` may build a command plan after protected-target validation, but
it returns that plan as dry-run evidence with `executed: false`.

This is a deliberate rollback and blast-radius control. A daemonized worker can process many
executions unattended; allowing live firewall mutation from this path would require stronger
operator controls than this spec grants. Any future firewall promotion must come from a
separate approved OpenSpec and must define, at minimum:

- Protected-target policy enforced before any command or API call.
- A dual approval gate for live remediation.
- Durable idempotency keys for each firewall action.
- A staging smoke test with explicit rollback evidence.
- No autonomous retries for live firewall mutation.
- Audit and dead-letter behavior that exposes no secrets or protected target details.

If `/integrations/status` is called with real-mode firewall env vars present, the firewall
adapter must still report simulation mode and `real_mode_available: false`. Treat any status
or log output implying live firewall availability as a stop condition.

## Stop Conditions Before Broader Rollout

Do not proceed from one-worker simulation to multi-worker simulation, or from
manual foreground operation to systemd, until:

- Simulation guards are confirmed in the active environment.
- SOAR Metrics Worker Operations matches DB-derived counts.
- Stale recovery behaves correctly for stale `running` rows and ignores
  `awaiting_approval`.
- Multi-worker tests show no duplicate execution.
- Logs show bounded loop behavior with no tight error spin.
- No real integration output is observed.
- Rollback to manual executor operation has been tested.
