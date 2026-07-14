## Why

Several data-driven workspaces still treat "first request has not completed yet" the same as "real empty data," which creates blank, frozen-looking, or zero-looking states during initial load. Separately, the dashboard alerts flow still fetches the full `/alerts` result set, and Live Logs can retain polled rows indefinitely in memory, making those two surfaces the only proven large-list risks in the current audit.

## What Changes

- Add one small reusable loading-state pattern for data-driven workspaces that distinguishes initial load, background refresh, loaded, and error states without resetting visible data during refresh.
- Apply that pattern only to the approved loading surfaces: Dashboard / Recent Alerts and SOC Command Center.
- Add bounded pagination to `GET /alerts` using the repository's established list contract shape and a validated maximum page size so the Recent Alerts table no longer fetches the full alert set to render one page.
- Add an authoritative alert dashboard summary contract so dashboard totals, severity counts, top-IP data, timeline data, and map/source summaries remain accurate and do not become page-local after alerts pagination is introduced.
- Keep Live Logs API polling bounded as-is, but add a deterministic client-side retention cap so long-running sessions cannot accumulate unbounded rows in memory.
- Preserve current alert filtering, sorting, expansion, navigation, refresh behavior, and existing workspace semantics outside this narrow scope.

## Capabilities

### New Capabilities

- `workspace-loading-and-list-bounds`: Defines consistent initial-load vs refresh behavior for scoped data workspaces, bounded alerts pagination with authoritative dashboard aggregates, and bounded in-memory Live Logs retention.

### Modified Capabilities

None.

## Impact

- Frontend app shell and dashboard state in [frontend/src/App.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/App.js:1) will split alert page data from dashboard aggregate data and add explicit load or refresh state handling.
- Dashboard surfaces including [frontend/src/components/DashboardSection.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/components/DashboardSection.js:1), [frontend/src/components/AlertsTable.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/components/AlertsTable.js:1), [frontend/src/components/DashboardMetrics.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/components/DashboardMetrics.js:1), and [frontend/src/components/DashboardVisuals.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/components/DashboardVisuals.js:1) will move from full-alert rendering to paged rows plus authoritative aggregate inputs.
- Live Logs in [frontend/src/components/LiveLogsPanel.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/components/LiveLogsPanel.js:1) will gain bounded client-side retention without changing polling or source navigation semantics.
- SOC Command Center in [frontend/src/components/SocCommandCenter.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/components/SocCommandCenter.js:1) will gain a true initial-loading state and refresh-safe stale-data behavior.
- Backend alerts APIs in [routes/alerts_events_routes.py](/Users/jadengomez/Projects/siem-security-dashboard-public/routes/alerts_events_routes.py:1) and [frontend/src/services/alertsService.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/services/alertsService.js:1) will add small contract changes for pagination and dashboard aggregates.
- No database schema change or migration is expected. Test impact is limited to alerts API contracts plus focused frontend coverage for App, Alerts, Live Logs, and SOC Command Center.
