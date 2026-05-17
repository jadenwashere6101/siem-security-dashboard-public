# Tasks: SOAR Operations UI

Implementation must proceed slice-by-slice. Do not implement from this file without reading `proposal.md` and `design.md` first.

After every slice: run the full frontend test suite and the backend ingest/detection/correlation regression suite before proceeding.

---

## Pre-Implementation Review

- [x] Audit existing frontend components: SoarQueuePanel, ApprovalsPanel, PlaybooksPanel, IntegrationStatusPanel.
- [x] Audit existing service files: playbookService.js, notificationDeliveryService.js, approvalService.js.
- [x] Confirm dead letter backend routes, access control, and response shapes (dead_letter_routes.py).
- [x] Confirm App.js section/nav wiring pattern.
- [x] Confirm `userRole` is passed as prop in ApprovalsPanel and PlaybooksPanel (pattern to follow).
- [x] Confirm `buildSiemPath` and `parseJsonResponse` patterns from existing service files.
- [ ] Verify `GET /playbook-executions/<id>` response shape — confirm whether `lease_owner`, `lease_expires_at`, `recovery_count` are included. If not, note as a prerequisite for Slice 5 sub-task only.

---

## Slice 1 — `deadLetterService.js`

Goal: Create the service file that wraps all six dead letter API calls. No UI changes.

- [ ] Create `frontend/src/services/deadLetterService.js`.
- [ ] Export `listDeadLetters(filters)` → `GET /dead-letters` with all supported query params.
- [ ] Export `getDeadLetter(id)` → `GET /dead-letters/<id>`.
- [ ] Export `getDeadLetterMetrics()` → `GET /metrics/dead-letters`.
- [ ] Export `dismissDeadLetter(id, comment)` → `POST /dead-letters/<id>/dismiss`.
- [ ] Export `retryRequestDeadLetter(id)` → `POST /dead-letters/<id>/retry-request`.
- [ ] Export `retryExecuteDeadLetter(id)` → `POST /dead-letters/<id>/retry-execute`.
- [ ] Follow exact import/error pattern of `notificationDeliveryService.js` (`getApiErrorMessage`, `parseJsonResponse`, `buildSiemPath`, `credentials: "include"`).
- [ ] Create `frontend/src/services/deadLetterService.test.js`.
  - [ ] Test `listDeadLetters` serializes all filter params correctly.
  - [ ] Test `getDeadLetter` uses correct URL.
  - [ ] Test `dismissDeadLetter` sends `comment` in body.
  - [ ] Test `retryExecuteDeadLetter` throws on non-201 response.
  - [ ] Test each function throws with API error message on non-OK response.

**Verification:** `npm test -- --testPathPattern=deadLetterService` passes. No other tests affected.

---

## Slice 2 — `DeadLettersPanel` Read-Only List and Detail

Goal: Render dead letter list and expandable detail. No action buttons yet.

- [ ] Create `frontend/src/components/DeadLettersPanel.js`.
- [ ] Accept props: `cardStyle`, `cardHeaderStyle`, `cardTitleStyle`, `cardSubtitleStyle`, `filterLabelStyle`, `selectStyle`, `userRole`.
- [ ] On mount: call `getDeadLetterMetrics()` and `listDeadLetters({})` in parallel.
- [ ] Render four summary metric cards: open, retrying, retried, dismissed — always visible, zero when empty.
- [ ] Render oldest active timestamp below metric cards when `oldest_active_at` is present.
- [ ] Render filter bar: status dropdown, source_type dropdown, failure_class dropdown (populated from `metrics.by_failure_class` keys).
- [ ] On filter change: re-fetch list with updated filters.
- [ ] Render dead letter table with columns: ID, Source Type, Source ID, Failure Class, Status badge, Retry Count, Created.
- [ ] Clicking a table row selects it and fetches detail via `getDeadLetter(id)`.
- [ ] Render expanded detail below the selected row (same expand-in-place pattern as `SoarQueuePanel`).
- [ ] Detail shows: all safe fields, redacted `payload_json` as key-value pairs, redacted `error_message`, `dismiss_reason`, timestamps.
- [ ] Render "Linked Context" section if any of `execution_id`, `incident_id`, `alert_id`, `playbook_id`, `action_name`, `step_index` are non-null.
  - Each linked field shows the ID/value and a static label: "View in SOAR Playbooks" (for execution), "View in SOAR Incidents" (for incident). Labels are informational text only, not navigation callbacks.
- [ ] Loading: full-panel spinner on initial load; quiet refresh indicator on filter change.
- [ ] Error: banner with "Retry" button if initial metrics or list load fails.
- [ ] Empty state: "No dead letters found" message with current filter summary.
- [ ] Detail error: inline error inside expanded row; does not collapse.
- [ ] Create `frontend/src/components/DeadLettersPanel.test.js`.
  - [ ] Test renders metric cards with correct counts.
  - [ ] Test renders table rows from list response.
  - [ ] Test row selection triggers detail fetch.
  - [ ] Test expanded detail renders safe fields.
  - [ ] Test empty state renders when list is empty.
  - [ ] Test filter change re-fetches list with updated params.
  - [ ] Test API error shows error banner.
  - [ ] Test detail fetch error shows inline error.
  - [ ] Test linked context section renders execution_id and incident_id labels.
  - [ ] Test linked context section is omitted when all IDs are null.

**Verification:** `npm test -- --testPathPattern=DeadLettersPanel` passes. No existing panel tests affected.

---

## Slice 3 — Dismiss and Retry-Request Actions

Goal: Add dismiss and retry-request controls. Both are available to analyst and super_admin.

- [ ] Add `actionPending`, `actionError`, `actionSuccess`, `dismissComment` state to `DeadLettersPanel`.
- [ ] Render "Dismiss" button in expanded detail when `status` is `open` or `retrying` AND user is analyst or super_admin.
  - Clicking "Dismiss" expands an inline comment input field.
  - Comment is optional.
  - "Confirm Dismiss" submits; "Cancel" collapses without action.
  - On success: update selected item status in state; show success message; clear action state.
  - On error: show inline error; preserve dismiss form state.
- [ ] Render "Retry Request" button in expanded detail when `status` is `open` AND user is analyst or super_admin.
  - Clicking immediately calls `retryRequestDeadLetter(id)`. No intermediate confirm.
  - On success: update selected item status from `open` → `retrying`; show success message.
  - On error: show inline error.
- [ ] After dismiss or retry-request success: quietly refresh the list (`loadDeadLetters({ quiet: true })`).
- [ ] Disable both action buttons while `actionPending` is set.
- [ ] Add tests to `DeadLettersPanel.test.js`:
  - [ ] Test "Dismiss" button is visible for analyst and super_admin when status is open.
  - [ ] Test "Dismiss" button is hidden when status is retried or dismissed.
  - [ ] Test dismiss comment input appears on button click.
  - [ ] Test "Confirm Dismiss" calls `dismissDeadLetter` with comment.
  - [ ] Test dismiss success updates status badge in detail.
  - [ ] Test dismiss API error shows inline error without collapsing row.
  - [ ] Test "Retry Request" button is visible when status is open.
  - [ ] Test "Retry Request" button is hidden when status is retrying or terminal.
  - [ ] Test retry-request success updates status badge from open to retrying.
  - [ ] Test buttons are disabled while actionPending is set.

**Verification:** All existing tests pass. New tests pass.

---

## Slice 4 — Retry-Execute Action (Super Admin Only)

Goal: Add retry-execute control with mandatory confirmation. Visible only to super_admin.

- [x] Add `retryExecuteConfirmed` state (bool, default `false`).
- [x] Render "Retry Execute" button section in expanded detail only when ALL of:
  - `userRole === "super_admin"`
  - `status === "retrying"`
  - `source_type === "playbook_execution"`
- [x] Render confirmation text before the button (verbatim from design.md):
  ```
  "Retry Execute creates a new pending playbook execution. No steps will run
  immediately. The new execution must be picked up by the next manual executor
  invocation (scripts/run_playbook_executor_once.py). This dead letter will
  transition to 'retried'. This action cannot be undone."
  ```
- [x] Render acknowledgment checkbox below confirmation text:
  `☐ I understand that retry-execute creates pending work only and does not run steps.`
- [x] "Retry Execute" button is disabled until checkbox is checked.
- [x] On submit: call `retryExecuteDeadLetter(id)`.
  - On success: show the returned `new_execution_id` in the success message: "New pending execution #<id> created. No steps have run. Pick it up with the manual executor."
  - Update dead letter status to `retried` in state.
  - Hide action buttons (dead letter is now terminal).
  - Uncheck the acknowledgment checkbox.
- [x] On 409 error: show the error message from the API response body verbatim.
- [x] On other error: show generic inline error.
- [x] Add tests to `DeadLettersPanel.test.js`:
  - [x] Test "Retry Execute" section is not rendered for analyst role.
  - [x] Test "Retry Execute" section is not rendered when source_type is not playbook_execution.
  - [x] Test "Retry Execute" section is not rendered when status is not retrying.
  - [x] Test confirmation text renders verbatim.
  - [x] Test "Retry Execute" button is disabled before checkbox is checked.
  - [x] Test "Retry Execute" button is enabled after checkbox is checked.
  - [x] Test success shows new_execution_id in message.
  - [x] Test success transitions status to retried and hides action buttons.
  - [x] Test 409 error shows API error message.
  - [x] Test non-409 error shows generic error without crashing.

**Verification:** All existing tests pass. New tests pass. Analyst mock cannot see or trigger retry-execute.

---

## Slice 5 — PlaybooksPanel Execution Detail Improvements

Goal: Add dead letter linkage and lease/recovery fields to existing PlaybooksPanel execution detail.

**Pre-slice verification:**
- [ ] Read the response shape of `GET /playbook-executions/<id>` to confirm which fields are returned.
- [ ] If `lease_owner`, `lease_expires_at`, `recovery_count` are not in the response: add them to the backend response in `routes/playbook_routes.py` (additive only — no behavior change, no schema change). Run backend tests before continuing.

**Dead letter linkage (in PlaybooksPanel execution detail):**

- [ ] After loading execution detail, call `listDeadLetters({ execution_id: selectedExecutionId, limit: 1 })`.
- [ ] Import `listDeadLetters` from `deadLetterService.js`.
- [ ] If a dead letter row is returned, render a read-only "Dead Letter" section in the execution detail:
  - Status badge, failure_class, created timestamp.
  - Static label: "Review in SOAR Operations tab" (no navigation callback).
- [ ] If no dead letter row, omit the section entirely.
- [ ] Dead letter fetch error is silently suppressed — never breaks execution detail loading.
- [ ] Dead letter fetch does not block or delay the execution detail render.

**Lease/recovery fields (in PlaybooksPanel execution detail):**

- [ ] If the execution response includes any of `lease_owner`, `lease_acquired_at`, `lease_heartbeat_at`, `lease_expires_at`, `recovery_count`, render a read-only "Worker Lease" section:
  - Lease Owner: `<value>` or "none"
  - Lease Acquired: `<timestamp>` or "—"
  - Lease Expires: `<timestamp>` or "—"
  - Heartbeat: `<timestamp>` or "—"
  - Recovery Count: `<n>`
- [ ] If all lease fields are null or absent, omit the section.

**Tests (add to `PlaybooksPanel.test.js`):**

- [ ] Test dead letter section renders when `listDeadLetters` returns one row for the execution.
- [ ] Test dead letter section is omitted when `listDeadLetters` returns empty.
- [ ] Test dead letter fetch error is suppressed and execution detail still renders.
- [ ] Test lease section renders when execution response includes `lease_owner`.
- [ ] Test lease section is omitted when all lease fields are null.

**Verification:** All existing `PlaybooksPanel.test.js` tests pass. New tests pass. No regressions in execution detail behavior.

---

## Slice 6 — SOAR Operations Nav and App.js Wiring

Goal: Register the new tab and section in App.js. Import `DeadLettersPanel`.

- [ ] Add import in `App.js`: `import DeadLettersPanel from "./components/DeadLettersPanel";`
- [ ] Add nav button in the tab bar, after "SOAR Integrations", with `canTakeAlertActions` guard:
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
- [ ] Add section render, after the "soar-playbook-metrics" section block:
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
- [ ] Confirm no other App.js changes. `activeSection`, `canTakeAlertActions`, and `userRole` require no new logic.
- [ ] Verify `canTakeAlertActions` correctly excludes viewer role (existing logic: `isSuperAdmin || isAnalyst`).

**Verification:** App renders without error. Viewer role does not see the "SOAR Operations" tab. Analyst and super_admin see the tab and can load the panel. All existing section tabs remain functional.

---

## Slice 7 — Tests and UX Polish

Goal: Tie up edge cases, accessibility, and UX details across all new components.

- [ ] Verify all loading states use quiet refresh (not full spinner) on re-fetch after filter change.
- [ ] Verify empty state message includes current filter summary (e.g. "No dead letters found with status 'open'").
- [ ] Verify status badges use consistent color conventions matching existing panels:
  - open: amber / warning color
  - retrying: blue / info color
  - retried: green / success color
  - dismissed: gray / muted color
- [ ] Verify action buttons are properly disabled during pending API calls (no double-submit).
- [ ] Verify panel-level error banner shows a retry button that re-triggers initial load.
- [ ] Verify expanded row detail does not lose scroll position on filter re-fetch.
- [ ] Verify `DeadLettersPanel` gracefully handles an API response with `items: null` (fallback to empty array).
- [ ] Verify `failure_class` filter dropdown resets to "all" when metrics response changes.
- [ ] Verify all new text is consistent with existing panel copy style (lowercase labels, consistent timestamp formatting using `formatAdminTimestamp` from `adminPanelDisplay`).
- [ ] Run full frontend test suite: `npm test -- --watchAll=false`.
- [ ] Run backend regression suite: `pytest tests/` — confirm all existing tests still pass.
- [ ] Confirm no ESLint warnings introduced by new files.
- [ ] Confirm frontend build completes cleanly: `npm run build`.

---

## Verification Planning

- [ ] `deadLetterService.test.js` — all exports tested.
- [ ] `DeadLettersPanel.test.js` — list, detail, dismiss, retry-request, retry-execute, role gating, empty states.
- [ ] Updated `PlaybooksPanel.test.js` — dead letter linkage, lease fields.
- [ ] Full `npm test -- --watchAll=false` passes.
- [ ] Full `pytest tests/` passes (backend regression).
- [ ] `npm run build` completes without errors or new warnings.
- [ ] Manual smoke check: log in as analyst → confirm "SOAR Operations" tab visible, retry-execute button absent.
- [ ] Manual smoke check: log in as super_admin → confirm retry-execute section visible on a retrying dead letter with source_type=playbook_execution.

---

## Safety Boundaries

- [ ] Do not change ingest transaction flow.
- [ ] Do not change detection internals.
- [ ] Do not change correlation internals.
- [ ] Do not add autonomous retry loops, daemons, cron jobs, or schedulers.
- [ ] Do not send real notifications from the UI.
- [ ] Do not add new backend routes unless the lease/recovery field gap requires the minimal additive response shape change described in Slice 5.
- [ ] Do not create or modify any migration files.
- [ ] Do not edit `schema.sql` directly.
- [ ] Do not modify `App.js` beyond the two changes described in Slice 6 (import + nav/section blocks).
- [ ] Do not add cross-section navigation callbacks in this slice — "view in X tab" references are static labels only.
- [ ] Do not add a retryable filter toggle that implies filtering will return results — document the current `retryable: false` default behavior in the UI with a note.
- [ ] Do not change ApprovalsPanel.js, IncidentsPanel.js, IntegrationStatusPanel.js, or SoarQueuePanel.js.
- [ ] Do not run VM or live DB actions.
