## 1. Loading-State Contract and Shared Primitive (Mac AI)

- [x] 1.1 Add one small shared loading-state primitive or helper that distinguishes initial load, background refresh, loaded, and error states for scoped data workspaces.
- [x] 1.2 Apply the shared loading-state behavior to Dashboard / Recent Alerts so initial load does not look like empty or zero data and background refresh preserves stale data.
- [x] 1.3 Apply the shared loading-state behavior to SOC Command Center so initial load does not render fake zero metrics and background refresh preserves the last successful data.
- [x] 1.4 Add focused frontend tests for initial-load, refresh, and refresh-failure behavior in the scoped workspaces.

## 2. Alerts API Pagination and Authoritative Dashboard Metrics (Mac AI)

- [x] 2.1 Update `GET /alerts` to use validated `limit` and `offset` parameters with a maximum page size of 100 and the repository's paginated list response shape.
- [x] 2.2 Add a dedicated authoritative alert summary API contract that preserves dashboard totals, severity counts, top-IP data, timeline data, and map/source summary data independently of the current alert page.
- [x] 2.3 Update alerts frontend services to consume the paginated row contract separately from the authoritative dashboard summary contract.
- [x] 2.4 Add focused backend API tests for alerts pagination bounds, authenticated access behavior, and authoritative aggregate accuracy independent of page selection.

## 3. Recent Alerts Frontend Integration (Mac AI)

- [x] 3.1 Update dashboard alert state management to separate Recent Alerts page rows from dashboard aggregate data.
- [x] 3.2 Update the Recent Alerts workspace to render only the current bounded page while preserving current sorting, filtering, expansion, and navigation behavior.
- [x] 3.3 Ensure dashboard metrics, charts, and map/source summaries use the authoritative aggregate contract rather than the current page rows.
- [x] 3.4 Add focused frontend regression tests for Recent Alerts pagination, dashboard aggregate correctness, and existing alert interaction behavior.

## 4. Live Logs Retention Bound (Mac AI)

- [x] 4.1 Add deterministic Live Logs retention trimming with a cap of 500 retained rows after merge and deduplication.
- [x] 4.2 Preserve newest events, source filters, polling cadence, focus, scroll, and view-mode behavior when trimming occurs.
- [x] 4.3 Add focused frontend tests covering long-poll retention growth, oldest-row trimming, and newest-row preservation.

## 5. SOC Command Center Loading Behavior (Mac AI)

- [x] 5.1 Add a true initial-loading state so SOC Command Center does not render valid-looking zero or empty cards before the first request resolves.
- [x] 5.2 Preserve existing data during manual refresh and show only a subtle refresh indicator plus partial-source warnings where applicable.
- [x] 5.3 Add focused frontend tests for initial loading, retained-data refresh, and refresh-failure behavior.

## 6. Final Verification and Handoff (Mac AI -> VM AI only after explicit authorization)

- [x] 6.1 Run affected backend and frontend tests for alerts API pagination, dashboard aggregates, Recent Alerts, Live Logs, and SOC Command Center loading behavior.
- [x] 6.2 Verify keyboard and accessibility behavior plus desktop and narrow-layout rendering for the scoped workspaces.
- [x] 6.3 Run `npm run build`.
- [x] 6.4 Run `openspec validate improve-workspace-loading-and-list-bounds --strict`.
- [x] 6.5 Run `git diff --check`.
- [x] 6.6 Prepare a VM handoff only if implementation later occurs, explicitly noting that this change has no migration and that deployment remains a separate authorized step.
