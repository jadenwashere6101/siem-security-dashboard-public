# Automatic Geo Enrichment on Ingest Spec

## Feature Overview

This change adds automatic geolocation enrichment during event ingest when incoming events do not already include location data.

The scope is intentionally focused:
- enrich events on `/ingest` when location is missing
- preserve caller-provided location when valid
- store enriched location inside `raw_payload.location`
- keep event ingestion resilient even if geolocation lookup fails

The goal is to make location handling consistent across bank app events, curl-based tests, and future integrations.

## Current State

- Events may already include `raw_payload.location`, but many manually ingested events do not.
- Alerts generated from events without location often show `Location: Unknown`.
- Alerts without latitude and longitude may not appear on the map.
- IP geolocation lookup already works for public IPs such as `88.88.88.88`.
- Location enrichment is not yet consistently applied at ingest time.

## Ingest Enrichment Behavior

On `POST /ingest`:

- If the incoming payload already includes a usable `location` object:
  - preserve it
  - do not overwrite caller-provided location unless it is clearly invalid

- If the incoming payload does not include location:
  - perform geolocation lookup using the existing geo lookup approach or a lightweight IP geolocation API
  - attempt to populate location fields from the lookup result
  - attach the result to `raw_payload.location` before storing the event

- If lookup fails:
  - continue ingest normally
  - store the event without blocking
  - location may remain unknown

## Location Data Shape

The location object stored in `raw_payload.location` should follow the existing shape already used by the SIEM where possible.

Expected fields:
- `country`
- `city`
- `lat`
- `lon`

Example:

```json
{
  "location": {
    "country": "United States",
    "city": "Des Moines",
    "lat": 41.6005,
    "lon": -93.6091
  }
}
```

## Backend Requirements

- Add ingest-time enrichment only when location is missing or unusable.
- Reuse the existing geolocation lookup logic if available.
- If a new lookup path is needed, keep it lightweight and operationally simple.
- Store enriched values in `raw_payload.location`.
- Do not require a schema migration in v1.
- Do not change detection logic.
- Keep implementation safe for future integrations and test traffic.
- To reduce excessive outbound lookups, an optional lightweight in-memory cache keyed by `source_ip` may be used.

## Failure Handling

- Geolocation lookup failure must not block event ingestion.
- If lookup fails:
  - the event must still be written
  - the endpoint should still return its normal success path if the ingest itself succeeds
  - location can remain absent or unknown
- Failures should be handled gracefully and safely without crashing the app.

## Map Compatibility Requirements

- Alerts generated from enriched events should display city and country when available.
- Alerts should appear on the map when latitude and longitude are available from enrichment.
- Existing map behavior should not need a redesign.
- The goal is additive compatibility with current map and alert rendering.

## Security/Privacy Requirements

- Do not alter authentication or RBAC behavior.
- Keep enrichment focused on IP-based geolocation only.
- Do not introduce unnecessary sensitive-data storage beyond the existing raw payload structure.
- Avoid excessive third-party lookups where possible.
- Preserve caller-provided location data unless it is clearly invalid.

## Testing Plan

Testing should cover:
- ingest with no location and a public IP successfully enriches `raw_payload.location`
- ingest with valid caller-provided location preserves the provided values
- ingest with missing location and lookup failure still stores the event successfully
- alerts created from enriched events show city/country
- alerts created from enriched events appear on the map when lat/lon are available
- repeated ingests from the same IP behave correctly if lightweight caching is enabled

## Acceptance Criteria

- Events ingested without location attempt automatic geolocation enrichment.
- Successful enrichment stores data in `raw_payload.location`.
- Existing provided location is preserved when valid.
- Event ingest does not fail if geolocation lookup fails.
- No schema migration is required.
- Detection logic remains unchanged.
- Alerts created from enriched events show improved location context when available.
- Alerts with enriched lat/lon can appear on the map.

## Non-Goals

This change does not include:
- schema redesign
- mandatory geolocation enrichment for private IPs
- historical backfill of old events
- changing detection rules
- frontend map redesign
- long-term persistent geo cache
- high-volume enrichment pipeline optimization
- privacy policy redesign
