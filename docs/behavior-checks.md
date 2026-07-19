# Behavior Checks

Use these lightweight checks before and after backend refactors that touch ingest, detection, correlation, or report/export behavior.

These are fast command-based checks, not a test framework.

## Setup

Some commands require environment variables loaded from `.env`.

```bash
set -a
source .env
set +a
```

For production VM checks, confirm `siem-backend.service` is running Gunicorn,
`/health` responds on `127.0.0.1:5051`, and the backend port is not publicly
bound before running route-level behavior checks.

## 1. `/ingest` Basic Flow

Command:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SIEM_INGEST_API_KEY" \
  -d '{
    "event_type": "failed_login",
    "severity": "medium",
    "source_ip": "198.51.100.101",
    "message": "Behavior check custom ingest",
    "app_name": "behavior_check",
    "environment": "test"
  }'
```

Expected result:
- success response
- new `events` row with `source = 'bank_app'` or the current custom-ingest source value used by the backend

Failure indicates:
- ingest route validation broke
- API key handling broke
- normalized event write path broke

## 2. `/ingest/web-log`

Command:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest/web-log \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SIEM_INGEST_API_KEY" \
  -d '{
    "line": "198.51.100.102 - - [30/Apr/2026:12:00:00 +0000] \"POST /login HTTP/1.1\" 401 162 \"-\" \"curl/8.0\""
  }'
```

Expected result:
- success response
- new `events` row with `source = 'nginx'`

Failure indicates:
- nginx parsing broke
- `/ingest/web-log` route validation broke
- adapter-to-backend normalization broke

## 3. `/ingest/azure`

Command:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest/azure \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AZURE_INGEST_API_KEY" \
  -d '[
    {
      "baseType": "RequestData",
      "sourceIp": "198.51.100.103",
      "timestamp": "2026-04-30T12:00:00Z",
      "message": "Behavior check Azure error",
      "data": {
        "baseData": {
          "responseCode": "500"
        }
      }
    }
  ]'
```

Expected result:
- success response
- new `events` row with `source = 'azure_insights'`

Failure indicates:
- Azure route dispatch broke
- Azure adapter mapping broke
- Azure auth/config handling broke

## 4. `/ingest/otlp`

Command:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest/otlp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OTEL_INGEST_API_KEY" \
  -d '[
    {
      "timestamp": "2026-04-30T12:00:00Z",
      "sourceIp": "198.51.100.104",
      "message": "Behavior check OTEL error",
      "statusCode": 500,
      "serviceName": "behavior_check"
    }
  ]'
```

Expected result:
- success response
- new `events` row with `source = 'opentelemetry'`

Failure indicates:
- OTEL route validation broke
- OTEL adapter mapping broke
- OTEL auth/config handling broke

## 5. Detector Trigger Example: `failed_login_threshold`

Commands:

```bash
for i in 1 2 3; do
  curl -s -X POST http://127.0.0.1:5051/ingest \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $SIEM_INGEST_API_KEY" \
    -d "{
      \"event_type\": \"failed_login\",
      \"severity\": \"medium\",
      \"source_ip\": \"198.51.100.110\",
      \"message\": \"Behavior check failed login $i\",
      \"app_name\": \"behavior_check\",
      \"environment\": \"test\"
    }"
done
```

```sql
SELECT created_at, alert_type, severity, source_ip
FROM alerts
WHERE source_ip = '198.51.100.110'
ORDER BY created_at DESC
LIMIT 5;
```

Expected result:
- a `failed_login_threshold` alert appears for that IP

Failure indicates:
- detector execution broke
- threshold config lookup broke
- alert creation path broke

## 6. Correlation Example: spray -> success pattern

Commands:

```bash
for i in 1 2 3 4 5; do
  curl -s -X POST http://127.0.0.1:5051/ingest \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $SIEM_INGEST_API_KEY" \
    -d "{
      \"event_type\": \"failed_login\",
      \"severity\": \"medium\",
      \"source_ip\": \"198.51.100.120\",
      \"message\": \"Behavior check spray $i\",
      \"app_name\": \"behavior_check\",
      \"environment\": \"test\"
    }"
done
```

```bash
curl -i -X POST http://127.0.0.1:5051/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SIEM_INGEST_API_KEY" \
  -d '{
    "event_type": "successful_login",
    "severity": "low",
    "source_ip": "198.51.100.120",
    "message": "Behavior check success after spray",
    "app_name": "behavior_check",
    "environment": "test"
  }'
```

```sql
SELECT created_at, alert_type, source_ip, message
FROM alerts
WHERE source_ip = '198.51.100.120'
ORDER BY created_at DESC
LIMIT 10;
```

Expected result:
- a correlation-style alert appears, ideally `spray_then_success_pattern` if current logic is still wired as expected

Failure indicates:
- correlation execution broke
- supporting detector alerts no longer chain together
- success-after-spray flow regressed

## 7. Report / Export Validation

Best run through the browser UI unless authenticated `curl` is already configured.

Commands:

```bash
curl -i http://127.0.0.1:5051/alerts/report
curl -i http://127.0.0.1:5051/alerts/report/pdf
curl -i http://127.0.0.1:5051/alerts/export/csv
```

Expected result:
- text report endpoint returns text
- PDF report endpoint returns PDF
- CSV export endpoint returns CSV

Failure indicates:
- report route wiring broke
- report/export helpers broke
- auth/session assumptions changed unexpectedly

## 8. Minimal DB Verification Queries

Load `.env` first using the setup block above.

Recent events:

```bash
psql -U "$SIEM_DB_USER" -d "$SIEM_DB_NAME" -c "SELECT created_at, source_ip, event_type, source, source_type, message FROM events ORDER BY created_at DESC LIMIT 15;"
```

Recent alerts:

```bash
psql -U "$SIEM_DB_USER" -d "$SIEM_DB_NAME" -c "SELECT created_at, alert_type, severity, source_ip, message FROM alerts ORDER BY created_at DESC LIMIT 15;"
```

Expected result:
- recent rows exist for the checks you just ran
- `source` and `source_type` values match expectations

Failure indicates:
- write path regressed
- detector/correlation side effects are missing
- recent ingest calls are not persisting correctly

## Pass Standard

After a cleanup/refactor, this step passes if:
- all four ingest paths still accept valid payloads
- expected `events` rows appear
- the detector example still creates an alert
- the correlation example still creates the expected higher-level alert behavior
- report/export endpoints still return valid responses

If one of these fails after structural work, stop and investigate before continuing.
