# Azure Ingestion Phase 3.5 Polish Spec

## Feature Overview

This change is a narrow polish and hardening pass for Azure Application Insights ingestion.

The goal is to make the Azure adapter more practical by accepting a few additional common client IP field variants while keeping the parser strict, predictable, and limited in scope.

## Current State

- `POST /ingest/azure` exists.
- Azure ingestion requires a valid source/client IP.
- Current accepted IP fields are intentionally narrow and include `sourceIp` / `clientIp` style variants.
- Azure telemetry mappings are intentionally limited to:
  - `application_exception`
  - `availability_failure`
  - `http_error`
  - `normal_activity`
- Bank app ingestion and nginx/web-log ingestion must remain unchanged.

## Requirements

1. Expand source/client IP extraction with these common safe variants:
   - `client_IP`
   - `clientIP`
   - `context.location.clientIp`
   - `context.location.clientip`
   - `properties.clientIp`
   - `customDimensions.clientIp`

2. Keep IP validation strict.
   - accepted values must still parse as valid IP addresses
   - invalid or missing IP values must still return `400`

3. Do not add:
   - fake placeholder IPs
   - recursive JSON search
   - hostname fallback
   - nullable `source_ip` behavior

4. Add or confirm validation coverage through tests or documented manual test examples for:
   - exception telemetry → `application_exception`
   - availability failure → `availability_failure`
   - `5xx` request/dependency telemetry → `http_error`
   - successful request/dependency telemetry → `normal_activity`

5. Keep batch behavior unchanged:
   - max 25 items
   - malformed item returns `400`
   - no partial success

6. Do not change:
   - `/ingest`
   - `/ingest/web-log`
   - bank app integration
   - nginx parser
   - detection logic
   - schema
   - frontend

## Non-Goals

- No new telemetry mappings
- No recursive field discovery
- No hostname-to-IP resolution
- No fake/default source IP behavior
- No batch redesign
- No frontend changes
- No schema changes
- No detector changes

## Acceptance Criteria

1. Azure payload with `client_IP` is accepted.
2. Azure payload with `context.location.clientip` is accepted.
3. Invalid or missing IP still returns `400`.
4. Existing successful Azure `sourceIp` ingestion still works.
5. Bank app and nginx ingestion remain unaffected.
6. Syntax check passes.

## Risks and Mitigations

- Risk: broadening IP extraction too much
  - Mitigation: add only a short allowlist of common field variants, not generic recursive lookup

- Risk: accepting wrong or non-IP values
  - Mitigation: keep strict IP parsing/validation after field extraction

- Risk: accidentally changing existing adapter mappings
  - Mitigation: limit this phase to IP field extraction and validation coverage only

- Risk: breaking current working `sourceIp` behavior
  - Mitigation: preserve existing lookup order and add new fields additively rather than replacing current keys
