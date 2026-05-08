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

---

## Implementation phases

### Phase 2A — Incident schema and store foundation ✓ COMPLETE

Schema additions (`incidents`, `incident_alerts`) and `core/incident_store.py` with full store
helper functions and direct DB-backed tests. No routes, no ingest wiring.

### Phase 2B — Incident API routes ✓ COMPLETE

`GET /incidents`, `GET /incidents/<id>`, `POST /incidents/<id>/status`. Auth, route tests,
blueprint registration in `siem_backend.py`.

### Phase 2C — Post-commit incident creation (current scope)

Wire `maybe_create_or_link_incident` into the ingest pipeline so HIGH and CRITICAL detection
alerts automatically create or link incidents after the alert commit.

**In scope:**
- Add `"severity"` field to `alerts_created` dicts in all 7 `_generate_*_core()` functions.
  The value is already a hardcoded literal in each function's INSERT statement — this is a
  one-line additive change per function. No logic changes. No test assertion updates required.
- Add `_create_incidents_for_alerts(alerts_created, conn)` as a private helper in
  `routes/ingest_routes.py`. Calls `maybe_create_or_link_incident` for each alert dict that
  has `alert_id`, `severity`, and `source_ip`. Does not commit. Does not raise.
- Wire an incident creation block after the existing enqueue block in all 4 ingest route
  handlers. Same try/except pattern as the enqueue block — failure is logged and swallowed.
- Integration tests: ingest triggers incident creation, dedup across two ingests from same IP,
  incident failure does not mask committed ingest.

**Out of scope:**
- No correlation alert incident linking (correlation functions return `bool`, not alert dicts).
- No playbooks, approval gates, Slack/email, or real firewall execution.
- No frontend incident UI.
- No SOAR queue or worker behavior changes.
- No schema changes.

---

## Phase 2C success criteria

- After a HIGH or CRITICAL detection alert is committed, an incident row exists in `incidents`
  and a link row exists in `incident_alerts`.
- A second HIGH alert from the same source IP within 1 hour links to the existing incident —
  no new incident row is created.
- A MEDIUM or LOW detection alert does not create an incident.
- If `maybe_create_or_link_incident` raises after `conn.commit()`, the ingest route still
  returns 201 and the committed alert is present in the DB.
- Adding `"severity"` to `alerts_created` dicts does not break any existing test.
- All six regression tests pass unchanged after every step.
