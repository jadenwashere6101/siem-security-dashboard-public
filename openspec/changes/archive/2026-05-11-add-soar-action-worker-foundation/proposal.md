## Problem

SOAR foundation work currently stops at queue insertion. The project has a `response_actions_queue` table and enqueue helper, but no worker foundation that can safely claim queued rows, advance status transitions, and produce structured execution outcomes outside request/ingest transactions. This blocks safe progression toward asynchronous response execution.

## Goal

Define and implement a first worker foundation that:
- processes `response_actions_queue` records outside ingestion/request flow,
- supports safe queue claiming for one or more worker processes,
- applies explicit status transitions (`pending`, `running`, `success`, `failed`, `skipped`) with retry support,
- prepares structured execution result payloads without executing real firewall/cloud actions,
- preserves existing `response_actions_log` behavior.

## Why this is the next safe SOAR step

This is the smallest operational step after queue creation:
- It validates queue lifecycle mechanics before introducing real integrations.
- It keeps ingest, detection, and correlation behavior untouched.
- It de-risks future automation by proving claim/retry/idempotency semantics in isolation.
- It is fully testable with deterministic DB-backed tests and no external side effects.

## In scope

- Worker foundation module under `engines/` for queue orchestration.
- DB helpers for row claim and status transitions (under `engines/` or `core/` as appropriate).
- Status lifecycle support:
  - `pending -> running`
  - `running -> success`
  - `running -> failed`
  - `failed -> pending` when retryable
  - `running -> skipped` when validation/safety requires skipping
- Structured execution result format for internal worker outcomes.
- Retry policy primitives (attempt counting, retryable failure handling, next attempt scheduling strategy).
- Guardrails for duplicate worker safety and stuck `running` recovery strategy (defined behavior and test coverage).
- Unit/integration tests for claim, transition, retry, and duplicate safety behavior.

## Out of scope

- Wiring worker invocation into ingest/request handling.
- Enqueue triggers from detection/correlation engines.
- Real firewall/cloud execution adapters.
- Background scheduler/systemd/daemon deployment wiring.
- Frontend UI for queue/worker status.
- Behavior changes to `execute_response_action()`.
- Any changes to ingest -> detection -> correlation transaction flow.

## Risks

- Incorrect claim semantics could allow duplicate processing by concurrent workers.
- Transition bugs could strand rows in `running` or create invalid state jumps.
- Retry logic could create tight failure loops without cooldown/backoff.
- Incomplete idempotency checks could duplicate downstream effects in future phases.
- Scope creep into integration wiring could accidentally touch ingest transaction boundaries.

## Success criteria

- A worker foundation API exists and is isolated from request/ingest flow.
- Queue rows can be safely claimed by one worker at a time under concurrent test conditions.
- All required status transitions are implemented with explicit validation.
- Retryable failures can be re-queued predictably; non-retryable outcomes are terminal.
- Structured execution results are produced consistently for success/failure/skipped paths.
- Existing `response_actions_log` behavior remains unchanged.
- Existing ingest/detection/correlation tests remain green with no transaction behavior regression.
