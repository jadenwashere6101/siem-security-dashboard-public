# Proposal: SOAR Incident Visibility UI

## Problem

Incident schema, store, API routes, and post-commit detection wiring are all complete. HIGH and
CRITICAL detection alerts automatically create or link incidents after commit. But there is no
frontend surface. Analysts cannot see incidents, track their status, or navigate from an
incident to its linked alerts. The backend incident layer is invisible to the people who need
to use it.

## This change

Add a read-only incident panel to the frontend that surfaces the incident list, incident
detail, and linked alerts. Include a status update control so analysts can move an incident
through its lifecycle without leaving the dashboard.

## In scope

- `frontend/src/services/incidentService.js` with three functions:
  - `loadIncidents({ status, severity, limit, offset })`
  - `loadIncidentDetail(id)`
  - `updateIncidentStatus(id, status)`
- `frontend/src/components/IncidentsPanel.js` — the full panel component:
  - Incident list with status/severity filters
  - Inline detail view (right pane or expanded row) showing all incident fields plus linked
    alerts table
  - Status update control visible to analysts and super_admins
  - Loading, empty, and error states for list and detail
- `App.js` wiring: nav tab + conditional render, gated to `canTakeAlertActions`
- Service tests: `incidentService.test.js`
- Component tests: `IncidentsPanel.test.js`

## Out of scope

- No playbooks, approval workflows, or queue mutation controls.
- No alert modification — the UI must not call any alert-mutation endpoint.
- No real firewall execution.
- No Slack or email.
- No correlation incident creation.
- No backend or schema changes.
- No new auth decorators or role changes — the backend already enforces
  `analyst_or_super_admin_required` on all incident routes.

## Role access

The `soar-queue` tab is `isSuperAdmin` only. Incidents are different — analysts are the
primary users of case management. The nav tab and component render are gated to
`canTakeAlertActions` (analyst or super_admin), consistent with how the blocklist and
threat-hunt tabs are gated.

The status update control is also available to `canTakeAlertActions`. The backend enforces
the role independently — the frontend just passes `canTakeAlertActions` as a prop to
conditionally render the control.

## Success criteria

- Frontend build passes with no new errors.
- The Incidents tab appears in the nav for analyst and super_admin roles.
- The Incidents tab does not appear for viewer role.
- Incident list loads and displays title, severity, priority, status, source IP,
  linked alert count, and created_at.
- Clicking an incident row loads the detail view.
- Detail view shows all incident fields and the linked alerts table.
- `null` resolved_at renders as a safe empty/dash value, not a crash.
- An empty incident list renders a "No incidents found" message, not a blank panel.
- Linked alerts table in detail renders "No linked alerts" when the list is empty.
- Status update dropdown and submit button appear for analyst/super_admin.
- Status update calls only `POST /incidents/<id>/status`. On success the detail refreshes.
- Backend error on status update (invalid transition) is shown inline — not a crash.
- Status update control does not appear for viewer role (even if `canTakeAlertActions`
  prop is false).
- Service tests cover all three functions including error paths.
- Component tests cover loading, empty, error, list render, detail render, and status update.
