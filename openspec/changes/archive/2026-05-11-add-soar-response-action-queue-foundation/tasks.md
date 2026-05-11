## 1. Define queue foundation

- [x] 1.1 Create the `response_actions_queue` schema/model with fields for status, retry metadata, idempotency key, and timestamps
- [x] 1.2 Define allowed queue statuses: `pending`, `running`, `success`, `failed`, and `skipped`
- [x] 1.3 Add schema documentation describing how queue rows relate to existing `response_actions_log`

## 2. Define enqueue helper

- [x] 2.1 Add `enqueue_response_action()` helper contract in the core response helper module
- [x] 2.2 Implement deterministic idempotency key generation and duplicate detection behavior
- [x] 2.3 Document that enqueueing must be executed only after the ingest transaction commits

## 3. Define safety and testing requirements

- [x] 3.1 Capture worker safety requirements for separate DB connections and idempotent retry behavior in design documentation
- [x] 3.2 Add unit tests for queue schema defaults, status transitions, and idempotency behavior
- [x] 3.3 Add integration guidance for future worker execution that verifies no ingest transaction changes are required
