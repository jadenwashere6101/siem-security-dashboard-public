# Tasks: SOAR Queue Item Detail UI

Implement later as a focused frontend-only enhancement.

---

## Task 1 — Inspect current queue UI/service

Inspect:

- `frontend/src/components/SoarQueuePanel.js`
- `frontend/src/services/soarQueueService.js`
- existing frontend service tests
- existing component test setup

Confirm:

- whether `loadSoarQueueItem(queueId)` already exists
- how current list rows render nullable `alert_id`
- how current panel handles loading/error states
- where a detail panel can fit without disrupting the table

---

## Task 2 — Wire detail service usage

Use existing:

```javascript
loadSoarQueueItem(queueId)
```

If missing, add only a GET helper for:

```text
GET /admin/soar/queue/<id>
```

Requirements:

- use `credentials: "include"`
- reuse existing parse/error helpers
- preserve nullable `alert_id`
- do not transform away `idempotency_key`
- do not add mutation service calls

---

## Task 3 — Add selected-item detail state

In `SoarQueuePanel`, add state for:

- selected queue id
- selected queue item detail
- detail loading
- detail error

Add a handler that:

- accepts a queue id
- clears previous detail errors
- fetches detail
- stores the selected detail
- handles failure safely

---

## Task 4 — Add row view affordance

Add a clear read-only way to view a row detail.

Recommended:

- add a `View` column/button to recent queue rows

Requirements:

- selecting a row only calls the GET detail endpoint
- no row mutation controls
- selected row should be visually distinguishable if practical
- keyboard/mouse interaction should be usable

---

## Task 5 — Render read-only detail panel

Render fields:

- queue id
- alert reference
- action
- status
- `source_ip`
- `retry_count / max_retries`
- `last_error`
- `created_at / updated_at`
- `idempotency_key`

Requirements:

- show `idempotency_key` only in detail view
- keep list view free of `idempotency_key`
- handle `alert_id: null` as `"Deleted alert"` or `"N/A"`
- wrap/truncate long `last_error` safely
- wrap long `idempotency_key` safely
- include loading, error, no-selection, and close states

---

## Task 6 — Preserve existing controls and safety boundaries

Confirm implementation does not add:

- retry/replay/cancel buttons
- selected-row worker execution
- real firewall actions
- backend changes
- schema changes
- ingest/detection/correlation changes

Confirm the existing manual simulation batch control remains panel-level and
unchanged.

---

## Task 7 — Add tests where current setup supports them

If service tests exist, cover:

- `loadSoarQueueItem(queueId)` endpoint path
- `credentials: "include"`
- API error handling

If component tests exist, cover:

- selecting/viewing a queue row fetches detail
- detail loading state
- detail success state
- nullable alert rendering
- `idempotency_key` shown only in detail
- no mutation controls present

Do not introduce broad new frontend test infrastructure solely for this change.

---

## Verification

Run:

```bash
cd frontend
npm run build
```

If frontend tests are added or updated, run the relevant test command.

Optionally run backend visibility tests to confirm endpoint contract remains
available:

```bash
python3 -m pytest tests/test_soar_queue_visibility_api.py -x --tb=short -v
```

---

## Explicit Non-Tasks

Do not:

- add retry/replay/cancel buttons
- add worker execution from detail view
- add real firewall actions
- change backend unless absolutely required
- change schema
- touch ingest/detection/correlation
- commit anything
