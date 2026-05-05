# Alerts API Specification

## Endpoint 1 — GET /alerts

### Purpose
Return all alerts from the SIEM.

### Behavior
- Query alerts from the `alerts` table
- Sort by `created_at DESC`
- Return alert objects as JSON

---

### Response Example

```json
[
  {
    "id": 4,
    "alert_type": "failed_login_threshold",
    "severity": "high",
    "message": "3 failed login attempts detected from 130.85.195.47",
    "source_ip": "130.85.195.47",
    "created_at": "2026-04-09 16:31:33.987511+00:00",
    "status": "open"
  }
]