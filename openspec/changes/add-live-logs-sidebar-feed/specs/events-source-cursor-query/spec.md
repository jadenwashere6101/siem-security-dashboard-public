## ADDED Requirements

### Requirement: Full source allowlist for event queries
The events-read API SHALL accept all six live ingestion sources as valid values for source-filtered queries: `honeypot`, `bank_app`, `pfsense`, `nginx`, `azure_insights`, `opentelemetry`.

#### Scenario: Honeypot source is accepted
- **WHEN** a request filters events by `source=honeypot`
- **THEN** the API returns a 200 response with only honeypot events, instead of rejecting the source as invalid

#### Scenario: pfSense source is accepted
- **WHEN** a request filters events by `source=pfsense`
- **THEN** the API returns a 200 response with only pfsense events, instead of rejecting the source as invalid

#### Scenario: Unknown source is still rejected
- **WHEN** a request filters events by a source value not in the six live sources
- **THEN** the API returns a validation error, consistent with current allowlist-rejection behavior

### Requirement: Cursor-based polling without duplicate rows
The events-read API SHALL support an optional cursor parameter (based on the event's monotonic primary key) that, when provided, returns only events created after the given cursor for the requested source, ordered newest first.

#### Scenario: First fetch with no cursor
- **WHEN** a client requests events for a source with no cursor parameter
- **THEN** the API returns the most recent events for that source, newest first, up to the existing result limit

#### Scenario: Subsequent poll with cursor returns only new rows
- **WHEN** a client requests events for a source using the highest event id it previously received as the cursor
- **THEN** the API returns only events for that source with an id greater than the cursor, and never re-returns a previously delivered event

#### Scenario: No new events since last poll
- **WHEN** a client polls with a cursor equal to the latest event id for that source
- **THEN** the API returns an empty result set rather than an error

### Requirement: Existing auth conventions preserved
The events-read API SHALL continue to require the same authentication and role checks it requires today for all source values, including the newly accepted `honeypot` and `pfsense` sources.

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request with no valid session is made to the events-read endpoint for any source, including honeypot or pfsense
- **THEN** the API returns a 401 response, matching current unauthenticated behavior

#### Scenario: Authenticated but insufficient role is rejected
- **WHEN** a request is made by an authenticated user lacking the required analyst-or-super-admin role
- **THEN** the API returns an authorization error, matching current role-enforcement behavior
