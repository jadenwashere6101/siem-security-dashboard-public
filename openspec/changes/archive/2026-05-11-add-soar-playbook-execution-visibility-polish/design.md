# Design: SOAR Playbook Execution Visibility Polish

## Proposed Frontend/Backend Visibility Behavior

The backend execution detail endpoint should remain read-only and continue returning stored
execution data. The current expected fields are:

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

If all fields are already present, no backend implementation change is needed. If any field
is missing from `GET /playbook-executions/<id>`, add only a narrow serializer/read response
fix. Do not add mutation endpoints or executor behavior.

The frontend should render execution detail as a structured read-only view instead of relying
primarily on raw JSON.

## Files Likely To Change

Frontend:

- `frontend/src/components/PlaybooksPanel.js`
- `frontend/src/components/PlaybooksPanel.test.js`

Backend only if required:

- `routes/playbook_routes.py`
- `tests/test_playbook_routes.py`

Do not change:

- `engines/playbook_step_executor.py`
- `engines/soar_playbook_orchestrator.py`
- `core/playbook_store.py`
- `routes/ingest_routes.py`
- SOAR queue, approval, incident, protected-target, adapter, or frontend non-playbook files

## Data Shown In Execution Detail

Execution context section:

| Field | Display |
|---|---|
| Execution ID | numeric ID |
| Playbook ID | exact `playbook_id` |
| Status | badge/label |
| Alert ID | linked ID value or `None` |
| Incident ID | linked ID value or `None` |
| Last completed step | integer or `None` |
| Created | formatted timestamp |
| Started | formatted timestamp or `Not started` |
| Completed | formatted timestamp or `Not completed` |

Status summary copy:

- `pending`: execution record exists but simulation has not started
- `running`: simulation started but has not reached terminal state
- `success`: all simulated steps completed successfully
- `failed`: at least one simulated step failed or execution validation failed
- `abandoned`: execution was intentionally abandoned or marked terminal outside this view

Step timeline section:

- step index
- action name
- status badge
- mode, expected `simulation`
- simulated flag, expected `true`
- executed flag, expected `false`
- started/completed timestamps
- message
- error code/message if present
- optional compact output summary

## Timeline Rendering Approach

Render `steps_log` as a vertical list of compact step rows/cards inside the execution detail
panel. Avoid nested cards inside cards if the surrounding component already uses a card shell;
use simple bordered rows or unframed sections.

Recommended rendering:

```text
Execution #42  success
Playbook: pb_block_high_rep
Alert: 123  Incident: None
Created: ... Started: ... Completed: ...

Step Timeline
1. monitor       success   simulation
   simulated: true   executed: false
   [SIMULATED PLAYBOOK STEP] monitor

2. block_ip      success   simulation
   simulated: true   executed: false
   [SIMULATED PLAYBOOK STEP] block_ip
```

For failed steps:

```text
2. unsupported_action   failed   simulation
   simulated: true   executed: false
   Unsupported playbook step action
   Error: unsupported_action
```

For empty `steps_log`:

- Pending: "No simulated steps have run yet."
- Running: "No step output has been recorded yet."
- Success with empty steps: "Playbook completed with no defined steps."
- Failed with empty steps: "Execution failed before step output was recorded."

Keep raw JSON optional and secondary. If shown, use `<pre>` with constrained wrapping so it
does not dominate the detail view.

## Loading/Error/Empty Behavior

Execution list:

- Preserve current loading/error/empty behavior.
- Keep filters unchanged.
- Avoid automatic mutation or retry prompts.

Execution detail:

- Loading: "Loading execution detail..."
- Detail fetch error: show safe error text from service layer.
- No `steps_log`: show status-aware empty message.
- Malformed `steps_log`: treat as empty and optionally show a safe warning.
- Unknown/null IDs: display `None` or `Not linked`; do not attempt implicit fetches.

Refresh:

- Existing refresh should re-run read-only list/detail API calls only.
- No polling loop is required.

## Safety Boundaries

- Visibility only.
- Must not execute or re-run playbooks.
- Must not add mutation controls.
- Must not add run/retry/cancel/execute controls.
- Must not change executor behavior.
- Must not enqueue SOAR queue rows.
- Must not create approvals.
- Must not call adapters or integrations.
- Must not mutate firewall/blocklist.
- Must not change existing SOAR queue, approval, incident, protected-target, or adapter
  behavior.
- Keep frontend changes focused inside `PlaybooksPanel` and tests.
- Backend changes, if any, must be serializer/read-only only.

## Test Strategy

Frontend tests:

- execution detail renders context fields
- pending execution without steps shows pending-specific empty message
- running execution without steps shows running-specific empty message
- success execution with simulated steps renders step timeline
- failed execution renders failed step, error code, and message
- simulated/executed flags are visible
- timestamps are rendered through existing formatting helpers
- malformed or non-array `steps_log` does not crash
- no run/retry/cancel/execute controls are present
- refresh/detail actions still call read-only service helpers only

Backend tests only if response shape changes:

- `GET /playbook-executions/<id>` includes all stored execution fields
- `steps_log` remains an array
- nullable `alert_id` and `incident_id` serialize as JSON `null`
- endpoint remains read-only and does not mutate status/steps

Regression tests:

- existing Playbooks panel tests
- existing playbook service tests
- existing playbook route tests
- existing playbook executor tests

## Risks/Stop Conditions

- Stop if implementation requires executor behavior changes.
- Stop if implementation requires schema changes.
- Stop if implementation requires run/retry/cancel controls.
- Stop if implementation needs backend mutation endpoints.
- Stop if implementation changes SOAR queue, approval, incident, protected-target, adapter,
  ingest, detection, or correlation behavior.
- Stop if the UI starts implying real execution occurred.
- Stop if large `steps_log` rendering creates layout issues that require broad app refactors.
