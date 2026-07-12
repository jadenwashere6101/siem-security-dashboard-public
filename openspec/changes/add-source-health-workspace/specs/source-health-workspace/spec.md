## ADDED Requirements

### Requirement: Canonical source inventory
The system SHALL provide one reusable recognized-source inventory containing exactly the six canonical source identities, their canonical source types, friendly display labels, and corresponding Live Logs destinations.

#### Scenario: Inventory contains all recognized sources
- **WHEN** the source inventory is read by backend aggregation or frontend workspace logic
- **THEN** it contains `honeypot`, `bank_app`, `pfsense`, `nginx`, `azure_insights`, and `opentelemetry` exactly once

#### Scenario: Canonical metadata matches established identities
- **WHEN** the inventory entry for each source is inspected
- **THEN** its source type and display label match `honeypot/Honeypot`, `custom/Bank App`, `firewall/pfSense`, `web_log/NGINX`, `cloud_api/Azure Application Insights`, and `telemetry/OpenTelemetry`, respectively

#### Scenario: Existing source consumers remain aligned
- **WHEN** Dashboard source filtering, Detection Rules source labels, Live Logs navigation, and Source Health use source metadata
- **THEN** they use the same canonical identities without changing existing Dashboard calculations

### Requirement: Authoritative all-source activity API
The system SHALL expose one read-only API that returns database-backed activity statistics for every recognized source in one response and SHALL NOT derive authoritative counts from `/events/search` or any capped row collection.

#### Scenario: Sources with and without events are returned
- **WHEN** an authorized user requests Source Health statistics
- **THEN** the response contains exactly one entry for each of the six recognized sources even when one or more sources have no matching `events` rows

#### Scenario: Counts are uncapped and database-backed
- **WHEN** a source has more than 100 stored events
- **THEN** `total_events`, `events_today`, and `events_last_hour` reflect all qualifying rows rather than the `/events/search` result limit

#### Scenario: Latest event is authoritative
- **WHEN** a source has stored events at multiple timestamps
- **THEN** `last_event_at` equals the maximum qualifying `events.created_at` value for that source

#### Scenario: API failure is read-only and explicit
- **WHEN** the aggregation query cannot be completed
- **THEN** the endpoint returns an error response without mutating events or manufacturing zero-count success data

### Requirement: Exact UTC observation windows
The system SHALL calculate all Source Health time windows from one timezone-aware UTC `generated_at` observation instant and persisted `events.created_at` values.

#### Scenario: Last-hour boundary
- **WHEN** last-hour activity is calculated
- **THEN** `events_last_hour` counts every row whose `created_at` is on or after `generated_at - 1 hour` and on or before `generated_at`

#### Scenario: UTC today boundary
- **WHEN** current-day activity is calculated
- **THEN** `events_today` counts every row from `00:00:00 UTC` on the UTC date of `generated_at` through `generated_at`

#### Scenario: Response discloses boundaries
- **WHEN** Source Health statistics are returned
- **THEN** the response includes `generated_at`, `last_hour_start`, `today_start`, and an explicit `UTC` timezone marker

#### Scenario: Sender timestamps do not redefine activity windows
- **WHEN** an event has an `event_timestamp` different from its database ingestion time
- **THEN** Source Health counts and `last_event_at` use `events.created_at` without changing either timestamp's storage semantics

### Requirement: Stable per-source response contract
Each source entry SHALL expose `source`, `source_type`, `display_label`, `last_event_at`, `events_last_hour`, `events_today`, `total_events`, and `ever_seen` using stable JSON types.

#### Scenario: Previously seen source
- **WHEN** at least one event exists for a recognized source
- **THEN** `ever_seen` is `true`, `last_event_at` is a timezone-aware timestamp, and counts are non-negative integers

#### Scenario: Never-seen source
- **WHEN** no event has ever been stored for a recognized source
- **THEN** `ever_seen` is `false`, `last_event_at` is `null`, and all three counts are `0`

#### Scenario: No unsupported health inference
- **WHEN** the API serializes a source entry
- **THEN** it does not include parser failures, listener health, ingest rejection counts, attempted-ingest timestamps, freshness thresholds, or Healthy/Stale/Offline classifications

### Requirement: Read-only authentication and authorization
The Source Health API and workspace SHALL use the existing analyst-or-super-admin read-only event workspace authorization boundary.

#### Scenario: Authorized analyst access
- **WHEN** an authenticated analyst or super administrator requests Source Health
- **THEN** the API returns the activity response and the workspace is available in navigation

#### Scenario: Unauthenticated access
- **WHEN** a request has no valid authenticated session
- **THEN** the API rejects the request using existing authentication behavior

#### Scenario: Insufficient role
- **WHEN** an authenticated role without Live Logs event-read permission requests Source Health
- **THEN** the API and navigation enforce the existing role restriction

### Requirement: Source Health workspace navigation
The frontend SHALL add Source Health directly beneath Dashboard in the Overview sidebar group and SHALL preserve existing Dashboard behavior.

#### Scenario: Sidebar order
- **WHEN** an authorized user views the Overview navigation group
- **THEN** Dashboard appears first and Source Health appears immediately after it

#### Scenario: Workspace activation
- **WHEN** the user selects Source Health
- **THEN** destination-aware workspace navigation renders and focuses the Source Health workspace at its top

#### Scenario: Dashboard regression protection
- **WHEN** Source Health is added
- **THEN** Dashboard alert loading, filtering, sorting, metrics, charts, polling, and navigation behavior remain unchanged

### Requirement: Complete source activity presentation
The Source Health workspace SHALL render one identifiable row or card per recognized source with its last event, last-hour count, UTC-today count, total count, and ever-seen state.

#### Scenario: Active source data
- **WHEN** a source entry has `ever_seen=true`
- **THEN** the workspace displays its canonical friendly label, last event timestamp, last-hour count, today count, and total count

#### Scenario: Never-seen source data
- **WHEN** a source entry has `ever_seen=false`
- **THEN** the workspace displays an explicit never-seen state, a missing last-event value, and zero counts without hiding the source

#### Scenario: Complete empty dataset
- **WHEN** all six sources have never been seen
- **THEN** the workspace displays all six never-seen entries and an appropriate empty-data explanation

#### Scenario: Loading state
- **WHEN** the initial Source Health request is pending
- **THEN** the workspace exposes a non-misleading loading state without displaying stale zero counts

#### Scenario: Error state
- **WHEN** the Source Health request fails
- **THEN** the workspace exposes an error state and does not represent the failure as six healthy or never-seen sources

### Requirement: Automatic refresh without navigation disruption
The Source Health workspace SHALL refresh using the existing frontend automatic-refresh configuration and SHALL preserve the current workspace focus and scroll position during background refresh.

#### Scenario: Automatic refresh enabled
- **WHEN** the configured automatic refresh interval is nonzero and Source Health is active
- **THEN** the frontend requests updated Source Health statistics at that interval without duplicating timers

#### Scenario: Automatic refresh disabled
- **WHEN** the configured automatic refresh interval is zero
- **THEN** the frontend performs the initial request but does not schedule background polling

#### Scenario: Background data update
- **WHEN** a polling response updates source statistics
- **THEN** the values update without triggering workspace navigation, focus movement, or scroll reset

### Requirement: Source-specific Live Logs navigation
Every Source Health source entry SHALL provide a link or action that opens the existing Live Logs workspace for the same canonical source through the established workspace navigation contract.

#### Scenario: Live Logs destination mapping
- **WHEN** an analyst activates Live Logs from a source entry
- **THEN** the frontend opens the matching destination for Honeypot, Bank App, pfSense, NGINX, Azure Application Insights, or OpenTelemetry without changing the source identity

#### Scenario: Accessible navigation action
- **WHEN** a keyboard or assistive-technology user encounters a source entry
- **THEN** its Live Logs navigation action has an accessible name that includes the friendly source label

### Requirement: No ingest or response behavior changes
The Source Health change SHALL remain read-only and SHALL NOT modify ingestion, parsing, database event insertion, detection, correlation, SOAR, or pfSense behavior.

#### Scenario: Event ingestion regression protection
- **WHEN** any existing source sends an event after Source Health is implemented
- **THEN** its existing validation, normalization, insertion, and downstream processing behavior is unchanged

#### Scenario: No schema migration by default
- **WHEN** implementation confirms the existing source and created-at indexes support the aggregation
- **THEN** no database migration is added
