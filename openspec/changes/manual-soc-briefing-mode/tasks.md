## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `manual-soc-briefing-mode`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. Backend Runtime

- [x] 2.1 Add additive persistence for global SOC briefing mode and pause state, with schema snapshot and migration updates.
- [x] 2.2 Add runtime-store helpers for reading/updating controls, status summaries, manual schedule resolution, manual job creation, and duplicate active manual job detection.
- [x] 2.3 Update autonomous materialization so manual-only mode and pause schedules prevent new scheduled jobs while preserving manual jobs and existing bounded catch-up behavior.
- [x] 2.4 Add narrow SOC briefing control API routes for status, mode update, pause update, and Run Now with RBAC and sanitized audit metadata.

## 3. Frontend

- [x] 3.1 Extend the SOC briefing service with status, mode, pause, and run-now API calls.
- [x] 3.2 Add visible SOC Briefings controls/status for Run Anakin Briefing Now, mode, pause, last/next run, catch-up, local model readiness, and no paid fallback.
- [x] 3.3 Add clear loading, success, already-running, blocked/unavailable, and failure UI feedback.

## 4. Tests

- [x] 4.1 Add backend tests for RBAC, status, mode/pause updates, manual-only schedule blocking, scheduled-mode catch-up preservation, run-now duplicate prevention, manual history persistence path, local model unavailable status, and no paid fallback.
- [x] 4.2 Add frontend service and component tests for controls/status rendering, run-now feedback, mode/pause calls, and error states.

## 5. Verification

- [x] 5.1 Run focused backend tests.
- [x] 5.2 Run focused frontend tests.
- [x] 5.3 Run frontend production build.
- [x] 5.4 Run strict OpenSpec validation and `git diff --check`.
