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

## Step 1: Schema additions

- [ ] Read `schema.sql` — confirm no `incidents` or `incident_alerts` tables exist.
- [ ] Add `incidents` table with columns: `id`, `title`, `severity`, `priority` (CHECK P1-P4,
  default P2), `status` (CHECK open/investigating/resolved/closed, default open), `source_ip`,
  `assigned_to` (FK to users ON DELETE SET NULL), `created_at`, `resolved_at`.
- [ ] Add `incident_alerts` table with columns: `incident_id` (FK to incidents ON DELETE CASCADE),
  `alert_id` (FK to alerts ON DELETE CASCADE), `linked_at`, PRIMARY KEY `(incident_id, alert_id)`.
- [ ] Add indexes: `idx_incidents_status`, `idx_incidents_source_ip`, `idx_incidents_created_at`,
  `idx_incidents_severity`, `idx_incident_alerts_alert_id`, `idx_incident_alerts_incident_id`.
- [ ] Apply `schema.sql` to a fresh test database — confirm it completes with no errors.
- [ ] Run full regression suite — all six tests green.

---

## Step 2: Verify `alerts_created` dict shape includes `severity`

- [ ] Read `engines/detection_engine.py` — inspect the dicts appended to `alerts_created` in
  all `_generate_*_core()` functions.
- [ ] Confirm each dict includes `alert_id`, `source_ip`, `response_action`, and `severity`.
- [ ] If `severity` is absent from any function: add it (one line per function, value already
  exists as a local variable). Update any test assertions that check exact `alerts_created`
  dict shapes.
- [ ] Run full regression suite — all six tests green.

---

## Step 3: Implement `core/incident_store.py`

- [ ] Create `core/incident_store.py`.
  - Import `logging` — use `logging.getLogger(__name__)`. No Flask dependency.
  - No imports from route modules, detection engines, or correlation engines.

- [ ] Implement `create_incident(conn, title, severity, source_ip) -> dict`.
  - Derive priority: `CRITICAL → P1`, `HIGH → P2`, anything else → `P2`.
  - INSERT into `incidents`. Return full row as dict with ISO 8601 `created_at`.
  - Does not commit.

- [ ] Implement `link_alert_to_incident(conn, incident_id, alert_id) -> None`.
  - INSERT into `incident_alerts` with `ON CONFLICT DO NOTHING`.
  - Log `[INCIDENT LINK]` on insert, `[INCIDENT LINK] already linked` on conflict.
  - Does not commit.

- [ ] Implement `find_open_incident_by_source_ip(conn, source_ip, dedup_window_minutes=60) -> dict | None`.
  - Query `incidents WHERE source_ip = %s AND status IN ('open', 'investigating')
    AND created_at >= NOW() - INTERVAL '%s minutes' ORDER BY created_at DESC LIMIT 1`.
  - Use parameterized interval: `NOW() - (%(window)s * INTERVAL '1 minute')` or equivalent.
  - Return incident dict or `None`.

- [ ] Implement `maybe_create_or_link_incident(conn, alert_id, severity, source_ip) -> dict | None`.
  - Severity gate: return `None` immediately if severity not in `{'HIGH', 'CRITICAL'}`.
  - Call `find_open_incident_by_source_ip`. If found: link and return existing.
  - If not found: create new incident, link alert, return new incident.
  - Does not commit.

- [ ] Implement `list_incidents(conn, status=None, severity=None, limit=50, offset=0) -> list`.
  - Hard cap limit at 100.
  - Build query dynamically based on provided filters.
  - ORDER BY `created_at DESC`.
  - Return list of incident dicts.

- [ ] Implement `get_incident_detail(conn, incident_id) -> dict | None`.
  - Return `None` for unknown ID.
  - JOIN `incident_alerts` and `alerts` to build `alerts` list in the response.
  - Each alert entry includes: `alert_id`, `alert_type`, `severity`, `source_ip`, `status`,
    `created_at`, `linked_at`.

- [ ] Implement `update_incident_status(conn, incident_id, new_status, actor_username) -> dict`.
  - Fetch current incident. Raise `ValueError("incident not found")` if absent.
  - Enforce transition table from design.md. Raise `ValueError(f"invalid status transition: ...")`.
  - Set `resolved_at = NOW()` when transitioning to `resolved`.
  - UPDATE `incidents`. Return updated incident dict.
  - Does not commit.

---

## Step 4: Test `core/incident_store.py`

All tests use a real test database connection. No Flask test client needed.

- [ ] Schema tests:
  - `incidents` and `incident_alerts` tables exist after schema apply.
  - `status` CHECK rejects `'unknown'`.
  - `priority` CHECK rejects `'P5'`.
  - Duplicate `(incident_id, alert_id)` in `incident_alerts` raises IntegrityError.

- [ ] `create_incident` tests:
  - Returns dict with `id`, `title`, `severity`, `priority`, `status='open'`.
  - `CRITICAL` → `priority='P1'`.
  - `HIGH` → `priority='P2'`.

- [ ] `link_alert_to_incident` tests:
  - Row appears in `incident_alerts` after call.
  - Calling twice: no exception, exactly one row.

- [ ] `find_open_incident_by_source_ip` tests:
  - Returns `None` when no incidents exist.
  - Returns `None` for `resolved` incidents even within window.
  - Returns `None` for `closed` incidents even within window.
  - Returns incident for `open` incident within window.
  - Returns incident for `investigating` incident within window.
  - Returns `None` for `open` incident outside window.
  - Returns most recent when multiple `open` incidents exist for same IP.

- [ ] `maybe_create_or_link_incident` tests:
  - `MEDIUM` → `None`, no incidents table rows.
  - `LOW` → `None`, no incidents table rows.
  - `HIGH`, no existing incident → new incident created, alert linked, incident returned.
  - `HIGH`, existing `open` incident in window → alert linked to existing, no new incident.
  - `HIGH`, existing incident outside window → new incident created.
  - `HIGH`, existing incident is `resolved` → new incident created.
  - `CRITICAL` → same dedup behavior as HIGH.

- [ ] `list_incidents` tests:
  - Returns all incidents ordered by `created_at DESC`.
  - `status='open'` filter returns only open incidents.
  - `severity='CRITICAL'` filter returns only CRITICAL incidents.
  - Limit of 200 is capped at 100.
  - Empty table returns `[]`.

- [ ] `get_incident_detail` tests:
  - Unknown ID returns `None`.
  - No linked alerts → `"alerts": []`.
  - After linking, returns correct alert summaries with `linked_at`.

- [ ] `update_incident_status` tests:
  - `open → investigating` succeeds, returns updated dict.
  - `open → resolved` succeeds, `resolved_at` is set.
  - `resolved → open` succeeds, `resolved_at` unchanged.
  - `closed → open` raises `ValueError`.
  - Unknown `new_status` raises `ValueError`.
  - Unknown `incident_id` raises `ValueError("incident not found")`.

- [ ] Run full regression suite — all six tests green.

---

## Step 5: Implement `routes/incident_routes.py`

- [ ] Create `routes/incident_routes.py`.
  - Import `login_required` from `flask_login`.
  - Import `analyst_or_super_admin_required` from `core.auth`.
  - Import store functions from `core.incident_store`.
  - Blueprint: `incident_bp = Blueprint("incidents", __name__)`.

- [ ] Implement `GET /incidents`.
  - Auth: `@login_required @analyst_or_super_admin_required`.
  - Parse and validate `status`, `severity`, `limit`, `offset` from query string.
  - Invalid `status`: return `400 {"error": "invalid status filter"}`.
  - Invalid `severity`: return `400 {"error": "invalid severity filter"}`.
  - Clamp `limit` to max 100.
  - Call `list_incidents(conn, ...)`.
  - Response: `200 {"incidents": [...], "count": len(results)}`.

- [ ] Implement `GET /incidents/<int:incident_id>`.
  - Auth: `@login_required @analyst_or_super_admin_required`.
  - Call `get_incident_detail(conn, incident_id)`.
  - `None` → `404 {"error": "incident not found"}`.
  - Response: `200 {"incident": {...}}`.

- [ ] Implement `POST /incidents/<int:incident_id>/status`.
  - Auth: `@login_required @analyst_or_super_admin_required`.
  - Parse JSON body. `status` field required → `400` if missing.
  - Validate `status` is a recognized value → `400` if unknown.
  - Call `update_incident_status(conn, incident_id, new_status, current_user.username)`.
  - Catch `ValueError("incident not found")` → `404 {"error": "incident not found"}`.
  - Catch `ValueError("invalid status transition: ...")` → `400 {"error": ...}`.
  - On success: `conn.commit()`. Write to `audit_log` using `log_audit_event()`.
  - Response: `200 {"incident": {...}}`.

---

## Step 6: Test `routes/incident_routes.py`

Use Flask test client consistent with existing route test patterns.

- [ ] `GET /incidents` — unauthenticated → 401.
- [ ] `GET /incidents` — viewer role → 403.
- [ ] `GET /incidents` — analyst → 200, correct response shape.
- [ ] `GET /incidents?status=open` — returns only open incidents.
- [ ] `GET /incidents?status=invalid` — 400.
- [ ] `GET /incidents?limit=200` — clamped to 100 results.
- [ ] `GET /incidents/<id>` — unauthenticated → 401.
- [ ] `GET /incidents/<id>` — viewer → 403.
- [ ] `GET /incidents/<id>` — analyst, valid ID → 200 with `alerts` list.
- [ ] `GET /incidents/<id>` — analyst, unknown ID → 404.
- [ ] `POST /incidents/<id>/status` — unauthenticated → 401.
- [ ] `POST /incidents/<id>/status` — viewer → 403.
- [ ] `POST /incidents/<id>/status` — analyst, valid transition → 200.
- [ ] `POST /incidents/<id>/status` — missing `status` field → 400.
- [ ] `POST /incidents/<id>/status` — invalid transition → 400 with message.
- [ ] `POST /incidents/<id>/status` — unknown incident ID → 404.
- [ ] Run full regression suite — all six tests green.

---

## Step 7: Wire post-commit incident creation into `routes/ingest_routes.py`

- [ ] Read `routes/ingest_routes.py` — locate the post-commit enqueue block in all 4 handlers
  (`add_event`, `add_web_log_event`, `add_azure_event`, `add_otel_event`).
- [ ] Add `_create_incidents_for_alerts(alerts_created, conn)` as a private module-level helper.
  - Iterates `alerts_created`. Skips dicts missing `alert_id`, `severity`, or `source_ip`.
  - Calls `maybe_create_or_link_incident(conn, alert_id, severity, source_ip)` for each.
  - Does not commit. Does not raise.
- [ ] In each of the 4 handlers, after the existing enqueue `try/except` block, add:
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
- [ ] Confirm no existing handler logic is modified except the addition of this block.

---

## Step 8: Integration tests for ingest → incident

- [ ] Ingest HIGH-severity event that triggers detection. Confirm incident row created and
  alert linked in `incident_alerts`.
- [ ] Ingest second HIGH-severity event from same IP within 1 hour. Confirm no new incident,
  second alert linked to existing incident.
- [ ] Ingest MEDIUM-severity event. Confirm no incident created.
- [ ] Monkeypatch `maybe_create_or_link_incident` to raise. Confirm ingest returns 201 and
  alert row exists in DB.
- [ ] Run full regression suite — all six tests green.

---

## Step 9: Register blueprint and final regression

- [ ] In `siem_backend.py`, import `incident_bp` from `routes.incident_routes`.
- [ ] Add `app.register_blueprint(incident_bp)` after the existing blueprint registrations.
- [ ] Run full pytest suite (not just the six regression tests — all tests).
  - All existing tests green.
  - All new incident tests green.
- [ ] Confirm no production file outside the explicitly listed files was modified:
  - `schema.sql` — only additions.
  - `core/incident_store.py` — new file.
  - `routes/incident_routes.py` — new file.
  - `routes/ingest_routes.py` — post-commit block addition only.
  - `siem_backend.py` — blueprint registration only.
  - `engines/detection_engine.py` — `severity` field addition to `alerts_created` dicts only
    (if required by Step 2). No logic changes.
