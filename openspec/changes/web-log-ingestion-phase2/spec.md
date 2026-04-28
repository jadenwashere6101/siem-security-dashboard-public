# Web Log Ingestion Phase 2 Spec

## Feature Overview

This change adds web server log ingestion as a second data source for the SIEM.

The goal is to allow nginx-style web server access logs to be parsed, normalized into standard SIEM events, and processed through the existing ingestion pipeline without changing the current bank app `/ingest` flow.

## Current State

- Phase 1a introduced `ingest_normalized_event(...)` as reusable normalized ingest logic.
- Phase 1b added `source`, `source_type`, and `event_timestamp` fields to the `events` model.
- The current `/ingest` endpoint is built around structured JSON events from the bank app and similar custom senders.
- Existing bank app ingestion must remain unchanged.
- There is currently no adapter or endpoint for raw web server access log ingestion.

## Requirements

1. Add a new adapter module:
   - `adapters/nginx_adapter.py`

2. The adapter should parse nginx Combined Log Format or a common access log format line.

3. Add a new backend endpoint:
   - `POST /ingest/web-log`

4. v1 endpoint request shape:
   - single line only:
     - `{ "line": "..." }`
   - future batch support may be considered later, but v1 should stay single-line if batch handling adds risk

5. Protect the endpoint with the same API key authentication model used for ingestion.

6. Normalize parsed log lines into the standard SIEM event structure:
   - `event_type`
   - `severity`
   - `source_ip`
   - `message`
   - `app_name`
   - `environment`
   - `raw_payload`
   - `source = "nginx"`
   - `source_type = "web_log"`
   - `event_timestamp` if parsed, otherwise `null`

7. Add explicit event types for web-log normalization:
   - `unauthorized_access`
   - `http_error`
   - `high_request_rate` if practical, otherwise leave as future detector

8. Event mapping rules:
   - HTTP `401` / `403` → `unauthorized_access`
   - HTTP `5xx` → `http_error`
   - normal `2xx` / `3xx` → `normal_activity`

9. Reuse `ingest_normalized_event(...)` for storage and downstream detection dispatch.

10. Do not change:
   - existing `/ingest` endpoint
   - bank app payload
   - bank app integration
   - existing response behavior
   - existing detection rules unless explicitly required for compatibility

11. Malformed log lines must return clean `400` errors in single-line v1.

12. No frontend changes in this phase.

## Non-Goals

- No frontend work
- No bank app changes
- No batch ingestion in v1 unless later approved
- No redesign of the existing `/ingest` endpoint
- No detection rule redesign
- No web log dashboard UI yet
- No historical log import tooling
- No support for every possible web log format in v1

## Acceptance Criteria

1. Existing bank app `/ingest` still works unchanged.
2. `POST /ingest/web-log` accepts a valid nginx log line.
3. A valid `401` or `403` log line becomes `unauthorized_access`.
4. A valid `5xx` log line becomes `http_error`.
5. A valid normal `2xx` or `3xx` log line becomes `normal_activity`.
6. Stored events use:
   - `source = "nginx"`
   - `source_type = "web_log"`
7. Malformed log lines return a clean error response.
8. No bank app behavior changes.

## Risks and Mitigations

- Risk: log format variations cause unreliable parsing
  - Mitigation: keep v1 scoped to nginx Combined Log Format or one clearly defined common format, and reject malformed lines cleanly

- Risk: bad parsing causes crashes or partial ingest failures
  - Mitigation: isolate parsing in `adapters/nginx_adapter.py`, validate parsed fields before normalization, and return controlled `400` responses for bad lines

- Risk: adding web-log event types accidentally weakens or broadens `VALID_EVENT_TYPES` unsafely
  - Mitigation: add only the explicitly required event types and keep validation strict

- Risk: auth behavior diverges from existing ingestion security
  - Mitigation: reuse the existing API key authentication pattern for `/ingest/web-log`

- Risk: normalized web log events accidentally alter current detection behavior
  - Mitigation: reuse `ingest_normalized_event(...)` without changing existing detector logic, and avoid introducing new detectors in this phase unless separately approved

- Risk: timestamp parsing from web logs is inconsistent
  - Mitigation: set `event_timestamp` only when parsing is successful; otherwise store `null` and rely on `created_at` as the ingest timestamp

- Risk: normal `2xx` / `3xx` traffic creates noisy events
  - Mitigation: explicitly normalize normal `2xx` / `3xx` traffic to `normal_activity` in v1 so behavior is predictable and consistent
