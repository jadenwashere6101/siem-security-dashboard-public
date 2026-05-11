## Why

Response actions are currently triggered in the same ingest transaction as detection and correlation. That tight coupling violates the SOAR roadmap goal of async action execution and risks breaking the existing transaction semantics that detection and correlation rely on.

## What Changes

- Add a new capability: `response-action-queue`.
- Define a DB-backed `response_actions_queue` table as the foundation for async action execution.
- Specify queue statuses: `pending`, `running`, `success`, `failed`, `skipped`.
- Define queue metadata fields: `retry_count`, `max_retries`, `last_error`, `created_at`, and `updated_at`.
- Specify idempotency key behavior to make retries safe and avoid duplicate action execution.
- Define an `enqueue_response_action()` helper design for future enqueueing after the ingest transaction commits.
- Define how the new queue design connects to existing `response_actions_log` without replacing it.
- Specify safety requirements for future worker execution and the strict transaction boundary.

## Capabilities

### New Capabilities
- `response-action-queue`: Defines the foundational database-backed queue model and enqueue semantics for SOAR response actions, including status tracking, retry metadata, and idempotency.

### Modified Capabilities
- 

## Impact

- Adds a new OpenSpec capability and design for SOAR async response actions.
- Impacts database schema design and future worker integration points.
- Leaves existing ingest, detection, correlation, and response action execution unchanged for this phase.
- Provides a safe upgrade path to connect to `response_actions_log` later without replacing it.
