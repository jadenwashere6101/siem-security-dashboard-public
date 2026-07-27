## 1. Persistence and Store Layer

- [x] 1.1 Add briefing history store helpers for list/detail queries over `soc_briefings`, runs, schedules, windows, run steps, and delivery status summaries.
- [x] 1.2 Decide whether to extend existing notification delivery tracking or add a narrow `soc_briefing_delivery_attempts` table; add only additive migration/indexes if required.
- [x] 1.3 Implement delivery idempotency keys, lifecycle states, attempt counts, retry/backoff timestamps, provider metadata, failure codes, and final outcomes.
- [x] 1.4 Preserve briefing content lifecycle independently from delivery lifecycle in all store updates.

## 2. Backend APIs and RBAC

- [x] 2.1 Add briefing history list API with status/date/schedule/delivery/provider/search filters, bounded pagination, stable ordering, and sanitized response shape.
- [x] 2.2 Add briefing detail API with structured sections, evidence references, bounded run-step summaries, run/window/schedule metadata, and delivery attempts.
- [x] 2.3 Enforce existing authentication/RBAC for analyst and super-admin read access; deny viewers and unauthenticated users.
- [x] 2.4 Ensure history/detail API reads never trigger investigation, AI synthesis, Slack delivery, SOAR, approvals, notes, incident mutations, or production actions.

## 3. Slack Summary Delivery

- [x] 3.1 Implement optional Slack summary builder from allowlisted briefing fields only.
- [x] 3.2 Integrate delivery with existing notification/Slack readiness and policy controls without requiring Slack for briefing success.
- [x] 3.3 Implement duplicate delivery suppression using deterministic idempotency keys.
- [x] 3.4 Implement bounded retry/backoff behavior and terminal failed/skipped/blocked/sent states.
- [x] 3.5 Audit delivery sent, skipped, blocked, failed, retried, exhausted, and duplicate-suppressed outcomes with sanitized metadata.

## 4. Frontend History Experience

- [x] 4.1 Add frontend service functions for briefing history list/detail and delivery status data.
- [x] 4.2 Add a SIEM briefing history workspace or panel with search, filters, status facets, pagination, and dense operational list layout.
- [x] 4.3 Add briefing detail presentation for saved sections, recommendations, evidence references, degraded-state errors, and delivery attempts.
- [x] 4.4 Distinguish content lifecycle from Slack delivery status visually and textually.
- [x] 4.5 Ensure the UI is read-only and exposes no production mutation, SOAR, approval, note, provider setup, or delivery-policy mutation controls.

## 5. Verification

- [x] 5.1 Add backend tests for list/detail filters, pagination bounds, RBAC denial, not-found behavior, and no side effects from reads.
- [x] 5.2 Add persistence tests for delivery idempotency, duplicate suppression, retry/backoff, exhausted failures, and briefing lifecycle independence.
- [x] 5.3 Add Slack tests proving sanitized payloads, no raw evidence/secrets, disabled/readiness-blocked behavior, and failure not invalidating saved briefings.
- [x] 5.4 Add audit tests for delivery and manual retry/control outcomes with sanitized metadata.
- [x] 5.5 Add frontend tests for list filters, pagination, detail rendering, degraded states, delivery badges, and read-only controls.
- [x] 5.6 Run focused backend tests, frontend tests for affected components, production frontend build when UI changes are implemented, `git diff --check`, and `openspec validate soc-briefing-history-and-delivery --strict`.

## 6. Documentation

- [x] 6.1 Update scheduled briefing runtime docs with history and delivery lifecycle behavior.
- [x] 6.2 Update Slack/notification runbook notes for optional briefing summaries, sanitized content, retries, and failure semantics.
- [x] 6.3 Update verification checklist and VM handoff documentation for briefing history UI, API, delivery tracking, and no-Teams scope.
