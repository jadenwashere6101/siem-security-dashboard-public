# Tasks: SOAR Incident Visibility UI

Verify the frontend build passes after every step: `cd frontend && npm run build`.
Run frontend tests after Steps 2, 3, and 5: `cd frontend && npm test -- --watchAll=false`.

---

## Step 1: Implement `frontend/src/services/incidentService.js`

- [x] Create `frontend/src/services/incidentService.js`.
  - Import `getApiErrorMessage`, `parseJsonResponse` from `../utils/apiResponse`.
  - Import `buildSiemPath` from `../utils/siemPath`.

- [x] Implement `loadIncidents({ status, severity, limit = 50, offset = 0 } = {})`.
  - Build query params: include `status` only if not `"all"` and not falsy.
  - Include `severity` only if not `"all"` and not falsy.
  - Include `limit`, `offset`.
  - Fetch `buildSiemPath("/incidents?...")` with `credentials: "include"`.
  - `parseJsonResponse(res, { incidents: [], count: 0 })`.
  - Throw on `!res.ok` using `getApiErrorMessage(data, "Unable to load incidents", ["error"])`.
  - Return `data`.

- [x] Implement `loadIncidentDetail(incidentId)`.
  - Fetch `buildSiemPath("/incidents/" + incidentId)` with `credentials: "include"`.
  - `parseJsonResponse(res, {})`.
  - Throw on `!res.ok`.
  - Return `data`.

- [x] Implement `updateIncidentStatus(incidentId, status)`.
  - POST to `buildSiemPath("/incidents/" + incidentId + "/status")`.
  - `credentials: "include"`, `Content-Type: application/json`, body `JSON.stringify({ status })`.
  - `parseJsonResponse(res, {})`.
  - Throw on `!res.ok` using `getApiErrorMessage(data, "Unable to update incident status", ["error"])`.
  - Return `data`.

- [x] Run build — passes with no errors.

---

## Step 2: Test `frontend/src/services/incidentService.test.js`

- [x] Create `frontend/src/services/incidentService.test.js`.
  - Mock `fetch` globally (consistent with existing service test patterns).
  - Import all three functions from `incidentService`.

- [x] `loadIncidents` tests:
  - No filters: fetches `/incidents` — no extra query params.
  - `status: "open"` → `?status=open` in URL.
  - `status: "all"` → no `status` param in URL.
  - `severity: "high"` → `?severity=high` in URL.
  - Both filters → both params present.
  - Success: returns the parsed data object.
  - `!res.ok`: throws with message from response `error` field.

- [x] `loadIncidentDetail` tests:
  - Fetches `/incidents/42` for `id=42`.
  - Success: returns parsed data.
  - `!res.ok`: throws.

- [x] `updateIncidentStatus` tests:
  - POSTs to `/incidents/42/status`.
  - Request body contains `{ "status": "investigating" }`.
  - `Content-Type: application/json` header is set.
  - Success: returns parsed data.
  - `!res.ok` (400 invalid transition): throws with backend error message.

- [x] Run `npm test -- --watchAll=false` — all service tests green.

---

## Step 3: Implement `frontend/src/components/IncidentsPanel.js`

Read `SoarQueuePanel.js` before implementing — match the structural and styling conventions.

- [x] Create `frontend/src/components/IncidentsPanel.js`.
  - Imports: `React`, `{ useCallback, useEffect, useState }`, service functions, `formatAdminTimestamp`.

- [x] Define constants at module level:
  ```javascript
  const INCIDENT_STATUS_FILTERS = ["all", "open", "investigating", "resolved", "closed"];
  const INCIDENT_SEVERITY_FILTERS = ["all", "LOW", "MEDIUM", "HIGH", "CRITICAL"];
  const INCIDENT_STATUSES = ["open", "investigating", "resolved", "closed"];
  ```

- [x] Implement component state (as listed in design.md).

- [x] Implement `loadIncidentList` (useCallback):
  - Quiet vs. initial load flag.
  - Calls `loadIncidents({ status: statusFilter, severity: severityFilter })`.
  - Sets `incidents` from `data.incidents` (guard with `Array.isArray`).
  - Sets `error` on failure.

- [x] Implement `loadDetail` (useCallback):
  - Calls `loadIncidentDetail(selectedIncidentId)`.
  - Sets `selectedIncident` from `data.incident`.
  - Pre-populates `pendingStatus` with `data.incident.status`.
  - Sets `detailError` on failure.

- [x] Implement `handleStatusUpdate`:
  - Guard: no-op if `pendingStatus === selectedIncident?.status`.
  - Sets `updatingStatus(true)`, clears `statusUpdateError`.
  - Calls `updateIncidentStatus(selectedIncidentId, pendingStatus)`.
  - On success: calls `loadDetail(selectedIncidentId)` then `loadIncidentList({ quiet: true })`.
  - On error: sets `statusUpdateError`.
  - `finally`: sets `updatingStatus(false)`.

- [x] Implement `useEffect` for initial load on mount and filter changes.

- [x] Implement `useEffect` for detail load when `selectedIncidentId` changes.

- [x] Implement JSX:
  - Header: title + Refresh button.
  - Filter row: status filter `<select>`, severity filter `<select>`.
  - Loading state: "Loading incidents..."
  - Error state: error message + Retry button.
  - Empty state: "No incidents found."
  - Incident list table:
    - Columns: ID, Title (truncated), Severity, Priority, Status, Source IP, Created.
    - Row click: `setSelectedIncidentId(incident.id)`. Highlight selected row.
  - Detail panel (renders when `selectedIncident` is not null):
    - Header: incident title + Close button (`setSelectedIncidentId(null)`, `setSelectedIncident(null)`).
    - Fields: Severity, Priority, Status, Source IP, Created, Resolved.
    - Resolved: `resolved_at ? formatAdminTimestamp(resolved_at) : "—"`.
    - Linked alerts sub-table:
      - Columns: Alert ID, Type, Severity, Status, Linked At.
      - Empty: "No linked alerts."
    - Status update section (only if `canTakeAlertActions`):
      - Label: "Update status:"
      - `<select>` over `INCIDENT_STATUSES`, value = `pendingStatus`.
      - Submit button: "Update Status", disabled when `updatingStatus` or
        `pendingStatus === selectedIncident.status`.
      - Inline error: `statusUpdateError && <div ...>{statusUpdateError}</div>`.
  - Detail loading state: "Loading incident..."
  - Detail error state: error message.

- [x] Run build — passes.

---

## Step 4: Test `frontend/src/components/IncidentsPanel.test.js`

Read `SoarQueuePanel.test.js` before implementing — match the test structure and fixture conventions.

- [x] Create `frontend/src/components/IncidentsPanel.test.js`.
  - `jest.mock("../services/incidentService", ...)`.
  - Define `incidentFixture` and `incidentDetailFixture` (as specified in design.md).
  - Define `renderPanel` helper with required props.

- [x] Loading state test:
  - `loadIncidents` returns a never-resolving promise.
  - `"Loading incidents..."` is in the document.

- [x] Error state test:
  - `loadIncidents` rejects with `new Error("load failed")`.
  - Error message is in the document after `waitFor`.

- [x] Empty state test:
  - `loadIncidents` resolves with `{ incidents: [], count: 0 }`.
  - `"No incidents found."` is in the document.

- [x] List render test:
  - `loadIncidents` resolves with one `incidentFixture`.
  - Incident title is visible. Severity, status, source_ip visible.

- [x] Filter change re-fetches test:
  - Change status filter dropdown. Confirm `loadIncidents` is called again with the new status.

- [x] Row click loads detail test:
  - `loadIncidents` resolves with one fixture.
  - `loadIncidentDetail` set up to return `incidentDetailFixture`.
  - Click the row. Confirm `loadIncidentDetail` called with correct ID.

- [x] Detail loading state test:
  - After row click, `loadIncidentDetail` pending → "Loading incident..." visible.

- [x] Detail error state test:
  - `loadIncidentDetail` rejects → detail error message visible.

- [x] Detail render test:
  - `loadIncidentDetail` resolves → title, severity, priority, source_ip, created_at visible.

- [x] Detail `resolved_at` null test:
  - Fixture has `resolved_at: null` → `"—"` visible, no crash.

- [x] Detail linked alerts test:
  - `incidentDetailFixture` has one alert → `alert_type` and alert status visible in sub-table.

- [x] Detail no linked alerts test:
  - Detail fixture with `alerts: []` → `"No linked alerts."` visible.

- [x] Status update control visible test:
  - Rendered with `canTakeAlertActions={true}` and detail loaded.
  - Status select and "Update Status" button are in the document.

- [x] Status update control hidden test:
  - Rendered with `canTakeAlertActions={false}`.
  - "Update Status" button is NOT in the document.

- [x] Status update success test:
  - `updateIncidentStatus` resolves.
  - Change select to a different status, click "Update Status".
  - `updateIncidentStatus` called with correct ID and status.
  - `loadIncidentDetail` called again (detail refreshed).

- [x] Status update error test:
  - `updateIncidentStatus` rejects with `new Error("invalid status transition")`.
  - Error message visible after submit.

- [x] Close detail test:
  - Click the close button in detail panel.
  - Detail panel is no longer in the document.

- [x] Run `npm test -- --watchAll=false` — all tests green.

---

## Step 5: Wire into App.js

Read `App.js` before making any changes.

- [x] Add import at the top of `App.js`:
  ```javascript
  import IncidentsPanel from "./components/IncidentsPanel";
  ```

- [x] Add nav tab after the `soar-queue` tab block:
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
  Confirm `baseTabStyle` (or equivalent) variable name by reading the existing tab blocks.

- [x] Add conditional render after the `soar-queue` render block:
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
  Confirm exact style variable names by reading the `SoarQueuePanel` render call in App.js.

- [x] Confirm no other App.js logic was changed.
- [x] Run build — passes.
- [x] Run `npm test -- --watchAll=false` — all tests still green.

---

## Step 6: Final audit

- [x] Confirm only these files were created or modified:
  - `frontend/src/services/incidentService.js` — new file.
  - `frontend/src/services/incidentService.test.js` — new file.
  - `frontend/src/components/IncidentsPanel.js` — new file.
  - `frontend/src/components/IncidentsPanel.test.js` — new file.
  - `frontend/src/App.js` — import + nav tab + conditional render only.
- [x] Confirm `IncidentsPanel.js` imports nothing from `soarQueueService`, `alertsService`,
  `alertStatusService`, or any other mutation service.
- [x] Confirm `updateIncidentStatus` is the only POST call made from the panel.
- [x] Confirm `resolved_at` null is handled before every `formatAdminTimestamp` call.
- [x] Run full build and test suite — clean.
