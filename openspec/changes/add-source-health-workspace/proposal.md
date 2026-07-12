## Why

Analysts can inspect alerts and recent per-source events, but they cannot obtain one authoritative view of whether every recognized ingest source has ever sent data or how much data it has sent recently. Source Health will provide database-backed activity facts for all six sources without treating the capped `/events/search` feed as an aggregation API.

## What Changes

- Add one authenticated, read-only backend endpoint that returns all six recognized sources in one response.
- Aggregate `last_event_at`, last-hour events, current-UTC-day events, total events, and ever-seen state directly from the `events` table.
- Define exact UTC boundaries and include zero-valued rows for sources with no stored events.
- Centralize the canonical source inventory, source types, and friendly labels for backend validation/aggregation, while keeping frontend source metadata aligned with that contract.
- Add a Source Health item directly beneath Dashboard in the Overview sidebar group.
- Add one shared frontend workspace that renders every source, refreshes through the existing polling pattern, handles loading/empty/error states, and links each source to its existing Live Logs workspace.
- Preserve Dashboard alert aggregation and all ingestion, parser, detection, correlation, SOAR, and pfSense behavior.
- Exclude parser/listener failures, ingest rejections, attempted-ingest tracking, service health, health classifications, and freshness thresholds.

## Capabilities

### New Capabilities

- `source-health-workspace`: Authoritative all-source event activity API, canonical source inventory, Source Health navigation/workspace, polling, state handling, and Live Logs navigation.

### Modified Capabilities

(none)

## Impact

- Backend: recognized-source metadata, a reusable `events` aggregation query/helper, one new read-only route, and focused API/query tests.
- Frontend: Overview navigation configuration, Source Health service/component integration, polling, source-to-Live-Logs navigation, and focused component/routing tests.
- Database: reads existing indexed `events.source` and `events.created_at` columns; no schema migration is expected unless implementation evidence proves the existing indexes inadequate.
- Deployment: combined backend/frontend release after Mac verification and explicit authorization; VM deployment and production verification remain a separate operator phase.
