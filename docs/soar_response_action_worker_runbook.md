# SOAR Response Action Queue Worker Runbook

Last updated: 2026-07-06

This runbook covers the worker that processes `response_actions_queue` through
`scripts/soar_worker_run.py`. It is separate from
`soar-playbook-worker.service`, which processes `playbook_executions`.

## Safety Model

- Default mode is simulation: `SOAR_EXECUTION_MODE=simulation`.
- `block_ip` remains approval-gated.
- Firewall enforcement remains dry-run/tracking-only unless a future approved
  OpenSpec changes that boundary.
- The systemd service runs one bounded batch and exits.
- The timer invokes the one-shot service periodically.
- The service enables stale-running recovery with a 15-minute threshold so an
  interrupted one-shot run can return eligible `running` rows to the normal
  queue flow before the next bounded batch.
- Rollback disables scheduling; it does not delete queue rows, approval rows,
  response logs, or canonical outcome events.

## Status Inspection

Run from `/home/jaden/siem-security-dashboard` on the VM:

```bash
scripts/run_response_action_worker_service.sh --dry-run-info --json
```

Expected JSON shape:

```json
{
  "mode": "dry_run_info",
  "queue_counts": {
    "pending": 0,
    "running": 0,
    "awaiting_approval": 0,
    "failed": 0,
    "skipped": 0,
    "success": 0
  }
}
```

Direct SQL status check, if needed:

```bash
psql "$DATABASE_URL" -c "
SELECT action, status, count(*)
FROM response_actions_queue
GROUP BY action, status
ORDER BY count(*) DESC, action, status;"
```

## One-Time Backlog Drain

Preflight:

```bash
systemctl status soar-playbook-worker.service --no-pager
systemctl list-unit-files --no-pager | grep -E 'soar-response-action|soar-playbook'
systemctl list-timers --no-pager | grep soar-response-action || true
scripts/run_response_action_worker_service.sh --dry-run-info --json
```

Run one bounded simulation batch:

```bash
SOAR_EXECUTION_MODE=simulation SOAR_RUNNER_BATCH_SIZE=10 \
  scripts/run_response_action_worker_service.sh --json
```

If a previous runner was interrupted and left a queue row in `running`, recover
only stale rows through the runner rather than editing rows by hand:

```bash
SOAR_EXECUTION_MODE=simulation SOAR_RUNNER_BATCH_SIZE=10 \
  scripts/run_response_action_worker_service.sh \
  --json --recover-stale --stale-after-seconds 900 --stale-limit 50
```

Expected transitions:

- `monitor` and `flag_high_priority` actions may move to `success`.
- `block_ip` actions should move to `awaiting_approval` unless protected-target
  validation safely skips them.
- No path should create real firewall enforcement.

Stop after the first batch if any transition differs from those expectations.

## Install Service and Timer

Dry-run first:

```bash
scripts/install_response_action_worker_service.sh --dry-run
```

Install units without starting:

```bash
scripts/install_response_action_worker_service.sh
```

Enable and start the timer only after a sample batch behaves correctly:

```bash
scripts/install_response_action_worker_service.sh --enable --start
```

## Verify Timer

```bash
systemctl status soar-response-action-worker.timer --no-pager
systemctl status soar-response-action-worker.service --no-pager || true
systemctl list-timers --no-pager | grep soar-response-action
journalctl -u soar-response-action-worker.service -n 100 --no-pager
scripts/run_response_action_worker_service.sh --dry-run-info --json
```

The service should run a bounded batch and exit. The timer should remain active
if enabled.

After installing a fresh timer, run the one-shot service once if
`systemctl list-timers` shows no next trigger yet:

```bash
sudo systemctl start soar-response-action-worker.service
systemctl list-timers --all 'soar-response-action-worker.timer' --no-pager
```

## Stop Conditions

Stop or disable the timer immediately if any of these occur:

- `SOAR_EXECUTION_MODE` is not `simulation`.
- Logs show real firewall enforcement or real provider enforcement.
- Batch size is unbounded or unexpectedly high.
- Queue rows transition outside expected states.
- Repeated database connection failures occur.
- Secrets, database URLs, webhook URLs, or tokens appear in logs.

## Rollback

Stop and disable the timer:

```bash
sudo systemctl stop soar-response-action-worker.timer
sudo systemctl disable soar-response-action-worker.timer
sudo systemctl stop soar-response-action-worker.service 2>/dev/null || true
```

Remove units:

```bash
sudo rm -f /etc/systemd/system/soar-response-action-worker.service
sudo rm -f /etc/systemd/system/soar-response-action-worker.timer
sudo systemctl daemon-reload
sudo systemctl reset-failed soar-response-action-worker.service soar-response-action-worker.timer 2>/dev/null || true
```

Or use the helper:

```bash
scripts/install_response_action_worker_service.sh --rollback --dry-run
scripts/install_response_action_worker_service.sh --rollback
```

Rollback preserves data. It does not delete queue rows or approvals.

## Rollout Evidence: 2026-07-06

Before rollout, the VM had 57 pending response-action queue rows, 3 success
rows, and 1 failed row. Pending rows were 50 `block_ip`, 5 `monitor`, and 2
`flag_high_priority`. The oldest pending row was created on 2026-06-23 and the
newest on 2026-07-05. `soar-playbook-worker.service` was active, but no
response-action worker service, timer, or cron entry was installed.

During rollout:

- `scripts/run_response_action_worker_service.sh --dry-run-info --json`
  reported all expected status keys without mutating the queue.
- A bounded simulation batch recovered an interrupted `running` row and moved
  `block_ip` rows to `awaiting_approval`.
- The remaining pending backlog was drained with a bounded simulation batch.
- No real firewall enforcement was enabled. The only `blocked_ips` row observed
  was an inactive manual row created on 2026-04-28, before this rollout.

Final VM queue counts after drain:

```text
pending=0
running=0
awaiting_approval=50
failed=1
skipped=0
success=10
```

Final action/status counts:

```text
block_ip awaiting_approval=50
block_ip failed=1
flag_high_priority success=2
monitor success=8
```

The 50 remaining `block_ip` items require analyst approval or denial. They are
not worker defects and should not be auto-executed by this change.

Installed units:

```text
soar-response-action-worker.service: Result=success, ExecMainStatus=0
soar-response-action-worker.timer: enabled, active, next run scheduled
soar-playbook-worker.service: active and unchanged
```
