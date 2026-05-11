# Design: SOAR Playbook Trigger Execution Records

## Proposed Architecture

Add a small playbook orchestration layer that runs after alert rows are committed.

Recommended module:

```text
engines/playbook_execution_orchestrator.py
```

The orchestrator should coordinate existing read-only trigger matching with idempotent
execution-record creation:

```python
create_pending_executions_for_committed_alerts(alerts_created, conn) -> list[dict]
```

Responsibilities:

- accept the same `alerts_created` list shape already returned by ingest
- extract committed `alert_id` values
- call `engines.playbook_engine.match_playbooks(conn, alert_id)`
- create pending `playbook_executions` rows for matched definitions
- skip duplicate `(playbook_id, alert_id)` pairs
- log skip/create/error outcomes
- never execute steps or enqueue SOAR actions

Keep matching logic in `engines/playbook_engine.py`. Keep database write logic in
`core/playbook_store.py`. Keep ingest route changes limited to calling the orchestrator after
the primary transaction has committed.

## Safe Data Flow

```text
ingest route
  -> ingest_normalized_event(...)
  -> detection/correlation create alert rows inside transaction
  -> conn.commit()                          # alert rows now visible
  -> enqueue_committed_alerts(...)          # existing SOAR queue behavior remains unchanged
  -> conn.commit()
  -> create incidents for alerts            # existing incident behavior remains unchanged
  -> conn.commit()
  -> create_pending_executions_for_committed_alerts(alerts_created, conn)
  -> conn.commit()
  -> return existing ingest response
```

Alternative ordering is acceptable only if all of these remain true:

- playbook matching occurs after the alert commit
- enqueue behavior remains unchanged
- incident behavior remains unchanged
- failures in playbook scheduling do not roll back alert creation, SOAR queue enqueueing, or
  incident creation

The orchestrator should operate on committed alert IDs. It must not run inside the
detection/correlation transaction.

## Exact Post-Commit Boundary

The first safe boundary is immediately after the existing `conn.commit()` that closes the
ingest transaction. That commit must remain before playbook matching.

Unsafe:

```text
detection/correlation transaction still open
  -> match playbooks
  -> create playbook_executions
```

Safe:

```text
detection/correlation transaction
  -> conn.commit()
  -> match playbooks against committed alert IDs
  -> insert pending playbook_executions
  -> conn.commit()
```

The implementation should not move, wrap, or refactor the existing detection/correlation
transaction flow. It should add a small post-commit try/except block at the same level as
existing SOAR enqueue and incident post-commit work.

## Idempotency/Deduplication Design

Required semantic guarantee:

```text
one playbook_executions row per playbook_id + alert_id
```

Recommended DB-level safety:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_executions_playbook_alert_unique
ON playbook_executions (playbook_id, alert_id)
WHERE alert_id IS NOT NULL;
```

This is a tiny additive index, not a schema behavior rewrite. It prevents duplicates if the
orchestrator is called twice or concurrent requests attempt to schedule the same pair.

Store helper options:

```python
def create_pending_playbook_execution_once(
    conn,
    playbook_id: str,
    alert_id: int,
    incident_id: int | None = None,
) -> int | None:
    ...
```

Behavior:

- insert `status='pending'`
- return execution ID when inserted
- return `None` when duplicate skipped
- do not update existing rows
- do not execute steps
- do not commit

If adding the unique index is not possible in the current implementation slice, the helper
may first query for an existing row and skip duplicates, but that is weaker under concurrency.
The preferred implementation uses both a pre-check for clear logs and a unique index for
hard safety.

## Files Likely To Change

- `schema.sql` — only if adding the unique partial index for `(playbook_id, alert_id)`.
- `core/playbook_store.py` — add idempotent pending execution creation helper.
- `engines/playbook_execution_orchestrator.py` — new post-commit orchestration module.
- `routes/ingest_routes.py` — minimal post-commit call in each existing ingest handler.
- `tests/test_playbook_store.py` — idempotent helper tests.
- `tests/test_playbook_execution_orchestrator.py` — orchestration tests.
- Existing ingest route tests — extend only where needed to assert no behavior regression.

Do not change:

- detection engine internals
- correlation engine internals
- ingest engine routing
- SOAR queue worker or executor
- approval routes/store
- incident routes/store, except reading incident linkage only if already safely available
- frontend files
- adapter/integration files

## Failure Behavior

Playbook scheduling is best-effort metadata creation after ingest commit.

Rules:

- invalid alert entries are skipped and logged
- missing `alert_id` is skipped and logged
- alert not found returns no matches and logs through existing matching behavior
- duplicate playbook/alert pair is skipped and logged as duplicate
- unexpected matching or insert error is logged and returned in orchestrator result
- ingest response must still succeed after alert commit
- errors must not roll back existing alert rows, SOAR queue rows, or incident rows

The route-level post-commit block should catch broad exceptions from the orchestrator, log a
clear message such as `[PLAYBOOK ORCHESTRATION ERROR]`, and continue returning the normal
ingest response.

## Safety Boundaries

- Matching must happen only after alert rows are committed and visible.
- Must not run inside the detection/correlation transaction.
- Must not alter existing alert creation behavior.
- Must not change existing SOAR response queue behavior.
- Must not execute actions.
- Must not enqueue actions.
- Must not create approvals.
- Must not call Slack, email, firewall, dry-run adapter, or real integrations.
- Must not consume or process `playbook_executions`.
- Must not update execution status beyond initial `pending` insert.
- Must not change existing queue, approval, incident, protected-target, or adapter behavior.
- Must preserve all existing ingest/detection/correlation tests.

## Test Strategy

### Store Tests

Add tests for idempotent pending execution creation:

- creates a pending row for a known playbook and alert
- returns execution ID on first insert
- returns `None` or duplicate marker on repeated insert for same `(playbook_id, alert_id)`
- creates separate rows for same alert with different playbooks
- creates separate rows for same playbook with different alerts
- does not update an existing execution row
- does not touch queue or response action log tables

If adding the unique index:

- schema applies cleanly on a fresh DB
- duplicate insert is safely handled without leaking DB errors

### Orchestrator Tests

Add tests for `create_pending_executions_for_committed_alerts`:

- no alerts returns empty results
- non-dict alert entries are skipped
- alert entries without `alert_id` are skipped
- no matching playbooks creates no executions
- one matching enabled playbook creates one pending execution
- multiple matching enabled playbooks create multiple pending executions
- disabled playbooks do not create executions
- repeated orchestrator call does not duplicate executions
- matching exception is logged and does not raise to caller
- insert exception is logged and result marks error without executing anything

### No-Execution Tests

Use mocks where appropriate to prove forbidden paths are not called:

- no SOAR queue enqueue helper is called by playbook orchestrator
- no playbook executor is imported or called
- no `update_execution_status` call occurs
- no approval creation occurs
- no adapter/integration function is called
- no `response_actions_queue` rows are created
- no `response_actions_log` rows are created

### Ingest Regression Tests

Extend only minimally to verify:

- playbook scheduling happens after commit
- scheduling failure does not fail ingest response
- existing SOAR queue enqueue behavior remains unchanged
- existing incident post-commit behavior remains unchanged

Run the six pipeline regression tests after any implementation step touching ingest routes.

## Risks/Stop Conditions

- Stop if implementation requires detection or correlation refactors.
- Stop if playbook matching must run before `conn.commit()`.
- Stop if idempotency cannot be guaranteed without a broad schema change.
- Stop if execution records need a worker or executor to be useful.
- Stop if queue enqueueing becomes necessary.
- Stop if approvals or integrations become necessary.
- Stop if route changes require a broad ingest refactor.
- Stop if existing SOAR queue or incident behavior changes.
