# Tasks: SOAR Scheduled Playbook Frontend Visibility

## Implementation steps
- [ ] Inspect existing `playbookService.js` patterns.
- [ ] Add `listPlaybookSchedules({ playbookId, enabled, limit } = {})`.
- [ ] Add `getPlaybookSchedule(scheduleId)`.
- [ ] Ensure both helpers use GET with `credentials: "include"`.
- [ ] Inspect current `PlaybooksPanel.js` section/tab structure.
- [ ] Add a read-only schedule section or tab without broad refactoring.
- [ ] Fetch schedule list data on schedule section load.
- [ ] Render schedule ID, `playbook_id`, enabled/paused state, schedule expression, missed-run policy, `next_run_at`, and `last_run_at`.
- [ ] Add optional read-only detail view for a selected schedule.
- [ ] Render safe detail metadata fields only.
- [ ] Add persistent metadata-only/no-scheduler notice.
- [ ] Add loading, error, retry/refresh, and empty states.
- [ ] Add focused frontend service tests.
- [ ] Add focused frontend component tests.
- [ ] Confirm no backend, schema, scheduler, executor, queue, integration, ingest, detection, or correlation files changed.

## Exact service test requirements
- [ ] Test `listPlaybookSchedules` calls `/playbook-schedules` with credentials.
- [ ] Test `listPlaybookSchedules` includes `playbook_id` only when provided.
- [ ] Test `listPlaybookSchedules` includes `enabled` only when provided.
- [ ] Test `listPlaybookSchedules` includes `limit` only when provided.
- [ ] Test `getPlaybookSchedule` calls `/playbook-schedules/<id>` with credentials.
- [ ] Test non-OK schedule list response throws a useful error.
- [ ] Test non-OK schedule detail response throws a useful error.
- [ ] Test schedule helpers do not use non-GET methods.

## Exact component test requirements
- [ ] Test schedule loading state renders.
- [ ] Test schedule rows render ID, playbook ID, enabled/paused state, schedule expression, missed-run policy, `next_run_at`, and `last_run_at`.
- [ ] Test schedule empty state renders.
- [ ] Test schedule error state renders.
- [ ] Test refresh refetches schedule data without mutation.
- [ ] Test selecting a schedule renders read-only detail metadata if detail view is implemented.
- [ ] Test metadata-only/no-scheduler notice is visible.
- [ ] Test analysts can view schedule metadata if existing playbook visibility allows.
- [ ] Test no create schedule control is rendered.
- [ ] Test no edit/delete schedule controls are rendered.
- [ ] Test no pause/resume controls are rendered.
- [ ] Test no run-now or execute controls are rendered.
- [ ] Test no approve/deny/retry/cancel/queue/circuit-breaker controls are introduced by the schedule section.
- [ ] Test existing playbook definitions and executions visibility still renders.

## Verification commands
Run:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/components/PlaybooksPanel.test.js src/services/playbookService.test.js
CI=true npm test -- --watchAll=false
npm run build
```

Then from repo root:

```bash
git status --short
```

## Stop and rollback conditions
- Stop if implementation requires backend changes.
- Stop if implementation requires schema changes.
- Stop if implementation adds create/edit/delete schedule UI.
- Stop if implementation adds pause/resume controls.
- Stop if implementation adds run-now controls.
- Stop if implementation adds scheduler implementation.
- Stop if implementation creates playbook executions from schedules.
- Stop if implementation changes executor or queue behavior.
- Stop if implementation changes ingest, detection, or correlation internals.
- Stop if implementation adds real integrations.
- Roll back if schedule visibility cannot remain read-only and metadata-only.
