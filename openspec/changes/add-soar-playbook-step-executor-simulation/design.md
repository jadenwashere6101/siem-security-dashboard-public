# Design: SOAR Playbook Step Executor Simulation

## Proposed Architecture

Add a simulation-only executor for existing pending `playbook_executions`.

Recommended module:

```text
engines/soar_playbook_step_executor.py
```

Primary functions:

```python
process_next_pending_playbook_execution(conn, now=None) -> dict | None
process_playbook_execution(conn, execution_id: int, now=None) -> dict
process_playbook_execution_batch(conn, limit=10, now=None) -> dict
```

The executor should be explicitly simulation-only. It should not share the response action
queue worker path and should not dispatch to adapter registries.

Manual/script entrypoint can be added only if kept simple:

```text
scripts/soar_playbook_simulation_run.py
```

The script should run one bounded batch and exit. No daemon/systemd/scheduler wiring belongs
in this change.

## Files Likely To Change

- `core/playbook_store.py` — add narrow helpers for claiming pending executions and writing
  step logs/status updates.
- `engines/soar_playbook_step_executor.py` — new simulation-only step executor.
- `scripts/soar_playbook_simulation_run.py` — optional manual batch runner.
- `tests/test_playbook_store.py` — store helper tests.
- `tests/test_soar_playbook_step_executor.py` — executor tests.
- `tests/test_soar_playbook_simulation_runner.py` — only if a script is added.

Do not change:

- `routes/ingest_routes.py`
- detection/correlation/ingest engines
- SOAR response queue worker/executor behavior
- approval routes/store
- incident routes/store
- protected-target policy
- adapter/integration modules
- frontend files

## Execution Data Flow

```text
manual caller/script
  -> process_playbook_execution_batch(conn, limit)
  -> claim one pending playbook_executions row
  -> set execution status running
  -> load linked playbook_definitions row
  -> iterate definition.steps
  -> simulate each step
  -> append step result to steps_log
  -> update last_completed_step after each successful simulated step
  -> set execution status success or failed
  -> return structured summary
```

The executor consumes existing `pending` `playbook_executions` rows only. It does not create
new executions and does not match alerts.

## Status Transition Design

Allowed executor transitions:

- `pending -> running`
- `running -> success`
- `running -> failed`

Rules:

- `success`, `failed`, and `abandoned` executions are terminal and must not be re-run.
- If `process_playbook_execution` is called for a terminal execution, return a skipped result.
- If called for a `running` execution, behavior should be conservative:
  - first implementation may skip it to avoid double-processing
  - stale-running recovery can be a later spec
- `started_at` should be set when moving to `running`.
- `completed_at` should be set when moving to `success` or `failed`.
- `last_completed_step` should track the 0-based index of the last successful step.

Store helpers should own the SQL updates. They should not commit; callers own transactions.

## `steps_log` Format

`steps_log` should remain JSONB array data.

Recommended entry shape:

```json
{
  "step_index": 0,
  "action": "monitor",
  "status": "success",
  "mode": "simulation",
  "started_at": "2026-05-10T12:00:00+00:00",
  "completed_at": "2026-05-10T12:00:00+00:00",
  "message": "[SIMULATED PLAYBOOK STEP] monitor",
  "output": {
    "simulated": true,
    "executed": false
  },
  "error": null
}
```

For failures:

```json
{
  "step_index": 1,
  "action": "unsupported_action",
  "status": "failed",
  "mode": "simulation",
  "started_at": "2026-05-10T12:00:01+00:00",
  "completed_at": "2026-05-10T12:00:01+00:00",
  "message": "Unsupported playbook step action",
  "output": {
    "simulated": true,
    "executed": false
  },
  "error": {
    "code": "unsupported_action",
    "message": "Unsupported playbook step action"
  }
}
```

Keep entries compact and stable for API/frontend display. Do not store secrets.

## Simulation Behavior

Supported action names come from `engines/playbook_registry.py`.

Initial simulation outcomes:

| Action | Simulation behavior |
|---|---|
| `monitor` | record a successful no-op monitoring step |
| `flag_high_priority` | record a successful simulated priority flag |
| `block_ip` | record a successful simulated block request; do not touch firewall, blocklist, adapters, approvals, or SOAR queue |

Every simulated step result must include:

- `simulated: true`
- `executed: false`
- no external call metadata

The executor must not import or call:

- `engines.soar_executor.AdapterBackedExecutor`
- `integrations.soar_adapters.*`
- Slack/email/PagerDuty/webhook clients
- firewall/blocklist mutation helpers
- `enqueue_response_action`
- `enqueue_committed_alerts`
- approval creation helpers

## Idempotency/Re-run Behavior

Minimum idempotency requirements:

- terminal `success`, `failed`, and `abandoned` executions are skipped
- completed successful steps in `steps_log` are not duplicated when a terminal execution is
  encountered again
- first implementation may skip `running` executions rather than resume them
- batch processor should claim only `pending` rows

Future resumability may use `last_completed_step` and successful `steps_log` entries to
resume partially completed executions. That is not required in this first simulation slice.

## Failure Behavior

Definition missing:

- mark execution `failed`
- record a failure entry or failure summary
- no external calls

Invalid `steps` root:

- mark execution `failed`
- record validation failure in `steps_log`

Unsupported step action:

- mark step `failed`
- mark execution `failed`
- stop processing further steps for this first implementation

Step simulation exception:

- mark step `failed`
- mark execution `failed`
- log server-side

Empty steps:

- mark execution `success`
- record empty `steps_log` or a concise execution-level result according to store helper
  design

The executor should return structured results with counts for processed, success, failed,
skipped, and errors.

## Safety Boundaries

- Executor must be simulation-only.
- Must not call real integration adapters.
- Must not mutate firewall/blocklist.
- Must not enqueue existing `response_actions_queue` items.
- Must not create approvals.
- Must not create incidents.
- Must not affect alert creation.
- Must not update alerts.
- Must not change ingest/detection/correlation code.
- Must be safe to run manually in development.
- Must not process terminal executions.
- Must preserve existing queue, approval, incident, protected-target, adapter, and frontend
  behavior.

## Test Strategy

### Store Tests

Cover:

- claim/list next pending execution returns only pending rows
- terminal rows are not claimed
- status transition to running sets `started_at`
- terminal transition sets `completed_at`
- writing `steps_log` preserves JSON array shape
- updating `last_completed_step` works
- helpers do not commit internally

### Executor Tests

Cover:

- no pending executions returns `None`/empty batch summary
- pending execution with `monitor` step becomes `success`
- pending execution with multiple supported steps becomes `success`
- `steps_log` contains stable simulated entries
- `block_ip` step is simulated only and does not call SOAR queue, approvals, adapters, or
  firewall helpers
- missing playbook definition marks execution `failed`
- unsupported step action marks execution `failed`
- terminal execution is skipped and not re-run
- running execution is skipped or handled according to first implementation decision
- batch limit is respected

### No-Real-Execution Tests

Use mocks/import checks to prove:

- no adapter registry calls
- no `AdapterBackedExecutor`
- no `SimulationExecutor` response-action queue executor path unless explicitly designed as
  pure local simulation without queue side effects
- no `enqueue_response_action`
- no `enqueue_committed_alerts`
- no approval creation
- no firewall/blocklist mutation
- no network calls

### Regression Tests

Run existing tests around:

- playbook store
- playbook routes/read APIs
- playbook trigger orchestration
- SOAR queue worker/admin controls
- approvals
- incidents
- protected targets
- ingest/detection/correlation contracts

## Risks/Stop Conditions

- Stop if implementation requires real adapters or integrations.
- Stop if implementation requires `response_actions_queue` enqueueing.
- Stop if implementation requires approval gates.
- Stop if implementation requires schema changes beyond a tiny additive helper field.
- Stop if implementation changes ingest, detection, or correlation.
- Stop if implementation changes existing SOAR queue behavior.
- Stop if daemon/systemd scheduling becomes necessary.
- Stop if frontend changes become necessary.
