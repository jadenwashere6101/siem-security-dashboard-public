## 10. Phase 10 - Retention, Archive, and Reporting Verification

> Parent roadmap task reference: tasks 10.1–10.6 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.

### Pre-Implementation

- [ ] 10.0.1 Confirm Phases 1–9 are implemented and their respective tests pass.
- [ ] 10.0.2 Confirm `soar_response_decisions` and `soar_response_outcome_events` tables exist in the schema.
- [ ] 10.0.3 Confirm latest-outcome query helpers exist and are callable.

### Retention Window Definition

- [ ] 10.1 Define and document the default retention window for canonical decisions and outcome events (e.g., 90 days, 365 days, or indefinite-by-default until a policy is set).
- [ ] 10.2 Define and document the archive criteria: which events are eligible for archival after the retention threshold, and what minimum fields must be preserved in the archive record.
- [ ] 10.3 Document that `external_executed = true` events (real execution evidence) must be preserved as audit records and not deleted during routine archival.

### Archive Verification

- [ ] 10.4 Verify that the archive criteria preserve at minimum: decision id, SOAR correlation id, selected action, decision source, final execution mode/state, execution booleans (final), outcome summary (final), and enough related ids (alert, incident, queue, playbook execution, approval request) to answer the primary analyst question.
- [ ] 10.5 Document the archive preservation contract in `design.md` or a dedicated document; confirm with this spec before implementation.

### Reporting Query

- [ ] 10.6 Add a helper or SQL query that answers the primary analyst question given an `alert_id`, `incident_id`, or `soar_correlation_id` as input.
- [ ] 10.7 Verify the query returns: selected action, decision source, execution actor, execution mode/state, execution booleans, outcome summary, playbook execution id, approval request id, and SOAR correlation id.
- [ ] 10.8 Verify the query works for both live canonical rows and backfill/inferred rows (decision_source = migration).

### Performance Verification

- [ ] 10.9 Generate or seed representative event volume: at least 10,000 decisions with ~5 events each (≥50,000 events) in the test database.
- [ ] 10.10 Verify `get_latest_outcome_for_decision(conn, decision_id)` executes in acceptable time (< 50 ms) at representative volume.
- [ ] 10.11 Verify `get_latest_outcomes_for_alerts_bulk(conn, alert_ids)` with a 100-item batch executes in acceptable time.
- [ ] 10.12 Verify `get_latest_outcomes_for_approvals_bulk(conn, approval_ids)` with a 50-item batch executes in acceptable time.
- [ ] 10.13 Record query plan or timing output for the most expensive query as part of verification.

### Metrics and Retention Window Documentation

- [ ] 10.14 Verify the `/metrics/playbooks`, `/metrics/notifications`, `/metrics/incidents`, and `/metrics/approvals` endpoints either include archived summaries in aggregation or include clear documentation of the live retention window.
- [ ] 10.15 If a metrics endpoint only counts live events, document that boundary explicitly in the API response description or inline documentation.

### Validation

- [ ] 10.16 Run `openspec validate add-response-outcome-retention-e2e --strict` and confirm valid.
- [ ] 10.17 Run `git diff --check` and confirm no whitespace errors.

---

## 11. Phase 11 - End-to-End Tests

> Parent roadmap task reference: tasks 11.1–11.12 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.

### Pre-Implementation

- [ ] 11.0.1 Confirm Phases 1–9 are implemented and all phase tests pass.
- [ ] 11.0.2 Confirm `postgres_db` fixture and test database connection are available.
- [ ] 11.0.3 Identify whether `tests/test_response_outcome_e2e.py` already exists or needs to be created.

### End-to-End Lifecycle Tests

- [ ] 11.1 Add end-to-end test for observed-only alert lifecycle: create alert with no decision/event → verify `response_outcome: null` from alert API.
- [ ] 11.2 Add end-to-end test for detection-selected simulated queue action: alert → decision → `simulation/succeeded/simulated=true` event → verify API response shape.
- [ ] 11.3 Add end-to-end test for manual tracking-only blocklist action: alert → tracking-only decision → `tracking_only/succeeded/tracking_recorded=true` event → verify `"Tracking only"` mode, `external_executed=false` in API response.
- [ ] 11.4 Add end-to-end test for playbook simulation step sequence: playbook execution → execution-level decision → step events (simulation) → verify API returns step events attached to execution-level decision.
- [ ] 11.5 Add end-to-end test for playbook awaiting approval: playbook execution → `awaiting_approval` event → verify `execution_state = awaiting_approval` in API response.
- [ ] 11.6 Add end-to-end test for approval denied/expired blocking execution: approval request → deny or expire → `blocked/approval_denied` event → verify `execution_state = blocked`, `reason_code = approval_denied` in API response.
- [ ] 11.7 Add end-to-end test for notification simulated delivery: notification delivery → decision with `simulation/selected` → `simulation/succeeded/simulated=true` event → verify simulated mode in API response.
- [ ] 11.8 Add end-to-end test for guarded real notification success with mocked provider: notification delivery with explicit real execution evidence → `real/succeeded/external_executed=true` event (mocked adapter call) → verify `external_executed = true` in API response.
- [ ] 11.9 Add end-to-end test for real-capable notification blocked/fail-closed path: adapter fail-closed result → `real/failed/external_executed=false` event → verify `external_executed = false` and `execution_state = failed` in API response.
- [ ] 11.10 Add end-to-end test for cross-surface canonical facts: one decision/event linked to a source IP and an incident → verify Source-IP Context API and SOC Command Center metrics API return the same canonical outcome facts.

### Regression Tests

- [ ] 11.11 Add regression test: simulated actions never shown as real executed. For every `simulated = true` event in the test dataset, assert that `external_executed = false` in all API responses for that event.
- [ ] 11.12 Add regression test: tracking-only blocklist entries never shown as firewall enforcement. For every `tracking_recorded = true` event, assert `external_executed = false` in all API responses, and assert the canonical label from the API is `"Tracking only"`, not `"Real executed"`.

### Validation

- [ ] 11.13 Run `python3 -m pytest tests/test_response_outcome_e2e.py -v` (or equivalent); confirm all 12 end-to-end and regression tests pass with zero failures.
- [ ] 11.14 Confirm no test uses hacks that would pass even if simulated work were relabeled as real or tracking-only were relabeled as enforcement.
- [ ] 11.15 Run `openspec validate add-response-outcome-retention-e2e --strict` and confirm valid.
- [ ] 11.16 Run `git diff --check` and confirm no whitespace errors.
