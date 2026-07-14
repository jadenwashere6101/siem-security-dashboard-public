## ADDED Requirements

### Requirement: Persisted daemon heartbeat
The system SHALL persist a process-level heartbeat for the logical `playbook_worker` independently of playbook execution leases. The heartbeat persistence model SHALL remain future-safe by recording worker name and worker instance identity, but this change SHALL manage only one logical worker. The heartbeat SHALL be written to durable storage on startup and refreshed at least once every 15 seconds while the daemon is running, including idle periods with no eligible executions.

#### Scenario: Idle worker reports healthy
- **WHEN** the playbook worker daemon is running and no eligible playbook executions are available
- **THEN** the daemon SHALL continue refreshing its persisted heartbeat without requiring an active execution row
- **AND** worker health SHALL be eligible to report `healthy`

#### Scenario: Worker restart refreshes daemon identity
- **WHEN** the playbook worker process restarts after a prior heartbeat was recorded
- **THEN** it SHALL write a new heartbeat immediately on startup
- **AND** it SHALL update the current persisted worker instance identity and process start time without deleting the logical worker record

#### Scenario: Build version is available
- **WHEN** the daemon can safely resolve a deterministic build or revision identifier at startup
- **THEN** it SHALL persist that build/version metadata alongside the daemon heartbeat
- **AND** the worker health API SHALL expose it for read-only operational visibility

#### Scenario: Heartbeat persistence fails
- **WHEN** the daemon cannot persist a heartbeat because the database write fails
- **THEN** it SHALL log the failure and continue bounded retry or backoff behavior
- **AND** it SHALL NOT repurpose execution lease heartbeats or alter playbook execution semantics to compensate

### Requirement: Deterministic daemon health states
The system SHALL derive playbook-worker daemon health from the persisted daemon heartbeat rather than from execution lease timestamps, integration enablement, or queue activity. Health states SHALL use these exact thresholds: `unknown` when no heartbeat has ever been recorded, `healthy` when the last heartbeat is at most 45 seconds old, `degraded` when the last heartbeat is more than 45 seconds old and at most 120 seconds old, and `offline` when the last heartbeat is more than 120 seconds old. The system SHALL also expose process start time and uptime derived from the current persisted worker row.

#### Scenario: Never-seen worker is unknown
- **WHEN** no persisted daemon heartbeat exists for the playbook worker
- **THEN** `GET /metrics/playbook-worker` SHALL return `daemon_health.status = "unknown"`
- **AND** `daemon_health.last_heartbeat_at` SHALL be `null`
- **AND** `daemon_health.started_at` SHALL be `null`
- **AND** `daemon_health.uptime_seconds` SHALL be `null`
- **AND** `daemon_health.worker_heartbeat_available` SHALL be `false`

#### Scenario: Recent heartbeat is healthy
- **WHEN** the persisted daemon heartbeat is at most 45 seconds old
- **THEN** `GET /metrics/playbook-worker` SHALL return `daemon_health.status = "healthy"`
- **AND** the response SHALL include the persisted `last_heartbeat_at`
- **AND** the response SHALL include the current process `started_at` and non-negative `uptime_seconds`

#### Scenario: Late heartbeat is degraded
- **WHEN** the persisted daemon heartbeat is more than 45 seconds old and at most 120 seconds old
- **THEN** `GET /metrics/playbook-worker` SHALL return `daemon_health.status = "degraded"`
- **AND** `daemon_health.message` SHALL explain that the heartbeat is late but not yet offline

#### Scenario: Expired heartbeat is offline
- **WHEN** the persisted daemon heartbeat is more than 120 seconds old
- **THEN** `GET /metrics/playbook-worker` SHALL return `daemon_health.status = "offline"`
- **AND** `daemon_health.message` SHALL explain that the final heartbeat timeout has been exceeded

## MODIFIED Requirements

### Requirement: Worker operational visibility
The system SHALL expose read-only operational visibility for worker health, queue depth, stale execution counts, recovery counts, and failure rates through the existing SOAR metrics or operations surfaces. Authorized users SHALL receive daemon health status, last heartbeat timestamp, process start time, uptime, build/version when available, and concise explanatory text without exposing mutation controls to viewers.

#### Scenario: Analyst views worker health
- **WHEN** an authorized analyst or super admin opens SOAR metrics or operations visibility
- **THEN** the system SHALL provide current worker and queue health
- **AND** the worker health payload SHALL include `status`, `worker_heartbeat_available`, `last_heartbeat_at`, `started_at`, `uptime_seconds`, optional build/version metadata, and concise reason text suitable for direct UI rendering
- **AND** viewer users SHALL remain excluded from worker operational data

#### Scenario: Worker heartbeat has never been seen
- **WHEN** the worker health API reports `status = "unknown"`
- **THEN** the UI SHALL render an explicit never-seen worker state with text that does not imply healthy service or zero activity
- **AND** the UI SHALL remain stable without crashing other dashboard sections

#### Scenario: Worker status is degraded or offline
- **WHEN** the worker health API reports `status = "degraded"` or `status = "offline"`
- **THEN** the UI SHALL display a clear text status badge, the last heartbeat timestamp, and concise explanatory text
- **AND** the state SHALL NOT rely on color alone for meaning

#### Scenario: Worker metadata is available
- **WHEN** the worker health API includes process start time, uptime, or build/version metadata
- **THEN** the UI SHALL display those values with visible text labels
- **AND** the UI SHALL fall back gracefully when build/version is unavailable

#### Scenario: Worker metrics load or fail
- **WHEN** worker metrics are loading or the worker metrics request fails
- **THEN** the UI SHALL present accessible loading or error text
- **AND** other SOAR metrics sections SHALL continue rendering independently

#### Scenario: Narrow layout renders worker health
- **WHEN** the Worker Operations section is rendered in a narrow layout
- **THEN** the status badge, last heartbeat timestamp, and explanatory text SHALL remain visible without hover-only affordances
