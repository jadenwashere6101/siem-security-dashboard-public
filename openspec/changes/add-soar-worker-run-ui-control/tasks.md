# Tasks: SOAR Worker Run UI Control

Implement later as a frontend-only follow-up to the backend run-once endpoint.

---

## Task 1 — Inspect existing queue UI and service

Inspect:

- `frontend/src/components/SoarQueuePanel.js`
- `frontend/src/services/soarQueueService.js`
- any existing frontend API helper modules
- existing admin role/navigation gating in `frontend/src/App.js`

Confirm:

- how queue status/recent refresh is currently orchestrated
- how errors are parsed and displayed
- whether frontend service or component tests already exist

---

## Task 2 — Add run-once service method

In:

```text
frontend/src/services/soarQueueService.js
```

Add:

```javascript
runSoarWorkerOnce({ batchSize })
```

Requirements:

- call `POST /admin/soar/worker/run-once`
- use `credentials: "include"`
- send JSON body with `batch_size` only when provided
- do not send `mode`
- do not expose a real-mode option
- reuse existing parse/error helper conventions

---

## Task 3 — Add simulation run control to queue panel

In:

```text
frontend/src/components/SoarQueuePanel.js
```

Add:

- compact batch size input
- button labeled `Run simulation batch` or equivalent
- in-flight disabled state
- concise loading text while running
- inline error display
- last run summary display

The control should be visually consistent with the existing dashboard style and
should not dominate the queue visibility view.

---

## Task 4 — Refresh queue data after success

After a successful run:

- refresh queue status counts
- refresh recent queue items
- preserve the current status filter/limit if the panel supports them
- keep the run summary visible even if the follow-up refresh fails

Do not add polling or background refresh loops.

---

## Task 5 — Enforce UI safety boundaries

Confirm the implementation does not add:

- real mode toggle
- adapter selector
- firewall controls
- retry/replay/cancel buttons
- worker loop/scheduler controls
- schema/backend changes
- ingest/detection/correlation changes

Confirm double-click protection by keeping the run button disabled while the
request is active.

---

## Task 6 — Add tests where current setup supports them

If service tests exist, cover:

- POST endpoint path
- `credentials: "include"`
- JSON body contains `batch_size`
- no `mode` field is sent
- API errors are surfaced

If component tests exist, cover:

- simulation/manual label renders
- one click triggers one request
- button disabled while running
- summary renders after success
- error renders after failure
- no real-mode toggle is present

Do not introduce broad new frontend test infrastructure solely for this change.

---

## Verification

Run:

```bash
cd frontend
npm run build
```

If tests are added or existing frontend tests cover this area, run the relevant
test command as well.

Optionally run the backend endpoint tests to confirm the frontend target remains
available:

```bash
python3 -m pytest tests/test_soar_worker_admin_run_control.py -x --tb=short -v
```

---

## Explicit Non-Tasks

Do not:

- add a frontend real mode option
- use `AdapterBackedExecutor`
- add real firewall execution UI
- add retry/replay individual item controls
- add daemon/scheduler controls
- change backend unless the frontend cannot call the existing endpoint
- change schema
- touch ingest/detection/correlation
- commit anything
