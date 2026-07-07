## ADDED Requirements

### Requirement: LIVE LOGS sidebar group
The sidebar SHALL display a top-level navigation group labeled "LIVE LOGS", rendered using the same group mechanism as the existing "ADMINISTRATION" group in `sectionsConfig.js`, containing exactly six navigation items, one per ingestion source: Honeypot, Bank App, pfSense, NGINX, Azure, OTEL.

#### Scenario: LIVE LOGS group is visible to authorized users
- **WHEN** an authenticated user with sufficient role (matching the existing `/events/search` role requirement) views the sidebar
- **THEN** a "LIVE LOGS" group heading is displayed with six clickable navigation items labeled Honeypot, Bank App, pfSense, NGINX, Azure, and OTEL

#### Scenario: Navigation item maps to correct source
- **WHEN** the user clicks the "pfSense" navigation item
- **THEN** the active section becomes the pfSense Live Logs page, parameterized with `source=pfsense`

### Requirement: Shared LiveLogsPanel component
The system SHALL render each Live Logs page using a single shared `LiveLogsPanel` component parameterized by a `source` value, rather than a separate component per source.

#### Scenario: Same component renders all six pages
- **WHEN** any of the six Live Logs navigation items is selected
- **THEN** the same `LiveLogsPanel` component is mounted, receiving only a different `source` prop per page

### Requirement: Per-source event isolation
Each Live Logs page SHALL display only events belonging to its assigned source, and SHALL NOT display events from any other source.

#### Scenario: Honeypot page shows only honeypot events
- **WHEN** the user views the Honeypot Live Logs page
- **THEN** every event row displayed has `source=honeypot`, and no events from `pfsense`, `nginx`, `azure_insights`, `opentelemetry`, or `bank_app` are shown

#### Scenario: pfSense page shows only pfSense events
- **WHEN** the user views the pfSense Live Logs page
- **THEN** every event row displayed has `source=pfsense`, and no events from any other source are shown

### Requirement: Newest-first ordering
Each Live Logs page SHALL display events ordered with the most recently created event first.

#### Scenario: Newly ingested event appears at the top
- **WHEN** a new event for the currently viewed source is ingested while the page is open
- **THEN** on the next refresh cycle, that event appears above all previously displayed events for that source

### Requirement: Auto-refreshing feed
Each Live Logs page SHALL automatically refresh its event feed on a fixed short interval (a few seconds) without requiring manual user action, and SHALL stop refreshing when the page is no longer active.

#### Scenario: Feed updates without manual refresh
- **WHEN** the user leaves a Live Logs page open and a new matching event is ingested
- **THEN** the new event appears in the feed within one polling interval, without the user clicking any refresh control

#### Scenario: Polling stops when navigating away
- **WHEN** the user navigates from a Live Logs page to a different sidebar section
- **THEN** the Live Logs page's polling interval is cleared and no further background requests for that source are made

### Requirement: Loading, error, and empty states
Each Live Logs page SHALL display a loading indicator on initial fetch, a clear error state if the fetch fails, and a clear empty state if the source has no events yet, consistent with existing panel conventions in the codebase.

#### Scenario: Initial load
- **WHEN** a Live Logs page is first opened
- **THEN** a loading indicator is shown until the first fetch completes

#### Scenario: Fetch failure
- **WHEN** the backend request for a source's events fails
- **THEN** the page displays an error message instead of a stale or blank table, and polling continues retrying on subsequent intervals

#### Scenario: No events yet for a source
- **WHEN** a source has zero events in the system
- **THEN** the page displays an explicit empty-state message rather than an empty table with no explanation

### Requirement: Source badges and labels
Each Live Logs page and its navigation item SHALL display a clear, human-readable label for its source, distinct from the raw `source` database value.

#### Scenario: Raw source value is translated to a display label
- **WHEN** the OTEL Live Logs page is rendered
- **THEN** the page and its sidebar item display the label "OTEL", not the raw value `opentelemetry`
