# Design: Response Outcome Retention and API Integration Tests

## Boundary

This child change is verification and test work only. It does not change canonical outcome writers, UI components, migrations, schema, or real execution policy. It may add retention-boundary metadata to existing metrics API responses so metrics document the live retention window required by Phase 10. All phases before this (1–9) must be implemented before API/read-model integration tests verify canonical lifecycle shapes.

## Retention Design (Phase 10)

### Retention window definition

**Default policy (implemented):** indefinite live retention until an operator sets `SIEM_OUTCOME_RETENTION_DAYS`; the retention helper reads that environment variable with safe positive-integer parsing. Recommended production starting point after policy review: **365 days**.

Full operator documentation: `docs/soar-response-outcome-retention.md`.

The canonical model introduces two append-only tables:
- `soar_response_decisions` — one row per selected response.
- `soar_response_outcome_events` — one append per lifecycle transition.

Decisions and events are audit data. The default retention policy must be documented before production deployment. It must answer:

1. What is the live/queryable retention window (e.g., 90 days, 365 days)?
2. What happens to events older than the window — deleted, archived to cold storage, or summarized?
3. What minimum fields must be preserved in archive for the primary analyst question to still be answerable?

Required preserved archive fields:
- `decision_id`
- `soar_correlation_id`
- `selected_action`
- `decision_source`
- `final/latest execution_mode`
- `final/latest execution_state`
- `external_executed` (final)
- `tracking_recorded` (final)
- `simulated` (final)
- `outcome_summary` (final)
- Related ids: alert id, incident id, queue id, playbook execution id, approval request id

### Archive criteria

Events eligible for archival after the retention window:
- All events with `occurred_at` older than the retention threshold.
- Decision rows where all related events are archived and no live FK dependencies exist.

Events that must be preserved regardless:
- The final/terminal outcome event per decision (must not be deleted without archiving a summary row).
- Events with `external_executed = true` (real execution evidence; treat as audit records).

### Metrics and retention window documentation

Metrics endpoints that aggregate canonical outcome counts must either:
- Include archived summaries in their aggregation, OR
- Document clearly in the API response or inline documentation that counts only reflect the live retention window.

### Performance verification

For representative event volume (e.g., 10,000 decisions with 5 events each = 50,000 events), verify:
- `get_latest_outcome_for_decision(conn, decision_id)` executes in acceptable time (< 50 ms).
- `get_latest_outcomes_for_alerts_bulk(conn, alert_ids)` with a 100-alert batch executes in acceptable time.
- `get_latest_outcomes_for_approvals_bulk(conn, approval_ids)` with a 50-approval batch executes in acceptable time.

These can be verified with local test data or a synthetic seed script.

### Reporting query

Implemented as `get_response_outcome_traceability_report(conn, alert_id=..., incident_id=..., soar_correlation_id=...)` in `core/soar_response_outcomes.py`.

Add a helper or SQL query that answers the primary analyst question:
> "What happened, what response was selected, what playbook ran, and was anything actually executed?"

The query must:
- Accept an `alert_id`, `incident_id`, or `soar_correlation_id` as input.
- Return: selected action, decision source, execution actor, execution mode/state, execution booleans, outcome summary, playbook execution id, approval request id, SOAR correlation id.
- Work for both live and inferred-from-legacy (backfill) rows.

## API/Read-Model Integration Test Design (Phase 11)

### Test scope contract

These Phase 11 tests are API/read-model integration tests. They seed canonical decisions/events directly, then exercise Flask route handlers and real PostgreSQL reads to verify canonical `response_outcome` fields at the API layer. They do not claim to exercise writer/orchestration paths end-to-end unless a test explicitly calls that writer/orchestrator.

No test may:
- Set `external_executed = true` without `execution_mode = real` and `execution_state = succeeded`.
- Set `simulated = true` without `execution_mode = simulation`.
- Set `tracking_recorded = true` without `execution_mode = tracking_only` and `execution_state = succeeded`.

### API/read-model lifecycle shapes

1. **Observed-only**: create alert with no decision/event → verify `response_outcome: null` from alert API.
2. **Simulated queue action**: create alert → create decision with `simulation/selected` → append `simulation/succeeded/simulated=true` event → verify API returns correct shape.
3. **Manual tracking-only blocklist**: create alert → create tracking-only decision → append `tracking_only/succeeded/tracking_recorded=true` event → verify API returns `"Tracking only"` mode, `external_executed=false`.
4. **Playbook simulation step sequence**: create playbook execution → create execution-level decision with `simulation` mode → append step events → verify API returns step events attached to execution-level decision.
5. **Playbook awaiting approval**: create playbook execution → append `awaiting_approval` event → verify `execution_state = awaiting_approval` in API response.
6. **Approval denied/expired**: create approval request → deny or expire → append `blocked/approval_denied` event → verify `execution_state = blocked`, `reason_code = approval_denied` in API response.
7. **Notification simulated delivery**: create notification delivery attempt → create decision with `simulation/selected` → append `simulation/succeeded/simulated=true` event → verify API returns simulated mode.
8. **Guarded real notification success**: create notification delivery with explicit real execution evidence → append `real/succeeded/external_executed=true` event → verify `external_executed = true` in API response.
9. **Real-capable notification blocked/fail-closed**: simulate adapter fail-closed result → append `real/failed/external_executed=false` event → verify `external_executed = false` and `execution_state = failed` in API response.
10. **Cross-surface canonical facts**: create one decision/event linked to both a source IP and an incident → verify Source-IP Context API and SOC Command Center metrics API return the same canonical outcome facts.

### Regression tests

11. **Simulated never shown as real**: for any `simulated = true` event, verify that no API response surfaces `external_executed = true` for that event.
12. **Tracking-only never shown as enforcement**: for any `tracking_recorded = true` event, verify that `external_executed = false` in all API responses for that event, and that the canonical label from the API is `"Tracking only"`, not `"Real executed"`.

### Test file location

Add API/read-model integration tests as `tests/test_response_outcome_e2e.py` for compatibility with the child task runner, but test names and module docs must classify seeded canonical-row tests as integration tests rather than true E2E writer/orchestrator tests.

## Dependencies

- All Phases 1–9 must be implemented.
- `postgres_db` fixture must be available (it is in `conftest.py`).
- Representative seed volume for performance tests must be generated locally; no production data is used.
