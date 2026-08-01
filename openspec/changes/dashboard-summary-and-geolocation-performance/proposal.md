## Why

The production dashboard is slow because `/alerts/summary` returns an effectively unbounded `map_markers` payload and enriches every distinct geolocated source IP before responding. During high-volume pfSense ingest, the synchronous IP geolocation path also keeps retrying an unavailable or malformed provider response, which adds CPU/log pressure without improving event quality.

## What Changes

- Add a hard configurable cap for alert-summary map markers with a safe default.
- Apply the cap in the database query before application enrichment and JSON serialization.
- Return map-marker metadata: `map_markers_total`, `map_markers_returned`, and `map_markers_truncated`.
- Preserve existing summary metrics, filters, timeline behavior, top source IP behavior, and synthetic/demo exclusion behavior.
- Show an analyst-visible map notice when only the top N of M sources are displayed.
- Add bounded negative caching and a short provider circuit breaker for geolocation failures.
- Preserve successful geolocation caching and allow ingest to succeed when geolocation is unavailable.
- Keep the fix narrow: no migration, no detection/SOAR/AI changes, and no production mutation path.

## Capabilities

### New Capabilities
- `dashboard-summary-and-geolocation-performance`: Bounded dashboard map-marker summaries and resilient geolocation lookup behavior for high-volume ingest.

### Modified Capabilities

## Impact

- Backend: alert summary query/response shape, geolocation helper caching/circuit-breaker behavior, focused tests.
- Frontend: dashboard map summary metadata handling and truncation notice.
- Database: no migration expected; existing alert schema and filters are reused.
- Runtime/deployment: source-only Mac change. No VM access, deployment, runtime provider reconfiguration, or production mutation is performed.
