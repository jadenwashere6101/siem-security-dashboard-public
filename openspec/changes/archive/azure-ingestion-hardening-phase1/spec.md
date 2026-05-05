# Azure Ingestion Hardening — Phase 1 Spec

## Feature Overview

This change hardens the existing Azure Application Insights ingestion path to make it more reliable, predictable, and easier to debug.

The goal is to close gaps between what the Azure Function forwards and what the backend adapter accepts, enforce consistent field values across all Azure events, and make failure modes explicit and observable — without changing the overall architecture.

## Current State

**What exists:**

- `POST /ingest/azure` accepts single or batched Azure telemetry (max 25 items)
- `adapters/azure_insights_adapter.py` normalizes telemetry to SIEM events
- `siem-azure-function/function_app.py` polls Log Analytics and forwards telemetry to the backend
- `source = "azure_insights"` and `source_type = "cloud_api"` are hardcoded in the route handler
- `_extract_source_ip` raises `ValueError` on missing or invalid IP (causes 400 for the whole batch)
- Message has fallback chains in the adapter, but behavior is undocumented
- Severity is hardcoded as a string in the adapter (`"high"`, `"medium"`, `"low"`) — the `severityLevel` integer from Log Analytics is ignored
- `app_name` is hardcoded as `"azure_application_insights"` in the route handler regardless of the cloud role name in the payload

**What is missing or inconsistent:**

1. **401/403 event type gap**: The Azure Function queries for 401 and 403 request telemetry and classifies them as `unauthorized_access` internally. It forwards these to the backend with `baseType = "RequestData"` and `responseCode = 401` or `403`. The backend adapter maps these to `normal_activity` (via the `result_code is not None` branch) because only 5xx is mapped to `http_error`. This is an undocumented, unintended mismatch.

2. **Missing source IP in batch**: A missing or invalid source IP in one batch item causes the entire batch to return 400. This behavior is correct but undocumented and not logged with context.

3. **Message fallback not formalized**: The adapter has message fallbacks but they vary by event type and are not consistently defined.

4. **`app_name` not sourced from payload**: `cloud_RoleName` is present in function_app-forwarded payloads but ignored by the route handler.

5. **`unauthorized_access` in function_app logging**: The function_app's `mapping_counts` dict includes `unauthorized_access` as a tracked type, but this type is not a recognized backend Azure event type.

## Requirements

### 1. Do not introduce new Azure event types

- Azure telemetry with 4xx response codes (401/403) must not introduce new SIEM event types.
- Existing behavior where such events fall through to `normal_activity` is acceptable.
- Do NOT modify the Azure Function KQL query.
- Do NOT modify classification logic in `function_app.py`.
- Improvements to 4xx handling can be handled in a future phase.

### 2. Define consistent message fallback behavior

- All Azure events must produce a non-empty message string.
- Message selection must prioritize:
  - primary Azure-provided message fields
  - operation/request names
  - type-specific fallback strings
- Each event type must have a deterministic fallback chain.
- Final message must never be empty or null.

### 3. Enforce safe source IP behavior

- Missing or invalid source IP must raise `ValueError("Missing valid source/client IP")` — this is correct current behavior and must be preserved.
- The batch route handler must log the offending item index and error type/message before returning 400.
- Do not log full raw payloads. Avoid logging sensitive data.
- Do not add nullable `source_ip` behavior. Do not add fallback/placeholder IPs.

### 4. Enforce consistent `source` and `source_type`

- `source = "azure_insights"` must always be set by the route handler, not by the adapter.
- `source_type = "cloud_api"` must always be set by the route handler, not by the adapter.
- Neither value should be user-supplied or overridable from the incoming payload.

### 5. Use `cloud_RoleName` for `app_name` when present

- If `cloud_RoleName` is present and non-empty in the payload, the route handler should use it as `app_name`.
- If missing or invalid, fall back safely to `"azure_application_insights"`.
- The adapter does not need to return `app_name` — the route handler owns this field.
- Value must be a non-empty string after fallback.

### 6. Do not change

- `/ingest` (bank app endpoint)
- `/ingest/web-log` (nginx endpoint)
- Existing detection dispatch behavior
- Existing correlation rules
- Alert schema
- Database schema
- Batch size cap (25 items)
- Batch failure behavior (whole batch fails on first invalid item)
- `VALID_EVENT_TYPES` list behavior
- Frontend

## Scope

**Files likely to be touched:**

- `adapters/azure_insights_adapter.py` — formalize message fallback chain per event type; verify all code paths produce a non-empty message
- `siem_backend.py` — add per-item error logging in `/ingest/azure` batch handler; implement `cloud_RoleName` → `app_name` lookup

**Explicit boundaries:**

- Do NOT modify `siem-azure-function/function_app.py` in this phase
- No changes to `/ingest` or `/ingest/web-log`
- No changes to detection or correlation logic
- No schema changes
- No frontend changes
- No new environment variables

## Non-Goals

- New event types beyond `application_exception` and `http_error`
- New Azure-specific detectors
- New Azure ingestion endpoints
- Nullable or placeholder source IP behavior
- Recursive field discovery in the adapter
- Async ingestion pipeline
- Frontend or dashboard changes
- OpenTelemetry changes
- Full Azure setup documentation
- Azure identity/login ingestion
- Geo enrichment changes
- No changes to Azure polling/query logic
- No changes to telemetry selection criteria

## Acceptance Criteria

1. Exception telemetry with no `message` field still produces a non-empty message in the stored event.
2. `http_error` telemetry with no `name` field still produces a non-empty message in the stored event.
3. A batch item with a missing source IP returns 400 and the backend logs the item index and error reason without logging raw payload data.
4. All stored Azure events have `source = "azure_insights"` and `source_type = "cloud_api"`.
5. Azure events forwarded with a `cloud_RoleName` value have that value stored as `app_name`.
6. Azure events forwarded without a `cloud_RoleName` fall back to `"azure_application_insights"` for `app_name`.
7. Existing bank app `/ingest` and nginx `/ingest/web-log` endpoints are unaffected.
8. Existing live Azure DB records (11 `application_exception`, 1 `http_error`) represent the types that will continue to be produced after this change.
9. Syntax check passes on all modified files.

## Risks and Mitigations

- Risk: message fallback changes produce different stored messages for events already in the DB
  - Mitigation: this only affects future ingested events; existing records are not backfilled; the change is additive and safe

- Risk: `cloud_RoleName` lookup in the route handler introduces a new failure mode if value is unexpected type
  - Mitigation: use defensive safe-get style access; never set `app_name` to None or empty string

- Risk: adding per-item error logging in the batch handler adds noise to logs under high error volume
  - Mitigation: log at WARNING level with item index only; do not log full raw payload to avoid credential leakage
