# Design: SOAR Playbook Approval Visibility Polish

## Proposed UI Behavior

Enhance the existing PlaybooksPanel execution detail timeline so approval-gated simulation
states are first-class read-only timeline events rather than generic step rows.

When `detailRecord.status === "awaiting_approval"` or the `steps_log` contains an
`approval_requested` event with `approval_status === "pending"`, show a prominent read-only
notice:

```text
Approval-gated simulation paused; no later steps will run until approval.
```

The notice should appear in the execution detail panel near the status summary. It must not
include approval, denial, resume, retry, run, cancel, or execution controls.

For terminal approval gate outcomes:

- approved/resumed: show that simulation resumed after approval
- denied: show that the simulated playbook stopped and later steps were skipped
- expired: show that the simulated playbook stopped after approval expiration and later steps
  were skipped

## Files Likely To Change

Frontend:

- `frontend/src/components/PlaybooksPanel.js`
- `frontend/src/components/PlaybooksPanel.test.js`

Backend only if required for read-only response shape:

- `routes/playbook_routes.py`
- `tests/test_playbook_routes.py`

Do not change:

- `engines/playbook_step_executor.py`
- `core/playbook_store.py`
- `core/approval_store.py`
- `schema.sql`
- `routes/approval_routes.py`
- `routes/ingest_routes.py`
- detection/correlation engines
- SOAR queue, worker, incident, protected-target, adapter, or integration modules

## Approval Step/Timeline Display Rules

The timeline should map approval-related `steps_log` events into clear human labels.

Recommended labels:

| Event/status | Display label | Meaning |
|---|---|---|
| `approval_requested` | Approval requested | Gate created a linked approval request and paused simulation |
| `approval_approved` | Approval approved | Approval request was approved |
| `approval_resumed` | Simulation resumed | Executor resumed after approval |
| `approval_denied` | Approval denied | Execution stopped safely; later steps did not run |
| `approval_expired` | Approval expired | Execution stopped safely after expiration |
| `skipped_after_approval_gate` | Skipped after approval gate | Step was intentionally not simulated after denial/expiration |
| failed approval gate entry | Approval gate failed | Missing/invalid approval context stopped execution |

Each approval event row should show:

- step number/index
- action `require_approval`
- event label
- approval request ID when present
- approval status when present
- risk level when present
- simulation flags (`simulated`, `executed`)
- message
- timestamp if present

For skipped later steps, show:

- skipped action name
- skip reason from `output.skip_reason` when present
- clear copy that the step did not run
- `executed=false`

Avoid raw JSON as the primary display. Keep raw JSON secondary if already present.

## Data Needed From Existing APIs

The existing `GET /playbook-executions/<id>` response should already include:

- `id`
- `playbook_id`
- `alert_id`
- `incident_id`
- `status`
- `started_at`
- `completed_at`
- `last_completed_step`
- `steps_log`
- `created_at`

For this change, the frontend can read approval context from stored `steps_log` entries:

- `event`
- `approval_request_id`
- `approval_status`
- `risk_level`
- `message`
- `output.skip_reason`
- `simulated`
- `executed`

Backend read API polish is allowed only if the current execution detail serializer omits
stored `steps_log` fields or strips approval context. Do not add mutation endpoints.

## Loading/Error/Empty Behavior

Preserve existing PlaybooksPanel behavior:

- existing execution list loading state
- existing execution detail loading state
- existing error rendering
- existing empty `steps_log` messages
- existing refresh behavior

Approval-specific rendering:

- If approval fields are missing, render the step safely with available data.
- If `approval_request_id` is missing, display `Not linked` or omit that line.
- If `approval_status` is missing, display `Unknown`.
- If `steps_log` is malformed/non-array, keep the existing safe empty behavior.
- If an execution is `awaiting_approval` but no approval event is present, show a cautious
  status message without inventing approval context.

## Safety Boundaries

- Visibility only.
- Must not approve or deny from PlaybooksPanel.
- Must not execute, resume, retry, or cancel playbooks from the UI.
- Must not add run/retry/cancel/resume buttons.
- Must not change executor state transitions.
- Must not change approval decision behavior.
- Must not enqueue SOAR queue actions.
- Must not mutate firewall/blocklist.
- Must not call adapters or integrations.
- Must not change ingest/detection/correlation code.
- Must not redesign approval UI/routes.
- Keep frontend changes focused inside PlaybooksPanel and tests.
- Backend changes, if any, must be read-only serializer polish only.

## Test Strategy

Frontend tests:

- awaiting approval execution shows the pause notice:
  - “Approval-gated simulation paused; no later steps will run until approval.”
- `approval_requested` renders as Approval requested with approval request ID/status/risk.
- `approval_approved` renders as Approval approved.
- `approval_resumed` renders as Simulation resumed.
- `approval_denied` renders as Approval denied and later skipped steps render as skipped.
- `approval_expired` renders as Approval expired and later skipped steps render as skipped.
- skipped-after-gate entries clearly show `executed=false` and skip reason.
- no approve/deny/resume/run/retry/cancel controls are present.
- existing non-approval timeline rendering still works.
- existing super-admin definition management controls remain unchanged.

Backend tests only if response shape changes:

- execution detail response preserves approval event fields inside `steps_log`
- endpoint remains read-only
- no execution status or approval request mutation occurs during read

Regression tests:

- PlaybooksPanel tests
- playbook service tests if fixtures are updated
- playbook route tests only if backend serializer changes

## Risks/Stop Conditions

- Stop if implementation requires executor behavior changes.
- Stop if implementation requires schema changes beyond a proven additive read-only field.
- Stop if implementation requires approval route/UI decision changes.
- Stop if implementation requires PlaybooksPanel mutation controls.
- Stop if implementation changes SOAR queue, approval, incident, protected-target, adapter,
  ingest, detection, or correlation behavior.
- Stop if the UI copy implies real execution or real remediation occurred.
- Stop if rendering large `steps_log` approval histories requires broad layout refactors.
