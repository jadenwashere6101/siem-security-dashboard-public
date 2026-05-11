# Proposal: SOAR Queue UI Component Tests

## Problem

The SOAR Queue UI now includes queue visibility, manual simulation worker runs,
and queue item detail behavior. Current frontend coverage is mostly service-level
and app smoke tests, so regressions in `SoarQueuePanel` could slip through even
when the build passes.

The next step should add targeted component tests without changing production
behavior or broadening the frontend test framework.

## Goal

Add focused React/Jest component tests for:

```text
frontend/src/components/SoarQueuePanel.js
```

The tests should cover:

- loading state
- error state
- empty queue state
- status counts rendering
- recent queue rows rendering
- `alert_id: null` displays as `"Deleted alert"`
- View/detail flow
- detail loading/error/success states
- `idempotency_key` appears only in detail view
- `Run simulation batch` button disables while running
- successful run refreshes queue status and recent rows

## Scope

In scope:

- add a focused `SoarQueuePanel` component test file
- mock `frontend/src/services/soarQueueService.js`
- use existing React Testing Library/Jest setup
- assert user-visible behavior rather than implementation internals
- preserve existing production code behavior unless tiny testability fixes are
  absolutely required
- run frontend test/build verification

Out of scope:

- no production feature changes
- no backend changes
- no schema changes
- no ingest/detection/correlation changes
- no real execution behavior
- no broad test framework rewrite
- no visual regression tooling
- no end-to-end browser automation

## Safety Requirements

- Tests must not call real backend endpoints.
- Tests must not trigger real worker execution.
- Tests must mock the run-once service and assert UI behavior only.
- Tests must not require schema/database setup.
- Tests must stay aligned with the existing Jest/React Testing Library stack.

## Success Criteria

- Targeted component tests cover the major SOAR queue UI states and interactions.
- Tests prove `idempotency_key` stays out of the list view and appears only after
  loading detail.
- Tests prove nullable alert references render safely.
- Tests prove run button double-submit protection by checking disabled state
  while the mocked run is pending.
- Frontend build passes.
- Relevant frontend tests pass.
