## SOAR Action Worker Foundation Tasks

- [ ] Inspect existing queue schema and helper behavior
  - Review `response_actions_queue` schema fields and constraints.
  - Review `enqueue_response_action()` semantics and current tests.
  - Confirm current `response_actions_log` behavior to preserve.

- [ ] Design worker module interface
  - Define worker entry points (`process_next_action`, `process_batch`).
  - Define structured execution result contract for worker outcomes.
  - Define explicit transition validation rules and stale-running recovery contract.
  - Fix deterministic Phase 1B policies:
    - stale running timeout: 15 minutes
    - recovery: `running -> pending` if `retry_count < max_retries`, else `running -> failed`
    - retry backoff: none; requeue immediately when retryable

- [ ] Implement queue claim helper
  - Add DB helper to claim eligible `pending` rows safely for concurrent workers.
  - Ensure claim and `pending -> running` transition are atomic.
  - Ensure already-claimed rows cannot be double-processed.

- [ ] Implement status transition helpers
  - Add validated transition helpers for:
    - `running -> success`
    - `running -> failed`
    - `failed -> pending` (retryable)
    - `running -> skipped`
  - Persist attempt/error/result metadata consistently.

- [ ] Add tests for claiming/status transitions/retries
  - Add tests for safe claim under concurrency assumptions.
  - Add tests for valid/invalid transitions.
  - Add tests for retryable vs terminal failure paths.
  - Add tests for skipped path and stuck-running recovery behavior.
  - Keep tests deterministic and side-effect free (no real external action execution).

- [ ] Verify no ingest/detection/correlation behavior changed
  - Re-run ingest/detection/correlation suites.
  - Confirm ingest transaction flow remains unchanged.
  - Confirm no worker execution is wired into request/ingest path.

- [ ] Run full backend tests
  - Run full `pytest` backend suite.
  - Confirm `response_actions_log` behavior remains unchanged.
  - Address regressions before moving to integration phase.
