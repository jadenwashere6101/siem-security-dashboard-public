# Design: SOAR Simulation Execution Reliability Safeguards

## Proposed architecture
Add reliability metadata and read-path visibility around simulation-only playbook executions. The implementation should remain manual and operator-driven: one-shot execution still runs only when explicitly invoked, and any stale-running recovery or retry review should require an explicit API or command action.

This change should harden the current simulation executor before autonomous workers or real integrations exist. It should not introduce background processing, scheduling, or external side effects.

## Files likely to change during implementation
- `schema.sql` only if existing `playbook_executions` columns cannot represent attempts and terminal state safely.
- `core/playbook_store.py` for narrow execution metadata helpers.
- `engines/playbook_step_executor.py` for attempt accounting and fail-closed terminal handling.
- `routes/playbook_routes.py` if existing execution detail/list APIs should expose attempt metadata or explicit stale-review actions.
- `routes/metrics_routes.py` or the planned playbook metrics route if metrics are implemented first or in parallel.
- `tests/test_playbook_step_executor.py`, `tests/test_playbook_routes.py`, and focused metrics tests.

Do not change frontend, real integration adapters, SOAR queue behavior, ingest, detection, or correlation logic for this reliability phase.

## Execution attempt metadata
Each playbook execution should expose enough metadata for operators to understand execution reliability:
- `attempt_count`: number of times the execution has entered a simulation run attempt.
- `max_attempts`: configured maximum attempts for the execution, defaulting to a conservative system value.
- `last_attempted_at`: timestamp of the latest attempt.
- `last_error`: latest failure summary safe for API display.
- `failure_classification`: optional structured value such as `step_failed`, `approval_denied`, `approval_expired`, `stale_running`, `attempt_limit_exhausted`, or `adapter_simulation_failed`.

If schema changes are needed, they should be additive only. If the existing `steps_log` can safely carry some metadata, use it for event detail, but avoid making `steps_log` the only source for top-level attempt counts if route and metric queries would become brittle.

## Retry count visibility
The existing execution read APIs should expose attempt and retry visibility. `retry_count` can be derived as `max(attempt_count - 1, 0)` if a separate stored column is unnecessary. The response should make the distinction clear:
- `attempt_count` means total tries.
- `retry_count` means tries after the initial attempt.
- `max_attempts` means the upper bound.
- `remaining_attempts` may be returned for operator clarity.

This visibility is informational and does not itself retry or execute anything.

## Max attempts and fail-closed behavior
Before the simulation executor starts or resumes an execution, it should check attempt limits. If an execution has exhausted `max_attempts`, it must not run steps, call adapters, create approval requests, or mutate execution progress. It should transition to a terminal dead-letter style state, preferably `permanently_failed`, with a clear reason such as `attempt_limit_exhausted`.

Manual retry controls should also enforce the limit before creating another pending execution. Preserve the existing immutable-history model: retry should create a new execution record only when allowed and should not rewrite prior terminal executions.

## Dead-letter style terminal state
Add a terminal state such as `permanently_failed` for executions that should not be retried without explicit future operator intervention or code/config changes.

`permanently_failed` is needed even in simulation mode because simulated failures still represent workflow problems: invalid parameters, unsafe config, repeatedly failing adapter simulation, or execution code errors. If these failures are not separated from ordinary `failed` rows, operators cannot distinguish "retry may help" from "stop and inspect before any future automation".

The state should:
- Be terminal.
- Not be eligible for automatic or ordinary manual retry.
- Be visible in execution lists/details and metrics.
- Preserve original failed execution history and steps log.
- Never enqueue SOAR queue work or call real integrations.

## Stale running detection
Stale `running` executions should be detected by comparing existing or added timestamps against a conservative stale threshold. Detection should be explicit and safe:
- A read-only endpoint or metrics field may report stale-running counts and IDs.
- An explicit super-admin action may mark stale executions as `failed` or `permanently_failed` only if implementation later chooses to add such a control.
- No daemon should scan for stale rows.
- No stale detection path should automatically resume execution.
- No stale detection path should call adapters or run steps.

Stale handling should treat interrupted `running` step entries as unknown and unsafe to auto-continue. The safe default is operator visibility and fail-closed marking, not automatic replay.

## Timeout metadata only
Timeout values should be metadata for operator visibility and future readiness. Examples:
- `execution_timeout_seconds`
- `stale_after_seconds`
- `attempt_started_at`
- `timed_out_at`

These fields must not create background timers, signals, cron jobs, or automatic state transitions. Timeout metadata exists to make stale and long-running states visible and testable before a future autonomous worker is designed.

## Preventing retry storms
Retry storms are prevented by combining several constraints:
- Manual-only retry path.
- No automatic background retry loop.
- `max_attempts` enforced before execution or retry creation.
- Active execution uniqueness remains in place for `pending`, `running`, and `awaiting_approval`.
- Terminal `permanently_failed` executions are not eligible for ordinary retry.
- Retry history remains immutable, so repeated failures are visible rather than overwritten.
- Metrics expose retries and exhausted attempts so operators can stop unsafe playbooks before enabling automation.

## Metrics visibility
Metrics should report reliability state without executing anything:
- Total executions by status, including `permanently_failed` if added.
- Total attempts and retry counts.
- Executions at or near `max_attempts`.
- Recently failed and permanently failed executions.
- Stale `running` execution counts.
- Failure classifications where available.

Metrics endpoints must be read-only and must not mutate stale executions as a side effect.

## Idempotent retry behavior
Retries must remain safe and idempotent:
- Completed successful steps should not be re-run within the same execution.
- Retry should create new execution history when allowed, preserving prior terminal rows.
- Idempotency keys or step-level success markers should continue to prevent duplicate simulated actions on resume.
- Approval-gated executions must not bypass approval state on retry or resume.
- Denied or expired approval outcomes should remain terminal for that execution history.

Even though adapters are simulation-only, the idempotency design should match the shape needed before real integrations exist.

## Operator visibility only
This change should improve what operators can see and explicitly control. It must not make the system more autonomous. Any action that changes stale or terminal reliability state should be explicit, authenticated, authorized, and audited if implemented.

Analyst users may receive read-only visibility where existing playbook visibility allows it. Super-admin users may receive explicit controls only if they do not run playbooks or call integrations directly.

## Safety boundaries
- Simulation-only.
- Fail closed.
- Preserve immutable execution history.
- No mutation of `blocked_ips`.
- No network calls.
- No subprocess execution.
- No real remediation.
- No real Slack, email, webhook, firewall, PagerDuty, or external messaging calls.
- No daemon or scheduler.
- No automatic background retries.
- No queue redesign or queue enqueueing.
- No ingest, detection, or correlation changes.

## Failure behavior
- Invalid `max_attempts` configuration should fail closed to a conservative default or reject the operation.
- Attempt-limit exhaustion should stop before step execution.
- Stale `running` detection should never resume automatically.
- Unsupported or unknown execution states should be surfaced safely and should not be treated as runnable.
- Adapter simulation errors should be classified and recorded without escalating to real integration paths.

## Test strategy
Add backend tests that verify:
- Attempt count increments only when an execution attempt starts.
- Retry count visibility is derived or returned correctly.
- `max_attempts` prevents additional simulation execution.
- Attempt exhaustion produces `permanently_failed` or the chosen dead-letter style terminal state.
- `permanently_failed` is not eligible for ordinary retry/resume.
- Stale `running` executions are detected without auto-resume or adapter calls.
- Timeout metadata is visible but does not trigger background mutation.
- Metrics include retries, failures, stale-running counts, and permanently failed counts.
- Immutable execution history is preserved across retry attempts.
- No `blocked_ips` writes occur.
- No network calls or subprocess calls occur.
- No SOAR queue, ingest, detection, or correlation behavior changes.

## Risks and stop conditions
- Stop if implementation requires a daemon, scheduler, or automatic retry loop.
- Stop if implementation requires real integrations, network calls, subprocess calls, or secrets.
- Stop if implementation would mutate `blocked_ips`.
- Stop if implementation needs queue redesign or ingest/detection/correlation changes.
- Stop if retry handling would rewrite historical executions instead of preserving immutable history.
- Stop if stale-running handling would automatically continue or replay unknown work.
