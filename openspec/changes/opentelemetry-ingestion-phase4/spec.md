# OpenTelemetry Ingestion Phase 4 Spec

## Feature Overview

This change adds OpenTelemetry JSON ingestion as a standardized telemetry source for the SIEM.

The goal is to allow OTLP-style JSON logs and spans to be normalized into standard SIEM events and processed through the existing normalized ingestion pipeline without changing the current bank app, nginx, or Azure ingestion behavior.

## Current State

- Phase 1a introduced `ingest_normalized_event(...)` as reusable normalized ingest logic.
- Phase 1b added:
  - `source`
  - `source_type`
  - `event_timestamp`
  to the `events` data model.
- Phase 2 added nginx/web-log ingestion through `POST /ingest/web-log`.
- Phase 2.5 extended detection for web-log events.
- Phase 3 added Azure Application Insights ingestion through `POST /ingest/azure`.
- Existing bank app ingestion, nginx ingestion, and Azure ingestion must remain unchanged.
- There is currently no OpenTelemetry adapter or OTLP ingestion endpoint.

## Requirements

1. Add a new adapter module:
   - `adapters/otel_adapter.py`

2. Add a new backend endpoint:
   - `POST /ingest/otlp`

3. Protect the endpoint with a separate API key:
   - `OTEL_INGEST_API_KEY`
   - use the same `X-API-Key` header pattern
   - do not reuse `SIEM_INGEST_API_KEY`
   - do not reuse `AZURE_INGEST_API_KEY`

4. Support JSON only in v1:
   - no binary Protobuf
   - no gRPC receiver
   - no OpenTelemetry Collector dependency required

5. Accept OTLP-style JSON payloads as:
   - a single telemetry object
   - or a batch/list capped at 25 items

6. Normalize OTEL telemetry into the standard SIEM event structure:
   - `event_type`
   - `severity`
   - `source_ip`
   - `message`
   - `app_name`
   - `environment`
   - `raw_payload`
   - `source = "opentelemetry"`
   - `source_type = "telemetry"`
   - `event_timestamp` if available, otherwise `null`

7. Initial mapping rules:
   - HTTP span/log with `status_code >= 500` → `http_error`
   - HTTP span/log with `status_code` `401` / `403` → `unauthorized_access`
   - error or exception telemetry → `application_exception`
   - other successful HTTP telemetry → `normal_activity`

8. Source IP handling:
   - extract from common OTEL attributes such as:
     - `net.peer.ip`
     - `client.address`
     - `http.client_ip`
     - `source_ip`
   - missing or invalid IP returns `400` in v1
   - do not use fake placeholder IPs

9. Batch behavior:
   - max 25 items
   - malformed item returns `400`
   - no partial success in v1

10. Reuse `ingest_normalized_event(...)` for storage and downstream processing.

11. Do not change:
   - `/ingest`
   - `/ingest/web-log`
   - `/ingest/azure`
   - bank app integration
   - nginx parser
   - Azure adapter
   - existing detection logic
   - schema
   - frontend

## Non-Goals

- No binary OTLP/Protobuf support
- No gRPC receiver
- No OpenTelemetry Collector integration requirement
- No schema changes
- No frontend changes
- No detector redesign
- No broad OTEL taxonomy support in v1
- No recursive generic parsing across arbitrary payloads
- No partial batch success behavior
- No changes to existing ingestion sources

## Acceptance Criteria

1. Existing bank app ingestion still works.
2. Existing nginx ingestion still works.
3. Existing Azure ingestion still works.
4. `POST /ingest/otlp` accepts valid OTLP-style JSON.
5. `5xx` HTTP telemetry becomes `http_error`.
6. `401` / `403` HTTP telemetry becomes `unauthorized_access`.
7. exception or error telemetry becomes `application_exception`.
8. stored events use:
   - `source = "opentelemetry"`
   - `source_type = "telemetry"`
9. missing or invalid IP returns clean `400`.
10. syntax check passes.

## Risks and Mitigations

- Risk: OTLP payload structures vary widely
  - Mitigation: keep the v1 adapter intentionally narrow and support only a small set of known JSON shapes and attribute keys

- Risk: binary/Protobuf OTLP is out of scope
  - Mitigation: explicitly support JSON-only OTLP in v1 and reject unsupported payload formats cleanly

- Risk: source IP may be missing in many OTEL payloads
  - Mitigation: require a valid IP from a short allowlist of known attribute fields and return `400` when missing

- Risk: broad mappings become brittle
  - Mitigation: keep initial mappings limited to `http_error`, `unauthorized_access`, `application_exception`, and `normal_activity`

- Risk: accidentally breaking existing ingestion sources
  - Mitigation: implement OTEL ingestion as a separate adapter and endpoint without touching current bank, nginx, or Azure flows

- Risk: batch payloads cause partial-ingest confusion
  - Mitigation: cap batches at 25 items and fail the whole request on malformed items rather than partially ingesting

- Risk: OTEL attribute nesting differs between logs and spans
  - Mitigation: isolate normalization in `adapters/otel_adapter.py` and keep supported field extraction explicit rather than generic
