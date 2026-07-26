## Why

Dashboard and Recent Alerts usability has three recurring problems: loading indicators reference animation CSS that is not loaded, Top Source IPs can still show demo/synthetic IPs because exclusions happen after aggregation, and analysts cannot filter alerts by the detection rule that fired. These issues make the dashboard feel unreliable and make alert triage slower than necessary.

## What Changes

- Standardize dashboard loading indicators on one shared loading component or shared loading style path with one globally loaded animation definition.
- Prefer a reliable animated spinner because the defect is a missing global keyframe import, not an inherent animation limitation.
- Keep a fallback requirement: if implementation-time visual verification proves animation cannot be made reliable, replace affected spinner indicators with a professional themed static `Loading...` state.
- Move synthetic/demo IP exclusion into the backend alert-summary filtering path before aggregation and `LIMIT`.
- Replace environment-specific Top Source IP post-filtering with a reusable, deterministic dashboard exclusion policy that can preserve real historical production IPs.
- Keep dashboard widgets internally consistent by applying the same synthetic/demo exclusion policy to all dashboard summary widgets that represent source-IP-derived alert aggregates.
- Add an explicit detection-rule filter to Recent Alerts that composes with existing search, severity, status, source, operational-scope, sort, exact source IP, exact target IP, alert ID, pagination, and export behavior.
- Do not include recon, navigation/history, SOAR, AI, cache, runtime hardening, schema migration, or deployment changes.

## Capabilities

### New Capabilities

- `dashboard-alerts-ux-cleanup`: Covers reliable dashboard loading states, dashboard source-IP aggregate filtering, and Recent Alerts detection-rule filtering.

### Modified Capabilities

- None.

## Impact

- Backend APIs: `GET /alerts`, `GET /alerts/summary`, filtered alert exports under `/alerts/report`, `/alerts/report/pdf`, and `/alerts/export/csv`.
- Backend helpers: alert filter parsing/query construction and reporting query helpers.
- Frontend: dashboard alert state in `App.js`, `alertsService`, `DashboardSection`, `AlertsTable`, `AlertsToolbar`, `TimelineChart`, `WorkspaceAsyncState`, `TopIPChart`, and related tests.
- Detection rule metadata: reuse existing detection-rule catalog/admin rule data for the filter options; no schema migration.
- Verification: focused backend/frontend tests, frontend production build, local visual review where practical, and VM/runtime visual confirmation after implementation deployment.
