## Why

The SIEM has request-scoped AI investigation services and systemd-managed SOAR workers, but it does not have a durable runtime for scheduled, read-only SOC briefing work. A scheduled briefing foundation needs PostgreSQL-backed schedules, jobs, leases, run state, step records, and worker health before any autonomous evidence collection, briefing content, Slack delivery, or UI history is added.

## What Changes

- Add a durable scheduled SOC briefing runtime capability for schedule definitions, schedule windows, queued jobs, investigation runs, run steps, and briefing lifecycle records.
- Define PostgreSQL idempotency and lease behavior so each schedule window creates at most one job and at most one worker can claim a job.
- Add bounded missed-window detection, catch-up, coalescing, stale-window skip outcomes, and recovery behavior for overnight VM downtime.
- Add a systemd-managed one-shot worker service and timer outside Flask/Gunicorn, with bounded batch size, maximum runtime, graceful shutdown, heartbeat, and health visibility.
- Define a scheduled read-only service actor that is attributed in run and audit records and can invoke only existing approved SOC read-tool paths.
- Persist clear disabled, unavailable, blocked, failed, partial, skipped, stale, and successful states without storing hidden model chain-of-thought.
- Keep autonomous evidence collection logic, briefing content generation, briefing history UI, Slack delivery, Mini PC/Ollama setup, model selection, draft generation, and production actions out of scope.

## Capabilities

### New Capabilities

- `scheduled-soc-briefing-runtime`: Durable PostgreSQL and systemd runtime for scheduling, claiming, tracking, and recovering future read-only SOC briefing jobs.

### Modified Capabilities

- None.

## Impact

- Backend/source areas expected to change during implementation: new `core/ai/soc_briefing_runtime_store.py`, new `core/ai/soc_briefing_scheduler.py`, new `core/ai/soc_briefing_worker.py`, new `scripts/soc_briefing_worker.py`, `core/worker_heartbeat_store.py`, `routes/metrics_routes.py`, migration files, migration tests, and focused worker tests.
- Deployment templates expected to change: new `deploy/systemd/soc-briefing-worker.service`, new `deploy/systemd/soc-briefing-worker.timer`, and `scripts/deploy_backend_vm.sh` worker installation flow.
- Runtime impact: additive PostgreSQL schema only; no production mutations, Slack delivery, paid-provider spending, frontend briefing UI, or VM access in this change.
