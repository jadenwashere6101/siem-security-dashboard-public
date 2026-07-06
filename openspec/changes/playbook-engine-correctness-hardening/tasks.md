This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes. Section 1 reflects the verification work completed to write this spec. Section 2 lists this same spec's own implementation work — owned here, not deferred to another child spec — to be executed only in a separate, later, explicitly-requested implementation pass. No file under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/` is touched by creating this spec.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Confirm `engines/playbook_step_executor.py` does not import or call `core.soar_protected_targets` anywhere in its `block_ip` dispatch path.
- [x] 1.2 Confirm `engines/soar_action_worker.py` (the response-action queue path) does enforce the protected-target guard, establishing the parity gap.
- [x] 1.3 Confirm `notify_teams` is present in `engines/playbook_step_executor.py`'s `ADAPTER_ACTIONS` but absent from `engines/playbook_registry.py`'s `SUPPORTED_ACTIONS`, and confirm the executor checks `ADAPTER_ACTIONS` before `SUPPORTED_ACTIONS` at dispatch time.
- [x] 1.4 Confirm `attempt_count` is read in `core/playbook_store.py`'s `mark_stale_execution_for_recovery` but that its only setter, `update_playbook_execution_reliability_metadata`, has no callers anywhere in the codebase.
- [x] 1.5 Confirm `recovery_count` (not `attempt_count`) is the counter actually incremented on every stale recovery, establishing that the `max_attempts` give-up branch is unreachable.
- [x] 1.6 Record the three fixes, their rationale, alternatives considered, and rejected alternatives in `design.md`.

## 2. Implementation (this spec's own future work — not started, not deferred to another spec)

- [ ] 2.1 Add a `require_unprotected_target` (or equivalent) call to the playbook `block_ip` step handler in `engines/playbook_step_executor.py`, before the adapter dispatch, matching the queue path's enforcement.
- [ ] 2.2 Add a test asserting playbook `block_ip` is rejected/blocked for a protected-target IP, mirroring the equivalent existing queue-path test.
- [ ] 2.3 Introduce one canonical action-vocabulary constant combining the current `SUPPORTED_ACTIONS` and `ADAPTER_ACTIONS` action names; update `engines/playbook_registry.py` and `engines/playbook_step_executor.py` to both read from it.
- [ ] 2.4 Add `notify_teams` acceptance to definition-time validation via the canonical vocabulary change in 2.3.
- [ ] 2.5 Add a test confirming a `notify_teams` step is accepted at definition-save time and dispatches correctly at execution time.
- [ ] 2.6 Increment `attempt_count` inside `mark_stale_execution_for_recovery` at the point an execution is requeued to `pending`, alongside the existing `recovery_count` increment.
- [ ] 2.7 Add a test confirming an execution that repeatedly goes stale reaches `failed` once `attempt_count` reaches `max_attempts`, where today it would recover indefinitely.
- [ ] 2.8 Run the full existing playbook test suite (`tests/test_playbook_registry.py`, `tests/test_playbook_step_executor.py`, `tests/test_playbook_store.py`, `tests/test_soar_playbook_orchestrator.py`, `tests/test_soar_playbook_worker.py`) and confirm no regressions.
- [ ] 2.9 Land 2.1–2.2, 2.3–2.5, and 2.6–2.7 as three independently revertible commits/PRs, per the Migration Plan in `design.md`.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] No new playbooks, new step/action types, schema changes, schedules, branching, chaining, or evidence-collection work is introduced by this spec.
- [x] No change to the response-action queue path's own implementation — this spec only brings the playbook path to parity.
- [x] Do not commit.
