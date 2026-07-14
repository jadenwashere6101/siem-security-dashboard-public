# Azure Integration Setup

## Setup & Demo Guide

## Overview

For runtime debugging, see `siem-azure-function/AZURE_TIMER_DEBUG.md`.

This is the current Azure -> SIEM polling path.

```text
Azure Application Insights / Log Analytics
  -> poll_application_insights timer
  -> SIEM /ingest/azure + /ingest/azure/checkpoint
  -> events + ingestion_checkpoints
  -> detections / Source Health / dashboard
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
| `PAGE_SIZE` | No | Per-query page size. Default `25` |
| `MAX_POLL_PAGES` | No | Max pages per timer invocation. Default `10` |
| `QUERY_RETRY_ATTEMPTS` | No | Query retry attempts. Default `3` |
| `FORWARD_RETRY_ATTEMPTS` | No | Per-row forward retry attempts. Default `3` |
| `RETRY_BACKOFF_SECONDS` | No | Base retry backoff in seconds. Default `1` |
| `HTTP_TIMEOUT_SECONDS` | No | Checkpoint/ingest HTTP timeout in seconds. Default `10` |

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

## Polling Steps

### 1. Wait for the next timer run

- `poll_application_insights` runs every 5 minutes
- It reads the last checkpoint from `/ingest/azure/checkpoint`
- It queries the checkpoint-to-now window in pages
- It forwards supported rows to the SIEM and patches the checkpoint with poll outcome/counts

### 2. Confirm Azure Function settings

Azure Portal -> Function App -> Settings -> Environment variables

Confirm:

```text
LOG_ANALYTICS_WORKSPACE_ID
SIEM_AZURE_INGEST_URL
AZURE_INGEST_API_KEY
APPLICATIONINSIGHTS_CONNECTION_STRING
AzureWebJobsStorage
FUNCTIONS_WORKER_RUNTIME=python
PAGE_SIZE
MAX_POLL_PAGES
```

### 3. Confirm Azure logs show successful polling

Look for a line like:

```text
Application Insights polling complete: status=success returned=N forwarded=N skipped_invalid_ip=N failures=0 ...
```

For a successful demo:

- `returned > 0`
- `forwarded > 0`

### 4. Confirm SIEM received Azure rows

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

Checkpoint state:

```sql
SELECT connector_name, last_processed_at, last_poll_status, last_poll_counts, updated_at
FROM ingestion_checkpoints
WHERE connector_name = 'azure_insights';
```

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

- Meaning: no matching telemetry was found between the persisted checkpoint and now

### `skipped_invalid_ip > 0`

- Meaning: no usable client IP was extracted from the returned telemetry

### `failures > 0`

- Meaning: the query or checkpoint/ingest HTTP call exhausted retries

### `401` from `test_endpoint`

- Meaning: the function key was missing or invalid

### `400` from `/ingest/azure`

- Meaning: the SIEM backend Azure adapter rejected the forwarded payload

## Supported Telemetry

- `AppExceptions`
- `AppRequests` for `401/403` and `5xx`
- `AppDependencies` where `Success == false`
- `AppAvailabilityResults` where `Success == false`

Not ingested:

- `AppTraces`
- Custom events
- Custom metrics
- Successful dependency or availability rows

## See Also

- Runtime debugging: `siem-azure-function/AZURE_TIMER_DEBUG.md`
