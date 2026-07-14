## ADDED Requirements

### Requirement: Scoped workspaces SHALL distinguish initial load from refresh
The system SHALL use a shared loading-state pattern for the scoped data workspaces in this change: Dashboard / Recent Alerts and SOC Command Center. Initial load SHALL show a small accessible loader or skeleton and SHALL NOT render fake zero, empty, or partially valid-looking data before the first request resolves. After at least one successful load, background refresh SHALL preserve the last successful data, keep current focus and workspace state, and show only a subtle refresh indicator. If a refresh fails while stale data exists, the system SHALL preserve the stale data and show a non-blocking refresh failure message.

#### Scenario: Dashboard initial load is not mistaken for empty data
- **WHEN** an authenticated user opens the dashboard and the first Recent Alerts requests have not resolved yet
- **THEN** the dashboard SHALL show an explicit initial-loading state for the affected dashboard content
- **AND** it SHALL NOT display real-looking zero metrics, empty charts, or an empty Recent Alerts table as if data had already loaded

#### Scenario: SOC Command Center initial load is not mistaken for valid zeros
- **WHEN** an operator opens SOC Command Center before its first composite data load completes
- **THEN** the workspace SHALL show a true initial-loading state
- **AND** summary cards and incident context panes SHALL NOT temporarily appear as authoritative zero or empty operational data

#### Scenario: Background refresh preserves stale data
- **WHEN** a scoped workspace has already loaded successfully and a background refresh starts
- **THEN** the existing rendered data SHALL remain visible
- **AND** the workspace SHALL show only a subtle `Refreshing…` indicator
- **AND** it SHALL NOT reset focus, scroll position, selected rows, filters, or navigation context

#### Scenario: Refresh failure preserves stale data
- **WHEN** a background refresh fails after the workspace has already loaded data successfully
- **THEN** the last successful data SHALL remain visible
- **AND** the workspace SHALL display a refresh-failure warning distinct from an initial-load failure

### Requirement: Recent Alerts SHALL use bounded row pagination with authoritative dashboard aggregates
The system SHALL bound the Recent Alerts row list through a paginated `GET /alerts` contract with validated `limit` and `offset` parameters and a maximum page size of 100. The frontend SHALL fetch only the current alert page for the Recent Alerts table and SHALL NOT request the entire alert list to render one page. Because dashboard metrics and visuals currently depend on the full alert set, the system SHALL provide a separate authoritative alert summary contract for dashboard aggregates so totals and visual summaries remain correct regardless of the current alert page.

#### Scenario: Alerts list request is bounded
- **WHEN** the frontend requests Recent Alerts rows
- **THEN** it SHALL send validated pagination parameters to `GET /alerts`
- **AND** the backend SHALL enforce a safe maximum page size of 100
- **AND** the response SHALL use the repository list shape with row items and pagination metadata

#### Scenario: Dashboard aggregates remain authoritative
- **WHEN** the user is viewing page 2 or later of Recent Alerts
- **THEN** dashboard totals, severity counts, top-IP chart data, timeline data, and map/source summary data SHALL remain authoritative for the full filtered result set
- **AND** they SHALL NOT degrade to page-local values

#### Scenario: Alert summary uses the same dashboard filters
- **WHEN** the dashboard applies supported alert filters used by its metrics, charts, and Recent Alerts workspace
- **THEN** the authoritative alert summary contract SHALL apply the same filter semantics as the dashboard row list where those filters affect aggregates
- **AND** the dashboard visuals SHALL stay consistent with the filtered Recent Alerts view

#### Scenario: Existing alert interactions remain intact
- **WHEN** Recent Alerts rows are paginated
- **THEN** sorting, filtering, row expansion, selection, and navigation behavior SHALL remain available in the paged row set
- **AND** the change SHALL NOT require a database migration

#### Scenario: Alerts authentication behavior is preserved
- **WHEN** an unauthenticated client requests the alerts row list or alert summary contract
- **THEN** the request SHALL continue to fail under the existing authenticated access rules
- **AND** authenticated users SHALL receive bounded data rather than the prior unbounded list behavior

### Requirement: Live Logs SHALL bound retained rows in memory
The system SHALL preserve the existing bounded Live Logs polling behavior and add a deterministic client-side retention cap of 500 accumulated rows per panel instance. The panel SHALL deduplicate rows by event identity, keep the newest rows, and trim the oldest retained rows when the cap is exceeded. It SHALL preserve current source filters, automatic polling, focus, scroll behavior, and navigation semantics.

#### Scenario: Long-running polling trims oldest rows
- **WHEN** repeated polling pushes a Live Logs panel above 500 retained rows
- **THEN** the panel SHALL trim the oldest retained rows after merge and deduplication
- **AND** the newest rows SHALL remain available in the rendered collection

#### Scenario: Polling remains bounded
- **WHEN** Live Logs requests continue during normal polling
- **THEN** the client SHALL continue using the existing bounded API polling contract
- **AND** the retention change SHALL NOT require a new database or schema contract

#### Scenario: Retention trimming preserves current workspace state
- **WHEN** old rows are trimmed because the retention cap is exceeded
- **THEN** the panel SHALL preserve the selected source, current view mode, and polling cadence
- **AND** it SHALL NOT reset navigation or introduce fake loading states
