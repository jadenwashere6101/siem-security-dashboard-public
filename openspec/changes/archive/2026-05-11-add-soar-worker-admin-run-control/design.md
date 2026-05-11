# Design: SOAR Worker Admin Run Control

---

## 1. Endpoint

Add:

```text
POST /admin/soar/worker/run-once
```

This endpoint triggers one bounded call to:

```python
process_batch(conn, limit=batch_size, executor=SimulationExecutor())
```

It must not start a loop, background thread, daemon, scheduler, or subprocess.
The request returns after the single batch completes.

---

## 2. Auth and Authorization

Use the existing admin route pattern:

```python
@login_required
@super_admin_required
```

Expected behavior:

- unauthenticated -> `401`
- viewer/analyst -> `403`
- super admin -> `200`

The endpoint belongs under the existing admin backend surface because it mutates
queue rows by running normal worker processing.

---

## 3. Execution Mode

First version is simulation-only.

Rules:

- always instantiate `SimulationExecutor()`
- do not read `SOAR_EXECUTION_MODE` for this endpoint
- do not accept a request `mode` field
- if a client sends `mode=real`, return `400` or ignore with an explicit
  simulation-only response; prefer `400` to make the safety boundary visible
- do not instantiate `AdapterBackedExecutor`
- do not import or use real adapters from this endpoint

Rationale:

The UI/API control is higher risk than the CLI because it is reachable from the
web app. Real adapter execution should require a separate follow-up spec with
approval gates, stronger logging, and operational controls.

---

## 4. Batch Size

Defaults:

```python
DEFAULT_ADMIN_RUN_BATCH_SIZE = 10
MAX_ADMIN_RUN_BATCH_SIZE = 25
```

Request body:

```json
{
  "batch_size": 10
}
```

Validation:

- missing body -> default batch size
- missing `batch_size` -> default batch size
- non-integer -> `400`
- less than 1 -> `400`
- greater than max -> clamp to max or return `400`

Recommendation:

- clamp excessive values to the hard max and include both requested and effective
  sizes in the response

This gives admins a forgiving UI while still enforcing a hard safety ceiling.

---

## 5. Response Shape

Response:

```json
{
  "mode": "simulation",
  "requested_batch_size": 100,
  "batch_size": 25,
  "started_at": "2026-05-06T12:00:00Z",
  "completed_at": "2026-05-06T12:00:01Z",
  "summary": {
    "processed": 3,
    "success": 2,
    "failed": 0,
    "skipped": 1,
    "requeued": 0
  },
  "results": [
    {
      "queue_id": 123,
      "prior_status": "running",
      "new_status": "success",
      "outcome": "success",
      "retryable": false,
      "retry_count": 0,
      "max_retries": 3,
      "error_code": null,
      "reason": null,
      "message": "Simulated IP block for 203.0.113.10"
    }
  ]
}
```

Notes:

- do not include secrets
- do not include adapter config
- do not include environment variables
- result rows are the existing worker result dicts
- empty queue returns `processed: 0` and `results: []`

---

## 6. Summary Aggregation

Reuse the same summary concept as `scripts/soar_worker_run.py`:

```python
{
    "processed": len(results),
    "success": sum(1 for row in results if row.get("outcome") == "success"),
    "failed": sum(1 for row in results if row.get("outcome") == "failed"),
    "skipped": sum(1 for row in results if row.get("outcome") == "skipped"),
    "requeued": sum(1 for row in results if row.get("outcome") == "requeued"),
}
```

If the helper is shared, move it to a side-effect-free module only if that stays
small. Otherwise duplicate the small aggregation locally in the route to avoid
coupling the Flask route to CLI internals.

Do not call `scripts/soar_worker_run.py` from Flask.

---

## 7. Route Placement

Recommended first placement:

```text
routes/admin_routes.py
```

Rationale:

- existing admin queue visibility endpoints live there
- existing auth guard and DB connection pattern are established
- avoids new Blueprint registration churn

If admin routes become too large later, extract all SOAR admin routes in a
separate refactor.

---

## 8. Audit and Logging

If existing `log_audit_event()` fits cleanly, write an audit event such as:

```text
SOAR_WORKER_RUN_ONCE
```

Audit details should include:

- actor username
- role
- request path/method
- source IP
- requested batch size
- effective batch size
- processed count
- summary counts
- mode: `simulation`

Do not include:

- secrets
- environment variables
- raw stack traces
- adapter configuration

Also log a concise server-side INFO event with actor, batch size, and summary.

---

## 9. Queue Mutation Boundary

This endpoint is not read-only, but mutation is limited to normal worker
processing.

Allowed:

- pending row claimed and processed by `process_batch`
- queue status transitions caused by `process_next_action`
- worker audit rows in `response_actions_log`

Forbidden:

- direct `UPDATE response_actions_queue` in route code
- retry/replay specific queue ID
- delete queue item
- reset failed row
- stale recovery
- worker loop/daemon behavior

The route must not call queue transition helpers directly. It calls
`process_batch()` only.

---

## 10. Error Handling

On validation errors:

- return `400`
- include a concise error message

On unexpected worker/DB errors:

- log server-side exception
- return `500` with generic error
- do not expose raw exception details

If `process_batch()` raises after processing some rows, committed row state may
already reflect worker transitions because `process_next_action()` commits per
item. The response should be a generic failure. A later operational-hardening
phase can add richer partial-failure reporting.

---

## 11. Tests

Recommended new file:

```text
tests/test_soar_worker_admin_run_control.py
```

Coverage:

- unauthenticated `POST /admin/soar/worker/run-once` -> `401`
- viewer/analyst -> `403`
- super admin with empty body -> `200`
- default batch size is used
- excessive batch size is clamped to max
- invalid batch size returns `400`
- request containing `"mode": "real"` returns `400`
- response shape includes `mode`, `summary`, `results`, timestamps, requested and
  effective batch size
- empty queue returns `processed: 0`
- seeded pending rows are processed by normal worker flow
- terminal rows are not mutated
- endpoint uses `SimulationExecutor` even if environment has
  `SOAR_EXECUTION_MODE=real`
- audit event is written if implemented

Patch DB connections in `routes.admin_routes` using the established admin route
test pattern.

---

## 12. Stop Conditions

Stop implementation and re-plan if:

- route needs real adapter execution
- UI button is being added in the same change
- batch run needs background threading
- request handling would block for unbounded time
- queue schema changes appear necessary
- route code starts calling queue mutation helpers directly
- implementation touches ingest/detection/correlation
- implementation needs scheduler/systemd behavior

