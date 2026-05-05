# Azure Plug-and-Play Setup — Phase 2 Spec

## Feature Overview

This phase makes Azure Application Insights integration deterministic to configure, verify, and debug.

No application logic is changed. The deliverable is documentation that eliminates ambiguity in environment variable naming, documents the end-to-end data flow, and defines a minimal setup checklist and verification process.

---

## Documentation Scope

This phase produces documentation only. No application code is modified.

**Allowed files to create or update:**

- `siem-azure-function/AZURE_TIMER_DEBUG.md` — update with setup, env var reference, and verification steps
- `docs/azure-integration-setup.md` — primary integration guide (create if not present)
- `README.md` — short pointer or link to `docs/azure-integration-setup.md` only, if needed

**Forbidden files (must not be modified):**

- `siem_backend.py`
- `adapters/azure_insights_adapter.py`
- `siem-azure-function/function_app.py`
- Any frontend file

---

## 1. Required Azure Function Settings

The Azure Function expects these values to be present in its Application Settings. All three application-level variables below are required for Azure ingestion to function.

| Variable | Required | Format | Description |
|---|---|---|---|
| `LOG_ANALYTICS_WORKSPACE_ID` | Yes | UUID string | Azure Log Analytics workspace ID to query |
| `SIEM_AZURE_INGEST_URL` | Yes | HTTPS URL ending in `/ingest/azure` | Full URL of the SIEM backend Azure ingest endpoint |
| `AZURE_INGEST_API_KEY` | Yes | Arbitrary secret string | API key sent to the SIEM backend as `X-API-Key` header |
| `FUNCTIONS_WORKER_RUNTIME` | Yes | `python` | Azure runtime setting — must be `python` |
| `AzureWebJobsStorage` | Yes | Azure storage connection string | Required by Azure Functions runtime |

**Naming rules:**

- Use `AZURE_INGEST_API_KEY` exactly. Do not use `SIEM_AZURE_INGEST_API_KEY` — that name is not read by the current function code.
- `SIEM_AZURE_INGEST_URL` must include the full path. Example value format: `https://<host>/ingest/azure`
- Do not add a trailing slash to `SIEM_AZURE_INGEST_URL`.

---

## 2. Required SIEM Backend Environment Variables

These variables must be set in the SIEM backend `.env` file (loaded via systemd `EnvironmentFile`).

### Required for Azure ingestion

| Variable | Required | Notes |
|---|---|---|
| `AZURE_INGEST_API_KEY` | Yes | Must be identical to the value set in the Azure Function App |

### Runtime prerequisites (backend must be operational for ingestion to reach the DB)

| Variable | Preferred Name | Accepted Alias |
|---|---|---|
| Database name | `SIEM_DB_NAME` | `DB_NAME` |
| Database user | `SIEM_DB_USER` | `DB_USER` |
| Database host | `SIEM_DB_HOST` | `DB_HOST` |
| Database password | `SIEM_DB_PASSWORD` | `DB_PASSWORD` |

**Naming rules:**

- `AZURE_INGEST_API_KEY` has no alias. It must match exactly between the backend `.env` and the Azure Function App configuration.
- `SIEM_INGEST_API_KEY` is for bank app ingestion only — do not confuse it with `AZURE_INGEST_API_KEY`.
- `OTEL_INGEST_API_KEY` is for OpenTelemetry ingestion only — unrelated to Azure.

**The value of `AZURE_INGEST_API_KEY` must be identical on both sides.** A mismatch causes the backend to reject all Azure Function requests with `401`.

---

## 3. End-to-End Data Flow

```
[Azure Application Insights]
        |
        | telemetry collected from monitored app
        v
[Azure Log Analytics Workspace]
        |
        | queried by timer function every 5 minutes
        | using LOG_ANALYTICS_WORKSPACE_ID
        v
[Azure Function: poll_application_insights]
        |
        | KQL query fetches up to 25 rows:
        |   - exceptions (any)
        |   - requests with resultCode 401, 403, or >= 500
        |   - only rows where client_IP is non-empty and non-zero
        |
        | each row is classified → mapped to SIEM telemetry format
        | rows without valid client_IP are skipped (logged as skipped_invalid_ip)
        | unmapped item types are skipped (logged as unmapped_telemetry)
        |
        | POST to SIEM_AZURE_INGEST_URL
        | with header: X-API-Key: AZURE_INGEST_API_KEY
        v
[SIEM Backend: POST /ingest/azure]
        |
        | validates X-API-Key against AZURE_INGEST_API_KEY
        | parses payload (single object or batch up to 25)
        | normalizes each item via azure_insights_adapter
        |   - extracts source_ip from known IP field variants
        |   - derives event_type from baseType/telemetryType
        |   - produces non-empty message string
        |   - sets source = "azure_insights", source_type = "cloud_api"
        |
        | inserts event into events table
        | runs detection rules
        | generates alerts if thresholds are met
        v
[SIEM Database: events + alerts tables]
        |
        | source = 'azure_insights' on all Azure-origin rows
        v
[SIEM UI: dashboard + alerts view]
```

**Failure points:**

| Stage | What can fail |
|---|---|
| Azure Function startup | Any of the three required env vars missing → function will not operate correctly |
| Log Analytics query | Wrong `LOG_ANALYTICS_WORKSPACE_ID` or missing workspace permission → empty result or query error |
| IP filtering | All returned rows have no valid `client_IP` → `forwarded = 0`, no error raised |
| Forwarding to backend | Wrong `SIEM_AZURE_INGEST_URL` or network unreachable → HTTP error, logged as failure |
| Backend auth | `AZURE_INGEST_API_KEY` mismatch → backend returns `401`, function logs failure |
| Backend normalization | Unsupported telemetry type → backend returns `400` |
| Database insert | DB connection failure → backend returns `500` |

---

## 4. Setup Checklist (Plug-and-Play)

Complete these steps in order. Each step has a single verifiable outcome.

**Prerequisites:**
- Azure subscription with Application Insights resource deployed
- Application Insights connected to a Log Analytics workspace
- SIEM backend reachable over HTTPS on the VM

---

**Step 1 — Get your Log Analytics Workspace ID**

- In Azure Portal: go to Log Analytics workspace → Overview → copy Workspace ID (UUID format)

**Step 2 — Choose an API key value**

- Generate a random secret string (e.g., 32+ character alphanumeric)
- This exact value will be used on both sides

**Step 3 — Set the SIEM backend env var**

- Add to the SIEM backend `.env` file on the VM:
  ```
  AZURE_INGEST_API_KEY=<your chosen key>
  ```
- Restart the backend service:
  ```
  sudo systemctl restart siem-backend.service
  ```

**Step 4 — Set Azure Function App settings**

- In Azure Portal: Function App → Settings → Environment variables → Application settings
- Add or update all three:
  ```
  LOG_ANALYTICS_WORKSPACE_ID = <workspace UUID from Step 1>
  SIEM_AZURE_INGEST_URL      = https://<your-siem-host>/ingest/azure
  AZURE_INGEST_API_KEY       = <same key from Step 2>
  ```
- Save and apply

**Step 5 — Restart the Azure Function App**

- In Azure Portal: Function App → Overview → Restart
- Wait for the function to come back online

**Step 6 — Verify the timer function is active**

- In Azure Portal: Function App → Functions → `poll_application_insights` → Monitor
- Confirm recent invocations appear (runs every 5 minutes)

**Step 7 — Verify events are reaching the SIEM DB**

- Query the SIEM database:
  ```sql
  SELECT created_at, source_ip, event_type, source
  FROM events
  WHERE source = 'azure_insights'
  ORDER BY created_at DESC
  LIMIT 10;
  ```
- If empty after 10 minutes, check invocation logs for `forwarded=0` or failures

---

## 5. Verification Process

After setup, use these checks to confirm Azure ingestion is working.

### Azure Function side

**Check invocation logs (primary verification):**

1. Azure Portal → Function App → Functions → `poll_application_insights` → Monitor
2. Open a recent successful invocation
3. Look for this log line:
   ```
   Application Insights polling complete: returned=N forwarded=N skipped_invalid_ip=N failures=0 ...
   ```
4. `forwarded > 0` confirms events are being sent to the SIEM
5. `failures > 0` indicates the SIEM backend is rejecting requests

**Check for skipped rows:**

- `skipped_invalid_ip > 0` means rows exist in Log Analytics but have no valid `client_IP` — expected behavior, not an error
- `unmapped_telemetry > 0` means row types are not supported — expected if query scope is narrow

### SIEM Database side

```sql
-- Confirm events are arriving
SELECT created_at, source_ip, event_type, source, source_type
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 25;
```

Expected values on every row:
- `source` = `azure_insights`
- `source_type` = `cloud_api`
- `event_type` is one of: `application_exception`, `http_error`, `normal_activity`, `availability_failure`

```sql
-- Confirm alerts are being generated
SELECT created_at, alert_type, severity, source
FROM alerts
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 10;
```

### SIEM UI side

- Log in to the dashboard
- Navigate to the Alerts or Events view
- Filter by source: `azure_insights`
- If events exist in the DB, they will appear here

**Minimum observable outcome for a working setup:**
- At least one invocation in Azure Portal with `forwarded >= 1`
- At least one row in `events` with `source = 'azure_insights'`

### Optional troubleshooting — endpoint reachability check

If invocations are failing and you need to confirm the backend endpoint is reachable before the Azure Function can reach it, use:

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST https://<your-siem-host>/ingest/azure \
  -H "X-API-Key: wrongkey" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected: `401` — confirms the endpoint exists and API key auth is active. This step is not required for a standard setup.

---

## 6. Common Failure Modes

### Missing environment variable in Azure Function

- **Symptom**: Function App fails to run or invocations show startup errors; no events in SIEM DB
- **Cause**: One of `LOG_ANALYTICS_WORKSPACE_ID`, `SIEM_AZURE_INGEST_URL`, or `AZURE_INGEST_API_KEY` is not set in Application Settings
- **Verify**: Azure Portal → Function App → Settings → Environment variables — confirm all three are present with non-empty values

---

### Wrong API key (key mismatch)

- **Symptom**: Invocations run but `failures > 0`; SIEM DB has no new Azure events
- **Cause**: `AZURE_INGEST_API_KEY` in Azure Function App does not match `AZURE_INGEST_API_KEY` in the SIEM backend `.env`
- **Verify**: Confirm both values are identical; restart backend after any `.env` change

---

### Wrong endpoint URL

- **Symptom**: Invocations show HTTP errors or connection errors; `failures > 0`
- **Cause**: `SIEM_AZURE_INGEST_URL` is incorrect (wrong host, wrong path, missing `/ingest/azure`, trailing slash)
- **Verify**: Confirm the URL ends with `/ingest/azure` exactly; use the optional curl check in Section 5 if needed

---

### Azure Function not forwarding (forwarded = 0, no failures)

- **Symptom**: Invocations succeed but `forwarded = 0`; `skipped_invalid_ip` may be high
- **Cause**: All rows returned from Log Analytics have missing or invalid `client_IP` values
- **Verify**: Run the KQL query manually in Log Analytics to check if `client_IP` is populated; expected if the monitored app does not emit client IP in its telemetry

---

### Azure Function not forwarding (forwarded = 0, returned = 0)

- **Symptom**: Invocations succeed but `returned = 0`
- **Cause**: No telemetry matching the query exists in the Log Analytics workspace for the last 5 minutes
- **Verify**: Confirm Application Insights is connected to the correct Log Analytics workspace; confirm the monitored app is generating exceptions or error requests

---

### Backend rejecting requests with 400

- **Symptom**: `failures > 0` in function invocation logs; DB still has no new Azure events
- **Cause**: Telemetry payload structure is not recognized by the backend adapter (unsupported `baseType` or missing required fields)
- **Verify**: Check SIEM backend logs for the specific error returned by `/ingest/azure`

---

### Backend returning 500

- **Symptom**: `failures > 0`; SIEM DB unchanged
- **Cause**: Backend internal error — most likely a database connection failure
- **Verify**: Check SIEM backend service logs; confirm DB is running and `.env` DB variables are correct

---

## Non-Goals

- No application logic changes
- Documentation-only repo changes are allowed
- No Azure Function logic changes
- No new endpoints
- No schema changes
- No UI changes
- No OpenTelemetry work
- No Azure identity or login ingestion
- No file ingestion
- No changes to Azure polling or query logic
- No changes to telemetry selection criteria
- No new Azure services

---

## Acceptance Criteria

1. A developer can complete the setup checklist without needing to read source code.
2. Environment variable names in the spec match exactly what the code reads — no aliases or guesswork.
3. `AZURE_INGEST_API_KEY` is unambiguously identified as the one value that must match on both sides.
4. The data flow section identifies every failure point between Azure and the SIEM DB.
5. The verification process produces a clear pass/fail result using Azure Portal and a single SQL query without requiring curl.
6. Each failure mode has a symptom, cause, and verification step.
7. No application logic, ingestion behavior, or architecture is changed.
