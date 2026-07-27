## Context

The current backend already has the ingredients for a safe runtime: PostgreSQL migrations, SOAR worker leases using `FOR UPDATE SKIP LOCKED`, systemd service/timer deployment, worker heartbeats, AI Gateway disabled/unavailable states, and request-scoped AI investigations. The missing layer is durable scheduling and run tracking for future autonomous SOC briefings. This change is a runtime foundation only; it must not collect evidence autonomously, generate briefing content, send Slack messages, or mutate production state.

## Goals / Non-Goals

**Goals:**

- Persist schedules, schedule windows, jobs, investigation runs, run steps, and briefing lifecycle records.
- Ensure duplicate prevention with schedule-window idempotency and PostgreSQL leases.
- Run outside Gunicorn through a bounded systemd one-shot service and persistent timer.
- Recover from missed timer windows with bounded catch-up and coalescing.
- Attribute all work to a scheduled read-only service actor.
- Persist explicit failure/degraded outcomes without silent exception swallowing.

**Non-Goals:**

- Autonomous evidence collection, briefing content generation, Slack delivery, Teams delivery, Mini PC/Ollama setup, model selection, draft generation, frontend briefing history UI, or production mutations.
- APScheduler, in-process Flask scheduling, provider-side tool callbacks, model-generated SQL, shell/file/subprocess execution from model output, or hidden chain-of-thought storage.

## Decisions

1. Use a one-shot worker plus systemd timer, not a long-running daemon.

Rationale: schedule materialization is naturally periodic, and a one-shot runner is easier to bound, restart, observe, and roll back. The service runs a small batch then exits. The timer uses `OnBootSec=2min`, `OnUnitActiveSec=5min`, `RandomizedDelaySec=30s`, and `Persistent=true`. PostgreSQL catch-up remains authoritative so systemd persistence cannot create unbounded work.

Alternative considered: long-running worker loop. Rejected for this foundation because heartbeat/sleep/shutdown logic is larger and not needed until the job volume justifies it.

2. Store schedule windows separately from jobs.

Rationale: a window is the durable idempotency boundary: `schedule_id + window_start + window_end` is unique. Jobs represent work attempts for a window and can be claimed, failed, skipped, or completed without losing the schedule-window identity.

3. Add these tables in one additive migration:

- `soc_briefing_schedules`: `id`, `name`, `schedule_kind`, `timezone`, `cadence_minutes`, `time_of_day`, `enabled`, `catch_up_enabled`, `max_catch_up_windows`, `max_lookback_hours`, `coalesce_missed_windows`, `next_due_at`, `last_successful_window_end`, `created_by`, timestamps, and validation checks.
- `soc_briefing_schedule_windows`: `id`, `schedule_id`, `window_start`, `window_end`, `idempotency_key`, `status`, `skip_reason`, `created_at`, `updated_at`, with unique `(schedule_id, window_start, window_end)` and unique `idempotency_key`.
- `soc_briefing_jobs`: `id`, `schedule_id`, `window_id`, `idempotency_key`, `status`, `priority`, `attempt_count`, `max_attempts`, `lease_owner`, `lease_acquired_at`, `lease_heartbeat_at`, `lease_expires_at`, `not_before`, `started_at`, `completed_at`, `failure_code`, `failure_message`, timestamps, with unique `window_id` and unique `idempotency_key`.
- `soc_briefing_runs`: `id`, `job_id`, `schedule_id`, `window_id`, `run_key`, `status`, `service_actor`, `started_at`, `completed_at`, `runtime_ms`, `ai_gateway_status`, `provider_status`, `budget_policy`, `error_code`, `error_message`, `metadata`, timestamps, with unique `run_key`.
- `soc_briefing_run_steps`: `id`, `run_id`, `step_index`, `step_type`, `status`, `tool_name`, `sanitized_input`, `evidence_refs`, `decision_summary`, `latency_ms`, `error_code`, `error_message`, timestamps, with unique `(run_id, step_index)`.
- `soc_briefings`: `id`, `run_id`, `schedule_id`, `window_id`, `status`, `lifecycle_status`, `briefing_type`, `generated_at`, `content_status`, `summary`, `sections`, `evidence_refs`, `error_code`, `error_message`, timestamps, with unique `run_id`.

Indexes: schedules `(enabled, next_due_at)`, windows `(schedule_id, status, window_end)`, jobs `(status, not_before, priority, id)`, jobs `(lease_expires_at)` where leased, runs `(status, started_at DESC)`, steps `(run_id, step_index)`, briefings `(schedule_id, generated_at DESC)`.

Retention: keep schedules indefinitely, preserve run/step/briefing evidence for at least 180 days by default, and add retention configuration later before any deletion job. No cleanup worker is included in this change.

4. Claim jobs with PostgreSQL leases.

The worker first materializes due windows, then claims pending jobs using `FOR UPDATE SKIP LOCKED`, sets `status='running'`, `lease_owner`, `lease_acquired_at`, `lease_heartbeat_at`, and `lease_expires_at`. Default lease duration is 120 seconds; heartbeat renewal occurs before each bounded phase. Expired running jobs are recovered in a bounded pass: requeue if attempts remain, otherwise mark `failed` with `stale_lease_expired`.

5. Catch-up is bounded and coalesced.

Each schedule tracks `last_successful_window_end` and `next_due_at`. On startup or timer fire, the scheduler computes missed windows between the later of those anchors and now. It creates at most `max_catch_up_windows` within `max_lookback_hours`. If more windows are missed and `coalesce_missed_windows=true`, it creates one coalesced window covering the bounded lookback and marks older windows skipped with `outside_lookback` or `coalesced`. No schedule can create an unbounded backlog.

6. Service identity is internal and read-only.

The actor is `scheduled_soc_briefing_worker` with a fixed role equivalent to analyst read-only SOC tool access. It cannot approve, deny, retry SOAR actions, mutate incidents, write notes, send Slack, or bypass validation. Run and audit records store this actor explicitly. The worker may call runtime helpers directly only through the same allowlisted SOC read-tool executor used by AI paths in later specs.

7. AI states are persisted but provider calls are not required for this foundation.

This runtime checks gateway configuration/readiness only to persist `disabled`, `unavailable`, `blocked`, or `provider_timeout` outcomes. No model call is needed to verify schedule, lease, catch-up, heartbeat, or persistence behavior.

## Risks / Trade-offs

- [Schema breadth] Multiple new tables add migration complexity. Mitigation: keep the migration additive, indexed, and covered by migration tests plus schema snapshot validation.
- [Timer persistence could replay too much work] Mitigation: systemd `Persistent=true` only wakes the runner; PostgreSQL catch-up limits remain authoritative.
- [Audit helper currently swallows exceptions] Mitigation: runtime step/run persistence is mandatory and failures abort the job; audit failures must be recorded as failed steps or surfaced errors, not ignored.
- [Malformed schedules could loop] Mitigation: schedules with invalid cadence/timezone are marked `blocked` with `malformed_schedule` and skipped until corrected.
- [Future investigation logic may try to widen authority] Mitigation: service actor and runtime tables record read-only labels and forbid production mutation states in this capability.

## Migration Plan

Mac AI implementation adds the migration, store helpers, worker service wrapper, systemd unit/timer templates, focused tests, and docs. The migration is additive only and does not alter existing SOAR, AI action, alert, incident, or notification tables.

VM AI later applies the approved commit through `scripts/deploy_backend_vm.sh` after clean-tree sync. Rollback disables/stops `soc-briefing-worker.timer` and `soc-briefing-worker.service`, reverts to the prior approved commit, and leaves additive tables in place for preservation unless a separately approved migration rollback exists.

## Verification Plan

Implementation must test duplicate window suppression, single-worker job claim, stale lease recovery, bounded catch-up, overnight coalescing, malformed schedule blocking, AI disabled/unavailable outcomes, isolated run state, durable step persistence, persistence-failure abort behavior, heartbeat health, and absence of production mutation paths. Validation must include `python3 -m pytest` focused tests, migration tests, schema snapshot validation, `git diff --check`, and `openspec validate scheduled-soc-briefing-runtime --strict`.

## Documentation Plan

Update narrowly: worker deployment/runbook docs, AI architecture documentation for the runtime boundary, migration workflow notes if a new schema convention is introduced, verification checklist, and VM handoff documentation. Update the Mac/VM source-of-truth policy only if deployment ownership or sync rules genuinely change.

## Open Questions

- Exact default seed schedules can wait for implementation; the runtime must support disabled-by-default schedules so rollout can be staged safely.
