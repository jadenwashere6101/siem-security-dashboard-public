# Azure Integration Setup

## Overview

This guide documents the plug-and-play setup for Azure Application Insights ingestion into the SIEM.

No application logic is changed in this phase.

## 1. Required Azure Function Settings

The Azure Function App must have these Application Settings:

| Variable | Required | Format | Description |
|---|---|---|---|
| `LOG_ANALYTICS_WORKSPACE_ID` | Yes | UUID string | Azure Log Analytics workspace ID to query |
| `SIEM_AZURE_INGEST_URL` | Yes | HTTPS URL ending in `/ingest/azure` | Full URL of the SIEM backend Azure ingest endpoint |
| `AZURE_INGEST_API_KEY` | Yes | Arbitrary secret string | API key sent to the SIEM backend as `X-API-Key` header |
| `FUNCTIONS_WORKER_RUNTIME` | Yes | `python` | Azure runtime setting |
| `AzureWebJobsStorage` | Yes | Azure storage connection string | Required by Azure Functions runtime |

### Naming Rules

- Use `AZURE_INGEST_API_KEY` exactly
- Do not use `SIEM_AZURE_INGEST_API_KEY`
- `SIEM_AZURE_INGEST_URL` must include the full path and end with `/ingest/azure`
- Do not add a trailing slash to `SIEM_AZURE_INGEST_URL`

## 2. Required SIEM Backend Environment Variables

### Required for Azure ingestion

| Variable | Required | Notes |
|---|---|---|
| `AZURE_INGEST_API_KEY` | Yes | Must be identical to the value set in the Azure Function App |

### Runtime prerequisites

| Variable | Preferred Name | Accepted Alias |
|---|---|---|
| Database name | `SIEM_DB_NAME` | `DB_NAME` |
| Database user | `SIEM_DB_USER` | `DB_USER` |
| Database host | `SIEM_DB_HOST` | `DB_HOST` |
| Database password | `SIEM_DB_PASSWORD` | `DB_PASSWORD` |

### Naming Rules

- `AZURE_INGEST_API_KEY` has no alias
- `SIEM_INGEST_API_KEY` is for bank app ingestion only
- `OTEL_INGEST_API_KEY` is for OpenTelemetry ingestion only

The value of `AZURE_INGEST_API_KEY` must be identical on both sides.

## 3. End-to-End Data Flow

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

### Failure Points

| Stage | What can fail |
|---|---|
| Azure Function startup | Required env var missing |
| Log Analytics query | Wrong workspace ID or missing workspace permission |
| IP filtering | All rows have no valid `client_IP` |
| Forwarding to backend | Wrong URL or network unreachable |
| Backend auth | `AZURE_INGEST_API_KEY` mismatch |
| Backend normalization | Unsupported telemetry type |
| Database insert | DB connection failure |

## 4. Setup Checklist

Complete these steps in order.

### Prerequisites

- Azure subscription with Application Insights deployed
- Application Insights connected to a Log Analytics workspace
- SIEM backend reachable over HTTPS

### Step 1 — Get the Log Analytics Workspace ID

- Azure Portal -> Log Analytics workspace -> Overview
- Copy the Workspace ID

### Step 2 — Choose an API key value

- Generate a random secret string
- This exact value must be used on both sides

### Step 3 — Set the SIEM backend env var

Add to the backend `.env` file:

```text
AZURE_INGEST_API_KEY=<your chosen key>
```

Restart the backend:

```bash
sudo systemctl restart siem-backend.service
```

### Step 4 — Set Azure Function App settings

Azure Portal -> Function App -> Settings -> Environment variables -> Application settings

Set:

```text
LOG_ANALYTICS_WORKSPACE_ID = <workspace UUID>
SIEM_AZURE_INGEST_URL      = https://<your-siem-host>/ingest/azure
AZURE_INGEST_API_KEY       = <same key from Step 2>
```

### Step 5 — Restart the Azure Function App

- Azure Portal -> Function App -> Overview -> Restart

### Step 6 — Verify the timer function is active

- Azure Portal -> Function App -> Functions -> `poll_application_insights` -> Monitor
- Confirm recent invocations appear

### Step 7 — Verify events are reaching the SIEM DB

```sql
SELECT created_at, source_ip, event_type, source
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 10;
```

If empty after 10 minutes, inspect invocation logs for `forwarded=0` or failures.

## 5. Verification Process

### Azure Function side

1. Azure Portal -> Function App -> Functions -> `poll_application_insights` -> Monitor
2. Open a recent successful invocation
3. Look for a line like:

```text
Application Insights polling complete: returned=N forwarded=N skipped_invalid_ip=N failures=0 ...
```

Interpretation:

- `forwarded > 0` confirms events are being sent to the SIEM
- `failures > 0` means the backend is rejecting requests or is unreachable
- `skipped_invalid_ip > 0` means matching rows had no usable client IP
- `unmapped_telemetry > 0` means returned rows were outside supported types

### SIEM Database side

```sql
SELECT created_at, source_ip, event_type, source, source_type
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 25;
```

Expected on every row:

- `source = 'azure_insights'`
- `source_type = 'cloud_api'`

```sql
SELECT created_at, alert_type, severity, source
FROM alerts
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 10;
```

### SIEM UI side

- Log in to the dashboard
- Navigate to Alerts or Events
- Filter by source: `azure_insights`

### Minimum observable outcome

- At least one Azure invocation with `forwarded >= 1`
- At least one row in `events` with `source = 'azure_insights'`

### Optional troubleshooting — endpoint reachability

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST https://<your-siem-host>/ingest/azure \
  -H "X-API-Key: wrongkey" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected: `401`

## 6. Common Failure Modes

### Missing environment variable in Azure Function

- Symptom: function fails to run correctly or no events appear in the SIEM DB
- Cause: one of `LOG_ANALYTICS_WORKSPACE_ID`, `SIEM_AZURE_INGEST_URL`, or `AZURE_INGEST_API_KEY` is missing
- Verify: Azure Portal -> Function App -> Environment variables

### Wrong API key

- Symptom: invocations run but `failures > 0`
- Cause: Azure Function App key does not match backend `.env`
- Verify: confirm both `AZURE_INGEST_API_KEY` values are identical

### Wrong endpoint URL

- Symptom: invocation failures or connection errors
- Cause: `SIEM_AZURE_INGEST_URL` is incorrect
- Verify: confirm it ends with `/ingest/azure` exactly

### Forwarded = 0, no failures

- Symptom: invocations succeed but no new SIEM rows appear
- Cause: all returned rows were skipped because `client_IP` was missing or invalid
- Verify: run the KQL query manually and inspect `client_IP`

### Forwarded = 0, returned = 0

- Symptom: invocations succeed but no rows are processed
- Cause: no matching telemetry exists in the last 5 minutes
- Verify: confirm Application Insights is connected to the correct Log Analytics workspace and the monitored app is generating exceptions or error requests

### Backend rejecting requests with 400

- Symptom: invocation failures and no new Azure DB rows
- Cause: unsupported telemetry payload structure or missing required fields
- Verify: check SIEM backend logs for `/ingest/azure` errors

### Backend returning 500

- Symptom: invocation failures and no new Azure DB rows
- Cause: backend internal error, usually DB-related
- Verify: check backend service logs and DB connectivity
