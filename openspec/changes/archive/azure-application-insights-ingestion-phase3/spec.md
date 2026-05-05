# Azure Application Insights Ingestion Phase 3 Spec

## Feature Overview

This change adds Azure Application Insights ingestion as a cloud telemetry source for the SIEM.

The goal is to allow Azure/Application Insights telemetry to be normalized into standard SIEM events and processed through the existing normalized ingestion pipeline without changing the current bank app or web-log ingestion behavior.

## Current State

- Phase 1a introduced `ingest_normalized_event(...)` as reusable normalized ingest logic.
- Phase 1b added:
  - `source`
  - `source_type`
  - `event_timestamp`
  to the `events` data model.
- Phase 2 added nginx/web-log ingestion through `POST /ingest/web-log`.
- Phase 2.5 extended detection for web-log events.
- The bank app `/ingest` flow and nginx/web-log ingestion must remain unchanged.
- There is currently no Azure/Application Insights adapter or ingestion endpoint.

## Requirements

1. Add a new adapter module:
   - `adapters/azure_insights_adapter.py`

2. Add a new backend endpoint:
   - `POST /ingest/azure`

3. Protect the endpoint with a separate API key:
   - `AZURE_INGEST_API_KEY`
   - use the same `X-API-Key` header pattern
   - do not reuse `SIEM_INGEST_API_KEY`

4. Endpoint payload support:
   - accept either:
     - a single telemetry object
     - or a list of telemetry objects
   - batch size must be capped at 25 items per request
   - malformed batch items must return a clean `400`
   - no partial success in v1

5. Normalize Azure telemetry into the standard SIEM event structure:
   - `event_type`
   - `severity`
   - `source_ip`
   - `message`
   - `app_name`
   - `environment`
   - `raw_payload`
   - `source = "azure_insights"`
   - `source_type = "cloud_api"`
   - `event_timestamp` if available, otherwise `null`

6. Add explicit Azure-related event types:
   - `application_exception`
   - `availability_failure`
   - `http_error` when Azure request/dependency telemetry represents `5xx` behavior

7. Initial mapping rules:
   - exception telemetry → `application_exception`
   - availability failure → `availability_failure`
   - failed request or `5xx` request/dependency telemetry → `http_error`
   - successful request/dependency telemetry → `normal_activity`

8. Handle nested JSON defensively:
   - use safe `.get()` access patterns
   - missing optional fields must not crash the endpoint
   - malformed required payload structure should return a clean `400`

9. Source IP handling:
   - if Azure telemetry does not contain a valid source/client IP, return `400`
   - do not ingest items with missing or invalid source/client IP in v1
   - do not use fake placeholder IPs

10. Reuse `ingest_normalized_event(...)` for storage and downstream processing.

11. Do not change:
   - existing `/ingest` endpoint
   - bank app integration
   - existing `/ingest/web-log` endpoint
   - nginx parser behavior
   - existing detection behavior unless clearly required for compatibility

12. No frontend changes in this phase.

13. No Azure-specific detectors in this phase.

## Non-Goals

- No frontend work
- No bank app changes
- No nginx/web-log parser changes
- No redesign of the existing ingest endpoints
- No Azure-specific dashboard UI
- No large telemetry taxonomy in v1
- No schema redesign unless proven necessary
- No async ingestion pipeline in this phase
- No broad cloud-provider abstraction layer yet
- No Azure-specific detectors

## Acceptance Criteria

1. Existing bank app `/ingest` still works unchanged.
2. Existing `/ingest/web-log` still works unchanged.
3. `POST /ingest/azure` accepts valid Azure-style telemetry.
4. Exception telemetry becomes `application_exception`.
5. Availability failure becomes `availability_failure`.
6. `5xx` request/dependency telemetry becomes `http_error`.
7. Stored events use:
   - `source = "azure_insights"`
   - `source_type = "cloud_api"`
8. Malformed payloads return clean errors.
9. Existing detection pipeline remains stable.

## Risks and Mitigations

- Risk: Azure payloads are nested and inconsistent
  - Mitigation: isolate parsing and normalization in `adapters/azure_insights_adapter.py` and use defensive `.get()` access throughout

- Risk: high-volume batch payloads could overwhelm synchronous ingestion
  - Mitigation: cap batch size at 25 items and fail the whole request on malformed items rather than attempting partial success

- Risk: separate API key misconfiguration
  - Mitigation: use a dedicated `AZURE_INGEST_API_KEY` and fail closed if it is missing or incorrect

- Risk: some telemetry may not contain a usable source IP
  - Mitigation: reject such payloads with a clean `400` and do not insert placeholder IPs

- Risk: accidentally changing existing bank or web ingestion behavior
  - Mitigation: add the Azure path as a separate adapter and endpoint, and leave existing routes untouched

- Risk: adding too many Azure mappings too early
  - Mitigation: keep v1 mapping intentionally narrow to exception, availability failure, `http_error`, and `normal_activity`

- Risk: Azure `http_error` events could create noisy alerts if volume is high
  - Mitigation: reuse the current normalized event pipeline first and avoid adding new Azure-specific detectors in this phase unless separately approved
