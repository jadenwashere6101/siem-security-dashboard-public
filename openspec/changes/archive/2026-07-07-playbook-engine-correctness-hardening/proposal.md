## Why

The playbook audit (`audit-soar-playbook-library`) and the automation-path consolidation decision (`soar-automation-path-consolidation-decision`) both depend on the playbook engine being correct on its own terms before any new content or capability is built on it. Three specific, verified bugs currently sit in the engine: (1) the playbook `block_ip` step never calls `soar_protected_targets.require_unprotected_target`, unlike the equivalent action on the response-action queue path — this is also Acceptance Criterion 1 the consolidation decision requires before that path can ever be retired; (2) `notify_teams` is dispatchable by the executor (`ADAPTER_ACTIONS`, `engines/playbook_step_executor.py:43`) but is absent from the registry's `SUPPORTED_ACTIONS` (`engines/playbook_registry.py:11-21`), so the two modules disagree about the action vocabulary; (3) `playbook_executions.attempt_count` is fully modeled in schema and read by `mark_stale_execution_for_recovery` (`core/playbook_store.py:551-560`), but is never incremented anywhere in the codebase — its setter, `update_playbook_execution_reliability_metadata`, has zero callers — so the "give up after `max_attempts`" branch is unreachable and a permanently-stale-recovering execution can loop indefinitely.

## What Changes

- Add the protected-target guard to the playbook `block_ip` step, matching the enforcement already present on the response-action queue path.
- Establish one canonical action-name vocabulary shared by `engines/playbook_registry.py` (definition-time validation) and `engines/playbook_step_executor.py` (execution-time dispatch), and add `notify_teams` to it so both modules agree.
- Wire `attempt_count` so it increments at the point an execution is stale-recovered, making the existing `max_attempts` give-up branch in `mark_stale_execution_for_recovery` reachable.
- No new playbooks, no new step types, no schema changes (the `attempt_count` column and its constraints already exist), no schedules, chaining, branching, or evidence-collection work.

## Capabilities

### New Capabilities
- `playbook-engine-correctness-hardening`: records the correctness requirements for the playbook step executor and registry — protected-target enforcement on `block_ip`, a single canonical action vocabulary shared by registry and executor, and a reachable `attempt_count`/`max_attempts` give-up path. No existing spec under `openspec/specs/` (`response-action-queue-worker-rollout`, `soar-worker-orchestration`) covers this domain, so this is additive, not a modification of either.

### Modified Capabilities
(none)

## Impact

- **Affected code (future implementation phase, not this proposal step):** `engines/playbook_step_executor.py`, `engines/playbook_registry.py`, `core/playbook_store.py`.
- **Affected artifacts (this step):** adds `openspec/changes/playbook-engine-correctness-hardening/` as a new, unimplemented child change under the `soar-playbook-modernization-roadmap` parent.
- **Downstream effect:** satisfies Acceptance Criterion 1 (`block_ip` protected-target parity) of `soar-automation-path-consolidation-decision`; unblocks `Core Playbook Pack v1` (playbooks can safely use `block_ip` and `notify_teams`) and `Conditional Branching Primitive` (built on a hardened, non-dead-logic base).
- **Dependencies:** `audit-soar-playbook-library` (source of all three findings); soft dependency on `soar-automation-path-consolidation-decision` for where the protected-target guard should eventually live if the queue path is ever retired — this change adds the guard call directly in the playbook step executor regardless, since the guard function itself (`core/soar_protected_targets.require_unprotected_target`) already exists and is path-agnostic.
