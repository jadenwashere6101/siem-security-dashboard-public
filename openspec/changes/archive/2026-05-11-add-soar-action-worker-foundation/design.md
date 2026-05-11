## Current state

- Phase 1A SOAR foundation is complete:
  - `response_actions_queue` table exists.
  - enqueue helper exists (`enqueue_response_action()`).
  - related tests pass.
- Engine modularization is complete:
  - `engines/detection_engine.py`
  - `engines/correlation_engine.py`
  - `engines/ingest_engine.py`
- There is no standalone worker foundation yet for queue consumption and lifecycle management.
- Ingest -> detection -> correlation execution occurs in existing transaction flow and must remain unchanged.

## Proposed worker foundation

Introduce a worker-oriented orchestration module that can:
1. Select and claim eligible queue rows safely.
2. Mark claimed rows `running`.
3. Execute a placeholder action handler (no real firewall/cloud integration in this phase).
4. Persist structured execution outcomes.
5. Transition row status according to success/failure/skip/retry rules.

Initial worker entry points should support deterministic, testable execution:
- `process_next_action(conn, now=None) -> Optional[result]`
- `process_batch(conn, limit=N, now=None) -> list[result]`

Both entry points must be callable from CLI/tests, not from ingest request flow.

## Module/file placement

- `engines/soar_action_worker.py` (new):
  - orchestration entry points (`process_next_action`, `process_batch`)
  - high-level worker flow and outcome mapping
- `core/response_action_queue_store.py` (new or similar):
  - DB helpers for claim and status transitions
  - strict transition validation and update queries
- No new root-level backend modules.
- No changes to detection/correlation/ingest modules beyond future integration points (documented only).

## Queue status lifecycle

Allowed transitions in this phase:
- `pending -> running` (claim succeeds)
- `running -> success` (placeholder execution success)
- `running -> failed` (execution error)
- `failed -> pending` (retryable failure and retry budget remains)
- `running -> skipped` (pre-execution validation/safety check fails)

Rules:
- Transitions are explicit and validated (no implicit jumps).
- Terminal states for this phase: `success`, `skipped` (and `failed` when non-retryable or retries exhausted).
- Each transition updates audit fields (attempt count, timestamps, error/result payload fields already present in schema).

## Retry behavior

Retry model for foundation phase:
- On retryable failure:
  - set row to `failed`,
  - increment attempt metadata,
  - if attempt count < max retries, requeue to `pending` immediately (no scheduling/backoff in Phase 1B).
- On non-retryable failure:
  - remain `failed` (terminal for now).
- Backoff/scheduling is intentionally omitted in Phase 1B to keep behavior deterministic and testable.

The design must ensure retries are bounded and observable.

## Idempotency and duplicate safety

Duplicate safety requirements:
- Claim query must be concurrency-safe for multiple workers (for example via row lock semantics such as `FOR UPDATE SKIP LOCKED` pattern).
- Claim operation and transition to `running` should be atomic.
- Worker must verify row is still in expected prior state before state change updates.
- Re-processing of terminal states is forbidden by selection query.

Idempotency considerations:
- Queue-level idempotency key created in Phase 1A remains source of enqueue dedupe.
- Worker foundation should treat each claimed queue row as single execution unit; any future external side effects must key off queue id/idempotency key.

Stuck running jobs:
- **Stale timeout**: \(15 minutes\).
- **Recovery policy** (explicit helper, not ingest/request flow):
  - `running -> pending` if `retry_count < max_retries`
  - `running -> failed` if `retry_count >= max_retries`
- Recovery behavior is part of foundation design and tests, even if scheduler wiring is deferred.

## Failure handling

Failure categories:
- Validation/safety failure -> `skipped` with structured reason.
- Retryable execution failure -> `failed` then `pending` (if retry budget remains).
- Non-retryable/unexpected failure -> `failed` terminal.

Structured result object (internal contract) should include:
- queue row id
- prior status/new status
- outcome type (`success`, `failed`, `skipped`, `requeued`)
- retryable flag
- attempt counters
- machine-readable error code/reason
- human-readable summary message

This structured result supports deterministic tests and future observability endpoints.

## Testing strategy

Add DB-backed tests that cover:
- Claiming:
  - single worker claims pending row.
  - concurrent claim attempts do not double-claim same row.
- Status transitions:
  - valid transitions succeed.
  - invalid transitions are rejected.
- Retry:
  - retryable failure requeues when attempts remain.
  - exhausted retries remain terminal `failed`.
- Skip:
  - validation/safety path marks row `skipped`.
- Stuck running recovery:
  - stale `running` row becomes recoverable according to policy.
- Regression guard:
  - existing ingest/detection/correlation behavior unchanged.
  - existing `response_actions_log` behavior unchanged.

No test in this phase executes real network/firewall/cloud actions.

## Future integration points

Planned later phases (not implemented here):
- enqueue from detection/correlation decisions.
- worker runner command and scheduler integration (cron/systemd/container worker).
- real action adapters (firewall/cloud).
- queue/worker observability APIs and UI.
- migration from placeholder executor to real policy-driven execution engine.
