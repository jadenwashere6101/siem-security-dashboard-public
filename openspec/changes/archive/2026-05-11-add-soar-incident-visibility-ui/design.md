# Design: SOAR Incident Visibility UI

---

## Current state (context only)

The frontend uses React 19 with Create React App. Navigation is state-driven — no router
library. `App.js` holds `activeSection` state and conditionally renders panels based on it.
Role state (`isSuperAdmin`, `isAnalyst`, `canTakeAlertActions`) is held at App.js level and
passed as props. All styling is inline.

The existing closest analog to this panel is `SoarQueuePanel.js`. The service pattern follows
`soarQueueService.js` exactly — `fetch` with `credentials: "include"`, `buildSiemPath()` for
URL construction, `parseJsonResponse()` for body parsing, `getApiErrorMessage()` for error
extraction.

The SOAR queue tab is gated to `isSuperAdmin`. This panel uses `canTakeAlertActions` instead,
because analysts are the primary users of incident management.

---

## `frontend/src/services/incidentService.js`

Three exported functions. Pattern mirrors `soarQueueService.js` exactly.

```javascript
import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadIncidents = async ({
  status,
  severity,
  limit = 50,
  offset = 0,
} = {}) => {
  const params = new URLSearchParams();
  if (status && status !== "all") params.set("status", status);
  if (severity && severity !== "all") params.set("severity", severity);
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  const query = params.toString();

  const res = await fetch(
    buildSiemPath(`/incidents${query ? `?${query}` : ""}`),
    { credentials: "include" }
  );
  const data = await parseJsonResponse(res, { incidents: [], count: 0 });

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load incidents", ["error"])
    );
  }
  return data;
};

export const loadIncidentDetail = async (incidentId) => {
  const res = await fetch(buildSiemPath(`/incidents/${incidentId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load incident detail", ["error"])
    );
  }
  return data;
};

export const updateIncidentStatus = async (incidentId, status) => {
  const res = await fetch(buildSiemPath(`/incidents/${incidentId}/status`), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update incident status", ["error"])
    );
  }
  return data;
};
```

---

## `frontend/src/components/IncidentsPanel.js`

### Props

```javascript
function IncidentsPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  canTakeAlertActions,
})
```

`canTakeAlertActions` is the only role prop needed. It controls whether the status update
control is rendered. The nav tab and conditional render in App.js already ensure only the
correct roles can reach this component — `canTakeAlertActions` is just for the mutation
control inside.

### State

```javascript
const [incidents, setIncidents] = useState([]);
const [loading, setLoading] = useState(true);
const [refreshing, setRefreshing] = useState(false);
const [error, setError] = useState("");
const [statusFilter, setStatusFilter] = useState("all");
const [severityFilter, setSeverityFilter] = useState("all");
const [selectedIncidentId, setSelectedIncidentId] = useState(null);
const [selectedIncident, setSelectedIncident] = useState(null);
const [detailLoading, setDetailLoading] = useState(false);
const [detailError, setDetailError] = useState("");
const [pendingStatus, setPendingStatus] = useState("");
const [updatingStatus, setUpdatingStatus] = useState(false);
const [statusUpdateError, setStatusUpdateError] = useState("");
```

### Data loading

`loadIncidentList` (useCallback, quiet flag for refreshes):
- On initial load: `setLoading(true)`.
- On refresh: `setRefreshing(true)`.
- Calls `loadIncidents({ status: statusFilter, severity: severityFilter })`.
- Sets `incidents` from `data.incidents`.
- On error: sets `error`, clears incidents only on non-quiet load.

`loadDetail` (useCallback):
- Called when `selectedIncidentId` changes (useEffect dependency).
- Calls `loadIncidentDetail(selectedIncidentId)`.
- Sets `selectedIncident` from `data.incident`.
- Sets `pendingStatus` to `selectedIncident.status` (pre-populate dropdown).
- On error: sets `detailError`.

`handleStatusUpdate`:
- Guards: if `!pendingStatus` or `pendingStatus === selectedIncident.status`, no-op.
- Sets `updatingStatus(true)`, clears `statusUpdateError`.
- Calls `updateIncidentStatus(selectedIncidentId, pendingStatus)`.
- On success: re-calls `loadDetail(selectedIncidentId)` to refresh detail, then re-calls
  `loadIncidentList({ quiet: true })` to refresh the list status column.
- On error: sets `statusUpdateError` from the thrown error message.
- Always sets `updatingStatus(false)` in finally.

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ SOAR Incidents                            [Refresh]         │
├───────────────────┬───────────────────┬─────────────────────┤
│ Status: [all ▼]   │ Severity: [all ▼] │                     │
├───────────────────┴───────────────────┴─────────────────────┤
│ [loading state / error state / empty state]                 │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ ID  │ Title  │ Sev  │ Pri │ Status │ Source IP │ Alerts │ │
│ │  1  │ [AUTO] │ HIGH │ P2  │ open   │ 1.2.3.4   │  3     │ │
│ │  2  │ [AUTO] │ CRIT │ P1  │ invest │ 5.6.7.8   │  1     │ │
│ └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

[When incident row clicked → detail panel opens below or to the right]

┌─────────────────────────────────────────────────────────────┐
│ Incident #1 — [AUTO] HIGH alert from 1.2.3.4  [✕ Close]    │
├─────────────────────────────────────────────────────────────┤
│ Severity: HIGH     Priority: P2    Status: open             │
│ Source IP: 1.2.3.4                                          │
│ Created: 2026-05-07 14:32:01 UTC                            │
│ Resolved: —                                                 │
├─────────────────────────────────────────────────────────────┤
│ Linked Alerts (3)                                           │
│  Alert ID │ Type              │ Sev  │ Status │ Linked At  │
│  42       │ failed_login_t... │ HIGH │ open   │ 14:32:01   │
│  43       │ password_spray... │ HIGH │ open   │ 14:35:11   │
│  44       │ failed_login_t... │ HIGH │ open   │ 14:40:22   │
├─────────────────────────────────────────────────────────────┤
│ [canTakeAlertActions only]                                   │
│ Update status: [investigating ▼]  [Update Status]           │
│ [inline error if transition rejected]                        │
└─────────────────────────────────────────────────────────────┘
```

### Incident list table columns

| Column | Source field | Notes |
|---|---|---|
| ID | `incident.id` | |
| Title | `incident.title` | Truncate at ~40 chars with `…` |
| Severity | `incident.severity` | Uppercase display |
| Priority | `incident.priority` | |
| Status | `incident.status` | |
| Source IP | `incident.source_ip` | |
| Alerts | Count from linked alerts — not directly on list response | Backend `GET /incidents` does **not** return alert count. See note below. |
| Created | `incident.created_at` | Use `formatAdminTimestamp()` from existing utils |

**Linked alert count note:** `GET /incidents` returns incident-level data only — it does not
return a linked alert count. Options:
1. Omit the count column from the list view (simplest, cleanest).
2. Fetch counts with a separate call per row (n+1, expensive, don't do this).
3. Accept the count is only visible in the detail view.

**Recommended: omit the count column from the list.** Show count in the detail panel header
once the detail is loaded. The list becomes leaner and the detail stays the authoritative
source for alert linkage.

### Status update control

Only renders when `canTakeAlertActions` is true. Placement: bottom section of the detail
panel.

```javascript
const INCIDENT_STATUSES = ["open", "investigating", "resolved", "closed"];
```

Dropdown: `<select>` over `INCIDENT_STATUSES`. Pre-populated to the incident's current
status on detail load. The implementer should NOT attempt to enforce the transition table
client-side — the backend rejects invalid transitions with a 400 and a message. The frontend
displays that message as `statusUpdateError`. This avoids duplicating transition logic and
means the frontend is always correct even if the backend transition rules change.

Submit button label: "Update Status". Disabled while `updatingStatus` is true or while
`pendingStatus === selectedIncident.status` (no change).

### Empty and error states

**List empty state:** When `incidents.length === 0` and not loading:
```
No incidents found.
```

**List error state:** When `error` is set:
```
Error: {error}
```
with a Retry button that calls `loadIncidentList({ quiet: false })`.

**Detail loading state:**
```
Loading incident...
```

**Detail error state:**
```
Error loading incident: {detailError}
```

**Detail: no linked alerts:**
```
No linked alerts.
```

**`resolved_at` null handling:** Render `—` (em dash) when `resolved_at` is null. Never pass
null directly to `formatAdminTimestamp()` without a null check.

---

## App.js wiring

### Nav tab addition

Add after the existing `soar-queue` tab block (which is `isSuperAdmin` only):

```javascript
{canTakeAlertActions && (
  <div
    onClick={() => setActiveSection("soar-incidents")}
    style={{
      ...baseTabStyle,
      ...(activeSection === "soar-incidents"
        ? activeSectionTabStyle
        : inactiveSectionTabStyle),
    }}
  >
    SOAR Incidents
  </div>
)}
```

### Conditional render addition

Add after the `soar-queue` render block:

```javascript
{canTakeAlertActions && activeSection === "soar-incidents" && (
  <IncidentsPanel
    cardStyle={cardStyle}
    cardHeaderStyle={cardHeaderStyle}
    cardTitleStyle={cardTitleStyle}
    cardSubtitleStyle={cardSubtitleStyle}
    filterLabelStyle={filterLabelStyle}
    selectStyle={selectStyle}
    canTakeAlertActions={canTakeAlertActions}
  />
)}
```

Import at the top of App.js:
```javascript
import IncidentsPanel from "./components/IncidentsPanel";
```

Read App.js before modifying to confirm the exact location of the `soar-queue` block and the
style variables that need to be passed. The style variables (`cardStyle`, `filterLabelStyle`,
etc.) are defined inline in App.js — confirm the names before adding the render call.

---

## `frontend/src/services/incidentService.test.js`

Pattern: mirrors `soarQueueService.test.js`. Mock `fetch` globally.

Tests:

**`loadIncidents`**
- No filters: fetches `/incidents` with no query string.
- Status filter `"open"`: query includes `status=open`.
- Status filter `"all"`: query omits `status` param.
- Severity filter `"high"`: query includes `severity=high`.
- Both filters: query includes both params.
- Returns `data.incidents` array on success.
- Non-ok response: throws with message from `getApiErrorMessage`.

**`loadIncidentDetail`**
- Fetches `/incidents/<id>`.
- Returns `data.incident` on success.
- Non-ok response: throws.

**`updateIncidentStatus`**
- POSTs to `/incidents/<id>/status` with `{ "status": "investigating" }` body.
- Sets `Content-Type: application/json`.
- Returns response data on success.
- Non-ok response (e.g., 400 invalid transition): throws with backend error message.

---

## `frontend/src/components/IncidentsPanel.test.js`

Pattern: mirrors `SoarQueuePanel.test.js`. `jest.mock` the service module. Use fixtures.

**Fixtures:**

```javascript
const incidentFixture = {
  id: 1,
  title: "[AUTO] HIGH alert from 1.2.3.4",
  severity: "HIGH",
  priority: "P2",
  status: "open",
  source_ip: "1.2.3.4",
  assigned_to: null,
  created_at: "2026-05-07T14:32:01Z",
  resolved_at: null,
};

const incidentDetailFixture = {
  ...incidentFixture,
  alerts: [
    {
      alert_id: 42,
      alert_type: "failed_login_threshold",
      severity: "HIGH",
      source_ip: "1.2.3.4",
      status: "open",
      created_at: "2026-05-07T14:32:00Z",
      linked_at: "2026-05-07T14:32:01Z",
    },
  ],
};
```

**Tests:**

- Loading state: `loadIncidents` pending → "Loading incidents..." visible.
- Error state: `loadIncidents` rejects → error message visible, no table rendered.
- Empty state: `loadIncidents` resolves with `{ incidents: [], count: 0 }` → "No incidents found."
- List render: resolves with one incident → title, severity, status, source_ip visible in the table.
- Status filter change: changing the status dropdown re-calls `loadIncidents` with the new status.
- Row click loads detail: clicking a row calls `loadIncidentDetail` with the correct ID.
- Detail loading state: `loadIncidentDetail` pending → "Loading incident..." visible.
- Detail error state: `loadIncidentDetail` rejects → detail error message visible.
- Detail render: resolves → incident title, severity, priority, source_ip, created_at visible in detail.
- Detail resolved_at null: renders `—` not a crash.
- Detail linked alerts: detail fixture with one alert → alert_type and status visible.
- Detail no linked alerts: fixture with `alerts: []` → "No linked alerts." visible.
- Status update control visible: rendered with `canTakeAlertActions={true}` → select and button visible.
- Status update control hidden: rendered with `canTakeAlertActions={false}` → select and button absent.
- Status update success: select changes, button clicked, `updateIncidentStatus` called, detail reloads.
- Status update error: `updateIncidentStatus` rejects → inline error message visible.
- Close detail: clicking close/dismiss clears selected incident, hides detail panel.
- Refresh button: calls `loadIncidents` again (quiet).

---

## Safety controls

- `incidentService.js` calls only `GET /incidents`, `GET /incidents/<id>`, and
  `POST /incidents/<id>/status`. No other endpoints.
- `IncidentsPanel.js` imports only from `incidentService.js`. It does not import from
  `soarQueueService.js`, `alertsService.js`, `alertStatusService.js`, or any mutation service.
- The status update handler calls `updateIncidentStatus` only — not `runSoarWorkerOnce` or
  any queue endpoint.
- No `dangerouslySetInnerHTML` usage.
- All `null` fields from the API (resolved_at, assigned_to, alert_id on a deleted alert) are
  explicitly guarded before rendering.

---

## Risks

**1. Style prop names in App.js.**
The exact names of the style props passed to panels (`cardStyle`, `filterLabelStyle`, etc.)
must be confirmed by reading App.js before the render call is added. If the variable names
differ from what's listed here, the panel will render with no styles. Read the existing
`SoarQueuePanel` render call in App.js and mirror it exactly.

**2. `canTakeAlertActions` not currently passed to panels that receive it by convention.**
`SoarQueuePanel` does not receive `canTakeAlertActions` because it is already gated to
`isSuperAdmin`. Confirm by reading the existing render call that `canTakeAlertActions` is
available as a local variable in App.js render scope before passing it as a prop. It is
defined at line ~201 — it will be in scope.

**3. `formatAdminTimestamp` may not handle null gracefully.**
Existing usage of `formatAdminTimestamp` in SoarQueuePanel passes non-null timestamps. If
the utility does not guard against null input, passing `resolved_at` (which is null until
resolved) will throw. Add a null check at the call site:
```javascript
resolved_at ? formatAdminTimestamp(resolved_at) : "—"
```

**4. Backend returns `source_ip` as a string from psycopg2 serialization.**
The `GET /incidents` response will return `source_ip` as a JSON string. No special handling
needed — render it directly.

**5. `GET /incidents` does not return linked alert count.**
As noted in the design, the list endpoint returns incident-level data only. The count column
is omitted from the list view by design. Do not add a per-row `GET /incidents/<id>` call to
fetch counts — this would be an n+1 problem that would make every page load fire 50+ requests.
