# Tasks: Unify Correlation Alerts With Modern SOAR Path

Implementation must be reviewed before code changes begin. Do not implement from this spec creation step.

## Pre-implementation Audit

- [ ] Re-read `engines/correlation_engine.py` and document every current alert insert path.
- [ ] Re-read `engines/ingest_engine.py` and document the current detection/correlation ordering.
- [ ] Re-read all ingest routes that call `enqueue_committed_alerts()` and `create_pending_executions_for_committed_alerts()`.
- [ ] Re-read `core/ip_helpers.execute_response_action()` and `core/ip_helpers.enqueue_response_action()`.
- [ ] Re-read queue worker, approval, protected-target, retry, and dead-letter tests that depend on queue semantics.
- [ ] Audit existing tests that assert correlation legacy `response_actions_log` behavior.

## Update Correlation Return Values

- [ ] Change `generate_correlated_activity_alerts()` to return a list of created alert dictionaries instead of `True`/`False`.
- [ ] Change `generate_targeted_correlation_alerts()` to return a list of created alert dictionaries instead of `None`.
- [ ] Include at least `alert_id`, `source_ip`, `response_action`, and `severity` in each returned dictionary.
- [ ] Preserve all existing correlation matching logic.
- [ ] Preserve existing duplicate suppression for `correlated_activity`.
- [ ] Preserve existing duplicate suppression for targeted correlation alert types.

## Update Ingest Collection/Handoff

- [ ] Update `ingest_normalized_event()` to collect correlation-created alert dictionaries.
- [ ] Use either the existing `alerts_created` list or a clearly named combined post-commit list.
- [ ] Ensure detection-created alerts and correlation-created alerts are both returned to the ingest route for post-commit handling.
- [ ] Preserve current detection-before-correlation ordering.
- [ ] Ensure post-commit handoff still happens only after the ingest transaction commits.

## Remove Legacy Synchronous Response Call From Correlation Path

- [ ] Remove correlation calls to `execute_response_action()` for newly created correlation alerts.
- [ ] Stop writing `response_actions_log` from correlation alert creation.
- [ ] Stop immediately updating correlation alert `response_status` to `executed`.
- [ ] Ensure newly created correlation alerts keep pending response semantics compatible with modern queue processing.
- [ ] Do not remove `execute_response_action()` globally; other manual/admin paths may still use it.

## Modern SOAR/Playbook Compatibility

- [ ] Verify `enqueue_committed_alerts()` can enqueue returned correlation alert dictionaries without special cases.
- [ ] Verify queue idempotency remains based on existing idempotency key behavior.
- [ ] Verify queue workers still enforce leases, retries, approval gating, protected-target behavior, and dead-letter safety.
- [ ] Verify `create_pending_executions_for_committed_alerts()` can schedule playbooks for correlation alert IDs.
- [ ] Verify playbook duplicate suppression remains intact.
- [ ] Do not change integration adapter behavior.
- [ ] Do not enable real firewall execution.

## Update Tests

- [ ] Update `tests/test_correlated_activity.py` for list return values and modern response status behavior.
- [ ] Update `tests/test_targeted_correlation.py` for list return values and modern response status behavior.
- [ ] Remove or rewrite assertions that require legacy synchronous `response_actions_log` rows at correlation creation time.
- [ ] Add assertions that no legacy response log is written during correlation alert creation.
- [ ] Update `tests/test_ingest_normalized_event.py` to prove correlation-created alerts are included in the post-commit alert list.
- [ ] Update post-commit enqueue tests to prove correlation alerts are passed to `enqueue_committed_alerts()` after commit.
- [ ] Add or update playbook orchestration tests to prove correlation alert IDs can create pending playbook executions through the existing duplicate-safe path.
- [ ] Add regression tests for duplicate suppression of correlation alerts after the return contract change.

## Verification

- [ ] Run `python3 -m py_compile engines/correlation_engine.py engines/ingest_engine.py routes/ingest_routes.py`.
- [ ] Run `python3 -m pytest tests/test_correlated_activity.py -v`.
- [ ] Run `python3 -m pytest tests/test_targeted_correlation.py -v`.
- [ ] Run `python3 -m pytest tests/test_ingest_normalized_event.py -v`.
- [ ] Run focused post-commit enqueue tests.
- [ ] Run focused SOAR queue worker tests.
- [ ] Run focused approval/protected-target tests.
- [ ] Run focused playbook orchestration tests.
- [ ] Run `git diff --check`.
- [ ] Run `git status --short`.

## Safety Boundaries

- [ ] Do not change detection rule logic.
- [ ] Do not change correlation matching logic.
- [ ] Do not change alert schemas.
- [ ] Do not change database schema unless this OpenSpec change is updated and reviewed first.
- [ ] Do not change integration adapter behavior.
- [ ] Do not enable real firewall execution.
- [ ] Do not weaken approval gates.
- [ ] Do not remove dead-letter or retry safety.
- [ ] Do not refactor broadly.
- [ ] Do not change frontend unless proven necessary and separately reviewed.
- [ ] Do not commit until reviewed.

