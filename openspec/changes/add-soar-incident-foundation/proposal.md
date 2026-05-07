# Proposal: SOAR Incident Foundation

## Problem

The SOAR queue, worker, executor, and post-commit enqueue pipeline are all working. Detection
alerts generate queue entries after commit. But every alert is still a standalone, disconnected
entity. There is no grouping layer. When ten alerts fire from the same source IP over five
minutes, analysts see ten separate rows with no indication they belong to the same attack
sequence.

A SOAR platform without a case layer is just a fancier queue. Incidents are the unit analysts
work. Without them, there is no place to track investigation state, no way to group related
alerts, and no foundation for playbook executions or approval gates in later phases.

## Implementation phases

This change is split into three sequential phases. Each phase is safe to implement and verify
independently. **The next implementation scope is Phase 2A only.**

### Phase 2A — Incident schema and store foundation (current scope)

Add the incident data layer: schema, store helpers, and direct DB-backed tests. No routes.
No ingest wiring. No detection function changes.

In scope:
- `incidents` table and `incident_alerts` join table added to `schema.sql`.
- `core/incident_store.py` with all store helper functions:
  - `create_incident(conn, title, severity, source_ip) -> dict`
  - `link_alert_to_incident(conn, incident_id, alert_id) -> None`
  - `find_open_incident_by_source_ip(conn, source_ip, dedup_window_minutes) -> dict | None`
  - `maybe_create_or_link_incident(conn, alert_id, severity, source_ip) -> dict | None`
  - `list_incidents(conn, status=None, severity=None, limit=50, offset=0) -> list`
  - `get_incident_detail(conn, incident_id) -> dict | None`
  - `update_incident_status(conn, incident_id, new_status, actor_username) -> dict`
- Direct DB-backed unit tests for every store function.
- Schema constraint tests.
- No changes to any route handler, detection engine, correlation engine, or ingest flow.

### Phase 2B — Incident API routes (deferred)

Add read and status-update endpoints once the store is verified:
- `GET /incidents`
- `GET /incidents/<id>`
- `POST /incidents/<id>/status`
- Auth, error handling, and route tests.
- Blueprint registration in `siem_backend.py`.

### Phase 2C — Post-commit incident creation (deferred)

Wire `maybe_create_or_link_incident` into the ingest pipeline:
- After alert commit and queue commit in all 4 ingest route handlers.
- HIGH and CRITICAL detection alerts only.
- Incident failure must not mask committed ingest — wrapped in `try/except`.
- Requires verifying `severity` is present in `alerts_created` dicts (may require a detection
  function change with test assertion updates before wiring can land).
- Correlation alert linking remains deferred beyond Phase 2C.

## Out of scope (all phases)

- No playbooks.
- No approval gates.
- No Slack or email notifications.
- No real firewall execution or queue behavior changes.
- No frontend UI.
- No correlation alert linking (requires correlation function return-shape changes).
- No `POST /incidents/<id>/assign` endpoint.
- No incident timeline endpoint (Phase 4 per roadmap).
- No schema changes beyond the two incident tables.

## Phase 2A success criteria

- `schema.sql` applies cleanly on a fresh database. Both tables exist with correct columns,
  constraints, and indexes.
- All six regression tests pass with no modifications.
- `create_incident` returns the correct dict and derives priority from severity.
- `link_alert_to_incident` is idempotent — duplicate calls do not raise and do not create
  duplicate rows.
- `find_open_incident_by_source_ip` returns `None` for resolved or closed incidents even if
  they are within the dedup window.
- `find_open_incident_by_source_ip` returns `None` for open incidents outside the window.
- `maybe_create_or_link_incident` returns `None` for MEDIUM and LOW severity without writing.
- `maybe_create_or_link_incident` creates a new incident and links the alert when no open
  incident exists for that IP within the window.
- `maybe_create_or_link_incident` links to an existing incident and does not create a new one
  when a matching open incident is within the window.
- `update_incident_status` enforces valid transitions and raises `ValueError` on invalid ones.
- `update_incident_status` sets `resolved_at` on transition to `resolved` and does not clear
  it on re-open.
- No route file, detection engine, correlation engine, or ingest route is modified.
