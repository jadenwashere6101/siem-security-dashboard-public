# Tasks: Unify Correlation Alerts With Modern SOAR Path

Implementation must be reviewed before code changes begin. Do not implement from this spec creation step.

## Pre-implementation Audit

- [x] Re-read `engines/correlation_engine.py` and document every current alert insert path.
- [x] Re-read `engines/ingest_engine.py` and document the current detection/correlation ordering.
- [x] Re-read all ingest routes that call `enqueue_committed_alerts()` and `create_pending_executions_for_committed_alerts()`.
- [x] Re-read `core/ip_helpers.execute_response_action()` and `core/ip_helpers.enqueue_response_action()`.
- [x] Re-read queue worker, approval, protected-target, retry, and dead-letter tests that depend on queue semantics.
- [x] Audit existing tests that assert correlation legacy `response_actions_log` behavior.

## Update Correlation Return Values

- [x] Change `generate_correlated_activity_alerts()` to return a list of created alert dictionaries instead of `True`/`False`.
- [x] Change `generate_targeted_correlation_alerts()` to return a list of created alert dictionaries instead of `None`.
- [x] Include at least `alert_id`, `source_ip`, `response_action`, and `severity` in each returned dictionary.
- [x] Preserve all existing correlation matching logic.
- [x] Preserve existing duplicate suppression for `correlated_activity`.
- [x] Preserve existing duplicate suppression for targeted correlation alert types.

## Update Ingest Collection/Handoff

- [x] Update `ingest_normalized_event()` to collect correlation-created alert dictionaries.
- [x] Use either the existing `alerts_created` list or a clearly named combined post-commit list.
- [x] Ensure detection-created alerts and correlation-created alerts are both returned to the ingest route for post-commit handling.
- [x] Preserve current detection-before-correlation ordering.
- [x] Ensure post-commit handoff still happens only after the ingest transaction commits.

## Remove Legacy Synchronous Response Call From Correlation Path

- [x] Remove correlation calls to `execute_response_action()` for newly created correlation alerts.
- [x] Stop writing `response_actions_log` from correlation alert creation.
- [x] Stop immediately updating correlation alert `response_status` to `executed`.
- [x] Ensure newly created correlation alerts keep pending response semantics compatible with modern queue processing.
- [x] Do not remove `execute_response_action()` globally; other manual/admin paths may still use it.

## Modern SOAR/Playbook Compatibility

- [x] Verify `enqueue_committed_alerts()` can enqueue returned correlation alert dictionaries without special cases.
- [x] Verify queue idempotency remains based on existing idempotency key behavior.
- [x] Verify queue workers still enforce leases, retries, approval gating, protected-target behavior, and dead-letter safety.
- [x] Verify `create_pending_executions_for_committed_alerts()` can schedule playbooks for correlation alert IDs.
- [x] Verify playbook duplicate suppression remains intact.
- [x] Do not change integration adapter behavior.
- [x] Do not enable real firewall execution.

## Update Tests

- [x] Update `tests/test_correlated_activity.py` for list return values and modern response status behavior.
- [x] Update `tests/test_targeted_correlation.py` for list return values and modern response status behavior.
- [x] Remove or rewrite assertions that require legacy synchronous `response_actions_log` rows at correlation creation time.
- [x] Add assertions that no legacy response log is written during correlation alert creation.
- [x] Update `tests/test_ingest_normalized_event.py` to prove correlation-created alerts are included in the post-commit alert list.
- [x] Update post-commit enqueue tests to prove correlation alerts are passed to `enqueue_committed_alerts()` after commit.
- [x] Add or update playbook orchestration tests to prove correlation alert IDs can create pending playbook executions through the existing duplicate-safe path.
- [x] Add regression tests for duplicate suppression of correlation alerts after the return contract change.

## Verification

- [x] Run `python3 -m py_compile engines/correlation_engine.py engines/ingest_engine.py routes/ingest_routes.py`.
- [x] Run `python3 -m pytest tests/test_correlated_activity.py -v`.
- [x] Run `python3 -m pytest tests/test_targeted_correlation.py -v`.
- [x] Run `python3 -m pytest tests/test_ingest_normalized_event.py -v`.
- [x] Run focused post-commit enqueue tests.
- [x] Run focused SOAR queue worker tests.
- [x] Run focused approval/protected-target tests.
- [x] Run focused playbook orchestration tests.
- [x] Run `git diff --check`.
- [x] Run `git status --short`.

## Safety Boundaries

- [x] Do not change detection rule logic.
- [x] Do not change correlation matching logic.
- [x] Do not change alert schemas.
- [x] Do not change database schema unless this OpenSpec change is updated and reviewed first.
- [x] Do not change integration adapter behavior.
- [x] Do not enable real firewall execution.
- [x] Do not weaken approval gates.
- [x] Do not remove dead-letter or retry safety.
- [x] Do not refactor broadly.
- [x] Do not change frontend unless proven necessary and separately reviewed.
- [x] Do not commit until reviewed.
