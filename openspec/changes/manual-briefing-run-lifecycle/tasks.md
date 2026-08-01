## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `manual-briefing-run-lifecycle`.
- [x] 1.2 Validate the OpenSpec strictly.

## 2. Backend Lifecycle Contract

- [x] 2.1 Add a narrow manual lifecycle status helper using existing job/run/window/briefing/worker state.
- [x] 2.2 Extend Run Now response with created/existing job id, lifecycle status, worker state, and blocked reasons.
- [x] 2.3 Add a pollable manual lifecycle endpoint for active or specified manual jobs.
- [x] 2.4 Preserve duplicate active manual job prevention and schedule-pause independence.

## 3. Frontend Lifecycle UI

- [x] 3.1 Display Run Now job id immediately.
- [x] 3.2 Poll durable lifecycle state through terminal outcome.
- [x] 3.3 Show queued/running/completed/partial/degraded/failed/blocked/timed-out states and exact reasons.
- [x] 3.4 Show briefing worker heartbeat state.
- [x] 3.5 Recover active manual tracking on page refresh/panel load.
- [x] 3.6 Refresh history and select/open completed manual briefing.

## 4. Tests

- [x] 4.1 Add backend tests for one-click creation, duplicate already-running state, paused schedules allowing manual runs, lifecycle normalization, worker unavailable state, and terminal briefing linkage.
- [x] 4.2 Add frontend tests for job id display, polling transitions, blocked/no-worker feedback, refresh recovery, and history selection after completion.
- [x] 4.3 Verify no long AI work runs inside Gunicorn and no paid fallback/production mutation path is introduced.

## 5. Verification

- [x] 5.1 Run Python compilation for modified modules.
- [x] 5.2 Run focused backend SOC briefing tests.
- [x] 5.3 Run affected frontend tests.
- [x] 5.4 Run frontend production build.
- [x] 5.5 Run `git diff --check`.
- [x] 5.6 Run `openspec validate manual-briefing-run-lifecycle --strict`.
- [x] 5.7 Run `openspec status --change manual-briefing-run-lifecycle`.
