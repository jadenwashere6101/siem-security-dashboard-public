# Tasks: SOAR Metrics Dashboard

Implementation must proceed slice-by-slice. Do not implement from this file without reading `proposal.md` and `design.md` first.

After every slice: run the full frontend test suite and the full backend test suite before proceeding.

---

## Pre-Implementation Review

- [ ] Audit `metricsService.js` — confirm existing exports (`getPlaybookMetrics`, `getNotificationDeliveryMetrics`) and their import patterns.
- [ ] Audit `deadLetterService.js` — confirm `getDeadLetterMetrics` is already exported and usable without duplication.
- [ ] Audit `PlaybookMetricsPanel.js` — extract the simulation-mode notice copy and the notification evidence disclaimer copy for reuse in `SoarMetricsDashboard`.
- [ ] Audit `PlaybookMetricsPanel.js` — extract `by_playbook_id` normalization helpers for reuse in Section 1 per-playbook table.
- [ ] Confirm `recharts` is available: `import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts"`. Verified in `SeverityChart.js`.
- [ ] Confirm `GET /admin/soar/queue/status` response shape matches design spec: `counts.{pending,running,awaiting_approval,success,failed,skipped}`, `total`, `generated_at`.
- [ ] Confirm App.js `soar-playbook-metrics` section ID and `<PlaybookMetricsPanel>` render block — identify the exact two lines to change.
- [ ] Confirm `userRole` prop is passed to the component render site in App.js (already done for `ApprovalsPanel` and `PlaybooksPanel`).
- [ ] Confirm `loadSoarQueueStatus` export from `soarQueueService.js` (or the correct service file). Identify the function name before wiring.

---

## Slice 1 — Backend: `GET /metrics/incidents`

Goal: Add a lightweight aggregate route for incident status/severity counts. No schema changes, no new tables.

- [x] In `routes/metrics_routes.py`, add `GET /metrics/incidents` under `metrics_bp`.
- [x] Access: `@login_required @analyst_or_super_admin_required`.
- [x] Query: `SELECT status, severity, COUNT(*) FROM incidents GROUP BY status, severity`.
- [x] Build response with zero-filled defaults for all known statuses (`open`, `investigating`, `resolved`, `closed`) and severities (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- [x] Compute `open_high_critical` server-side: sum of rows where `status IN ('open', 'investigating') AND severity IN ('CRITICAL', 'HIGH')`.
- [x] Compute `total` as sum of all counts.
- [x] Response shape: `{ total, by_status: {open, investigating, resolved, closed}, by_severity: {CRITICAL, HIGH, MEDIUM, LOW}, open_high_critical }`.
- [x] No raw row passthrough — only pre-aggregated counts in response.
- [x] Add `# spec: SPEC-METRICS-001` traceability comment to the new route.
- [x] Confirm existing route tests still pass.

**Verification:** `GET /metrics/incidents` returns correct shape with an empty `incidents` table (all zeros). Run backend test suite.

---

## Slice 2 — Backend: `GET /metrics/approvals`

Goal: Add a lightweight aggregate route for approval status counts. No schema changes.

- [x] In `routes/metrics_routes.py`, add `GET /metrics/approvals` under `metrics_bp`.
- [x] Access: `@login_required @analyst_or_super_admin_required`.
- [x] Query: `SELECT status, COUNT(*) FROM approval_requests GROUP BY status`.
- [x] Build response with zero-filled defaults for all known statuses: `pending`, `approved`, `denied`, `expired`.
- [x] `pending_count` mirrors `by_status["pending"]` as a convenience field.
- [x] Compute `total` as sum of all counts.
- [x] Response shape: `{ total, by_status: {pending, approved, denied, expired}, pending_count }`.
- [x] Add `# spec: SPEC-METRICS-001` traceability comment to the new route.
- [x] Confirm existing route tests still pass.

**Verification:** `GET /metrics/approvals` returns correct shape with an empty `approval_requests` table (all zeros). Run backend test suite.

---

## Slice 3 — Backend (Optional): `stale_running_count` on `GET /metrics/playbooks`

Goal: Add one additive field to the existing playbook metrics response. Skip this slice if deemed unnecessary.

- [x] In `routes/metrics_routes.py`, in the `GET /metrics/playbooks` handler, add:
  ```sql
  SELECT COUNT(*) FROM playbook_executions
  WHERE status = 'running' AND lease_expires_at < NOW()
  ```
- [x] Include result as `stale_running_count: <int>` in the JSON response.
- [x] Field must be additive only — existing consumers that ignore unknown fields are unaffected.
- [x] Add `# spec: SPEC-METRICS-001` traceability comment at the modified block.

**Verification:** `GET /metrics/playbooks` response includes `stale_running_count` field. No existing test broken.

---

## Slice 4 — Frontend: `metricsService.js` additions

Goal: Add two new service functions for the new backend routes.

- [x] In `frontend/src/services/metricsService.js`, add:
  ```js
  export async function getIncidentMetrics() {
    // GET /metrics/incidents
  }
  export async function getApprovalMetrics() {
    // GET /metrics/approvals
  }
  ```
- [x] Both follow the existing `buildSiemPath` / `parseJsonResponse` / `getApiErrorMessage` / `credentials: "include"` pattern.
- [x] Do NOT import or re-export `getDeadLetterMetrics` — it already lives in `deadLetterService.js`.
- [x] Update `frontend/src/services/metricsService.test.js`:
  - [x] Test `getIncidentMetrics` calls the correct URL and returns parsed response.
  - [x] Test `getApprovalMetrics` calls the correct URL and returns parsed response.
  - [x] Test both functions throw with API error message on non-OK response.

**Verification:** `npm test -- --testPathPattern=metricsService` passes. No other tests broken.

---

## Slice 5 — Frontend: `SoarMetricsDashboard.js` — skeleton + data loading

Goal: Create the component file, wire all data sources, implement auto-refresh, and render section headings with loading/error states. No charts or metric cards yet.

- [x] Create `frontend/src/components/SoarMetricsDashboard.js`.
- [x] Props: `cardStyle`, `cardHeaderStyle`, `cardTitleStyle`, `cardSubtitleStyle`, `userRole`.
- [x] State per data source: per-section object state (`{data, loading, error}` per section).
- [x] Loading state per section (individual, not a single shared flag).
- [x] Error state per section (individual strings/null).
- [x] `refreshing` boolean for quiet refresh indicator.
- [x] `lastRefreshedAt` Date for the header timestamp.
- [x] `REFRESH_INTERVAL_MS = 60_000` (exported constant).
- [x] `fetchAll()` function: fires all fetches via `Promise.allSettled`. Applies results independently — a rejected promise sets that section's error state only.
- [x] Queue fetch inside `fetchAll()` is conditional: only runs when `userRole === "super_admin"`.
- [x] `useEffect` on mount: call `fetchAll()`, then set up `setInterval(fetchAll, REFRESH_INTERVAL_MS)`. Return cleanup that clears the interval.
- [x] Manual "Refresh now" button clears all error states, calls `fetchAll()`, and resets the interval.
- [x] Panel header renders:
  - Title: "SOAR Metrics Dashboard"
  - Last refreshed timestamp (formatted, e.g. "14:32:05 UTC")
  - Quiet refresh indicator (visible when `refreshing: true`)
  - "Refresh now" button
- [x] Render six `<section>` containers (Sections 1–6) with placeholder headings and per-section loading/error states.
  - Section 6 is not rendered when `userRole !== "super_admin"`.
- [x] Per-section error state: inline message + "Retry" button that retries only that section's fetch.
- [x] Create `frontend/src/components/SoarMetricsDashboard.test.js` — 20 tests: section rendering, loading states, per-section error isolation, Promise.allSettled partial failures, role gating, manual refresh, interval setup/cleanup, fake-timer auto-refresh.

**Verification:** 20/20 tests pass. `npm run build` clean (pre-existing App.js warning only). No chart or card content yet. No existing tests broken.

---

## Slice 6 — Frontend: `SoarMetricsDashboard.js` — metric cards and charts

Goal: Implement all metric card content, BarCharts, and section-specific sub-components for all six sections.

### Section 1 — Playbook Execution Health

- [ ] Metric cards: Total Executions, Success (24h), Failed (24h), Awaiting Approval.
- [ ] Metric card for Stale Running: rendered only when `playbookMetrics.stale_running_count` is present and non-null.
- [ ] BarChart: `by_status` object transformed to `[{ name, count }]` array. Colors: green=success, red=failed, amber=awaiting_approval, gray=others. `ResponsiveContainer width="100%" height={200}`.
- [ ] Per-playbook breakdown table: collapsible (default collapsed). Shows playbook_id, total, status breakdown per row. Reuse normalization helpers extracted from `PlaybookMetricsPanel.js`.
- [ ] Simulation-only notice: match copy from `PlaybookMetricsPanel`.
- [ ] Empty state: if all status values are zero, omit the BarChart and show "No executions recorded" text. Metric cards still render (zeroed).

### Section 2 — Dead Letter Health

- [ ] Import `getDeadLetterMetrics` from `deadLetterService.js` (not metricsService).
- [ ] Metric cards: Open, Retrying, Oldest Active.
  - Oldest Active: formatted as relative time ("3 days ago") using a `formatRelativeTime(isoString)` helper. Show "None" when null.
- [ ] Add `formatRelativeTime` helper: converts ISO timestamp to human-readable relative label. Reuse or extend `formatAdminTimestamp` if applicable.
- [ ] BarChart: `by_status` (open, retrying, retried, dismissed). Colors: red=open, amber=retrying, green=retried, gray=dismissed.
- [ ] Top 5 failure classes table from `by_failure_class`: failure_class column + count column. "No failures recorded" empty state when object is empty.
- [ ] Operational note (static text): "Review and retry failed executions in the SOAR Operations tab."
- [ ] Empty state: omit BarChart when all status values are zero.

### Section 3 — Notification Delivery

- [ ] Metric cards: Total Attempts, Success (24h), Failed + Blocked (24h) (`recent.failed + recent.blocked`), Simulation/Real split (inline `by_mode.simulation` vs `by_mode.real`).
- [ ] Horizontal BarChart: `by_provider` entries sorted alphabetically. Use `layout="vertical"` in Recharts.
- [ ] Circuit breaker summary: inline row — "closed: N, open: N, half_open: N" from `circuit_breaker_state_counts`.
- [ ] Evidence disclaimer: match copy from `PlaybookMetricsPanel` NOTIFICATION_METRICS_NOTICE.
- [ ] Empty state: omit BarChart when `by_provider` is empty or all zero.

### Section 4 — Incident Operational Counts

- [ ] Metric cards: Open + Investigating (`by_status.open + by_status.investigating`), Resolved + Closed, Open Critical/High (`open_high_critical`).
- [ ] Status BarChart: `by_status` (open, investigating, resolved, closed). Colors: red=open, amber=investigating, green=resolved, gray=closed.
- [ ] Severity BarChart: `by_severity` (CRITICAL, HIGH, MEDIUM, LOW). Colors: red=CRITICAL, orange=HIGH, amber=MEDIUM, gray=LOW.
- [ ] Render both charts side-by-side in a two-column inline grid when viewport permits; stack vertically on narrow viewports.
- [ ] Empty state: omit both charts when all counts are zero.

### Section 5 — Approval Operational Counts

- [ ] Metric cards: Pending (`pending_count`), Approved, Denied, Expired.
- [ ] BarChart: `by_status` (pending, approved, denied, expired). Colors: amber=pending, green=approved, red=denied, gray=expired.
- [ ] Operational note (static text): "Approve or deny pending approvals in the SOAR Approvals tab."
- [ ] Empty state: omit BarChart when all status values are zero.

### Section 6 — SOAR Queue Health (super_admin only)

- [ ] Entire section not rendered when `userRole !== "super_admin"`. No placeholder, no loading state visible to analysts.
- [ ] Metric cards: Pending (`counts.pending`), Running (`counts.running`), Awaiting Approval (`counts.awaiting_approval`), Failed (`counts.failed`).
- [ ] BarChart: all six statuses from `counts`. Colors: amber=pending, blue=running, purple=awaiting_approval, green=success, red=failed, gray=skipped.
- [ ] Generated-at timestamp: "Queue snapshot as of `generated_at`" rendered below chart.
- [ ] Empty state: omit BarChart when all counts are zero.

**Verification:** All six sections render with correct data. Charts appear only when data has at least one non-zero value. Section 6 absent for analyst `userRole`. No existing tests broken.

---

## Slice 7 — Frontend: App.js wiring

Goal: Replace `PlaybookMetricsPanel` with `SoarMetricsDashboard` in the existing `soar-playbook-metrics` section. Two lines only.

- [ ] In `frontend/src/App.js`, replace:
  ```js
  import PlaybookMetricsPanel from "./components/PlaybookMetricsPanel"
  ```
  with:
  ```js
  import SoarMetricsDashboard from "./components/SoarMetricsDashboard"
  ```
- [ ] In the `soar-playbook-metrics` section render block, replace:
  ```jsx
  <PlaybookMetricsPanel ... />
  ```
  with:
  ```jsx
  <SoarMetricsDashboard
    cardStyle={cardStyle}
    cardHeaderStyle={cardHeaderStyle}
    cardTitleStyle={cardTitleStyle}
    cardSubtitleStyle={cardSubtitleStyle}
    userRole={userRole}
  />
  ```
- [ ] Section ID (`soar-playbook-metrics`), nav tab label ("SOAR Metrics"), and `canTakeAlertActions` guard are unchanged.
- [ ] `PlaybookMetricsPanel.js` file is NOT modified or deleted.
- [ ] `PlaybookMetricsPanel.test.js` is NOT modified.

**Verification:** App renders without import errors. "SOAR Metrics" nav tab loads `SoarMetricsDashboard`. `PlaybookMetricsPanel` tests still pass (they test the component in isolation, not the App).

---

## Slice 8 — Tests: `SoarMetricsDashboard.test.js`

Goal: Cover all section rendering, role gating, loading/error states, refresh, and empty states.

- [ ] Create `frontend/src/components/SoarMetricsDashboard.test.js`.
- [ ] Mock all service imports: `getPlaybookMetrics`, `getNotificationDeliveryMetrics`, `getDeadLetterMetrics`, `getIncidentMetrics`, `getApprovalMetrics`, `loadSoarQueueStatus` (or equivalent).
- [ ] **Rendering — Section visibility:**
  - [ ] All sections 1–5 render for `userRole="analyst"`.
  - [ ] Section 6 renders for `userRole="super_admin"`.
  - [ ] Section 6 is absent for `userRole="analyst"` (no DOM node, not just hidden).
- [ ] **Loading states:**
  - [ ] Individual section shows loading indicator while its fetch is in-flight.
  - [ ] Other sections not blocked when one section is loading.
- [ ] **Error states:**
  - [ ] Section renders error message + Retry button when its fetch rejects.
  - [ ] Other sections not affected by one section's error.
  - [ ] Retry button re-fires only that section's fetch.
- [ ] **Data rendering:**
  - [ ] Section 1 renders Total Executions, Success 24h, Failed 24h, Awaiting Approval cards.
  - [ ] Section 1 Stale Running card is absent when `stale_running_count` not in response.
  - [ ] Section 1 Stale Running card renders when `stale_running_count` is present.
  - [ ] Section 1 per-playbook table is collapsed by default; expands on toggle.
  - [ ] Section 2 Oldest Active shows "None" when `oldest_active_at` is null.
  - [ ] Section 2 failure class table shows "No failures recorded" when `by_failure_class` is empty.
  - [ ] Section 3 Sim/Real metric card displays both counts.
  - [ ] Section 3 circuit breaker summary row renders all three states.
  - [ ] Section 4 dual BarCharts (status + severity) render when data non-zero.
  - [ ] Section 5 pending_count shown in Pending metric card.
  - [ ] Section 6 generated_at timestamp rendered below chart.
- [ ] **Empty states:**
  - [ ] BarChart is omitted when all values in the chart data are zero (one test per section).
  - [ ] Metric cards still render with zero values when data is empty.
- [ ] **Auto-refresh:**
  - [ ] `setInterval` is set on mount with `REFRESH_INTERVAL_MS`.
  - [ ] Interval is cleared on unmount.
  - [ ] "Refresh now" button triggers `fetchAll` and resets interval.
- [ ] **Queue not fetched for analyst:**
  - [ ] `loadSoarQueueStatus` is never called when `userRole="analyst"`.

**Verification:** All `SoarMetricsDashboard.test.js` tests pass. Full suite (`npm test`) passes.

---

## Pre-Review Checklist

Before marking this OpenSpec complete:

- [ ] All backend routes return correct shapes with zero-data input.
- [ ] All backend routes have `# spec: SPEC-METRICS-001` traceability tags.
- [ ] `SoarMetricsDashboard.js` passes JSX linting (`npm run lint` or equivalent).
- [ ] Full frontend test suite passes with no regressions.
- [ ] Full backend test suite passes with no regressions.
- [ ] Section 6 is confirmed absent in DOM for analyst role (not just visually hidden).
- [ ] No `GET /admin/soar/queue/status` call is made for analyst users.
- [ ] `PlaybookMetricsPanel.js` and `PlaybookMetricsPanel.test.js` are byte-for-byte unchanged.
- [ ] `oldest_active_at` relative time helper handles null without throwing.
- [ ] Auto-refresh interval is confirmed cleared on component unmount (no leak in StrictMode).
- [ ] `stale_running_count` card is conditionally rendered — no failure when field is absent.
- [ ] All BarCharts use `ResponsiveContainer width="100%" height={200}` (or `height={180}` for dual-chart sections).

---

## Safety Boundaries

- [ ] No execution triggers of any kind. Dashboard is strictly read-only.
- [ ] No raw event data, IP addresses, webhook URLs, or tokens in any API response or chart.
- [ ] `GET /metrics/incidents` and `GET /metrics/approvals` are additive routes only. No schema changes, no new tables.
- [ ] Simulation-mode notice preserved in Section 1. Evidence-only disclaimer preserved in Section 3.
- [ ] `PlaybookMetricsPanel.js` is preserved unchanged — it is simply no longer imported in App.js.
- [ ] Recharts is already installed. No new frontend dependencies are added.
- [ ] All charts receive pre-aggregated counts from API responses. No raw record passthrough.
- [ ] No real Slack, Teams, firewall, email, or webhook execution.
- [ ] No changes to ingest, detection, or correlation internals.
- [ ] No changes to approval semantics, dead letter lifecycle, incident status transitions, or queue execution behavior.
