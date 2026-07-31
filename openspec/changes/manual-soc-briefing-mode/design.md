## Context

The repository already has a scheduled SOC briefing runtime with PostgreSQL schedules, windows, jobs, leases, runs, run steps, briefing records, delivery attempts, and a systemd one-shot worker outside Gunicorn. The investigation engine is read-only and uses the AI Gateway for bounded advisory synthesis. The current SOC Briefings frontend is a history/detail workspace; it does not let an analyst run a briefing on demand or see schedule/model operating mode.

The VM may be offline for long periods. In that operating model, autonomous schedules are useful only when explicitly enabled, while a manual "run now" control should be the primary workflow.

## Goals / Non-Goals

**Goals:**
- Add a narrow authenticated control/status API for briefing mode, pause state, run-now, schedule timing, catch-up, and model readiness.
- Reuse existing schedule/window/job/run/briefing tables and worker processing path.
- Create manual jobs with a durable idempotency boundary so repeated clicks do not create duplicate active runs.
- Prevent automatic schedule materialization while in manual-only mode or while schedules are paused.
- Show analyst-visible controls and status in the existing SOC Briefings workspace.

**Non-Goals:**
- No VM access, deployment, service restart, or runtime provider configuration.
- No paid fallback or cloud-provider enablement.
- No production action path, SOAR execution, approval decision, incident/note mutation, or Slack policy redesign.
- No duplicate scheduler, in-process Flask scheduler, or separate manual investigation engine.
- No full schedule-management editor beyond mode, pause, status, and run-now controls.

## Decisions

1. Add one small control table for global briefing mode and pause state.
   - Rationale: `soc_briefing_schedules.enabled` is per-schedule and cannot safely distinguish "manual-only product mode" from disabled schedules. A single control row lets manual-only block autonomous materialization without destroying schedule definitions.
   - Alternative considered: overload all schedules by setting `enabled=false`. Rejected because it loses the distinction between paused/manual mode and intentionally disabled schedules, and it makes resume ambiguous.

2. Manual "Run Now" creates one existing-style schedule window and job.
   - Rationale: the current worker already handles leases, runs, AI Gateway synthesis, briefing persistence, failure states, and history. Manual work should enter the same path.
   - Alternative considered: run the investigation synchronously in the API request. Rejected because it would duplicate worker behavior, risk request timeouts, and blur runtime boundaries.

3. Duplicate prevention uses active manual job/run lookup plus deterministic manual window keys.
   - Rationale: repeated clicks should return an existing pending/running manual job where possible. A short manual window anchored to "now" records a bounded request while avoiding replaying every missed schedule interval.
   - Alternative considered: allow every click to enqueue a job. Rejected because it can overwhelm the local model and create confusing duplicate briefings.

4. Manual-only and pause are checked only during autonomous materialization.
   - Rationale: manual runs must stay available in either mode and while schedules are paused. The worker may still claim and finish already queued jobs; blocking claim would strand explicit manual work.
   - Alternative considered: block all worker processing when paused. Rejected because pause is scoped to schedules, not manual jobs or cleanup.

5. Status combines database runtime facts with AI Gateway readiness.
   - Rationale: analysts need a clear local model/no-paid-fallback signal before clicking run-now. The existing AI status path and config can be reused without exposing secrets.

## Risks / Trade-offs

- [Manual jobs need a schedule relationship] -> Use or create a disabled/system manual schedule row so existing foreign keys remain intact without enabling autonomous scheduling.
- [Queued scheduled jobs may exist before switching to manual-only] -> Manual-only prevents new autonomous enqueueing; it does not silently delete existing queued work. Status should show pending/running counts.
- [AI readiness probes can be slow] -> Use the existing bounded provider readiness path and surface unavailable/timeout clearly.
- [This adds schema] -> Keep migration additive and update `schema.sql`; no destructive rollback is required.
- [Visual behavior can be subtle] -> Put mode, run-now, pause, model, next run, last run, and no-paid-fallback indicators in the first visible SOC Briefings panel area.
