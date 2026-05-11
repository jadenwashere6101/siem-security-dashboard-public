# Design: SOAR Scheduled Playbook Frontend Visibility

## Proposed frontend architecture
Add scheduled playbook metadata visibility to the existing playbook frontend surface. Prefer extending `PlaybooksPanel` with a small read-only "Schedules" section or tab rather than adding a new top-level navigation item.

Likely files for a future implementation:
- `frontend/src/services/playbookService.js`
- `frontend/src/services/playbookService.test.js`
- `frontend/src/components/PlaybooksPanel.js`
- `frontend/src/components/PlaybooksPanel.test.js`

No backend, schema, executor, queue, ingest, detection, correlation, or integration files should change.

## Service helpers
Use existing frontend service patterns:
- `buildSiemPath`
- `parseJsonResponse`
- `getApiErrorMessage`
- `credentials: "include"`

Recommended helpers:

```javascript
listPlaybookSchedules({ playbookId, enabled, limit } = {})
getPlaybookSchedule(scheduleId)
```

API behavior:
- `listPlaybookSchedules` calls `GET /playbook-schedules`.
- It may include `playbook_id`, `enabled`, and `limit` query params only when provided.
- `getPlaybookSchedule` calls `GET /playbook-schedules/<id>`.
- Both helpers use GET only.
- Non-OK responses throw safe user-facing errors.

Do not add service helpers for create, edit, delete, pause, resume, run-now, execute, retry, or queue actions.

## UI placement
Add a read-only schedules section inside the existing `PlaybooksPanel`, near existing playbook definitions and executions visibility.

Recommended layout:
- Internal tab or section label: `Schedules`.
- Compact table/list of schedules.
- Optional detail panel when a schedule is selected.
- Refresh button using GET only.
- Persistent notice explaining metadata-only behavior.

Do not create a separate app-level nav item unless the existing PlaybooksPanel structure cannot support the section without broad refactoring.

## Fields to show
List view should show:
- Schedule ID.
- `playbook_id`.
- Enabled state.
- Paused state.
- Schedule expression.
- Missed-run policy.
- `next_run_at`.
- `last_run_at`.

Detail view may also show:
- `last_success_at`.
- `last_failure_at`.
- `last_scheduled_execution_id`.
- `max_catchup_runs`.
- `max_concurrent_runs`.
- `timezone`.
- `created_at`.
- `updated_at`.

Use existing timestamp formatting utilities. Render missing timestamps as `N/A` or the local panel convention.

## Metadata-only notice
The schedules section must include a persistent notice such as:

```text
Schedules are metadata-only. No scheduler or daemon exists, and these records do not execute playbooks.
```

This notice should be visible in populated, empty, and error states where practical.

Avoid language like "next execution will run" or "scheduled job is active". Prefer "next run metadata" or "configured next_run_at" to avoid implying autonomous execution exists.

## Loading, error, and empty states
Loading:

```text
Loading playbook schedules...
```

Error:

```text
Error loading playbook schedules: {error}
```

Empty:

```text
No playbook schedules found.
```

Filtered empty:

```text
No playbook schedules match this filter.
```

Detail error should be scoped to the detail area and should not clear the schedule list.

## Filtering
Safe filters:
- Enabled: all, enabled, disabled.
- Optional playbook ID text filter if consistent with current PlaybooksPanel patterns.
- Limit may remain service-only or use current panel defaults.

Filters must call read-only list APIs only.

## Controls explicitly forbidden
Do not add:
- Create schedule.
- Edit schedule.
- Delete schedule.
- Pause schedule.
- Resume schedule.
- Run now.
- Execute playbook.
- Retry execution.
- Cancel or abandon execution.
- Queue worker controls.
- Approval controls.
- Circuit breaker controls.

A refresh button is allowed because it only refetches data.

## Auth and roles
Use the same frontend role visibility as existing playbook read visibility:
- Analysts can view schedule metadata if they can view playbooks.
- Super-admins can view schedule metadata.
- Viewers should not receive a new visible schedule surface if they cannot view playbook state.

Do not add new role-specific mutation behavior because there are no mutation controls in this change.

## Safe metadata handling
Do not render secrets, raw params, raw config blobs, or external API credentials. The schedule API fields should be safe metadata, but the frontend should still avoid arbitrary raw JSON dumps.

Allowed metadata fields are the explicit schedule fields listed above. Ignore unknown fields until reviewed.

## Test strategy
Service tests should verify:
- `listPlaybookSchedules` calls `GET /playbook-schedules` with credentials.
- Query params are included only when provided.
- `getPlaybookSchedule` calls `GET /playbook-schedules/<id>` with credentials.
- Non-OK responses throw useful errors.
- Helpers do not use non-GET methods.

Component tests should verify:
- Schedules loading state renders.
- Schedule rows render key fields.
- Empty state renders.
- Error state renders with retry/refresh behavior if included.
- Detail selection renders read-only schedule metadata.
- Metadata-only notice is visible.
- No create/edit/delete/pause/resume/run-now/execution controls are rendered.
- Existing definitions/executions UI remains usable.

## Safety boundaries
- Visibility only.
- Must clearly say schedules are metadata-only and do not execute yet.
- Must not imply autonomous execution exists.
- Must not add mutation controls.
- No backend changes.
- No schema changes.
- No scheduler implementation.
- No playbook execution from schedules.
- No executor or queue changes.
- No ingest, detection, or correlation changes.
- No real integrations.

## Risks and stop conditions
- Stop if frontend needs backend changes to show the schedule metadata.
- Stop if UI requires create/edit/delete/pause/resume/run controls to be useful.
- Stop if adding schedule visibility requires broad PlaybooksPanel restructuring.
- Stop if copy implies schedules will execute automatically.
- Stop if unknown metadata fields would need unsafe raw JSON rendering.
