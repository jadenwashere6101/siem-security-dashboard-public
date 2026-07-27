# Scheduled SOC Briefing Runtime

This runtime is a foundation for future read-only scheduled SOC briefings. It does not perform autonomous investigation, generate briefing content, send Slack messages, configure AI providers, create drafts, or execute production actions.

## Runtime Boundary

The worker runs outside Flask and Gunicorn as a systemd one-shot service triggered by a persistent timer. PostgreSQL is the source of truth for schedules, windows, jobs, leases, runs, steps, briefing lifecycle rows, and worker heartbeat.

The scheduled service actor is `scheduled_soc_briefing_worker`. It is read-only and analyst-equivalent for future SOC read-tool use. It cannot approve, deny, retry, resume, abandon, block, unblock, send notifications, write notes, mutate incidents, run shell/file/subprocess code, or bypass existing validation.

## Tables

- `soc_briefing_schedules`: disabled-by-default schedules, due state, catch-up policy, and malformed schedule state.
- `soc_briefing_schedule_windows`: one durable idempotency boundary per schedule window.
- `soc_briefing_jobs`: queued/running/completed work with PostgreSQL lease ownership.
- `soc_briefing_runs`: isolated run records with service actor, gateway/provider outcome, and runtime metadata.
- `soc_briefing_run_steps`: durable sanitized step records with evidence references and concise decisions.
- `soc_briefings`: lifecycle placeholder rows for future briefing content generation.
- `soar_worker_heartbeats`: also stores the logical `soc_briefing_worker` heartbeat.

## Worker Behavior

The timer wakes the one-shot worker every five minutes and after boot when a scheduled invocation was missed. Application catch-up remains bounded in PostgreSQL: `max_catch_up_windows`, `max_lookback_hours`, and coalescing prevent unbounded backlog after VM downtime.

Jobs are claimed with `FOR UPDATE SKIP LOCKED`, a lease owner, lease heartbeat, and lease expiration. Only the owning worker may renew or complete a job. Expired leases are recovered in bounded batches.

## Rollout

After implementation is committed, pushed, and explicitly approved, VM AI applies the migration and installs units through `scripts/deploy_backend_vm.sh`. Rollback stops/disables `soc-briefing-worker.timer` and `soc-briefing-worker.service`, restores the prior approved commit, and preserves additive tables unless a separate approved rollback migration exists.
