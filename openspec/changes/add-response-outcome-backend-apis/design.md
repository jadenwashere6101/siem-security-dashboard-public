# Design: Response Outcome Backend APIs

## Boundary

This child change is backend API contract work only. It does not change canonical outcome writers, migrations, frontend screens, tests until implementation, SOAR runtime behavior, or real execution policy.

Alert list/detail API response-outcome work is already implemented and verified in the parent roadmap context. This child starts after that slice and covers the remaining Phase 6 backend surfaces.

## Shared API Contract

Entity routes that return one or more domain records should add a `response_outcome` key to each returned record where a canonical outcome can be associated with that record.

Rules:
- Preserve all legacy fields.
- Add fields only; do not rename or remove existing fields.
- Always include `response_outcome` on updated entity payloads.
- Return `response_outcome: null` when no canonical outcome exists.
- Use `core.soar_response_outcomes.serialize_latest_outcome(...)` for single-record lookups where suitable.
- Use bulk lookup helpers or route-local single-query batching for list endpoints.
- Do not derive canonical truth from legacy fields when a canonical helper can resolve it.
- Do not call adapters, mutate stale state, enqueue work, expire approvals, retry playbooks, or update blocklist state while serializing read responses.

The `response_outcome` shape should remain aligned with the parent Decision 6 serializer shape:
- `soar_correlation_id`
- `decision_id`
- `latest_outcome_event_id`
- `selected_action`
- `decision_source`
- `execution_actor`
- `execution_mode`
- `execution_state`
- `external_executed`
- `tracking_recorded`
- `simulated`
- `outcome_summary`
- `reason_code`
- related ids
- timestamps

## Route/File Mapping

### Response log API

Current candidate file: `routes/alerts_events_routes.py`.

There is no obvious dedicated response-log route in the current route decorator inventory. During implementation, inspect whether response log rows are embedded in alert detail, admin, or another route. If no public response log API exists, document the route as deferred and do not create a new endpoint in this child change.

Expected behavior when a response log route exists:
- Include `response_outcome` on each response log record.
- Resolve by `response_action_log_id` through canonical events or by linked `decision_id`/`soar_correlation_id` where present.
- Preserve existing log fields such as action, status, details, timestamps, and alert linkage.

### SOAR queue API

Current file: `routes/admin_routes.py`.

Existing routes:
- `GET /admin/soar/queue/status`
- `GET /admin/soar/queue/recent`
- `GET /admin/soar/queue/<queue_id>`

Expected behavior:
- Add canonical outcome counts or summary fields to queue status where it reports aggregate queue state.
- Add `response_outcome` to recent/list queue rows.
- Add `response_outcome` to queue detail.
- Preserve queue status, action, retry, approval, playbook, log, and legacy fields.
- Avoid N+1 outcome lookups for recent/list responses.

### Playbook execution API

Current file: `routes/playbook_routes.py`.

Existing routes:
- `GET /playbook-executions`
- `GET /playbook-executions/<execution_id>`

Expected behavior:
- Add execution-level `response_outcome` to each execution payload.
- Add ordered canonical outcome timeline or step-level canonical outcome payloads to execution detail where available.
- Step-level payloads must attach to the execution-level decision already created by Phase 5; this child must not create child decisions.
- Preserve `steps_log`, status, lease, retry, dead-letter, audit, and playbook metadata fields.
- Avoid N+1 outcome lookups in the execution list.

### Approval API

Current file: `routes/approval_routes.py`.

Existing routes:
- `GET /approvals`
- `GET /approvals/<approval_id>`
- `POST /approvals/<approval_id>/decision`

Expected behavior:
- Add `response_outcome` to approval list and detail payloads.
- Add canonical approval outcome fields to decision responses where an approval decision writes or links canonical outcome events.
- Preserve approval request fields, event history, queue/playbook linkage, status, and decision response shape.
- Avoid N+1 outcome lookups in approval lists.

### Notification delivery API

Current file: `routes/notification_delivery_routes.py`.

Existing routes:
- `GET /notification-deliveries`
- `GET /notification-deliveries/<attempt_id>`

Expected behavior:
- Add `response_outcome` to delivery list and detail payloads.
- Include canonical mode/state booleans from latest outcome where available.
- Preserve delivery `mode`, `status`, provider, adapter, action, failure, circuit breaker, metadata, and linkage fields.
- Do not relabel legacy delivery `mode`/`status`; canonical fields are additive.
- Avoid N+1 outcome lookups in delivery lists.

### Incident timeline API

Current file: `routes/incident_routes.py`.

Existing routes:
- `GET /incidents`
- `GET /incidents/<incident_id>`
- `GET /incidents/<incident_id>/timeline`

Expected behavior:
- Add incident-level `response_outcome` to incident list and detail payloads.
- Add canonical outcome timeline entries to incident timeline without mutating incident state.
- Preserve all existing timeline entries and incident fields.
- Canonical entries should be clearly typed so clients can distinguish them from legacy incident, alert, playbook, notification, approval, and audit events.
- Avoid N+1 outcome lookups in incident lists.

### Source-IP context API

Current file: `routes/source_ip_context_routes.py`.

Existing route:
- `GET /source-ip-context`

Expected behavior:
- Add recent canonical outcomes for the requested source IP.
- Add counts grouped by `execution_mode`, `execution_state`, `external_executed`, `tracking_recorded`, and `simulated`.
- Preserve existing alert, incident, queue, blocklist, reputation, and playbook context fields.
- Use a bounded recent outcome query and avoid per-related-record outcome lookups.

### Attack Map/source-IP popup API

Current candidate file: `routes/alerts_events_routes.py`.

No dedicated Attack Map popup backend route was found in the current route decorator inventory. The frontend may derive popup data from alert/event/search/source-IP context routes. During implementation, document the exact backend route used by the popup if one exists. If no dedicated backend route exists, skip this task and record that Attack Map backend work is deferred to the frontend/API integration phase.

### Blocklist API

Current file: `routes/blocklist_routes.py`.

Existing routes:
- `GET /blocked-ips`
- `POST /blocked-ips`
- `PATCH /blocked-ips/<block_id>/unblock`

Expected behavior:
- Add `response_outcome` or tracking-only provenance fields to blocklist records returned by list/detail-equivalent responses.
- Preserve blocklist fields, status normalization, expiry behavior, and unblock behavior.
- Do not imply firewall enforcement.
- If canonical linkage cannot directly resolve by blocked IP id because schema linkage is deferred, resolve conservatively by alert/source IP where available or return `response_outcome: null`.

### Metrics and SOC Command Center aggregation

Current file: `routes/metrics_routes.py`.

Existing routes:
- `GET /metrics/playbooks`
- `GET /metrics/notifications`
- `GET /metrics/incidents`
- `GET /metrics/approvals`

There is no dedicated SOC Command Center backend route in the current route inventory. SOC Command Center should continue aggregating from existing metrics endpoints.

Expected behavior:
- Add canonical outcome count fields to the four existing metrics endpoints.
- Do not create a new SOC route.
- Preserve every existing metric field.
- Counts should be grouped by:
  - `execution_mode`
  - `execution_state`
  - `external_executed`
  - `tracking_recorded`
  - `simulated`
- Queries must be read-only and must not call workers, adapters, provider health checks, or mutation helpers.

## Query Strategy

Implementation should prefer one of these patterns:
- Add reusable bulk helpers in `core/soar_response_outcomes.py` for route families that return many records.
- Use one route-local query with `WHERE <entity_id> = ANY(%s)` and map results back by id.
- Use aggregate SQL grouped directly from `soar_response_outcome_events` for metrics.

List endpoints must not call `serialize_latest_outcome(...)` once per row if that causes one query per returned record.

## Compatibility

Older records may not have canonical decisions/events. Updated entity payloads should still include `response_outcome: null` unless an existing compatibility helper can safely infer a canonical payload without ambiguous real-execution claims.

Legacy fields remain the compatibility contract for existing clients. Canonical fields are additive and must not change existing status values or response shapes beyond adding keys.

## Testing Strategy

Each updated route should have API contract tests that assert:
- legacy fields are preserved.
- `response_outcome` key is present.
- `response_outcome` is `null` when canonical outcome rows are absent.
- canonical payload shape matches the shared serializer when rows exist.
- list endpoints use bulk/batched lookup behavior or otherwise avoid N+1 queries.
- metrics endpoints include additive canonical count fields with zero buckets where appropriate.
- no read route mutates database state or calls adapter/worker execution paths.
