# OpenTelemetry Ingestion — Phase 4 Spec

## Feature Overview

This phase standardizes OpenTelemetry telemetry ingestion by defining the exact supported payload shape, formalizing the field mapping from OTEL fields to SIEM event fields, and closing two behavioral gaps in the existing implementation.

The existing `POST /ingest/otlp` endpoint and `adapters/otel_adapter.py` already handle the core ingestion flow. This phase does not introduce a new endpoint or pipeline. It defines the correct behavior precisely and identifies two requirements that need tightening: `app_name` sourcing and unclassified telemetry handling.

## Current State

**What exists:**

- `POST /ingest/otlp` in `siem_backend.py` — accepts single or batched OTEL telemetry (max 25 items), protected by `OTEL_INGEST_API_KEY`
- `adapters/otel_adapter.py` — exports `normalize_otel_telemetry(telemetry)` which extracts and maps OTEL fields to normalized SIEM event fields
- The adapter handles both flat attribute dicts and OTEL proto-style attribute arrays (`[{"key": "k", "value": {"stringValue": "v"}}]`)
- The adapter searches for attributes across `attributes`, `resource.attributes`, `span.attributes`, and `logRecord.attributes`
- `source = "opentelemetry"` and `source_type = "telemetry"` are hardcoded in the route handler
- The route passes all normalized events through `ingest_normalized_event` — the same detection and correlation pipeline used by all other ingest paths
- A whole batch fails with `400` if any single item raises `ValueError`

**What is missing or inconsistent:**

1. **`app_name` hardcoded**: `app_name` is always stored as `"opentelemetry"` regardless of what the payload contains. OTEL payloads commonly carry `service.name` in resource attributes, which should be used instead.

2. **Unclassified telemetry rejected with `400`**: If a payload has a valid source IP and message but no HTTP status code, no `exception.type`, and no OTEL error status, the adapter currently raises `ValueError("Unsupported OpenTelemetry telemetry type")`. A valid OTEL log record with no HTTP context would hit this path and be rejected, which is incorrect behavior.

3. **Supported payload shape is undocumented**: The adapter handles multiple OTEL signal shapes but there is no spec defining what is and is not accepted.

## Requirements

### 1. Supported OTEL Payload Shape

The endpoint accepts JSON only — no binary Protobuf, no gRPC.

The top-level payload must be either:
- A single OTEL telemetry object (JSON object)
- A batch of up to 25 OTEL telemetry objects (JSON array)

An empty array or a non-object/non-array payload must return `400`.

The following OTEL signal shapes are supported within a single telemetry object:

**Span-style:**
```json
{
  "name": "...",
  "startTimeUnixNano": "...",
  "status": {"code": "ERROR"},
  "attributes": [...],
  "resource": {"attributes": [...]},
  "span": {"startTimeUnixNano": "...", "attributes": [...]}
}
```

**Log record-style:**
```json
{
  "body": "...",
  "timeUnixNano": "...",
  "attributes": [...],
  "logRecord": {"timeUnixNano": "...", "attributes": [...]}
}
```

**Flat/generic event:**
```json
{
  "source_ip": "1.2.3.4",
  "message": "...",
  "status_code": 500,
  "timestamp": "..."
}
```

All three shapes are processed through the same adapter function. Mixed batches are allowed.

### 2. Field Mapping

The adapter is responsible for extracting `event_type`, `severity`, `source_ip`, `message`, and `event_timestamp`. The route handler is responsible for setting `source`, `source_type`, `app_name`, `environment`, and `raw_payload`.

#### Source IP

Checked in this priority order:
1. Top-level `source_ip`
2. Top-level `sourceIp`
3. Attributes: `net.peer.ip`, `client.address`, `http.client_ip`

Attributes are searched across `attributes`, `resource.attributes`, `span.attributes`, `logRecord.attributes` — in that order, first match wins.

If no valid IP is found, the adapter raises `ValueError`. The route returns `400` for the entire batch.

#### Event Type and Severity

Determined in this priority order:

| Condition | `event_type` | `severity` |
|---|---|---|
| HTTP status code 401 or 403 | `unauthorized_access` | `medium` |
| HTTP status code 500–599 | `http_error` | `medium` |
| Attribute `exception.type` present, OR OTEL status is `"error"` or `"2"` | `application_exception` | `high` |
| Any other non-null HTTP status code | `normal_activity` | `low` |
| No classifiable signal at all | `normal_activity` | `low` |

The last row is a behavioral fix. Payloads with a valid source IP but no HTTP status code, no exception type, and no OTEL error status must map to `normal_activity` — not raise `ValueError`. The current `raise ValueError("Unsupported OpenTelemetry telemetry type")` path must be removed and replaced with this fallback.

**Guardrail — `unauthorized_access` event type**: `unauthorized_access` is not in `VALID_EVENT_TYPES` (the strict set validated by `/ingest`) but is present in `VALID_EVENT_SEARCH_TYPES` and is handled by `ingest_normalized_event`. The current OTEL adapter already maps 401/403 status codes to `unauthorized_access`. This mapping must be preserved as-is. Do not introduce `unauthorized_access` as a new event type in any path that validates against `VALID_EVENT_TYPES`. If future backend behavior removes support for `unauthorized_access` in the OTEL pipeline, revert to the next applicable mapping rather than forcing it through.

HTTP status code is extracted from: top-level `status_code` → `statusCode` → attributes `http.status_code`, `status_code`, `statusCode` — first non-empty value wins.

OTEL status is extracted from: `status.code` (nested) → top-level `status` → attribute `otel.status_code`.

#### Message

Checked in this priority order:
1. Top-level `body` (only if the value is a non-empty string)
2. Top-level `message`
3. Attribute `exception.message`

If all are absent or empty, a type-specific fallback string is used:
- `unauthorized_access`: `"Unauthorized HTTP telemetry detected: status {code} for {operation_name}"`
- `http_error`: `"HTTP error telemetry detected: status {code} for {operation_name}"`
- `application_exception`: `"Application exception telemetry detected: {operation_name}"`
- `normal_activity`: `"OpenTelemetry event observed: {operation_name}"`

`operation_name` falls back through: `name` → `message` → attributes `http.target`, `url.path`, `http.route` → `"OpenTelemetry event"`.

Final message must never be null or empty.

#### Event Timestamp

Checked in this priority order:
1. `timeUnixNano`
2. `observedTimeUnixNano`
3. `startTimeUnixNano`
4. `timestamp`
5. `time`
6. `span.startTimeUnixNano`
7. `logRecord.timeUnixNano`

Unix nanosecond integer values are converted to ISO 8601. String values are passed through as-is. If no timestamp is found, `event_timestamp` is `null`.

#### app_name

The adapter may return an optional `app_name` key in its result dict if it can safely extract `service.name` from the attribute maps. The adapter must not raise an error if `service.name` is absent.

The route handler is responsible for storing `app_name`. It must derive the value using this fallback order:
1. `app_name` from the normalized adapter result (if present and non-empty)
2. Top-level `serviceName` from the raw payload
3. `"opentelemetry"`

The route handler must never store a null or empty `app_name`.

#### Fixed fields (set by route handler only)

| Field | Value |
|---|---|
| `source` | `"opentelemetry"` — always, not overridable from payload |
| `source_type` | `"telemetry"` — always, not overridable from payload |
| `environment` | payload `environment` field → `"prod"` default |
| `raw_payload` | entire incoming telemetry item stored as-is |

### 3. Validation Behavior

- Payload must be a non-empty dict or a non-empty list of dicts. Anything else returns `400`.
- Batch size is capped at 25 items. Exceeding this returns `400`.
- Missing or invalid source IP is a hard failure — returns `400` for the entire batch.
- Missing message is not a failure — type-specific fallback strings are used.
- A payload with no classifiable signal must map to `normal_activity`, not return `400`.
- A single invalid item in a batch causes the entire batch to fail. There is no partial success.

### 4. Authentication

- Preserve current OTEL API-key protection behavior exactly.
- Do not weaken authentication.
- Do not change the auth scheme.
- The key is passed via the `X-API-Key` header — same pattern as all other ingest endpoints.
- Do not reuse `SIEM_INGEST_API_KEY` or `AZURE_INGEST_API_KEY`.

### 5. Ingestion Behavior

- The route calls `ingest_normalized_event(event_dict, conn, cur)` for each normalized item — the same shared function used by all other ingest paths.
- Detection and correlation run after every insert, exactly as they do for bank app, nginx, and Azure events.
- No separate storage path or new database table is created.
- All events are stored in the existing `events` table.
- A single database transaction covers the entire batch. If the commit fails, the entire batch is rolled back.

## Scope

**Files to be modified:**

- `adapters/otel_adapter.py` — remove the `raise ValueError("Unsupported OpenTelemetry telemetry type")` path; replace with `normal_activity` fallback; add `app_name` extraction from `service.name` to the returned dict
- `siem_backend.py` — update the `/ingest/otlp` route handler to read `app_name` from the adapter result, falling back to payload lookup or `"opentelemetry"`

**Explicit boundaries:**

- Do not modify `/ingest`, `/ingest/web-log`, or `/ingest/azure`
- Do not modify `adapters/nginx_adapter.py` or `adapters/azure_insights_adapter.py`
- Do not modify any frontend file
- Do not add new routes or endpoints
- Do not add new database tables or columns
- Do not add new libraries

## Non-Goals

- No frontend or UI changes
- No schema changes
- No new database tables
- No new libraries
- No new ingest endpoints
- No binary OTLP or Protobuf support
- No gRPC receiver
- No OpenTelemetry Collector integration
- No support for OTEL metric signals
- No support for every OTEL semantic convention
- No Azure changes
- No file ingestion changes
- No rewrite of existing ingestion endpoint structure

## Acceptance Criteria

1. A payload with only `source_ip` and `body` (no status code, no exception) returns `201` and stores an event with `event_type = 'normal_activity'`.
2. A payload with `status_code = 500` stores an event with `event_type = 'http_error'`.
3. A payload with `exception.type` in attributes stores an event with `event_type = 'application_exception'`.
4. A payload with `service.name` in `resource.attributes` stores an event with `app_name` equal to that service name.
5. A payload with no `service.name` anywhere stores an event with `app_name = 'opentelemetry'`.
6. A payload with a missing or invalid source IP returns `400`.
7. A batch exceeding 25 items returns `400`.
8. Existing OTEL API-key protection behavior is preserved and not weakened.
9. A request with a wrong or missing API key is rejected.
10. All stored OTEL events have `source = 'opentelemetry'` and `source_type = 'telemetry'`.
11. OTEL events flow through the existing detection pipeline and can produce alerts when thresholds are met.
12. No changes are made to `/ingest`, `/ingest/web-log`, `/ingest/azure`, or any frontend file.
13. Syntax check passes on all modified files.

## Risks and Mitigations

- Risk: replacing `ValueError` with `normal_activity` causes low-value events from unrecognized payload shapes to accumulate silently
  - Mitigation: `normal_activity` with severity `low` does not trigger alerts on its own; only detection rules acting on volume would generate an alert; this is consistent with how `normal_activity` behaves for all other sources

- Risk: `app_name` extraction from `service.name` returns a non-string or unexpected type
  - Mitigation: apply the same `_first_non_empty_value` defensive approach already used throughout the adapter; always fall back to `"opentelemetry"` if the extracted value is not a usable string

- Risk: the adapter returning `app_name` in its output dict represents a minor interface change between adapter and route handler
  - Mitigation: the route handler reads it with `.get("app_name")` and has its own fallback; existing behavior is unchanged for any caller that ignores the new key

- Risk: removing the `ValueError` fallthrough accidentally masks a real error type
  - Mitigation: the priority order in Section 2 checks exception and error signals before reaching the `normal_activity` fallback; a payload with `exception.type` or OTEL error status will never reach the fallback
