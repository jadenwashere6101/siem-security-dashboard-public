## Why

“Run Anakin Briefing Now” currently queues a manual SOC briefing job but does not behave like a complete analyst workflow. Analysts need visible job/run progress, worker availability, specific blocked reasons, and automatic history refresh without moving long AI work into Gunicorn.

## What Changes

- Add a narrow durable lifecycle status contract for the active/latest manual briefing job.
- Return and display the created or existing manual job id after Run Now.
- Poll durable job/run/briefing state through queued, running, completed, partial/degraded, failed, blocked, and timed-out outcomes.
- Surface briefing-worker heartbeat health and worker availability.
- Show specific blocked/failure reasons such as provider unavailable, local model unavailable, worker unavailable, already running, schedule pause relevance, and runtime/budget failures when available.
- Refresh briefing history and select/open the produced briefing when the manual run completes.
- Recover active manual-run tracking after page refresh.
- Preserve duplicate active manual job prevention, schedule-pause independence for manual runs, PostgreSQL-backed worker execution, local-only/no-paid-fallback behavior, and read-only/advisory boundaries.

## Capabilities

### New Capabilities
- `manual-briefing-run-lifecycle`: Visible manual SOC briefing job lifecycle tracking using existing durable scheduler/worker/run/briefing state.

### Modified Capabilities

## Impact

- Backend SOC briefing routes/runtime store for manual lifecycle status.
- Frontend SOC Briefings panel/service for Run Now tracking, polling, worker state display, history refresh, and terminal-state feedback.
- Focused backend/frontend tests for duplicate prevention, polling, worker heartbeat, blocked/failure visibility, and schedule-pause independence.
- No database migration unless existing tables cannot expose required lifecycle state.
- No VM access, deployment, runtime provider changes, model installation, paid fallback, or production mutation.
