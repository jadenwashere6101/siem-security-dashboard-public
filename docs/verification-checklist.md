# Verification Checklist

Use this checklist before and after structural cleanup work. The goal is to confirm the core SIEM flows still behave correctly without introducing a full test framework.

Some commands require environment variables loaded from `.env`.

Setup:

```bash
set -a
source .env
set +a
```

## 1. Backend Startup / Status

Check:

```bash
python3 -m py_compile siem_backend.py
curl -i http://127.0.0.1:5051/health
sudo systemctl cat siem-backend.service --no-pager | grep gunicorn
ss -ltnp | grep '127.0.0.1:5051'
ss -ltnp | grep '127.0.0.1:6379'
```

Pass:
- `py_compile` succeeds
- `/health` returns `200`
- production service evidence shows Gunicorn, not Flask's development server
- backend bind is loopback-only in production
- shared Redis-backed Flask-Limiter storage is present on loopback and not printed with credentials

## 2. Frontend Build

Check:

```bash
cd frontend && npm run build
```

Pass:
- production build completes
- no new errors are introduced
- existing warnings are unchanged or reduced

## 3. Azure Function Syntax Sanity

Check:

```bash
python3 -m py_compile siem-azure-function/function_app.py
```

Pass:
- `function_app.py` compiles successfully

## 4. Bank App / Custom Ingest Path

Check:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SIEM_INGEST_API_KEY" \
  -d '{
    "event_type": "failed_login",
    "severity": "medium",
    "source_ip": "198.51.100.10",
    "message": "Verification checklist custom ingest test",
    "app_name": "verification_check",
    "environment": "test"
  }'
```

Pass:
- endpoint returns success (`200` or `201`)
- event is stored in `events`

## 5. nginx `/ingest/web-log` Path

Check:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest/web-log \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SIEM_INGEST_API_KEY" \
  -d '{
    "line": "198.51.100.20 - - [30/Apr/2026:12:00:00 +0000] \"GET /admin HTTP/1.1\" 401 162 \"-\" \"curl/8.0\""
  }'
```

Pass:
- endpoint returns success
- event row appears with `source = 'nginx'`

## 6. Azure `/ingest/azure` Path

Check:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest/azure \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AZURE_INGEST_API_KEY" \
  -d '[
    {
      "baseType": "RequestData",
      "sourceIp": "198.51.100.30",
      "timestamp": "2026-04-30T12:00:00Z",
      "message": "Azure verification test",
      "data": {
        "baseData": {
          "responseCode": "500"
        }
      }
    }
  ]'
```

Pass:
- endpoint returns success
- event row appears with `source = 'azure_insights'`

## 7. OpenTelemetry `/ingest/otlp` Path

Check:

```bash
curl -i -X POST http://127.0.0.1:5051/ingest/otlp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OTEL_INGEST_API_KEY" \
  -d '[
    {
      "timestamp": "2026-04-30T12:00:00Z",
      "sourceIp": "198.51.100.40",
      "message": "OTEL verification test",
      "statusCode": 500,
      "serviceName": "verification_check"
    }
  ]'
```

Pass:
- endpoint returns success
- event row appears with `source = 'opentelemetry'`

## 8. Events DB Verification

Check:

```sql
SELECT created_at, source_ip, event_type, source, source_type, message
FROM events
ORDER BY created_at DESC
LIMIT 10;
```

Pass:
- new verification rows appear for the exercised ingest paths
- `source` and `source_type` values match expectations

## 9. Alerts / Report Export Sanity

Check:

Best verified through the browser UI unless authenticated `curl` is already configured.

```bash
curl -i http://127.0.0.1:5051/alerts/report
curl -i http://127.0.0.1:5051/alerts/report/pdf
curl -i http://127.0.0.1:5051/alerts/export/csv
```

Pass:
- endpoints return valid authenticated responses in the expected environment
- text export returns text content
- PDF export returns PDF content
- CSV export returns CSV content

Note:
- If auth is required, run these with a valid authenticated session or use the existing browser session path you normally use.

## 10. What Pass Looks Like After Cleanup / Refactor

Minimum pass criteria:
- backend still compiles and responds on `/health`
- frontend still builds
- Azure Function file still compiles
- all four ingest paths still accept valid payloads
- `events` shows expected new rows
- report/export endpoints still respond correctly
- no new unexpected errors appear in logs during the checks

## Suggested Usage

- Run the syntax/build checks first
- Run one request through each ingest path
- Verify the database rows
- Verify export/report responses
- Stop immediately if one core path fails after a structural change
