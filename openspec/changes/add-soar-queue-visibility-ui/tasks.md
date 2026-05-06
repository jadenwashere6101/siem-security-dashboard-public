# Tasks: SOAR Queue Visibility UI

Implement later as a frontend-only, read-only change unless a small backend
compatibility issue is discovered.

---

## Task 1 — Inspect current frontend navigation and admin panel patterns

Inspect:

- `frontend/src/App.js`
- existing admin panel components
- existing service modules
- existing role-gating behavior

Decide where `"SOAR Queue"` belongs without redesigning navigation.

---

## Task 2 — Add frontend service

Create:

```text
frontend/src/services/soarQueueService.js
```

Add:

- `loadSoarQueueStatus()`
- `loadRecentSoarQueueItems({ limit, status })`
- `loadSoarQueueItem(queueId)`

Rules:

- use `buildSiemPath`
- use `credentials: "include"`
- use GET only
- preserve `alert_id: null`
- do not expose or transform `idempotency_key` in recent list data

---

## Task 3 — Add queue display helpers

Either inside the component or in a small utility if reused:

- format action labels
- format status labels
- format timestamps
- format retry count
- format nullable alert reference

Nullable alert behavior:

- prefer `item.alert_reference.label`
- else show `Alert <id>` for non-null IDs
- else show `Deleted alert` or `N/A`

---

## Task 4 — Add read-only panel component

Create:

```text
frontend/src/components/SoarQueuePanel.js
```

Show:

- queue counts by status
- recent queue table
- action
- status
- source IP
- alert reference
- retry count / max retries
- last error
- created/updated timestamps

Include:

- loading state
- error state
- empty state
- refresh control if consistent with existing admin panels

Do not include:

- retry button
- replay button
- cancel button
- worker execution button
- firewall execution button

---

## Task 5 — Wire panel into app navigation

Update the existing app shell minimally to expose the panel to admin users.

Rules:

- preserve existing auth/session behavior
- preserve existing routes/sections
- do not move admin state ownership broadly
- do not introduce custom hooks unless already used for similar panels

---

## Task 6 — Optional detail view

If backend detail endpoint exists and the UI remains small, add a read-only row
detail view.

Allowed:

- display queue metadata
- display `idempotency_key` only if backend already returns it

Forbidden:

- mutation controls
- worker execution controls
- real adapter controls

If detail endpoint is absent or inconsistent, defer detail UI.

---

## Task 7 — Add tests where supported

If frontend service tests exist:

- test service URLs
- test credentials include
- test GET-only behavior

If component tests exist:

- loading state
- error state
- empty state
- counts render
- recent rows render
- nullable alert ID renders safely
- no mutation buttons appear
- list view does not display `idempotency_key`

Do not add a large new testing framework solely for this change.

---

## Verification

Run:

```bash
cd frontend && npm run build
```

If backend files are touched for a compatibility fix, also run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py
python3 -m pytest tests/ -x --tb=short -v
```

---

## Explicit Non-Tasks

Do not:

- add retry/replay buttons
- add worker execution controls
- add real firewall execution UI
- add playbooks/incidents UI
- change schema
- change queue mutation behavior
- change ingest/detection/correlation flow
- expose `idempotency_key` in list view

