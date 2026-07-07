## Why

Analysts currently have no way to watch raw normalized events from a single ingestion source as they arrive. The only events-oriented view (`/events/search`) requires manually re-running a search, doesn't support all six live sources (honeypot and pfsense are rejected by the current allowlist), and has no dedup-safe way to poll for new rows. A per-source "LIVE LOGS" sidebar section gives analysts a lightweight, always-current feed per source, reusing the existing sidebar/panel/polling patterns already proven in this codebase.

## What Changes

- Add a new top-level sidebar group, "LIVE LOGS", following the same `sectionsConfig.js` group pattern as the existing "ADMINISTRATION" group.
- Add six navigation items under LIVE LOGS, one per ingestion source: Honeypot (`honeypot`), Bank App (`bank_app`), pfSense (`pfsense`), NGINX (`nginx`), Azure (`azure_insights`), OTEL (`opentelemetry`).
- Add one shared `LiveLogsPanel` component, parameterized by `source`, rendering a newest-first raw normalized event feed that auto-refreshes every few seconds. No per-source component duplication.
- Add a `liveLogsService` frontend module following the existing hand-rolled fetch + `buildSiemPath` + `parseJsonResponse` convention.
- Extend backend source filtering (`VALID_EVENT_SOURCES` in `routes/alerts_events_routes.py`) to accept `honeypot` and `pfsense`, which are valid, ingested sources today but are currently unfilterable. **BREAKING**: none — this only widens an existing allowlist.
- Add cursor/since-based polling support to the events-read path so repeated auto-refresh requests return only new rows instead of duplicating the top 100 each time.
- Add a database index on `events.source` to support per-source filtering at poll frequency.

## Capabilities

### New Capabilities
- `live-logs-feed`: Sidebar group, navigation items, shared `LiveLogsPanel` UI, `liveLogsService`, polling/loading/error/empty-state behavior for a per-source near-real-time raw event feed.
- `events-source-cursor-query`: Backend capability for querying events scoped to a single source with cursor/since semantics, extending the existing `/events/search` allowlist and read path to support all six live sources without duplicate rows on repeated polls.

### Modified Capabilities
(none — no existing `openspec/specs/` capability governs sidebar navigation or events search today; both areas are treated as new capabilities above rather than deltas.)

## Impact

- Frontend: `frontend/src/utils/sectionsConfig.js`, `frontend/src/App.js`, new `frontend/src/components/LiveLogsPanel.js`, new `frontend/src/services/liveLogsService.js`.
- Backend: `routes/alerts_events_routes.py` (`VALID_EVENT_SOURCES`, `/events/search` or a new cursor-aware route), a new migration for an `events.source` index.
- Tests: new/extended frontend component, service, sidebar-config, and App-routing tests; new/extended backend API contract tests.
- No changes to ingestion adapters, detection/SOAR logic, or infrastructure (Azure, VM, pfSense production).
