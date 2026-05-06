# Proposal: Wire Post-Commit SOAR Enqueue into Ingest Routes

## What This Change Does

Connects `enqueue_committed_alerts()` — which already exists and is tested in
`engines/soar_enqueue_orchestrator.py` — to all four ingest route handlers in
`routes/ingest_routes.py`. After each successful `conn.commit()`, the route calls
`enqueue_committed_alerts(alerts_created, conn)` and commits the resulting queue
rows. If the enqueue fails, the failure is logged and the route still returns 201.
The committed alert and event rows are never affected by enqueue failures.

For `enqueue_committed_alerts` to receive usable data, all 7 detection functions in
`engines/detection_engine.py` must be updated to include `alert_id` and
`response_action` in their returned alert dicts. Both values are already in local
scope at the `alerts_created.append()` call in each function; the change is purely
additive.

## Background

Phase 1D-a (spec: `add-post-commit-soar-enqueue`) built and tested the
`enqueue_committed_alerts()` orchestrator in isolation. That work deliberately
stopped before touching any route or detection code. This spec covers the wiring
step described in Phase 1D-b of that prior spec.

The goal is to get real alert data flowing into `response_actions_queue` after every
successful ingest commit, without touching the ingest transaction, detection logic,
or correlation logic.

## What Changes

| File | Change |
|---|---|
| `engines/detection_engine.py` | Add `alert_id` and `response_action` to `.append()` dict in all 7 detection functions |
| `routes/ingest_routes.py` | Call `enqueue_committed_alerts` + second `conn.commit()` after existing `conn.commit()` in all 4 routes, inside a `try/except` |
| `tests/test_wire_soar_enqueue_post_commit.py` | New test file covering route-level enqueue wiring |

## What Does Not Change

- `engines/detection_engine.py` function signatures
- `engines/detection_engine.py` detection logic, SQL, thresholds, response action execution
- `engines/correlation_engine.py` (any file, any line)
- `engines/ingest_engine.py` (any file, any line)
- `engines/soar_enqueue_orchestrator.py`
- `core/ip_helpers.py`
- All existing test files
- The HTTP response shape returned by each ingest route (the `alerts_created` key
  in the JSON response will now contain richer dicts, but the field names that were
  there before remain)
- Transaction ownership — `conn`/`cur` ownership does not change; detection and
  correlation functions still receive the caller's cursor

## Correlation Alerts — Explicitly Deferred

`generate_correlated_activity_alerts` and `generate_targeted_correlation_alerts`
return `False`/`True`, not lists. `ingest_engine.py` does not collect their results
into `alerts_created`. Wiring correlation alert enqueueing requires changing those
function return types, which is a separate phase. Correlation enqueueing is out of
scope here.

## Success Criteria

1. All 4 ingest routes call `enqueue_committed_alerts` after `conn.commit()`.
2. Enqueue failure produces a logged error but returns 201 with committed data.
3. No enqueue attempt occurs on the rollback path (exception before `conn.commit()`).
4. `response_actions_queue` receives rows after a real ingest request that triggers
   a detection alert.
5. Full existing pytest suite passes unchanged (`116 passed, 2 warnings` baseline).
