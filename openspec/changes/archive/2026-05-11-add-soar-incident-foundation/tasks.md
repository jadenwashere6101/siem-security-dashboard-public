# Tasks: SOAR Incident Foundation

Run the six regression tests after every step. If any fail, revert the step before continuing.

```
pytest tests/test_failed_login_detection.py
pytest tests/test_password_spraying_detection.py
pytest tests/test_correlated_activity.py
pytest tests/test_targeted_correlation.py
pytest tests/test_ingest_api_contracts.py
pytest tests/test_alert_mutation_api_contracts.py
```

---

## Phase 2A — Schema and store ✓ COMPLETE

- [x] Add `incidents` table and `incident_alerts` join table to `schema.sql`.
- [x] Add indexes for status, source_ip, created_at, severity, and join table FKs.
- [x] Implement `core/incident_store.py` with all 7 store helper functions.
- [x] Tests: schema constraints, create/link/list/detail/status/dedup behaviors.
- [x] Regression suite green.

---

## Phase 2B — Incident API routes ✓ COMPLETE

- [x] Implement `routes/incident_routes.py` with `incident_bp`.
- [x] `GET /incidents`, `GET /incidents/<id>`, `POST /incidents/<id>/status`.
- [x] Auth, filter validation, status transition error handling.
- [x] Route tests: 401/403, response shapes, invalid filters, unknown IDs.
- [x] Register `incident_bp` in `siem_backend.py`.
- [x] Regression suite green.

---

## Phase 2C — Post-commit incident creation (current scope)

---

### Step 1: Add `severity` to `alerts_created` dicts in all 7 detection functions

Read `engines/detection_engine.py` before making any changes.

- [x] Read `_generate_failed_login_alerts_core` — locate `alerts_created.append({...})`.
  Add `"severity": "high"` to the dict. Confirm the value matches the INSERT VALUES literal.
- [x] Read `_generate_password_spraying_alerts_core` — same. Add `"severity": "high"`.
- [x] Read `_generate_successful_login_after_spray_alerts_core` — same. Add `"severity": "critical"`.
- [x] Read `_generate_application_exception_alerts_core` — same. Add `"severity": "high"`.
- [x] Read `_generate_http_error_alerts_core` — same. Add `"severity": "medium"`.
- [x] Read `_generate_port_scan_alerts_core` — same. Add `"severity": "medium"`.
- [x] Read `_generate_high_request_rate_alerts_core` — same. Add `"severity": "medium"`.
- [x] Confirm no other code in the file was modified.
- [x] Run regression suite — all six green. **If any fail, stop. Do not proceed.**

> Severity values are confirmed by reading the INSERT VALUES tuple in each function.
> Existing test assertions check named fields (`alert_id`, `source_ip`, `attempts`,
> `response_action`) — not the complete key set. Adding `"severity"` is purely additive.

---

### Step 2: Add import and private helper to `routes/ingest_routes.py`

Read `routes/ingest_routes.py` before making any changes.

- [x] Add import at the top of the file:
  ```python
  from core.incident_store import maybe_create_or_link_incident
  ```
- [x] Add private module-level helper (after imports, before the blueprint definition or
  alongside other module-level helpers if any exist):
  ```python
  def _create_incidents_for_alerts(alerts_created, conn):
      for alert in alerts_created:
          alert_id = alert.get("alert_id")
          severity = alert.get("severity")
          source_ip = alert.get("source_ip")
          if not alert_id or not severity or not source_ip:
              continue
          maybe_create_or_link_incident(conn, alert_id, severity, str(source_ip))
  ```
- [x] Confirm the function does not commit, does not raise, and uses `str(source_ip)`.
- [x] Run regression suite — all six green.

---

### Step 3: Wire incident block into `add_event` handler

- [x] Locate the existing enqueue `try/except` block in `add_event`. Confirm it ends with
  `conn.commit()` on success.
- [x] Add the incident block immediately after the enqueue block, before `return jsonify(...)`:
  ```python
  try:
      _create_incidents_for_alerts(alerts_created, conn)
      conn.commit()
  except Exception as incident_error:
      current_app.logger.error(
          "[SOAR INCIDENT FAILED] %s | alerts=%s",
          incident_error,
          [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
      )
  ```
- [x] Confirm no other logic in `add_event` was changed.
- [x] Run regression suite — all six green. **If `test_ingest_api_contracts.py` fails, revert
  and stop.**

---

### Step 4: Wire incident block into `add_web_log_event` handler

- [x] Read `add_web_log_event` — confirm the enqueue block location.
- [x] Add incident block after enqueue block, same pattern as Step 3.
- [x] Confirm no other logic changed.
- [x] Run regression suite — all six green.

---

### Step 5: Wire incident block into `add_azure_event` handler

- [x] Read `add_azure_event` — confirm it uses `extend()` to accumulate `alerts_created`
  across multiple events. Confirm the enqueue block fires once after the loop.
- [x] Add incident block after enqueue block, same pattern. The block fires once per handler
  call over the full `alerts_created` list — do not add it inside the event loop.
- [x] Confirm no other logic changed.
- [x] Run regression suite — all six green.

---

### Step 6: Wire incident block into `add_otel_event` handler

- [x] Read `add_otel_event` — same `extend()` pattern as Azure.
- [x] Add incident block after enqueue block, same pattern.
- [x] Confirm no other logic changed.
- [x] Run regression suite — all six green.

---

### Step 7: Integration tests

Write new integration tests. Use the ingest route test pattern from
`tests/test_ingest_api_contracts.py` — real test database, Flask test client.

- [x] Test: HIGH alert creates incident.
  - Trigger a detection alert with `"high"` severity via ingest route.
  - Assert one row in `incidents`.
  - Assert one row in `incident_alerts` linking that alert to that incident.
  - Assert incident `severity = 'HIGH'` and `status = 'open'`.

- [x] Test: Second HIGH alert from same IP deduplicates.
  - Trigger a second alert from the same source IP within 1 hour.
  - Assert `incidents` still has one row.
  - Assert `incident_alerts` has two rows (both alerts linked to same incident).

- [x] Test: MEDIUM alert does not create incident.
  - Trigger an alert with `"medium"` severity via ingest route.
  - Assert `incidents` has zero rows.
  - Assert ingest returns 201.

- [x] Test: Incident failure does not mask committed ingest.
  - Monkeypatch `maybe_create_or_link_incident` to raise `RuntimeError`.
  - Trigger a HIGH-severity alert via ingest route.
  - Assert ingest returns 201.
  - Assert alert row exists in `alerts`.
  - Assert `incidents` has zero rows.

- [x] Test: Missing severity skipped cleanly.
  - Call `_create_incidents_for_alerts([{"alert_id": 1, "source_ip": "1.2.3.4"}], conn)` directly.
  - Assert no exception propagates.
  - Assert no incident row created.

- [x] Run full pytest suite — all existing tests green, all new integration tests green.

---

### Step 8: Final file audit

- [x] Confirm only these files were modified in Phase 2C:
  - `engines/detection_engine.py` — `"severity"` added to 7 `alerts_created.append({...})` dicts.
  - `routes/ingest_routes.py` — import added, `_create_incidents_for_alerts` added, incident
    block added to 4 handlers.
- [x] Confirm no schema changes.
- [x] Confirm no changes to `core/incident_store.py`, `engines/soar_*.py`, or any test file
  outside the new integration test file.
