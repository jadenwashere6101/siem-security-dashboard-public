# Design: SOAR Scheduled Playbook Simulation Architecture

## Proposed architecture
Design a simulation-only scheduled playbook layer that records schedule intent, exposes operator-visible schedule status, and creates schedule-linked playbook execution records only through an explicitly controlled future scheduler path.

This design does not implement a scheduler. It defines the data model, state transitions, safety rules, metrics, and audit expectations needed before any scheduler implementation is considered.

The architecture should remain:
- Simulation-only.
- Fail-closed.
- Operator-visible.
- Bounded in concurrency and missed-run handling.
- Explicit about startup and restart behavior.
- Separate from ingest, detection, correlation, SOAR queue, and real integrations.

## Scheduled playbook definitions
Scheduled playbooks should extend existing playbook definition management without changing alert-triggered playbook semantics. A schedule may be represented as additive metadata on `playbook_definitions` or a separate `playbook_schedules` table if that keeps lifecycle and audit behavior clearer.

Recommended schedule fields:
- `schedule_id`: stable schedule identifier if schedules are separate records.
- `playbook_id`: existing playbook definition ID.
- `enabled`: whether the schedule is eligible.
- `paused`: whether an operator has paused the schedule.
- `schedule_expression`: cron-like expression or constrained interval expression.
- `timezone`: explicit timezone, defaulting to UTC if unset.
- `next_run_at`: next expected run timestamp.
- `last_run_at`: latest attempted scheduled run timestamp.
- `last_success_at`: latest successful scheduled execution timestamp.
- `last_failure_at`: latest failed scheduled execution timestamp.
- `last_scheduled_execution_id`: latest execution row created by the schedule.
- `missed_run_policy`: bounded policy such as `skip`, `record_only`, or `run_once`.
- `max_catchup_runs`: small integer, defaulting to `0` or `1`.
- `max_concurrent_runs`: conservative integer, defaulting to `1`.
- `created_at`, `updated_at`, and operator metadata where existing patterns support it.

Schedule definitions must not contain secrets, real integration credentials, firewall details, or external API configuration.

## Enabled, disabled, paused, and resumed states
Use explicit schedule lifecycle state:
- Disabled schedules are not eligible and should not produce execution records.
- Enabled schedules are eligible only when not paused and when safety checks pass.
- Paused schedules are operator-disabled temporarily and should retain `next_run_at` visibility without executing.
- Resumed schedules should recalculate or validate `next_run_at` without replaying old missed runs by default.

Manual pause/resume should be super-admin-only in any future implementation and should write audit events. Pause/resume must not run a playbook directly.

## Last run and next run visibility
Operators need read-only visibility before any scheduler runs:
- Schedule enabled/paused state.
- Last run timestamp.
- Last result.
- Last execution ID.
- Next run timestamp.
- Missed-run policy.
- Whether a schedule is blocked by concurrency, approval backlog, circuit breaker, or stale active execution.

This visibility may be exposed through future backend read APIs and metrics. The design should not require frontend implementation in this change.

## Safe missed-run handling
Missed runs are dangerous after downtime or restart. Default behavior should be fail-closed:
- Do not replay all missed intervals.
- Do not run automatically on startup.
- Record missed-run metadata for operator visibility.
- Allow at most one catch-up execution only if explicitly configured and bounded.
- Prefer `missed_run_policy = skip` as the default.

Accepted missed-run policies:
- `skip`: mark missed intervals as skipped/visible metadata only.
- `record_only`: store missed-run count and window without creating executions.
- `run_once`: create at most one catch-up execution if no active execution exists and all safety gates pass.

Unbounded catch-up is forbidden.

## Schedule execution history linkage
Scheduled runs should create immutable playbook execution history. Future execution rows should clearly indicate scheduled origin without rewriting alert-triggered history.

Recommended linkage:
- `trigger_source`: `alert` or `schedule`.
- `schedule_id` or `scheduled_run_id`.
- `scheduled_for`: intended schedule time.
- `created_by`: `scheduler` or explicit operator/system identity.
- `schedule_metadata`: safe context such as expression, timezone, missed-run policy, and catch-up flag.

If schema changes are needed, they must be additive. Do not overload `alert_id` with fake alerts for scheduled runs. Scheduled executions that do not originate from alerts should have nullable alert linkage or an explicit schedule linkage model.

## Manual pause and resume
Manual pause/resume controls should be designed as operator controls, not execution controls:
- Pause prevents future schedule-created executions.
- Resume re-enables eligibility from a recalculated `next_run_at`.
- Resume does not catch up missed runs unless a bounded missed-run policy explicitly allows it.
- Both actions require super-admin authorization and audit logging.
- Analysts may receive read-only visibility if existing SOAR visibility patterns allow it.

Pause/resume must not run the executor, call adapters, enqueue queue rows, approve requests, or mutate unrelated playbook executions.

## Bounded execution concurrency
Schedules must prevent overlapping runs:
- Default `max_concurrent_runs = 1` per schedule.
- A schedule is blocked if any active execution exists for the same schedule and playbook.
- Active statuses include `pending`, `running`, and `awaiting_approval`; include `half_open` or future statuses only if they are active execution states.
- If blocked, record operator-visible skipped/blocked metadata rather than creating duplicate executions.

This prevents duplicate execution after restart and avoids piling up approval-gated or circuit-breaker-blocked runs.

## Approval-gated playbooks
Scheduled playbooks may include approval gates, but schedule handling must not bypass them:
- A scheduled execution that reaches `require_approval` should pause at `awaiting_approval`.
- The schedule should not create another overlapping execution while an approval-gated execution is active.
- Approval bottlenecks should be visible in metrics and schedule status.
- Approval expiration remains explicit and should not be triggered by schedule status reads.

No schedule path should approve, deny, expire, or resume approvals automatically.

## Permanently failed executions
Scheduled execution failures should preserve immutable history:
- Failed executions may become `permanently_failed` through existing reliability safeguards.
- A `permanently_failed` scheduled execution should not be retried automatically.
- Future scheduled runs for the same playbook should be controlled by policy. The safest default is to pause or block the schedule after permanent failure until operator review.
- Metrics should show schedules with recent or repeated permanent failures.

Do not rewrite terminal execution rows.

## Circuit breaker interaction
Schedules must respect simulation circuit breakers:
- If a required adapter's breaker is `open`, adapter-backed steps fail closed through existing execution behavior.
- Schedules must not reset, force-open, or enable half-open breakers.
- A schedule should not repeatedly create executions that immediately fail because a breaker is open. Use concurrency, max attempts, and optional schedule backoff/pause-after-failure policy.
- Circuit breaker state should appear in schedule/run visibility when a run is blocked or failed by breaker metadata.

Circuit breaker controls remain separate explicit operator actions.

## Retry metadata and retry storms
Scheduled playbooks must use existing retry metadata and attempt limits:
- No automatic background retries.
- No retry loops.
- `max_attempts` and `permanently_failed` remain authoritative.
- Schedule-created executions should not bypass retry limits.
- Repeated schedule failures should trigger visible schedule health state, not unbounded replay.

Retry storms are prevented by bounded concurrency, missed-run caps, fail-closed startup, and no autonomous retry loop.

## Stale execution detection
Schedules must interact safely with stale-running detection:
- If a prior scheduled execution is stale `running`, do not create a new overlapping run.
- Surface the stale execution in schedule status and metrics.
- Do not auto-mark stale executions failed on scheduler startup.
- Do not auto-resume stale executions.
- Require explicit operator action for stale execution cleanup if a future control exists.

## Scheduler startup and restart behavior
Startup/restart must fail closed:
- Do not execute schedules during application import or startup.
- Do not replay missed runs automatically.
- Recalculate schedule visibility and `next_run_at` deterministically where safe.
- Mark ambiguous schedule state as requiring operator review.
- Do not auto-heal stale execution, open breaker, or approval bottleneck state.

If a future scheduler process exists, it should acquire explicit locks before creating execution records. Lock failure should skip safely with visible metadata, not create duplicate runs.

## Read-only metrics visibility
Scheduled playbook metrics should be read-only and should not mutate schedule state:
- Schedule count by enabled/paused/disabled.
- Last run status.
- Next run due count.
- Missed-run count.
- Skipped due to active execution.
- Skipped due to approval backlog.
- Failed due to circuit breaker.
- Permanently failed scheduled executions.
- Stale scheduled executions.

Metrics must not execute schedules or recalculate state with side effects.

## Audit logging expectations
Future implementation should audit:
- Schedule created, updated, enabled, disabled, paused, resumed.
- Missed-run policy changes.
- Manual catch-up authorization if ever allowed.
- Scheduled execution record creation.
- Schedule skipped due to active execution, stale execution, approval backlog, circuit breaker, or safety policy.
- Scheduler startup/restart summary if a scheduler is later implemented.

Audit failures for state-changing schedule controls should fail closed unless an existing project-wide audit pattern explicitly allows best-effort logging.

## Safety boundaries
- Simulation-only.
- No hidden execution.
- All schedule behavior must be operator-visible.
- Scheduler restart behavior must fail closed.
- No replay storms after restart.
- No autonomous recovery loops.
- No daemon implementation in this change.
- No APScheduler, Celery, Redis, RQ, cron, or systemd implementation in this change.
- No background autonomous retries.
- No real integrations.
- No enabling `INTEGRATION_MODE=real`.
- No firewall, blocklist, or `blocked_ips` mutation.
- No queue redesign.
- No execution implementation.
- No frontend implementation yet.
- No ingest, detection, or correlation changes.

## Risks and mitigations
- Duplicate execution after restart: require active-run checks, schedule locks, and fail-closed startup.
- Stale schedule recovery: surface stale state and require operator action; do not auto-resume.
- Overlapping playbook runs: enforce `max_concurrent_runs = 1` by default.
- Retry storms: no background retries, bounded missed-run handling, max attempts, and permanent failure states.
- Schedule drift: expose `scheduled_for`, `last_run_at`, and `next_run_at`; avoid silent catch-up.
- Approval bottlenecks: block overlapping scheduled runs while `awaiting_approval` executions exist.
- Circuit breaker interaction: respect breaker fail-closed state; do not auto-reset breakers.
- Missed-run replay ambiguity: default to skip/record-only and make catch-up explicit and bounded.

## Test strategy for future implementation
When implemented later, tests should verify:
- Disabled and paused schedules do not create execution records.
- Enabled schedules create at most one eligible simulation execution.
- Missed runs are skipped or recorded by default without replay storm.
- Restart handling does not execute hidden work.
- Active `pending`, `running`, or `awaiting_approval` executions block overlapping schedule runs.
- Approval-gated scheduled executions pause safely.
- `permanently_failed` scheduled executions are not automatically retried.
- Open circuit breakers are respected and surfaced.
- Stale running executions block new scheduled runs and do not auto-resume.
- Metrics are read-only.
- Audit events are written for schedule state changes.
- No network calls, subprocess calls, `blocked_ips` writes, queue redesign, or ingest/detection/correlation changes occur.

## Stop conditions
- Stop if implementation requires a daemon or scheduler before the design is approved.
- Stop if implementation would execute schedules on startup.
- Stop if implementation requires real integrations or `INTEGRATION_MODE=real`.
- Stop if implementation requires queue redesign.
- Stop if implementation mutates `blocked_ips`.
- Stop if implementation changes ingest, detection, or correlation internals.
- Stop if missed-run handling cannot be bounded.
- Stop if schedule behavior cannot be made operator-visible.
