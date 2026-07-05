## 10. Phase 10 - Retention, Archive, and Reporting Verification

> Parent roadmap task reference: tasks 10.1–10.6 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.

### Pre-Implementation

- [x] 10.0.1 Confirm Phases 1–9 are implemented and their respective tests pass.
- [x] 10.0.2 Confirm `soar_response_decisions` and `soar_response_outcome_events` tables exist in the schema.
- [x] 10.0.3 Confirm latest-outcome query helpers exist and are callable.

### Retention Window Definition

- [x] 10.1 Define and document the default retention window for canonical decisions and outcome events (e.g., 90 days, 365 days, or indefinite-by-default until a policy is set).
- [x] 10.2 Define and document the archive criteria: which events are eligible for archival after the retention threshold, and what minimum fields must be preserved in the archive record.
- [x] 10.3 Document that `external_executed = true` events (real execution evidence) must be preserved as audit records and not deleted during routine archival.

### Archive Verification

- [x] 10.4 Verify that the archive criteria preserve at minimum: decision id, SOAR correlation id, selected action, decision source, final execution mode/state, execution booleans (final), outcome summary (final), and enough related ids (alert, incident, queue, playbook execution, approval request) to answer the primary analyst question.
- [x] 10.5 Document the archive preservation contract in `design.md` or a dedicated document; confirm with this spec before implementation.

### Reporting Query

- [x] 10.6 Add a helper or SQL query that answers the primary analyst question given an `alert_id`, `incident_id`, or `soar_correlation_id` as input.
- [x] 10.7 Verify the query returns: selected action, decision source, execution actor, execution mode/state, execution booleans, outcome summary, playbook execution id, approval request id, and SOAR correlation id.
- [x] 10.8 Verify the query works for both live canonical rows and backfill/inferred rows (decision_source = migration).

### Performance Verification

- [x] 10.9 Generate or seed representative event volume: at least 10,000 decisions with ~5 events each (≥50,000 events) in the test database.
- [x] 10.10 Verify `get_latest_outcome_for_decision(conn, decision_id)` executes in acceptable time (< 50 ms) at representative volume.
- [x] 10.11 Verify `get_latest_outcomes_for_alerts_bulk(conn, alert_ids)` with a 100-item batch executes in acceptable time.
- [x] 10.12 Verify `get_latest_outcomes_for_approvals_bulk(conn, approval_ids)` with a 50-item batch executes in acceptable time.
- [x] 10.13 Record query plan or timing output for the most expensive query as part of verification.

### Metrics and Retention Window Documentation

- [x] 10.14 Verify the `/metrics/playbooks`, `/metrics/notifications`, `/metrics/incidents`, and `/metrics/approvals` endpoints either include archived summaries in aggregation or include clear documentation of the live retention window.
- [x] 10.15 If a metrics endpoint only counts live events, document that boundary explicitly in the API response description or inline documentation.

### Validation

- [x] 10.16 Run `openspec validate add-response-outcome-retention-e2e --strict` and confirm valid.
- [x] 10.17 Run `git diff --check` and confirm no whitespace errors.

---

## 11. Phase 11 - API/Read-Model Integration Tests

> Parent roadmap task reference: tasks 11.1–11.12 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.

### Pre-Implementation

- [x] 11.0.1 Confirm Phases 1–9 are implemented and all phase tests pass.
- [x] 11.0.2 Confirm `postgres_db` fixture and test database connection are available.
- [x] 11.0.3 Identify whether `tests/test_response_outcome_e2e.py` already exists or needs to be created.

### API/Read-Model Lifecycle Tests

- [x] 11.1 Add API/read-model integration test for observed-only alert lifecycle: create alert with no decision/event → verify `response_outcome: null` from alert API.
- [x] 11.2 Add API/read-model integration test for detection-selected simulated queue action: alert → decision → `simulation/succeeded/simulated=true` event → verify API response shape.
- [x] 11.3 Add API/read-model integration test for manual tracking-only blocklist action: alert → tracking-only decision → `tracking_only/succeeded/tracking_recorded=true` event → verify `"Tracking only"` mode, `external_executed=false` in API response.
- [x] 11.4 Add API/read-model integration test for playbook simulation step sequence: playbook execution → execution-level decision → step events (simulation) → verify API returns step events attached to execution-level decision.
- [x] 11.5 Add API/read-model integration test for playbook awaiting approval: playbook execution → `awaiting_approval` event → verify `execution_state = awaiting_approval` in API response.
- [x] 11.6 Add API/read-model integration test for approval denied/expired blocking execution: approval request → deny or expire → `blocked/approval_denied` event → verify `execution_state = blocked`, `reason_code = approval_denied` in API response.
- [x] 11.7 Add API/read-model integration test for notification simulated delivery: notification delivery → decision with `simulation/selected` → `simulation/succeeded/simulated=true` event → verify simulated mode in API response.
- [x] 11.8 Add API/read-model integration test for guarded real notification success with seeded real execution evidence → `real/succeeded/external_executed=true` event → verify `external_executed = true` in API response.
- [x] 11.9 Add API/read-model integration test for real-capable notification blocked/fail-closed path: seeded `real/failed/external_executed=false` event → verify `external_executed = false` and `execution_state = failed` in API response.
- [x] 11.10 Add API/read-model integration test for cross-surface canonical facts: one decision/event linked to a source IP and an incident → verify Source-IP Context API and SOC Command Center metrics API return the same canonical outcome facts.

### Regression Tests

- [x] 11.11 Add regression test: simulated actions never shown as real executed. For every `simulated = true` event in the test dataset, assert that `external_executed = false` in all API responses for that event.
- [x] 11.12 Add regression test: tracking-only blocklist entries never shown as firewall enforcement. For every `tracking_recorded = true` event, assert `external_executed = false` in all API responses, and assert the canonical label from the API is `"Tracking only"`, not `"Real executed"`.

### Validation

- [x] 11.13 Run `python3 -m pytest tests/test_response_outcome_e2e.py -v` (or equivalent); confirm all 12 API/read-model integration and regression tests pass with zero failures.
- [x] 11.14 Confirm seeded canonical-row tests are classified as API/read-model integration tests, not true writer/orchestrator E2E tests, and no test uses hacks that would pass even if simulated work were relabeled as real or tracking-only were relabeled as enforcement.
- [x] 11.15 Run `openspec validate add-response-outcome-retention-e2e --strict` and confirm valid.
- [x] 11.16 Run `git diff --check` and confirm no whitespace errors.
