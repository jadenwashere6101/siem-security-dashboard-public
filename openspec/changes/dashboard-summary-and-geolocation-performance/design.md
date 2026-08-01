## Context

`/alerts/summary` currently computes metrics, top source IPs, timeline data, and map markers in one response. The map marker path fetches the latest geolocated alert for every distinct source IP, then enriches each marker with response outcome, cooldown, intelligence, and reputation data. Under pfSense ingest bursts, this can produce a multi-megabyte response and heavy per-marker application work.

The ingest path calls `lookup_ip_location()` synchronously when an event lacks a valid location. The helper caches successful responses but does not cache unknown/unavailable responses and does not protect the provider after repeated malformed or empty responses.

## Decisions

- Use an environment-configurable hard cap named `ALERT_SUMMARY_MAP_MARKER_LIMIT`, defaulting to `500`.
- Enforce the cap in SQL with `LIMIT`, after the existing ranking by alert count and recency.
- Calculate `map_markers_total` with the same filtered, synthetic-excluded, geolocated-source criteria as the marker query.
- Keep non-map summary metrics unchanged; only marker fetch/enrichment is bounded.
- Add response metadata alongside the existing `map_markers` array for backward compatibility.
- Add frontend metadata plumbing from the summary service through App and Dashboard visuals.
- Show a concise notice only when `map_markers_truncated` is true.
- Add in-memory negative caching for unknown/unavailable geolocation outcomes. This is intentionally process-local because the current positive cache is also in-memory and the immediate bottleneck is per-worker retry pressure.
- Add a provider-level circuit breaker so repeated provider failures stop synchronous retry attempts for a short cooldown window, including across different IPs.
- Throttle geolocation failure logs so provider failures remain visible without emitting one log per ingest event.

## Non-Goals

- Moving geolocation fully off the ingest path.
- Adding a durable geolocation cache table or migration.
- Changing alert detection, alert creation, SOAR behavior, AI behavior, or dashboard metrics.
- Inventing location data when the provider is unavailable.
- Rendering every historical source on the map.

## Risks

- In-memory caches reset on service restart and are per Gunicorn worker. This is acceptable for a narrow quick fix and avoids schema/runtime changes.
- The marker total requires an extra count query. It is bounded to the same filtered/geolocated source set and avoids the much larger serialization/enrichment cost.
- A circuit breaker may temporarily skip provider calls after transient failures. Successful recovery occurs after the cooldown expires.
