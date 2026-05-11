# Tasks: SOAR Playbook Execution Visibility Polish

Implement later in small visibility-only steps. Do not implement as part of this spec-only
change.

## Step 1: Confirm Current API Shape

- [ ] Inspect `routes/playbook_routes.py`.
- [ ] Confirm `GET /playbook-executions/<id>` returns `id`.
- [ ] Confirm it returns `playbook_id`.
- [ ] Confirm it returns `alert_id`.
- [ ] Confirm it returns `incident_id`.
- [ ] Confirm it returns `status`.
- [ ] Confirm it returns `started_at`, `completed_at`, and `created_at`.
- [ ] Confirm it returns `last_completed_step`.
- [ ] Confirm it returns `steps_log`.

If all fields are present, do not change backend code.

## Step 2: Add Backend Response Tests Only If Needed

File:

```text
tests/test_playbook_routes.py
```

Only add/adjust tests if the existing route tests do not already cover the required fields.

- [ ] Execution detail includes context IDs and timestamps.
- [ ] Execution detail includes `steps_log`.
- [ ] `steps_log` serializes as an array.
- [ ] Nullable `alert_id` and `incident_id` serialize as JSON `null`.
- [ ] Detail endpoint is read-only and does not mutate status or `steps_log`.

Verification if backend tests change:

```bash
python3 -m pytest tests/test_playbook_routes.py -v
```

## Step 3: Add Timeline Rendering Helpers

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Add helper to normalize `steps_log` to an array.
- [ ] Add helper to format status labels/badges.
- [ ] Add helper to render `simulated` and `executed` flags.
- [ ] Add helper to select status-aware empty text for empty timelines.
- [ ] Keep helpers local to `PlaybooksPanel` unless an existing shared utility is already
      appropriate.

## Step 4: Improve Execution Detail Context View

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Render execution ID.
- [ ] Render playbook ID.
- [ ] Render status summary.
- [ ] Render alert ID or `None`.
- [ ] Render incident ID or `None`.
- [ ] Render last completed step or `None`.
- [ ] Render created/started/completed timestamps.
- [ ] Preserve existing detail close behavior.
- [ ] Do not add mutation controls.

## Step 5: Add Step Timeline UI

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Render one row/card per `steps_log` entry.
- [ ] Show step index.
- [ ] Show action.
- [ ] Show status.
- [ ] Show mode.
- [ ] Show `simulated` flag.
- [ ] Show `executed` flag.
- [ ] Show message.
- [ ] Show started/completed timestamps.
- [ ] Show error code/message when present.
- [ ] Show status-aware empty state when no steps exist.
- [ ] Keep raw JSON secondary or omit it if timeline is complete enough.

## Step 6: Add Frontend Tests

File:

```text
frontend/src/components/PlaybooksPanel.test.js
```

Add tests for:

- [ ] pending execution detail without steps shows "No simulated steps have run yet."
- [ ] running execution detail without steps shows running-specific empty text.
- [ ] success execution detail renders simulated step timeline.
- [ ] failed execution detail renders error code/message.
- [ ] simulated/executed flags are visible.
- [ ] linked `playbook_id`, `alert_id`, `incident_id`, and timestamps are visible.
- [ ] malformed `steps_log` does not crash.
- [ ] no run/retry/cancel/execute controls are rendered.
- [ ] detail fetch still calls `getPlaybookExecution` only.

## Frontend Verification Commands

Run:

```bash
npm test -- --watchAll=false frontend/src/components/PlaybooksPanel.test.js
```

Run nearby regressions:

```bash
npm test -- --watchAll=false frontend/src/services/playbookService.test.js
npm test -- --watchAll=false frontend/src/components/SoarQueuePanel.test.js
npm test -- --watchAll=false frontend/src/components/ApprovalsPanel.test.js
npm test -- --watchAll=false frontend/src/components/IncidentsPanel.test.js
```

Run build:

```bash
npm run build
```

## Backend Verification Commands

Only needed if backend response polish is implemented:

```bash
python3 -m py_compile routes/playbook_routes.py
python3 -m pytest tests/test_playbook_routes.py -v
```

Always run playbook executor regression tests if available:

```bash
python3 -m pytest tests/test_playbook_step_executor.py -v
python3 -m pytest tests/test_soar_playbook_orchestrator.py -v
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires schema changes.
- [ ] Stop if implementation changes executor behavior.
- [ ] Stop if implementation adds run/retry/cancel/execute controls.
- [ ] Stop if implementation calls mutation APIs from execution detail.
- [ ] Stop if implementation changes SOAR queue, approval, incident, protected-target,
      adapter, ingest, detection, or correlation behavior.
- [ ] Stop if implementation requires broad `App.js` or layout refactors.
- [ ] Roll back the current implementation step if Playbooks panel tests fail.
- [ ] Roll back the current implementation step if existing playbook route/executor tests
      regress.
