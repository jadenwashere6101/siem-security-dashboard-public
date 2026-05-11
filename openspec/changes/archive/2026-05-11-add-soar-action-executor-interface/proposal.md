## Problem

The SOAR worker (Phase 1B) is complete and functional, but its execution layer is a stub. `placeholder_execute_action()` in `engines/soar_action_worker.py` accepts a queue row and returns a hardcoded `"placeholder_success"` result. It has no validation, no action-type-specific behavior, and no stable interface contract. Any future real adapter that replaces it would have to guess what the worker expects and what it needs to return.

Without a formal executor interface, plugging in real action handlers in Phase 3 (firewall, Slack, cloud blocking) requires modifying the worker's internals rather than dropping in a new executor. This creates coupling that the current dependency-injection design is trying to avoid.

## Goal

Define a stable executor interface and a simulation-mode executor that:
- Replaces the placeholder with real action-type-specific behavior (still no external calls).
- Establishes the callable contract that Phase 3 real adapters will implement.
- Validates queue row inputs before any execution attempt.
- Produces structured result objects that the worker can rely on.
- Makes simulation mode explicit and safe by design — no real network or DB writes can happen through it.

## Why this is the next safe SOAR step

The worker already accepts an `executor` parameter for dependency injection. The interface is fully definable in pure Python without touching any production code, existing tests, or ingest/detection/correlation behavior. Defining the interface now means future real integrations can be dropped in as adapters without requiring any change to the worker itself. This is the smallest possible step between the placeholder and real execution.

## In scope

- Formal executor callable interface definition: signature, return contract, exception contract.
- Structured result dict format: mandatory fields (`code`, `message`), optional fields (`details`).
- Per-action validation rules before execution for `block_ip`, `flag_high_priority`, and `monitor`.
- Simulation executor (`SimulationExecutor`) implementing the interface for all three action types with no external side effects.
- Behavior for unknown action types: raise `SkippedAction`.
- Module placement decision: `engines/soar_executor.py`.
- Documented adapters/ directory contract for future real integrations.
- Test contract for executor result handling (tests to be added in implementation step).

## Out of scope

- No real firewall blocking, Azure NSG calls, or cloud API calls.
- No systemd, cron, or background scheduler wiring.
- No frontend UI.
- No changes to ingest, detection, or correlation behavior.
- No changes to `execute_response_action()` in `core/ip_helpers.py` (it remains synchronous inside ingest; decoupling is future work, documented only).
- No writes to `response_actions_log` from the executor (log writing from the worker path is deferred to a later phase).
- No changes to existing `response_actions_log` behavior.
- Minimal changes to `engines/soar_action_worker.py`: remove placeholder, update exception imports to use `soar_errors`, add result validation. Worker orchestration flow is otherwise unchanged.

## Risks

- **Interface too narrow**: future adapters may need additional row fields or kwargs the current contract does not accommodate. Design the interface to pass the full row dict so nothing is dropped.
- **Validation over-reach**: validation rules that are too strict could skip legitimate actions. Each validation rule must have a specific, auditable reason.
- **Simulation bleed**: if simulation behavior is gated by a flag rather than explicit executor injection, it can be accidentally disabled or bypassed. Simulation mode should be the executor itself, not a flag.
- **Exception class coupling**: resolved by design. `RetryableActionError` and `SkippedAction` are extracted to `engines/soar_errors.py` before the executor is written. The worker, executor, and future adapters all import from that neutral file. No module imports exception classes from a peer module.
- **result dict shape drift**: resolved by design. The worker validates the executor result dict immediately after return and raises a non-retryable exception if `code` or `message` is missing or empty. The existing silent fallback helpers are not used for the success path.

## Success criteria

- `engines/soar_errors.py` exists and is the sole definition point for `RetryableActionError` and `SkippedAction`.
- A formal executor interface exists and is documented with signature, return format, and exception contract.
- `SimulationExecutor` implements the interface for all three action types.
- Validation raises `SkippedAction` (not `RetryableActionError`) for all invalid input cases.
- The worker validates executor results and raises a non-retryable exception for missing `code` or `message`.
- The worker can be called with `SimulationExecutor()` as the executor in tests — no placeholder needed.
- No real external actions are possible through `SimulationExecutor`.
- Existing queue, worker, and ingest/detection/correlation tests remain green.
- `response_actions_log` behavior is unchanged.
- Future Phase 3 adapters are identified as living under `adapters/` and implementing the same interface.
