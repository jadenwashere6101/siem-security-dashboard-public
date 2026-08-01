## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `dashboard-summary-and-geolocation-performance`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. Backend Summary

- [x] 2.1 Add a bounded, configurable map-marker limit with safe default.
- [x] 2.2 Enforce the limit before marker enrichment and serialization.
- [x] 2.3 Return `map_markers_total`, `map_markers_returned`, and `map_markers_truncated`.
- [x] 2.4 Preserve existing summary metrics, filters, top source IPs, timeline, and synthetic/demo exclusions.

## 3. Backend Geolocation

- [x] 3.1 Add negative caching for unknown, empty, malformed, non-JSON, and provider-error geolocation outcomes.
- [x] 3.2 Add a short provider circuit breaker with bounded log emission.
- [x] 3.3 Preserve successful geolocation caching and make ingest continue when geolocation is unavailable.

## 4. Frontend

- [x] 4.1 Extend summary service/state metadata defaults.
- [x] 4.2 Show a concise dashboard map truncation notice when the response is truncated.

## 5. Tests

- [x] 5.1 Add backend tests for marker cap, metadata, bounded payload behavior, and synthetic/filter preservation.
- [x] 5.2 Add backend tests for successful geolocation caching, negative cache/circuit breaker, recovery, bounded logs, and ingest success.
- [x] 5.3 Add frontend tests for the truncation notice.

## 6. Verification

- [x] 6.1 Run relevant Python compilation and focused pytest suites.
- [x] 6.2 Run affected frontend tests.
- [x] 6.3 Run frontend production build.
- [x] 6.4 Run `git diff --check`.
- [x] 6.5 Run strict OpenSpec validation and OpenSpec status.
