# Proposal: Unify Correlation Alerts With Modern SOAR Path

## Problem

Correlation alerts currently use a different response path than normal detection alerts. Detection alerts are returned through `alerts_created` and handed off after commit to the modern SOAR queue and playbook scheduling flow, while correlation alerts are created inside the ingest transaction and immediately call the legacy synchronous `execute_response_action()` helper.

That makes correlation alert handling harder to reason about: correlation alerts appear response-executed, but they bypass `response_actions_queue`, queue idempotency, worker leasing, approval handling, retry/dead-letter safety, and post-commit playbook scheduling.

## Goals

- Move correlation alert response handling to the same modern post-commit SOAR handoff used by detection alerts.
- Preserve existing correlation alert creation semantics and matching logic.
- Preserve existing correlation duplicate suppression.
- Preserve queue idempotency, playbook duplicate suppression, approval gating, protected-target behavior, retries, leases, and dead-letter safety.
- Stop calling legacy synchronous `execute_response_action()` from the correlation creation path for newly created correlation alerts.
- Ensure correlation-created alerts can be enqueued and scheduled for playbooks after the ingest transaction commits.
- Keep response status semantics accurate: a correlation alert should not be marked `executed` merely because correlation fired.

## Non-Goals

- Do not change detection rule logic.
- Do not change correlation matching logic.
- Do not change alert schemas or database schema unless implementation proves a schema change is unavoidable.
- Do not change integration adapter behavior.
- Do not enable real firewall execution.
- Do not weaken approval gates or protected-target checks.
- Do not remove retry, dead-letter, worker lease, or idempotency safety.
- Do not add frontend work unless implementation proves it is required.
- Do not broadly refactor ingest, SOAR, playbook, or correlation modules.

## User-Visible Behavior

Correlation alerts should still be created for the same situations and should keep the same alert types:

- `correlated_activity`
- `web_to_app_attack_pattern`
- `spray_then_success_pattern`
- `cloud_app_error_pattern`

The visible response status may change for newly created correlation alerts. Instead of immediately showing `response_status='executed'` because the legacy helper wrote a simulated log, correlation alerts should follow the modern lifecycle: created with a pending response state, then queued, worked, approved if required, retried, skipped, failed, or completed through the existing SOAR systems.

Queue visibility, playbook execution visibility, approval visibility, and dead-letter visibility should become consistent with normal detection alerts.

## Risks

- Existing tests assert legacy synchronous `response_actions_log` rows and `response_status='executed'` for correlation alerts; those tests will need careful updates.
- Changing return values from correlation functions may affect ingest orchestration assumptions.
- Adding correlation alerts to post-commit handoff may create new queue rows or playbook executions for alert types that were previously SOAR-invisible.
- Mis-ordering transaction boundaries could enqueue uncommitted alerts or lose correlation alerts after commit.
- Removing legacy response logging without replacing it through modern queue execution could temporarily reduce response audit visibility.
- Playbook matching may already recognize correlation alert types, so newly scheduling them may trigger pending executions that did not previously exist.

## Rollback Plan

Keep the implementation small and reversible:

- Make correlation alert collection explicit, preferably through return contracts rather than hidden side effects.
- Avoid schema changes unless absolutely required.
- If queue/playbook handoff for correlation alerts causes regressions, revert the correlation return contract and ingest collection changes to restore the legacy behavior.
- Keep tests for legacy behavior updated in a way that clearly documents the new intended behavior, so rollback is limited to correlation/ingest response path files and focused tests.

