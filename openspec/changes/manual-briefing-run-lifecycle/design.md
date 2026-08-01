## Overview

The existing `/soc-briefings/run-now` route correctly creates or returns a durable manual job, and the existing worker owns long-running briefing execution. The missing piece is a visible lifecycle contract that lets the UI track that durable job from request through terminal result.

This change keeps Gunicorn request handling short: Run Now only enqueues or returns the active manual job. The UI polls a status endpoint backed by PostgreSQL job/run/window/briefing state plus worker heartbeat and AI readiness signals.

## Backend Contract

Add or extend a narrow status response for manual runs with:

- `job`: id, status, trigger type, timestamps, attempt count, lease owner/heartbeat/expiry, failure code/message, requested by, already-running flag.
- `run`: id, status/content status/provider status, model/provider, runtime, failure code/message when available.
- `briefing`: id, status/content status/delivery status/generated timestamp when available.
- `worker`: heartbeat summary from existing worker heartbeat store, normalized as available/stale/offline.
- `ai`: existing local provider readiness/local-only/no-paid-fallback indicators.
- `lifecycle`: normalized status for UI: queued, running, completed, partial, degraded, failed, blocked, timed_out, already_running, or unknown.
- `blocked_reasons`: concise reason codes/messages derived from job/run failure fields, worker health, and AI readiness.
- `terminal`: whether polling can stop.

The status endpoint must not claim the worker ran anything; it only reports durable state. It must not create fake/demo briefings.

## Frontend Flow

1. User clicks Run Anakin Briefing Now.
2. UI shows the returned job id immediately.
3. UI stores/tracks the active manual job id in component state.
4. UI polls manual lifecycle status until terminal.
5. On completed/partial/degraded terminal states, the briefing history reloads and the new briefing is selected/opened when available.
6. On failed/blocked/timed-out states, UI shows exact reason and worker/model availability.
7. On panel load or refresh, UI recovers active manual tracking from the control/status endpoint if a manual job is pending/running.

## Worker State

Worker availability is informational but important. A queued job with offline/stale worker should clearly say the job is queued but no fresh briefing worker heartbeat is visible. This is not a Gunicorn failure and should not trigger inline job execution.

## Safety

Manual runs must remain allowed while schedules are paused and in either briefing mode. Duplicate active manual jobs remain prevented by existing store semantics. This change does not introduce paid fallback, production mutation, SOAR execution, or long AI work in API requests.

## Verification Strategy

Backend tests cover one-click creation, repeat click already-running state, paused schedules allowing manual jobs, lifecycle status normalization, worker heartbeat/no-worker states, terminal briefing linkage, and paid-fallback absence. Frontend tests cover immediate job id display, polling transitions, page-refresh recovery, history refresh/select on success, and visible failure/blocked/no-worker messages.
