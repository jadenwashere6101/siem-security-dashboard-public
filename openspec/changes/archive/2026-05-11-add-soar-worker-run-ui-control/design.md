# Design: SOAR Worker Run UI Control

---

## 1. UI Placement

Add the control to the existing SOAR Queue visibility panel:

```text
frontend/src/components/SoarQueuePanel.js
```

Recommended placement:

- near the existing refresh/filter controls
- visually grouped as an admin operation
- clearly labeled as a manual simulation batch

Do not create a separate page for the first version. The control belongs beside
queue health because the expected workflow is:

1. inspect status counts and recent rows
2. run one bounded simulation batch
3. inspect refreshed queue state and summary

---

## 2. Service Method

Extend:

```text
frontend/src/services/soarQueueService.js
```

Add:

```javascript
export const runSoarWorkerOnce = async ({ batchSize } = {}) => { ... };
```

Endpoint:

```text
POST /admin/soar/worker/run-once
```

Request body:

```json
{
  "batch_size": 10
}
```

Rules:

- use the existing API path helper pattern, such as `buildSiemPath`
- use `credentials: "include"`
- use `Content-Type: application/json`
- use existing JSON parsing/error helpers where available
- do not send `mode`
- do not expose any service option that can send `mode: "real"`
- do not call adapter, firewall, or worker-specific frontend paths

If the user leaves the batch size blank, either omit `batch_size` or send the
panel default. Prefer omitting it if the current service conventions make that
simple, so the backend default remains authoritative.

---

## 3. Batch Size Control

Add a small numeric input or compact stepper.

Suggested behavior:

- default value: `10`
- min: `1`
- max displayed by UI: `25`
- step: `1`
- reject or clamp invalid local values before submitting

The backend still owns final validation and clamping. The UI should avoid sending
obviously invalid values because this is an admin control, not a validation demo.

Labeling should make the unit clear:

```text
Batch size
```

Button label:

```text
Run simulation batch
```

Avoid labels like `"Run worker"` alone because they do not communicate the safety
mode.

---

## 4. Run State

Component state should track:

- `runBatchSize`
- `isRunningBatch`
- `runError`
- `lastRunResult`

On click:

1. clear previous run error
2. set `isRunningBatch = true`
3. call `runSoarWorkerOnce({ batchSize })`
4. store response as `lastRunResult`
5. refresh queue status and recent items on success
6. set `isRunningBatch = false`

While running:

- disable the run button
- disable the batch size input or leave it read-only
- keep the existing queue data visible
- show a short in-progress label such as `"Running simulation..."`

The control should not poll worker state. The backend call is synchronous and
returns after exactly one batch.

---

## 5. Result Summary

Render a compact summary from the backend response:

```json
{
  "summary": {
    "processed": 3,
    "success": 2,
    "failed": 0,
    "skipped": 1,
    "requeued": 0
  }
}
```

Display:

- processed
- success
- failed
- skipped
- requeued

Also show the effective batch size if the backend returns it:

```text
Batch size used: 25
```

If `requested_batch_size` differs from `batch_size`, display a neutral note that
the request was capped by the backend. Do not treat clamping as an error.

Do not render full raw result JSON by default. If individual row results are
shown, render only safe fields already returned by the backend, such as:

- queue ID
- outcome
- new status
- message
- reason

No secret, environment, adapter config, or idempotency key display is needed for
this control.

---

## 6. Refresh Behavior

After a successful run:

- refresh queue status counts
- refresh recent queue items using the currently selected filter/limit

This should reuse the existing panel load/refresh function if one exists. Avoid
duplicating fetch orchestration in separate branches.

If refresh fails after a successful worker run:

- keep the run summary visible
- show the refresh error using the existing queue error state or a small inline
  message
- do not hide the successful run result

---

## 7. Error Handling

Expected backend errors:

- `401` unauthenticated
- `403` non-admin
- `400` invalid request, including attempts to use real mode
- `500` unexpected server/worker error

The UI should show concise messages from the existing API error helper. If no
message is available, use a generic message:

```text
Unable to run SOAR simulation batch.
```

Do not show:

- raw stack traces
- raw HTML error pages
- environment variables
- adapter config
- low-level database errors

---

## 8. Authorization Display

The control should live only inside the current admin SOAR Queue UI. Do not add
new role logic unless the existing component already receives current user/role
metadata and uses it for other admin controls.

Backend authorization remains the source of truth. If an unauthorized user
somehow reaches the panel, the request should fail normally with `401` or `403`.

---

## 9. Explicit Safety Non-Features

Do not add:

- real/simulation mode toggle
- adapter selector
- firewall provider selector
- retry/replay/cancel per-row buttons
- run loop
- schedule interval
- daemon/systemd controls
- dry-run Linux firewall controls
- incident/playbook controls

This UI is only a manual trigger for the already-safe simulation backend
endpoint.

---

## 10. Testing Strategy

### Service tests

If frontend service tests already exist, add coverage for:

- `runSoarWorkerOnce({ batchSize: 10 })` calls
  `/admin/soar/worker/run-once`
- request method is `POST`
- `credentials: "include"` is set
- body includes `batch_size`
- service does not send `mode`
- service surfaces API errors consistently

If no service test setup exists, do not introduce a broad new framework just for
this change.

### Component tests

If React component tests are already configured, cover:

- button renders with simulation/manual wording
- clicking button calls the service once
- button is disabled while request is in flight
- summary renders after success
- status/recent reload is triggered after success
- error state renders after failure
- no real-mode toggle is present

### Manual/build verification

Run:

```bash
cd frontend
npm run build
```

Optionally verify in browser:

- queue panel loads
- batch size can be changed
- run button disables during request
- result summary appears
- queue data refreshes after success
