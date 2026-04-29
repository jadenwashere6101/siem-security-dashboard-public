# Azure Timer Debug Guide

This guide is the Azure Function-side reference for setup verification and troubleshooting.

For the full plug-and-play setup flow, use:
- `docs/azure-integration-setup.md`

## Required Azure Function Settings

| Variable | Required | Format | Description |
|---|---|---|---|
| `LOG_ANALYTICS_WORKSPACE_ID` | Yes | UUID string | Azure Log Analytics workspace ID to query |
| `SIEM_AZURE_INGEST_URL` | Yes | HTTPS URL ending in `/ingest/azure` | Full URL of the SIEM backend Azure ingest endpoint |
| `AZURE_INGEST_API_KEY` | Yes | Arbitrary secret string | API key sent to the SIEM backend as `X-API-Key` header |
| `FUNCTIONS_WORKER_RUNTIME` | Yes | `python` | Azure runtime setting |
| `AzureWebJobsStorage` | Yes | Azure storage connection string | Required by Azure Functions runtime |

## Naming Rules

- Use `AZURE_INGEST_API_KEY` exactly
- Do not use `SIEM_AZURE_INGEST_API_KEY`
- `SIEM_AZURE_INGEST_URL` must include the full path and end with `/ingest/azure`
- Do not add a trailing slash to `SIEM_AZURE_INGEST_URL`

## What This Timer Does

- Runs every 5 minutes
- Queries Log Analytics for the last 5 minutes
- Caps results at 25 records
- Forwards only:
  - exceptions
  - requests with `401` / `403`
  - requests with `>= 500`

## Important IP Behavior

Rows with these `client_IP` values are skipped intentionally:

- missing
- blank
- `0.0.0.0`

This is expected behavior. The SIEM backend keeps strict IP validation and does not accept fake or placeholder IPs.

## End-to-End Data Flow

```text
Azure Application Insights
  -> Azure Log Analytics Workspace
  -> poll_application_insights timer function
  -> POST SIEM_AZURE_INGEST_URL with X-API-Key: AZURE_INGEST_API_KEY
  -> SIEM /ingest/azure
  -> events table
  -> alerts table
  -> SIEM UI
```

## Verification

### Check Azure Function Invocations

Use Azure Portal:

1. Open the Function App
2. Open `Functions`
3. Open `poll_application_insights`
4. Review `Monitor` and recent runs

Look for a log line like:

```text
Application Insights polling complete: returned=N forwarded=N skipped_invalid_ip=N failures=0 ...
```

Interpretation:

- `forwarded > 0` means events were sent to the SIEM
- `failures > 0` means the SIEM rejected requests or was unreachable
- `skipped_invalid_ip > 0` means matching rows had no usable client IP
- `returned = 0` means no matching telemetry was found in the last 5 minutes

### Manual KQL Queries

#### Requests

```kusto
requests
| where timestamp >= ago(5m)
| where toint(resultCode) in (401, 403) or toint(resultCode) >= 500
| project timestamp, operation_Name, name, resultCode, client_IP
| order by timestamp asc
| take 25
```

#### Exceptions

```kusto
exceptions
| where timestamp >= ago(5m)
| project timestamp, operation_Name, message, client_IP
| order by timestamp asc
| take 25
```

#### Combined View Matching Timer Scope

```kusto
union isfuzzy=true
(
    exceptions
    | where timestamp >= ago(5m)
    | project itemType = "exception", timestamp, operation_Name, message, client_IP, resultCode = ""
),
(
    requests
    | where timestamp >= ago(5m)
    | where toint(resultCode) in (401, 403) or toint(resultCode) >= 500
    | project itemType = "request", timestamp, operation_Name, message = name, client_IP, resultCode
)
| where isnotempty(client_IP)
| order by timestamp asc
| take 25
```

### Verify Forwarded Events in SIEM

```sql
SELECT created_at, source_ip, event_type, source, source_type
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 25;
```

Expected values:

- `source = 'azure_insights'`
- `source_type = 'cloud_api'`

### Optional Endpoint Reachability Check

If you need to confirm the backend endpoint exists before the Azure Function can reach it:

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST https://<your-siem-host>/ingest/azure \
  -H "X-API-Key: wrongkey" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected: `401`

## Common Failure Modes

### Missing environment variable in Azure Function

- Symptom: function does not run correctly or no events appear in the SIEM DB
- Cause: one of `LOG_ANALYTICS_WORKSPACE_ID`, `SIEM_AZURE_INGEST_URL`, or `AZURE_INGEST_API_KEY` is missing
- Verify: Azure Portal -> Function App -> Environment variables

### Wrong API key

- Symptom: invocations run but `failures > 0`
- Cause: `AZURE_INGEST_API_KEY` does not match the backend `.env`
- Verify: confirm both values are identical

### Wrong endpoint URL

- Symptom: invocation failures or connection errors
- Cause: `SIEM_AZURE_INGEST_URL` is wrong
- Verify: confirm it ends with `/ingest/azure` exactly

### Forwarded = 0, no failures

- Symptom: invocations succeed but nothing reaches the SIEM
- Cause: all matching rows were skipped for invalid or missing `client_IP`
- Verify: run the KQL query manually and inspect `client_IP`

### Returned = 0

- Symptom: invocations succeed but no rows are processed
- Cause: no matching telemetry exists in the last 5 minutes
- Verify: confirm Application Insights is connected to the correct Log Analytics workspace and the monitored app is emitting exceptions or error requests

### Backend returns 400

- Symptom: invocation failures with no new DB rows
- Cause: unsupported telemetry payload shape or missing required fields
- Verify: check SIEM backend logs for `/ingest/azure` errors

### Backend returns 500

- Symptom: invocation failures with no new DB rows
- Cause: backend internal error, usually database-related
- Verify: check SIEM backend service logs and DB connectivity

## v1 Duplicate Behavior

- 5-minute query window
- max 25 records
- no persisted watermark yet

Duplicate forwarding is still possible across overlapping runs or retries. That is an accepted v1 limitation.
