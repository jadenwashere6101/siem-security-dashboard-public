## ADDED Requirements

### Requirement: Bounded alert summary map markers
The system SHALL cap `/alerts/summary` map markers with a configurable hard limit and SHALL enforce that limit before application enrichment and JSON serialization.

#### Scenario: Map markers are capped before serialization
- **WHEN** the filtered alert set contains more geolocated source IPs than the configured map-marker limit
- **THEN** `/alerts/summary` SHALL return no more than the configured limit in `map_markers`
- **AND** marker enrichment SHALL only run for the returned marker rows.

#### Scenario: Map marker metadata reports truncation
- **WHEN** the filtered geolocated source IP count is greater than the configured map-marker limit
- **THEN** the response SHALL include `map_markers_total` equal to the filtered geolocated source IP count
- **AND** `map_markers_returned` equal to the number of returned markers
- **AND** `map_markers_truncated` set to `true`.

#### Scenario: Map marker metadata reports non-truncated results
- **WHEN** the filtered geolocated source IP count is less than or equal to the configured map-marker limit
- **THEN** `map_markers_total` SHALL equal the filtered geolocated source IP count
- **AND** `map_markers_returned` SHALL equal the number of returned markers
- **AND** `map_markers_truncated` SHALL be `false`.

#### Scenario: Non-map summary behavior is preserved
- **WHEN** `/alerts/summary` is requested with existing filters
- **THEN** metrics, top source IPs, timeline data, and synthetic/demo source exclusion behavior SHALL remain accurate according to the existing contracts.

### Requirement: Dashboard map truncation notice
The frontend SHALL clearly indicate when the map is displaying a capped subset of sources.

#### Scenario: Truncated map response is visible
- **WHEN** `/alerts/summary` returns `map_markers_truncated: true`
- **THEN** the dashboard map SHALL show a concise notice such as "Showing top N of M sources"
- **AND** the map SHALL render only the returned markers.

#### Scenario: Non-truncated map response has no truncation warning
- **WHEN** `/alerts/summary` returns `map_markers_truncated: false`
- **THEN** the dashboard map SHALL NOT show the truncation notice.

### Requirement: Resilient geolocation lookup on ingest
The system SHALL prevent unavailable, empty, malformed, non-JSON, or provider-error geolocation responses from being retried synchronously for nearly every ingest event.

#### Scenario: Successful geolocation is cached
- **WHEN** a provider returns a valid successful geolocation response for an IP
- **THEN** subsequent lookups for that IP within the cache lifetime SHALL use the cached location
- **AND** SHALL NOT call the provider again.

#### Scenario: Unknown or malformed geolocation is negatively cached
- **WHEN** a provider response is unavailable, empty, malformed, non-JSON, or reports a non-success status
- **THEN** lookup SHALL return an unknown location shape without inventing location data
- **AND** subsequent lookups within the negative-cache TTL SHALL NOT call the provider again for that IP.

#### Scenario: Provider circuit breaker limits repeated failures
- **WHEN** repeated provider failures reach the configured failure threshold
- **THEN** lookup SHALL open a short provider cooldown window
- **AND** additional lookups during the cooldown SHALL return unknown without calling the provider.

#### Scenario: Geolocation failure logs are bounded
- **WHEN** repeated provider failures occur within the log throttle window
- **THEN** the system SHALL avoid emitting one failure log per ingest event
- **AND** SHALL still expose useful failure visibility through throttled warning/error logs.

#### Scenario: Ingest succeeds while geolocation is unavailable
- **WHEN** pfSense or generic ingest receives a valid event and geolocation is unavailable
- **THEN** ingestion SHALL continue without blocking or rejecting the event for geolocation failure
- **AND** the event SHALL NOT receive fabricated location values.

#### Scenario: Provider recovery after cooldown
- **WHEN** the negative-cache TTL or provider cooldown expires and the provider returns a valid response
- **THEN** lookup SHALL call the provider again
- **AND** cache and return the successful location.
