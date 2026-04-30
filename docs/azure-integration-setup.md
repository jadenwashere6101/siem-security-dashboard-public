# Azure Integration Setup

## Setup & Demo Guide

## Overview

For runtime debugging, see `siem-azure-function/AZURE_TIMER_DEBUG.md`.

This is the current working Azure -> SIEM demo path.

```text
Azure Function test_endpoint
  -> Application Insights traces
  -> poll_application_insights timer
  -> SIEM /ingest/azure
  -> events table
  -> dashboard
```

## Required Azure Function Settings

| Variable | Required | Notes |
|---|---|---|
| `LOG_ANALYTICS_WORKSPACE_ID` | Yes | Log Analytics workspace queried by the timer |
| `SIEM_AZURE_INGEST_URL` | Yes | Full backend URL ending in `/ingest/azure` |
| `AZURE_INGEST_API_KEY` | Yes | Must match the SIEM backend value |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Yes | Sends Function logs and traces to Application Insights |
| `AzureWebJobsStorage` | Yes | Required by Azure Functions runtime |
| `FUNCTIONS_WORKER_RUNTIME` | Yes | Set to `python` |

## Required SIEM Backend Setting

| Variable | Required | Notes |
|---|---|---|
| `AZURE_INGEST_API_KEY` | Yes | Must match the Azure Function setting |

### Backend `.env` requirement

Add this to the SIEM backend environment:

```text
AZURE_INGEST_API_KEY=<SHARED_AZURE_INGEST_KEY>
```

The backend must be restarted after updating the value.

## Demo Steps

### 1. Call the Azure Function test endpoint

Use the deployed Function URL with a function key:

```bash
curl "https://<FUNCTION_APP_HOST>/api/test_endpoint?code=<FUNCTION_KEY>"
```

Expected response:

```json
{"status": "ok"}
```

### 2. Wait for the next timer run

- `poll_application_insights` runs every 5 minutes
- It queries recent Application Insights telemetry and forwards supported rows to the SIEM

### 3. Confirm Azure Function settings

Azure Portal -> Function App -> Settings -> Environment variables

Confirm:

```text
LOG_ANALYTICS_WORKSPACE_ID
SIEM_AZURE_INGEST_URL
AZURE_INGEST_API_KEY
APPLICATIONINSIGHTS_CONNECTION_STRING
AzureWebJobsStorage
FUNCTIONS_WORKER_RUNTIME=python
```

### 4. Confirm Azure logs show successful polling

Look for a line like:

```text
Application Insights polling complete: returned=N forwarded=N skipped_invalid_ip=N failures=0 ...
```

For a successful demo:

- `returned > 0`
- `forwarded > 0`

### 5. Confirm SIEM received Azure rows

```sql
SELECT created_at, source_ip, event_type, source, source_type, message
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 5;
```

Expected:

- `source = 'azure_insights'`
- `source_type = 'cloud_api'`

## Verification

### Azure Function side

Check:

- Azure Portal -> Function App -> Functions -> `poll_application_insights` -> Monitor
- Recent invocation logs for:
  - `returned`
  - `forwarded`
  - `skipped_invalid_ip`
  - `failures`

### SIEM Database side

Run on the VM database:

```sql
SELECT created_at, source_ip, event_type, source, source_type, message
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 5;
```

### SIEM UI side

- Open the dashboard
- Filter Alerts or Events by source: `azure_insights`

## Troubleshooting

### `returned=0`

- Meaning: no matching telemetry was found in the query window

### `skipped_invalid_ip > 0`

- Meaning: no usable client IP was extracted from the returned telemetry

### `failures > 0`

- Meaning: the SIEM backend rejected the payload or the endpoint was unreachable

### `401` from `test_endpoint`

- Meaning: the function key was missing or invalid

### `400` from `/ingest/azure`

- Meaning: the SIEM backend Azure adapter rejected the forwarded payload

## Demo Talking Points

- This proves real Azure telemetry can flow into the SIEM.
- Real IP is extracted from Azure trace logs.
- Azure events normalize into the same SIEM ingestion pipeline as other sources.
- No new database schema was required for the demo.

## See Also

- Runtime debugging: `siem-azure-function/AZURE_TIMER_DEBUG.md`
