## 1. OpenSpec And Invariants

- [x] 1.1 Create proposal, design, specification, and implementation tasks with database/service invariant ownership, transaction boundaries, concurrency, retention, failure classes, and deferred work.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. PostgreSQL Foundation

- [x] 2.1 Add migration `0033` for threads, turns, entities, state, hypotheses, evidence, tombstones, constraints, indexes, and nullable owner-safe async request linkage.
- [x] 2.2 Update and validate the schema snapshot at migration version `0033`.
- [x] 2.3 Implement owner-scoped store helpers for default/explicit creation, read, cursor turns, transactional append, reset, expiry, purge, state, hypotheses, evidence, and async linkage.
- [x] 2.4 Implement bounded recursive sanitization and structured-state/provenance validation.

## 3. Service And API

- [x] 3.1 Implement target access validation and foundation service responses for lifecycle, ownership, stale versions, idempotency, and pagination.
- [x] 3.2 Add authenticated `/ai/threads` create/read/turn-list/turn-submit/reset routes with content-free audit metadata.
- [x] 3.3 Preserve existing AI workflow, Repo Assistant, SOC Briefing, Analyst Workspace, Decision Support, and artifact apply boundaries.

## 4. PostgreSQL And Contract Tests

- [x] 4.1 Add PostgreSQL tests for default identity, explicit threads, ordered immutable turns, duplicate requests, stale versions, and concurrent writes.
- [x] 4.2 Add PostgreSQL tests for reset races, expiry, archived mutation rejection, 90-day purge, pagination, and malformed state recovery.
- [x] 4.3 Add PostgreSQL tests for provenance separation, corrections, artifact labels, sanitization, evidence bounds, entity loss, and owner-safe async linkage.
- [x] 4.4 Add route/RBAC tests for authentication, current role/disabled users, owner isolation, lifecycle status codes, idempotency, and namespace rejection.
- [x] 4.5 Add migration/schema contract tests and run affected existing async/auth/Anakin regressions.

## 5. Verification And Handoff

- [x] 5.1 Run Python compilation for modified backend modules.
- [x] 5.2 Run required PostgreSQL-backed foundation, migration/schema, RBAC, async request, and affected Anakin tests without skips.
- [x] 5.3 Run existing Anakin acceptance regressions, `git diff --check`, and strict OpenSpec validation.
- [x] 5.4 Review every documented failure class for general invariant enforcement rather than supplied-example handling.
- [x] 5.5 Capture files changed and `git status --short`; confirm no frontend, model/config, VM, deployment, commit, push, or production mutation occurred.
- [x] 5.6 Report `Implementation complete; production behavior unverified.` because browser -> `/siem/` -> nginx -> frontend -> backend verification is outside this Mac-only phase.
