# Design: SOAR Incident Foundation — Phase 2C

---

## Completed context

**Phase 2A** — `incidents` table, `incident_alerts` join table, and all `core/incident_store.py`
helpers are implemented and tested.

**Phase 2B** — `routes/incident_routes.py` with `GET /incidents`, `GET /incidents/<id>`, and
`POST /incidents/<id>/status` is implemented, tested, and registered in `siem_backend.py`.

---

## Current state before Phase 2C

### Ingest route post-commit structure (all 4 handlers)

```python
conn.commit()   # alert row is durable

try:
    enqueue_committed_alerts(alerts_created, conn)
    conn.commit()
except Exception as enqueue_error:
    current_app.logger.error(
        "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
        enqueue_error,
    )

return jsonify({"message": "...", "alerts_created": alerts_created}), 201
```

### `alerts_created` dict shape (confirmed by reading detection_engine.py)

Each `_generate_*_core()` function appends:
```python
{
    "source_ip": ...,
    "attempts": ...,
    "alert_id": ...,
    "response_action": ...,
}
```

`severity` is **not included**. It is a hardcoded string literal in each function's INSERT
VALUES tuple, not a named variable. It must be added to the dict before post-commit incident
wiring can use it.

### Severity values per detection function (confirmed)

| Function                                       | Hardcoded severity | Creates incident? |
|------------------------------------------------|--------------------|-------------------|
| `_generate_failed_login_alerts_core`           | `"high"`           | Yes               |
| `_generate_password_spraying_alerts_core`      | `"high"`           | Yes               |
| `_generate_successful_login_after_spray_alerts_core` | `"critical"` | Yes               |
| `_generate_application_exception_alerts_core`  | `"high"`           | Yes               |
| `_generate_http_error_alerts_core`             | `"medium"`         | No                |
| `_generate_port_scan_alerts_core`              | `"medium"`         | No                |
| `_generate_high_request_rate_alerts_core`      | `"medium"`         | No                |

The `maybe_create_or_link_incident` severity gate (`severity.upper() not in {'HIGH', 'CRITICAL'}`)
will naturally pass through the 4 high/critical functions and silently skip the 3 medium ones.
No special casing is needed in the ingest wiring.

---

## Phase 2C changes

### Step 1 — Add `severity` to `alerts_created` dicts (detection_engine.py)

In each of the 7 `_generate_*_core()` functions, add `"severity"` to the dict appended to
`alerts_created`. The value is the same literal already used in the INSERT VALUES tuple for
that function.

Example for `_generate_failed_login_alerts_core` (currently at line ~139):
```python
# before
alerts_created.append(
    {
        "source_ip": source_ip,
        "attempts": attempts,
        "alert_id": alert_id,
        "response_action": response_action,
    }
)

# after
alerts_created.append(
    {
        "source_ip": source_ip,
        "attempts": attempts,
        "alert_id": alert_id,
        "response_action": response_action,
        "severity": "high",
    }
)
```

Each function gets the correct hardcoded value from the table above. Do not introduce a named
variable — keep the literal. Introducing a variable (e.g., `severity = "high"`) would be an
unnecessary intermediate that has no other use in the function.

**Test assertion impact: none.** Existing tests check individual named fields on alert dicts
(`alert_id`, `source_ip`, `attempts`, `response_action`). None assert on the complete key set.
Adding `"severity"` is purely additive. No test file needs updating.

**`test_ingest_api_contracts.py` impact: none.** The test submits `"severity"` as an input
field on the request body. It does not assert on the shape of `alerts_created` in the response.

### Step 2 — Add `_create_incidents_for_alerts` helper (ingest_routes.py)

Add a private module-level function to `routes/ingest_routes.py`:

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

Import at top of file:
```python
from core.incident_store import maybe_create_or_link_incident
```

Rules:
- Does not commit.
- Does not raise — missing-field guard handles incomplete dicts silently.
- Does not call `maybe_create_or_link_incident` on dicts missing any of the three required
  fields. This is the safety net for any dict that doesn't include `severity` yet.
- `str(source_ip)` cast handles psycopg2 `Inet` objects correctly.

### Step 3 — Wire incident block into all 4 ingest route handlers (ingest_routes.py)

In each of the 4 handlers (`add_event`, `add_web_log_event`, `add_azure_event`,
`add_otel_event`), add the following block **immediately after** the existing enqueue
`try/except` block, **before** the `return jsonify(...)` statement:

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

The resulting commit sequence per handler:
```
conn.commit()            # 1 — alert row durable
enqueue try/except       # 2 — queue row, commits on success
incident try/except      # 3 — incident rows, commits on success
return 201
```

**Why failure is swallowed:** The alert is the source of truth. It is already committed and
returned as 201. Incident creation is a downstream grouping effect. Its failure must not
invalidate a committed ingest event. The structured error log includes `alert_id`, `source_ip`,
and `severity` for each affected alert so manual re-linking is possible if needed.

**Why a separate commit for incidents:** The incident block runs after the enqueue commit
closes. Opening a new implicit transaction allows the incident writes to be atomic with each
other. If incident creation raises mid-loop (e.g., on the second alert in a batch), the
rollback in `finally` (or the absence of a commit) leaves the DB clean.

**Why after enqueue, not before:** The enqueue block is already established and tested. Adding
the incident block after it keeps the two post-commit effects independent — an enqueue failure
does not prevent incident creation, and vice versa.

### Exact integration point in `add_event` (for reference)

```python
conn.commit()                              # existing

try:                                       # existing enqueue block
    enqueue_committed_alerts(alerts_created, conn)
    conn.commit()
except Exception as enqueue_error:
    current_app.logger.error(
        "[SOAR ENQUEUE ERROR] Post-commit enqueue failed — ingest was committed: %s",
        enqueue_error,
    )

try:                                       # NEW incident block
    _create_incidents_for_alerts(alerts_created, conn)
    conn.commit()
except Exception as incident_error:
    current_app.logger.error(
        "[SOAR INCIDENT FAILED] %s | alerts=%s",
        incident_error,
        [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
    )

return jsonify({                           # existing, unchanged
    "message": "Event added successfully",
    "alerts_created": alerts_created
}), 201
```

The same pattern applies to `add_web_log_event`, `add_azure_event`, and `add_otel_event`.
Read each handler before modifying — the `add_azure_event` and `add_otel_event` handlers
batch multiple events into `alerts_created` with `extend()`; the pattern is the same.

---

## Testing strategy — Phase 2C

### Pre-step regression (after adding severity to detection dicts, before route wiring)

Run the six regression tests immediately after the detection dict changes:
```
pytest tests/test_failed_login_detection.py
pytest tests/test_password_spraying_detection.py
pytest tests/test_correlated_activity.py
pytest tests/test_targeted_correlation.py
pytest tests/test_ingest_api_contracts.py
pytest tests/test_alert_mutation_api_contracts.py
```

All must be green before proceeding. If any fail, the severity addition has an unexpected
interaction — stop and investigate before touching ingest_routes.py.

### Integration tests (after route wiring)

Use the ingest route test pattern from `tests/test_ingest_api_contracts.py`. These tests
hit the actual route handlers against a real test database.

**Test 1 — HIGH alert creates an incident**
- POST a `failed_login` event from a source IP that will trigger detection (insert enough
  events to cross the threshold beforehand, or use the detection function directly).
- Confirm `incidents` table has one row.
- Confirm `incident_alerts` table has one row linking the alert to the incident.
- Confirm incident `severity = 'HIGH'` and `status = 'open'`.

**Test 2 — Second HIGH alert from same IP deduplicates**
- Trigger a second `failed_login` alert from the same source IP within 1 hour.
- Confirm `incidents` table still has only one row.
- Confirm `incident_alerts` table has two rows (both alerts linked to the same incident).

**Test 3 — MEDIUM alert does not create an incident**
- POST an `http_error` event from a source IP that will trigger `_generate_http_error_alerts_core`.
- Confirm `incidents` table has zero rows after ingest.
- Confirm ingest still returns 201.

**Test 4 — Incident failure does not mask committed ingest**
- Monkeypatch `maybe_create_or_link_incident` to raise `RuntimeError("simulated failure")`.
- POST a `failed_login` event that would normally create an incident.
- Confirm ingest returns 201.
- Confirm the alert row exists in `alerts`.
- Confirm `incidents` table has zero rows (incident creation was rolled back).

**Test 5 — Missing severity field is skipped cleanly**
- Call `_create_incidents_for_alerts` directly with a dict missing `severity`.
- Confirm no exception propagates.
- Confirm no incident row created.

### Regression tests (after every step)

```
pytest tests/test_failed_login_detection.py
pytest tests/test_password_spraying_detection.py
pytest tests/test_correlated_activity.py
pytest tests/test_targeted_correlation.py
pytest tests/test_ingest_api_contracts.py
pytest tests/test_alert_mutation_api_contracts.py
```

---

## Module placement — Phase 2C

```
engines/
  detection_engine.py         MODIFY: add "severity" to alerts_created dicts in all 7 functions

routes/
  ingest_routes.py            MODIFY: add import, private helper, incident block in 4 handlers
```

No new files. No schema changes. No changes to `core/`, `engines/soar_*`, or any test file.

---

## Risks and stop conditions

**1. Severity literal mismatch.**
The severity value added to the dict must exactly match what is already inserted into the DB.
If there is any doubt about a function's hardcoded value, read the function directly and
confirm against the table in this document before adding the dict field. A mismatch would
silently skip incident creation (severity gate fails) for `"high"` functions if the value is
wrong.

**Stop condition:** If regression tests fail after the detection dict changes, stop. Do not
proceed to route wiring until all six regression tests are green.

**2. `source_ip` type mismatch.**
psycopg2 returns `source_ip` as an `Inet` object when fetched from the DB (e.g., in the
enqueue orchestrator). Detection functions build the dict from the raw query row which also
returns `Inet`. The `str(source_ip)` cast in `_create_incidents_for_alerts` handles this.
If `maybe_create_or_link_incident` receives an `Inet` object instead of a string, the dedup
query may not match correctly. Confirm the cast is in place before testing.

**3. Batch route handlers.**
`add_azure_event` and `add_otel_event` loop over multiple event dicts and use `extend()` to
accumulate `alerts_created`. The incident block fires once per handler call, processing all
accumulated alert dicts. This is correct — one incident block handles the whole batch. Do not
add the incident block inside the event loop.

**Stop condition:** If `test_ingest_api_contracts.py` fails after route wiring, revert the
ingest_routes.py change and diagnose before re-attempting.

**4. Partial commit visibility.**
The incident block runs after `conn.commit()` has already closed the alert transaction. The
incident writes open a new implicit transaction. If the `conn.commit()` inside the incident
block fails (e.g., DB connectivity), the incident rows are not persisted. The structured error
log captures `alert_id`, `source_ip`, and `severity` for every affected alert so manual
re-queue is possible. This is acceptable — the alert is the source of truth.

**5. Correlation alerts remain unlinked.**
Correlation functions (`generate_correlated_activity_alerts`, etc.) return `bool`. They do
not contribute to `alerts_created`. Correlation-generated alerts are not linked to incidents
in Phase 2C. This is intentional and documented. Do not attempt to address this here.
