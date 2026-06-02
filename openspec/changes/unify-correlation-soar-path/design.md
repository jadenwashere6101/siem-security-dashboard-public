# Design: Unify Correlation Alerts With Modern SOAR Path

## Current Flow

Normal detection flow:

1. `ingest_normalized_event()` inserts the event.
2. A detection function may insert an alert.
3. The detection function returns an alert dictionary containing fields such as `alert_id`, `source_ip`, `response_action`, and `severity`.
4. `ingest_normalized_event()` returns `alerts_created`.
5. The ingest route commits the transaction.
6. The ingest route calls `enqueue_committed_alerts(alerts_created, conn)`.
7. The ingest route calls incident creation and playbook scheduling using the same committed alert list.

Current correlation flow:

1. `ingest_normalized_event()` calls correlation after detection alert creation.
2. `generate_correlated_activity_alerts()` may insert `correlated_activity`.
3. `generate_targeted_correlation_alerts()` may insert one or more targeted correlation alerts.
4. Correlation functions call `execute_response_action()` synchronously inside the ingest transaction.
5. `execute_response_action()` writes `response_actions_log` and returns `executed`.
6. Correlation updates `alerts.response_status` to `executed`.
7. Generic correlation returns `True` or `False`; targeted correlation effectively returns `None`.
8. Correlation-created alerts are not included in `alerts_created`, so they are not passed to post-commit queue enqueue or playbook scheduling.

## Proposed Flow

Correlation should keep the same matching and alert insertion logic, but return created alert dictionaries compatible with the modern post-commit handoff.

Proposed ingest flow:

1. Detection creates and returns detection alert dictionaries as today.
2. `ingest_normalized_event()` calls correlation for source IPs from detection results.
3. Correlation functions return created correlation alert dictionaries.
4. `ingest_normalized_event()` appends those dictionaries to a combined post-commit list.
5. The ingest route commits once after event/detection/correlation alert creation.
6. The ingest route passes the combined committed alert list to:
   - `enqueue_committed_alerts()`
   - incident creation if applicable
   - `create_pending_executions_for_committed_alerts()`
7. Queue workers, approval flow, retries, leases, and dead-letter handling process correlation alerts through the same modern path as detection alerts.

The combined list can be named `alerts_created` if the contract remains clear, or a more explicit name such as `post_commit_alerts` can be introduced in a narrow way.

## Alert Return Contract

Each newly created correlation alert should return a dictionary with the same minimum fields used by modern handoff:

- `alert_id`
- `source_ip`
- `response_action`
- `severity`

Optional fields may include:

- `alert_type`
- `source`
- `source_type`

Generic correlation:

- Return `[]` when no alert is created.
- Return `[alert_dict]` when `correlated_activity` is created.

Targeted correlation:

- Return `[]` when no targeted alert is created.
- Return one alert dictionary per created targeted correlation alert.
- Preserve the possibility that multiple targeted correlation alerts may be created in one pass.

Avoid returning booleans for new code paths. If backwards compatibility is needed during implementation, add wrappers or update tests deliberately rather than overloading return types.

## Transaction Boundary/Post-Commit Behavior

Correlation alert insertion should remain inside the ingest database transaction so detection and correlation alert creation stay atomic with the event insert.

Modern SOAR handoff must remain post-commit:

- Do not enqueue response actions before committing the ingest transaction.
- Do not create playbook executions before committing the ingest transaction.
- Do not rely on uncommitted correlation alert IDs from a separate connection.

If post-commit enqueue fails, preserve the existing ingest route behavior: the ingest result remains committed and the enqueue failure is logged.

## Response Status Behavior

Correlation should no longer set `response_status='executed'` just because an alert was created.

Preferred behavior:

- Correlation alert insert sets `response_action` as before.
- Correlation alert insert sets `response_status='pending'`, matching detection alert creation semantics.
- Queue/worker/playbook systems update downstream execution status through existing mechanisms.

Do not create a `response_actions_log` row at correlation creation time. Response logs should come from the modern execution path.

## Queue/Playbook Handoff Behavior

Correlation alerts included in the combined post-commit list should be eligible for:

- `enqueue_committed_alerts()`
- `response_actions_queue` idempotency
- worker leasing
- approval gating
- protected-target checks
- retry and dead-letter behavior
- playbook matching and pending execution scheduling

The implementation must not directly call adapters or execute real firewall actions from correlation.

## Duplicate/Idempotency Considerations

Preserve existing duplicate suppression:

- `correlated_activity` should still skip creation when an open `correlated_activity` exists for the same `source_ip`.
- Targeted correlation should still skip creation when an open alert of the targeted correlation type exists for the same `source_ip`.

Modern queue idempotency should continue to be based on the existing queue idempotency key behavior. Since each correlation alert has a stable committed `alert_id`, duplicate queue rows for the same alert/action should be prevented by the existing `ON CONFLICT DO NOTHING` path.

Playbook duplicate suppression should continue to use existing playbook execution duplicate prevention. Do not create a special correlation-only duplicate system.

## Test Strategy

Update tests in small groups:

- Correlation unit tests:
  - Assert created correlation alert dictionaries are returned.
  - Assert alert rows still have the same alert type, severity, message, source, source type, location, reputation, and response action.
  - Assert response status is no longer immediately `executed`.
  - Assert no legacy synchronous `response_actions_log` row is created at correlation creation time.
  - Assert duplicate suppression still works.

- Targeted correlation tests:
  - Assert each targeted correlation type returns an alert dictionary when created.
  - Assert multiple targeted alerts can be returned if multiple rules match.
  - Assert no legacy synchronous response log is written.

- Ingest tests:
  - Assert correlation-created alerts are included in the post-commit handoff list.
  - Assert detection still runs before correlation.
  - Assert correlation matching logic is unchanged.

- Post-commit SOAR tests:
  - Assert `enqueue_committed_alerts()` receives correlation-created alerts after commit.
  - Assert queue duplicate/idempotency behavior still applies.
  - Assert playbook scheduling sees correlation alert IDs.
  - Assert enqueue failures remain post-commit and do not roll back alert creation.

- Regression tests:
  - Run focused detection, correlation, queue, approval, playbook orchestration, and ingest route suites.

## Migration/Schema Decision

No schema change is expected.

The existing `alerts` table already stores correlation alerts. The existing `response_actions_queue`, `response_actions_log`, playbook execution, approval, retry, lease, and dead-letter schemas should be reused.

If implementation discovers that a schema change is needed, stop and update this OpenSpec change before implementing that schema change.

