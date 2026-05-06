## Problem

The SOAR queue, worker, and executor are fully implemented but completely disconnected from the ingest pipeline. No alert created by detection or correlation ever produces a queue entry. The queue is permanently empty until someone manually calls `enqueue_response_action()` in a test.

Before wiring enqueueing into the ingest routes, the enqueue orchestration logic needs to exist as a testable, standalone module — one that can accept alert dicts, call `enqueue_response_action()`, handle missing fields, log results, and surface failures cleanly. Attempting to add route integration and orchestrator logic in the same step conflates two concerns and makes regression isolation impossible.

## This change: Phase 1D-a

Define and implement the enqueue orchestration helper as a standalone, ingest-independent module. The module must be fully testable by calling it directly with sample alert dicts. No route handlers are modified. No detection functions are modified.

## Phase 1D-b (explicitly deferred)

Wiring the orchestrator into the ingest routes requires:
- Detection functions to surface `alert_id` and `response_action` in `alerts_created` return dicts (currently absent).
- All 4 route handlers to call the orchestrator after `conn.commit()`.
- Test updates for all detection function return shape assertions.

That is a separate change with its own spec entry. It is not implemented here.

## Why this split is the right next step

- The orchestrator has no dependency on route handlers, detection functions, or ingest transaction state. It only needs `enqueue_response_action()` and a committed connection.
- Testing it in isolation before connecting it to live ingest means any failure in route integration is unambiguously a route problem, not an orchestrator problem.
- Changing 7 detection functions and their tests at the same time as adding post-commit route wiring is too large a surface for a single safe implementation step.

## In scope

- `engines/soar_enqueue_orchestrator.py` with one public function: `enqueue_committed_alerts(alerts_created, conn)`.
- Handling for alert dicts missing required fields (`alert_id`, `source_ip`, `response_action`): skip with a warning log, do not raise.
- Logging for enqueue success and idempotent skips.
- Direct unit and integration tests for the orchestrator called with sample alert dicts.
- Confirming `enqueue_response_action()` idempotency behavior at the orchestrator level.

## Out of scope

- No changes to `routes/ingest_routes.py` (Phase 1D-b).
- No changes to any detection function in `engines/detection_engine.py` (Phase 1D-b).
- No changes to `engines/correlation_engine.py` or `engines/ingest_engine.py`.
- No changes to existing tests.
- No real firewall blocking, cloud API calls, or external integrations.
- No scheduler, systemd, or background worker deployment.
- No frontend UI changes.
- No playbooks, incidents, or cases.
- No schema changes.

## Risks

- **`enqueue_response_action()` interface assumption.** The orchestrator will call `enqueue_response_action(cur, alert_id, source_ip, action)`. Confirm the function signature and idempotency behavior match what is expected before implementing.
- **Flask context dependency.** Logging via `current_app.logger` requires Flask application context. Tests that call the orchestrator directly must push an app context or use a test app. Confirm this is consistent with how existing orchestration tests are structured.
- **Missing field behavior must be explicit.** If an alert dict is missing `alert_id`, the orchestrator must skip it with a warning — not raise. Raising would propagate to the route handler and convert a field-level data issue into a 500. This behavior must be covered by tests, not just documented.

## Success criteria

- `engines/soar_enqueue_orchestrator.py` exists with `enqueue_committed_alerts(alerts_created, conn)`.
- Called with a valid alert dict, the function writes a queue entry and returns a result list.
- Called with an alert dict missing `alert_id`, the function skips it without raising.
- Duplicate calls with the same alert dict produce no error and no duplicate queue entry.
- No existing test file is modified.
- No route handler is modified.
- No detection or correlation function is modified.
