# Design: SOAR Metrics Dashboard

## Metrics Inventory Audit

### Existing backend endpoints (no changes needed)

| Endpoint | Access | Data available |
|---|---|---|
| `GET /metrics/playbooks` | analyst + super_admin | `total_executions`, `by_status` (6 statuses), `by_playbook_id` (per-playbook breakdown), `recent.success`, `recent.failed` (24h), `approval_gated.awaiting_approval`, `approval_gated.with_linked_approval` |
| `GET /metrics/notifications` | analyst + super_admin | `total_delivery_attempts`, `by_provider`, `by_mode` (simulation/real), `by_status` (5 statuses), `by_adapter_name`, `recent` (24h buckets), `circuit_breaker_state_counts` |
| `GET /metrics/dead-letters` | analyst + super_admin | `total`, `open`, `retrying`, `retried`, `dismissed`, `active`, `oldest_active_at`, `by_status`, `by_source_type`, `by_failure_class` |
| `GET /admin/soar/queue/status` | super_admin only | `counts` (pending/running/awaiting_approval/success/failed/skipped), `total`, `generated_at` |

### Backend gaps (new endpoints required)

| Missing endpoint | Why needed | Query complexity |
|---|---|---|
| `GET /metrics/incidents` | Incident status counts unavailable without full list fetch; `list_incidents` is paginated | Single `SELECT status, severity, COUNT(*) GROUP BY status, severity` query |
| `GET /metrics/approvals` | Approval status counts unavailable without full list fetch; `list_approval_requests` is paginated | Single `SELECT status, COUNT(*) GROUP BY status` query |

### Optional backend extension

`GET /metrics/playbooks` response can gain one additive field: `stale_running_count` (integer). Query: `SELECT COUNT(*) FROM playbook_executions WHERE status = 'running' AND lease_expires_at < NOW()`. This field is null-safe — if the field is absent, the dashboard renders it as `0`.

---

## New Backend Routes

### `GET /metrics/incidents`

Location: `routes/metrics_routes.py`, registered on `metrics_bp`.

Access: `@login_required @analyst_or_super_admin_required`

Query:

```sql
SELECT status, severity, COUNT(*)
FROM incidents
GROUP BY status, severity
```

Response shape:

```json
{
  "total": <int>,
  "by_status": {
    "open": <int>,
    "investigating": <int>,
    "resolved": <int>,
    "closed": <int>
  },
  "by_severity": {
    "CRITICAL": <int>,
    "HIGH": <int>,
    "MEDIUM": <int>,
    "LOW": <int>
  },
  "open_high_critical": <int>
}
```

`open_high_critical` is computed server-side as the count of rows where `status IN ('open', 'investigating') AND severity IN ('CRITICAL', 'HIGH')`. This is the most operationally important signal — active incidents that are high severity.

All known status/severity keys always present with zero defaults. No raw row passthrough.

### `GET /metrics/approvals`

Location: `routes/metrics_routes.py`, registered on `metrics_bp`.

Access: `@login_required @analyst_or_super_admin_required`

Query:

```sql
SELECT status, COUNT(*)
FROM approval_requests
GROUP BY status
```

Response shape:

```json
{
  "total": <int>,
  "by_status": {
    "pending": <int>,
    "approved": <int>,
    "denied": <int>,
    "expired": <int>
  },
  "pending_count": <int>
}
```

`pending_count` mirrors `by_status.pending` as a convenience field for the dashboard cards. All known status keys always present with zero defaults.

---

## Frontend Architecture

### Component: `SoarMetricsDashboard.js`

New component replacing `PlaybookMetricsPanel` in the `soar-playbook-metrics` App.js section. The old `PlaybookMetricsPanel.js` is preserved unchanged but no longer rendered in the app.

**Props:** `cardStyle`, `cardHeaderStyle`, `cardTitleStyle`, `cardSubtitleStyle`, `userRole`

No `filterLabelStyle` or `selectStyle` needed — this is a read-only dashboard with no filter controls.

**Data sources loaded on mount (parallel, isolated):**

```js
const [playbookMetrics, setPlaybookMetrics]   = useState(null)   // GET /metrics/playbooks
const [notifMetrics, setNotifMetrics]         = useState(null)   // GET /metrics/notifications
const [dlMetrics, setDlMetrics]               = useState(null)   // GET /metrics/dead-letters
const [incidentMetrics, setIncidentMetrics]   = useState(null)   // GET /metrics/incidents
const [approvalMetrics, setApprovalMetrics]   = useState(null)   // GET /metrics/approvals
const [queueStatus, setQueueStatus]           = useState(null)   // GET /admin/soar/queue/status (super_admin only)
```

Each data source has independent `loading` and `error` state so a failure in one section does not block others. Initial load fires all fetches in parallel (`Promise.allSettled`). Queue status is only fetched when `userRole === "super_admin"`.

**Auto-refresh:**

```js
const REFRESH_INTERVAL_MS = 60_000  // 60 seconds
```

A `useEffect` sets up `setInterval` that re-fires all fetches quietly (no loading spinner). A quiet refresh indicator (small rotating icon or "Refreshing…" text, top-right of the panel header) shows during in-progress refresh. Manual "Refresh now" button always visible in the panel header.

---

## Dashboard Layout

The panel is one `<section>` with a header and six sub-sections arranged vertically. No tab/accordion structure — scroll is acceptable for a metrics-heavy view.

```
┌─────────────────────────────────────────────────────────────┐
│ SOAR Metrics Dashboard         [Refreshing…] [Refresh now]  │
│ Last refreshed: 14:32:05 UTC   (simulation-safe notice)     │
├─────────────────────────────────────────────────────────────┤
│ SECTION 1: Playbook Execution Health                        │
│   [Total] [Success 24h] [Failed 24h] [Awaiting Approval]   │
│   [Stale Running?]                                          │
│   BarChart: executions by status                            │
│   Per-playbook breakdown (collapsible table)                │
├─────────────────────────────────────────────────────────────┤
│ SECTION 2: Dead Letter Health                               │
│   [Open] [Retrying] [Oldest active]                         │
│   BarChart: dead letters by status                          │
│   Failure class breakdown (top N rows)                      │
├─────────────────────────────────────────────────────────────┤
│ SECTION 3: Notification Delivery                            │
│   [Total attempts] [Success 24h] [Failed/Blocked 24h]      │
│   BarChart: delivery attempts by provider                   │
│   Circuit breaker state summary (closed/open/half_open)     │
│   Simulation vs real mode count                             │
├─────────────────────────────────────────────────────────────┤
│ SECTION 4: Incident Operational Counts                      │
│   [Total] [Open + Investigating] [Open Critical/High]       │
│   BarChart: incidents by status                             │
│   Severity split (CRITICAL/HIGH/MEDIUM/LOW bar)             │
├─────────────────────────────────────────────────────────────┤
│ SECTION 5: Approval Operational Counts                      │
│   [Pending] [Approved] [Denied] [Expired]                   │
│   BarChart: approvals by status                             │
├─────────────────────────────────────────────────────────────┤
│ SECTION 6: SOAR Queue Health  (super_admin only)            │
│   [Pending] [Running] [Awaiting Approval] [Failed]          │
│   BarChart: queue items by status                           │
│   Generated-at timestamp from queue status API              │
└─────────────────────────────────────────────────────────────┘
```

---

## Section Detail Specifications

### Section 1 — Playbook Execution Health

**Data:** `GET /metrics/playbooks`

**Metric cards (4–5):**
- Total Executions: `total_executions`
- Success (24h): `recent.success`
- Failed (24h): `recent.failed`
- Awaiting Approval: `approval_gated.awaiting_approval`
- Stale Running: `stale_running_count` if present in response, else omitted

**BarChart (Recharts):**
- Data: `by_status` object transformed to `[{ name: "pending", count: N }, ...]`
- X-axis: status name; Y-axis: count
- Colors: green=success, red=failed, amber=awaiting_approval, gray=others
- `ResponsiveContainer` width="100%" height=200

**Per-playbook table:** Collapsible (default collapsed). Shows playbook_id, total, and status breakdown per row. Uses existing normalization helpers from `PlaybookMetricsPanel.js`.

**Notice:** Simulation-only notice matching existing `PlaybookMetricsPanel` copy.

---

### Section 2 — Dead Letter Health

**Data:** `GET /metrics/dead-letters` (via `getDeadLetterMetrics` from `deadLetterService.js`)

**Metric cards (3):**
- Open: `open`
- Retrying: `retrying`
- Oldest Active: `oldest_active_at` formatted as relative time ("3 days ago") or ISO date. Show "none" when null.

**BarChart:**
- Data: `by_status` (open, retrying, retried, dismissed)
- Colors: red=open, amber=retrying, green=retried, gray=dismissed

**Failure class breakdown:** Top 5 failure classes from `by_failure_class` as a small table (failure_class, count). "No failures recorded" empty state.

**Operational note:** "Review and retry failed executions in the SOAR Operations tab." (static text, no navigation callback)

---

### Section 3 — Notification Delivery

**Data:** `GET /metrics/notifications`

**Metric cards (4):**
- Total Attempts: `total_delivery_attempts`
- Success (24h): `recent.success`
- Failed + Blocked (24h): `recent.failed + recent.blocked`
- Simulation/Real split: `by_mode.simulation` vs `by_mode.real` as a two-value inline display

**BarChart:**
- Data: `by_provider` entries sorted alphabetically
- Horizontal BarChart (provider names can be long)

**Circuit breaker summary:** Inline row: closed=N, open=N, half_open=N from `circuit_breaker_state_counts`.

**Evidence disclaimer:** Same simulation/real-mode notice as `PlaybookMetricsPanel` NOTIFICATION_METRICS_NOTICE.

---

### Section 4 — Incident Operational Counts

**Data:** `GET /metrics/incidents` (new endpoint)

**Metric cards (3):**
- Open + Investigating: `by_status.open + by_status.investigating`
- Resolved + Closed: `by_status.resolved + by_status.closed`
- Open Critical/High: `open_high_critical`

**BarChart (status):**
- Data: `by_status` (open, investigating, resolved, closed)
- Colors: red=open, amber=investigating, green=resolved, gray=closed

**BarChart (severity):**
- Data: `by_severity` (CRITICAL, HIGH, MEDIUM, LOW)
- Colors: red=CRITICAL, orange=HIGH, amber=MEDIUM, gray=LOW

Render both status and severity charts in a two-column grid when space permits.

---

### Section 5 — Approval Operational Counts

**Data:** `GET /metrics/approvals` (new endpoint)

**Metric cards (4):**
- Pending: `pending_count`
- Approved: `by_status.approved`
- Denied: `by_status.denied`
- Expired: `by_status.expired`

**BarChart:**
- Data: `by_status` (pending, approved, denied, expired)
- Colors: amber=pending, green=approved, red=denied, gray=expired

**Operational note:** "Approve or deny pending approvals in the SOAR Approvals tab." (static text only)

---

### Section 6 — SOAR Queue Health (super_admin only)

**Rendered only when `userRole === "super_admin"`.**

**Data:** `GET /admin/soar/queue/status` (via `loadSoarQueueStatus` from `soarQueueService.js`)

**Metric cards (4):**
- Pending: `counts.pending`
- Running: `counts.running`
- Awaiting Approval: `counts.awaiting_approval`
- Failed: `counts.failed`

**BarChart:**
- Data: all six statuses from `counts`
- Colors: amber=pending, blue=running, purple=awaiting_approval, green=success, red=failed, gray=skipped

**Generated-at timestamp:** "Queue snapshot as of `generated_at`" — rendered below the chart.

**Role gate note:** This section is not rendered for analysts. No error is shown to analysts for the missing queue data; the section is simply absent.

---

## `metricsService.js` Changes

Add two new exports:

```js
export async function getIncidentMetrics() {
  // GET /metrics/incidents
  // Returns: { total, by_status, by_severity, open_high_critical }
}

export async function getApprovalMetrics() {
  // GET /metrics/approvals
  // Returns: { total, by_status, pending_count }
}
```

Both follow the existing pattern in `metricsService.js` (buildSiemPath, parseJsonResponse, getApiErrorMessage, credentials: "include").

`getDeadLetterMetrics` is already exported from `deadLetterService.js`. Import it from there; do not duplicate it in `metricsService.js`.

---

## App.js Changes

Two changes only:

1. Replace `import PlaybookMetricsPanel from "./components/PlaybookMetricsPanel"` with `import SoarMetricsDashboard from "./components/SoarMetricsDashboard"`.
2. In the `soar-playbook-metrics` section render block, replace `<PlaybookMetricsPanel ...>` with `<SoarMetricsDashboard cardStyle={cardStyle} cardHeaderStyle={cardHeaderStyle} cardTitleStyle={cardTitleStyle} cardSubtitleStyle={cardSubtitleStyle} userRole={userRole} />`.

The section ID (`soar-playbook-metrics`), the nav tab label ("SOAR Metrics"), and the `canTakeAlertActions` guard are all unchanged.

---

## Data Refresh Strategy

**Initial load:** `Promise.allSettled([...all fetches...])` fires on mount. Each fetch result is applied independently — a rejected promise sets that section's `error` state without affecting others.

**Auto-refresh:** A single `setInterval` at `REFRESH_INTERVAL_MS` (60 000 ms) re-fires all fetches. During refresh: `refreshing: true` shows a quiet indicator in the panel header. No full re-render spinner.

**Queue refresh:** Queue status is included in the interval only when `userRole === "super_admin"`.

**Manual refresh:** "Refresh now" button in the panel header clears all error states, fires all fetches, and resets the interval timer.

**On section error:** An inline "Retry" button appears within the failed section only. Clicking it retries that section's fetch without triggering a full-panel refresh.

---

## Role Visibility

| Section | Analyst | Super Admin | Rendered when hidden |
|---|---|---|---|
| Playbook Execution Health | Yes | Yes | — |
| Dead Letter Health | Yes | Yes | — |
| Notification Delivery | Yes | Yes | — |
| Incident Operational Counts | Yes | Yes | — |
| Approval Operational Counts | Yes | Yes | — |
| SOAR Queue Health | No | Yes | Section entirely absent; no placeholder |

---

## Safety Boundaries

- No execution triggers of any kind. The dashboard is strictly read-only.
- All charts receive pre-aggregated counts from API responses. No raw event data, no IP addresses, no webhook URLs, no tokens.
- Recharts is already installed (`recharts@^3.8.1`). No new dependencies.
- `GET /metrics/incidents` and `GET /metrics/approvals` are purely additive — two new routes in an existing blueprint, no schema changes, no new tables.
- Simulation-mode notice preserved in Section 1 (playbook metrics).
- Evidence-only disclaimer preserved in Section 3 (notification delivery).
- Per-section error isolation: a failing metrics endpoint shows an inline error within that section only. The rest of the dashboard renders normally.
- `PlaybookMetricsPanel.js` and `PlaybookMetricsPanel.test.js` are unchanged.
- No changes to approval semantics, dead letter lifecycle, incident status transitions, or queue execution behavior.

---

## Risks Before Implementation

1. **`incidents` table may be sparsely populated in dev/test** — Section 4 will show zero counts. Tests must cover this zero-data state.

2. **`by_playbook_id` can grow large** — the per-playbook table is collapsible by default. If many playbooks are defined, the collapsed default prevents the section from dominating the viewport.

3. **Chart readability at zero data** — Recharts renders empty BarCharts with no bars. Each section needs an empty state that shows the section heading + metric cards (zeroed) but omits the chart until at least one non-zero value exists.

4. **Queue endpoint is super_admin-only** — if `loadSoarQueueStatus` is called for an analyst, it returns 403. Do not call it for analysts. The section must not render even a loading state for analyst users.

5. **Refresh interval and React StrictMode double-invoke** — `useEffect` cleanup must clear the interval. In StrictMode, effects run twice in development. Ensure interval is properly cleaned up.

6. **`stale_running_count` is optional** — the backend may or may not add it. The Section 1 metric card for stale running is conditionally rendered only when the field is present and non-null. No frontend or test logic should assume it exists.

7. **`oldest_active_at` relative time formatting** — this needs a helper that converts an ISO timestamp to a human-readable relative label ("2 hours ago", "5 days ago"). The existing `formatAdminTimestamp` in `adminPanelDisplay` may need extension or a new `formatRelativeTime` helper.
