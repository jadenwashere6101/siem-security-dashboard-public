## Context

The sidebar is a config array (`frontend/src/utils/sectionsConfig.js`) of `{ id, label, group, visibleWhen }` entries, grouped and rendered by `Sidebar.js`; there is no router, only an `activeSection` string toggled in `App.js`. The only existing events-read endpoint, `GET /events/search` (`routes/alerts_events_routes.py`), allowlists just four of the six live sources (`bank_app`, `nginx`, `azure_insights`, `opentelemetry` — missing `honeypot` and `pfsense`), has no pagination/cursor, and returns a flat `ORDER BY created_at DESC LIMIT 100`. The `events` table has no index on `source`. The only existing polling precedent is a plain `setInterval`/`clearInterval` in `App.js` refreshing alerts every 5s; every other list panel (`AuditLogPanel`, `SoarQueuePanel`, `DeadLettersPanel`) fetches once and relies on a manual refresh button. This feature must fit these existing patterns rather than introduce new architecture (no router, no websockets, no state-management library).

## Goals / Non-Goals

**Goals:**
- One shared, source-parameterized `LiveLogsPanel` + `liveLogsService` reused across all six sources — no per-source component duplication.
- Every live source (including honeypot and pfsense, currently unfilterable) is queryable by source alone.
- Auto-refresh (every few seconds) does not duplicate or drop rows, and does not require unbounded client-side memory growth.
- Reuse existing sidebar-group, panel-shape, auth, and fetch conventions exactly as they exist today.

**Non-Goals:**
- No WebSockets/SSE — polling only, matching the codebase's only existing precedent.
- No new ingestion sources, adapters, parsers, or listener changes.
- No changes to detection rules, correlation, or SOAR playbooks.
- No infrastructure changes (Azure resources, VM provisioning, pfSense production config).
- No global/shared polling-interval config system, backoff strategy, or visibility-based pause/resume — out of scope; a fixed short interval mirroring `App.js` is sufficient.

## Decisions

**One shared `LiveLogsPanel(source)` component, not six.** Each of the six pages differs only by `source` and label; a single component parameterized by a `source` prop (passed from six distinct `activeSection` branches in `App.js`) avoids duplicating fetch/render/polling logic six times. Alternative considered: six thin wrapper components each rendering a shared inner component — rejected as unnecessary indirection when a single component accepting `source` as a prop is sufficient.

**Extend `/events/search` rather than build a new endpoint.** `VALID_EVENT_SOURCES` gets `honeypot` and `pfsense` added, and the endpoint gains an optional cursor param (e.g. `after_id`, using `events.id` — monotonic and already the primary key) so repeated polls can request only rows newer than the last-seen id. Alternative considered: a dedicated `/events/live` endpoint — rejected because the existing endpoint already has the right shape (per-source filter, ordering, allowlist validation) and the only missing piece is the allowlist and a cursor param; forking a parallel endpoint would duplicate validation logic for no benefit.

**Cursor is `after_id` (integer, `events.id`), not a timestamp.** `created_at` is not guaranteed unique at insert granularity under bursty ingestion, so a timestamp cursor risks skipping or re-fetching rows with identical timestamps. `id` is a serial primary key and strictly monotonic, so `WHERE source = :source AND id > :after_id ORDER BY id DESC` (or `created_at DESC` — order is equivalent given monotonic `id`) is race-free.

**Add a plain B-tree index on `events.source`.** Six panels will each poll this exact filter every few seconds; the table already has indexes on `source_ip`, `created_at`, and `event_type` but not `source`, so this is a straightforward gap-fill matching the existing indexing pattern in `schema.sql`, added via a new migration rather than editing `schema.sql` in place (per `add-schema-migration-versioning` precedent).

**Polling: fixed-interval `setInterval` per mounted panel, cleared on unmount.** Matches `App.js`'s only existing polling precedent exactly (5s interval, `useEffect` cleanup). Alternative considered: a shared polling hook — deferred; a single inline `useEffect`/`setInterval` inside `LiveLogsPanel` is sufficient for one component used six times and avoids introducing a new shared abstraction not otherwise present in the codebase.

**Auth: reuse `@login_required` + `@analyst_or_super_admin_required` exactly as `/events/search` uses today.** No new roles or permission levels are introduced.

## Risks / Trade-offs

- [Widening `VALID_EVENT_SOURCES` to include `honeypot`/`pfsense` changes existing endpoint behavior for any current caller of `/events/search`] → Purely additive (more accepted values, no previously-valid value is removed or reinterpreted); existing contract tests in `tests/test_events_search_api_contracts.py` continue to pass unmodified and get extended, not rewritten.
- [Six independently-polling panels increase read load on `events` if a user has multiple Live Logs tabs open, or switches between them quickly] → Mitigated by the `events.source` index and by only polling the currently-mounted (active) panel — `activeSection` toggling unmounts the previous panel and clears its interval, so at most one Live Logs panel polls at a time.
- [`after_id` cursor resets to "latest 100" on every page mount/source switch] → Acceptable: matches the "near-real-time feed from now" expectation of a live-logs view; historical backfill/search is intentionally left to the existing `/events/search` full-filter flow, not this feature.
- [No visibility/backoff handling means polling continues at fixed cadence even if the browser tab is backgrounded] → Accepted trade-off, consistent with the existing `App.js` alerts-polling behavior; not introducing new complexity beyond the established pattern.

## Migration Plan

1. Add migration for `events.source` index (additive, non-locking `CREATE INDEX IF NOT EXISTS`).
2. Extend `VALID_EVENT_SOURCES` and add the `after_id` cursor param to `/events/search` (backward compatible — cursor param is optional).
3. Add `liveLogsService.js`, `LiveLogsPanel.js`, and the six `sectionsConfig.js` entries under a new `live-logs` group.
4. Wire six `activeSection` branches in `App.js`.
5. No rollback complexity: entirely additive on both schema (new index) and API (new optional param, widened allowlist); reverting is a straightforward revert of the change.

## Open Questions

- Should `bank_app` — the schema's default `source` value, never explicitly set by any ingest route — be included as a real Live Logs page, or excluded/relabeled since it may represent legacy/uncategorized rows rather than a genuine distinct source? (Proposal includes it per explicit user request; flagged here for confirmation during implementation.)
- Is a fixed multi-second polling interval (no user-configurable rate, no pause-on-inactive-tab) acceptable long-term, or should that be tracked as a fast-follow improvement?
