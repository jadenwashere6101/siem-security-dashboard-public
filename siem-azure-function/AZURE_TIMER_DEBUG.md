# Azure Timer Debug Guide

## Runtime Debug Guide

For initial setup and demo flow, see `docs/azure-integration-setup.md`.

## Current Working Architecture

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

## Required Backend Setting

```text
AZURE_INGEST_API_KEY=<SHARED_AZURE_INGEST_KEY>
```

This value must match the Azure Function setting exactly.

## Demo Steps

### 1. Trigger a trace

```bash
curl "https://<FUNCTION_APP_HOST>/api/test_endpoint?code=<FUNCTION_KEY>"
```

### 2. Wait for the timer

- `poll_application_insights` runs every 5 minutes

### 3. Check timer logs

Look for:

```text
Application Insights polling complete: returned=N forwarded=N skipped_invalid_ip=N failures=0 ...
```

Success means:

- `returned > 0`
- `forwarded > 0`

### 4. Verify in Azure Portal

- Function App -> Functions -> `poll_application_insights` -> Monitor
- Function App -> Settings -> Environment variables
- Confirm the required settings are present before debugging code

## Verification Query

Run against the SIEM VM database:

```sql
SELECT created_at, source_ip, event_type, source, source_type, message
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 5;
```

## Troubleshooting

### `returned=0`

- No matching telemetry was found in the time window

### `skipped_invalid_ip > 0`

- No usable IP was extracted from the trace or telemetry row

### `failures > 0`

- The SIEM rejected the payload or the backend was unreachable

### `401` from `test_endpoint`

- The function key was missing or invalid

### `400` from `/ingest/azure`

- The backend Azure adapter rejected the forwarded payload

## Demo Talking Points

- This demonstrates a real Azure-to-SIEM ingestion path.
- The Azure Function extracts the real client IP from trace logs.
- Forwarded rows enter the same SIEM normalization pipeline as other sources.
- No new database schema was required.

## See Also

- Setup and demo flow: `docs/azure-integration-setup.md`
