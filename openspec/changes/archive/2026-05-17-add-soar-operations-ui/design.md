# Design: SOAR Operations UI

## Architecture Overview

This change is frontend-only (with one conditional read-only backend field addition). It follows the exact component and service patterns established by `SoarQueuePanel`, `ApprovalsPanel`, and `PlaybooksPanel`. No new architectural patterns are introduced.

```
App.js
  soar-operations section (new nav tab, canTakeAlertActions)
    └── DeadLettersPanel (new component)
          ├── Metric cards (GET /metrics/dead-letters)
          ├── Filter bar (status, source_type, failure_class, retryable)
          ├── Dead letter table (GET /dead-letters)
          └── Expandable detail row
                ├── Full field display
                ├── Linked execution link → soar-playbooks section
                ├── Linked incident link → soar-incidents section
                └── Action buttons (dismiss, retry-request, retry-execute)

PlaybooksPanel (modified — execution detail only)
  └── Execution detail
        ├── Existing: steps_log, approval gates, notification delivery history
        ├── New: lease/recovery fields (if API exposes them)
        └── New: linked dead letter summary (GET /dead-letters?execution_id=...)
```

---

## New Files

### `frontend/src/services/deadLetterService.js`

Wraps all dead letter API calls. Follows the same pattern as `playbookService.js` and `notificationDeliveryService.js`.

**Exports:**

```js
listDeadLetters({ status, source_type, failure_class, retryable, incident_id, alert_id, execution_id, limit, offset })
  // GET /dead-letters
  // Returns { items: [...], limit, offset }

getDeadLetter(id)
  // GET /dead-letters/<id>
  // Returns dead letter object

getDeadLetterMetrics()
  // GET /metrics/dead-letters
  // Returns aggregate counts

dismissDeadLetter(id, comment)
  // POST /dead-letters/<id>/dismiss
  // Body: { comment } (optional)
  // Returns updated dead letter

retryRequestDeadLetter(id)
  // POST /dead-letters/<id>/retry-request
  // No body required
  // Returns updated dead letter

retryExecuteDeadLetter(id)
  // POST /dead-letters/<id>/retry-execute
  // No body required
  // Returns { dead_letter, new_execution_id, message }
```

All functions throw on non-OK HTTP responses using `getApiErrorMessage` from `../utils/apiResponse`. All functions use `buildSiemPath` from `../utils/siemPath`. All functions use `credentials: "include"`.

---

### `frontend/src/components/DeadLettersPanel.js`

New component. Receives standard card/filter style props matching existing panels.

**Props:**

```
cardStyle, cardHeaderStyle, cardTitleStyle, cardSubtitleStyle,
filterLabelStyle, selectStyle, userRole
```

`userRole` is passed from App.js exactly as it is to `ApprovalsPanel` and `PlaybooksPanel`.

**State:**

```
metrics: null | { by_status, by_source_type, by_failure_class, oldest_active_at, ... }
items: []
statusFilter: "all"
sourceTypeFilter: "all"
failureClassFilter: "all"
loading: bool
refreshing: bool
error: ""
selectedId: null | number
selectedItem: null | object
detailLoading: bool
detailError: ""
actionError: ""
actionPending: ""   // "dismiss" | "retry-request" | "retry-execute" | ""
actionSuccess: ""
dismissComment: ""
retryExecuteConfirmed: bool
```

**Layout: Metric Cards**

Four summary cards at top, pulled from `GET /metrics/dead-letters`:

```
[ Open ]   [ Retrying ]   [ Retried ]   [ Dismissed ]
```

Values come from `metrics.by_status`. Cards always render; show 0 when empty. Oldest active timestamp shown below cards as a secondary line if `metrics.oldest_active_at` is present.

**Layout: Filter Bar**

Three dropdowns (status, source_type, failure_class) + optional retryable toggle. On change, re-fetches list. Default: all filters set to "all" / unset.

Status options: `all | open | retrying | retried | dismissed`
Source type options: `all | playbook_execution | notification_delivery | response_action | approval`
Failure class options: `all` + values observed in metrics response (populate dynamically from `metrics.by_failure_class` keys).

**Layout: Dead Letter Table**

Columns:

| # | Source Type | Source ID | Failure Class | Status | Retry Count | Created | Actions |
|---|---|---|---|---|---|---|---|

- Clicking a row expands inline detail (same pattern as SoarQueuePanel and PlaybooksPanel).
- Action buttons appear in the table row for quick access and also in the expanded detail.
- Truncate long `failure_class` values; show full value in detail.

**Layout: Expanded Detail**

Full field display:

```
Dead Letter #<id>
Status: <badge>           Source Type: <value>       Source ID: <value>
Created: <timestamp>      Failure Class: <value>     Retry Count: <n>

Error Message: <sanitized text or "—">

Payload (redacted):
  <key-value display of redacted payload_json fields>

Linked Context:
  Execution: #<execution_id>  [View in SOAR Playbooks →]   (if execution_id present)
  Incident:  #<incident_id>   [View in SOAR Incidents →]   (if incident_id present)
  Alert:     #<alert_id>                                    (if alert_id present)
  Playbook:  <playbook_id>                                  (if playbook_id present)
  Step:      index <step_index>, action <action_name>       (if present)

Dismiss Reason: <value or "—">   (if dismissed)
Dismissed At: <timestamp>        (if dismissed)
Retry Requested At: <timestamp>  (if retried)
Retry Executed At: <timestamp>   (if retried)
```

"View in SOAR Playbooks →" and "View in SOAR Incidents →" are informational labels, not programmatic cross-section navigators. They tell the operator where to look; they do not wire inter-panel navigation in this slice. Cross-panel navigation is a follow-up.

**Layout: Action Buttons**

Actions appear below the detail fields. Role-gating follows the backend exactly.

```
[ Dismiss ]         visible to analyst + super_admin; enabled when status is open or retrying
[ Retry Request ]   visible to analyst + super_admin; enabled when status is open
[ Retry Execute ]   visible to super_admin only; enabled when status is retrying AND source_type is playbook_execution
```

**Dismiss flow:**

1. Clicking "Dismiss" expands an optional comment input field inline.
2. A "Confirm Dismiss" button submits; "Cancel" collapses without action.
3. On success: row status badge updates; action buttons re-evaluate.
4. Error shown inline below button row.

**Retry Request flow:**

1. Clicking "Retry Request" immediately calls the API (no intermediate confirm — the action is low-stakes; it only sets intent).
2. Inline feedback: success message or error.
3. Row status badge updates from `open` → `retrying`.

**Retry Execute flow (super_admin only):**

This action has higher stakes — it creates a new pending execution row. The UI must make the semantics explicit before submission.

Confirmation text shown before the user can submit:

```
"Retry Execute creates a new pending playbook execution. No steps will run
immediately. The new execution must be picked up by the next manual executor
invocation (scripts/run_playbook_executor_once.py). This dead letter will
transition to 'retried'. This action cannot be undone."
```

The button is disabled until the user acknowledges by checking an inline checkbox:
`☐ I understand that retry-execute creates pending work only and does not run steps.`

On success: show the returned `new_execution_id`; update dead letter status to `retried`; hide action buttons.

On API error (409, etc.): show the error message from the response body; do not retry automatically.

**Empty, loading, and error states:**

- Full-panel loading spinner on initial load.
- Quiet refresh indicator (not full spinner) on filter change or after action.
- Error banner with "Retry" button if initial load fails.
- Empty state: "No dead letters found" with current filter summary.
- Detail error: inline error in the expanded row; does not collapse the row.

---

## Modified Files

### `frontend/src/components/PlaybooksPanel.js`

Two additive changes to the execution detail section:

**Change 1 — Dead letter linkage:**

When an execution detail is loaded (existing `loadExecution(id)` call), also call `listDeadLetters({ execution_id: id })`. If one or more dead letters exist for this execution, render a read-only "Dead Letter" section in the execution detail:

```
Dead Letter (execution #<id>)
  Status: <badge>    Failure Class: <value>    Created: <timestamp>
  [View in SOAR Operations]  (informational label, not a navigator)
```

If no dead letters exist, this section is omitted entirely. The dead letter call is fire-and-forget with silent failure — if it errors, suppress the section rather than breaking the execution detail.

**Change 2 — Lease/recovery fields:**

If the existing `GET /playbook-executions/<id>` response includes lease/recovery fields, render them in a read-only "Worker Lease" section in the execution detail:

```
Worker Lease
  Lease Owner:       <value or "none">
  Lease Acquired:    <timestamp or "—">
  Lease Expires:     <timestamp or "—">
  Heartbeat:         <timestamp or "—">
  Recovery Count:    <n>
```

Fields are rendered only if at least one of them is non-null in the response. If none are present, the section is omitted.

If the backend does not currently expose these fields in the execution detail response, a small additive change is needed to include them. This must be verified before implementing this sub-slice. The backend change is strictly additive — existing fields, types, and behavior are unchanged.

---

## App.js Changes

**Nav tab** (follows the exact pattern of all existing SOAR tabs):

```jsx
{canTakeAlertActions && (
  <button
    type="button"
    onClick={() => setActiveSection("soar-operations")}
    style={{
      ...sectionTabStyle,
      ...(activeSection === "soar-operations" ? activeSectionTabStyle : inactiveSectionTabStyle),
    }}
  >
    SOAR Operations
  </button>
)}
```

Placed after "SOAR Integrations" in tab order.

**Section render** (follows the exact pattern of all existing SOAR sections):

```jsx
{canTakeAlertActions && activeSection === "soar-operations" && (
  <DeadLettersPanel
    cardStyle={cardStyle}
    cardHeaderStyle={cardHeaderStyle}
    cardTitleStyle={cardTitleStyle}
    cardSubtitleStyle={cardSubtitleStyle}
    filterLabelStyle={filterLabelStyle}
    selectStyle={selectStyle}
    userRole={userRole}
  />
)}
```

**Import:**

```jsx
import DeadLettersPanel from "./components/DeadLettersPanel";
```

No other changes to App.js. `activeSection`, `canTakeAlertActions`, and `userRole` are already present.

---

## Approval Queue Visibility

The existing `ApprovalsPanel` already covers approval list, detail, decision controls, expiration cleanup, event history, and notification delivery history. No changes to `ApprovalsPanel` are in scope.

If an analyst navigating from dead letter detail to approvals needs context, the `linked_approval_id` or `source_id` on the dead letter row provides the link. The dead letter detail's "Linked Context" section shows the execution ID; the analyst can navigate to SOAR Playbooks → execution detail to see the linked approval from there. Cross-panel deep-linking is a follow-up improvement.

---

## Worker / Deploy / Health Visibility

`GET /health/worker` exposes queue depth and last execution timestamp. This is an existing endpoint. No new backend work is needed.

If adding a read-only status card to the dead letter panel summary is desirable (e.g. "Worker last seen: X"), this can be done in a follow-up slice by calling `GET /health/worker` from `deadLetterService.js` without any new backend work. It is not in scope for the initial slices.

---

## Incident Integration

Dead letter detail shows `incident_id`, `alert_id`, and `execution_id` as labeled read-only fields. The operator can use these IDs to navigate directly to the SOAR Incidents or SOAR Playbooks tab.

No programmatic cross-section navigation is implemented in this change. Deep-linking (clicking an incident ID and jumping to that incident's detail in IncidentsPanel) requires a shared navigation callback in App.js and is explicitly deferred to a follow-up.

---

## Safety Boundaries

- No backend behavior changes. Dismiss/retry-request/retry-execute semantics are unchanged; the UI is a thin layer over existing APIs.
- Retry-execute shows mandatory confirmation text and a required checkbox before the button is enabled. The confirmation text must be displayed verbatim as specified above.
- Retry-execute is never shown to analyst role. Role check: `userRole === "super_admin"`.
- The "SOAR Operations" nav tab uses `canTakeAlertActions` (analyst + super_admin). Viewer role does not see it.
- All API calls use `credentials: "include"`. HTTP 403 responses are shown as inline errors, not silent failures.
- The dead letter call in PlaybooksPanel (execution dead letter linkage) is fire-and-forget. Failure is suppressed; it never breaks execution detail loading.
- Lease/recovery fields are read-only display only. No controls to acquire, release, or modify leases from the UI.
- No new backend schema changes in this slice.
- No changes to ingest, detection, or correlation.
- Simulation-mode notice is not required on `DeadLettersPanel` (dead letters are operational records, not simulation artifacts). The existing adapter-simulation notices in `PlaybooksPanel` and `IntegrationStatusPanel` remain unchanged.

---

## Risks Before Implementation

1. **Lease/recovery fields may not be in API response.** Verify `GET /playbook-executions/<id>` response shape before implementing the lease section. If not present, a minimal backend additive change is needed before that sub-slice.

2. **Dead letter `retryable` flag is hardcoded `False`.** The filter UI can still offer a retryable toggle, but the backend returns all rows as `retryable: false` today. The filter will return empty results until the backend is updated (tracked separately as Priority 4 in the handoff). Document this in the panel.

3. **`failure_class` values are not enum-constrained.** Populate the failure class filter dropdown from observed values in the metrics response rather than a hardcoded list. If metrics are empty, show only "all".

4. **Dismiss is allowed to analyst.** This is correct per the backend (`@analyst_or_super_admin_required`). The UI must mirror this — do not restrict dismiss to super_admin only.

5. **Retry-execute creates a pending row; execution is CLI-only.** The confirmation text and required acknowledgment checkbox are mandatory. Do not allow submission without them.

6. **Nav tab count.** The nav already has 10+ tabs. Verify the UI renders correctly on smaller screens before merging; no responsive layout changes are in scope but visual regression testing is recommended.

7. **No loading race condition on filter changes.** Debounce or cancel in-flight requests when filters change rapidly (particularly the failure_class filter populated from metrics).
