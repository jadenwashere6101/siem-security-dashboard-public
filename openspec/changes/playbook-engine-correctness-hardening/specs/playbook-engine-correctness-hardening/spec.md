## ADDED Requirements

### Requirement: Playbook Block-IP Protected-Target Enforcement
The playbook step executor SHALL enforce the same protected-target policy for the `block_ip` action that the response-action queue path already enforces, before dispatching to the firewall adapter.

#### Scenario: Protected target is not blocked via a playbook step
- **WHEN** a playbook execution reaches a `block_ip` step whose target IP is on the protected-target list
- **THEN** the step SHALL be rejected by the same guard the response-action queue path uses (`core.soar_protected_targets.require_unprotected_target` or equivalent), and SHALL NOT reach the firewall adapter dispatch.

#### Scenario: Non-protected target is unaffected
- **WHEN** a playbook execution reaches a `block_ip` step whose target IP is not on the protected-target list
- **THEN** the step SHALL proceed to the firewall adapter dispatch exactly as it does today, with no behavior change for non-protected targets.

### Requirement: Canonical Playbook Action Vocabulary
The playbook registry and the playbook step executor SHALL share one canonical set of recognized action names, so that definition-time validation and execution-time dispatch can never disagree about which actions are supported.

#### Scenario: `notify_teams` is accepted and dispatches correctly
- **WHEN** a playbook definition is saved with a step whose action is `notify_teams`
- **THEN** definition-time validation SHALL accept it, and execution-time dispatch SHALL route it to the Teams adapter exactly as the other notification actions are routed.

#### Scenario: An unsupported action is rejected consistently
- **WHEN** a playbook definition is saved with a step whose action is not in the canonical vocabulary
- **THEN** definition-time validation SHALL reject it, and this rejection SHALL be based on the same canonical vocabulary the executor uses for dispatch, not a separately-maintained list.

### Requirement: Reachable Stale-Execution Give-Up Path
The playbook execution's `attempt_count` SHALL increment each time a stale-leased execution is recovered and requeued, so that the existing `max_attempts` give-up behavior in stale-execution recovery is reachable.

#### Scenario: Execution gives up after exceeding max attempts
- **WHEN** a playbook execution's lease goes stale and is recovered `max_attempts` times in a row without making forward progress
- **THEN** the next stale-recovery evaluation SHALL mark the execution `failed` instead of requeuing it to `pending` again, consistent with the existing `attempt_count < max_attempts` branch condition in `mark_stale_execution_for_recovery`.

#### Scenario: Healthy multi-batch executions are not penalized
- **WHEN** a playbook execution proceeds through multiple normal processing batches without its lease ever going stale
- **THEN** `attempt_count` SHALL NOT increment from ordinary batch processing alone — only from an actual stale-lease recovery event.

<!-- No MODIFIED Requirements: no existing openspec/specs/ capability (response-action-queue-worker-rollout, soar-worker-orchestration) covers playbook step-execution correctness today, so this is purely additive. -->
