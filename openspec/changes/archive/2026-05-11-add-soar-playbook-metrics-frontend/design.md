# Design: SOAR Playbook Metrics Frontend

## Proposed architecture

Add a small frontend service function that calls the existing read-only
`GET /metrics/playbooks` endpoint, and a new `PlaybookMetricsPanel` component that
renders the aggregated result. The panel follows the same read-only pattern used by
`SoarQueuePanel`, `ApprovalsPanel`, `PlaybooksPanel`, and `IntegrationStatusPanel`.

No backend, schema, executor, or queue code changes are required. The backend endpoint
already exists, is stable, and is authenticated.

## API being consumed

```http
GET /metrics/playbooks
```

Exact response shape from `routes/metrics_routes.py`:

```json
{
  "total_executions": 12,
  "by_status": {
    "pending": 2,
    "running": 1,
    "awaiting_approval": 1,
    "success": 5,
    "failed": 2,
    "abandoned": 1
  },
  "by_playbook_id": [
    {
      "playbook_id": "block_and_notify",
      "total": 7,
      "by_status": {
        "pending": 1,
        "running": 0,
        "awaiting_approval": 0,
        "success": 4,
        "failed": 2,
        "abandoned": 0
      }
    }
  ],
  "recent": {
    "window_hours": 24,
    "success": 3,
    "failed": 1,
    "time_basis": "Rows are included when COALESCE(completed_at, created_at) falls within the last 24 hours (UTC)."
  },
  "approval_gated": {
    "awaiting_approval": 1,
    "with_linked_approval": 3
  }
}
```

Notes on field behavior from the implementation:

- `by_status` always contains all six known keys (`pending`, `running`,
  `awaiting_approval`, `success`, `failed`, `abandoned`), defaulting to `0`.
- `by_playbook_id` is an array sorted by `playbook_id` alphabetically. Each entry
  always contains `playbook_id`, `total`, and `by_status`. An optional
  `other_status_count` key appears only when the total exceeds the sum of known
  status counts (i.e., there are rows with an unrecognized status value).
- `recent.window_hours` is always `24`. `recent.time_basis` is a human-readable
  explanation of the time window logic.
- `approval_gated.awaiting_approval` is a subset of `by_status.awaiting_approval`
  (same value, sourced from the aggregated status count). `with_linked_approval`
  counts distinct executions that have ever had any linked approval request regardless
  of current status.
- An optional top-level `unknown_statuses` object appears only when the database
  contains execution rows with a status value outside the six known values. The
  frontend should handle its absence gracefully.

## Files to create or modify

**New files:**

- `frontend/src/services/metricsService.js` — exports `getPlaybookMetrics()` which
  calls `GET /metrics/playbooks` using the existing fetch/auth helper pattern.
- `frontend/src/components/PlaybookMetricsPanel.js` — read-only metrics panel.
- `frontend/src/services/metricsService.test.js` — service layer tests.
- `frontend/src/components/PlaybookMetricsPanel.test.js` — component render tests.

**Modified files:**

- `frontend/src/App.js` — add `PlaybookMetricsPanel` to the panel layout using the
  same import and panel registration pattern as other SOAR panels. Do not restructure
  layout, routing, or existing panels.

No backend files, schema files, executor files, queue files, or other frontend files
should change.

## Service helper design

`metricsService.js` should export a single named function:

```js
export async function getPlaybookMetrics() { ... }
```

It should use the same fetch wrapper and auth token pattern already used by
`playbookService.js`, `approvalService.js`, `soarQueueService.js`, and
`integrationService.js`. No retry logic, polling, or background refresh. Returns
parsed JSON on success or throws on non-OK status.

## Component design

`PlaybookMetricsPanel` should:

- Call `getPlaybookMetrics()` on mount via `useEffect`, following the same pattern
  used in other panels.
- Display a loading state while the request is in flight.
- Display a user-friendly error message if the request fails, consistent with error
  rendering in other panels.
- Display an empty state when `total_executions` is `0` and all `by_status` counts
  are `0` (or when the response body is otherwise empty/missing).
- Include a persistent panel-level note that all metrics reflect simulation-only
  playbook executions and that no real integrations or remediation actions have been
  performed. This note must never be conditionally hidden.

### Summary section

Show a top-level summary row or header area containing:

- `total_executions` — labeled "Total Executions"

### Status breakdown section

Render all six known statuses from `by_status` as a compact table or grid:

| Status              | Count |
|---------------------|-------|
| `pending`           | N     |
| `running`           | N     |
| `awaiting_approval` | N     |
| `success`           | N     |
| `failed`            | N     |
| `abandoned`         | N     |

All six statuses should render even when their count is `0`. If `unknown_statuses`
is present in the response, render an additional row labeled "Other / Unknown" with
the aggregated count, and include a tooltip or note that unexpected status values
were encountered.

### Recent activity section

Render the 24-hour window counts with the window clearly labeled:

- "Last 24 hours — Success: N | Failed: N"
- The `recent.time_basis` string from the response may be shown as a secondary note
  or tooltip if it fits the layout, but is not required to be visible by default.

### Approval-gated section

Render approval-gated counts:

- "Currently awaiting approval: N" (from `approval_gated.awaiting_approval`)
- "Ever had a linked approval: N" (from `approval_gated.with_linked_approval`)

### Per-playbook breakdown section

Render one row or card per entry in `by_playbook_id`, sorted as received
(already alphabetical from the backend):

- Playbook ID
- Total executions
- Status counts for the six known statuses (compact, e.g. inline key/value pairs)
- If `other_status_count` is present and greater than `0`, show it labeled as
  "Other: N"

Render a note such as "No playbook-level data available." when `by_playbook_id` is
empty or missing, without hiding the summary, status breakdown, or recent sections.

### What the panel must never render

Under no conditions should the panel render any of the following:

- Run buttons
- Retry buttons
- Cancel or abandon controls
- Approve or deny controls
- Any form input or mutation trigger
- Any link or button that invokes a non-GET endpoint

## Auth and role expectations

- Use the same auth header pattern as other frontend service files.
- The backend already restricts `GET /metrics/playbooks` to analyst and super-admin
  roles using `@analyst_or_super_admin_required`.
- The frontend panel does not need to implement role-gating logic independently.
- If the API returns a 401 or 403, render the same error state used by other panels.

## Loading, error, and empty state behavior

| State     | Trigger                                                          | Render                                                  |
|-----------|------------------------------------------------------------------|---------------------------------------------------------|
| Loading   | Request in flight                                                | Consistent loading indicator matching other panels      |
| Error     | Non-OK response or network failure                               | Error message; no metric rows rendered                  |
| Empty     | `total_executions` is `0` and all status counts are `0`          | "No playbook execution data yet." or equivalent         |
| Populated | At least one non-zero count or a non-empty `by_playbook_id`     | Full panel with all sections                            |

## Safety boundaries

- Panel is strictly read-only with no mutation controls.
- The simulation-only notice must always be visible when the panel is populated.
- The panel must never render a state that implies real remediation occurred.
- Only `GET /metrics/playbooks` is called — no other endpoints.
- No executor, queue, approval, ingest, detection, or correlation paths are invoked.
- No executor behavior changes.
- No schema changes.
- No backend files modified.

## Failure behavior

- API failure renders an error state without crashing the panel or other panels.
- Missing or null top-level fields (`by_status`, `by_playbook_id`, `recent`,
  `approval_gated`) are handled defensively — the panel renders available sections
  and an appropriate partial-data note rather than throwing a JS error.
- A `by_playbook_id` entry missing `by_status` renders without status counts rather
  than crashing.
- An absent `unknown_statuses` key is treated as no unknown statuses — no row rendered.
- An absent `other_status_count` on a per-playbook entry is treated as `0`.

## Test strategy

**Service tests (`metricsService.test.js`):**

- `getPlaybookMetrics()` calls `GET /metrics/playbooks`.
- `getPlaybookMetrics()` returns parsed JSON on a mocked success response.
- `getPlaybookMetrics()` throws on a mocked non-OK response.

**Component tests (`PlaybookMetricsPanel.test.js`):**

- Loading state renders while request is in flight.
- Error state renders on mocked API failure.
- Empty state renders when `total_executions` is `0` and all status counts are `0`.
- `total_executions` is visible in the populated state.
- All six known statuses from `by_status` are rendered, including those with count `0`.
- Recent 24-hour success and failure counts are visible with the window labeled.
- Approval-gated `awaiting_approval` and `with_linked_approval` counts are visible.
- Per-playbook breakdown renders playbook ID and total for each entry.
- Simulation-only notice is always visible in the populated state.
- No run, retry, cancel, approve, or mutation controls are rendered.
- Missing `by_playbook_id` does not crash the component.
- Missing `recent` does not crash the component.
- Missing `approval_gated` does not crash the component.
- `other_status_count` present on a per-playbook entry renders an "Other" label.
- Absent `other_status_count` renders nothing for that label.
- `unknown_statuses` present in the top-level response renders an "Other / Unknown"
  status row.
- Absent `unknown_statuses` renders no such row.

## Risks and stop conditions

- Stop if the service helper requires backend changes to work.
- Stop if `App.js` integration requires layout or routing restructuring beyond adding
  a panel entry and import.
- Stop if the panel cannot persistently label simulation-only mode without backend
  changes.
- Stop if rendering requires calling any endpoint other than `GET /metrics/playbooks`.
- Stop if any mutation control is introduced in any state of the panel.
