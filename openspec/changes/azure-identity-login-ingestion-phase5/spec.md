# Azure Identity/Login Ingestion — Phase 5 Spec

## Feature Overview

This phase adds support for Azure-style authentication/login signal ingestion by extending the existing Azure ingestion path with a narrow identity adapter.

Login success and login failure events from Azure identity sources are mapped into the existing SIEM event model using `failed_login` and `successful_login` event types — the same types already used by bank app ingestion and already wired into failed login threshold, password spraying, and successful-login-after-spray detection.

No new endpoint, no new database table, no new detection rules. The existing `/ingest/azure` route, `AZURE_INGEST_API_KEY` auth, and `ingest_normalized_event` pipeline are reused.

## Current State

**What exists:**

- `POST /ingest/azure` accepts single or batched Azure telemetry, protected by `AZURE_INGEST_API_KEY`
- `adapters/azure_insights_adapter.py` normalizes `ExceptionData` and `RequestData` payloads to `application_exception`, `http_error`, and `normal_activity`
- `ingest_normalized_event` dispatches `failed_login` events through `_generate_failed_login_alerts_core` and `_generate_password_spraying_alerts_core`
- `ingest_normalized_event` dispatches `successful_login` events through `_generate_successful_login_after_spray_alerts_core`
- `_generate_password_spraying_alerts_core` extracts username from `raw_payload->>'username'` or via regex on `raw_payload->>'message'` — the `raw_payload` field in the stored event must contain a top-level `username` key for spraying detection to work
- `spray_then_success_pattern` targeted correlation fires when both `password_spraying_threshold` and `successful_login_after_spray` alerts exist for the same source IP within the window — no extra fields required beyond source IP
- `VALID_EVENT_TYPES` = `{"failed_login", "login_failure", "successful_login", "port_scan", "normal_activity"}` — both `failed_login` and `successful_login` are already supported
- `VALID_EVENT_SOURCES` = `{"bank_app", "nginx", "azure_insights", "opentelemetry"}` — `"azure_insights"` already covers Azure-origin events and is used in the events search API

**What is missing:**

- No adapter or route logic handles identity/login payloads from Azure

## Requirements

### 1. Supported Azure Identity Payload Shape

The adapter accepts payloads where `baseType` is `"SignInData"` or `"SignInLog"`. No other baseType values trigger the identity path.

Supported v1 payload shape:

```json
{
  "baseType": "SignInData",
  "sourceIp": "1.2.3.4",
  "userPrincipalName": "user@example.com",
  "result": "success",
  "appDisplayName": "MyApp",
  "timestamp": "2024-10-10T12:00:00Z"
}
```

All other top-level fields are preserved in `raw_payload` but are not mapped.

Payloads with a `baseType` value that does not match `"SignInData"` or `"SignInLog"` must continue to be routed through the existing `normalize_azure_insights_telemetry` logic unchanged.

### 2. Field Mapping

#### Source IP

Checked in this priority order:
1. `sourceIp`
2. `source_ip`
3. `client_IP`
4. `clientIp`

All values must be validated as a parseable IP address. If no valid IP is found after all lookups, raise `ValueError("Missing valid source/client IP")`. The route returns `400` for the entire batch.

#### Username

Checked in this priority order:
1. `userPrincipalName`
2. `username`
3. `upn`

If no username value is found, raise `ValueError("Missing username")`. The route returns `400` for the entire batch.

Username must be stored as a top-level `username` key in `raw_payload`. This is required for `_generate_password_spraying_alerts_core` to extract it correctly from the database.

#### Event Type and Severity

Determined by the `result` or `resultType` field:

| Result value | `event_type` | `severity` |
|---|---|---|
| `"success"` or `"0"` | `successful_login` | `low` |
| `"failure"` or any non-zero numeric string | `failed_login` | `medium` |
| absent or unrecognized | raise `ValueError("Missing or unrecognized login result")` |

`result` is checked before `resultType`. Both are checked as case-insensitive strings after stripping whitespace.

#### Message

Checked in this priority order:
1. Top-level `message`
2. Top-level `resultDescription`

If both are absent, use type-specific fallback:
- `failed_login`: `"Azure login failure for {username} from {source_ip}"`
- `successful_login`: `"Azure login success for {username} from {source_ip}"`

Final message must never be null or empty.

#### Event Timestamp

Checked in this priority order:
1. `timestamp`
2. `time`
3. `createdDateTime`

If none are present, `event_timestamp` is `null`.

#### Fixed fields (set by route handler)

| Field | Value |
|---|---|
| `source` | `"azure_insights"` |
| `source_type` | `"cloud_api"` |
| `app_name` | payload `appDisplayName` → payload `app_name` → `"azure_identity"` |
| `environment` | payload `environment` → `"prod"` |
| `raw_payload` | entire incoming payload dict, with `username` guaranteed at top level |

### 3. Validation Behavior

- Payload must be a non-empty dict. Batches follow the existing `/ingest/azure` behavior (max 25, no partial success).
- Missing or invalid source IP is a hard failure — returns `400` for the entire batch.
- Missing username is a hard failure — returns `400` for the entire batch.
- Missing or unrecognized `result`/`resultType` is a hard failure — returns `400` for the entire batch.
- Missing message is not a failure — type-specific fallback strings are used.
- Missing timestamp is not a failure — stored as `null`.

### 4. Authentication

- Preserve existing Azure ingest API-key protection behavior exactly.
- Do not weaken authentication.
- Do not create a new auth scheme or a new API key.
- The endpoint continues to use `AZURE_INGEST_API_KEY` via the `X-API-Key` header.

### 5. Ingestion Behavior

- Reuse `POST /ingest/azure`. No new endpoint is created.
- The route handler detects identity payloads by checking `baseType` before calling the existing adapter. If `baseType` matches `"SignInData"` or `"SignInLog"`, it calls the new identity normalizer. Otherwise, it calls the existing `normalize_azure_insights_telemetry`.
- The normalized event is passed to `ingest_normalized_event` — the same function used by all other ingest paths.
- No changes to `VALID_EVENT_SOURCES` are required — identity events use `source = "azure_insights"`, which is already valid.
- No new database tables or columns are created.
- A single database transaction covers the entire batch, same as current behavior.

### 6. Detection and Correlation Compatibility

**Failed login detection:**
- `failed_login` events from Azure identity are counted by `_generate_failed_login_alerts_core`, which queries `event_type IN ('failed_login', 'login_failure', 'unauthorized_access')`. No change needed.

**Password spraying detection:**
- `_generate_password_spraying_alerts_core` queries `event_type = 'failed_login'` and extracts username from `raw_payload->>'username'`. Azure identity `failed_login` events must include `username` at the top level of `raw_payload` for this to work. This is a hard requirement — see Section 2 field mapping.

**Successful login after spray:**
- `_generate_successful_login_after_spray_alerts_core` queries `event_type = 'successful_login'` and correlates by `source_ip`. Azure identity `successful_login` events will participate automatically.

**spray_then_success_pattern targeted correlation:**
- Fires when both `password_spraying_threshold` and `successful_login_after_spray` alerts exist for the same source IP. Azure identity events will trigger this pattern if the volume and timing thresholds are met. No new detectors or correlation rules are needed.

**No new detectors are created in this phase.**

### 7. Verification

**Test a failed login payload:**

```bash
curl -X POST https://<siem-host>/ingest/azure \
  -H "X-API-Key: <AZURE_INGEST_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "baseType": "SignInData",
    "sourceIp": "1.2.3.4",
    "userPrincipalName": "attacker@example.com",
    "result": "failure",
    "appDisplayName": "MyApp"
  }'
```

Expected: `201` response.

**Test a successful login payload:**

```bash
curl -X POST https://<siem-host>/ingest/azure \
  -H "X-API-Key: <AZURE_INGEST_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "baseType": "SignInData",
    "sourceIp": "1.2.3.4",
    "userPrincipalName": "attacker@example.com",
    "result": "success",
    "appDisplayName": "MyApp"
  }'
```

Expected: `201` response.

**Verify events were inserted:**

```sql
SELECT created_at, source_ip, event_type, source, source_type, app_name, raw_payload->>'username' AS username
FROM events
WHERE source = 'azure_insights'
  AND source_type = 'cloud_api'
  AND event_type IN ('failed_login', 'successful_login')
ORDER BY created_at DESC
LIMIT 10;
```

Expected:
- `source = 'azure_insights'`
- `source_type = 'cloud_api'`
- `event_type` is `failed_login` or `successful_login`
- `app_name` reflects the identity app (e.g., `"MyApp"` or `"azure_identity"` fallback)
- `username` column is non-null

**Verify existing correlation can use them:**

Submit enough `failed_login` events from the same source IP targeting distinct usernames to cross the `password_spraying_threshold`. Then submit a `successful_login` from the same IP. Query:

```sql
SELECT created_at, alert_type, source_ip, source
FROM alerts
WHERE source_ip = '1.2.3.4'
ORDER BY created_at DESC
LIMIT 10;
```

Expected: `password_spraying_threshold` and `successful_login_after_spray` alerts, and potentially a `spray_then_success_pattern` targeted correlation alert.

## Scope

**New file to be created:**

- None. The identity normalizer is added to the existing `adapters/azure_insights_adapter.py` as a new function `normalize_azure_identity_telemetry`.

**Existing files to be modified:**

- `adapters/azure_insights_adapter.py` — add `normalize_azure_identity_telemetry(telemetry)` function
- `siem_backend.py` — update the `/ingest/azure` route handler to detect identity payloads and dispatch to the new function

**Explicit boundaries:**

- Do not modify `/ingest`, `/ingest/web-log`, or `/ingest/otlp`
- Do not modify `normalize_azure_insights_telemetry` — the new function is additive
- Do not modify `adapters/nginx_adapter.py` or `adapters/otel_adapter.py`
- Do not modify any frontend file
- Do not add new endpoints
- Do not add new database tables or columns
- Do not add new libraries

## Non-Goals

- No frontend or UI changes
- No schema changes
- No new database tables
- No new libraries
- No new ingest endpoints
- No new detection rules or detectors
- No full Azure AD or Entra ID clone
- No broad identity analytics
- No MFA or risk-based sign-in handling
- No conditional access policy modeling
- No Graph API integration
- No new Azure services
- No OpenTelemetry changes
- No file ingestion changes
- No rewrite of existing ingestion endpoint structure

## Acceptance Criteria

1. A `SignInData` payload with `result = "failure"` is stored as `event_type = 'failed_login'` with `source = 'azure_insights'` and `source_type = 'cloud_api'`.
2. A `SignInData` payload with `result = "success"` is stored as `event_type = 'successful_login'` with `source = 'azure_insights'` and `source_type = 'cloud_api'`.
3. The stored event's `raw_payload` contains a top-level `username` key with the extracted username value.
4. A payload missing `userPrincipalName`, `username`, and `upn` returns `400`.
5. A payload missing or with an unrecognized `result` and `resultType` returns `400`.
6. A payload missing or with an invalid source IP returns `400`.
7. Non-identity Azure payloads (`ExceptionData`, `RequestData`) continue to be handled by the existing adapter without change.
8. Azure identity `failed_login` events are counted by the existing `failed_login_threshold` and `password_spraying_threshold` detection rules.
9. Azure identity `successful_login` events are correlated by the existing `successful_login_after_spray` rule.
10. The `spray_then_success_pattern` targeted correlation fires when the appropriate alert preconditions are met using only Azure identity events.
11. Identity events are queryable via the events search API using `source = 'azure_insights'`; `app_name` identifies the specific identity app or service.
12. No changes are made to `/ingest`, `/ingest/web-log`, `/ingest/otlp`, or any frontend file.
13. Syntax check passes on all modified files.

## Risks and Mitigations

- Risk: missing `username` in `raw_payload` silently breaks password spraying detection
  - Mitigation: failing to extract a username is a hard validation error — the adapter raises `ValueError` before the event is stored; a missing username cannot reach the database

- Risk: identity payloads with a `baseType` that partially matches (e.g., a future `"SignInDataV2"`) fall through to the existing adapter and raise `ValueError`
  - Mitigation: the spec keeps the supported baseType values narrow (`"SignInData"` and `"SignInLog"` only); unknown identity variants return `400` rather than being silently misclassified

- Risk: result field values from real Azure sign-in logs differ from the spec (`"0"` vs `"success"`, non-zero vs `"failure"`)
  - Mitigation: both string forms are checked; the adapter must handle `"0"` (success) and any non-zero numeric string (failure) as well as the word forms; unknown values hard-fail with `400`

- Risk: existing bank app `failed_login` events and new Azure identity `failed_login` events are counted together by detection rules
  - Mitigation: this is intentional and correct — detection rules are source-agnostic on purpose; the `source` field in the stored alert preserves the origin for investigation
