# SOAR Execution Locking Validation

Manual staging checklist for SOAR playbook lease ownership, stale recovery, and durable resume.

This procedure is for an operator-controlled staging window only. It does not introduce a daemon or background scheduler, and it must not be used to send real notifications or run real remediation.

## Safety Preconditions

- Confirm runtime is simulation-only:
  - `INTEGRATION_MODE=simulation`
  - `SOAR_REAL_SLACK_ENABLED=false`
  - `SOAR_EXECUTION_MODE=simulation`
- Confirm `DATABASE_URL` points to the intended staging database. Do not print or paste the DSN.
- Confirm no real Slack, Teams, email, webhook, or remediation adapter credentials are enabled.
- Confirm the repo and database are at the expected deployed migration version.
- Confirm only one operator is running this checklist.
- Do not start a recurring worker, daemon, cron job, or scheduler.

## Baseline Read-Only Checks

Run a dry recovery scan:

```bash
python3 scripts/run_playbook_executor_once.py --recover-stale --dry-run-recovery --stale-limit 20
```

Expected:

- Output includes a worker id.
- Output includes `Dry run: True`.
- Output includes scanned, recovered, pending, failed, and skipped awaiting-approval counts.
- Output says no playbook steps were executed.
- No `playbook_executions` rows change status.

## Two-Worker Lease Contention Check

Use two shells with the same simulation-safe environment.

1. Create or identify one pending playbook execution with harmless simulated steps.
2. In shell A, run one batch:

   ```bash
   python3 scripts/run_playbook_executor_once.py --batch-size 1
   ```

3. In shell B, run one batch at nearly the same time:

   ```bash
   python3 scripts/run_playbook_executor_once.py --batch-size 1
   ```

Expected:

- Each output includes a distinct worker id.
- At most one worker claims the pending execution.
- Any skipped execution reports a visible skip reason.
- No duplicate notification delivery attempts are created for already completed notification steps.
- The final execution status is either `success`, `failed`, or `awaiting_approval` according to the playbook definition.

## Stale Recovery Dry Run

For an intentionally expired test lease, run:

```bash
python3 scripts/run_playbook_executor_once.py --recover-stale --dry-run-recovery --stale-limit 20
```

Expected:

- Stale execution ids are listed.
- Recovered execution ids are `none`.
- `Recovered: 0`.
- The test execution remains `running`.
- Lease fields remain unchanged.

## Stale Recovery Apply

For the same intentionally expired test lease, run:

```bash
python3 scripts/run_playbook_executor_once.py --recover-stale --stale-limit 20
```

Expected:

- Output includes recovered execution ids.
- Rows with attempts remaining move from `running` to `pending`.
- Exhausted rows move to `failed`.
- Lease fields are cleared.
- `recovery_count` increments.
- `awaiting_approval` rows are not recovered and are counted only as skipped awaiting approval when applicable.
- No playbook steps are executed during recovery.

## Post-Recovery Resume Check

Run one normal worker batch after recovery:

```bash
python3 scripts/run_playbook_executor_once.py --batch-size 1
```

Expected:

- The recovered `pending` execution is eligible for normal claim.
- Processing resumes after `last_completed_step`.
- Steps already marked successful in `steps_log` are not executed again.
- Slack/Teams notification delivery rows are not duplicated for completed notification steps.

## Evidence To Capture

Capture these values without secrets:

- Command timestamps.
- Worker ids.
- Execution ids.
- Pre/post execution status.
- `last_completed_step`.
- `recovery_count`.
- `lease_owner`, `lease_heartbeat_at`, and `lease_expires_at`.
- Notification delivery attempt counts by execution id.

Do not capture:

- `DATABASE_URL`.
- Webhook URLs.
- API tokens.
- Passwords.
- Raw adapter credential material.

## Stop Conditions

Stop and investigate before retrying if any of these happen:

- Runtime is not simulation.
- A command prints a secret or DSN.
- Two workers complete the same execution.
- A completed notification step creates an extra delivery row after recovery.
- `awaiting_approval` is moved by stale recovery.
- A recovery run executes playbook steps.
