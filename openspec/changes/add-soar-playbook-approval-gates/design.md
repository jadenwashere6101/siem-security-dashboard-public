# Design: SOAR Playbook Approval Gates

## Proposed Architecture

Extend the simulation-only playbook executor with an approval gate state machine. The executor
continues to run manually and remains simulation-only.

Recommended responsibilities:

- `engines/playbook_step_executor.py`
  - detect `require_approval` steps
  - create/reuse approval requests for that execution step
  - mark the execution `awaiting_approval`
  - resume only when a linked approval is approved
  - stop safely when a linked approval is denied or expired
- `core/playbook_store.py`
  - add narrow helpers for `awaiting_approval` status and `steps_log` updates
  - add helpers to find the next step after an approved gate
- `core/approval_store.py`
  - add narrow helpers for playbook execution approval requests if the schema link is added
  - preserve existing queue/incident approval behavior

Manual execution remains the only run mode. No daemon or systemd worker is introduced.

## Files Likely To Change

- `schema.sql` — only if adding nullable playbook approval link columns/indexes is required.
- `core/approval_store.py` — add playbook-specific approval request helper/query support.
- `core/playbook_store.py` — add `awaiting_approval` transition helpers and resume helpers.
- `engines/playbook_registry.py` — register/validate `require_approval` as a supported
  playbook step type.
- `engines/playbook_step_executor.py` — add approval gate pause/resume behavior.
- `scripts/run_playbook_executor_once.py` — optionally add a manual resume/process flag if
  the current one-shot runner needs it.
- `tests/test_approval_store.py` — only for additive playbook approval linking behavior.
- `tests/test_playbook_registry.py` — validate `require_approval` step schema.
- `tests/test_playbook_store.py` — status and resume helper tests.
- `tests/test_playbook_step_executor.py` — approval gate executor tests.
- `tests/test_approval_routes.py` and frontend approval tests — only if a small additive
  response field is needed for visibility.

Do not change ingest routes, detection engines, correlation engines, SOAR queue worker logic,
real adapters, firewall helpers, incident creation behavior, or PlaybooksPanel execution
controls.

## Approval Step Schema

Add a playbook step action:

```json
{
  "action": "require_approval",
  "risk_level": "high",
  "reason": "Approve simulated block before continuing",
  "expires_in_minutes": 60,
  "on_denied": "fail",
  "on_expired": "fail"
}
```

Validation rules:

- `action` must be exactly `require_approval`.
- `risk_level` must be one of `medium`, `high`, or `critical`; default `high`.
- `reason` is optional but should be stored when present.
- `expires_in_minutes` is optional, bounded, and defaults to the approval store default.
- `on_denied` supports `fail` initially. `skip_remaining` can be documented for future work
  but should not be implemented unless explicitly approved.
- `on_expired` supports `fail` initially.

The approval step is a gate, not an executable remediation action.

## Execution Status/State Machine

Current simulation status flow:

```text
pending -> running -> success|failed
```

Add approval pause:

```text
pending -> running -> awaiting_approval
awaiting_approval + approved -> running -> success|failed|awaiting_approval
awaiting_approval + denied -> failed
awaiting_approval + expired -> failed
```

Rules:

- `awaiting_approval` is non-terminal and must not be picked up as normal `pending` work.
- Terminal statuses remain skipped and are not re-run.
- A pending approval blocks later steps.
- Approved approval resumes from the step after the approval gate.
- Denied/expired approval stops the execution safely before later steps.
- `last_completed_step` should record the last completed non-gate or completed gate index.
- `completed_at` is not set while awaiting approval.

## Approval Request Lifecycle

Existing `approval_requests` supports `incident_id` and `queue_id`, but not a direct
`playbook_execution_id` or step index. For playbook gates, the implementation should add the
smallest direct link unless an equivalent direct link already exists by then:

```sql
ALTER TABLE approval_requests
ADD COLUMN IF NOT EXISTS playbook_execution_id INTEGER
    REFERENCES playbook_executions(id) ON DELETE RESTRICT;

ALTER TABLE approval_requests
ADD COLUMN IF NOT EXISTS playbook_step_index INTEGER;
```

Also add narrow indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_approval_requests_playbook_execution_id
ON approval_requests (playbook_execution_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_approval_requests_playbook_step_active
ON approval_requests (playbook_execution_id, playbook_step_index)
WHERE playbook_execution_id IS NOT NULL
  AND status IN ('pending', 'approved');
```

The existing target check must allow a playbook execution target. If changing that check is
not acceptable as a tiny schema adjustment, stop and do not implement approval-gated
playbooks.

Lifecycle:

- At a `require_approval` step, create or reuse one active approval request for
  `(playbook_execution_id, step_index)`.
- Use `action='playbook.require_approval'` or a similarly explicit action value.
- Set `risk_level`, `request_reason`, and `expires_at` from the step.
- Leave approval decision APIs as the source of truth for approve/deny/expire.
- Do not create SOAR queue rows.

## Resume Behavior

Resume is manual/script-based only.

Recommended executor entrypoint:

```python
resume_awaiting_playbook_execution(conn, execution_id: int, now=None) -> dict
```

Behavior:

- Load the `awaiting_approval` execution.
- Find the latest linked approval request for the gate step.
- If `pending`, return skipped/awaiting result and do not run steps.
- If `approved`, append approved/resumed entries, mark `running`, and continue from the next
  step.
- If `denied`, append denied/skipped entries and mark execution `failed`.
- If expired or past `expires_at`, materialize expiration if needed, append expired/skipped
  entries, and mark execution `failed`.
- If no linked approval exists, mark failed or return a stop result; do not continue.

The existing one-shot script may optionally process both `pending` and approved
`awaiting_approval` executions, but it must still run once and exit.

## Denial/Expiration Behavior

Denied approval:

- Append an approval denied entry.
- Append skipped entries for later steps only if useful for visibility.
- Mark execution `failed`.
- Do not run later steps.

Expired approval:

- Materialize expiration through approval store behavior.
- Append an approval expired entry.
- Mark execution `failed`.
- Do not run later steps.

Denial/expiration must not create queue rows, approvals, incidents, adapter calls, or network
calls.

## `steps_log` Format

Approval requested:

```json
{
  "step_index": 1,
  "action": "require_approval",
  "status": "awaiting_approval",
  "mode": "simulation",
  "simulated": true,
  "executed": false,
  "approval_request_id": 123,
  "approval_status": "pending",
  "message": "Approval requested before continuing simulated playbook.",
  "started_at": "2026-05-10T12:00:00+00:00",
  "completed_at": null
}
```

Approved/resumed:

```json
{
  "step_index": 1,
  "action": "require_approval",
  "status": "approved",
  "mode": "simulation",
  "simulated": true,
  "executed": false,
  "approval_request_id": 123,
  "approval_status": "approved",
  "message": "Approval granted; simulation resumed.",
  "completed_at": "2026-05-10T12:15:00+00:00"
}
```

Denied/expired:

```json
{
  "step_index": 1,
  "action": "require_approval",
  "status": "denied",
  "mode": "simulation",
  "simulated": true,
  "executed": false,
  "approval_request_id": 123,
  "approval_status": "denied",
  "message": "Approval denied; later steps were not run.",
  "completed_at": "2026-05-10T12:15:00+00:00"
}
```

Every entry must clearly include `simulated: true` and `executed: false`.

## Safety Boundaries

- Approval gates pause before later high-risk simulated steps.
- Pending approval must not run later steps.
- Denied or expired approval must not run later high-risk steps.
- Approved approval may resume only from the next step after the gate.
- Must not call real adapters.
- Must not enqueue SOAR response actions.
- Must not mutate firewall/blocklist.
- Must not create incidents.
- Must not alter alert creation or incident creation behavior.
- Must not change ingest/detection/correlation internals.
- Must preserve existing queue, approval, incident, protected-target, adapter, and frontend
  behavior.

## Failure Behavior

- Approval request creation failure: mark execution `failed` or return an error before any
  later step runs.
- Duplicate approval request race: reuse the active request and leave execution
  `awaiting_approval`.
- Missing linked approval during resume: stop and do not continue.
- Approval already denied/expired: mark execution `failed`.
- Approval still pending: return skipped/awaiting result.
- Invalid `require_approval` step: fail validation or mark execution `failed`.
- Any unexpected exception: log clearly, do not call external systems, and do not run later
  steps.

## Test Strategy

Backend tests should prove:

- `require_approval` is accepted by playbook registry validation.
- Pending execution pauses at `require_approval` with status `awaiting_approval`.
- Later steps are not simulated while approval is pending.
- One approval request is created or reused for the playbook execution and step index.
- Approved approval resumes from the next step and eventually succeeds when later steps
  succeed.
- Denied approval marks execution failed and does not run later steps.
- Expired approval marks execution failed and does not run later steps.
- `steps_log` contains requested, approved, denied, expired, resumed, and skipped entries as
  applicable.
- No `response_actions_queue` rows are created.
- No adapters/firewall/blocklist/network calls occur.
- Existing approval routes and queue approval behavior still pass.

Frontend/API tests are needed only if approval list/detail responses add playbook execution
context fields. Do not redesign approval UI.

## Risks/Stop Conditions

- Stop if direct playbook approval linking cannot be represented with a small additive schema
  change.
- Stop if implementation requires changing detection/correlation/ingest internals.
- Stop if implementation requires SOAR queue behavior changes.
- Stop if implementation requires real adapter calls or external integrations.
- Stop if implementation requires a daemon/systemd worker.
- Stop if approval resume cannot be made idempotent enough to avoid duplicate later step logs.
- Stop if existing approval API/UI behavior would need a broad rewrite.
