## ADDED Requirements

### Requirement: Durable Canonical Push-Source State
The system SHALL persist one bounded health-state record per observed canonical push source containing the latest stored-event ingestion timestamp, latest qualifying real-ingestion timestamp, historical-backfill completion state, resumable backfill position, and update timestamp.

#### Scenario: Canonical push event is persisted
- **WHEN** a normalized event for a canonical push source is successfully inserted
- **THEN** its durable source state SHALL be updated in the same transaction using the database ingestion timestamp

#### Scenario: Checkpoint event is persisted
- **WHEN** a normalized event for a checkpoint-driven source is inserted
- **THEN** that event SHALL increment its initialized informational total but SHALL NOT replace the checkpoint as the source's health authority

#### Scenario: Unsupported direct writer
- **WHEN** an external process bypasses the supported normalized application persistence path
- **THEN** the system SHALL document that writer as unsupported and SHALL NOT claim its state is maintained

### Requirement: Monotonic Operational Ingestion State
The system SHALL use the existing canonical synthetic provenance policy to distinguish qualifying real ingestion and SHALL update durable timestamps monotonically.

#### Scenario: Recent real push event
- **WHEN** a qualifying real push event commits with a newer ingestion timestamp
- **THEN** both latest-event and latest-qualifying-real timestamps SHALL advance

#### Scenario: Synthetic push event
- **WHEN** a synthetic, demo, simulated, smoke, seed, or test push event commits
- **THEN** latest-event MAY advance but latest-qualifying-real SHALL NOT advance

#### Scenario: Out-of-order state update
- **WHEN** a state update carries a timestamp older than the stored timestamp
- **THEN** neither durable timestamp SHALL move backward

#### Scenario: Event transaction fails
- **WHEN** canonical event persistence is rolled back
- **THEN** its health-state mutation SHALL also be rolled back

### Requirement: Bounded Resumable Historical Backfill
The system SHALL initialize existing push-source state through an explicit deterministic backfill that captures a high-water event ID, processes bounded primary-key ranges, commits progress atomically, and can resume safely.

#### Scenario: Initial backfill start
- **WHEN** backfill begins without an existing high-water mark
- **THEN** it SHALL capture the current maximum event ID once and persist the same boundary for all canonical push sources

#### Scenario: Backfill batch succeeds
- **WHEN** one bounded ID range is processed
- **THEN** the system SHALL atomically merge timestamp maxima and advance the persisted cursor

#### Scenario: Backfill is interrupted
- **WHEN** execution stops after a committed batch
- **THEN** a later invocation SHALL resume after the stored cursor without restarting completed ranges

#### Scenario: Backfill is repeated
- **WHEN** the command is rerun after completion
- **THEN** it SHALL be idempotent and perform no historical rescan

#### Scenario: Live ingestion overlaps backfill
- **WHEN** a newer live event updates state while older historical batches are processed
- **THEN** monotonic merging SHALL preserve the newer live timestamps

#### Scenario: Backfill completes
- **WHEN** the persisted cursor has processed the captured high-water range
- **THEN** historical-backfill completion SHALL be marked true for every canonical push source and not before

### Requirement: Bounded Runtime Source Health
Runtime source-health aggregation SHALL read only durable per-source state and checkpoint state and SHALL perform work proportional to canonical source count, independent of event-table size.

#### Scenario: Runtime health is requested
- **WHEN** `/source-health` or a NIST assessment requests a source-health snapshot
- **THEN** runtime health SQL SHALL NOT reference or scan `events`

#### Scenario: Durable state is absent or incomplete
- **WHEN** a push source has no qualifying timestamp and durable historical knowledge is missing or incomplete
- **THEN** health SHALL fail closed as Unknown and SHALL NOT fall back to event history

#### Scenario: Event volume grows
- **WHEN** event-table size grows from a small fixture to millions of rows after state initialization
- **THEN** the source-health read plan and maximum returned state rows SHALL remain effectively constant

### Requirement: Preserved Push and Checkpoint Semantics
The system SHALL preserve established freshness thresholds and health outcomes for push and checkpoint sources.

#### Scenario: Recent qualifying push ingestion
- **WHEN** latest qualifying real ingestion is within the source freshness threshold
- **THEN** push health SHALL be Healthy

#### Scenario: Stale qualifying push ingestion
- **WHEN** a qualifying real timestamp exists but is older than the source freshness threshold
- **THEN** push health SHALL be Degraded even if a newer synthetic event exists

#### Scenario: Completed history has no qualifying ingestion
- **WHEN** historical backfill is complete and no qualifying real timestamp exists
- **THEN** push health SHALL be Unknown with no qualifying ingestion established

#### Scenario: Fresh successful checkpoint
- **WHEN** a checkpoint source has a fresh successful checkpoint
- **THEN** checkpoint health SHALL be Healthy

#### Scenario: Unhealthy checkpoint
- **WHEN** a checkpoint is stale, partial, or failed
- **THEN** checkpoint health SHALL be Degraded

#### Scenario: Missing checkpoint
- **WHEN** a checkpoint source has no checkpoint
- **THEN** checkpoint health SHALL be Unknown

### Requirement: Health-Focused API Contract
The synchronous source-health API SHALL return canonical identity, health status and reason, freshness basis, bounded durable timestamps, historical-completion state, and an independently maintained lifetime event total without calculating event-history statistics during requests.

#### Scenario: Analyst views source health
- **WHEN** an authorized analyst opens the Source Health workspace
- **THEN** the UI SHALL clearly present health and freshness using the bounded API response

#### Scenario: Historical counters are unavailable cheaply
- **WHEN** rolling event counts would require runtime event-history work
- **THEN** the health endpoint SHALL omit those rolling counters rather than execute an expensive compatibility query

#### Scenario: Lifetime event volume is displayed
- **WHEN** the durable canonical-source total has been initialized
- **THEN** the Source Health card SHALL display that total without using it to determine health

#### Scenario: Lifetime total is not initialized
- **WHEN** the durable total is unavailable or initialization is incomplete
- **THEN** health SHALL still render and the total SHALL be presented as unavailable rather than zero

### Requirement: NIST Confidence Preservation
NIST assessment runs SHALL consume the bounded canonical health snapshot while preserving evidence and confidence safeguards.

#### Scenario: Healthy real evidence exists
- **WHEN** a qualifying real push source is Healthy and all required operational evidence is available
- **THEN** NIST evidence status SHALL remain able to reach `evidence_available`

#### Scenario: Collection health is degraded or unknown
- **WHEN** a required source is Degraded or Unknown
- **THEN** an empty completed collector SHALL NOT produce `no_evidence_found`

#### Scenario: Evidence is synthetic
- **WHEN** evidence is classified as synthetic under the existing policy
- **THEN** it SHALL NOT establish operational evidence or Healthy push ingestion
