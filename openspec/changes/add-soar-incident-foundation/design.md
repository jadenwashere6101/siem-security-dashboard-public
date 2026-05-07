# Design: SOAR Incident Foundation

---

## Current state (context only)

Post-commit SOAR enqueueing is wired into all 4 ingest route handlers. Each handler commits the
alert transaction, then calls `enqueue_committed_alerts(alerts_created, conn)` in a `try/except`
block that swallows enqueue failures so ingest always returns 201.

`alerts_created` dicts now include `alert_id`, `source_ip`, `response_action`, and `severity`
(added during the wire-post-commit-soar-enqueue phase). The incident orchestration function
can use these fields directly.

There is no incidents table, no incident_alerts table, and no incident store. This phase adds
all three and wires incident creation into the same post-commit path as enqueueing.

---

## Schema additions

Both tables are added to `schema.sql` using `CREATE TABLE IF NOT EXISTS`. No existing table is
modified. No columns are dropped or renamed.

### `incidents` table

```sql
CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'P2'
        CHECK (priority IN ('P1', 'P2', 'P3', 'P4')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'investigating', 'resolved', 'closed')),
    source_ip INET,
    assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
```

**Priority vs. severity distinction:**

`severity` mirrors the triggering alert's severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`). It
describes the threat level of the event. `priority` describes how urgently the incident needs
analyst attention. They are not always equal. Default derivation at create time:

| Triggering severity | Default priority |
|---------------------|-----------------|
| CRITICAL            | P1              |
| HIGH                | P2              |

Priority can be updated by an analyst later. Encoding the default at creation allows analysts
to override without re-deriving from severity.

**`source_ip`:** The IP from the triggering alert. Stored directly on the incident to support
the dedup lookup without a join to `incident_alerts` every time. This is denormalization for
query performance on the dedup path — it is not authoritative. The join table is the
authoritative link between alerts and incidents.

**No `source_alert_ids` column:** Alert-to-incident relationships live exclusively in
`incident_alerts`. An array column creates update anomalies and breaks dedup logic.

### `incident_alerts` join table

```sql
CREATE TABLE IF NOT EXISTS incident_alerts (
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (incident_id, alert_id)
);
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_source_ip ON incidents (source_ip);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents (created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents (severity);
CREATE INDEX IF NOT EXISTS idx_incident_alerts_alert_id ON incident_alerts (alert_id);
CREATE INDEX IF NOT EXISTS idx_incident_alerts_incident_id ON incident_alerts (incident_id);
```

`idx_incidents_source_ip` is critical — the dedup query filters by `source_ip` and `status`
on every HIGH/CRITICAL alert ingest.

---

## `core/incident_store.py`

All functions accept a `conn` (psycopg2 connection). None commit. None close the cursor. The
caller owns the connection lifecycle. This is consistent with `core/response_action_queue_store.py`.

Use `logging.getLogger(__name__)` — no Flask context dependency.

### `create_incident(conn, title, severity, source_ip) -> dict`

Inserts a new incident row. Derives default priority from severity. Returns the full incident
row as a dict.

```python
def create_incident(conn, title: str, severity: str, source_ip: str) -> dict:
```

Priority derivation:
```python
SEVERITY_TO_PRIORITY = {"CRITICAL": "P1", "HIGH": "P2"}
priority = SEVERITY_TO_PRIORITY.get(severity.upper(), "P2")
```

Returns:
```python
{
    "id": int,
    "title": str,
    "severity": str,
    "priority": str,
    "status": "open",
    "source_ip": str,
    "assigned_to": None,
    "created_at": str (ISO 8601),
    "resolved_at": None,
}
```

### `link_alert_to_incident(conn, incident_id, alert_id) -> None`

Inserts a row into `incident_alerts`. Uses `ON CONFLICT DO NOTHING` — safe to call twice for
the same pair.

```python
def link_alert_to_incident(conn, incident_id: int, alert_id: int) -> None:
```

Logs `[INCIDENT LINK] incident_id=... alert_id=...` on success, `already linked` on conflict.

### `find_open_incident_by_source_ip(conn, source_ip, dedup_window_minutes=60) -> dict | None`

Queries for the most recent open or investigating incident with a matching `source_ip` whose
`created_at` falls within the dedup window.

```python
def find_open_incident_by_source_ip(
    conn, source_ip: str, dedup_window_minutes: int = 60
) -> dict | None:
```

SQL sketch:
```sql
SELECT *
FROM incidents
WHERE source_ip = %(source_ip)s
  AND status IN ('open', 'investigating')
  AND created_at >= NOW() - INTERVAL '%(window)s minutes'
ORDER BY created_at DESC
LIMIT 1
```

Returns the incident dict if found, `None` if not.

**Why `source_ip` on incidents directly:** Joining `incident_alerts` on every ingest call to
find a matching incident would require joining back to `alerts` to get the IP. Storing
`source_ip` on the incident row makes the dedup query a single table scan.

### `maybe_create_or_link_incident(conn, alert_id, severity, source_ip) -> dict | None`

The orchestration function. Called after commit for HIGH and CRITICAL alerts.

```python
def maybe_create_or_link_incident(
    conn, alert_id: int, severity: str, source_ip: str
) -> dict | None:
```

Logic:
1. If `severity` is not in `{'HIGH', 'CRITICAL'}`: return `None` immediately. No DB write.
2. Call `find_open_incident_by_source_ip(conn, source_ip)`.
3. If a matching incident exists:
   - Call `link_alert_to_incident(conn, existing.id, alert_id)`.
   - Log `[INCIDENT LINKED] alert_id=... to existing incident_id=...`.
   - Return the existing incident dict.
4. If no match:
   - Build title: `f"[AUTO] {severity} alert from {source_ip}"`.
   - Call `create_incident(conn, title, severity, source_ip)`.
   - Call `link_alert_to_incident(conn, new_incident.id, alert_id)`.
   - Log `[INCIDENT CREATED] incident_id=... for alert_id=...`.
   - Return the new incident dict.

Does NOT commit. The caller commits after this returns (same pattern as enqueue).

### `list_incidents(conn, status=None, severity=None, limit=50, offset=0) -> list`

Returns a list of incident dicts, ordered by `created_at DESC`. Supports optional filtering
by `status` and `severity`. Hard maximum of 100 rows regardless of caller-supplied limit.

```python
def list_incidents(
    conn,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
```

Does not join `incident_alerts` — returns incident-level data only. The detail endpoint
returns linked alerts.

### `get_incident_detail(conn, incident_id) -> dict | None`

Returns the incident row plus a list of linked alert summaries.

```python
def get_incident_detail(conn, incident_id: int) -> dict | None:
```

Returns `None` if no incident with that ID. Otherwise:

```python
{
    "id": int,
    "title": str,
    "severity": str,
    "priority": str,
    "status": str,
    "source_ip": str,
    "assigned_to": int | None,
    "created_at": str,
    "resolved_at": str | None,
    "alerts": [
        {
            "alert_id": int,
            "alert_type": str,
            "severity": str,
            "source_ip": str,
            "status": str,
            "created_at": str,
            "linked_at": str,
        },
        ...
    ]
}
```

SQL: JOIN `incident_alerts` ON `incident_id`, JOIN `alerts` ON `alert_id`. One query.

### `update_incident_status(conn, incident_id, new_status, actor_username) -> dict`

Updates the incident's `status`. Enforces valid transitions. Sets `resolved_at` when
transitioning to `resolved`. Returns the updated incident dict.

```python
def update_incident_status(
    conn, incident_id: int, new_status: str, actor_username: str
) -> dict:
```

Valid transitions:

| From          | To                             |
|---------------|--------------------------------|
| open          | investigating, resolved, closed |
| investigating | resolved, closed               |
| resolved      | closed, open (re-open)         |
| closed        | (no transitions allowed)       |

If `incident_id` does not exist: raise `ValueError("incident not found")`.
If `new_status` is not a valid transition: raise `ValueError("invalid status transition")`.
If `new_status == "resolved"`: set `resolved_at = NOW()`.
If `new_status != "resolved"`: leave `resolved_at` unchanged (do not clear it on re-open;
the timestamp remains as a record).

Does NOT commit. Does NOT write to `audit_log` — the route handler handles audit logging
using the existing `audit_helpers` pattern.

---

## `routes/incident_routes.py`

Blueprint: `incident_bp`, url_prefix not set (routes are top-level `/incidents/...`).

Import and auth pattern consistent with `routes/blocklist_routes.py`:
```python
from flask_login import current_user, login_required
from core.auth import analyst_or_super_admin_required
```

### `GET /incidents`

Auth: `login_required` + `analyst_or_super_admin_required`.

Query params:
- `status`: optional filter (`open`, `investigating`, `resolved`, `closed`)
- `severity`: optional filter (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
- `limit`: integer, max 100, default 50
- `offset`: integer, default 0

Calls `list_incidents(conn, status=..., severity=..., limit=..., offset=...)`.

Response `200`:
```json
{
  "incidents": [ { ...incident fields... } ],
  "count": 12
}
```

Validates `status` and `severity` against allowed sets. Returns `400` with a message on
invalid filter values.

### `GET /incidents/<int:incident_id>`

Auth: `login_required` + `analyst_or_super_admin_required`.

Calls `get_incident_detail(conn, incident_id)`.

Returns `404` with `{"error": "incident not found"}` if not found.

Response `200`:
```json
{
  "incident": { ...incident fields + alerts list... }
}
```

### `POST /incidents/<int:incident_id>/status`

Auth: `login_required` + `analyst_or_super_admin_required`.

Request body:
```json
{ "status": "investigating" }
```

Validates `status` is present and is a recognized status value. Returns `400` if missing or
unrecognized.

Calls `update_incident_status(conn, incident_id, new_status, current_user.username)`.

Catches `ValueError` from `update_incident_status` and returns `400` with the error message
(covers "incident not found" as `404` and "invalid status transition" as `400` — see below).

`ValueError("incident not found")` → `404 {"error": "incident not found"}`.
`ValueError("invalid status transition: ...")` → `400 {"error": ...}`.

Writes to `audit_log` using existing `log_audit_event()` pattern.

Commits after success. Returns `200` with the updated incident dict.

---

## Post-commit integration in `routes/ingest_routes.py`

The integration follows the exact same pattern as `enqueue_committed_alerts`. After the first
`conn.commit()`, and after the existing enqueue block, add a second try/except block:

```python
# After conn.commit() and after enqueue block:
try:
    _create_incidents_for_alerts(alerts_created, conn)
    conn.commit()
except Exception as incident_error:
    current_app.logger.error(
        "[SOAR INCIDENT FAILED] %s | alerts=%s",
        incident_error,
        [(a.get("alert_id"), a.get("source_ip"), a.get("severity")) for a in alerts_created],
    )
    # Do not re-raise — committed ingest must not surface as 500.
```

`_create_incidents_for_alerts` is a thin private helper in `ingest_routes.py`:

```python
def _create_incidents_for_alerts(alerts_created, conn):
    for alert in alerts_created:
        alert_id = alert.get("alert_id")
        severity = alert.get("severity")
        source_ip = alert.get("source_ip")
        if not alert_id or not severity or not source_ip:
            continue
        maybe_create_or_link_incident(conn, alert_id, severity, source_ip)
```

This helper does not commit. It is not a public function. It is not tested directly — the
store function `maybe_create_or_link_incident` carries the full test coverage.

**Why a second commit after incident creation:** `maybe_create_or_link_incident` inserts
rows into `incidents` and `incident_alerts`. These writes must be committed before the
response returns. The enqueue commit and the incident commit are separate for isolation:
an enqueue failure still allows incident creation to proceed, and vice versa.

**Why incident failure is swallowed:** The alert is the source of truth. It is committed.
The caller sees 201. Incident creation is a downstream effect. Its failure must not invalidate
a committed ingest event. The error log provides structured context for investigation.

**Ordering in the handler:**
1. `conn.commit()` — alert is durable.
2. Enqueue block (existing, try/except).
3. `conn.commit()` — queue row is durable.
4. Incident block (new, try/except).
5. `conn.commit()` — incident row is durable.
6. Return 201.

**Correlation alerts:** Correlation functions still return `bool`. They are not included in
`alerts_created`. Correlation alerts are not linked to incidents in this phase.

---

## Blueprint registration

In `siem_backend.py`:
```python
from routes.incident_routes import incident_bp
app.register_blueprint(incident_bp)
```

Add after the existing blueprint registrations. No url_prefix — routes are `/incidents/...`.

---

## Testing strategy

### Schema tests

- Apply `schema.sql` to a test database. Confirm `incidents` and `incident_alerts` tables
  exist with correct columns and constraints.
- Confirm `status` CHECK constraint rejects invalid values.
- Confirm `priority` CHECK constraint rejects invalid values.
- Confirm `incident_alerts` PRIMARY KEY prevents duplicate `(incident_id, alert_id)` pairs.

### Store function tests

All tests call store functions directly with a real test database connection. No route calls.
No Flask test client needed for these tests.

**`create_incident`**
- Valid call returns a dict with `id`, `title`, `severity`, `priority`, `status='open'`.
- `CRITICAL` severity → `priority='P1'`.
- `HIGH` severity → `priority='P2'`.

**`link_alert_to_incident`**
- Links alert to incident. Row appears in `incident_alerts`.
- Calling twice with same pair: no exception, one row in table (idempotency via ON CONFLICT).

**`find_open_incident_by_source_ip`**
- Returns `None` when no incidents exist.
- Returns `None` when only `resolved` or `closed` incidents exist for that IP.
- Returns the incident when an `open` incident for that IP is within the window.
- Returns `None` when the incident is within the window but `status='resolved'`.
- Returns `None` when the incident is `open` but outside the window (simulate by
  inserting with `created_at = NOW() - INTERVAL '90 minutes'`).
- Returns the most recent incident when multiple open incidents exist for the same IP.

**`maybe_create_or_link_incident`**
- `severity='MEDIUM'`: returns `None`, no rows in `incidents`.
- `severity='LOW'`: returns `None`, no rows in `incidents`.
- `severity='HIGH'`, no existing incident: creates one, links alert, returns incident dict.
- `severity='HIGH'`, existing open incident within window: links alert to existing, no new
  incident created.
- `severity='HIGH'`, existing incident outside window: creates a new incident.
- `severity='HIGH'`, existing incident is `resolved`: creates a new incident (does not link
  to a closed/resolved incident).
- `severity='CRITICAL'`: same dedup behavior as HIGH.

**`list_incidents`**
- Returns all incidents ordered by `created_at DESC`.
- `status` filter returns only matching rows.
- `severity` filter returns only matching rows.
- `limit` caps results; `offset` skips rows.
- Limit above 100 is capped at 100.
- Empty table returns `[]`.

**`get_incident_detail`**
- Returns `None` for a nonexistent ID.
- Returns incident dict with empty `alerts` list when no alerts linked.
- Returns incident dict with correct alert summaries after linking alerts.
- `linked_at` field is present in each alert entry.

**`update_incident_status`**
- Valid transitions succeed and return updated dict.
- `open → resolved` sets `resolved_at`.
- `resolved → open` does not clear `resolved_at`.
- `closed → open` raises `ValueError`.
- Unknown `new_status` raises `ValueError`.
- Nonexistent `incident_id` raises `ValueError`.

### Route tests

Use Flask test client with the app factory pattern consistent with existing route tests.

**`GET /incidents`**
- Unauthenticated: 401.
- Viewer role: 403.
- Analyst: 200 with `{"incidents": [...], "count": int}`.
- `status=open` filter: returns only open incidents.
- `status=invalid`: 400.
- `limit=200`: clamped to 100.

**`GET /incidents/<id>`**
- Unauthenticated: 401.
- Viewer: 403.
- Analyst, valid ID: 200 with `{"incident": {..., "alerts": [...]}}`.
- Analyst, unknown ID: 404.

**`POST /incidents/<id>/status`**
- Unauthenticated: 401.
- Viewer: 403.
- Analyst, valid transition: 200 with updated incident dict.
- Analyst, missing `status` in body: 400.
- Analyst, invalid transition: 400 with error message.
- Analyst, unknown incident ID: 404.

### Integration tests (ingest → incident)

Use the ingest route test pattern from `test_ingest_api_contracts.py`.

- Ingest a HIGH-severity event that triggers a detection alert. Confirm an incident is created.
- Ingest a second HIGH-severity event from the same IP within 1 hour. Confirm the same
  incident gains a second link — no new incident created.
- Ingest a MEDIUM-severity event. Confirm no incident is created.
- Simulate `maybe_create_or_link_incident` raising an exception (monkeypatch). Confirm ingest
  still returns 201 and alert is present in the DB.

### Regression tests

After every implementation step, run:
```
pytest tests/test_failed_login_detection.py
pytest tests/test_password_spraying_detection.py
pytest tests/test_correlated_activity.py
pytest tests/test_targeted_correlation.py
pytest tests/test_ingest_api_contracts.py
pytest tests/test_alert_mutation_api_contracts.py
```

All must pass with no modifications.

---

## Module placement

```
core/
  incident_store.py              NEW: all incident DB helpers

routes/
  incident_routes.py             NEW: GET /incidents, GET /incidents/<id>,
                                      POST /incidents/<id>/status
  ingest_routes.py               MODIFY: add post-commit incident block
                                          (same pattern as enqueue block)

schema.sql                       ADD: incidents, incident_alerts tables + indexes

siem_backend.py                  MODIFY: register incident_bp
```

No new package directories. No changes to `engines/`, `core/ip_helpers.py`,
`core/response_action_queue_store.py`, detection engine, or correlation engine.

---

## Risks

**1. `alerts_created` dict shape may not include `severity`.**

If `severity` was not added to `alerts_created` dicts during the wire-post-commit-soar-enqueue
phase, `_create_incidents_for_alerts` will skip every alert (missing field guard). Verify
`alerts_created` dicts contain `severity` before implementing the integration step. If absent,
add it to the detection function return dicts as a pre-step — this is a one-line change per
function but requires updating test assertions.

**2. High-volume ingest creates many incidents.**

Under alert flood conditions, every new HIGH/CRITICAL alert that falls outside the dedup
window creates a new incident. The dedup window only matches on `source_ip`. Two different
source IPs always create two incidents. This is correct behavior, but in flood scenarios the
`incidents` table will grow rapidly. Mitigation: the dedup logic and a reasonable default
window (60 minutes) limit per-IP duplication. Rate limiting is a Phase 5 concern.

**3. Dual post-commit blocks add latency to the ingest response.**

Each `conn.commit()` call adds a round-trip. The ingest handler now commits three times:
once for the alert, once for the queue row, once for the incident row. For low-volume
ingest this is negligible. Document this explicitly so future phases don't add additional
post-commit commits without awareness of the pattern.

**4. Incident creation failure is silent to the caller.**

A failed incident creation is logged but not surfaced in the 201 response body. There is
no signal to the ingest caller that incident creation failed. This is intentional — the
ingest contract guarantees event durability, not downstream effect durability. Future phases
may add a `/health/incident-creator` endpoint to surface persistent failure rates.

**5. `resolved_at` is not cleared on re-open.**

`resolved → open` leaves `resolved_at` set. This is a deliberate choice (the timestamp is a
historical record) but may surprise future analysts. Document the behavior in the status
update function. A future timeline feature (Phase 4) will surface this with explicit context.
