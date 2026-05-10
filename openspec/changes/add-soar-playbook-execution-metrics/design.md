# Design: SOAR Playbook Execution Metrics

## Proposed architecture
Add a small read-only backend route for aggregated SOAR playbook execution metrics. The route should query existing `playbook_executions` records and, only where safe, existing approval linkage data. It must not call the playbook executor, adapter registry execution paths, SOAR queue worker, ingest pipeline, detection engine, or correlation engine.

Recommended endpoint:

```http
GET /metrics/playbooks
```

The endpoint should return a stable JSON object suitable for backend tests and future frontend consumption. Exact field names may follow existing project API conventions, but the response should be explicit enough that consumers do not need to infer status buckets from raw rows.

## Files likely to change during implementation
- `routes/metrics_routes.py` or the existing metrics route module if one already exists.
- `siem_backend.py` only if route registration is centralized there.
- `core/playbook_store.py` or a new narrow metrics helper only if route-level SQL would not match local patterns.
- `tests/test_playbook_metrics_routes.py` or an existing route test file if that better matches project convention.

No frontend, schema, executor, adapter, SOAR queue, ingest, detection, or correlation files should change for the initial implementation.

## API endpoint behavior
`GET /metrics/playbooks` should:
- Require authentication using existing route auth patterns.
- Allow analyst and super-admin read access unless existing metrics route conventions require a narrower role.
- Deny viewer access if current SOAR/playbook visibility patterns deny viewers.
- Return HTTP 200 with aggregate metrics.
- Perform read-only database queries only.
- Avoid execution, scheduling, queue enqueueing, adapter calls, and external network calls.

Example response shape:

```json
{
  "total_executions": 12,
  "by_status": {
    "pending": 2,
    "running": 0,
    "awaiting_approval": 1,
    "success": 6,
    "failed": 2,
    "abandoned": 1
  },
  "by_playbook_id": [
    {
      "playbook_id": "pb_block_and_notify",
      "total": 7,
      "by_status": {
        "pending": 1,
        "running": 0,
        "awaiting_approval": 1,
        "success": 4,
        "failed": 1,
        "abandoned": 0
      }
    }
  ],
  "recent": {
    "window_hours": 24,
    "success": 3,
    "failed": 1
  },
  "approval_gated": {
    "awaiting_approval": 1,
    "with_linked_approval": 2
  }
}
```

The endpoint should include all known status keys even when a count is zero. This keeps the contract stable for tests and future UI work.

## Metrics definitions
- `total_executions`: Count of all rows in `playbook_executions`.
- `by_status`: Count of executions for each known playbook execution status.
- `by_playbook_id`: Count of executions grouped by playbook id, with per-status breakdowns where practical.
- `recent.success`: Count of executions with `status = 'success'` and a completion or update timestamp inside the documented recent window.
- `recent.failed`: Count of executions with `status = 'failed'` and a completion or update timestamp inside the documented recent window.
- `approval_gated.awaiting_approval`: Count of executions currently in `awaiting_approval`.
- `approval_gated.with_linked_approval`: Count of executions that have linked approval requests, if existing approval schema links allow this without mutation or expensive ambiguous joins.

If the current schema does not expose a reliable timestamp for recent metrics, implementation should use the safest existing timestamp field and document it in the response or route tests. Do not add schema solely for this first read-only metrics endpoint unless query correctness is impossible without it.

## Auth and permission expectations
- Use existing token/session authentication helpers.
- Follow the role pattern already used by playbook read APIs.
- Analysts and super-admins should be able to read metrics if that matches current playbook visibility.
- Unauthenticated requests should return the existing unauthorized response shape.
- Viewers should be forbidden if they are forbidden from playbook visibility routes.

## Safety boundaries
- Read-only database access.
- No mutation of playbook definitions, playbook executions, approval requests, approval events, SOAR queue rows, alerts, incidents, or audit logs.
- No playbook executor invocation.
- No retry, abandon, or resume behavior.
- No queue enqueueing or worker processing.
- No adapter execution.
- No real integrations.
- No network calls.
- No daemon, scheduler, or background worker.
- No ingest, detection, or correlation changes.

## Failure behavior
- Invalid query parameters, if any are added, should return HTTP 400 using existing API error conventions.
- Internal query failures should return the project-standard 500 response and log the error.
- Unknown or legacy statuses should not break the endpoint. They may be included in an `unknown_statuses` field or ignored from the fixed `by_status` buckets while preserving `total_executions`.

## Test strategy
Add backend tests that verify:
- Authenticated analyst or super-admin can read `GET /metrics/playbooks`.
- Unauthenticated requests are rejected using existing auth behavior.
- Viewer access follows existing playbook read visibility rules.
- Empty data returns zero counts for every known status.
- Seeded executions produce correct `total_executions` and `by_status` counts.
- Seeded executions produce correct grouped counts by `playbook_id`.
- Recent success and failure counts respect the documented recent window.
- Approval-gated counts are returned correctly when linked approvals exist.
- The endpoint does not mutate `playbook_executions`, `approval_requests`, `response_actions_queue`, or `response_actions_log`.
- The endpoint does not call playbook executor or integration adapter execution paths.

## Risks and stop conditions
- Stop if implementation requires changing executor behavior.
- Stop if implementation requires queue, ingest, detection, or correlation changes.
- Stop if implementation requires real adapter calls, network calls, or secrets.
- Stop if approval-gated metrics cannot be computed unambiguously from existing read-only data; omit or narrow that portion rather than changing behavior.
- Stop if the query plan appears unsafe for existing expected data volume and no existing index supports the needed aggregation.
