# Azure Timer Debug Guide

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

## Check Azure Function Invocations

Use the Azure Portal:

1. Open the Function App
2. Open `Functions`
3. Open `poll_application_insights`
4. Review:
   - `Monitor`
   - recent runs
   - success/failure status
   - invocation logs

You should see run-level counts for:

- `returned`
- `forwarded`
- `skipped_invalid_ip`
- `failures`
- `query_window_minutes`
- `max_records`

## Manual KQL Queries

### Requests

```kusto
requests
| where timestamp >= ago(5m)
| where toint(resultCode) in (401, 403) or toint(resultCode) >= 500
| project timestamp, operation_Name, name, resultCode, client_IP
| order by timestamp asc
| take 25
```

### Exceptions

```kusto
exceptions
| where timestamp >= ago(5m)
| project timestamp, operation_Name, message, client_IP
| order by timestamp asc
| take 25
```

### Combined View Matching Timer Scope

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

## Verify Forwarded Events In SIEM

Run against the SIEM database:

```sql
SELECT
    created_at,
    source_ip,
    event_type,
    source,
    source_type,
    raw_payload
FROM events
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 25;
```

Useful follow-up check:

```sql
SELECT
    created_at,
    source_ip,
    alert_type,
    severity,
    source,
    source_type
FROM alerts
WHERE source = 'azure_insights'
ORDER BY created_at DESC
LIMIT 25;
```

## Expected v1 Duplicate Behavior

- 5-minute query window
- max 25 records
- no persisted watermark yet

This means duplicate forwarding is still possible across overlapping runs or retries. That is an accepted v1 limitation.
