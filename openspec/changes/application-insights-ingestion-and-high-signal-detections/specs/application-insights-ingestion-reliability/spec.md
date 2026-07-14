## ADDED Requirements

### Requirement: Ingestion checkpoint prevents silent data loss
The system SHALL persist a durable checkpoint watermark for Application Insights ingestion, and the Azure Function's polling query SHALL use that checkpoint as its lower time bound instead of a fixed rolling window, so that a missed, delayed, or failed poll cannot permanently lose telemetry generated in the gap.

#### Scenario: Checkpoint advances only past successfully processed telemetry
- **WHEN** a poll successfully processes telemetry rows up to a given `TimeGenerated` value
- **THEN** the persisted checkpoint SHALL advance to that value, and the next poll's query SHALL start from that checkpoint rather than from a fixed `ago(N minutes)` window.

#### Scenario: A missed poll does not lose events
- **WHEN** the Azure Function fails to run for one or more scheduled intervals (e.g., a transient outage) and then runs successfully again
- **THEN** the next successful poll SHALL query from the last persisted checkpoint, not from `now - 5 minutes`, so all telemetry generated during the gap is still retrieved.

#### Scenario: Checkpoint read failure falls back to a bounded default, not unbounded backfill
- **WHEN** the Azure Function cannot read the persisted checkpoint (e.g., the checkpoint endpoint is unreachable)
- **THEN** it SHALL fall back to a bounded default lookback window (not less than 15 minutes, not more than 1 hour) rather than either failing the poll entirely or querying an unbounded historical range.

### Requirement: Polling handles volume above a single page without silent truncation
The system SHALL page through Application Insights telemetry above a configured per-page size within a single poll invocation, bounded by a maximum page count, rather than silently discarding rows beyond a fixed record cap.

#### Scenario: A burst larger than one page is fully retrieved within the same poll cycle
- **WHEN** more telemetry rows exist in the checkpoint-to-now window than fit in one page
- **THEN** the Function SHALL query subsequent pages within the same invocation (up to the configured maximum page count) and advance the checkpoint only as far as it successfully processed, rather than dropping the excess rows.

#### Scenario: A burst larger than the maximum page count is picked up on the next poll
- **WHEN** the number of pages needed exceeds the configured maximum pages per invocation
- **THEN** the checkpoint SHALL advance only through the pages actually processed, and the remaining telemetry SHALL be retrieved on the next scheduled poll — no telemetry SHALL be permanently skipped.

### Requirement: Transient failures are retried, not immediately dropped
Both the Log Analytics query and the forward-to-SIEM HTTP call SHALL retry a bounded number of times with backoff on transient failure before being counted as failed for that poll.

#### Scenario: A transient query failure is retried before the poll is abandoned
- **WHEN** `_query_recent_telemetry` raises a transient error
- **THEN** the Function SHALL retry up to a configured bounded number of attempts with backoff before logging the poll as failed; a poll that fails after retries SHALL NOT advance the checkpoint.

#### Scenario: A transient forward failure is retried per row
- **WHEN** `forward_telemetry_to_siem` fails for a specific row due to a transient network or server error
- **THEN** the Function SHALL retry that row up to a configured bounded number of attempts with backoff before counting it as a failure for that poll.

### Requirement: Application-tier authentication-abuse telemetry is classified consistently
`AppRequests` telemetry with `resultCode` 401 or 403 SHALL be classified as an authentication-abuse event type by both the Azure Function's row classification and the backend's `azure_insights_adapter` normalizer, so the signal is not silently downgraded between the two layers.

#### Scenario: A 401/403 request is not classified as normal_activity
- **WHEN** `normalize_azure_insights_telemetry` processes a request/dependency-type telemetry item with `result_code` 401 or 403
- **THEN** it SHALL return `event_type = "unauthorized_access"`, not `"normal_activity"`.

#### Scenario: Function and backend classification agree
- **WHEN** the Azure Function's `_classify_telemetry_row` classifies a row as `"unauthorized_access"` and forwards it to `/ingest/azure`
- **THEN** the backend's normalization of that same payload SHALL also resolve to `event_type = "unauthorized_access"` — the two layers SHALL NOT disagree on this classification.

### Requirement: Ingestion covers dependency and availability failures, not raw call volume or general traces
The system SHALL ingest `AppDependencies` failure rows and `AppAvailabilityResults` failure rows, and SHALL NOT ingest successful dependency calls, custom events, custom metrics, or general-purpose trace telemetry.

#### Scenario: Dependency failures are ingested, successful dependency calls are not
- **WHEN** the Application Insights KQL query runs
- **THEN** it SHALL include `AppDependencies` rows where `Success == false`, and SHALL NOT include `AppDependencies` rows where `Success == true`.

#### Scenario: Availability failures are ingested, successful availability tests are not
- **WHEN** the Application Insights KQL query runs
- **THEN** it SHALL include `AppAvailabilityResults` rows where `Success == false`, and SHALL NOT include successful availability results.

#### Scenario: The demo-only trace query is removed
- **WHEN** the Application Insights KQL query is reviewed after this change
- **THEN** it SHALL NOT include an `AppTraces` clause matching the literal string `"HTTP request received"` or any other general-purpose trace pattern; custom events and custom metrics tables SHALL NOT be queried.

### Requirement: Poll outcome is visible without a second health system
Each poll's outcome (success, failure, or partial; row counts; checkpoint watermark) SHALL be recorded and surfaced through the existing Source Health workspace/API, not a new, separate health surface.

#### Scenario: A failed poll is distinguishable from genuinely absent telemetry
- **WHEN** an analyst checks Source Health for the `azure_insights` source after a period with no new events
- **THEN** the response SHALL indicate whether the most recent poll succeeded with no new telemetry, or failed, rather than only showing event-arrival staleness with no explanation.

#### Scenario: Poll-health reuses the existing Source Health surface
- **WHEN** poll-health data is added
- **THEN** it SHALL be exposed as additional fields on the existing `core/source_health.py` aggregation for the `azure_insights` source, and SHALL NOT introduce a separate "Application Health" or "Connector Health" API or workspace.

### Requirement: Ingestion operational settings do not require a new SIEM-DB configuration surface
Polling interval, page size, maximum pages per invocation, retry attempts/backoff, and query/HTTP timeouts SHALL remain Azure Function application settings; they SHALL NOT be added to the SIEM's runtime-configurable detection settings.

#### Scenario: Changing the polling cadence does not require a SIEM configuration change
- **WHEN** an operator wants to change how often the Function polls
- **THEN** they SHALL do so via the Function's timer schedule/app settings, not via any SIEM admin API or database row.
