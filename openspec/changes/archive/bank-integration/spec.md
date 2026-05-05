# Bank Application to SIEM Integration Specification

## Overview

The banking application is a Flask backend running in the same deployment environment as the SIEM backend.  
The SIEM backend is also a Flask application in that environment.

The bank app forwards selected events to the SIEM ingestion API using HTTP requests over localhost.

### Communication Path

Bank App (Flask backend)  
→ HTTP POST to SIEM  
→ `http://your-siem-base-url/ingest`

The React frontend is separate and connects to the SIEM through an SSH tunnel, but that is outside the bank-to-SIEM event delivery path.

---

## Environment Variables

The integration depends on:

| Variable | Purpose |
|---------|---------|
| `SIEM_API_URL` | SIEM ingestion endpoint URL |
| `SIEM_INGEST_API_KEY` | API key used in request header |

### Example Value
- `SIEM_API_URL = http://your-siem-base-url/ingest`

---

## Helper Function

The banking app uses a helper function:

```python
send_siem_event(event_type, severity, source_ip, message, app_name="bank_app", environment="prod")
