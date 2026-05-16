# SOAR Dead Letter Validation

Operational checklist for validating SOAR dead letter review and recovery flows.

This runbook is for staging or operator-controlled validation windows. It does not
enable autonomous retries, real notifications, or real remediation.

## Safety Preconditions

- Confirm runtime is simulation-only:
  - `INTEGRATION_MODE=simulation`
  - `SOAR_REAL_SLACK_ENABLED=false`
  - `SOAR_EXECUTION_MODE=simulation`
- Confirm `DATABASE_URL` points to the intended staging database. Do not print or paste the DSN.
- Confirm the deployed database is at migration `0010` or later.
- Confirm no real Slack, Teams, email, webhook, or remediation credentials are enabled.
- Confirm only one operator is running this checklist.
- Do not start a recurring worker, daemon, cron job, or scheduler during validation.

## Lifecycle

Supported dead letter states:

- `open -> retrying -> retried`
- `open -> dismissed`
- `retrying -> dismissed`

Meaning:

- `open`: failure is available for review.
- `retrying`: an operator requested retry handling, but retry execution may not have happened yet.
- `retried`: retry execution was accepted and the dead letter is closed as retried.
- `dismissed`: operator reviewed and intentionally closed the dead letter without retry execution.

## RBAC

- `analyst`
  - Can list dead letters.
  - Can view details.
  - Can view metrics.
  - Can dismiss.
  - Can request retry.
  - Cannot execute retry.
- `super_admin`
  - Can perform all analyst actions.
  - Can execute supported retries with `POST /dead-letters/<id>/retry-execute`.
- `viewer`
  - Denied from dead letter review and mutation endpoints.

## Supported Retry Sources

Currently supported:

- `playbook_execution`
  - `retry-execute` creates a new pending playbook execution with existing playbook retry semantics.
  - The new execution is not processed immediately.

Deferred source types:

- `notification_delivery`
- `response_action`
- `approval`

Retry execution for deferred types must return a clear conflict until explicit idempotency and approval semantics are implemented.

## Staging Validation Workflow

Use authenticated API calls through the staging backend. Replace ids with values from your environment.

### 1. Create a Simulated Failed Playbook

Use a harmless simulation-only playbook with a step that fails safely, such as an adapter-backed notification step under simulated failure conditions.

Expected:

- The playbook execution reaches `failed`.
- A dead letter is created with:
  - `source_type=playbook_execution`
  - `source_id=<failed execution id>`
  - `status=open`
  - `execution_id`, `playbook_id`, `alert_id` or `incident_id` when available
  - failed `step_index`, `action_name`, and sanitized `error_message`

### 2. Verify Dead Letter Creation

List:

```bash
curl -sS -b cookies.txt http://127.0.0.1:5051/dead-letters
```

Detail:

```bash
curl -sS -b cookies.txt http://127.0.0.1:5051/dead-letters/<dead_letter_id>
```

Expected:

- Response includes the failed playbook dead letter.
- Payload does not expose webhook URLs, tokens, passwords, authorization headers, or raw credential material.
- Re-reading list/detail does not mutate row counts or statuses.

### 3. Retry Request

```bash
curl -sS -X POST -b cookies.txt http://127.0.0.1:5051/dead-letters/<dead_letter_id>/retry-request
```

Expected:

- Dead letter moves from `open` to `retrying`.
- `retry_count` increments.
- `retry_requested_at` is set.
- `retry_requested_by` is set when the session user maps to `users.id`.
- No playbook execution is created by this step.
- No adapters or notifications are invoked.

### 4. Retry Execute

Super admin only:

```bash
curl -sS -X POST -b cookies.txt http://127.0.0.1:5051/dead-letters/<dead_letter_id>/retry-execute
```

Expected:

- Source type must be `playbook_execution`.
- Dead letter must already be `retrying`.
- A new `playbook_executions` row is created with `status=pending`.
- Dead letter moves to `retried`.
- Response includes `new_execution_id`.
- `DEAD_LETTER_RETRY_EXECUTE` audit event is written.
- The new pending execution is not automatically processed.
- No Slack, Teams, webhook, email, or remediation action is executed.

### 5. Confirm New Pending Execution

Inspect the new execution:

```bash
curl -sS -b cookies.txt http://127.0.0.1:5051/playbook-executions/<new_execution_id>
```

Expected:

- `status=pending`
- `steps_log=[]`
- `started_at` and `completed_at` are not advanced by retry-execute.

Only a later explicit worker run should process this pending execution.

### 6. Dismiss Flow

For a separate `open` or `retrying` dead letter:

```bash
curl -sS -X POST -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"comment":"reviewed in staging"}' \
  http://127.0.0.1:5051/dead-letters/<dead_letter_id>/dismiss
```

Expected:

- Dead letter moves to `dismissed`.
- `dismissed_at` is set.
- `dismissed_by` is set when the session user maps to `users.id`.
- Comment is sanitized before persistence.
- `DEAD_LETTER_DISMISS` audit event is written.
- No playbook, adapter, notification, or remediation work is invoked.

## Metrics Validation

```bash
curl -sS -b cookies.txt http://127.0.0.1:5051/metrics/dead-letters
```

Expected:

- Counts reflect `open`, `retrying`, `retried`, and `dismissed`.
- `active` counts `open` plus `retrying`.
- Breakdown includes source types and failure classes.
- Metrics response does not include `payload_json`, `error_message`, tokens, webhook URLs, or raw payload material.

## Recovery Guidance

### Stuck `retrying` Rows

If a dead letter remains `retrying` after a failed or abandoned review:

1. Inspect detail:

   ```bash
   curl -sS -b cookies.txt http://127.0.0.1:5051/dead-letters/<dead_letter_id>
   ```

2. Check whether retry execution is unsupported, blocked by source status, or blocked by an active execution conflict.
3. If the item should not be retried, dismiss it:

   ```bash
   curl -sS -X POST -b cookies.txt \
     -H 'Content-Type: application/json' \
     -d '{"comment":"dismissed stuck retrying row after review"}' \
     http://127.0.0.1:5051/dead-letters/<dead_letter_id>/dismiss
   ```

### Retry Conflicts

For `playbook_execution` retry-execute conflicts:

- `current status: permanently_failed`
  - Retry is blocked by existing playbook retry policy.
  - Leave the dead letter `retrying` for review or dismiss it after operator decision.
- `active execution already exists for playbook and alert`
  - Inspect active executions for the same `playbook_id` and `alert_id`.
  - Do not force another retry until the active execution is terminal or abandoned through existing controls.
- `execution not found`
  - Source execution is missing. Treat as a data integrity issue and dismiss only after review.

### Duplicate Execution Check

Before and after retry-execute, inspect active executions for the source pair:

- `playbook_id`
- `alert_id`
- status in `pending`, `running`, or `awaiting_approval`

Expected:

- Retry-execute creates at most one new pending execution.
- If an active execution already exists, retry-execute returns conflict and leaves the dead letter `retrying`.
- Dead letter moves to `retried` only after the new pending execution is created.

## Stop Conditions

Stop and investigate before continuing if any of these happen:

- Runtime is not simulation.
- A response contains a webhook URL, token, password, DSN, or raw credential material.
- Retry-execute processes playbook steps immediately.
- Retry-execute sends Slack, Teams, email, webhook, or remediation traffic.
- A deferred source type successfully retry-executes.
- Duplicate active executions are created for the same playbook and alert.
- A dead letter moves to `retried` without a new pending retry execution.

## Future Work

- Add `response_action` retry execution once queue idempotency and approval behavior are explicit.
- Define notification retry semantics for `notification_delivery` without duplicate sends.
- Add frontend/admin UI for review, filtering, dismissal, and retry workflow.
- Add dashboards for open depth, retry backlog, age, and source/failure-class trends.
- Add retry observability migration if future workflows need `retried_at`, `retried_by`, or retry result detail columns.
