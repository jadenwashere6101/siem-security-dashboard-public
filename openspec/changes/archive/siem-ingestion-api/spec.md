# SIEM Ingestion API Specification

## API Endpoint

### POST `/ingest`

Accepts a JSON payload representing a security event.

---

## Request Format

### Headers
- `Content-Type: application/json`
- `X-API-Key: <API_KEY>` (optional, enforced if configured)

---

## JSON Body

```json
{
  "event_type": "failed_login",
  "severity": "low",
  "source_ip": "130.85.195.47",
  "message": "Failed login attempt",
  "app_name": "bank_app",
  "environment": "prod"
}