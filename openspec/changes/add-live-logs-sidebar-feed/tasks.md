## 1. Database migration

- [ ] 1.1 Add a new migration adding `CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)` following the existing migration-versioning convention.
- [ ] 1.2 Verify the migration applies cleanly against the existing `events` table without locking issues.

## 2. Backend: source allowlist and cursor query

- [ ] 2.1 Extend `VALID_EVENT_SOURCES` in `routes/alerts_events_routes.py` to include `honeypot` and `pfsense`.
- [ ] 2.2 Add an optional `after_id` query parameter to `/events/search` (or the events-read path), filtering `WHERE id > after_id` when provided, scoped to the given `source`.
- [ ] 2.3 Ensure ordering is newest-first (`ORDER BY id DESC` or equivalent `created_at DESC`) and preserve the existing result-limit behavior.
- [ ] 2.4 Confirm existing `@login_required` + `@analyst_or_super_admin_required` decorators remain unchanged and apply to the newly accepted sources.
- [ ] 2.5 Confirm response shape (`id, event_type, severity, source_ip, message, app_name, environment, source, source_type, raw_payload, created_at`) is unchanged for backward compatibility with existing callers.

## 3. Backend tests

- [ ] 3.1 Extend `tests/test_events_search_api_contracts.py` to cover `source=honeypot` and `source=pfsense` returning 200 with correctly scoped results.
- [ ] 3.2 Add a test asserting an unknown/invalid source is still rejected.
- [ ] 3.3 Add a test for `after_id` cursor behavior: first fetch with no cursor, subsequent fetch with cursor returns only newer rows, and a cursor at the current max returns an empty set.
- [ ] 3.4 Add/extend a 401 (unauthenticated) and role-rejection test covering the newly accepted sources.

## 4. Frontend: sidebar and navigation

- [ ] 4.1 Add a `live-logs` group with six entries (Honeypot, Bank App, pfSense, NGINX, Azure, OTEL) to `frontend/src/utils/sectionsConfig.js`, mapping each `id` to its `source` value and applying the same `visibleWhen` role gating used for `/events/search` access.
- [ ] 4.2 Confirm the "LIVE LOGS" group heading renders correctly via the existing `Sidebar.js` group-bucketing/uppercase-heading logic (no changes to `Sidebar.js` should be needed if the config pattern is followed).

## 5. Frontend: shared LiveLogsPanel and service

- [ ] 5.1 Create `frontend/src/services/liveLogsService.js` following the existing `fetch(buildSiemPath(...), { credentials: "include" })` + `parseJsonResponse` + `getApiErrorMessage` pattern, supporting `source` and `after_id` params.
- [ ] 5.2 Create `frontend/src/components/LiveLogsPanel.js` accepting a `source` prop: initial fetch on mount, `setInterval` polling every few seconds (mirroring `App.js`'s existing 5s alerts-poll pattern), cleared on unmount.
- [ ] 5.3 Implement loading, error, and empty states in `LiveLogsPanel` consistent with `AuditLogPanel.js` conventions.
- [ ] 5.4 Implement newest-first table rendering of raw normalized event fields, merging newly polled rows above existing ones without duplicating previously seen ids.
- [ ] 5.5 Add a source-label mapping (e.g. `opentelemetry` → "OTEL", `azure_insights` → "Azure") used for page headers/badges, distinct from the raw `source` value.
- [ ] 5.6 Wire six `activeSection === "live-logs-<source>"` branches in `frontend/src/App.js`, each rendering `LiveLogsPanel` with the corresponding `source` and label.

## 6. Frontend tests

- [ ] 6.1 Extend `frontend/src/utils/sectionsConfig.test.js` to cover the six new `live-logs` entries and their visibility gating.
- [ ] 6.2 Extend `frontend/src/components/Sidebar.test.js` to cover the "LIVE LOGS" group rendering.
- [ ] 6.3 Add `frontend/src/components/LiveLogsPanel.test.js` covering loading, error, empty, populated, and polling/merge-without-duplicates behavior (mocked timers/fetch).
- [ ] 6.4 Add `frontend/src/services/liveLogsService.test.js` covering request construction (source/after_id params) and response/error parsing.
- [ ] 6.5 Extend `frontend/src/App.test.js` to cover navigation into each of the six Live Logs sections.

## 7. Validation

- [ ] 7.1 Run backend test suite covering the extended `/events/search`/cursor behavior.
- [ ] 7.2 Run frontend test suite covering sidebar, panel, service, and App routing changes.
- [ ] 7.3 Manually verify in a dev environment that each of the six Live Logs pages shows only its own source's events, newest first, auto-refreshing, with correct labels.
- [ ] 7.4 Run `openspec validate add-live-logs-sidebar-feed --strict` and `git diff --check` before considering the change ready to archive.
