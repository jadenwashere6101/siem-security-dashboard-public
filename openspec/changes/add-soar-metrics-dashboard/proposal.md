# Proposal: SOAR Metrics Dashboard

## Problem

Metrics exist across several backend endpoints but are not consolidated into a usable operational dashboard. Analysts and super_admins must navigate four separate panels to piece together SOAR health:

- `PlaybookMetricsPanel` — text-heavy, no visual hierarchy, no auto-refresh, no dead letter or queue signals
- `DeadLettersPanel` — metric cards shown only as a header inside the operational panel
- SOAR Integrations — circuit breaker state only, not linked to delivery outcomes
- SOAR Queue — super_admin only, isolated counts with no trend context

The current "SOAR Metrics" tab (`PlaybookMetricsPanel`) covers playbook execution counts and notification delivery totals as flat text blocks. No charts, no auto-refresh, no dead letter view, no incident or approval operational counts, no queue health summary.

Additionally, two metric domains have no aggregate API at all: incidents and approvals. Their counts are only obtainable by fetching the full list (50-100 rows) and counting client-side, which is inaccurate and wasteful.

This creates operational blind spots:

- Can't answer "how many incidents are open right now?" without opening IncidentsPanel and eyeballing the list.
- Can't see approval backlog depth at a glance without opening ApprovalsPanel.
- Dead letter open count is visible only inside DeadLettersPanel.
- Queue health (pending/running/awaiting_approval) is visible only to super_admin in a separate panel.
- No trend view — all existing metrics are totals (all-time), not windowed trends.

## Goal

Build a unified SOAR Metrics Dashboard that consolidates all available SOAR operational signals into one panel with visual hierarchy, charts, and auto-refresh. Replace the existing flat-text `PlaybookMetricsPanel` in-place with a richer `SoarMetricsDashboard` component.

The change should:

1. Consolidate all existing metric endpoints into one panel.
2. Add two lightweight backend aggregate routes that are currently missing (`GET /metrics/incidents`, `GET /metrics/approvals`).
3. Optionally extend `GET /metrics/playbooks` with a stale execution count (additive field).
4. Render metric cards + Recharts bar charts for visual hierarchy (Recharts already in use).
5. Add per-section auto-refresh (60-second interval, quiet, configurable).
6. Preserve all simulation-safe constraints — no execution, no real integrations.
7. Isolate per-section errors so one failing endpoint doesn't break the whole dashboard.

## Scope

**In scope:**

- New file: `frontend/src/components/SoarMetricsDashboard.js`
- New file: `frontend/src/components/SoarMetricsDashboard.test.js`
- New routes in `routes/metrics_routes.py`: `GET /metrics/incidents`, `GET /metrics/approvals`
- Updated `frontend/src/services/metricsService.js` — add `getIncidentMetrics()`, `getApprovalMetrics()`
- Updated `metricsService.test.js` — cover new service functions
- `App.js` — swap `PlaybookMetricsPanel` import for `SoarMetricsDashboard` in the existing `soar-playbook-metrics` section (two-line change)
- Optional additive field `stale_running_count` on `GET /metrics/playbooks` response

**Out of scope:**

- No changes to `PlaybookMetricsPanel.js` or its test — kept as-is, just no longer wired to App.js
- No new schema changes or migrations
- No changes to ingest, detection, or correlation
- No real Slack/Teams/firewall actions
- No autonomous execution, daemons, or scheduled workers
- No time-series storage — all metrics remain all-time aggregates or 24-hour windows pulled live from existing tables

## Why New Backend Routes Are Justified

`GET /metrics/incidents` and `GET /metrics/approvals` are pure COUNTs grouped by status and/or severity. They are:
- A single read-only query each (GROUP BY on a small table)
- Safe to add to `metrics_routes.py` with zero risk
- Required to avoid inaccurate client-side counting from paginated list endpoints

These routes do not change any existing behavior, add any tables, or require migrations.

## Role Access Summary

| Dashboard Section | Analyst | Super Admin |
|---|---|---|
| Execution metrics (playbooks) | Yes | Yes |
| Notification delivery metrics | Yes | Yes |
| Dead letter summary | Yes | Yes |
| Incident operational counts | Yes | Yes |
| Approval operational counts | Yes | Yes |
| SOAR Queue summary | No — section hidden | Yes |

SOAR Queue data comes from `GET /admin/soar/queue/status` which requires `super_admin`. The queue section is conditionally rendered only when `userRole === "super_admin"`. No new access control changes are needed.
