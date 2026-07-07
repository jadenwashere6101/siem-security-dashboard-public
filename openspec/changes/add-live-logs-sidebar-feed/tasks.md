## 1. Database migration

- [x] 1.1 Add a new migration adding `CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)` following the existing migration-versioning convention.
- [x] 1.2 Verify the migration applies cleanly against the existing `events` table without locking issues.

## 2. Backend: source allowlist and cursor query

- [x] 2.1 Extend `VALID_EVENT_SOURCES` in `routes/alerts_events_routes.py` to include `honeypot` and `pfsense`.
- [x] 2.2 Add an optional `after_id` query parameter to `/events/search` (or the events-read path), filtering `WHERE id > after_id` when provided, scoped to the given `source`.
- [x] 2.3 Ensure ordering is newest-first (`ORDER BY id DESC` or equivalent `created_at DESC`) and preserve the existing result-limit behavior.
- [x] 2.4 Confirm existing `@login_required` + `@analyst_or_super_admin_required` decorators remain unchanged and apply to the newly accepted sources.
- [x] 2.5 Confirm response shape (`id, event_type, severity, source_ip, message, app_name, environment, source, source_type, raw_payload, created_at`) is unchanged for backward compatibility with existing callers.

## 3. Backend tests

- [x] 3.1 Extend `tests/test_events_search_api_contracts.py` to cover `source=honeypot` and `source=pfsense` returning 200 with correctly scoped results.
- [x] 3.2 Add a test asserting an unknown/invalid source is still rejected.
- [x] 3.3 Add a test for `after_id` cursor behavior: first fetch with no cursor, subsequent fetch with cursor returns only newer rows, and a cursor at the current max returns an empty set.
- [x] 3.4 Add/extend a 401 (unauthenticated) and role-rejection test covering the newly accepted sources.

## 4. Frontend: sidebar and navigation

- [x] 4.1 Add a `live-logs` group with six entries (Honeypot, Bank App, pfSense, NGINX, Azure, OTEL) to `frontend/src/utils/sectionsConfig.js`, mapping each `id` to its `source` value and applying the same `visibleWhen` role gating used for `/events/search` access.
- [x] 4.2 Confirm the "LIVE LOGS" group heading renders correctly via the existing `Sidebar.js` group-bucketing/uppercase-heading logic (no changes to `Sidebar.js` should be needed if the config pattern is followed).

## 5. Frontend: shared LiveLogsPanel and service

- [x] 5.1 Create `frontend/src/services/liveLogsService.js` following the existing `fetch(buildSiemPath(...), { credentials: "include" })` + `parseJsonResponse` + `getApiErrorMessage` pattern, supporting `source` and `after_id` params.
- [x] 5.2 Create `frontend/src/components/LiveLogsPanel.js` accepting a `source` prop: initial fetch on mount, `setInterval` polling every few seconds (mirroring `App.js`'s existing 5s alerts-poll pattern), cleared on unmount.
- [x] 5.3 Implement loading, error, and empty states in `LiveLogsPanel` consistent with `AuditLogPanel.js` conventions.
- [x] 5.4 Implement newest-first table rendering of raw normalized event fields, merging newly polled rows above existing ones without duplicating previously seen ids.
- [x] 5.5 Add a source-label mapping (e.g. `opentelemetry` → "OTEL", `azure_insights` → "Azure") used for page headers/badges, distinct from the raw `source` value.
- [x] 5.6 Wire six `activeSection === "live-logs-<source>"` branches in `frontend/src/App.js`, each rendering `LiveLogsPanel` with the corresponding `source` and label.

## 6. Frontend tests

- [x] 6.1 Extend `frontend/src/utils/sectionsConfig.test.js` to cover the six new `live-logs` entries and their visibility gating.
- [x] 6.2 Extend `frontend/src/components/Sidebar.test.js` to cover the "LIVE LOGS" group rendering.
- [x] 6.3 Add `frontend/src/components/LiveLogsPanel.test.js` covering loading, error, empty, populated, and polling/merge-without-duplicates behavior (mocked timers/fetch).
- [x] 6.4 Add `frontend/src/services/liveLogsService.test.js` covering request construction (source/after_id params) and response/error parsing.
- [x] 6.5 Extend `frontend/src/App.test.js` to cover navigation into each of the six Live Logs sections.

## 7. Validation

- [x] 7.1 Run backend test suite covering the extended `/events/search`/cursor behavior.
- [x] 7.2 Run frontend test suite covering sidebar, panel, service, and App routing changes.
- [x] 7.3 Manually verify in a dev environment that each of the six Live Logs pages shows only its own source's events, newest first, auto-refreshing, with correct labels.
- [x] 7.4 Run `openspec validate add-live-logs-sidebar-feed --strict` and `git diff --check` before considering the change ready to archive.
