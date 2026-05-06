## Problem

Detection alerts are now eligible for post-commit SOAR enqueueing through the
`alerts_created` return path and `enqueue_committed_alerts()`. However, every
detection function still calls `execute_response_action()` synchronously inside
the ingest transaction.

This creates temporary dual-path response behavior for detection alerts:

- synchronous execution inside `engines/detection_engine.py`
- post-commit enqueue through `routes/ingest_routes.py`
- later execution by the SOAR queue/worker path

The dual path was useful while wiring the queue safely, but it is no longer the
target architecture. Detection should create alert rows and return queue metadata
only. Response execution should happen through the SOAR queue/worker path after
the ingest transaction commits.

## Goal

Plan the safe removal of synchronous `execute_response_action()` calls from
detection functions only.

After implementation, detection-created alerts should:

- be inserted with `response_action` and initial `response_status`
- be returned in `alerts_created` with `alert_id`, `source_ip`, and
  `response_action`
- be enqueued post-commit by the existing route-level SOAR enqueue block
- have response execution and `response_actions_log` writes handled by the
  queue/worker path

## In scope

- Analyze every current `execute_response_action()` call site.
- Remove synchronous `execute_response_action()` calls from the 7 detection
  functions in `engines/detection_engine.py`.
- Remove the detection-engine import of `execute_response_action()` if it is no
  longer used there.
- Preserve the existing detection alert inserts and `alerts_created` return
  metadata.
- Define how `response_status` should behave when execution is deferred.
- Define how `response_actions_log` is preserved through the queued execution
  path instead of the detection transaction.
- Update tests that currently expect a synchronous `response_actions_log` row for
  detection-created alerts.
- Add regression coverage proving detection enqueues post-commit without
  synchronously executing actions.

## Out of scope

- No production implementation in this spec-only change.
- No test edits in this spec-only change.
- No frontend changes.
- No changes to `engines/correlation_engine.py`.
- No correlation alert queueing.
- No changes to queue schema.
- No playbooks.
- No incidents.
- No real firewall execution or external integrations.
- No manual alert execution behavior changes in `routes/alert_mutation_routes.py`.

## Current call-site inventory

`execute_response_action()` is currently defined in `core/ip_helpers.py` and called
from these production locations:

| Location | Count | Scope decision |
|---|---:|---|
| `engines/detection_engine.py` | 7 | In scope: remove synchronous calls |
| `engines/correlation_engine.py` | 2 | Out of scope: preserve behavior |
| `routes/alert_mutation_routes.py` | 1 | Out of scope: manual execution remains synchronous |

Detection functions that currently call it:

1. `_generate_failed_login_alerts_core`
2. `_generate_http_error_alerts_core`
3. `_generate_port_scan_alerts_core`
4. `_generate_password_spraying_alerts_core`
5. `_generate_successful_login_after_spray_alerts_core`
6. `_generate_application_exception_alerts_core`
7. `_generate_high_request_rate_alerts_core`

## Why this change is the right next step

The route-level enqueue path now runs after a successful ingest commit, which is
the correct transaction boundary for SOAR response work. Keeping synchronous
detection execution means every detection alert can produce duplicate response
side effects and duplicate audit semantics: one immediate `response_actions_log`
row from detection and one queued action intent for the worker.

Removing only the detection calls is the smallest useful step. It avoids touching
correlation return types, queue schema, frontend behavior, playbooks, incidents,
or real integrations.

## Success criteria

- `engines/detection_engine.py` no longer imports or calls
  `execute_response_action()`.
- The 7 detection functions still create alert rows and still return
  `alerts_created` entries with `alert_id`, `source_ip`, and `response_action`.
- Detection-created alerts remain visible to `enqueue_committed_alerts()` after
  route-level `conn.commit()`.
- No synchronous `response_actions_log` row is expected during detection tests.
- Queue/worker tests cover the audit-log write that replaces the old synchronous
  detection-side log write.
- Correlation tests and manual alert mutation tests continue to validate their
  existing synchronous behavior.
- No queue schema, correlation behavior, frontend behavior, playbook behavior, or
  incident behavior changes are included.
