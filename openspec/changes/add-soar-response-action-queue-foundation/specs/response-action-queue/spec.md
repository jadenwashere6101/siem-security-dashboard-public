## ADDED Requirements

### Requirement: Define response_actions_queue table
The system SHALL define a new `response_actions_queue` table to hold pending response actions for future execution.

#### Scenario: Create queue row
- **WHEN** a response action is enqueued for future execution
- **THEN** the system inserts a new row into `response_actions_queue` with status `pending`, a computed `idempotency_key`, and timestamps for `created_at` and `updated_at`

### Requirement: Support queue status lifecycle
The `response_actions_queue` table SHALL support at least the following statuses: `pending`, `running`, `success`, `failed`, and `skipped`.

#### Scenario: Queue status updates
- **WHEN** a queued action begins execution
- **THEN** its status may be updated to `running`

#### Scenario: Queue success update
- **WHEN** an action completes successfully
- **THEN** its status may be updated to `success` and `updated_at` set to the completion time

#### Scenario: Queue failure update
- **WHEN** an action fails during execution
- **THEN** its status may be updated to `failed`, `retry_count` incremented, and `last_error` recorded

#### Scenario: Queue skipped update
- **WHEN** an action is deliberately not executed because it is no longer necessary or has already completed elsewhere
- **THEN** its status MAY be updated to `skipped`

### Requirement: Track retry metadata on queue records
Each queue record SHALL include `retry_count`, `max_retries`, `last_error`, `created_at`, and `updated_at`.

#### Scenario: Retry metadata exists
- **WHEN** a new queue row is created
- **THEN** `retry_count` SHALL be initialized to `0`, `max_retries` SHALL be set to a configured default or explicit value, `last_error` SHALL be null, and timestamps SHALL be populated

#### Scenario: Retry count increments
- **WHEN** an execution fails and the action is eligible for retry
- **THEN** `retry_count` SHALL increment and `updated_at` SHALL update while `created_at` remains unchanged

### Requirement: Use idempotency key behavior
The queue SHALL include an `idempotency_key` that uniquely identifies a logical response action instance for the same target and alert.

#### Scenario: Duplicate enqueue attempts
- **WHEN** the same logical response action is enqueued more than once
- **THEN** the system SHALL detect the duplicate using `idempotency_key` and avoid creating a second identical pending record

### Requirement: Define enqueue_response_action() helper contract
The system SHALL define an `enqueue_response_action()` helper that accepts action metadata, computes the idempotency key, creates or returns a queue record, and does not require the ingest transaction to remain open after commit.

#### Scenario: Helper contract for post-commit use
- **WHEN** enqueue_response_action() is called as part of a future post-commit step
- **THEN** it SHALL be able to write to `response_actions_queue` using a new DB connection or the committed session, without reading uncommitted ingest transaction state

### Requirement: Keep response_actions_log intact as audit trail
The new queue SHALL be designed to coexist with the existing `response_actions_log` table without replacing it.

#### Scenario: Queue and log coexistence
- **WHEN** the queue foundation is introduced
- **THEN** the existing `response_actions_log` SHALL remain unchanged, and the queue design SHALL include a future reference path to link executed queue entries to log entries if needed

### Requirement: Preserve ingest transaction behavior
This change SHALL not alter the existing ingest → detection → correlation transaction flow.

#### Scenario: No ingest transaction changes
- **WHEN** the queue design is implemented as foundation work
- **THEN** detection and correlation SHALL continue to read uncommitted writes inside the same cursor, and no queue enqueueing SHALL happen inside that transaction in this phase

### Requirement: Define safety requirements for future worker execution
The system SHALL define worker safety requirements such as separate DB connections, idempotent retries, and no reliance on ingest transaction state.

#### Scenario: Worker safety contract
- **WHEN** a future worker processes queue rows
- **THEN** it SHALL open its own DB connection, evaluate each row using `idempotency_key`, and never assume the ingest transaction is still active or the ingest cursor still valid
